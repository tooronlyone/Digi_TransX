"""Real PostgreSQL proof for the bounded Phase 1B-2A auth integration."""

import os
from contextlib import contextmanager
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

from flask import Flask
import psycopg2
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
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.test_canonical_event_acl_hardening import _semantic_signature


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVATION_MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260801100000_security_login_event_integration.sql"
)
EXPECTED_BASE_DATABASE_PREFIX = "dtx_phase1b2c0_"
EXPECTED_PRIOR_SIGNATURE = "772212260b85fd6b5cd4aa35ca9ffdfb"
EXPECTED_FINAL_SIGNATURE = "f5168975e0605fe0f7b84c1276a0082a"
ACTIVATION_PRE_SCHEMA_SHA = "7282d049a1bd9e0c8543c4752b5c0980dc817a68"
EXPECTED_EVENTS = {
    "security.login.started",
    "security.login.failed",
    "security.login.succeeded",
    "security.logout.completed",
}


def _local_test_url():
    url = require_test_db_url()
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert parsed.path.lstrip("/").startswith(EXPECTED_BASE_DATABASE_PREFIX)
    assert url != os.environ.get("SUPABASE_DB_URL", "").strip()
    return url


def _activation_pre_schema():
    return subprocess.check_output(
        ["git", "show", f"{ACTIVATION_PRE_SCHEMA_SHA}:supabase/schema.sql"],
        cwd=REPO_ROOT,
    ).decode("utf-8")


@pytest.fixture(scope="module")
def auth_database_url():
    url, cleanup = make_disposable(
        _local_test_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def auth_client(auth_database_url, monkeypatch):
    @contextmanager
    def test_open_db():
        conn = psycopg2.connect(auth_database_url)
        try:
            wrapper = Db(conn)
            yield wrapper
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
    app.config.update(SECRET_KEY="phase1b2a-test", SESSION_COOKIE_SECURE=False)
    app.register_blueprint(auth_routes.auth_blueprint)
    client = app.test_client()
    yield client, auth_database_url

    conn = psycopg2.connect(auth_database_url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "truncate public.security_events, public.business_audit_events, "
                    "public.login_activity, public.trusted_devices, public.user_action_logs, "
                    "public.users restart identity cascade"
                )
    finally:
        conn.close()


def _seed_user(url, *, blocked=False, admin=False):
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.users
                        (full_name, email, phone, cnic, role, legacy_role, is_blocked)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                    (
                        "Bounded Test User",
                        "bounded@example.invalid",
                        "03000000000",
                        "0000000000000",
                        "admin" if admin else "customer",
                        "platform_admin" if admin else "service_seeker",
                        blocked,
                    ),
                )
                return cursor.fetchone()[0]
    finally:
        conn.close()


def _rows(url, table, columns="*"):
    conn = psycopg2.connect(url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"select {columns} from public.{table} order by 1")
            return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _event_rows(url):
    return _rows(
        url,
        "security_events",
        "event_name,actor_type,actor_id,actor_role,subject_user_id,request_id,"
        "session_ref,device_ref,source,provider_mode,metadata",
    )


def test_catalog_preserves_login_events_and_adds_only_bounded_signup_events():
    expected = EXPECTED_EVENTS | {
        "security.signup.started",
        "security.signup.failed",
        "security.signup.completed",
    }
    assert set(INTEGRATED_EVENT_NAMES) == expected
    assert {name for name, item in CATALOG.items() if item.integrated} == expected
    assert sum(item.integrated for item in CATALOG.values()) == 7
    assert sum(item.lifecycle_status == "planned" and not item.integrated for item in CATALOG.values()) == 155
    assert sum(item.lifecycle_status == "deferred" and not item.integrated for item in CATALOG.values()) == 8


