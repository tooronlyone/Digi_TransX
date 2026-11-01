"""Owner-scoped active session and trusted-device management.

Management references use a dedicated keyed domain, separate from canonical
event references. This module is the only owner of the
management population selection and one-target revocation flows.
"""

import hashlib
import hmac
import re

from flask import current_app

from auth.session_service import (
    SessionFoundationError,
    digest_opaque_token,
    locked_access_proof_is_valid,
    session_event_reference,
    trusted_device_reference,
)
from events.contract import EventContext, EventData
from events.writer import write_security_event


SESSION_REF_RE = re.compile(r"^session_[0-9a-f]{32}$")
DEVICE_REF_RE = re.compile(r"^device_[0-9a-f]{32}$")
MANAGEMENT_LIMIT = 100
REFERENCE_KEY_DOMAIN = b"digitransx:management-reference:key:v1"
REFERENCE_VALUE_DOMAIN = "digitransx:management-reference:v1"


class SessionDeviceManagementError(ValueError):
    """A bounded management request or invariant failed."""


def _context(request_id, user, *, session_ref=None, device_ref=None):
    role = (user.get("legacy_role") or user.get("role") or "").strip().lower()
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


def _reference_key():
    """Derive a purpose-specific key from the validated Flask signing secret."""

    secret = current_app.config.get("SECRET_KEY")
    if not isinstance(secret, (str, bytes)) or not secret:
        raise SessionDeviceManagementError("Management reference signing is unavailable.")
    raw_secret = secret.encode("utf-8") if isinstance(secret, str) else secret
    return hmac.new(raw_secret, REFERENCE_KEY_DOMAIN, hashlib.sha256).digest()


def _management_reference(target_type, owner_id, target_id):
    if target_type not in {"session", "device"}:
        raise SessionDeviceManagementError("Unsupported management reference type.")
    if owner_id is None or target_id is None:
        raise SessionDeviceManagementError("Management reference ownership is required.")
    payload = (
        f"{REFERENCE_VALUE_DOMAIN}\x00{target_type}\x00{owner_id}\x00{target_id}"
    ).encode("utf-8")
    digest = hmac.new(_reference_key(), payload, hashlib.sha256).hexdigest()[:32]
    return f"{target_type}_{digest}"


def session_management_reference(owner_id, session_id):
    return _management_reference("session", owner_id, session_id)


def device_management_reference(owner_id, device_id):
    return _management_reference("device", owner_id, device_id)


def _timestamp(row, key):
    value = row.get(key)
    return value.isoformat() if hasattr(value, "isoformat") else value


def _session_view(row, owner_id, current_session_id):
    return {
        "management_ref": session_management_reference(owner_id, row["session_id"]),
        "category_label": "Active session",
        "created_at": _timestamp(row, "created_at"),
        "last_activity_at": _timestamp(row, "last_genuine_activity_at"),
        "status": "current" if row["session_id"] == current_session_id else "active",
        "is_current": row["session_id"] == current_session_id,
        "revocable": row["session_id"] != current_session_id,
    }


