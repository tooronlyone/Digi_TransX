import secrets
import uuid

from flask import Blueprint, current_app, request, session
from shared.db import open_db
from shared.supabase_client import (
    PasswordProviderUnavailable,
    SignupProviderConflict,
    SignupProviderUnavailable,
    SignupProviderValidationError,
    supabase_create_signup_user,
    supabase_delete_created_signup_user,
    supabase_signup_identity_is_owned,
    supabase_update_password,
    supabase_verify_password,
)
from events.contract import EventContext, EventData
from events.writer import write_security_event
from .helpers import (
    _with_legacy_role,
    map_legacy_role,
    DEVICE_COOKIE_NAME,
    SESSION_TOKEN_COOKIE_NAME,
    ACCESS_PROOF_COOKIE_NAME,
    LOGIN_COOLDOWN_MINUTES,
    OTP_EXPIRY_MINUTES,
    OTP_REGEX,
    build_auth_success_response,
    claim_reset_token,
    clear_authentication_cookies,
    clear_access_proof_cookie,
    clear_device_cookie,
    consume_otp_for_user,
    create_otp_record,
    csrf_error,
    ensure_csrf_token,
    finalize_reset_token_claim,
    generate_numeric_code,
    get_user_by_id,
    get_user_by_id_with_executor,
    get_user_by_login,
    json_response,
    latest_otp_record,
    login_required,
    mask_email,
    mark_reset_token_reconciliation,
    normalize_cnic,
    normalize_email,
    normalize_phone,
    parse_login_id,
    record_login_activity,
    require_csrf,
    role_redirect,
    send_email,
    serialize_user,
    set_access_proof_cookie,
    split_name,
    timestamp_bundle,
    update_user_settings,
    validate_signup_payload,
)
from auth import mpin_service, step_up_service
from auth.trusted_device_service import digest_token, establish_after_full_login
from auth.session_service import (
    access_lock_reference,
    access_proof_reference,
    create_session,
    digest_access_proof,
    digest_opaque_token,
    locked_access_proof_is_valid,
    lock_session_by_id,
    lock_session_user_and_device,
    record_genuine_activity,
    revoke_session,
    rotate_access_proof,
    session_event_reference,
    trusted_device_reference,
)


auth_blueprint = Blueprint("auth", __name__, url_prefix="/auth")


def _auth_event_context(request_id, *, user=None, session_ref=None):
    if user is None:
        return EventContext(
            request_id=request_id,
            source="server_route",
            actor_type="anonymous",
        )
    role = (user.get("role") or "").strip().lower()
    return EventContext(
        request_id=request_id,
        source="server_route",
        actor_type="admin" if role == "platform_admin" else "user",
        actor_id=user["id"],
        actor_role=role,
        subject_user_id=user["id"],
        session_ref=session_ref,
    )


def _invalid_credentials_response():
    return json_response(
        {"success": False, "field": "password", "message": "Incorrect password."},
        401,
    )


def _generic_reverification_response(status=401):
    return json_response(
        {"success": False, "message": "Unable to verify current credentials."},
        status,
    )


def _password_matches_current_user(user, password):
    if (
        not user
        or user.get("is_blocked")
        or not isinstance(password, str)
        or not password
    ):
        return False
    return supabase_verify_password(
        user["email"], password, raise_provider_errors=True
    )


def _identifier_matches_current_user(user, identifier):
    if not isinstance(identifier, str) or not identifier.strip():
        return False
    kind, value = parse_login_id(identifier)
    expected = user.get("cnic", "") if kind == "cnic" else user.get("email", "")
    normalized = normalize_cnic(expected) if kind == "cnic" else normalize_email(expected)
    return bool(value and normalized and secrets.compare_digest(value, normalized))


def _service_subject_context(request_id, user_id):
    return EventContext(
        request_id=request_id,
        source="server_route",
        actor_type="system",
        subject_user_id=user_id,
    )


def _lock_current_authentication(db):
    raw_device = request.cookies.get(DEVICE_COOKIE_NAME, "")
    if not raw_device:
        return None, None, None
    return lock_session_user_and_device(
        db,
        request.current_session["session_id"],
        request.current_user["id"],
        digest_token(raw_device),
    )


def _mpin_unavailable_response():
    return json_response(
        {"success": False, "message": "Secure MPIN service is unavailable."}, 503
    )


def _step_up_metadata(descriptor, *, authorization_id=None, result_code=None):
    metadata = {
        "action_key": descriptor["action_key"],
        "resource_type": descriptor["resource_type"],
        "resource_id": descriptor["resource_id"],
        "request_fingerprint_ref": step_up_service.request_fingerprint_reference(
            descriptor["request_fingerprint"]
        ),
    }
    if authorization_id is not None:
        metadata["authorization_ref"] = step_up_service.authorization_reference(
            authorization_id
        )
    if result_code is not None:
        metadata["result_code"] = result_code
    return metadata


def _record_signup_started(request_id):
    with open_db() as db:
        write_security_event(
            db,
            "security.signup.started",
            _auth_event_context(request_id),
            EventData(),
            idempotency_scope="security.signup.started",
            idempotency_key=request_id,
        )


def _record_signup_failed(request_id, result_code):
    try:
        with open_db() as db:
            write_security_event(
                db,
                "security.signup.failed",
                _auth_event_context(request_id),
                EventData(metadata={"result_code": result_code}),
                idempotency_scope="security.signup.terminal",
                idempotency_key=request_id,
            )
        return True
    except Exception:
        return False


def _signup_failure_response(request_id, result_code, status, payload):
    """Persist a terminal denial before returning any public signup response."""
    if not _record_signup_failed(request_id, result_code):
        return json_response(
            {"success": False, "message": "Signup service is temporarily unavailable."}, 503
        )
    return json_response(payload, status)


