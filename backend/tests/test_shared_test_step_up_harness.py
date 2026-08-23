"""Narrow safety tests for the opt-in shared-TEST step-up harness."""
import pytest
from shared.payments import PaymentProviderRejected
from tests.shared_test_step_up_harness import (
    ACTIVATION_ENV, EXPECTED_PROJECT_REF, PROJECT_ENV, URL_ENV,
    SharedTestHarnessError, deterministic_payout_provider,
    require_authorized_shared_test_url,
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
