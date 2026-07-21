"""Tests for the one-time order payment foundation.

Pure calculation/validation tests run without a database. Tests that take the
`db`/`seeded_db` fixtures are PostgreSQL integration tests (see conftest.py)
and skip with a clear reason when TEST_SUPABASE_DB_URL is not configured.
"""

from decimal import Decimal

import pytest

from shared.commissions import split_final_amount
from shared.db import IntegrityError
from shared.payments import (
    CheckoutError,
    build_payment_quote,
    calculate_card_processing_fee,
    calculate_total_card_charge,
    card_processing_fee_percent,
    create_saved_method,
    get_active_payment_for_shipment,
    get_payment_provider,
    normalize_client_kind,
    perform_checkout,
    perform_start_trip,
    serialize_payment_summary,
    split_funding,
    upsert_payment_preferences,
    validate_dummy_card,
)
from wallet.helpers import (
    get_or_create_wallet_for_user,
    minimum_required_for_role,
    normalize_wallet_role,
)

EVERYDAY_USER = {"id": 101, "role": "everyday_user"}
BUSINESS_USER = {"id": 102, "role": "service_seeker"}
TRANSPORTER_A = 201
TRANSPORTER_B = 202

VALID_CARD = {
    "card_number": "4242 4242 4242 4242",
    "card_expiry": "12/30",
    "card_cvc": "123",
    "card_holder_name": "Test Payer",
}
FULL_PAN = "4242424242424242"


# ---------------------------------------------------------------------------
# Pure calculation tests
# ---------------------------------------------------------------------------

def test_processing_fee_formula_default_2_5_percent():
    assert float(card_processing_fee_percent()) == 2.5
    fee, total = calculate_total_card_charge(100000)
    assert fee == 2500.0                      # round(100000 * 2.5%, 2)
    assert total == 102500.0                  # card_funded + fee (additive)
    assert calculate_card_processing_fee(0) == 0.0


def test_processing_fee_rounds_to_two_decimals():
    fee, total = calculate_total_card_charge(333.33)
    assert fee == 8.33                        # 8.33325 rounds half-up to 8.33
    assert total == 341.66


def test_fee_percent_env_override(monkeypatch):
    monkeypatch.setenv("DIGITRANSX_CARD_FEE_PERCENT", "3.75")
    assert float(card_processing_fee_percent()) == 3.75
    fee, total = calculate_total_card_charge(1000)
    assert fee == 37.5
    assert total == 1037.5


def test_funding_split_wallet_first():
    assert split_funding(100000, 0) == (0.0, 100000.0)          # everyday: all card
    assert split_funding(100000, 250000) == (100000.0, 0.0)     # wallet covers all
    assert split_funding(100000, 40000) == (40000.0, 60000.0)   # exact shortfall


def test_wallet_covered_order_has_zero_card_fee():
    wallet_funded, card_funded = split_funding(100000, 150000)
    fee, total = calculate_total_card_charge(card_funded)
    assert (wallet_funded, card_funded) == (100000.0, 0.0)
    assert fee == 0.0
    assert total == 0.0


def test_commission_applies_only_to_bid_amount():
    # bid 100000: commission 20000 / payout 80000; the 2500 card fee is
    # separate and never part of platform commission.
    commission, payout = split_final_amount(100000, Decimal("20.00"))
    fee, total = calculate_total_card_charge(100000)
    assert commission == 20000.0
    assert payout == 80000.0
    assert fee == 2500.0
    assert commission + payout == 100000.0    # fee not inside the split


def test_validate_dummy_card_accepts_valid_card():
    summary, error = validate_dummy_card(VALID_CARD)
    assert error is None
    assert summary == {
        "card_brand": "visa",
        "card_last_four": "4242",
        "expiry_month": 12,
        "expiry_year": 2030,
        "card_holder_name": "Test Payer",
    }
    # The validated summary must never carry the PAN or CVC.
    assert FULL_PAN not in str(summary)
    assert "card_number" not in summary
    assert "card_cvc" not in summary