def _write_signup_profile(db, user_id, role, clean):
    """Write exactly the one server-selected public role profile."""
    if role in {"service_seeker", "client"}:
        db.execute("DELETE FROM everyday_user_profiles WHERE user_id = %s", (user_id,))
        db.execute(
            """
            INSERT INTO service_seeker_profiles
                (user_id, company_name, business_type, transport_need,
                 default_pickup_city, billing_address)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                company_name = excluded.company_name,
                business_type = excluded.business_type,
                transport_need = excluded.transport_need,
                default_pickup_city = excluded.default_pickup_city,
                billing_address = excluded.billing_address
            """,
            (user_id, clean("company_name"), clean("business_type"), clean("transport_need"),
             clean("default_pickup_city"), clean("billing_address")),
        )
    elif role == "everyday_user":
        db.execute("DELETE FROM service_seeker_profiles WHERE user_id = %s", (user_id,))
        db.execute("INSERT INTO everyday_user_profiles (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
    elif role == "logistics_provider":
        db.execute(
            """INSERT INTO transporter_profiles (user_id, company_name, fleet_size)
               VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET
               company_name = excluded.company_name, fleet_size = excluded.fleet_size""",
            (user_id, clean("company_name"), clean("fleet_size")),
        )
    elif role == "fuel_station_manager":
        db.execute(
            """INSERT INTO fuel_station_profiles (user_id, station_name, pumps_count, license_no)
               VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET
               station_name = excluded.station_name, pumps_count = excluded.pumps_count,
               license_no = excluded.license_no""",
            (user_id, clean("station_name"), clean("pumps_count"), clean("license_no")),
        )
    elif role == "shopkeeper":
        db.execute(
            """INSERT INTO shopkeeper_profiles (user_id, shop_name)
               VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET shop_name = excluded.shop_name""",
            (user_id, clean("shop_name")),
        )
    else:
        raise ValueError("Unsupported signup role.")


def _compensate_signup_identity(auth_user_id, request_id):
    """Remove only public/Auth state proven to belong to this signup request."""
    if not supabase_signup_identity_is_owned(auth_user_id, request_id):
        return False
    try:
        with open_db() as db:
            deleted = db.execute("DELETE FROM users WHERE auth_id = %s", (str(auth_user_id),))
            if getattr(deleted, "rowcount", 0) > 1:
                raise RuntimeError("Signup ownership is ambiguous.")
    except Exception:
        return False
    return supabase_delete_created_signup_user(auth_user_id, request_id)


@auth_blueprint.get("/csrf-token")
def csrf_token():
    return json_response({"success": True, "csrf_token": ensure_csrf_token()})


@auth_blueprint.post("/signup")
def signup():
    data = request.get_json(silent=True) or {}
    request_id = f"signup.{uuid.uuid4().hex}"
    try:
        _record_signup_started(request_id)
    except Exception:
        return json_response(
            {"success": False, "message": "Signup service is temporarily unavailable."}, 503
        )

    errors = validate_signup_payload(data)
    if errors:
        field = next(iter(errors))
        return _signup_failure_response(
            request_id,
            "validation_failed",
            400,
            {"success": False, "field": field, "message": errors[field]},
        )
    full_name = (data.get("name") or "").strip()
    email = normalize_email(data.get("email"))
    phone = normalize_phone(data.get("phone"))
    cnic = normalize_cnic(data.get("cnic"))
    role = (data.get("role") or "").strip()
    stamp = timestamp_bundle()
    with open_db() as db:
        email_exists = db.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        cnic_exists = db.execute("SELECT id FROM users WHERE cnic = %s", (cnic,)).fetchone()
    if email_exists or cnic_exists:
        return _signup_failure_response(
            request_id, "account_conflict", 409,
            {"success": False, "field": "signup", "message": "Unable to complete signup."},
        )

    # Create the account in Supabase Auth. The database trigger inserts the
    # public.users profile row automatically from this metadata.
    try:
        auth_user = supabase_create_signup_user(
            email,
            data.get("password") or "",
            {
                "full_name": full_name,
                "phone": phone,
                "cnic": cnic,
                "role": map_legacy_role(role),
                "legacy_role": role,
                "signup_request_id": request_id,
            },
        )
    except SignupProviderConflict:
        return _signup_failure_response(
            request_id, "account_conflict", 409,
            {"success": False, "field": "signup", "message": "Unable to complete signup."},
        )
    except SignupProviderValidationError:
        return _signup_failure_response(
            request_id, "validation_failed", 400,
            {"success": False, "field": "signup", "message": "Unable to complete signup."},
        )
    except SignupProviderUnavailable:
        return _signup_failure_response(
            request_id, "provider_unavailable", 503,
            {"success": False, "message": "Signup service is temporarily unavailable."},
        )

    def clean(key):
        return (data.get(key) or "").strip() or None

    try:
        with open_db() as db:
            row = db.execute("SELECT id FROM users WHERE auth_id = %s", (str(auth_user.id),)).fetchone()
            if not row:
                raise RuntimeError("Created Auth identity was not linked to a public user.")
            user_id = row["id"]
            db.execute(
                """UPDATE users SET full_name = %s, phone = %s, cnic = %s, legacy_role = %s,
                    city = %s, address = %s, about = %s, updated_at = %s, last_login_at = %s
                    WHERE id = %s AND auth_id = %s""",
                (full_name, phone, cnic, role, clean("city"), clean("address"), clean("about"),
                 stamp["iso"], stamp["iso"], user_id, str(auth_user.id)),
            )
            _write_signup_profile(db, user_id, role, clean)
            record_login_activity(user_id, email, "signup", "success", "", executor=db)
            device_token, device_id, device_event = establish_after_full_login(
                db, user_id, request.cookies.get(DEVICE_COOKIE_NAME)
            )
            session_token, access_proof, session_id = create_session(
                db, user_id, trusted_device_id=device_id
            )
            user = db.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
            if not user:
                raise RuntimeError("Signup public user disappeared.")
            write_security_event(
                db,
                "security.signup.completed",
                _auth_event_context(request_id, user=dict(user)),
                EventData(metadata={"result_code": "completed"}),
                idempotency_scope="security.signup.terminal",
                idempotency_key=request_id,
            )
            write_security_event(
                db, device_event, _auth_event_context(request_id, user=dict(user)),
                EventData(metadata={"result_code": "full_login"} if device_event.endswith("rotated") else {}),
                idempotency_scope="security.trusted_device.terminal", idempotency_key=request_id,
            )
            write_security_event(
                db, "security.session.issued", _auth_event_context(request_id, user=dict(user)),
                EventData(), idempotency_scope="security.session.issued",
                idempotency_key=request_id,
            )
    except Exception:
        result_code = "persistence_failed" if _compensate_signup_identity(auth_user.id, request_id) else "reconciliation_required"
        return _signup_failure_response(
            request_id, result_code, 503,
            {"success": False, "message": "Signup service is temporarily unavailable."},
        )
    return build_auth_success_response(
        dict(user), device_token=device_token, session_token=session_token,
        access_proof=access_proof,
    )


@auth_blueprint.post("/login")
def login():
    request_id = f"auth.{uuid.uuid4().hex}"
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    login_id = data.get("loginId") or ""
    password = data.get("password") or ""
    if not login_id.strip():
        validation_response = json_response(
            {"success": False, "field": "loginId", "message": "Email or CNIC is required."},
            400,
        )
    elif not password:
        validation_response = json_response(
            {"success": False, "field": "password", "message": "Password is required."},
            400,
        )
    else:
        validation_response = None

    if validation_response is not None:
        try:
            with open_db() as db:
                write_security_event(
                    db,
                    "security.login.failed",
                    _auth_event_context(request_id),
                    EventData(metadata={"result_code": "validation_failed"}),
                    idempotency_scope="security.login.terminal",
                    idempotency_key=request_id,
                )
        except Exception:
            current_app.logger.error("Canonical login failure evidence could not be persisted.")
        return validation_response

    try:
        with open_db() as db:
            write_security_event(
                db,
                "security.login.started",
                _auth_event_context(request_id),
                EventData(),
                idempotency_scope="security.login.started",
                idempotency_key=request_id,
            )
    except Exception:
        current_app.logger.error("Mandatory canonical login-start evidence could not be persisted.")
        return json_response(
            {"success": False, "message": "Login service is temporarily unavailable."}, 503
        )

    try:
        user, login_method, lookup_value = get_user_by_login(login_id)
    except Exception:
        current_app.logger.error("Login account lookup could not be completed.")
        return json_response(
            {"success": False, "message": "Login service is temporarily unavailable."}, 503
        )
    password_valid = False
    provider_unavailable = False
    if user and not user.get("is_blocked"):
        try:
            password_valid = supabase_verify_password(
                user["email"], password, raise_provider_errors=True
            )
        except PasswordProviderUnavailable:
            provider_unavailable = True

    terminal_response = None
    committed_user = None
    device_token = None
    session_token = None
    access_proof = None
    try:
        with open_db() as db:
            anonymous_context = _auth_event_context(request_id)
            failure_code = None
            failure_reason = ""
            current_user = (
                get_user_by_id_with_executor(db, user["id"], lock=True)
                if user else None
            )
            if not user:
                failure_code = "invalid_credentials"
                failure_reason = "Account not found."
                terminal_response = _invalid_credentials_response()
            elif (
                not current_user
                or current_user.get("is_blocked")
                or current_user.get("email") != user.get("email")
                or current_user.get("auth_id") != user.get("auth_id")
            ):
                failure_code = "account_unavailable"
                failure_reason = "Account state changed."
                terminal_response = _invalid_credentials_response()
            elif provider_unavailable:
                failure_code = "provider_unavailable"
                failure_reason = "Provider unavailable."
                terminal_response = json_response(
                    {"success": False, "message": "Login service is temporarily unavailable."},
                    503,
                )
            elif not password_valid:
                failure_code = "invalid_credentials"
                failure_reason = "Invalid password."
                terminal_response = _invalid_credentials_response()

            if failure_code is not None:
                record_login_activity(
                    current_user["id"] if current_user else (user["id"] if user else None),
                    lookup_value,
                    login_method,
                    "failed",
                    failure_reason,
                    executor=db,
                )
                write_security_event(
                    db,
                    "security.login.failed",
                    anonymous_context,
                    EventData(metadata={"result_code": failure_code}),
                    idempotency_scope="security.login.terminal",
                    idempotency_key=request_id,
                )
            else:
                stamp = timestamp_bundle()
                db.execute(
                    "UPDATE users SET last_login_at = %s, updated_at = %s WHERE id = %s",
                    (stamp["display"], stamp["display"], current_user["id"]),
                )
                record_login_activity(
                    current_user["id"], lookup_value, login_method, "success", "", executor=db
                )
                device_token, device_id, device_event = establish_after_full_login(
                    db, current_user["id"], request.cookies.get(DEVICE_COOKIE_NAME)
                )
                session_token, access_proof, session_id = create_session(
                    db, current_user["id"], trusted_device_id=device_id
                )
                write_security_event(
                    db,
                    "security.login.succeeded",
                    _auth_event_context(request_id, user=current_user),
                    EventData(metadata={"result_code": "authenticated"}),
                    idempotency_scope="security.login.terminal",
                    idempotency_key=request_id,
                )
                write_security_event(
                    db, device_event, _auth_event_context(request_id, user=current_user),
                    EventData(metadata={"result_code": "full_login"} if device_event.endswith("rotated") else {}),
                    idempotency_scope="security.trusted_device.terminal", idempotency_key=request_id,
                )
                write_security_event(
                    db, "security.session.issued", _auth_event_context(request_id, user=current_user),
                    EventData(), idempotency_scope="security.session.issued",
                    idempotency_key=request_id,
                )
                committed_user = current_user
    except Exception:
        if terminal_response is not None:
            current_app.logger.error("Canonical login failure evidence could not be persisted.")
            return terminal_response
        current_app.logger.error("Mandatory canonical login evidence could not be persisted.")
        return json_response(
            {"success": False, "message": "Login service is temporarily unavailable."}, 503
        )

    if terminal_response is not None:
        return terminal_response
    return build_auth_success_response(
        committed_user, device_token=device_token, session_token=session_token,
        access_proof=access_proof,
    )


@auth_blueprint.get("/me")
@login_required(refresh_activity=False, allow_locked=True)
def auth_me():
    ensure_csrf_token()
    current_session = request.current_session
    return json_response(
        {
            "success": True,
            "user": serialize_user(request.current_user),
            "csrf_token": session["csrf_token"],
            "redirect": role_redirect(request.current_user.get("role")),
            "session": {"last_active_at": session.get("last_active_at", "")},
            "access_locked": bool(current_session.get("access_locked")),
            "security_context": {
                "session_ref": session_event_reference(current_session["session_id"]),
                "trusted_device_ref": trusted_device_reference(
                    current_session["trusted_device_id"]
                ),
                "access_proof_ref": access_proof_reference(
                    current_session.get("access_proof_digest")
                ),
            },
        }
    )


@auth_blueprint.post("/session/activity")
@login_required(refresh_activity=False)
def genuine_session_activity():
    """Accept only the browser's empty, CSRF-backed genuine-activity signal."""

    if request.content_length not in (None, 0):
        return json_response(
            {"success": False, "message": "Activity signal must be empty."}, 400
        )
    err = csrf_error()
    if err:
        return err

    raw_session = request.cookies.get(SESSION_TOKEN_COOKIE_NAME, "")
    raw_device = request.cookies.get(DEVICE_COOKIE_NAME, "")
    raw_access_proof = request.cookies.get(ACCESS_PROOF_COOKIE_NAME, "")
    try:
        session_digest = digest_opaque_token(raw_session)
        device_digest = digest_token(raw_device)
        proof_digest = digest_access_proof(raw_access_proof)
        with open_db() as db:
            outcome = record_genuine_activity(
                db,
                session_id=request.current_session["session_id"],
                user_id=request.current_user["id"],
                session_digest=session_digest,
                device_digest=device_digest,
                access_proof_digest=proof_digest,
            )
            if outcome["status"] == "access_locked" and outcome.get(
                "newly_locked"
            ):
                lock_reference = access_lock_reference(
                    request.current_session["session_id"]
                )
                request_id = f"access.lock.{lock_reference}"
                write_security_event(
                    db,
                    "security.session.access_locked",
                    _service_subject_context(
                        request_id, request.current_user["id"]
                    ),
                    EventData(metadata={"result_code": "app_launch"}),
                    idempotency_scope="security.session.access_locked",
                    idempotency_key=request_id,
                )
            elif outcome["refreshed"]:
                reference = session_event_reference(
                    request.current_session["session_id"]
                )
                request_id = (
                    f"activity.refresh.{reference[8:]}."
                    f"{outcome['refresh_bucket']}"
                )
                write_security_event(
                    db,
                    "security.session.refreshed",
                    _auth_event_context(
                        request_id,
                        user=request.current_user,
                        session_ref=reference,
                    ),
                    EventData(),
                    idempotency_scope="security.session.refreshed",
                    idempotency_key=request_id,
                )
    except Exception:
        current_app.logger.error("Genuine session activity could not be committed.")
        return json_response(
            {"success": False, "message": "Activity service is temporarily unavailable."},
            503,
        )

    if outcome["status"] == "invalid_authentication":
        return clear_authentication_cookies(
            json_response(
                {"success": False, "message": "Authentication required."}, 401
            )
        )
    if outcome["status"] == "access_locked":
        return clear_access_proof_cookie(
            json_response(
                {
                    "success": False,
                    "code": "access_locked",
                    "message": "Access is locked.",
                },
                423,
            )
        )
    return ("", 204)


@auth_blueprint.post("/logout")
@login_required(refresh_activity=False, allow_locked=True)
def logout():
    request_id = f"auth.{uuid.uuid4().hex}"
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)
    try:
        with open_db() as db:
            locked = lock_session_by_id(
                db, request.current_session["session_id"], request.current_user["id"]
            )
            if not locked:
                raise RuntimeError("Current durable session could not be locked for logout.")
            if revoke_session(db, locked["session_id"], "logout") != 1:
                raise RuntimeError("Current durable session could not be revoked.")
            context = _auth_event_context(request_id, user=request.current_user)
            write_security_event(
                db, "security.session.revoked", context,
                EventData(metadata={"result_code": "logout"}),
                idempotency_scope="security.session.revoked", idempotency_key=request_id,
            )
            write_security_event(
                db, "security.logout.completed", context,
                EventData(metadata={"result_code": "completed"}),
                idempotency_scope="security.logout.completed", idempotency_key=request_id,
            )
    except Exception:
        current_app.logger.error("Canonical logout revocation/evidence could not be persisted.")
    response = json_response({"success": True, "message": "Logged out successfully."})
    return clear_authentication_cookies(response)


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
                f"Dear {user.get('first_name') or user.get('full_name') or 'User'},",
                "",
                f"Your Digi_TransX password reset code is: {otp_code}",
                f"This code will expire in {OTP_EXPIRY_MINUTES} minutes.",
                "",
                "If you did not request this code, please ignore this email.",
            ],
        )
    except Exception:
        current_app.logger.error("Password-reset OTP email delivery failed.")
        return json_response(
            {"success": False, "message": "Unable to send the password-reset code."},
            503,
        )
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
    _, error_message, reset_token = consume_otp_for_user(
        user["id"], "password_reset", otp_code,
        issue_reset_authorization=True,
    )
    if error_message:
        return json_response({"success": False, "message": error_message}, 400)
    return json_response({"success": True, "reset_token": reset_token})


