"""Owner-scoped active session and trusted-device management.

Management references are deliberately non-reversible references already used
by the security event contract.  This module is the only owner of the
management population selection and one-target revocation flows.
"""

import re

from auth.session_service import session_event_reference, trusted_device_reference
from events.contract import EventContext, EventData
from events.writer import write_security_event


SESSION_REF_RE = re.compile(r"^session_[0-9a-f]{32}$")
DEVICE_REF_RE = re.compile(r"^device_[0-9a-f]{32}$")
MANAGEMENT_LIMIT = 100


class SessionDeviceManagementError(ValueError):
    """A bounded management request or invariant failed."""


def _context(request_id, user, *, session_ref=None, device_ref=None):
    role = (user.get("role") or user.get("legacy_role") or "").strip().lower()
    return EventContext(
        request_id=request_id,
        source="server_route",
        actor_type="admin" if role == "platform_admin" else "user",
        actor_id=user["id"],
        actor_role=role,
        subject_user_id=user["id"],
        session_ref=session_ref,
        device_ref=device_ref,
    )


def _valid_ref(value, pattern):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _timestamp(row, key):
    value = row.get(key)
    return value.isoformat() if hasattr(value, "isoformat") else value


def _session_view(row, current_session_id):
    return {
        "management_ref": session_event_reference(row["session_id"]),
        "category_label": "Active session",
        "created_at": _timestamp(row, "created_at"),
        "last_activity_at": _timestamp(row, "last_genuine_activity_at"),
        "status": "current" if row["session_id"] == current_session_id else "active",
        "is_current": row["session_id"] == current_session_id,
        "revocable": row["session_id"] != current_session_id,
    }


def _device_view(row, current_device_id):
    return {
        "management_ref": trusted_device_reference(row["id"]),
        "category_label": "Trusted device",
        "created_at": _timestamp(row, "created_at"),
        "last_activity_at": _timestamp(row, "last_used_at"),
        "status": "current" if row["id"] == current_device_id else "active",
        "is_current": row["id"] == current_device_id,
        "revocable": row["id"] != current_device_id,
    }


def list_active(executor, user_id, *, current_session_id, current_device_id):
    """List only active records owned by ``user_id`` with safe fields."""

    sessions = executor.execute(
        """
        SELECT s.session_id, s.created_at, s.last_genuine_activity_at
          FROM user_sessions s
          JOIN trusted_devices d ON d.id=s.trusted_device_id AND d.user_id=s.user_id
         WHERE s.user_id=%s AND s.revoked_at IS NULL
           AND s.inactivity_expires_at>now() AND s.absolute_expires_at>now()
           AND d.revoked_at IS NULL AND d.expires_at>now()
         ORDER BY s.last_genuine_activity_at DESC, s.session_id
         LIMIT %s
        """,
        (user_id, MANAGEMENT_LIMIT),
    ).fetchall()
    devices = executor.execute(
        """
        SELECT id, created_at, last_used_at
          FROM trusted_devices
         WHERE user_id=%s AND revoked_at IS NULL AND expires_at>now()
         ORDER BY last_used_at DESC, id
         LIMIT %s
        """,
        (user_id, MANAGEMENT_LIMIT),
    ).fetchall()
    return {
        "sessions": [_session_view(row, current_session_id) for row in sessions],
        "trusted_devices": [_device_view(row, current_device_id) for row in devices],
        "counts": {"sessions": len(sessions), "trusted_devices": len(devices)},
    }


def _find_session(executor, user_id, management_ref, *, lock=False):
    if not _valid_ref(management_ref, SESSION_REF_RE):
        return None
    rows = executor.execute(
        """
        SELECT session_id, created_at, trusted_device_id
          FROM user_sessions
         WHERE user_id=%s
           AND revoked_at IS NULL
           AND inactivity_expires_at>now() AND absolute_expires_at>now()
         ORDER BY session_id
         """ + ("FOR UPDATE" if lock else ""),
        (user_id,),
    ).fetchall()
    return next((row for row in rows if session_event_reference(row["session_id"]) == management_ref), None)


def _find_device(executor, user_id, management_ref, *, lock=False):
    if not _valid_ref(management_ref, DEVICE_REF_RE):
        return None
    rows = executor.execute(
        """
        SELECT id, created_at
          FROM trusted_devices
         WHERE user_id=%s AND revoked_at IS NULL AND expires_at>now()
         ORDER BY id
         """ + ("FOR UPDATE" if lock else ""),
        (user_id,),
    ).fetchall()
    return next((row for row in rows if trusted_device_reference(row["id"]) == management_ref), None)


