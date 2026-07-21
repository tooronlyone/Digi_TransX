from flask import Blueprint, request

from auth.helpers import get_settings_dict, json_response, login_required, csrf_error, update_user_settings
from shared.db import open_db


settings_blueprint = Blueprint("settings", __name__, url_prefix="/api/settings")


@settings_blueprint.get("")
@login_required
def settings_get():
    return json_response({"success": True, "data": get_settings_dict(request.current_user)})


@settings_blueprint.put("")
@login_required
def settings_update():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    settings_dict = get_settings_dict(request.current_user)
    settings_dict["preferences"].update(
        {
            "language": data.get("language", settings_dict["preferences"].get("language", "en")),
            "theme": data.get("theme", settings_dict["preferences"].get("theme", "light")),
            "currency": data.get("preferred_currency", settings_dict["preferences"].get("currency", "PKR")),
            "timezone": data.get("preferred_timezone", settings_dict["preferences"].get("timezone", "PKT")),
            "dateFormat": data.get("preferred_date_format", settings_dict["preferences"].get("dateFormat", "DD/MM/YYYY")),
            "autoRefresh": bool(data.get("auto_refresh_dashboard", settings_dict["preferences"].get("autoRefresh", True))),
            "tips": bool(data.get("show_tutorial_tips", settings_dict["preferences"].get("tips", False))),
        }
    )
    update_user_settings(request.current_user["id"], settings_dict)
    return json_response({"success": True, "data": settings_dict})


@settings_blueprint.put("/notifications")
@login_required
def settings_notifications():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    settings_dict = get_settings_dict(request.current_user)
    settings_dict["notifications"].update(
        {
            "email": bool(data.get("email", True)),
            "sms": bool(data.get("sms", True)),
            "whatsapp": bool(data.get("whatsapp", True)),
            "push": bool(data.get("push", True)),
            "jobAlerts": bool(data.get("jobAlerts", True)),
            "paymentUpdates": bool(data.get("paymentUpdates", True)),
            "systemUpdates": bool(data.get("systemUpdates", False)),
            "promotions": bool(data.get("promotions", False)),
        }
    )
    update_user_settings(request.current_user["id"], settings_dict)
    return json_response({"success": True, "data": settings_dict})


@settings_blueprint.get("/security/activity")
@login_required
def security_activity():
    with open_db() as db:
        rows = db.execute(
            """
            SELECT created_at, ip_address, status, login_method, failure_reason
            FROM login_activity
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 20
            """,
            (request.current_user["id"],),
        ).fetchall()
    activity = [
        {
            "created_at": row["created_at"],
            "ip_address": row["ip_address"],
            "status": row["status"],
            "login_method": row["login_method"],
            "failure_reason": row["failure_reason"],
        }
        for row in rows
    ]
    return json_response({"success": True, "activity": activity})

