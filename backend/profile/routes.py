from flask import Blueprint, request
from werkzeug.security import generate_password_hash

from auth.helpers import (
    OTP_EXPIRY_MINUTES,
    OTP_REGEX,
    create_otp_record,
    get_user_by_id,
    json_response,
    latest_otp_record,
    login_required,
    normalize_phone,
    csrf_error,
    send_email,
    serialize_user,
    split_name,
    timestamp_bundle,
    verify_otp_for_user,
)
from shared.db import open_db


profile_blueprint = Blueprint("profile", __name__, url_prefix="/api/profile")


@profile_blueprint.get("")
@login_required
def profile_get():
    return json_response({"success": True, "user": serialize_user(request.current_user)})


@profile_blueprint.put("")
@login_required
def profile_update():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    full_name = (data.get("first_name") or request.current_user.get("full_name") or "").strip()
    first_name, last_name = split_name(full_name)
    phone = normalize_phone(data.get("phone") or request.current_user.get("phone"))
    city = (data.get("city") or request.current_user.get("city") or "").strip()
    about = (data.get("about") or request.current_user.get("about") or "").strip()
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute(
            """
            UPDATE users
            SET full_name = ?, first_name = ?, last_name = ?, phone = ?, city = ?, about = ?, updated_at = ?
            WHERE id = ?
            """,
            (full_name, first_name, last_name, phone, city, about, stamp["display"], request.current_user["id"]),
        )
        db.commit()
    return json_response({"success": True, "user": serialize_user(get_user_by_id(request.current_user["id"]))})


@profile_blueprint.post("/password/request-otp")
@login_required
def request_password_change_otp():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    if not current_password:
        return json_response({"success": False, "message": "Current password is required."}, 400)
    from werkzeug.security import check_password_hash
    if not check_password_hash(request.current_user.get("password_hash", ""), current_password):
        return json_response({"success": False, "message": "Current password is incorrect."}, 400)
    latest = latest_otp_record(request.current_user["id"], "password_change")
    if latest and latest.get("cooldown_until_iso"):
        from auth.helpers import is_future
        if is_future(latest["cooldown_until_iso"]):
            return json_response({"success": False, "message": "Too many wrong attempts. Please wait 15 minutes before requesting a new code."}, 429)
    otp_code = "".join(__import__("secrets").choice("0123456789") for _ in range(6))
    try:
        send_email(
            "Digi_TransX Password Change OTP",
            request.current_user["email"],
            [
                f"Dear {request.current_user.get('first_name') or request.current_user.get('full_name') or 'User'},",
                "",
                f"Your Digi_TransX password change code is: {otp_code}",
                f"This code will expire in {OTP_EXPIRY_MINUTES} minutes.",
            ],
        )
    except Exception as exc:
        return json_response({"success": False, "message": f"Unable to send OTP email: {exc}"}, 500)
    create_otp_record(request.current_user["id"], "password_change", otp_code, request.current_user["email"])
    return json_response({"success": True, "message": "OTP sent to your registered email."})


@profile_blueprint.put("/password")
@login_required
def change_password():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    new_password = data.get("new_password") or ""
    otp_code = (data.get("otp_code") or "").strip()
    if len(new_password) < 8:
        return json_response({"success": False, "message": "Password must be at least 8 characters."}, 400)
    if not OTP_REGEX.fullmatch(otp_code):
        return json_response({"success": False, "message": "Enter a valid 6 digit OTP."}, 400)
    _, error_message = verify_otp_for_user(request.current_user["id"], "password_change", otp_code)
    if error_message:
        return json_response({"success": False, "message": error_message}, 400)
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (generate_password_hash(new_password), stamp["display"], request.current_user["id"]))
        db.commit()
    return json_response({"success": True, "message": "Password changed successfully."})

