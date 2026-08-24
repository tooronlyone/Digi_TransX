"""Action-bound, one-use MPIN step-up authorization owner.

Raw MPINs, authorization proofs, claim proofs, and destination identifiers stay
in process memory. Persistent and canonical-event evidence is digest/reference
only. Every function participates in its caller-owned transaction.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
import secrets
import uuid


PROOF_BYTES = 32
AUTHORIZATION_LIFETIME_SECONDS = 180
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class StepUpError(ValueError):
    """A bounded descriptor or authorization-state failure."""


@dataclass(frozen=True)
class ActionPolicy:
    resource_type: str
    amount_required: bool = False
    destination_required: bool = False
    funding_sources: frozenset[str] = frozenset()


# Canonical policies for approved action-bound targets. Logout-all is a
# security action, not an alias for one of the six Category A business actions.
ACTION_POLICIES = {
    "one_time.checkout.wallet_only": ActionPolicy(
        "order", amount_required=True, funding_sources=frozenset({"wallet"})
    ),
    "wallet.withdrawal.request": ActionPolicy(
        "wallet", amount_required=True, destination_required=True
    ),
    "wallet.withdrawal_limit.purchase": ActionPolicy(
        "wallet", amount_required=True, funding_sources=frozenset({"wallet"})
    ),
    "wallet.payout_destination.replace": ActionPolicy(
        "wallet", destination_required=True
    ),
    "agreement.finalize": ActionPolicy("agreement", amount_required=True),
    "client.delivery.confirm_release": ActionPolicy("trip", amount_required=True),
    "security.logout_all": ActionPolicy("account_security"),
}


STEP_UP_PROOF_HEADER = "X-MPIN-Step-Up-Proof"


@dataclass(frozen=True)
class ConsumptionGate:
    status: str
    authorization: dict | None = None
    claim_proof: str | None = None
    durable_session: dict | None = None
    user: dict | None = None
    trusted_device: dict | None = None
    credential: dict | None = None


def _digest(raw):
    return hashlib.sha256(raw.encode("ascii")).digest()


def money_to_minor(value):
    """Convert an authoritative PKR amount to exact integer minor units."""
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise StepUpError("The action amount is invalid.") from exc
    minor = int(amount * 100)
    if minor <= 0:
        raise StepUpError("The action amount must be positive.")
    return minor


def payout_destination_input_fingerprint(card_data):
    """Digest a new payout destination without retaining its personal fields."""
    from shared.payments import parse_card_expiry

    data = card_data if isinstance(card_data, dict) else {}
    number = re.sub(r"\D", "", str(data.get("card_number") or ""))
    month, year, expiry_error = parse_card_expiry(data.get("card_expiry"))
    if expiry_error:
        raise StepUpError("The payout destination is invalid.")
    canonical = {
        "bank": " ".join(str(data.get("bank") or "").strip().split()),
        "card_expiry": f"{month:02d}/{year:04d}",
        "card_holder": " ".join(str(data.get("card_holder") or "").strip().split()),
        "card_number": number,
    }
    encoded = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stored_payout_destination_fingerprint(provider_token):
    if not isinstance(provider_token, str) or not provider_token:
        raise StepUpError("A payout destination is required.")
    return hashlib.sha256(
        ("payout-token:" + provider_token).encode("utf-8")
    ).hexdigest()


def _digest_hex(value, field_name, *, required):
    if value is None and not required:
        return None
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise StepUpError(f"{field_name} must be a lowercase SHA-256 digest.")
    return bytes.fromhex(value)


def normalize_descriptor(value):
    if not isinstance(value, dict):
        raise StepUpError("A step-up action descriptor is required.")
    allowed = {
        "action_key", "resource_type", "resource_id", "amount_minor", "currency",
        "destination_fingerprint", "funding_source",
    }
    if set(value) - allowed:
        raise StepUpError("The step-up action descriptor contains unknown fields.")
    action_key = value.get("action_key")
    policy = ACTION_POLICIES.get(action_key)
    if policy is None or value.get("resource_type") != policy.resource_type:
        raise StepUpError("The step-up action is not recognized.")
    resource_id = value.get("resource_id")
    if isinstance(resource_id, bool) or not isinstance(resource_id, int) or resource_id <= 0:
        raise StepUpError("resource_id must be a positive integer.")
    amount_minor = value.get("amount_minor")
    currency = value.get("currency")
    if policy.amount_required:
        if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
            raise StepUpError("A positive amount_minor is required for this action.")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise StepUpError("A three-letter uppercase currency is required.")
    elif amount_minor is not None or currency is not None:
        raise StepUpError("This action does not accept an amount or currency.")
    destination_digest = _digest_hex(
        value.get("destination_fingerprint"),
        "destination_fingerprint",
        required=policy.destination_required,
    )
    if not policy.destination_required and destination_digest is not None:
        raise StepUpError("This action does not accept a destination fingerprint.")
    funding_source = value.get("funding_source")
    if policy.funding_sources:
        if funding_source not in policy.funding_sources:
            raise StepUpError("The funding source is not valid for this action.")
    elif funding_source is not None:
        raise StepUpError("This action does not accept a funding source.")
    canonical = {
        "action_key": action_key,
        "resource_type": policy.resource_type,
        "resource_id": resource_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "destination_fingerprint": (
            destination_digest.hex() if destination_digest is not None else None
        ),
        "funding_source": funding_source,
    }
    encoded = json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("ascii")
    return {**canonical, "destination_digest": destination_digest,
            "request_fingerprint": hashlib.sha256(encoded).digest()}


def public_descriptor(descriptor):
    return {
        key: descriptor.get(key)
        for key in (
            "action_key", "resource_type", "resource_id", "amount_minor",
            "currency", "destination_fingerprint", "funding_source",
        )
        if descriptor.get(key) is not None
    }


def authorization_reference(authorization_id):
    return "authorization_" + uuid.UUID(str(authorization_id)).hex


def request_fingerprint_reference(request_fingerprint):
    return "request_" + bytes(request_fingerprint).hex()


def issue_authorization(
    executor, *, user_id, session_id, trusted_device_id, credential_generation,
    descriptor,
):
    """Insert one available digest-only authorization and return its raw proof.

    The partial unique index makes simultaneous issuance for an identical live
    binding deterministic: exactly one caller receives a proof.
    """
    proof = secrets.token_urlsafe(PROOF_BYTES)
    authorization_id = uuid.uuid4()
    row = executor.execute(
        """
        INSERT INTO public.mpin_step_up_authorizations
            (authorization_id,user_id,session_id,trusted_device_id,
             credential_generation,proof_digest,action_key,resource_type,
             resource_id,amount_minor,currency,destination_digest,
             funding_source,request_fingerprint,expires_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                now() + interval '3 minutes')
        ON CONFLICT (user_id,session_id,action_key,resource_type,resource_id,
                     request_fingerprint) WHERE state='available'
        DO NOTHING
        RETURNING authorization_id,issued_at,expires_at
        """,
        (
            str(authorization_id), user_id, session_id, trusted_device_id,
            credential_generation, _digest(proof), descriptor["action_key"],
            descriptor["resource_type"], descriptor["resource_id"],
            descriptor["amount_minor"], descriptor["currency"],
            descriptor["destination_digest"], descriptor["funding_source"],
            descriptor["request_fingerprint"],
        ),
    ).fetchone()
    if not row:
        return None
    return {"authorization_id": row["authorization_id"], "proof": proof,
            "issued_at": row["issued_at"], "expires_at": row["expires_at"]}


def _lock_bound(executor, *, raw_proof, user_id, session_id, trusted_device_id,
                credential_generation, descriptor):
    if not isinstance(raw_proof, str) or not 32 <= len(raw_proof) <= 512:
        return None
    return executor.execute(
        """
        SELECT a.*, now() AS database_now
          FROM public.mpin_step_up_authorizations a
         WHERE proof_digest=%s AND user_id=%s AND session_id=%s
           AND trusted_device_id=%s AND credential_generation=%s
           AND action_key=%s AND resource_type=%s AND resource_id=%s
           AND request_fingerprint=%s
           AND amount_minor IS NOT DISTINCT FROM %s
           AND currency IS NOT DISTINCT FROM %s
           AND destination_digest IS NOT DISTINCT FROM %s
           AND funding_source IS NOT DISTINCT FROM %s
         FOR UPDATE
        """,
        (_digest(raw_proof), user_id, session_id, trusted_device_id,
         credential_generation, descriptor["action_key"], descriptor["resource_type"],
         descriptor["resource_id"], descriptor["request_fingerprint"],
         descriptor["amount_minor"], descriptor["currency"],
         descriptor["destination_digest"], descriptor["funding_source"]),
    ).fetchone()


def consume_authorization(executor, **binding):
    """Atomically consume an available authorization for a DB-owned mutation."""
    row = _lock_bound(executor, **binding)
    if not row or row["state"] != "available":
        return None
    if row["expires_at"] <= row["database_now"]:
        executor.execute(
            """UPDATE public.mpin_step_up_authorizations
                  SET state='expired',expired_at=now()
                WHERE authorization_id=%s AND state='available'""",
            (row["authorization_id"],),
        )
        return None
    return executor.execute(
        """UPDATE public.mpin_step_up_authorizations
              SET state='consumed',consumed_at=now()
            WHERE authorization_id=%s AND state='available'
            RETURNING *""",
        (row["authorization_id"],),
    ).fetchone()


def claim_authorization(executor, **binding):
    """Claim once before a non-transactional provider action; return raw claim."""
    row = _lock_bound(executor, **binding)
    if not row or row["state"] != "available":
        return None
    if row["expires_at"] <= row["database_now"]:
        executor.execute(
            """UPDATE public.mpin_step_up_authorizations
                  SET state='expired',expired_at=now()
                WHERE authorization_id=%s AND state='available'""",
            (row["authorization_id"],),
        )
        return None
    claim = secrets.token_urlsafe(PROOF_BYTES)
    claimed = executor.execute(
        """UPDATE public.mpin_step_up_authorizations
              SET state='claimed',claim_digest=%s,claimed_at=now()
            WHERE authorization_id=%s AND state='available'
            RETURNING *""",
        (_digest(claim), row["authorization_id"]),
    ).fetchone()
    return (claimed, claim) if claimed else None


def finalize_claim(
    executor, *, authorization_id, raw_claim, reconciliation_required=False,
    provider_rejected=False,
):
    if not isinstance(raw_claim, str) or not 32 <= len(raw_claim) <= 512:
        return None
    if reconciliation_required and provider_rejected:
        raise ValueError("A claim outcome must be unambiguous.")
    target = (
        "reconciliation_required" if reconciliation_required
        else "invalidated" if provider_rejected
        else "consumed"
    )
    timestamp = (
        "reconciliation_required_at" if reconciliation_required
        else "invalidated_at" if provider_rejected
        else "consumed_at"
    )
    return executor.execute(
        f"""UPDATE public.mpin_step_up_authorizations
                SET state=%s,{timestamp}=now()
              WHERE authorization_id=%s AND state='claimed' AND claim_digest=%s
              RETURNING *""",
        (target, str(authorization_id), _digest(raw_claim)),
    ).fetchone()


def reconcile_claim_after_uncertain_outcome(
    executor, *, gate, descriptor,
):
    """Classify and safely reconcile one exact claim after an uncertain commit.

    A reconnect can observe consumed only when the original transaction
    committed. Otherwise it moves the still-claimed authorization to the
    terminal reconciliation state. Repeated calls are idempotent and never
    make an authorization available again.
    """
    if (
        not gate
        or not gate.authorization
        or not isinstance(gate.claim_proof, str)
        or not 32 <= len(gate.claim_proof) <= 512
    ):
        return None
    row = executor.execute(
        """
        SELECT *
          FROM public.mpin_step_up_authorizations
         WHERE authorization_id=%s AND claim_digest=%s
           AND user_id=%s AND session_id=%s AND trusted_device_id=%s
           AND credential_generation=%s
           AND action_key=%s AND resource_type=%s AND resource_id=%s
           AND request_fingerprint=%s
           AND amount_minor IS NOT DISTINCT FROM %s
           AND currency IS NOT DISTINCT FROM %s
           AND destination_digest IS NOT DISTINCT FROM %s
           AND funding_source IS NOT DISTINCT FROM %s
         FOR UPDATE
        """,
        (
            gate.authorization["authorization_id"], _digest(gate.claim_proof),
            gate.user["id"], gate.durable_session["session_id"],
            gate.trusted_device["id"], gate.credential["credential_generation"],
            descriptor["action_key"], descriptor["resource_type"],
            descriptor["resource_id"], descriptor["request_fingerprint"],
            descriptor["amount_minor"], descriptor["currency"],
            descriptor["destination_digest"], descriptor["funding_source"],
        ),
    ).fetchone()
    if not row or row["state"] not in {
        "claimed", "consumed", "reconciliation_required",
    }:
        return None
    observed_state = row["state"]
    if observed_state == "claimed":
        row = executor.execute(
            """
            UPDATE public.mpin_step_up_authorizations
               SET state='reconciliation_required',
                   reconciliation_required_at=now()
             WHERE authorization_id=%s AND state='claimed' AND claim_digest=%s
             RETURNING *
            """,
            (gate.authorization["authorization_id"], _digest(gate.claim_proof)),
        ).fetchone()
        if not row:
            return None
    return {"authorization": row, "observed_state": observed_state}


def lock_and_finalize_current_request_claim(
    executor, request_object, *, gate, descriptor,
):
    """Revalidate every auth binding and consume an exact provider claim.

    The caller continues the same transaction with its locked domain rows and
    evidence write. Provider I/O must already be complete before this helper is
    entered.
    """
    from auth import mpin_service, session_service
    from auth.helpers import (
        ACCESS_PROOF_COOKIE_NAME,
        DEVICE_COOKIE_NAME,
        SESSION_TOKEN_COOKIE_NAME,
    )
    from auth.trusted_device_service import TrustedDeviceError, digest_token

    try:
        device_digest = digest_token(
            request_object.cookies.get(DEVICE_COOKIE_NAME, "")
        )
        session_digest = session_service.digest_opaque_token(
            request_object.cookies.get(SESSION_TOKEN_COOKIE_NAME, "")
        )
    except (TrustedDeviceError, session_service.SessionFoundationError):
        return None
    durable, user, device = session_service.lock_session_user_and_device(
        executor,
        request_object.current_session["session_id"],
        request_object.current_user["id"],
        device_digest,
    )
    if not durable or not user or not device:
        return None
    if not secrets.compare_digest(bytes(durable["token_digest"]), session_digest):
        return None
    if not session_service.locked_access_proof_is_valid(
        executor,
        durable,
        request_object.cookies.get(ACCESS_PROOF_COOKIE_NAME, ""),
    ):
        return None
    credential = mpin_service.lock_credential(
        executor, request_object.current_user["id"]
    )
    if (
        not credential
        or credential["permanently_locked"]
        or credential["credential_generation"]
            != gate.authorization["credential_generation"]
    ):
        return None
    if not isinstance(gate.claim_proof, str) or not 32 <= len(gate.claim_proof) <= 512:
        return None
    return executor.execute(
        """
        UPDATE public.mpin_step_up_authorizations
           SET state='consumed',consumed_at=now()
         WHERE authorization_id=%s AND state='claimed' AND claim_digest=%s
           AND user_id=%s AND session_id=%s AND trusted_device_id=%s
           AND credential_generation=%s
           AND action_key=%s AND resource_type=%s AND resource_id=%s
           AND request_fingerprint=%s
           AND amount_minor IS NOT DISTINCT FROM %s
           AND currency IS NOT DISTINCT FROM %s
           AND destination_digest IS NOT DISTINCT FROM %s
           AND funding_source IS NOT DISTINCT FROM %s
         RETURNING *
        """,
        (
            gate.authorization["authorization_id"], _digest(gate.claim_proof),
            user["id"], durable["session_id"], device["id"],
            credential["credential_generation"], descriptor["action_key"],
            descriptor["resource_type"], descriptor["resource_id"],
            descriptor["request_fingerprint"], descriptor["amount_minor"],
            descriptor["currency"], descriptor["destination_digest"],
            descriptor["funding_source"],
        ),
    ).fetchone()


def verify_authorization(executor, **binding):
    """Lock and verify an exact available, unexpired binding without mutating it."""
    row = _lock_bound(executor, **binding)
    return bool(
        row and row["state"] == "available"
        and row["expires_at"] > row["database_now"]
    )


def lock_and_consume_for_mutation(
    executor, *, user_id, session_id, raw_session_token, raw_device_token,
    raw_access_proof, raw_step_up_proof, descriptor,
):
    """Revalidate the complete authentication chain and consume one proof.

    Lock order is session -> user -> trusted device -> software proof verdict ->
    MPIN credential generation -> step-up authorization. The caller owns the
    transaction and must roll it back if its domain mutation or evidence fails.
    """
    from auth import mpin_service, session_service
    from auth.trusted_device_service import TrustedDeviceError, digest_token

    try:
        device_digest = digest_token(raw_device_token)
        session_digest = session_service.digest_opaque_token(raw_session_token)
    except (TrustedDeviceError, session_service.SessionFoundationError):
        return ConsumptionGate("authentication_required")
    durable, user, device = session_service.lock_session_user_and_device(
        executor, session_id, user_id, device_digest
    )
    if not durable or not user or not device:
        return ConsumptionGate("authentication_required")
    if not secrets.compare_digest(bytes(durable["token_digest"]), session_digest):
        return ConsumptionGate("authentication_required")
    if not session_service.locked_access_proof_is_valid(
        executor, durable, raw_access_proof
    ):
        return ConsumptionGate(
            "access_locked", durable_session=durable, user=user,
            trusted_device=device,
        )
    credential = mpin_service.lock_credential(executor, user_id)
    if not credential:
        return ConsumptionGate(
            "mpin_enrollment_required", durable_session=durable, user=user,
            trusted_device=device,
        )
    if credential["permanently_locked"]:
        return ConsumptionGate(
            "mpin_locked", durable_session=durable, user=user,
            trusted_device=device, credential=credential,
        )
    authorization = consume_authorization(
        executor,
        raw_proof=raw_step_up_proof,
        user_id=user_id,
        session_id=session_id,
        trusted_device_id=device["id"],
        credential_generation=credential["credential_generation"],
        descriptor=descriptor,
    )
    if not authorization:
        return ConsumptionGate(
            "step_up_required", durable_session=durable, user=user,
            trusted_device=device, credential=credential,
        )
    return ConsumptionGate(
        "authorized", authorization=dict(authorization),
        durable_session=durable, user=user, trusted_device=device,
        credential=credential,
    )


def lock_and_claim_for_provider_mutation(
    executor, *, user_id, session_id, raw_session_token, raw_device_token,
    raw_access_proof, raw_step_up_proof, descriptor,
):
    """Revalidate the authentication chain and claim before a provider call."""
    from auth import mpin_service, session_service
    from auth.trusted_device_service import TrustedDeviceError, digest_token

    try:
        device_digest = digest_token(raw_device_token)
        session_digest = session_service.digest_opaque_token(raw_session_token)
    except (TrustedDeviceError, session_service.SessionFoundationError):
        return ConsumptionGate("authentication_required")
    durable, user, device = session_service.lock_session_user_and_device(
        executor, session_id, user_id, device_digest
    )
    if not durable or not user or not device:
        return ConsumptionGate("authentication_required")
    if not secrets.compare_digest(bytes(durable["token_digest"]), session_digest):
        return ConsumptionGate("authentication_required")
    if not session_service.locked_access_proof_is_valid(
        executor, durable, raw_access_proof
    ):
        return ConsumptionGate(
            "access_locked", durable_session=durable, user=user,
            trusted_device=device,
        )
    credential = mpin_service.lock_credential(executor, user_id)
    if not credential:
        return ConsumptionGate(
            "mpin_enrollment_required", durable_session=durable, user=user,
            trusted_device=device,
        )
    if credential["permanently_locked"]:
        return ConsumptionGate(
            "mpin_locked", durable_session=durable, user=user,
            trusted_device=device, credential=credential,
        )
    claimed = claim_authorization(
        executor,
        raw_proof=raw_step_up_proof,
        user_id=user_id,
        session_id=session_id,
        trusted_device_id=device["id"],
        credential_generation=credential["credential_generation"],
        descriptor=descriptor,
    )
    if not claimed:
        return ConsumptionGate(
            "step_up_required", durable_session=durable, user=user,
            trusted_device=device, credential=credential,
        )
    authorization, claim_proof = claimed
    return ConsumptionGate(
        "authorized", authorization=dict(authorization), claim_proof=claim_proof,
        durable_session=durable, user=user, trusted_device=device,
        credential=credential,
    )


def consume_current_request(executor, request_object, descriptor):
    """Read credentials from their sole approved transports and enter the gate."""
    from auth.helpers import (
        ACCESS_PROOF_COOKIE_NAME,
        DEVICE_COOKIE_NAME,
        SESSION_TOKEN_COOKIE_NAME,
    )

    return lock_and_consume_for_mutation(
        executor,
        user_id=request_object.current_user["id"],
        session_id=request_object.current_session["session_id"],
        raw_session_token=request_object.cookies.get(SESSION_TOKEN_COOKIE_NAME, ""),
        raw_device_token=request_object.cookies.get(DEVICE_COOKIE_NAME, ""),
        raw_access_proof=request_object.cookies.get(ACCESS_PROOF_COOKIE_NAME, ""),
        raw_step_up_proof=request_object.headers.get(STEP_UP_PROOF_HEADER, ""),
        descriptor=descriptor,
    )


def claim_current_request(executor, request_object, descriptor):
    """Claim an exact proof using credentials from their approved transports."""
    from auth.helpers import (
        ACCESS_PROOF_COOKIE_NAME,
        DEVICE_COOKIE_NAME,
        SESSION_TOKEN_COOKIE_NAME,
    )

    return lock_and_claim_for_provider_mutation(
        executor,
        user_id=request_object.current_user["id"],
        session_id=request_object.current_session["session_id"],
        raw_session_token=request_object.cookies.get(SESSION_TOKEN_COOKIE_NAME, ""),
        raw_device_token=request_object.cookies.get(DEVICE_COOKIE_NAME, ""),
        raw_access_proof=request_object.cookies.get(ACCESS_PROOF_COOKIE_NAME, ""),
        raw_step_up_proof=request_object.headers.get(STEP_UP_PROOF_HEADER, ""),
        descriptor=descriptor,
    )


def gate_error_response(gate, descriptor):
    """Return the one bounded HTTP failure contract, or None when authorized."""
    from auth.helpers import clear_access_proof_cookie, json_response

    if gate.status == "authorized":
        return None
    if gate.status == "authentication_required":
        return json_response(
            {"success": False, "message": "Authentication required."}, 401
        )
    if gate.status == "access_locked":
        return clear_access_proof_cookie(
            json_response(
                {
                    "success": False,
                    "code": "access_locked",
                    "message": "Access is locked.",
                },
                423,
            )
        )
    if gate.status == "mpin_enrollment_required":
        return json_response(
            {
                "success": False,
                "code": "mpin_enrollment_required",
                "message": "MPIN enrollment is required for this action.",
            },
            409,
        )
    if gate.status == "mpin_locked":
        return json_response(
            {
                "success": False,
                "code": "mpin_locked",
                "message": "MPIN is locked. Recovery is not currently available.",
            },
            423,
        )
    if gate.status == "step_up_required":
        return json_response(
            {
                "success": False,
                "code": "mpin_step_up_required",
                "message": "MPIN step-up authorization is required.",
                "action": public_descriptor(descriptor),
            },
            428,
        )
    raise RuntimeError("Unknown MPIN step-up gate state.")


def write_consumed_event(executor, *, request_id, gate, descriptor):
    from events.contract import EventContext, EventData
    from events.writer import write_security_event

    role = (gate.user.get("role") or "").strip().lower()
    metadata = {
        "authorization_ref": authorization_reference(
            gate.authorization["authorization_id"]
        ),
        "action_key": descriptor["action_key"],
        "resource_type": descriptor["resource_type"],
        "resource_id": descriptor["resource_id"],
        "request_fingerprint_ref": request_fingerprint_reference(
            descriptor["request_fingerprint"]
        ),
    }
    return write_security_event(
        executor,
        "security.mpin.step_up_consumed",
        EventContext(
            request_id=request_id,
            source="domain_service",
            actor_type="admin" if role == "platform_admin" else "user",
            actor_id=gate.user["id"],
            actor_role=role,
            subject_user_id=gate.user["id"],
        ),
        EventData(metadata=metadata),
        idempotency_scope="security.mpin.step_up_consumed",
        idempotency_key=request_id,
    )


def write_reconciliation_event(executor, *, request_id, gate, descriptor):
    from events.contract import EventContext, EventData
    from events.writer import write_security_event

    metadata = {
        "result_code": "domain_outcome_uncertain",
        "authorization_ref": authorization_reference(
            gate.authorization["authorization_id"]
        ),
        "action_key": descriptor["action_key"],
        "resource_type": descriptor["resource_type"],
        "resource_id": descriptor["resource_id"],
        "request_fingerprint_ref": request_fingerprint_reference(
            descriptor["request_fingerprint"]
        ),
    }
    return write_security_event(
        executor,
        "security.mpin.step_up_reconciliation_required",
        EventContext(
            request_id=request_id,
            source="domain_service",
            actor_type="system",
            subject_user_id=gate.user["id"],
        ),
        EventData(metadata=metadata),
        idempotency_scope="security.mpin.step_up_reconciliation_required",
        idempotency_key=request_id,
    )


def domain_event_context(*, request_id, gate):
    from events.contract import EventContext

    role = (gate.user.get("role") or "").strip().lower()
    return EventContext(
        request_id=request_id,
        source="domain_service",
        actor_type="admin" if role == "platform_admin" else "user",
        actor_id=gate.user["id"],
        actor_role=role,
        subject_user_id=gate.user["id"],
    )
