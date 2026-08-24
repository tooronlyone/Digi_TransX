"""Canonical user-initiated logout-all orchestration.

This is the sole owner of population selection, deterministic locking,
revocation, and canonical evidence for the user-facing logout-all action.
Raw credentials and proofs remain request-memory-only.
"""

from dataclasses import dataclass
import secrets

from auth import mpin_service, step_up_service
from auth.session_service import (
    SessionFoundationError,
    digest_opaque_token,
    locked_access_proof_is_valid,
    lock_session_user_and_device,
    session_event_reference,
    trusted_device_reference,
)
from auth.trusted_device_service import TrustedDeviceError, digest_token
from events.contract import EventContext, EventData
from events.writer import write_security_event
from shared.db import open_db
from shared.supabase_client import PasswordProviderUnavailable, supabase_verify_password


LOGOUT_ALL_DESCRIPTOR = step_up_service.normalize_descriptor({
    "action_key": "security.logout_all",
    "resource_type": "account_security",
    "resource_id": 1,
})


@dataclass(frozen=True)
class LogoutAllResult:
    status: str
    session_count: int = 0
    trusted_device_count: int = 0
    provider_status: int | None = None
    provider_code: str | None = None


def _confirmation_method(role, credential):
    if (
        mpin_service.role_is_eligible(role)
        and credential
        and not credential["permanently_locked"]
    ):
        return "mpin"
    return "password"


def _preflight_method(user_id, role):
    with open_db() as db:
        credential = db.execute(
            "SELECT permanently_locked FROM mpin_credentials WHERE user_id=%s",
            (user_id,),
        ).fetchone()
    return _confirmation_method(role, credential)


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


def _same_identity(locked_user, presented_user):
    return bool(
        locked_user
        and presented_user
        and locked_user["id"] == presented_user.get("id")
        and locked_user.get("email") == presented_user.get("email")
        and locked_user.get("auth_id") == presented_user.get("auth_id")
        and (locked_user.get("legacy_role") or locked_user.get("role"))
        == presented_user.get("role")
        and not locked_user.get("is_blocked")
    )


def _lock_complete_populations(db, user_id):
    sessions = db.execute(
        """
        SELECT session_id
          FROM user_sessions
         WHERE user_id=%s AND revoked_at IS NULL
           AND inactivity_expires_at>now() AND absolute_expires_at>now()
         ORDER BY session_id
         FOR UPDATE
        """,
        (user_id,),
    ).fetchall()
    devices = db.execute(
        """
        SELECT id
          FROM trusted_devices
         WHERE user_id=%s AND revoked_at IS NULL AND expires_at>now()
         ORDER BY id
         FOR UPDATE
        """,
        (user_id,),
    ).fetchall()
    return sessions, devices


def _revoke_locked_populations(db, user_id, sessions, devices):
    revoked_sessions = db.execute(
        """
        UPDATE user_sessions
           SET revoked_at=now(),revocation_reason='logout_all',updated_at=now()
         WHERE user_id=%s AND revoked_at IS NULL
           AND inactivity_expires_at>now() AND absolute_expires_at>now()
        RETURNING session_id
        """,
        (user_id,),
    ).fetchall()
    revoked_devices = db.execute(
        """
        UPDATE trusted_devices
           SET revoked_at=now()
         WHERE user_id=%s AND revoked_at IS NULL AND expires_at>now()
        RETURNING id
        """,
        (user_id,),
    ).fetchall()
    if (
        {row["session_id"] for row in revoked_sessions}
        != {row["session_id"] for row in sessions}
        or {row["id"] for row in revoked_devices}
        != {row["id"] for row in devices}
    ):
        raise RuntimeError("Logout-all population changed after deterministic locking.")
    return revoked_sessions, revoked_devices


