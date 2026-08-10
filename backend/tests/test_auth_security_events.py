"""Real PostgreSQL proof for the bounded Phase 1B-2A auth integration."""

import os
import hashlib
import secrets
import threading
import time
import uuid
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
DURABLE_RUNTIME_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260801170000_durable_session_runtime_events.sql"
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


def _seed_linked_user(url, *, email="linked@example.invalid"):
    auth_id = str(uuid.uuid4())
    metadata = (
        '{"full_name":"Linked Test User","phone":"03000000009",'
        '"cnic":"9000000000000","role":"service_seeker"}'
    )
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,%s::jsonb)",
                (auth_id, email, metadata),
            )
            cursor.execute(
                "select id from public.users where auth_id=%s", (auth_id,)
            )
            return cursor.fetchone()[0]


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


def _authenticate_client(client, url, user_id, csrf="csrf-test"):
    device_raw = secrets.token_urlsafe(32)
    session_raw = secrets.token_urlsafe(32)
    access_proof = secrets.token_urlsafe(32)
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "insert into public.trusted_devices(token_digest,user_id,expires_at) "
                    "values(%s,%s,now()+interval '30 days') returning id",
                    (hashlib.sha256(device_raw.encode()).digest(), user_id),
                )
                device_id = cursor.fetchone()[0]
                cursor.execute(
                    "insert into public.user_sessions(user_id,token_digest,trusted_device_id,"
                    "inactivity_expires_at,absolute_expires_at,access_proof_digest,"
                    "access_proof_expires_at) values "
                    "(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',"
                    "%s,now()+interval '8 hours') "
                    "returning session_id",
                    (
                        user_id,
                        hashlib.sha256(session_raw.encode()).digest(),
                        device_id,
                        hashlib.sha256(access_proof.encode()).digest(),
                    ),
                )
                session_id = cursor.fetchone()[0]
    finally:
        conn.close()
    client.set_cookie("dtx_device_token", device_raw)
    client.set_cookie("dtx_session_token", session_raw)
    client.set_cookie("dtx_access_proof", access_proof)
    with client.session_transaction() as state:
        state["csrf_token"] = csrf
    return device_raw, session_raw, device_id, session_id


def test_catalog_preserves_login_events_and_adds_only_bounded_signup_events():
    expected = EXPECTED_EVENTS | {
        "security.signup.started",
        "security.signup.failed",
        "security.signup.completed",
        "security.trusted_device.added",
        "security.trusted_device.removed",
        "security.trusted_device.rotated",
        "security.session.issued",
        "security.session.revoked",
        "security.session.access_locked",
        "security.session.refreshed",
        "security.mpin.enrolled",
        "security.mpin.changed",
        "security.mpin.disabled",
        "security.mpin.unlock_succeeded",
        "security.mpin.unlock_failed",
        "security.mpin.locked",
        "security.mpin.reset_completed",
    }
    assert set(INTEGRATED_EVENT_NAMES) == expected
    assert {name for name, item in CATALOG.items() if item.integrated} == expected
    assert sum(item.integrated for item in CATALOG.values()) == 21
    assert sum(item.lifecycle_status == "planned" and not item.integrated for item in CATALOG.values()) == 141
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
    proof_headers = [
        value for value in response.headers.getlist("Set-Cookie")
        if value.startswith("dtx_access_proof=")
    ]
    assert len(proof_headers) == 1
    assert "HttpOnly" in proof_headers[0] and "SameSite=Lax" in proof_headers[0]
    assert "Max-Age" not in proof_headers[0] and "Expires" not in proof_headers[0]
    events = _event_rows(url)
    assert [event["event_name"] for event in events] == [
        "security.login.started",
        "security.login.succeeded",
        "security.session.issued",
        "security.trusted_device.added",
    ]
    assert len({event["request_id"] for event in events}) == 1
    assert events[0]["actor_type"] == "anonymous"
    assert all(events[0][key] is None for key in ("actor_id", "actor_role", "subject_user_id"))
    assert events[1]["actor_type"] == "user"
    assert events[1]["actor_id"] == events[1]["subject_user_id"] == user_id
    assert events[1]["actor_role"] == "service_seeker"
    assert events[2]["actor_id"] == events[2]["subject_user_id"] == user_id
    assert all(event["source"] == "server_route" and event["provider_mode"] == "none" for event in events)
    assert all(event["session_ref"] is None and event["device_ref"] is None for event in events)
    activity = _rows(url, "login_activity")
    assert len(activity) == 1 and activity[0]["status"] == "success"
    devices = _rows(url, "trusted_devices")
    assert len(devices) == 1 and devices[0]["user_id"] == user_id
    sessions = _rows(url, "user_sessions")
    assert len(sessions) == 1 and sessions[0]["trusted_device_id"] == devices[0]["id"]
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


