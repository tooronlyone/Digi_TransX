"""Focused Phase 1A tests for the contained legacy tracking endpoint."""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from flask import Flask

import auth.helpers as auth_helpers
import tracking.contract as tracking_contract
import tracking.routes as tracking_routes


ROOT = Path(__file__).resolve().parents[2]
CSRF = "tracking-test-csrf"
SECRET_SENTINEL = "do-not-log-this-secret"


class FakeDb:
    def __init__(self):
        self.executions = []
        self.commits = 0

    def execute(self, query, params=()):
        self.executions.append((query, params))
        return self

    def commit(self):
        self.commits += 1


@pytest.fixture
def tracking_env(monkeypatch):
    fake_db = FakeDb()
    open_count = {"value": 0}

    @contextmanager
    def fake_open_db():
        open_count["value"] += 1
        yield fake_db

    monkeypatch.setattr(tracking_routes, "open_db", fake_open_db)
    monkeypatch.setattr(
        auth_helpers,
        "get_user_by_id",
        lambda user_id: {
            "id": 42,
            "email": "server-owned@example.invalid",
            "role": "client",
        }
        if str(user_id) == "42"
        else None,
    )

    app = Flask(__name__)
    app.config.update(SECRET_KEY="tracking-test-secret", TESTING=True)
    app.register_blueprint(tracking_routes.tracking_blueprint)
    client = app.test_client()

    def login():
        with client.session_transaction() as sess:
            sess["user_id"] = 42
            sess["csrf_token"] = CSRF
            sess["last_active_at"] = "original-user-activity"

    return client, fake_db, open_count, login


def valid_payload(page_url="/client/orders"):
    return {
        "action_type": "page_visit",
        "action_name": "page_view",
        "page_url": page_url,
        "metadata": {"navigation_source": "router"},
    }


def post(client, payload, *, csrf=True):
    headers = {"X-CSRF-Token": CSRF} if csrf else {}
    return client.post("/api/track", json=payload, headers=headers)


def test_allowed_page_visit_uses_server_identity_and_safe_metadata(tracking_env):
    client, fake_db, open_count, login = tracking_env
    login()

    response = post(client, valid_payload("/client/orders?token=secret#private"))

    assert response.status_code == 200
    assert open_count["value"] == 1
    assert fake_db.commits == 1
    assert len(fake_db.executions) == 1
    query, params = fake_db.executions[0]
    assert "INSERT INTO user_action_logs" in query
    assert params[0] == "42"
    assert params[1] == ""
    assert params[2] == "client"
    assert params[3:6] == ("page_visit", "page_view", "/client/orders")
    assert json.loads(params[6]) == {
        "navigation_source": "router",
        "page_url": "/client/orders",
    }
    assert CSRF not in params[6]
    assert "server-owned@example.invalid" not in params

    with client.session_transaction() as sess:
        assert sess["last_active_at"] == "original-user-activity"


def test_client_ip_and_user_agent_headers_are_not_stored(tracking_env):
    client, fake_db, _, login = tracking_env
    login()

    response = client.post(
        "/api/track",
        json=valid_payload(),
        headers={
            "X-CSRF-Token": CSRF,
            "X-Forwarded-For": "198.51.100.99",
            "User-Agent": "secret-browser-fingerprint",
        },
    )

    assert response.status_code == 200
    stored_params = fake_db.executions[0][1]
    assert "198.51.100.99" not in stored_params
    assert "secret-browser-fingerprint" not in stored_params
    assert "198.51.100.99" not in stored_params[6]
    assert "secret-browser-fingerprint" not in stored_params[6]


def test_default_login_required_still_refreshes_genuine_user_activity(monkeypatch):
    monkeypatch.setattr(
        auth_helpers,
        "get_user_by_id",
        lambda user_id: {"id": 42, "role": "client"} if str(user_id) == "42" else None,
    )
    app = Flask(__name__)
    app.config.update(SECRET_KEY="login-required-regression-test", TESTING=True)

    @app.get("/protected")
    @auth_helpers.login_required
    def protected():
        return auth_helpers.json_response({"success": True})

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 42
        sess["last_active_at"] = "original-user-activity"

    response = client.get("/protected")

    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess["last_active_at"] != "original-user-activity"


def test_unknown_event_is_rejected_without_opening_database(tracking_env):
    client, fake_db, open_count, login = tracking_env
    login()
    payload = valid_payload()
    payload["action_type"] = "button_click"

    response = post(client, payload)

    assert response.status_code == 400
    assert open_count["value"] == 0
    assert fake_db.executions == []


@pytest.mark.parametrize(
    ("body", "content_type", "expected"),
    [
        ("not-json", "application/json", 400),
        ("[]", "application/json", 400),
        ("null", "application/json", 400),
        ("{}", "text/plain", 415),
    ],
)
def test_malformed_non_object_and_wrong_content_type_are_rejected(
    tracking_env, body, content_type, expected
):
    client, fake_db, open_count, login = tracking_env
    login()

    response = client.post(
        "/api/track",
        data=body,
        content_type=content_type,
        headers={"X-CSRF-Token": CSRF},
    )

    assert response.status_code == expected
    assert open_count["value"] == 0
    assert fake_db.executions == []


