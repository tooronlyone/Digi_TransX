"""Phase 4B-1 Least-Privilege Database Access & Residual Grant Tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg2
from psycopg2 import errors
from psycopg2.extras import Json
import pytest

from orders.business_lifecycle import (
    delivery_otp_for_client,
    issue_delivery_otp,
    release_due_settlements,
    verify_delivery_otp,
)
from orders.lifecycle import process_overdue_delivery_confirmations
import scheduler as scheduler_mod
from scripts import reconcile_business_rules
from shared.commissions import create_policy_version, create_terms_version, get_active_policy
from shared.db import (
    DB_ROLE_API,
    DB_ROLE_AUDITOR,
    DB_ROLE_SCHEDULER,
    Db,
    open_auditor_db,
    open_db,
    open_scheduler_db,
    reset_db_pools,
    resolve_database_dsn,
    resolve_migration_dsn,
)
from shared.payments import perform_checkout, perform_start_trip, refund_one_time_payment
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.test_database_authorization_hardening import DEFAULT_GRANTS
from wallet import helpers as wallet_helpers, withdrawal_limits


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"


def _local_url():
    url = require_test_db_url()
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Phase 4B-1 tests require isolated loopback PostgreSQL.")
    return url


def _dsn_for_role(base_url, username, password):
    parts = urlsplit(base_url)
    host = parts.hostname or "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{username}:{password}@{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@pytest.fixture(scope="module", params=["fresh_schema", "fresh_baseline"])
def role_env_db(request):
    if request.param == "fresh_schema":
        blocks = [STUBS, DEFAULT_GRANTS, SCHEMA_SQL.read_text(encoding="utf-8")]
    else:
        blocks = [
            STUBS,
            DEFAULT_GRANTS,
            *(p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS_DIR.glob("*.sql"))),
        ]
    url, cleanup = make_disposable(_local_url(), *blocks)
    tag = uuid4().hex[:10]
    pw = f"P4b1_{uuid4().hex}"
    login_roles = {
        "api": f"p4b1_api_{tag}",
        "scheduler": f"p4b1_sched_{tag}",
        "auditor": f"p4b1_aud_{tag}",
    }
    role_memberships = {
        "api": "dtx_api_runtime",
        "scheduler": "dtx_scheduler_worker",
        "auditor": "dtx_auditor_ro",
    }
    try:
        with psycopg2.connect(url) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                for key, login_name in login_roles.items():
                    cur.execute(
                        f"CREATE ROLE {login_name} LOGIN PASSWORD %s "
                        f"NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION "
                        f"IN ROLE {role_memberships[key]}",
                        (pw,),
                    )
        yield {
            "owner_url": url,
            "api_url": _dsn_for_role(url, login_roles["api"], pw),
            "scheduler_url": _dsn_for_role(url, login_roles["scheduler"], pw),
            "auditor_url": _dsn_for_role(url, login_roles["auditor"], pw),
            "login_roles": login_roles,
        }
    finally:
        reset_db_pools()
        cleanup()
        with psycopg2.connect(_local_url()) as admin_conn:
            admin_conn.autocommit = True
            with admin_conn.cursor() as cur:
                for login_name in login_roles.values():
                    cur.execute(f"DROP ROLE IF EXISTS {login_name}")


def _seed_user(cur, legacy_role):
    auth_id = str(uuid4())
    email = f"p4b1_{legacy_role}_{uuid4().hex[:8]}@example.test"
    cnic = f"{int(uuid4().int % 9000000000000) + 1000000000000:013d}"
    cur.execute(
        "INSERT INTO auth.users(id, email, raw_user_meta_data) VALUES(%s, %s, %s)",
        (auth_id, email, Json({"legacy_role": legacy_role, "full_name": "Phase 4B1", "cnic": cnic})),
    )
    cur.execute("SELECT id FROM public.users WHERE auth_id = %s", (auth_id,))
    uid = cur.fetchone()[0]
    if legacy_role in {"service_seeker", "client"}:
        cur.execute("INSERT INTO public.service_seeker_profiles(user_id) VALUES(%s)", (uid,))
    elif legacy_role in {"transporter", "logistics_provider"}:
        cur.execute("INSERT INTO public.transporter_profiles(user_id) VALUES(%s)", (uid,))
    return {"id": uid, "auth_id": auth_id, "email": email}


def test_role_attributes_and_no_table_ownership(role_env_db):
    with psycopg2.connect(role_env_db["owner_url"]) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin, rolreplication
            FROM pg_roles
            WHERE rolname IN ('dtx_api_runtime', 'dtx_scheduler_worker', 'dtx_auditor_ro')
            ORDER BY rolname
            """
        )
        rows = cur.fetchall()
        assert rows == [
            ("dtx_api_runtime", False, False, False, False, False, False),
            ("dtx_auditor_ro", False, False, False, False, False, False),
            ("dtx_scheduler_worker", False, False, False, False, False, False),
        ]
        cur.execute(
            """
            SELECT count(*)
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tableowner IN ('dtx_api_runtime', 'dtx_scheduler_worker', 'dtx_auditor_ro')
            """
        )
        assert cur.fetchone()[0] == 0
        for client_role in ("anon", "authenticated"):
            for runtime_role in ("dtx_api_runtime", "dtx_scheduler_worker", "dtx_auditor_ro"):
                cur.execute("SELECT pg_has_role(%s, %s, 'MEMBER')", (client_role, runtime_role))
                assert cur.fetchone()[0] is False
        for role_name in ("public", "anon", "authenticated", "dtx_api_runtime", "dtx_scheduler_worker", "dtx_auditor_ro"):
            cur.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (role_name,))
            assert cur.fetchone()[0] is False
        cur.execute("SELECT rolconfig FROM pg_roles WHERE rolname = 'dtx_auditor_ro'")
        auditor_config = cur.fetchone()[0] or []
        assert "default_transaction_read_only=on" in auditor_config


