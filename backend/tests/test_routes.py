"""Route-level Flask tests for the one-time payment endpoints.

These exercise the real blueprints (orders + payments + wallet) through a
Flask test client, with the database layer pointed at the isolated
PostgreSQL test schema and authentication stubbed to a known user. They cover
access/ownership, CSRF and role guards, the Idempotency-Key contract, the
three checkout funding paths, saved-method ownership, Start Trip
authorization, and that no response ever leaks a provider token / PAN / CVC.

A genuine concurrency test uses two independent PostgreSQL connections racing
the same checkout to prove the shipment row lock allows only one trip.
"""

import threading

import pytest

from shared.payments import get_payment_provider

VALID_CARD = {
    "card_number": "4242 4242 4242 4242",
    "card_expiry": "12/30",
    "card_cvc": "123",
    "card_holder_name": "Test Payer",
}
FULL_PAN = "4242424242424242"


# ---------------------------------------------------------------------------
# App / client fixtures live in conftest.py (shared with the location suite).
# ---------------------------------------------------------------------------


def _headers(idempotency_key=None, csrf=True):
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = "test-csrf-token"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


# Shared reference point (Gujranwala): the order pickup and the seeded truck
# sit here so the truck is location-eligible (distance 0) under the composed
# cargo + pickup eligibility rule. Callers can override any of these.
_PICKUP = (32.1877, 74.1945)


def _seed_order(db, client_id, status="open", **cols):
    base = {
        "client_user_id": client_id, "status": status,
        "pickup_city": "Gujranwala", "pickup_lat": _PICKUP[0], "pickup_lng": _PICKUP[1],
    }
    base.update(cols)
    keys = list(base.keys())
    placeholders = ", ".join(["%s"] * len(keys))
    order_id = db.execute(
        f"INSERT INTO shipments ({', '.join(keys)}) VALUES ({placeholders}) RETURNING id",
        tuple(base[k] for k in keys),
    ).fetchone()["id"]
    return order_id


def _seed_user(db, user_id, full_name="Ali Traders", email="ali-secret@example.com",
               phone="03001234567", cnic="3520212345671", role="logistics_provider"):
    db.execute(
        "INSERT INTO users (id, full_name, email, phone, cnic, role) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, full_name, email, phone, cnic, role),
    )


def _seed_transporter_profile(db, user_id, company_name="Ali Logistics Pvt Ltd"):
    db.execute(
        "INSERT INTO transporter_profiles (user_id, company_name) VALUES (%s, %s)",
        (user_id, company_name),
    )


def _seed_truck(db, owner_id, status="active", **overrides):
    """Seed an active, high-capacity vehicle owned by the transporter so the
    bid's truck passes the shared current-truck validation at checkout."""
    cols = {
        "owner_user_id": owner_id,
        "truck_number": f"T-{owner_id}",
        "truck_company": "Volvo",
        "truck_model": "Volvo FH",
        "truck_type": "Cargo Truck",
        "catalog_type_key": None,
        "capacity_tons": 100,
        "payload_max_tons": 100,
        "current_city": "Gujranwala",
        "current_lat": _PICKUP[0],
        "current_lng": _PICKUP[1],
        "service_radius_km": 100,
        "status": status,
    }
    cols.update(overrides)
    keys = list(cols.keys())
    placeholders = ", ".join(["%s"] * len(keys))
    return db.execute(
        f"INSERT INTO vehicles ({', '.join(keys)}) VALUES ({placeholders}) RETURNING id",
        tuple(cols[k] for k in keys),
    ).fetchone()["id"]


def _seed_bid(db, order_id, transporter_id, price, truck_id=None, truck_status="active"):
    if truck_id is None:
        truck_id = _seed_truck(db, transporter_id, status=truck_status)
    return db.execute(
        "INSERT INTO shipment_bids (order_id, transporter_user_id, truck_id, bid_price) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (order_id, transporter_id, truck_id, price),
    ).fetchone()["id"]


def _seed_wallet(db, user_id, balance, role="client"):
    db.execute(
        "INSERT INTO wallets (user_id, role, balance, minimum_required, is_minimum_met) "
        "VALUES (%s, %s, %s, 0, true)",
        (user_id, role, balance),
    )


