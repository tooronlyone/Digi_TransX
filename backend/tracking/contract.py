"""Strict, temporary Phase 1A contract for the legacy analytics endpoint.

This module intentionally does not implement the Phase 1B canonical event
catalog. It contains the single minimal legacy event that remains necessary
while broad browser tracking is contained.
"""

import json
import re
from urllib.parse import urlsplit


MAX_TRACKING_REQUEST_BYTES = 2048
MAX_TRACKING_STRING_LENGTH = 512
MAX_TRACKING_OBJECT_KEYS = 8
MAX_TRACKING_DEPTH = 2
MAX_PAGE_PATH_LENGTH = 255

PAGE_VISIT_EVENT = "page_visit"
PAGE_VISIT_ACTION = "page_view"

TRACKING_EVENT_CONTRACTS = {
    PAGE_VISIT_EVENT: {
        "action_name": PAGE_VISIT_ACTION,
        "top_level_keys": frozenset(
            {"action_type", "action_name", "page_url", "metadata"}
        ),
        "metadata_keys": frozenset({"navigation_source"}),
    },
}

_SAFE_PATH_RE = re.compile(r"^/[A-Za-z0-9/_.-]*$")
_PROHIBITED_KEYS = frozenset(
    {
        "authorization",
        "button_text",
        "chat",
        "comment",
        "cookie",
        "csrf",
        "csrf_token",
        "cvc",
        "cvv",
        "dispute",
        "element_text",
        "email",
        "fragment",
        "headers",
        "input_data",
        "ip",
        "ip_address",
        "link_text",
        "message",
        "mpin",
        "otp",
        "output_result",
        "pan",
        "password",
        "payment_token",
        "phone",
        "pin",
        "provider_token",
        "query",
        "recovery_code",
        "request_body",
        "response_body",
        "review",
        "role",
        "search",
        "search_text",
        "session",
        "session_id",
        "token",
        "user_agent",
        "user_email",
        "user_id",
        "user_role",
    }
)


class TrackingContractError(ValueError):
    """Safe validation failure that never includes submitted values."""


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TrackingContractError("Tracking payload contains duplicate fields.")
        result[key] = value
    return result


def _reject_nonfinite_number(_value):
    raise TrackingContractError("Tracking payload contains an invalid number.")


def decode_tracking_json(raw_body):
    try:
        return json.loads(
            raw_body.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonfinite_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrackingContractError("Malformed JSON payload.") from exc


def _contains_prohibited_key(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                return True
            normalized = key.strip().lower().replace("-", "_")
            if normalized in _PROHIBITED_KEYS:
                return True
            if _contains_prohibited_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_prohibited_key(item) for item in value)
    return False


def _validate_shape(value, depth=0):
    if depth > MAX_TRACKING_DEPTH:
        raise TrackingContractError("Tracking payload structure is too deep.")
    if isinstance(value, dict):
        if len(value) > MAX_TRACKING_OBJECT_KEYS:
            raise TrackingContractError("Tracking payload has too many fields.")
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TrackingContractError("Tracking field names must be strings.")
            _validate_shape(nested, depth + 1)
        return
    if isinstance(value, list):
        raise TrackingContractError("Tracking collections are not supported.")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise TrackingContractError("Tracking values must be JSON primitives.")
    if isinstance(value, str) and len(value) > MAX_TRACKING_STRING_LENGTH:
        raise TrackingContractError("Tracking string is too long.")


def sanitize_page_path(raw_page_url):
    if not isinstance(raw_page_url, str) or not raw_page_url:
        raise TrackingContractError("A page path is required.")
    if len(raw_page_url) > MAX_TRACKING_STRING_LENGTH:
        raise TrackingContractError("Page path is too long.")

    parsed = urlsplit(raw_page_url)
    if parsed.scheme or parsed.netloc:
        raise TrackingContractError("Absolute page URLs are not accepted.")
    path = parsed.path or "/"
    if len(path) > MAX_PAGE_PATH_LENGTH:
        raise TrackingContractError("Page path is too long.")
    if not _SAFE_PATH_RE.fullmatch(path):
        raise TrackingContractError("Page path contains unsupported characters.")
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise TrackingContractError("Page path is invalid.")
    return path


def validate_tracking_payload(data):
    if not isinstance(data, dict):
        raise TrackingContractError("Tracking payload must be a JSON object.")
    if _contains_prohibited_key(data):
        raise TrackingContractError("Tracking payload contains prohibited fields.")
    _validate_shape(data)

    action_type = data.get("action_type")
    if not isinstance(action_type, str) or action_type not in TRACKING_EVENT_CONTRACTS:
        raise TrackingContractError("Unknown tracking event.")
    contract = TRACKING_EVENT_CONTRACTS[action_type]

    if set(data) != contract["top_level_keys"]:
        raise TrackingContractError("Tracking payload fields do not match the event contract.")
    if data.get("action_name") != contract["action_name"]:
        raise TrackingContractError("Tracking action name does not match the event contract.")

    metadata = data.get("metadata")
    if not isinstance(metadata, dict) or set(metadata) != contract["metadata_keys"]:
        raise TrackingContractError("Tracking metadata does not match the event contract.")
    if metadata.get("navigation_source") != "router":
        raise TrackingContractError("Tracking metadata value is not allowed.")

    page_path = sanitize_page_path(data.get("page_url"))
    return {
        "action_type": action_type,
        "action_name": contract["action_name"],
        "page_url": page_path,
        "payload_json": {
            "page_url": page_path,
            "navigation_source": "router",
        },
    }
