"""One-time lifecycle DATABASE-INTEGRITY tests (relationship + arithmetic).

These exercise the composite foreign keys and CHECK constraints added by
migration 20260723120000 / schema.sql section 4.1 against a REAL PostgreSQL
database built from the canonical supabase/schema.sql. They prove the database
is the final backstop: related one-time IDs can never point at another order's,
truck's or party's row, and the money split of a checkout row can never be
persisted inconsistently — on INSERT and on UPDATE — while the intentionally
NULLable legacy paths stay valid.

Skipped (never failed) when TEST_SUPABASE_DB_URL is unset or the role cannot
CREATE DATABASE. No SQLite / in-memory substitute: the point is the real
constraints.
"""

import uuid
from decimal import Decimal

import pytest

from tests._life_helpers import (
    require_test_db_url,
    make_disposable,
    STUBS,
    SCHEMA_SQL,
)

RESET_TABLES = (
    "shipment_disputes", "shipment_notifications", "chat_messages", "chat_threads",
    "shipment_status_history", "payments", "wallet_transactions", "wallets",
    "shipment_no_show_tracking", "shipment_trips", "shipment_bids", "shipments",
    "vehicles", "users",
)


# ---------------------------------------------------------------------------
# Disposable database built once from schema.sql; reset between tests.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _schema_db():
    url = require_test_db_url()
    child_url, cleanup = make_disposable(
        url, STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    try:
        yield child_url
    finally:
        cleanup()


@pytest.fixture
def db(_schema_db):
    import psycopg2
    from shared.db import Db

    conn = psycopg2.connect(_schema_db)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(RESET_TABLES) + " RESTART IDENTITY CASCADE")
    conn.commit()
    wrapper = Db(conn)
    try:
        yield wrapper
    finally:
        conn.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# Seed a full, self-consistent one-time order chain (NO payment yet, so tests
# own the payment rows and never trip the active-payment uniqueness index).
# ---------------------------------------------------------------------------

def _user(db, legacy, app_role):
    token = uuid.uuid4().hex[:12]
    email = f"{legacy}_{token}@t"
    cnic = f"C{token}"  # unique per user (users.cnic is UNIQUE)
    return db.execute(
        "INSERT INTO users (email, cnic, role, legacy_role) VALUES (%s, %s, %s, %s) RETURNING id",
        (email, cnic, app_role, legacy),
    ).fetchone()["id"]


def seed_order(db, *, bid=Decimal("10000")):
    """A consistent client/transporter/admin + shipment + truck + accepted bid +
    ready_to_start trip. Commits. Returns the ids and the bid amount."""
    suffix = uuid.uuid4().hex[:8]
    client_id = _user(db, "service_seeker", "customer")
    transporter_id = _user(db, "transporter", "transporter")

    order_id = db.execute(
        """
        INSERT INTO shipments (client_user_id, pickup_city, dropoff_city, pickup_date,
            pickup_time, goods_type, goods_weight_tons, seeker_kind_snapshot, status,
            payment_amount, payment_status, company_share_percent_snapshot,
            transporter_share_percent_snapshot)
        VALUES (%s, 'Lahore', 'Karachi', '2026-08-01', '09:00', 'Steel', 5, 'business',
                'ready_to_start', %s, 'held', 20, 80)
        RETURNING id
        """,
        (client_id, bid),
    ).fetchone()["id"]

    truck_id = db.execute(
        "INSERT INTO vehicles (owner_user_id, truck_number, truck_type, chassis_number, "
        "capacity_tons, main_use, status) "
        "VALUES (%s, %s, 'flatbed', %s, 20, 'general', 'active') RETURNING id",
        (transporter_id, f"TRK-{suffix}", f"CHS-{suffix}"),
    ).fetchone()["id"]

    bid_id = db.execute(
        "INSERT INTO shipment_bids (order_id, transporter_user_id, truck_id, bid_price, status) "
        "VALUES (%s, %s, %s, %s, 'accepted') RETURNING id",
        (order_id, transporter_id, truck_id, bid),
    ).fetchone()["id"]

    db.execute("UPDATE shipments SET accepted_bid_id = %s WHERE id = %s", (bid_id, order_id))

    trip_id = db.execute(
        "INSERT INTO shipment_trips (order_id, accepted_bid_id, transporter_user_id, truck_id, status) "
        "VALUES (%s, %s, %s, %s, 'ready_to_start') RETURNING id",
        (order_id, bid_id, transporter_id, truck_id),
    ).fetchone()["id"]

    db.commit()
    return {
        "order_id": order_id, "trip_id": trip_id, "bid_id": bid_id,
        "truck_id": truck_id, "client_id": client_id, "transporter_id": transporter_id,
        "bid": bid,
    }


