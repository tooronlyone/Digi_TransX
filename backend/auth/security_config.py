"""Fail-closed Flask secret and cookie configuration."""

import os
from pathlib import Path

from auth.mpin_service import MpinConfigurationError, validate_configuration as validate_mpin_configuration
from shared.db import (
    DB_ROLE_API,
    DB_ROLE_AUDITOR,
    DB_ROLE_SCHEDULER,
    resolve_database_dsn,
)
from shared.supabase_client import validate_supabase_url


LOCAL_ENVIRONMENTS = frozenset({"local", "test"})
PLACEHOLDER_SECRETS = frozenset(
    {
        "change-me-to-a-long-random-string",
        "digitransx-dev-secret-change-me",
        "digitransx-explicit-local-only-secret",
    }
)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_TRUE_FLAGS = frozenset({"1", "true", "yes", "on"})


class FlaskSecurityConfigurationError(RuntimeError):
    pass


def _is_truthy(value):
    return str(value or "").strip().lower() in _TRUE_FLAGS


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
        DEBUG=explicit_local and _is_truthy(values.get("FLASK_DEBUG")),
        SECRET_KEY=secret,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not explicit_local,
    )
    return environment


def validate_production_security_config(app=None, environ=None):
    """Fail closed when staging/production runtime settings violate V1 policy."""

    values = os.environ if environ is None else environ
    environment = str(values.get("DIGITRANSX_ENVIRONMENT") or "").strip().lower()
    raw_proxy_count = values.get("DIGITRANSX_TRUST_PROXY_COUNT")
    if raw_proxy_count not in (None, ""):
        try:
            proxy_count = int(str(raw_proxy_count).strip())
        except (TypeError, ValueError) as exc:
            raise FlaskSecurityConfigurationError(
                "DIGITRANSX_TRUST_PROXY_COUNT must be a non-negative integer."
            ) from exc
        if proxy_count < 0:
            raise FlaskSecurityConfigurationError(
                "DIGITRANSX_TRUST_PROXY_COUNT must be a non-negative integer."
            )

    if environment in LOCAL_ENVIRONMENTS:
        return environment

    if _is_truthy(values.get("FLASK_DEBUG")):
        raise FlaskSecurityConfigurationError(
            "FLASK_DEBUG must be disabled outside explicit local/test mode."
        )
    if _is_truthy(values.get("DIGITRANSX_ALLOW_DUMMY_PAYMENTS")):
        raise FlaskSecurityConfigurationError(
            "DIGITRANSX_ALLOW_DUMMY_PAYMENTS must be disabled outside explicit local/test mode."
        )

    configured_secret = str(values.get("FLASK_SECRET_KEY") or "")
    if (
        not configured_secret
        or len(configured_secret) < 32
        or configured_secret in PLACEHOLDER_SECRETS
    ):
        raise FlaskSecurityConfigurationError(
            "FLASK_SECRET_KEY must be strong and non-placeholder outside explicit local/test mode."
        )

    if app is not None:
        if app.config.get("DEBUG") or _is_truthy(values.get("FLASK_DEBUG")):
            raise FlaskSecurityConfigurationError(
                "Flask debug mode must remain disabled outside explicit local/test mode."
            )
        if not app.config.get("SESSION_COOKIE_SECURE"):
            raise FlaskSecurityConfigurationError(
                "SESSION_COOKIE_SECURE must be enabled outside explicit local/test mode."
            )
        if not app.config.get("SESSION_COOKIE_HTTPONLY"):
            raise FlaskSecurityConfigurationError(
                "SESSION_COOKIE_HTTPONLY must remain enabled."
            )
        if app.config.get("SESSION_COOKIE_SAMESITE") not in {"Lax", "Strict"}:
            raise FlaskSecurityConfigurationError(
                "SESSION_COOKIE_SAMESITE must be Lax or Strict."
            )

    try:
        validate_mpin_configuration(values)
    except MpinConfigurationError as exc:
        raise FlaskSecurityConfigurationError(
            "DIGITRANSX_MPIN_PEPPER must be a valid URL-safe base64 32-byte key outside explicit local/test mode."
        ) from exc

    otp_secret = str(values.get("DIGITRANSX_DELIVERY_OTP_SECRET") or "")
    if (
        not otp_secret
        or len(otp_secret) < 32
        or otp_secret in PLACEHOLDER_SECRETS
    ):
        raise FlaskSecurityConfigurationError(
            "DIGITRANSX_DELIVERY_OTP_SECRET must be >= 32 characters outside explicit local/test mode."
        )

    try:
        resolve_database_dsn(DB_ROLE_API, environ=values)
        if values.get("DIGITRANSX_SCHEDULER_DB_URL") or _is_truthy(values.get("DIGITRANSX_ENABLE_SCHEDULER")):
            resolve_database_dsn(DB_ROLE_SCHEDULER, environ=values)
        if values.get("DIGITRANSX_AUDITOR_DB_URL"):
            resolve_database_dsn(DB_ROLE_AUDITOR, environ=values)
    except RuntimeError as exc:
        raise FlaskSecurityConfigurationError(str(exc)) from exc

    cors_origins = str(values.get("DIGITRANSX_CORS_ORIGINS") or "").strip()
    if cors_origins == "*":
        raise FlaskSecurityConfigurationError(
            "Wildcard CORS origins are forbidden outside explicit local/test mode."
        )

    root_cert = str(values.get("DIGITRANSX_DB_SSLROOTCERT") or "").strip()
    if root_cert and root_cert.lower() not in {"system", "certifi"} and not Path(root_cert).is_file():
        raise FlaskSecurityConfigurationError(
            "DIGITRANSX_DB_SSLROOTCERT references a certificate file that does not exist."
        )

    supabase_url = str(values.get("SUPABASE_URL") or "").strip()
    if not supabase_url:
        raise FlaskSecurityConfigurationError(
            "SUPABASE_URL must be configured outside explicit local/test mode."
        )
    try:
        validate_supabase_url(supabase_url)
    except RuntimeError as exc:
        raise FlaskSecurityConfigurationError(str(exc)) from exc

    return environment
