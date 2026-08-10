"""Real PostgreSQL proof for bounded Phase 1B-2B signup event integration."""

import json
import os
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from flask import Flask
import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor
import pytest
from supabase_auth.errors import AuthApiError, AuthRetryableError

import auth.helpers as auth_helpers
import auth.routes as auth_routes
from events.catalog import CATALOG, INTEGRATED_EVENT_NAMES
from events.contract import EventContext, EventData
from events.writer import EventIdempotencyConflict, write_security_event
from shared.db import Db
import shared.supabase_client as supabase_client
from shared.supabase_client import SignupProviderConflict, SignupProviderUnavailable
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url, schema_before_migration_or_skip
from tests.test_canonical_event_acl_hardening import _semantic_signature
from tests.test_canonical_event_foundation import _direct_insert


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260801130000_security_signup_event_integration.sql"
PRE_SIGNATURE = "993b1de965a1791a2a84ccff5fcfbdf9"
POST_SIGNATURE = "371c7010a0553c7953708dea164ed0bc"
INTEGRATED = {
    "security.login.started", "security.login.failed", "security.login.succeeded",
    "security.logout.completed", "security.signup.started", "security.signup.failed",
    "security.signup.completed",
    "security.trusted_device.added", "security.trusted_device.removed",
    "security.trusted_device.rotated",
    "security.session.issued", "security.session.revoked",
    "security.session.access_locked",
    "security.mpin.enrolled", "security.mpin.changed", "security.mpin.disabled",
    "security.mpin.unlock_succeeded", "security.mpin.unlock_failed",
    "security.mpin.locked", "security.mpin.reset_completed",
}
HISTORICAL_SIGNUP_INTEGRATED = {
    "security.login.started", "security.login.failed", "security.login.succeeded",
    "security.logout.completed", "security.signup.started", "security.signup.failed",
    "security.signup.completed",
}


def _local_url():
    url = require_test_db_url()
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert parsed.path.lstrip("/").startswith("dtx_phase1b2c0_")
    assert url != os.environ.get("SUPABASE_DB_URL", "")
    return url


def _signup_integration_final_schema():
    return subprocess.check_output(
        ["git", "show", "9944bd5fa6c8acbe790e55c39edc8b3b951c6ef8:supabase/schema.sql"],
        cwd=REPO_ROOT,
        text=True,
    )


