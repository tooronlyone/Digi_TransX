"""Canonical durable-session persistence and runtime authority.

Raw credentials exist only in caller memory and the protected browser cookie.
Every operation participates in the caller-owned transaction.
"""

import hashlib
import secrets


TOKEN_DIGEST_BYTES = 32
OPAQUE_TOKEN_BYTES = 32
INACTIVITY_DAYS = 7
ABSOLUTE_LIFETIME_DAYS = 30

REVOCATION_REASONS = frozenset(
    {
        "logout",
        "logout_all",
        "password_changed",
        "password_reset",
        "account_blocked",
        "device_removed",
        "inactivity_expired",
        "absolute_expiry",
        "security_action",
        "token_rotated",
        "replay_detected",
    }
)


class SessionFoundationError(ValueError):
    """A caller supplied an invalid durable-session value."""


def generate_opaque_token():
    """Return a high-entropy browser token; callers must never persist it."""

    return secrets.token_urlsafe(OPAQUE_TOKEN_BYTES)


def digest_opaque_token(raw_token):
    """Return the fixed-size database representation of an opaque token."""

    if not isinstance(raw_token, str) or not 32 <= len(raw_token) <= 512:
        raise SessionFoundationError("Session token must be a bounded opaque string.")
    return hashlib.sha256(raw_token.encode("utf-8")).digest()


def create_session(executor, user_id, *, trusted_device_id):
    """Issue one device-bound session inside the caller transaction."""

    if not trusted_device_id:
        raise SessionFoundationError("A trusted device is required for session issuance.")

    raw_token = generate_opaque_token()
    result = executor.execute(
        """
        INSERT INTO user_sessions (
            user_id, token_digest, trusted_device_id,
            inactivity_expires_at, absolute_expires_at
        ) VALUES (
            %s, %s, %s,
            now() + interval '7 days', now() + interval '30 days'
        )
        RETURNING session_id
        """,
        (user_id, digest_opaque_token(raw_token), trusted_device_id),
    ).fetchone()
    if not result:
        raise RuntimeError("Durable session creation returned no session identifier.")
    return raw_token, result["session_id"]


def find_session_by_token(executor, raw_token, device_digest, *, lock=False):
    """Resolve only a currently valid session bound to the exact active device."""

    return executor.execute(
        f"""
        SELECT s.*
          FROM user_sessions s
          JOIN users u ON u.id = s.user_id
          JOIN trusted_devices d
            ON d.id = s.trusted_device_id AND d.user_id = s.user_id
         WHERE s.token_digest = %s
           AND d.token_digest = %s
           AND s.revoked_at IS NULL
           AND s.inactivity_expires_at > now()
           AND s.absolute_expires_at > now()
           AND NOT s.access_locked
           AND NOT u.is_blocked
           AND d.revoked_at IS NULL
           AND d.expires_at > now()
        {"FOR UPDATE OF s, d" if lock else ""}
        """,
        (digest_opaque_token(raw_token), device_digest),
    ).fetchone()


def lock_session_by_id(executor, session_id, user_id):
    """Lock one exact active session before a conflicting revoke operation."""

    return executor.execute(
        """SELECT * FROM user_sessions
             WHERE session_id = %s AND user_id = %s AND revoked_at IS NULL
             FOR UPDATE""",
        (session_id, user_id),
    ).fetchone()


def record_genuine_activity(executor, session_id):
    """Refresh only explicit genuine activity and its seven-day boundary."""

    return executor.execute(
        """
        UPDATE user_sessions
           SET last_genuine_activity_at = now(),
               inactivity_expires_at = now() + interval '7 days',
               updated_at = now()
         WHERE session_id = %s AND revoked_at IS NULL
        """,
        (session_id,),
    ).rowcount


def set_access_locked(executor, session_id, *, locked):
    """Set the software access-lock state without changing authentication."""

    return executor.execute(
        """
        UPDATE user_sessions
           SET access_locked = %s,
               access_locked_at = CASE WHEN %s THEN now() ELSE NULL END,
               updated_at = now()
         WHERE session_id = %s AND revoked_at IS NULL
        """,
        (bool(locked), bool(locked), session_id),
    ).rowcount


def revoke_session(executor, session_id, reason):
    """Idempotently revoke one session with a bounded server-owned reason."""

    if reason not in REVOCATION_REASONS:
        raise SessionFoundationError("Unsupported session revocation reason.")
    return executor.execute(
        """
        UPDATE user_sessions
           SET revoked_at = now(), revocation_reason = %s, updated_at = now()
         WHERE session_id = %s AND revoked_at IS NULL
        """,
        (reason, session_id),
    ).rowcount


def revoke_user_sessions(executor, user_id, reason):
    """Idempotently revoke all active sessions for one exact public user."""

    if reason not in REVOCATION_REASONS:
        raise SessionFoundationError("Unsupported session revocation reason.")
    return executor.execute(
        """
        UPDATE user_sessions
           SET revoked_at = now(), revocation_reason = %s, updated_at = now()
         WHERE user_id = %s AND revoked_at IS NULL
        """,
        (reason, user_id),
    ).rowcount