@auth_blueprint.post("/reset-password")
def reset_password():
    data = request.get_json(silent=True) or {}
    raw_token = data.get("reset_token") or ""
    new_password = data.get("new_password") or ""
    if not raw_token:
        return json_response({"success": False, "message": "Reset token is required."}, 400)
    if len(new_password) < 8:
        return json_response({"success": False, "field": "password", "message": "Password must be at least 8 characters."}, 400)
    token_record, claim_secret, error_message = claim_reset_token(
        raw_token, "password_reset"
    )
    if error_message:
        return json_response({"success": False, "message": error_message}, 400)
    if not token_record.get("auth_id"):
        try:
            mark_reset_token_reconciliation(token_record["id"], claim_secret)
        except Exception:
            current_app.logger.error("Reset authorization reconciliation state could not be persisted.")
        return json_response(
            {"success": False, "message": "Password reset service is temporarily unavailable."},
            503,
        )
    try:
        supabase_update_password(token_record["auth_id"], new_password)
    except Exception:
        try:
            mark_reset_token_reconciliation(token_record["id"], claim_secret)
        except Exception:
            current_app.logger.error("Reset authorization reconciliation state could not be persisted.")
        current_app.logger.error("Auth provider password reset failed.")
        return json_response(
            {
                "success": False,
                "message": "Password reset could not be completed. Request a new code.",
            },
            503,
        )
    try:
        with open_db() as db:
            db.execute(
                "UPDATE users SET updated_at = now() WHERE id = %s",
                (token_record["user_id"],),
            )
            if finalize_reset_token_claim(
                db, token_record["id"], claim_secret, completed=True
            ) != 1:
                raise RuntimeError("Reset authorization finalization lost its claim.")
    except Exception:
        current_app.logger.error("Password reset finalization requires reconciliation.")
        return json_response(
            {
                "success": False,
                "message": (
                    "Password was changed, but confirmation is pending. "
                    "Request a new code if you cannot sign in."
                ),
            },
            503,
        )
    return json_response({"success": True, "message": "Password reset successful."})