def test_valid_password_login_emits_started_and_succeeded_atomically(auth_client, monkeypatch):
    client, url = auth_client
    user_id = _seed_user(url)
    monkeypatch.setattr(auth_routes, "supabase_verify_password", lambda *_a, **_k: True)

    response = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "valid-password"}
    )
    assert response.status_code == 200
    assert set(response.get_json()) == {"success", "user", "csrf_token", "redirect", "session"}
    events = _event_rows(url)
    assert [event["event_name"] for event in events] == [
        "security.login.started",
        "security.login.succeeded",
    ]
    assert len({event["request_id"] for event in events}) == 1
    assert events[0]["actor_type"] == "anonymous"
    assert all(events[0][key] is None for key in ("actor_id", "actor_role", "subject_user_id"))
    assert events[1]["actor_type"] == "user"
    assert events[1]["actor_id"] == events[1]["subject_user_id"] == user_id
    assert events[1]["actor_role"] == "service_seeker"
    assert all(event["source"] == "server_route" and event["provider_mode"] == "none" for event in events)
    assert all(event["session_ref"] is None and event["device_ref"] is None for event in events)
    activity = _rows(url, "login_activity")
    assert len(activity) == 1 and activity[0]["status"] == "success"
    devices = _rows(url, "trusted_devices")
    assert len(devices) == 1 and devices[0]["user_id"] == user_id
    users = _rows(url, "users")
    assert users[0]["last_login_at"] is not None
    assert _rows(url, "business_audit_events") == []
    assert _rows(url, "user_action_logs") == []


def test_login_started_is_committed_before_provider_verification(auth_client, monkeypatch):
    client, url = auth_client
    _seed_user(url)
    observed = []

    def verify(*_args, **_kwargs):
        events = _event_rows(url)
        observed.append([event["event_name"] for event in events])
        assert _rows(url, "login_activity") == []
        assert _rows(url, "trusted_devices") == []
        assert _rows(url, "users")[0]["last_login_at"] is None
        return True

    monkeypatch.setattr(auth_routes, "supabase_verify_password", verify)
    response = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "valid"}
    )
    assert response.status_code == 200
    assert observed == [["security.login.started"]]


def test_login_started_failure_prevents_provider_and_session(auth_client, monkeypatch):
    client, url = auth_client
    _seed_user(url)
    provider_calls = []
    real_writer = auth_routes.write_security_event

    def fail_started(executor, event_name, *args, **kwargs):
        if event_name == "security.login.started":
            raise RuntimeError("started evidence unavailable")
        return real_writer(executor, event_name, *args, **kwargs)

    def provider(*_args, **_kwargs):
        provider_calls.append(True)
        return True

    monkeypatch.setattr(auth_routes, "write_security_event", fail_started)
    monkeypatch.setattr(auth_routes, "supabase_verify_password", provider)
    response = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "valid"}
    )
    assert response.status_code == 503
    assert provider_calls == []
    with client.session_transaction() as session:
        assert "user_id" not in session
    assert _event_rows(url) == []
    assert _rows(url, "login_activity") == []
    assert _rows(url, "trusted_devices") == []
    assert _rows(url, "users")[0]["last_login_at"] is None


def test_wrong_password_unknown_and_blocked_have_same_response_and_private_events(
    auth_client, monkeypatch
):
    client, url = auth_client
    _seed_user(url)
    monkeypatch.setattr(auth_routes, "supabase_verify_password", lambda *_a, **_k: False)
    wrong = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "wrong"}
    )
    unknown = client.post(
        "/auth/login", json={"loginId": "unknown@example.invalid", "password": "wrong"}
    )
    conn = psycopg2.connect(url)
    with conn:
        with conn.cursor() as cursor:
            cursor.execute("update users set is_blocked=true")
    conn.close()
    blocked = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "wrong"}
    )
    assert wrong.status_code == unknown.status_code == blocked.status_code == 401
    assert wrong.get_json() == unknown.get_json() == blocked.get_json() == {
        "success": False,
        "field": "password",
        "message": "Incorrect password.",
    }
    events = _event_rows(url)
    assert [event["event_name"] for event in events].count("security.login.started") == 3
    failed = [event for event in events if event["event_name"] == "security.login.failed"]
    assert len(failed) == 3
    assert [event["metadata"]["result_code"] for event in failed].count("invalid_credentials") == 2
    assert [event["metadata"]["result_code"] for event in failed].count("account_unavailable") == 1
    for event in failed:
        assert event["actor_type"] == "anonymous"
        assert all(event[key] is None for key in ("actor_id", "actor_role", "subject_user_id"))
        serialized = str(event).lower()
        assert not any(value in serialized for value in ("bounded@", "unknown@", "0300", "0000000000000", "wrong"))
    activity = _rows(url, "login_activity")
    assert len(activity) == 3 and all(row["status"] == "failed" for row in activity)
    assert _rows(url, "users")[0]["last_login_at"] is None


