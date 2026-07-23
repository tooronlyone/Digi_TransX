"""Smoke + safety tests for the corrected one-time-lifecycle migration.

Stands up a DISPOSABLE database from the real origin/main (pre-lifecycle)
supabase/schema.sql, then runs the actual shipped migration file
supabase/migrations/20260723120000_one_time_trip_completion_lifecycle.sql and
proves:

  * it applies cleanly on the pre-lifecycle baseline and is idempotent on reapply;
  * the legacy shipment_trip_verification table is dropped when empty, but the
    migration ABORTS (no data loss) when it still holds rows;
  * the anomaly precheck aborts with a precise diagnostic when existing rows
    violate an invariant, instead of "repairing" financial history;
  * valid representative existing order/payment data survives the migration and
    the new constraints are live afterwards.

Skipped (never failed) when TEST_SUPABASE_DB_URL is unset, the role cannot
CREATE DATABASE, or origin/main is not reachable. Real PostgreSQL only.
"""

import uuid

import pytest

from tests._life_helpers import (
    require_test_db_url,
    make_disposable,
    origin_main_schema_or_skip,
    run_sql,
    STUBS,
    MIGRATION_SQL,
)


@pytest.fixture
def main_conn():
    """A fresh disposable database loaded with the origin/main pre-lifecycle
    schema. Function-scoped: the migration is one-way, so each test starts clean."""
    url = require_test_db_url()
    schema = origin_main_schema_or_skip()
    child_url, cleanup = make_disposable(url, STUBS, schema)
    import psycopg2

    conn = psycopg2.connect(child_url)
    try:
        yield conn
    finally:
        conn.close()
        cleanup()


def _run_migration(conn):
    run_sql(conn, MIGRATION_SQL.read_text(encoding="utf-8"))


def _regclass(conn, name):
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s)", (name,))
        return cur.fetchone()[0]


def _has_constraint(conn, name):
    with conn.cursor() as cur:
        cur.execute("select 1 from pg_constraint where conname = %s", (name,))
        return cur.fetchone() is not None


COMPOSITE_FKS = (
    "fk_shipments_accepted_bid_same_order", "fk_trips_bid_matches",
    "fk_payments_trip_transporter", "fk_payments_trip_shipment",
    "fk_payments_shipment_client", "fk_disputes_trip_shipment",
    "fk_disputes_trip_transporter", "fk_disputes_shipment_client",
    "fk_disputes_payment_trip", "fk_disputes_chat_shipment", "fk_chat_trip_shipment",
)
CHECK_CONSTRAINTS = (
    "ck_payments_amounts_nonneg", "ck_payments_funding_split",
    "ck_payments_commission_split", "ck_payments_total_card_charge",
    "ck_payments_processing_percent_range", "ck_payments_snapshot_sum",
    "ck_shipments_snapshot_sum",
)


# ---------------------------------------------------------------------------
# Seed helpers against the PRE-LIFECYCLE schema (no dispute table / lifecycle
# columns; shipment_trip_verification still present).
# ---------------------------------------------------------------------------