_PAYMENT_COLS = (
    "trip_id", "shipment_id", "invoice_number", "client_user_id", "transporter_user_id",
    "bid_price", "company_fee", "transporter_amount", "company_share_percent",
    "transporter_share_percent", "wallet_funded_amount", "card_funded_amount",
    "processing_fee_percent", "processing_fee_amount", "total_card_charge",
    "funding_source", "payment_method", "status",
)


def _payment_values(seed, **overrides):
    """Valid wallet-funded held-payment values for ``seed``, with overrides."""
    bid = seed["bid"]
    values = {
        "trip_id": seed["trip_id"],
        "shipment_id": seed["order_id"],
        "invoice_number": f"INV-{uuid.uuid4().hex[:12]}",
        "client_user_id": seed["client_id"],
        "transporter_user_id": seed["transporter_id"],
        "bid_price": bid,
        "company_fee": Decimal("2000"),
        "transporter_amount": bid - Decimal("2000"),
        "company_share_percent": Decimal("20"),
        "transporter_share_percent": Decimal("80"),
        "wallet_funded_amount": bid,
        "card_funded_amount": Decimal("0"),
        "processing_fee_percent": Decimal("2.5"),
        "processing_fee_amount": Decimal("0"),
        "total_card_charge": None,
        "funding_source": "wallet",
        "payment_method": "wallet",
        "status": "held",
    }
    values.update(overrides)
    return values


def insert_payment(db, seed, **overrides):
    values = _payment_values(seed, **overrides)
    cols = ", ".join(_PAYMENT_COLS)
    placeholders = ", ".join("%s" for _ in _PAYMENT_COLS)
    return db.execute(
        f"INSERT INTO payments ({cols}, held_at) VALUES ({placeholders}, now()) RETURNING id",
        tuple(values[c] for c in _PAYMENT_COLS),
    ).fetchone()["id"]


def insert_thread(db, *, shipment_id, trip_id, client_id, transporter_id):
    return db.execute(
        "INSERT INTO chat_threads (client_user_id, transporter_user_id, shipment_id, "
        "one_time_trip_id, created_at) VALUES (%s, %s, %s, %s, now()) RETURNING id",
        (client_id, transporter_id, shipment_id, trip_id),
    ).fetchone()["id"]


def insert_dispute(db, *, shipment_id, trip_id, payment_id, client_id, transporter_id,
                   chat_thread_id, trigger="client_no"):
    return db.execute(
        "INSERT INTO shipment_disputes (shipment_id, trip_id, payment_id, client_user_id, "
        "transporter_user_id, chat_thread_id, trigger, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 'open') RETURNING id",
        (shipment_id, trip_id, payment_id, client_id, transporter_id, chat_thread_id, trigger),
    ).fetchone()["id"]


def expect_violation(db, constraint, fn):
    """Run ``fn`` (an INSERT/UPDATE), assert it is rejected by ``constraint``,
    then roll back so the connection stays usable."""
    import psycopg2

    try:
        fn()
    except psycopg2.Error as exc:
        db._conn.rollback()
        cname = getattr(getattr(exc, "diag", None), "constraint_name", None) or ""
        haystack = cname or str(exc)
        assert constraint in haystack, f"expected {constraint}, got: {haystack}"
        return
    db._conn.rollback()
    raise AssertionError(f"expected {constraint} violation but the statement succeeded")