@auth_blueprint.get("/fast-login/options")
def fast_login_options():
    response = json_response({"success": True, "available": False})
    return clear_device_cookie(response)


@auth_blueprint.post("/fast-login/mpin")
def fast_login_mpin():
    response = json_response(
        {"success": False, "message": "Full login is required."}, 401
    )
    return clear_device_cookie(response)


@auth_blueprint.post("/fast-login/setup")
@login_required
def setup_fast_login():
    err = csrf_error()
    if err:
        return err
    return json_response(
        {"success": False, "message": "Legacy MPIN setup is unavailable."}, 410
    )


@auth_blueprint.post("/fast-login/disable")
@login_required
def disable_fast_login():
    err = csrf_error()
    if err:
        return err
    return json_response(
        {"success": False, "message": "Legacy MPIN disable is unavailable."}, 410
    )


@auth_blueprint.get("/mpin/status")
@login_required(refresh_activity=False, allow_locked=True)
def mpin_status():
    try:
        mpin_service.validate_configuration()
        with open_db() as db:
            row = db.execute(
                "SELECT permanently_locked FROM mpin_credentials WHERE user_id = %s",
                (request.current_user["id"],),
            ).fetchone()
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    except Exception:
        current_app.logger.error("Secure MPIN status could not be determined.")
        return _mpin_unavailable_response()
    return json_response(
        {
            "success": True,
            "access_locked": bool(request.current_session.get("access_locked")),
            "mpin": {
                "enrolled": bool(row),
                "locked": bool(row and row["permanently_locked"]),
                "role_eligible": mpin_service.role_is_eligible(
                    request.current_user.get("role")
                ),
            },
        }
    )


