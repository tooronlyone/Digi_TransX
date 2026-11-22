"""Real PostgreSQL proofs for the forward database audit remediation.

Only TEST_SUPABASE_DB_URL on a loopback host is accepted. Tests create and
remove their own disposable databases; the application DSN is never used.
"""
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg2
import pytest
from psycopg2.extras import Json

from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url


ROOT = Path(__file__).resolve().parents[2]
FEATURE_MARKER = "-- BEGIN OCTOBER 2026 FEATURE BASELINE"
LEGACY_MIGRATIONS = ROOT / "Future" / "supabase" / "legacy_migrations"
LEGACY_SCHEMA = ROOT / "Future" / "supabase" / "schema-with-agreements-v1.sql"
V1_BASELINE_MIGRATION = ROOT / "supabase" / "migrations" / "20261116000000_digitransx_v1_baseline.sql"
MIGRATION_PATHS = [
    LEGACY_MIGRATIONS / "20261024010000_database_authorization_hardening.sql",
    LEGACY_MIGRATIONS / "20261024020000_marketplace_financial_controls.sql",
    LEGACY_MIGRATIONS / "20261024030000_private_operational_read_surfaces.sql",
    LEGACY_MIGRATIONS / "20261024040000_validate_wallet_money_invariants.sql",
    LEGACY_MIGRATIONS / "20261025010000_driver_workflow_integrity.sql",
    LEGACY_MIGRATIONS / "20261025020000_payment_preference_convergence.sql",
]
FEATURE_PATHS = sorted(LEGACY_MIGRATIONS.glob("2026102[123]*.sql"))
DEFAULT_GRANTS = """
GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO anon,authenticated,service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE,SELECT ON SEQUENCES TO anon,authenticated,service_role;
"""
BACKEND_ONLY = [
    "admin_step_up_authorizations",
    "contact_messages",
    "driver_profiles", "driver_incidents", "driver_reviews",
    "driver_trip_assignments", "driver_gps_pings", "driver_fuel_logs",
    "driver_hire_contracts", "http_rate_limits", "vehicles",
    "withdrawal_limit_upgrade_requests",
]


def _local_url():
    url = require_test_db_url()
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Database authorization tests require isolated loopback PostgreSQL")
    return url


def _without_transaction_wrapper(sql):
    return "\n".join(line for line in sql.splitlines()
                     if line.strip().upper() not in {"BEGIN;", "COMMIT;"})


@pytest.fixture(scope="module", params=["fresh_schema", "fresh_baseline"])
def database_url(request):
    if request.param == "fresh_schema":
        blocks = [STUBS, DEFAULT_GRANTS, SCHEMA_SQL.read_text(encoding="utf-8")]
    else:
        migration_sqls = [
            p.read_text(encoding="utf-8")
            for p in sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
        ]
        blocks = [STUBS, DEFAULT_GRANTS, *migration_sqls]
    url, cleanup = make_disposable(_local_url(), *blocks)
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def database(database_url):
    conn = psycopg2.connect(database_url)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _user(cursor, legacy_role="service_seeker"):
    auth_id = str(uuid4())
    email = f"{uuid4().hex}@hardening.invalid"
    cursor.execute(
        "INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,%s)",
        (auth_id, email, Json({"legacy_role": legacy_role, "full_name": "Audit fixture"})),
    )
    cursor.execute("SELECT id,role,legacy_role FROM public.users WHERE auth_id=%s", (auth_id,))
    user_id, role, legacy = cursor.fetchone()
    return {"id": user_id, "auth_id": auth_id, "email": email, "role": role, "legacy": legacy}


@contextmanager
def _role(cursor, user=None, role="authenticated"):
    cursor.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",
                   (user["auth_id"] if user else "",))
    # role is a test-controlled constant, never application input.
    cursor.execute(f"SET LOCAL ROLE {role}")
    try:
        yield
    finally:
        cursor.execute("RESET ROLE")


def _rejected(cursor, query, params=(), codes=("42501",)):
    cursor.execute("SAVEPOINT rejected_operation")
    with pytest.raises(psycopg2.Error) as error:
        cursor.execute(query, params)
    error_code = error.value.pgcode
    cursor.execute("ROLLBACK TO SAVEPOINT rejected_operation")
    cursor.execute("RELEASE SAVEPOINT rejected_operation")
    assert error_code in codes