# ===========================================================================
# 1. The valid checkout -> trip -> held payment -> chat -> dispute chain.
# ===========================================================================

def test_valid_chain_inserts_successfully(db):
    seed = seed_order(db)
    payment_id = insert_payment(db, seed)
    thread_id = insert_thread(
        db, shipment_id=seed["order_id"], trip_id=seed["trip_id"],
        client_id=seed["client_id"], transporter_id=seed["transporter_id"],
    )
    dispute_id = insert_dispute(
        db, shipment_id=seed["order_id"], trip_id=seed["trip_id"], payment_id=payment_id,
        client_id=seed["client_id"], transporter_id=seed["transporter_id"],
        chat_thread_id=thread_id,
    )
    db.commit()
    assert payment_id and thread_id and dispute_id
    row = db.execute("SELECT count(*) AS n FROM shipment_disputes").fetchone()
    assert row["n"] == 1


# ===========================================================================
# 2. Accepted bid from another shipment is rejected.
# ===========================================================================

def test_accepted_bid_from_other_shipment_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_shipments_accepted_bid_same_order",
        lambda: db.execute(
            "UPDATE shipments SET accepted_bid_id = %s WHERE id = %s",
            (b["bid_id"], a["order_id"]),
        ),
    )


# ===========================================================================
# 3. Trip with a mismatched bid / order / transporter / truck is rejected.
# ===========================================================================

def test_trip_with_foreign_bid_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_trips_bid_matches",
        lambda: db.execute(
            "INSERT INTO shipment_trips (order_id, accepted_bid_id, transporter_user_id, truck_id, status) "
            "VALUES (%s, %s, %s, %s, 'ready_to_start')",
            (a["order_id"], b["bid_id"], a["transporter_id"], a["truck_id"]),
        ),
    )


def test_trip_with_foreign_transporter_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_trips_bid_matches",
        lambda: db.execute(
            "INSERT INTO shipment_trips (order_id, accepted_bid_id, transporter_user_id, truck_id, status) "
            "VALUES (%s, %s, %s, %s, 'ready_to_start')",
            (a["order_id"], a["bid_id"], b["transporter_id"], a["truck_id"]),
        ),
    )


def test_trip_with_foreign_truck_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_trips_bid_matches",
        lambda: db.execute(
            "INSERT INTO shipment_trips (order_id, accepted_bid_id, transporter_user_id, truck_id, status) "
            "VALUES (%s, %s, %s, %s, 'ready_to_start')",
            (a["order_id"], a["bid_id"], a["transporter_id"], b["truck_id"]),
        ),
    )


# ===========================================================================
# 4. Payment with a mismatched shipment / trip / client / transporter.
# ===========================================================================

def test_payment_with_foreign_transporter_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_payments_trip_transporter",
        lambda: insert_payment(db, a, transporter_user_id=b["transporter_id"]),
    )


def test_payment_with_foreign_shipment_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_payments_trip_shipment",
        lambda: insert_payment(db, a, shipment_id=b["order_id"]),
    )


def test_payment_with_foreign_client_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_payments_shipment_client",
        lambda: insert_payment(db, a, client_user_id=b["client_id"]),
    )


# ===========================================================================
# 5. Dispute with a mismatched shipment / trip / payment / parties / thread.
# ===========================================================================

def test_dispute_with_foreign_shipment_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_disputes_trip_shipment",
        lambda: insert_dispute(
            db, shipment_id=b["order_id"], trip_id=a["trip_id"], payment_id=None,
            client_id=a["client_id"], transporter_id=a["transporter_id"], chat_thread_id=None,
        ),
    )


def test_dispute_with_foreign_transporter_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_disputes_trip_transporter",
        lambda: insert_dispute(
            db, shipment_id=a["order_id"], trip_id=a["trip_id"], payment_id=None,
            client_id=a["client_id"], transporter_id=b["transporter_id"], chat_thread_id=None,
        ),
    )


