"""Canonical secure MPIN credential owner.

The raw four-digit MPIN and server pepper remain process memory only. All
database operations participate in the caller-owned transaction.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets


MPIN_PATTERN = re.compile(r"^[0-9]{4}$", re.ASCII)
ELIGIBLE_ROLES = frozenset(
    {"logistics_provider", "service_seeker", "everyday_user"}
)
PEPPER_ENV = "DIGITRANSX_MPIN_PEPPER"
KDF_VERSION = 1
SALT_BYTES = 32
VERIFIER_BYTES = 32
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
MAX_FAILURES = 5


class MpinError(ValueError):
    pass


class MpinConfigurationError(RuntimeError):
    pass


def validate_mpin(value):
    if not isinstance(value, str) or MPIN_PATTERN.fullmatch(value) is None:
        raise MpinError("MPIN must be exactly four ASCII digits.")
    return value


def role_is_eligible(role):
    return isinstance(role, str) and role.strip().lower() in ELIGIBLE_ROLES


def _pepper(environ=None):
    values = os.environ if environ is None else environ
    raw = values.get(PEPPER_ENV)
    if not isinstance(raw, str) or not raw:
        raise MpinConfigurationError("Secure MPIN service is unavailable.")
    try:
        padded = raw + "=" * (-len(raw) % 4)
        value = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        raise MpinConfigurationError("Secure MPIN service is unavailable.") from None
    if len(value) != 32:
        raise MpinConfigurationError("Secure MPIN service is unavailable.")
    return value


def validate_configuration(environ=None):
    _pepper(environ)


def generate_salt():
    return secrets.token_bytes(SALT_BYTES)


def derive_verifier(mpin, salt, *, environ=None, kdf_version=KDF_VERSION):
    validate_mpin(mpin)
    if kdf_version != KDF_VERSION:
        raise MpinError("Unsupported MPIN verifier version.")
    if not isinstance(salt, (bytes, bytearray, memoryview)) or len(salt) != SALT_BYTES:
        raise MpinError("Invalid MPIN salt.")
    material = mpin.encode("ascii") + b"\x00" + _pepper(environ)
    return hashlib.scrypt(
        material,
        salt=bytes(salt),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=VERIFIER_BYTES,
    )


def build_credential(mpin, *, environ=None):
    salt = generate_salt()
    return salt, derive_verifier(mpin, salt, environ=environ)


def verify_mpin(mpin, credential, *, environ=None):
    try:
        candidate = derive_verifier(
            mpin,
            credential["salt"],
            environ=environ,
            kdf_version=int(credential["kdf_version"]),
        )
    except (MpinError, TypeError, ValueError):
        return False
    verifier = credential.get("verifier")
    return isinstance(verifier, (bytes, bytearray, memoryview)) and hmac.compare_digest(
        candidate, bytes(verifier)
    )


def lock_credential(executor, user_id):
    return executor.execute(
        "SELECT * FROM mpin_credentials WHERE user_id = %s FOR UPDATE",
        (user_id,),
    ).fetchone()


def enroll(executor, user_id, mpin, *, environ=None):
    salt, verifier = build_credential(mpin, environ=environ)
    return executor.execute(
        """
        INSERT INTO mpin_credentials
            (user_id, verifier, salt, kdf_version)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        RETURNING user_id
        """,
        (user_id, verifier, salt, KDF_VERSION),
    ).fetchone()


def replace(executor, user_id, mpin, *, environ=None):
    salt, verifier = build_credential(mpin, environ=environ)
    return executor.execute(
        """
        UPDATE mpin_credentials
           SET verifier = %s, salt = %s, kdf_version = %s,
               failed_attempts = 0, permanently_locked = false,
               locked_at = NULL, updated_at = now()
         WHERE user_id = %s
        RETURNING user_id
        """,
        (verifier, salt, KDF_VERSION, user_id),
    ).fetchone()


def reset_or_enroll(executor, user_id, mpin, *, environ=None):
    salt, verifier = build_credential(mpin, environ=environ)
    return executor.execute(
        """
        INSERT INTO mpin_credentials
            (user_id, verifier, salt, kdf_version)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            verifier = excluded.verifier,
            salt = excluded.salt,
            kdf_version = excluded.kdf_version,
            failed_attempts = 0,
            permanently_locked = false,
            locked_at = NULL,
            updated_at = now()
        RETURNING user_id
        """,
        (user_id, verifier, salt, KDF_VERSION),
    ).fetchone()


def record_failure(executor, user_id):
    """Increment one locked row and report ``failed`` or ``locked``."""

    row = lock_credential(executor, user_id)
    if not row:
        return "unavailable", None
    if row["permanently_locked"]:
        return "already_locked", row
    attempts = int(row["failed_attempts"]) + 1
    permanently_locked = attempts >= MAX_FAILURES
    updated = executor.execute(
        """
        UPDATE mpin_credentials
           SET failed_attempts = %s,
               permanently_locked = %s,
               locked_at = CASE WHEN %s THEN now() ELSE NULL END,
               updated_at = now()
         WHERE user_id = %s
        RETURNING *
        """,
        (attempts, permanently_locked, permanently_locked, user_id),
    ).fetchone()
    return ("locked" if permanently_locked else "failed"), updated


def reset_failures(executor, user_id):
    return executor.execute(
        """
        UPDATE mpin_credentials
           SET failed_attempts = 0, updated_at = now()
         WHERE user_id = %s AND NOT permanently_locked
        """,
        (user_id,),
    ).rowcount


def disable(executor, user_id):
    return executor.execute(
        "DELETE FROM mpin_credentials WHERE user_id = %s", (user_id,)
    ).rowcount
