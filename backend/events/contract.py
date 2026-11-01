"""Strict shared envelope validation for canonical server-side events."""

from dataclasses import dataclass, field
import json
import math
import re
from typing import Mapping

from .catalog import get_event_definition, get_writable_event_definition


MAX_ENVELOPE_BYTES = 8192
MAX_METADATA_BYTES = 2048
MAX_STATE_BYTES = 1024
MAX_OBJECT_KEYS = 16
MAX_STRING_LENGTH = 128

ACTOR_TYPES = frozenset({"user", "admin", "system", "provider", "anonymous"})
SOURCES = frozenset(
    {
        "server_route",
        "domain_service",
        "admin_route",
        "scheduler",
        "manual_worker",
        "provider_webhook",
        "test",
    }
)
PROVIDER_MODES = frozenset({"none", "dummy", "real"})
REASON_CODES = frozenset(
    {
        "user_request",
        "policy_decision",
        "risk_rule",
        "provider_confirmation",
        "provider_rejection",
        "timeout",
        "manual_review",
        "scheduled_transition",
        "system_recovery",
        "not_applicable",
    }
)

RELATED_ENTITY_KEYS = (
    "order_id",
    "bid_id",
    "trip_id",
    "payment_id",
    "wallet_id",
    "wallet_transaction_id",
    "withdrawal_id",
    "dispute_id",
    "chat_thread_id",
    "review_id",
    "policy_id",
    "terms_version_id",
    "notification_id",
    "transporter_profile_id",
    "truck_id",
    "driver_id",
    "document_id",
    "agreement_id",
)

STATE_KEY_TYPES = {
    "status": str,
    "enabled": bool,
    "verified": bool,
    "active": bool,
    "is_default": bool,
    "version": int,
    "amount_minor": int,
    "currency": str,
    "method": str,
    "decision": str,
    "delivery_status": str,
}

METADATA_KEY_TYPES = {
    "result_code": str,
    "policy_version": int,
    "attempt_number": int,
    "item_count": int,
    "amount_minor": int,
    "currency": str,
    "channel": str,
    "delivery_method": str,
    "risk_tier": str,
    "is_replay": bool,
    "provider_event_type": str,
    "authorization_ref": str,
    "action_key": str,
    "resource_type": str,
    "resource_id": int,
    "request_fingerprint_ref": str,
}

PROHIBITED_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "mpin",
        "mpin_hash",
        "otp",
        "recovery_code",
        "reset_token",
        "csrf",
        "csrf_token",
        "session_token",
        "refresh_token",
        "access_token",
        "device_token",
        "provider_token",
        "payment_token",
        "authorization",
        "cookie",
        "pan",
        "card_number",
        "cvc",
        "cvv",
        "request_body",
        "response_body",
        "body",
        "message",
        "chat",
        "comment",
        "review",
        "statement",
        "notes",
        "document_content",
        "filename",
        "path",
        "latitude",
        "longitude",
        "gps",
        "email",
        "phone",
        "cnic",
        "ip",
        "ip_address",
        "user_agent",
        "fingerprint",
    }
)

SERVER_OWNED_KEYS = frozenset(
    {
        "event_id",
        "event_version",
        "category",
        "actor_type",
        "actor_id",
        "actor_role",
        "subject_user_id",
        "request_id",
        "correlation_id",
        "session_ref",
        "device_ref",
        "source",
        "provider_mode",
        "environment",
        "occurred_at",
        "retention_class",
        "consent_category",
        "idempotency_scope",
        "idempotency_key",
        "fingerprint",
    }
)

_CODE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_REQUEST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SESSION_REF_RE = re.compile(r"^session_[0-9a-f]{32}$")
_DEVICE_REF_RE = re.compile(r"^device_[0-9a-f]{32}$")


class EventContractError(ValueError):
    pass


@dataclass(frozen=True)
class EventContext:
    request_id: str
    source: str
    actor_type: str
    actor_id: int | None = None
    actor_role: str | None = None
    subject_user_id: int | None = None
    correlation_id: str | None = None
    session_ref: str | None = None
    device_ref: str | None = None
    provider_mode: str = "none"


@dataclass(frozen=True)
class EventData:
    related_entities: Mapping[str, int] = field(default_factory=dict)
    before_state: Mapping[str, object] = field(default_factory=dict)
    after_state: Mapping[str, object] = field(default_factory=dict)
    reason_code: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    consent_category: str | None = None


def _positive_id(value, field_name, optional=True):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EventContractError(f"{field_name} must be a positive integer.")
    return value


