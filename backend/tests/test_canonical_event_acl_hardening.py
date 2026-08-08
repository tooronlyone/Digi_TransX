"""PostgreSQL proof for the forward-only Phase 1B-1 ACL correction."""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import errors, sql
import pytest

from events.catalog import CATALOG
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.test_canonical_event_foundation import (
    _event_counts,
    _expected_catalog_projection,
    _expected_foundation_projection,
    _foundation_metadata,
    _locked_main_schema,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FOUNDATION_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260731230000_canonical_event_foundation.sql"
)
ACL_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260731240000_canonical_event_acl_hardening.sql"
)
ACTIVATION_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260801100000_security_login_event_integration.sql"
)
INTEGRATED_GUARD_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260801110000_canonical_event_integrated_guard.sql"
)
SIGNUP_FAILED_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations" / "20260801120000_add_signup_failed_event.sql"
)
SIGNUP_INTEGRATION_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations" / "20260801130000_security_signup_event_integration.sql"
)
DURABLE_SESSION_MIGRATION = REPO_ROOT / "supabase/migrations/20260801150000_durable_server_session_foundation.sql"
TRUSTED_DEVICE_MIGRATION = REPO_ROOT / "supabase/migrations/20260801160000_trusted_device_hardening.sql"
DEVICE_SESSION_MPIN_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260801140000_device_session_mpin_event_contracts.sql"
)
EXPECTED_DATABASE_PREFIX = "dtx_phase1b2c0_"
EVENT_TABLES = ("security_events", "business_audit_events")
PROJECTION = "canonical_event_catalog_projection"
NARROW_PRIVILEGES = {"SELECT", "INSERT", "DELETE"}


def _local_url():
    url = require_test_db_url()
    if url == os.environ.get("SUPABASE_DB_URL", "").strip():
        pytest.fail("TEST_SUPABASE_DB_URL must not equal SUPABASE_DB_URL.")
    parsed = urlsplit(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("ACL hardening tests require local disposable PostgreSQL.")
    if not parsed.path.lstrip("/").startswith(EXPECTED_DATABASE_PREFIX):
        pytest.fail("TEST_SUPABASE_DB_URL must name the approved local Phase 1B-2C0 runner.")
    return url


def _disposable(*blocks):
    return make_disposable(_local_url(), *blocks)


def _migration_text(path):
    return path.read_text(encoding="utf-8")


def _direct_acl(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT relation.relname, coalesce(grantee.rolname, 'PUBLIC'),
                   privilege.privilege_type
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            CROSS JOIN LATERAL aclexplode(
                coalesce(relation.relacl, acldefault('r', relation.relowner))
            ) AS privilege
            LEFT JOIN pg_roles AS grantee ON grantee.oid = privilege.grantee
            WHERE namespace.nspname='public'
              AND relation.relname IN (
                  'security_events', 'business_audit_events',
                  'canonical_event_catalog_projection'
              )
              AND privilege.grantee <> relation.relowner
            ORDER BY relation.relname, coalesce(grantee.rolname, 'PUBLIC'),
                     privilege.privilege_type
            """
        )
        return cursor.fetchall()


def _service_privileges(conn, table):
    return {
        privilege
        for relation, role, privilege in _direct_acl(conn)
        if relation == table and role == "service_role"
    }


def _supported_table_privileges(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT privilege.privilege_type
            FROM pg_class AS relation
            CROSS JOIN LATERAL aclexplode(
                acldefault('r', relation.relowner)
            ) AS privilege
            WHERE relation.oid = 'public.security_events'::regclass
              AND privilege.grantee = relation.relowner
            ORDER BY privilege.privilege_type
            """
        )
        return {row[0] for row in cursor.fetchall()}


def _non_acl_metadata(conn):
    return {
        key: value
        for key, value in _foundation_metadata(conn).items()
        if len(key) < 2 or key[1] != "privileges"
    }


def _semantic_signature(conn):
    text = _migration_text(DEVICE_SESSION_MPIN_MIGRATION)
    start = text.index("create or replace function pg_temp.canonical_event_semantic_signature()")
    stop = text.index("\ndo $migration$", start)
    with conn.cursor() as cursor:
        cursor.execute(text[start:stop])
        cursor.execute("select pg_temp.canonical_event_semantic_signature()")
        return cursor.fetchone()[0]


def _projection(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_name, event_version, category, ownership_domain,
                   retention_class, lifecycle_status, writable, integrated
            FROM public.canonical_event_catalog_projection
            ORDER BY event_name
            """
        )
        return cursor.fetchall()


def _all_public_counts(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT relation.relname
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace
            WHERE namespace.nspname='public' AND relation.relkind IN ('r','p')
            ORDER BY relation.relname
            """
        )
        tables = [row[0] for row in cursor.fetchall()]
        result = {}
        for table in tables:
            cursor.execute(
                sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))
            )
            result[table] = cursor.fetchone()[0]
        return result


