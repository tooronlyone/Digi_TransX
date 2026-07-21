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
# App / client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_env(seeded_db, pg_session_info, monkeypatch):
    """Flask app wired to the test schema + a stub user registry.

    Returns (app, ctx) where ctx holds mutable test state (current user,
    seeded ids). The route modules' open_db() is redirected to a fresh
    connection into the same isolated schema so handlers run their own real
    transactions, exactly like production.
    """
    import psycopg2
    from contextlib import contextmanager
    from flask import Flask

    from shared.db import Db
    import auth.helpers as auth_helpers
    import orders.routes as orders_routes
    import payments.routes as payments_routes
    import wallet.routes as wallet_routes
    import wallet.helpers as wallet_helpers

    schema = pg_session_info["schema"]
    url = pg_session_info["url"]

    open_connections = []

    @contextmanager
    def test_open_db():
        conn = psycopg2.connect(url)
        open_connections.append(conn)
        try:
            with conn.cursor() as cur:
                cur.execute(f'set search_path to "{schema}"')
            wrapper = Db(conn)
            yield wrapper
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Redirect every module-local open_db reference to the test schema.
    for module in (orders_routes, payments_routes, wallet_routes, wallet_helpers, auth_helpers):
        if hasattr(module, "open_db"):
            monkeypatch.setattr(module, "open_db", test_open_db)

    ctx = {"user": None}

    def fake_get_user_by_id(user_id):
        user = ctx["user"]
        if user and str(user["id"]) == str(user_id):
            return dict(user)
        return None

    monkeypatch.setattr(auth_helpers, "get_user_by_id", fake_get_user_by_id)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["SESSION_COOKIE_SECURE"] = False
    app.register_blueprint(orders_routes.orders_blueprint)
    app.register_blueprint(payments_routes.payments_blueprint)
    app.register_blueprint(wallet_routes.wallet_blueprint)

    yield app, ctx, seeded_db

    for conn in open_connections:
        try:
            conn.close()
        except Exception:
            pass


@pytest.fixture
def client(app_env):
    app, ctx, db = app_env
    test_client = app.test_client()

    def login(user):
        ctx["user"] = user
        with test_client.session_transaction() as sess:
            sess["user_id"] = user["id"]
            sess["csrf_token"] = "test-csrf-token"

    test_client.login = login
    test_client.ctx = ctx
    test_client.db = db
    return test_client


def _headers(idempotency_key=None, csrf=True):
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = "test-csrf-token"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _seed_order(db, client_id, status="open"):
    order_id = db.execute(
        "INSERT INTO shipments (client_user_id, status) VALUES (%s, %s) RETURNING id",
        (client_id, status),
    ).fetchone()["id"]
    return order_id


def _seed_bid(db, order_id, transporter_id, price, truck_id=1):
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
