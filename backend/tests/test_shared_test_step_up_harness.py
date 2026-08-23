"""Targeted safety tests for the opt-in shared-TEST step-up harness."""
from copy import deepcopy
from inspect import signature
from types import SimpleNamespace
import os
import pytest
from shared.payments import PaymentProviderRejected
from tests.shared_test_step_up_harness import (
    ACTIVATION_ENV, EXPECTED_PROJECT_REF, PROJECT_ENV, URL_ENV,
    ProbeAndCleanupError, SharedTestFixtureLedger, SharedTestHarnessError,
    deterministic_payout_provider, require_authorized_shared_test_url,
    run_authorized_pending_probe_matrix,
)

def _env(url):
    return {ACTIVATION_ENV: "1", PROJECT_ENV: EXPECTED_PROJECT_REF, URL_ENV: url}

def test_harness_requires_explicit_activation_and_exact_identity():
    with pytest.raises(SharedTestHarnessError):
        require_authorized_shared_test_url({})
    with pytest.raises(SharedTestHarnessError):
        require_authorized_shared_test_url(_env("postgresql://postgres:secret@127.0.0.1:5432/postgres"))
    wrong = _env("postgresql://postgres:secret@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres")
    wrong[PROJECT_ENV] = "not-the-authorized-project"
    with pytest.raises(SharedTestHarnessError):
        require_authorized_shared_test_url(wrong)

def test_harness_rejects_non_postgres_or_non_pooler_targets():
    for url in (
        "postgresql://postgres:secret@aws-0-ap-northeast-1.pooler.supabase.com:5432/other",
        "postgresql://postgres:secret@example.invalid:5432/postgres",
    ):
        with pytest.raises(SharedTestHarnessError):
            require_authorized_shared_test_url(_env(url))
    qualified = (
        "postgresql://postgres.fysupkvuvhvtowbfgoev:secret@"
        "aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"
    )
    assert require_authorized_shared_test_url(_env(qualified)) == qualified
    wrong_role = (
        "postgresql://postgres.another-project:secret@"
        "aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"
    )
    with pytest.raises(SharedTestHarnessError):
        require_authorized_shared_test_url(_env(wrong_role))



def test_provider_boundary_is_deterministic_and_in_process():
    from tests import shared_test_step_up_harness as harness
    original = harness.wallet_routes.get_payment_provider
    with deterministic_payout_provider("reject") as provider:
        with pytest.raises(PaymentProviderRejected):
            harness.wallet_routes.get_payment_provider().tokenize({})
        assert provider.calls == 1
    assert harness.wallet_routes.get_payment_provider() is original()
    with deterministic_payout_provider("ambiguous") as provider:
        with pytest.raises(RuntimeError):
            harness.wallet_routes.get_payment_provider().tokenize({})
        assert provider.calls == 1
    assert harness.wallet_routes.get_payment_provider() is original()

class _Cursor:
    def __init__(self, *, owned=True, delete_count=1, returned_ids=(7,)):
        self.owned = owned
        self.delete_count = delete_count
        self.returned_ids = iter(returned_ids)
        self.rowcount = 0
        self.deleted = 0
        self.statements = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if sql.startswith("SELECT"):
            self._result = (1,) if self.owned else None
        elif sql.startswith("INSERT"):
            value = next(self.returned_ids) if "RETURNING" in sql else None
            self._result = value if isinstance(value, tuple) else (value,)
        elif sql.startswith("DELETE"):
            self.rowcount = self.delete_count
            self.deleted += 1
    def fetchone(self): return self._result

class _Connection:
    def __init__(self, *, owned=True, delete_count=1, returned_ids=(7,)):
        self.cursor_value = _Cursor(
            owned=owned, delete_count=delete_count, returned_ids=returned_ids,
        )
        self.commits = 0
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self, *args, **kwargs): return self.cursor_value
    def commit(self): self.commits += 1

def _created_user(ledger, conn):
    ledger.connect = lambda: conn
    return ledger.create_user(legacy_role="user", app_role="everyday_user")