def test_oversized_payload_is_rejected_before_database_work(tracking_env):
    client, fake_db, open_count, login = tracking_env
    login()
    payload = valid_payload()
    payload["padding"] = "x" * tracking_contract.MAX_TRACKING_REQUEST_BYTES

    response = post(client, payload)

    assert response.status_code == 413
    assert open_count["value"] == 0
    assert fake_db.executions == []


@pytest.mark.parametrize(
    "body",
    [
        (
            '{"action_type":"page_visit","action_type":"page_visit",'
            '"action_name":"page_view","page_url":"/client/orders",'
            '"metadata":{"navigation_source":"router"}}'
        ),
        (
            '{"action_type":"page_visit","action_name":"page_view",'
            '"page_url":"/client/orders","metadata":{"navigation_source":NaN}}'
        ),
    ],
)
def test_duplicate_keys_and_nonfinite_numbers_are_rejected(tracking_env, body):
    client, fake_db, open_count, login = tracking_env
    login()

    response = client.post(
        "/api/track",
        data=body,
        content_type="application/json",
        headers={"X-CSRF-Token": CSRF},
    )

    assert response.status_code == 400
    assert open_count["value"] == 0
    assert fake_db.executions == []


@pytest.mark.parametrize(
    "field",
    [
        "user_id",
        "user_email",
        "user_role",
        "role",
        "email",
        "phone",
        "ip_address",
        "user_agent",
        "session_id",
        "csrf_token",
    ],
)
def test_client_identity_and_session_fields_cannot_spoof_storage(
    tracking_env, field
):
    client, fake_db, open_count, login = tracking_env
    login()
    payload = valid_payload()
    payload[field] = "attacker-claimed-value"

    response = post(client, payload)

    assert response.status_code == 400
    assert open_count["value"] == 0
    assert fake_db.executions == []


@pytest.mark.parametrize(
    "field",
    [
        "input_data",
        "output_result",
        "request_body",
        "response_body",
        "element_text",
        "button_text",
        "link_text",
        "password",
        "mpin",
        "otp",
        "recovery_code",
        "pan",
        "cvc",
        "payment_token",
        "cookie",
        "authorization",
        "search_text",
        "chat",
        "dispute",
        "review",
    ],
)
def test_sensitive_and_broad_capture_fields_are_rejected_at_any_depth(
    tracking_env, field
):
    client, fake_db, open_count, login = tracking_env
    login()
    payload = valid_payload()
    payload["metadata"] = {
        "navigation_source": "router",
        "nested": {field: SECRET_SENTINEL},
    }

    response = post(client, payload)

    assert response.status_code == 400
    assert open_count["value"] == 0
    assert fake_db.executions == []


def test_unknown_metadata_key_is_rejected(tracking_env):
    client, fake_db, open_count, login = tracking_env
    login()
    payload = valid_payload()
    payload["metadata"]["campaign"] = "unapproved"

    response = post(client, payload)

    assert response.status_code == 400
    assert open_count["value"] == 0
    assert fake_db.executions == []


def test_anonymous_and_missing_csrf_requests_write_nothing(tracking_env):
    client, fake_db, open_count, login = tracking_env

    anonymous = post(client, valid_payload())
    assert anonymous.status_code == 401

    login()
    missing_csrf = post(client, valid_payload(), csrf=False)
    assert missing_csrf.status_code == 403

    assert open_count["value"] == 0
    assert fake_db.executions == []


def test_rejected_secret_is_not_written_or_logged(tracking_env, caplog):
    client, fake_db, open_count, login = tracking_env
    login()
    payload = valid_payload()
    payload["password"] = SECRET_SENTINEL

    with caplog.at_level("DEBUG"):
        response = post(client, payload)

    assert response.status_code == 400
    assert open_count["value"] == 0
    assert fake_db.executions == []
    assert SECRET_SENTINEL not in caplog.text


def test_admin_audit_writer_remains_separate_and_unchanged():
    routes_source = (ROOT / "backend" / "admin" / "routes.py").read_text(
        encoding="utf-8"
    )
    source = routes_source.split("def publish_commission():", 1)[1].split(
        "# ---------------------------------------------------------------------------",
        1,
    )[0]
    assert "INSERT INTO user_action_logs" in source
    assert "admin_platform_settings" in source
    assert "change_summary" in source
    assert "validate_tracking_payload" not in source


def test_single_tracker_endpoint_contract_and_analytics_writer():
    backend_sources = [
        path
        for path in (ROOT / "backend").rglob("*.py")
        if "tests" not in path.parts and "scripts" not in path.parts
    ]
    route_owners = [
        path
        for path in backend_sources
        if '@tracking_blueprint.post("/track")' in path.read_text(encoding="utf-8")
    ]
    contract_owners = [
        path
        for path in backend_sources
        if "TRACKING_EVENT_CONTRACTS =" in path.read_text(encoding="utf-8")
    ]
    analytics_writers = [
        path
        for path in (ROOT / "backend" / "tracking").rglob("*.py")
        if "INSERT INTO user_action_logs" in path.read_text(encoding="utf-8")
    ]

    assert route_owners == [ROOT / "backend" / "tracking" / "routes.py"]
    assert contract_owners == [ROOT / "backend" / "tracking" / "contract.py"]
    assert analytics_writers == [ROOT / "backend" / "tracking" / "routes.py"]
