"""Fail-closed Flask secret and cookie environment matrix."""

from flask import Flask
import pytest

from auth.security_config import (
    FlaskSecurityConfigurationError,
    configure_flask_security,
)


@pytest.mark.parametrize("environment", [None, "", "staging", "production", "unknown"])
@pytest.mark.parametrize(
    "secret", [None, "", "too-short", "change-me-to-a-long-random-string"]
)
def test_nonlocal_or_unidentified_runtime_rejects_missing_placeholder_secret(
    environment, secret
):
    values = {}
    if environment is not None:
        values["DIGITRANSX_ENVIRONMENT"] = environment
    if secret is not None:
        values["FLASK_SECRET_KEY"] = secret
    with pytest.raises(FlaskSecurityConfigurationError):
        configure_flask_security(Flask(__name__), values)


@pytest.mark.parametrize("environment", [None, "", "staging", "production", "unknown"])
def test_nonlocal_runtime_uses_secure_cookies_with_configured_secret(environment):
    values = {"FLASK_SECRET_KEY": "isolated-test-strong-signing-key-value"}
    if environment is not None:
        values["DIGITRANSX_ENVIRONMENT"] = environment
    app = Flask(__name__)
    configure_flask_security(app, values)
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


@pytest.mark.parametrize("environment", ["local", "test"])
def test_explicit_local_and_test_modes_are_deterministic(environment):
    app = Flask(__name__)
    configure_flask_security(
        app,
        {"DIGITRANSX_ENVIRONMENT": environment, "FLASK_HOST": "127.0.0.1"},
    )
    assert app.secret_key == "digitransx-explicit-local-only-secret"
    assert app.config["SESSION_COOKIE_SECURE"] is False


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.1", "example.invalid"])
def test_local_mode_rejects_nonloopback_binding(host):
    with pytest.raises(FlaskSecurityConfigurationError):
        configure_flask_security(
            Flask(__name__),
            {"DIGITRANSX_ENVIRONMENT": "local", "FLASK_HOST": host},
        )


def test_deprecated_flask_env_cannot_downgrade_cookie_security():
    app = Flask(__name__)
    configure_flask_security(
        app,
        {
            "FLASK_ENV": "development",
            "FLASK_SECRET_KEY": "isolated-test-strong-signing-key-value",
        },
    )
    assert app.config["SESSION_COOKIE_SECURE"] is True
