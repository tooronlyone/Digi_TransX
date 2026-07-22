"""One-time trip-completion lifecycle tests (Phase M).

Builds a disposable database from supabase/schema.sql (with minimal Supabase
stubs), seeds a post-checkout state (accepted bid + ready_to_start trip + held
payment with commission snapshots) and drives the REAL services:

    perform_start_trip -> perform_complete_delivery
        -> perform_client_confirm(yes|no) | process_overdue_delivery_confirmations
        -> resolve_dispute_transporter_win | resolve_dispute_client_win

`now` is always injected — no test waits six hours. Concurrency tests use two
independent connections into the same schema. Skipped (never failed) when the
test user cannot CREATE DATABASE or TEST_SUPABASE_DB_URL is unset.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_ROOT / "supabase" / "schema.sql"

STUBS = """
create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;
do $r$ begin
  if not exists (select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role nologin; end if;
end $r$;
create schema if not exists auth;
create table if not exists auth.users (
    id uuid primary key default gen_random_uuid(), email text,
    raw_user_meta_data jsonb not null default '{}'::jsonb);
create or replace function auth.uid() returns uuid language sql stable as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
create schema if not exists storage;
create table if not exists storage.buckets (id text primary key, name text, public boolean default false);
create table if not exists storage.objects (
    id uuid primary key default gen_random_uuid(), bucket_id text, name text);
"""

RESET_TABLES = (
    "shipment_disputes", "shipment_notifications", "chat_messages", "chat_threads",
    "shipment_status_history", "payments", "wallet_transactions", "wallets",
    "shipment_no_show_tracking", "shipment_trips", "shipment_bids", "shipments",
    "vehicles", "users",
)


# ---------------------------------------------------------------------------
# Disposable database (built once), reset between tests.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _life_db():
    psycopg2 = pytest.importorskip("psycopg2")
    url = os.environ.get("TEST_SUPABASE_DB_URL", "").strip()
    if not url:
        pytest.skip("TEST_SUPABASE_DB_URL not set")
    parts = urlsplit(url)
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    dbname = f"dtx_life_{uuid.uuid4().hex[:10]}"
    try:
        admin = psycopg2.connect(admin_url)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"cannot reach admin database: {exc}")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE {dbname}")
    except Exception as exc:
        admin.close()
        pytest.skip(f"CREATE DATABASE not permitted: {exc}")
    child_url = urlunsplit((parts.scheme, parts.netloc, "/" + dbname, "", ""))
    conn = psycopg2.connect(child_url)
    with conn.cursor() as cur:
        cur.execute(STUBS)
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()
    try:
        yield child_url
    finally:
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
        admin.close()


@pytest.fixture
def env(_life_db):
    """Fresh state per test. Yields a helper exposing a primary Db and a factory
    for extra independent connections (concurrency)."""
    import psycopg2
    from shared.db import Db

    conns = []

    def connect(lock_timeout_ms=None):
        c = psycopg2.connect(_life_db)
        conns.append(c)
        if lock_timeout_ms is not None:
            with c.cursor() as cur:
                cur.execute("SET lock_timeout = %s", (f"{lock_timeout_ms}ms",))
            c.commit()
        return Db(c)

    primary = connect()
    with primary._conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(RESET_TABLES) + " RESTART IDENTITY CASCADE")
    primary._conn.commit()

    class _Env:
        db = primary
        new_db = staticmethod(connect)

    yield _Env()
    for c in conns:
        try:
            c.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Seed a post-checkout "ready_to_start" order.
# ---------------------------------------------------------------------------

def _insert_user(db, role_legacy, app_role, email):
    row = db.execute(
        "INSERT INTO users (email, cnic, role, legacy_role) VALUES (%s, %s, %s, %s) RETURNING id",
        (email, email.replace("@", "")[:13].ljust(13, "0"), app_role, role_legacy),
    ).fetchone()
    return row["id"]


def seed_ready_order(db, *, client_kind="business", bid=Decimal("10000"),
                     wallet_funded=Decimal("0"), card_funded=None, fee=Decimal("0"),
                     company_fee=Decimal("2000"), client_wallet_balance=Decimal("0")):
    """Create client/transporter/admin, a vehicle, an accepted bid, a
    ready_to_start trip and a HELD payment carrying commission snapshots.
    Returns a dict of ids + the user dicts the services expect."""
    suffix = uuid.uuid4().hex[:8]
    if client_kind == "business":
        client_legacy, client_app = "service_seeker", "customer"
    else:
        client_legacy, client_app = "everyday_user", "customer"
    client_id = _insert_user(db, client_legacy, client_app, f"client_{suffix}@t")
    transporter_id = _insert_user(db, "transporter", "transporter", f"carrier_{suffix}@t")
    admin_id = _insert_user(db, "platform_admin", "admin", f"admin_{suffix}@t")

    if card_funded is None:
        card_funded = bid - wallet_funded
    transporter_amount = bid - company_fee
    total_card = (card_funded + fee) if card_funded > 0 else None
    funding = "wallet" if card_funded <= 0 else ("card" if wallet_funded <= 0 else "wallet_card")

    if client_kind == "business":
        db.execute(
            "INSERT INTO wallets (user_id, role, balance, locked_balance, minimum_required, is_minimum_met) "
            "VALUES (%s, 'client', %s, 0, 0, true)",
            (client_id, client_wallet_balance),
        )

    order_id = db.execute(
        """
        INSERT INTO shipments (client_user_id, pickup_city, dropoff_city, pickup_date, pickup_time,
            goods_type, goods_weight_tons, seeker_kind_snapshot, status, payment_amount, payment_status,
            company_share_percent_snapshot, transporter_share_percent_snapshot)
        VALUES (%s, 'Lahore', 'Karachi', '2026-08-01', '09:00', 'Steel', 5, %s,
                'ready_to_start', %s, 'held', 20, 80)
        RETURNING id
        """,
        (client_id, "everyday" if client_kind == "everyday" else "business", bid),
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

    payment_id = db.execute(
        """
        INSERT INTO payments (trip_id, shipment_id, invoice_number, client_user_id, transporter_user_id,
            bid_price, company_fee, transporter_amount, company_share_percent, transporter_share_percent,
            wallet_funded_amount, card_funded_amount, processing_fee_percent, processing_fee_amount,
            total_card_charge, funding_source, payment_method, status, held_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 20, 80, %s, %s, 2.5, %s, %s, %s, %s, 'held', now())
        RETURNING id
        """,
        (trip_id, order_id, f"ORD-{order_id}-{trip_id}-{suffix}", client_id, transporter_id,
         bid, company_fee, transporter_amount, wallet_funded, card_funded, fee, total_card,
         funding, funding),
    ).fetchone()["id"]

    db.commit()
    return {
        "order_id": order_id, "trip_id": trip_id, "bid_id": bid_id, "payment_id": payment_id,
        "truck_id": truck_id,
        "client": {"id": client_id, "role": client_legacy},
        "transporter": {"id": transporter_id, "role": "transporter"},
        "admin": {"id": admin_id, "role": "platform_admin"},
        "bid": bid, "company_fee": company_fee, "transporter_amount": transporter_amount,
        "wallet_funded": wallet_funded, "total_card": total_card, "fee": fee,
    }


def _status(db, table, _id):
    return db.execute(f"SELECT status FROM {table} WHERE id = %s", (_id,)).fetchone()["status"]


def _now():
    return datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def _wallet_balance(db, user_id):
    row = db.execute("SELECT balance FROM wallets WHERE user_id = %s", (user_id,)).fetchone()
    return Decimal(str(row["balance"])) if row else None


def _started(db, s):
    from shared.payments import perform_start_trip
    perform_start_trip(db, s["transporter"], s["order_id"], s["trip_id"])
    db.commit()


def _completed(db, s, now=None):
    from orders.lifecycle import perform_complete_delivery
    _started(db, s)
    res = perform_complete_delivery(db, s["transporter"], s["order_id"], s["trip_id"], now=now or _now())
    db.commit()
    return res


# ---------------------------------------------------------------------------
# Start trip (Phase D)
# ---------------------------------------------------------------------------

def test_cannot_start_without_held_payment(env):
    from shared.payments import perform_start_trip, CheckoutError
    s = seed_ready_order(env.db)
    env.db.execute("UPDATE payments SET status = 'refunded' WHERE id = %s", (s["payment_id"],))
    env.db.commit()
    with pytest.raises(CheckoutError) as exc:
        perform_start_trip(env.db, s["transporter"], s["order_id"], s["trip_id"])
    assert exc.value.code == "payment_not_held"


def test_wrong_transporter_cannot_start(env):
    from shared.payments import perform_start_trip, CheckoutError
    s = seed_ready_order(env.db)
    intruder = {"id": s["admin"]["id"], "role": "transporter"}
    with pytest.raises(CheckoutError) as exc:
        perform_start_trip(env.db, intruder, s["order_id"], s["trip_id"])
    assert exc.value.status == 403


def test_valid_start_transitions(env):
    from shared.payments import perform_start_trip
    s = seed_ready_order(env.db)
    perform_start_trip(env.db, s["transporter"], s["order_id"], s["trip_id"])
    env.db.commit()
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "in_progress"
    assert _status(env.db, "shipments", s["order_id"]) == "in_progress"


def test_start_replay_idempotent(env):
    from shared.payments import perform_start_trip
    s = seed_ready_order(env.db)
    perform_start_trip(env.db, s["transporter"], s["order_id"], s["trip_id"])
    env.db.commit()
    r2 = perform_start_trip(env.db, s["transporter"], s["order_id"], s["trip_id"])
    env.db.commit()
    assert r2["already_started"] is True


def test_concurrent_start_one_transition(env):
    import psycopg2
    from shared.payments import perform_start_trip
    s = seed_ready_order(env.db)
    a = env.new_db()
    b = env.new_db(lock_timeout_ms=600)
    # a acquires the shipment row lock and holds it (uncommitted).
    perform_start_trip(a, s["transporter"], s["order_id"], s["trip_id"])
    # b cannot proceed while a holds the lock -> it times out (serialized).
    with pytest.raises(psycopg2.errors.LockNotAvailable):
        perform_start_trip(b, s["transporter"], s["order_id"], s["trip_id"])
    b.rollback()
    a.commit()
    # Exactly one in_progress trip and exactly one history row.
    hist = env.db.execute(
        "SELECT count(*) AS c FROM shipment_status_history WHERE shipment_id = %s AND new_status = 'in_progress'",
        (s["order_id"],),
    ).fetchone()["c"]
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "in_progress"
    assert hist == 1
    # A later start replays idempotently (no second transition).
    r = perform_start_trip(b, s["transporter"], s["order_id"], s["trip_id"])
    b.commit()
    assert r["already_started"] is True


# ---------------------------------------------------------------------------
# Complete delivery (Phase E)
# ---------------------------------------------------------------------------

def test_cannot_complete_before_start(env):
    from orders.lifecycle import perform_complete_delivery
    from shared.payments import CheckoutError
    s = seed_ready_order(env.db)
    with pytest.raises(CheckoutError) as exc:
        perform_complete_delivery(env.db, s["transporter"], s["order_id"], s["trip_id"], now=_now())
    assert exc.value.code == "trip_not_in_progress"


def test_wrong_transporter_cannot_complete(env):
    from orders.lifecycle import perform_complete_delivery
    from shared.payments import CheckoutError
    s = seed_ready_order(env.db)
    _started(env.db, s)
    with pytest.raises(CheckoutError) as exc:
        perform_complete_delivery(env.db, {"id": s["admin"]["id"], "role": "transporter"},
                                  s["order_id"], s["trip_id"], now=_now())
    assert exc.value.status == 403


def _deadline_gap(db, trip_id):
    """The stored window as a timedelta (deadline - completion request), tz-safe."""
    return db.execute(
        "SELECT confirmation_deadline_at - delivery_completion_requested_at AS g "
        "FROM shipment_trips WHERE id = %s", (trip_id,),
    ).fetchone()["g"]


def test_completion_sets_six_hour_deadline(env):
    s = seed_ready_order(env.db)
    _completed(env.db, s, now=_now())
    assert _deadline_gap(env.db, s["trip_id"]) == timedelta(hours=6)
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "awaiting_client_confirmation"
    assert _status(env.db, "shipments", s["order_id"]) == "awaiting_client_confirmation"


def test_completion_replay_preserves_deadline(env):
    from orders.lifecycle import perform_complete_delivery
    s = seed_ready_order(env.db)
    now = _now()
    _completed(env.db, s, now=now)
    stored_before = env.db.execute(
        "SELECT confirmation_deadline_at AS d FROM shipment_trips WHERE id = %s", (s["trip_id"],)
    ).fetchone()["d"]
    later = perform_complete_delivery(env.db, s["transporter"], s["order_id"], s["trip_id"],
                                      now=now + timedelta(hours=2))
    env.db.commit()
    stored_after = env.db.execute(
        "SELECT confirmation_deadline_at AS d FROM shipment_trips WHERE id = %s", (s["trip_id"],)
    ).fetchone()["d"]
    assert later["already"] is True
    assert stored_before == stored_after  # replay did not move the deadline


def test_payment_held_after_completion(env):
    s = seed_ready_order(env.db)
    _completed(env.db, s)
    assert _status(env.db, "payments", s["payment_id"]) == "held"


# ---------------------------------------------------------------------------
# Client Yes / No (Phase F) + release (Phase G)
# ---------------------------------------------------------------------------

def test_client_yes_releases_payout_once(env):
    from orders.lifecycle import perform_client_confirm
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "yes")
    env.db.commit()
    # Replay is a no-op.
    r2 = perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "yes")
    env.db.commit()
    assert r2["already"] is True
    assert _status(env.db, "payments", s["payment_id"]) == "released"
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "completed"
    assert _status(env.db, "shipments", s["order_id"]) == "completed"
    assert _wallet_balance(env.db, s["transporter"]["id"]) == s["transporter_amount"]
    payouts = env.db.execute(
        "SELECT count(*) AS c FROM wallet_transactions WHERE type = 'order_payout' "
        "AND reference_id = %s", (f"payout:trip:{s['trip_id']}",),
    ).fetchone()["c"]
    assert payouts == 1


def test_client_yes_uses_snapshot_and_excludes_processing_fee(env):
    from orders.lifecycle import perform_client_confirm
    # Snapshot 20% on bid 10000 => company 2000 / transporter 8000; fee 250 excluded.
    s = seed_ready_order(env.db, client_kind="everyday", bid=Decimal("10000"),
                         company_fee=Decimal("2000"), fee=Decimal("250"))
    _completed(env.db, s)
    res = perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "yes")
    env.db.commit()
    assert res["payout_amount"] == 8000.0
    assert _wallet_balance(env.db, s["transporter"]["id"]) == Decimal("8000")
    # company_fee + payout == bid (fee NOT part of it).
    p = env.db.execute("SELECT * FROM payments WHERE id = %s", (s["payment_id"],)).fetchone()
    assert Decimal(str(p["company_fee"])) + Decimal(str(p["transporter_amount"])) == s["bid"]


def test_concurrent_yes_credits_once(env):
    import psycopg2
    from orders.lifecycle import perform_client_confirm
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    a = env.new_db()
    b = env.new_db(lock_timeout_ms=600)
    perform_client_confirm(a, s["client"], s["order_id"], s["trip_id"], "yes")  # holds lock
    with pytest.raises(psycopg2.errors.LockNotAvailable):
        perform_client_confirm(b, s["client"], s["order_id"], s["trip_id"], "yes")
    b.rollback()
    a.commit()
    # b now sees 'completed' -> idempotent replay, no second credit.
    r_b = perform_client_confirm(b, s["client"], s["order_id"], s["trip_id"], "yes")
    b.commit()
    assert r_b["already"] is True
    assert _wallet_balance(env.db, s["transporter"]["id"]) == s["transporter_amount"]
    payouts = env.db.execute(
        "SELECT count(*) AS c FROM wallet_transactions WHERE reference_id = %s",
        (f"payout:trip:{s['trip_id']}",)).fetchone()["c"]
    assert payouts == 1


def test_yes_vs_no_one_winner(env):
    import psycopg2
    from orders.lifecycle import perform_client_confirm
    from shared.payments import CheckoutError
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    a = env.new_db()
    b = env.new_db(lock_timeout_ms=600)
    perform_client_confirm(a, s["client"], s["order_id"], s["trip_id"], "yes")  # holds lock
    # Concurrent No is blocked out by the row lock.
    with pytest.raises(psycopg2.errors.LockNotAvailable):
        perform_client_confirm(b, s["client"], s["order_id"], s["trip_id"], "no")
    b.rollback()
    a.commit()
    # After Yes commits, a fresh No sees 'completed' -> rejected. Yes is the one winner.
    with pytest.raises(CheckoutError):
        perform_client_confirm(b, s["client"], s["order_id"], s["trip_id"], "no")
    b.rollback()
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "completed"
    assert env.db.execute("SELECT count(*) AS c FROM shipment_disputes WHERE trip_id = %s",
                          (s["trip_id"],)).fetchone()["c"] == 0


def test_yes_vs_timeout_one_winner(env):
    from orders.lifecycle import perform_client_confirm, process_overdue_delivery_confirmations
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    past = _now() + timedelta(hours=7)  # deadline already passed
    a, b = env.new_db(), env.new_db()
    # a (client Yes) locks shipment first.
    perform_client_confirm(a, s["client"], s["order_id"], s["trip_id"], "yes")
    # b (sweep) tries the same shipment with SKIP LOCKED -> skips it this round.
    swept = process_overdue_delivery_confirmations(b, now=past)
    b.commit()
    a.commit()
    assert swept["processed_count"] == 0
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "completed"
    assert _status(env.db, "payments", s["payment_id"]) == "released"


def test_client_no_creates_one_dispute_no_payout(env):
    from orders.lifecycle import perform_client_confirm
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    res = perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "no",
                                 reason="Damaged goods")
    env.db.commit()
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "delivery_disputed"
    assert _status(env.db, "payments", s["payment_id"]) == "held"  # no payout
    disputes = env.db.execute(
        "SELECT count(*) AS c FROM shipment_disputes WHERE trip_id = %s AND status = 'open'",
        (s["trip_id"],),
    ).fetchone()["c"]
    assert disputes == 1
    assert res["dispute"]["trigger"] == "client_no"
    assert _wallet_balance(env.db, s["transporter"]["id"]) in (None, Decimal("0"))


def test_no_replay_no_duplicate(env):
    from orders.lifecycle import perform_client_confirm
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "no")
    env.db.commit()
    r2 = perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "no")
    env.db.commit()
    assert r2["already"] is True
    n = env.db.execute("SELECT count(*) AS c FROM shipment_disputes WHERE trip_id = %s",
                       (s["trip_id"],)).fetchone()["c"]
    assert n == 1


# ---------------------------------------------------------------------------
# 6-hour timeout (Phase I)
# ---------------------------------------------------------------------------

def test_timeout_keeps_payment_held_and_one_case(env):
    from orders.lifecycle import process_overdue_delivery_confirmations
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s, now=_now())
    res = process_overdue_delivery_confirmations(env.db, now=_now() + timedelta(hours=7))
    env.db.commit()
    assert res["processed_count"] == 1
    assert s["trip_id"] in res["processed_trip_ids"]
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "admin_review"
    assert _status(env.db, "payments", s["payment_id"]) == "held"
    n = env.db.execute("SELECT count(*) AS c, min(trigger) AS trg FROM shipment_disputes WHERE trip_id = %s",
                       (s["trip_id"],)).fetchone()
    assert n["c"] == 1 and n["trg"] == "confirmation_timeout"


def test_timeout_not_before_deadline(env):
    from orders.lifecycle import process_overdue_delivery_confirmations
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s, now=_now())
    res = process_overdue_delivery_confirmations(env.db, now=_now() + timedelta(hours=3))
    env.db.commit()
    assert res["processed_count"] == 0
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "awaiting_client_confirmation"


def test_repeated_sweeps_idempotent(env):
    from orders.lifecycle import process_overdue_delivery_confirmations
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s, now=_now())
    late = _now() + timedelta(hours=7)
    process_overdue_delivery_confirmations(env.db, now=late)
    env.db.commit()
    res2 = process_overdue_delivery_confirmations(env.db, now=late)
    env.db.commit()
    assert res2["processed_count"] == 0
    n = env.db.execute("SELECT count(*) AS c FROM shipment_disputes WHERE trip_id = %s",
                       (s["trip_id"],)).fetchone()["c"]
    assert n == 1


def test_client_cannot_confirm_after_escalation(env):
    from orders.lifecycle import perform_client_confirm, process_overdue_delivery_confirmations
    from shared.payments import CheckoutError
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s, now=_now())
    process_overdue_delivery_confirmations(env.db, now=_now() + timedelta(hours=7))
    env.db.commit()
    with pytest.raises(CheckoutError) as exc:
        perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "yes")
    assert exc.value.code == "not_awaiting_confirmation"


# ---------------------------------------------------------------------------
# Admin resolution (Phase H)
# ---------------------------------------------------------------------------

def _open_dispute(db, s, kind="no"):
    from orders.lifecycle import perform_client_confirm, process_overdue_delivery_confirmations
    _completed(db, s, now=_now())
    if kind == "no":
        perform_client_confirm(db, s["client"], s["order_id"], s["trip_id"], "no")
    else:
        process_overdue_delivery_confirmations(db, now=_now() + timedelta(hours=7))
    db.commit()
    return db.execute("SELECT id FROM shipment_disputes WHERE trip_id = %s", (s["trip_id"],)).fetchone()["id"]


def test_admin_transporter_win_uses_release_service(env):
    from orders.lifecycle import resolve_dispute_transporter_win
    s = seed_ready_order(env.db, client_kind="everyday")
    dispute_id = _open_dispute(env.db, s, "no")
    resolve_dispute_transporter_win(env.db, s["admin"], dispute_id, "Proof of delivery verified.")
    env.db.commit()
    assert _status(env.db, "payments", s["payment_id"]) == "released"
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "completed"
    assert _wallet_balance(env.db, s["transporter"]["id"]) == s["transporter_amount"]
    payouts = env.db.execute(
        "SELECT count(*) AS c FROM wallet_transactions WHERE reference_id = %s AND type='order_payout'",
        (f"payout:trip:{s['trip_id']}",)).fetchone()["c"]
    assert payouts == 1


def test_admin_client_win_restores_wallet_once(env):
    from orders.lifecycle import resolve_dispute_client_win
    # Business, wallet-only funding: wallet_funded=10000.
    s = seed_ready_order(env.db, client_kind="business", bid=Decimal("10000"),
                         wallet_funded=Decimal("10000"), card_funded=Decimal("0"),
                         fee=Decimal("0"), client_wallet_balance=Decimal("500"))
    dispute_id = _open_dispute(env.db, s, "timeout")
    resolve_dispute_client_win(env.db, s["admin"], dispute_id, "Client uploaded evidence.")
    env.db.commit()
    assert _status(env.db, "payments", s["payment_id"]) == "refunded"
    assert _status(env.db, "shipment_trips", s["trip_id"]) == "resolved_client"
    # 500 starting + 10000 restored.
    assert _wallet_balance(env.db, s["client"]["id"]) == Decimal("10500")
    refunds = env.db.execute(
        "SELECT count(*) AS c FROM wallet_transactions WHERE reference_id = %s AND type='order_refund'",
        (f"refund:trip:{s['trip_id']}",)).fetchone()["c"]
    assert refunds == 1


def test_dummy_card_refund_once(env):
    from orders.lifecycle import resolve_dispute_client_win
    s = seed_ready_order(env.db, client_kind="everyday", bid=Decimal("10000"),
                         wallet_funded=Decimal("0"), card_funded=Decimal("10000"), fee=Decimal("250"))
    dispute_id = _open_dispute(env.db, s, "no")
    res = resolve_dispute_client_win(env.db, s["admin"], dispute_id, "Refund approved.")
    env.db.commit()
    p = env.db.execute("SELECT * FROM payments WHERE id = %s", (s["payment_id"],)).fetchone()
    assert p["status"] == "refunded"
    assert p["refund_provider_reference"] is not None
    # Everyday: no wallet restore, full card charge refunded (incl. dummy fee).
    assert res["refund"]["wallet_refund_amount"] == 0.0
    assert res["refund"]["card_refund_amount"] == 10250.0
    ref1 = p["refund_provider_reference"]
    # Idempotent replay keeps the same reference and does not double-refund.
    r2 = resolve_dispute_client_win(env.db, s["admin"], dispute_id, "Refund approved.")
    env.db.commit()
    assert r2["already"] is True
    p2 = env.db.execute("SELECT refund_provider_reference FROM payments WHERE id = %s",
                        (s["payment_id"],)).fetchone()
    assert p2["refund_provider_reference"] == ref1


def test_mixed_wallet_card_refund_totals(env):
    from orders.lifecycle import resolve_dispute_client_win
    # Business mixed funding: wallet 4000 + card 6000 (+150 fee).
    s = seed_ready_order(env.db, client_kind="business", bid=Decimal("10000"),
                         wallet_funded=Decimal("4000"), card_funded=Decimal("6000"),
                         fee=Decimal("150"), client_wallet_balance=Decimal("0"))
    dispute_id = _open_dispute(env.db, s, "no")
    res = resolve_dispute_client_win(env.db, s["admin"], dispute_id, "Approved.")
    env.db.commit()
    assert res["refund"]["wallet_refund_amount"] == 4000.0
    assert res["refund"]["card_refund_amount"] == 6150.0
    assert _wallet_balance(env.db, s["client"]["id"]) == Decimal("4000")


def test_resolution_requires_notes(env):
    from orders.lifecycle import resolve_dispute_transporter_win
    from shared.payments import CheckoutError
    s = seed_ready_order(env.db, client_kind="everyday")
    dispute_id = _open_dispute(env.db, s, "no")
    with pytest.raises(CheckoutError) as exc:
        resolve_dispute_transporter_win(env.db, s["admin"], dispute_id, "   ")
    assert exc.value.code == "notes_required"


def test_resolution_idempotent(env):
    from orders.lifecycle import resolve_dispute_transporter_win
    s = seed_ready_order(env.db, client_kind="everyday")
    dispute_id = _open_dispute(env.db, s, "no")
    resolve_dispute_transporter_win(env.db, s["admin"], dispute_id, "ok")
    env.db.commit()
    r2 = resolve_dispute_transporter_win(env.db, s["admin"], dispute_id, "ok")
    env.db.commit()
    assert r2["already"] is True
    payouts = env.db.execute(
        "SELECT count(*) AS c FROM wallet_transactions WHERE reference_id = %s",
        (f"payout:trip:{s['trip_id']}",)).fetchone()["c"]
    assert payouts == 1


def test_transporter_statement(env):
    from orders.lifecycle import add_transporter_statement
    from shared.payments import CheckoutError
    s = seed_ready_order(env.db, client_kind="everyday")
    dispute_id = _open_dispute(env.db, s, "no")
    add_transporter_statement(env.db, s["transporter"], dispute_id, "I delivered on time.")
    env.db.commit()
    row = env.db.execute("SELECT transporter_statement FROM shipment_disputes WHERE id = %s",
                        (dispute_id,)).fetchone()
    assert row["transporter_statement"] == "I delivered on time."
    # A different transporter cannot write to the case.
    with pytest.raises(CheckoutError):
        add_transporter_statement(env.db, {"id": s["admin"]["id"], "role": "transporter"},
                                  dispute_id, "hi")
    env.db.rollback()


# ---------------------------------------------------------------------------
# Chat / notifications / history (Phases J, K, C)
# ---------------------------------------------------------------------------

def test_one_chat_thread_per_accepted_trip(env):
    from chat.helpers import ensure_one_time_thread
    s = seed_ready_order(env.db)
    t1 = ensure_one_time_thread(env.db, s["order_id"], s["trip_id"], s["client"]["id"], s["transporter"]["id"])
    t2 = ensure_one_time_thread(env.db, s["order_id"], s["trip_id"], s["client"]["id"], s["transporter"]["id"])
    env.db.commit()
    assert t1 == t2
    n = env.db.execute("SELECT count(*) AS c FROM chat_threads WHERE shipment_id = %s",
                       (s["order_id"],)).fetchone()["c"]
    assert n == 1


def test_completion_opens_chat_and_notifies_client(env):
    from shared import notifications as notif
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    thread = env.db.execute("SELECT id FROM chat_threads WHERE shipment_id = %s", (s["order_id"],)).fetchone()
    assert thread is not None
    note = env.db.execute(
        "SELECT count(*) AS c FROM shipment_notifications WHERE trip_id = %s AND user_id = %s AND notification_type = %s",
        (s["trip_id"], s["client"]["id"], notif.DELIVERY_CONFIRMATION_REQUESTED),
    ).fetchone()["c"]
    assert note == 1


def test_notifications_created_once_per_event(env):
    from orders.lifecycle import perform_complete_delivery
    from shared import notifications as notif
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    # Replay completion should not create a second notification.
    perform_complete_delivery(env.db, s["transporter"], s["order_id"], s["trip_id"], now=_now())
    env.db.commit()
    note = env.db.execute(
        "SELECT count(*) AS c FROM shipment_notifications WHERE trip_id = %s AND notification_type = %s",
        (s["trip_id"], notif.DELIVERY_CONFIRMATION_REQUESTED),
    ).fetchone()["c"]
    assert note == 1


def test_status_history_contains_every_transition(env):
    from orders.lifecycle import perform_client_confirm
    s = seed_ready_order(env.db, client_kind="everyday")
    _completed(env.db, s)
    perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "yes")
    env.db.commit()
    hist = [r["new_status"] for r in env.db.execute(
        "SELECT new_status FROM shipment_status_history WHERE shipment_id = %s ORDER BY id",
        (s["order_id"],)).fetchall()]
    for expected in ("in_progress", "awaiting_client_confirmation", "completed"):
        assert expected in hist


def test_no_raw_pan_or_cvc_in_db(env):
    # Full lifecycle then scan every text column for card-number/CVC patterns.
    from orders.lifecycle import perform_client_confirm
    s = seed_ready_order(env.db, client_kind="everyday", card_funded=Decimal("10000"), fee=Decimal("250"))
    _completed(env.db, s)
    perform_client_confirm(env.db, s["client"], s["order_id"], s["trip_id"], "yes")
    env.db.commit()
    hits = env.db.execute(
        """
        SELECT count(*) AS c FROM (
            SELECT unnest(array[content, media_path]) AS v FROM chat_messages
            UNION ALL SELECT message FROM shipment_notifications
            UNION ALL SELECT provider_reference FROM payments
            UNION ALL SELECT refund_provider_reference FROM payments
            UNION ALL SELECT description FROM wallet_transactions
        ) t WHERE v ~ '\\d{13,19}' OR lower(v) ~ 'cvc|cvv'
        """
    ).fetchone()["c"]
    assert hits == 0
