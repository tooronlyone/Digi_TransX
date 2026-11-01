from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from threading import Event

import pytest
from auth import credential_changes, routes as auth_routes, helpers as auth_helpers
from supabase_auth.errors import AuthApiError
from shared.validation import finite_decimal
from scripts import reconcile_password_change as recovery_cli
from tests.remediation_harness import remediation_database_url,remediation_env


@pytest.mark.parametrize("value",["NaN","Infinity","-Infinity",True,None,"1e999999",[],{}])
def test_nonfinite_and_wrong_numeric_inputs_are_validation_errors(value):
    with pytest.raises(ValueError):
        finite_decimal(value,"Amount",scale=2)


def test_password_update_revokes_every_device_before_provider_io(remediation_env):
    env=remediation_env
    user=env.user()
    client_a,_=env.login(user)
    client_b,_=env.login(user)
    assert client_a.get("/auth/me").status_code==200
    observed=[]
    def provider(auth_id,password):
        with env.db() as db:
            assert db.execute("SELECT count(*) AS n FROM user_sessions WHERE user_id=%s AND revoked_at IS NULL",(user["id"],)).fetchone()["n"]==0
            assert db.execute("SELECT count(*) AS n FROM trusted_devices WHERE user_id=%s AND revoked_at IS NULL",(user["id"],)).fetchone()["n"]==0
        observed.append((auth_id,password))
    credential_changes.execute_password_change(user["id"],user["auth_id"],"new-password","password_reset",provider)
    assert observed==[(user["auth_id"],"new-password")]
    assert client_a.get("/auth/me").status_code==401
    assert client_b.get("/auth/me").status_code==401
    with env.db() as db:
        row=db.execute("SELECT credentials_version,password_change_pending FROM users WHERE id=%s",(user["id"],)).fetchone()
        assert row=={"credentials_version":2,"password_change_pending":False}


def test_returned_provider_failure_cannot_restore_old_sessions(remediation_env):
    env=remediation_env
    user=env.user()
    client,_=env.login(user)
    def unavailable(*args):
        raise RuntimeError("provider outcome unavailable")
    with pytest.raises(credential_changes.PasswordProviderUpdateFailed):
        credential_changes.execute_password_change(user["id"],user["auth_id"],"new-password","password_changed",unavailable)
    assert client.get("/auth/me").status_code==401
    with env.db() as db:
        assert db.execute("SELECT password_change_pending FROM users WHERE id=%s",(user["id"],)).fetchone()["password_change_pending"] is True
    calls=[]
    with pytest.raises(credential_changes.CredentialChangeUnavailable):
        credential_changes.execute_password_change(user["id"],user["auth_id"],"retry-password","password_reset",lambda *a:calls.append(a))
    assert calls==[]


def test_failed_finalization_requires_explicit_reconciliation_without_replaying_old_sessions(remediation_env):
    env=remediation_env
    user=env.user()
    client,_=env.login(user)
    def fail_finalization(db):
        raise RuntimeError("commit could not be completed")
    with pytest.raises(RuntimeError):
        credential_changes.execute_password_change(user["id"],user["auth_id"],"password-one","password_reset",lambda *a:None,finalize=fail_finalization)
    with pytest.raises(credential_changes.CredentialChangeUnavailable):
        credential_changes.execute_password_change(user["id"],user["auth_id"],"password-two","password_reset",lambda *a:None)
    assert client.get("/auth/me").status_code==401


def test_confirmed_provider_rejection_allows_a_new_verified_attempt_without_old_sessions(remediation_env):
    env=remediation_env
    user=env.user()
    client,_=env.login(user)
    def reject(*args):
        raise AuthApiError("Password rejected",422,"weak_password")
    with pytest.raises(credential_changes.PasswordProviderUpdateFailed) as raised:
        credential_changes.execute_password_change(user["id"],user["auth_id"],"rejected-password","password_changed",reject)
    assert raised.value.reconciliation_required is False
    with env.db() as db:
        assert db.execute("SELECT password_change_pending FROM users WHERE id=%s",(user["id"],)).fetchone()["password_change_pending"] is False
    credential_changes.execute_password_change(user["id"],user["auth_id"],"accepted-password","password_reset",lambda *a:None)
    assert client.get("/auth/me").status_code==401