@auth_blueprint.post("/mpin/enroll")
@login_required(refresh_activity=False)
def mpin_enroll():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    try:
        mpin = mpin_service.validate_mpin(data.get("mpin"))
        mpin_service.validate_configuration()
    except mpin_service.MpinError:
        return json_response(
            {"success": False, "field": "mpin", "message": "MPIN must be exactly four ASCII digits."},
            400,
        )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    if not mpin_service.role_is_eligible(request.current_user.get("role")):
        return json_response(
            {"success": False, "message": "MPIN is not supported for this account."},
            403,
        )
    try:
        if not _password_matches_current_user(
            request.current_user, data.get("password")
        ):
            return _generic_reverification_response()
    except PasswordProviderUnavailable:
        return _generic_reverification_response(503)

    request_id = f"mpin.{uuid.uuid4().hex}"
    try:
        with open_db() as db:
            durable, user, device = _lock_current_authentication(db)
            if not durable or not user or not device or durable["access_locked"]:
                raise RuntimeError("Current authentication changed during enrollment.")
            if mpin_service.lock_credential(db, user["id"]):
                return json_response(
                    {"success": False, "message": "MPIN is already enrolled."}, 409
                )
            if not mpin_service.enroll(db, user["id"], mpin):
                raise RuntimeError("MPIN enrollment lost its locked user.")
            db.execute(
                "UPDATE user_sessions SET password_verified_at=now(), updated_at=now() WHERE session_id=%s",
                (durable["session_id"],),
            )
            write_security_event(
                db,
                "security.mpin.enrolled",
                _auth_event_context(request_id, user=request.current_user),
                EventData(),
                idempotency_scope="security.mpin.enrolled",
                idempotency_key=request_id,
            )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    except Exception:
        current_app.logger.error("Secure MPIN enrollment could not be committed.")
        return _mpin_unavailable_response()
    return json_response({"success": True, "message": "MPIN enrolled."})


