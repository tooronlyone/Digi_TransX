"""Phase 1B-2C3B1 secure MPIN and software-access-lock proofs."""

import base64
from contextlib import contextmanager
import hashlib
import importlib
import os
from pathlib import Path
import secrets
import sys
import threading
from urllib.parse import urlsplit

from flask import Flask
import psycopg2
from psycopg2 import errors
import pytest

import auth.helpers as auth_helpers
from auth import mpin_service, session_service
import auth.routes as auth_routes
from shared.db import Db
from tests._life_helpers import (
    SCHEMA_SQL,
    STUBS,
    make_disposable,
    require_test_db_url,
    schema_before_migration_or_skip,
)
from tests.test_canonical_event_acl_hardening import _semantic_signature


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20260801180000_secure_mpin_access_lock.sql"
GENUINE_ACTIVITY_MIGRATION = (
    ROOT / "supabase/migrations/20260801200000_genuine_session_activity.sql"
)
MPIN_STEP_UP_MIGRATION = (
    ROOT / "supabase/migrations/20260801210000_mpin_step_up_authorization_foundation.sql"
)
PEPPER = base64.urlsafe_b64encode(b"P" * 32).decode()
NEW_INTEGRATIONS = {
    "security.session.access_locked",
    "security.mpin.enrolled",
    "security.mpin.changed",
    "security.mpin.disabled",
    "security.mpin.unlock_succeeded",
    "security.mpin.unlock_failed",
    "security.mpin.locked",
    "security.mpin.reset_completed",
}


def _local_url():
    url = require_test_db_url()
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert parsed.path.lstrip("/").startswith("dtx_phase1b2c0_")
    assert url != os.environ.get("SUPABASE_DB_URL", "").strip()
    return url


@pytest.fixture(scope="module")
def mpin_database_url():
    url, cleanup = make_disposable(
        _local_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def mpin_client(mpin_database_url, monkeypatch):
    @contextmanager
    def test_open_db():
        conn = psycopg2.connect(mpin_database_url)
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
    monkeypatch.setattr(
        auth_routes, "supabase_verify_password", lambda *_args, **_kwargs: True
    )
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    monkeypatch.setenv("DIGITRANSX_MPIN_PEPPER", PEPPER)

    app = Flask(__name__)
    app.config.update(SECRET_KEY="mpin-test-only", SESSION_COOKIE_SECURE=False)
    app.register_blueprint(auth_routes.auth_blueprint)

    @app.get("/business")
    @auth_helpers.login_required(refresh_activity=False)
    def business_route():
        return auth_helpers.json_response({"success": True})

    client = app.test_client()
    yield client, mpin_database_url

    with psycopg2.connect(mpin_database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "truncate public.security_events, public.login_activity, "
                "public.trusted_devices, public.users restart identity cascade"
            )


def _authenticate(client, url, *, role="service_seeker", with_mpin=None):
    app_role = "transporter" if role == "logistics_provider" else (
        "admin" if role == "platform_admin" else "customer"
    )
    device_raw = secrets.token_urlsafe(32)
    session_raw = secrets.token_urlsafe(32)
    proof_raw = secrets.token_urlsafe(32)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "insert into public.users(full_name,email,cnic,role,legacy_role) "
                "values('MPIN Test','mpin@example.invalid','1111111111111',%s,%s) returning id",
                (app_role, role),
            )
            user_id = cursor.fetchone()[0]
            cursor.execute(
                "insert into public.trusted_devices(token_digest,user_id,expires_at) "
                "values(%s,%s,now()+interval '30 days') returning id",
                (hashlib.sha256(device_raw.encode()).digest(), user_id),
            )
            device_id = cursor.fetchone()[0]
            cursor.execute(
                "insert into public.user_sessions(user_id,token_digest,trusted_device_id,"
                "inactivity_expires_at,absolute_expires_at,access_proof_digest,"
                "access_proof_expires_at) values(%s,%s,%s,now()+interval '7 days',"
                "now()+interval '30 days',%s,now()+interval '8 hours') returning session_id",
                (
                    user_id,
                    hashlib.sha256(session_raw.encode()).digest(),
                    device_id,
                    hashlib.sha256(proof_raw.encode()).digest(),
                ),
            )
            session_id = cursor.fetchone()[0]
            if with_mpin is not None:
                salt, verifier = mpin_service.build_credential(with_mpin)
                cursor.execute(
                    "insert into public.mpin_credentials(user_id,verifier,salt,kdf_version) "
                    "values(%s,%s,%s,1)",
                    (user_id, verifier, salt),
                )
    client.set_cookie(auth_helpers.DEVICE_COOKIE_NAME, device_raw)
    client.set_cookie(auth_helpers.SESSION_TOKEN_COOKIE_NAME, session_raw)
    client.set_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME, proof_raw)
    with client.session_transaction() as state:
        state["csrf_token"] = "mpin-csrf"
    return {
        "user_id": user_id,
        "session_id": session_id,
        "device_id": device_id,
        "device_raw": device_raw,
        "session_raw": session_raw,
        "proof_raw": proof_raw,
    }