EVERYDAY = {"id": 501, "role": "everyday_user"}
BUSINESS = {"id": 502, "role": "service_seeker"}
TRANSPORTER = {"id": 601, "role": "logistics_provider"}
OTHER_TRANSPORTER = {"id": 602, "role": "logistics_provider"}


def _assert_no_secret_leak(payload_text):
    lowered = payload_text.lower()
    assert FULL_PAN not in payload_text
    assert "provider_token" not in payload_text
    assert "dummytok_" not in payload_text
    assert "card_cvc" not in lowered and "\"cvc\"" not in lowered


# ---------------------------------------------------------------------------
# Quote access / ownership
# ---------------------------------------------------------------------------

def test_quote_requires_ownership(client):
    db = client.db
    order_id = _seed_order(db, BUSINESS["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    _seed_wallet(db, BUSINESS["id"], 150000)
    db.commit()

    # Owner gets a quote.
    client.login(BUSINESS)
    ok = client.get(f"/api/orders/{order_id}/bids/{bid_id}/payment-quote")
    assert ok.status_code == 200
    assert ok.get_json()["quote"]["bid_amount"] == 100000.0

    # A different client cannot quote someone else's order.
    client.login({"id": 999, "role": "service_seeker"})
    denied = client.get(f"/api/orders/{order_id}/bids/{bid_id}/payment-quote")
    assert denied.status_code == 403


# ---------------------------------------------------------------------------
# Checkout: CSRF + role guards + idempotency-key contract
# ---------------------------------------------------------------------------

def test_checkout_rejects_missing_csrf(client):
    db = client.db
    order_id = _seed_order(db, EVERYDAY["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 50000)
    db.commit()
    client.login(EVERYDAY)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD},
        headers=_headers(idempotency_key="key-csrf", csrf=False),
    )
    assert resp.status_code == 403


def test_checkout_rejects_transporter_role(client):
    db = client.db
    order_id = _seed_order(db, EVERYDAY["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 50000)
    db.commit()
    client.login(TRANSPORTER)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD},
        headers=_headers(idempotency_key="key-role"),
    )
    assert resp.status_code == 403


def test_checkout_requires_idempotency_key(client):
    db = client.db
    order_id = _seed_order(db, EVERYDAY["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 50000)
    db.commit()
    client.login(EVERYDAY)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD},
        headers=_headers(csrf=True),          # no Idempotency-Key
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "idempotency_key_required"


def test_checkout_rejects_invalid_idempotency_key(client):
    db = client.db
    order_id = _seed_order(db, EVERYDAY["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 50000)
    db.commit()
    client.login(EVERYDAY)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD},
        headers=_headers(idempotency_key="short"),
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "idempotency_key_invalid"


# ---------------------------------------------------------------------------
# Checkout funding paths
# ---------------------------------------------------------------------------

def test_everyday_card_checkout_route(client):
    db = client.db
    order_id = _seed_order(db, EVERYDAY["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()
    client.login(EVERYDAY)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD},
        headers=_headers(idempotency_key="key-everyday-route"),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["trip"]["status"] == "ready_to_start"
    assert body["payment"]["status"] == "held"
    assert body["payment"]["total_card_charge"] == 102500.0
    _assert_no_secret_leak(resp.get_data(as_text=True))


def test_business_wallet_only_checkout_route(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 150000)
    order_id = _seed_order(db, BUSINESS["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()
    client.login(BUSINESS)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={},
        headers=_headers(idempotency_key="key-wallet-route"),
    )
    assert resp.status_code == 200
    assert resp.get_json()["payment"]["funding_source"] == "wallet"


def test_business_confirmed_shortfall_route(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 40000)
    order_id = _seed_order(db, BUSINESS["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()
    client.login(BUSINESS)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD},
        headers=_headers(idempotency_key="key-shortfall-route"),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["payment"]["funding_source"] == "wallet_card"
    assert body["payment"]["card_funded_amount"] == 60000.0


def test_idempotent_replay_route_returns_same_payment(client):
    db = client.db
    order_id = _seed_order(db, EVERYDAY["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()
    client.login(EVERYDAY)
    first = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD}, headers=_headers(idempotency_key="key-replay-route"),
    )
    second = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD}, headers=_headers(idempotency_key="key-replay-route"),
    )
    assert first.status_code == 200 and second.status_code == 200
    assert second.get_json()["replayed"] is True
    assert first.get_json()["payment"]["id"] == second.get_json()["payment"]["id"]
    count = db.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"]
    assert count == 1


# ---------------------------------------------------------------------------
# Auto-shortfall preference + saved-method ownership
# ---------------------------------------------------------------------------

def test_saved_method_and_auto_preference_flow(client):
    db = client.db
    client.login(BUSINESS)
    created = client.post("/api/payment-methods", json=VALID_CARD, headers=_headers())
    assert created.status_code == 201
    method_id = created.get_json()["method"]["id"]
    _assert_no_secret_leak(created.get_data(as_text=True))

    pref = client.put(
        "/api/payment-preferences",
        json={"auto_shortfall_charge_enabled": True, "default_payment_method_id": method_id},
        headers=_headers(),
    )
    assert pref.status_code == 200
    assert pref.get_json()["preferences"]["auto_shortfall_charge_enabled"] is True

    # A string boolean is rejected.
    bad = client.put(
        "/api/payment-preferences",
        json={"auto_shortfall_charge_enabled": "true"},
        headers=_headers(),
    )
    assert bad.status_code == 400

    # Auto-charge now covers a shortfall with no card in the request body.
    _seed_wallet(db, BUSINESS["id"], 40000)
    order_id = _seed_order(db, BUSINESS["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={}, headers=_headers(idempotency_key="key-auto-route"),
    )
    assert resp.status_code == 200
    assert resp.get_json()["payment"]["status"] == "held"


def test_saved_method_ownership_enforced(client):
    db = client.db
    # BUSINESS owns a card.
    client.login(BUSINESS)
    created = client.post("/api/payment-methods", json=VALID_CARD, headers=_headers())
    method_id = created.get_json()["method"]["id"]

    # A different business user cannot set it as their default.
    client.login({"id": 777, "role": "service_seeker"})
    resp = client.put(
        f"/api/payment-methods/{method_id}",
        json={"is_default": True}, headers=_headers(),
    )
    assert resp.status_code == 404

    # Everyday users cannot manage saved methods at all.
    client.login(EVERYDAY)
    denied = client.get("/api/payment-methods")
    assert denied.status_code == 403


def test_payment_methods_never_expose_token(client):
    client.login(BUSINESS)
    client.post("/api/payment-methods", json=VALID_CARD, headers=_headers())
    listing = client.get("/api/payment-methods")
    assert listing.status_code == 200
    _assert_no_secret_leak(listing.get_data(as_text=True))
    method = listing.get_json()["methods"][0]
    assert method["card_last_four"] == "4242"
    assert "provider_token" not in method


# ---------------------------------------------------------------------------
# Order access via route
# ---------------------------------------------------------------------------

def test_order_details_route_scopes_by_access(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 200000)
    order_id = _seed_order(db, BUSINESS["id"])
    bid_win = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    _seed_bid(db, order_id, OTHER_TRANSPORTER["id"], 110000)
    db.commit()
    client.login(BUSINESS)
    client.post(
        f"/api/orders/{order_id}/bids/{bid_win}/checkout",
        json={}, headers=_headers(idempotency_key="key-access-route"),
    )

    # Owner sees all bids + payment funding detail.
    owner_view = client.get(f"/api/orders/{order_id}").get_json()
    assert owner_view["access"] == "owner"
    assert len(owner_view["bids"]) == 2

    # Accepted transporter sees the order + trip + only their own bid.
    client.login(TRANSPORTER)
    tr_view = client.get(f"/api/orders/{order_id}")
    body = tr_view.get_json()
    assert tr_view.status_code == 200
    assert body["access"] == "accepted_transporter"
    assert len(body["bids"]) == 1
    assert body["bids"][0]["transporter_user_id"] == TRANSPORTER["id"]
    assert body["trip"] is not None
    _assert_no_secret_leak(tr_view.get_data(as_text=True))

    # The losing bidder is unrelated -> 403.
    client.login(OTHER_TRANSPORTER)
    assert client.get(f"/api/orders/{order_id}").status_code == 403


# ---------------------------------------------------------------------------
# Enriched bid comparison + current-truck validation
# ---------------------------------------------------------------------------

SENSITIVE_STRINGS = (
    "ali-secret@example.com",     # email
    "03001234567",                # phone
    "3520212345671",              # cnic
    "driver-cnic-9",              # driver cnic (never selected)
)


def _seed_enriched_bid(db, order_id, transporter_id, price, company="Ali Logistics Pvt Ltd",
                       full_name="Ali Traders", truck_status="active", **truck_overrides):
    """Seed a transporter user + profile + a specced truck + the bid."""
    _seed_user(db, transporter_id, full_name=full_name)
    _seed_transporter_profile(db, transporter_id, company_name=company)
    truck_id = _seed_truck(
        db, transporter_id, status=truck_status,
        truck_number="LES-8842", truck_company="Hino", truck_model="Hino 500",
        catalog_type_key="heavy_rigid_truck_9_15_ton",
        capacity_tons=15, payload_min_tons=9, payload_max_tons=15,
        volume_min_cbm=30, volume_max_cbm=55,
        bed_length_ft=20, bed_width_ft=8, bed_height_ft=8,
        body_style="Rigid cargo body",
        **truck_overrides,
    )
    bid_id = _seed_bid(db, order_id, transporter_id, price, truck_id=truck_id)
    return bid_id, truck_id


def test_owner_receives_enriched_bid_data_without_sensitive_fields(client):
    db = client.db
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=10, goods_type="Steel bars")
    bid_id, truck_id = _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()

    client.login(BUSINESS)
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["access"] == "owner"
    assert len(body["bids"]) == 1
    bid = body["bids"][0]

    # (1) Enriched transporter + truck data.
    assert bid["transporter"]["display_name"] == "Ali Traders"
    assert bid["transporter"]["company_name"] == "Ali Logistics Pvt Ltd"
    assert bid["transporter"]["completed_trips"] == 0
    assert bid["truck"]["truck_number"] == "LES-8842"
    assert bid["truck"]["type_name"] == "Heavy rigid truck 9-15 ton"
    assert bid["truck"]["type_key"] == "heavy_rigid_truck_9_15_ton"
    assert bid["truck"]["capacity_tons"] == 15.0
    assert bid["truck"]["payload_max_tons"] == 15.0
    assert bid["truck"]["volume_max_cbm"] == 55.0
    assert bid["truck"]["bed_length_ft"] == 20.0
    assert bid["truck"]["status"] == "active"
    # Legacy top-level fields preserved for backward compatibility.
    assert bid["bid_price"] == 100000.0
    assert bid["truck_id"] == truck_id
    assert bid["can_checkout"] is True
    assert bid["unavailable_reason"] is None

    # (2) No sensitive fields anywhere in the JSON.
    text = resp.get_data(as_text=True)
    for secret in SENSITIVE_STRINGS:
        assert secret not in text
    for banned in ("email", "phone", "cnic", "driver_cnic", "payout", "tracking_id",
                   "traccar", "provider_token"):
        assert banned not in text


def test_withdrawn_bids_excluded_from_comparison(client):
    db = client.db
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=10)
    live_id, _ = _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    gone_id, _ = _seed_enriched_bid(db, order_id, OTHER_TRANSPORTER["id"], 90000,
                                    company="Gone Ltd", full_name="Gone Bidder")
    db.execute("UPDATE shipment_bids SET status = 'withdrawn' WHERE id = %s", (gone_id,))
    db.commit()

    client.login(BUSINESS)
    body = client.get(f"/api/orders/{order_id}").get_json()
    ids = [b["id"] for b in body["bids"]]
    assert live_id in ids
    assert gone_id not in ids
    assert len(body["bids"]) == 1


def test_accepted_transporter_sees_only_their_own_enriched_bid(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 300000)
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=10)
    win_id, _ = _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    _seed_enriched_bid(db, order_id, OTHER_TRANSPORTER["id"], 90000,
                       company="Rival Ltd", full_name="Rival Bidder")
    db.commit()
    client.login(BUSINESS)
    client.post(
        f"/api/orders/{order_id}/bids/{win_id}/checkout",
        json={}, headers=_headers(idempotency_key="key-enriched-accept"),
    )

    client.login(TRANSPORTER)
    resp = client.get(f"/api/orders/{order_id}")
    body = resp.get_json()
    assert body["access"] == "accepted_transporter"
    assert len(body["bids"]) == 1
    assert body["bids"][0]["transporter_user_id"] == TRANSPORTER["id"]
    # Their own bid still carries the enriched shape.
    assert body["bids"][0]["truck"]["truck_number"] == "LES-8842"
    assert "Rival" not in resp.get_data(as_text=True)


def test_unrelated_users_receive_403(client):
    db = client.db
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=10)
    _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()
    # A different client.
    client.login({"id": 4040, "role": "service_seeker"})
    assert client.get(f"/api/orders/{order_id}").status_code == 403
    # A transporter who never bid.
    client.login(OTHER_TRANSPORTER)
    assert client.get(f"/api/orders/{order_id}").status_code == 403


def test_quote_rejects_inactive_truck(client):
    db = client.db
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=10)
    bid_id, truck_id = _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    _seed_wallet(db, BUSINESS["id"], 300000)
    db.execute("UPDATE vehicles SET status = 'inactive' WHERE id = %s", (truck_id,))
    db.commit()
    client.login(BUSINESS)
    resp = client.get(f"/api/orders/{order_id}/bids/{bid_id}/payment-quote")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "bid_truck_unavailable"


def test_quote_rejects_truck_no_longer_owned_by_bidder(client):
    db = client.db
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=10)
    bid_id, truck_id = _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    _seed_wallet(db, BUSINESS["id"], 300000)
    db.execute("UPDATE vehicles SET owner_user_id = %s WHERE id = %s",
               (OTHER_TRANSPORTER["id"], truck_id))
    db.commit()
    client.login(BUSINESS)
    resp = client.get(f"/api/orders/{order_id}/bids/{bid_id}/payment-quote")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "bid_truck_unavailable"