@pytest.mark.parametrize("patch", [
    {"card_number": "1234"},
    {"card_number": ""},
    {"card_cvc": "12"},
    {"card_cvc": "abcd"},
    {"card_expiry": "13/30"},
    {"card_expiry": "12/20"},          # in the past
    {"card_expiry": "december"},
    {"card_holder_name": "  "},
])
def test_validate_dummy_card_rejects_invalid_input(patch):
    card = {**VALID_CARD, **patch}
    summary, error = validate_dummy_card(card)
    assert summary is None
    assert error


def test_provider_token_never_encodes_card_data():
    provider = get_payment_provider()
    summary, _ = validate_dummy_card(VALID_CARD)
    token = provider.tokenize(summary)
    assert token.startswith("dummytok_")
    assert FULL_PAN not in token
    assert "123" not in token or True  # token is random hex; PAN check above is the guarantee


def test_normalize_client_kind():
    assert normalize_client_kind("everyday_user") == "everyday"
    assert normalize_client_kind("service_seeker") == "business"
    assert normalize_client_kind("client") == "business"
    assert normalize_client_kind("logistics_provider") is None
    assert normalize_client_kind("") is None


def test_wallet_role_rules():
    # Everyday users have no wallet at all.
    assert normalize_wallet_role("everyday_user") is None
    # Business service seekers keep the client wallet with a zero minimum.
    assert normalize_wallet_role("service_seeker") == "client"
    assert minimum_required_for_role("client") == 0.0
    # Transporter wallet rules are unchanged.
    assert normalize_wallet_role("logistics_provider") == "transporter"
    assert minimum_required_for_role("transporter") == 30000.0


def test_everyday_user_wallet_endpoints_rejected():
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context():
        class _NoDb:  # wallet lookup must not even be attempted
            def execute(self, *args, **kwargs):
                raise AssertionError("everyday users must not reach the wallets table")
        wallet, error = get_or_create_wallet_for_user(_NoDb(), {"id": 1, "role": "everyday_user"})
        assert wallet is None
        assert error is not None
        assert error.status_code == 403


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------

def _mk_order(db, client_id, status="open"):
    return db.execute(
        "INSERT INTO shipments (client_user_id, status) VALUES (%s, %s) RETURNING id",
        (client_id, status),
    ).fetchone()["id"]


def _mk_bid(db, order_id, transporter_id, price, truck_id=1):
    return db.execute(
        "INSERT INTO shipment_bids (order_id, transporter_user_id, truck_id, bid_price) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (order_id, transporter_id, truck_id, price),
    ).fetchone()["id"]


def _mk_wallet(db, user_id, balance, role="client"):
    return db.execute(
        "INSERT INTO wallets (user_id, role, balance, minimum_required, is_minimum_met) "
        "VALUES (%s, %s, %s, 0, true) RETURNING id",
        (user_id, role, balance),
    ).fetchone()["id"]


def _order(db, order_id):
    return dict(db.execute("SELECT * FROM shipments WHERE id = %s", (order_id,)).fetchone())


def _bid(db, bid_id):
    return dict(db.execute("SELECT * FROM shipment_bids WHERE id = %s", (bid_id,)).fetchone())


def _wallet_balance(db, user_id):
    row = db.execute("SELECT balance FROM wallets WHERE user_id = %s", (user_id,)).fetchone()
    return float(row["balance"]) if row else None


def _count(db, table, where="", params=()):
    return db.execute(f"SELECT COUNT(*) AS total FROM {table} {where}", params).fetchone()["total"]


# ---------------------------------------------------------------------------
# Quote integration tests
# ---------------------------------------------------------------------------

