"""Focused tests for the versioned commission-policy feature.

Pure calculation/validation tests run without a database. Tests that take the
`db`/`seeded_db` fixtures are PostgreSQL integration tests (see conftest.py)
and skip with a clear reason when TEST_SUPABASE_DB_URL is not configured.
"""

from decimal import Decimal

import psycopg2
import pytest

from shared import commissions
from shared.commissions import (
    POLICY_TYPE_AGREEMENT,
    POLICY_TYPE_ONE_TIME,
    changed_policy_types,
    get_active_policy,
    get_current_terms_version,
    has_acknowledged,
    list_policy_versions,
    list_terms_versions,
    parse_company_share_percent,
    policy_company_share,
    publish_commission_change,
    recalculate_payment_fields,
    record_acknowledgement,
    requires_acknowledgement,
    snapshot_company_share,
    split_final_amount,
    transporter_share_percent_for,
)

STAMP = "2026-07-21T12:00:00"


# ---------------------------------------------------------------------------
# 1. Defaults
# ---------------------------------------------------------------------------

def test_default_policies_are_independent_20_80(seeded_db):
    one_time = get_active_policy(seeded_db, POLICY_TYPE_ONE_TIME)
    agreement = get_active_policy(seeded_db, POLICY_TYPE_AGREEMENT)
    assert one_time["company_share_percent"] == 20.0
    assert one_time["transporter_share_percent"] == 80.0
    assert agreement["company_share_percent"] == 20.0
    assert agreement["transporter_share_percent"] == 80.0
    assert one_time["id"] != agreement["id"]
    assert one_time["version_number"] == 1
    assert agreement["version_number"] == 1


# ---------------------------------------------------------------------------
# 2. Non-admin protection (route guard)
# ---------------------------------------------------------------------------

def test_non_admin_users_cannot_pass_admin_guard():
    from flask import Flask
    from auth.helpers import require_admin_role

    app = Flask(__name__)
    with app.test_request_context():
        for role in ("service_seeker", "everyday_user", "logistics_provider", "shopkeeper", "", None):
            response = require_admin_role({"role": role})
            assert response is not None
            assert response.status_code == 403
        assert require_admin_role(None) is not None
        assert require_admin_role({"role": "platform_admin"}) is None


# ---------------------------------------------------------------------------
# 3. Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["15.5", 15.5, 0, "0", 99.99, "99.99", "20", 20])
def test_valid_company_share_accepted(value):
    parsed = parse_company_share_percent(value)
    assert Decimal("0") <= parsed < Decimal("100")


@pytest.mark.parametrize("value", [-1, "-0.01", 100, "100.00", 150, "15.555", "abc", "", None, True, float("nan"), float("inf")])
def test_invalid_company_share_rejected(value):
    with pytest.raises(ValueError):
        parse_company_share_percent(value)


def test_blank_change_summary_rejected(seeded_db):
    # The route rejects blank summaries before reaching the helper; the
    # database schema also enforces a non-blank summary via CHECK constraint.
    from shared.db import IntegrityError

    with pytest.raises(IntegrityError):
        commissions.create_policy_version(
            seeded_db, POLICY_TYPE_ONE_TIME, "15.00", "   ", None, STAMP,
        )


def test_transporter_share_always_derived():
    assert transporter_share_percent_for(Decimal("15.5")) == Decimal("84.50")
    assert transporter_share_percent_for(Decimal("0")) == Decimal("100.00")
    assert transporter_share_percent_for(Decimal("99.99")) == Decimal("0.01")


# ---------------------------------------------------------------------------
# 4/5. Independence of the two policy types
# ---------------------------------------------------------------------------

def test_one_time_change_does_not_affect_agreement(seeded_db):
    result = publish_commission_change(
        seeded_db, POLICY_TYPE_ONE_TIME, Decimal("15.50"), "Market adjustment.", 1, STAMP,
    )
    seeded_db.commit()
    assert result["new_policy"]["version_number"] == 2
    assert result["new_policy"]["company_share_percent"] == 15.5
    assert result["new_policy"]["transporter_share_percent"] == 84.5

    agreement = get_active_policy(seeded_db, POLICY_TYPE_AGREEMENT)
    assert agreement["company_share_percent"] == 20.0
    assert agreement["version_number"] == 1