def test_quote_rejects_truck_that_no_longer_matches_order(client):
    db = client.db
    # Truck capacity 15 t; raise the load to 40 t so it no longer fits.
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=40)
    bid_id, truck_id = _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    _seed_wallet(db, BUSINESS["id"], 300000)
    db.commit()
    client.login(BUSINESS)
    resp = client.get(f"/api/orders/{order_id}/bids/{bid_id}/payment-quote")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "bid_truck_unavailable"


def test_checkout_rechecks_truck_under_lock_and_makes_no_mutations(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 300000)
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=10)
    bid_id, truck_id = _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    # Truck goes inactive after the bid — checkout must catch it under the lock.
    db.execute("UPDATE vehicles SET status = 'maintenance' WHERE id = %s", (truck_id,))
    db.commit()

    client.login(BUSINESS)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={}, headers=_headers(idempotency_key="key-truck-gone"),
    )
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "bid_truck_unavailable"

    # (10) No provider charge, no wallet mutation, no payment, no trip, no accept.
    assert db.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) AS c FROM shipment_trips").fetchone()["c"] == 0
    assert db.execute("SELECT status FROM shipment_bids WHERE id = %s", (bid_id,)).fetchone()["status"] == "pending"
    assert float(db.execute("SELECT balance FROM wallets WHERE user_id = %s", (BUSINESS["id"],)).fetchone()["balance"]) == 300000.0
    assert db.execute("SELECT status FROM shipments WHERE id = %s", (order_id,)).fetchone()["status"] == "open"