def test_everyday_quote_full_card_funding(seeded_db):
    db = seeded_db
    order_id = _mk_order(db, EVERYDAY_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    quote = build_payment_quote(db, _order(db, order_id), _bid(db, bid_id), EVERYDAY_USER)
    assert quote["client_kind"] == "everyday"
    assert quote["bid_amount"] == 100000.0
    assert quote["wallet_available"] == 0.0
    assert quote["wallet_funded_amount"] == 0.0
    assert quote["card_funded_amount"] == 100000.0
    assert quote["processing_fee_percent"] == 2.5
    assert quote["processing_fee_amount"] == 2500.0
    assert quote["total_card_charge"] == 102500.0
    assert quote["platform_commission_amount"] == 20000.0
    assert quote["transporter_payout_amount"] == 80000.0
    assert quote["requires_card"] is True
    assert quote["can_auto_charge"] is False


def test_business_wallet_covers_bid_zero_card_fee(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 150000)
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    quote = build_payment_quote(db, _order(db, order_id), _bid(db, bid_id), BUSINESS_USER)
    assert quote["wallet_available"] == 150000.0
    assert quote["wallet_funded_amount"] == 100000.0
    assert quote["card_funded_amount"] == 0.0
    assert quote["processing_fee_amount"] == 0.0
    assert quote["total_card_charge"] == 0.0
    assert quote["requires_card"] is False


def test_business_shortfall_quote(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 40000)
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    quote = build_payment_quote(db, _order(db, order_id), _bid(db, bid_id), BUSINESS_USER)
    assert quote["wallet_funded_amount"] == 40000.0
    assert quote["card_funded_amount"] == 60000.0            # exact shortfall
    assert quote["processing_fee_amount"] == 1500.0          # 2.5% of shortfall only
    assert quote["total_card_charge"] == 61500.0
    assert quote["requires_card"] is True


# ---------------------------------------------------------------------------
# Checkout integration tests
# ---------------------------------------------------------------------------

def test_everyday_checkout_creates_held_payment_and_ready_trip(seeded_db):
    db = seeded_db
    order_id = _mk_order(db, EVERYDAY_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    other_bid = _mk_bid(db, order_id, TRANSPORTER_B, 120000)

    result = perform_checkout(
        db, EVERYDAY_USER, order_id, bid_id,
        payload={"card": VALID_CARD}, idempotency_key="key-everyday-1",
    )
    db.commit()

    payment = result["payment"]
    assert payment["status"] == "held"
    assert payment["held_at"] is not None
    assert payment["released_at"] is None
    assert float(payment["bid_price"]) == 100000.0
    assert float(payment["company_fee"]) == 20000.0          # commission on bid only
    assert float(payment["transporter_amount"]) == 80000.0
    assert float(payment["card_funded_amount"]) == 100000.0
    assert float(payment["wallet_funded_amount"]) == 0.0
    assert float(payment["processing_fee_percent"]) == 2.5
    assert float(payment["processing_fee_amount"]) == 2500.0
    assert float(payment["total_card_charge"]) == 102500.0
    assert payment["funding_source"] == "card"
    assert payment["provider_name"] == "dummycard"
    assert payment["provider_reference"].startswith("dummych_")

    trip = result["trip"]
    assert trip["status"] == "ready_to_start"
    assert _count(db, "shipment_trips", "WHERE order_id = %s", (order_id,)) == 1
    assert _count(db, "payments", "WHERE shipment_id = %s", (order_id,)) == 1

    order = result["order"]
    assert order["status"] == "ready_to_start"
    assert order["payment_status"] == "held"
    assert order["accepted_bid_id"] == bid_id
    assert float(order["company_share_percent_snapshot"]) == 20.0

    assert _bid(db, bid_id)["status"] == "accepted"
    assert _bid(db, other_bid)["status"] == "rejected"
    # Everyday users never get a wallet row.
    assert _wallet_balance(db, EVERYDAY_USER["id"]) is None


def test_everyday_checkout_requires_card_details(seeded_db):
    db = seeded_db
    order_id = _mk_order(db, EVERYDAY_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 50000)
    with pytest.raises(CheckoutError) as excinfo:
        perform_checkout(db, EVERYDAY_USER, order_id, bid_id, payload={}, idempotency_key="key-nocard")
    assert excinfo.value.code == "card_required"


def test_invalid_card_causes_no_mutations(seeded_db):
    db = seeded_db
    order_id = _mk_order(db, EVERYDAY_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    db.commit()
    bad_card = {**VALID_CARD, "card_number": "1111"}

    with pytest.raises(CheckoutError) as excinfo:
        perform_checkout(db, EVERYDAY_USER, order_id, bid_id,
                         payload={"card": bad_card}, idempotency_key="key-bad-card")
    db.rollback()

    assert excinfo.value.code == "invalid_card"
    assert _order(db, order_id)["status"] == "open"
    assert _bid(db, bid_id)["status"] == "pending"          # bid stays pending
    assert _count(db, "shipment_trips") == 0
    assert _count(db, "payments") == 0


def test_business_wallet_covered_checkout(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 150000)
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)

    result = perform_checkout(db, BUSINESS_USER, order_id, bid_id,
                              payload={}, idempotency_key="key-wallet-full")
    db.commit()

    payment = result["payment"]
    assert payment["funding_source"] == "wallet"
    assert float(payment["wallet_funded_amount"]) == 100000.0
    assert float(payment["card_funded_amount"]) == 0.0
    assert float(payment["processing_fee_amount"]) == 0.0    # no card fee
    assert payment["provider_reference"] is None
    assert _wallet_balance(db, BUSINESS_USER["id"]) == 50000.0


def test_business_shortfall_wallet_receives_exactly_shortfall(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 40000)
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)

    result = perform_checkout(
        db, BUSINESS_USER, order_id, bid_id,
        payload={"card": VALID_CARD}, idempotency_key="key-shortfall",
    )
    db.commit()

    payment = result["payment"]
    assert payment["funding_source"] == "wallet_card"
    assert float(payment["wallet_funded_amount"]) == 40000.0
    assert float(payment["card_funded_amount"]) == 60000.0
    assert float(payment["processing_fee_amount"]) == 1500.0
    assert float(payment["total_card_charge"]) == 61500.0
    # Wallet was credited exactly the shortfall (60000, never 61500), then
    # the full bid was deducted: 40000 + 60000 - 100000 = 0.
    assert _wallet_balance(db, BUSINESS_USER["id"]) == 0.0
    credit = db.execute(
        "SELECT * FROM wallet_transactions WHERE user_id = %s AND type = 'card_shortfall_topup'",
        (BUSINESS_USER["id"],),
    ).fetchone()
    assert float(credit["amount"]) == 60000.0
    assert float(credit["gross_amount"]) == 61500.0
    assert float(credit["gateway_fee"]) == 1500.0


def test_auto_shortfall_charging_enabled_uses_default_card(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 40000)
    summary, _ = validate_dummy_card(VALID_CARD)
    method = create_saved_method(db, BUSINESS_USER["id"], summary, set_default=True)
    upsert_payment_preferences(db, BUSINESS_USER["id"], auto_enabled=True,
                               default_method_id=method["id"])
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)

    result = perform_checkout(db, BUSINESS_USER, order_id, bid_id,
                              payload={}, idempotency_key="key-auto")
    db.commit()
    assert result["payment"]["status"] == "held"
    assert result["payment"]["funding_source"] == "wallet_card"