def test_login_provider_runs_with_no_database_context_held(auth_client, monkeypatch):
    client, url = auth_client
    _seed_user(url)
    original = auth_routes.open_db
    active = 0
    guard = threading.Lock()

    @contextmanager
    def tracked_open_db():
        nonlocal active
        with guard:
            active += 1
        try:
            with original() as db:
                yield db
        finally:
            with guard:
                active -= 1

    def provider(*_args, **_kwargs):
        assert active == 0
        assert [row["event_name"] for row in _event_rows(url)] == [
            "security.login.started"
        ]
        return True

    monkeypatch.setattr(auth_routes, "open_db", tracked_open_db)
    monkeypatch.setattr(auth_helpers, "open_db", tracked_open_db)
    monkeypatch.setattr(auth_routes, "supabase_verify_password", provider)
    response = client.post(
        "/auth/login",
        json={"loginId": "bounded@example.invalid", "password": "valid"},
    )
    assert response.status_code == 200
    assert active == 0


def test_login_revalidates_blocked_account_after_provider(auth_client, monkeypatch):
    client, url = auth_client
    _seed_user(url)

    def provider(*_args, **_kwargs):
        with psycopg2.connect(url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("update public.users set is_blocked=true")
        return True

    monkeypatch.setattr(auth_routes, "supabase_verify_password", provider)
    response = client.post(
        "/auth/login",
        json={"loginId": "bounded@example.invalid", "password": "valid"},
    )
    assert response.status_code == 401
    assert _rows(url, "trusted_devices") == []
    assert _rows(url, "user_sessions") == []
    assert _rows(url, "login_activity")[0]["status"] == "failed"


def test_login_uses_committed_snapshot_without_post_commit_user_read(
    auth_client, monkeypatch
):
    client, url = auth_client
    _seed_user(url)
    monkeypatch.setattr(auth_routes, "supabase_verify_password", lambda *_a, **_k: True)
    monkeypatch.setattr(
        auth_routes,
        "get_user_by_id",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("forbidden-post-commit-read")
        ),
    )
    response = client.post(
        "/auth/login",
        json={"loginId": "bounded@example.invalid", "password": "valid"},
    )
    assert response.status_code == 200
    assert len(_rows(url, "trusted_devices")) == 1
    assert len(_rows(url, "user_sessions")) == 1


def test_otp_is_one_shot_and_wrong_replay_mints_no_authorization(
    auth_client
):
    client, url = auth_client
    user_id = _seed_user(url)
    with client.application.app_context():
        auth_helpers.create_otp_record(
            user_id, "password_reset", "123456", "bounded@example.invalid"
        )
        _, first_error, first_token = auth_helpers.consume_otp_for_user(
            user_id,
            "password_reset",
            "123456",
            issue_reset_authorization=True,
        )
        _, replay_error, replay_token = auth_helpers.consume_otp_for_user(
            user_id,
            "password_reset",
            "654321",
            issue_reset_authorization=True,
        )
    assert first_error == "" and first_token
    assert replay_error and replay_token is None
    rows = _rows(url, "reset_tokens")
    assert len(rows) == 1
    serialized = str(rows).lower()
    assert "123456" not in serialized and first_token not in serialized


def test_concurrent_reset_consumers_call_provider_exactly_once(
    auth_client, monkeypatch
):
    client, url = auth_client
    user_id = _seed_linked_user(url)
    with client.application.app_context():
        auth_helpers.create_otp_record(
            user_id, "password_reset", "123456", "linked@example.invalid"
        )
        _, error, raw_token = auth_helpers.consume_otp_for_user(
            user_id,
            "password_reset",
            "123456",
            issue_reset_authorization=True,
        )
    assert not error
    calls = []
    call_lock = threading.Lock()

    def provider(*_args, **_kwargs):
        with call_lock:
            calls.append(True)
        time.sleep(0.1)

    monkeypatch.setattr(auth_routes, "supabase_update_password", provider)
    barrier = threading.Barrier(2)
    responses = []
    response_lock = threading.Lock()

    def consume():
        clone = client.application.test_client()
        barrier.wait()
        response = clone.post(
            "/auth/reset-password",
            json={"reset_token": raw_token, "new_password": "new-password-1"},
        )
        with response_lock:
            responses.append(response)

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert len(calls) == 1
    assert sorted(response.status_code for response in responses) == [200, 400]
    rows = _rows(url, "reset_tokens")
    assert len(rows) == 1 and rows[0]["claim_state"] == "completed"