def _csrf():
    return {"X-CSRF-Token": "mpin-csrf"}


def _lock(client):
    client.delete_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME)
    response = client.get("/business")
    assert response.status_code == 423
    assert response.get_json()["code"] == "access_locked"


def _session_snapshot(url, session_id):
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select inactivity_expires_at,absolute_expires_at,last_genuine_activity_at,"
                "access_locked from public.user_sessions where session_id=%s",
                (session_id,),
            )
            return cursor.fetchone()


@pytest.mark.parametrize(
    "value",
    [None, 1234, True, 12.34, "", "123", "12345", " 1234", "1234 ", "12 34", "１２３４", "١٢٣٤", "+123", "-123"],
)
def test_mpin_validation_is_exactly_four_ascii_digits(value):
    with pytest.raises(mpin_service.MpinError):
        mpin_service.validate_mpin(value)
    assert mpin_service.validate_mpin("0000") == "0000"
    assert mpin_service.validate_mpin("9876") == "9876"


def test_memory_hard_kdf_requires_pepper_and_uses_unique_salts(monkeypatch):
    monkeypatch.delenv("DIGITRANSX_MPIN_PEPPER", raising=False)
    with pytest.raises(mpin_service.MpinConfigurationError):
        mpin_service.build_credential("1234")
    monkeypatch.setenv("DIGITRANSX_MPIN_PEPPER", "invalid")
    with pytest.raises(mpin_service.MpinConfigurationError):
        mpin_service.build_credential("1234")
    monkeypatch.setenv("DIGITRANSX_MPIN_PEPPER", PEPPER)
    salt_a, verifier_a = mpin_service.build_credential("1234")
    salt_b, verifier_b = mpin_service.build_credential("1234")
    assert len(salt_a) == len(salt_b) == 32
    assert len(verifier_a) == len(verifier_b) == 32
    assert salt_a != salt_b and verifier_a != verifier_b
    assert mpin_service.verify_mpin(
        "1234", {"salt": salt_a, "verifier": verifier_a, "kdf_version": 1}
    )
    assert not mpin_service.verify_mpin(
        "1235", {"salt": salt_a, "verifier": verifier_a, "kdf_version": 1}
    )


@pytest.mark.parametrize(
    "role,eligible",
    [
        ("logistics_provider", True),
        ("service_seeker", True),
        ("everyday_user", True),
        ("platform_admin", False),
        ("fuel_station_manager", False),
        ("shopkeeper", False),
        ("admin", False),
    ],
)
def test_role_allowlist_is_closed(role, eligible):
    assert mpin_service.role_is_eligible(role) is eligible


def test_enrollment_requires_password_and_uses_one_canonical_row(mpin_client, monkeypatch):
    client, url = mpin_client
    _authenticate(client, url)
    monkeypatch.setattr(
        auth_routes, "supabase_verify_password", lambda *_args, **_kwargs: False
    )
    denied = client.post(
        "/auth/mpin/enroll", json={"mpin": "1234", "password": "wrong"}, headers=_csrf()
    )
    assert denied.status_code == 401
    monkeypatch.setattr(
        auth_routes, "supabase_verify_password", lambda *_args, **_kwargs: True
    )
    enrolled = client.post(
        "/auth/mpin/enroll", json={"mpin": "1234", "password": "valid"}, headers=_csrf()
    )
    assert enrolled.status_code == 200
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*),count(distinct salt) from public.mpin_credentials")
            assert cursor.fetchone() == (1, 1)
            cursor.execute("select count(*) from public.security_events where event_name='security.mpin.enrolled'")
            assert cursor.fetchone()[0] == 1
    body = enrolled.get_data(as_text=True).lower()
    assert "1234" not in body and "verifier" not in body and "pepper" not in body