def _apply(conn, migration):
    with conn:
        with conn.cursor() as cursor:
            cursor.execute(migration)


def test_supabase_like_additive_acl_is_narrowed_without_row_or_object_drift():
    broad_defaults = (
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT ALL PRIVILEGES ON TABLES TO service_role"
    )
    url, cleanup = _disposable(
        STUBS,
        broad_defaults,
        _locked_main_schema(),
        _migration_text(FOUNDATION_MIGRATION),
    )
    conn = psycopg2.connect(url)
    try:
        for table in EVENT_TABLES:
            before = _service_privileges(conn, table)
            assert NARROW_PRIVILEGES < before
            assert {"UPDATE", "TRUNCATE", "REFERENCES", "TRIGGER"} <= before
        before_metadata = _non_acl_metadata(conn)
        before_projection = _projection(conn)
        before_rows = _all_public_counts(conn)

        _apply(conn, _migration_text(ACL_MIGRATION))

        assert _semantic_signature(conn) == "772212260b85fd6b5cd4aa35ca9ffdfb"
        assert _non_acl_metadata(conn) == before_metadata
        assert _projection(conn) == before_projection == _expected_foundation_projection()
        assert _all_public_counts(conn) == before_rows
        assert _event_counts(conn) == (0, 0)
        for table in EVENT_TABLES:
            assert _service_privileges(conn, table) == NARROW_PRIVILEGES
        assert _service_privileges(conn, PROJECTION) == set()
    finally:
        conn.close()
        cleanup()