def test_context_exit_cleans_and_repeated_cleanup_is_idempotent():
    conn = _Connection()
    ledger = SharedTestFixtureLedger("fake")
    _created_user(ledger, conn)
    with ledger:
        pass
    ledger.cleanup()
    assert conn.cursor_value.deleted == 1
    with pytest.raises(SharedTestHarnessError, match="closed"):
        ledger.create_user(legacy_role="user", app_role="everyday_user")
    assert ledger._cleaned is True

def test_probe_exception_is_preserved_after_successful_cleanup():
    conn = _Connection()
    ledger = SharedTestFixtureLedger("fake")
    _created_user(ledger, conn)
    with pytest.raises(ValueError, match="probe failed"):
        with ledger:
            raise ValueError("probe failed")
    assert conn.cursor_value.deleted == 1

def test_cleanup_failure_surfaces_with_original_exception():
    conn = _Connection(owned=False)
    ledger = SharedTestFixtureLedger("fake")
    _created_user(ledger, conn)
    with pytest.raises(ProbeAndCleanupError) as caught:
        with ledger:
            raise ValueError("probe failed")
    assert isinstance(caught.value.probe_error, ValueError)
    assert isinstance(caught.value.cleanup_error, SharedTestHarnessError)

def test_foreign_supported_row_fails_ownership_check_before_delete():
    ledger = SharedTestFixtureLedger("fake")
    conn = _Connection(owned=False)
    _created_user(ledger, conn)
    with pytest.raises(SharedTestHarnessError):
        ledger.cleanup()
    assert conn.cursor_value.deleted == 0
    assert ledger._cleaned is False

def test_forged_supported_key_and_injected_predicate_cannot_reach_delete():
    conn = _Connection()
    ledger = SharedTestFixtureLedger("fake")
    user_id = _created_user(ledger, conn)
    assert not hasattr(ledger, "record")
    assert not hasattr(ledger, "_register_owned")
    assert not hasattr(ledger, "_owned_rows")
    assert not any("owned" in name for name in vars(ledger))
    ledger._owned_rows = (
        ("users", "id", 8, "SELECT 1", ()),
    )
    ledger._SharedTestFixtureLedger__owned_rows = (
        ("users", "id", 8, "SELECT 1", ()),
    )
    ledger.owner_sql = "SELECT 1"
    ledger.cleanup()
    deletes = [
        (sql, params) for sql, params in conn.cursor_value.statements
        if sql.startswith("DELETE")
    ]
    assert len(deletes) == 1
    assert deletes[0][1][0] == user_id
    assert all("SELECT 1" not in sql for sql, _ in conn.cursor_value.statements)
    assert all(params[0] != 8 for _, params in deletes)

def test_cleanup_uses_hard_coded_ownership_predicate_and_exact_delete():
    conn = _Connection()
    ledger = SharedTestFixtureLedger("fake")
    user_id = _created_user(ledger, conn)
    ledger.cleanup()
    select_sql, select_params = conn.cursor_value.statements[-2]
    delete_sql, delete_params = conn.cursor_value.statements[-1]
    assert select_sql == (
        "SELECT id FROM public.users "
        "WHERE id=%s AND email=%s AND full_name=%s FOR UPDATE"
    )
    assert delete_sql == (
        "DELETE FROM public.users "
        "WHERE id=%s AND email=%s AND full_name=%s"
    )
    assert select_params == delete_params
    assert select_params[0] == user_id
    assert conn.cursor_value.deleted == 1

def test_cleanup_is_dependency_safe_reverse_creation_order(monkeypatch):
    from tests import shared_test_step_up_harness as harness

    conn = _Connection(returned_ids=(7, 11, 13, (17, "created")))
    ledger = SharedTestFixtureLedger("fake")
    _created_user(ledger, conn)
    monkeypatch.setattr(
        harness.mpin_service, "build_credential", lambda value: ("salt", "verifier"),
    )
    ledger.attach_authentication()
    ledger.cleanup()
    deleted_tables = [
        sql.split("public.", 1)[1].split(" ", 1)[0]
        for sql, _ in conn.cursor_value.statements
        if sql.startswith("DELETE")
    ]
    assert deleted_tables == [
        "mpin_credentials", "user_sessions", "trusted_devices", "users",
    ]

