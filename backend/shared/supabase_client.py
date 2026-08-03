"""Supabase client configuration (Auth + Storage).

Two clients:
- service client (SUPABASE_SERVICE_ROLE_KEY): admin operations — creating
  users, updating passwords, storage uploads. Server-side only; bypasses RLS.
- anon client (SUPABASE_ANON_KEY): used only to verify a user's email/password
  through GoTrue's sign-in endpoint.
"""

import os

from supabase import create_client
from supabase_auth.errors import AuthApiError

from shared.db import BASE_DIR  # noqa: F401  (ensures .env is loaded first)


def _require(name):
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


_service_client = None


def get_service_client():
    global _service_client
    if _service_client is None:
        _service_client = create_client(_require("SUPABASE_URL"), _require("SUPABASE_SERVICE_ROLE_KEY"))
    return _service_client


def supabase_create_user(email, password, metadata=None):
    """Create a Supabase Auth user (email confirmed). Returns the auth user.

    The database trigger on auth.users inserts/links the public.users profile
    row from the metadata automatically.
    """
    response = get_service_client().auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": metadata or {},
        }
    )
    return response.user


class PasswordProviderUnavailable(RuntimeError):
    """Supabase Auth could not make a credential decision."""


def supabase_verify_password(email, password, *, raise_provider_errors=False):
    """Return whether Supabase Auth accepted an email/password pair.

    Strict callers distinguish an ordinary, structured credential rejection
    from failures where the provider could not make a trustworthy decision.
    The default keeps the historical boolean-only contract used elsewhere.
    """
    try:
        client = create_client(_require("SUPABASE_URL"), _require("SUPABASE_ANON_KEY"))
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        ok = bool(response and response.user)
        if not ok and raise_provider_errors:
            raise PasswordProviderUnavailable("Password provider unavailable.")
        try:
            client.auth.sign_out()
        except Exception:
            pass
        return ok
    except AuthApiError as exc:
        # GoTrue exposes credential rejection as a structured API error.  Do
        # not trust a human-readable provider message (or a code detached from
        # its response class): only the documented client-error shape is an
        # ordinary failed credential check.  Every other API outcome is a
        # provider decision failure for strict authentication callers.
        if exc.status in {400, 401} and exc.code == "invalid_credentials":
            return False
        if raise_provider_errors:
            raise PasswordProviderUnavailable("Password provider unavailable.") from None
        return False
    except PasswordProviderUnavailable:
        raise
    except Exception:
        if raise_provider_errors:
            raise PasswordProviderUnavailable("Password provider unavailable.") from None
        return False


def supabase_update_password(auth_user_id, new_password):
    """Set a new password for the given Supabase Auth user id (uuid)."""
    get_service_client().auth.admin.update_user_by_id(str(auth_user_id), {"password": new_password})