def logout_all(
    *,
    presented_user,
    presented_session,
    raw_session_token,
    raw_device_token,
    raw_access_proof,
    raw_step_up_proof,
    password,
    request_id,
    password_verifier=None,
):
    """Revoke every active session/device with one atomic evidence commit."""

    if password_verifier is None:
        password_verifier = supabase_verify_password

    user_id = presented_user["id"]
    preflight_method = _preflight_method(user_id, presented_user.get("role"))
    provider_verified = False
    provider_attempted = False

    if preflight_method == "password" and password is not None:
        provider_attempted = True
        if not isinstance(password, str) or not 1 <= len(password) <= 1024:
            return LogoutAllResult("invalid_password")
        try:
            provider_verified = password_verifier(
                presented_user["email"], password, raise_provider_errors=True
            )
        except PasswordProviderUnavailable as exc:
            return LogoutAllResult(
                "provider_unavailable",
                provider_status=getattr(exc, "status", 503),
                provider_code=getattr(exc, "code", "password_provider_unavailable"),
            )
        if not provider_verified:
            return LogoutAllResult("invalid_password")

    try:
        session_digest = digest_opaque_token(raw_session_token)
        device_digest = digest_token(raw_device_token)
    except (SessionFoundationError, TrustedDeviceError):
        return LogoutAllResult("authentication_required")

    with open_db() as db:
        durable, user, device = lock_session_user_and_device(
            db, presented_session["session_id"], user_id, device_digest
        )
        if (
            not durable
            or not device
            or not _same_identity(user, presented_user)
            or not secrets.compare_digest(bytes(durable["token_digest"]), session_digest)
            or not locked_access_proof_is_valid(db, durable, raw_access_proof)
        ):
            return LogoutAllResult("authentication_required")

        credential = mpin_service.lock_credential(db, user_id)
        final_method = _confirmation_method(
            user.get("legacy_role") or user.get("role"), credential
        )
        if final_method != preflight_method:
            return LogoutAllResult("confirmation_changed")

        gate = None
        if final_method == "mpin":
            authorization = step_up_service.consume_authorization(
                db,
                raw_proof=raw_step_up_proof,
                user_id=user_id,
                session_id=durable["session_id"],
                trusted_device_id=device["id"],
                credential_generation=credential["credential_generation"],
                descriptor=LOGOUT_ALL_DESCRIPTOR,
            )
            if not authorization:
                return LogoutAllResult("mpin_required")
            gate = step_up_service.ConsumptionGate(
                "authorized",
                authorization=dict(authorization),
                durable_session=durable,
                user=user,
                trusted_device=device,
                credential=credential,
            )
        elif not provider_attempted:
            return LogoutAllResult("password_required")
        elif not provider_verified:
            return LogoutAllResult("invalid_password")

        sessions, devices = _lock_complete_populations(db, user_id)
        if durable["session_id"] not in {row["session_id"] for row in sessions}:
            raise RuntimeError("Current session was omitted from logout-all selection.")
        if device["id"] not in {row["id"] for row in devices}:
            raise RuntimeError("Current trusted device was omitted from logout-all selection.")

        revoked_sessions, revoked_devices = _revoke_locked_populations(
            db, user_id, sessions, devices
        )
        for row in sorted(revoked_sessions, key=lambda item: str(item["session_id"])):
            reference = session_event_reference(row["session_id"])
            write_security_event(
                db,
                "security.session.revoked",
                _context(request_id, user, session_ref=reference),
                EventData(metadata={"result_code": "logout_all"}),
                idempotency_scope="security.session.revoked",
                idempotency_key=f"{request_id}:{reference}",
            )
        for row in sorted(revoked_devices, key=lambda item: item["id"]):
            reference = trusted_device_reference(row["id"])
            write_security_event(
                db,
                "security.trusted_device.removed",
                _context(request_id, user, device_ref=reference),
                EventData(metadata={"result_code": "logout_all"}),
                idempotency_scope="security.trusted_device.removed",
                idempotency_key=f"{request_id}:{reference}",
            )
        if gate:
            step_up_service.write_consumed_event(
                db, request_id=request_id, gate=gate, descriptor=LOGOUT_ALL_DESCRIPTOR
            )
        write_security_event(
            db,
            "security.logout.completed",
            _context(request_id, user),
            EventData(metadata={"result_code": "completed"}),
            idempotency_scope="security.logout.completed",
            idempotency_key=request_id,
        )

    return LogoutAllResult(
        "success",
        session_count=len(revoked_sessions),
        trusted_device_count=len(revoked_devices),
    )
