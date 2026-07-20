"""Supabase client configuration (Auth + Storage).

Two clients:
- service client (SUPABASE_SERVICE_ROLE_KEY): admin operations — creating
  users, updating passwords, storage uploads. Server-side only; bypasses RLS.
- anon client (SUPABASE_ANON_KEY): used only to verify a user's email/password
  through GoTrue's sign-in endpoint.
"""

import os

from supabase import create_client

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


def supabase_verify_password(email, password):
    """Return True if the email/password pair is valid in Supabase Auth."""
    try:
        client = create_client(_require("SUPABASE_URL"), _require("SUPABASE_ANON_KEY"))
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        ok = bool(response and response.user)
        try:
            client.auth.sign_out()
        except Exception:
            pass
        return ok
    except Exception:
        return False


def supabase_update_password(auth_user_id, new_password):
    """Set a new password for the given Supabase Auth user id (uuid)."""
    get_service_client().auth.admin.update_user_by_id(str(auth_user_id), {"password": new_password})