def test_residual_grants_locked_down_for_anon_and_authenticated(role_env_db):
    locked_objects = (
        "password_reset_otps",
        "login_activity",
        "commission_policies",
        "terms_versions",
        "saved_payment_methods_safe",
        "transporter_review_aggregates",
    )
    with psycopg2.connect(role_env_db["owner_url"]) as conn, conn.cursor() as cur:
        for role in ("public", "anon", "authenticated"):
            for obj in locked_objects:
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    cur.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (role, f"public.{obj}", priv),
                    )
                    assert cur.fetchone()[0] is False, f"{role} unexpectedly has {priv} on {obj}"

        for role in ("anon", "authenticated"):
            for obj in locked_objects:
                cur.execute(f"SET LOCAL ROLE {role}")
                cur.execute("SAVEPOINT sp_res")
                with pytest.raises(errors.InsufficientPrivilege):
                    cur.execute(f"SELECT 1 FROM public.{obj}")
                cur.execute("ROLLBACK TO SAVEPOINT sp_res")
                cur.execute("RELEASE SAVEPOINT sp_res")
                cur.execute("RESET ROLE")


def _ensure_commission_policy(db):
    if get_active_policy(db, "one_time_order") is not None:
        return
    stamp = datetime.now(timezone.utc).isoformat()
    policy = create_policy_version(db, "one_time_order", Decimal("20.00"), "Phase 4B-1 seed", None, stamp)
    create_terms_version(db, policy["id"], "Phase 4B-1 terms seed", None, stamp)