def revoke_session(executor, *, user, management_ref, current_session_id, request_id):
    """Revoke exactly one non-current, active owned session and write evidence."""

    if not _valid_ref(management_ref, SESSION_REF_RE):
        return {"status": "not_found", "session_count": 0}
    candidate = _find_session(executor, user["id"], management_ref)
    if not candidate or candidate["session_id"] == current_session_id:
        return {"status": "not_found", "session_count": 0}

    locked = _find_session(executor, user["id"], management_ref, lock=True)
    if not locked or locked["session_id"] == current_session_id:
        return {"status": "stale", "session_count": 0}
    locked_user = executor.execute(
        "SELECT id FROM users WHERE id=%s AND NOT is_blocked FOR UPDATE", (user["id"],)
    ).fetchone()
    if not locked_user:
        return {"status": "stale", "session_count": 0}
    locked_device = executor.execute(
        """
        SELECT id FROM trusted_devices
         WHERE id=%s AND user_id=%s AND revoked_at IS NULL AND expires_at>now()
         FOR UPDATE
        """,
        (locked["trusted_device_id"], user["id"]),
    ).fetchone()
    if not locked_device:
        return {"status": "stale", "session_count": 0}
    changed = executor.execute(
        """
        UPDATE user_sessions
           SET revoked_at=now(), revocation_reason='security_action', updated_at=now()
         WHERE session_id=%s AND user_id=%s AND revoked_at IS NULL
        """,
        (locked["session_id"], user["id"]),
    ).rowcount
    if changed != 1:
        raise RuntimeError("Session revocation affected an unexpected number of rows.")
    reference = session_event_reference(locked["session_id"])
    write_security_event(
        executor, "security.session.revoked",
        _context(request_id, user, session_ref=reference),
        EventData(metadata={"result_code": "security_action"}),
        idempotency_scope="security.session.revoked",
        idempotency_key=f"{request_id}:{reference}",
    )
    return {"status": "revoked", "session_count": 1}


def revoke_device(executor, *, user, management_ref, current_device_id, request_id):
    """Revoke one device and every active session bound to it atomically."""

    if not _valid_ref(management_ref, DEVICE_REF_RE):
        return {"status": "not_found", "session_count": 0, "device_count": 0}
    candidate = _find_device(executor, user["id"], management_ref)
    if not candidate or candidate["id"] == current_device_id:
        return {"status": "not_found", "session_count": 0, "device_count": 0}

    # Session -> user -> trusted-device is the repository lock order.
    device_id = candidate["id"]
    sessions = executor.execute(
        """
        SELECT session_id FROM user_sessions
         WHERE user_id=%s AND trusted_device_id=%s AND revoked_at IS NULL
           AND inactivity_expires_at>now() AND absolute_expires_at>now()
         ORDER BY session_id FOR UPDATE
        """,
        (user["id"], device_id),
    ).fetchall()
    locked_user = executor.execute(
        "SELECT id FROM users WHERE id=%s AND NOT is_blocked FOR UPDATE", (user["id"],)
    ).fetchone()
    locked_device = executor.execute(
        """
        SELECT id FROM trusted_devices
         WHERE id=%s AND user_id=%s AND revoked_at IS NULL AND expires_at>now()
         FOR UPDATE
        """,
        (device_id, user["id"]),
    ).fetchone()
    if not locked_user or not locked_device:
        return {"status": "stale", "session_count": 0, "device_count": 0}

    changed_sessions = executor.execute(
        """
        UPDATE user_sessions
           SET revoked_at=now(), revocation_reason='device_removed', updated_at=now()
         WHERE user_id=%s AND trusted_device_id=%s AND revoked_at IS NULL
           AND inactivity_expires_at>now() AND absolute_expires_at>now()
        """,
        (user["id"], device_id),
    ).rowcount
    if changed_sessions != len(sessions):
        raise RuntimeError("Device session cascade affected an unexpected number of rows.")
    changed_device = executor.execute(
        "UPDATE trusted_devices SET revoked_at=now() WHERE id=%s AND user_id=%s AND revoked_at IS NULL",
        (device_id, user["id"]),
    ).rowcount
    if changed_device != 1:
        raise RuntimeError("Device revocation affected an unexpected number of rows.")

    device_ref = trusted_device_reference(device_id)
    for row in sessions:
        session_ref = session_event_reference(row["session_id"])
        write_security_event(
            executor, "security.session.revoked",
            _context(request_id, user, session_ref=session_ref, device_ref=device_ref),
            EventData(metadata={"result_code": "device_removed"}),
            idempotency_scope="security.session.revoked",
            idempotency_key=f"{request_id}:{session_ref}",
        )
    write_security_event(
        executor, "security.trusted_device.removed",
        _context(request_id, user, device_ref=device_ref),
        EventData(metadata={"result_code": "security_action"}),
        idempotency_scope="security.trusted_device.removed",
        idempotency_key=f"{request_id}:{device_ref}",
    )
    return {"status": "revoked", "session_count": changed_sessions, "device_count": 1}
