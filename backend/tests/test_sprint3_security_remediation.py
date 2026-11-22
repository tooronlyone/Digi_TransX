"""Sprint 3 Security Remediation regression tests (V1-SEC-007, 008, 012, 014)."""

import base64
import json
from pathlib import Path
import smtplib
import ssl
from urllib.parse import urlsplit
from uuid import uuid4

from flask import Flask
import httpx
import psycopg2
from psycopg2 import errors
from psycopg2.extras import Json
import pytest

from auth import helpers as auth_helpers
from auth.security_config import (
    FlaskSecurityConfigurationError,
    configure_flask_security,
    validate_production_security_config,
)
import scheduler as scheduler_mod
from shared.db import is_loopback_postgres_target, normalize_postgres_dsn
from shared.supabase_client import (
    SUPABASE_HTTP_TIMEOUT,
    _client_options,
    validate_supabase_url,
)
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.test_database_authorization_hardening import DEFAULT_GRANTS


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
CANONICAL_EVENT_LOCKED_FUNCTIONS = {
    "is_bounded_event_json",
    "prevent_canonical_event_update",
    "enforce_canonical_event_contract",
}
EXPECTED_TRIGGER_PRIVATE_FUNCTIONS = {
    "enforce_single_client_profile",
    "prevent_version_mutation",
    "set_updated_at",
    "log_shipment_status_change",
    "handle_new_auth_user",
    "prevent_canonical_event_update",
    "enforce_canonical_event_contract",
    "validate_driver_reputation_provenance",
    "sync_driver_allocation_with_trip",
    "reject_financial_record_mutation",
    "guard_journal_line_insert",
    "validate_financial_journal_balance",
    "preserve_bid_market_audit",
    "protect_versioned_booking_terms",
    "guard_payment_financial_invariants",
    "protect_approved_reserve_reference",
    "validate_settlement_resolution_integrity",
    "protect_business_financial_history",
    "guard_operational_incident_history",
    "guard_business_wallet_transaction",
    "guard_withdrawal_request_lifecycle",
    "guard_security_reserve_balance",
    "reconcile_security_reserve_backing",
}
RLS_HELPER_FUNCTIONS = {
    "current_app_user_id",
    "current_app_role",
    "is_admin",
    "is_transporter_assigned_to_shipment",
}


def _local_url():
    url = require_test_db_url()
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Sprint 3 DB tests require isolated loopback TEST_SUPABASE_DB_URL")
    return url


def _valid_production_env(**overrides):
    pepper = base64.urlsafe_b64encode(b"S" * 32).decode("ascii")
    env = {
        "DIGITRANSX_ENVIRONMENT": "staging",
        "FLASK_SECRET_KEY": "staging-strong-secret-key-minimum-32-chars",
        "DIGITRANSX_MPIN_PEPPER": pepper,
        "DIGITRANSX_DELIVERY_OTP_SECRET": "staging-delivery-otp-hmac-secret-32chars",
        "DIGITRANSX_API_DB_URL": "postgresql://dtx_api_runtime.ref:secret@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require",
        "SUPABASE_URL": "https://example-project.supabase.co",
        "FLASK_DEBUG": "false",
        "DIGITRANSX_ALLOW_DUMMY_PAYMENTS": "false",
        "DIGITRANSX_TRUST_PROXY_COUNT": "1",
    }
    env.update(overrides)
    return env


@pytest.fixture(scope="module", params=["fresh_schema", "fresh_baseline"])
def hardened_db_url(request):
    if request.param == "fresh_schema":
        blocks = [STUBS, DEFAULT_GRANTS, SCHEMA_SQL.read_text(encoding="utf-8")]
    else:
        migration_sqls = [
            p.read_text(encoding="utf-8")
            for p in sorted(MIGRATIONS_DIR.glob("*.sql"))
        ]
        blocks = [STUBS, DEFAULT_GRANTS, *migration_sqls]
    url, cleanup = make_disposable(_local_url(), *blocks)
    try:
        yield url
    finally:
        cleanup()


