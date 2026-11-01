"""Adversarial proofs for the closed Phase 1B-2C6 shared-TEST harness."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
import pytest

from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.shared_test_session_device_management_harness import (
    ACTIVATION_ENV,
    EXPECTED_HOST,
    EXPECTED_PROJECT_REF,
    PROJECT_ENV,
    ProbeAndCleanupError,
    SharedTestSessionDeviceHarnessError,
    SharedTestSessionDeviceLedger,
    URL_ENV,
    _run_probe_matrix,
    require_authorized_shared_test_url,
    run_authorized_session_device_probe_matrix,
)

SOURCE_PATH = Path(__file__).with_name("shared_test_session_device_management_harness.py")


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
        with pytest.raises(SharedTestSessionDeviceHarnessError):
            require_authorized_shared_test_url(changed)


def test_public_api_has_no_generic_registration_adoption_or_database_surface():
    ledger = SharedTestSessionDeviceLedger("unused")
    public = {name for name in dir(ledger) if not name.startswith("_")}
    assert public == {
        "cleanup", "cleanup_trace", "closed", "events_seen", "fail_after", "graphs",
        "run_current_logout_route", "run_event_failure", "run_management_matrix",
        "sanitized_evidence", "setup_graphs", "tag", "url",
    }
    forbidden = ("register", "adopt", "sql", "query", "predicate", "table", "column", "delete", "event_name", "ownership", "key")
    callable_public = {name for name in public if callable(getattr(ledger, name))}
    assert not any(any(word in name.lower() for word in forbidden) for name in callable_public)


def test_source_has_fixed_cleanup_reverse_order_and_no_injection_surface():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert "TRUNCATE" not in source
    assert "DELETE FROM public." in source
    assert "DELETE FROM public.{" not in source
    assert "cursor.execute(f\"DELETE" not in source and "cur.execute(f\"DELETE" not in source
    assert "rowcount != 1" in source
    cleanup_block = source[source.index("for receipt_type in (EventReceipt"):]
    order = [cleanup_block.index(name) for name in ("EventReceipt", "SessionReceipt", "DeviceReceipt", "UserReceipt")]
    assert order == sorted(order)
    assert "FOR UPDATE" in source
    assert "management.write_security_event = fixed_writer" in source
    assert "canonical_write_security_event" in source
    for forbidden in ("caller_table", "caller_key", "caller_sql", "caller_predicate", "table_name", "predicate"):
        assert forbidden not in source


def test_probe_and_cleanup_failures_are_both_preserved():
    ledger = SharedTestSessionDeviceLedger("unused")
    ledger.cleanup = lambda: (_ for _ in ()).throw(RuntimeError("cleanup"))
    with pytest.raises(ProbeAndCleanupError) as caught:
        with ledger:
            raise ValueError("probe")
    assert isinstance(caught.value.probe_error, ValueError)
    assert isinstance(caught.value.cleanup_error, RuntimeError)


def test_partial_fixture_creation_cleanup_is_exact_idempotent_and_closes(disposable_url):
    before = _counts(disposable_url)
    ledger = SharedTestSessionDeviceLedger(disposable_url)
    ledger.setup_graphs()
    ledger.cleanup()
    ledger.cleanup()
    assert _counts(disposable_url) == before
    assert ledger.sanitized_evidence()["closed"] is True
    with pytest.raises(SharedTestSessionDeviceHarnessError, match="closed"):
        ledger.setup_graphs()


def test_ownership_mismatch_prevents_deletion_and_preserves_foreign_rows(disposable_url):
    isolated, drop = make_disposable(_loopback_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        ledger = SharedTestSessionDeviceLedger(isolated)
        ledger.setup_graphs()
        with psycopg2.connect(isolated) as conn, conn.cursor() as cur:
            cur.execute("UPDATE public.users SET full_name=full_name || '_tampered' WHERE full_name LIKE 'dtx_shared_2c6_%owner'")
        with pytest.raises(SharedTestSessionDeviceHarnessError, match="mismatch"):
            ledger.cleanup()
        with psycopg2.connect(isolated) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.users WHERE full_name LIKE 'dtx_shared_2c6_%'")
            assert cur.fetchone()[0] >= 1
    finally:
        drop()


def test_complete_local_matrix_reconciles_and_preserves_controls(disposable_url):
    result = _run_probe_matrix(disposable_url)
    assert result["probes"] == {
        "management": {"sessions_listed": 3, "devices_listed": 3, "revoked_sessions": 3, "revoked_devices": 1, "events": 4},
        "current_logout": {"current_logout": "canonical", "events": 2},
        "event_failure": {"rolled_back": True, "events": 0},
    }
    assert result["external_provider_calls"] == 0
    assert result["before_counts"] == result["after_counts"]
    assert all(result["fingerprints_equal"].values())
    assert result["created_counts"] == {"users": 4, "trusted_devices": 9, "user_sessions": 11, "mpin_credentials": 0, "mpin_step_up_authorizations": 0, "security_events": 6}


def _counts(url):
    tables = ("users", "trusted_devices", "user_sessions", "mpin_credentials", "mpin_step_up_authorizations", "security_events")
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        out = {}
        for table in tables:
            cur.execute(f"SELECT count(*) FROM public.{table}")
            out[table] = cur.fetchone()[0]
        conn.rollback()
    return out


@pytest.mark.skipif(os.environ.get(ACTIVATION_ENV) != "1", reason="explicit shared-TEST opt-in is absent")
def test_authorized_shared_test_session_device_matrix():
    result = run_authorized_session_device_probe_matrix()
    assert result["external_provider_calls"] == 0
    assert result["before_counts"] == result["after_counts"]
    assert all(result["fingerprints_equal"].values())
