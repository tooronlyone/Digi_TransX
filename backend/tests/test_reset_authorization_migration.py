"""Forward-only reset-authorization migration convergence and corruption gates."""

from pathlib import Path
import subprocess

import psycopg2
import pytest

from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
MPIN_MIGRATION = MIGRATIONS / "20260801180000_secure_mpin_access_lock.sql"
CLAIM_MIGRATION = MIGRATIONS / "20260801190000_reset_authorization_claims.sql"


def _metadata(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            select
              (select array_agg(column_name||':'||data_type||':'||is_nullable order by ordinal_position)
                 from information_schema.columns
                where table_schema='public' and table_name='reset_tokens'),
              (select array_agg(conname||':'||contype::text order by conname)
                 from pg_constraint where conrelid='public.reset_tokens'::regclass),
              (select array_agg(indexname order by indexname)
                 from pg_indexes where schemaname='public' and tablename='reset_tokens'),
              (select array_agg(policyname order by policyname)
                 from pg_policies where schemaname='public' and tablename='reset_tokens'),
              (select array_agg(grantee||':'||privilege_type order by grantee,privilege_type)
                 from information_schema.role_table_grants
                where table_schema='public' and table_name='reset_tokens'
                  and grantee in ('PUBLIC','anon','authenticated','service_role'))
            """
        )
        return cursor.fetchone()


def test_reset_claim_migration_converges_reapplies_and_invalidates_legacy():
    base = require_test_db_url()
    main_schema = subprocess.check_output(
        ["git", "show", "origin/main:supabase/schema.sql"], cwd=ROOT, text=True
    )
    mpin_sql = MPIN_MIGRATION.read_text(encoding="utf-8")
    claim_sql = CLAIM_MIGRATION.read_text(encoding="utf-8")
    assert "cascade" not in claim_sql.lower()
    sequential_url, sequential_cleanup = make_disposable(
        base, STUBS, main_schema, mpin_sql
    )
    fresh_url, fresh_cleanup = make_disposable(
        base, STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    try:
        with psycopg2.connect(sequential_url) as sequential:
            with sequential.cursor() as cursor:
                cursor.execute(
                    "insert into public.users(email,cnic) values"
                    "('legacy-reset@example.invalid','8000000000000') returning id"
                )
                user_id = cursor.fetchone()[0]
                cursor.execute(
                    "insert into public.reset_tokens(user_id,purpose,token_hash,expires_at_iso,used) "
                    "values(%s,'password_reset','legacy-salted-verifier','2099-01-01T00:00:00',0)",
                    (user_id,),
                )
                cursor.execute(claim_sql)
                cursor.execute(claim_sql)
                cursor.execute(
                    "select used,claim_state,claim_digest,claimed_at,completed_at "
                    "from public.reset_tokens"
                )
                assert cursor.fetchone() == (1, "invalidated", None, None, None)
            sequential.commit()
            sequential_meta = _metadata(sequential)

        with psycopg2.connect(fresh_url) as fresh:
            with fresh.cursor() as cursor:
                cursor.execute(claim_sql)
                cursor.execute(claim_sql)
            fresh.commit()
            assert _metadata(fresh) == sequential_meta
    finally:
        sequential_cleanup()
        fresh_cleanup()


def test_reset_claim_migration_aborts_partial_and_corrupt_states_without_repair():
    base = require_test_db_url()
    main_schema = subprocess.check_output(
        ["git", "show", "origin/main:supabase/schema.sql"], cwd=ROOT, text=True
    )
    partial_url, partial_cleanup = make_disposable(
        base,
        STUBS,
        main_schema,
        MPIN_MIGRATION.read_text(encoding="utf-8"),
    )
    corrupt_url, corrupt_cleanup = make_disposable(
        base, STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    migration = CLAIM_MIGRATION.read_text(encoding="utf-8")
    try:
        with psycopg2.connect(partial_url) as partial:
            with partial.cursor() as cursor:
                cursor.execute("alter table public.reset_tokens add column claim_state text")
            partial.commit()
            with pytest.raises(psycopg2.Error):
                with partial.cursor() as cursor:
                    cursor.execute(migration)
            partial.rollback()
            with partial.cursor() as cursor:
                cursor.execute(
                    "select count(*) from information_schema.columns "
                    "where table_schema='public' and table_name='reset_tokens' "
                    "and column_name in ('claim_state','claim_digest','claimed_at','completed_at')"
                )
                assert cursor.fetchone()[0] == 1

        with psycopg2.connect(corrupt_url) as corrupt:
            with corrupt.cursor() as cursor:
                cursor.execute("alter table public.reset_tokens add column corrupt text")
            corrupt.commit()
            with pytest.raises(psycopg2.Error):
                with corrupt.cursor() as cursor:
                    cursor.execute(migration)
            corrupt.rollback()
            with corrupt.cursor() as cursor:
                cursor.execute(
                    "select count(*) from information_schema.columns "
                    "where table_schema='public' and table_name='reset_tokens' "
                    "and column_name='corrupt'"
                )
                assert cursor.fetchone()[0] == 1
    finally:
        partial_cleanup()
        corrupt_cleanup()


def test_migrations_through_180000_remain_byte_identical_to_feature_head():
    paths = sorted(MIGRATIONS.glob("*.sql"))
    immutable = [path for path in paths if path.name <= MPIN_MIGRATION.name]
    for path in immutable:
        subprocess.check_call(
            [
                "git",
                "diff",
                "--quiet",
                "HEAD",
                "--",
                path.relative_to(ROOT).as_posix(),
            ],
            cwd=ROOT,
        )