def test_reset_provider_failure_is_sanitized_nonreplayable_and_explicit(
    auth_client, monkeypatch, caplog
):
    client, url = auth_client
    user_id = _seed_linked_user(url, email="failure@example.invalid")
    with client.application.app_context():
        auth_helpers.create_otp_record(
            user_id, "password_reset", "234567", "failure@example.invalid"
        )
        _, error, raw_token = auth_helpers.consume_otp_for_user(
            user_id,
            "password_reset",
            "234567",
            issue_reset_authorization=True,
        )
    assert not error
    sentinel = "SENTINEL_RESET_PROVIDER_SECRET"
    calls = []

    def provider(*_args, **_kwargs):
        calls.append(True)
        raise RuntimeError(sentinel)

    monkeypatch.setattr(auth_routes, "supabase_update_password", provider)
    first = client.post(
        "/auth/reset-password",
        json={"reset_token": raw_token, "new_password": "new-password-2"},
    )
    replay = client.post(
        "/auth/reset-password",
        json={"reset_token": raw_token, "new_password": "new-password-2"},
    )
    assert first.status_code == 503 and replay.status_code == 400
    assert len(calls) == 1
    assert sentinel not in first.get_data(as_text=True)
    assert sentinel not in replay.get_data(as_text=True)
    assert sentinel not in caplog.text
    assert _rows(url, "reset_tokens")[0]["claim_state"] == "reconciliation_required"


def test_reset_finalization_failure_is_explicit_and_nonreplayable(
    auth_client, monkeypatch, caplog
):
    client, url = auth_client
    user_id = _seed_linked_user(url, email="finalize@example.invalid")
    with client.application.app_context():
        auth_helpers.create_otp_record(
            user_id, "password_reset", "345678", "finalize@example.invalid"
        )
        _, error, raw_token = auth_helpers.consume_otp_for_user(
            user_id,
            "password_reset",
            "345678",
            issue_reset_authorization=True,
        )
    assert not error
    calls = []
    monkeypatch.setattr(
        auth_routes,
        "supabase_update_password",
        lambda *_a, **_k: calls.append(True),
    )
    sentinel = "SENTINEL_RESET_FINALIZE_SECRET"
    monkeypatch.setattr(
        auth_routes,
        "finalize_reset_token_claim",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(sentinel)),
    )
    first = client.post(
        "/auth/reset-password",
        json={"reset_token": raw_token, "new_password": "new-password-3"},
    )
    replay = client.post(
        "/auth/reset-password",
        json={"reset_token": raw_token, "new_password": "new-password-3"},
    )
    assert first.status_code == 503 and replay.status_code == 400
    assert "confirmation is pending" in first.get_json()["message"]
    assert calls == [True]
    assert sentinel not in first.get_data(as_text=True)
    assert sentinel not in replay.get_data(as_text=True)
    assert sentinel not in caplog.text
    assert _rows(url, "reset_tokens")[0]["claim_state"] == "claimed"


def test_forgot_password_email_exception_is_sanitized(
    auth_client, monkeypatch, caplog
):
    client, url = auth_client
    _seed_user(url)
    sentinel = "SENTINEL_PASSWORD_EMAIL_SECRET"
    monkeypatch.setattr(
        auth_routes,
        "send_email",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(sentinel)),
    )
    response = client.post(
        "/auth/forgot-password", json={"loginId": "bounded@example.invalid"}
    )
    assert response.status_code == 503
    assert sentinel not in response.get_data(as_text=True)
    assert sentinel not in caplog.text
    assert _rows(url, "password_reset_otps") == []


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
    assert _rows(url, "user_sessions") == []
    assert not any(
        value.startswith("dtx_access_proof=")
        for value in response.headers.getlist("Set-Cookie")
    )
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
        "establish_after_full_login",
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
    _authenticate_client(client, url, user_id)
    response = client.post("/auth/logout", headers={"X-CSRF-Token": "csrf-test"})
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "user_id" not in session
    events = _event_rows(url)
    assert [event["event_name"] for event in events] == [
        "security.logout.completed", "security.session.revoked"
    ]
    assert all(event["actor_type"] == "admin" for event in events)
    assert all(event["actor_id"] == event["subject_user_id"] == user_id for event in events)
    assert all(event["actor_role"] == "platform_admin" for event in events)


