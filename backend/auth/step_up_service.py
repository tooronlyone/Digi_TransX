"""Action-bound, one-use MPIN step-up authorization owner.

Raw MPINs, authorization proofs, claim proofs, and destination identifiers stay
in process memory. Persistent and canonical-event evidence is digest/reference
only. Every function participates in its caller-owned transaction.
"""

from dataclasses import dataclass
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


# Foundation only: these policies recognize the six approved Category A
# targets, but no protected domain mutation consumes them in this phase.
ACTION_POLICIES = {
    "one_time.checkout.wallet_only": ActionPolicy("order", amount_required=True),
    "wallet.withdrawal.request": ActionPolicy(
        "wallet", amount_required=True, destination_required=True
    ),
    "wallet.withdrawal_limit.purchase": ActionPolicy("wallet", amount_required=True),
    "wallet.payout_destination.replace": ActionPolicy(
        "wallet", destination_required=True
    ),
    "agreement.finalize": ActionPolicy("agreement", amount_required=True),
    "client.delivery.confirm_release": ActionPolicy("trip", amount_required=True),
}


def _digest(raw):
    return hashlib.sha256(raw.encode("ascii")).digest()


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
        "destination_fingerprint",
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
    canonical = {
        "action_key": action_key,
        "resource_type": policy.resource_type,
        "resource_id": resource_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "destination_fingerprint": (
            destination_digest.hex() if destination_digest is not None else None
        ),
    }
    encoded = json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("ascii")
    return {**canonical, "destination_digest": destination_digest,
            "request_fingerprint": hashlib.sha256(encoded).digest()}


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
             request_fingerprint,expires_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
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
            descriptor["destination_digest"], descriptor["request_fingerprint"],
        ),
    ).fetchone()
    if not row:
        return None
    return {"authorization_id": row["authorization_id"], "proof": proof,
            "issued_at": row["issued_at"], "expires_at": row["expires_at"]}


def _lock_bound(executor, *, raw_proof, user_id, session_id, trusted_device_id,
                credential_generation, descriptor):
    if not isinstance(raw_proof, str) or len(raw_proof) < 32:
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
         FOR UPDATE
        """,
        (_digest(raw_proof), user_id, session_id, trusted_device_id,
         credential_generation, descriptor["action_key"], descriptor["resource_type"],
         descriptor["resource_id"], descriptor["request_fingerprint"],
         descriptor["amount_minor"], descriptor["currency"],
         descriptor["destination_digest"]),
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


def finalize_claim(executor, *, authorization_id, raw_claim, reconciliation_required=False):
    if not isinstance(raw_claim, str) or len(raw_claim) < 32:
        return None
    target = "reconciliation_required" if reconciliation_required else "consumed"
    timestamp = "reconciliation_required_at" if reconciliation_required else "consumed_at"
    return executor.execute(
        f"""UPDATE public.mpin_step_up_authorizations
                SET state=%s,{timestamp}=now()
              WHERE authorization_id=%s AND state='claimed' AND claim_digest=%s
              RETURNING *""",
        (target, str(authorization_id), _digest(raw_claim)),
    ).fetchone()


def verify_authorization(executor, **binding):
    """Lock and verify an exact available, unexpired binding without mutating it."""
    row = _lock_bound(executor, **binding)
    return bool(
        row and row["state"] == "available"
        and row["expires_at"] > row["database_now"]
    )