def test_concurrent_password_changes_call_the_provider_once(remediation_env):
    env=remediation_env
    user=env.user()
    entered,release=Event(),Event()
    def provider(*args):
        entered.set()
        assert release.wait(10)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first=pool.submit(credential_changes.execute_password_change,user["id"],user["auth_id"],"password-one","password_reset",provider)
        assert entered.wait(10)
        try:
            with pytest.raises(credential_changes.CredentialChangeUnavailable):
                credential_changes.execute_password_change(user["id"],user["auth_id"],"password-two","password_reset",lambda *a:pytest.fail("Competing provider call"))
        finally:
            release.set()
        first.result(timeout=10)


def test_operator_reconciliation_requires_exact_generation_and_keeps_old_sessions_revoked(remediation_env,monkeypatch):
    env=remediation_env
    monkeypatch.setattr(recovery_cli,"open_db",env.db)
    user=env.user()
    client,_=env.login(user)
    def unavailable(*args):
        raise TimeoutError("Provider outcome is unknown")
    with pytest.raises(credential_changes.PasswordProviderUpdateFailed):
        credential_changes.execute_password_change(user["id"],user["auth_id"],"new-password","password_reset",unavailable)
    with pytest.raises(credential_changes.CredentialChangeUnavailable):
        recovery_cli.reconcile(user["id"],2,"support-ticket-123")
    recovery_cli.reconcile(user["id"],1,"support-ticket-123")
    with env.db() as db:
        assert db.execute("SELECT password_change_pending,credentials_version FROM users WHERE id=%s",(user["id"],)).fetchone()=={"password_change_pending":False,"credentials_version":2}
        assert db.execute("SELECT count(*) AS n FROM user_action_logs WHERE user_id=%s AND action_name='password_change_reconciled'",(str(user["id"]),)).fetchone()["n"]==1
    assert client.get("/auth/me").status_code==401


@pytest.mark.parametrize("path,payload",[
    ("/auth/forgot-password",{"loginId":123}),
    ("/auth/password-reset/verify-otp",{"loginId":[],"otp":"123456"}),
    ("/auth/reset-password",{"reset_token":"token","new_password":123}),
    ("/auth/reset-password",["not","an","object"]),
])
def test_password_reset_wrong_scalar_types_are_400(remediation_env,path,payload):
    assert remediation_env.app.test_client().post(path,json=payload).status_code==400


def test_login_rejects_password_proof_from_prior_credential_generation(remediation_env,monkeypatch):
    env=remediation_env
    user=env.user()
    def verify(*args,**kwargs):
        with env.db() as db:
            db.execute("UPDATE users SET credentials_version=credentials_version+1 WHERE id=%s",(user["id"],))
        return True
    monkeypatch.setattr(auth_routes,"supabase_verify_password",verify)
    response=env.app.test_client().post("/auth/login",json={"loginId":user["email"],"password":"old-password"})
    assert response.status_code==401
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM user_sessions WHERE user_id=%s",(user["id"],)).fetchone()["n"]==0


def test_missing_access_proof_is_persisted_lock_not_a_pool_error(remediation_env):
    env=remediation_env
    user=env.user()
    client,session_id=env.login(user)
    client.delete_cookie("dtx_access_proof")
    assert client.get("/api/profile").status_code==423
    with env.db() as db:
        assert db.execute("SELECT access_locked FROM user_sessions WHERE session_id=%s",(session_id,)).fetchone()["access_locked"] is True


