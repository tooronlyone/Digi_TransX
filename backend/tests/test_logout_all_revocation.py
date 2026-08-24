"""PostgreSQL-backed proofs for user-initiated logout-all revocation."""

from contextlib import contextmanager
import base64
import hashlib
import secrets
import threading
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask
import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

from auth import logout_all_service, mpin_service, routes as auth_routes, step_up_service
from auth.session_service import create_session
from auth.trusted_device_service import establish_after_full_login
import auth.helpers as auth_helpers
from shared.db import Db
from shared.supabase_client import PasswordProviderUnavailable
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url


ROOT = Path(__file__).resolve().parents[2]
CSRF = {"X-CSRF-Token": "logout-all-csrf"}


def _loopback_url():
    url = require_test_db_url()
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    return url


@pytest.fixture(scope="module")
def logout_all_database_url():
    url, cleanup = make_disposable(
        _loopback_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def logout_all_client(logout_all_database_url, monkeypatch):
    active_contexts = {"count": 0}

    @contextmanager
    def test_open_db():
        conn = psycopg2.connect(logout_all_database_url)
        active_contexts["count"] += 1
        try:
            wrapper = Db(conn)
            yield wrapper
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            active_contexts["count"] -= 1
            conn.close()

    monkeypatch.setattr(auth_helpers, "open_db", test_open_db)
    monkeypatch.setattr(auth_routes, "open_db", test_open_db)
    monkeypatch.setattr(logout_all_service, "open_db", test_open_db)
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    monkeypatch.setenv(
        "DIGITRANSX_MPIN_PEPPER",
        base64.urlsafe_b64encode(b"p" * 32).decode("ascii").rstrip("="),
    )

    app = Flask(__name__)
    app.config.update(SECRET_KEY="logout-all-test", SESSION_COOKIE_SECURE=False)
    app.register_blueprint(auth_routes.auth_blueprint)
    client = app.test_client()
    yield client, logout_all_database_url, active_contexts

    with psycopg2.connect(logout_all_database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "TRUNCATE security_events,business_audit_events,login_activity,"
                "trusted_devices,user_action_logs,users RESTART IDENTITY CASCADE"
            )


def _seed_user(url, suffix, *, role="service_seeker", blocked=False):
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users(full_name,email,phone,cnic,role,legacy_role,is_blocked)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    f"Logout All {suffix}",
                    f"logout-all-{suffix}@example.invalid",
                    f"0300{int(hashlib.sha256(suffix.encode()).hexdigest()[:7], 16):07d}"[:11],
                    str(int(hashlib.sha256((suffix + 'cnic').encode()).hexdigest()[:13], 16))[:13].zfill(13),
                    "admin" if role == "platform_admin" else "customer",
                    role,
                    blocked,
                ),
            )
            return cursor.fetchone()[0]


