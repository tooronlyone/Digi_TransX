"""Server-verified, action-and-target-bound administrator step-up authentication."""

from decimal import Decimal
import hashlib
import json
import secrets

from auth.helpers import (
    ACCESS_PROOF_COOKIE_NAME,
    DEVICE_COOKIE_NAME,
    is_admin_user,
    json_response,
)
from auth.session_service import (
    digest_opaque_token,
    generate_opaque_token,
    lock_session_user_and_device,
    locked_access_proof_is_valid,
)


ADMIN_STEP_UP_HEADER = "X-Admin-Step-Up-Proof"
ADMIN_STEP_UP_TTL_MINUTES = 3
ADMIN_PASSWORD_MIN_LENGTH = 12
ADMIN_PASSWORD_MAX_LENGTH = 128

ADMIN_ACTION_POLICIES = {
    "admin.user.create": {
        "resource_type": "admin_user",
        "requires_positive_id": False,
        "label": "Create platform administrator account",
    },
    "admin.user.block_status": {
        "resource_type": "user",
        "requires_positive_id": True,
        "label": "Change user account block status",
    },
    "admin.withdrawal.approve": {
        "resource_type": "withdrawal_request",
        "requires_positive_id": True,
        "label": "Approve wallet withdrawal request",
    },
    "admin.withdrawal.reject": {
        "resource_type": "withdrawal_request",
        "requires_positive_id": True,
        "label": "Reject wallet withdrawal request",
    },
    "admin.commission.publish": {
        "resource_type": "commission_policy",
        "requires_positive_id": False,
        "label": "Publish platform commission policy",
    },
    "admin.dispute.resolve": {
        "resource_type": "dispute",
        "requires_positive_id": True,
        "label": "Resolve shipment financial dispute",
    },
    "admin.settlement.resolve": {
        "resource_type": "settlement",
        "requires_positive_id": True,
        "label": "Resolve freight settlement",
    },
    "admin.delivery_overdue.process": {
        "resource_type": "delivery_confirmation_sweep",
        "requires_positive_id": False,
        "label": "Process overdue delivery confirmations",
    },
    "admin.owner_operator.verify": {
        "resource_type": "owner_operator",
        "requires_positive_id": True,
        "label": "Verify owner-operator driver credentials",
    },
    "admin.incident.decide": {
        "resource_type": "operational_incident",
        "requires_positive_id": True,
        "label": "Record operational incident investigation decision",
    },
}


class AdminStepUpValidationError(ValueError):
    """Raised when an administrator step-up action descriptor or password is invalid."""


def validate_admin_password(password):
    """Validate bounded administrator password strength and composition."""
    if not isinstance(password, str):
        return False, "Password must be text."
    if any(ord(ch) < 32 for ch in password):
        return False, "Password contains unsupported control characters."
    if password != password.strip():
        return False, "Password must not begin or end with whitespace."
    if len(password) < ADMIN_PASSWORD_MIN_LENGTH or len(password) > ADMIN_PASSWORD_MAX_LENGTH:
        return (
            False,
            f"Admin password must be between {ADMIN_PASSWORD_MIN_LENGTH} and {ADMIN_PASSWORD_MAX_LENGTH} characters.",
        )
    has_letter = any(ch.isalpha() for ch in password)
    has_digit_or_symbol = any(ch.isdigit() or not ch.isalnum() for ch in password)
    if not (has_letter and has_digit_or_symbol):
        return False, "Admin password must include letters and at least one number or symbol."
    return True, None


