"""Financial authorization and concurrency regressions on a disposable local DB.

Never imports backend.app and never falls back to the application DB URL.
PostgreSQL cases require an explicitly configured loopback test database.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import threading
from urllib.parse import urlsplit

from flask import Flask, request
import psycopg2
import pytest

import marketplace.routes as marketplace_routes
import marketplace.service as service
import admin.routes as admin_routes
from shared.db import Db
import shared.payments as payments
import wallet.helpers as wallet_helpers
import wallet.routes as wallet_routes
from wallet.withdrawal_limits import get_active_tier, max_withdrawable
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url


BUYER = {"id": 1, "role": "service_seeker", "phone": "03000000001"}
SELLER = {"id": 2, "role": "shopkeeper"}


@pytest.fixture
def finance_app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="financial-tests-only-secret-key", TESTING=True)
    with app.app_context():
        yield app


@pytest.mark.parametrize("environment", ["", "production", "staging", "local", "development"])
def test_unconfigured_payment_provider_fails_closed(environment, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", environment)
    monkeypatch.delenv("DIGITRANSX_ALLOW_DUMMY_PAYMENTS", raising=False)
    app = Flask(__name__)
    with app.app_context(), pytest.raises(payments.CheckoutError) as error:
        payments.get_payment_provider()
    assert error.value.status == 503


def test_production_cannot_opt_into_dummy_with_flag_alone(monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "production")
    monkeypatch.setenv("DIGITRANSX_ALLOW_DUMMY_PAYMENTS", "true")
    with Flask(__name__).app_context(), pytest.raises(payments.CheckoutError):
        payments.get_payment_provider()


@pytest.mark.parametrize("environment",["production","prod","staging"])
def test_deployment_environment_blocks_dummy_even_with_flask_testing(monkeypatch,environment):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT",environment)
    monkeypatch.setenv("DIGITRANSX_ALLOW_DUMMY_PAYMENTS","true")
    app=Flask(__name__)
    app.config["TESTING"]=True
    app.extensions["digitransx_payment_provider"]=payments.DummyCardProvider()
    with app.app_context(),pytest.raises(payments.CheckoutError) as error:
        payments.get_payment_provider()
    assert error.value.status==503


@pytest.mark.parametrize("environment,opt_in", [("test", ""), ("local", "true"), ("development", "1")])
def test_explicit_simulator_selection(environment, opt_in, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", environment)
    monkeypatch.setenv("DIGITRANSX_ALLOW_DUMMY_PAYMENTS", opt_in)
    with Flask(__name__).app_context():
        assert isinstance(payments.get_payment_provider(), payments.DummyCardProvider)


def test_testing_app_and_injected_real_adapter(finance_app):
    assert isinstance(payments.get_payment_provider(), payments.DummyCardProvider)
    adapter = object()  # Selection alone never invokes a provider or network.
    finance_app.extensions["digitransx_payment_provider"] = adapter
    finance_app.config.update(TESTING=False, DIGITRANSX_ENVIRONMENT="production")
    assert payments.get_payment_provider() is adapter


@pytest.mark.parametrize("response", [None, {}, {"status":"pending","reference":"p1"},
                                      {"status":"declined","reference":"p1"},
                                      {"status":"succeeded","reference":None}])
def test_unconfirmed_adapter_response_is_not_card_funding(response):
    class Adapter:
        def charge(self,*args,**kwargs):
            return response
    with pytest.raises(payments.CheckoutError) as error:
        payments._confirmed_card_charge(Adapter(), Decimal("100"))
    assert error.value.code == "card_charge_unconfirmed"


@pytest.mark.parametrize("role", ["driver", "service_seeker", "fuel_station_manager", "logistics_provider"])
def test_marketplace_seller_actions_reject_other_roles(finance_app, role):
    with finance_app.test_request_context("/api/marketplace/shop/parts", method="POST", json={}):
        request.current_user = {"id": 1, "role": role}
        # Skip login plumbing, retain the production seller-role decorator.
        response = marketplace_routes.add_shop_part.__wrapped__()
    assert response.status_code == 403


@pytest.mark.parametrize("function", [wallet_routes.lock_wallet_balance, wallet_routes.unlock_wallet_balance])
def test_generic_reservation_api_cannot_change_holds(finance_app, monkeypatch, function):
    monkeypatch.setattr(wallet_routes, "csrf_error", lambda: None)
    def forbidden_open():
        raise AssertionError("Generic reservation endpoints must not open a DB.")
    monkeypatch.setattr(wallet_routes, "open_db", forbidden_open)
    with finance_app.test_request_context("/api/wallet/unlock", method="POST", json={"amount": 30000}):
        request.current_user = {"id": 1, "role": "logistics_provider"}
        response = function.__wrapped__()
    assert response.status_code == 403
    assert response.get_json()["code"] == "reservation_workflow_required"


def test_withdrawal_protects_all_holds_and_aware_tier_expiry():
    assert max_withdrawable({"balance": 100000, "locked_balance": 90000, "role": "transporter"}) == 10000
    assert max_withdrawable({"balance": "NaN", "locked_balance": 0}) == 0
    future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    assert get_active_tier({"withdrawal_tier": 4, "withdrawal_tier_expires_at": future}) == 4


def test_production_withdrawal_fails_before_debit_or_step_up(finance_app, monkeypatch):
    finance_app.config.update(TESTING=False, DIGITRANSX_ENVIRONMENT="production")
    monkeypatch.setattr(wallet_routes, "csrf_error", lambda: None)
    def forbidden_open():
        raise AssertionError("Unconfigured payout must not touch wallet or claims.")
    monkeypatch.setattr(wallet_routes, "open_db", forbidden_open)
    with finance_app.test_request_context("/api/wallet/withdraw-locked", method="POST", json={"amount": 1000}):
        request.current_user = {"id": 1, "role": "logistics_provider"}
        response = wallet_routes.create_locked_withdrawal_request.__wrapped__()
    assert response.status_code == 503


@pytest.mark.parametrize("function", [marketplace_routes.add_shop_part,marketplace_routes.submit_rfq_bid])
@pytest.mark.parametrize("bad_field,bad_value", [("price","NaN"),("price","Infinity"),
    ("price",True),("stock_quantity",-1),("stock_quantity","NaN"),("warranty_days",1.5)])
def test_marketplace_numeric_boundary_rejects_before_sql(finance_app,monkeypatch,function,bad_field,bad_value):
    monkeypatch.setattr(marketplace_routes,"csrf_error",lambda:None)
    payload = {"title":"Filter","price":"700.00","offered_price":"700.00","stock_quantity":1}
    if function is marketplace_routes.submit_rfq_bid and bad_field in {"price","stock_quantity"}:
        bad_field = "offered_price" if bad_field == "price" else "delivery_time_hours"
    payload[bad_field] = bad_value
    with finance_app.test_request_context("/api/marketplace/shop/parts",method="POST",json=payload):
        request.current_user = SELLER
        with pytest.raises(payments.CheckoutError) as error:
            function.__wrapped__(1) if function is marketplace_routes.submit_rfq_bid else function.__wrapped__()
    assert error.value.status == 400


def test_admin_production_withdrawal_fails_before_any_db_access(finance_app,monkeypatch):
    finance_app.config.update(TESTING=False,DIGITRANSX_ENVIRONMENT="production")
    monkeypatch.setattr(admin_routes,"csrf_error",lambda:None)
    def forbidden_open():
        raise AssertionError("Production payout approval must fail before database writes.")
    monkeypatch.setattr(admin_routes,"open_db",forbidden_open)
    with finance_app.test_request_context("/api/admin/wallet/withdrawals/1/approve",method="POST",json={}):
        request.current_user = {"id":99,"role":"platform_admin"}
        response = admin_routes.approve_withdrawal.__wrapped__(1)
    assert response.status_code == 503


@pytest.mark.parametrize("items", [None, [], [None], [{"part_id": True}],
    [{"part_id": 1, "quantity": -1}], [{"part_id": 1, "quantity": 1.5}],
    [{"part_id": 1}, {"part_id": 1}]])
def test_checkout_rejects_invalid_item_shapes(items):
    with pytest.raises(payments.CheckoutError):
        service.parse_checkout({"items": items, "delivery_type": "pickup"}, BUYER)


@pytest.fixture(scope="module")
def finance_database_url():
    url = require_test_db_url()
    parsed = urlsplit(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.skip("Financial concurrency tests require an explicit loopback test server.")
    if not parsed.path.lstrip("/").startswith("dtx_phase1b2c0_"):
        pytest.skip("Use a dedicated dtx_phase1b2c0_ test database for financial regressions.")
    child, cleanup = make_disposable(url, STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        yield child
    finally:
        cleanup()


@pytest.fixture
def finance_store(finance_database_url, finance_app):
    @contextmanager
    def connect():
        conn = psycopg2.connect(finance_database_url)
        try:
            yield Db(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    with connect() as db:
        for user_id, app_role, legacy in [(1, "customer", "service_seeker"), (2, "shopkeeper", "shopkeeper"),
                                           (3, "transporter", "logistics_provider")]:
            db.execute("INSERT INTO users(id,full_name,email,cnic,role,legacy_role) VALUES(%s,%s,%s,%s,%s,%s)",
                       (user_id,f"Finance {user_id}",f"finance{user_id}@example.invalid",f"{user_id:013}",app_role,legacy))
    try:
        yield connect
    finally:
        with connect() as db:
            # Immutable financial journals survive dependent fixture cleanup;
            # never reuse resource IDs as if a new payment were an old replay.
            db.execute("TRUNCATE users CONTINUE IDENTITY CASCADE")


def _wallet(db, user_id=1, balance="1000", locked="0", role="client"):
    minimum = Decimal("30000") if role == "transporter" else Decimal("0")
    return db.execute(
        "INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
        "VALUES(%s,%s,%s,%s,%s,true) RETURNING *", (user_id,role,Decimal(balance),Decimal(locked),minimum)).fetchone()


def _part(db, price="700", stock=10):
    return db.execute("INSERT INTO marketplace_parts(shop_user_id,title,category,price,stock_quantity) "
                      "VALUES(2,'Filter','engine',%s,%s) RETURNING id", (Decimal(price),stock)).fetchone()["id"]


def _payload(part_id):
    return {"items": [{"part_id": part_id, "quantity": 1}], "delivery_type": "pickup", "payment_method": "wallet_escrow"}


def _new_order(store, price="700", key="checkout-test-0001"):
    with store() as db:
        _wallet(db)
        part = _part(db, price)
        result = service.perform_marketplace_checkout(db, BUYER, _payload(part), key)
        db.execute("UPDATE marketplace_orders SET fulfillment_status='ready_for_pickup' WHERE id=%s", (result["id"],))
    return result


def _parallel(app, store, operations):
    start = threading.Barrier(len(operations))
    def worker(operation):
        with app.app_context():
            start.wait(timeout=10)
            try:
                with store() as db:
                    return True, operation(db)
            except payments.CheckoutError as exc:
                return False, exc
    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        futures = [executor.submit(worker, operation) for operation in operations]
        return [future.result(timeout=20) for future in futures]


def test_first_wallet_creation_is_concurrent_safe(finance_store, finance_app):
    read_barrier = threading.Barrier(2)
    class ReadBarrierDb:
        def __init__(self, db):
            self.db, self.first = db, True
        def execute(self, query, params=()):
            result = self.db.execute(query, params)
            if self.first and query.startswith("SELECT * FROM wallets"):
                self.first = False
                read_barrier.wait(timeout=10)
            return result
    results = _parallel(finance_app, finance_store, [
        lambda db: wallet_helpers.get_or_create_wallet_for_user(ReadBarrierDb(db), BUYER),
        lambda db: wallet_helpers.get_or_create_wallet_for_user(ReadBarrierDb(db), BUYER),
    ])
    assert all(ok and result[1] is None for ok,result in results)
    assert results[0][1][0]["id"] == results[1][1][0]["id"]
    with finance_store() as db:
        assert db.execute("SELECT count(*) AS n FROM wallets").fetchone()["n"] == 1


def test_stale_wallet_lock_snapshots_cannot_overreserve(finance_store, finance_app):
    with finance_store() as db:
        initial = _wallet(db)
    snapshots = [dict(initial), dict(initial)]
    results = _parallel(finance_app, finance_store, [
        lambda db: wallet_helpers.ensure_wallet_locked_balance(db, snapshots[0], 1, Decimal("700")),
        lambda db: wallet_helpers.ensure_wallet_locked_balance(db, snapshots[1], 1, Decimal("700")),
    ])
    assert sum(ok and result is None for ok,result in results) == 1
    with finance_store() as db:
        assert db.execute("SELECT locked_balance FROM wallets WHERE user_id=1").fetchone()["locked_balance"] == 700
        assert db.execute("SELECT count(*) AS n FROM wallet_transactions WHERE type='lock'").fetchone()["n"] == 1


def test_concurrent_credits_do_not_overwrite_each_other(finance_store, finance_app):
    with finance_store() as db:
        initial = _wallet(db)
    snapshots = [dict(initial),dict(initial)]
    results = _parallel(finance_app,finance_store,[
        lambda db: wallet_helpers.adjust_wallet_balance(db,snapshots[0],1,Decimal("500.01"),"test_credit"),
        lambda db: wallet_helpers.adjust_wallet_balance(db,snapshots[1],1,Decimal("700.02"),"test_credit"),
    ])
    assert all(ok and result is None for ok,result in results)
    with finance_store() as db:
        assert Decimal(str(db.execute("SELECT balance FROM wallets WHERE user_id=1").fetchone()["balance"])) == Decimal("2200.03")
        assert db.execute("SELECT count(*) AS n FROM wallet_transactions").fetchone()["n"] == 2


def test_checkout_replay_and_payload_binding(finance_store):
    with finance_store() as db:
        _wallet(db)
        part = _part(db)
        payload = _payload(part)
        first = service.perform_marketplace_checkout(db,BUYER,payload,"stable-checkout-key")
    with finance_store() as db:
        replay = service.perform_marketplace_checkout(db,BUYER,payload,"stable-checkout-key")
        assert replay["replayed"] is True and replay["id"] == first["id"]
        assert "delivery_otp" not in replay
        assert db.execute("SELECT stock_quantity FROM marketplace_parts WHERE id=%s",(part,)).fetchone()["stock_quantity"] == 9
        assert db.execute("SELECT locked_balance FROM wallets WHERE user_id=1").fetchone()["locked_balance"] == 700
    with pytest.raises(payments.CheckoutError) as error, finance_store() as db:
        service.perform_marketplace_checkout(db,BUYER,{**payload,"buyer_notes":"changed"},"stable-checkout-key")
    assert error.value.code == "idempotency_key_conflict"


def test_simultaneous_orders_do_not_share_the_same_money(finance_store, finance_app):
    with finance_store() as db:
        _wallet(db)
        parts = [_part(db),_part(db)]
    results = _parallel(finance_app,finance_store,[
        lambda db: service.perform_marketplace_checkout(db,BUYER,_payload(parts[0]),"different-cart-001"),
        lambda db: service.perform_marketplace_checkout(db,BUYER,_payload(parts[1]),"different-cart-002"),
    ])
    assert sum(ok for ok,result in results) == 1
    with finance_store() as db:
        assert db.execute("SELECT count(*) AS n FROM marketplace_orders").fetchone()["n"] == 1
        assert db.execute("SELECT locked_balance FROM wallets WHERE user_id=1").fetchone()["locked_balance"] == 700


def test_delivery_secret_is_not_a_seller_readable_order_column(finance_store):
    result = _new_order(finance_store)
    with finance_store() as db:
        order = db.execute("SELECT * FROM marketplace_orders WHERE id=%s",(result["id"],)).fetchone()
        secret = db.execute("SELECT * FROM marketplace_delivery_secrets WHERE order_id=%s",(result["id"],)).fetchone()
        assert order["delivery_otp"] is None
        assert "delivery_otp" not in marketplace_routes.serialize_order(order)
        assert result["delivery_otp"] not in secret["otp_digest"]
        assert len(secret["otp_digest"]) == 64
        assert not db.execute("SELECT has_table_privilege('authenticated','marketplace_delivery_secrets','SELECT') AS allowed").fetchone()["allowed"]


def test_simultaneous_delivery_verification_transfers_once(finance_store,finance_app):
    order = _new_order(finance_store)
    results = _parallel(finance_app,finance_store,[
        lambda db: service.perform_delivery_verification(db,SELLER,order["id"],order["delivery_otp"]),
        lambda db: service.perform_delivery_verification(db,SELLER,order["id"],order["delivery_otp"]),
    ])
    assert all(ok for ok,result in results)
    assert sorted(result["already_delivered"] for ok,result in results) == [False,True]
    with finance_store() as db:
        balances = db.execute("SELECT user_id,balance,locked_balance FROM wallets ORDER BY user_id").fetchall()
        assert [(r["user_id"],r["balance"],r["locked_balance"]) for r in balances] == [(1,300,0),(2,630,0)]
        assert db.execute_exact("SELECT platform_fee FROM marketplace_financial_events WHERE order_id=%s",(order["id"],)).fetchone()["platform_fee"]==Decimal("70")
        assert db.execute("SELECT count(*) AS n FROM wallet_transactions WHERE type IN ('parts_purchase','parts_sale')").fetchone()["n"] == 2


def test_concurrent_orders_settle_without_losing_shop_credit(finance_store,finance_app):
    with finance_store() as db:
        _wallet(db,balance="2000")
        parts = [_part(db),_part(db)]
        orders = [service.perform_marketplace_checkout(db,BUYER,_payload(part),f"multi-settle-{idx:04}")
                  for idx,part in enumerate(parts)]
        db.execute("UPDATE marketplace_orders SET fulfillment_status='ready_for_pickup'")
    results = _parallel(finance_app,finance_store,[
        lambda db: service.perform_delivery_verification(db,SELLER,orders[0]["id"],orders[0]["delivery_otp"]),
        lambda db: service.perform_delivery_verification(db,SELLER,orders[1]["id"],orders[1]["delivery_otp"]),
    ])
    assert all(ok and result["success"] for ok,result in results)
    with finance_store() as db:
        assert db.execute("SELECT balance FROM wallets WHERE user_id=2").fetchone()["balance"] == 1260
        assert db.execute_exact("SELECT sum(platform_fee) AS fee FROM marketplace_financial_events").fetchone()["fee"]==Decimal("140")
        assert db.execute("SELECT balance FROM wallets WHERE user_id=1").fetchone()["balance"] == 600


@pytest.mark.parametrize("failed_leg", ["parts_purchase", "parts_sale"])
def test_failed_transfer_leg_rolls_back_every_mutation(finance_store,monkeypatch,failed_leg):
    order = _new_order(finance_store)
    real_adjust = service.adjust_wallet_balance
    def fail_selected(db,wallet,user_id,amount,kind,**kwargs):
        if kind == failed_leg:
            from auth.helpers import json_response
            return json_response({"success":False,"message":"Injected leg failure"},409)
        return real_adjust(db,wallet,user_id,amount,kind,**kwargs)
    monkeypatch.setattr(service,"adjust_wallet_balance",fail_selected)
    with pytest.raises(payments.CheckoutError), finance_store() as db:
        service.perform_delivery_verification(db,SELLER,order["id"],order["delivery_otp"])
    with finance_store() as db:
        wallet = db.execute("SELECT * FROM wallets WHERE user_id=1").fetchone()
        assert wallet["balance"] == 1000 and wallet["locked_balance"] == 700
        assert db.execute("SELECT count(*) AS n FROM wallet_transactions WHERE type IN ('parts_purchase','parts_sale','unlock')").fetchone()["n"] == 0
        assert db.execute("SELECT payment_status FROM marketplace_orders WHERE id=%s",(order["id"],)).fetchone()["payment_status"] == "escrow_locked"
        assert db.execute("SELECT consumed_at FROM marketplace_delivery_secrets WHERE order_id=%s",(order["id"],)).fetchone()["consumed_at"] is None


def test_bad_codes_are_persistently_limited_and_buyer_can_reissue(finance_store,monkeypatch):
    sequence = iter([123456,654321])
    monkeypatch.setattr(service.secrets,"randbelow",lambda maximum: next(sequence))
    order = _new_order(finance_store)
    for _ in range(5):
        with finance_store() as db:
            failed = service.perform_delivery_verification(db,SELLER,order["id"],"000000")
            assert failed["success"] is False
    with pytest.raises(payments.CheckoutError), finance_store() as db:
        service.perform_delivery_verification(db,SELLER,order["id"],order["delivery_otp"])
    with finance_store() as db:
        assert db.execute("SELECT failed_attempts FROM marketplace_delivery_secrets WHERE order_id=%s",(order["id"],)).fetchone()["failed_attempts"] == 5
        db.execute("UPDATE marketplace_delivery_secrets SET created_at=now()-interval '61 seconds' WHERE order_id=%s",(order["id"],))
        new = service.issue_buyer_delivery_challenge(db,BUYER,order["id"])
    assert new["delivery_otp"] == "654321" and new["expires_at"].endswith("Z")
    with pytest.raises(payments.CheckoutError) as error, finance_store() as db:
        service.issue_buyer_delivery_challenge(db,BUYER,order["id"])
    assert error.value.status == 429
    with finance_store() as db:
        assert service.perform_delivery_verification(db,SELLER,order["id"],new["delivery_otp"])["success"] is True


def test_expired_code_and_wrong_buyer_cannot_authorize_delivery(finance_store):
    order = _new_order(finance_store)
    with finance_store() as db:
        db.execute("UPDATE marketplace_delivery_secrets SET created_at=now()-interval '21 minutes',"
                   "expires_at=now()-interval '1 minute' WHERE order_id=%s",(order["id"],))
    with pytest.raises(payments.CheckoutError), finance_store() as db:
        service.perform_delivery_verification(db,SELLER,order["id"],order["delivery_otp"])
    with pytest.raises(payments.CheckoutError) as error, finance_store() as db:
        service.issue_buyer_delivery_challenge(db,{"id":3},order["id"])
    assert error.value.status == 404


def test_security_deposit_cannot_be_unlocked_or_debited(finance_store):
    with finance_store() as db:
        wallet = _wallet(db,user_id=3,balance="40000",locked="30000",role="transporter")
        assert wallet_helpers.ensure_wallet_unlocked_balance(db,wallet,3,Decimal("1")) is not None
        assert wallet_helpers.adjust_wallet_balance(db,wallet,3,Decimal("-10000.01"),"test_spend") is not None
        assert wallet["balance"] == 40000 and wallet["locked_balance"] == 30000


def _admin_approve(app,request_id):
    with app.test_request_context(f"/api/admin/wallet/withdrawals/{request_id}/approve",method="POST",json={}):
        request.current_user = {"id":99,"role":"platform_admin"}
        return admin_routes.approve_withdrawal.__wrapped__(request_id)


def test_admin_approval_cannot_spend_marketplace_or_security_holds(finance_store,finance_app,monkeypatch):
    monkeypatch.setattr(admin_routes,"open_db",finance_store)
    monkeypatch.setattr(admin_routes,"csrf_error",lambda:None)
    with finance_store() as db:
        _wallet(db,user_id=3,balance="100000",locked="90000",role="transporter")
        request_id = db.execute("INSERT INTO wallet_withdrawal_requests(user_id,amount,status) "
                                "VALUES(3,70000,'pending') RETURNING id").fetchone()["id"]
    response = _admin_approve(finance_app,request_id)
    assert response.status_code == 400
    with finance_store() as db:
        assert db.execute("SELECT balance FROM wallets WHERE user_id=3").fetchone()["balance"] == 100000
        assert db.execute("SELECT status FROM wallet_withdrawal_requests WHERE id=%s",(request_id,)).fetchone()["status"] == "pending"


@pytest.mark.parametrize("same_request",[False,True])
def test_two_admin_requests_cannot_overdraw_same_wallet(finance_store,finance_app,monkeypatch,same_request):
    monkeypatch.setattr(admin_routes,"open_db",finance_store)
    monkeypatch.setattr(admin_routes,"csrf_error",lambda:None)
    with finance_store() as db:
        _wallet(db,user_id=3,balance="100000",locked="30000",role="transporter")
        requests = [db.execute("INSERT INTO wallet_withdrawal_requests(user_id,amount,status) "
                               "VALUES(3,50000,'pending') RETURNING id").fetchone()["id"] for _ in range(2)]
        if same_request:
            requests[1] = requests[0]
    start = threading.Barrier(2)
    def approve(request_id):
        with finance_app.app_context():
            start.wait(timeout=10)
            return _admin_approve(finance_app,request_id)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(approve,requests))
    assert sorted(response.status_code for response in responses) == [200,400]
    assert next(response for response in responses if response.status_code == 200).get_json()["simulated"] is True
    with finance_store() as db:
        assert db.execute("SELECT balance FROM wallets WHERE user_id=3").fetchone()["balance"] == 50000
        assert db.execute("SELECT count(*) AS n FROM wallet_transactions WHERE type='withdrawal'").fetchone()["n"] == 1
