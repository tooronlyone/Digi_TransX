from flask import Blueprint, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from shared.db import open_db
from .helpers import (
    DEVICE_COOKIE_NAME,
    LOGIN_COOLDOWN_MINUTES,
    MPIN_REGEX,
    OTP_EXPIRY_MINUTES,
    OTP_REGEX,
    build_auth_success_response,
    create_otp_record,
    create_reset_token,
    ensure_csrf_token,
    find_valid_reset_token,
    generate_numeric_code,
    get_user_by_id,
    get_user_by_login,
    json_response,
    latest_otp_record,
    login_required,
    mask_email,
    normalize_cnic,
    normalize_email,
    normalize_phone,
    parse_login_id,
    record_login_activity,
    require_csrf,
    role_redirect,
    send_email,
    serialize_user,
    split_name,
    timestamp_bundle,
    update_user_settings,
    validate_signup_payload,
    verify_otp_for_user,
)


auth_blueprint = Blueprint("auth", __name__, url_prefix="/auth")


@auth_blueprint.get("/csrf-token")
def csrf_token():
    return json_response({"success": True, "csrf_token": ensure_csrf_token()})


@auth_blueprint.post("/signup")
def signup():
    data = request.get_json(silent=True) or {}
    errors = validate_signup_payload(data)
    if errors:
        field = next(iter(errors))
        return json_response({"success": False, "field": field, "message": errors[field]}, 400)
    full_name = (data.get("name") or "").strip()
    first_name, last_name = split_name(full_name)
    email = normalize_email(data.get("email"))
    phone = normalize_phone(data.get("phone"))
    cnic = normalize_cnic(data.get("cnic"))
    role = (data.get("role") or "").strip()
    stamp = timestamp_bundle()
    with open_db() as db:
        email_exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if email_exists:
            return json_response({"success": False, "field": "email", "message": "Email is already registered."}, 409)
        cnic_exists = db.execute("SELECT id FROM users WHERE cnic = ?", (cnic,)).fetchone()
        if cnic_exists:
            return json_response({"success": False, "field": "cnic", "message": "CNIC is already registered."}, 409)
        db.execute(
            """
            INSERT INTO users (
                full_name, first_name, last_name, email, phone, cnic, password_hash, role,
                company_name, business_type, city, fleet_size, transport_need,
                station_name, pumps_count, license_no, shop_name, address, about,
                mpin_hash, mpin_enabled, settings_json, created_at, updated_at, last_login_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, '{}', ?, ?, ?)
            """,
            (
                full_name,
                first_name,
                last_name,
                email,
                phone,
                cnic,
                generate_password_hash(data.get("password") or ""),
                role,
                (data.get("company_name") or "").strip() or None,
                (data.get("business_type") or "").strip() or None,
                (data.get("city") or "").strip() or None,
                (data.get("fleet_size") or "").strip() or None,
                (data.get("transport_need") or "").strip() or None,
                (data.get("station_name") or "").strip() or None,
                (data.get("pumps_count") or "").strip() or None,
                (data.get("license_no") or "").strip() or None,
                (data.get("shop_name") or "").strip() or None,
                (data.get("address") or "").strip() or None,
                (data.get("about") or "").strip() or None,
                stamp["display"],
                stamp["display"],
                stamp["display"],
            ),
        )
        user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()
    user = get_user_by_id(user_id)
    record_login_activity(user_id, email, "signup", "success", "")
    return build_auth_success_response(user)


@auth_blueprint.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    login_id = data.get("loginId") or ""
    password = data.get("password") or ""
    if not login_id.strip():
        return json_response({"success": False, "field": "loginId", "message": "Email or CNIC is required."}, 400)
    if not password:
        return json_response({"success": False, "field": "password", "message": "Password is required."}, 400)
    user, login_method, lookup_value = get_user_by_login(login_id)
    if not user:
        record_login_activity(None, lookup_value, login_method, "failed", "Account not found.")
        return json_response({"success": False, "field": "loginId", "message": "Account not found."}, 401)
    if not check_password_hash(user["password_hash"], password):
        record_login_activity(user["id"], lookup_value, login_method, "failed", "Invalid password.")
        return json_response({"success": False, "field": "password", "message": "Incorrect password."}, 401)
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute("UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?", (stamp["display"], stamp["display"], user["id"]))
        db.commit()
    user = get_user_by_id(user["id"])
    record_login_activity(user["id"], lookup_value, login_method, "success", "")
    return build_auth_success_response(user)