@auth_blueprint.post("/mpin/unlock")
@login_required(refresh_activity=False, allow_locked=True)
def mpin_unlock():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    try:
        mpin = mpin_service.validate_mpin(data.get("mpin"))
        mpin_service.validate_configuration()
    except mpin_service.MpinError:
        return json_response(
            {"success": False, "field": "mpin", "message": "MPIN must be exactly four ASCII digits."},
            400,
        )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    if not mpin_service.role_is_eligible(request.current_user.get("role")):
        return json_response(
            {"success": False, "message": "MPIN is not supported for this account."},
            403,
        )

    request_id = f"mpin.{uuid.uuid4().hex}"
    access_proof = None
    try:
        with open_db() as db:
            durable, user, device = _lock_current_authentication(db)
            if not durable or not user or not device:
                raise RuntimeError("Current authentication changed during unlock.")
            if not durable["access_locked"]:
                return json_response(
                    {"success": False, "message": "Access is already unlocked."}, 409
                )
            credential = mpin_service.lock_credential(db, user["id"])
            if not credential:
                return json_response(
                    {"success": False, "message": "Unable to unlock access."}, 401
                )
            if credential["permanently_locked"]:
                return json_response(
                    {
                        "success": False,
                        "code": "mpin_locked",
                        "message": "MPIN is locked. Use password recovery.",
                    },
                    423,
                )
            if not mpin_service.verify_mpin(mpin, credential):
                outcome, _ = mpin_service.record_failure(db, user["id"])
                if outcome == "locked":
                    write_security_event(
                        db,
                        "security.mpin.locked",
                        _service_subject_context(request_id, user["id"]),
                        EventData(metadata={"result_code": "attempt_limit"}),
                        idempotency_scope="security.mpin.unlock",
                        idempotency_key=request_id,
                    )
                    return json_response(
                        {
                            "success": False,
                            "code": "mpin_locked",
                            "message": "MPIN is locked. Use password recovery.",
                        },
                        423,
                    )
                if outcome != "failed":
                    raise RuntimeError("MPIN failure state changed unexpectedly.")
                write_security_event(
                    db,
                    "security.mpin.unlock_failed",
                    _service_subject_context(request_id, user["id"]),
                    EventData(metadata={"result_code": "invalid_mpin"}),
                    idempotency_scope="security.mpin.unlock",
                    idempotency_key=request_id,
                )
                return json_response(
                    {"success": False, "message": "Unable to unlock access."}, 401
                )
            if mpin_service.reset_failures(db, user["id"]) != 1:
                raise RuntimeError("MPIN success could not reset its failure state.")
            access_proof = rotate_access_proof(db, durable["session_id"])
            write_security_event(
                db,
                "security.mpin.unlock_succeeded",
                _auth_event_context(request_id, user=request.current_user),
                EventData(),
                idempotency_scope="security.mpin.unlock",
                idempotency_key=request_id,
            )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    except Exception:
        current_app.logger.error("Secure MPIN unlock could not be committed.")
        return _mpin_unavailable_response()
    return set_access_proof_cookie(
        json_response({"success": True, "message": "Access unlocked."}),
        access_proof,
    )


@auth_blueprint.post("/mpin/password-unlock")
@auth_blueprint.post("/access/unlock/password")
@login_required(refresh_activity=False, allow_locked=True)
def password_unlock():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    identifier = data.get("identifier", data.get("loginId"))
    if not _identifier_matches_current_user(request.current_user, identifier):
        return _generic_reverification_response()
    try:
        if not _password_matches_current_user(
            request.current_user, data.get("password")
        ):
            return _generic_reverification_response()
    except PasswordProviderUnavailable:
        return _generic_reverification_response(503)

    access_proof = None
    try:
        with open_db() as db:
            durable, user, device = _lock_current_authentication(db)
            if not durable or not user or not device:
                raise RuntimeError("Current authentication changed during password unlock.")
            if not durable["access_locked"]:
                return json_response(
                    {"success": False, "message": "Access is already unlocked."}, 409
                )
            access_proof = rotate_access_proof(
                db, durable["session_id"], password_verified=True
            )
    except Exception:
        current_app.logger.error("Password access unlock could not be committed.")
        return _generic_reverification_response(503)
    return set_access_proof_cookie(
        json_response({"success": True, "message": "Access unlocked."}),
        access_proof,
    )