def test_corrected_schema_and_old_plus_new_migrations_converge_and_reapply():
    new_sql = _migration_text(ACL_MIGRATION)
    activation_sql = _migration_text(ACTIVATION_MIGRATION)
    guard_sql = _migration_text(INTEGRATED_GUARD_MIGRATION)
    signup_failed_sql = _migration_text(SIGNUP_FAILED_MIGRATION)
    signup_integration_sql = _migration_text(SIGNUP_INTEGRATION_MIGRATION)
    device_session_mpin_sql = _migration_text(DEVICE_SESSION_MPIN_MIGRATION)
    migrated_url, migrated_cleanup = _disposable(
        STUBS,
        _locked_main_schema(),
        _migration_text(FOUNDATION_MIGRATION),
        new_sql,
        activation_sql,
        guard_sql,
        signup_failed_sql,
        signup_integration_sql,
        device_session_mpin_sql,
        _migration_text(DURABLE_SESSION_MIGRATION),
        _migration_text(TRUSTED_DEVICE_MIGRATION),
    )
    schema_url, schema_cleanup = _disposable(STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    migrated = psycopg2.connect(migrated_url)
    schema = psycopg2.connect(schema_url)
    try:
        expected_metadata = _foundation_metadata(schema)
        expected_projection = _projection(schema)
        assert _foundation_metadata(migrated) == expected_metadata
        assert _projection(migrated) == expected_projection == _expected_catalog_projection()
        assert _semantic_signature(migrated) == _semantic_signature(schema)
        assert _semantic_signature(schema) == "11043982605bef207d3b9a5626bd86d8"
        before = _foundation_metadata(schema), _projection(schema), _all_public_counts(schema)
        _apply(schema, _migration_text(TRUSTED_DEVICE_MIGRATION))
        _apply(schema, _migration_text(TRUSTED_DEVICE_MIGRATION))
        assert (_foundation_metadata(schema), _projection(schema), _all_public_counts(schema)) == before
    finally:
        migrated.close()
        schema.close()
        migrated_cleanup()
        schema_cleanup()


@pytest.fixture(scope="module")
def corrected_database_url():
    url, cleanup = _disposable(
        STUBS,
        SCHEMA_SQL.read_text(encoding="utf-8"),
    )
    try:
        yield url
    finally:
        cleanup()


def _denied(cursor, statement):
    cursor.execute("SAVEPOINT denied_acl_operation")
    with pytest.raises(errors.InsufficientPrivilege):
        cursor.execute(statement)
    cursor.execute("ROLLBACK TO SAVEPOINT denied_acl_operation")


def test_effective_role_matrix_and_rolled_back_probes(corrected_database_url):
    conn = psycopg2.connect(corrected_database_url)
    try:
        with conn.cursor() as cursor:
            assert not [row for row in _direct_acl(conn) if row[1] == "PUBLIC"]
            for role in ("anon", "authenticated"):
                cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                for table in (*EVENT_TABLES, PROJECTION):
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        cursor.execute(
                            "SELECT has_table_privilege(current_user, %s, %s)",
                            (f"public.{table}", privilege),
                        )
                        assert cursor.fetchone()[0] is False
                cursor.execute("RESET ROLE")

            cursor.execute("SET LOCAL ROLE service_role")
            for table in EVENT_TABLES:
                assert _service_privileges(conn, table) == NARROW_PRIVILEGES
                for privilege in _supported_table_privileges(conn) - NARROW_PRIVILEGES:
                    cursor.execute(
                        "SELECT has_table_privilege(current_user, %s, %s)",
                        (f"public.{table}", privilege),
                    )
                    assert cursor.fetchone()[0] is False
                _denied(cursor, f"TRUNCATE public.{table}")
            _denied(cursor, f"SELECT * FROM public.{PROJECTION}")

            cursor.execute(
                """
                INSERT INTO public.security_events (
                    event_name,event_version,category,actor_type,request_id,
                    source,provider_mode,environment,retention_class
                ) VALUES (
                    'security.login.succeeded',1,'security','system',
                    'acl.probe.security','test','none','test','security_12_months'
                ) RETURNING event_id
                """
            )
            security_id = cursor.fetchone()[0]
            cursor.execute("SAVEPOINT invalid_catalog_event")
            with pytest.raises(errors.CheckViolation):
                cursor.execute(
                    """
                    INSERT INTO public.security_events (
                        event_name,event_version,category,actor_type,request_id,
                        source,provider_mode,environment,retention_class
                    ) VALUES (
                        'security.unknown.succeeded',1,'security','system',
                        'acl.probe.invalid','test','none','test','security_12_months'
                    )
                    """
                )
            cursor.execute("ROLLBACK TO SAVEPOINT invalid_catalog_event")
            _denied(
                cursor,
                "UPDATE public.security_events SET request_id='changed' "
                f"WHERE event_id='{security_id}'",
            )
            cursor.execute(
                "DELETE FROM public.security_events WHERE event_id=%s", (security_id,)
            )
            cursor.execute("RESET ROLE")
        conn.rollback()
        assert _event_counts(conn) == (0, 0)

        with conn.cursor() as owner:
            owner.execute(
                """
                INSERT INTO public.security_events (
                    event_name,event_version,category,actor_type,request_id,
                    source,provider_mode,environment,retention_class
                ) VALUES (
                    'security.login.succeeded',1,'security','system',
                    'acl.owner.defence','test','none','test','security_12_months'
                ) RETURNING event_id
                """
            )
            event_id = owner.fetchone()[0]
            owner.execute("SAVEPOINT owner_update")
            with pytest.raises(errors.RaiseException):
                owner.execute(
                    "UPDATE public.security_events SET request_id='changed' "
                    "WHERE event_id=%s",
                    (event_id,),
                )
            owner.execute("ROLLBACK TO SAVEPOINT owner_update")
        conn.rollback()
    finally:
        conn.close()


@pytest.mark.parametrize(
    "mutation",
    [
        "DROP TRIGGER trg_security_events_no_update ON public.security_events",
        "REVOKE DELETE ON public.security_events FROM service_role",
        "GRANT SELECT ON public.security_events TO anon",
        "INSERT INTO public.security_events (event_name,event_version,category,actor_type,"
        "request_id,source,provider_mode,environment,retention_class) VALUES ("
        "'security.login.succeeded',1,'security','system','acl.preserve.row','test',"
        "'none','test','security_12_months')",
    ],
    ids=["partial-foundation", "unexpected-combination", "unexpected-grantee", "nonempty-event"],
)
def test_incompatible_state_aborts_before_acl_mutation_and_preserves_state(mutation):
    url, cleanup = _disposable(STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(mutation)
        before_acl = _direct_acl(conn)
        before_metadata = _foundation_metadata(conn)
        before_counts = _event_counts(conn)
        with conn.cursor() as cursor:
            with pytest.raises(psycopg2.Error) as raised:
                cursor.execute(_migration_text(ACL_MIGRATION))
            assert raised.value.pgcode == "55000"
        conn.rollback()
        assert _direct_acl(conn) == before_acl
        assert _foundation_metadata(conn) == before_metadata
        assert _event_counts(conn) == before_counts
    finally:
        conn.close()
        cleanup()


def test_migration_is_forward_only_and_does_not_mutate_catalog_or_runtime():
    text = _migration_text(ACL_MIGRATION)
    assert FOUNDATION_MIGRATION.name < ACL_MIGRATION.name
    assert "CASCADE" not in text.upper()
    assert "ALTER DEFAULT PRIVILEGES" not in text.upper()
    assert not re.search(r"(?im)^\s*insert\s+into\s+", text)
    assert not re.search(r"(?im)^\s*update\s+", text)
    assert not re.search(r"(?im)^\s*delete\s+from\s+", text)
    assert "REVOKE ALL PRIVILEGES ON TABLE public.security_events FROM service_role" in text
    assert "GRANT SELECT, INSERT, DELETE ON TABLE public.security_events TO service_role" in text
    assert len(CATALOG) == 170