def test_blocked_and_provider_failure_use_only_coarse_codes(auth_client, monkeypatch, caplog):
    client, url = auth_client
    _seed_user(url, blocked=True)
    blocked = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "not-stored"}
    )
    assert blocked.status_code == 401
    blocked_event = next(
        event for event in _event_rows(url) if event["event_name"] == "security.login.failed"
    )
    assert blocked_event["metadata"] == {"result_code": "account_unavailable"}

    conn = psycopg2.connect(url)
    with conn:
        with conn.cursor() as cursor:
            cursor.execute("update users set is_blocked=false")
            cursor.execute("truncate security_events, login_activity")
    conn.close()

    def unavailable(*_args, **_kwargs):
        raise auth_routes.PasswordProviderUnavailable("raw-provider-secret")

    monkeypatch.setattr(auth_routes, "supabase_verify_password", unavailable)
    provider = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "not-stored"}
    )
    assert provider.status_code == 503
    rows = _event_rows(url)
    provider_event = next(
        event for event in rows if event["event_name"] == "security.login.failed"
    )
    assert provider_event["metadata"] == {"result_code": "provider_unavailable"}
    assert "raw-provider-secret" not in str(rows)
    assert "not-stored" not in str(rows)
    assert "raw-provider-secret" not in caplog.text


def test_installed_invalid_credentials_exception_maps_to_false_and_route_401(
    auth_client, monkeypatch
):
    client, url = auth_client
    _seed_user(url)
    provider_detail = "raw-invalid-credential-detail"

    class Auth:
        def sign_in_with_password(self, _payload):
            raise AuthApiError(provider_detail, 400, "invalid_credentials")

    class Client:
        auth = Auth()

    monkeypatch.setenv("SUPABASE_URL", "https://local-invalid.example")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "local-test-key")
    monkeypatch.setattr(supabase_client, "create_client", lambda *_a, **_k: Client())
    assert (
        supabase_client.supabase_verify_password(
            "bounded@example.invalid", "wrong", raise_provider_errors=True
        )
        is False
    )
    monkeypatch.setattr(auth_routes, "supabase_verify_password", supabase_client.supabase_verify_password)
    response = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.get_json() == {
        "success": False,
        "field": "password",
        "message": "Incorrect password.",
    }
    rows = _event_rows(url)
    failed = next(event for event in rows if event["event_name"] == "security.login.failed")
    assert failed["metadata"] == {"result_code": "invalid_credentials"}
    assert provider_detail not in str(rows)


@pytest.mark.parametrize(
    "provider_error",
    [
        AuthRetryableError("raw-network-detail", 503),
        AuthApiError("raw-provider-5xx-detail", 500, "unexpected_failure"),
        AuthApiError("raw-misclassified-5xx-detail", 500, "invalid_credentials"),
        TimeoutError("raw-timeout-detail"),
    ],
)
def test_structured_provider_failures_are_sanitized(provider_error, monkeypatch):
    class Auth:
        def sign_in_with_password(self, _payload):
            raise provider_error

    class Client:
        auth = Auth()

    monkeypatch.setenv("SUPABASE_URL", "https://local-invalid.example")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "local-test-key")
    monkeypatch.setattr(supabase_client, "create_client", lambda *_a, **_k: Client())
    assert supabase_client.supabase_verify_password("bounded@example.invalid", "wrong") is False
    with pytest.raises(supabase_client.PasswordProviderUnavailable) as caught:
        supabase_client.supabase_verify_password(
            "bounded@example.invalid", "wrong", raise_provider_errors=True
        )
    assert str(caught.value) == "Password provider unavailable."
    assert "raw-" not in str(caught.value)


def test_malformed_provider_response_is_unavailable_in_strict_mode(monkeypatch):
    class Auth:
        def sign_in_with_password(self, _payload):
            return None

    class Client:
        auth = Auth()

    monkeypatch.setenv("SUPABASE_URL", "https://local-invalid.example")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "local-test-key")
    monkeypatch.setattr(supabase_client, "create_client", lambda *_a, **_k: Client())
    with pytest.raises(supabase_client.PasswordProviderUnavailable):
        supabase_client.supabase_verify_password(
            "bounded@example.invalid", "wrong", raise_provider_errors=True
        )


