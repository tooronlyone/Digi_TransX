"""Fail-closed server environment derivation for canonical evidence."""

import os


ALLOWED_ENVIRONMENTS = frozenset({"local", "test", "staging", "production"})


class EnvironmentConfigurationError(RuntimeError):
    pass


def derive_server_environment(environ=None):
    values = os.environ if environ is None else environ
    raw = values.get("DIGITRANSX_ENVIRONMENT") or values.get("FLASK_ENV")
    value = str(raw or "").strip().lower()
    if value not in ALLOWED_ENVIRONMENTS:
        raise EnvironmentConfigurationError(
            "DIGITRANSX_ENVIRONMENT must explicitly identify local, test, staging, or production."
        )
    return value