def test_valid_enriched_bid_completes_checkout(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 300000)
    order_id = _seed_order(db, BUSINESS["id"], goods_weight_tons=10)
    bid_id, truck_id = _seed_enriched_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()
    client.login(BUSINESS)
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={}, headers=_headers(idempotency_key="key-enriched-ok"),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["trip"]["status"] == "ready_to_start"
    assert body["payment"]["status"] == "held"
    assert db.execute("SELECT status FROM shipment_bids WHERE id = %s", (bid_id,)).fetchone()["status"] == "accepted"


# ---------------------------------------------------------------------------
# Start Trip authorization
# ---------------------------------------------------------------------------

def test_start_trip_authorization_route(client):
    db = client.db
    order_id = _seed_order(db, EVERYDAY["id"])
    bid_id = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    db.commit()
    client.login(EVERYDAY)
    checkout = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        json={"card": VALID_CARD}, headers=_headers(idempotency_key="key-start-route"),
    )
    trip_id = checkout.get_json()["trip"]["id"]

    # The wrong transporter cannot start.
    client.login(OTHER_TRANSPORTER)
    denied = client.post(f"/api/orders/{order_id}/trips/{trip_id}/start", json={}, headers=_headers())
    assert denied.status_code == 403

    # A client cannot start (role guard).
    client.login(EVERYDAY)
    role_denied = client.post(f"/api/orders/{order_id}/trips/{trip_id}/start", json={}, headers=_headers())
    assert role_denied.status_code == 403

    # The accepted transporter starts, idempotently.
    client.login(TRANSPORTER)
    started = client.post(f"/api/orders/{order_id}/trips/{trip_id}/start", json={}, headers=_headers())
    assert started.status_code == 200
    assert started.get_json()["trip"]["status"] == "in_progress"
    again = client.post(f"/api/orders/{order_id}/trips/{trip_id}/start", json={}, headers=_headers())
    assert again.get_json()["already_started"] is True