def test_signup_metadata_cannot_create_admin_and_trusted_promotion_still_works(database):
    with database.cursor() as cursor:
        user = _user(cursor, "platform_admin")
        assert (user["role"], user["legacy"]) == ("customer", "everyday_user")
        cursor.execute("UPDATE public.users SET role='admin',legacy_role='platform_admin' WHERE id=%s",
                       (user["id"],))
        with _role(cursor, user):
            cursor.execute("SELECT public.is_admin(),public.current_app_role()")
            assert cursor.fetchone() == (True, "admin")


def test_signup_cannot_rebind_an_existing_email(database):
    with database.cursor() as cursor:
        user = _user(cursor)
        _rejected(cursor,
                  "INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,'{}')",
                  (str(uuid4()), user["email"]), codes=("23505",))
        cursor.execute("SELECT auth_id::text FROM public.users WHERE id=%s", (user["id"],))
        assert cursor.fetchone()[0] == user["auth_id"]


def test_owner_cannot_mutate_legacy_role_block_or_credential_authority(database):
    with database.cursor() as cursor:
        user = _user(cursor)
        with _role(cursor, user):
            for assignments in ["legacy_role='platform_admin'", "is_blocked=false",
                                "credentials_version=999", "password_change_pending=false"]:
                _rejected(cursor, f"UPDATE public.users SET {assignments} WHERE id=%s", (user["id"],))
            _rejected(cursor, "UPDATE public.wallet_withdrawal_requests SET status='approved' WHERE user_id=%s",
                      (user["id"],))
            _rejected(cursor, "UPDATE public.transporter_profiles SET withdrawal_tier=3 WHERE user_id=%s",
                      (user["id"],))
        cursor.execute("SELECT credentials_version,password_change_pending FROM public.users WHERE id=%s",
                       (user["id"],))
        assert cursor.fetchone() == (0, False)
        cursor.execute("SELECT has_column_privilege('authenticated','public.users','legacy_role','UPDATE')")
        assert cursor.fetchone() == (False,)


@pytest.mark.parametrize("table_name", BACKEND_ONLY)
def test_portal_and_proof_tables_are_rls_enabled_and_backend_only(database, table_name):
    with database.cursor() as cursor:
        cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(%s)", (f"public.{table_name}",))
        assert cursor.fetchone() == (True,)
        for role in ("anon", "authenticated"):
            cursor.execute("SELECT has_table_privilege(%s,%s,'SELECT'),has_table_privilege(%s,%s,'INSERT'),"
                           "has_table_privilege(%s,%s,'UPDATE'),has_table_privilege(%s,%s,'DELETE')",
                           (role, f"public.{table_name}") * 4)
            assert cursor.fetchone() == (False, False, False, False)
        with _role(cursor, role="anon"):
            _rejected(cursor, f"SELECT * FROM public.{table_name}")


def test_service_role_keeps_portal_access_without_bypassrls(database):
    with database.cursor() as cursor:
        driver = _user(cursor, "driver")
        with _role(cursor, role="service_role"):
            cursor.execute("INSERT INTO public.driver_fuel_logs(driver_user_id,pump_name,city,fuel_type,liters,price_per_liter,total_amount,payment_mode,fuel_date) "
                           "VALUES(%s,'Audit Pump','Lahore','diesel',10,280,2800,'cash',current_date) RETURNING id", (driver["id"],))
            log_id = cursor.fetchone()[0]
            cursor.execute("SELECT driver_user_id FROM public.driver_fuel_logs WHERE id=%s", (log_id,))
            assert cursor.fetchone()[0] == driver["id"]