def test_unsupported_role_cannot_enroll(mpin_client):
    client, url = mpin_client
    _authenticate(client, url, role="platform_admin")
    response = client.post(
        "/auth/mpin/enroll", json={"mpin": "1234", "password": "valid"}, headers=_csrf()
    )
    assert response.status_code == 403
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*) from public.mpin_credentials")
            assert cursor.fetchone()[0] == 0


def test_missing_pepper_fails_mpin_endpoint_closed_but_password_unlock_works(mpin_client, monkeypatch):
    client, url = mpin_client
    _authenticate(client, url, with_mpin="1234")
    monkeypatch.delenv("DIGITRANSX_MPIN_PEPPER", raising=False)
    assert client.get("/auth/mpin/status").status_code == 503
    _lock(client)
    response = client.post(
        "/auth/mpin/password-unlock",
        json={"identifier": "mpin@example.invalid", "password": "valid"},
        headers=_csrf(),
    )
    assert response.status_code == 200
    assert client.get("/business").status_code == 200


def test_lock_transition_is_423_once_and_status_logout_remain_available(mpin_client):
    client, url = mpin_client
    _authenticate(client, url, with_mpin="1234")
    _lock(client)
    assert client.get("/business").status_code == 423
    status = client.get("/auth/mpin/status")
    assert status.status_code == 200 and status.get_json()["access_locked"] is True
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*) from public.security_events where event_name='security.session.access_locked'")
            assert cursor.fetchone()[0] == 1
    logout = client.post("/auth/logout", headers=_csrf())
    assert logout.status_code == 200


def test_password_unlock_rotates_only_access_proof(mpin_client, monkeypatch):
    client, url = mpin_client
    state = _authenticate(client, url, with_mpin="1234")
    before = _session_snapshot(url, state["session_id"])
    _lock(client)
    mismatch = client.post(
        "/auth/mpin/password-unlock",
        json={"identifier": "someone@example.invalid", "password": "valid"},
        headers=_csrf(),
    )
    monkeypatch.setattr(
        auth_routes, "supabase_verify_password", lambda *_args, **_kwargs: False
    )
    wrong = client.post(
        "/auth/mpin/password-unlock",
        json={"identifier": "mpin@example.invalid", "password": "wrong"},
        headers=_csrf(),
    )
    assert mismatch.status_code == wrong.status_code == 401
    assert mismatch.get_json() == wrong.get_json()
    monkeypatch.setattr(
        auth_routes, "supabase_verify_password", lambda *_args, **_kwargs: True
    )
    response = client.post(
        "/auth/mpin/password-unlock",
        json={"identifier": "mpin@example.invalid", "password": "valid"},
        headers=_csrf(),
    )
    assert response.status_code == 200
    proof_cookie = next(
        value for value in response.headers.getlist("Set-Cookie")
        if value.startswith(auth_helpers.ACCESS_PROOF_COOKIE_NAME + "=")
    )
    assert "Max-Age" not in proof_cookie and "Expires" not in proof_cookie
    assert "HttpOnly" in proof_cookie and "SameSite=Lax" in proof_cookie
    after = _session_snapshot(url, state["session_id"])
    assert after[:3] == before[:3]
    assert after[3] is False
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*) from public.user_sessions")
            assert cursor.fetchone()[0] == 1
    assert client.get("/business").status_code == 200
    # The password proof is recent and session-bound, so disable needs no
    # second credential in the same bounded window.
    disabled = client.post("/auth/mpin/disable", json={}, headers=_csrf())
    assert disabled.status_code == 200


def test_mpin_unlock_fifth_failure_permanently_locks_without_disclosure(mpin_client):
    client, url = mpin_client
    _authenticate(client, url, with_mpin="1234")
    _lock(client)
    responses = [
        client.post("/auth/mpin/unlock", json={"mpin": "9999"}, headers=_csrf())
        for _ in range(5)
    ]
    assert [response.status_code for response in responses] == [401, 401, 401, 401, 423]
    combined = " ".join(response.get_data(as_text=True).lower() for response in responses)
    assert "remaining" not in combined and "attempts" not in combined and "threshold" not in combined
    again = client.post("/auth/mpin/unlock", json={"mpin": "1234"}, headers=_csrf())
    assert again.status_code == 423
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select failed_attempts,permanently_locked from public.mpin_credentials")
            assert cursor.fetchone() == (5, True)
            cursor.execute("select event_name,count(*) from public.security_events where event_name like 'security.mpin.%' group by event_name")
            assert dict(cursor.fetchall()) == {
                "security.mpin.unlock_failed": 4,
                "security.mpin.locked": 1,
            }