def test_invalid_csrf_and_anonymous_logout_emit_no_event(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    _authenticate_client(client, url, user_id, "expected")
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert _event_rows(url) == []
    client.delete_cookie("dtx_session_token")
    assert client.post("/auth/logout").status_code == 401
    assert _event_rows(url) == []


def test_durable_session_and_exact_device_are_the_only_runtime_authority(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)

    with client.session_transaction() as state:
        state["user_id"] = user_id
    signed_only = client.get("/auth/me")
    assert signed_only.status_code == 401
    assert signed_only.get_json() == {
        "success": False,
        "message": "Authentication required.",
    }

    device_raw, session_raw, _device_id, _session_id = _authenticate_client(
        client, url, user_id
    )
    client.delete_cookie("dtx_session_token")
    assert client.get("/auth/me").status_code == 401
    client.set_cookie("dtx_session_token", session_raw)
    client.delete_cookie("dtx_device_token")
    assert client.get("/auth/me").status_code == 401
    client.set_cookie("dtx_session_token", session_raw)
    client.set_cookie("dtx_device_token", device_raw)
    assert client.get("/auth/me").status_code == 200


@pytest.mark.parametrize(
    "statement",
    [
        "update user_sessions set revoked_at=now(), revocation_reason='logout'",
        "update user_sessions set created_at=now()-interval '40 days', "
        "authenticated_at=now()-interval '40 days', "
        "last_genuine_activity_at=now()-interval '8 days', "
        "inactivity_expires_at=now()-interval '1 second'",
        "update user_sessions set created_at=now()-interval '40 days', "
        "authenticated_at=now()-interval '40 days', "
        "last_genuine_activity_at=now()-interval '31 days', "
        "inactivity_expires_at=now()-interval '24 days', "
        "absolute_expires_at=now()-interval '1 second', "
        "access_proof_digest=null, access_proof_expires_at=null",
        "update trusted_devices set revoked_at=now()",
        "update trusted_devices set created_at=now()-interval '31 days', "
        "expires_at=now()-interval '1 second'",
    ],
)
def test_revoked_or_expired_session_or_device_fails_closed(auth_client, statement):
    client, url = auth_client
    user_id = _seed_user(url)
    _authenticate_client(client, url, user_id)
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(statement)
    finally:
        conn.close()
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.get_json() == {
        "success": False,
        "message": "Authentication required.",
    }
    assert any("dtx_session_token=;" in value for value in response.headers.getlist("Set-Cookie"))
    assert any("dtx_device_token=;" in value for value in response.headers.getlist("Set-Cookie"))


def test_unknown_token_is_generic_and_passive_me_does_not_refresh_genuine_activity(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    device_raw, _session_raw, _device_id, session_id = _authenticate_client(client, url, user_id)
    before = _rows(url, "user_sessions")[0]["last_genuine_activity_at"]
    assert client.get("/auth/me").status_code == 200
    after = _rows(url, "user_sessions")[0]["last_genuine_activity_at"]
    assert after == before

    client.set_cookie("dtx_device_token", device_raw)
    client.set_cookie("dtx_session_token", secrets.token_urlsafe(32))
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.get_json() == {
        "success": False,
        "message": "Authentication required.",
    }
    assert str(session_id) not in response.get_data(as_text=True)


def test_logout_revokes_only_current_session(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    _device_raw, _session_raw, _device_id, current_id = _authenticate_client(
        client, url, user_id
    )
    other_device = hashlib.sha256(secrets.token_bytes(32)).digest()
    other_session = hashlib.sha256(secrets.token_bytes(32)).digest()
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "insert into trusted_devices(token_digest,user_id,expires_at) "
                    "values(%s,%s,now()+interval '30 days') returning id",
                    (other_device, user_id),
                )
                other_device_id = cursor.fetchone()[0]
                cursor.execute(
                    "insert into user_sessions(user_id,token_digest,trusted_device_id,"
                    "inactivity_expires_at,absolute_expires_at) values "
                    "(%s,%s,%s,now()+interval '7 days',now()+interval '30 days') "
                    "returning session_id",
                    (user_id, other_session, other_device_id),
                )
                other_id = cursor.fetchone()[0]
    finally:
        conn.close()
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "csrf-test"}).status_code == 200
    rows = {row["session_id"]: row for row in _rows(url, "user_sessions")}
    assert rows[current_id]["revoked_at"] is not None
    assert rows[current_id]["revocation_reason"] == "logout"
    assert rows[other_id]["revoked_at"] is None