def test_non_exact_delete_is_rejected():
    conn = _Connection(delete_count=0)
    ledger = SharedTestFixtureLedger("fake")
    _created_user(ledger, conn)
    with pytest.raises(SharedTestHarnessError, match="not exact"):
        ledger.cleanup()
    assert ledger._cleaned is False

class _RuntimeResult:
    def __init__(self, row=None, *, rowcount=1):
        self.row = row
        self.rowcount = rowcount
    def fetchone(self):
        return self.row

class _RuntimeDb:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []
    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        row = self.rows.pop(0) if self.rows else None
        return _RuntimeResult(row)

class _RuntimeConnection:
    def __init__(self, db):
        self.db = db
        self.commits = 0
        self.rollbacks = 0
    def __enter__(self): return self
    def __exit__(self, exc_type, *args):
        if exc_type is not None:
            self.rollbacks += 1
        return False
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1

def _authenticated_ledger(monkeypatch):
    from tests import shared_test_step_up_harness as harness

    conn = _Connection(returned_ids=(7, 11, 13, (17, "created")))
    ledger = SharedTestFixtureLedger("fake")
    _created_user(ledger, conn)
    monkeypatch.setattr(
        harness.mpin_service, "build_credential", lambda value: ("salt", "verifier"),
    )
    ledger.attach_authentication()
    return harness, ledger, conn

def _issue_owned_checkout(monkeypatch, ledger, harness):
    issued = {"authorization_id": "00000000-0000-0000-0000-000000000001", "proof": "p" * 43}
    runtime_db = _RuntimeDb((None, {"authorization_id": "00000000-0000-0000-0000-000000000001"}))
    runtime_conn = _RuntimeConnection(runtime_db)
    monkeypatch.setattr(harness, "Db", lambda conn: conn.db)
    monkeypatch.setattr(
        harness.step_up_service,
        "issue_authorization",
        lambda db, **kwargs: issued,
    )
    ledger.connect = lambda: runtime_conn
    ledger.issue_checkout_authorization()
    return runtime_db, runtime_conn

def _capture_owned_consumed_event(monkeypatch, ledger, harness):
    event = {
        "event_id": "00000000-0000-0000-0000-000000000002",
        "fingerprint": "f" * 64,
    }
    runtime_db = _RuntimeDb((None, {"event_id": "00000000-0000-0000-0000-000000000002"}))
    runtime_conn = _RuntimeConnection(runtime_db)
    monkeypatch.setattr(harness, "Db", lambda conn: conn.db)
    monkeypatch.setattr(
        harness.step_up_service,
        "write_consumed_event",
        lambda db, **kwargs: SimpleNamespace(event=event, replayed=False),
    )
    ledger.connect = lambda: runtime_conn
    ledger.write_consumed_evidence()
    return runtime_db, runtime_conn

def test_foreign_authorization_collision_fails_before_mutation_and_is_identical(
    monkeypatch,
):
    harness, ledger, base_conn = _authenticated_ledger(monkeypatch)
    foreign = {"authorization_id": "foreign-auth", "fingerprint": b"foreign"}
    before = deepcopy(foreign)
    runtime_db = _RuntimeDb((foreign,))
    runtime_conn = _RuntimeConnection(runtime_db)
    called = {"issue": 0}
    monkeypatch.setattr(harness, "Db", lambda conn: conn.db)
    monkeypatch.setattr(
        harness.step_up_service,
        "issue_authorization",
        lambda *args, **kwargs: called.__setitem__("issue", called["issue"] + 1),
    )
    ledger.connect = lambda: runtime_conn
    with pytest.raises(SharedTestHarnessError, match="collision before creation"):
        ledger.issue_checkout_authorization()
    assert called["issue"] == 0
    assert foreign == before
    ledger.connect = lambda: base_conn
    ledger.cleanup()
    assert all(
        "mpin_step_up_authorizations" not in sql
        for sql, _ in base_conn.cursor_value.statements
        if sql.startswith("DELETE")
    )