def _safe_text(value, field_name, pattern, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise EventContractError(f"{field_name} has an invalid format.")
    return value


def _scan_prohibited_keys(value):
    if not isinstance(value, Mapping):
        return
    for key, nested in value.items():
        normalized = str(key).strip().lower()
        if normalized in PROHIBITED_KEYS:
            raise EventContractError("Sensitive or unrestricted event fields are prohibited.")
        if isinstance(nested, Mapping):
            _scan_prohibited_keys(nested)


def _validate_scalar_object(value, field_name, type_map, max_bytes):
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise EventContractError(f"{field_name} must be an object.")
    _scan_prohibited_keys(value)
    if len(value) > MAX_OBJECT_KEYS:
        raise EventContractError(f"{field_name} contains too many keys.")
    normalized = {}
    for raw_key, item in value.items():
        if not isinstance(raw_key, str) or raw_key not in type_map:
            raise EventContractError(f"{field_name} contains an unknown key.")
        expected = type_map[raw_key]
        if expected is int:
            valid = isinstance(item, int) and not isinstance(item, bool) and item >= 0
        else:
            valid = isinstance(item, expected)
        if not valid:
            raise EventContractError(f"{field_name}.{raw_key} has an invalid type.")
        if isinstance(item, float) and not math.isfinite(item):
            raise EventContractError(f"{field_name}.{raw_key} must be finite.")
        if isinstance(item, str) and (
            len(item) > MAX_STRING_LENGTH or not _CODE_RE.fullmatch(item)
        ):
            raise EventContractError(f"{field_name}.{raw_key} has an invalid value.")
        if raw_key == "authorization_ref" and not re.fullmatch(
            r"authorization_[0-9a-f]{32}", item
        ):
            raise EventContractError("metadata.authorization_ref has an invalid value.")
        if raw_key == "request_fingerprint_ref" and not re.fullmatch(
            r"request_[0-9a-f]{64}", item
        ):
            raise EventContractError(
                "metadata.request_fingerprint_ref has an invalid value."
            )
        normalized[raw_key] = item
    try:
        encoded = json.dumps(
            normalized, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise EventContractError(f"{field_name} is not valid bounded JSON.") from None
    if len(encoded) > max_bytes:
        raise EventContractError(f"{field_name} is too large.")
    return normalized


def _validate_related_entities(value):
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise EventContractError("related_entities must be an object.")
    if len(value) > len(RELATED_ENTITY_KEYS):
        raise EventContractError("related_entities contains too many keys.")
    normalized = {}
    for key, entity_id in value.items():
        if key not in RELATED_ENTITY_KEYS:
            raise EventContractError("related_entities contains an unknown key.")
        normalized[key] = _positive_id(entity_id, f"related_entities.{key}", optional=False)
    return normalized


def validate_event_context(context):
    if not isinstance(context, EventContext):
        raise EventContractError("A server-owned EventContext is required.")
    if context.actor_type not in ACTOR_TYPES:
        raise EventContractError("actor_type is not allowed.")
    actor_id = _positive_id(context.actor_id, "actor_id")
    if context.actor_type in {"user", "admin"} and actor_id is None:
        raise EventContractError("User and admin actors require a server-derived actor_id.")
    actor_role = _safe_text(context.actor_role, "actor_role", _ROLE_RE, optional=True)
    if context.actor_type in {"user", "admin"} and actor_role is None:
        raise EventContractError("User and admin actors require a server-derived actor_role.")
    if context.source not in SOURCES:
        raise EventContractError("source is not allowed.")
    if context.provider_mode not in PROVIDER_MODES:
        raise EventContractError("provider_mode is not allowed.")
    request_id = _safe_text(context.request_id, "request_id", _REQUEST_RE)
    correlation_id = _safe_text(
        context.correlation_id, "correlation_id", _REQUEST_RE, optional=True
    )
    session_ref = _safe_text(
        context.session_ref, "session_ref", _SESSION_REF_RE, optional=True
    )
    device_ref = _safe_text(
        context.device_ref, "device_ref", _DEVICE_REF_RE, optional=True
    )
    return {
        "request_id": request_id,
        "source": context.source,
        "actor_type": context.actor_type,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "subject_user_id": _positive_id(context.subject_user_id, "subject_user_id"),
        "correlation_id": correlation_id,
        "session_ref": session_ref,
        "device_ref": device_ref,
        "provider_mode": context.provider_mode,
    }


def validate_event_data(data, *, definition=None):
    if data is None:
        data = EventData()
    if not isinstance(data, EventData):
        raise EventContractError("EventData is required.")
    if data.consent_category is not None:
        raise EventContractError(
            "Consent category is not applicable to security or business-audit persistence."
        )
    reason_code = data.reason_code
    if reason_code is not None and reason_code not in REASON_CODES:
        raise EventContractError("reason_code is not allowed.")
    normalized = {
        "related_entities": _validate_related_entities(data.related_entities),
        "before_state": _validate_scalar_object(
            data.before_state, "before_state", STATE_KEY_TYPES, MAX_STATE_BYTES
        ),
        "after_state": _validate_scalar_object(
            data.after_state, "after_state", STATE_KEY_TYPES, MAX_STATE_BYTES
        ),
        "reason_code": reason_code,
        "metadata": _validate_scalar_object(
            data.metadata, "metadata", METADATA_KEY_TYPES, MAX_METADATA_BYTES
        ),
        "consent_category": None,
    }
    if definition is not None and definition.name == "security.signup.started":
        if (
            normalized["related_entities"]
            or normalized["before_state"]
            or normalized["after_state"]
            or normalized["reason_code"] is not None
            or normalized["metadata"]
        ):
            raise EventContractError("Signup started events must not carry request data.")
    if definition is not None and definition.name == "security.signup.failed":
        if (
            normalized["related_entities"]
            or normalized["before_state"]
            or normalized["after_state"]
            or normalized["reason_code"] is not None
            or set(normalized["metadata"]) != {"result_code"}
            or normalized["metadata"]["result_code"] not in definition.allowed_result_codes
        ):
            raise EventContractError(
                "Signup failure events require one approved coarse result_code only."
            )
    if definition is not None and definition.actor_policy != "generic":
        if set(normalized["metadata"]) != set(definition.allowed_metadata_keys):
            raise EventContractError("Event metadata does not match its canonical contract.")
        if (
            definition.allowed_result_codes is not None
            and normalized["metadata"].get("result_code")
            not in definition.allowed_result_codes
        ):
            raise EventContractError("Event result_code is not approved.")
        if "resource_id" in normalized["metadata"] and normalized["metadata"]["resource_id"] <= 0:
            raise EventContractError("metadata.resource_id must be a positive integer.")
    return normalized


def validate_catalog_event_contract(event_name, context, data=None):
    """Validate a catalog definition without granting runtime write eligibility."""
    definition = get_event_definition(event_name)
    normalized_context = validate_event_context(context)
    if definition.name in {"security.signup.started", "security.signup.failed"} and (
        normalized_context["actor_type"] != "anonymous"
        or normalized_context["actor_id"] is not None
        or normalized_context["actor_role"] is not None
        or normalized_context["subject_user_id"] is not None
    ):
        raise EventContractError("Anonymous signup events must remain anonymous.")
    authenticated_self = normalized_context["actor_type"] in {"user", "admin"} and normalized_context["actor_id"] == normalized_context["subject_user_id"]
    service_subject = normalized_context["actor_type"] == "system" and normalized_context["actor_id"] is None and normalized_context["actor_role"] is None and normalized_context["subject_user_id"] is not None
    if definition.actor_policy == "authenticated_self" and not authenticated_self:
        raise EventContractError("This event requires an authenticated actor and matching subject.")
    if definition.actor_policy == "service_subject" and not service_subject:
        raise EventContractError("This event requires the service actor and a derived subject.")
    if definition.actor_policy == "authenticated_self_or_service" and not (authenticated_self or service_subject):
        raise EventContractError("This event requires an authenticated self actor or service subject.")
    return definition, normalized_context, validate_event_data(data, definition=definition)


def validate_envelope_inputs(event_name, context, data=None):
    definition = get_writable_event_definition(event_name)
    checked_definition, normalized_context, normalized_data = validate_catalog_event_contract(
        event_name, context, data
    )
    if checked_definition != definition:
        raise RuntimeError("Canonical catalog lookup drift.")
    normalized = {
        "event_name": definition.name,
        "event_version": definition.version,
        "category": definition.category,
        "retention_class": definition.retention_class,
        **normalized_context,
        **normalized_data,
    }
    encoded = json.dumps(
        normalized, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise EventContractError("Canonical event envelope is too large.")
    return definition, normalized


def decode_untrusted_event_json(raw_body):
    if not isinstance(raw_body, (bytes, bytearray)):
        raise EventContractError("Event body must be UTF-8 JSON.")
    if len(raw_body) > MAX_ENVELOPE_BYTES:
        raise EventContractError("Event body is too large.")

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EventContractError("Duplicate JSON keys are not allowed.")
            result[key] = value
        return result

    try:
        decoded = raw_body.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=object_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                EventContractError("Non-finite numbers are not allowed.")
            ),
        )
    except EventContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise EventContractError("Malformed event JSON.") from None
    if not isinstance(value, dict):
        raise EventContractError("Event body must be an object.")
    return value


def validate_untrusted_event_payload(payload):
    if not isinstance(payload, Mapping):
        raise EventContractError("Event payload must be an object.")
    _scan_prohibited_keys(payload)
    if SERVER_OWNED_KEYS.intersection(payload):
        raise EventContractError("Server-owned event fields cannot be supplied by a client.")
    allowed = {
        "event_name",
        "related_entities",
        "before_state",
        "after_state",
        "reason_code",
        "metadata",
    }
    if set(payload) != allowed:
        raise EventContractError("Event payload keys do not match the strict contract.")
    definition = get_writable_event_definition(payload["event_name"])
    data = validate_event_data(
        EventData(
            related_entities=payload["related_entities"],
            before_state=payload["before_state"],
            after_state=payload["after_state"],
            reason_code=payload["reason_code"],
            metadata=payload["metadata"],
        )
    )
    return definition, data
