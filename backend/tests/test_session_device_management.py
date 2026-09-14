"""Executable PostgreSQL and route proofs for Phase 1B-2C6 management."""

import hashlib
import secrets
import threading
import time

import psycopg2
import pytest

pytest_plugins = ("tests.test_logout_all_revocation",)

from auth import logout_all_service, session_device_management as management
from auth.session_service import create_session, session_event_reference, trusted_device_reference
from auth.trusted_device_service import establish_after_full_login
from shared.db import Db
from tests.test_logout_all_revocation import (
    CSRF,
    _add_active_auth,
    _authenticate,
    _rows,
    _seed_inactive_rows,
    _seed_user,
)


def _add_session(url, user_id, device_id):
    raw = secrets.token_urlsafe(32)
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO user_sessions(
                   user_id,token_digest,trusted_device_id,inactivity_expires_at,
                   absolute_expires_at,access_proof_digest,access_proof_expires_at)
               VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',
                      %s,now()+interval '8 hours') RETURNING session_id""",
            (user_id, hashlib.sha256(raw.encode()).digest(), device_id, secrets.token_bytes(32)),
        )
        return cursor.fetchone()[0]


def _session_ref(client, owner_id, session_id):
    with client.application.app_context():
        return management.session_management_reference(owner_id, session_id)


def _device_ref(client, owner_id, device_id):
    with client.application.app_context():
        return management.device_management_reference(owner_id, device_id)


def _authority(current):
    return {
        "current_session_id": current["session_id"],
        "current_device_id": current["device_id"],
        "raw_session_token": current["session"],
        "raw_device_token": current["device"],
        "raw_access_proof": current["proof"],
    }


def _user(url, user_id):
    row = _rows(url, "SELECT * FROM users WHERE id=%s", (user_id,))[0]
    row["role"] = row.get("legacy_role") or row.get("role")
    return row


def _run_management(app, url, operation, **kwargs):
    with app.app_context(), psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='5s'")
        return operation(Db(conn), **kwargs)


def _logout_all(app, user, current, request_id):
    with app.app_context():
        return logout_all_service.logout_all(
            presented_user=user,
            presented_session={"session_id": current["session_id"]},
            raw_session_token=current["session"],
            raw_device_token=current["device"],
            raw_access_proof=current["proof"],
            raw_step_up_proof="",
            password="verified",
            request_id=request_id,
            password_verifier=lambda *_args, **_kwargs: True,
        )


def test_owner_only_listing_exact_current_markers_and_safe_projection(logout_all_client):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "management-list-owner")
    foreign_owner = _seed_user(url, "management-list-foreign")
    current = _add_active_auth(url, owner)
    extra = _add_active_auth(url, owner)
    foreign = _add_active_auth(url, foreign_owner)
    inactive = _seed_inactive_rows(url, owner)
    _authenticate(client, current)

    response = client.get("/auth/security/sessions")
    assert response.status_code == 200
    payload = response.get_json()
    assert {row["management_ref"] for row in payload["sessions"]} == {
        _session_ref(client, owner, current["session_id"]),
        _session_ref(client, owner, extra["session_id"]),
    }
    assert {row["management_ref"] for row in payload["trusted_devices"]} == {
        _device_ref(client, owner, current["device_id"]),
        _device_ref(client, owner, extra["device_id"]),
    }
    assert [row["management_ref"] for row in payload["sessions"] if row["is_current"]] == [
        _session_ref(client, owner, current["session_id"])
    ]
    assert [row["management_ref"] for row in payload["trusted_devices"] if row["is_current"]] == [
        _device_ref(client, owner, current["device_id"])
    ]
    serialized = response.get_data(as_text=True)
    for forbidden in (
        str(foreign["session_id"]),
        str(inactive[2]), str(inactive[3]),
        current["session"], current["device"], current["proof"],
        "token_digest", "user_agent", "ip_address",
    ):
        assert forbidden not in serialized
    for row in payload["sessions"] + payload["trusted_devices"]:
        assert set(row) == {
            "management_ref", "category_label", "created_at", "last_activity_at",
            "status", "is_current", "revocable",
        }


def test_references_are_keyed_owner_and_type_bound_and_use_constant_time(logout_all_client, monkeypatch):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "management-ref-owner")
    foreign_owner = _seed_user(url, "management-ref-foreign")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    _authenticate(client, current)

    session_ref = _session_ref(client, owner, target["session_id"])
    device_ref = _device_ref(client, owner, target["device_id"])
    assert session_ref != _session_ref(client, foreign_owner, target["session_id"])
    assert device_ref != _device_ref(client, foreign_owner, target["device_id"])
    assert session_ref[8:] != device_ref[7:]
    assert str(target["session_id"]) not in session_ref
    assert len(device_ref) == len("device_") + 32
    assert session_event_reference(target["session_id"]) != session_ref
    assert trusted_device_reference(target["device_id"]) != device_ref

    calls = []
    original = management.hmac.compare_digest

    def observed(left, right):
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(management.hmac, "compare_digest", observed)
    assert client.delete(f"/auth/security/sessions/{session_ref}", headers=CSRF).status_code == 200
    assert any(left == session_ref and right == session_ref for left, right in calls)


@pytest.mark.parametrize("kind", ["session", "device"])
def test_forged_old_neighbor_cross_owner_and_cross_type_references_are_indistinguishable(logout_all_client, kind):
    client, url, _ = logout_all_client
    owner = _seed_user(url, f"management-forgery-owner-{kind}")
    foreign_owner = _seed_user(url, f"management-forgery-foreign-{kind}")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    foreign = _add_active_auth(url, foreign_owner)
    _authenticate(client, current)
    endpoint = f"/auth/security/{'sessions' if kind == 'session' else 'devices'}/"
    valid_foreign = _session_ref(client, foreign_owner, foreign["session_id"]) if kind == "session" else _device_ref(client, foreign_owner, foreign["device_id"])
    old_unkeyed = session_event_reference(target["session_id"]) if kind == "session" else trusted_device_reference(target["device_id"])
    neighbor = "session_" + hashlib.sha256(str(target["session_id"]).encode()).hexdigest()[:32] if kind == "session" else trusted_device_reference(target["device_id"] + 1)
    cross_type = _device_ref(client, owner, target["device_id"]) if kind == "session" else _session_ref(client, owner, target["session_id"])
    attempts = [valid_foreign, old_unkeyed, neighbor, cross_type, "bad", "session_" + "f" * 31]
    results = [client.delete(endpoint + value, headers=CSRF) for value in attempts]
    assert {(result.status_code, result.get_json()["code"]) for result in results} == {(409, "not_found")}
    assert _rows(url, "SELECT event_id FROM security_events") == []
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (target["session_id"],))[0]["revoked_at"] is None
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (target["device_id"],))[0]["revoked_at"] is None


def test_targeted_session_is_exact_and_event_contract_is_complete(logout_all_client):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "management-session-event", role="platform_admin")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    same_device = _add_session(url, owner, target["device_id"])
    _authenticate(client, current)

    response = client.delete(f"/auth/security/sessions/{_session_ref(client, owner, target['session_id'])}", headers=CSRF)
    assert response.get_json() == {"success": True, "status": "revoked", "session_count": 1}
    rows = _rows(url, "SELECT session_id,revoked_at,revocation_reason FROM user_sessions WHERE session_id IN (%s,%s)", (target["session_id"], same_device))
    states = {row["session_id"]: row for row in rows}
    assert states[target["session_id"]]["revocation_reason"] == "security_action"
    assert states[same_device]["revoked_at"] is None
    event = _rows(url, "SELECT * FROM security_events")[0]
    assert len(_rows(url, "SELECT event_id FROM security_events")) == 1
    assert event["event_name"] == "security.session.revoked"
    assert event["metadata"] == {"result_code": "security_action"}
    assert event["actor_type"] == "admin"
    assert event["actor_id"] == owner and event["subject_user_id"] == owner
    assert event["session_ref"] == session_event_reference(target["session_id"])
    assert event["device_ref"] is None
    assert event["idempotency_scope"] == "security.session.revoked"
    assert event["idempotency_key"] == f"{event['request_id']}:{event['session_ref']}"


def test_device_cascade_is_exact_preserves_inactive_controls_and_events_every_row(logout_all_client):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "management-device-event")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    bound = _add_session(url, owner, target["device_id"])
    inactive = _seed_inactive_rows(url, owner)
    before = {
        (table, key, value): _rows(url, f"SELECT revoked_at FROM {table} WHERE {key}=%s", (value,))[0]["revoked_at"]
        for table, key, value in (
            ("trusted_devices", "id", inactive[0]), ("trusted_devices", "id", inactive[1]),
            ("user_sessions", "session_id", inactive[2]), ("user_sessions", "session_id", inactive[3]),
        )
    }
    _authenticate(client, current)
    response = client.delete(f"/auth/security/devices/{_device_ref(client, owner, target['device_id'])}", headers=CSRF)
    assert response.get_json() == {"success": True, "status": "revoked", "session_count": 2, "device_count": 1}
    changed = _rows(url, "SELECT session_id,revocation_reason FROM user_sessions WHERE session_id IN (%s,%s)", (target["session_id"], bound))
    assert len(changed) == 2 and {row["revocation_reason"] for row in changed} == {"device_removed"}
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (target["device_id"],))[0]["revoked_at"] is not None
    for (table, key, value), old_state in before.items():
        assert _rows(url, f"SELECT revoked_at FROM {table} WHERE {key}=%s", (value,))[0]["revoked_at"] == old_state
    events = _rows(url, "SELECT * FROM security_events")
    assert len(events) == 3
    session_events = [row for row in events if row["event_name"] == "security.session.revoked"]
    device_events = [row for row in events if row["event_name"] == "security.trusted_device.removed"]
    event_device_ref = trusted_device_reference(target["device_id"])
    assert {row["session_ref"] for row in session_events} == {session_event_reference(target["session_id"]), session_event_reference(bound)}
    assert all(row["metadata"] == {"result_code": "device_removed"} and row["device_ref"] == event_device_ref for row in session_events)
    assert len(device_events) == 1 and device_events[0]["metadata"] == {"result_code": "security_action"}
    assert device_events[0]["device_ref"] == event_device_ref
    assert all(row["actor_id"] == owner and row["subject_user_id"] == owner for row in events)
    assert all(row["idempotency_key"] == f"{row['request_id']}:{row['session_ref'] or row['device_ref']}" for row in events)


@pytest.mark.parametrize("operation,fail_after", [("session", 0), ("device", 0), ("device", 1), ("device", 2)])
def test_event_failure_rolls_back_every_related_mutation(logout_all_client, monkeypatch, operation, fail_after):
    client, url, _ = logout_all_client
    owner = _seed_user(url, f"management-rollback-{operation}")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    bound = _add_session(url, owner, target["device_id"])
    _authenticate(client, current)
    original_writer = management.write_security_event
    writes = []
    def fail_at_boundary(*args, **kwargs):
        if len(writes) == fail_after:
            raise RuntimeError("injected event failure")
        result = original_writer(*args, **kwargs)
        writes.append(True)
        return result
    monkeypatch.setattr(management, "write_security_event", fail_at_boundary)
    ref = _session_ref(client, owner, target["session_id"]) if operation == "session" else _device_ref(client, owner, target["device_id"])
    response = client.delete(f"/auth/security/{'sessions' if operation == 'session' else 'devices'}/{ref}", headers=CSRF)
    assert response.status_code == 503
    assert all(row["revoked_at"] is None for row in _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id IN (%s,%s)", (target["session_id"], bound)))
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (target["device_id"],))[0]["revoked_at"] is None
    assert _rows(url, "SELECT event_id FROM security_events") == []


def test_anonymous_csrf_blocked_locked_and_stale_authentication_fail_closed(logout_all_client):
    client, url, _ = logout_all_client
    assert client.get("/auth/security/sessions").status_code == 401
    owner = _seed_user(url, "management-auth-fail")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    _authenticate(client, current)
    endpoint = f"/auth/security/sessions/{_session_ref(client, owner, target['session_id'])}"
    assert client.delete(endpoint).status_code == 403
    assert client.delete(endpoint, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE user_sessions SET access_locked=true,access_locked_at=now(),access_proof_digest=NULL,access_proof_expires_at=NULL WHERE session_id=%s", (current["session_id"],))
    assert client.delete(endpoint, headers=CSRF).status_code == 423
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE user_sessions SET access_locked=false,access_locked_at=NULL,access_proof_digest=%s,access_proof_expires_at=now()+interval '1 hour' WHERE session_id=%s", (hashlib.sha256(current["proof"].encode()).digest(), current["session_id"]))
        cursor.execute("UPDATE users SET is_blocked=true WHERE id=%s", (owner,))
    assert client.delete(endpoint, headers=CSRF).status_code == 401
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE users SET is_blocked=false WHERE id=%s", (owner,))
        cursor.execute("UPDATE user_sessions SET revoked_at=now(),revocation_reason='logout' WHERE session_id=%s", (current["session_id"],))
    assert client.delete(endpoint, headers=CSRF).status_code == 401
    assert _rows(url, "SELECT event_id FROM security_events") == []


def _controlled_owner_race(url, monkeypatch, first_action, second_action):
    """Force a real PostgreSQL owner-lock wait inside the production operations."""
    acquired = threading.Event()
    attempted = threading.Event()
    release = threading.Event()
    pids = {}
    results = {}
    errors = []
    original = Db.execute

    def execute(db, statement, params=()):
        name = threading.current_thread().name
        is_owner_lock = "from users" in statement.lower() and "for update" in statement.lower()
        if name not in {"2c6-first", "2c6-second"} or not is_owner_lock or name in pids:
            return original(db, statement, params)
        pids[name] = db._conn.get_backend_pid()
        with db._conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='6s'")
            cur.execute("SET LOCAL statement_timeout='8s'")
        if name == "2c6-second":
            attempted.set()
        result = original(db, statement, params)
        if name == "2c6-first":
            acquired.set()
            assert release.wait(5), "Controlled first operation was not released."
        return result

    def run(name, action):
        try:
            results[name] = action()
        except Exception as exc:
            errors.append((name, type(exc).__name__, getattr(exc, "pgcode", None)))

    first = threading.Thread(name="2c6-first", target=run, args=("first", first_action))
    second = threading.Thread(name="2c6-second", target=run, args=("second", second_action))
    blocked = False
    with monkeypatch.context() as patch:
        patch.setattr(Db, "execute", execute)
        try:
            first.start()
            assert acquired.wait(5), "First production operation did not acquire the owner."
            second.start()
            assert attempted.wait(5), "Second operation did not attempt the owner."
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                row = _rows(url, "SELECT %s=ANY(pg_blocking_pids(%s)) AS blocked", (pids["2c6-first"], pids["2c6-second"]))[0]
                if row["blocked"]:
                    blocked = True
                    break
                release.wait(0.02)
        finally:
            release.set()
            if first.ident is not None:
                first.join(10)
            if second.ident is not None:
                second.join(10)
    assert not first.is_alive() and not second.is_alive(), "Bounded workers did not finish."
    assert errors == [], "A controlled operation failed or timed out."
    assert blocked, "The dangerous interleaving was not established in PostgreSQL."
    return results["first"], results["second"]


def _control_fingerprint(url, owner):
    rows = [
        _rows(url, "SELECT md5(row_to_json(t)::text) AS fingerprint FROM users t WHERE id=%s", (owner,)),
        _rows(url, "SELECT md5(row_to_json(t)::text) AS fingerprint FROM trusted_devices t WHERE user_id=%s ORDER BY id", (owner,)),
        _rows(url, "SELECT md5(row_to_json(t)::text) AS fingerprint FROM user_sessions t WHERE user_id=%s ORDER BY session_id", (owner,)),
    ]
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def _assert_exact_revocation_events(url, owner, sessions, devices, *, logout=False):
    events = _rows(url, "SELECT * FROM security_events WHERE subject_user_id=%s", (owner,))
    assert len(events) == len(sessions) + len(devices) + int(logout)
    session_events = [e for e in events if e["event_name"] == "security.session.revoked"]
    device_events = [e for e in events if e["event_name"] == "security.trusted_device.removed"]
    assert {e["session_ref"] for e in session_events} == {session_event_reference(value) for value in sessions}
    assert {e["device_ref"] for e in device_events} == {trusted_device_reference(value) for value in devices}
    assert len(session_events) == len(sessions) and len(device_events) == len(devices)
    assert all(e["actor_id"] == owner and e["subject_user_id"] == owner for e in events)
    assert all(e["source"] == "server_route" for e in events)
    for event in session_events + device_events:
        reference = event["session_ref"] or event["device_ref"]
        assert event["idempotency_scope"] == event["event_name"]
        assert event["idempotency_key"] == f"{event['request_id']}:{reference}"
    if logout:
        envelopes = [e for e in events if e["event_name"] == "security.logout.completed"]
        assert len(envelopes) == 1
        assert envelopes[0]["metadata"] == {"result_code": "completed"}
    return events


@pytest.mark.parametrize("kind", ["session", "device"])
def test_simultaneous_duplicate_mutations_force_lock_wait_and_exact_evidence(logout_all_client, monkeypatch, kind):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "duplicate-owner")
    foreign_owner = _seed_user(url, "duplicate-foreign")
    _add_active_auth(url, foreign_owner)
    before = _control_fingerprint(url, foreign_owner)
    assert _control_fingerprint(url, foreign_owner) == before
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    user = _user(url, owner)
    operation = management.revoke_session if kind == "session" else management.revoke_device
    ref = _session_ref(client, owner, target["session_id"]) if kind == "session" else _device_ref(client, owner, target["device_id"])
    def action(index):
        return _run_management(client.application, url, operation, user=user, management_ref=ref,
                               **_authority(current), request_id=f"auth.management.duplicate.{kind}.{index}")
    first, second = _controlled_owner_race(url, monkeypatch, lambda: action(1), lambda: action(2))
    assert first["status"] == "revoked" and second["status"] == "not_found"
    assert action(3)["status"] == "not_found"
    assert _control_fingerprint(url, foreign_owner) == before
    events = _assert_exact_revocation_events(url, owner, [target["session_id"]], [target["device_id"]] if kind == "device" else [])
    assert all(e["metadata"] == {"result_code": "device_removed" if e["event_name"] == "security.session.revoked" and kind == "device" else "security_action"} for e in events)
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (current["session_id"],))[0]["revoked_at"] is None


@pytest.mark.parametrize("kind", ["session", "device"])
@pytest.mark.parametrize("target_first", [True, False])
def test_targeted_and_logout_all_force_lock_wait_without_stale_authority(logout_all_client, monkeypatch, kind, target_first):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "all-race", role="platform_admin")
    foreign_owner = _seed_user(url, "all-race-foreign")
    _add_active_auth(url, foreign_owner)
    foreign_before = _control_fingerprint(url, foreign_owner)
    assert _control_fingerprint(url, foreign_owner) == foreign_before
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    sessions = [current["session_id"], target["session_id"]]
    if kind == "device":
        sessions.append(_add_session(url, owner, target["device_id"]))
    user = _user(url, owner)
    operation = management.revoke_session if kind == "session" else management.revoke_device
    ref = _session_ref(client, owner, target["session_id"]) if kind == "session" else _device_ref(client, owner, target["device_id"])
    targeted = lambda: _run_management(client.application, url, operation, user=user, management_ref=ref,
                                      **_authority(current), request_id=f"auth.management.all-race.{kind}")
    logout = lambda: _logout_all(client.application, user, current, f"auth.logout_all.race.{kind}")
    results = _controlled_owner_race(url, monkeypatch, targeted if target_first else logout, logout if target_first else targeted)
    targeted_result, logout_result = results if target_first else results[::-1]
    assert targeted_result["status"] == ("revoked" if target_first else "authentication_required")
    assert logout_result.status == "success"
    assert _control_fingerprint(url, foreign_owner) == foreign_before
    assert all(r["revoked_at"] is not None for r in _rows(url, "SELECT revoked_at FROM user_sessions WHERE user_id=%s", (owner,)))
    assert all(r["revoked_at"] is not None for r in _rows(url, "SELECT revoked_at FROM trusted_devices WHERE user_id=%s", (owner,)))
    events = _assert_exact_revocation_events(url, owner, sessions, [current["device_id"], target["device_id"]], logout=True)
    targeted_events = [e for e in events if e["request_id"].startswith("auth.management.")]
    assert len(targeted_events) == ((1 if kind == "session" else 3) if target_first else 0)
    for event in events:
        if event["event_name"] == "security.logout.completed":
            continue
        expected = "logout_all"
        if event in targeted_events:
            expected = "device_removed" if kind == "device" and event["event_name"] == "security.session.revoked" else "security_action"
        assert event["metadata"] == {"result_code": expected}


@pytest.mark.parametrize("kind", ["session", "device"])
@pytest.mark.parametrize("login_first", [True, False])
def test_real_login_rotation_and_issuance_versus_targeted_revoke(logout_all_client, monkeypatch, kind, login_first):
    from auth import routes
    client, url, _ = logout_all_client
    owner = _seed_user(url, "login-race")
    foreign_owner = _seed_user(url, "login-race-foreign")
    _add_active_auth(url, foreign_owner)
    foreign_before = _control_fingerprint(url, foreign_owner)
    assert _control_fingerprint(url, foreign_owner) == foreign_before
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    user = _user(url, owner)
    calls = []
    monkeypatch.setattr(routes, "supabase_verify_password", lambda *_a, **_k: calls.append("local-stub") or True)
    def login():
        with client.application.test_client() as login_client:
            login_client.set_cookie("dtx_device_token", target["device"])
            response = login_client.post("/auth/login", json={"loginId": user["email"], "password": "local-stub"})
            return response.status_code
    operation = management.revoke_session if kind == "session" else management.revoke_device
    ref = _session_ref(client, owner, target["session_id"]) if kind == "session" else _device_ref(client, owner, target["device_id"])
    revoke = lambda: _run_management(client.application, url, operation, user=user, management_ref=ref,
                                    **_authority(current), request_id=f"auth.management.login-race.{kind}")
    values = _controlled_owner_race(url, monkeypatch, login if login_first else revoke, revoke if login_first else login)
    login_result, revoke_result = values if login_first else values[::-1]
    assert login_result == 200 and revoke_result["status"] == "revoked"
    assert calls == ["local-stub"]
    assert _control_fingerprint(url, foreign_owner) == foreign_before
    sessions = _rows(url, "SELECT session_id,trusted_device_id,revoked_at FROM user_sessions WHERE user_id=%s", (owner,))
    new = [r for r in sessions if r["session_id"] not in {current["session_id"], target["session_id"]}]
    assert len(new) == 1
    assert (new[0]["revoked_at"] is not None) == (login_first and kind == "device")
    assert new[0]["trusted_device_id"] == target["device_id"] if login_first or kind == "session" else new[0]["trusted_device_id"] != target["device_id"]
    events = _rows(url, "SELECT event_name,metadata,session_ref,device_ref,request_id,idempotency_scope,idempotency_key FROM security_events")
    from collections import Counter
    expected = Counter({"security.login.started": 1, "security.login.succeeded": 1, "security.session.issued": 1,
                        "security.trusted_device.added" if not login_first and kind == "device" else "security.trusted_device.rotated": 1,
                        "security.session.revoked": 2 if login_first and kind == "device" else 1})
    if kind == "device":
        expected["security.trusted_device.removed"] = 1
    assert Counter(e["event_name"] for e in events) == expected
    evidence = [e for e in events if e["request_id"].startswith("auth.management.")]
    expected_sessions = {session_event_reference(target["session_id"])}
    if login_first and kind == "device":
        expected_sessions.add(session_event_reference(new[0]["session_id"]))
    assert {e["session_ref"] for e in evidence if e["event_name"] == "security.session.revoked"} == expected_sessions
    assert all(e["idempotency_key"] == f"{e['request_id']}:{e['session_ref'] or e['device_ref']}" for e in evidence)


def test_current_targets_fail_closed_and_canonical_logout_remains_owner(logout_all_client):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "management-current")
    current = _add_active_auth(url, owner)
    _authenticate(client, current)
    session_response = client.delete(f"/auth/security/sessions/{_session_ref(client, owner, current['session_id'])}", headers=CSRF)
    device_response = client.delete(f"/auth/security/devices/{_device_ref(client, owner, current['device_id'])}", headers=CSRF)
    assert (session_response.status_code, session_response.get_json()["code"]) == (409, "not_found")
    assert (device_response.status_code, device_response.get_json()["code"]) == (409, "not_found")
    logout = client.post("/auth/logout", headers=CSRF)
    assert logout.status_code == 200 and logout.get_json()["success"] is True
    assert _rows(url, "SELECT event_name,metadata FROM security_events ORDER BY event_name") == [
        {"event_name": "security.logout.completed", "metadata": {"result_code": "completed"}},
        {"event_name": "security.session.revoked", "metadata": {"result_code": "logout"}},
    ]


def test_sensitive_values_never_appear_in_responses_or_logs(logout_all_client, caplog):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "management-sensitive")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    _authenticate(client, current)
    response = client.delete(f"/auth/security/sessions/{_session_ref(client, owner, target['session_id'])}", headers=CSRF)
    combined = response.get_data(as_text=True) + caplog.text
    for forbidden in (
        current["session"], current["device"], current["proof"],
        target["session"], target["device"], target["proof"],
        str(target["session_id"]), str(target["device_id"]),
        "token_digest", "access_proof_digest",
    ):
        assert forbidden not in combined


@pytest.mark.parametrize("kind", ["session", "device"])
@pytest.mark.parametrize("change", [
    "session_revoked", "session_expired", "device_revoked", "device_expired",
    "device_rotated", "owner_blocked", "access_locked", "proof_rotated",
    "proof_expired", "binding_changed",
])
def test_authority_changed_after_decorator_cannot_mutate(logout_all_client, monkeypatch, kind, change):
    from contextlib import contextmanager
    from auth import routes

    client, url, _ = logout_all_client
    owner = _seed_user(url, "authority-window")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    alternate = _add_active_auth(url, owner)
    # Age the fixture before authentication, preserving production timestamp
    # constraints when the simulated clock later crosses an expiry boundary.
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute("UPDATE user_sessions SET created_at=now()-interval '1 day',authenticated_at=now()-interval '1 day',last_genuine_activity_at=now()-interval '1 day' WHERE session_id=%s", (current["session_id"],))
    _authenticate(client, current)
    original = routes.open_db
    entered = []

    @contextmanager
    def change_between_transactions():
        entered.append(True)
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            if change == "session_revoked":
                cur.execute("UPDATE user_sessions SET revoked_at=now(),revocation_reason='logout' WHERE session_id=%s", (current["session_id"],))
            elif change == "session_expired":
                cur.execute("UPDATE user_sessions SET inactivity_expires_at=now()-interval '1 second' WHERE session_id=%s", (current["session_id"],))
            elif change == "device_revoked":
                cur.execute("UPDATE trusted_devices SET revoked_at=now() WHERE id=%s", (current["device_id"],))
            elif change == "device_expired":
                cur.execute("UPDATE trusted_devices SET expires_at=now()-interval '1 second',created_at=now()-interval '1 day' WHERE id=%s", (current["device_id"],))
            elif change == "device_rotated":
                cur.execute("UPDATE trusted_devices SET token_digest=%s WHERE id=%s", (secrets.token_bytes(32), current["device_id"]))
            elif change == "owner_blocked":
                cur.execute("UPDATE users SET is_blocked=true WHERE id=%s", (owner,))
            elif change == "access_locked":
                cur.execute("UPDATE user_sessions SET access_locked=true,access_locked_at=now(),access_proof_digest=NULL,access_proof_expires_at=NULL WHERE session_id=%s", (current["session_id"],))
            elif change == "proof_rotated":
                cur.execute("UPDATE user_sessions SET access_proof_digest=%s WHERE session_id=%s", (secrets.token_bytes(32), current["session_id"]))
            elif change == "proof_expired":
                cur.execute("UPDATE user_sessions SET access_proof_expires_at=now()-interval '1 second' WHERE session_id=%s", (current["session_id"],))
            else:
                cur.execute("UPDATE user_sessions SET trusted_device_id=%s WHERE session_id=%s", (alternate["device_id"], current["session_id"]))
        with original() as db:
            yield db

    monkeypatch.setattr(routes, "open_db", change_between_transactions)
    ref = _session_ref(client, owner, target["session_id"]) if kind == "session" else _device_ref(client, owner, target["device_id"])
    response = client.delete(f"/auth/security/{'sessions' if kind == 'session' else 'devices'}/{ref}", headers=CSRF)
    assert entered == [True]
    assert (response.status_code, response.get_json()["code"]) == (401, "authentication_required")
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (target["session_id"],))[0]["revoked_at"] is None
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (target["device_id"],))[0]["revoked_at"] is None
    assert _rows(url, "SELECT event_name FROM security_events") == []


@pytest.mark.parametrize("kind", ["session", "device"])
def test_population_overflow_fails_closed_without_truncation(logout_all_client, monkeypatch, kind):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "bounded-owner")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    _authenticate(client, current)
    monkeypatch.setattr(management, "MANAGEMENT_LIMIT", 2)
    # Exactly the configured bound remains usable.
    assert client.get("/auth/security/sessions").status_code == 200
    _add_active_auth(url, owner)
    response = client.get("/auth/security/sessions")
    assert response.status_code == 503
    assert "sessions" not in response.get_json()
    ref = _session_ref(client, owner, target["session_id"]) if kind == "session" else _device_ref(client, owner, target["device_id"])
    assert client.delete(f"/auth/security/{'sessions' if kind == 'session' else 'devices'}/{ref}", headers=CSRF).status_code == 503
    assert _rows(url, "SELECT event_name FROM security_events") == []
    assert all(row["revoked_at"] is None for row in _rows(url, "SELECT revoked_at FROM user_sessions WHERE user_id=%s", (owner,)))


@pytest.mark.parametrize("kind", ["session", "device"])
def test_reference_version_secret_rotation_and_full_forgery_set(logout_all_client, monkeypatch, kind):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "full-forgery")
    current = _add_active_auth(url, owner)
    target = _add_active_auth(url, owner)
    _authenticate(client, current)
    reference = _session_ref(client, owner, target["session_id"]) if kind == "session" else _device_ref(client, owner, target["device_id"])
    make_ref = management.session_management_reference if kind == "session" else management.device_management_reference
    target_id = target["session_id"] if kind == "session" else target["device_id"]
    with client.application.app_context():
        assert make_ref(owner, target_id) == reference
        with monkeypatch.context() as patch:
            patch.setitem(client.application.config, "SECRET_KEY", "different-worker-secret-for-rotation-test")
            assert make_ref(owner, target_id) != reference
        with monkeypatch.context() as patch:
            patch.setattr(management, "REFERENCE_VALUE_DOMAIN", "digitransx:management-reference:v2")
            assert make_ref(owner, target_id) != reference
    changed = reference[:-1] + ("0" if reference[-1] != "0" else "1")
    attempts = [reference[:-1], reference + "0", changed, kind + "_" + secrets.token_hex(16), reference + "\n"]
    bodies = []
    from urllib.parse import quote
    for attempt in attempts:
        response = client.delete(f"/auth/security/{'sessions' if kind == 'session' else 'devices'}/{quote(attempt, safe='')}", headers=CSRF)
        assert response.status_code == 409
        bodies.append(response.get_json())
    assert all(body == bodies[0] for body in bodies)
    assert bodies[0]["code"] == "not_found"
    assert _rows(url, "SELECT event_name FROM security_events") == []


def test_standalone_rotation_acquires_owner_and_rejects_unavailable_owner(logout_all_client, monkeypatch):
    from auth.trusted_device_service import rotate_trusted_device, TrustedDeviceError
    client, url, _ = logout_all_client
    owner = _seed_user(url, "standalone-rotation")
    target = _add_active_auth(url, owner)
    statements = []
    original = Db.execute

    def observed(db, statement, params=()):
        statements.append(" ".join(statement.split()).lower())
        return original(db, statement, params)

    with monkeypatch.context() as patch:
        patch.setattr(Db, "execute", observed)
        with psycopg2.connect(url) as conn:
            rotate_trusted_device(Db(conn), owner, target["device"])
    assert "from users" in statements[0] and "for update" in statements[0]
    assert "from public.trusted_devices" in statements[1] and "order by id for update" in statements[1]
    before = _rows(url, "SELECT rotated_at FROM trusted_devices WHERE id=%s", (target["device_id"],))[0]
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET is_blocked=true WHERE id=%s", (owner,))
    with psycopg2.connect(url) as conn, pytest.raises(TrustedDeviceError):
        rotate_trusted_device(Db(conn), owner, target["device"])
    assert _rows(url, "SELECT rotated_at FROM trusted_devices WHERE id=%s", (target["device_id"],))[0] == before