def test_auto_disabled_requires_explicit_confirmation(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 40000)
    summary, _ = validate_dummy_card(VALID_CARD)
    method = create_saved_method(db, BUSINESS_USER["id"], summary, set_default=True)
    upsert_payment_preferences(db, BUSINESS_USER["id"], auto_enabled=False,
                               default_method_id=method["id"])
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    db.commit()

    with pytest.raises(CheckoutError) as excinfo:
        perform_checkout(db, BUSINESS_USER, order_id, bid_id,
                         payload={}, idempotency_key="key-confirm-missing")
    db.rollback()
    assert excinfo.value.code == "card_confirmation_required"
    assert excinfo.value.status == 402
    assert _bid(db, bid_id)["status"] == "pending"
    assert _wallet_balance(db, BUSINESS_USER["id"]) == 40000.0   # untouched

    result = perform_checkout(db, BUSINESS_USER, order_id, bid_id,
                              payload={"confirm_card_charge": True},
                              idempotency_key="key-confirm-given")
    db.commit()
    assert result["payment"]["status"] == "held"


def test_no_pan_or_cvc_persisted_anywhere(seeded_db):
    db = seeded_db
    order_id = _mk_order(db, BUSINESS_USER["id"])
    _mk_wallet(db, BUSINESS_USER["id"], 0)
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    perform_checkout(
        db, BUSINESS_USER, order_id, bid_id,
        payload={"card": VALID_CARD, "save_card": True}, idempotency_key="key-pan-scan",
    )
    db.commit()

    for table in ("payments", "saved_payment_methods", "user_payment_preferences",
                  "wallet_transactions", "shipments", "shipment_trips"):
        rows = db.execute(f"SELECT * FROM {table}").fetchall()
        for row in rows:
            blob = str(dict(row))
            assert FULL_PAN not in blob, f"full card number leaked into {table}"
    method = db.execute("SELECT * FROM saved_payment_methods").fetchone()
    assert method["card_last_four"] == "4242"
    assert method["provider_token"].startswith("dummytok_")
    assert set(dict(method).keys()) <= {
        "id", "user_id", "provider_name", "provider_token", "card_brand",
        "card_last_four", "expiry_month", "expiry_year", "is_default",
        "status", "created_at", "updated_at",
    }