def test_foreign_event_collision_fails_before_writer_and_is_identical(monkeypatch):
    harness, ledger, base_conn = _authenticated_ledger(monkeypatch)
    _issue_owned_checkout(monkeypatch, ledger, harness)
    foreign = {"event_id": "foreign-event", "fingerprint": "a" * 64}
    before = deepcopy(foreign)
    runtime_db = _RuntimeDb((foreign,))
    runtime_conn = _RuntimeConnection(runtime_db)
    called = {"writer": 0}
    monkeypatch.setattr(
        harness.step_up_service,
        "write_consumed_event",
        lambda *args, **kwargs: called.__setitem__(
            "writer", called["writer"] + 1
        ),
    )
    ledger.connect = lambda: runtime_conn
    with pytest.raises(SharedTestHarnessError, match="collision before creation"):
        ledger.write_consumed_evidence()
    assert called["writer"] == 0
    assert foreign == before
    cleanup_conn = _Connection()
    ledger.connect = lambda: cleanup_conn
    ledger.cleanup()
    assert all(
        params[0] != "foreign-event"
        for sql, params in cleanup_conn.cursor_value.statements
        if sql.startswith("DELETE")
    )

def test_closed_artifact_api_has_no_caller_selected_identity_or_registration():
    ledger = SharedTestFixtureLedger("fake")
    for name in (
        "issue_checkout_authorization", "issue_payout_authorization",
        "write_consumed_evidence", "replay_consumed_evidence",
        "write_reconciliation_evidence", "replay_reconciliation_evidence",
    ):
        assert list(signature(getattr(ledger, name)).parameters) == []
    for forbidden in (
        "register", "capture", "adopt", "authorization_id", "event_id",
        "table", "owner_sql", "owner_params", "key_column", "key_value",
    ):
        assert not hasattr(ledger, forbidden)
    ledger.authorization_id = "foreign-auth"
    ledger.event_id = "foreign-event"
    ledger.owner_sql = "DELETE FROM public.security_events"
    assert not any(name.startswith("_capture") for name in vars(ledger))

def test_partial_authorization_creation_rolls_back_and_cleans_only_proven_rows(
    monkeypatch,
):
    harness, ledger, base_conn = _authenticated_ledger(monkeypatch)
    runtime_db = _RuntimeDb((None, None))
    runtime_conn = _RuntimeConnection(runtime_db)
    monkeypatch.setattr(harness, "Db", lambda conn: conn.db)
    monkeypatch.setattr(
        harness.step_up_service,
        "issue_authorization",
        lambda db, **kwargs: {
            "authorization_id": "unverified-auth", "proof": "p" * 43,
        },
    )
    ledger.connect = lambda: runtime_conn
    with pytest.raises(SharedTestHarnessError, match="verification failed"):
        ledger.issue_checkout_authorization()
    assert runtime_conn.rollbacks == 1
    ledger.connect = lambda: base_conn
    ledger.cleanup()
    assert all(
        "mpin_step_up_authorizations" not in sql
        for sql, _ in base_conn.cursor_value.statements
        if sql.startswith("DELETE")
    )

def test_authorization_ownership_mismatch_preserves_probe_error(monkeypatch):
    harness, ledger, _ = _authenticated_ledger(monkeypatch)
    _issue_owned_checkout(monkeypatch, ledger, harness)
    mismatch = _Connection(owned=False)
    ledger.connect = lambda: mismatch
    with pytest.raises(ProbeAndCleanupError) as caught:
        with ledger:
            raise ValueError("probe failed")
    assert isinstance(caught.value.probe_error, ValueError)
    assert isinstance(caught.value.cleanup_error, SharedTestHarnessError)
    assert mismatch.cursor_value.deleted == 0

def test_event_authorization_cleanup_is_exact_reverse_dependency_order(monkeypatch):
    harness, ledger, _ = _authenticated_ledger(monkeypatch)
    _issue_owned_checkout(monkeypatch, ledger, harness)
    _capture_owned_consumed_event(monkeypatch, ledger, harness)
    cleanup_conn = _Connection()
    ledger.connect = lambda: cleanup_conn
    ledger.cleanup()
    deleted_tables = [
        sql.split("public.", 1)[1].split(" ", 1)[0]
        for sql, _ in cleanup_conn.cursor_value.statements
        if sql.startswith("DELETE")
    ]
    assert deleted_tables == [
        "security_events", "mpin_step_up_authorizations",
        "mpin_credentials", "user_sessions", "trusted_devices", "users",
    ]
    deletes = [
        (sql, params) for sql, params in cleanup_conn.cursor_value.statements
        if sql.startswith("DELETE")
    ]
    assert all("WHERE" in sql for sql, _ in deletes)
    assert all(params for _, params in deletes)

