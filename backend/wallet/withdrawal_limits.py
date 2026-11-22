"""
Withdrawal limit tiers and validation for Digi_TransX.
All internal financial arithmetic uses exact quantized Decimal values.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from wallet.helpers import round_money, security_deposit_floor


PERMANENT_LOCK_DECIMAL = Decimal("30000.00")
PERMANENT_LOCK = float(PERMANENT_LOCK_DECIMAL)

TIERS_DECIMAL = {
    0: {
        "single_max": Decimal("300000.00"),
        "daily_max": Decimal("1000000.00"),
        "fee_3yr": Decimal("0.00"),
        "fee_5yr": Decimal("0.00"),
    },
    1: {
        "single_max": Decimal("500000.00"),
        "daily_max": Decimal("1500000.00"),
        "fee_3yr": Decimal("20000.00"),
        "fee_5yr": Decimal("28000.00"),
    },
    2: {
        "single_max": Decimal("700000.00"),
        "daily_max": Decimal("3000000.00"),
        "fee_3yr": Decimal("30000.00"),
        "fee_5yr": Decimal("42000.00"),
    },
    3: {
        "single_max": Decimal("1000000.00"),
        "daily_max": Decimal("6000000.00"),
        "fee_3yr": Decimal("50000.00"),
        "fee_5yr": Decimal("70000.00"),
    },
    4: {
        "single_max": Decimal("2000000.00"),
        "daily_max": Decimal("12000000.00"),
        "fee_3yr": Decimal("70000.00"),
        "fee_5yr": Decimal("98000.00"),
    },
}

TIERS = {
    tier: {k: float(v) for k, v in cfg.items()}
    for tier, cfg in TIERS_DECIMAL.items()
}


def _to_decimal(value) -> Decimal:
    if value is None or isinstance(value, bool):
        return Decimal("0.00")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")
    if not dec.is_finite():
        return Decimal("0.00")
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_active_tier(user_row) -> int:
    """Return user's active tier (0 if expired or none)."""
    try:
        tier = int(user_row.get("withdrawal_tier") or 0)
    except (TypeError, ValueError):
        return 0
    if tier not in TIERS_DECIMAL or tier == 0:
        return 0
    expires_at = user_row.get("withdrawal_tier_expires_at")
    if not expires_at:
        return 0
    try:
        expiry = datetime.fromisoformat(str(expires_at))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expiry:
            return 0
    except (TypeError, ValueError):
        return 0
    return tier


def get_limits_decimal(user_row) -> dict:
    """Return active Decimal tier limits for user."""
    return TIERS_DECIMAL[get_active_tier(user_row)]


def get_limits(user_row) -> dict:
    """Return active single_max and daily_max floats for JSON compatibility."""
    return TIERS[get_active_tier(user_row)]


def tier_fee_decimal(tier: int, duration_years: int) -> Decimal:
    """Return exact Decimal fee for a valid upgrade tier and duration."""
    cfg = TIERS_DECIMAL[tier]
    return cfg["fee_3yr"] if duration_years == 3 else cfg["fee_5yr"]


def pending_withdrawal_total(db, user_id, *, exclude_request_id=None) -> Decimal:
    """Return sum of unresolved pending withdrawal requests for a user."""
    if exclude_request_id is not None:
        row = db.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM wallet_withdrawal_requests
            WHERE user_id = %s AND status = 'pending' AND id <> %s
            """,
            (user_id, exclude_request_id),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM wallet_withdrawal_requests
            WHERE user_id = %s AND status = 'pending'
            """,
            (user_id,),
        ).fetchone()
    if not row or "total" not in row:
        return Decimal("0.00")
    return max(Decimal("0.00"), _to_decimal(row["total"]))


def get_24h_withdrawn_decimal(db, user_id) -> Decimal:
    """Exact Decimal sum of approved/pending withdrawals in last 24 hours."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    row = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM wallet_withdrawal_requests
        WHERE user_id = %s AND status IN ('pending', 'approved')
        AND requested_at >= %s
        """,
        (user_id, since),
    ).fetchone()
    if not row or "total" not in row:
        return Decimal("0.00")
    return max(Decimal("0.00"), _to_decimal(row["total"]))


def get_24h_withdrawn(db, user_id) -> float:
    """Sum of approved/pending withdrawals in last 24 hours."""
    return round_money(get_24h_withdrawn_decimal(db, user_id))


def max_withdrawable_decimal(wallet_row, *, pending_total=Decimal("0.00")) -> Decimal:
    """Protect live holds, security deposit floor, and existing pending withdrawals."""
    if not wallet_row:
        return Decimal("0.00")
    try:
        balance = Decimal(str(wallet_row.get("balance") or 0))
        locked = Decimal(str(wallet_row.get("locked_balance") or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")
    if not balance.is_finite() or not locked.is_finite():
        return Decimal("0.00")
    floor = max(PERMANENT_LOCK_DECIMAL, security_deposit_floor(wallet_row), locked)
    available = balance - floor - _to_decimal(pending_total)
    return max(Decimal("0.00"), available).quantize(Decimal("0.01"))


def max_withdrawable(wallet_row, *, pending_total=Decimal("0.00")) -> float:
    """Float projection of exact max withdrawable balance for API serialization."""
    return float(max_withdrawable_decimal(wallet_row, pending_total=pending_total))


def validate_withdrawal(db, user_row, wallet_row, amount) -> str | None:
    """Validate a withdrawal request using exact Decimal arithmetic.

    Returns error string or None if valid.
    """
    try:
        amount_dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return "Amount must be a valid number."
    if not amount_dec.is_finite() or amount_dec <= Decimal("0.00"):
        return "Amount must be greater than 0."

    limits = get_limits_decimal(user_row)
    pending_total = pending_withdrawal_total(db, user_row["id"])
    withdrawable = max_withdrawable_decimal(wallet_row, pending_total=pending_total)
    if withdrawable <= Decimal("0.00"):
        return (
            "No withdrawable balance available. "
            "Minimum Rs 30,000 security deposit and pending withdrawals must remain covered."
        )

    if amount_dec > withdrawable:
        return (
            f"Maximum withdrawable amount is Rs {float(withdrawable):,.0f} "
            "(balance minus Rs 30,000 security deposit and pending withdrawals)."
        )

    if amount_dec > limits["single_max"]:
        return f"Single withdrawal limit is Rs {float(limits['single_max']):,.0f}. Upgrade your limit to withdraw more."

    withdrawn_24h = get_24h_withdrawn_decimal(db, user_row["id"])
    remaining_daily = max(Decimal("0.00"), limits["daily_max"] - withdrawn_24h)
    if amount_dec > remaining_daily:
        return f"Daily withdrawal limit reached. Remaining today: Rs {float(remaining_daily):,.0f}. Upgrade your limit or try tomorrow."

    return None
