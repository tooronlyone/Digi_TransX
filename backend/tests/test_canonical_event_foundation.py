"""PostgreSQL and contract proof for the Phase 1B-1 event foundation."""

import json
import os
from pathlib import Path
import subprocess
import threading
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import errors, sql
from psycopg2.extras import RealDictCursor
import pytest

from events.catalog import (
    BUSINESS_AUDIT,
    CATALOG,
    DEFERRED,
    DEFERRED_EVENT_NAMES,
    NonWritableEventName,
    OPERATIONS,
    PLANNED,
    PLANNED_EVENT_NAMES,
    SECURITY,
    UnknownEventName,
    get_writable_event_definition,
)
from events.contract import (
    EventContext,
    EventContractError,
    EventData,
    decode_untrusted_event_json,
    validate_envelope_inputs,
    validate_untrusted_event_payload,
)
from events.environment import EnvironmentConfigurationError, derive_server_environment
from events.writer import (
    EventIdempotencyConflict,
    write_business_audit_event,
    write_security_event,
)
from tests._life_helpers import (
    SCHEMA_SQL,
    STUBS,
    make_disposable,
    require_test_db_url,
    schema_before_migration_or_skip,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCKED_MAIN_SHA = "6f2c9211876959ad8df2ffad19ff4714ae9d284e"
BASELINE_MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260731220000_schema_trigger_rls_baseline.sql"
)
EVENT_MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260731230000_canonical_event_foundation.sql"
)
EXPECTED_BASE_DATABASE = "dtx_schema_trigger_rls_baseline"
EVENT_TABLES = ("security_events", "business_audit_events")