def test_agreement_change_does_not_affect_one_time(seeded_db):
    publish_commission_change(
        seeded_db, POLICY_TYPE_AGREEMENT, Decimal("25.00"), "Agreement fee revision.", 1, STAMP,
    )
    seeded_db.commit()
    one_time = get_active_policy(seeded_db, POLICY_TYPE_ONE_TIME)
    assert one_time["company_share_percent"] == 20.0
    assert one_time["version_number"] == 1
    agreement = get_active_policy(seeded_db, POLICY_TYPE_AGREEMENT)
    assert agreement["company_share_percent"] == 25.0
    assert agreement["version_number"] == 2


def test_old_versions_remain_unchanged(seeded_db):
    publish_commission_change(
        seeded_db, POLICY_TYPE_ONE_TIME, Decimal("10.00"), "Promo rate.", 1, STAMP,
    )
    seeded_db.commit()
    versions = list_policy_versions(seeded_db, POLICY_TYPE_ONE_TIME)
    assert [v["version_number"] for v in versions] == [2, 1]
    assert versions[1]["company_share_percent"] == 20.0  # v1 untouched
    assert versions[0]["company_share_percent"] == 10.0


def test_publishing_same_rate_is_rejected(seeded_db):
    with pytest.raises(ValueError):
        publish_commission_change(
            seeded_db, POLICY_TYPE_ONE_TIME, Decimal("20.00"), "No-op.", 1, STAMP,
        )


# ---------------------------------------------------------------------------
# 6-9. Snapshots
# ---------------------------------------------------------------------------

def test_old_accepted_shipment_keeps_its_snapshot(seeded_db):
    # Shipment accepted under 20% keeps 20% even after the global rate changes.
    shipment = {"company_share_percent_snapshot": 20.0}
    publish_commission_change(
        seeded_db, POLICY_TYPE_ONE_TIME, Decimal("10.00"), "Rate cut.", 1, STAMP,
    )
    seeded_db.commit()
    company_fee, transporter_amount = split_final_amount(1000, snapshot_company_share(shipment))
    assert company_fee == 200.0
    assert transporter_amount == 800.0


def test_new_shipment_snapshots_new_active_policy(seeded_db):
    publish_commission_change(
        seeded_db, POLICY_TYPE_ONE_TIME, Decimal("12.50"), "New rate.", 1, STAMP,
    )
    seeded_db.commit()
    active = get_active_policy(seeded_db, POLICY_TYPE_ONE_TIME)
    assert policy_company_share(active) == Decimal("12.50")
    company_fee, transporter_amount = split_final_amount(1000, policy_company_share(active))
    assert company_fee == 125.0
    assert transporter_amount == 875.0


def test_existing_agreement_keeps_rate_for_future_payments(seeded_db):
    # Agreement finalized at 20%; the agreement setting later changes to 30%.
    agreement_snapshot = {"company_share_percent_snapshot": 20.0}
    publish_commission_change(
        seeded_db, POLICY_TYPE_AGREEMENT, Decimal("30.00"), "Fee increase.", 1, STAMP,
    )
    seeded_db.commit()
    # Future monthly payment for the OLD agreement still splits at 20/80.
    _, final_amount, company_fee, transporter_amount = recalculate_payment_fields(
        100, 50, 3000, snapshot_company_share(agreement_snapshot),
    )
    assert final_amount == 5000.0
    assert company_fee == 1000.0
    assert transporter_amount == 4000.0


def test_new_agreement_snapshots_new_active_policy(seeded_db):
    publish_commission_change(
        seeded_db, POLICY_TYPE_AGREEMENT, Decimal("30.00"), "Fee increase.", 1, STAMP,
    )
    seeded_db.commit()
    active = get_active_policy(seeded_db, POLICY_TYPE_AGREEMENT)
    _, final_amount, company_fee, transporter_amount = recalculate_payment_fields(
        100, 50, 3000, policy_company_share(active),
    )
    assert final_amount == 5000.0
    assert company_fee == 1500.0
    assert transporter_amount == 3500.0


def test_legacy_rows_without_snapshot_fall_back_to_20_80():
    # Mirrors the migration backfill: pre-feature rows behave as 20/80.
    assert snapshot_company_share({}) == Decimal("20.00")
    assert snapshot_company_share({"company_share_percent_snapshot": None}) == Decimal("20.00")
    company_fee, transporter_amount = split_final_amount(2500, None)
    assert company_fee == 500.0
    assert transporter_amount == 2000.0


