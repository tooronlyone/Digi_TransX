"""Fail-closed Flask secret and cookie configuration."""

import os


LOCAL_ENVIRONMENTS = frozenset({"local", "test"})
PLACEHOLDER_SECRETS = frozenset(
    {
        "change-me-to-a-long-random-string",
        "digitransx-dev-secret-change-me",
        "digitransx-explicit-local-only-secret",
    }
)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class FlaskSecurityConfigurationError(RuntimeError):
    pass


def configure_flask_security(app, environ=None):
    """Configure signing and cookie security from an explicit environment.

    Only explicit ``local`` on a loopback host and ``test`` may use the
    deterministic local-only fallback or non-Secure cookies. Missing/unknown
    environment identification is treated as deployment, not development.
    """

    values = os.environ if environ is None else environ
    environment = str(values.get("DIGITRANSX_ENVIRONMENT") or "").strip().lower()
    explicit_local = environment in LOCAL_ENVIRONMENTS
    if environment == "local":
        host = str(values.get("FLASK_HOST") or "127.0.0.1").strip().lower()
        if host not in LOOPBACK_HOSTS:
            raise FlaskSecurityConfigurationError(
                "Local mode requires an explicit loopback Flask host."
            )

    configured_secret = str(values.get("FLASK_SECRET_KEY") or "")
    placeholder = (
        not configured_secret
        or len(configured_secret) < 32
        or configured_secret in PLACEHOLDER_SECRETS
    )
    if placeholder and not explicit_local:
        raise FlaskSecurityConfigurationError(
            "FLASK_SECRET_KEY must be configured outside explicit local/test mode."
        )
    secret = configured_secret if not placeholder else "digitransx-explicit-local-only-secret"

    app.config.update(
        SECRET_KEY=secret,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not explicit_local,
    )
    return environment