def _local_test_url():
    url = require_test_db_url()
    if url == os.environ.get("SUPABASE_DB_URL", "").strip():
        pytest.fail("TEST_SUPABASE_DB_URL must not equal SUPABASE_DB_URL.")
    parsed = urlsplit(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Canonical event tests require local disposable PostgreSQL.")
    if parsed.path.lstrip("/") != EXPECTED_BASE_DATABASE:
        pytest.fail("TEST_SUPABASE_DB_URL must name the exact approved local database.")
    return url


def _disposable(*blocks):
    return make_disposable(_local_test_url(), *blocks)


def _locked_main_schema():
    shown = subprocess.run(
        ["git", "show", f"{LOCKED_MAIN_SHA}:supabase/schema.sql"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if shown.returncode:
        pytest.fail(shown.stderr.decode("utf-8", "replace"), pytrace=False)
    return shown.stdout.decode("utf-8")


def _foundation_metadata(conn):
    result = {}
    with conn.cursor() as cursor:
        for table in EVENT_TABLES:
            cursor.execute(
                """
                SELECT column_name, data_type, udt_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            result[(table, "columns")] = cursor.fetchall()
            cursor.execute(
                """
                SELECT constraint_name, constraint_type,
                       pg_get_constraintdef(con.oid)
                FROM information_schema.table_constraints AS catalog
                JOIN pg_constraint AS con
                  ON con.conname = catalog.constraint_name
                JOIN pg_class AS relation ON relation.oid = con.conrelid
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE catalog.table_schema = 'public'
                  AND catalog.table_name = %s
                  AND namespace.nspname = 'public'
                  AND relation.relname = %s
                ORDER BY constraint_name
                """,
                (table, table),
            )
            result[(table, "constraints")] = cursor.fetchall()
            cursor.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = %s
                ORDER BY indexname
                """,
                (table,),
            )
            result[(table, "indexes")] = cursor.fetchall()
            cursor.execute(
                """
                SELECT trigger.tgname, trigger.tgtype, function.proname
                FROM pg_trigger AS trigger
                JOIN pg_class AS relation ON relation.oid = trigger.tgrelid
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                JOIN pg_proc AS function ON function.oid = trigger.tgfoid
                WHERE namespace.nspname = 'public'
                  AND relation.relname = %s
                  AND NOT trigger.tgisinternal
                ORDER BY trigger.tgname
                """,
                (table,),
            )
            result[(table, "triggers")] = cursor.fetchall()
            cursor.execute(
                """
                SELECT policyname, permissive, roles, cmd, qual, with_check
                FROM pg_policies
                WHERE schemaname = 'public' AND tablename = %s
                ORDER BY policyname
                """,
                (table,),
            )
            result[(table, "policies")] = cursor.fetchall()
        cursor.execute(
            """
            SELECT p.proname, pg_get_function_identity_arguments(p.oid),
                   p.provolatile, p.prosecdef, p.proconfig, pg_get_functiondef(p.oid)
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND p.proname IN ('is_bounded_event_json', 'prevent_canonical_event_update')
            ORDER BY p.proname
            """
        )
        result[("functions",)] = cursor.fetchall()
    return result


def _event_counts(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT (SELECT count(*) FROM public.security_events), "
            "(SELECT count(*) FROM public.business_audit_events)"
        )
        return cursor.fetchone()


def _context(**changes):
    values = {
        "request_id": "request.phase1b.1",
        "source": "domain_service",
        "actor_type": "user",
        "actor_id": 7,
        "actor_role": "customer",
        "subject_user_id": 7,
        "correlation_id": "correlation.phase1b.1",
        "session_ref": "session_" + "a" * 32,
        "device_ref": "device_" + "b" * 32,
        "provider_mode": "none",
    }
    values.update(changes)
    return EventContext(**values)


def _data(**changes):
    values = {
        "related_entities": {"order_id": 11, "trip_id": 12},
        "before_state": {"status": "held"},
        "after_state": {"status": "released"},
        "reason_code": "policy_decision",
        "metadata": {"result_code": "ok", "attempt_number": 1},
    }
    values.update(changes)
    return EventData(**values)


def test_catalog_is_single_locked_owner_and_deferred_names_are_not_writable():
    assert len(CATALOG) == 157
    assert len(PLANNED_EVENT_NAMES) == 149
    assert len(DEFERRED_EVENT_NAMES) == 8
    assert len(set(CATALOG)) == len(CATALOG)
    assert all(CATALOG[name].lifecycle_status == PLANNED for name in PLANNED_EVENT_NAMES)
    assert all(not CATALOG[name].integrated for name in CATALOG)
    assert all(CATALOG[name].lifecycle_status == DEFERRED for name in DEFERRED_EVENT_NAMES)
    assert all(not CATALOG[name].writable for name in DEFERRED_EVENT_NAMES)
    assert all(
        not definition.writable
        for definition in CATALOG.values()
        if definition.category == OPERATIONS
    )
    with pytest.raises(NonWritableEventName):
        get_writable_event_definition(DEFERRED_EVENT_NAMES[0])
    with pytest.raises(UnknownEventName):
        get_writable_event_definition("admin.withdrawal.approved")


def test_envelope_is_strict_and_server_owned(monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    security, security_envelope = validate_envelope_inputs(
        "security.login.succeeded", _context(source="server_route"), EventData()
    )
    business, business_envelope = validate_envelope_inputs(
        "one_time.payment.released", _context(), _data()
    )
    assert security.category == SECURITY
    assert business.category == BUSINESS_AUDIT
    assert security_envelope["event_version"] == business_envelope["event_version"] == 1
    assert "environment" not in security_envelope
    assert derive_server_environment() == "test"
    with pytest.raises(EnvironmentConfigurationError):
        derive_server_environment({})
    with pytest.raises(NonWritableEventName):
        get_writable_event_definition("one_time.payment.released", SECURITY)


@pytest.mark.parametrize(
    "bad_data",
    [
        EventData(metadata={"password": "not-a-real-secret"}),
        EventData(metadata={"result_code": "x" * 513}),
        EventData(metadata={"result_code": {"nested": "value"}}),
        EventData(metadata={"unknown": "value"}),
        EventData(before_state={"amount_minor": -1}),
        EventData(related_entities={"order_id": 0}),
    ],
)
def test_sensitive_oversized_nested_and_malformed_data_is_rejected(bad_data):
    with pytest.raises(EventContractError):
        validate_envelope_inputs("one_time.payment.released", _context(), bad_data)


def test_untrusted_json_rejects_duplicates_nonfinite_and_server_fields():
    with pytest.raises(EventContractError):
        decode_untrusted_event_json(b'{"metadata":{},"metadata":{}}')
    with pytest.raises(EventContractError):
        decode_untrusted_event_json(b'{"value":NaN}')
    with pytest.raises(EventContractError):
        decode_untrusted_event_json(b"[1,2,3]")
    payload = {
        "event_name": "one_time.payment.released",
        "related_entities": {},
        "before_state": {},
        "after_state": {},
        "reason_code": None,
        "metadata": {},
        "actor_id": 99,
    }
    with pytest.raises(EventContractError):
        validate_untrusted_event_payload(payload)
    payload.pop("actor_id")
    payload["event_version"] = 1
    with pytest.raises(EventContractError):
        validate_untrusted_event_payload(payload)


def test_writer_uses_only_caller_cursor_and_never_controls_transaction(monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")

    class CursorOnly:
        def __init__(self):
            self.calls = []
            self.row = {
                "event_id": "00000000-0000-0000-0000-000000000001",
                "fingerprint": None,
            }

        def execute(self, statement, values):
            self.calls.append((statement, values))
            return None

        def fetchone(self):
            return self.row

    cursor = CursorOnly()
    result = write_security_event(
        cursor, "security.login.succeeded", _context(source="server_route"), EventData()
    )
    assert not result.replayed
    assert len(cursor.calls) == 1
    assert cursor.calls[0][0].startswith("INSERT INTO public.security_events")
    assert not hasattr(cursor, "commit") and not hasattr(cursor, "rollback")

    class Result:
        def fetchone(self):
            return {
                "event_id": "00000000-0000-0000-0000-000000000002",
                "fingerprint": None,
            }

    class ProductionDbStyle:
        def execute(self, statement, values):
            assert statement.startswith("INSERT INTO public.business_audit_events")
            return Result()

    production_style = write_business_audit_event(
        ProductionDbStyle(), "one_time.payment.released", _context(), EventData()
    )
    assert not production_style.replayed
    writer_source = (REPO_ROOT / "backend" / "events" / "writer.py").read_text(
        encoding="utf-8"
    )
    assert "import psycopg2" not in writer_source
    assert ".connect(" not in writer_source
    assert ".commit(" not in writer_source
    assert ".rollback(" not in writer_source


def test_migration_order_and_no_old_provisional_reference():
    old_stamp = "20260731" + "210000"
    repository_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in REPO_ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "node_modules" not in path.parts
        and "dist" not in path.parts
        and "__pycache__" not in path.parts
    )
    assert old_stamp not in repository_text
    assert BASELINE_MIGRATION.name < EVENT_MIGRATION.name
    assert "event_outbox" not in EVENT_MIGRATION.read_text(encoding="utf-8")


def test_full_sequence_corrected_main_and_fresh_schema_converge():
    event_sql = EVENT_MIGRATION.read_text(encoding="utf-8")
    baseline_sql = BASELINE_MIGRATION.read_text(encoding="utf-8")
    sequence_url, sequence_cleanup = _disposable(
        STUBS,
        schema_before_migration_or_skip(BASELINE_MIGRATION),
        baseline_sql,
        event_sql,
    )
    corrected_url, corrected_cleanup = _disposable(
        STUBS,
        _locked_main_schema(),
        event_sql,
    )
    fresh_url, fresh_cleanup = _disposable(STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    sequence = psycopg2.connect(sequence_url)
    corrected = psycopg2.connect(corrected_url)
    fresh = psycopg2.connect(fresh_url)
    try:
        assert _foundation_metadata(sequence) == _foundation_metadata(corrected)
        assert _foundation_metadata(corrected) == _foundation_metadata(fresh)
        assert _event_counts(sequence) == _event_counts(corrected) == _event_counts(fresh) == (0, 0)
        with sequence.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FROM pg_trigger
                WHERE tgname IN (
                    'trg_transporter_profiles_updated_at',
                    'trg_fuel_station_profiles_updated_at',
                    'trg_shopkeeper_profiles_updated_at'
                ) AND NOT tgisinternal
                """
            )
            assert cursor.fetchone()[0] == 3
            cursor.execute(
                "SELECT count(*) FROM pg_proc WHERE proname = "
                "'is_transporter_assigned_to_shipment'"
            )
            assert cursor.fetchone()[0] == 1
    finally:
        sequence.close()
        corrected.close()
        fresh.close()
        sequence_cleanup()
        corrected_cleanup()
        fresh_cleanup()


def test_migration_reapplication_is_safe_and_creates_no_rows():
    event_sql = EVENT_MIGRATION.read_text(encoding="utf-8")
    url, cleanup = _disposable(STUBS, _locked_main_schema(), event_sql)
    conn = psycopg2.connect(url)
    try:
        before = _foundation_metadata(conn)
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(event_sql)
        assert _foundation_metadata(conn) == before
        assert _event_counts(conn) == (0, 0)
    finally:
        conn.close()
        cleanup()


@pytest.fixture(scope="module")
def event_database_url():
    url, cleanup = _disposable(STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def event_connection(event_database_url):
    conn = psycopg2.connect(event_database_url)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_valid_security_and_business_writes_use_server_fields(
    event_connection, monkeypatch
):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    with event_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        security = write_security_event(
            cursor,
            "security.login.succeeded",
            _context(source="server_route"),
            EventData(metadata={"result_code": "ok"}),
        )
        business = write_business_audit_event(
            cursor, "one_time.payment.released", _context(), _data()
        )
    assert security.event["category"] == "security"
    assert business.event["category"] == "business_audit"
    assert security.event["environment"] == business.event["environment"] == "test"
    assert security.event["occurred_at"] is not None
    assert security.event["actor_id"] == 7


def test_unknown_deferred_and_wrong_category_fail_before_insert(
    event_connection, monkeypatch
):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    with event_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        with pytest.raises(UnknownEventName):
            write_security_event(cursor, "security.login.alias", _context(), EventData())
        with pytest.raises(NonWritableEventName):
            write_business_audit_event(
                cursor, DEFERRED_EVENT_NAMES[0], _context(), EventData()
            )
        with pytest.raises(NonWritableEventName):
            write_security_event(
                cursor, "one_time.payment.released", _context(), EventData()
            )
        cursor.execute(
            "SELECT (SELECT count(*) FROM security_events) AS security_count, "
            "(SELECT count(*) FROM business_audit_events) AS business_count"
        )
        assert cursor.fetchone() == {"security_count": 0, "business_count": 0}


def test_database_rejects_wrong_version_category_and_untyped_json(event_connection):
    base = (
        "INSERT INTO public.security_events "
        "(event_name,event_version,category,actor_type,request_id,source,provider_mode,"
        "environment,retention_class,metadata) VALUES "
        "('security.login.succeeded',%s,%s,'system','request.db.1','test','none',"
        "'test','security_12_months',%s::jsonb)"
    )
    with event_connection.cursor() as cursor:
        for version, category, metadata in (
            (2, "security", "{}"),
            (1, "business_audit", "{}"),
            (1, "security", '{"amount_minor":"wrong"}'),
            (1, "security", '{"result_code":{"nested":true}}'),
        ):
            cursor.execute("SAVEPOINT invalid_event")
            with pytest.raises((errors.CheckViolation, errors.RaiseException)):
                cursor.execute(base, (version, category, metadata))
            cursor.execute("ROLLBACK TO SAVEPOINT invalid_event")


def test_same_key_replays_and_conflicting_key_fails_closed(
    event_connection, monkeypatch
):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    with event_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        first = write_business_audit_event(
            cursor,
            "one_time.payment.released",
            _context(),
            _data(),
            idempotency_scope="payment.release",
            idempotency_key="payment.11",
        )
        replay = write_business_audit_event(
            cursor,
            "one_time.payment.released",
            _context(),
            _data(),
            idempotency_scope="payment.release",
            idempotency_key="payment.11",
        )
        assert not first.replayed and replay.replayed
        assert first.event["event_id"] == replay.event["event_id"]
        with pytest.raises(EventIdempotencyConflict):
            write_business_audit_event(
                cursor,
                "one_time.payment.refunded",
                _context(),
                _data(after_state={"status": "refunded"}),
                idempotency_scope="payment.release",
                idempotency_key="payment.11",
            )
        cursor.execute("SELECT 1 AS usable")
        assert cursor.fetchone()["usable"] == 1


def test_concurrent_duplicate_creates_one_row(event_database_url, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    scope = "concurrent.payment.release"
    key = "payment.12"
    barrier = threading.Barrier(2)
    results = []
    failures = []

    def worker():
        conn = psycopg2.connect(event_database_url)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                barrier.wait(timeout=10)
                result = write_business_audit_event(
                    cursor,
                    "one_time.payment.released",
                    _context(request_id="request.concurrent.1"),
                    _data(),
                    idempotency_scope=scope,
                    idempotency_key=key,
                )
            conn.commit()
            results.append(result)
        except Exception as exc:  # pragma: no cover - surfaced below
            conn.rollback()
            failures.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not failures
    assert len(results) == 2
    assert sorted(result.replayed for result in results) == [False, True]
    assert len({result.event["event_id"] for result in results}) == 1
    cleanup = psycopg2.connect(event_database_url)
    try:
        with cleanup:
            with cleanup.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM business_audit_events "
                    "WHERE idempotency_scope=%s AND idempotency_key=%s",
                    (scope, key),
                )
                assert cursor.fetchone()[0] == 1
                cursor.execute(
                    "DELETE FROM business_audit_events "
                    "WHERE idempotency_scope=%s AND idempotency_key=%s",
                    (scope, key),
                )
    finally:
        cleanup.close()


def test_mutation_and_event_share_atomic_rollback(event_connection, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    with event_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("CREATE TEMP TABLE authoritative_mutation (id integer primary key)")
    event_connection.commit()
    with event_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("INSERT INTO authoritative_mutation VALUES (1)")
        write_business_audit_event(
            cursor, "one_time.payment.released", _context(), _data()
        )
    event_connection.rollback()
    with event_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT count(*) AS count FROM authoritative_mutation")
        assert cursor.fetchone()["count"] == 0
        cursor.execute("SELECT count(*) AS count FROM business_audit_events")
        assert cursor.fetchone()["count"] == 0


def _expect_denied(cursor, statement):
    cursor.execute("SAVEPOINT denied_operation")
    with pytest.raises(errors.InsufficientPrivilege):
        cursor.execute(statement)
    cursor.execute("ROLLBACK TO SAVEPOINT denied_operation")


def test_real_roles_rls_grants_update_block_and_retention_delete(
    event_connection, monkeypatch
):
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    with event_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        for role in ("anon", "authenticated"):
            cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            for table in EVENT_TABLES:
                _expect_denied(cursor, f"SELECT * FROM public.{table}")
                _expect_denied(
                    cursor,
                    f"INSERT INTO public.{table} "
                    "(event_name,event_version,category,actor_type,request_id,source,"
                    "provider_mode,environment,retention_class) VALUES "
                    "('security.login.succeeded',1,'security','system','request.rls.1',"
                    "'test','none','test','security_12_months')",
                )
                _expect_denied(cursor, f"UPDATE public.{table} SET request_id='changed'")
                _expect_denied(cursor, f"DELETE FROM public.{table}")
            cursor.execute("RESET ROLE")

        cursor.execute("SET LOCAL ROLE service_role")
        created = write_security_event(
            cursor,
            "security.login.succeeded",
            _context(source="server_route"),
            EventData(),
        )
        cursor.execute("SELECT count(*) AS count FROM public.security_events")
        assert cursor.fetchone()["count"] == 1
        cursor.execute(
            "DELETE FROM public.security_events WHERE event_id=%s",
            (created.event["event_id"],),
        )
        cursor.execute("RESET ROLE")

        owner_created = write_security_event(
            cursor,
            "security.login.succeeded",
            _context(source="server_route"),
            EventData(),
        )
        cursor.execute("SAVEPOINT update_forbidden")
        with pytest.raises(errors.RaiseException):
            cursor.execute(
                "UPDATE public.security_events SET request_id='changed' WHERE event_id=%s",
                (owner_created.event["event_id"],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT update_forbidden")
        cursor.execute(
            "SELECT count(*) AS count FROM information_schema.views "
            "WHERE table_schema='public' AND table_name LIKE '%event%'"
        )
        assert cursor.fetchone()["count"] == 0


def test_no_runtime_route_imports_or_emits_canonical_events():
    forbidden = (
        "write_security_event",
        "write_business_audit_event",
        "security_events",
        "business_audit_events",
    )
    matches = []
    for path in (REPO_ROOT / "backend").rglob("*.py"):
        if "tests" in path.parts or "events" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(token in text for token in forbidden):
            matches.append(path.relative_to(REPO_ROOT).as_posix())
    assert matches == []