def _canonical_value(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, dict):
        return {str(k): _canonical_value(value[k]) for k in sorted(value.keys(), key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return str(value)


def _compute_descriptor_fingerprint(action_key, resource_type, resource_id, target):
    payload = {
        "action_key": action_key,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "target": _canonical_value(target if target is not None else {}),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def _parse_fingerprint_hex(hex_value):
    if not isinstance(hex_value, str):
        raise AdminStepUpValidationError("Invalid step-up request fingerprint.")
    cleaned = hex_value.strip().lower()
    if len(cleaned) != 64:
        raise AdminStepUpValidationError("Invalid step-up request fingerprint length.")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise AdminStepUpValidationError("Malformed step-up request fingerprint.") from exc


def build_admin_descriptor(
    action_key,
    *,
    resource_id=1,
    resource_type=None,
    target=None,
    request_fingerprint_hex=None,
):
    """Build and validate a canonical administrator step-up descriptor."""
    if not isinstance(action_key, str) or action_key not in ADMIN_ACTION_POLICIES:
        raise AdminStepUpValidationError("Unsupported administrator step-up action.")
    policy = ADMIN_ACTION_POLICIES[action_key]
    expected_type = policy["resource_type"]
    if resource_type is not None and resource_type != expected_type:
        raise AdminStepUpValidationError("Mismatched administrator step-up resource type.")

    parsed_id = 1 if (resource_id is None and not policy["requires_positive_id"]) else resource_id
    if isinstance(parsed_id, bool):
        raise AdminStepUpValidationError("Invalid administrator step-up resource identifier.")
    try:
        parsed_id = int(parsed_id)
    except (TypeError, ValueError) as exc:
        raise AdminStepUpValidationError("Invalid administrator step-up resource identifier.") from exc
    if parsed_id <= 0:
        raise AdminStepUpValidationError("Administrator step-up resource identifier must be positive.")

    if request_fingerprint_hex is not None:
        fingerprint = _parse_fingerprint_hex(request_fingerprint_hex)
        if target is not None:
            expected_fp = _compute_descriptor_fingerprint(action_key, expected_type, parsed_id, target)
            if not secrets.compare_digest(fingerprint, expected_fp):
                raise AdminStepUpValidationError("Administrator step-up fingerprint does not match target payload.")
    else:
        fingerprint = _compute_descriptor_fingerprint(action_key, expected_type, parsed_id, target)

    return {
        "action_key": action_key,
        "resource_type": expected_type,
        "resource_id": parsed_id,
        "label": policy["label"],
        "request_fingerprint": fingerprint,
        "request_fingerprint_ref": fingerprint[:8].hex(),
    }


def public_admin_descriptor(descriptor):
    """Serialize a canonical descriptor safely for challenge responses and modal rendering."""
    return {
        "action_key": descriptor["action_key"],
        "resource_type": descriptor["resource_type"],
        "resource_id": descriptor["resource_id"],
        "label": descriptor["label"],
        "request_fingerprint": descriptor["request_fingerprint"].hex(),
        "request_fingerprint_ref": descriptor["request_fingerprint_ref"],
    }


def lock_current_admin_authentication(db, request_object):
    """Lock the current durable session, user, and trusted device rows cleanly."""
    current_session = getattr(request_object, "current_session", None)
    current_user = getattr(request_object, "current_user", None)
    session_id = current_session.get("session_id") if isinstance(current_session, dict) else None
    user_id = current_user.get("id") if isinstance(current_user, dict) else None
    raw_device = request_object.cookies.get(DEVICE_COOKIE_NAME, "")
    raw_access_proof = request_object.cookies.get(ACCESS_PROOF_COOKIE_NAME, "")
    if not (session_id and user_id and raw_device and raw_access_proof):
        return None, None, None, "missing_session_binding"

    durable, user, device = lock_session_user_and_device(
        db, session_id, user_id, digest_opaque_token(raw_device)
    )
    if not (durable and user and device):
        return None, None, None, "session_not_found"
    if durable.get("revoked_at") is not None or device.get("revoked_at") is not None:
        return None, None, None, "session_revoked"
    if not locked_access_proof_is_valid(db, durable, raw_access_proof):
        return None, None, None, "access_proof_invalid"
    if user.get("is_blocked"):
        return None, None, None, "user_blocked"
    if not is_admin_user(user):
        return None, None, None, "not_admin"
    return durable, user, device, None


def issue_admin_authorization(
    db, *, user_id, session_id, trusted_device_id, credentials_version, descriptor
):
    """Persist a single-use 3-minute action-bound authorization proof."""
    db.execute(
        """
        UPDATE admin_step_up_authorizations
        SET state = 'expired', expired_at = now()
        WHERE user_id = %s
          AND session_id = %s
          AND state = 'available'
          AND expires_at <= now()
        """,
        (user_id, str(session_id)),
    )
    db.execute(
        """
        UPDATE admin_step_up_authorizations
        SET state = 'invalidated', invalidated_at = now()
        WHERE user_id = %s
          AND session_id = %s
          AND action_key = %s
          AND resource_type = %s
          AND resource_id = %s
          AND request_fingerprint = %s
          AND state = 'available'
        """,
        (
            user_id,
            str(session_id),
            descriptor["action_key"],
            descriptor["resource_type"],
            descriptor["resource_id"],
            descriptor["request_fingerprint"],
        ),
    )

    raw_proof = generate_opaque_token()
    proof_digest = digest_opaque_token(raw_proof)
    row = db.execute(
        """
        INSERT INTO admin_step_up_authorizations (
            user_id, session_id, trusted_device_id, credentials_version,
            proof_digest, action_key, resource_type, resource_id, request_fingerprint
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING authorization_id, expires_at
        """,
        (
            user_id,
            str(session_id),
            trusted_device_id,
            credentials_version,
            proof_digest,
            descriptor["action_key"],
            descriptor["resource_type"],
            descriptor["resource_id"],
            descriptor["request_fingerprint"],
        ),
    ).fetchone()
    db.execute(
        "UPDATE user_sessions SET password_verified_at = now(), updated_at = now() WHERE session_id = %s",
        (str(session_id),),
    )
    expires_at = row["expires_at"]
    return {
        "proof": raw_proof,
        "authorization_id": str(row["authorization_id"]),
        "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at),
        "action": public_admin_descriptor(descriptor),
    }


def _step_up_challenge(descriptor, message="Fresh administrator reauthentication is required for this action."):
    return json_response(
        {
            "success": False,
            "code": "admin_step_up_required",
            "message": message,
            "action": public_admin_descriptor(descriptor),
        },
        428,
    )


def require_admin_step_up(db, request_object, action_key, *, resource_id=1, target=None):
    """Lock caller authentication + consume single-use action-and-target-bound proof.

    Returns ``(None, authorization_row)`` on success, or ``(error_response, None)``
    on failure (401/403 for invalid/blocked session or non-admin, 428 for missing/invalid/
    expired/replayed/wrong-target step-up proof).
    """
    descriptor = build_admin_descriptor(action_key, resource_id=resource_id, target=target)
    durable, user, device, auth_err = lock_current_admin_authentication(db, request_object)
    if auth_err in {"user_blocked", "not_admin"}:
        return json_response({"success": False, "message": "Administrator authorization required."}, 403), None
    if auth_err:
        return json_response({"success": False, "message": "Authentication session is no longer valid."}, 401), None

    raw_proof = (request_object.headers.get(ADMIN_STEP_UP_HEADER) or "").strip()
    if not raw_proof:
        return _step_up_challenge(descriptor), None

    proof_digest = digest_opaque_token(raw_proof)
    auth_row = db.execute(
        """
        SELECT *, (expires_at <= now()) AS is_expired
        FROM admin_step_up_authorizations
        WHERE proof_digest = %s
        FOR UPDATE
        """,
        (proof_digest,),
    ).fetchone()
    if not auth_row:
        return _step_up_challenge(descriptor), None

    matches_binding = (
        auth_row["user_id"] == user["id"]
        and str(auth_row["session_id"]) == str(durable["session_id"])
        and auth_row["trusted_device_id"] == device["id"]
        and auth_row["credentials_version"] == user["credentials_version"]
        and auth_row["action_key"] == descriptor["action_key"]
        and auth_row["resource_type"] == descriptor["resource_type"]
        and auth_row["resource_id"] == descriptor["resource_id"]
        and bytes(auth_row["request_fingerprint"]) == descriptor["request_fingerprint"]
    )
    if not matches_binding or auth_row["state"] != "available" or auth_row["is_expired"]:
        return _step_up_challenge(descriptor), None

    consumed = db.execute(
        """
        UPDATE admin_step_up_authorizations
        SET state = 'consumed', consumed_at = now()
        WHERE authorization_id = %s
          AND state = 'available'
          AND expires_at > now()
        RETURNING *
        """,
        (str(auth_row["authorization_id"]),),
    ).fetchone()
    if not consumed:
        return _step_up_challenge(descriptor), None
    return None, dict(consumed)


def invalidate_user_step_up_authorizations(db, user_id):
    """Invalidate any open step-up proofs belonging to a user (e.g. on block)."""
    db.execute(
        """
        UPDATE admin_step_up_authorizations
        SET state = 'invalidated', invalidated_at = now()
        WHERE user_id = %s AND state IN ('available')
        """,
        (user_id,),
    )
    db.execute(
        """
        UPDATE mpin_step_up_authorizations
        SET state = 'invalidated', invalidated_at = now()
        WHERE user_id = %s AND state IN ('available', 'claimed')
        """,
        (user_id,),
    )
