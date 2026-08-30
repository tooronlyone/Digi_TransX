"""Focused PostgreSQL proofs for Phase 1B-2C6 management."""

import hashlib
import secrets

import pytest

pytest_plugins = ("tests.test_logout_all_revocation",)

from auth import session_device_management as management
from auth.session_service import session_event_reference, trusted_device_reference
from tests.test_logout_all_revocation import (
    _add_active_auth,
    _authenticate,
    _rows,
    _seed_inactive_rows,
    _seed_user,
)


def _add_session(url, user_id, device_id):
    raw = secrets.token_urlsafe(32)
    with management_db(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_sessions(
                    user_id,token_digest,trusted_device_id,inactivity_expires_at,
                    absolute_expires_at,access_proof_digest,access_proof_expires_at
                ) VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',%s,now()+interval '8 hours')
                RETURNING session_id
                """,
                (user_id, hashlib.sha256(raw.encode()).digest(), device_id, secrets.token_bytes(32)),
            )
            return cursor.fetchone()[0]


class management_db:
    def __init__(self, url):
        self.url = url

    def __enter__(self):
        import psycopg2

        self.conn = psycopg2.connect(self.url)
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()


def test_2c6_inventory_is_collected():
    assert "test_session_device_management" in __file__


def test_lists_only_owned_records_and_marks_current(logout_all_client):
    client, url, _ = logout_all_client
    user_id = _seed_user(url, "management-owner")
    other_id = _seed_user(url, "management-foreign")
    current = _add_active_auth(url, user_id)
    extra = _add_active_auth(url, user_id)
    foreign = _add_active_auth(url, other_id)
    _authenticate(client, current)

    response = client.get("/auth/security/sessions")
    assert response.status_code == 200
    payload = response.get_json()
    assert {row["management_ref"] for row in payload["sessions"]} == {
        session_event_reference(current["session_id"]), session_event_reference(extra["session_id"])
    }
    assert {row["management_ref"] for row in payload["trusted_devices"]} == {
        trusted_device_reference(current["device_id"]), trusted_device_reference(extra["device_id"])
    }
    current_row = next(row for row in payload["sessions"] if row["is_current"])
    current_device = next(row for row in payload["trusted_devices"] if row["is_current"])
    assert current_row["management_ref"] == session_event_reference(current["session_id"])
    assert current_device["management_ref"] == trusted_device_reference(current["device_id"])
    assert foreign["session_id"] not in {row["management_ref"] for row in payload["sessions"]}
    for row in payload["sessions"] + payload["trusted_devices"]:
        assert set(row) <= {"management_ref", "category_label", "created_at", "last_activity_at", "status", "is_current", "revocable"}
        assert "token" not in str(row).lower()
        assert "digest" not in str(row).lower()


def test_session_and_device_revocation_are_exact_and_evented(logout_all_client):
    client, url, _ = logout_all_client
    user_id = _seed_user(url, "management-revoke")
    current = _add_active_auth(url, user_id)
    target = _add_active_auth(url, user_id)
    bound = _add_session(url, user_id, target["device_id"])
    _authenticate(client, current)

    session_response = client.delete(
        f"/auth/security/sessions/{session_event_reference(target['session_id'])}",
        headers={"X-CSRF-Token": "logout-all-csrf"},
    )
    assert session_response.status_code == 200
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (target["session_id"],))[0]["revoked_at"] is not None
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (bound,))[0]["revoked_at"] is None
    device_response = client.delete(
        f"/auth/security/devices/{trusted_device_reference(target['device_id'])}",
        headers={"X-CSRF-Token": "logout-all-csrf"},
    )
    assert device_response.status_code == 200
    assert device_response.get_json()["session_count"] == 1
    assert _rows(url, "SELECT revoked_at,revocation_reason FROM user_sessions WHERE session_id=%s", (bound,))[0]["revocation_reason"] == "device_removed"
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (target["device_id"],))[0]["revoked_at"] is not None
    events = _rows(url, "SELECT event_name,session_ref,device_ref FROM security_events ORDER BY occurred_at")
    assert [event["event_name"] for event in events] == ["security.session.revoked", "security.session.revoked", "security.trusted_device.removed"]

    repeated = client.delete(
        f"/auth/security/devices/{trusted_device_reference(target['device_id'])}",
        headers={"X-CSRF-Token": "logout-all-csrf"},
    )
    assert repeated.status_code == 409
    assert len(_rows(url, "SELECT * FROM security_events")) == 3


def test_foreign_current_invalid_and_inactive_references_fail_closed(logout_all_client):
    client, url, _ = logout_all_client
    owner = _seed_user(url, "management-owner-fail")
    foreign = _seed_user(url, "management-foreign-fail")
    current = _add_active_auth(url, owner)
    other = _add_active_auth(url, foreign)
    inactive = _seed_inactive_rows(url, owner)
    _authenticate(client, current)
    headers = {"X-CSRF-Token": "logout-all-csrf"}
    for ref in (session_event_reference(other["session_id"]), "session_" + "f" * 32):
        response = client.delete(f"/auth/security/sessions/{ref}", headers=headers)
        assert response.status_code == 409
    response = client.delete(
        f"/auth/security/devices/{trusted_device_reference(other['device_id'])}", headers=headers
    )
    assert response.status_code == 409
    response = client.delete(
        f"/auth/security/sessions/{session_event_reference(current['session_id'])}", headers=headers
    )
    assert response.status_code == 409
    assert len(_rows(url, "SELECT * FROM security_events")) == 0
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (inactive[2],))[0]["revoked_at"] is None


def test_event_failure_rolls_back_device_cascade(logout_all_client, monkeypatch):
    client, url, _ = logout_all_client
    user_id = _seed_user(url, "management-rollback")
    current = _add_active_auth(url, user_id)
    target = _add_active_auth(url, user_id)
    bound = _add_session(url, user_id, target["device_id"])
    _authenticate(client, current)

    def fail(*args, **kwargs):
        raise RuntimeError("test event failure")

    monkeypatch.setattr(management, "write_security_event", fail)
    response = client.delete(
        f"/auth/security/devices/{trusted_device_reference(target['device_id'])}",
        headers={"X-CSRF-Token": "logout-all-csrf"},
    )
    assert response.status_code == 503
    assert _rows(url, "SELECT revoked_at FROM trusted_devices WHERE id=%s", (target["device_id"],))[0]["revoked_at"] is None
    assert _rows(url, "SELECT revoked_at FROM user_sessions WHERE session_id=%s", (bound,))[0]["revoked_at"] is None
    assert len(_rows(url, "SELECT * FROM security_events")) == 0
