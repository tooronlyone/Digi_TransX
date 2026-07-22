"""Business vs everyday client separation.

Covers: the single role-normalization helper, business-only backend guards
(agreements / wallet / saved cards) returning 403 for everyday users, the
server-set seeker_kind_snapshot (un-overridable by the browser), both kinds
flowing through the ONE shared availability/matching path, unchanged checkout
formulas, mutual-exclusivity of the two profile tables, and signup writing to
the correct profile table.

Pure-helper tests run without a database; the rest use the PostgreSQL test
schema (skipped without TEST_SUPABASE_DB_URL).
"""

import json
import types
from datetime import date, timedelta

import pytest

from shared.roles import (
    normalize_client_kind,
    is_business_client,
    is_everyday_client,
    SEEKER_KIND_EVERYDAY,
    SEEKER_KIND_BUSINESS,
)

EVERYDAY = {"id": 9001, "role": "everyday_user"}
BUSINESS = {"id": 9002, "role": "service_seeker"}
TRANSPORTER = {"id": 9003, "role": "logistics_provider"}
GUJRANWALA = (32.1877, 74.1945)


# ---------------------------------------------------------------------------
# Single role normalizer (one implementation, in shared.roles)
# ---------------------------------------------------------------------------

def test_normalize_client_kind_single_source():
    assert normalize_client_kind("everyday_user") == SEEKER_KIND_EVERYDAY
    assert normalize_client_kind("service_seeker") == SEEKER_KIND_BUSINESS
    assert normalize_client_kind("client") == SEEKER_KIND_BUSINESS
    assert normalize_client_kind("logistics_provider") is None
    assert normalize_client_kind("") is None
    assert is_business_client("service_seeker") and not is_business_client("everyday_user")
    assert is_everyday_client("everyday_user") and not is_everyday_client("service_seeker")
    # shared.payments re-exports the SAME object (no second implementation).
    from shared.payments import normalize_client_kind as pay_nck
    assert pay_nck is normalize_client_kind


def test_role_guards_split_orders_vs_agreements():
    from flask import Flask
    from agreements.helpers import require_client_role, require_business_client_role

    # The reject path builds a json_response, which needs an app context.
    with Flask(__name__).app_context():
        # Orders: any client, including everyday.
        assert require_client_role(EVERYDAY) is None
        assert require_client_role(BUSINESS) is None
        assert require_client_role(TRANSPORTER) is not None
        # Agreements / business-only: everyday rejected, business allowed.
        assert require_business_client_role(BUSINESS) is None
        assert require_business_client_role(EVERYDAY) is not None
        assert require_business_client_role(TRANSPORTER) is not None


# ---------------------------------------------------------------------------
# PostgreSQL integration helpers
# ---------------------------------------------------------------------------

def _mk_user(db, role, email, legacy_role=None, uid=None):
    return db.execute(
        "INSERT INTO users (id, full_name, email, role, legacy_role) "
        "VALUES (COALESCE(%s, nextval(pg_get_serial_sequence('users','id'))), %s, %s, %s, %s) RETURNING id",
        (uid, email, email, role, legacy_role or role),
    ).fetchone()["id"]


def _mk_flatbed(db, owner_id, lat, lng, city="Gujranwala"):
    return db.execute(
        "INSERT INTO vehicles (owner_user_id, truck_number, truck_type, catalog_type_key, "
        "capacity_tons, payload_max_tons, volume_max_cbm, bed_length_ft, bed_width_ft, bed_height_ft, "
        "current_city, current_lat, current_lng, service_radius_km, status) "
        "VALUES (%s, %s, 'Flatbed', 'flatbed_trailer_open_semi_trailer', 45, 45, 0, 21, 7, 8, "
        "%s, %s, %s, 100, 'active') RETURNING id",
        (owner_id, f"T-{owner_id}", city, lat, lng),
    ).fetchone()["id"]


# ---------------------------------------------------------------------------
# Mutual exclusivity of the two profile tables (#3)
# ---------------------------------------------------------------------------

def test_user_cannot_hold_both_profile_types(db):
    import psycopg2
    uid = _mk_user(db, "service_seeker", "both@test")
    db.execute("INSERT INTO service_seeker_profiles (user_id) VALUES (%s)", (uid,))
    db.commit()
    with pytest.raises(psycopg2.errors.RaiseException):
        db.execute("INSERT INTO everyday_user_profiles (user_id) VALUES (%s)", (uid,))
    db.rollback()


# ---------------------------------------------------------------------------
# Signup writes to the correct profile table (#1, #2)
# ---------------------------------------------------------------------------