@auth_blueprint.get("/me")
def auth_me():
    user_id = session.get("user_id")
    if not user_id:
        return json_response({"success": False, "message": "Not authenticated."}, 401)
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return json_response({"success": False, "message": "Session expired."}, 401)
    session["last_active_at"] = timestamp_bundle()["display"]
    ensure_csrf_token()
    return json_response(
        {
            "success": True,
            "user": serialize_user(user),
            "csrf_token": session["csrf_token"],
            "redirect": role_redirect(user.get("role")),
            "session": {"last_active_at": session.get("last_active_at", "")},
        }
    )


@auth_blueprint.post("/logout")
def logout():
    if session.get("user_id") and not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)
    session.clear()
    return json_response({"success": True, "message": "Logged out successfully."})


@auth_blueprint.post("/forgot-password")
def forgot_password():
    data = request.get_json(silent=True) or {}
    login_id = data.get("loginId") or ""
    if not login_id.strip():
        return json_response({"success": False, "field": "loginId", "message": "Email or CNIC is required."}, 400)
    user, _, _ = get_user_by_login(login_id)
    if not user:
        return json_response({"success": True, "message": "If an account exists, a 6 digit code has been sent to the registered email."})
    latest = latest_otp_record(user["id"], "password_reset")
    if latest and latest.get("cooldown_until_iso"):
        from .helpers import is_future
        if is_future(latest["cooldown_until_iso"]):
            return json_response({"success": False, "message": "Too many wrong attempts. Please wait 15 minutes before requesting a new code."}, 429)
    otp_code = generate_numeric_code(6)
    try:
        send_email(
            "Digi_TransX Password Reset OTP",
            user["email"],
            [
                f"Assalam o Alaikum {user.get('first_name') or user.get('full_name') or 'User'},",
                "",
                f"Your Digi_TransX password reset code is: {otp_code}",
                f"This code will expire in {OTP_EXPIRY_MINUTES} minutes.",
                "",
                "If you did not request this code, please ignore this email.",
            ],
        )
    except Exception as exc:
        return json_response({"success": False, "message": f"Unable to send OTP email: {exc}"}, 500)
    create_otp_record(user["id"], "password_reset", otp_code, user["email"])
    return json_response({"success": True, "masked_email": mask_email(user["email"]), "message": "OTP sent to your registered email."})


@auth_blueprint.post("/password-reset/verify-otp")
def verify_password_reset_otp():
    data = request.get_json(silent=True) or {}
    login_id = data.get("loginId") or ""
    otp_code = (data.get("otp") or "").strip()
    if not login_id.strip():
        return json_response({"success": False, "field": "loginId", "message": "Email or CNIC is required."}, 400)
    if not OTP_REGEX.fullmatch(otp_code):
        return json_response({"success": False, "field": "otp", "message": "Enter a valid 6 digit OTP."}, 400)
    user, _, _ = get_user_by_login(login_id)
    if not user:
        return json_response({"success": False, "message": "Account not found."}, 404)
    _, error_message = verify_otp_for_user(user["id"], "password_reset", otp_code)
    if error_message:
        return json_response({"success": False, "message": error_message}, 400)
    return json_response({"success": True, "reset_token": create_reset_token(user["id"], "password_reset")})


