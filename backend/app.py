import os
import sys
from pathlib import Path

from flask import Flask, send_from_directory

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from auth import auth_blueprint
from auth.helpers import json_response
from admin import admin_blueprint
from agreements import agreements_blueprint
from chat import chat_blueprint
from orders import orders_blueprint
from profile import profile_blueprint
from settings import settings_blueprint
from shared.db import FRONTEND_DIST, check_connection
from tracking import tracking_blueprint
from trucks import trucks_blueprint
from wallet import wallet_blueprint


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "digitransx-dev-secret-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"

app.register_blueprint(auth_blueprint)
app.register_blueprint(admin_blueprint)
app.register_blueprint(agreements_blueprint)
app.register_blueprint(chat_blueprint)
app.register_blueprint(orders_blueprint)
app.register_blueprint(profile_blueprint)
app.register_blueprint(settings_blueprint)
app.register_blueprint(tracking_blueprint)
app.register_blueprint(trucks_blueprint)
app.register_blueprint(wallet_blueprint)

# Schema lives in Supabase (supabase/schema.sql) — just verify connectivity.
check_connection()
from scheduler import start_scheduler
start_scheduler()


@app.get("/")
def serve_root():
    if FRONTEND_DIST.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return json_response({"success": True, "message": "Digi_TransX Flask backend is running."})


@app.get("/<path:path>")
def serve_frontend(path):
    if path.startswith("auth/") or path.startswith("api/"):
        return json_response({"success": False, "message": "Not found."}, 404)
    asset_path = FRONTEND_DIST / path
    if FRONTEND_DIST.exists() and asset_path.exists():
        return send_from_directory(FRONTEND_DIST, path)
    if FRONTEND_DIST.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return json_response({"success": False, "message": "Not found."}, 404)


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host=host, port=port, debug=debug)