def test_logout_clears_session_when_event_persistence_fails(auth_client, monkeypatch):
    client, url = auth_client
    user_id = _seed_user(url)
    _authenticate_client(client, url, user_id)
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


def test_durable_runtime_migration_rejects_partial_state_without_repair():
    base = _local_test_url()
    prior_schema = subprocess.check_output(
        ["git", "show", "330509618dcfc7f8d70c3056f3128d4a7fcafcb0:supabase/schema.sql"],
        cwd=REPO_ROOT,
    ).decode("utf-8")
    url, cleanup = make_disposable(base, STUBS, prior_schema)
    try:
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "update canonical_event_catalog_projection set integrated=true "
                    "where event_name='security.session.issued'"
                )
            conn.commit()
            with pytest.raises(psycopg2.Error):
                with conn.cursor() as cursor:
                    cursor.execute(DURABLE_RUNTIME_MIGRATION.read_text(encoding="utf-8"))
                conn.commit()
            conn.rollback()
            with conn.cursor() as cursor:
                cursor.execute(
                    "select event_name,integrated from canonical_event_catalog_projection "
                    "where event_name in ('security.session.issued','security.session.revoked') "
                    "order by event_name"
                )
                assert cursor.fetchall() == [
                    ("security.session.issued", True),
                    ("security.session.revoked", False),
                ]
        finally:
            conn.close()
    finally:
        cleanup()


def _genuine_activity_session(url, session_id):
    with psycopg2.connect(url) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                select authenticated_at,last_genuine_activity_at,
                       inactivity_expires_at,absolute_expires_at,updated_at,
                       access_locked,access_proof_digest,access_proof_expires_at,
                       trusted_device_id
                  from public.user_sessions where session_id=%s
                """,
                (session_id,),
            )
            return dict(cursor.fetchone())


def _age_valid_session(url, session_id):
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update public.user_sessions
                   set created_at=now()-interval '8 days',
                       authenticated_at=now()-interval '8 days',
                       last_genuine_activity_at=now()-interval '13 hours',
                       inactivity_expires_at=now()+interval '1 day',
                       absolute_expires_at=now()+interval '22 days',
                       access_proof_expires_at=now()+interval '1 hour',
                       updated_at=now()
                 where session_id=%s
                """,
                (session_id,),
            )