def test_malformed_payload_cannot_inject_server_fields_or_sensitive_values(auth_client):
    client, url = auth_client
    response = client.post(
        "/auth/login",
        json={
            "event_name": "security.login.succeeded",
            "actor_id": 999,
            "request_id": "client-controlled",
            "csrf_token": "not-stored",
        },
    )
    assert response.status_code == 400
    events = _event_rows(url)
    assert len(events) == 1
    assert events[0]["event_name"] == "security.login.failed"
    assert events[0]["metadata"] == {"result_code": "validation_failed"}
    assert events[0]["request_id"] != "client-controlled"
    assert "not-stored" not in str(events)
    assert _rows(url, "login_activity") == []

    oversized = client.post(
        "/auth/login",
        json={
            "event_name": "security.login.succeeded",
            "metadata": {"password": "x" * 10_000},
        },
    )
    assert oversized.status_code == 400
    events = _event_rows(url)
    assert len(events) == 2
    assert all(event["event_name"] == "security.login.failed" for event in events)
    assert "x" * 128 not in str(events)


def test_success_evidence_failure_rolls_back_activity_and_last_login_and_issues_no_session(
    auth_client, monkeypatch
):
    client, url = auth_client
    _seed_user(url)
    monkeypatch.setattr(auth_routes, "supabase_verify_password", lambda *_a, **_k: True)
    real_writer = auth_routes.write_security_event

    def fail_success(executor, event_name, *args, **kwargs):
        if event_name == "security.login.succeeded":
            raise RuntimeError("database evidence unavailable")
        return real_writer(executor, event_name, *args, **kwargs)

    monkeypatch.setattr(auth_routes, "write_security_event", fail_success)
    response = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "valid"}
    )
    assert response.status_code == 503
    with client.session_transaction() as session:
        assert "user_id" not in session
    assert [event["event_name"] for event in _event_rows(url)] == ["security.login.started"]
    assert _rows(url, "login_activity") == []
    assert _rows(url, "trusted_devices") == []
    assert _rows(url, "users")[0]["last_login_at"] is None


def test_failed_authentication_stays_denied_when_terminal_evidence_fails(auth_client, monkeypatch):
    client, url = auth_client
    _seed_user(url)
    monkeypatch.setattr(auth_routes, "supabase_verify_password", lambda *_a, **_k: False)
    real_writer = auth_routes.write_security_event

    def fail_terminal(executor, event_name, *args, **kwargs):
        if event_name == "security.login.failed":
            raise RuntimeError("database evidence unavailable")
        return real_writer(executor, event_name, *args, **kwargs)

    monkeypatch.setattr(auth_routes, "write_security_event", fail_terminal)
    response = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "wrong"}
    )
    assert response.status_code == 401
    with client.session_transaction() as session:
        assert "user_id" not in session
    assert [event["event_name"] for event in _event_rows(url)] == ["security.login.started"]
    assert _rows(url, "login_activity") == []
    assert _rows(url, "trusted_devices") == []


def test_trusted_device_failure_rolls_back_terminal_success_and_issues_no_session(
    auth_client, monkeypatch
):
    client, url = auth_client
    _seed_user(url)
    monkeypatch.setattr(auth_routes, "supabase_verify_password", lambda *_a, **_k: True)
    monkeypatch.setattr(
        auth_routes,
        "upsert_trusted_device",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("device write failed")),
    )
    response = client.post(
        "/auth/login", json={"loginId": "bounded@example.invalid", "password": "valid"}
    )
    assert response.status_code == 503
    with client.session_transaction() as session:
        assert "user_id" not in session
        assert "csrf_token" not in session
    assert [event["event_name"] for event in _event_rows(url)] == ["security.login.started"]
    assert _rows(url, "login_activity") == []
    assert _rows(url, "trusted_devices") == []
    assert _rows(url, "users")[0]["last_login_at"] is None


def test_authenticated_logout_emits_once_and_clears_session(auth_client):
    client, url = auth_client
    user_id = _seed_user(url, admin=True)
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["csrf_token"] = "csrf-test"
    response = client.post("/auth/logout", headers={"X-CSRF-Token": "csrf-test"})
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "user_id" not in session
    events = _event_rows(url)
    assert len(events) == 1
    assert events[0]["event_name"] == "security.logout.completed"
    assert events[0]["actor_type"] == "admin"
    assert events[0]["actor_id"] == events[0]["subject_user_id"] == user_id
    assert events[0]["actor_role"] == "platform_admin"


