import json

from flask import Blueprint, request

from auth.helpers import csrf_error, json_response, login_required, timestamp_bundle
from shared.db import open_db
from tracking.contract import (
    MAX_TRACKING_REQUEST_BYTES,
    TrackingContractError,
    decode_tracking_json,
    validate_tracking_payload,
)


tracking_blueprint = Blueprint("tracking", __name__, url_prefix="/api")


@tracking_blueprint.post("/track")
@login_required(refresh_activity=False)
def api_track():
    if not request.is_json:
        return json_response(
            {"success": False, "message": "Content-Type must be application/json."},
            415,
        )
    if (
        request.content_length is not None
        and request.content_length > MAX_TRACKING_REQUEST_BYTES
    ):
        return json_response({"success": False, "message": "Tracking payload is too large."}, 413)

    err = csrf_error()
    if err:
        return err

    raw_body = request.stream.read(MAX_TRACKING_REQUEST_BYTES + 1)
    if len(raw_body) > MAX_TRACKING_REQUEST_BYTES:
        return json_response({"success": False, "message": "Tracking payload is too large."}, 413)
    try:
        submitted = decode_tracking_json(raw_body)
        event = validate_tracking_payload(submitted)
    except TrackingContractError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    user = request.current_user
    with open_db() as db:
        db.execute(
            """
            INSERT INTO user_action_logs (
                user_id, user_email, user_role, action_type, action_name, page_url, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(user["id"]),
                "",
                str(user.get("role") or ""),
                event["action_type"],
                event["action_name"],
                event["page_url"],
                json.dumps(event["payload_json"], separators=(",", ":"), sort_keys=True),
                timestamp_bundle()["display"],
            ),
        )
        db.commit()
    return json_response({"success": True})