def test_sec012_all_public_functions_have_safe_search_path_and_locked_acls(hardened_db_url):
    with psycopg2.connect(hardened_db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                p.proname,
                p.prosecdef,
                p.proconfig,
                has_function_privilege('public', p.oid, 'EXECUTE') AS pub_exec,
                has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_exec,
                has_function_privilege('authenticated', p.oid, 'EXECUTE') AS auth_exec
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND NOT EXISTS (
                  SELECT 1 FROM pg_depend d
                  WHERE d.objid = p.oid AND d.deptype = 'e'
              )
            ORDER BY p.proname
            """
        )
        rows = cur.fetchall()
        assert rows
        by_name = {}
        for name, prosecdef, proconfig, pub_exec, anon_exec, auth_exec in rows:
            by_name[name] = {
                "prosecdef": prosecdef,
                "proconfig": list(proconfig or []),
                "pub_exec": pub_exec,
                "anon_exec": anon_exec,
                "auth_exec": auth_exec,
            }
            assert any(item.startswith("search_path=pg_catalog") for item in (proconfig or [])), (
                f"{name} missing pg_catalog-first search_path: {proconfig}"
            )
            if name not in CANONICAL_EVENT_LOCKED_FUNCTIONS:
                assert list(proconfig or []) == ["search_path=pg_catalog"], (
                    f"{name} must restrict search_path solely to pg_catalog: {proconfig}"
                )

        for fn in EXPECTED_TRIGGER_PRIVATE_FUNCTIONS:
            info = by_name[fn]
            assert info["pub_exec"] is False, f"{fn} must revoke PUBLIC execute"
            assert info["anon_exec"] is False, f"{fn} must revoke anon execute"
            assert info["auth_exec"] is False, f"{fn} must revoke authenticated execute"

        for fn in RLS_HELPER_FUNCTIONS:
            info = by_name[fn]
            assert info["prosecdef"] is True, f"{fn} must remain SECURITY DEFINER"
            assert info["pub_exec"] is False, f"{fn} must revoke PUBLIC execute"


def test_sec012_temp_table_and_search_path_shadowing_cannot_escalate(hardened_db_url):
    conn = psycopg2.connect(hardened_db_url)
    try:
        with conn.cursor() as cur:
            auth_id = str(uuid4())
            cur.execute(
                "INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,%s)",
                (auth_id, f"{auth_id}@example.test", Json({"legacy_role": "service_seeker"})),
            )
            cur.execute("SELECT id FROM public.users WHERE auth_id=%s", (auth_id,))
            real_user_id = cur.fetchone()[0]

            # Switch to authenticated caller and create malicious pg_temp objects.
            cur.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (auth_id,))
            cur.execute("SET LOCAL ROLE authenticated")
            cur.execute("SET LOCAL search_path = pg_temp, public")
            cur.execute("CREATE TEMP TABLE users(id bigint, role public.app_role, auth_id uuid)")
            cur.execute("INSERT INTO pg_temp.users VALUES (999999, 'admin', %s)", (auth_id,))

            # SECURITY DEFINER RLS helpers ignore pg_temp shadowing completely.
            cur.execute("SELECT public.current_app_user_id(), public.current_app_role(), public.is_admin()")
            assert cur.fetchone() == (real_user_id, "customer", False)

            # Authenticated role cannot invoke private/trigger SECURITY DEFINER functions directly.
            for fn_call in (
                "SELECT public.handle_new_auth_user()",
                "SELECT public.log_shipment_status_change()",
                "SELECT public.enforce_single_client_profile()",
                "SELECT public.set_updated_at()",
            ):
                cur.execute("SAVEPOINT sp_priv")
                with pytest.raises(errors.InsufficientPrivilege):
                    cur.execute(fn_call)
                cur.execute("ROLLBACK TO SAVEPOINT sp_priv")
                cur.execute("RELEASE SAVEPOINT sp_priv")
    finally:
        conn.rollback()
        conn.close()


def test_sec008_postgres_tls_enforcement_and_local_compatibility(tmp_path):
    assert is_loopback_postgres_target("postgresql://postgres@127.0.0.1:5432/dtx_phase1b2c0_test")
    assert is_loopback_postgres_target("postgresql://postgres@localhost:5432/postgres")
    assert is_loopback_postgres_target("postgresql://postgres@[::1]:5432/postgres")
    assert not is_loopback_postgres_target(
        "postgresql://postgres:secret@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    )

    local_dsn = "postgresql://postgres@127.0.0.1:5432/dtx_phase1b2c0_test"
    assert normalize_postgres_dsn(local_dsn) == local_dsn

    remote_dsn = "postgresql://postgres:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    assert "sslmode=require" in normalize_postgres_dsn(remote_dsn, environ={})

    ca_file = tmp_path / "supabase-ca.pem"
    ca_file.write_text("dummy-pem", encoding="utf-8")
    verified_dsn = normalize_postgres_dsn(
        remote_dsn, environ={"DIGITRANSX_DB_SSLROOTCERT": str(ca_file)}
    )
    assert "sslmode=verify-full" in verified_dsn
    assert "sslrootcert=" in verified_dsn

    certifi_dsn = normalize_postgres_dsn(
        remote_dsn, environ={"DIGITRANSX_DB_SSLROOTCERT": "certifi"}
    )
    assert "sslmode=verify-full" in certifi_dsn

    for bad_mode in ("disable", "allow", "prefer"):
        with pytest.raises(RuntimeError):
            normalize_postgres_dsn(f"{remote_dsn}?sslmode={bad_mode}", environ={})
        with pytest.raises(RuntimeError):
            normalize_postgres_dsn(remote_dsn, environ={"PGSSLMODE": bad_mode})


def test_sec008_external_http_and_smtp_tls_and_timeout_controls(monkeypatch):
    opts = _client_options()
    client = opts.httpx_client
    assert isinstance(client, httpx.Client)
    assert client.timeout == SUPABASE_HTTP_TIMEOUT
    assert client.timeout.connect == 5.0
    assert client.timeout.read == 15.0
    assert client.trust_env is False

    assert validate_supabase_url("https://abc.supabase.co").startswith("https://")
    assert validate_supabase_url("http://127.0.0.1:54321").startswith("http://127.0.0.1")
    with pytest.raises(RuntimeError):
        validate_supabase_url("http://abc.supabase.co")

    captured = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            captured["init"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            captured["ehlo"] = captured.get("ehlo", 0) + 1

        def starttls(self, context=None):
            captured["ssl_context"] = context

        def login(self, user, pwd):
            captured["login"] = (user, pwd)

        def send_message(self, msg):
            captured["to"] = msg["To"]

    monkeypatch.setenv("DIGITRANSX_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("DIGITRANSX_SMTP_PORT", "587")
    monkeypatch.setenv("DIGITRANSX_SMTP_USER", "mailer@example.test")
    monkeypatch.setenv("DIGITRANSX_SMTP_PASSWORD", "app-secret")
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    auth_helpers.send_email("Subject", "user@example.test", ["Line 1"])
    assert captured["init"] == ("smtp.example.test", 587, 30)
    assert isinstance(captured["ssl_context"], ssl.SSLContext)
    assert captured["ssl_context"].check_hostname is True
    assert captured["ssl_context"].verify_mode == ssl.CERT_REQUIRED


def test_task5_production_config_validation_fails_closed_and_debug_defaults_off(monkeypatch):
    app_source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    assert 'os.environ.get("FLASK_DEBUG", "true")' not in app_source
    assert 'env_flag("FLASK_DEBUG", default=False)' in app_source

    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "FLASK_DEBUG=false" in env_example
    assert "DIGITRANSX_TRUST_PROXY_COUNT=0" in env_example
    assert "?sslmode=require" in env_example
    assert "FUEL_VOUCHER" not in env_example

    app = Flask(__name__)
    valid_env = _valid_production_env()
    configure_flask_security(app, valid_env)
    assert validate_production_security_config(app, valid_env) == "staging"

    for bad_overrides in (
        {"FLASK_DEBUG": "true"},
        {"DIGITRANSX_ALLOW_DUMMY_PAYMENTS": "true"},
        {"FLASK_SECRET_KEY": "change-me-to-a-long-random-string"},
        {"DIGITRANSX_MPIN_PEPPER": ""},
        {"DIGITRANSX_MPIN_PEPPER": "not-base64"},
        {"DIGITRANSX_DELIVERY_OTP_SECRET": "short"},
        {"DIGITRANSX_API_DB_URL": ""},
        {"DIGITRANSX_API_DB_URL": "postgresql://postgres.ref:pw@db.example.com:5432/postgres?sslmode=require"},
        {"DIGITRANSX_API_DB_URL": "postgresql://dtx_api_runtime:pw@db.example.com:5432/postgres?sslmode=disable"},
        {"DIGITRANSX_DB_SSLROOTCERT": str(ROOT / "nonexistent-ca.pem")},
        {"SUPABASE_URL": "http://project.supabase.co"},
        {"DIGITRANSX_TRUST_PROXY_COUNT": "-1"},
        {"DIGITRANSX_CORS_ORIGINS": "*"},
    ):
        broken_env = _valid_production_env(**bad_overrides)
        broken_app = Flask(__name__)
        if "FLASK_SECRET_KEY" not in bad_overrides:
            configure_flask_security(broken_app, broken_env)
        with pytest.raises(FlaskSecurityConfigurationError):
            validate_production_security_config(broken_app, broken_env)

    # Scheduler remains OFF by default unless explicitly enabled.
    monkeypatch.delenv("DIGITRANSX_ENABLE_SCHEDULER", raising=False)
    assert scheduler_mod.start_scheduler() is None


def test_sec014_dead_v2_and_dev_residue_removed_while_preserving_future_archives():
    for deleted in (
        ROOT / "backend" / "fuelstation",
        ROOT / "backend" / "marketplace",
        ROOT / "backend" / "shopkeeper",
        ROOT / "backend" / "uploads" / "trucks" / "2_1784526384_2.jpg",
        ROOT / "frontend-react" / "package.json.bak",
        ROOT / "frontend-react" / "package-lock.json.bak",
        ROOT / "frontend-react" / ".phase2c6-qa.html",
        ROOT / "frontend-react" / ".phase2c6-qa.jsx",
        ROOT / "frontend-react" / "vite-5175.out.log",
        ROOT / "frontend-react" / "vite-dev.out.log",
        ROOT / "frontend-react" / "vite-dev.err.log",
        ROOT / ".frontend_hardening_lint.json",
    ):
        assert not deleted.exists(), f"{deleted} should have been cleaned up"

    vite_cfg = (ROOT / "frontend-react" / "vite.config.js").read_text(encoding="utf-8")
    assert "'/ai'" not in vite_cfg

    login_jsx = (ROOT / "frontend-react" / "src" / "pages" / "auth" / "Login.jsx").read_text(encoding="utf-8")
    assert "dtx_remember_loginId" not in login_jsx

    serialized = auth_helpers.serialize_user({"id": 1, "full_name": "Ali Khan", "role": "service_seeker"})
    assert "shop_name" not in serialized
    assert "station_name" not in serialized

    assert (ROOT / "Future" / "README.md").exists()
    assert (ROOT / "backend" / "requirements.lock").exists()
    assert (ROOT / ".github" / "workflows" / "security-checks.yml").exists()