def test_invalid_csrf_and_anonymous_logout_emit_no_event(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["csrf_token"] = "expected"
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert _event_rows(url) == []
    with client.session_transaction() as session:
        session.clear()
    assert client.post("/auth/logout").status_code == 200
    assert _event_rows(url) == []


def test_logout_clears_session_when_event_persistence_fails(auth_client, monkeypatch):
    client, url = auth_client
    user_id = _seed_user(url)
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["csrf_token"] = "csrf-test"
    monkeypatch.setattr(
        auth_routes,
        "write_security_event",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("not logged")),
    )
    response = client.post("/auth/logout", headers={"X-CSRF-Token": "csrf-test"})
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "user_id" not in session
    assert _event_rows(url) == []


def test_exact_auth_event_replay_is_idempotent_and_conflict_fails(auth_database_url, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    conn = psycopg2.connect(auth_database_url)
    try:
        context = EventContext(
            request_id="auth.replay00000000000000000000000001",
            source="server_route",
            actor_type="anonymous",
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            first = write_security_event(
                cursor,
                "security.login.failed",
                context,
                EventData(metadata={"result_code": "invalid_credentials"}),
                idempotency_scope="security.login.terminal",
                idempotency_key=context.request_id,
            )
            replay = write_security_event(
                cursor,
                "security.login.failed",
                context,
                EventData(metadata={"result_code": "invalid_credentials"}),
                idempotency_scope="security.login.terminal",
                idempotency_key=context.request_id,
            )
            assert first.event["event_id"] == replay.event["event_id"] and replay.replayed
            with pytest.raises(EventIdempotencyConflict):
                write_security_event(
                    cursor,
                    "security.login.started",
                    context,
                    EventData(),
                    idempotency_scope="security.login.terminal",
                    idempotency_key=context.request_id,
                )
        conn.rollback()
    finally:
        conn.close()


def test_activation_migration_is_exact_idempotent_and_converges_with_schema():
    base = _local_test_url()
    old_schema = _activation_pre_schema()
    migration = ACTIVATION_MIGRATION.read_text(encoding="utf-8")
    observed = []
    for blocks, apply_migration in (
        ((STUBS, old_schema), True),
        ((STUBS, old_schema), True),
    ):
        url, cleanup = make_disposable(base, *blocks)
        try:
            conn = psycopg2.connect(url)
            try:
                if apply_migration:
                    for _ in range(2):
                        with conn.cursor() as cursor:
                            cursor.execute(migration)
                        conn.commit()
                with conn.cursor() as cursor:
                    cursor.execute(
                        "select event_name from canonical_event_catalog_projection "
                        "where integrated order by event_name"
                    )
                    names = {row[0] for row in cursor.fetchall()}
                    cursor.execute(
                        "select (select count(*) from security_events), "
                        "(select count(*) from business_audit_events)"
                    )
                    event_counts = cursor.fetchone()
                observed.append((_semantic_signature(conn), names, event_counts))
            finally:
                conn.close()
        finally:
            cleanup()
    assert observed[0] == observed[1] == (EXPECTED_FINAL_SIGNATURE, EXPECTED_EVENTS, (0, 0))


def test_activation_migration_rejects_partial_state_without_repair():
    base = _local_test_url()
    old_schema = _activation_pre_schema()
    url, cleanup = make_disposable(base, STUBS, old_schema)
    try:
        conn = psycopg2.connect(url)
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "alter table canonical_event_catalog_projection drop constraint "
                        "canonical_event_catalog_projection_integrated_check"
                    )
                    cursor.execute(
                        "alter table canonical_event_catalog_projection add constraint "
                        "canonical_event_catalog_projection_integrated_check check "
                        "(not integrated or (lifecycle_status='planned' and writable and "
                        "category in ('security','business_audit')))"
                    )
                    cursor.execute(
                        "update canonical_event_catalog_projection set integrated=true "
                        "where event_name='security.login.started'"
                    )
            before = _semantic_signature(conn)
            with pytest.raises(psycopg2.Error):
                with conn.cursor() as cursor:
                    cursor.execute(ACTIVATION_MIGRATION.read_text(encoding="utf-8"))
            conn.rollback()
            assert _semantic_signature(conn) == before
            with conn.cursor() as cursor:
                cursor.execute(
                    "select array_agg(event_name order by event_name) from "
                    "canonical_event_catalog_projection where integrated"
                )
                assert cursor.fetchone()[0] == ["security.login.started"]
        finally:
            conn.close()
    finally:
        cleanup()
