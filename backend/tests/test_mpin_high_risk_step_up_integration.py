from pathlib import Path
import os
from urllib.parse import urlsplit

import psycopg2
import pytest

from auth import step_up_service
from tests._life_helpers import (
    STUBS,
    make_disposable,
    origin_main_schema_or_skip,
    require_test_db_url,
)


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20260801220000_mpin_step_up_high_risk_integration.sql"
WALLET_ROUTES = ROOT / "backend/wallet/routes.py"


def test_exact_six_category_a_actions_and_security_extension():
    category_a = set(step_up_service.ACTION_POLICIES) - {"security.logout_all"}
    assert category_a == {
        "one_time.checkout.wallet_only",
        "wallet.withdrawal.request",
        "wallet.withdrawal_limit.purchase",
        "wallet.payout_destination.replace",
        "agreement.finalize",
        "client.delivery.confirm_release",
    }
    logout_all = step_up_service.normalize_descriptor({
        "action_key": "security.logout_all",
        "resource_type": "account_security",
        "resource_id": 1,
    })
    assert step_up_service.public_descriptor(logout_all) == {
        "action_key": "security.logout_all",
        "resource_type": "account_security",
        "resource_id": 1,
    }
    base = {
        "action_key": "one_time.checkout.wallet_only",
        "resource_type": "order",
        "resource_id": 9,
        "amount_minor": 100,
        "currency": "PKR",
    }
    with pytest.raises(step_up_service.StepUpError):
        step_up_service.normalize_descriptor(base)
    with pytest.raises(step_up_service.StepUpError):
        step_up_service.normalize_descriptor({**base, "funding_source": "card"})
    descriptor = step_up_service.normalize_descriptor(
        {**base, "funding_source": "wallet"}
    )
    assert descriptor["funding_source"] == "wallet"


def test_money_and_destination_fingerprints_are_canonical_and_non_raw():
    assert step_up_service.money_to_minor("1.005") == 101
    with pytest.raises(step_up_service.StepUpError):
        step_up_service.money_to_minor(0)
    first = step_up_service.payout_destination_input_fingerprint({
        "card_number": "4111 1111 1111 1111",
        "card_holder": "  A   User ",
        "card_expiry": "12/30",
        "bank": " Example   Bank ",
    })
    second = step_up_service.payout_destination_input_fingerprint({
        "card_number": "4111111111111111",
        "card_holder": "A User",
        "card_expiry": "12/2030",
        "bank": "Example Bank",
    })
    assert first == second
    assert len(first) == 64
    assert "4111111111111111" not in first


def test_forward_migration_is_single_bounded_activation():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "add column if not exists funding_source text" in sql
    assert "security.mpin.step_up_consumed" in sql
    assert "security.mpin.step_up_reconciliation_required" in sql
    assert "where integrated) <> 25" in sql
    for forbidden in ("create table public.users", "insert into public.security_events", "insert into public.mpin_step_up_authorizations"):
        assert forbidden not in sql


def test_payout_provider_boundary_has_no_open_database_during_io_and_three_outcomes():
    source = WALLET_ROUTES.read_text(encoding="utf-8")
    claim_commit = source.index("db.commit()", source.index("def save_payout_card"))
    provider_call = source.index("get_payment_provider().tokenize(summary)", claim_commit)
    final_database = source.index("with open_db() as db:", provider_call)
    assert claim_commit < provider_call < final_database
    boundary = source[claim_commit:final_database]
    assert "with open_db()" not in boundary
    assert "except PaymentProviderRejected" in source
    assert "provider_rejected=True" in source
    assert "_mark_payout_reconciliation" in source
    assert "lock_and_finalize_current_request_claim" in source
    assert "reconcile_claim_after_uncertain_outcome" in source
    assert '"code": "reconciliation_required"' in source
    assert "_payout_reconciliation_response()" in source
    for forbidden in ("str(exc)", "repr(exc)", "authorization_proof", "card_number"):
        assert forbidden not in source[source.index("except PaymentProviderRejected"):]


def test_high_risk_migration_reapplies_only_from_complete_final_state_and_rejects_corruption():
    base = require_test_db_url()
    parsed = urlsplit(base)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert base != os.environ.get("SUPABASE_DB_URL", "").strip()
    migration = MIGRATION.read_text(encoding="utf-8")
    child, cleanup = make_disposable(
        base, STUBS, origin_main_schema_or_skip(), migration
    )
    try:
        with psycopg2.connect(child) as conn:
            with conn.cursor() as cursor:
                cursor.execute(migration)
                cursor.execute(migration)
                cursor.execute(
                    "select count(*),count(*) filter(where integrated),"
                    "count(*) filter(where lifecycle_status='planned' and not integrated),"
                    "count(*) filter(where writable and not integrated) "
                    "from public.canonical_event_catalog_projection"
                )
                assert cursor.fetchone() == (172, 25, 139, 133)
                cursor.execute(
                    "update public.canonical_event_catalog_projection "
                    "set integrated=false "
                    "where event_name='security.mpin.step_up_consumed'"
                )
            conn.commit()
            with pytest.raises(psycopg2.errors.ObjectNotInPrerequisiteState):
                with conn.cursor() as cursor:
                    cursor.execute(migration)
            conn.rollback()
            with conn.cursor() as cursor:
                cursor.execute(
                    "select count(*) filter(where integrated) "
                    "from public.canonical_event_catalog_projection"
                )
                assert cursor.fetchone()[0] == 24
    finally:
        cleanup()