def test_logout_event_failure_rolls_back_and_returns_retryable_error(remediation_env,monkeypatch):
    env=remediation_env
    user=env.user()
    client,session_id=env.login(user)
    writer=auth_routes.write_security_event
    def failed_event(*args,**kwargs):
        raise RuntimeError("Synthetic mandatory event failure")
    monkeypatch.setattr(auth_routes,"write_security_event",failed_event)
    response=client.post("/auth/logout",headers=env.headers)
    assert response.status_code==503 and response.json["success"] is False
    assert not response.headers.getlist("Set-Cookie")
    assert client.get("/auth/me").status_code==200
    with env.db() as db:
        assert db.execute("SELECT revoked_at FROM user_sessions WHERE session_id=%s",(session_id,)).fetchone()["revoked_at"] is None
    monkeypatch.setattr(auth_routes,"write_security_event",writer)
    assert client.post("/auth/logout",headers=env.headers).status_code==200
    assert client.get("/auth/me").status_code==401


def test_logout_authority_database_outage_is_retryable_not_reported_as_expired_session(remediation_env,monkeypatch):
    env=remediation_env
    user=env.user()
    client,session_id=env.login(user)
    def unavailable():
        raise RuntimeError("Synthetic database outage; no credentials")
    monkeypatch.setattr(auth_helpers,"open_db",unavailable)
    response=client.post("/auth/logout",headers=env.headers)
    assert response.status_code==503 and response.json["code"]=="authentication_service_unavailable"
    assert not response.headers.getlist("Set-Cookie")
    with env.db() as db:
        assert db.execute("SELECT revoked_at FROM user_sessions WHERE session_id=%s",(session_id,)).fetchone()["revoked_at"] is None
    monkeypatch.setattr(auth_helpers,"open_db",env.db)
    assert client.post("/auth/logout",headers=env.headers).status_code==200
    assert client.get("/auth/me").status_code==401


def test_malformed_authentication_cookie_still_returns_401(remediation_env):
    env=remediation_env
    client,_=env.login(env.user())
    client.set_cookie("dtx_device_token","invalid")
    assert client.get("/auth/me").status_code==401


def _fuel_pump(env,stock="10"):
    user=env.user("fuel_station_manager")
    client,_=env.login(user)
    response=client.post("/api/fuelstation/pumps",headers=env.headers,json={
        "pump_number":"Test pump","fuel_type":"diesel","price_per_liter":"100.00",
        "tank_capacity_liters":"100.00","current_stock_liters":stock,
    })
    assert response.status_code==200,response.json
    return user,client,response.json["pump_id"]


def test_fuel_sale_cannot_oversell_or_override_stored_rate(remediation_env):
    env=remediation_env
    user,client,pump_id=_fuel_pump(env)
    payload={"pump_id":pump_id,"vehicle_plate":"TEST-123","liters":"6","price_per_liter":"0.01"}
    response=client.post("/api/fuelstation/dispense",headers=env.headers,json=payload)
    assert response.status_code==200,response.json
    assert response.json["receipt"]["total_pkr"]==600
    assert client.post("/api/fuelstation/dispense",headers=env.headers,json=payload).status_code==409
    with env.db() as db:
        assert db.execute("SELECT current_stock_liters FROM fuel_station_pumps WHERE id=%s",(pump_id,)).fetchone()["current_stock_liters"]==4
        assert db.execute("SELECT count(*) AS n FROM fuel_station_dispenses WHERE user_id=%s",(user["id"],)).fetchone()["n"]==1