def test_negative_privilege_and_rls_isolation_across_non_owner_roles(role_env_db):
    with psycopg2.connect(role_env_db["owner_url"]) as conn, conn.cursor() as cur:
        _ensure_commission_policy(Db(conn))
        buyer = _seed_user(cur, "service_seeker")
        blocked_user = _seed_user(cur, "everyday_user")
        cur.execute("UPDATE public.users SET is_blocked = true WHERE id = %s", (blocked_user["id"],))
        admin_u = _seed_user(cur, "platform_admin")
        cur.execute("UPDATE public.users SET role='admin', legacy_role='platform_admin' WHERE id=%s", (admin_u["id"],))
        cur.execute("INSERT INTO public.wallets(user_id, role, balance, locked_balance) VALUES(%s, 'client', 2000, 0) RETURNING id", (buyer["id"],))
        wid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.wallet_transactions(wallet_id, user_id, type, amount, balance_after, description) "
            "VALUES(%s, %s, 'topup', 2000, 2000, 'seed') RETURNING id",
            (wid, buyer["id"]),
        )
        wtx_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.http_rate_limits(bucket_key, window_start, request_count, expires_at) "
            "VALUES('active.bucket', now(), 1, now() + interval '1 hour'), "
            "('expired.bucket', now() - interval '2 hours', 1, now() - interval '1 hour')"
        )
        conn.commit()

    # 1. API runtime cannot DDL, disable triggers, update/delete immutable tables, or delete blocked/admin users
    with psycopg2.connect(role_env_db["api_url"]) as aconn, aconn.cursor() as acur:
        for ddl_stmt in (
            "CREATE TABLE public.evil_table(x int)",
            "ALTER TABLE public.wallet_transactions DISABLE TRIGGER business_wallet_ledger_immutable",
            "ALTER TABLE public.wallets DROP CONSTRAINT wallets_money_invariants",
            "TRUNCATE TABLE public.wallet_transactions",
            "UPDATE public.wallet_transactions SET amount = 99999 WHERE id = %s" % wtx_id,
            "DELETE FROM public.wallet_transactions WHERE id = %s" % wtx_id,
            "DELETE FROM public.security_events",
            "DELETE FROM public.business_audit_events",
            "UPDATE public.financial_journal SET reference = 'x'",
        ):
            acur.execute("SAVEPOINT sp_api")
            with pytest.raises(errors.InsufficientPrivilege):
                acur.execute(ddl_stmt)
            acur.execute("ROLLBACK TO SAVEPOINT sp_api")
            acur.execute("RELEASE SAVEPOINT sp_api")

        # Narrow DELETE RLS: blocked user, admin, and active rate limit bucket cannot be deleted
        acur.execute("DELETE FROM public.users WHERE id = %s", (blocked_user["id"],))
        assert acur.rowcount == 0
        acur.execute("DELETE FROM public.users WHERE id = %s", (admin_u["id"],))
        assert acur.rowcount == 0
        acur.execute("DELETE FROM public.http_rate_limits WHERE bucket_key = 'active.bucket'")
        assert acur.rowcount == 0
        acur.execute("DELETE FROM public.http_rate_limits WHERE bucket_key = 'expired.bucket'")
        assert acur.rowcount == 1
        aconn.rollback()

    # 2. Scheduler cannot touch auth secrets, PII columns, or delete/truncate tables
    with psycopg2.connect(role_env_db["scheduler_url"]) as sconn, sconn.cursor() as scur:
        for denied_stmt in (
            "SELECT * FROM public.mpin_credentials",
            "SELECT * FROM public.mpin_step_up_authorizations",
            "SELECT * FROM public.user_sessions",
            "SELECT * FROM public.password_reset_otps",
            "SELECT * FROM public.reset_tokens",
            "SELECT * FROM public.admin_step_up_authorizations",
            "SELECT * FROM public.delivery_otp_challenges",
            "SELECT * FROM public.saved_payment_methods",
            "SELECT * FROM public.wallet_withdrawal_requests",
            "SELECT mpin_hash FROM public.users",
            "SELECT email FROM public.users",
            "SELECT cnic FROM public.users",
            "SELECT * FROM public.security_events",
            "DELETE FROM public.shipments",
            "ALTER TABLE public.shipments DISABLE TRIGGER ALL",
        ):
            scur.execute("SAVEPOINT sp_sched")
            with pytest.raises(errors.InsufficientPrivilege):
                scur.execute(denied_stmt)
            scur.execute("ROLLBACK TO SAVEPOINT sp_sched")
            scur.execute("RELEASE SAVEPOINT sp_sched")

    # 3. Auditor is strictly read-only and blocked from auth/credential tables
    with psycopg2.connect(role_env_db["auditor_url"]) as rconn, rconn.cursor() as rcur:
        for forbidden in (
            "INSERT INTO public.wallet_transactions(wallet_id, user_id, type, amount, balance_after) VALUES(1,1,'x',1,1)",
            "UPDATE public.wallets SET balance = 1",
            "DELETE FROM public.shipments",
            "SELECT * FROM public.mpin_credentials",
            "SELECT * FROM public.mpin_step_up_authorizations",
            "SELECT * FROM public.password_reset_otps",
            "SELECT * FROM public.reset_tokens",
            "SELECT * FROM public.admin_step_up_authorizations",
            "SELECT * FROM public.delivery_otp_challenges",
            "SELECT * FROM public.saved_payment_methods",
            "SELECT mpin_hash FROM public.users",
            "SELECT email FROM public.users",
        ):
            rcur.execute("SAVEPOINT sp_aud")
            with pytest.raises(psycopg2.Error):
                rcur.execute(forbidden)
            rcur.execute("ROLLBACK TO SAVEPOINT sp_aud")
            rcur.execute("RELEASE SAVEPOINT sp_aud")
        rcur.execute("SELECT count(*) FROM public.financial_journal")
        assert rcur.fetchone()[0] == 0