def test_dispute_with_foreign_client_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_disputes_shipment_client",
        lambda: insert_dispute(
            db, shipment_id=a["order_id"], trip_id=a["trip_id"], payment_id=None,
            client_id=b["client_id"], transporter_id=a["transporter_id"], chat_thread_id=None,
        ),
    )


def test_dispute_with_foreign_payment_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    b_payment = insert_payment(db, b)
    db.commit()
    expect_violation(
        db, "fk_disputes_payment_trip",
        lambda: insert_dispute(
            db, shipment_id=a["order_id"], trip_id=a["trip_id"], payment_id=b_payment,
            client_id=a["client_id"], transporter_id=a["transporter_id"], chat_thread_id=None,
        ),
    )


def test_dispute_with_foreign_thread_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    b_thread = insert_thread(
        db, shipment_id=b["order_id"], trip_id=b["trip_id"],
        client_id=b["client_id"], transporter_id=b["transporter_id"],
    )
    db.commit()
    expect_violation(
        db, "fk_disputes_chat_shipment",
        lambda: insert_dispute(
            db, shipment_id=a["order_id"], trip_id=a["trip_id"], payment_id=None,
            client_id=a["client_id"], transporter_id=a["transporter_id"], chat_thread_id=b_thread,
        ),
    )


# ===========================================================================
# 6. Chat thread with a trip from another shipment is rejected.
# ===========================================================================

def test_chat_thread_with_foreign_trip_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    # Give shipment A no thread of its own, then try to link B's trip to A.
    expect_violation(
        db, "fk_chat_trip_shipment",
        lambda: db.execute(
            "INSERT INTO chat_threads (client_user_id, transporter_user_id, shipment_id, "
            "one_time_trip_id, created_at) VALUES (%s, %s, %s, %s, now())",
            (a["client_id"], a["transporter_id"], a["order_id"], b["trip_id"]),
        ),
    )


# ===========================================================================
# 7-11. Arithmetic invariants.
# ===========================================================================

def test_valid_wallet_card_split_accepted(db):
    seed = seed_order(db)
    pid = insert_payment(
        db, seed,
        wallet_funded_amount=Decimal("4000"),
        card_funded_amount=Decimal("6000"),
        processing_fee_percent=Decimal("2.5"),
        processing_fee_amount=Decimal("150"),
        total_card_charge=Decimal("6150"),
        funding_source="wallet_card",
        payment_method="wallet_card",
    )
    db.commit()
    assert pid


def test_invalid_funding_split_rejected(db):
    seed = seed_order(db)
    expect_violation(
        db, "ck_payments_funding_split",
        lambda: insert_payment(
            db, seed,
            wallet_funded_amount=Decimal("4000"),
            card_funded_amount=Decimal("5000"),  # 9000 != 10000
            funding_source="wallet_card",
        ),
    )


def test_invalid_commission_split_rejected(db):
    seed = seed_order(db)
    expect_violation(
        db, "ck_payments_commission_split",
        lambda: insert_payment(
            db, seed,
            company_fee=Decimal("2000"),
            transporter_amount=Decimal("7000"),  # 9000 != 10000
        ),
    )


def test_invalid_total_card_charge_rejected(db):
    seed = seed_order(db)
    expect_violation(
        db, "ck_payments_total_card_charge",
        lambda: insert_payment(
            db, seed,
            wallet_funded_amount=Decimal("4000"),
            card_funded_amount=Decimal("6000"),
            processing_fee_amount=Decimal("150"),
            total_card_charge=Decimal("6000"),  # should be 6150
            funding_source="wallet_card",
        ),
    )


def test_processing_percent_out_of_range_rejected(db):
    seed = seed_order(db)
    expect_violation(
        db, "ck_payments_processing_percent_range",
        lambda: insert_payment(db, seed, processing_fee_percent=Decimal("100")),
    )


