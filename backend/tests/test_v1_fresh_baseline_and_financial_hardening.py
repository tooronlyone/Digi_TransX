"""Authoritative V1 fresh-install baseline and Task 3 financial hardening proofs.

All database tests execute strictly against isolated disposable local
PostgreSQL databases via TEST_SUPABASE_DB_URL.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg2
from psycopg2 import errors
import pytest

from orders.business_lifecycle import (
    RULES_VERSION,
    delivery_otp_for_client,
    issue_delivery_otp,
    open_delivery_dispute,
    resolve_delivery_settlement,
    verify_delivery_otp,
)
from scripts.reconcile_business_rules import CHECKS, reconcile
from shared.commissions import itemized_fee
from shared.db import Db
from shared.payments import perform_checkout
from shared.reserves import ensure_security_reserve
from tests._life_helpers import STUBS, make_disposable, require_test_db_url
from tests.test_business_escrow_settlement import ACCEPTANCE, NOW, seed as seed_business_order
from tests.test_mpin_high_risk_routes_postgres import (
    _attach_authentication,
    _new_user,
    _protected_post,
    high_risk_route_database_url,
    high_risk_route_env,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = ROOT / "supabase" / "schema.sql"
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
BASELINE_MIGRATION = MIGRATIONS_DIR / "20261116000000_digitransx_v1_baseline.sql"
LEGACY_MIGRATIONS_DIR = ROOT / "Future" / "supabase" / "legacy_migrations"
SHOPKEEPER_REF_SQL = ROOT / "Future" / "supabase" / "shopkeeper-marketplace-v2-reference.sql"

EXCLUDED_V2_TABLES = (
    "agreement_posts",
    "agreement_post_trucks",
    "agreement_bids",
    "agreement_bid_trucks",
    "agreements",
    "agreement_trucks",
    "agreement_trips",
    "agreement_monthly_payments",
    "agreement_payment_penalties",
    "fuel_station_profiles",
    "fuel_station_pumps",
    "fuel_station_dispenses",
    "fuel_platform_treasury",
    "fuel_credit_accounts",
    "fuel_vouchers",
    "fuel_credit_events",
    "shopkeeper_profiles",
    "marketplace_parts",
    "marketplace_orders",
    "marketplace_order_items",
    "part_rfqs",
    "part_rfq_bids",
    "shop_products",
    "shop_sales",
    "shop_sale_items",
    "marketplace_delivery_secrets",
    "marketplace_financial_events",
)


def _local_url():
    url = require_test_db_url()
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Baseline and hardening tests require loopback TEST_SUPABASE_DB_URL")
    return url


@pytest.fixture(scope="module")
def baseline_url():
    migration_blocks = [
        p.read_text(encoding="utf-8")
        for p in sorted(MIGRATIONS_DIR.glob("*.sql"))
    ]
    url, cleanup = make_disposable(_local_url(), STUBS, *migration_blocks)
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def baseline_env(baseline_url, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_DELIVERY_OTP_SECRET", "v1-hardening-test-otp-secret-32chars-min")

    @contextmanager
    def connect():
        conn = psycopg2.connect(baseline_url)
        try:
            yield Db(conn)
        finally:
            conn.rollback()
            conn.close()

    return connect


def _savepoint_rejects(db, fn, expected_errors):
    db.execute("SAVEPOINT v1_guard")
    with pytest.raises(expected_errors) as exc:
        fn()
    db.execute("ROLLBACK TO SAVEPOINT v1_guard")
    db.execute("RELEASE SAVEPOINT v1_guard")
    return exc.value


def test_active_migrations_consolidated_and_v2_archives_preserved():
    active = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    assert active == [
        "20261116000000_digitransx_v1_baseline.sql",
        "20261116010000_sprint1_security_hardening.sql",
        "20261116020000_sprint2_security_hardening.sql",
        "20261116030000_sprint3_security_hardening.sql",
        "20261116040000_phase4b1_least_privilege_roles.sql",
    ]
    assert len(list(LEGACY_MIGRATIONS_DIR.glob("*.sql"))) == 49
    assert SHOPKEEPER_REF_SQL.exists()
    for mig in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = mig.read_text(encoding="utf-8")
        assert sql.lstrip().startswith("--")
        assert "\nBEGIN;\n" in sql
        assert sql.rstrip().endswith("COMMIT;")


def test_fresh_v1_baseline_matches_schema_sql_and_excludes_v2_objects(baseline_url):
    schema_url, cleanup_schema = make_disposable(
        _local_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    try:
        with psycopg2.connect(baseline_url) as b_conn, psycopg2.connect(schema_url) as s_conn:
            def snapshot(conn):
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT table_name, column_name, data_type, is_nullable "
                        "FROM information_schema.columns WHERE table_schema='public' ORDER BY 1,2"
                    )
                    cols = cur.fetchall()
                    cur.execute(
                        "SELECT conrelid::regclass::text, conname, contype "
                        "FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1,2"
                    )
                    cons = cur.fetchall()
                    cur.execute(
                        "SELECT c.relname, t.tgname FROM pg_trigger t "
                        "JOIN pg_class c ON c.oid=t.tgrelid "
                        "WHERE c.relnamespace='public'::regnamespace AND NOT t.tgisinternal ORDER BY 1,2"
                    )
                    trgs = cur.fetchall()
                    cur.execute(
                        "SELECT tablename, policyname, cmd FROM pg_policies WHERE schemaname='public' ORDER BY 1,2"
                    )
                    pols = cur.fetchall()
                    return cols, cons, trgs, pols

            assert snapshot(b_conn) == snapshot(s_conn)

            with b_conn.cursor() as cur:
                for excluded in EXCLUDED_V2_TABLES:
                    cur.execute("SELECT to_regclass(%s)", (f"public.{excluded}",))
                    assert cur.fetchone()[0] is None, excluded

                cur.execute("SELECT enum_range(NULL::public.app_role)::text[]")
                assert set(cur.fetchone()[0]) == {"admin", "customer", "transporter"}

                cur.execute(
                    "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='public' AND c.relkind='r' AND NOT c.relrowsecurity"
                )
                assert cur.fetchall() == []

                cur.execute("SELECT count(*) FROM public.commission_policies")
                assert cur.fetchone()[0] >= 1
                cur.execute("SELECT count(*) FROM public.terms_versions")
                assert cur.fetchone()[0] >= 1
                cur.execute("SELECT count(*) FROM public.security_reserve_brackets")
                assert cur.fetchone()[0] == 5
                cur.execute("SELECT id FROM storage.buckets WHERE id='shipment-documents'")
                assert cur.fetchone() == ("shipment-documents",)
                cur.execute(
                    "SELECT convalidated FROM pg_constraint "
                    "WHERE conrelid='public.wallets'::regclass AND conname='wallets_money_invariants'"
                )
                assert cur.fetchone() == (True,)
    finally:
        cleanup_schema()


def test_financial_constraints_reject_ownership_mismatch_nan_infinity_and_null_bypasses(baseline_env):
    with baseline_env() as db:
        s = seed_business_order(db, open_order=False)
        client_id = s["client"]["id"]
        transporter_id = s["transporter"]["id"]
        payment_id = s["payment_id"]
        trip_id = s["trip_id"]
        order_id = s["order_id"]

        client_wallet = db.execute_exact(
            "SELECT id FROM wallets WHERE user_id=%s", (client_id,)
        ).fetchone()["id"]
        transporter_wallet = db.execute_exact(
            "SELECT id FROM wallets WHERE user_id=%s", (transporter_id,)
        ).fetchone()["id"]

        # 1. Cross-owner wallet_transactions rejected
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,balance_after) "
                "VALUES(%s,%s,'topup',100,100)",
                (client_wallet, transporter_id),
            ),
            errors.ForeignKeyViolation,
        )

        # 2. Zero / NaN / Infinity / oversize wallet_transactions rejected
        for bad_sql, params in (
            ("INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,balance_after) VALUES(%s,%s,'topup',0,10000)", (client_wallet, client_id)),
            ("INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,balance_after) VALUES(%s,%s,'topup','NaN'::numeric,10000)", (client_wallet, client_id)),
            ("INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,balance_after) VALUES(%s,%s,'topup','Infinity'::numeric,10000)", (client_wallet, client_id)),
            ("INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,balance_after) VALUES(%s,%s,'topup',100,'Infinity'::numeric)", (client_wallet, client_id)),
            ("INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,balance_after) VALUES(%s,%s,'topup',1000000000000.00,10000)", (client_wallet, client_id)),
        ):
            _savepoint_rejects(db, lambda q=bad_sql, p=params: db.execute(q, p), errors.CheckViolation)

        # 3. Wallets invalid role & NaN/Infinity/oversize rejected
        _savepoint_rejects(
            db,
            lambda: db.execute("UPDATE wallets SET role='shopkeeper' WHERE id=%s", (client_wallet,)),
            errors.CheckViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute("UPDATE wallets SET balance='NaN'::numeric WHERE id=%s", (client_wallet,)),
            errors.CheckViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute("UPDATE wallets SET balance=1000000000000.00 WHERE id=%s", (client_wallet,)),
            errors.CheckViolation,
        )

        # 4. payments NOT NULL shipment_id & zero/NaN/Infinity checks
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO payments(trip_id,shipment_id,invoice_number,client_user_id,transporter_user_id,"
                "bid_price,company_fee,transporter_amount,status) VALUES(%s,NULL,%s,%s,%s,100,20,80,'held')",
                (trip_id, f"INV-{uuid4().hex[:8]}", client_id, transporter_id),
            ),
            errors.NotNullViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO payments(trip_id,shipment_id,invoice_number,client_user_id,transporter_user_id,"
                "bid_price,company_fee,transporter_amount,wallet_funded_amount,funding_source,status) "
                "VALUES(%s,%s,%s,%s,%s,0,0,0,0,'wallet','held')",
                (trip_id, order_id, f"INV-{uuid4().hex[:8]}", client_id, transporter_id),
            ),
            errors.CheckViolation,
        )

        # 5. freight_settlements NaN = NaN + 0 bypass rejected
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO freight_settlements(payment_id,trip_id,transporter_user_id,client_user_id,"
                "gross_amount,company_fee,net_entitlement,reserve_contribution,tranche1_amount,tranche2_amount,"
                "fee_breakdown,reserve_policy_state,completed_at,dispute_deadline_at,release_eligible_at) "
                "VALUES(%s,%s,%s,%s,'NaN'::numeric,0,'NaN'::numeric,0,'NaN'::numeric,0,'{}'::jsonb,'test',now(),now()+interval '90 minutes',now()+interval '120 minutes')",
                (payment_id, trip_id, transporter_id, client_id),
            ),
            errors.CheckViolation,
        )

        # 6. Withdrawals constraints & idempotency uniqueness
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO wallet_withdrawal_requests(user_id,amount,status) VALUES(%s,0,'pending')",
                (transporter_id,),
            ),
            errors.CheckViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO wallet_withdrawal_requests(user_id,amount,status,resolved_at) VALUES(%s,500,'approved',NULL)",
                (transporter_id,),
            ),
            errors.CheckViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO wallet_withdrawal_requests(wallet_id,user_id,amount,status) VALUES(%s,%s,500,'pending')",
                (client_wallet, transporter_id),
            ),
            errors.CheckViolation,
        )

        # Valid insert omitting wallet_id resolves wallet_id automatically via trigger
        req_id = db.execute_exact(
            "INSERT INTO wallet_withdrawal_requests(user_id,amount,status,idempotency_key) "
            "VALUES(%s,500,'pending','idem-v1-check') RETURNING id",
            (transporter_id,),
        ).fetchone()["id"]
        assert db.execute_exact(
            "SELECT wallet_id FROM wallet_withdrawal_requests WHERE id=%s", (req_id,)
        ).fetchone()["wallet_id"] == transporter_wallet

        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO wallet_withdrawal_requests(user_id,amount,status,idempotency_key) "
                "VALUES(%s,500,'pending','idem-v1-check')",
                (transporter_id,),
            ),
            errors.UniqueViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute("UPDATE wallet_withdrawal_requests SET amount=99999 WHERE id=%s", (req_id,)),
            errors.CheckViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute("DELETE FROM wallet_withdrawal_requests WHERE id=%s", (req_id,)),
            errors.CheckViolation,
        )


def test_immutable_financial_history_settlement_resolution_and_reserve_reconciliation(baseline_env):
    with baseline_env() as db:
        s = seed_business_order(db, open_order=True, client_balance=Decimal("100000"))
        checkout = perform_checkout(
            db, s["client"], s["order_id"], s["bid_id"], ACCEPTANCE, "hardening-" + uuid4().hex
        )
        payment_id = checkout["payment"]["id"]
        trip_id = checkout["trip"]["id"]
        order_id = s["order_id"]

        # Append-only wallet_transactions blocks both UPDATE and DELETE even on order_payment
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "UPDATE wallet_transactions SET amount=0.01 WHERE user_id=%s", (s["client"]["id"],)
            ),
            errors.CheckViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute("DELETE FROM wallet_transactions WHERE user_id=%s", (s["client"]["id"],)),
            errors.CheckViolation,
        )

        # Balanced mutation of payments financial terms blocked by guard_payment_financial_invariants
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "UPDATE payments SET company_fee=company_fee+100, transporter_amount=transporter_amount-100 WHERE id=%s",
                (payment_id,),
            ),
            errors.RaiseException,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute("DELETE FROM payments WHERE id=%s", (payment_id,)),
            errors.RaiseException,
        )

        # Deliver + dispute + settlement resolution validation
        now = datetime.now(timezone.utc)
        db.execute("UPDATE shipment_trips SET status='in_progress' WHERE id=%s", (trip_id,))
        db.execute("UPDATE shipments SET status='in_progress' WHERE id=%s", (order_id,))
        issue_delivery_otp(db, s["transporter"], order_id, trip_id, now=now)
        otp = delivery_otp_for_client(db, s["client"], order_id, trip_id, reveal=True, now=now)
        verify_delivery_otp(db, s["transporter"], order_id, trip_id, otp["otp"], now=now)
        dispute_res = open_delivery_dispute(
            db, s["client"], order_id, trip_id, "damaged", evidence=[{"kind": "photo"}], now=now
        )
        settlement = db.execute_exact(
            "SELECT * FROM freight_settlements WHERE trip_id=%s", (trip_id,)
        ).fetchone()

        # Bad resolution arithmetic / non-admin / empty evidence rejected at SQL level
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO freight_settlement_resolutions(settlement_id,dispute_id,admin_user_id,"
                "client_refund_amount,transporter_release_amount,investigation_result,notes,evidence) "
                "VALUES(%s,%s,%s,%s,%s,'verified_misconduct','bad sum','[\"doc\"]'::jsonb)",
                (settlement["id"], dispute_res["dispute"]["id"], s["admin"]["id"], Decimal("1"), Decimal("1")),
            ),
            errors.CheckViolation,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO freight_settlement_resolutions(settlement_id,dispute_id,admin_user_id,"
                "client_refund_amount,transporter_release_amount,investigation_result,notes,evidence) "
                "VALUES(%s,%s,%s,%s,0,'verified_misconduct','non admin','[\"doc\"]'::jsonb)",
                (settlement["id"], dispute_res["dispute"]["id"], s["client"]["id"], settlement["tranche2_amount"]),
            ),
            errors.CheckViolation,
        )

        # Valid resolution succeeds and reconciliation report stays consistent
        resolve_delivery_settlement(
            db,
            s["admin"],
            settlement["id"],
            Decimal("1000.00"),
            "Verified partial adjustment.",
            ["evidence://doc-1"],
            "verified_misconduct",
            now=now,
        )
        # Terminal status regression blocked on BOTH payments and freight_settlements
        _savepoint_rejects(
            db,
            lambda: db.execute("UPDATE payments SET status='held' WHERE id=%s", (payment_id,)),
            errors.RaiseException,
        )
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "UPDATE freight_settlements SET status='pending_release' WHERE id=%s", (settlement["id"],)
            ),
            errors.CheckViolation,
        )

        # Underbacked security_reserves update blocked at commit / reserve decrease blocked immediately
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "UPDATE security_reserves SET balance=balance-1 WHERE user_id=%s", (s["transporter"]["id"],)
            ),
            errors.CheckViolation,
        )
        report = reconcile(db)
        assert set(CHECKS) >= {
            "unbalanced_journals",
            "freight_split_mismatches",
            "underbacked_security_reserves",
            "wallet_transaction_owner_mismatches",
            "security_reserve_entry_mismatches",
            "settlement_resolution_mismatches",
        }
        assert report["consistent"] is True

        # Security reserve deferred backing check aborts transaction when underbacked
        db.commit()
        _savepoint_rejects(
            db,
            lambda: (
                db.execute("SET CONSTRAINTS trg_reconcile_security_reserve IMMEDIATE"),
                db.execute(
                    "UPDATE security_reserves SET balance=50000 WHERE user_id=%s",
                    (s["transporter"]["id"],),
                ),
            ),
            errors.CheckViolation,
        )

        # Driver fuel log constraints & isolation from financial balances
        wallet_before = db.execute_exact(
            "SELECT balance, locked_balance FROM wallets WHERE user_id=%s", (s["transporter"]["id"],)
        ).fetchone()
        _savepoint_rejects(
            db,
            lambda: db.execute(
                "INSERT INTO driver_fuel_logs(driver_user_id,pump_name,city,fuel_type,liters,price_per_liter,total_amount,payment_mode) "
                "VALUES(%s,'Test Pump','Lahore','diesel',0,280,0,'cash')",
                (s["transporter"]["id"],),
            ),
            errors.CheckViolation,
        )
        db.commit()
        assert db.execute_exact(
            "SELECT balance, locked_balance FROM wallets WHERE user_id=%s", (s["transporter"]["id"],)
        ).fetchone() == wallet_before


def test_http_withdrawal_idempotency_replay_conflict_and_concurrent_race(
    high_risk_route_env, baseline_url
):
    client, db = high_risk_route_env
    user_id = _new_user(
        db, legacy_role="logistics_provider", app_role="transporter", suffix="withdraw-idem"
    )
    db.execute(
        "INSERT INTO transporter_profiles(user_id,company_name,payout_card_token) "
        "VALUES(%s,'Carrier','provider-token-idem')",
        (user_id,),
    )
    db.execute(
        "INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
        "VALUES(%s,'transporter',40000,30000,30000,true)",
        (user_id,),
    )
    _attach_authentication(client, db, user_id)

    first, _ = _protected_post(
        client,
        "/api/wallet/withdraw-locked",
        {"amount": 5000},
        extra_headers={"Idempotency-Key": "withdraw-key-001"},
    )
    assert first.status_code == 200, first.get_data(as_text=True)
    assert first.get_json()["auto_approved"] is True
    assert Decimal(str(db.execute("SELECT balance FROM wallets WHERE user_id=%s", (user_id,)).fetchone()["balance"])) == Decimal("35000.00")

    # Replay with exact same Idempotency-Key and amount must not debit again
    replay = client.post(
        "/api/wallet/withdraw-locked",
        json={"amount": 5000},
        headers={"X-CSRF-Token": "route-step-up-csrf", "Idempotency-Key": "withdraw-key-001"},
    )
    assert replay.status_code == 200, replay.get_data(as_text=True)
    assert replay.get_json()["replayed"] is True
    assert db.execute("SELECT count(*) AS n FROM wallet_withdrawal_requests WHERE user_id=%s", (user_id,)).fetchone()["n"] == 1
    assert Decimal(str(db.execute("SELECT balance FROM wallets WHERE user_id=%s", (user_id,)).fetchone()["balance"])) == Decimal("35000.00")

    # Conflict: reusing key with different amount must be rejected 409
    conflict = client.post(
        "/api/wallet/withdraw-locked",
        json={"amount": 2000},
        headers={"X-CSRF-Token": "route-step-up-csrf", "Idempotency-Key": "withdraw-key-001"},
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["code"] == "idempotency_conflict"

    # Concurrent DB-level checkout race on an isolated baseline DB: only 1 worker can win
    race_url, race_cleanup = make_disposable(_local_url(), STUBS, BASELINE_MIGRATION.read_text(encoding="utf-8"))
    try:
        with psycopg2.connect(race_url) as setup_conn:
            sdb = Db(setup_conn)
            s = seed_business_order(sdb, gross=Decimal("50000.00"), open_order=True, client_balance=Decimal("55000.00"))
            setup_conn.commit()
        barrier = threading.Barrier(4)

        def attempt(idx):
            with psycopg2.connect(race_url) as t_conn:
                tdb = Db(t_conn)
                barrier.wait(timeout=10)
                try:
                    res = perform_checkout(tdb, s["client"], s["order_id"], s["bid_id"], ACCEPTANCE, f"concurrent-race-{idx:02d}")
                    t_conn.commit()
                    return ("ok", res["payment"]["id"])
                except Exception as exc:
                    t_conn.rollback()
                    return ("err", f"{type(exc).__name__}: {exc}")

        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(attempt, range(4)))
        wins = [o for o in outcomes if o[0] == "ok"]
        assert len(wins) == 1, outcomes
        with psycopg2.connect(race_url) as verify_conn:
            vdb = Db(verify_conn)
            assert vdb.execute("SELECT count(*) AS n FROM payments WHERE shipment_id=%s AND status='held'", (s["order_id"],)).fetchone()["n"] == 1
            assert Decimal(str(vdb.execute("SELECT balance FROM wallets WHERE user_id=%s", (s["client"]["id"],)).fetchone()["balance"])) == Decimal("5000.00")
    finally:
        race_cleanup()
