import logging
from flask import Blueprint, request

from auth.helpers import (
    csrf_error, json_response, timestamp_bundle, send_email,
    SESSION_TOKEN_COOKIE_NAME, DEVICE_COOKIE_NAME, ACCESS_PROOF_COOKIE_NAME,
)
from auth.session_service import find_session_by_token, SessionFoundationError
from auth.trusted_device_service import digest_token, TrustedDeviceError
from shared.db import open_db

logger = logging.getLogger(__name__)

contact_blueprint = Blueprint("contact", __name__, url_prefix="/api/contact")


@contact_blueprint.post("")
def submit_contact():
    """Submit a contact / support inquiry."""
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_response({"success": False, "message": "A JSON object is required."}, 400)
    if any(data.get(field) is not None and not isinstance(data[field], str)
           for field in ("name", "email", "phone", "subject", "message")):
        return json_response({"success": False, "message": "Contact fields must be text."}, 400)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()

    if not name:
        return json_response({"success": False, "message": "Full name is required."}, 400)
    if not email or "@" not in email:
        return json_response({"success": False, "message": "Valid email address is required."}, 400)
    if not subject:
        return json_response({"success": False, "message": "Subject is required."}, 400)
    if not message:
        return json_response({"success": False, "message": "Message cannot be empty."}, 400)

    user_id = None
    current_user = getattr(request, "current_user", None)
    if current_user and isinstance(current_user, dict) and current_user.get("id"):
        user_id = current_user["id"]
    elif request.cookies.get(SESSION_TOKEN_COOKIE_NAME) and request.cookies.get(DEVICE_COOKIE_NAME):
        try:
            with open_db() as db:
                active = find_session_by_token(
                    db, request.cookies[SESSION_TOKEN_COOKIE_NAME],
                    digest_token(request.cookies[DEVICE_COOKIE_NAME]),
                    raw_access_proof=request.cookies.get(ACCESS_PROOF_COOKIE_NAME),
                )
                if active and active["access_proof_valid"]:
                    user_id = active["user_id"]
        except (SessionFoundationError, TrustedDeviceError):
            pass

    stamp = timestamp_bundle()["display"]

    with open_db() as db:
        row = db.execute(
            """
            INSERT INTO contact_messages (user_id, name, email, phone, subject, message, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'new', %s, %s)
            RETURNING id
            """,
            (user_id, name[:255], email[:255], phone[:50] or None, subject[:255], message[:5000], stamp, stamp),
        ).fetchone()
        db.commit()

    # Attempt email dispatch if SMTP is configured
    try:
        support_email = "support@digitransx.com"
        email_body = [
            f"New support inquiry from: {name}",
            f"User Email: {email}",
            f"Phone: {phone or 'Not provided'}",
            f"Subject: {subject}",
            "",
            "Message:",
            message,
        ]
        send_email(f"[Digi_TransX Support] {subject}", support_email, email_body)
    except Exception as exc:
        logger.info("Support contact email notification skipped or unavailable: %s", exc)

    return json_response({
        "success": True,
        "message": "Thank you! Your message has been sent successfully. We will respond within 24 hours.",
        "ticket_id": row["id"] if row else None,
    })