def _add_active_auth(url, user_id):
    raw_device = secrets.token_urlsafe(32)
    raw_session = secrets.token_urlsafe(32)
    raw_proof = secrets.token_urlsafe(32)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO trusted_devices(token_digest,user_id,expires_at) "
                "VALUES(%s,%s,now()+interval '30 days') RETURNING id",
                (hashlib.sha256(raw_device.encode()).digest(), user_id),
            )
            device_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO user_sessions(
                    user_id,token_digest,trusted_device_id,inactivity_expires_at,
                    absolute_expires_at,access_proof_digest,access_proof_expires_at
                ) VALUES(
                    %s,%s,%s,now()+interval '7 days',now()+interval '30 days',
                    %s,now()+interval '8 hours'
                ) RETURNING session_id
                """,
                (
                    user_id,
                    hashlib.sha256(raw_session.encode()).digest(),
                    device_id,
                    hashlib.sha256(raw_proof.encode()).digest(),
                ),
            )
            session_id = cursor.fetchone()[0]
    return {
        "device": raw_device,
        "session": raw_session,
        "proof": raw_proof,
        "device_id": device_id,
        "session_id": session_id,
    }


def _authenticate(client, auth):
    client.set_cookie("dtx_device_token", auth["device"])
    client.set_cookie("dtx_session_token", auth["session"])
    client.set_cookie("dtx_access_proof", auth["proof"])
    with client.session_transaction() as state:
        state["csrf_token"] = CSRF["X-CSRF-Token"]


def _rows(url, sql, params=()):
    with psycopg2.connect(url) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]


def _seed_inactive_rows(url, user_id):
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO trusted_devices(
                    token_digest,user_id,created_at,last_used_at,expires_at
                ) VALUES(%s,%s,now()-interval '40 days',now()-interval '39 days',
                         now()-interval '10 days') RETURNING id
                """,
                (secrets.token_bytes(32), user_id),
            )
            expired_device = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO trusted_devices(token_digest,user_id,expires_at,revoked_at)
                VALUES(%s,%s,now()+interval '10 days',now()) RETURNING id
                """,
                (secrets.token_bytes(32), user_id),
            )
            revoked_device = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO user_sessions(
                    user_id,token_digest,trusted_device_id,created_at,authenticated_at,
                    last_genuine_activity_at,inactivity_expires_at,absolute_expires_at,
                    updated_at
                ) VALUES(
                    %s,%s,%s,now()-interval '10 days',now()-interval '10 days',
                    now()-interval '9 days',now()-interval '1 day',now()+interval '1 day',now()
                ) RETURNING session_id
                """,
                (user_id, secrets.token_bytes(32), expired_device),
            )
            expired_session = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO user_sessions(
                    user_id,token_digest,trusted_device_id,inactivity_expires_at,
                    absolute_expires_at,revoked_at,revocation_reason
                ) VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',
                         now(),'logout') RETURNING session_id
                """,
                (user_id, secrets.token_bytes(32), revoked_device),
            )
            revoked_session = cursor.fetchone()[0]
    return expired_device, revoked_device, expired_session, revoked_session


def _password_ok(active_contexts):
    def verify(email, password, *, raise_provider_errors):
        assert active_contexts["count"] == 0
        assert email.endswith("@example.invalid")
        assert password == "correct horse battery staple"
        assert raise_provider_errors is True
        return True

    return verify


def test_password_logout_all_is_user_scoped_atomic_and_exact(logout_all_client, monkeypatch):
    client, url, active_contexts = logout_all_client
    user_id = _seed_user(url, "password", role="platform_admin")
    other_id = _seed_user(url, "other", role="platform_admin")
    current = _add_active_auth(url, user_id)
    extra = _add_active_auth(url, user_id)
    other = _add_active_auth(url, other_id)
    inactive = _seed_inactive_rows(url, user_id)
    _authenticate(client, current)
    monkeypatch.setattr(
        logout_all_service, "supabase_verify_password", _password_ok(active_contexts)
    )

    challenge = client.post("/auth/logout-all", json={}, headers=CSRF)
    assert challenge.status_code == 428
    assert challenge.get_json()["code"] == "current_password_required"
    response = client.post(
        "/auth/logout-all",
        json={"password": "correct horse battery staple"},
        headers=CSRF,
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json() == {
        "success": True,
        "session_count": 2,
        "trusted_device_count": 2,
    }
    cookies = response.headers.getlist("Set-Cookie")
    for name in ("dtx_session_token", "dtx_device_token", "dtx_access_proof", "session"):
        assert any(item.startswith(f"{name}=") and "Expires=" in item for item in cookies)

    active_sessions = _rows(
        url,
        "SELECT session_id,revocation_reason FROM user_sessions "
        "WHERE session_id IN (%s,%s) ORDER BY session_id",
        (current["session_id"], extra["session_id"]),
    )
    assert len(active_sessions) == 2
    assert {row["revocation_reason"] for row in active_sessions} == {"logout_all"}
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (other["session_id"],))[0]["revoked_at"] is None
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (other["device_id"],))[0]["revoked_at"] is None
    expired_device, revoked_device, expired_session, revoked_session = inactive
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (expired_device,))[0]["revoked_at"] is None
    assert _rows(url, "SELECT revocation_reason FROM user_sessions WHERE session_id=%s", (expired_session,))[0]["revocation_reason"] is None
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (revoked_device,))[0]["revoked_at"] is not None
    assert _rows(url, "SELECT revocation_reason FROM user_sessions WHERE session_id=%s", (revoked_session,))[0]["revocation_reason"] == "logout"

    events = _rows(
        url,
        "SELECT event_name,metadata,session_ref,device_ref FROM security_events "
        "ORDER BY event_name,event_id",
    )
    names = [row["event_name"] for row in events]
    assert names.count("security.session.revoked") == 2
    assert names.count("security.trusted_device.removed") == 2
    assert names.count("security.logout.completed") == 1
    assert all(
        row["metadata"]["result_code"] == "logout_all"
        for row in events
        if row["event_name"] in {
            "security.session.revoked", "security.trusted_device.removed"
        }
    )

    before = len(events)
    _authenticate(client, current)
    repeated = client.post(
        "/auth/logout-all",
        json={"password": "correct horse battery staple"},
        headers=CSRF,
    )
    assert repeated.status_code == 401
    assert len(_rows(url, "SELECT event_id FROM security_events")) == before


def test_mpin_binding_expiry_replay_and_locked_password_recovery(logout_all_client, monkeypatch):
    client, url, active_contexts = logout_all_client
    user_id = _seed_user(url, "mpin")
    current = _add_active_auth(url, user_id)
    _authenticate(client, current)
    salt, verifier = mpin_service.build_credential("1234")
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO mpin_credentials(user_id,verifier,salt,kdf_version) "
                "VALUES(%s,%s,%s,1)",
                (user_id, verifier, salt),
            )

    challenged = client.post("/auth/logout-all", json={}, headers=CSRF)
    assert challenged.status_code == 428
    action = challenged.get_json()["action"]
    assert action == {
        "action_key": "security.logout_all",
        "resource_type": "account_security",
        "resource_id": 1,
    }
    issued = client.post(
        "/auth/mpin/step-up", json={"mpin": "1234", "action": action}, headers=CSRF
    )
    assert issued.status_code == 200, issued.get_data(as_text=True)
    proof = issued.get_json()["authorization_proof"]

    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE mpin_step_up_authorizations
                   SET issued_at=now()-interval '4 minutes',
                       expires_at=now()-interval '1 minute'
                """
            )
    expired = client.post(
        "/auth/logout-all", json={}, headers={**CSRF, step_up_service.STEP_UP_PROOF_HEADER: proof}
    )
    assert expired.status_code == 428
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (current["session_id"],))[0]["revoked_at"] is None

    issued = client.post(
        "/auth/mpin/step-up", json={"mpin": "1234", "action": action}, headers=CSRF
    )
    assert issued.status_code == 200
    proof = issued.get_json()["authorization_proof"]

    alternate = _add_active_auth(url, user_id)
    _authenticate(client, alternate)
    binding_mismatch = client.post(
        "/auth/logout-all", json={}, headers={**CSRF, step_up_service.STEP_UP_PROOF_HEADER: proof}
    )
    assert binding_mismatch.status_code == 428
    _authenticate(client, current)

    with psycopg2.connect(url) as conn:
        db = Db(conn)
        assert mpin_service.lock_credential(db, user_id)
        assert mpin_service.replace(db, user_id, "4321")
        conn.commit()
    rotated = client.post(
        "/auth/logout-all", json={}, headers={**CSRF, step_up_service.STEP_UP_PROOF_HEADER: proof}
    )
    assert rotated.status_code == 428

    issued = client.post(
        "/auth/mpin/step-up", json={"mpin": "4321", "action": action}, headers=CSRF
    )
    assert issued.status_code == 200
    proof = issued.get_json()["authorization_proof"]
    completed = client.post(
        "/auth/logout-all", json={}, headers={**CSRF, step_up_service.STEP_UP_PROOF_HEADER: proof}
    )
    assert completed.status_code == 200
    assert len(_rows(url, "SELECT authorization_id FROM mpin_step_up_authorizations WHERE state='consumed'")) == 1
    assert len(_rows(url, "SELECT event_id FROM security_events WHERE event_name='security.mpin.step_up_consumed'")) == 1

    replay_count = len(_rows(url, "SELECT event_id FROM security_events"))
    _authenticate(client, current)
    replay = client.post(
        "/auth/logout-all", json={}, headers={**CSRF, step_up_service.STEP_UP_PROOF_HEADER: proof}
    )
    assert replay.status_code == 401
    assert len(_rows(url, "SELECT event_id FROM security_events")) == replay_count

    recovery_id = _seed_user(url, "locked-recovery")
    recovery = _add_active_auth(url, recovery_id)
    salt, verifier = mpin_service.build_credential("5678")
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO mpin_credentials(
                    user_id,verifier,salt,kdf_version,failed_attempts,
                    permanently_locked,locked_at
                ) VALUES(%s,%s,%s,1,5,true,now())
                """,
                (recovery_id, verifier, salt),
            )
    _authenticate(client, recovery)
    monkeypatch.setattr(
        logout_all_service, "supabase_verify_password", _password_ok(active_contexts)
    )
    required = client.post("/auth/logout-all", json={}, headers=CSRF)
    assert required.status_code == 428
    assert required.get_json()["code"] == "current_password_required"
    recovered = client.post(
        "/auth/logout-all",
        json={"password": "correct horse battery staple"},
        headers=CSRF,
    )
    assert recovered.status_code == 200


def test_anonymous_blocked_stale_locked_and_csrf_fail_closed(logout_all_client):
    client, url, _ = logout_all_client
    assert client.post("/auth/logout-all", json={}, headers=CSRF).status_code == 401

    user_id = _seed_user(url, "negative", role="platform_admin")
    current = _add_active_auth(url, user_id)
    _authenticate(client, current)
    assert client.post("/auth/logout-all", json={}).status_code == 403

    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE user_sessions SET access_locked=true,access_locked_at=now(),
                    access_proof_digest=NULL,access_proof_expires_at=NULL,updated_at=now()
                WHERE session_id=%s
                """,
                (current["session_id"],),
            )
    assert client.post("/auth/logout-all", json={}, headers=CSRF).status_code == 423
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (current["session_id"],))[0]["revoked_at"] is None

    fresh = _add_active_auth(url, user_id)
    _authenticate(client, fresh)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET is_blocked=true WHERE id=%s", (user_id,))
    assert client.post("/auth/logout-all", json={}, headers=CSRF).status_code == 401
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (fresh["session_id"],))[0]["revoked_at"] is None

    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET is_blocked=false WHERE id=%s", (user_id,))
            cursor.execute(
                "UPDATE user_sessions SET revoked_at=now(),revocation_reason='logout' "
                "WHERE session_id=%s",
                (fresh["session_id"],),
            )
    _authenticate(client, fresh)
    assert client.post("/auth/logout-all", json={}, headers=CSRF).status_code == 401
    assert _rows(url, "SELECT event_id FROM security_events") == []