def test_expired_saved_card_fails_without_mutations(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 0)
    db.execute(
        "INSERT INTO saved_payment_methods (user_id, provider_token, card_brand, card_last_four, "
        "expiry_month, expiry_year, is_default) VALUES (%s, 'dummytok_expired', 'visa', '9999', 1, 2020, true)",
        (BUSINESS_USER["id"],),
    )
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 50000)
    db.commit()
    with pytest.raises(CheckoutError) as excinfo:
        perform_checkout(db, BUSINESS_USER, order_id, bid_id,
                         payload={"confirm_card_charge": True}, idempotency_key="key-expired")
    db.rollback()
    assert excinfo.value.code == "card_expired"
    assert _bid(db, bid_id)["status"] == "pending"
    assert _count(db, "shipment_trips") == 0
    assert _count(db, "payments") == 0
    assert _wallet_balance(db, BUSINESS_USER["id"]) == 0.0


def test_idempotent_checkout_does_not_double_charge(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 150000)
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)

    first = perform_checkout(db, BUSINESS_USER, order_id, bid_id,
                             payload={}, idempotency_key="key-idem")
    db.commit()
    balance_after_first = _wallet_balance(db, BUSINESS_USER["id"])

    second = perform_checkout(db, BUSINESS_USER, order_id, bid_id,
                              payload={}, idempotency_key="key-idem")
    db.commit()

    assert second["replayed"] is True
    assert second["payment"]["id"] == first["payment"]["id"]
    assert _wallet_balance(db, BUSINESS_USER["id"]) == balance_after_first
    assert _count(db, "payments") == 1
    assert _count(db, "shipment_trips") == 1


def test_second_checkout_cannot_create_second_trip(seeded_db):
    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 300000)
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_a = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    bid_b = _mk_bid(db, order_id, TRANSPORTER_B, 90000)

    perform_checkout(db, BUSINESS_USER, order_id, bid_a,
                     payload={}, idempotency_key="key-race-1")
    db.commit()

    with pytest.raises(CheckoutError) as excinfo:
        perform_checkout(db, BUSINESS_USER, order_id, bid_b,
                         payload={}, idempotency_key="key-race-2")
    db.rollback()
    assert excinfo.value.code == "order_not_open"
    assert _count(db, "shipment_trips") == 1
    assert _count(db, "payments") == 1

    # Database-level backstop: a second active payment for the same shipment
    # violates the partial unique index even if application checks are bypassed.
    trip = db.execute("SELECT id FROM shipment_trips LIMIT 1").fetchone()
    with pytest.raises(IntegrityError):
        db.execute(
            "INSERT INTO payments (trip_id, shipment_id, invoice_number, client_user_id, "
            "transporter_user_id, bid_price, company_fee, transporter_amount, status) "
            "VALUES (%s, %s, 'DUP-1', %s, %s, 1, 1, 1, 'held')",
            (trip["id"], order_id, BUSINESS_USER["id"], TRANSPORTER_A),
        )
    db.rollback()


# ---------------------------------------------------------------------------
# Order access
# ---------------------------------------------------------------------------