@pytest.fixture(scope="module")
def signup_database_url():
    url, cleanup = make_disposable(_local_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def signup_client(signup_database_url, monkeypatch):
    @contextmanager
    def test_open_db():
        conn = psycopg2.connect(signup_database_url)
        try:
            yield Db(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(auth_helpers, "open_db", test_open_db)
    monkeypatch.setattr(auth_routes, "open_db", test_open_db)
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    app = Flask(__name__)
    app.config.update(SECRET_KEY="phase1b2b-test", SESSION_COOKIE_SECURE=False)
    app.register_blueprint(auth_routes.auth_blueprint)
    client = app.test_client()
    yield client, signup_database_url
    conn = psycopg2.connect(signup_database_url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("truncate public.security_events, public.business_audit_events, public.login_activity, public.trusted_devices, public.users, auth.users restart identity cascade")
    finally:
        conn.close()


def _provider(url):
    def create(email, _password, metadata):
        auth_id = str(uuid.uuid4())
        conn = psycopg2.connect(url)
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "insert into auth.users (id, email, raw_user_meta_data) values (%s, %s, %s::jsonb)",
                        (auth_id, email, json.dumps(metadata)),
                    )
        finally:
            conn.close()
        return SimpleNamespace(id=auth_id)
    return create


def _payload(role="service_seeker", **changes):
    data = {
        "name": "Signup Test", "email": "signup@example.invalid", "phone": "3001234567",
        "cnic": "3520212345678", "password": "safe-password-123", "role": role,
        "city": "Lahore", "company_name": "Bounded Co", "business_type": "Retail",
    }
    data.update(changes)
    return data


def _rows(url, table, columns="*"):
    conn = psycopg2.connect(url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"select {columns} from public.{table} order by 1")
            return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _events(url):
    return _rows(url, "security_events", "event_name, request_id, actor_type, actor_id, actor_role, subject_user_id, metadata")


def test_successful_signup_commits_public_evidence_before_session(signup_client, monkeypatch):
    client, url = signup_client
    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", _provider(url))
    response = client.post("/auth/signup", json=_payload())
    assert response.status_code == 200
    assert set(response.get_json()) == {"success", "user", "csrf_token", "redirect", "session"}
    events = _events(url)
    assert {row["event_name"] for row in events} == {
        "security.signup.started", "security.signup.completed",
        "security.trusted_device.added", "security.session.issued",
        "security.session.issued",
    }
    assert len({row["request_id"] for row in events}) == 1
    started = next(row for row in events if row["event_name"] == "security.signup.started")
    completed = next(row for row in events if row["event_name"] == "security.signup.completed")
    assert started["actor_type"] == "anonymous"
    assert all(started[key] is None for key in ("actor_id", "actor_role", "subject_user_id"))
    assert completed["actor_type"] == "user" and completed["actor_id"] == completed["subject_user_id"]
    assert completed["metadata"] == {"result_code": "completed"}
    assert len(_rows(url, "users")) == len(_rows(url, "service_seeker_profiles")) == 1
    assert not _rows(url, "everyday_user_profiles")
    assert len(_rows(url, "login_activity")) == len(_rows(url, "trusted_devices")) == 1
    assert "dtx_device_token=" in response.headers.get("Set-Cookie", "")
    assert "dtx_session_token=" in "\n".join(response.headers.getlist("Set-Cookie"))
    proof = next(
        value for value in response.headers.getlist("Set-Cookie")
        if value.startswith("dtx_access_proof=")
    )
    assert "HttpOnly" in proof and "Max-Age" not in proof and "Expires" not in proof


def test_validation_and_provider_conflict_are_anonymous_terminal_denials(signup_client, monkeypatch):
    client, url = signup_client
    called = []
    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", lambda *_args: called.append(True))
    validation = client.post("/auth/signup", json=_payload(email="not-an-email"))
    assert validation.status_code == 400 and not called
    assert {row["event_name"] for row in _events(url)} == {"security.signup.started", "security.signup.failed"}
    assert next(row for row in _events(url) if row["event_name"] == "security.signup.failed")["metadata"] == {"result_code": "validation_failed"}
    # Fixture cleanup occurs per test; this separate request verifies structured conflict handling.
    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", lambda *_args: (_ for _ in ()).throw(SignupProviderConflict()))
    conflict = client.post("/auth/signup", json=_payload())
    assert conflict.status_code == 409
    assert conflict.get_json()["message"] == "Unable to complete signup."
    assert "example.invalid" not in conflict.get_data(as_text=True)


def test_started_or_failed_evidence_write_failure_never_calls_provider_or_issues_session(signup_client, monkeypatch):
    client, _url = signup_client
    called = []
    monkeypatch.setattr(auth_routes, "_record_signup_started", lambda *_args: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", lambda *_args: called.append(True))
    assert client.post("/auth/signup", json=_payload()).status_code == 503
    assert not called
    monkeypatch.setattr(auth_routes, "_record_signup_started", lambda *_args: None)
    monkeypatch.setattr(auth_routes, "_record_signup_failed", lambda *_args: False)
    denied = client.post("/auth/signup", json=_payload(email="not-an-email"))
    assert denied.status_code == 503 and denied.get_json()["success"] is False
    with client.session_transaction() as state:
        assert "user_id" not in state


@pytest.mark.parametrize(
    ("role", "profile_table", "extra"),
    (
        ("service_seeker", "service_seeker_profiles", {"company_name": "One", "business_type": "Retail"}),
        ("everyday_user", "everyday_user_profiles", {}),
        ("logistics_provider", "transporter_profiles", {}),
        ("fuel_station_manager", "fuel_station_profiles", {"station_name": "Station"}),
        ("shopkeeper", "shopkeeper_profiles", {"shop_name": "Shop"}),
    ),
)
def test_each_supported_signup_role_creates_only_its_server_selected_profile(signup_client, monkeypatch, role, profile_table, extra):
    client, url = signup_client
    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", _provider(url))
    suffix = role[:4]
    response = client.post("/auth/signup", json=_payload(role, email=f"{suffix}@example.invalid", cnic="3520212345679", **extra))
    assert response.status_code == 200
    assert len(_rows(url, profile_table)) == 1
    assert len(_rows(url, "users")) == 1
    assert {row["event_name"] for row in _events(url)} == {
        "security.signup.started", "security.signup.completed",
        "security.trusted_device.added", "security.session.issued",
    }


def test_provider_and_public_persistence_failures_fail_closed(signup_client, monkeypatch):
    client, url = signup_client
    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", lambda *_args: (_ for _ in ()).throw(SignupProviderUnavailable()))
    outage = client.post("/auth/signup", json=_payload())
    assert outage.status_code == 503 and "provider" not in outage.get_data(as_text=True).lower()
    assert next(row for row in _events(url) if row["event_name"] == "security.signup.failed")["metadata"] == {"result_code": "provider_unavailable"}

    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", _provider(url))
    monkeypatch.setattr(auth_routes, "_write_signup_profile", lambda *_args: (_ for _ in ()).throw(RuntimeError("db secret")))
    monkeypatch.setattr(auth_routes, "supabase_signup_identity_is_owned", lambda *_args: True)
    monkeypatch.setattr(auth_routes, "supabase_delete_created_signup_user", lambda *_args: True)
    failed = client.post("/auth/signup", json=_payload(email="persistence@example.invalid", cnic="3520212345679"))
    assert failed.status_code == 503
    assert {tuple(row["metadata"].items()) for row in _events(url) if row["event_name"] == "security.signup.failed"} == {
        (("result_code", "provider_unavailable"),), (("result_code", "persistence_failed"),)
    }
    assert not _rows(url, "users") and not _rows(url, "trusted_devices")


def test_trusted_device_failure_and_unproven_compensation_never_issue_a_session(signup_client, monkeypatch):
    client, url = signup_client
    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", _provider(url))
    monkeypatch.setattr(auth_routes, "establish_after_full_login", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("device failure")))
    monkeypatch.setattr(auth_routes, "supabase_signup_identity_is_owned", lambda *_args: False)
    response = client.post("/auth/signup", json=_payload())
    assert response.status_code == 503
    assert response.get_json()["success"] is False
    assert next(row for row in _events(url) if row["event_name"] == "security.signup.failed")["metadata"] == {"result_code": "reconciliation_required"}
    assert not any(row["event_name"] == "security.signup.completed" for row in _events(url))
    with client.session_transaction() as state:
        assert "user_id" not in state and "csrf_token" not in state


def test_terminal_idempotency_and_direct_sql_activation_matrix(signup_database_url, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    conn = psycopg2.connect(signup_database_url)
    try:
        with conn:
            with conn.cursor() as cursor:
                context = EventContext(request_id="signup.replay", source="server_route", actor_type="anonymous")
                db = Db(conn)
                write_security_event(db, "security.signup.started", context, EventData(), idempotency_scope="security.signup.started", idempotency_key="signup.replay")
                write_security_event(db, "security.signup.started", context, EventData(), idempotency_scope="security.signup.started", idempotency_key="signup.replay")
                write_security_event(db, "security.signup.failed", context, EventData(metadata={"result_code": "validation_failed"}), idempotency_scope="security.signup.terminal", idempotency_key="signup.replay")
                with pytest.raises(EventIdempotencyConflict):
                    write_security_event(db, "security.signup.failed", context, EventData(metadata={"result_code": "account_conflict"}), idempotency_scope="security.signup.terminal", idempotency_key="signup.replay")
                cursor.execute("set local role service_role")
                for name in ("security.signup.started", "security.signup.failed", "security.signup.completed"):
                    _direct_insert(cursor, "security_events", event_name=name, event_version=1, category="security", retention_class="security_12_months", request_id="direct." + name)
                for name, category, retention in (
                    ("security.signup.gps_result_recorded", "security", "security_12_months"),
                    ("security.signup.email_otp_sent", "security", "security_12_months"),
                    ("system.job.started", "operations", "operations_90_days"),
                    ("one_time.qr_payment.intent_created", "business_audit", "financial_7_years"),
                ):
                    cursor.execute("savepoint rejected_event")
                    with pytest.raises((errors.CheckViolation, errors.RaiseException)):
                        _direct_insert(cursor, "security_events", event_name=name, event_version=1, category=category, retention_class=retention, request_id="reject." + name)
                    cursor.execute("rollback to savepoint rejected_event")
                cursor.execute("reset role")
    finally:
        conn.close()


def test_signup_integration_migration_is_exact_idempotent_and_converges():
    migration = MIGRATION.read_text(encoding="utf-8")
    observed = []
    for blocks, expected, apply in (
        ((STUBS, schema_before_migration_or_skip(MIGRATION)), PRE_SIGNATURE, True),
        ((STUBS, _signup_integration_final_schema()), POST_SIGNATURE, False),
    ):
        url, cleanup = make_disposable(_local_url(), *blocks)
        try:
            conn = psycopg2.connect(url)
            try:
                assert _semantic_signature(conn) == expected
                if apply:
                    with conn.cursor() as cursor:
                        cursor.execute(migration)
                    conn.commit()
                for _ in range(2):
                    with conn.cursor() as cursor:
                        cursor.execute(migration)
                    conn.commit()
                with conn.cursor() as cursor:
                    cursor.execute("select event_name from public.canonical_event_catalog_projection where integrated order by event_name")
                    observed.append((_semantic_signature(conn), {row[0] for row in cursor.fetchall()}))
            finally:
                conn.close()
        finally:
            cleanup()
    assert observed == [
        (POST_SIGNATURE, HISTORICAL_SIGNUP_INTEGRATED),
        (POST_SIGNATURE, HISTORICAL_SIGNUP_INTEGRATED),
    ]


def test_signup_integration_migration_aborts_partial_state_without_repair():
    url, cleanup = make_disposable(_local_url(), STUBS, schema_before_migration_or_skip(MIGRATION))
    try:
        conn = psycopg2.connect(url)
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute("update public.canonical_event_catalog_projection set integrated=true where event_name='security.signup.started'")
            before = _semantic_signature(conn)
            with pytest.raises((psycopg2.Error, errors.RaiseException)):
                with conn.cursor() as cursor:
                    cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            conn.rollback()
            assert _semantic_signature(conn) == before
        finally:
            conn.close()
    finally:
        cleanup()


def test_signup_catalog_totals_and_contracts_are_locked():
    assert {name for name, definition in CATALOG.items() if definition.integrated} == INTEGRATED
    assert len(CATALOG) == 170
    assert sum(definition.lifecycle_status == "planned" for definition in CATALOG.values()) == 162
    assert sum(definition.lifecycle_status == "deferred" for definition in CATALOG.values()) == 8
    assert sum(definition.writable for definition in CATALOG.values()) == 156
    assert sum(definition.integrated for definition in CATALOG.values()) == 20
    assert sum(definition.lifecycle_status == "planned" and not definition.integrated for definition in CATALOG.values()) == 142
    assert sum(definition.writable and not definition.integrated for definition in CATALOG.values()) == 136


def test_signup_provider_classification_uses_only_structured_status_and_code(monkeypatch):
    monkeypatch.setattr(
        supabase_client, "supabase_create_user",
        lambda *_args: (_ for _ in ()).throw(AuthApiError("private provider text", 409, "user_already_exists")),
    )
    with pytest.raises(SignupProviderConflict):
        supabase_client.supabase_create_signup_user("person@example.invalid", "password", {})
    monkeypatch.setattr(
        supabase_client, "supabase_create_user",
        lambda *_args: (_ for _ in ()).throw(AuthApiError("private provider text", 503, "unexpected_failure")),
    )
    with pytest.raises(SignupProviderUnavailable):
        supabase_client.supabase_create_signup_user("person@example.invalid", "password", {})
    monkeypatch.setattr(
        supabase_client, "supabase_create_user",
        lambda *_args: (_ for _ in ()).throw(AuthRetryableError("private provider text", 503)),
    )
    with pytest.raises(SignupProviderUnavailable):
        supabase_client.supabase_create_signup_user("person@example.invalid", "password", {})
