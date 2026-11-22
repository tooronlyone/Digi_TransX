import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from flask import Flask, render_template_string, request, send_from_directory

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from auth import auth_blueprint
from auth.helpers import (
    ACCESS_PROOF_COOKIE_NAME,
    DEVICE_COOKIE_NAME,
    SESSION_TOKEN_COOKIE_NAME,
    get_user_by_id_with_executor,
    json_response,
    role_redirect,
)
from auth.security_config import (
    configure_flask_security,
    validate_production_security_config,
)
from auth.security_headers import ensure_csp_nonce, install_security_headers
from auth.session_service import (
    access_proof_reference,
    find_session_by_token,
    session_event_reference,
    trusted_device_reference,
)
from auth.trusted_device_service import digest_token
from admin import admin_blueprint
from chat import chat_blueprint
from orders import orders_blueprint
from payments import payments_blueprint
from profile import profile_blueprint
from settings import settings_blueprint
from shared.db import FRONTEND_DIST, check_connection
from shared.db import open_db
from terms import terms_blueprint
from tracking import tracking_blueprint
from trucks import trucks_blueprint
from wallet import wallet_blueprint
from contact import contact_blueprint
from driver.routes import driver_blueprint


app = Flask(__name__)
configure_flask_security(app)
validate_production_security_config(app)
install_security_headers(app)

app.register_blueprint(auth_blueprint)
# Preserve the established /auth contract while exposing the bounded API
# namespace used by the secure MPIN backend contract.
app.register_blueprint(auth_blueprint, url_prefix="/api/auth", name="api_auth")
app.register_blueprint(admin_blueprint)
app.register_blueprint(chat_blueprint)
app.register_blueprint(orders_blueprint)
app.register_blueprint(payments_blueprint)
app.register_blueprint(profile_blueprint)
app.register_blueprint(settings_blueprint)
app.register_blueprint(terms_blueprint)
app.register_blueprint(tracking_blueprint)
app.register_blueprint(trucks_blueprint)
app.register_blueprint(wallet_blueprint)
app.register_blueprint(contact_blueprint)
app.register_blueprint(driver_blueprint)

# Schema lives in Supabase (supabase/schema.sql) — just verify connectivity.
check_connection()
# Background jobs do NOT auto-start on a web worker by default: start_scheduler()
# is gated by DIGITRANSX_ENABLE_SCHEDULER (default OFF). Production runs the
# lifecycle jobs in exactly one dedicated worker: `python -m scripts.run_scheduler`
# (see scheduler.py's deployment contract). This call is a no-op unless the flag
# is explicitly enabled.
from scheduler import start_scheduler
start_scheduler()


BOOTSTRAP_FRESHNESS_MINUTES = 15