def test_real_non_owner_financial_scheduler_and_auditor_workflows_succeed(role_env_db, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    monkeypatch.setenv("DIGITRANSX_DELIVERY_OTP_SECRET", "phase4b1-delivery-otp-secret-minimum-32")
    monkeypatch.setenv("DIGITRANSX_API_DB_URL", role_env_db["api_url"])
    monkeypatch.setenv("DIGITRANSX_SCHEDULER_DB_URL", role_env_db["scheduler_url"])
    monkeypatch.setenv("DIGITRANSX_AUDITOR_DB_URL", role_env_db["auditor_url"])
    reset_db_pools()

    with psycopg2.connect(role_env_db["owner_url"]) as conn, conn.cursor() as cur:
        _ensure_commission_policy(Db(conn))
        client_u = _seed_user(cur, "service_seeker")
        transporter_u = _seed_user(cur, "transporter")
        cur.execute("INSERT INTO public.wallets(user_id, role, balance, locked_balance) VALUES(%s, 'client', 250000, 0)", (client_u["id"],))
        cur.execute("INSERT INTO public.wallets(user_id, role, balance, locked_balance, minimum_required, is_minimum_met) VALUES(%s, 'transporter', 50000, 30000, 30000, true)", (transporter_u["id"],))
        cur.execute(
            "INSERT INTO public.vehicles(owner_user_id, truck_number, chassis_number, truck_type, capacity_tons, main_use, status, current_city, current_lat, current_lng, service_radius_km, operating_provinces) "
            "VALUES(%s, %s, %s, 'flatbed', 15, 'goods', 'active', 'Lahore', 31.5204, 74.3587, 150, 'Punjab') RETURNING id",
            (transporter_u["id"], f"LEA-{uuid4().hex[:6]}", f"CHS-{uuid4().hex[:10]}"),
        )
        truck_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.shipments(client_user_id, pickup_city, pickup_lat, pickup_lng, dropoff_city, dropoff_lat, dropoff_lng, pickup_date, pickup_time, goods_type, goods_weight_tons, required_truck_types, seeker_kind_snapshot, status, estimated_budget) "
            "VALUES(%s, 'Lahore', 31.5204, 74.3587, 'Faisalabad', 31.4504, 73.1350, current_date + 2, '09:00', 'Steel', 10, '[\"flatbed\"]', 'business', 'open', 100000) RETURNING id",
            (client_u["id"],),
        )
        order_id = cur.fetchone()[0]
        conn.commit()

    # Step 1: dtx_api_runtime executes bid, checkout, start trip, and delivery OTP
    with open_db() as db:
        bid_id = db.execute_exact(
            "INSERT INTO public.shipment_bids(order_id, transporter_user_id, truck_id, bid_price, status) "
            "VALUES(%s, %s, %s, %s, 'pending') RETURNING id",
            (order_id, transporter_u["id"], truck_id, Decimal("100000.00")),
        ).fetchone()["id"]
        db.commit()

    with open_db() as db:
        checkout_res = perform_checkout(
            db,
            {"id": client_u["id"], "role": "service_seeker"},
            order_id,
            bid_id,
            {},
            idempotency_key=f"p4b1-chk-{uuid4().hex}",
        )
        trip_id = checkout_res["trip"]["id"]
        payment_id = checkout_res["payment"]["id"]
        perform_start_trip(db, {"id": transporter_u["id"], "role": "logistics_provider"}, order_id, trip_id)
        issue_delivery_otp(db, {"id": transporter_u["id"], "role": "logistics_provider"}, order_id, trip_id)
        otp = delivery_otp_for_client(db, {"id": client_u["id"], "role": "service_seeker"}, order_id, trip_id, reveal=True)["otp"]
        verify_res = verify_delivery_otp(db, {"id": transporter_u["id"], "role": "logistics_provider"}, order_id, trip_id, otp)
        assert verify_res["verified"] is True
        db.commit()

    # Step 2: dtx_scheduler_worker releases due tranche 2 settlement
    with open_scheduler_db() as sdb:
        past_completion = datetime.now(timezone.utc) + timedelta(minutes=130)
        rel = release_due_settlements(sdb, now=past_completion)
        assert rel["released_count"] == 1
        overdue = process_overdue_delivery_confirmations(sdb)
        assert overdue["processed_count"] == 0
        sdb.commit()

    # Also test scheduler top-level job using DIGITRANSX_SCHEDULER_DB_URL
    res = scheduler_mod.run_process_overdue_confirmations()
    assert "freight_settlements" in res

    # Step 3: Verify another held order refunds cleanly via dtx_api_runtime
    with psycopg2.connect(role_env_db["owner_url"]) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO public.shipments(client_user_id, pickup_city, pickup_lat, pickup_lng, dropoff_city, dropoff_lat, dropoff_lng, pickup_date, pickup_time, goods_type, goods_weight_tons, required_truck_types, seeker_kind_snapshot, status, estimated_budget) "
            "VALUES(%s, 'Lahore', 31.5204, 74.3587, 'Multan', 30.1575, 71.5249, current_date + 3, '10:00', 'Cement', 10, '[\"flatbed\"]', 'business', 'open', 50000) RETURNING id",
            (client_u["id"],),
        )
        order2_id = cur.fetchone()[0]
        conn.commit()
    with open_db() as db:
        bid2 = db.execute_exact(
            "INSERT INTO public.shipment_bids(order_id, transporter_user_id, truck_id, bid_price, status) "
            "VALUES(%s, %s, %s, %s, 'pending') RETURNING id",
            (order2_id, transporter_u["id"], truck_id, Decimal("50000.00")),
        ).fetchone()["id"]
        chk2 = perform_checkout(
            db,
            {"id": client_u["id"], "role": "service_seeker"},
            order2_id,
            bid2,
            {},
            idempotency_key=f"p4b1-ref-{uuid4().hex}",
        )
        ref = refund_one_time_payment(db, chk2["payment"]["id"])
        assert ref["refunded"] is True
        db.commit()

    # Step 3b: Verify withdrawal workflow executes under dtx_api_runtime
    with open_db() as db:
        t_wallet = db.execute_exact("SELECT * FROM public.wallets WHERE user_id = %s FOR UPDATE", (transporter_u["id"],)).fetchone()
        pending_req = db.execute_exact(
            "INSERT INTO public.wallet_withdrawal_requests(wallet_id, user_id, amount, status, idempotency_key) "
            "VALUES(%s, %s, %s, 'pending', %s) RETURNING id",
            (t_wallet["id"], transporter_u["id"], Decimal("10000.00"), f"p4b1-wd-p-{uuid4().hex}"),
        ).fetchone()["id"]
        assert withdrawal_limits.pending_withdrawal_total(db, transporter_u["id"]) == Decimal("10000.00")
        assert withdrawal_limits.max_withdrawable(t_wallet, pending_total=Decimal("10000.00")) == Decimal("90000.00")
        new_bal = Decimal(str(t_wallet["balance"])) - Decimal("5000.00")
        db.execute_exact("UPDATE public.wallets SET balance = %s WHERE id = %s", (new_bal, t_wallet["id"]))
        t_wallet_updated = dict(t_wallet)
        t_wallet_updated["balance"] = new_bal
        db.execute_exact(
            "INSERT INTO public.wallet_withdrawal_requests(wallet_id, user_id, amount, status, idempotency_key, resolved_at) "
            "VALUES(%s, %s, %s, 'approved', %s, now())",
            (t_wallet["id"], transporter_u["id"], Decimal("5000.00"), f"p4b1-wd-a-{uuid4().hex}"),
        )
        wallet_helpers.insert_wallet_transaction(
            db,
            t_wallet_updated,
            transporter_u["id"],
            "withdrawal",
            Decimal("-5000.00"),
            description="Phase 4B-1 withdrawal check",
            reference_id=f"p4b1_wd_{pending_req}",
        )
        db.commit()

    # Step 4: dtx_auditor_ro verifies full reconciliation read-only
    with open_auditor_db() as adb:
        adb.execute("SET TRANSACTION READ ONLY")
        report = reconcile_business_rules.reconcile(adb)
        assert report["consistent"] is True
        bal = adb.execute_exact("SELECT balance FROM wallets WHERE user_id = %s", (transporter_u["id"],)).fetchone()["balance"]
        assert Decimal(str(bal)) == Decimal("125000.00")

    assert reconcile_business_rules.main() == 0


