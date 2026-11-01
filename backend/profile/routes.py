from flask import Blueprint, current_app, request
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
    clear_authentication_cookies,
)
from auth.credential_changes import execute_password_change, PasswordProviderUpdateFailed
from shared.db import open_db
from shared.roles import BUSINESS_CLIENT_ROLES


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
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_response({"success": False, "message": "A JSON object is required."}, 400)
    fields = ("first_name", "last_name", "full_name", "phone", "city", "about",
              "address", "shop_name", "company_name", "contact_phone", "billing_address")
    if any(data.get(field) is not None and not isinstance(data[field], str) for field in fields):
        return json_response({"success": False, "message": "Profile fields must be text."}, 400)
    user = request.current_user

    def text_value(field):
        value = data[field] if field in data else user.get(field)
        return (value or "").strip()

    full_name = user.get("full_name") or ""
    if "full_name" in data:
        full_name = text_value("full_name")
    elif "last_name" in data:
        first_name = text_value("first_name") if "first_name" in data else split_name(full_name)[0]
        full_name = " ".join(part for part in (first_name, text_value("last_name")) if part)
    elif "first_name" in data:
        # Legacy shopkeeper/transporter clients send the entire name in this field.
        full_name = text_value("first_name")
    if not full_name:
        return json_response({"success": False, "message": "Full name is required."}, 400)
    phone = normalize_phone(text_value("phone"))
    city = text_value("city")
    about = text_value("about")
    address = text_value("address")
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute(
            """
            UPDATE users
            SET full_name = %s, phone = %s, city = %s, about = %s, address = %s, updated_at = %s
            WHERE id = %s
            """,
            (full_name, phone, city, about, address, stamp["display"], user["id"]),
        )
        if user.get("role") in BUSINESS_CLIENT_ROLES:
            db.execute(
                """INSERT INTO service_seeker_profiles
                    (user_id, company_name, contact_phone, billing_address, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    contact_phone = EXCLUDED.contact_phone,
                    billing_address = EXCLUDED.billing_address,
                    updated_at = EXCLUDED.updated_at""",
                (user["id"], text_value("company_name"), text_value("contact_phone"),
                 text_value("billing_address"), stamp["display"]),
            )
        shop_name = (data.get("shop_name") or "").strip()
        if shop_name and user.get("role") == "shopkeeper":
            db.execute(
                """
                INSERT INTO shopkeeper_profiles (user_id, shop_name, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET shop_name = EXCLUDED.shop_name, updated_at = EXCLUDED.updated_at
                """,
                (request.current_user["id"], shop_name, stamp["display"]),
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
    if not isinstance(data,dict) or not isinstance(data.get("current_password",""),str):
        return json_response({"success": False,"message": "Current password must be text."},400)
    current_password = data.get("current_password") or ""
    if not current_password:
        return json_response({"success": False, "message": "Current password is required."}, 400)
    from shared.supabase_client import supabase_verify_password
    if not supabase_verify_password(request.current_user.get("email", ""), current_password):
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
    except Exception:
        current_app.logger.error("Password-change OTP email delivery failed.")
        return json_response(
            {"success": False, "message": "Unable to send the password-change code."},
            503,
        )
    create_otp_record(request.current_user["id"], "password_change", otp_code, request.current_user["email"])
    return json_response({"success": True, "message": "OTP sent to your registered email."})


@profile_blueprint.put("/password")
@login_required
def change_password():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    if not isinstance(data,dict) or any(not isinstance(data.get(key,""),str) for key in ("new_password","otp_code")):
        return json_response({"success": False,"message": "Password and OTP must be text."},400)
    new_password = data.get("new_password") or ""
    otp_code = (data.get("otp_code") or "").strip()
    if not 8 <= len(new_password) <= 4096:
        return json_response({"success": False, "message": "Password must be at least 8 characters."}, 400)
    if not OTP_REGEX.fullmatch(otp_code):
        return json_response({"success": False, "message": "Enter a valid 6 digit OTP."}, 400)
    _, error_message = verify_otp_for_user(request.current_user["id"], "password_change", otp_code)
    if error_message:
        return json_response({"success": False, "message": error_message}, 400)
    auth_id = request.current_user.get("auth_id")
    if not auth_id:
        return json_response({"success": False, "message": "Account is not linked to the auth system. Please contact support."}, 500)
    from shared.supabase_client import supabase_update_password
    try:
        execute_password_change(request.current_user["id"],auth_id,new_password,"password_changed",
                                supabase_update_password)
    except PasswordProviderUpdateFailed as exc:
        return clear_authentication_cookies(json_response({
            "success": False,
            "code": "password_change_reconciliation_required" if exc.reconciliation_required else "password_update_rejected",
            "message": ("Password change outcome is pending verification. Contact support before retrying."
                        if exc.reconciliation_required else "Password update was rejected. Request a new code and choose a different password."),
        },503))
    except Exception:
        current_app.logger.error("Auth provider password change failed.")
        return clear_authentication_cookies(json_response(
            {
                "success": False,
                "code": "password_change_reconciliation_required",
                "message": "Password change outcome is pending verification. Contact support before retrying.",
            },
            503,
        ))
    return clear_authentication_cookies(json_response({
        "success": True, "message": "Password changed successfully. Sign in again on your devices.",
        "reauthentication_required": True,
    }))

