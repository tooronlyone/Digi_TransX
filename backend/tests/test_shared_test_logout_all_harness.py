"""Adversarial proofs for the closed Phase 1B-2C4 shared-TEST harness."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
import pytest

from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.shared_test_logout_all_harness import (
    ACTIVATION_ENV,
    EXPECTED_HOST,
    EXPECTED_PROJECT_REF,
    PROJECT_ENV,
    ProbeAndCleanupError,
    SharedTestLogoutAllHarnessError,
    SharedTestLogoutAllLedger,
    URL_ENV,
    _assert_request_namespace_clear,
    _run_probe_matrix,
    require_authorized_shared_test_url,
    run_authorized_logout_all_probe_matrix,
)


SOURCE_PATH = Path(__file__).with_name("shared_test_logout_all_harness.py")


def _loopback_url():
    url = require_test_db_url()
    assert urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"}
    return url


@pytest.fixture(scope="module")
def disposable_url():
    url, cleanup = make_disposable(_loopback_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        yield url
    finally:
        cleanup()


def test_authorization_gate_is_exact_and_fail_closed():
    good = {
        ACTIVATION_ENV: "1",
        PROJECT_ENV: EXPECTED_PROJECT_REF,
        URL_ENV: f"postgresql://postgres.{EXPECTED_PROJECT_REF}:secret@{EXPECTED_HOST}:6543/postgres",
    }
    assert require_authorized_shared_test_url(good) == good[URL_ENV]
    for changed in (
        {},
        {**good, ACTIVATION_ENV: "0"},
        {**good, PROJECT_ENV: "another"},
        {**good, URL_ENV: "postgresql://postgres:secret@127.0.0.1/postgres"},
        {**good, URL_ENV: f"postgresql://postgres:secret@{EXPECTED_HOST}/other"},
    ):
        with pytest.raises(SharedTestLogoutAllHarnessError):
            require_authorized_shared_test_url(changed)


def test_public_api_has_no_generic_registration_adoption_or_database_surface():
    ledger = SharedTestLogoutAllLedger("unused")
    public = {name for name in dir(ledger) if not name.startswith("_")}
    assert public == {
        "cleanup", "run_event_failure", "run_mpin_matrix", "run_password_route",
        "sanitized_evidence", "setup_mpin_graph", "setup_password_graph",
        "setup_rollback_graph",
    }
    forbidden = ("register", "adopt", "capture", "sql", "query", "predicate", "table", "column", "delete", "event_name", "ownership", "key")
    assert not any(any(word in name.lower() for word in forbidden) for name in public)


def test_source_has_fixed_cleanup_and_complete_runtime_binding():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert "TRUNCATE" not in source
    assert "DELETE FROM public." in source
    assert "DELETE FROM public.{" not in source
    assert "cursor.rowcount != 1" in source
    dependency_line = next(line for line in source.splitlines() if "dependency_order =" in line)
    order = [dependency_line.index(name) for name in ("EventReceipt", "AuthorizationReceipt", "SessionReceipt", "DeviceReceipt", "CredentialReceipt", "UserReceipt")]
    assert order == sorted(order)
    for owner in ("auth_helpers", "auth_routes", "logout_all_service"):
        assert f'patch.object({owner}, "open_db", fixed_open_db)' in source
    assert 'patch.object(logout_all_service, "supabase_verify_password", fixed_password_verifier)' in source
    assert 'patch.object(event_writer, "write_security_event", fixed_event_writer)' in source
    assert "canonical_write_security_event" in source


def test_correlation_collision_fails_before_mutation():
    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params):
            self.calls.append((statement, params))

        def fetchone(self):
            return ("existing",)

    cursor = Cursor()
    with pytest.raises(SharedTestLogoutAllHarnessError, match="collision before mutation"):
        _assert_request_namespace_clear(cursor, "owned.request")
    assert len(cursor.calls) == 1 and cursor.calls[0][0].lstrip().startswith("SELECT")


def test_probe_and_cleanup_failures_are_both_preserved():
    ledger = SharedTestLogoutAllLedger("unused")

    def failed_cleanup():
        raise RuntimeError("cleanup")

    ledger.cleanup = failed_cleanup
    with pytest.raises(ProbeAndCleanupError) as caught:
        with ledger:
            raise ValueError("probe")
    assert isinstance(caught.value.probe_error, ValueError)
    assert isinstance(caught.value.cleanup_error, RuntimeError)


def test_partial_creation_cleanup_is_exact_idempotent_and_closes(disposable_url):
    before = _table_counts(disposable_url)
    ledger = SharedTestLogoutAllLedger(disposable_url)
    ledger.setup_password_graph()
    ledger.cleanup()
    ledger.cleanup()
    assert _table_counts(disposable_url) == before
    assert ledger.sanitized_evidence()["closed"] is True
    with pytest.raises(SharedTestLogoutAllHarnessError, match="closed"):
        ledger.setup_password_graph()


def test_ownership_mismatch_prevents_deletion(disposable_url):
    isolated, drop = make_disposable(_loopback_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        ledger = SharedTestLogoutAllLedger(isolated)
        ledger.setup_password_graph()
        with psycopg2.connect(isolated) as conn, conn.cursor() as cursor:
            cursor.execute("UPDATE public.users SET full_name=full_name || '_tampered' WHERE full_name LIKE 'dtx_shared_logout_all_%'")
        with pytest.raises(SharedTestLogoutAllHarnessError, match="ownership mismatch"):
            ledger.cleanup()
        with psycopg2.connect(isolated) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM public.users WHERE full_name LIKE 'dtx_shared_logout_all_%'")
            assert cursor.fetchone()[0] == 1
    finally:
        drop()


def test_complete_local_matrix_reconciles_and_preserves_controls(disposable_url):
    result = _run_probe_matrix(disposable_url)
    assert result["probes"] == {
        "mpin": {"sessions": 2, "devices": 2, "events": 6},
        "password": {"sessions": 2, "devices": 2, "events": 5, "deterministic_verifier_calls": 1},
        "rollback": {"rolled_back": True, "events": 0},
    }
    assert result["external_provider_calls"] == 0
    assert result["deterministic_verifier_calls"] == 2
    assert all(result["fingerprints_equal"].values())
    assert result["before_counts"] == result["after_counts"]


def _table_counts(url):
    tables = ("users", "trusted_devices", "user_sessions", "mpin_credentials", "mpin_step_up_authorizations", "security_events")
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        values = {}
        for table in tables:
            cursor.execute(f"SELECT count(*) FROM public.{table}")
            values[table] = cursor.fetchone()[0]
        conn.rollback()
    return values


@pytest.mark.skipif(os.environ.get(ACTIVATION_ENV) != "1", reason="explicit shared-TEST opt-in is absent")
def test_authorized_shared_test_logout_all_matrix():
    result = run_authorized_logout_all_probe_matrix()
    assert result["external_provider_calls"] == 0
    assert result["before_counts"] == result["after_counts"]
    assert all(result["fingerprints_equal"].values())