@auth_blueprint.post("/mpin/change")
@login_required(refresh_activity=False)
def mpin_change():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    try:
        current_mpin = mpin_service.validate_mpin(data.get("current_mpin"))
        new_mpin = mpin_service.validate_mpin(data.get("new_mpin"))
        mpin_service.validate_configuration()
    except mpin_service.MpinError:
        return json_response(
            {"success": False, "field": "mpin", "message": "MPIN values must be exactly four ASCII digits."},
            400,
        )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    if not mpin_service.role_is_eligible(request.current_user.get("role")):
        return json_response(
            {"success": False, "message": "MPIN is not supported for this account."},
            403,
        )
    request_id = f"mpin.{uuid.uuid4().hex}"
    try:
        with open_db() as db:
            durable, user, device = _lock_current_authentication(db)
            if not durable or not user or not device or durable["access_locked"]:
                raise RuntimeError("Current authentication changed during MPIN change.")
            credential = mpin_service.lock_credential(db, user["id"])
            if not credential:
                return json_response(
                    {"success": False, "message": "Unable to verify current MPIN."}, 401
                )
            if credential["permanently_locked"]:
                return json_response(
                    {"success": False, "code": "mpin_locked", "message": "MPIN is locked. Use password recovery."},
                    423,
                )
            if not mpin_service.verify_mpin(current_mpin, credential):
                outcome, _ = mpin_service.record_failure(db, user["id"])
                if outcome == "locked":
                    write_security_event(
                        db, "security.mpin.locked",
                        _service_subject_context(request_id, user["id"]),
                        EventData(metadata={"result_code": "attempt_limit"}),
                        idempotency_scope="security.mpin.change",
                        idempotency_key=request_id,
                    )
                    return json_response(
                        {"success": False, "code": "mpin_locked", "message": "MPIN is locked. Use password recovery."},
                        423,
                    )
                if outcome != "failed":
                    raise RuntimeError("MPIN failure state changed unexpectedly.")
                return json_response(
                    {"success": False, "message": "Unable to verify current MPIN."}, 401
                )
            if not mpin_service.replace(db, user["id"], new_mpin):
                raise RuntimeError("MPIN change lost its locked credential.")
            write_security_event(
                db,
                "security.mpin.changed",
                _auth_event_context(request_id, user=request.current_user),
                EventData(),
                idempotency_scope="security.mpin.changed",
                idempotency_key=request_id,
            )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    except Exception:
        current_app.logger.error("Secure MPIN change could not be committed.")
        return _mpin_unavailable_response()
    return json_response({"success": True, "message": "MPIN changed."})


@auth_blueprint.post("/mpin/disable")
@login_required(refresh_activity=False)
def mpin_disable():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    try:
        mpin_service.validate_configuration()
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()

    password_verified = False
    if data.get("password") is not None:
        try:
            password_verified = _password_matches_current_user(
                request.current_user, data.get("password")
            )
        except PasswordProviderUnavailable:
            return _generic_reverification_response(503)
        if not password_verified:
            return _generic_reverification_response()

    request_id = f"mpin.{uuid.uuid4().hex}"
    try:
        with open_db() as db:
            durable, user, device = _lock_current_authentication(db)
            if not durable or not user or not device or durable["access_locked"]:
                raise RuntimeError("Current authentication changed during MPIN disable.")
            credential = mpin_service.lock_credential(db, user["id"])
            if not credential:
                return json_response({"success": True, "message": "MPIN disabled."})
            if password_verified:
                db.execute(
                    "UPDATE user_sessions SET password_verified_at=now(), updated_at=now() WHERE session_id=%s",
                    (durable["session_id"],),
                )
                authorized = True
            else:
                recent = db.execute(
                    """
                    SELECT password_verified_at IS NOT NULL
                       AND password_verified_at > now() - interval '10 minutes' AS recent
                      FROM user_sessions WHERE session_id=%s
                    """,
                    (durable["session_id"],),
                ).fetchone()
                authorized = bool(recent and recent["recent"])
                if not authorized and data.get("current_mpin") is not None:
                    try:
                        current_mpin = mpin_service.validate_mpin(
                            data.get("current_mpin")
                        )
                    except mpin_service.MpinError:
                        current_mpin = None
                    if credential["permanently_locked"]:
                        return json_response(
                            {"success": False, "code": "mpin_locked", "message": "MPIN is locked. Use password recovery."},
                            423,
                        )
                    authorized = bool(current_mpin and mpin_service.verify_mpin(current_mpin, credential))
                    if current_mpin and not authorized:
                        outcome, _ = mpin_service.record_failure(db, user["id"])
                        if outcome == "locked":
                            write_security_event(
                                db, "security.mpin.locked",
                                _service_subject_context(request_id, user["id"]),
                                EventData(metadata={"result_code": "attempt_limit"}),
                                idempotency_scope="security.mpin.disable",
                                idempotency_key=request_id,
                            )
                            return json_response(
                                {"success": False, "code": "mpin_locked", "message": "MPIN is locked. Use password recovery."},
                                423,
                            )
                        if outcome != "failed":
                            raise RuntimeError("MPIN failure state changed unexpectedly.")
            if not authorized:
                return json_response(
                    {"success": False, "message": "Unable to authorize MPIN disable."},
                    401,
                )
            if mpin_service.disable(db, user["id"]) != 1:
                raise RuntimeError("MPIN disable lost its locked credential.")
            write_security_event(
                db,
                "security.mpin.disabled",
                _auth_event_context(request_id, user=request.current_user),
                EventData(),
                idempotency_scope="security.mpin.disabled",
                idempotency_key=request_id,
            )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    except Exception:
        current_app.logger.error("Secure MPIN disable could not be committed.")
        return _mpin_unavailable_response()
    return json_response({"success": True, "message": "MPIN disabled."})


