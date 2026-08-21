"""Regression coverage for the email-only external security-channel policy."""

import json
from pathlib import Path

from flask import Flask, request
import pytest

from auth.helpers import get_settings_dict, validate_signup_payload
from events.catalog import CATALOG
from settings import routes as settings_routes


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_TAIL = "20260801210000_mpin_step_up_authorization_foundation.sql"


def test_legacy_sms_preferences_are_removed_from_settings_projection():
    settings = get_settings_dict(
        {
            "settings_json": json.dumps(
                {
                    "notifications": {
                        "email": False,
                        "sms": True,
                        " SMS ": False,
                        "paymentUpdates": False,
                        "push": True,
                    },
                    "preferences": {"theme": "dark"},
                }
            )
        }
    )

    assert settings == {
        "notifications": {"email": False, "push": True},
        "preferences": {"theme": "dark"},
    }


def test_notification_update_ignores_sms_and_cannot_persist_it(monkeypatch):
    captured = {}
    monkeypatch.setattr(settings_routes, "csrf_error", lambda: None)
    monkeypatch.setattr(
        settings_routes,
        "update_user_settings",
        lambda user_id, value: captured.update(user_id=user_id, settings=value),
    )
    app = Flask(__name__)

    with app.test_request_context(
        "/api/settings/notifications",
        method="PUT",
        json={"email": False, "sms": True, "push": False},
    ):
        request.current_user = {
            "id": 17,
            "settings_json": json.dumps(
                {
                    "notifications": {
                        "sms": False,
                        "paymentUpdates": False,
                        "jobAlerts": False,
                    }
                }
            ),
        }
        response = settings_routes.settings_notifications.__wrapped__()

    assert response.status_code == 200
    assert captured["user_id"] == 17
    assert "sms" not in captured["settings"]["notifications"]
    assert "paymentUpdates" not in captured["settings"]["notifications"]
    assert "sms" not in response.get_json()["data"]["notifications"]
    assert captured["settings"]["notifications"]["email"] is False
    assert captured["settings"]["notifications"]["push"] is False


def test_runtime_and_catalog_have_no_sms_channel_surface():
    runtime_files = (
        "backend/settings/routes.py",
        "backend/shared/notifications.py",
        "frontend-react/src/pages/transporter/settings.jsx",
        "frontend-react/src/pages/transporter/help.jsx",
    )
    for relative in runtime_files:
        source = (REPO_ROOT / relative).read_text(encoding="utf-8").lower()
        assert "sms" not in source, relative
        assert "email or phone" not in source, relative

    assert not [name for name in CATALOG if "sms" in name.lower()]
    assert len(CATALOG) == 172
    assert sum(item.lifecycle_status == "planned" for item in CATALOG.values()) == 164
    assert sum(item.lifecycle_status == "deferred" for item in CATALOG.values()) == 8
    assert sum(item.writable for item in CATALOG.values()) == 158
    assert sum(item.integrated for item in CATALOG.values()) == 23

    expected_email_events = {
        "security.signup.email_otp_sent",
        "security.signup.email_otp_failed",
        "security.login.email_otp_sent",
        "security.login.email_otp_failed",
    }
    assert {name for name in CATALOG if ".email_otp_" in name} == expected_email_events
    for name in expected_email_events:
        definition = CATALOG[name]
        assert definition.lifecycle_status == "planned"
        assert definition.writable is True
        assert definition.integrated is False