def test_genuine_activity_refreshes_only_current_deadline_beyond_login_age(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    _, _, device_id, session_id = _authenticate_client(client, url, user_id)
    _age_valid_session(url, session_id)
    second_raw = secrets.token_urlsafe(32)
    second_proof = secrets.token_urlsafe(32)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                insert into public.user_sessions(
                    user_id,token_digest,trusted_device_id,
                    inactivity_expires_at,absolute_expires_at,
                    access_proof_digest,access_proof_expires_at
                ) values(
                    %s,%s,%s,now()+interval '2 days',now()+interval '20 days',
                    %s,now()+interval '1 hour'
                ) returning session_id
                """,
                (
                    user_id,
                    hashlib.sha256(second_raw.encode()).digest(),
                    device_id,
                    hashlib.sha256(second_proof.encode()).digest(),
                ),
            )
            second_id = cursor.fetchone()[0]
    before = _genuine_activity_session(url, session_id)
    second_before = _genuine_activity_session(url, second_id)

    response = client.post(
        "/auth/session/activity", headers={"X-CSRF-Token": "csrf-test"}
    )

    assert response.status_code == 204 and response.data == b""
    after = _genuine_activity_session(url, session_id)
    assert after["authenticated_at"] == before["authenticated_at"]
    assert after["absolute_expires_at"] == before["absolute_expires_at"]
    assert after["access_proof_digest"] == before["access_proof_digest"]
    assert after["access_proof_expires_at"] == before["access_proof_expires_at"]
    assert after["trusted_device_id"] == before["trusted_device_id"]
    assert after["last_genuine_activity_at"] > before["last_genuine_activity_at"]
    assert after["inactivity_expires_at"] > before["inactivity_expires_at"]
    assert 6.99 < (
        after["inactivity_expires_at"] - after["last_genuine_activity_at"]
    ).total_seconds() / 86400 <= 7
    assert _genuine_activity_session(url, second_id) == second_before
    events = _event_rows(url)
    assert len(events) == 1
    assert events[0]["event_name"] == "security.session.refreshed"
    assert events[0]["actor_id"] == events[0]["subject_user_id"] == user_id
    assert events[0]["session_ref"].startswith("session_")
    assert str(session_id) not in events[0]["session_ref"]
    assert events[0]["metadata"] == {}


def test_no_activity_expires_and_cannot_be_revived(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    _, _, _, session_id = _authenticate_client(client, url, user_id)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update public.user_sessions
                   set created_at=now()-interval '8 days',
                       authenticated_at=now()-interval '8 days',
                       last_genuine_activity_at=now()-interval '8 days',
                       inactivity_expires_at=now()-interval '1 day',
                       absolute_expires_at=now()+interval '22 days',
                       updated_at=now()
                 where session_id=%s
                """,
                (session_id,),
            )
    before = _genuine_activity_session(url, session_id)

    response = client.post(
        "/auth/session/activity", headers={"X-CSRF-Token": "csrf-test"}
    )

    assert response.status_code == 401
    assert _genuine_activity_session(url, session_id) == before
    assert _event_rows(url) == []


@pytest.mark.parametrize(
    ("state", "expected_status"),
    [
        ("revoked", 401),
        ("blocked", 401),
        ("device_expired", 401),
        ("device_mismatch", 401),
        ("absolute_expired", 401),
        ("access_locked", 423),
    ],
)
def test_ineligible_authentication_states_never_refresh(
    auth_client, state, expected_status
):
    client, url = auth_client
    user_id = _seed_user(url)
    _, _, device_id, session_id = _authenticate_client(client, url, user_id)
    _age_valid_session(url, session_id)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            if state == "revoked":
                cursor.execute(
                    "update user_sessions set revoked_at=now(),revocation_reason='security_action',updated_at=now() where session_id=%s",
                    (session_id,),
                )
            elif state == "blocked":
                cursor.execute("update users set is_blocked=true where id=%s", (user_id,))
            elif state == "device_expired":
                cursor.execute(
                    "update trusted_devices set created_at=now()-interval '2 days',expires_at=now()-interval '1 day' where id=%s",
                    (device_id,),
                )
            elif state == "device_mismatch":
                client.set_cookie("dtx_device_token", secrets.token_urlsafe(32))
            elif state == "absolute_expired":
                cursor.execute(
                    """
                    update user_sessions
                       set created_at=now()-interval '31 days',
                           authenticated_at=now()-interval '31 days',
                           last_genuine_activity_at=now()-interval '3 days',
                           inactivity_expires_at=now()-interval '2 days',
                           absolute_expires_at=now()-interval '1 day',
                           access_locked=true,access_locked_at=now()-interval '2 days',
                           access_proof_digest=null,access_proof_expires_at=null,
                           updated_at=now()
                     where session_id=%s
                    """,
                    (session_id,),
                )
            elif state == "access_locked":
                cursor.execute(
                    "update user_sessions set access_locked=true,access_locked_at=now(),access_proof_digest=null,access_proof_expires_at=null,updated_at=now() where session_id=%s",
                    (session_id,),
                )
    before = _genuine_activity_session(url, session_id)

    response = client.post(
        "/auth/session/activity", headers={"X-CSRF-Token": "csrf-test"}
    )

    assert response.status_code == expected_status
    after = _genuine_activity_session(url, session_id)
    assert after["last_genuine_activity_at"] == before["last_genuine_activity_at"]
    assert after["inactivity_expires_at"] == before["inactivity_expires_at"]
    assert after["absolute_expires_at"] == before["absolute_expires_at"]
    assert _event_rows(url) == []