def test_password_reset_clears_permanent_lock_and_new_mpin_unlocks(mpin_client):
    client, url = mpin_client
    _authenticate(client, url, with_mpin="1234")
    _lock(client)
    for _ in range(5):
        client.post("/auth/mpin/unlock", json={"mpin": "9999"}, headers=_csrf())
    blocked_reset = client.post(
        "/auth/mpin/reset",
        json={"new_mpin": "5678", "password": "valid"},
        headers=_csrf(),
    )
    assert blocked_reset.status_code == 423
    password_unlock = client.post(
        "/auth/mpin/password-unlock",
        json={"identifier": "mpin@example.invalid", "password": "valid"},
        headers=_csrf(),
    )
    assert password_unlock.status_code == 200
    reset = client.post(
        "/auth/mpin/reset",
        json={"new_mpin": "5678", "password": "valid"},
        headers=_csrf(),
    )
    assert reset.status_code == 200
    _lock(client)
    old = client.post("/auth/mpin/unlock", json={"mpin": "1234"}, headers=_csrf())
    assert old.status_code == 401
    unlocked = client.post("/auth/mpin/unlock", json={"mpin": "5678"}, headers=_csrf())
    assert unlocked.status_code == 200
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select failed_attempts,permanently_locked from public.mpin_credentials")
            assert cursor.fetchone() == (0, False)
            cursor.execute("select count(*) from public.security_events where event_name='security.mpin.reset_completed'")
            assert cursor.fetchone()[0] == 1
            cursor.execute("select count(*) from public.security_events where event_name='security.session.access_locked'")
            assert cursor.fetchone()[0] == 1


def test_change_invalidates_old_and_disable_removes_credential(mpin_client):
    client, url = mpin_client
    _authenticate(client, url, with_mpin="1234")
    changed = client.post(
        "/auth/mpin/change",
        json={"current_mpin": "1234", "new_mpin": "5678"},
        headers=_csrf(),
    )
    assert changed.status_code == 200
    _lock(client)
    assert client.post("/auth/mpin/unlock", json={"mpin": "1234"}, headers=_csrf()).status_code == 401
    assert client.post("/auth/mpin/unlock", json={"mpin": "5678"}, headers=_csrf()).status_code == 200
    disabled = client.post(
        "/auth/mpin/disable", json={"current_mpin": "5678"}, headers=_csrf()
    )
    assert disabled.status_code == 200
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*) from public.mpin_credentials")
            assert cursor.fetchone()[0] == 0


def test_unlock_requires_exact_valid_session_and_device(mpin_client):
    client, url = mpin_client
    state = _authenticate(client, url, with_mpin="1234")
    _lock(client)
    client.set_cookie(auth_helpers.DEVICE_COOKIE_NAME, secrets.token_urlsafe(32))
    response = client.post("/auth/mpin/unlock", json={"mpin": "1234"}, headers=_csrf())
    assert response.status_code == 401
    assert "1234" not in response.get_data(as_text=True)
    client.set_cookie(auth_helpers.DEVICE_COOKIE_NAME, state["device_raw"])
    client.delete_cookie(auth_helpers.SESSION_TOKEN_COOKIE_NAME)
    assert client.post("/auth/mpin/unlock", json={"mpin": "1234"}, headers=_csrf()).status_code == 401


def test_unlock_rollback_issues_no_cookie_and_preserves_lock(
    mpin_client, monkeypatch, caplog
):
    client, url = mpin_client
    state = _authenticate(client, url, with_mpin="1234")
    _lock(client)
    original = auth_routes.write_security_event

    def fail_success(executor, name, *args, **kwargs):
        if name == "security.mpin.unlock_succeeded":
            raise RuntimeError("forced rollback")
        return original(executor, name, *args, **kwargs)

    monkeypatch.setattr(auth_routes, "write_security_event", fail_success)
    response = client.post("/auth/mpin/unlock", json={"mpin": "1234"}, headers=_csrf())
    assert response.status_code == 503
    assert "1234" not in response.get_data(as_text=True)
    assert "1234" not in caplog.text and PEPPER not in caplog.text
    assert not any(
        value.startswith(auth_helpers.ACCESS_PROOF_COOKIE_NAME + "=")
        and not value.startswith(auth_helpers.ACCESS_PROOF_COOKIE_NAME + "=;")
        for value in response.headers.getlist("Set-Cookie")
    )
    assert _session_snapshot(url, state["session_id"])[3] is True