def _signup(client, monkeypatch, role, email, extra=None):
    import auth.routes as auth_routes

    def fake_create_user(em, password, metadata):
        # Mimic the DB trigger that creates the public.users row on Auth signup.
        with auth_routes.open_db() as d:
            d.execute(
                "INSERT INTO users (email, full_name, phone, cnic, role, legacy_role) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (em, metadata.get("full_name", ""), metadata.get("phone", ""),
                 metadata.get("cnic", ""), metadata.get("role"), metadata.get("legacy_role")),
            )
            d.commit()
        return types.SimpleNamespace(user=types.SimpleNamespace(id="auth-" + em))

    monkeypatch.setattr(auth_routes, "supabase_create_user", fake_create_user)
    monkeypatch.setattr(auth_routes, "record_login_activity", lambda *a, **k: None)
    # The profile row is committed before the auth response is built; stub the
    # session/trusted-device machinery so the test stays focused on the profile.
    from auth.helpers import json_response as _jr
    monkeypatch.setattr(auth_routes, "build_auth_success_response",
                        lambda user: _jr({"success": True, "user": {"id": user.get("id")}}))

    payload = {
        "name": "Test User", "email": email, "phone": "3001234567",
        "cnic": "3520212345678", "password": "password123", "role": role,
        "city": "Lahore",
    }
    payload.update(extra or {})
    return client.post("/auth/signup", data=json.dumps(payload), content_type="application/json")