# ---------------------------------------------------------------------------
# 10. Rounding
# ---------------------------------------------------------------------------

def test_fee_rounding_two_decimals():
    company_fee, transporter_amount = split_final_amount(3333.33, Decimal("17.50"))
    assert company_fee == 583.33  # 583.33275 rounds half-up to 583.33
    assert transporter_amount == 2750.00
    assert round(company_fee + transporter_amount, 2) == 3333.33

    company_fee, transporter_amount = split_final_amount(0.03, Decimal("20.00"))
    assert company_fee == 0.01
    assert transporter_amount == 0.02

    # Never binary-float drift: 0.1 + 0.2 style inputs stay exact.
    company_fee, transporter_amount = split_final_amount(4999.995, Decimal("20.00"))
    assert round(company_fee + transporter_amount, 2) == 5000.0


def test_recalculate_payment_fields_uses_guarantee_floor():
    total_earned, final_amount, company_fee, transporter_amount = recalculate_payment_fields(
        10, 50, 3000, Decimal("20.00"),
    )
    assert total_earned == 500.0
    assert final_amount == 3000.0  # minimum guarantee wins
    assert company_fee == 600.0
    assert transporter_amount == 2400.0


# ---------------------------------------------------------------------------
# 11. Terms versions
# ---------------------------------------------------------------------------

def test_every_rate_update_creates_terms_version(seeded_db):
    assert get_current_terms_version(seeded_db)["version_number"] == 1
    first = publish_commission_change(
        seeded_db, POLICY_TYPE_ONE_TIME, Decimal("15.00"), "One-time cut.", 1, STAMP,
    )
    second = publish_commission_change(
        seeded_db, POLICY_TYPE_AGREEMENT, Decimal("22.00"), "Agreement bump.", 1, STAMP,
    )
    seeded_db.commit()
    assert first["terms_version"]["version_number"] == 2
    assert second["terms_version"]["version_number"] == 3
    assert len(list_terms_versions(seeded_db)) == 3

    # Latest Terms references the new agreement policy AND the retained
    # (unchanged for that publish) one-time policy from the first change.
    latest = get_current_terms_version(seeded_db)
    assert latest["one_time_policy_id"] == first["new_policy"]["id"]
    assert latest["agreement_policy_id"] == second["new_policy"]["id"]

    changed = changed_policy_types(latest, first["terms_version"])
    assert changed == {POLICY_TYPE_AGREEMENT}


# ---------------------------------------------------------------------------
# 12/13. Review notice + acknowledgements
# ---------------------------------------------------------------------------

def test_review_notice_persists_until_acknowledged(seeded_db):
    result = publish_commission_change(
        seeded_db, POLICY_TYPE_ONE_TIME, Decimal("18.00"), "Adjustment.", 1, STAMP,
    )
    seeded_db.commit()
    terms = result["terms_version"]
    changed = {POLICY_TYPE_ONE_TIME}

    def needs_review(user_id):
        acknowledged = has_acknowledged(seeded_db, user_id, terms["id"])
        return requires_acknowledgement("service_seeker", terms["version_number"], changed, acknowledged)

    assert needs_review(7) is True
    assert needs_review(7) is True  # still shown until reviewed
    record_acknowledgement(seeded_db, 7, terms["id"], STAMP)
    seeded_db.commit()
    assert needs_review(7) is False


def test_acknowledgements_are_user_specific_and_idempotent(seeded_db):
    terms = get_current_terms_version(seeded_db)
    record_acknowledgement(seeded_db, 1, terms["id"], STAMP)
    record_acknowledgement(seeded_db, 1, terms["id"], STAMP)  # idempotent repeat
    seeded_db.commit()
    rows = seeded_db.execute(
        "SELECT COUNT(*) AS total FROM terms_acknowledgements WHERE user_id = 1"
    ).fetchone()
    assert rows["total"] == 1
    assert has_acknowledged(seeded_db, 1, terms["id"]) is True
    assert has_acknowledged(seeded_db, 2, terms["id"]) is False


def test_seed_version_never_requires_review():
    assert requires_acknowledgement("service_seeker", 1, set(), False) is False


