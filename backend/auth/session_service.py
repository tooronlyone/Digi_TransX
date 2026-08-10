"""Canonical durable-session persistence and runtime authority.

Raw credentials exist only in caller memory and the protected browser cookie.
Every operation participates in the caller-owned transaction.
"""

import hashlib
import secrets


TOKEN_DIGEST_BYTES = 32
OPAQUE_TOKEN_BYTES = 32
ACCESS_PROOF_BYTES = 32
ACCESS_PROOF_LIFETIME_HOURS = 8
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


def generate_access_proof():
    """Return a browser-session-only software-access credential."""

    return secrets.token_urlsafe(ACCESS_PROOF_BYTES)


def digest_opaque_token(raw_token):
    """Return the fixed-size database representation of an opaque token."""

    if not isinstance(raw_token, str) or not 32 <= len(raw_token) <= 512:
        raise SessionFoundationError("Session token must be a bounded opaque string.")
    return hashlib.sha256(raw_token.encode("utf-8")).digest()


def digest_access_proof(raw_proof):
    if not isinstance(raw_proof, str) or not 32 <= len(raw_proof) <= 512:
        raise SessionFoundationError("Access proof must be a bounded opaque string.")
    return hashlib.sha256(raw_proof.encode("utf-8")).digest()


def access_lock_reference(session_id):
    """Return a stable non-reversible event replay reference for one session."""

    if session_id is None:
        raise SessionFoundationError("A session identifier is required.")
    return hashlib.sha256(str(session_id).encode("ascii")).hexdigest()


def create_session(executor, user_id, *, trusted_device_id):
    """Issue one device-bound session inside the caller transaction."""

    if not trusted_device_id:
        raise SessionFoundationError("A trusted device is required for session issuance.")

    raw_token = generate_opaque_token()
    raw_access_proof = generate_access_proof()
    result = executor.execute(
        """
        INSERT INTO user_sessions (
            user_id, token_digest, trusted_device_id,
            inactivity_expires_at, absolute_expires_at,
            access_proof_digest, access_proof_expires_at
        ) VALUES (
            %s, %s, %s,
            now() + interval '7 days', now() + interval '30 days',
            %s, now() + interval '8 hours'
        )
        RETURNING session_id
        """,
        (
            user_id,
            digest_opaque_token(raw_token),
            trusted_device_id,
            digest_access_proof(raw_access_proof),
        ),
    ).fetchone()
    if not result:
        raise RuntimeError("Durable session creation returned no session identifier.")
    return raw_token, raw_access_proof, result["session_id"]


def find_session_by_token(
    executor, raw_token, device_digest, *, raw_access_proof=None, lock=False
):
    """Resolve valid authentication and independently evaluate software access."""

    proof_digest = None
    if raw_access_proof:
        try:
            proof_digest = digest_access_proof(raw_access_proof)
        except SessionFoundationError:
            proof_digest = None

    return executor.execute(
        f"""
        SELECT s.*,
               (NOT s.access_locked
                AND s.access_proof_digest IS NOT NULL
                AND s.access_proof_digest = %s
                AND s.access_proof_expires_at > now()) AS access_proof_valid
          FROM user_sessions s
          JOIN users u ON u.id = s.user_id
          JOIN trusted_devices d
            ON d.id = s.trusted_device_id AND d.user_id = s.user_id
         WHERE s.token_digest = %s
           AND d.token_digest = %s
           AND s.revoked_at IS NULL
           AND s.inactivity_expires_at > now()
           AND s.absolute_expires_at > now()
           AND NOT u.is_blocked
           AND d.revoked_at IS NULL
           AND d.expires_at > now()
        {"FOR UPDATE OF s, d" if lock else ""}
        """,
        (proof_digest, digest_opaque_token(raw_token), device_digest),
    ).fetchone()


def lock_session_by_id(executor, session_id, user_id):
    """Lock one exact active session before a conflicting revoke operation."""

    return executor.execute(
        """SELECT * FROM user_sessions
             WHERE session_id = %s AND user_id = %s AND revoked_at IS NULL
               AND inactivity_expires_at > now()
               AND absolute_expires_at > now()
             FOR UPDATE""",
        (session_id, user_id),
    ).fetchone()


def lock_session_user_and_device(executor, session_id, user_id, device_digest):
    """Acquire the deterministic session -> user -> trusted-device lock order."""

    durable = lock_session_by_id(executor, session_id, user_id)
    if not durable:
        return None, None, None
    user = executor.execute(
        "SELECT * FROM users WHERE id = %s AND NOT is_blocked FOR UPDATE",
        (user_id,),
    ).fetchone()
    if not user:
        return durable, None, None
    device = executor.execute(
        """
        SELECT * FROM trusted_devices
         WHERE id = %s AND user_id = %s AND token_digest = %s
           AND revoked_at IS NULL AND expires_at > now()
         FOR UPDATE
        """,
        (durable["trusted_device_id"], user_id, device_digest),
    ).fetchone()
    return durable, user, device


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
               access_proof_digest = CASE WHEN %s THEN NULL ELSE access_proof_digest END,
               access_proof_expires_at = CASE WHEN %s THEN NULL ELSE access_proof_expires_at END,
               updated_at = now()
         WHERE session_id = %s AND revoked_at IS NULL
        """,
        (bool(locked), bool(locked), bool(locked), bool(locked), session_id),
    ).rowcount


def lock_access_once(executor, session_id):
    """Atomically enter the software-lock state once and invalidate its proof."""

    return executor.execute(
        """
        UPDATE user_sessions
           SET access_locked = true,
               access_locked_at = now(),
               access_proof_digest = NULL,
               access_proof_expires_at = NULL,
               updated_at = now()
         WHERE session_id = %s AND revoked_at IS NULL AND NOT access_locked
        """,
        (session_id,),
    ).rowcount


def rotate_access_proof(executor, session_id, *, password_verified=False):
    """Unlock one locked session with a fresh at-most-eight-hour proof."""

    raw_proof = generate_access_proof()
    row = executor.execute(
        """
        UPDATE user_sessions
           SET access_locked = false,
               access_locked_at = NULL,
               access_proof_digest = %s,
               access_proof_expires_at = least(
                   now() + interval '8 hours', absolute_expires_at
               ),
               password_verified_at = CASE
                   WHEN %s THEN now() ELSE password_verified_at END,
               updated_at = now()
         WHERE session_id = %s AND revoked_at IS NULL
           AND inactivity_expires_at > now()
           AND absolute_expires_at > now()
        RETURNING session_id
        """,
        (digest_access_proof(raw_proof), bool(password_verified), session_id),
    ).fetchone()
    if not row:
        raise RuntimeError("Access-proof rotation lost its locked session.")
    return raw_proof


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
