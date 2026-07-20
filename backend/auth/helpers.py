import json
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps

from flask import current_app, jsonify, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from shared.db import open_db


EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CNIC_REGEX = re.compile(r"^\d{13}$")
PHONE_DIGIT_REGEX = re.compile(r"^\d{10,15}$")
OTP_REGEX = re.compile(r"^\d{6}$")
MPIN_REGEX = re.compile(r"^\d{4}$")
LOGIN_COOLDOWN_MINUTES = 15
OTP_EXPIRY_MINUTES = 10
OTP_ATTEMPT_LIMIT = 5
RESET_TOKEN_EXPIRY_MINUTES = 10
DEVICE_COOKIE_NAME = "dtx_device_token"


def now_local():
    return datetime.now()


def timestamp_bundle(moment=None):
    current = moment or now_local()
    return {
        "display": current.strftime("%d %b %Y %I:%M:%S %p"),
        "iso": current.isoformat(timespec="seconds"),
    }


def add_minutes(iso_value, minutes):
    return (datetime.fromisoformat(iso_value) + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def is_future(iso_value):
    if not iso_value:
        return False
    return datetime.fromisoformat(iso_value) > now_local()


def normalize_email(value):
    return (value or "").strip().lower()


def normalize_phone(value):
    return re.sub(r"\D+", "", value or "")


def normalize_cnic(value):
    return re.sub(r"\D+", "", value or "")


def parse_login_id(login_id):
    raw = (login_id or "").strip()
    digits = normalize_cnic(raw)
    if CNIC_REGEX.fullmatch(digits):
        return "cnic", digits
    return "email", normalize_email(raw)


def mask_email(email):
    email = normalize_email(email)
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        local_masked = local[0] + "*"
    else:
        local_masked = local[:2] + "*" * max(2, len(local) - 2)
    return f"{local_masked}@{domain}"


def role_redirect(role):
    mapping = {
        "logistics_provider": "/transporter/dashboard",
        "transporter": "/transporter/dashboard",
        "service_seeker": "/client/dashboard",
        "client": "/client/dashboard",
        "shopkeeper": "/shopkeeper/dashboard",
        "everyday_user": "/client/dashboard",
        "fuel_station_manager": "/fuelstation/dashboard",
        "platform_admin": "/admin/dashboard",
    }
    return mapping.get((role or "").strip().lower(), "/transporter/dashboard")


def json_response(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    return response


def get_request_meta():
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded.split(",")[0].strip() if forwarded else (request.remote_addr or "")
    return {
        "ip_address": ip_address,
        "user_agent": (request.headers.get("User-Agent") or "")[:255],
    }


def send_email(subject, recipient, body_lines):
    smtp_host = os.environ.get("DIGITRANSX_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("DIGITRANSX_SMTP_PORT", "587"))
    smtp_user = os.environ.get("DIGITRANSX_SMTP_USER", "")
    smtp_password = os.environ.get("DIGITRANSX_SMTP_PASSWORD", "")
    sender = os.environ.get("DIGITRANSX_SMTP_FROM", smtp_user)
    if not smtp_user or not smtp_password or not sender:
        raise RuntimeError("SMTP environment variables are missing.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content("\n".join(body_lines))
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def split_name(full_name):
    parts = [part for part in (full_name or "").strip().split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def ensure_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        session["csrf_token"] = token
    return token


def require_csrf():
    expected = session.get("csrf_token", "")
    received = request.headers.get("X-CSRF-Token", "")
    return bool(expected and received and secrets.compare_digest(expected, received))


def csrf_error():
    """Return a 403 response if the CSRF token is missing/invalid, else None.

    Shared guard used by every state-changing route so the check exists in one
    place. Usage:  err = csrf_error();  if err: return err
    """
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)
    return None


def get_session_snapshot():
    return {"last_active_at": session.get("last_active_at", "")}


LEGACY_TO_APP_ROLE = {
    "platform_admin": "admin",
    "client": "customer",
    "service_seeker": "customer",
    "everyday_user": "customer",
    "transporter": "transporter",
    "logistics_provider": "transporter",
    "fuel_station_manager": "fuel_station_manager",
    "shopkeeper": "shopkeeper",
    "dispatcher": "dispatcher",
}


def map_legacy_role(legacy_role):
    return LEGACY_TO_APP_ROLE.get((legacy_role or "").strip().lower(), "customer")


def _with_legacy_role(user):
    """App logic keeps using the legacy role strings (users.legacy_role)."""
    if user and user.get("legacy_role"):
        user["role"] = user["legacy_role"]
    return user


def get_user_by_id(user_id):
    if not user_id:
        return None
    with open_db() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _with_legacy_role(dict(row)) if row else None


def get_user_by_login(login_id):
    login_kind, value = parse_login_id(login_id)
    column = "cnic" if login_kind == "cnic" else "email"
    with open_db() as db:
        row = db.execute(f"SELECT * FROM users WHERE {column} = ?", (value,)).fetchone()
        return (_with_legacy_role(dict(row)) if row else None), login_kind, value


def serialize_user(user):
    return {
        "id": user["id"],
        "full_name": user.get("full_name", ""),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "email": user.get("email", ""),
        "phone": user.get("phone", ""),
        "cnic": user.get("cnic", ""),
        "role": user.get("role", ""),
        "registered_role": user.get("role", ""),
        "company_name": user.get("company_name", ""),
        "city": user.get("city", ""),
        "shop_name": user.get("shop_name", ""),
        "station_name": user.get("station_name", ""),
        "address": user.get("address", ""),
        "about": user.get("about", ""),
        "organization_default_route": role_redirect(user.get("role", "")),
        "mpin_enabled": bool(user.get("mpin_enabled")),
        "last_login_at": user.get("last_login_at", ""),
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return json_response({"success": False, "message": "Authentication required."}, 401)
        user = get_user_by_id(user_id)
        if not user:
            session.clear()
            return json_response({"success": False, "message": "Session expired."}, 401)
        session["last_active_at"] = timestamp_bundle()["display"]
        request.current_user = user
        return view(*args, **kwargs)

    return wrapped


def require_admin_role(user):
    if not user or (user.get("role") or "").strip().lower() != "platform_admin":
        return json_response({"success": False, "message": "Admin access required."}, 403)
    return None


def generate_numeric_code(length):
    return "".join(secrets.choice("0123456789") for _ in range(length))


def record_login_activity(user_id, login_identifier, login_method, status, failure_reason=""):
    stamp = timestamp_bundle()
    meta = get_request_meta()
    with open_db() as db:
        db.execute(
            """
            INSERT INTO login_activity (
                user_id, login_identifier, login_method, status, failure_reason,
                ip_address, user_agent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                login_identifier,
                login_method,
                status,
                failure_reason,
                meta["ip_address"],
                meta["user_agent"],
                stamp["iso"],
            ),
        )
        db.commit()


def upsert_trusted_device(user_id):
    stamp = timestamp_bundle()
    device_token = request.cookies.get(DEVICE_COOKIE_NAME) or secrets.token_urlsafe(32)
    with open_db() as db:
        existing = db.execute("SELECT id FROM trusted_devices WHERE device_token = ?", (device_token,)).fetchone()
        if existing:
            db.execute(
                "UPDATE trusted_devices SET user_id = ?, last_seen_at = ? WHERE device_token = ?",
                (user_id, stamp["display"], device_token),
            )
        else:
            db.execute(
                "INSERT INTO trusted_devices (device_token, user_id, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
                (device_token, user_id, stamp["display"], stamp["display"]),
            )
        db.commit()
    return device_token


def build_auth_success_response(user):
    session["user_id"] = user["id"]
    session["csrf_token"] = secrets.token_urlsafe(24)
    session["last_active_at"] = timestamp_bundle()["display"]
    device_token = upsert_trusted_device(user["id"])
    payload = {
        "success": True,
        "user": serialize_user(user),
        "csrf_token": session["csrf_token"],
        "redirect": role_redirect(user.get("role")),
        "session": get_session_snapshot(),
    }
    response = json_response(payload)
    response.set_cookie(
        DEVICE_COOKIE_NAME,
        device_token,
        httponly=True,
        samesite="Lax",
        secure=current_app.config["SESSION_COOKIE_SECURE"],
        max_age=60 * 60 * 24 * 180,
    )
    return response


def latest_otp_record(user_id, purpose):
    with open_db() as db:
        row = db.execute(
            """
            SELECT * FROM password_reset_otps
            WHERE user_id = ? AND purpose = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, purpose),
        ).fetchone()
        return dict(row) if row else None


def create_otp_record(user_id, purpose, otp_code, recipient_email):
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute(
            """
            INSERT INTO password_reset_otps (
                user_id, purpose, otp_hash, expires_at_iso, created_at, created_at_iso,
                attempts, max_attempts, verified, cooldown_until_iso, delivery_target
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0, NULL, ?)
            """,
            (
                user_id,
                purpose,
                generate_password_hash(otp_code),
                add_minutes(stamp["iso"], OTP_EXPIRY_MINUTES),
                stamp["display"],
                stamp["iso"],
                OTP_ATTEMPT_LIMIT,
                recipient_email,
            ),
        )
        db.commit()


def get_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def create_reset_token(user_id, purpose):
    raw_token = get_serializer().dumps({"user_id": user_id, "purpose": purpose, "nonce": secrets.token_urlsafe(16)})
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute(
            """
            INSERT INTO reset_tokens (user_id, purpose, token_hash, expires_at_iso, created_at_iso, used)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                user_id,
                purpose,
                generate_password_hash(raw_token),
                add_minutes(stamp["iso"], RESET_TOKEN_EXPIRY_MINUTES),
                stamp["iso"],
            ),
        )
        db.commit()
    return raw_token


def find_valid_reset_token(raw_token, purpose):
    try:
        payload = get_serializer().loads(raw_token, max_age=RESET_TOKEN_EXPIRY_MINUTES * 60)
    except SignatureExpired:
        return None, "Reset token expired."
    except BadSignature:
        return None, "Invalid reset token."
    user_id = payload.get("user_id")
    with open_db() as db:
        rows = db.execute(
            """
            SELECT * FROM reset_tokens
            WHERE user_id = ? AND purpose = ? AND used = 0
            ORDER BY id DESC
            """,
            (user_id, purpose),
        ).fetchall()
    for row in rows:
        token_record = dict(row)
        if not is_future(token_record["expires_at_iso"]):
            continue
        if check_password_hash(token_record["token_hash"], raw_token):
            return token_record, ""
    return None, "Reset token is no longer valid."


def validate_signup_payload(data):
    errors = {}
    full_name = (data.get("name") or "").strip()
    email = normalize_email(data.get("email"))
    phone = normalize_phone(data.get("phone"))
    password = data.get("password") or ""
    cnic = normalize_cnic(data.get("cnic"))
    role = (data.get("role") or "").strip()
    if not full_name:
        errors["name"] = "Full name is required."
    if not email:
        errors["email"] = "Email is required."
    elif not EMAIL_REGEX.fullmatch(email):
        errors["email"] = "Enter a valid email address."
    if not phone:
        errors["phone"] = "Phone number is required."
    elif not PHONE_DIGIT_REGEX.fullmatch(phone):
        errors["phone"] = "Enter a valid phone number."
    if not password:
        errors["password"] = "Password is required."
    elif len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."
    if not cnic:
        errors["cnic"] = "CNIC is required."
    elif not CNIC_REGEX.fullmatch(cnic):
        errors["cnic"] = "CNIC must be exactly 13 digits."
    if role not in {"service_seeker", "logistics_provider", "everyday_user", "fuel_station_manager", "shopkeeper"}:
        errors["role"] = "Please select a valid role."
    role_required = {
        "service_seeker": ("city", "City is required."),
        "logistics_provider": ("city", "City is required."),
        "everyday_user": ("city", "Please tell us your city."),
        "fuel_station_manager": ("station_name", "Station name is required."),
        "shopkeeper": ("shop_name", "Shop or business name is required."),
    }
    if role in role_required:
        field_name, message = role_required[role]
        if not (data.get(field_name) or "").strip():
            errors[field_name] = message
    if role == "fuel_station_manager" and not (data.get("city") or "").strip():
        errors["city"] = "City is required."
    if role == "shopkeeper" and not (data.get("city") or "").strip():
        errors["city"] = "City is required."
    return errors


def get_settings_dict(user):
    raw = user.get("settings_json") or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    parsed.setdefault("notifications", {})
    parsed.setdefault("preferences", {})
    return parsed


def update_user_settings(user_id, settings_dict):
    with open_db() as db:
        db.execute(
            "UPDATE users SET settings_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(settings_dict), timestamp_bundle()["display"], user_id),
        )
        db.commit()


def verify_otp_for_user(user_id, purpose, otp_code):
    record = latest_otp_record(user_id, purpose)
    if not record:
        return None, "No active OTP request found."
    if record.get("cooldown_until_iso") and is_future(record["cooldown_until_iso"]):
        return None, "Too many wrong attempts. Please wait 15 minutes before requesting a new code."
    if not is_future(record["expires_at_iso"]):
        return None, "OTP has expired. Please request a new code."
    if record["verified"]:
        return record, ""
    if not check_password_hash(record["otp_hash"], otp_code):
        attempts = int(record["attempts"]) + 1
        cooldown_until = None
        message = "Invalid OTP."
        if attempts >= OTP_ATTEMPT_LIMIT:
            cooldown_until = (now_local() + timedelta(minutes=LOGIN_COOLDOWN_MINUTES)).isoformat(timespec="seconds")
            message = "Too many wrong attempts. Please wait 15 minutes before requesting a new code."
        with open_db() as db:
            db.execute(
                "UPDATE password_reset_otps SET attempts = ?, cooldown_until_iso = ? WHERE id = ?",
                (attempts, cooldown_until, record["id"]),
            )
            db.commit()
        return None, message
    with open_db() as db:
        db.execute("UPDATE password_reset_otps SET verified = 1 WHERE id = ?", (record["id"],))
        db.commit()
    return latest_otp_record(user_id, purpose), ""