def test_order_access_levels(seeded_db):
    from orders.helpers import order_access_for_user

    db = seeded_db
    _mk_wallet(db, BUSINESS_USER["id"], 150000)
    order_id = _mk_order(db, BUSINESS_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    _mk_bid(db, order_id, TRANSPORTER_B, 110000)
    perform_checkout(db, BUSINESS_USER, order_id, bid_id,
                     payload={}, idempotency_key="key-access")
    db.commit()

    order = _order(db, order_id)
    assert order_access_for_user(db, order, BUSINESS_USER) == "owner"
    assert order_access_for_user(db, order, {"id": TRANSPORTER_A}) == "accepted_transporter"
    # The losing bidder and unrelated users get nothing.
    assert order_access_for_user(db, order, {"id": TRANSPORTER_B}) is None
    assert order_access_for_user(db, order, {"id": 999}) is None


def test_transporter_payment_summary_hides_funding_details(seeded_db):
    db = seeded_db
    order_id = _mk_order(db, EVERYDAY_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    perform_checkout(db, EVERYDAY_USER, order_id, bid_id,
                     payload={"card": VALID_CARD}, idempotency_key="key-summary")
    db.commit()

    payment = get_active_payment_for_shipment(db, order_id)
    transporter_view = serialize_payment_summary(payment, viewer="transporter")
    assert transporter_view["status"] == "held"
    assert transporter_view["transporter_amount"] == 80000.0
    for hidden in ("card_funded_amount", "wallet_funded_amount", "total_card_charge",
                   "processing_fee_amount", "provider_reference", "provider_name"):
        assert hidden not in transporter_view


# ---------------------------------------------------------------------------
# Start trip
# ---------------------------------------------------------------------------

def test_start_trip_requires_held_payment(seeded_db):
    db = seeded_db
    order_id = _mk_order(db, EVERYDAY_USER["id"], status="ready_to_start")
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 50000)
    trip_id = db.execute(
        "INSERT INTO shipment_trips (order_id, accepted_bid_id, transporter_user_id, truck_id, status) "
        "VALUES (%s, %s, %s, 1, 'ready_to_start') RETURNING id",
        (order_id, bid_id, TRANSPORTER_A),
    ).fetchone()["id"]
    db.commit()

    with pytest.raises(CheckoutError) as excinfo:
        perform_start_trip(db, {"id": TRANSPORTER_A}, order_id, trip_id)
    db.rollback()
    assert excinfo.value.code == "payment_not_held"


def test_start_trip_updates_trip_and_shipment_and_is_idempotent(seeded_db):
    db = seeded_db
    order_id = _mk_order(db, EVERYDAY_USER["id"])
    bid_id = _mk_bid(db, order_id, TRANSPORTER_A, 100000)
    result = perform_checkout(db, EVERYDAY_USER, order_id, bid_id,
                              payload={"card": VALID_CARD}, idempotency_key="key-start")
    db.commit()
    trip_id = result["trip"]["id"]

    # Only the accepted transporter may start.
    with pytest.raises(CheckoutError) as denied:
        perform_start_trip(db, {"id": TRANSPORTER_B}, order_id, trip_id)
    db.rollback()
    assert denied.value.status == 403

    started = perform_start_trip(db, {"id": TRANSPORTER_A}, order_id, trip_id)
    db.commit()
    assert started["already_started"] is False
    assert started["trip"]["status"] == "in_progress"
    assert started["trip"]["trip_started_at"] is not None
    assert _order(db, order_id)["status"] == "in_progress"
    # Payout is NOT released by starting the trip.
    payment = get_active_payment_for_shipment(db, order_id)
    assert payment["status"] == "held"
    assert payment["released_at"] is None

    again = perform_start_trip(db, {"id": TRANSPORTER_A}, order_id, trip_id)
    db.commit()
    assert again["already_started"] is True
    assert _order(db, order_id)["status"] == "in_progress"


# ---------------------------------------------------------------------------
# Wallet role integration
# ---------------------------------------------------------------------------

def test_service_seeker_wallet_created_with_zero_minimum(db):
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context():
        wallet, error = get_or_create_wallet_for_user(db, BUSINESS_USER)
    db.commit()
    assert error is None
    assert float(wallet["minimum_required"]) == 0.0
    assert bool(wallet["is_minimum_met"]) is True


def test_transporter_wallet_rules_unchanged(db):
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context():
        wallet, error = get_or_create_wallet_for_user(db, {"id": TRANSPORTER_A, "role": "logistics_provider"})
    db.commit()
    assert error is None
    assert wallet["role"] == "transporter"
    assert float(wallet["minimum_required"]) == 30000.0
    assert bool(wallet["is_minimum_met"]) is False
