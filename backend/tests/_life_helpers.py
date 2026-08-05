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
    from psycopg2 import sql

    parts = urlsplit(url)
    # Tests may supply a loopback maintenance connection explicitly.  It owns
    # teardown and is independent of any intentionally corrupted child schema.
    admin_url = os.environ.get("TEST_LOCAL_MAINTENANCE_DB_URL", "").strip()
    if not admin_url:
        admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    admin_parts = urlsplit(admin_url)
    if admin_parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("TEST_LOCAL_MAINTENANCE_DB_URL must use a loopback host.")
    if admin_parts.path.lstrip("/").startswith("dtx_life_"):
        pytest.fail("The maintenance connection must not target a disposable child database.")
    dbname = f"dtx_life_{uuid.uuid4().hex[:10]}"
    child_url = urlunsplit((parts.scheme, parts.netloc, "/" + dbname, "", ""))

    try:
        admin = psycopg2.connect(admin_url)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"cannot reach a maintenance database: {exc}")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("create database {} owner {}").format(
                    sql.Identifier(dbname), sql.Identifier(parts.username)
                )
            )
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
            cur.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(dbname)))
        admin.close()
        raise

    def cleanup():
        with admin.cursor() as cur:
            cur.execute(
                "select pg_terminate_backend(pid) from pg_stat_activity where datname = %s",
                (dbname,),
            )
            cur.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(dbname)))
            cur.execute("select 1 from pg_database where datname = %s", (dbname,))
            assert cur.fetchone() is None
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


def schema_before_migration_or_skip(migration_path):
    """Return ``schema.sql`` from the parent of the commit that introduced a
    migration.

    Lifecycle migration tests must exercise the schema that existed before
    that migration. Pointing them at today's ``origin/main`` becomes invalid as
    soon as the migration is merged and its final state is mirrored there.
    """

    import subprocess

    relative = Path(migration_path).resolve().relative_to(REPO_ROOT).as_posix()
    added = subprocess.run(
        [
            "git",
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--",
            relative,
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    commits = added.stdout.decode("utf-8", "replace").splitlines()
    if added.returncode != 0:
        pytest.fail(f"cannot inspect history for {relative}", pytrace=False)
    if commits:
        baseline_ref = f"{commits[0]}^:supabase/schema.sql"
    else:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", relative],
            cwd=str(REPO_ROOT),
            capture_output=True,
        )
        state = status.stdout.decode("utf-8", "replace")[:2]
        if status.returncode != 0 or state not in {"??", "A ", " A"}:
            pytest.fail(
                f"cannot find the introducing commit for {relative}",
                pytrace=False,
            )
        # Before a brand-new migration has its first commit, origin/main is its
        # only possible historical baseline. Once committed, the branch above
        # always selects the introducing commit's parent instead.
        baseline_ref = "origin/main:supabase/schema.sql"
    shown = subprocess.run(
        ["git", "show", baseline_ref],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    if shown.returncode != 0:
        pytest.fail(
            f"pre-migration schema {baseline_ref} is unavailable "
            f"({shown.stderr.decode('utf-8', 'replace').strip()})",
            pytrace=False,
        )
    return shown.stdout.decode("utf-8")