def _one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def seed_order(conn, *, funding_ok=True, commission_ok=True):
    """A consistent client/transporter + shipment + truck + accepted bid + trip +
    held payment. When funding_ok/commission_ok are False the payment's split is
    deliberately broken (only possible because the equality checks do not exist
    yet on the pre-lifecycle schema). Commits. Returns key ids."""
    cur = conn.cursor()
    tok = uuid.uuid4().hex[:12]
    client = _one(cur,
        "INSERT INTO users (email,cnic,role,legacy_role) VALUES (%s,%s,'customer','service_seeker') RETURNING id",
        (f"c{tok}@t", f"C{tok}"))
    transporter = _one(cur,
        "INSERT INTO users (email,cnic,role,legacy_role) VALUES (%s,%s,'transporter','transporter') RETURNING id",
        (f"t{tok}@t", f"T{tok}"))
    order = _one(cur,
        "INSERT INTO shipments (client_user_id, pickup_city, dropoff_city, pickup_date, pickup_time, "
        "goods_type, goods_weight_tons, seeker_kind_snapshot, status, payment_amount, payment_status, "
        "company_share_percent_snapshot, transporter_share_percent_snapshot) "
        "VALUES (%s,'Lahore','Karachi','2026-08-01','09:00','Steel',5,'business','ready_to_start',10000,'held',20,80) "
        "RETURNING id", (client,))
    truck = _one(cur,
        "INSERT INTO vehicles (owner_user_id, truck_number, truck_type, chassis_number, capacity_tons, main_use, status) "
        "VALUES (%s,%s,'flatbed',%s,20,'general','active') RETURNING id",
        (transporter, f"TRK-{tok}", f"CHS-{tok}"))
    bid = _one(cur,
        "INSERT INTO shipment_bids (order_id, transporter_user_id, truck_id, bid_price, status) "
        "VALUES (%s,%s,%s,10000,'accepted') RETURNING id", (order, transporter, truck))
    cur.execute("UPDATE shipments SET accepted_bid_id=%s WHERE id=%s", (bid, order))
    trip = _one(cur,
        "INSERT INTO shipment_trips (order_id, accepted_bid_id, transporter_user_id, truck_id, status) "
        "VALUES (%s,%s,%s,%s,'ready_to_start') RETURNING id", (order, bid, transporter, truck))
    wallet_funded = 10000 if funding_ok else 9000
    company_fee = 2000
    transporter_amount = 8000 if commission_ok else 7000
    payment = _one(cur,
        "INSERT INTO payments (trip_id, shipment_id, invoice_number, client_user_id, transporter_user_id, "
        "bid_price, company_fee, transporter_amount, company_share_percent, transporter_share_percent, "
        "wallet_funded_amount, card_funded_amount, processing_fee_percent, processing_fee_amount, "
        "total_card_charge, funding_source, payment_method, status, held_at) "
        "VALUES (%s,%s,%s,%s,%s,10000,%s,%s,20,80,%s,0,2.5,0,NULL,'wallet','wallet','held',now()) RETURNING id",
        (trip, order, f"INV-{tok}", client, transporter, company_fee, transporter_amount, wallet_funded))
    conn.commit()
    return {"order": order, "trip": trip, "bid": bid, "payment": payment,
            "client": client, "transporter": transporter, "truck": truck}


def seed_verification_row(conn, trip_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO shipment_trip_verification (trip_id, final_verification_status) "
            "VALUES (%s, 'pending') RETURNING id", (trip_id,))
        vid = cur.fetchone()[0]
    conn.commit()
    return vid


# ===========================================================================
# 16 (part) + smoke: applies cleanly on the pre-lifecycle baseline, idempotent.
# ===========================================================================

def test_migration_applies_and_is_idempotent(main_conn):
    conn = main_conn
    assert _regclass(conn, "public.shipment_trip_verification") is not None
    assert _regclass(conn, "public.shipment_disputes") is None

    _run_migration(conn)

    # legacy table gone; new dispute table + lifecycle columns present.
    assert _regclass(conn, "public.shipment_trip_verification") is None
    assert _regclass(conn, "public.shipment_disputes") is not None
    with conn.cursor() as cur:
        cur.execute(
            "select column_name from information_schema.columns "
            "where table_name='shipment_trips' and column_name in "
            "('delivery_completion_requested_at','confirmation_deadline_at')")
        assert {r[0] for r in cur.fetchall()} == {
            "delivery_completion_requested_at", "confirmation_deadline_at"}
        cur.execute(
            "select column_name from information_schema.columns "
            "where table_name='chat_threads' and column_name in ('shipment_id','one_time_trip_id')")
        assert {r[0] for r in cur.fetchall()} == {"shipment_id", "one_time_trip_id"}

    for name in COMPOSITE_FKS + CHECK_CONSTRAINTS:
        assert _has_constraint(conn, name), f"{name} missing after migration"

    # Reapply: idempotent, no duplicate constraints or errors.
    _run_migration(conn)
    for name in COMPOSITE_FKS + CHECK_CONSTRAINTS:
        assert _has_constraint(conn, name), f"{name} lost after reapply"
    with conn.cursor() as cur:
        cur.execute(
            "select conname, count(*) from pg_constraint where conname = any(%s) group by conname having count(*) > 1",
            (list(COMPOSITE_FKS + CHECK_CONSTRAINTS),))
        assert cur.fetchall() == [], "duplicate constraints after reapply"


