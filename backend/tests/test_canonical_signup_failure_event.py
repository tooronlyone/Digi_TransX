"""Forward-only proof for the bounded canonical signup-failure definition."""

from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import errors
import pytest

from events.catalog import CATALOG, INTEGRATED_EVENT_NAMES, SIGNUP_FAILURE_RESULT_CODES
from events.contract import EventContext, EventContractError, EventData, validate_catalog_event_contract
from events.writer import write_security_event
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url, schema_before_migration_or_skip
from tests.test_canonical_event_acl_hardening import _semantic_signature
from tests.test_canonical_event_foundation import _direct_insert, _event_counts


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260801120000_add_signup_failed_event.sql"
EXPECTED_PRE_SIGNATURE = "7b8157021244549cfed79416b40ab662"
EXPECTED_POST_SIGNATURE = "993b1de965a1791a2a84ccff5fcfbdf9"
INTEGRATED_NAMES = {
    "security.login.started",
    "security.login.failed",
    "security.login.succeeded",
    "security.logout.completed",
}


def _local_url():
    url = require_test_db_url()
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert parsed.path.lstrip("/") == "dtx_schema_trigger_rls_baseline"
    return url


def _context(**changes):
    values = {
        "request_id": "request.signup.failure.contract",
        "source": "server_route",
        "actor_type": "anonymous",
    }
    values.update(changes)
    return EventContext(**values)


def _insert_integrated_event(conn, request_id):
    with conn.cursor() as cursor:
        _direct_insert(
            cursor,
            "security_events",
            event_name="security.login.started",
            event_version=1,
            category="security",
            retention_class="security_12_months",
            request_id=request_id,
        )
    conn.commit()


def test_signup_failure_catalog_definition_and_minimal_contract():
    definition = CATALOG["security.signup.failed"]
    assert definition.name == "security.signup.failed"
    assert (
        definition.version,
        definition.category,
        definition.ownership_domain,
        definition.retention_class,
        definition.lifecycle_status,
        definition.writable,
        definition.integrated,
    ) == (1, "security", "security", "security_12_months", "planned", True, True)
    assert definition.allowed_result_codes == SIGNUP_FAILURE_RESULT_CODES == {
        "validation_failed",
        "account_conflict",
        "provider_unavailable",
        "persistence_failed",
        "reconciliation_required",
    }
    assert sum(item.name == definition.name for item in CATALOG.values()) == 1
    for code in SIGNUP_FAILURE_RESULT_CODES:
        checked, context, data = validate_catalog_event_contract(
            definition.name, _context(), EventData(metadata={"result_code": code})
        )
        assert checked == definition
        assert context["actor_type"] == "anonymous"
        assert context["actor_id"] is None
        assert context["actor_role"] is None
        assert context["subject_user_id"] is None
        assert data["metadata"] == {"result_code": code}
    for data in (
        EventData(metadata={"result_code": "unknown_code"}),
        EventData(metadata={"result_code": "provider-error-secret"}),
        EventData(metadata={"result_code": "validation_failed", "attempt_number": 1}),
        EventData(metadata={"email": "not-permitted"}),
        EventData(after_state={"status": "failed"}, metadata={"result_code": "validation_failed"}),
    ):
        with pytest.raises(EventContractError):
            validate_catalog_event_contract(definition.name, _context(), data)
    with pytest.raises(EventContractError):
        validate_catalog_event_contract(
            definition.name,
            _context(actor_type="user", actor_id=1, actor_role="customer"),
            EventData(metadata={"result_code": "validation_failed"}),
        )


def test_signup_failure_direct_sql_is_accepted_only_in_the_corrected_final_schema():
    url, cleanup = make_disposable(_local_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE service_role")
                _direct_insert(
                    cursor,
                    "security_events",
                    event_name="security.signup.failed",
                    event_version=1,
                    category="security",
                    retention_class="security_12_months",
                    request_id="request.signup.failed.accepted",
                )
                cursor.execute("RESET ROLE")
            assert _event_counts(conn) == (1, 0)
        finally:
            conn.close()
    finally:
        cleanup()


def test_signup_failure_migration_converges_and_reapplies_after_integrated_rows():
    migration = MIGRATION.read_text(encoding="utf-8")
    observed = []
    for blocks, requires_migration in (
        ((STUBS, schema_before_migration_or_skip(MIGRATION)), True),
        ((STUBS, SCHEMA_SQL.read_text(encoding="utf-8")), False),
    ):
        url, cleanup = make_disposable(_local_url(), *blocks)
        try:
            conn = psycopg2.connect(url)
            try:
                assert _semantic_signature(conn) == (
                    EXPECTED_PRE_SIGNATURE if requires_migration else "371c7010a0553c7953708dea164ed0bc"
                )
                if requires_migration:
                    with conn.cursor() as cursor:
                        cursor.execute(migration)
                    conn.commit()
                _insert_integrated_event(conn, "request.signup.failed.migration")
                if requires_migration:
                    for _ in range(2):
                        with conn.cursor() as cursor:
                            cursor.execute(migration)
                        conn.commit()
                with conn.cursor() as cursor:
                    cursor.execute(
                        "select count(*) from public.security_events where event_name='security.login.started'"
                    )
                    rows = cursor.fetchone()[0]
                observed.append((_semantic_signature(conn), rows))
            finally:
                conn.close()
        finally:
            cleanup()
    assert observed == [(EXPECTED_POST_SIGNATURE, 1), ("371c7010a0553c7953708dea164ed0bc", 1)]


def test_signup_failure_migration_rejects_alias_partial_state_without_repair():
    url, cleanup = make_disposable(_local_url(), STUBS, schema_before_migration_or_skip(MIGRATION))
    try:
        conn = psycopg2.connect(url)
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        insert into public.canonical_event_catalog_projection
                            (event_name, event_version, category, ownership_domain,
                             retention_class, lifecycle_status, writable, integrated)
                        values ('security.registration.failed', 1, 'security', 'security',
                                'security_12_months', 'planned', true, false)
                        """
                    )
            before = _semantic_signature(conn)
            with pytest.raises((psycopg2.Error, errors.RaiseException)):
                with conn.cursor() as cursor:
                    cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            conn.rollback()
            assert _semantic_signature(conn) == before
            with conn.cursor() as cursor:
                cursor.execute(
                    "select count(*) from public.canonical_event_catalog_projection where event_name='security.registration.failed'"
                )
                assert cursor.fetchone()[0] == 1
        finally:
            conn.close()
    finally:
        cleanup()


def test_signup_failure_definition_migration_remains_forward_only_after_runtime_activation():
    assert INTEGRATED_NAMES.issubset(INTEGRATED_EVENT_NAMES)
    assert "security.signup.failed" in INTEGRATED_EVENT_NAMES
    routes = (REPO_ROOT / "backend" / "auth" / "routes.py").read_text(encoding="utf-8")
    assert "security.signup.failed" in routes
    text = MIGRATION.read_text(encoding="utf-8")
    assert text.count("begin;") == 1 and text.count("commit;") == 1
    assert "create trigger" not in text.lower()
    assert "create table" not in text.lower()