def test_concurrent_fuel_sales_commit_only_one_available_stock_claim(remediation_env):
    env=remediation_env
    user,_,pump_id=_fuel_pump(env)
    clients=[env.login(user)[0] for _ in range(2)]
    barrier=Barrier(2)
    def sale(client):
        barrier.wait(timeout=10)
        return client.post("/api/fuelstation/dispense",headers=env.headers,
                           json={"pump_id":pump_id,"vehicle_plate":"RACE-123","liters":"7"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(sale,clients))==[200,409]


@pytest.mark.parametrize("value",["NaN","Infinity","-1","0.001"])
def test_fuel_rejects_nonfinite_negative_and_unsupported_quantity_scale(remediation_env,value):
    env=remediation_env
    _,client,pump_id=_fuel_pump(env)
    assert client.post("/api/fuelstation/dispense",headers=env.headers,
                       json={"pump_id":pump_id,"vehicle_plate":"INVALID-1","liters":value}).status_code==400


def _product(env,client,name="Item",price="1.00",stock="6.000",unit="piece"):
    response=client.post("/api/shopkeeper/products",headers=env.headers,
                         json={"name":name,"price":price,"stock_quantity":stock,"unit":unit})
    assert response.status_code==201,response.json
    return response.json["data"]["id"]


def test_pos_merges_duplicate_product_before_stock_validation(remediation_env):
    env=remediation_env
    user=env.user("shopkeeper")
    client,_=env.login(user)
    product_id=_product(env,client)
    body={"amount_paid":"10.00","items":[{"product_id":product_id,"quantity":4},{"product_id":product_id,"quantity":4}]}
    assert client.post("/api/shopkeeper/sales",headers=env.headers,json=body).status_code==409
    body["items"][0]["quantity"]=2
    body["items"][1]["quantity"]=3
    response=client.post("/api/shopkeeper/sales",headers=env.headers,json=body)
    assert response.status_code==201,response.json
    assert len(response.json["data"]["items"])==1
    assert response.json["data"]["items"][0]["quantity"]==5
    with env.db() as db:
        assert db.execute("SELECT stock_quantity FROM shop_products WHERE id=%s",(product_id,)).fetchone()["stock_quantity"]==1


def test_pos_rounded_lines_equal_receipt_and_paid_amount(remediation_env):
    env=remediation_env
    client,_=env.login(env.user("shopkeeper"))
    ids=[_product(env,client,name=f"Liquid {i}",price="0.01",unit="liter") for i in range(2)]
    response=client.post("/api/shopkeeper/sales",headers=env.headers,json={
        "amount_paid":"0.02","items":[{"product_id":p,"quantity":"0.500"} for p in ids],
    })
    assert response.status_code==201,response.json
    data=response.json["data"]
    assert sum(Decimal(str(item["subtotal"])) for item in data["items"])==Decimal("0.02")
    assert data["total_amount"]==0.02 and data["change_amount"]==0


@pytest.mark.parametrize("overrides",[
    {"liters":"100000000"},
    {"price_per_liter":"100000000"},
    {"liters":"1000000","price_per_liter":"1000000"},
    {"trip_distance_km":"100000000"},
    {"odometer_km":"10000000000"},
    {"liters":"0.01","trip_distance_km":"100"},
    {"trip_distance_km":"NaN"},
    {"fuel_date":"not-a-date"},
    {"assignment_id":0},
    {"pump_name":"x"*151},
])
def test_driver_fuel_log_rejects_database_overflow_before_insert(remediation_env,overrides):
    env=remediation_env
    user=env.user("driver")
    client,_=env.login(user)
    payload={"pump_name":"Test station","city":"Test city","liters":"1.00","price_per_liter":"100.00",**overrides}
    response=client.post("/api/driver/fuel-logs",headers=env.headers,json=payload)
    assert response.status_code==400,response.json
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM driver_fuel_logs WHERE driver_user_id=%s",(user["id"],)).fetchone()["n"]==0


def test_driver_fuel_log_rounds_half_up_and_returns_numeric_average(remediation_env):
    env=remediation_env
    user=env.user("driver")
    client,_=env.login(user)
    response=client.post("/api/driver/fuel-logs",headers=env.headers,json={
        "pump_name":"Test station","city":"Test city","liters":"0.50","price_per_liter":"0.01","trip_distance_km":"1.00",
    })
    assert response.status_code==200,response.json
    assert response.json["fuel_average_km_per_liter"]==2.0
    with env.db() as db:
        row=db.execute("SELECT total_amount,fuel_average_km_per_liter FROM driver_fuel_logs WHERE id=%s",(response.json["log_id"],)).fetchone()
        assert row=={"total_amount":0.01,"fuel_average_km_per_liter":2.0}