def test_private_operational_records_stay_hidden_after_accidental_read_grant(database):
    private_tables = ["vehicles", "driver_fuel_logs"]
    with database.cursor() as cursor:
        owner, driver = _user(cursor, "transporter"), _user(cursor, "driver")
        cursor.execute("INSERT INTO public.vehicles(owner_user_id,truck_number,chassis_number,truck_type,"
                       "capacity_tons,main_use,status,driver_cnic) "
                       "VALUES(%s,%s,%s,'flatbed',10,'goods','active','private-driver-cnic') RETURNING id",
                       (owner["id"], uuid4().hex, uuid4().hex))
        vehicle_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO public.driver_fuel_logs(driver_user_id,truck_id,pump_name,city,fuel_type,liters,price_per_liter,total_amount,payment_mode,fuel_date) "
                       "VALUES(%s,%s,'Audit Pump','Lahore','diesel',10,280,2800,'cash',current_date) RETURNING id",
                       (driver["id"], vehicle_id))
        log_id = cursor.fetchone()[0]
        cursor.execute("SELECT has_column_privilege('authenticated','public.vehicles','driver_cnic','SELECT'),"
                       "has_column_privilege('authenticated','public.driver_fuel_logs','total_amount','SELECT')")
        assert cursor.fetchone() == (False, False)
        for table_name in private_tables:
            cursor.execute(f"GRANT SELECT ON public.{table_name} TO anon,authenticated")
        for role, user in (("anon", None), ("authenticated", owner), ("authenticated", driver)):
            with _role(cursor, user, role=role):
                for table_name in private_tables:
                    cursor.execute(f"SELECT count(*) FROM public.{table_name}")
                    assert cursor.fetchone()[0] == 0
        with _role(cursor, role="service_role"):
            cursor.execute("SELECT driver_cnic FROM public.vehicles WHERE id=%s", (vehicle_id,))
            assert cursor.fetchone() == ("private-driver-cnic",)
            cursor.execute("SELECT total_amount FROM public.driver_fuel_logs WHERE id=%s", (log_id,))
            assert cursor.fetchone()[0] == 2800


def test_chat_insert_checks_membership_even_after_accidental_insert_grant(database):
    with database.cursor() as cursor:
        client, transporter, stranger = _user(cursor), _user(cursor, "transporter"), _user(cursor)
        cursor.execute("INSERT INTO public.chat_threads(client_user_id,transporter_user_id) VALUES(%s,%s) RETURNING id",
                       (client["id"], transporter["id"]))
        thread_id = cursor.fetchone()[0]
        with _role(cursor, stranger):
            _rejected(cursor, "INSERT INTO public.chat_messages(thread_id,sender_user_id,content) VALUES(%s,%s,'x')",
                      (thread_id, stranger["id"]))
        cursor.execute("GRANT INSERT ON public.chat_messages TO authenticated")
        with _role(cursor, stranger):
            _rejected(cursor, "INSERT INTO public.chat_messages(thread_id,sender_user_id,content) VALUES(%s,%s,'x')",
                      (thread_id, stranger["id"]))
        with _role(cursor, client):
            cursor.execute("INSERT INTO public.chat_messages(thread_id,sender_user_id,content) VALUES(%s,%s,'allowed')",
                           (thread_id, client["id"]))


def test_hire_contract_runtime_columns_and_one_active_contract(database):
    with database.cursor() as cursor:
        driver, owner = _user(cursor, "driver"), _user(cursor, "transporter")
        cursor.execute("INSERT INTO public.driver_profiles(user_id,unique_driver_id,license_number) VALUES(%s,%s,'AUDIT')",
                       (driver["id"], f"DRV-{uuid4().hex[:20]}"))
        query = "INSERT INTO public.driver_hire_contracts(driver_user_id,transporter_user_id,monthly_salary,contract_months,terms,status,accepted_at) VALUES(%s,%s,30000,12,'Audit','active',now())"
        cursor.execute(query, (driver["id"], owner["id"]))
        _rejected(cursor, query, (driver["id"], owner["id"]), codes=("23505",))
        _rejected(cursor, "INSERT INTO public.driver_hire_contracts(driver_user_id,transporter_user_id,monthly_salary,contract_months) VALUES(%s,%s,-1,12)",
                  (driver["id"], owner["id"]), codes=("23514",))


def test_existing_administrator_survives_forward_migration():
    snapshot = LEGACY_SCHEMA.read_text(encoding="utf-8")
    baseline = snapshot.split(FEATURE_MARKER, 1)[0]
    features = [_without_transaction_wrapper(p.read_text(encoding="utf-8")) for p in FEATURE_PATHS]
    url, cleanup = make_disposable(_local_url(), STUBS, DEFAULT_GRANTS, baseline, *features)
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                administrator = _user(cursor, "platform_admin")
                assert administrator["role"] == "admin"
                for migration in MIGRATION_PATHS:
                    cursor.execute(migration.read_text(encoding="utf-8"))
                cursor.execute("SELECT role,legacy_role,auth_id::text FROM public.users WHERE id=%s",
                               (administrator["id"],))
                assert cursor.fetchone() == ("admin", "platform_admin", administrator["auth_id"])
                with _role(cursor, administrator):
                    cursor.execute("SELECT public.is_admin()")
                    assert cursor.fetchone() == (True,)
    finally:
        conn.close()
        cleanup()


