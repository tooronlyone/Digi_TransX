"""Driver consent, ownership, reputation and concurrency on isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import psycopg2
import pytest

from tests.remediation_harness import remediation_database_url, remediation_env


def _driver(env):
    user = env.user("driver")
    code = "DRV-" + uuid4().hex[:12].upper()
    with env.db() as db:
        db.execute("INSERT INTO driver_profiles(user_id,unique_driver_id,license_number) VALUES(%s,%s,'TEST-LICENSE')",
                   (user["id"],code))
        db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) VALUES(%s,'driver',10000,0,10000,true)",(user['id'],))
    return user,code


def _graph(env, *, owner=None, driver=None, kind="one_time", truck_id=None, fare="1000"):
    owner = owner or env.user("logistics_provider")
    driver,code = driver or _driver(env)
    customer = env.user()
    with env.db() as db:
        if truck_id is None:
            truck_id = db.execute(
                "INSERT INTO vehicles(owner_user_id,truck_number,chassis_number,truck_type,capacity_tons,main_use,status) "
                "VALUES(%s,%s,%s,'Cargo',10,'Cargo','active') RETURNING id",
                (owner["id"],uuid4().hex,uuid4().hex),
            ).fetchone()["id"]
        if kind == "one_time":
            shipment_id = db.execute(
                "INSERT INTO shipments(client_user_id,pickup_city,dropoff_city,pickup_date,pickup_time,goods_type,goods_weight_tons,seeker_kind_snapshot,status) "
                "VALUES(%s,'Test A','Test B',CURRENT_DATE,'10:00','Test goods',1,'business','ready_to_start') RETURNING id",
                (customer["id"],),
            ).fetchone()["id"]
            bid_id = db.execute(
                "INSERT INTO shipment_bids(order_id,transporter_user_id,truck_id,bid_price,status) VALUES(%s,%s,%s,%s,'accepted') RETURNING id",
                (shipment_id,owner["id"],truck_id,fare),
            ).fetchone()["id"]
            trip_id = db.execute(
                "INSERT INTO shipment_trips(order_id,accepted_bid_id,transporter_user_id,truck_id,status) VALUES(%s,%s,%s,%s,'ready_to_start') RETURNING id",
                (shipment_id,bid_id,owner["id"],truck_id),
            ).fetchone()["id"]
        else:
            post_id = db.execute(
                "INSERT INTO agreement_posts(client_user_id,title,cargo_type,service_area,status) VALUES(%s,'Test contract','Test goods','Test area','active') RETURNING id",
                (customer["id"],),
            ).fetchone()["id"]
            agreement_id = db.execute(
                "INSERT INTO agreements(post_id,client_user_id,duration_months,cargo_type,service_area,start_date,end_date) "
                "VALUES(%s,%s,1,'Test goods','Test area',CURRENT_DATE,CURRENT_DATE+30) RETURNING id",
                (post_id,customer["id"]),
            ).fetchone()["id"]
            agreement_truck_id = db.execute(
                "INSERT INTO agreement_trucks(agreement_id,truck_id,transporter_user_id,per_km_rate,minimum_monthly_guarantee) VALUES(%s,%s,%s,10,100) RETURNING id",
                (agreement_id,truck_id,owner["id"]),
            ).fetchone()["id"]
            trip_id = db.execute(
                "INSERT INTO agreement_trips(agreement_id,agreement_truck_id,truck_id,transporter_user_id,pickup_description,trip_date,status) "
                "VALUES(%s,%s,%s,%s,'Test pickup',CURRENT_DATE,'in_progress') RETURNING id",
                (agreement_id,agreement_truck_id,truck_id,owner["id"]),
            ).fetchone()["id"]
    owner_client,_ = env.login(owner)
    driver_client,_ = env.login(driver)
    payload = {"unique_driver_id":code,"truck_id":truck_id,"offer_amount":"100.00",
               "agreement_trip_id" if kind == "agreement" else "trip_id":trip_id}
    return SimpleNamespace(owner=owner,driver=driver,driver_code=code,customer=customer,owner_client=owner_client,
                           driver_client=driver_client,truck_id=truck_id,trip_id=trip_id,kind=kind,payload=payload)


def _invite(env, graph):
    response = graph.owner_client.post("/api/transporter/dispatch-driver",headers=env.headers,json=graph.payload)
    assert response.status_code == 200,response.json
    return response.json["assignment_id"]


def _accept(env, graph, assignment_id):
    response = graph.driver_client.post(f"/api/driver/trips/{assignment_id}/respond",headers=env.headers,json={"action":"accept"})
    assert response.status_code == 200,response.json


def _set_status(env, graph, status):
    table = "agreement_trips" if graph.kind == "agreement" else "shipment_trips"
    with env.db() as db:
        db.execute(f"UPDATE {table} SET status=%s WHERE id=%s",(status,graph.trip_id))


def _review_payload(graph, assignment_id, **extra):
    return {"assignment_id":assignment_id,"driver_user_id":graph.driver["id"],"rating":5,**extra}


@pytest.mark.parametrize("kind",["one_time","agreement"])
def test_dispatch_requires_owned_trip_and_matching_truck(remediation_env,kind):
    env = remediation_env
    graph = _graph(env,kind=kind)
    outsider = env.user("logistics_provider")
    outsider_graph = _graph(env,owner=outsider,kind=kind)
    forged = {**graph.payload,"agreement_trip_id" if kind == "agreement" else "trip_id":outsider_graph.trip_id}
    response = graph.owner_client.post("/api/transporter/dispatch-driver",headers=env.headers,json=forged)
    assert response.status_code == 404
    mismatched = {**graph.payload,"truck_id":outsider_graph.truck_id}
    assert graph.owner_client.post("/api/transporter/dispatch-driver",headers=env.headers,json=mismatched).status_code == 404
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM driver_trip_assignments WHERE transporter_user_id=%s",(graph.owner["id"],)).fetchone()["n"] == 0


@pytest.mark.parametrize("extra",[{"trip_id":None},{"agreement_trip_id":1},{"trip_id":True},{"truck_id":0}])
def test_dispatch_rejects_missing_ambiguous_or_wrong_identifier_shape(remediation_env,extra):
    env = remediation_env
    graph = _graph(env)
    assert graph.owner_client.post("/api/transporter/dispatch-driver",headers=env.headers,json={**graph.payload,**extra}).status_code == 400


def test_invitation_does_not_assign_until_driver_accepts_and_retry_is_stable(remediation_env):
    env = remediation_env
    graph = _graph(env)
    assignment_id = _invite(env,graph)
    assert _invite(env,graph) == assignment_id
    with env.db() as db:
        profile = db.execute("SELECT current_truck_id,is_available FROM driver_profiles WHERE user_id=%s",(graph.driver["id"],)).fetchone()
        assert profile == {"current_truck_id":None,"is_available":True}
    _accept(env,graph,assignment_id)
    with env.db() as db:
        profile = db.execute("SELECT current_truck_id,is_available FROM driver_profiles WHERE user_id=%s",(graph.driver["id"],)).fetchone()
        assert profile == {"current_truck_id":graph.truck_id,"is_available":False}
        assert db.execute("SELECT accepted_at IS NOT NULL AS consented FROM driver_trip_assignments WHERE id=%s",(assignment_id,)).fetchone()["consented"] is True
        assert db.execute("SELECT driver_name,driver_cnic FROM vehicles WHERE id=%s",(graph.truck_id,)).fetchone() == {"driver_name":graph.driver["full_name"],"driver_cnic":graph.driver["cnic"]}


def test_two_simultaneous_acceptances_cannot_double_book_driver(remediation_env):
    env = remediation_env
    driver = _driver(env)
    graphs = [_graph(env,driver=driver) for _ in range(2)]
    ids = [_invite(env,g) for g in graphs]
    barrier = Barrier(2)
    def accept(item):
        graph,assignment_id = item
        barrier.wait(10)
        return graph.driver_client.post(f"/api/driver/trips/{assignment_id}/respond",headers=env.headers,json={"action":"accept"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept,zip(graphs,ids))) == [200,409]
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM driver_trip_assignments WHERE driver_user_id=%s AND status IN ('accepted','in_progress')",(driver[0]["id"],)).fetchone()["n"] == 1


def test_two_drivers_cannot_accept_same_truck_and_trip(remediation_env):
    env = remediation_env
    first = _graph(env)
    second_driver,second_code = _driver(env)
    second_client,_ = env.login(second_driver)
    first_id = _invite(env,first)
    response = first.owner_client.post("/api/transporter/dispatch-driver",headers=env.headers,json={**first.payload,"unique_driver_id":second_code})
    assert response.status_code == 200,response.json
    second_id = response.json["assignment_id"]
    barrier = Barrier(2)
    def accept(item):
        client,assignment_id = item
        barrier.wait(10)
        return client.post(f"/api/driver/trips/{assignment_id}/respond",headers=env.headers,json={"action":"accept"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept,[(first.driver_client,first_id),(second_client,second_id)])) == [200,409]


@pytest.mark.parametrize("kind",["one_time","agreement"])
def test_gps_derives_active_assignment_identifiers_and_rejects_forgery(remediation_env,kind):
    env = remediation_env
    graph = _graph(env,kind=kind)
    assignment_id = _invite(env,graph)
    assert graph.driver_client.post("/api/driver/gps/ping",headers=env.headers,json={"lat":31,"lng":74}).status_code == 409
    _accept(env,graph,assignment_id)
    assert graph.driver_client.post("/api/driver/gps/ping",headers=env.headers,json={"lat":31,"lng":74,"trip_id":graph.trip_id+999}).status_code == 404
    response = graph.driver_client.post("/api/driver/gps/ping",headers=env.headers,json={"lat":31.5,"lng":74.25,"battery_level":0})
    assert response.status_code == 200,response.json
    assert response.json["assignment_id"] == assignment_id
    with env.db() as db:
        ping = db.execute("SELECT truck_id,trip_id,agreement_trip_id,battery_level FROM driver_gps_pings WHERE driver_user_id=%s",(graph.driver["id"],)).fetchone()
        assert ping == {"truck_id":graph.truck_id,"trip_id":graph.trip_id if kind == "one_time" else None,
                        "agreement_trip_id":graph.trip_id if kind == "agreement" else None,"battery_level":0}
        assert db.execute("SELECT current_lat,current_lng FROM vehicles WHERE id=%s",(graph.truck_id,)).fetchone() == {"current_lat":31.5,"current_lng":74.25}
    _set_status(env,graph,"completed")
    assert graph.driver_client.post("/api/driver/gps/ping",headers=env.headers,json={"lat":32,"lng":75}).status_code == 409


@pytest.mark.parametrize("field,value",[("lat",999),("lng",181),("lat","NaN"),("lng","Infinity"),("assignment_id",True)])
def test_gps_rejects_bad_coordinates_and_identifiers_before_write(remediation_env,field,value):
    env = remediation_env
    graph = _graph(env)
    response = graph.driver_client.post("/api/driver/gps/ping",headers=env.headers,json={"lat":31,"lng":74,field:value})
    assert response.status_code == 400,response.json


@pytest.mark.parametrize("role",["driver","shopkeeper","service_seeker"])
def test_review_rejects_unrelated_roles(remediation_env,role):
    env = remediation_env
    client,_ = env.login(env.user(role))
    assert client.post("/api/driver/rate",headers=env.headers,json={"driver_user_id":1,"assignment_id":1,"rating":5}).status_code == 403


@pytest.mark.parametrize("kind",["one_time","agreement"])
def test_review_requires_owned_completed_assignment_and_incident_starts_investigating(remediation_env,kind):
    env = remediation_env
    graph = _graph(env,kind=kind)
    assignment_id = _invite(env,graph)
    payload = _review_payload(graph,assignment_id,incident_type="theft",incident_description="Unverified allegation")
    assert graph.owner_client.post("/api/driver/rate",headers=env.headers,json=payload).status_code == 409
    outsider,_ = env.login(env.user("logistics_provider"))
    assert outsider.post("/api/driver/rate",headers=env.headers,json=payload).status_code == 404
    _accept(env,graph,assignment_id)
    _set_status(env,graph,"completed")
    response = graph.owner_client.post("/api/driver/rate",headers=env.headers,json=payload)
    assert response.status_code == 200,response.json
    assert response.json["new_rating"] == 5 and response.json["incident_status"] == "investigating"
    assert graph.owner_client.post("/api/driver/rate",headers=env.headers,json=payload).status_code == 409
    with env.db() as db:
        assert db.execute("SELECT assignment_id,status,rating_penalty FROM driver_incidents WHERE driver_user_id=%s",(graph.driver["id"],)).fetchone() == {"assignment_id":assignment_id,"status":"investigating","rating_penalty":0}
        assert db.execute("SELECT rating,rating_count FROM driver_profiles WHERE user_id=%s",(graph.driver["id"],)).fetchone() == {"rating":5,"rating_count":1}
    lookup = graph.owner_client.get(f"/api/driver/lookup/{graph.driver_code}")
    assert lookup.status_code == 200 and lookup.json["incidents"] == []


def test_unconfirmed_delivery_cannot_be_reviewed(remediation_env):
    env = remediation_env
    graph = _graph(env)
    assignment_id = _invite(env,graph)
    _accept(env,graph,assignment_id)
    _set_status(env,graph,"awaiting_client_confirmation")
    assert graph.owner_client.post("/api/driver/rate",headers=env.headers,json=_review_payload(graph,assignment_id)).status_code == 409


def test_concurrent_reviews_commit_once(remediation_env):
    env = remediation_env
    graph = _graph(env)
    assignment_id = _invite(env,graph)
    _accept(env,graph,assignment_id)
    _set_status(env,graph,"completed")
    clients = [env.login(graph.owner)[0] for _ in range(2)]
    barrier = Barrier(2)
    def review(client):
        barrier.wait(10)
        return client.post("/api/driver/rate",headers=env.headers,json=_review_payload(graph,assignment_id)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(review,clients)) == [200,409]
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM driver_reviews WHERE assignment_id=%s",(assignment_id,)).fetchone()["n"] == 1


@pytest.mark.parametrize("terminal,status",[("completed","completed"),("resolved_client","cancelled")])
def test_terminal_source_releases_driver_and_allows_next_invitation(remediation_env,terminal,status):
    env = remediation_env
    graph = _graph(env)
    assignment_id = _invite(env,graph)
    _accept(env,graph,assignment_id)
    _set_status(env,graph,terminal)
    with env.db() as db:
        assert db.execute("SELECT status FROM driver_trip_assignments WHERE id=%s",(assignment_id,)).fetchone()["status"] == status
        assert db.execute("SELECT current_truck_id,is_available FROM driver_profiles WHERE user_id=%s",(graph.driver["id"],)).fetchone() == {"current_truck_id":None,"is_available":True}
    next_graph = _graph(env,driver=(graph.driver,graph.driver_code))
    _accept(env,next_graph,_invite(env,next_graph))


def test_database_rejects_second_active_assignment_even_without_route(remediation_env):
    env = remediation_env
    graph = _graph(env)
    assignment_id = _invite(env,graph)
    _accept(env,graph,assignment_id)
    next_graph = _graph(env,driver=(graph.driver,graph.driver_code))
    with pytest.raises(psycopg2.IntegrityError) as failure:
        with env.db() as db:
            db.execute("INSERT INTO driver_trip_assignments(driver_user_id,transporter_user_id,truck_id,trip_type,trip_id,status,accepted_at) VALUES(%s,%s,%s,'one_time',%s,'accepted',now())",
                       (graph.driver["id"],next_graph.owner["id"],next_graph.truck_id,next_graph.trip_id))
    assert failure.value.pgcode == "23505"
    assert failure.value.diag.constraint_name == "driver_assignment_one_active_driver"


@pytest.mark.parametrize("kind",["one_time","agreement"])
def test_assignment_listing_is_owned_and_exposes_only_safe_consent_review_fields(remediation_env,kind):
    env = remediation_env
    graph = _graph(env,kind=kind)
    assignment_id = _invite(env,graph)
    query = {"agreement_trip_id" if kind == "agreement" else "trip_id":graph.trip_id}
    url = "/api/transporter/driver-assignments"
    outsider,_ = env.login(env.user("logistics_provider"))
    assert outsider.get(url,query_string=query).status_code == 404
    pending = graph.owner_client.get(url,query_string=query)
    assert pending.status_code == 200,pending.json
    row = pending.json["assignments"][0]
    assert row["id"] == assignment_id and row["unique_driver_id"] == graph.driver_code
    assert row["reviewed"] is False and row["can_review"] is False
    assert not any(key in row for key in ("cnic","driver_cnic","email","phone","license_number"))
    _accept(env,graph,assignment_id)
    _set_status(env,graph,"completed")
    completed = graph.owner_client.get(url,query_string=query)
    assert completed.json["assignments"][0]["can_review"] is True
    assert completed.json["can_dispatch"] is False
    assert graph.owner_client.post("/api/driver/rate",headers=env.headers,json=_review_payload(graph,assignment_id)).status_code == 200
    assert graph.owner_client.get(url,query_string=query).json["assignments"][0]["reviewed"] is True


def test_assignment_listing_limit_cannot_hide_active_driver(remediation_env):
    env = remediation_env
    graph = _graph(env)
    assignment_id = _invite(env,graph)
    _accept(env,graph,assignment_id)
    with env.db() as db:
        db.execute(
            "INSERT INTO driver_trip_assignments(driver_user_id,transporter_user_id,truck_id,trip_type,trip_id,status) "
            "SELECT %s,%s,%s,'one_time',%s,'requested' FROM generate_series(1,101)",
            (graph.driver["id"],graph.owner["id"],graph.truck_id,graph.trip_id),
        )
    response = graph.owner_client.get("/api/transporter/driver-assignments",query_string={"trip_id":graph.trip_id})
    assert response.status_code == 200,response.json
    assert len(response.json["assignments"]) == 100
    assert response.json["assignments"][0]["id"] == assignment_id
    assert response.json["can_dispatch"] is False


def test_legacy_foreign_assignment_cannot_leak_through_fuel_endpoints(remediation_env):
    env = remediation_env
    graph = _graph(env)
    foreign = _graph(env)
    with env.db() as db:
        assignment_id = db.execute(
            "INSERT INTO driver_trip_assignments(driver_user_id,transporter_user_id,truck_id,trip_type,trip_id,status,accepted_at) "
            "VALUES(%s,%s,%s,'one_time',%s,'completed',now()) RETURNING id",
            (graph.driver["id"],graph.owner["id"],graph.truck_id,foreign.trip_id),
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO driver_fuel_logs(driver_user_id,truck_id,assignment_id,trip_id,pump_name,city,liters,price_per_liter,total_amount) "
            "VALUES(%s,%s,%s,%s,'Historical pump','Historical city',1,100,100)",
            (graph.driver["id"],graph.truck_id,assignment_id,foreign.trip_id),
        )
    assert graph.driver_client.get("/api/driver/trips-for-fuel").json["trips"] == []
    attempted = graph.driver_client.post("/api/driver/fuel-logs",headers=env.headers,json={
        "assignment_id":assignment_id,"pump_name":"Test pump","city":"Test city","liters":1,"price_per_liter":100,
    })
    assert attempted.status_code == 404,attempted.json
    history = graph.driver_client.get("/api/driver/fuel-logs")
    assert history.status_code == 200,history.json
    assert history.json["logs"][0]["pickup_city"] is None and history.json["logs"][0]["dropoff_city"] is None


@pytest.mark.parametrize("kind",["one_time","agreement"])
def test_fuel_history_uses_consented_assignment_and_keeps_source_namespace(remediation_env,kind):
    env = remediation_env
    graph = _graph(env,kind=kind)
    assignment_id = _invite(env,graph)
    assert graph.driver_client.get("/api/driver/trips-for-fuel").json["trips"] == []
    _accept(env,graph,assignment_id)
    trips = graph.driver_client.get("/api/driver/trips-for-fuel")
    assert trips.status_code == 200 and trips.json["trips"][0]["assignment_id"] == assignment_id
    logged = graph.driver_client.post("/api/driver/fuel-logs",headers=env.headers,json={
        "assignment_id":assignment_id,"pump_name":"Test pump","city":"Test city","liters":1,"price_per_liter":100,
    })
    assert logged.status_code == 200,logged.json
    with env.db() as db:
        row = db.execute("SELECT trip_id,agreement_trip_id FROM driver_fuel_logs WHERE id=%s",(logged.json["log_id"],)).fetchone()
        assert row == {"trip_id":graph.trip_id if kind == "one_time" else None,
                       "agreement_trip_id":graph.trip_id if kind == "agreement" else None}
