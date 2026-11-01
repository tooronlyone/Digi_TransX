"""Create local-only auth/session seed data for refresh tracing.

This script is intentionally separate from the Flask app bootstrap because the
app loads the project .env. For this runtime-tracing setup we want explicit,
local-only inputs and hard refusal when the database target is not disposable.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = ROOT / "supabase" / "schema.sql"
DEFAULT_OUTPUT = ROOT / "backend" / "scripts" / "seed_output" / "local_auth_refresh_trace.json"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
DISPOSABLE_DB_PREFIXES = ("dtx_trace_", "dtx_auth_trace_", "dtx_phase1b2c0_", "dtx_local_")
PEPPER_ENV = "DIGITRANSX_MPIN_PEPPER"
ENVIRONMENT_ENV = "DIGITRANSX_ENVIRONMENT"


SUPABASE_STUBS = r"""
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN;
  END IF;
END
$$;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE,
  created_at timestamptz DEFAULT now()
);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql STABLE
AS $$ SELECT NULL::uuid $$;
CREATE SCHEMA IF NOT EXISTS storage;
CREATE TABLE IF NOT EXISTS storage.buckets (
  id text PRIMARY KEY,
  name text,
  public boolean DEFAULT false,
  file_size_limit bigint,
  allowed_mime_types text[],
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS storage.objects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bucket_id text,
  name text,
  owner uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
"""


MINIMAL_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS public.users (
  id bigserial PRIMARY KEY,
  email text UNIQUE NOT NULL,
  password_hash text,
  role text NOT NULL DEFAULT 'transporter',
  legacy_role text,
  full_name text,
  phone text,
  cnic text UNIQUE,
  verified boolean DEFAULT true,
  is_blocked boolean DEFAULT false,
  failed_login_attempts integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.transporter_profiles (
  id bigserial PRIMARY KEY,
  user_id bigint UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
  company_name text,
  fleet_size text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.service_seeker_profiles (
  id bigserial PRIMARY KEY,
  user_id bigint UNIQUE REFERENCES public.users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS public.everyday_users (
  id bigserial PRIMARY KEY,
  user_id bigint UNIQUE REFERENCES public.users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS public.fuel_stations (
  id bigserial PRIMARY KEY,
  user_id bigint UNIQUE REFERENCES public.users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS public.shopkeepers (
  id bigserial PRIMARY KEY,
  user_id bigint UNIQUE REFERENCES public.users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.trusted_devices (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  token_digest bytea UNIQUE NOT NULL,
  previous_token_digest bytea,
  created_at timestamptz DEFAULT now(),
  last_used_at timestamptz DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  rotated_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.user_sessions (
  session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id bigint NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  trusted_device_id bigint REFERENCES public.trusted_devices(id) ON DELETE SET NULL,
  token_digest bytea UNIQUE NOT NULL,
  created_at timestamptz DEFAULT now(),
  authenticated_at timestamptz DEFAULT now(),
  last_genuine_activity_at timestamptz DEFAULT now(),
  inactivity_expires_at timestamptz NOT NULL,
  absolute_expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  revocation_reason text,
  access_locked boolean DEFAULT false,
  access_locked_at timestamptz,
  token_version integer DEFAULT 1,
  token_rotated_at timestamptz,
  access_proof_digest bytea,
  access_proof_expires_at timestamptz,
  password_verified_at timestamptz,
  updated_at timestamptz DEFAULT now()
);

CREATE SEQUENCE IF NOT EXISTS public.mpin_credentials_id_seq;
CREATE TABLE IF NOT EXISTS public.mpin_credentials (
  id bigint PRIMARY KEY DEFAULT nextval('public.mpin_credentials_id_seq'),
  user_id bigint UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  verifier bytea NOT NULL,
  salt bytea NOT NULL,
  kdf_version smallint NOT NULL DEFAULT 1,
  failed_attempts integer NOT NULL DEFAULT 0,
  locked_at timestamptz,
  permanently_locked boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.security_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_name text NOT NULL,
  event_version smallint NOT NULL,
  category text NOT NULL,
  actor_type text NOT NULL,
  actor_id bigint,
  actor_role text,
  subject_user_id bigint,
  shipment_id bigint,
  bid_id bigint,
  document_id bigint,
  payment_id bigint,
  request_id text,
  correlation_id text,
  session_ref text,
  device_ref text,
  source text,
  provider_mode text,
  environment text,
  before_state jsonb,
  after_state jsonb,
  reason_code text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  retention_class text,
  consent_category text,
  idempotency_scope text,
  idempotency_key text,
  fingerprint text,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS security_events_idempotency_idx
  ON public.security_events (idempotency_scope, idempotency_key)
  WHERE idempotency_scope IS NOT NULL AND idempotency_key IS NOT NULL;
"""


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def _db_info(db_url: str) -> tuple[str, str]:
    parsed = urlparse(db_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        _fail("Database URL must use postgresql:// or postgres://.")
    host = parsed.hostname or ""
    db_name = (parsed.path or "").lstrip("/")
    if host not in LOCAL_HOSTS:
        _fail(f"Refusing non-loopback database host {host!r}.")
    if not db_name.startswith(DISPOSABLE_DB_PREFIXES):
        _fail(
            "Refusing database name that does not look disposable. "
            f"Use one of these prefixes: {', '.join(DISPOSABLE_DB_PREFIXES)}."
        )
    root_env_db = os.environ.get("SUPABASE_DB_URL")
    if root_env_db:
        root = urlparse(root_env_db)
        root_host = root.hostname or ""
        root_db_name = (root.path or "").lstrip("/")
        if root_host not in LOCAL_HOSTS:
            _fail(f"Refusing because SUPABASE_DB_URL host is non-loopback: {root_host!r}.")
        if not root_db_name.startswith(DISPOSABLE_DB_PREFIXES):
            _fail(
                "Refusing because SUPABASE_DB_URL database does not look disposable. "
                f"Use one of these prefixes: {', '.join(DISPOSABLE_DB_PREFIXES)}."
            )
        if root_env_db != db_url:
            _fail("Refusing because SUPABASE_DB_URL and the tracing DB URL differ.")
    return host, db_name


def _pepper() -> bytes:
    raw = os.environ.get(PEPPER_ENV)
    if not raw:
        _fail(f"{PEPPER_ENV} is required.")
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as exc:
        _fail(f"{PEPPER_ENV} must be URL-safe base64: {exc}")
    if len(decoded) != 32:
        _fail(f"{PEPPER_ENV} must decode to exactly 32 bytes.")
    return decoded


def _environment() -> str:
    value = os.environ.get(ENVIRONMENT_ENV)
    if value not in {"local", "test"}:
        _fail(f"{ENVIRONMENT_ENV} must be local or test.")
    return value


def _sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _mpin_secret(mpin: str, pepper: bytes) -> tuple[bytes, bytes]:
    salt = secrets.token_bytes(32)
    derived = hashlib.scrypt(
        mpin.encode("ascii") + b"\0" + pepper,
        salt=salt,
        n=1 << 14,
        r=8,
        p=1,
        dklen=32,
    )
    return derived, salt


def _exec_sql(conn: psycopg2.extensions.connection, sql: str) -> None:
    with conn.cursor() as cur:
        cur.execute(sql)


def _reset_database(conn: psycopg2.extensions.connection) -> None:
    _exec_sql(
        conn,
        """
        DROP SCHEMA IF EXISTS public CASCADE;
        DROP SCHEMA IF EXISTS auth CASCADE;
        DROP SCHEMA IF EXISTS storage CASCADE;
        CREATE SCHEMA public;
        """,
    )


def _load_schema(conn: psycopg2.extensions.connection, mode: str) -> None:
    _exec_sql(conn, SUPABASE_STUBS)
    if mode == "full":
        if not SCHEMA_SQL.exists():
            _fail(f"Missing schema file: {SCHEMA_SQL}")
        _exec_sql(conn, SCHEMA_SQL.read_text(encoding="utf-8"))
    elif mode == "minimal":
        _exec_sql(conn, MINIMAL_SCHEMA)
    else:
        _fail("Unknown schema mode.")


def _insert_user(
    conn: psycopg2.extensions.connection,
    *,
    email: str,
    full_name: str,
    has_mpin: bool,
    proof_cookie: bool,
    proof_valid_in_db: bool,
    pepper: bytes,
    mpin: str,
) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    session_raw = secrets.token_urlsafe(32)
    device_raw = secrets.token_urlsafe(32)
    proof_raw = secrets.token_urlsafe(32)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO public.users (email, role, legacy_role, full_name, phone, cnic, is_blocked)
            VALUES (%s, %s, %s, %s, %s, %s, false)
            ON CONFLICT (email) DO UPDATE
              SET full_name = EXCLUDED.full_name,
                  role = EXCLUDED.role,
                  legacy_role = EXCLUDED.legacy_role,
                  is_blocked = false
            RETURNING id
            """,
            (
                email,
                "transporter",
                "logistics_provider",
                full_name,
                "+10000000000",
                f"LOCAL-{hashlib.sha1(email.encode('utf-8')).hexdigest()[:24]}",
            ),
        )
        user_id = int(cur.fetchone()["id"])
        cur.execute(
            """
            INSERT INTO public.transporter_profiles (user_id, company_name, fleet_size)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
              SET company_name = EXCLUDED.company_name,
                  fleet_size = EXCLUDED.fleet_size
            """,
            (user_id, "Local Trace Transport", "3"),
        )
        cur.execute("DELETE FROM public.mpin_credentials WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM public.user_sessions WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM public.trusted_devices WHERE user_id = %s", (user_id,))
        cur.execute(
            """
            INSERT INTO public.trusted_devices
              (user_id, token_digest, expires_at, last_used_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                _sha256(device_raw),
                now + dt.timedelta(days=30),
                now,
            ),
        )
        device_id = int(cur.fetchone()["id"])
        proof_digest = _sha256(proof_raw) if proof_valid_in_db else None
        proof_expires = now + dt.timedelta(hours=8) if proof_valid_in_db else None
        cur.execute(
            """
            INSERT INTO public.user_sessions
              (user_id, trusted_device_id, token_digest, inactivity_expires_at,
               absolute_expires_at, last_genuine_activity_at, access_locked, access_proof_digest,
               access_proof_expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, false, %s, %s)
            RETURNING session_id
            """,
            (
                user_id,
                device_id,
                _sha256(session_raw),
                now + dt.timedelta(days=7),
                now + dt.timedelta(days=30),
                now,
                proof_digest,
                proof_expires,
            ),
        )
        session_id = str(cur.fetchone()["session_id"])
        if has_mpin:
            verifier, salt = _mpin_secret(mpin, pepper)
            cur.execute(
                """
                INSERT INTO public.mpin_credentials (user_id, verifier, salt, kdf_version)
                VALUES (%s, %s, %s, 1)
                """,
                (user_id, verifier, salt),
            )
    cookies = {
        "dtx_device_token": device_raw,
        "dtx_session_token": session_raw,
    }
    if proof_cookie:
        cookies["dtx_access_proof"] = proof_raw
    return {
        "email": email,
        "password": "database-seeded-only",
        "mpin": mpin if has_mpin else None,
        "user_id": user_id,
        "device_id": device_id,
        "session_id": session_id,
        "cookies": cookies,
        "notes": [
            "Cookie values are local disposable test secrets.",
            "Do not paste these into a browser connected to any non-local backend.",
        ],
    }


def _cookie_preview(cookies: dict[str, str]) -> dict[str, str]:
    return {name: f"{value[:8]}...redacted" for name, value in cookies.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=os.environ.get("LOCAL_AUTH_TRACE_DB_URL"))
    parser.add_argument("--schema-mode", choices=["full", "minimal"], default="full")
    parser.add_argument("--reset-schema", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--mpin", default="123456")
    args = parser.parse_args()

    if not args.db_url:
        _fail("Provide --db-url or LOCAL_AUTH_TRACE_DB_URL.")
    host, db_name = _db_info(args.db_url)
    environment = _environment()
    pepper = _pepper()

    conn = psycopg2.connect(args.db_url)
    conn.autocommit = False
    try:
        if args.reset_schema:
            _reset_database(conn)
        _load_schema(conn, args.schema_mode)
        states = {
            "A_valid_session_valid_access_proof_mpin": _insert_user(
                conn,
                email="trace.valid.mpin@local.test",
                full_name="Trace Valid MPIN",
                has_mpin=True,
                proof_cookie=True,
                proof_valid_in_db=True,
                pepper=pepper,
                mpin=args.mpin,
            ),
            "B_valid_session_missing_access_proof_mpin": _insert_user(
                conn,
                email="trace.locked.mpin@local.test",
                full_name="Trace Missing Proof MPIN",
                has_mpin=True,
                proof_cookie=False,
                proof_valid_in_db=True,
                pepper=pepper,
                mpin=args.mpin,
            ),
            "C_valid_session_missing_access_proof_no_mpin": _insert_user(
                conn,
                email="trace.locked.no-mpin@local.test",
                full_name="Trace Missing Proof No MPIN",
                has_mpin=False,
                proof_cookie=False,
                proof_valid_in_db=True,
                pepper=pepper,
                mpin=args.mpin,
            ),
        }
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    output = {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database": {"host": host, "name": db_name, "schema_mode": args.schema_mode},
        "environment": environment,
        "states": states,
    }
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print("Local auth refresh seed data created.")
    print(f"Database: {host}/{db_name} ({args.schema_mode} schema)")
    print(f"Output: {output_path}")
    for key, state in states.items():
        print(f"- {key}: {state['email']} cookies={_cookie_preview(state['cookies'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