def test_everyday_users_skip_agreement_only_changes():
    agreement_only = {POLICY_TYPE_AGREEMENT}
    one_time_only = {POLICY_TYPE_ONE_TIME}
    assert requires_acknowledgement("everyday_user", 2, agreement_only, False) is False
    assert requires_acknowledgement("everyday_user", 2, one_time_only, False) is True
    # Service seekers and transporters are notified for both change types.
    assert requires_acknowledgement("service_seeker", 2, agreement_only, False) is True
    assert requires_acknowledgement("logistics_provider", 2, agreement_only, False) is True
    # Unaffected roles are never targeted.
    assert requires_acknowledgement("shopkeeper", 2, one_time_only, False) is False
    assert requires_acknowledgement("platform_admin", 2, one_time_only, False) is False


# ---------------------------------------------------------------------------
# 14. PostgreSQL data-layer behaviour: RETURNING id, ON CONFLICT, rowcount
# ---------------------------------------------------------------------------

def test_insert_returning_id_yields_usable_generated_key(db):
    row = db.execute(
        "INSERT INTO commission_policies ("
        "    policy_type, version_number, company_share_percent,"
        "    transporter_share_percent, change_summary"
        ") VALUES (%s, 1, 20.00, 80.00, %s) RETURNING id",
        (POLICY_TYPE_ONE_TIME, "Baseline rate."),
    ).fetchone()
    assert row["id"] >= 1
    fetched = db.execute(
        "SELECT id, policy_type FROM commission_policies WHERE id = %s", (row["id"],)
    ).fetchone()
    assert fetched["id"] == row["id"]
    assert fetched["policy_type"] == POLICY_TYPE_ONE_TIME


def test_on_conflict_do_nothing_reports_rowcount_and_creates_no_duplicate(seeded_db):
    terms = get_current_terms_version(seeded_db)
    insert_sql = (
        "INSERT INTO terms_acknowledgements (user_id, terms_version_id, acknowledged_at) "
        "VALUES (%s, %s, %s) ON CONFLICT (user_id, terms_version_id) DO NOTHING"
    )
    first = seeded_db.execute(insert_sql, (5, terms["id"], STAMP))
    second = seeded_db.execute(insert_sql, (5, terms["id"], STAMP))
    assert first.rowcount == 1
    assert second.rowcount == 0  # conflict path: skipped, not duplicated
    total = seeded_db.execute(
        "SELECT COUNT(*) AS total FROM terms_acknowledgements WHERE user_id = 5"
    ).fetchone()
    assert total["total"] == 1


def test_update_rowcount_reflects_affected_rows(seeded_db):
    terms = get_current_terms_version(seeded_db)
    record_acknowledgement(seeded_db, 9, terms["id"], STAMP)
    hit = seeded_db.execute(
        "UPDATE terms_acknowledgements SET acknowledged_at = %s WHERE user_id = %s",
        (STAMP, 9),
    )
    assert hit.rowcount == 1
    miss = seeded_db.execute(
        "UPDATE terms_acknowledgements SET acknowledged_at = %s WHERE user_id = %s",
        (STAMP, 999),
    )
    assert miss.rowcount == 0


def test_published_versions_are_immutable_at_database_level(seeded_db):
    policy = get_active_policy(seeded_db, POLICY_TYPE_ONE_TIME)
    with pytest.raises(psycopg2.DatabaseError):
        seeded_db.execute(
            "UPDATE commission_policies SET company_share_percent = 1.00, "
            "transporter_share_percent = 99.00 WHERE id = %s",
            (policy["id"],),
        )


# ---------------------------------------------------------------------------
# 15. Backfill parity
# ---------------------------------------------------------------------------

def test_backfill_split_matches_legacy_hardcoded_behaviour():
    # The migration backfills 20/80; the fee produced for a backfilled row
    # must equal what the old hard-coded 0.20 code produced.
    for amount in (100, 999.99, 12345.67, 0.01):
        company_fee, transporter_amount = split_final_amount(amount, Decimal("20.00"))
        legacy_fee = round(amount * 0.20, 2)
        assert company_fee == pytest.approx(legacy_fee, abs=0.01)
        assert round(company_fee + transporter_amount, 2) == round(amount, 2)
