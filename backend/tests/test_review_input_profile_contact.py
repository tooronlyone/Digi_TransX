"""HTTP regressions for malformed input, profile persistence and ticket ownership."""
import pytest
from flask import Flask, request

from auth import routes as auth_routes
from auth.helpers import serialize_user
from profile import routes as profile_routes
from contact import routes as contact_routes
from wallet import routes as wallet_routes
from tests.remediation_harness import remediation_database_url, remediation_env


@pytest.fixture
def boundary_client(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="review-inputs")
    monkeypatch.setattr(auth_routes, "_record_signup_started", lambda *_: None)
    monkeypatch.setattr(auth_routes, "_record_signup_failed", lambda *_: True)
    for module in (profile_routes, contact_routes, wallet_routes):
        monkeypatch.setattr(module, "csrf_error", lambda: None)
        monkeypatch.setattr(module, "open_db", lambda: pytest.fail("Invalid input reached the database"))
    app.register_blueprint(auth_routes.auth_blueprint)
    app.add_url_rule("/profile", view_func=profile_routes.profile_update.__wrapped__, methods=["PUT"])
    app.add_url_rule("/contact", view_func=contact_routes.submit_contact, methods=["POST"])
    app.add_url_rule("/topup", view_func=wallet_routes.topup_wallet.__wrapped__, methods=["POST"])
    app.add_url_rule("/plan", view_func=wallet_routes.upgrade_withdrawal_limit.__wrapped__, methods=["POST"])
    app.add_url_rule("/payout", view_func=wallet_routes.save_payout_card.__wrapped__, methods=["POST"])

    @app.before_request
    def identity():
        request.current_user = {"id": 1, "role": "logistics_provider", "full_name": "Test User"}

    return app.test_client()


@pytest.mark.parametrize("body", ['[]', '[1]', '"hello"', '42', 'true', 'null'])
@pytest.mark.parametrize("method,path", [
    ("POST", "/auth/signup"), ("PUT", "/profile"), ("POST", "/contact"),
    ("POST", "/topup"), ("POST", "/plan"), ("POST", "/payout"),
])
def test_wrong_json_shapes_are_client_errors(boundary_client, body, method, path):
    response = boundary_client.open(path, method=method, data=body, content_type="application/json")
    assert response.status_code == 400, response.json


@pytest.mark.parametrize("path,method,payload", [
    ("/auth/signup", "POST", {"name": ["Ali"]}),
    ("/auth/signup", "POST", {"password": 12345678}),
    ("/auth/signup", "POST", {"city": {"name": "Lahore"}}),
    ("/auth/signup", "POST", {"fleet_size": {"count": 2}}),
    ("/auth/signup", "POST", {"pumps_count": []}),
    ("/auth/signup", "POST", {"license_expiry": []}),
    ("/auth/signup", "POST", {"experience_years": {"years": 2}}),
    ("/profile", "PUT", {"last_name": ["Abbas"]}),
    ("/profile", "PUT", {"company_name": 123}),
    ("/contact", "POST", {"message": ["help"]}),
])
def test_nested_wrong_field_types_are_client_errors(boundary_client, path, method, payload):
    assert boundary_client.open(path, method=method, json=payload).status_code == 400


def test_profile_retains_full_name_and_business_fields_after_reload(remediation_env):
    env = remediation_env
    owner = env.user("service_seeker")
    client, _ = env.login(owner)
    payload = {"first_name": "Azhar", "last_name": "Ali Abbas", "phone": "03001234567",
               "company_name": "Review Logistics", "contact_phone": "03111234567",
               "billing_address": "10 Test Road", "address": "10 Test Road"}
    response = client.put("/api/profile", json=payload, headers=env.headers)
    assert response.status_code == 200, response.json
    loaded = client.get("/api/profile").json["user"]
    assert loaded["full_name"] == "Azhar Ali Abbas"
    for field, value in payload.items():
        assert loaded[field] == value
    # Omitted fields survive partial updates, and optional values can be cleared.
    response = client.put("/api/profile", json={"about": "", "contact_phone": None}, headers=env.headers)
    assert response.status_code == 200, response.json
    assert response.json["user"]["company_name"] == payload["company_name"]
    assert response.json["user"]["contact_phone"] == ""


def test_profile_keeps_legacy_full_name_input_and_role_boundaries(remediation_env):
    env = remediation_env
    owner = env.user("everyday_user")
    client, _ = env.login(owner)
    response = client.put("/api/profile", json={"first_name": "Full Legacy Name",
        "company_name": "Not a business", "shop_name": "Not a shop"}, headers=env.headers)
    assert response.status_code == 200, response.json
    assert response.json["user"]["full_name"] == "Full Legacy Name"
    with env.db() as db:
        for table in ("shopkeeper_profiles", "service_seeker_profiles"):
            assert db.execute(f"SELECT id FROM {table} WHERE user_id=%s", (owner["id"],)).fetchone() is None


@pytest.mark.parametrize("revoke", [False, True])
def test_contact_attributes_only_valid_session_owner(remediation_env, revoke):
    env = remediation_env
    owner = env.user()
    client, session_id = env.login(owner)
    if revoke:
        with env.db() as db:
            db.execute("UPDATE user_sessions SET revoked_at=now() WHERE session_id=%s", (session_id,))
    response = client.post("/api/contact", json={"name": "Support User", "email": "user@example.test",
        "subject": "Question", "message": "Please help", "user_id": 99999}, headers=env.headers)
    assert response.status_code == 200, response.json
    with env.db() as db:
        row = db.execute("SELECT user_id FROM contact_messages WHERE id=%s", (response.json["ticket_id"],)).fetchone()
    assert row["user_id"] == (None if revoke else owner["id"])


def test_profile_serializes_distinct_business_contact_details():
    profile = serialize_user({"id": 1, "full_name": "Test User", "contact_phone": "03001112222",
                              "billing_address": "Billing Road"})
    assert profile["contact_phone"] == "03001112222"
    assert profile["billing_address"] == "Billing Road"