# ===========================================================================
# 14. Legacy verification cleanup succeeds when the table is empty.
# ===========================================================================

def test_empty_verification_table_dropped(main_conn):
    conn = main_conn
    with conn.cursor() as cur:
        cur.execute("select count(*) from public.shipment_trip_verification")
        assert cur.fetchone()[0] == 0
    _run_migration(conn)
    assert _regclass(conn, "public.shipment_trip_verification") is None


# ===========================================================================
# 15. Cleanup ABORTS without data loss when the table still holds rows.
# ===========================================================================

def test_verification_with_rows_aborts_without_data_loss(main_conn):
    conn = main_conn
    seed = seed_order(conn)
    vid = seed_verification_row(conn, seed["trip"])

    import psycopg2
    with pytest.raises(psycopg2.Error) as ei:
        _run_migration(conn)
    conn.rollback()
    assert "shipment_trip_verification still has" in str(ei.value)

    # The table AND its row must still be intact; the migration made no changes.
    assert _regclass(conn, "public.shipment_trip_verification") is not None
    with conn.cursor() as cur:
        cur.execute("select count(*) from public.shipment_trip_verification where id=%s", (vid,))
        assert cur.fetchone()[0] == 1
    # And because the transaction rolled back, no new constraints were created.
    assert not _has_constraint(conn, "fk_trips_bid_matches")
    assert _regclass(conn, "public.shipment_disputes") is None


# ===========================================================================
# Anomaly precheck aborts on inconsistent existing financial rows.
# ===========================================================================

def test_precheck_aborts_on_bad_funding_split(main_conn):
    conn = main_conn
    seed_order(conn, funding_ok=False)  # wallet+card (9000) != bid (10000)

    import psycopg2
    with pytest.raises(psycopg2.Error) as ei:
        _run_migration(conn)
    conn.rollback()
    msg = str(ei.value)
    assert "Integrity precheck failed" in msg and "funding_split" in msg
    # Aborted before any constraint/table change.
    assert not _has_constraint(conn, "ck_payments_funding_split")
    assert _regclass(conn, "public.shipment_trip_verification") is not None


def test_precheck_aborts_on_bad_commission_split(main_conn):
    conn = main_conn
    seed_order(conn, commission_ok=False)  # company_fee+transporter (9000) != bid

    import psycopg2
    with pytest.raises(psycopg2.Error) as ei:
        _run_migration(conn)
    conn.rollback()
    assert "Integrity precheck failed" in str(ei.value)


# ===========================================================================
# 3. Valid representative existing data survives; constraints live afterwards.
# ===========================================================================

def test_valid_existing_data_survives_and_constraints_enforced(main_conn):
    conn = main_conn
    seed = seed_order(conn)  # fully consistent order + held payment

    _run_migration(conn)  # must not abort

    # The representative rows are untouched.
    with conn.cursor() as cur:
        cur.execute("select bid_price, company_fee, transporter_amount from payments where id=%s",
                    (seed["payment"],))
        bid_price, company_fee, transporter_amount = cur.fetchone()
    assert (float(bid_price), float(company_fee), float(transporter_amount)) == (10000.0, 2000.0, 8000.0)

    # The new constraints are now enforced: a broken UPDATE is rejected.
    import psycopg2
    with pytest.raises(psycopg2.Error) as ei:
        with conn.cursor() as cur:
            cur.execute("update payments set company_fee = 3000 where id=%s", (seed["payment"],))
    conn.rollback()
    cname = getattr(getattr(ei.value, "diag", None), "constraint_name", "") or str(ei.value)
    assert "ck_payments_commission_split" in cname