def test_no_sms_provider_dependency_or_configuration_and_phone_fields_remain():
    dependency_text = "\n".join(
        (REPO_ROOT / relative).read_text(encoding="utf-8").lower()
        for relative in (
            "requirements.txt",
            "backend/requirements.txt",
            "frontend-react/package.json",
        )
    )
    for provider in ("twilio", "nexmo", "vonage", "messagebird", "plivo", "telnyx"):
        assert provider not in dependency_text

    env_keys = {
        line.split("=", 1)[0].strip().lower()
        for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    assert not [key for key in env_keys if "sms" in key]

    schema = (
        (REPO_ROOT / "supabase" / "schema.sql")
        .read_text(encoding="utf-8")
        .lower()
    )
    for legitimate_field in ("phone", "cnic", "driver_cnic"):
        assert legitimate_field in schema


def test_sms_correction_has_zero_migration_delta():
    migrations = sorted(
        path.name for path in (REPO_ROOT / "supabase" / "migrations").glob("*.sql")
    )
    assert migrations[-1] == MIGRATION_TAIL
    assert not [name for name in migrations if "sms" in name.lower()]
    assert not [name for name in migrations if name.startswith("20260801220000")]


@pytest.mark.parametrize(
    "address",
    (
        "person@gmail.com",
        "person@outlook.com",
        "operations@carrier.example",
    ),
)
def test_provider_neutral_email_syntax_accepts_valid_providers(address):
    errors = validate_signup_payload(
        {
            "name": "Provider Neutral User",
            "email": address,
            "phone": "03001234567",
            "password": "bounded-password",
            "cnic": "3520212345678",
            "role": "service_seeker",
            "city": "Lahore",
        }
    )
    assert "email" not in errors


def test_dedicated_organization_portal_is_truthful_and_fail_closed():
    frontend = REPO_ROOT / "frontend-react" / "src"
    production_source = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in frontend.rglob("*")
        if path.is_file()
    ).lower()
    unavailable = (
        frontend / "components" / "org" / "OrgUnavailablePage.jsx"
    ).read_text(encoding="utf-8")
    app_source = (frontend / "App.jsx").read_text(encoding="utf-8")

    for gmail_only_claim in (
        "verify gmail",
        "gmail verified",
        "verified gmail",
        "gmail profile",
        "gmail verification is required",
    ):
        assert gmail_only_claim not in production_source
    assert "gmail, outlook, yahoo, company domains" in production_source
    assert "/api/org/" not in production_source
    assert "/api/organization/" not in production_source
    assert "OrgUnavailablePage" in app_source
    assert 'path="/org/*"' in app_source
    assert "return <OrgUnavailablePage />" in app_source
    assert not list((frontend / "pages" / "org").rglob("*.jsx"))
    assert not (frontend / "lib" / "orgPortal.js").exists()

    assert "Organization portal unavailable" in unavailable
    assert "has no organization authentication backend yet" in unavailable
    assert "does not collect credentials" in unavailable
    assert 'to="/login"' in unavailable
    assert 'to="/signup"' in unavailable
    for forbidden_owner in (
        "fetch(",
        "orgRequest(",
        "orgAuthRequest(",
        "onSubmit",
        'type="password"',
        "setItem(",
        "history.",
        "console.",
    ):
        assert forbidden_owner not in unavailable
    for legacy_key in (
        "org_access_token",
        "org_department_token",
        "org_department_id",
    ):
        assert legacy_key in unavailable
    assert "localStorage.removeItem(key)" in unavailable
    assert "sessionStorage.removeItem(key)" in unavailable


def test_org_routes_have_no_owner_and_canonical_company_auth_remains():
    backend_runtime = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (REPO_ROOT / "backend").rglob("*.py")
        if "tests" not in path.parts
    )
    auth_routes = (
        REPO_ROOT / "backend" / "auth" / "routes.py"
    ).read_text(encoding="utf-8")
    app_source = (
        REPO_ROOT / "frontend-react" / "src" / "App.jsx"
    ).read_text(encoding="utf-8")
    login_source = (
        REPO_ROOT / "frontend-react" / "src" / "pages" / "auth" / "Login.jsx"
    ).read_text(encoding="utf-8")

    assert 'url_prefix="/api/org"' not in backend_runtime
    assert 'url_prefix="/api/organization"' not in backend_runtime
    assert "/api/org/" not in backend_runtime
    assert auth_routes.count('@auth_blueprint.post("/login")') == 1
    assert auth_routes.count('@auth_blueprint.post("/signup")') == 1
    assert "fetch('/auth/login'" in login_source
    assert 'path="/login"' in app_source
    assert 'path="/signup"' in app_source
    assert 'path="details/service-seeker"' in app_source


def test_public_partner_contact_email_surface_remains_unchanged():
    source = (
        REPO_ROOT
        / "frontend-react"
        / "src"
        / "pages"
        / "transporter"
        / "partner_with_us.jsx"
    ).read_text(encoding="utf-8")
    assert "Apply to Partner" in source
    assert "name=\"email\"" in source
    assert 'type="email"' in source
    assert 'placeholder="you@example.com"' in source