def test_invalid_payment_snapshot_sum_rejected(db):
    seed = seed_order(db)
    expect_violation(
        db, "ck_payments_snapshot_sum",
        lambda: insert_payment(
            db, seed,
            company_share_percent=Decimal("20"),
            transporter_share_percent=Decimal("70"),  # 90 != 100
        ),
    )


def test_invalid_shipment_snapshot_sum_rejected(db):
    a = seed_order(db)
    expect_violation(
        db, "ck_shipments_snapshot_sum",
        lambda: db.execute(
            "UPDATE shipments SET transporter_share_percent_snapshot = 70 WHERE id = %s",
            (a["order_id"],),
        ),
    )


def test_negative_amount_rejected(db):
    seed = seed_order(db)
    expect_violation(
        db, "ck_payments_amounts_nonneg",
        lambda: insert_payment(
            db, seed,
            company_fee=Decimal("-1"),
            transporter_amount=Decimal("10001"),
            funding_source=None,  # dodge commission-split check; test non-negativity only
        ),
    )


# ===========================================================================
# 12. NULL-compatible legacy paths stay valid.
# ===========================================================================

def test_legacy_null_funding_source_skips_equality_checks(db):
    """A legacy immediate-payout 'paid' row (funding_source NULL, snapshots NULL)
    is accepted even with a split that would fail the gated equality checks."""
    seed = seed_order(db)
    pid = insert_payment(
        db, seed,
        funding_source=None,
        company_share_percent=None,
        transporter_share_percent=None,
        company_fee=Decimal("3333"),
        transporter_amount=Decimal("1"),      # commission split gated off -> allowed
        wallet_funded_amount=Decimal("0"),
        card_funded_amount=Decimal("0"),        # funding split gated off -> allowed
        processing_fee_percent=None,
        total_card_charge=None,
        status="paid",
        payment_method="wallet",
    )
    db.commit()
    assert pid


def test_legacy_null_shipment_id_payment_accepted(db):
    """payments.shipment_id may be NULL (ON DELETE SET NULL legacy path); the
    trip/shipment and shipment/client composite FKs are then skipped."""
    seed = seed_order(db)
    pid = insert_payment(db, seed, shipment_id=None)
    db.commit()
    assert pid


def test_dispute_with_null_payment_and_thread_accepted(db):
    seed = seed_order(db)
    did = insert_dispute(
        db, shipment_id=seed["order_id"], trip_id=seed["trip_id"], payment_id=None,
        client_id=seed["client_id"], transporter_id=seed["transporter_id"], chat_thread_id=None,
    )
    db.commit()
    assert did


def test_agreement_style_thread_without_trip_accepted(db):
    """An agreement chat thread carries neither shipment_id nor one_time_trip_id;
    fk_chat_trip_shipment is skipped (both columns NULL)."""
    client_id = _user(db, "service_seeker", "customer")
    transporter_id = _user(db, "transporter", "transporter")
    tid = db.execute(
        "INSERT INTO chat_threads (client_user_id, transporter_user_id, created_at) "
        "VALUES (%s, %s, now()) RETURNING id",
        (client_id, transporter_id),
    ).fetchone()["id"]
    db.commit()
    assert tid


# ===========================================================================
# 13. Constraints also reject invalid UPDATEs (not only INSERTs).
# ===========================================================================

def test_update_breaking_commission_split_rejected(db):
    seed = seed_order(db)
    pid = insert_payment(db, seed)
    db.commit()
    expect_violation(
        db, "ck_payments_commission_split",
        lambda: db.execute(
            "UPDATE payments SET company_fee = 3000 WHERE id = %s", (pid,)
        ),
    )


def test_update_moving_trip_to_foreign_truck_rejected(db):
    a = seed_order(db)
    b = seed_order(db)
    expect_violation(
        db, "fk_trips_bid_matches",
        lambda: db.execute(
            "UPDATE shipment_trips SET truck_id = %s WHERE id = %s",
            (b["truck_id"], a["trip_id"]),
        ),
    )