def test_canonical_schema_keeps_active_authorization_baseline_without_retired_domain():
    snapshot = SCHEMA_SQL.read_text(encoding="utf-8")
    assert FEATURE_MARKER in snapshot
    assert "database_authorization_hardening.sql" in snapshot
    for retired_name in (
        "agreement_posts",
        "agreement_bids",
        "agreement_trips",
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
    ):
        assert retired_name not in snapshot


def test_manual_remote_hire_shape_converges_without_losing_offer_history():
    snapshot = LEGACY_SCHEMA.read_text(encoding="utf-8")
    baseline = snapshot.split(FEATURE_MARKER, 1)[0]
    features = [_without_transaction_wrapper(p.read_text(encoding="utf-8")) for p in FEATURE_PATHS]
    old_hire = """
    CREATE TABLE public.driver_hire_contracts(
        id bigserial PRIMARY KEY,
        driver_user_id bigint NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        transporter_user_id bigint NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        monthly_salary numeric(12,2) NOT NULL,
        contract_months integer DEFAULT 12,
        terms text,
        status varchar(32) NOT NULL DEFAULT 'offered',
        offered_at timestamptz DEFAULT now(),
        accepted_at timestamptz,
        terminated_at timestamptz
    );
    """
    url, cleanup = make_disposable(_local_url(), STUBS, DEFAULT_GRANTS, baseline, *features, old_hire)
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                driver, owner = _user(cursor, "driver"), _user(cursor, "transporter")
                cursor.execute("INSERT INTO public.driver_profiles(user_id,unique_driver_id,license_number) VALUES(%s,%s,'AUDIT')",
                               (driver["id"], f"DRV-{uuid4().hex[:20]}"))
                cursor.execute("INSERT INTO public.driver_hire_contracts(driver_user_id,transporter_user_id,monthly_salary,terms,offered_at) "
                               "VALUES(%s,%s,30000,'Preserved terms',now()-interval '2 days') RETURNING id,offered_at",
                               (driver["id"], owner["id"]))
                contract_id, offered_at = cursor.fetchone()
                for _ in range(2):
                    for migration in MIGRATION_PATHS:
                        cursor.execute(migration.read_text(encoding="utf-8"))
                cursor.execute("SELECT terms,created_at,offered_at,status FROM public.driver_hire_contracts WHERE id=%s",
                               (contract_id,))
                assert cursor.fetchone() == ("Preserved terms", offered_at, offered_at, "offered")
    finally:
        conn.close()
        cleanup()


def test_legacy_wallet_violation_blocks_validation_without_rewriting_money():
    snapshot = LEGACY_SCHEMA.read_text(encoding="utf-8")
    baseline = snapshot.split(FEATURE_MARKER, 1)[0]
    features = [_without_transaction_wrapper(p.read_text(encoding="utf-8")) for p in FEATURE_PATHS]
    url, cleanup = make_disposable(_local_url(), STUBS, DEFAULT_GRANTS, baseline, *features)
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                buyer = _user(cursor)
                cursor.execute("INSERT INTO public.wallets(user_id,role,balance,locked_balance) "
                               "VALUES(%s,'client',100,101)", (buyer["id"],))
                validation = next(p for p in MIGRATION_PATHS if p.name == "20261024040000_validate_wallet_money_invariants.sql")
                for migration in MIGRATION_PATHS:
                    if migration == validation:
                        break
                    cursor.execute(migration.read_text(encoding="utf-8"))
                _rejected(cursor, validation.read_text(encoding="utf-8"), codes=("23514",))
                cursor.execute("SELECT balance,locked_balance FROM public.wallets WHERE user_id=%s", (buyer["id"],))
                assert cursor.fetchone() == (100, 101)
                cursor.execute("SELECT convalidated FROM pg_constraint WHERE conrelid='public.wallets'::regclass "
                               "AND conname='wallets_money_invariants'")
                assert cursor.fetchone() == (False,)
    finally:
        conn.close()
        cleanup()
