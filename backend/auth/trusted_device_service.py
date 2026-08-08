"""Canonical trusted-device persistence and token handling.

Raw credentials exist only in caller memory and the protected browser cookie.
All functions participate in the caller's transaction and never open, commit,
or roll back a database connection.
"""

import hashlib
import os
import secrets


TOKEN_BYTES = 32
DIGEST_BYTES = 32
DEFAULT_LIFETIME_DAYS = 30
MAX_LIFETIME_DAYS = 30


class TrustedDeviceError(ValueError):
    pass


def trusted_device_lifetime_days():
    raw = os.environ.get("DIGITRANSX_TRUSTED_DEVICE_DAYS", str(DEFAULT_LIFETIME_DAYS))
    try:
        days = int(raw)
    except (TypeError, ValueError) as exc:
        raise TrustedDeviceError("Trusted-device lifetime must be an integer.") from exc
    if not 1 <= days <= MAX_LIFETIME_DAYS:
        raise TrustedDeviceError("Trusted-device lifetime must be between 1 and 30 days.")
    return days


def generate_raw_token():
    return secrets.token_urlsafe(TOKEN_BYTES)


def digest_token(raw_token):
    if not isinstance(raw_token, str) or not 32 <= len(raw_token) <= 512:
        raise TrustedDeviceError("Trusted-device token must be a bounded opaque string.")
    return hashlib.sha256(raw_token.encode("utf-8")).digest()


def create_trusted_device(executor, user_id):
    raw_token = generate_raw_token()
    row = executor.execute(
        """
        INSERT INTO public.trusted_devices
            (token_digest, user_id, expires_at)
        VALUES (%s, %s, now() + %s * interval '1 day')
        RETURNING id
        """,
        (digest_token(raw_token), user_id, trusted_device_lifetime_days()),
    ).fetchone()
    if not row:
        raise RuntimeError("Trusted-device creation returned no identifier.")
    return raw_token, row["id"]


def resolve_active_trusted_device(executor, raw_token, *, touch=False):
    digest = digest_token(raw_token)
    if touch:
        return executor.execute(
            """
            UPDATE public.trusted_devices
               SET last_used_at = now()
             WHERE token_digest = %s AND revoked_at IS NULL AND expires_at > now()
            RETURNING *
            """,
            (digest,),
        ).fetchone()
    return executor.execute(
        """
        SELECT * FROM public.trusted_devices
         WHERE token_digest = %s AND revoked_at IS NULL AND expires_at > now()
        """,
        (digest,),
    ).fetchone()


def rotate_trusted_device(executor, user_id, raw_token):
    digest = digest_token(raw_token)
    existing = executor.execute(
        """SELECT id FROM public.trusted_devices
             WHERE (token_digest = %s OR previous_token_digest = %s) AND user_id = %s
               AND revoked_at IS NULL AND expires_at > now()
             FOR UPDATE""",
        (digest, digest, user_id),
    ).fetchone()
    if not existing:
        token, device_id = create_trusted_device(executor, user_id)
        return token, device_id, False
    replacement = generate_raw_token()
    row = executor.execute(
        """
        UPDATE public.trusted_devices
           SET previous_token_digest = token_digest, token_digest = %s,
               rotated_at = now(), last_used_at = now(),
               expires_at = now() + %s * interval '1 day'
         WHERE id = %s AND revoked_at IS NULL
        RETURNING id
        """,
        (digest_token(replacement), trusted_device_lifetime_days(), existing["id"]),
    ).fetchone()
    if not row:
        raise RuntimeError("Trusted-device rotation lost its locked row.")
    return replacement, row["id"], True


def establish_after_full_login(executor, user_id, presented_token=None):
    if presented_token:
        token, device_id, rotated = rotate_trusted_device(
            executor, user_id, presented_token
        )
        if rotated:
            return token, device_id, "security.trusted_device.rotated"
        return token, device_id, "security.trusted_device.added"
    token, device_id = create_trusted_device(executor, user_id)
    return token, device_id, "security.trusted_device.added"


def revoke_trusted_device(executor, user_id, raw_token):
    return executor.execute(
        """
        UPDATE public.trusted_devices
           SET revoked_at = COALESCE(revoked_at, now())
         WHERE token_digest = %s AND user_id = %s
        """,
        (digest_token(raw_token), user_id),
    ).rowcount


def revoke_all_trusted_devices(executor, user_id):
    return executor.execute(
        """UPDATE public.trusted_devices SET revoked_at = now()
             WHERE user_id = %s AND revoked_at IS NULL""",
        (user_id,),
    ).rowcount
