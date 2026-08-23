"""Targeted safety tests for the opt-in shared-TEST step-up harness."""
import pytest
from shared.payments import PaymentProviderRejected
from tests.shared_test_step_up_harness import (
    ACTIVATION_ENV, EXPECTED_PROJECT_REF, PROJECT_ENV, URL_ENV,
    SharedTestFixtureLedger, SharedTestHarnessError,
    deterministic_payout_provider, require_authorized_shared_test_url,
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
    def __init__(self, owned=True):
        self.owned = owned
        self.rowcount = 0
        self.deleted = 0
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=()):
        if sql.startswith("SELECT"):
            self._result = (1,) if self.owned else None
        elif sql.startswith("DELETE"):
            self.rowcount = 1
            self.deleted += 1
    def fetchone(self): return self._result

class _Connection:
    def __init__(self, owned=True):
        self.cursor_value = _Cursor(owned)
        self.commits = 0
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self.cursor_value
    def commit(self): self.commits += 1

def _owned(ledger):
    ledger._register_owned("users", "id", 7, "SELECT id FROM public.users WHERE id=%s", (7,))

def test_context_exit_cleans_and_repeated_cleanup_is_idempotent(monkeypatch):
    conn = _Connection()
    ledger = SharedTestFixtureLedger("fake")
    monkeypatch.setattr(ledger, "connect", lambda: conn)
    _owned(ledger)
    with ledger:
        pass
    ledger.cleanup()
    assert conn.cursor_value.deleted == 1
    assert ledger._cleaned is True

def test_probe_exception_is_preserved_after_successful_cleanup(monkeypatch):
    conn = _Connection()
    ledger = SharedTestFixtureLedger("fake")
    monkeypatch.setattr(ledger, "connect", lambda: conn)
    _owned(ledger)
    with pytest.raises(ValueError, match="probe failed"):
        with ledger:
            raise ValueError("probe failed")
    assert conn.cursor_value.deleted == 1

def test_cleanup_failure_surfaces_with_original_exception(monkeypatch):
    conn = _Connection(owned=False)
    ledger = SharedTestFixtureLedger("fake")
    monkeypatch.setattr(ledger, "connect", lambda: conn)
    _owned(ledger)
    with pytest.raises(ExceptionGroup) as caught:
        with ledger:
            raise ValueError("probe failed")
    assert any(isinstance(item, ValueError) for item in caught.value.exceptions)
    assert any(isinstance(item, SharedTestHarnessError) for item in caught.value.exceptions)

def test_arbitrary_registration_and_non_owned_delete_are_rejected(monkeypatch):
    ledger = SharedTestFixtureLedger("fake")
    assert not hasattr(ledger, "record")
    with pytest.raises(SharedTestHarnessError):
        ledger._register_owned("security_events", "id", 1, "SELECT 1", ())
    conn = _Connection(owned=False)
    monkeypatch.setattr(ledger, "connect", lambda: conn)
    _owned(ledger)
    with pytest.raises(SharedTestHarnessError):
        ledger.cleanup()
    assert conn.cursor_value.deleted == 0
    assert ledger._cleaned is False

def test_supported_owned_fixture_can_be_registered_and_cleaned(monkeypatch):
    conn = _Connection()
    ledger = SharedTestFixtureLedger("fake")
    monkeypatch.setattr(ledger, "connect", lambda: conn)
    ledger._register_owned("users", "id", 8, "SELECT id FROM public.users WHERE id=%s", (8,))
    ledger.cleanup()
    assert conn.cursor_value.deleted == 1
