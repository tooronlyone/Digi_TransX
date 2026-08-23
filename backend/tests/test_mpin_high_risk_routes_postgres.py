"""Real PostgreSQL route proofs for all six high-risk MPIN mutations."""

import base64
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import secrets
from urllib.parse import urlsplit

from flask import Flask
import psycopg2
import pytest

import agreements.routes as agreements_routes
import auth.helpers as auth_helpers
from auth import mpin_service
import auth.routes as auth_routes
import orders.routes as orders_routes
from shared.db import Db
import wallet.helpers as wallet_helpers
import wallet.routes as wallet_routes
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.test_trip_lifecycle import _completed, seed_ready_order


PEPPER = base64.urlsafe_b64encode(b"R" * 32).decode()
CSRF = {"X-CSRF-Token": "route-step-up-csrf"}


def _local_url():
    url = require_test_db_url()
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert parsed.path.lstrip("/").startswith("dtx_phase1b2c0_")
    return url


@pytest.fixture(scope="module")
def high_risk_route_database_url():
    url, cleanup = make_disposable(
        _local_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def high_risk_route_env(high_risk_route_database_url, monkeypatch):
    @contextmanager
    def test_open_db():
        conn = psycopg2.connect(high_risk_route_database_url)
        try:
            yield Db(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    for module in (
        agreements_routes,
        auth_helpers,
        auth_routes,
        orders_routes,
        wallet_helpers,
        wallet_routes,
    ):
        monkeypatch.setattr(module, "open_db", test_open_db)

    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    monkeypatch.setenv("DIGITRANSX_MPIN_PEPPER", PEPPER)

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="high-risk-route-test-only",
        SESSION_COOKIE_SECURE=False,
        TESTING=True,
    )
    app.register_blueprint(auth_routes.auth_blueprint)
    app.register_blueprint(orders_routes.orders_blueprint)
    app.register_blueprint(wallet_routes.wallet_blueprint)
    app.register_blueprint(agreements_routes.agreements_blueprint)

    seed_connection = psycopg2.connect(high_risk_route_database_url)
    db = Db(seed_connection)
    client = app.test_client()
    try:
        yield client, db
    finally:
        seed_connection.rollback()
        seed_connection.close()
        with psycopg2.connect(high_risk_route_database_url) as cleanup_connection:
            with cleanup_connection.cursor() as cursor:
                cursor.execute(
                    "TRUNCATE public.security_events, public.business_audit_events, "
                    "public.login_activity, public.trusted_devices, public.users "
                    "RESTART IDENTITY CASCADE"
                )


def _new_user(db, *, legacy_role, app_role, suffix):
    return db.execute(
        """
        INSERT INTO users(full_name,email,cnic,role,legacy_role)
        VALUES(%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            f"Route {suffix}",
            f"{suffix}@example.invalid",
            str(abs(hash(suffix)))[:13].ljust(13, "0"),
            app_role,
            legacy_role,
        ),
    ).fetchone()["id"]


def _attach_authentication(client, db, user_id):
    device_raw = secrets.token_urlsafe(32)
    session_raw = secrets.token_urlsafe(32)
    access_proof_raw = secrets.token_urlsafe(32)
    device_id = db.execute(
        """
        INSERT INTO trusted_devices(token_digest,user_id,expires_at)
        VALUES(%s,%s,now()+interval '30 days')
        RETURNING id
        """,
        (hashlib.sha256(device_raw.encode()).digest(), user_id),
    ).fetchone()["id"]
    db.execute(
        """
        INSERT INTO user_sessions(
            user_id,token_digest,trusted_device_id,
            inactivity_expires_at,absolute_expires_at,
            access_proof_digest,access_proof_expires_at
        )
        VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',
               %s,now()+interval '8 hours')
        """,
        (
            user_id,
            hashlib.sha256(session_raw.encode()).digest(),
            device_id,
            hashlib.sha256(access_proof_raw.encode()).digest(),
        ),
    )
    salt, verifier = mpin_service.build_credential("1234")
    db.execute(
        """
        INSERT INTO mpin_credentials(user_id,verifier,salt,kdf_version)
        VALUES(%s,%s,%s,1)
        """,
        (user_id, verifier, salt),
    )
    db.commit()
    client.set_cookie(auth_helpers.DEVICE_COOKIE_NAME, device_raw)
    client.set_cookie(auth_helpers.SESSION_TOKEN_COOKIE_NAME, session_raw)
    client.set_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME, access_proof_raw)
    with client.session_transaction() as state:
        state["csrf_token"] = CSRF["X-CSRF-Token"]


def _protected_post(client, url, payload, *, extra_headers=None):
    headers = {**CSRF, **(extra_headers or {})}
    challenged = client.post(url, json=payload, headers=headers)
    assert challenged.status_code == 428, challenged.get_data(as_text=True)
    challenge = challenged.get_json()
    assert challenge["code"] == "mpin_step_up_required"

    issued = client.post(
        "/auth/mpin/step-up",
        json={"mpin": "1234", "action": challenge["action"]},
        headers=CSRF,
    )
    assert issued.status_code == 200, issued.get_data(as_text=True)
    proof = issued.get_json()["authorization_proof"]
    completed = client.post(
        url,
        json=payload,
        headers={**headers, "X-MPIN-Step-Up-Proof": proof},
    )
    return completed, challenge["action"]


def _assert_consumed(db, action_key):
    row = db.execute(
        """
        SELECT state
          FROM mpin_step_up_authorizations
         WHERE action_key=%s
         ORDER BY issued_at DESC
         LIMIT 1
        """,
        (action_key,),
    ).fetchone()
    assert row and row["state"] == "consumed"
    event = db.execute(
        """
        SELECT count(*) AS count
          FROM security_events
         WHERE event_name='security.mpin.step_up_consumed'
           AND metadata->>'action_key'=%s
        """,
        (action_key,),
    ).fetchone()
    assert event["count"] == 1


def _seed_vehicle(db, owner_id, suffix):
    return db.execute(
        """
        INSERT INTO vehicles(
            owner_user_id,truck_number,truck_type,chassis_number,
            capacity_tons,main_use,status,current_city,current_lat,current_lng
        )
        VALUES(%s,%s,'Cargo Truck',%s,20,'general','active',
               'Gujranwala',32.1877,74.1945)
        RETURNING id
        """,
        (owner_id, f"TR-{suffix}", f"CH-{suffix}"),
    ).fetchone()["id"]


def test_wallet_only_checkout_consumes_real_authorization_and_writes_event(
    high_risk_route_env,
):
    client, db = high_risk_route_env
    user_id = _new_user(
        db, legacy_role="service_seeker", app_role="customer", suffix="checkout"
    )
    transporter_id = _new_user(
        db, legacy_role="logistics_provider", app_role="transporter",
        suffix="checkout-carrier",
    )
    truck_id = _seed_vehicle(db, transporter_id, "checkout")
    wallet_id = db.execute(
        """
        INSERT INTO wallets(user_id,role,balance,minimum_required,is_minimum_met)
        VALUES(%s,'client',150000,0,true)
        RETURNING id
        """,
        (user_id,),
    ).fetchone()["id"]
    order_id = db.execute(
        """
        INSERT INTO shipments(
            client_user_id,pickup_city,pickup_lat,pickup_lng,dropoff_city,
            pickup_date,pickup_time,goods_type,goods_weight_tons,
            seeker_kind_snapshot,status
        )
        VALUES(%s,'Gujranwala',32.1877,74.1945,'Lahore',
               '2026-09-01','09:00','Steel',5,'business','open')
        RETURNING id
        """,
        (user_id,),
    ).fetchone()["id"]
    bid_id = db.execute(
        """
        INSERT INTO shipment_bids(
            order_id,transporter_user_id,truck_id,bid_price,status
        )
        VALUES(%s,%s,%s,100000,'pending')
        RETURNING id
        """,
        (order_id, transporter_id, truck_id),
    ).fetchone()["id"]
    _attach_authentication(client, db, user_id)

    response, action = _protected_post(
        client,
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        {},
        extra_headers={"Idempotency-Key": "real-route-checkout-0001"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert action["action_key"] == "one_time.checkout.wallet_only"
    assert action["resource_id"] == order_id
    assert db.execute("SELECT count(*) AS count FROM payments").fetchone()["count"] == 1
    assert db.execute("SELECT count(*) AS count FROM shipment_trips").fetchone()["count"] == 1
    assert float(
        db.execute("SELECT balance FROM wallets WHERE id=%s", (wallet_id,)).fetchone()["balance"]
    ) == 50000.0
    _assert_consumed(db, action["action_key"])


def test_withdrawal_consumes_real_authorization_and_writes_event(high_risk_route_env):
    client, db = high_risk_route_env
    user_id = _new_user(
        db, legacy_role="logistics_provider", app_role="transporter",
        suffix="withdrawal",
    )
    db.execute(
        """
        INSERT INTO transporter_profiles(user_id,company_name,payout_card_token)
        VALUES(%s,'Carrier','provider-token-withdrawal')
        """,
        (user_id,),
    )
    db.execute(
        """
        INSERT INTO wallets(user_id,role,balance,minimum_required,is_minimum_met)
        VALUES(%s,'transporter',100000,30000,true)
        """,
        (user_id,),
    )
    _attach_authentication(client, db, user_id)

    response, action = _protected_post(
        client, "/api/wallet/withdraw-locked", {"amount": 10000}
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["auto_approved"] is True
    assert db.execute(
        "SELECT status FROM wallet_withdrawal_requests"
    ).fetchone()["status"] == "approved"
    assert float(
        db.execute("SELECT balance FROM wallets WHERE user_id=%s", (user_id,)).fetchone()["balance"]
    ) == 90000.0
    _assert_consumed(db, action["action_key"])


def test_tier_purchase_consumes_real_authorization_and_writes_event(high_risk_route_env):
    client, db = high_risk_route_env
    user_id = _new_user(
        db, legacy_role="logistics_provider", app_role="transporter",
        suffix="tier",
    )
    db.execute(
        "INSERT INTO transporter_profiles(user_id,company_name) VALUES(%s,'Carrier')",
        (user_id,),
    )
    db.execute(
        """
        INSERT INTO wallets(user_id,role,balance,minimum_required,is_minimum_met)
        VALUES(%s,'transporter',100000,30000,true)
        """,
        (user_id,),
    )
    _attach_authentication(client, db, user_id)

    response, action = _protected_post(
        client,
        "/api/wallet/upgrade-limit",
        {"tier": 1, "duration_years": 3},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert db.execute(
        "SELECT withdrawal_tier FROM transporter_profiles WHERE user_id=%s",
        (user_id,),
    ).fetchone()["withdrawal_tier"] == 1
    assert float(
        db.execute("SELECT balance FROM wallets WHERE user_id=%s", (user_id,)).fetchone()["balance"]
    ) == 80000.0
    _assert_consumed(db, action["action_key"])


def test_payout_destination_consumes_real_claim_and_writes_event(high_risk_route_env):
    client, db = high_risk_route_env
    user_id = _new_user(
        db, legacy_role="logistics_provider", app_role="transporter",
        suffix="payout",
    )
    db.execute(
        "INSERT INTO transporter_profiles(user_id,company_name) VALUES(%s,'Carrier')",
        (user_id,),
    )
    db.execute(
        """
        INSERT INTO wallets(user_id,role,balance,minimum_required,is_minimum_met)
        VALUES(%s,'transporter',50000,30000,true)
        """,
        (user_id,),
    )
    _attach_authentication(client, db, user_id)
    payload = {
        "card_number": "4111111111111111",
        "card_holder": "Route Carrier",
        "card_expiry": "12/30",
        "bank": "Route Bank",
    }

    response, action = _protected_post(
        client, "/api/wallet/payout-card", payload
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    destination = db.execute(
        """
        SELECT payout_card_token,payout_card_last_four
          FROM transporter_profiles
         WHERE user_id=%s
        """,
        (user_id,),
    ).fetchone()
    assert destination["payout_card_token"].startswith("dummytok_")
    assert destination["payout_card_last_four"] == "1111"
    _assert_consumed(db, action["action_key"])


def test_agreement_finalize_consumes_real_authorization_and_writes_event(
    high_risk_route_env,
):
    client, db = high_risk_route_env
    user_id = _new_user(
        db, legacy_role="service_seeker", app_role="customer", suffix="agreement"
    )
    transporter_id = _new_user(
        db, legacy_role="logistics_provider", app_role="transporter",
        suffix="agreement-carrier",
    )
    truck_id = _seed_vehicle(db, transporter_id, "agreement")
    post_id = db.execute(
        """
        INSERT INTO agreement_posts(client_user_id,title,cargo_type,service_area)
        VALUES(%s,'Annual steel','Steel','Punjab')
        RETURNING id
        """,
        (user_id,),
    ).fetchone()["id"]
    bid_id = db.execute(
        """
        INSERT INTO agreement_bids(post_id,transporter_user_id,status)
        VALUES(%s,%s,'pending')
        RETURNING id
        """,
        (post_id, transporter_id),
    ).fetchone()["id"]
    db.execute(
        """
        INSERT INTO agreement_bid_trucks(
            bid_id,truck_id,per_km_rate,minimum_monthly_guarantee
        )
        VALUES(%s,%s,100,50000)
        """,
        (bid_id, truck_id),
    )
    _attach_authentication(client, db, user_id)
    payload = {
        "post_id": post_id,
        "duration_months": 3,
        "start_date": "2026-09-01",
        "cargo_type": "Steel",
        "service_area": "Punjab",
        "selected_trucks": [{"bid_id": bid_id, "truck_id": truck_id}],
        "contract_text": "Canonical route integration agreement.",
    }

    response, action = _protected_post(
        client, "/api/agreements/finalize", payload
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert db.execute("SELECT count(*) AS count FROM agreements").fetchone()["count"] == 1
    assert db.execute(
        "SELECT status FROM agreement_posts WHERE id=%s", (post_id,)
    ).fetchone()["status"] == "active"
    _assert_consumed(db, action["action_key"])


def test_delivery_release_consumes_real_authorization_and_writes_event(
    high_risk_route_env,
):
    client, db = high_risk_route_env
    seed = seed_ready_order(
        db,
        client_kind="business",
        bid=Decimal("10000"),
        wallet_funded=Decimal("10000"),
        card_funded=Decimal("0"),
        client_wallet_balance=Decimal("0"),
    )
    _completed(db, seed)
    _attach_authentication(client, db, seed["client"]["id"])

    response, action = _protected_post(
        client,
        f"/api/orders/{seed['order_id']}/trips/{seed['trip_id']}/confirm-delivery",
        {"decision": "yes", "rating": 5, "comment": "Delivered as agreed."},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert db.execute(
        "SELECT status FROM payments WHERE id=%s", (seed["payment_id"],)
    ).fetchone()["status"] == "released"
    assert db.execute(
        "SELECT status FROM shipment_trips WHERE id=%s", (seed["trip_id"],)
    ).fetchone()["status"] == "completed"
    assert db.execute(
        "SELECT count(*) AS count FROM shipment_trip_reviews WHERE trip_id=%s",
        (seed["trip_id"],),
    ).fetchone()["count"] == 1
    _assert_consumed(db, action["action_key"])
