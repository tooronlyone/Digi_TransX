"""Shared plumbing for the one-time-lifecycle PostgreSQL integration tests.

These helpers stand up a DISPOSABLE database on the server named by
TEST_SUPABASE_DB_URL, load a given set of SQL blocks into it (the canonical
supabase/schema.sql for constraint-behaviour tests, or the origin/main
pre-lifecycle schema plus the real migration for migration-smoke tests), and
drop it again afterwards. There is deliberately no fallback to SUPABASE_DB_URL
and no SQLite/in-memory substitute: the tests must exercise real PostgreSQL
constraints and triggers, never a dialect stand-in.

The file name starts with an underscore so pytest never collects it as a test
module; it only exposes constants and helper functions.
"""

import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_ROOT / "supabase" / "schema.sql"
MIGRATION_SQL = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260723120000_one_time_trip_completion_lifecycle.sql"
)

# Minimal Supabase stubs so schema.sql / the origin-main schema load on a plain
# PostgreSQL server (roles, the auth + storage schemas and auth.uid()).
STUBS = """
create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;
do $r$ begin
  if not exists (select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role nologin; end if;
end $r$;
create schema if not exists auth;
create table if not exists auth.users (
    id uuid primary key default gen_random_uuid(), email text,
    raw_user_meta_data jsonb not null default '{}'::jsonb);
create or replace function auth.uid() returns uuid language sql stable as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
create schema if not exists storage;
create table if not exists storage.buckets (id text primary key, name text, public boolean default false);
create table if not exists storage.objects (
    id uuid primary key default gen_random_uuid(), bucket_id text, name text);
"""


def require_test_db_url():
    """The dedicated test database URL, or skip the test with a clear reason."""
    url = os.environ.get("TEST_SUPABASE_DB_URL", "").strip()
    if not url:
        pytest.skip(
            "TEST_SUPABASE_DB_URL is not set; the lifecycle-integrity integration "
            "tests need a dedicated PostgreSQL server and never fall back to "
            "SUPABASE_DB_URL."
        )
    if url == os.environ.get("SUPABASE_DB_URL", "").strip():
        pytest.skip("TEST_SUPABASE_DB_URL must not equal SUPABASE_DB_URL.")
    return url


def make_disposable(url, *sql_blocks):
    """Create a throwaway database on ``url``'s server, run each SQL block in it
    (in order, one committed transaction per block), and return
    ``(child_url, cleanup)``. ``cleanup()`` drops the database. Skips (never
    fails) when the test role cannot CREATE DATABASE, mirroring the other
    migration tests.
    """
    import psycopg2

    parts = urlsplit(url)
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    dbname = f"dtx_life_{uuid.uuid4().hex[:10]}"
    child_url = urlunsplit((parts.scheme, parts.netloc, "/" + dbname, "", ""))

    try:
        admin = psycopg2.connect(admin_url)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"cannot reach a maintenance database: {exc}")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(f'create database "{dbname}"')
    except psycopg2.Error as exc:
        admin.close()
        pytest.skip(f"test role cannot CREATE DATABASE (managed environment?): {exc}")

    try:
        conn = psycopg2.connect(child_url)
        with conn:
            with conn.cursor() as cur:
                for block in sql_blocks:
                    cur.execute(block)
        conn.close()
    except Exception:
        with admin.cursor() as cur:
            cur.execute(
                "select pg_terminate_backend(pid) from pg_stat_activity where datname = %s",
                (dbname,),
            )
            cur.execute(f'drop database if exists "{dbname}"')
        admin.close()
        raise

    def cleanup():
        with admin.cursor() as cur:
            cur.execute(
                "select pg_terminate_backend(pid) from pg_stat_activity where datname = %s",
                (dbname,),
            )
            cur.execute(f'drop database if exists "{dbname}"')
        admin.close()

    return child_url, cleanup


def run_sql(conn, sql):
    """Execute ``sql`` on ``conn`` and commit."""
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def origin_main_schema_or_skip():
    """The pre-lifecycle canonical schema (git show origin/main:supabase/schema.sql),
    or skip when git / the ref is unavailable. Faithful 'origin/main database'
    baseline for the migration smoke tests."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "show", "origin/main:supabase/schema.sql"],
            cwd=str(REPO_ROOT), capture_output=True,
        )
    except Exception as exc:  # pragma: no cover - git absent
        pytest.skip(f"git is unavailable for the origin/main baseline: {exc}")
    if proc.returncode != 0:
        pytest.skip(
            "origin/main:supabase/schema.sql is unavailable "
            f"({proc.stderr.decode('utf-8', 'replace').strip()})"
        )
    return proc.stdout.decode("utf-8")