def test_provider_failure_and_event_failure_never_partially_revoke(logout_all_client, monkeypatch):
    client, url, _ = logout_all_client
    user_id = _seed_user(url, "rollback", role="platform_admin")
    current = _add_active_auth(url, user_id)
    extra = _add_active_auth(url, user_id)
    _authenticate(client, current)

    def unavailable(*_args, **_kwargs):
        raise PasswordProviderUnavailable(status=503, code="password_provider_unavailable")

    monkeypatch.setattr(logout_all_service, "supabase_verify_password", unavailable)
    provider = client.post(
        "/auth/logout-all", json={"password": "not logged"}, headers=CSRF
    )
    assert provider.status_code == 503
    assert provider.get_json() == {
        "success": False,
        "code": "password_provider_unavailable",
        "message": "Unable to verify current credentials.",
    }

    monkeypatch.setattr(logout_all_service, "supabase_verify_password", lambda *_args, **_kwargs: True)
    original_writer = logout_all_service.write_security_event
    calls = {"count": 0}

    def fail_event(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("synthetic event failure")
        return original_writer(*args, **kwargs)

    monkeypatch.setattr(logout_all_service, "write_security_event", fail_event)
    failed = client.post(
        "/auth/logout-all", json={"password": "correct"}, headers=CSRF
    )
    assert failed.status_code == 503
    for session_id in (current["session_id"], extra["session_id"]):
        assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (session_id,))[0]["revoked_at"] is None
    assert _rows(url, "SELECT event_id FROM security_events") == []


