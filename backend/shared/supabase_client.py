"""Supabase client configuration (Auth + Storage).

Two clients:
- service client (SUPABASE_SERVICE_ROLE_KEY): admin operations — creating
  users, updating passwords, storage uploads. Server-side only; bypasses RLS.
- anon client (SUPABASE_ANON_KEY): used only to verify a user's email/password
  through GoTrue's sign-in endpoint.
"""

import os

from supabase import create_client
from supabase_auth.errors import AuthApiError, AuthRetryableError, AuthWeakPasswordError

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

    def __init__(self, message="Password provider unavailable.", *, status=503,
                 code="password_provider_unavailable"):
        super().__init__(message)
        self.status = status
        self.code = code


class SignupProviderConflict(RuntimeError):
    """Supabase Auth reported a structured account conflict."""


class SignupProviderValidationError(RuntimeError):
    """Supabase Auth rejected signup input using a structured client error."""


class SignupProviderUnavailable(RuntimeError):
    """Supabase Auth could not safely complete a signup operation."""


_SIGNUP_CONFLICT_CODES = frozenset(
    {"email_exists", "identity_already_exists", "user_already_exists"}
)


def supabase_create_signup_user(email, password, metadata=None):
    """Create an Auth identity and classify only structured provider outcomes.

    This intentionally keeps the legacy ``supabase_create_user`` contract for
    administrative callers.  Signup routes need a small, non-enumerating
    outcome vocabulary, so provider messages are never inspected or surfaced.
    """
    try:
        user = supabase_create_user(email, password, metadata)
        if not user or not getattr(user, "id", None):
            raise SignupProviderUnavailable("Signup provider unavailable.")
        return user
    except SignupProviderUnavailable:
        raise
    except AuthWeakPasswordError:
        raise SignupProviderValidationError("Signup input was rejected.") from None
    except AuthApiError as exc:
        code = (getattr(exc, "code", None) or "").lower()
        status = getattr(exc, "status", None)
        if status == 409 or code in _SIGNUP_CONFLICT_CODES:
            raise SignupProviderConflict("Signup account conflict.") from None
        if status in {400, 422}:
            raise SignupProviderValidationError("Signup input was rejected.") from None
        raise SignupProviderUnavailable("Signup provider unavailable.") from None
    except AuthRetryableError:
        raise SignupProviderUnavailable("Signup provider unavailable.") from None
    except Exception:
        raise SignupProviderUnavailable("Signup provider unavailable.") from None


def supabase_signup_identity_is_owned(auth_user_id, request_id):
    """Prove that a provider identity belongs to this server-owned request."""
    try:
        response = get_service_client().auth.admin.get_user_by_id(str(auth_user_id))
        user = getattr(response, "user", None)
        metadata = getattr(user, "user_metadata", None) or {}
        return (
            user is not None
            and str(getattr(user, "id", "")) == str(auth_user_id)
            and metadata.get("signup_request_id") == request_id
        )
    except Exception:
        return False


def supabase_delete_created_signup_user(auth_user_id, request_id):
    """Delete only a signup identity proven to belong to this request."""
    if not supabase_signup_identity_is_owned(auth_user_id, request_id):
        return False
    try:
        get_service_client().auth.admin.delete_user(str(auth_user_id), should_soft_delete=False)
        return True
    except Exception:
        return False


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