def test_separate_credential_resolution_prevents_silent_owner_fallback():
    staging_api = "postgresql://dtx_api_runtime.ref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"
    staging_sched = "postgresql://dtx_scheduler_worker.ref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"
    staging_aud = "postgresql://dtx_auditor_ro.ref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"
    staging_mig = "postgresql://postgres.ref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"

    env = {
        "DIGITRANSX_ENVIRONMENT": "staging",
        "DIGITRANSX_API_DB_URL": staging_api,
        "DIGITRANSX_SCHEDULER_DB_URL": staging_sched,
        "DIGITRANSX_AUDITOR_DB_URL": staging_aud,
        "DIGITRANSX_MIGRATION_DB_URL": staging_mig,
    }
    assert resolve_database_dsn(DB_ROLE_API, env) == staging_api
    assert resolve_database_dsn(DB_ROLE_SCHEDULER, env) == staging_sched
    assert resolve_database_dsn(DB_ROLE_AUDITOR, env) == staging_aud
    assert resolve_migration_dsn(env) == staging_mig

    # Never fall back silently to SUPABASE_DB_URL or MIGRATION_DB_URL outside local/test
    with pytest.raises(RuntimeError):
        resolve_database_dsn(DB_ROLE_API, {"DIGITRANSX_ENVIRONMENT": "production", "SUPABASE_DB_URL": staging_api})
    with pytest.raises(RuntimeError):
        resolve_database_dsn(DB_ROLE_SCHEDULER, {"DIGITRANSX_ENVIRONMENT": "staging", "DIGITRANSX_API_DB_URL": staging_api})
    with pytest.raises(RuntimeError):
        resolve_database_dsn(DB_ROLE_AUDITOR, {"DIGITRANSX_ENVIRONMENT": "staging", "DIGITRANSX_API_DB_URL": staging_api})

    # Owner roles blocked on API, scheduler, and auditor
    for bad_owner in (
        "postgresql://postgres:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require",
        "postgresql://postgres.projref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require",
        "postgresql://supabase_admin:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require",
    ):
        for role in (DB_ROLE_API, DB_ROLE_SCHEDULER, DB_ROLE_AUDITOR):
            env_key = {
                DB_ROLE_API: "DIGITRANSX_API_DB_URL",
                DB_ROLE_SCHEDULER: "DIGITRANSX_SCHEDULER_DB_URL",
                DB_ROLE_AUDITOR: "DIGITRANSX_AUDITOR_DB_URL",
            }[role]
            with pytest.raises(RuntimeError):
                resolve_database_dsn(role, {"DIGITRANSX_ENVIRONMENT": "production", env_key: bad_owner})

    # Local/test compatibility fallback remains intact
    local_env = {
        "DIGITRANSX_ENVIRONMENT": "test",
        "SUPABASE_DB_URL": "postgresql://postgres@127.0.0.1:5432/dtx_phase1b2c0_test",
    }
    assert resolve_database_dsn(DB_ROLE_API, local_env) == local_env["SUPABASE_DB_URL"]
    assert resolve_database_dsn(DB_ROLE_SCHEDULER, local_env) == local_env["SUPABASE_DB_URL"]
    assert resolve_database_dsn(DB_ROLE_AUDITOR, local_env) == local_env["SUPABASE_DB_URL"]
