import json

from flask import Blueprint, request

from auth.helpers import json_response, timestamp_bundle
from shared.db import open_db


tracking_blueprint = Blueprint("tracking", __name__, url_prefix="/api")


@tracking_blueprint.post("/track")
def api_track():
    data = request.get_json(silent=True) or {}
    with open_db() as db:
        db.execute(
            """
            INSERT INTO user_action_logs (
                user_id, user_email, user_role, action_type, action_name, page_url, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(data.get("user_id") or ""),
                str(data.get("user_email") or ""),
                str(data.get("user_role") or ""),
                str(data.get("action_type") or ""),
                str(data.get("action_name") or ""),
                str(data.get("page_url") or ""),
                json.dumps(data),
                timestamp_bundle()["display"],
            ),
        )
        db.commit()
    return json_response({"success": True})