# ---------------------------------------------------------------------------
# Wallet top-up: shared card validation + role-specific fee semantics (item 6)
# ---------------------------------------------------------------------------

def test_topup_rejects_invalid_card(client):
    client.login(BUSINESS)
    resp = client.post(
        "/api/wallet/topup",
        json={"amount": 10000, "card_number": "123", "card_expiry": "12/30",
              "card_cvc": "123", "card_holder_name": "X"},
        headers=_headers(idempotency_key="key-topup-badcard"),
    )
    assert resp.status_code == 400


def test_topup_requires_idempotency_key_and_makes_no_charge(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 0)
    db.commit()
    client.login(BUSINESS)
    resp = client.post(
        "/api/wallet/topup",
        json={"amount": 10000, **VALID_CARD},
        headers=_headers(),                       # no Idempotency-Key
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "idempotency_key_required"
    # No transaction/credit happened.
    count = db.execute(
        "SELECT COUNT(*) AS c FROM wallet_transactions WHERE user_id = %s", (BUSINESS["id"],)
    ).fetchone()["c"]
    assert count == 0
    assert float(db.execute("SELECT balance FROM wallets WHERE user_id = %s", (BUSINESS["id"],)).fetchone()["balance"]) == 0.0


def test_topup_business_credits_exact_amount_and_charges_fee(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 0)
    db.commit()
    client.login(BUSINESS)
    resp = client.post(
        "/api/wallet/topup",
        json={"amount": 10000, **VALID_CARD},
        headers=_headers(idempotency_key="key-topup-biz"),
    )
    assert resp.status_code == 200
    tx = resp.get_json()["transaction"]
    # Business: card charged amount + 2.5% fee; wallet credited EXACTLY amount.
    assert tx["gross_amount"] == 10250.0
    assert tx["gateway_fee"] == 250.0
    assert tx["net_amount"] == 10000.0
    assert tx["new_balance"] == 10000.0
    _assert_no_secret_leak(resp.get_data(as_text=True))
    # Provider reference persisted on the transaction.
    row = db.execute(
        "SELECT provider_name, provider_reference FROM wallet_transactions "
        "WHERE user_id = %s AND type = 'topup'", (BUSINESS["id"],),
    ).fetchone()
    assert row["provider_name"] == "dummycard"
    assert row["provider_reference"] and row["provider_reference"].startswith("dummych_")


def test_topup_replay_returns_original_without_card_data(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 0)
    db.commit()
    client.login(BUSINESS)
    first = client.post(
        "/api/wallet/topup", json={"amount": 10000, **VALID_CARD},
        headers=_headers(idempotency_key="key-topup-replay"),
    )
    # Replay with the SAME amount but NO card data — must still replay.
    second = client.post(
        "/api/wallet/topup", json={"amount": 10000},
        headers=_headers(idempotency_key="key-topup-replay"),
    )
    assert first.status_code == 200 and second.status_code == 200
    assert second.get_json()["replayed"] is True
    assert second.get_json()["transaction"]["new_balance"] == 10000.0
    # Exactly one credit and one transaction.
    count = db.execute(
        "SELECT COUNT(*) AS c FROM wallet_transactions WHERE user_id = %s AND type = 'topup'",
        (BUSINESS["id"],),
    ).fetchone()["c"]
    assert count == 1
    assert float(db.execute("SELECT balance FROM wallets WHERE user_id = %s", (BUSINESS["id"],)).fetchone()["balance"]) == 10000.0


def test_topup_same_key_different_amount_conflicts_without_mutation(client):
    db = client.db
    _seed_wallet(db, BUSINESS["id"], 0)
    db.commit()
    client.login(BUSINESS)
    client.post(
        "/api/wallet/topup", json={"amount": 10000, **VALID_CARD},
        headers=_headers(idempotency_key="key-topup-conflict"),
    )
    # Same key, DIFFERENT amount -> 409, no second charge or mutation.
    resp = client.post(
        "/api/wallet/topup", json={"amount": 25000, **VALID_CARD},
        headers=_headers(idempotency_key="key-topup-conflict"),
    )
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "idempotency_key_conflict"
    count = db.execute(
        "SELECT COUNT(*) AS c FROM wallet_transactions WHERE user_id = %s AND type = 'topup'",
        (BUSINESS["id"],),
    ).fetchone()["c"]
    assert count == 1
    assert float(db.execute("SELECT balance FROM wallets WHERE user_id = %s", (BUSINESS["id"],)).fetchone()["balance"]) == 10000.0


def test_topup_missing_key_for_user_without_wallet_creates_nothing(client):
    db = client.db
    # NO wallet seeded for this user.
    no_wallet_user = {"id": 8080, "role": "service_seeker"}
    client.login(no_wallet_user)
    resp = client.post(
        "/api/wallet/topup", json={"amount": 10000, **VALID_CARD},
        headers=_headers(),                            # no Idempotency-Key
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "idempotency_key_required"
    # No wallet row and no transaction were created (validation happens first).
    assert db.execute("SELECT COUNT(*) AS c FROM wallets WHERE user_id = %s", (no_wallet_user["id"],)).fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) AS c FROM wallet_transactions WHERE user_id = %s", (no_wallet_user["id"],)).fetchone()["c"] == 0


def test_topup_overlength_key_creates_no_wallet(client):
    db = client.db
    no_wallet_user = {"id": 8081, "role": "service_seeker"}
    client.login(no_wallet_user)
    resp = client.post(
        "/api/wallet/topup", json={"amount": 10000, **VALID_CARD},
        headers=_headers(idempotency_key="x" * 200),   # over the 128 limit
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "idempotency_key_invalid"
    assert db.execute("SELECT COUNT(*) AS c FROM wallets WHERE user_id = %s", (no_wallet_user["id"],)).fetchone()["c"] == 0


def test_topup_transporter_keeps_legacy_gross_semantics(client):
    db = client.db
    _seed_wallet(db, TRANSPORTER["id"], 60000, role="transporter")
    # Transporter wallets already meet the minimum here.
    db.execute("UPDATE wallets SET is_minimum_met = true WHERE user_id = %s", (TRANSPORTER["id"],))
    db.commit()
    client.login(TRANSPORTER)
    resp = client.post(
        "/api/wallet/topup",
        json={"amount": 10000, **VALID_CARD},
        headers=_headers(idempotency_key="key-topup-transporter"),
    )
    assert resp.status_code == 200
    tx = resp.get_json()["transaction"]
    # Transporter (legacy): fee taken OUT of the entered amount, remainder credited.
    assert tx["gross_amount"] == 10000.0
    assert tx["gateway_fee"] == 250.0
    assert tx["net_amount"] == 9750.0


# ---------------------------------------------------------------------------
# Genuine concurrency: two independent connections race the same order
# ---------------------------------------------------------------------------

def test_concurrent_checkout_creates_only_one_trip(seeded_db, pg_session_info):
    import psycopg2

    from shared.db import Db
    from shared.payments import CheckoutError, perform_checkout

    db = seeded_db
    schema = pg_session_info["schema"]
    url = pg_session_info["url"]

    _seed_wallet(db, BUSINESS["id"], 500000)
    order_id = _seed_order(db, BUSINESS["id"])
    bid_a = _seed_bid(db, order_id, TRANSPORTER["id"], 100000)
    bid_b = _seed_bid(db, order_id, OTHER_TRANSPORTER["id"], 90000)
    db.commit()

    results = {}
    barrier = threading.Barrier(2)

    def run(tag, bid_id, key):
        conn = psycopg2.connect(url)
        with conn.cursor() as cur:
            cur.execute(f'set search_path to "{schema}"')
        wrapper = Db(conn)
        try:
            barrier.wait()          # start both together
            perform_checkout(wrapper, BUSINESS, order_id, bid_id, payload={}, idempotency_key=key)
            conn.commit()
            results[tag] = "ok"
        except CheckoutError as exc:
            conn.rollback()
            results[tag] = f"error:{exc.code}"
        except Exception as exc:
            conn.rollback()
            results[tag] = f"exc:{exc}"
        finally:
            conn.close()

    t1 = threading.Thread(target=run, args=("a", bid_a, "key-conc-a"))
    t2 = threading.Thread(target=run, args=("b", bid_b, "key-conc-b"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    outcomes = sorted(results.values())
    # Exactly one succeeds; the other is cleanly rejected (order no longer open).
    assert outcomes.count("ok") == 1
    assert any(o.startswith("error:") for o in outcomes)

    trips = db.execute("SELECT COUNT(*) AS c FROM shipment_trips WHERE order_id = %s", (order_id,)).fetchone()["c"]
    payments = db.execute("SELECT COUNT(*) AS c FROM payments WHERE shipment_id = %s", (order_id,)).fetchone()["c"]
    assert trips == 1
    assert payments == 1


def _topup_worker(url, schema, user, amount, key, results, tag, barrier):
    """Drive the REAL production top-up service on an independent connection.

    No business logic is duplicated here — this only opens a second DB
    connection into the test schema and calls perform_wallet_topup, exactly as
    the HTTP route does.
    """
    import psycopg2

    from shared.db import Db
    from shared.payments import CheckoutError, perform_wallet_topup

    conn = psycopg2.connect(url)
    with conn.cursor() as cur:
        cur.execute(f'set search_path to "{schema}"')
    db = Db(conn)
    try:
        barrier.wait()
        result = perform_wallet_topup(db, user, amount, VALID_CARD, key)
        conn.commit()
        results[tag] = "replay" if result["replayed"] else "ok"
    except CheckoutError as exc:
        conn.rollback()
        results[tag] = f"error:{exc.code}"
    except Exception as exc:
        conn.rollback()
        results[tag] = f"exc:{type(exc).__name__}"
    finally:
        conn.close()


def test_concurrent_same_key_topup_credits_once(seeded_db, pg_session_info):
    # Two independent connections run the production service with the SAME key.
    db = seeded_db
    schema, url = pg_session_info["schema"], pg_session_info["url"]
    get_payment_provider().reset()
    _seed_wallet(db, BUSINESS["id"], 0)
    db.commit()

    results = {}
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(target=_topup_worker, args=(url, schema, BUSINESS, 10000, "same-key-concurrent", results, tag, barrier))
        for tag in ("a", "b")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # One charges+credits, the other replays — exactly one credit either way.
    assert "ok" in results.values()
    assert all(v in ("ok", "replay") for v in results.values()), results
    tx_count = db.execute(
        "SELECT COUNT(*) AS c FROM wallet_transactions WHERE user_id = %s AND type = 'topup'",
        (BUSINESS["id"],),
    ).fetchone()["c"]
    assert tx_count == 1                              # exactly one credit
    assert float(db.execute("SELECT balance FROM wallets WHERE user_id = %s", (BUSINESS["id"],)).fetchone()["balance"]) == 10000.0


def test_concurrent_different_keys_both_credit(seeded_db, pg_session_info):
    db = seeded_db
    schema, url = pg_session_info["schema"], pg_session_info["url"]
    get_payment_provider().reset()
    _seed_wallet(db, BUSINESS["id"], 0)
    db.commit()

    results = {}
    barrier = threading.Barrier(2)
    t1 = threading.Thread(target=_topup_worker, args=(url, schema, BUSINESS, 10000, "key-diff-1", results, "a", barrier))
    t2 = threading.Thread(target=_topup_worker, args=(url, schema, BUSINESS, 25000, "key-diff-2", results, "b", barrier))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert sorted(results.values()) == ["ok", "ok"], results
    tx_count = db.execute(
        "SELECT COUNT(*) AS c FROM wallet_transactions WHERE user_id = %s AND type = 'topup'",
        (BUSINESS["id"],),
    ).fetchone()["c"]
    assert tx_count == 2
    # Both amounts serialized into the final balance (35000, not a lost update).
    assert float(db.execute("SELECT balance FROM wallets WHERE user_id = %s", (BUSINESS["id"],)).fetchone()["balance"]) == 35000.0
