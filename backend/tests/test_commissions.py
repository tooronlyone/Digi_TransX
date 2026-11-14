from decimal import Decimal

import pytest

from shared.commissions import (
    POLICY_TYPE_ONE_TIME,
    get_active_policy,
    get_current_terms_version,
    parse_company_share_percent,
    publish_commission_change,
    split_final_amount,
    transporter_share_percent_for,
)


def test_transporter_share_is_derived_from_company_share():
    assert transporter_share_percent_for(Decimal("20.00")) == Decimal("80.00")


@pytest.mark.parametrize("value", ["-1", "100", "15.555", "abc", "", None, True, "NaN", "Infinity"])
def test_invalid_company_share_is_rejected(value):
    with pytest.raises(ValueError):
        parse_company_share_percent(value)


@pytest.mark.parametrize("value,expected", [("0", Decimal("0.00")), ("15.5", Decimal("15.50")), ("99.99", Decimal("99.99"))])
def test_valid_company_share_is_normalized(value, expected):
    assert parse_company_share_percent(value) == expected


def test_fee_split_uses_decimal_safe_rounding():
    assert split_final_amount("100.03", "20.00") == (20.01, 80.02)


def test_seed_contains_only_one_time_policy(seeded_db):
    policy = get_active_policy(seeded_db, POLICY_TYPE_ONE_TIME)
    assert policy["company_share_percent"] == Decimal("20.00")
    rows = seeded_db.execute("SELECT policy_type FROM commission_policies").fetchall()
    assert [row["policy_type"] for row in rows] == [POLICY_TYPE_ONE_TIME]


def test_publish_creates_policy_and_matching_terms_version(seeded_db):
    result = publish_commission_change(
        seeded_db,
        POLICY_TYPE_ONE_TIME,
        Decimal("25.00"),
        "One-time fee revision.",
        1,
        "2026-11-14T00:00:00+00:00",
    )
    assert result["new_policy"]["version_number"] == 2
    assert result["new_policy"]["company_share_percent"] == Decimal("25.00")
    assert result["terms_version"]["one_time_policy_id"] == result["new_policy"]["id"]
    assert get_current_terms_version(seeded_db)["version_number"] == 2


def test_unknown_policy_type_is_rejected(seeded_db):
    with pytest.raises(ValueError, match="one_time_order"):
        publish_commission_change(
            seeded_db,
            "agreement",
            Decimal("25.00"),
            "Unsupported policy.",
            1,
            "2026-11-14T00:00:00+00:00",
        )