def test_event_exact_delete_rowcount_is_required(monkeypatch):
    harness, ledger, _ = _authenticated_ledger(monkeypatch)
    _issue_owned_checkout(monkeypatch, ledger, harness)
    _capture_owned_consumed_event(monkeypatch, ledger, harness)
    cleanup_conn = _Connection(delete_count=0)
    ledger.connect = lambda: cleanup_conn
    with pytest.raises(SharedTestHarnessError, match="not exact"):
        ledger.cleanup()
    assert cleanup_conn.cursor_value.deleted == 1
    assert ledger._cleaned is False

def test_partial_event_creation_rolls_back_and_does_not_enter_cleanup(monkeypatch):
    harness, ledger, _ = _authenticated_ledger(monkeypatch)
    _issue_owned_checkout(monkeypatch, ledger, harness)
    runtime_db = _RuntimeDb((None, None))
    runtime_conn = _RuntimeConnection(runtime_db)
    monkeypatch.setattr(harness, "Db", lambda conn: conn.db)
    monkeypatch.setattr(
        harness.step_up_service,
        "write_consumed_event",
        lambda db, **kwargs: SimpleNamespace(
            event={
                "event_id": "00000000-0000-0000-0000-000000000003",
                "fingerprint": "e" * 64,
            },
            replayed=False,
        ),
    )
    ledger.connect = lambda: runtime_conn
    with pytest.raises(SharedTestHarnessError, match="verification failed"):
        ledger.write_consumed_evidence()
    assert runtime_conn.rollbacks == 1
    cleanup_conn = _Connection()
    ledger.connect = lambda: cleanup_conn
    ledger.cleanup()
    assert all(
        "security_events" not in sql
        for sql, _ in cleanup_conn.cursor_value.statements
        if sql.startswith("DELETE")
    )

def test_event_ownership_mismatch_prevents_delete_and_preserves_probe_error(
    monkeypatch,
):
    harness, ledger, _ = _authenticated_ledger(monkeypatch)
    _issue_owned_checkout(monkeypatch, ledger, harness)
    _capture_owned_consumed_event(monkeypatch, ledger, harness)
    mismatch = _Connection(owned=False)
    ledger.connect = lambda: mismatch
    with pytest.raises(ProbeAndCleanupError) as caught:
        with ledger:
            raise ValueError("probe failed")
    assert isinstance(caught.value.probe_error, ValueError)
    assert isinstance(caught.value.cleanup_error, SharedTestHarnessError)
    assert mismatch.cursor_value.deleted == 0

def test_authorized_shared_test_pending_probe_matrix():
    if os.environ.get(ACTIVATION_ENV) != "1":
        pytest.skip("shared TEST harness is not explicitly enabled")
    try:
        evidence = run_authorized_pending_probe_matrix()
    except Exception as error:
        raise AssertionError(
            f"sanitized shared TEST matrix failure: {type(error).__name__}") from None
    assert evidence["exact_reconciliation"] is True
    assert evidence["before"] == evidence["after"]
    assert evidence["proofs"] == {
        "binding_mismatch": "rejected",
        "replay": "rejected",
        "expiry": "expired",
        "mpin_generation_rotation": "invalidated",
        "wallet_funding_source_change": "rejected",
        "provider_rejection": "invalidated",
        "provider_ambiguity": "reconciliation_required",
        "evidence_replay": "idempotent",
        "deterministic_provider_calls": 2,
        "external_provider_calls": 0,
    }
    assert evidence["created_row_deltas"] == {
        "users": 1,
        "trusted_devices": 1,
        "user_sessions": 1,
        "mpin_credentials": 1,
        "mpin_step_up_authorizations": 6,
        "security_events": 2,
    }