def test_business_signup_creates_service_seeker_profile(client, monkeypatch):
    db = client.db
    resp = _signup(client, monkeypatch, "service_seeker", "biz-signup@test.com",
                   extra={"company_name": "BizCo", "business_type": "Retail"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    uid = db.execute("SELECT id FROM users WHERE email = 'biz-signup@test.com'").fetchone()["id"]
    assert db.execute("SELECT count(*) c FROM service_seeker_profiles WHERE user_id=%s", (uid,)).fetchone()["c"] == 1
    assert db.execute("SELECT count(*) c FROM everyday_user_profiles WHERE user_id=%s", (uid,)).fetchone()["c"] == 0
    assert db.execute("SELECT company_name FROM service_seeker_profiles WHERE user_id=%s", (uid,)).fetchone()["company_name"] == "BizCo"


def test_everyday_signup_creates_everyday_profile_only(client, monkeypatch):
    db = client.db
    resp = _signup(client, monkeypatch, "everyday_user", "eve-signup@test.com")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    uid = db.execute("SELECT id FROM users WHERE email = 'eve-signup@test.com'").fetchone()["id"]
    assert db.execute("SELECT count(*) c FROM everyday_user_profiles WHERE user_id=%s", (uid,)).fetchone()["c"] == 1
    assert db.execute("SELECT count(*) c FROM service_seeker_profiles WHERE user_id=%s", (uid,)).fetchone()["c"] == 0


# ---------------------------------------------------------------------------
# seeker_kind_snapshot set server-side; browser cannot override (#11,#12,#13)
# ---------------------------------------------------------------------------

def _post_order(client, extra=None):
    payload = {
        "pickup_location": "Gujranwala", "dropoff_location": "Karachi",
        "pickup_lat": GUJRANWALA[0], "pickup_lng": GUJRANWALA[1],
        "pickup_date": (date.today() + timedelta(days=2)).isoformat(),
        "pickup_time": "14:30", "goods_type": "General cargo", "goods_weight_tons": 5,
    }
    payload.update(extra or {})
    return client.post("/api/orders", data=json.dumps(payload), content_type="application/json",
                       headers={"X-CSRF-Token": "test-csrf-token"})


def test_everyday_order_snapshot_is_everyday(client):
    db = client.db
    client.login(EVERYDAY)
    resp = _post_order(client)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["order"]["seeker_kind_snapshot"] == "everyday"
    row = db.execute("SELECT seeker_kind_snapshot FROM shipments ORDER BY id DESC LIMIT 1").fetchone()
    assert row["seeker_kind_snapshot"] == "everyday"


def test_business_order_snapshot_is_business(client):
    db = client.db
    client.login(BUSINESS)
    resp = _post_order(client)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["order"]["seeker_kind_snapshot"] == "business"


def test_browser_supplied_seeker_kind_is_ignored(client):
    # Everyday user tries to claim 'business' via the request body — ignored.
    client.login(EVERYDAY)
    resp = _post_order(client, extra={"seeker_kind_snapshot": "business", "seeker_kind": "business"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["order"]["seeker_kind_snapshot"] == "everyday"


def test_order_response_has_no_area_fields(client):
    client.login(EVERYDAY)
    order = _post_order(client).get_json()["order"]
    assert "pickup_area" not in order
    assert "dropoff_area" not in order


# ---------------------------------------------------------------------------
# Everyday users are blocked from business-only backends (403) (#7,#8,#9,#10)
# ---------------------------------------------------------------------------

def test_everyday_agreement_post_forbidden(client):
    client.login(EVERYDAY)
    resp = client.post("/api/agreements/posts", data=json.dumps({"title": "x"}),
                       content_type="application/json", headers={"X-CSRF-Token": "test-csrf-token"})
    assert resp.status_code == 403


def test_everyday_my_agreements_forbidden(client):
    client.login(EVERYDAY)
    assert client.get("/api/agreements/my").status_code == 403


def test_everyday_wallet_forbidden(client):
    client.login(EVERYDAY)
    assert client.get("/api/wallet").status_code == 403


def test_everyday_saved_methods_forbidden(client):
    client.login(EVERYDAY)
    assert client.get("/api/payment-methods").status_code == 403
    resp = client.get("/api/payment-preferences")
    # Endpoint may or may not exist; if it does, it must be 403 for everyday.
    assert resp.status_code in (403, 404)


def test_business_retains_access(client):
    client.login(BUSINESS)
    # Business can read saved methods (empty) and wallet.
    assert client.get("/api/payment-methods").status_code == 200
    assert client.get("/api/wallet").status_code == 200
    # Business is NOT blocked from agreements (passes the role guard; the empty
    # body then fails validation with 400 — the point is it is not a 403).
    resp = client.post("/api/agreements/posts", data=json.dumps({"title": "x"}),
                       content_type="application/json", headers={"X-CSRF-Token": "test-csrf-token"})
    assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Both kinds flow through the ONE shared availability/matching path (#14,#15)
# ---------------------------------------------------------------------------

def test_both_kinds_share_transporter_availability(client):
    db = client.db
    everyday_id = _mk_user(db, "everyday_user", "eve-av@test")
    business_id = _mk_user(db, "service_seeker", "biz-av@test")
    transporter_id = _mk_user(db, "logistics_provider", "carrier-av@test")
    _mk_flatbed(db, transporter_id, *GUJRANWALA)
    db.commit()

    # An everyday order and a business order, same pickup, same shared table.
    for uid, kind in ((everyday_id, EVERYDAY), (business_id, BUSINESS)):
        client.login({"id": uid, "role": kind["role"]})
        assert _post_order(client).status_code == 200

    client.login({"id": transporter_id, "role": "logistics_provider"})
    orders = client.get("/api/orders/available").get_json()["orders"]
    kinds = {o["seeker_kind_snapshot"] for o in orders}
    assert {"everyday", "business"} <= kinds
    # Location matching still works: both are within the truck's radius.
    assert all(o["distance_to_pickup_km"] is not None for o in orders)


# ---------------------------------------------------------------------------
# Checkout formulas unchanged for both roles (#16)
# ---------------------------------------------------------------------------

def test_checkout_funding_split_by_role(db, seeded_db):
    """Everyday: full bid is card-funded (no wallet). Business: wallet first."""
    from shared.payments import build_payment_quote

    everyday_id = _mk_user(db, "everyday_user", "eve-quote@test")
    business_id = _mk_user(db, "service_seeker", "biz-quote@test")
    transporter_id = _mk_user(db, "logistics_provider", "carrier-quote@test")
    truck_id = _mk_flatbed(db, transporter_id, *GUJRANWALA)
    # Business wallet with funds.
    db.execute("INSERT INTO wallets (user_id, role, balance, minimum_required, is_minimum_met) "
               "VALUES (%s, 'client', 100000, 0, true)", (business_id,))
    order_id = db.execute(
        "INSERT INTO shipments (client_user_id, status, seeker_kind_snapshot, goods_weight_tons, "
        "required_truck_types, pickup_lat, pickup_lng) "
        "VALUES (%s, 'open', 'business', 10, '[\"flatbed_trailer_open_semi_trailer\"]', %s, %s) RETURNING id",
        (business_id, GUJRANWALA[0], GUJRANWALA[1]),
    ).fetchone()["id"]
    bid = {"id": 1, "truck_id": truck_id, "transporter_user_id": transporter_id, "bid_price": 50000}
    order = dict(db.execute("SELECT * FROM shipments WHERE id=%s", (order_id,)).fetchone())
    db.commit()

    everyday_quote = build_payment_quote(db, order, bid, {"id": everyday_id, "role": "everyday_user"})
    business_quote = build_payment_quote(db, order, bid, {"id": business_id, "role": "service_seeker"})

    # Everyday: no wallet, whole bid card-funded.
    assert everyday_quote["wallet_funded_amount"] == 0
    assert everyday_quote["card_funded_amount"] == 50000
    # Business: wallet covers it, no card needed.
    assert business_quote["wallet_funded_amount"] == 50000
    assert business_quote["card_funded_amount"] == 0
    # Additive processing fee formula is identical (2.5% of the card-funded part).
    assert everyday_quote["processing_fee_amount"] == pytest.approx(50000 * 0.025, abs=0.01)
