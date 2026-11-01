"""Invalidate server authentication around a verified provider password update.

The caller has already consumed an OTP/reset claim. Revocation commits before
provider I/O, so provider or finalization failures cannot resurrect old sessions.
The version/pending gate rejects password proofs obtained across this operation.
"""

import uuid
import logging
from contextlib import contextmanager
from supabase_auth.errors import AuthApiError, AuthWeakPasswordError

from events.contract import EventContext, EventData
from events.writer import write_security_event
from shared.db import open_db
from auth.session_service import session_event_reference, trusted_device_reference


class CredentialChangeUnavailable(RuntimeError):
    pass


class PasswordProviderUpdateFailed(CredentialChangeUnavailable):
    def __init__(self, *, reconciliation_required=True):
        super().__init__("Password provider update could not be confirmed.")
        self.reconciliation_required = reconciliation_required


@contextmanager
def _password_change_guard(user_id):
    """Serialize provider calls with a transaction-scoped advisory lock.

    This works with both session and transaction poolers. A rare password update
    holds this otherwise idle transaction across bounded provider I/O. The
    separately committed pending flag survives connection/process loss.
    """
    with open_db() as db:
        locked = db.execute(
            "SELECT pg_try_advisory_xact_lock(hashtextextended('dtx.password-change:' || %s::text,0)) AS acquired",
            (user_id,),
        ).fetchone()
        if not locked or not locked["acquired"]:
            raise CredentialChangeUnavailable("A password update is already in progress.")
        yield


def begin_password_change(user_id, auth_id, reason):
    if reason not in {"password_changed", "password_reset"}:
        raise ValueError("Invalid password-change reason.")
    request_id = f"credential.change.{uuid.uuid4().hex}"
    with open_db() as db:
        owner = db.execute("SELECT * FROM users WHERE id=%s FOR UPDATE", (user_id,)).fetchone()
        if not owner or not auth_id or str(owner.get("auth_id")) != str(auth_id):
            raise CredentialChangeUnavailable("Authentication identity changed.")
        if owner.get("password_change_pending"):
            raise CredentialChangeUnavailable("Password update requires reconciliation.")
        version = db.execute(
            "UPDATE users SET credentials_version=credentials_version+1, "
            "password_change_pending=true,updated_at=now() WHERE id=%s "
            "RETURNING credentials_version", (user_id,),
        ).fetchone()["credentials_version"]
        sessions = db.execute(
            "UPDATE user_sessions SET revoked_at=now(),revocation_reason=%s, "
            "access_locked=true,access_locked_at=coalesce(access_locked_at,now()), "
            "access_proof_digest=NULL,access_proof_expires_at=NULL, "
            "updated_at=now() WHERE user_id=%s AND revoked_at IS NULL RETURNING session_id",
            (reason,user_id),
        ).fetchall()
        devices = db.execute(
            "UPDATE trusted_devices SET revoked_at=now() WHERE user_id=%s "
            "AND revoked_at IS NULL RETURNING id", (user_id,),
        ).fetchall()
        for session in sessions:
            ref = session_event_reference(session["session_id"])
            write_security_event(
                db,"security.session.revoked",
                EventContext(request_id=request_id,source="server_route",actor_type="system",
                             subject_user_id=user_id,session_ref=ref),
                EventData(metadata={"result_code":reason}),
                idempotency_scope="security.session.revoked",
                idempotency_key=f"{request_id}.{ref}",
            )
        for device in devices:
            ref = trusted_device_reference(device["id"])
            write_security_event(
                db,"security.trusted_device.removed",
                EventContext(request_id=request_id,source="server_route",actor_type="system",
                             subject_user_id=user_id,device_ref=ref),
                EventData(metadata={"result_code":reason}),
                idempotency_scope="security.trusted_device.removed",
                idempotency_key=f"{request_id}.{ref}",
            )
    return version


def finish_password_change(db,user_id,auth_id,version):
    owner = db.execute("SELECT * FROM users WHERE id=%s FOR UPDATE", (user_id,)).fetchone()
    if (not owner or str(owner.get("auth_id")) != str(auth_id)
            or owner.get("credentials_version") != version
            or not owner.get("password_change_pending")):
        raise CredentialChangeUnavailable("Password update requires reconciliation.")
    db.execute(
        "UPDATE users SET password_change_pending=false,credentials_version=credentials_version+1, "
        "updated_at=now() WHERE id=%s", (user_id,),
    )


def reconcile_rejected_password_change(user_id,auth_id,version):
    """Clear a positively rejected attempt; old sessions stay revoked.

    A timeout/5xx is never proof of rejection and must not call this function.
    """
    with open_db() as db:
        finish_password_change(db,user_id,auth_id,version)


def execute_password_change(user_id,auth_id,new_password,reason,provider_update,*,finalize=None):
    """Revoke, call the provider once, and finalize under one owner operation.

    Ambiguous provider outcomes and database finalization failures stay pending.
    Automatically retrying them could race a delayed provider write. Operator
    reconciliation is required before another OTP-authorized attempt can start.
    """
    with _password_change_guard(user_id):
        version = begin_password_change(user_id,auth_id,reason)
        try:
            provider_update(auth_id,new_password)
        except Exception as exc:
            # Only a structured, terminal client rejection proves the provider
            # did not accept this update. Never infer this from error text.
            rejected = isinstance(exc, AuthWeakPasswordError) or (
                isinstance(exc, AuthApiError) and exc.status in {400,401,403,404,422}
            )
            pending = True
            if rejected:
                try:
                    reconcile_rejected_password_change(user_id,auth_id,version)
                    pending = False
                except Exception:
                    logging.getLogger(__name__).error("Password-change reconciliation remains pending.")
            raise PasswordProviderUpdateFailed(reconciliation_required=pending) from None
        with open_db() as db:
            finish_password_change(db,user_id,auth_id,version)
            if finalize is not None:
                finalize(db)