@auth_blueprint.post("/mpin/step-up")
@login_required(refresh_activity=False)
def mpin_step_up():
    """Issue a three-minute, action-bound, one-use authorization proof."""
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    try:
        mpin = mpin_service.validate_mpin(data.get("mpin"))
        descriptor = step_up_service.normalize_descriptor(data.get("action"))
        mpin_service.validate_configuration()
    except (mpin_service.MpinError, step_up_service.StepUpError):
        return json_response(
            {"success": False, "message": "A valid MPIN and action descriptor are required."},
            400,
        )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    if not mpin_service.role_is_eligible(request.current_user.get("role")):
        return json_response(
            {"success": False, "message": "MPIN is not supported for this account."},
            403,
        )

    request_id = f"mpin.step_up.{uuid.uuid4().hex}"
    issued = None
    try:
        with open_db() as db:
            durable, user, device = _lock_current_authentication(db)
            if (
                not durable or not user or not device or durable["access_locked"]
            ):
                raise RuntimeError("Current authentication changed during MPIN step-up.")
            raw_access_proof = request.cookies.get(ACCESS_PROOF_COOKIE_NAME, "")
            if not locked_access_proof_is_valid(db, durable, raw_access_proof):
                return clear_access_proof_cookie(
                    json_response(
                        {
                            "success": False,
                            "code": "access_locked",
                            "message": "Access is locked.",
                        },
                        423,
                    )
                )
            credential = mpin_service.lock_credential(db, user["id"])
            if not credential:
                return json_response(
                    {"success": False, "code": "mpin_enrollment_required", "message": "MPIN enrollment is required."},
                    409,
                )
            if credential["permanently_locked"]:
                write_security_event(
                    db, "security.mpin.step_up_failed",
                    _service_subject_context(request_id, user["id"]),
                    EventData(metadata=_step_up_metadata(descriptor, result_code="rate_limited")),
                    idempotency_scope="security.mpin.step_up",
                    idempotency_key=request_id,
                )
                return json_response(
                    {"success": False, "code": "mpin_locked", "message": "MPIN is locked. Use password recovery."},
                    423,
                )
            if not mpin_service.verify_mpin(mpin, credential):
                outcome, _ = mpin_service.record_failure(db, user["id"])
                result_code = "rate_limited" if outcome == "locked" else "invalid_mpin"
                if outcome not in {"failed", "locked"}:
                    raise RuntimeError("MPIN failure state changed unexpectedly.")
                write_security_event(
                    db, "security.mpin.step_up_failed",
                    _service_subject_context(request_id, user["id"]),
                    EventData(metadata=_step_up_metadata(descriptor, result_code=result_code)),
                    idempotency_scope="security.mpin.step_up",
                    idempotency_key=request_id,
                )
                if outcome == "locked":
                    write_security_event(
                        db, "security.mpin.locked",
                        _service_subject_context(request_id, user["id"]),
                        EventData(metadata={"result_code": "attempt_limit"}),
                        idempotency_scope="security.mpin.step_up.locked",
                        idempotency_key=request_id,
                    )
                    return json_response(
                        {"success": False, "code": "mpin_locked", "message": "MPIN is locked. Use password recovery."},
                        423,
                    )
                return json_response(
                    {"success": False, "message": "Unable to authorize this action."}, 401
                )
            if mpin_service.reset_failures(db, user["id"]) != 1:
                raise RuntimeError("MPIN success could not reset its failure state.")
            issued = step_up_service.issue_authorization(
                db, user_id=user["id"], session_id=durable["session_id"],
                trusted_device_id=device["id"],
                credential_generation=credential["credential_generation"],
                descriptor=descriptor,
            )
            if issued is None:
                return json_response(
                    {"success": False, "code": "step_up_already_issued", "message": "An authorization is already active for this action."},
                    409,
                )
            write_security_event(
                db, "security.mpin.step_up_succeeded",
                _auth_event_context(request_id, user=request.current_user),
                EventData(metadata=_step_up_metadata(
                    descriptor, authorization_id=issued["authorization_id"]
                )),
                idempotency_scope="security.mpin.step_up",
                idempotency_key=request_id,
            )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    except Exception:
        current_app.logger.error("MPIN step-up authorization could not be committed.")
        return json_response(
            {"success": False, "message": "Step-up authorization is temporarily unavailable."},
            503,
        )
    response = json_response(
        {"success": True, "authorization_id": str(issued["authorization_id"]),
         "authorization_proof": issued["proof"], "expires_at": issued["expires_at"]}
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@auth_blueprint.post("/mpin/reset")
@login_required(refresh_activity=False)
def mpin_reset():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    try:
        new_mpin = mpin_service.validate_mpin(data.get("new_mpin"))
        mpin_service.validate_configuration()
    except mpin_service.MpinError:
        return json_response(
            {"success": False, "field": "mpin", "message": "MPIN must be exactly four ASCII digits."},
            400,
        )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    if not mpin_service.role_is_eligible(request.current_user.get("role")):
        return json_response(
            {"success": False, "message": "MPIN is not supported for this account."},
            403,
        )
    try:
        if not _password_matches_current_user(
            request.current_user, data.get("password")
        ):
            return _generic_reverification_response()
    except PasswordProviderUnavailable:
        return _generic_reverification_response(503)

    request_id = f"mpin.{uuid.uuid4().hex}"
    try:
        with open_db() as db:
            durable, user, device = _lock_current_authentication(db)
            if not durable or not user or not device:
                raise RuntimeError("Current authentication changed during MPIN reset.")
            mpin_service.lock_credential(db, user["id"])
            if not mpin_service.reset_or_enroll(db, user["id"], new_mpin):
                raise RuntimeError("MPIN reset lost its locked user.")
            db.execute(
                "UPDATE user_sessions SET password_verified_at=now(), updated_at=now() WHERE session_id=%s",
                (durable["session_id"],),
            )
            write_security_event(
                db,
                "security.mpin.reset_completed",
                _auth_event_context(request_id, user=request.current_user),
                EventData(metadata={"result_code": "user_reauthentication"}),
                idempotency_scope="security.mpin.reset_completed",
                idempotency_key=request_id,
            )
    except mpin_service.MpinConfigurationError:
        return _mpin_unavailable_response()
    except Exception:
        current_app.logger.error("Secure MPIN reset could not be committed.")
        return _mpin_unavailable_response()
    return json_response({"success": True, "message": "MPIN reset completed."})