def _device_view(row, owner_id, current_device_id):
    return {
        "management_ref": device_management_reference(owner_id, row["id"]),
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
           AND s.inactivity_expires_at>clock_timestamp() AND s.absolute_expires_at>clock_timestamp()
           AND d.revoked_at IS NULL AND d.expires_at>clock_timestamp()
         ORDER BY s.last_genuine_activity_at DESC, s.session_id
         LIMIT %s
        """,
        (user_id, MANAGEMENT_LIMIT + 1),
    ).fetchall()
    devices = executor.execute(
        """
        SELECT id, created_at, last_used_at
          FROM trusted_devices
         WHERE user_id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp()
         ORDER BY last_used_at DESC, id
         LIMIT %s
        """,
        (user_id, MANAGEMENT_LIMIT + 1),
    ).fetchall()
    _require_bounded(sessions)
    _require_bounded(devices)
    return {
        "sessions": [_session_view(row, user_id, current_session_id) for row in sessions],
        "trusted_devices": [_device_view(row, user_id, current_device_id) for row in devices],
        "counts": {"sessions": len(sessions), "trusted_devices": len(devices)},
    }


def _require_bounded(rows):
    if len(rows) > MANAGEMENT_LIMIT:
        raise SessionDeviceManagementError("Management population exceeds the safe bound.")


def _locked_authority(
    executor, *, user, current_session_id, current_device_id,
    raw_session_token, raw_device_token, raw_access_proof,
):
    """Own the complete ordered lock set before validating mutation authority.

    The decorator's result is only a presented identity. Every live row and
    browser credential is checked again here, in the mutation transaction.
    No target lookup or event write precedes this check.
    """
    locked_user = executor.execute(
        "SELECT * FROM users WHERE id=%s AND NOT is_blocked FOR UPDATE",
        (user["id"],),
    ).fetchone()
    if not locked_user:
        return None
    sessions = executor.execute(
        """SELECT * FROM user_sessions
             WHERE user_id=%s AND revoked_at IS NULL
               AND inactivity_expires_at>clock_timestamp() AND absolute_expires_at>clock_timestamp()
             ORDER BY session_id LIMIT %s FOR UPDATE""",
        (user["id"], MANAGEMENT_LIMIT + 1),
    ).fetchall()
    _require_bounded(sessions)
    devices = executor.execute(
        """SELECT * FROM trusted_devices
             WHERE user_id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp()
             ORDER BY id LIMIT %s FOR UPDATE""",
        (user["id"], MANAGEMENT_LIMIT + 1),
    ).fetchall()
    _require_bounded(devices)
    durable = next((row for row in sessions if row["session_id"] == current_session_id), None)
    device = next((row for row in devices if row["id"] == current_device_id), None)
    role = lambda row: (row.get("legacy_role") or row.get("role") or "").lower()
    if (
        not durable or not device
        or durable["trusted_device_id"] != device["id"]
        or durable["user_id"] != locked_user["id"]
        or device["user_id"] != locked_user["id"]
        or locked_user.get("auth_id") != user.get("auth_id")
        or locked_user.get("email") != user.get("email")
        or role(locked_user) != role(user)
    ):
        return None
    # Recheck clock-dependent validity after the complete lock set has been
    # acquired, including any time spent waiting for a device lock.
    active = executor.execute(
        """SELECT s.trusted_device_id=%s
                   AND s.inactivity_expires_at>clock_timestamp()
                   AND s.absolute_expires_at>clock_timestamp()
                   AND d.expires_at>clock_timestamp() AS active
              FROM user_sessions s JOIN trusted_devices d
                ON d.id=s.trusted_device_id AND d.user_id=s.user_id
             WHERE s.session_id=%s AND s.user_id=%s AND d.id=%s""",
        (current_device_id, current_session_id, user["id"], current_device_id),
    ).fetchone()
    if not active or not active["active"]:
        return None
    try:
        session_digest = digest_opaque_token(raw_session_token)
        device_digest = digest_opaque_token(raw_device_token)
    except SessionFoundationError:
        return None
    if (
        not hmac.compare_digest(bytes(durable["token_digest"]), session_digest)
        or not hmac.compare_digest(bytes(device["token_digest"]), device_digest)
        or not locked_access_proof_is_valid(executor, durable, raw_access_proof)
    ):
        return None
    return locked_user, sessions, devices


def _resolve_locked(rows, owner_id, management_ref, *, kind):
    pattern = SESSION_REF_RE if kind == "session" else DEVICE_REF_RE
    if not _valid_ref(management_ref, pattern):
        return None
    key = "session_id" if kind == "session" else "id"
    return next((row for row in rows if hmac.compare_digest(
        _management_reference(kind, owner_id, row[key]), management_ref
    )), None)


def revoke_session(
    executor, *, user, management_ref, current_session_id, current_device_id,
    raw_session_token, raw_device_token, raw_access_proof, request_id,
):
    """Revoke exactly one non-current, active owned session and write evidence."""

    authority = _locked_authority(
        executor, user=user, current_session_id=current_session_id,
        current_device_id=current_device_id, raw_session_token=raw_session_token,
        raw_device_token=raw_device_token, raw_access_proof=raw_access_proof,
    )
    if authority is None:
        return {"status": "authentication_required", "session_count": 0}
    user, sessions, devices = authority
    user_id = user["id"]
    locked = _resolve_locked(sessions, user_id, management_ref, kind="session")
    if (
        not locked or locked["session_id"] == current_session_id
        or locked["trusted_device_id"] not in {row["id"] for row in devices}
    ):
        return {"status": "not_found", "session_count": 0}
    changed = executor.execute(
        """
        UPDATE user_sessions
           SET revoked_at=now(), revocation_reason='security_action', updated_at=now()
         WHERE session_id=%s AND user_id=%s AND revoked_at IS NULL
           AND inactivity_expires_at>clock_timestamp() AND absolute_expires_at>clock_timestamp()
           AND EXISTS (SELECT 1 FROM trusted_devices d WHERE d.id=user_sessions.trusted_device_id
                         AND d.user_id=user_sessions.user_id AND d.revoked_at IS NULL
                         AND d.expires_at>clock_timestamp())
        """,
        (locked["session_id"], user_id),
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


def revoke_device(
    executor, *, user, management_ref, current_session_id, current_device_id,
    raw_session_token, raw_device_token, raw_access_proof, request_id,
):
    """Revoke one device and every active session bound to it atomically."""

    authority = _locked_authority(
        executor, user=user, current_session_id=current_session_id,
        current_device_id=current_device_id, raw_session_token=raw_session_token,
        raw_device_token=raw_device_token, raw_access_proof=raw_access_proof,
    )
    if authority is None:
        return {"status": "authentication_required", "session_count": 0, "device_count": 0}
    user, all_sessions, devices = authority
    user_id = user["id"]
    locked_device = _resolve_locked(devices, user_id, management_ref, kind="device")
    if not locked_device or locked_device["id"] == current_device_id:
        return {"status": "not_found", "session_count": 0, "device_count": 0}
    device_id = locked_device["id"]
    sessions = [row for row in all_sessions if row["trusted_device_id"] == device_id]

    changed_sessions = executor.execute(
        """
        UPDATE user_sessions
           SET revoked_at=now(), revocation_reason='device_removed', updated_at=now()
         WHERE user_id=%s AND trusted_device_id=%s AND revoked_at IS NULL
           AND inactivity_expires_at>clock_timestamp() AND absolute_expires_at>clock_timestamp()
        """,
        (user_id, device_id),
    ).rowcount
    if changed_sessions != len(sessions):
        raise RuntimeError("Device session cascade affected an unexpected number of rows.")
    changed_device = executor.execute(
        "UPDATE trusted_devices SET revoked_at=now() WHERE id=%s AND user_id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp()",
        (device_id, user_id),
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