@auth_blueprint.post("/reset-password")
def reset_password():
    data = request.get_json(silent=True) or {}
    raw_token = data.get("reset_token") or ""
    new_password = data.get("new_password") or ""
    if not raw_token:
        return json_response({"success": False, "message": "Reset token is required."}, 400)
    if len(new_password) < 8:
        return json_response({"success": False, "field": "password", "message": "Password must be at least 8 characters."}, 400)
    token_record, error_message = find_valid_reset_token(raw_token, "password_reset")
    if error_message:
        return json_response({"success": False, "message": error_message}, 400)
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (generate_password_hash(new_password), stamp["display"], token_record["user_id"]))
        db.execute("UPDATE reset_tokens SET used = 1 WHERE id = ?", (token_record["id"],))
        db.execute("UPDATE password_reset_otps SET verified = 1 WHERE user_id = ? AND purpose = 'password_reset'", (token_record["user_id"],))
        db.commit()
    return json_response({"success": True, "message": "Password reset successful."})


@auth_blueprint.get("/fast-login/options")
def fast_login_options():
    device_token = request.cookies.get(DEVICE_COOKIE_NAME)
    if not device_token:
        return json_response({"success": True, "available": False})
    with open_db() as db:
        row = db.execute(
            "SELECT u.* FROM trusted_devices td JOIN users u ON u.id = td.user_id WHERE td.device_token = ?",
            (device_token,),
        ).fetchone()
    if not row:
        return json_response({"success": True, "available": False})
    user = dict(row)
    return json_response({"success": True, "available": bool(user.get("mpin_enabled") and user.get("mpin_hash")), "masked_email": mask_email(user.get("email", "")), "user_role": user.get("role", "")})


@auth_blueprint.post("/fast-login/mpin")
def fast_login_mpin():
    data = request.get_json(silent=True) or {}
    mpin = (data.get("mpin") or "").strip()
    if not MPIN_REGEX.fullmatch(mpin):
        return json_response({"success": False, "message": "MPIN must be exactly 4 digits."}, 400)
    device_token = request.cookies.get(DEVICE_COOKIE_NAME)
    if not device_token:
        return json_response({"success": False, "message": "No trusted device found. Please login with password first."}, 404)
    with open_db() as db:
        row = db.execute(
            "SELECT u.* FROM trusted_devices td JOIN users u ON u.id = td.user_id WHERE td.device_token = ?",
            (device_token,),
        ).fetchone()
    if not row:
        return json_response({"success": False, "message": "Trusted device not found. Please login with password first."}, 404)
    user = dict(row)
    if not user.get("mpin_enabled") or not user.get("mpin_hash"):
        return json_response({"success": False, "message": "Fast login is not enabled for this account."}, 400)
    if not check_password_hash(user["mpin_hash"], mpin):
        record_login_activity(user["id"], user.get("email", ""), "mpin", "failed", "Invalid MPIN.")
        return json_response({"success": False, "message": "Invalid MPIN."}, 401)
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute("UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?", (stamp["display"], stamp["display"], user["id"]))
        db.commit()
    user = get_user_by_id(user["id"])
    record_login_activity(user["id"], user.get("email", ""), "mpin", "success", "")
    return build_auth_success_response(user)


@auth_blueprint.post("/fast-login/setup")
@login_required
def setup_fast_login():
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)
    data = request.get_json(silent=True) or {}
    mpin = (data.get("mpin") or "").strip()
    if not MPIN_REGEX.fullmatch(mpin):
        return json_response({"success": False, "field": "mpin", "message": "MPIN must be exactly 4 digits."}, 400)
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute("UPDATE users SET mpin_hash = ?, mpin_enabled = 1, updated_at = ? WHERE id = ?", (generate_password_hash(mpin), stamp["display"], request.current_user["id"]))
        db.commit()
    user = get_user_by_id(request.current_user["id"])
    return json_response({"success": True, "message": "MPIN enabled successfully.", "user": serialize_user(user), "csrf_token": session.get("csrf_token", "")})


@auth_blueprint.post("/fast-login/disable")
@login_required
def disable_fast_login():
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute("UPDATE users SET mpin_hash = NULL, mpin_enabled = 0, updated_at = ? WHERE id = ?", (stamp["display"], request.current_user["id"]))
        db.commit()
    user = get_user_by_id(request.current_user["id"])
    return json_response({"success": True, "message": "MPIN disabled successfully.", "user": serialize_user(user), "csrf_token": session.get("csrf_token", "")})