def test_concurrent_login_and_device_rotation_are_deterministic(logout_all_client, monkeypatch):
    _, url, _ = logout_all_client

    def presented(user_id, suffix):
        return {
            "id": user_id,
            "email": f"logout-all-{suffix}@example.invalid",
            "auth_id": None,
            "role": "platform_admin",
        }

    user_id = _seed_user(url, "concurrent-login", role="platform_admin")
    current = _add_active_auth(url, user_id)
    user_locked = threading.Event()
    continue_login = threading.Event()
    entered_logout_lock = threading.Event()
    concurrent_ids = {}
    thread_errors = []

    def concurrent_login():
        try:
            with psycopg2.connect(url) as conn:
                db = Db(conn)
                db.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user_id,))
                user_locked.set()
                assert continue_login.wait(10)
                _, device_id, _ = establish_after_full_login(db, user_id)
                _, _, session_id = create_session(
                    db, user_id, trusted_device_id=device_id
                )
                concurrent_ids.update(device_id=device_id, session_id=session_id)
        except Exception as exc:  # pragma: no cover - asserted below
            thread_errors.append(exc)

    original_lock = logout_all_service.lock_session_user_and_device

    def tracked_lock(*args, **kwargs):
        entered_logout_lock.set()
        return original_lock(*args, **kwargs)

    monkeypatch.setattr(logout_all_service, "lock_session_user_and_device", tracked_lock)
    login_thread = threading.Thread(target=concurrent_login)
    login_thread.start()
    assert user_locked.wait(10)
    result_holder = {}

    def revoke_after_login():
        try:
            result_holder["result"] = logout_all_service.logout_all(
                presented_user=presented(user_id, "concurrent-login"),
                presented_session={"session_id": current["session_id"]},
                raw_session_token=current["session"],
                raw_device_token=current["device"],
                raw_access_proof=current["proof"],
                raw_step_up_proof="",
                password="verified",
                request_id="auth.logout_all.concurrent_login",
                password_verifier=lambda *_args, **_kwargs: True,
            )
        except Exception as exc:  # pragma: no cover - asserted below
            thread_errors.append(exc)

    logout_thread = threading.Thread(target=revoke_after_login)
    logout_thread.start()
    assert entered_logout_lock.wait(10)
    continue_login.set()
    login_thread.join(10)
    logout_thread.join(10)
    assert not login_thread.is_alive() and not logout_thread.is_alive()
    assert thread_errors == []
    assert result_holder["result"].status == "success"
    assert result_holder["result"].session_count == 2
    assert result_holder["result"].trusted_device_count == 2
    assert _rows(
        url,
        "SELECT revocation_reason FROM user_sessions WHERE session_id=%s",
        (concurrent_ids["session_id"],),
    )[0]["revocation_reason"] == "logout_all"

    race_id = _seed_user(url, "concurrent-logout", role="platform_admin")
    race_current = _add_active_auth(url, race_id)
    race_extra = _add_active_auth(url, race_id)
    start_race = threading.Barrier(3)
    race_results = []
    race_errors = []

    def concurrent_logout(index):
        try:
            start_race.wait(10)
            race_results.append(logout_all_service.logout_all(
                presented_user=presented(race_id, "concurrent-logout"),
                presented_session={"session_id": race_current["session_id"]},
                raw_session_token=race_current["session"],
                raw_device_token=race_current["device"],
                raw_access_proof=race_current["proof"],
                raw_step_up_proof="",
                password="verified",
                request_id=f"auth.logout_all.concurrent_{index}",
                password_verifier=lambda *_args, **_kwargs: True,
            ))
        except Exception as exc:  # pragma: no cover - asserted below
            race_errors.append(exc)

    race_threads = [
        threading.Thread(target=concurrent_logout, args=(index,))
        for index in range(2)
    ]
    for thread in race_threads:
        thread.start()
    start_race.wait(10)
    for thread in race_threads:
        thread.join(10)
    assert all(not thread.is_alive() for thread in race_threads)
    assert race_errors == []
    assert sorted(result.status for result in race_results) == [
        "authentication_required", "success"
    ]
    assert all(
        row["revocation_reason"] == "logout_all"
        for row in _rows(
            url,
            "SELECT revocation_reason FROM user_sessions WHERE session_id IN (%s,%s)",
            (race_current["session_id"], race_extra["session_id"]),
        )
    )
    race_events = _rows(
        url,
        "SELECT event_name FROM security_events WHERE subject_user_id=%s",
        (race_id,),
    )
    assert [row["event_name"] for row in race_events].count(
        "security.session.revoked"
    ) == 2
    assert [row["event_name"] for row in race_events].count(
        "security.trusted_device.removed"
    ) == 2
    assert [row["event_name"] for row in race_events].count(
        "security.logout.completed"
    ) == 1
    rotation_id = _seed_user(url, "concurrent-rotation", role="platform_admin")
    rotation_current = _add_active_auth(url, rotation_id)
    rotation_locked = threading.Event()
    continue_rotation = threading.Event()
    rotation_errors = []

    def concurrent_rotation():
        try:
            with psycopg2.connect(url) as conn:
                db = Db(conn)
                db.execute(
                    "SELECT id FROM users WHERE id=%s FOR UPDATE", (rotation_id,)
                )
                rotation_locked.set()
                assert continue_rotation.wait(10)
                _, device_id, device_event = establish_after_full_login(
                    db, rotation_id, rotation_current["device"]
                )
                assert device_event == "security.trusted_device.rotated"
                create_session(db, rotation_id, trusted_device_id=device_id)
        except Exception as exc:  # pragma: no cover - asserted below
            rotation_errors.append(exc)

    entered_logout_lock.clear()
    rotation_thread = threading.Thread(target=concurrent_rotation)
    rotation_thread.start()
    assert rotation_locked.wait(10)
    rotation_result = {}

    def revoke_during_rotation():
        try:
            rotation_result["result"] = logout_all_service.logout_all(
                presented_user=presented(rotation_id, "concurrent-rotation"),
                presented_session={"session_id": rotation_current["session_id"]},
                raw_session_token=rotation_current["session"],
                raw_device_token=rotation_current["device"],
                raw_access_proof=rotation_current["proof"],
                raw_step_up_proof="",
                password="verified",
                request_id="auth.logout_all.concurrent_rotation",
                password_verifier=lambda *_args, **_kwargs: True,
            )
        except Exception as exc:  # pragma: no cover - asserted below
            rotation_errors.append(exc)

    logout_thread = threading.Thread(target=revoke_during_rotation)
    logout_thread.start()
    assert entered_logout_lock.wait(10)
    continue_rotation.set()
    rotation_thread.join(10)
    logout_thread.join(10)
    assert not rotation_thread.is_alive() and not logout_thread.is_alive()
    assert rotation_errors == []
    assert rotation_result["result"].status == "authentication_required"
    assert all(
        row["revoked_at"] is None
        for row in _rows(
            url, "SELECT revoked_at FROM user_sessions WHERE user_id=%s", (rotation_id,)
        )
    )
    assert _rows(
        url,
        "SELECT event_id FROM security_events WHERE subject_user_id=%s",
        (rotation_id,),
    ) == []

def test_static_lock_order_and_no_unsafe_route_primitive():
    source = (ROOT / "backend/auth/logout_all_service.py").read_text(encoding="utf-8")
    routes = (ROOT / "backend/auth/routes.py").read_text(encoding="utf-8")
    handler_source = source[source.index("def logout_all("):]
    assert handler_source.index("lock_session_user_and_device(") < handler_source.index("lock_credential(")
    assert handler_source.index("lock_credential(") < handler_source.index("_lock_complete_populations(")
    assert "ORDER BY session_id\n         FOR UPDATE" in source
    assert "ORDER BY id\n         FOR UPDATE" in source
    assert routes.count('@auth_blueprint.post("/logout-all")') == 1
    handler = routes[routes.index('@auth_blueprint.post("/logout-all")'):routes.index('@auth_blueprint.post("/forgot-password")')]
    assert "logout_all_service.logout_all(" in handler
    assert "UPDATE user_sessions" not in handler
    assert "UPDATE trusted_devices" not in handler