@pytest.mark.parametrize("csrf", [None, "wrong-csrf"])
def test_activity_requires_csrf_and_an_empty_private_signal(auth_client, csrf):
    client, url = auth_client
    user_id = _seed_user(url)
    _, _, _, session_id = _authenticate_client(client, url, user_id)
    _age_valid_session(url, session_id)
    before = _genuine_activity_session(url, session_id)
    headers = {} if csrf is None else {"X-CSRF-Token": csrf}

    response = client.post("/auth/session/activity", headers=headers)

    assert response.status_code == 403
    assert _genuine_activity_session(url, session_id) == before
    assert _event_rows(url) == []

    detailed = client.post(
        "/auth/session/activity",
        json={"key": "private-interaction-detail"},
        headers={"X-CSRF-Token": "csrf-test"},
    )
    assert detailed.status_code == 400
    assert _genuine_activity_session(url, session_id) == before
    assert _event_rows(url) == []


def test_passive_me_and_throttled_activity_are_noop(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    _, _, _, session_id = _authenticate_client(client, url, user_id)
    _age_valid_session(url, session_id)
    before_me = _genuine_activity_session(url, session_id)
    assert client.get("/auth/me").status_code == 200
    assert _genuine_activity_session(url, session_id) == before_me

    first = client.post(
        "/auth/session/activity", headers={"X-CSRF-Token": "csrf-test"}
    )
    assert first.status_code == 204
    after_first = _genuine_activity_session(url, session_id)
    second = client.post(
        "/auth/session/activity", headers={"X-CSRF-Token": "csrf-test"}
    )
    assert second.status_code == 204
    assert _genuine_activity_session(url, session_id) == after_first
    assert [row["event_name"] for row in _event_rows(url)] == [
        "security.session.refreshed"
    ]


def test_later_signal_after_database_throttle_boundary_refreshes(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    _, _, _, session_id = _authenticate_client(client, url, user_id)
    initial = _genuine_activity_session(url, session_id)
    assert client.post(
        "/auth/session/activity", headers={"X-CSRF-Token": "csrf-test"}
    ).status_code == 204
    assert _genuine_activity_session(url, session_id) == initial
    assert _event_rows(url) == []

    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "update user_sessions set created_at=now()-interval '1 day',"
                "authenticated_at=now()-interval '1 day',last_genuine_activity_at="
                "now()-interval '12 hours 1 second' where session_id=%s",
                (session_id,),
            )
    boundary = _genuine_activity_session(url, session_id)
    assert client.post(
        "/auth/session/activity", headers={"X-CSRF-Token": "csrf-test"}
    ).status_code == 204
    after = _genuine_activity_session(url, session_id)
    assert after["last_genuine_activity_at"] > boundary["last_genuine_activity_at"]
    assert len(_event_rows(url)) == 1


def test_concurrent_activity_has_one_update_and_one_event(auth_client):
    client, url = auth_client
    user_id = _seed_user(url)
    _, _, _, session_id = _authenticate_client(client, url, user_id)
    _age_valid_session(url, session_id)
    before = _genuine_activity_session(url, session_id)
    cookie_names = (
        "dtx_device_token",
        "dtx_session_token",
        "dtx_access_proof",
        client.application.config.get("SESSION_COOKIE_NAME", "session"),
    )
    cookie_values = {
        name: client.get_cookie(name).value for name in cookie_names
    }
    responses = []
    failures = []

    def worker():
        try:
            isolated = client.application.test_client()
            for name, value in cookie_values.items():
                isolated.set_cookie(name, value)
            responses.append(
                isolated.post(
                    "/auth/session/activity",
                    headers={"X-CSRF-Token": "csrf-test"},
                ).status_code
            )
        except Exception as exc:
            failures.append(type(exc).__name__)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert failures == []
    assert responses == [204] * 4
    after = _genuine_activity_session(url, session_id)
    assert after["last_genuine_activity_at"] > before["last_genuine_activity_at"]
    assert len(_event_rows(url)) == 1


def test_refresh_and_event_roll_back_together(auth_client, monkeypatch):
    client, url = auth_client
    user_id = _seed_user(url)
    _, _, _, session_id = _authenticate_client(client, url, user_id)
    _age_valid_session(url, session_id)
    before = _genuine_activity_session(url, session_id)
    monkeypatch.setattr(
        auth_routes,
        "write_security_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("forced")),
    )

    response = client.post(
        "/auth/session/activity", headers={"X-CSRF-Token": "csrf-test"}
    )

    assert response.status_code == 503
    assert _genuine_activity_session(url, session_id) == before
    assert _event_rows(url) == []