def _iso_utc(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _display_name(user):
    return (
        user.get("full_name")
        or " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part).strip()
        or user.get("company_name")
        or user.get("username")
        or user.get("email")
        or "User"
    )


def _limited_bootstrap_user(user):
    role = user.get("role") or ""
    return {
        "id": user["id"],
        "name": _display_name(user),
        "role": role,
        "organization_default_route": role_redirect(role),
    }


def _bootstrap_auth_from_session():
    now = datetime.now(timezone.utc)
    invalid = {
        "status": "invalid",
        "verified_at": _iso_utc(now),
        "fresh_until": _iso_utc(now + timedelta(minutes=BOOTSTRAP_FRESHNESS_MINUTES)),
    }
    raw_session = request.cookies.get(SESSION_TOKEN_COOKIE_NAME, "")
    raw_device = request.cookies.get(DEVICE_COOKIE_NAME, "")
    raw_access = request.cookies.get(ACCESS_PROOF_COOKIE_NAME, "")
    if not raw_session or not raw_device:
        return invalid
    try:
        with open_db() as db:
            durable = find_session_by_token(
                db,
                raw_session,
                digest_token(raw_device),
                raw_access_proof=raw_access,
            )
            if not durable:
                return invalid
            user = get_user_by_id_with_executor(db, durable["user_id"])
            if not user:
                return invalid
            proof_expires_at = durable.get("access_proof_expires_at")
            fresh_until = now + timedelta(minutes=BOOTSTRAP_FRESHNESS_MINUTES)
            if proof_expires_at is not None:
                if isinstance(proof_expires_at, str):
                    from datetime import datetime as dt
                    try:
                        proof_expires_at = dt.fromisoformat(proof_expires_at)
                    except Exception:
                        proof_expires_at = None
                if proof_expires_at is not None:
                    if proof_expires_at.tzinfo is None:
                        proof_expires_at = proof_expires_at.replace(tzinfo=timezone.utc)
                    fresh_until = min(fresh_until, proof_expires_at.astimezone(timezone.utc))
            unlocked = bool(durable.get("access_proof_valid")) and not durable.get("access_locked")
            return {
                "status": "unlocked" if unlocked else "locked",
                "verified_at": _iso_utc(now),
                "fresh_until": _iso_utc(fresh_until),
                "user": _limited_bootstrap_user(user),
                "access_locked": not unlocked,
                "security_context": {
                    "session_ref": session_event_reference(durable["session_id"]),
                    "trusted_device_ref": trusted_device_reference(durable["trusted_device_id"]),
                    "access_proof_ref": access_proof_reference(
                        durable.get("access_proof_digest")
                    ),
                },
            }
    except Exception:
        return invalid


def _serve_index():
    index_path = FRONTEND_DIST / "index.html"
    if not index_path.exists():
        return json_response({"success": True, "message": "Digi_TransX Flask backend is running."})
    html = index_path.read_text(encoding="utf-8")
    auth_bootstrap = _bootstrap_auth_from_session()
    csp_nonce = ensure_csp_nonce()
    marker = "</head>"
    script_template = """
<script nonce="{{ csp_nonce }}">
  window.__BOOTSTRAP__ = {{ bootstrap|tojson }};
</script>
"""
    legacy_user = auth_bootstrap.get("user") if auth_bootstrap.get("status") != "invalid" else None
    script = render_template_string(
        script_template,
        bootstrap={"auth": auth_bootstrap, "user": legacy_user},
        csp_nonce=csp_nonce,
    )
    if marker in html:
        html = html.replace(marker, f"{script}{marker}", 1)
    else:
        html = f"{script}{html}"
    response = app.response_class(html, mimetype="text/html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def serve_root():
    if FRONTEND_DIST.exists():
        return _serve_index()
    return json_response({"success": True, "message": "Digi_TransX Flask backend is running."})


@app.get("/<path:path>")
def serve_frontend(path):
    decoded = unquote(unquote(path))
    lower_raw = path.lower()
    lower_dec = decoded.lower()
    if (
        lower_raw in {"auth", "api", "uploads"}
        or lower_dec in {"auth", "api", "uploads"}
        or lower_raw.startswith(("auth/", "api/", "uploads/"))
        or lower_dec.startswith(("auth/", "api/", "uploads/"))
        or "\\" in path
        or "\\" in decoded
        or "\x00" in path
        or "\x00" in decoded
    ):
        return json_response({"success": False, "message": "Not found."}, 404)
    if not FRONTEND_DIST.exists():
        return json_response({"success": False, "message": "Not found."}, 404)
    raw_parts = path.split("/")
    dec_parts = decoded.replace("\\", "/").split("/")
    if ".." in raw_parts or ".." in dec_parts:
        return json_response({"success": False, "message": "Not found."}, 404)
    if any(part.startswith(".") for part in raw_parts + dec_parts if part):
        return json_response({"success": False, "message": "Not found."}, 404)
    dist_root = FRONTEND_DIST.resolve()
    candidate = (dist_root / path).resolve()
    if not candidate.is_relative_to(dist_root):
        return json_response({"success": False, "message": "Not found."}, 404)
    if candidate != dist_root and candidate.is_file():
        rel = candidate.relative_to(dist_root).as_posix()
        return send_from_directory(dist_root, rel)
    if "." in raw_parts[-1] or "." in dec_parts[-1]:
        return json_response({"success": False, "message": "Not found."}, 404)
    return _serve_index()


if __name__ == "__main__":
    from scheduler import env_flag

    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    environment = str(os.environ.get("DIGITRANSX_ENVIRONMENT") or "").strip().lower()
    debug = environment in {"local", "test"} and env_flag("FLASK_DEBUG", default=False)
    app.run(host=host, port=port, debug=debug)