def test_atomic_concurrent_failures_reach_exact_permanent_lock(mpin_database_url, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_MPIN_PEPPER", PEPPER)
    with psycopg2.connect(mpin_database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "insert into public.users(email,cnic,role,legacy_role) values"
                "('concurrent@example.invalid','2222222222222','customer','service_seeker') returning id"
            )
            user_id = cursor.fetchone()[0]
            salt, verifier = mpin_service.build_credential("1234")
            cursor.execute(
                "insert into public.mpin_credentials(user_id,verifier,salt,kdf_version) values(%s,%s,%s,1)",
                (user_id, verifier, salt),
            )

    barrier = threading.Barrier(5)
    outcomes = []
    lock = threading.Lock()

    def worker():
        conn = psycopg2.connect(mpin_database_url)
        try:
            barrier.wait()
            result, _ = mpin_service.record_failure(Db(conn), user_id)
            conn.commit()
            with lock:
                outcomes.append(result)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert sorted(outcomes) == ["failed", "failed", "failed", "failed", "locked"]
    with psycopg2.connect(mpin_database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select failed_attempts,permanently_locked from public.mpin_credentials where user_id=%s", (user_id,))
            assert cursor.fetchone() == (5, True)


def test_concurrent_unlock_responses_leave_one_database_usable_proof(mpin_client):
    client, url = mpin_client
    state = _authenticate(client, url, with_mpin="1234")
    _lock(client)
    cookie_names = (
        auth_helpers.DEVICE_COOKIE_NAME,
        auth_helpers.SESSION_TOKEN_COOKIE_NAME,
        client.application.config.get("SESSION_COOKIE_NAME", "session"),
    )
    cookie_values = {
        name: client.get_cookie(name).value for name in cookie_names
    }
    clients = [client.application.test_client(), client.application.test_client()]
    for clone in clients:
        for name, value in cookie_values.items():
            clone.set_cookie(name, value)
    barrier = threading.Barrier(2)
    responses = []
    guard = threading.Lock()

    def unlock(clone):
        barrier.wait()
        response = clone.post(
            "/auth/mpin/unlock", json={"mpin": "1234"}, headers=_csrf()
        )
        with guard:
            responses.append(response)

    threads = [threading.Thread(target=unlock, args=(clone,)) for clone in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert len(responses) == 2 and any(response.status_code == 200 for response in responses)
    raw_proofs = []
    for response in responses:
        for value in response.headers.getlist("Set-Cookie"):
            if value.startswith(auth_helpers.ACCESS_PROOF_COOKIE_NAME + "="):
                raw = value.split(";", 1)[0].split("=", 1)[1]
                if raw:
                    raw_proofs.append(raw)
    assert raw_proofs
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            matches = 0
            for raw in raw_proofs:
                cursor.execute(
                    "select count(*) from public.user_sessions where session_id=%s "
                    "and access_proof_digest=%s and not access_locked",
                    (state["session_id"], hashlib.sha256(raw.encode()).digest()),
                )
                matches += cursor.fetchone()[0]
            assert matches == 1


def test_migration_converges_reapplies_invalidates_legacy_and_rejects_corruption():
    main_schema = schema_before_migration_or_skip(MIGRATION)
    migration = MIGRATION.read_text(encoding="utf-8")
    activity_migration = GENUINE_ACTIVITY_MIGRATION.read_text(encoding="utf-8")
    assert "cascade" not in migration.lower()
    sequential_url, sequential_cleanup = make_disposable(_local_url(), STUBS, main_schema)
    # Compare at the genuine-activity boundary. Today's origin/main includes
    # the later step-up migration, whose stricter final signature correctly
    # rejects replay of this older migration.
    fresh_url, fresh_cleanup = make_disposable(
        _local_url(), STUBS, schema_before_migration_or_skip(MPIN_STEP_UP_MIGRATION)
    )
    try:
        sequential = psycopg2.connect(sequential_url)
        fresh = psycopg2.connect(fresh_url)
        try:
            with sequential.cursor() as cursor:
                cursor.execute(
                    "insert into public.users(email,cnic,mpin_hash,mpin_enabled) "
                    "values('legacy@example.invalid','3333333333333','legacy-verifier',true)"
                )
                cursor.execute(migration)
                cursor.execute(migration)
            sequential.commit()
            with sequential.cursor() as cursor:
                cursor.execute("alter table public.mpin_credentials add column corrupt text")
                with pytest.raises((psycopg2.Error, errors.RaiseException)):
                    cursor.execute(migration)
            sequential.rollback()
            with sequential.cursor() as cursor:
                cursor.execute(activity_migration)
                cursor.execute(activity_migration)
            sequential.commit()
            with fresh.cursor() as cursor:
                cursor.execute(activity_migration)
                cursor.execute(activity_migration)
            fresh.commit()
            assert _semantic_signature(sequential) == _semantic_signature(fresh) == "b57a59369062e678a7b269cd61d4e01e"
            for conn in (sequential, fresh):
                with conn.cursor() as cursor:
                    cursor.execute(
                        "select count(*),count(*) filter(where integrated),"
                        "count(*) filter(where lifecycle_status='planned' and not integrated),"
                        "count(*) filter(where writable and not integrated) "
                        "from public.canonical_event_catalog_projection"
                    )
                    assert cursor.fetchone() == (170, 21, 141, 135)
                    cursor.execute("select count(*) from public.mpin_credentials")
                    assert cursor.fetchone()[0] == 0
                    cursor.execute("select count(*) from public.users where mpin_hash is not null or mpin_enabled")
                    assert cursor.fetchone()[0] == 0
            with sequential.cursor() as cursor:
                cursor.execute("select count(*) from information_schema.columns where table_schema='public' and table_name='mpin_credentials' and column_name='corrupt'")
                assert cursor.fetchone()[0] == 0
        finally:
            sequential.close()
            fresh.close()
    finally:
        sequential_cleanup()
        fresh_cleanup()


def test_schema_catalog_acl_and_step_up_contract_remain_bounded(mpin_database_url):
    with psycopg2.connect(mpin_database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select event_name from public.canonical_event_catalog_projection "
                "where integrated and event_name in %s",
                (tuple(NEW_INTEGRATIONS),),
            )
            assert {row[0] for row in cursor.fetchall()} == NEW_INTEGRATIONS
            cursor.execute(
                "select event_name,integrated from public.canonical_event_catalog_projection "
                "where event_name like 'security.mpin.step_up_%' order by event_name"
            )
            assert cursor.fetchall() == [
                ("security.mpin.step_up_consumed", False),
                ("security.mpin.step_up_failed", True),
                ("security.mpin.step_up_reconciliation_required", False),
                ("security.mpin.step_up_succeeded", True),
            ]
            cursor.execute(
                "select count(*) from information_schema.role_table_grants where table_schema='public' "
                "and table_name='mpin_credentials' and grantee in ('PUBLIC','anon','authenticated')"
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select array_agg(privilege_type::text order by privilege_type) from information_schema.role_table_grants "
                "where table_schema='public' and table_name='mpin_credentials' and grantee='service_role'"
            )
            assert cursor.fetchone()[0] == ["DELETE", "INSERT", "SELECT", "UPDATE"]
            cursor.execute(
                "select count(*) from information_schema.views where table_schema='public' "
                "and view_definition ilike '%mpin_credentials%'"
            )
            assert cursor.fetchone()[0] == 0


def test_no_frontend_access_proof_storage_or_sensitive_response_fields():
    frontend = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "frontend-react/src").rglob("*")
        if path.is_file()
    ).lower()
    assert "dtx_access_proof" not in frontend
    route_text = (ROOT / "backend/auth/routes.py").read_text(encoding="utf-8").lower()
    for forbidden in (
        '"verifier"', '"salt"', '"pepper_version"', '"failed_attempts"',
        '"remaining_attempts"', '"access_proof"', '"digest"',
    ):
        assert forbidden not in route_text


def test_application_registers_all_mpin_operations_under_api_auth(monkeypatch):
    import shared.db as shared_db

    monkeypatch.setattr(shared_db, "check_connection", lambda: None)
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", "0")
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    sys.modules.pop("app", None)
    app = importlib.import_module("app").app

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert {
        "/api/auth/mpin/status",
        "/api/auth/mpin/enroll",
        "/api/auth/mpin/unlock",
        "/api/auth/mpin/password-unlock",
        "/api/auth/mpin/change",
        "/api/auth/mpin/disable",
        "/api/auth/mpin/reset",
        "/api/auth/mpin/step-up",
    } <= rules
