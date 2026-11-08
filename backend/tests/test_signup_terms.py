import json

import pytest
from flask import Flask

from auth.helpers import validate_signup_payload
from auth.signup_terms import (
    ROLE_TERMS, SIGNUP_TERMS_VERSION, record_signup_terms, signup_terms_document,
)


def payload(**changes):
    data = {
        "name": "Agreement Test", "email": "agreement@example.invalid",
        "phone": "03001234567", "cnic": "3520212345678", "password": "test-password",
        "role": "service_seeker", "city": "Lahore",
        "signup_terms_accepted": True, "signup_terms_version": SIGNUP_TERMS_VERSION,
        "signup_terms_role": "service_seeker",
    }
    return {**data, **changes}


@pytest.mark.parametrize("changes", [
    {"signup_terms_accepted": False}, {"signup_terms_accepted": "true"},
    {"signup_terms_accepted": None}, {"signup_terms_version": "outdated"},
    {"signup_terms_role": "driver"},
])
def test_signup_requires_explicit_current_role_agreement(changes):
    assert "signup_terms" in validate_signup_payload(payload(**changes))


def test_valid_agreement_passes_and_exact_document_is_recorded():
    assert validate_signup_payload(payload()) == {}
    statements = []

    class Db:
        def execute(self, sql, params):
            statements.append((sql, params))

    record_signup_terms(Db(), 123, "service_seeker")
    sql, params = statements[0]
    assert "signup_terms_acceptances" in sql
    assert params[:3] == (123, SIGNUP_TERMS_VERSION, "service_seeker")
    assert json.loads(params[3]) == signup_terms_document("service_seeker")


@pytest.mark.parametrize("role", ROLE_TERMS)
def test_terms_endpoint_exposes_role_document_with_insurance_and_legal_scope(role):
    from auth.routes import auth_blueprint
    app = Flask(__name__)
    app.register_blueprint(auth_blueprint)
    response = app.test_client().get(f"/auth/signup-terms?role={role}")
    assert response.status_code == 200
    document = response.get_json()
    assert document["role"] == role
    assert document["version"] == SIGNUP_TERMS_VERSION
    assert "mandatory legal obligations" in document["sections"][-1]["text"]
    assert "no-store" in response.headers["Cache-Control"]


def test_signup_rejects_missing_agreement_before_provider_creation(monkeypatch):
    import auth.routes as routes
    monkeypatch.setattr(routes, "_record_signup_started", lambda *_: None)
    monkeypatch.setattr(routes, "_record_signup_failed", lambda *_: True)
    monkeypatch.setattr(routes, "supabase_create_signup_user", lambda *_: pytest.fail("Provider called without consent"))
    app = Flask(__name__)
    app.register_blueprint(routes.auth_blueprint)
    response = app.test_client().post("/auth/signup", json=payload(signup_terms_accepted=False))
    assert response.status_code == 400
    assert response.json["field"] == "signup_terms"


@pytest.mark.parametrize("role", ["fuel_station_manager", "shopkeeper"])
def test_v2_roles_are_unavailable_in_v1_signup(role):
    from auth.routes import auth_blueprint
    app = Flask(__name__)
    app.register_blueprint(auth_blueprint)
    assert "role" in validate_signup_payload(payload(role=role, signup_terms_role=role))
    assert app.test_client().get(f"/auth/signup-terms?role={role}").status_code == 400
