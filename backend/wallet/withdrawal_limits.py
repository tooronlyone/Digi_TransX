"""
Withdrawal limit tiers and validation for Digi_TransX.
"""
from datetime import datetime, timedelta

from wallet.helpers import round_money


PERMANENT_LOCK = 30000.0

TIERS = {
    0: {"single_max": 300000.0, "daily_max": 1000000.0, "fee_3yr": 0.0, "fee_5yr": 0.0},
    1: {"single_max": 500000.0, "daily_max": 1500000.0, "fee_3yr": 20000.0, "fee_5yr": 28000.0},
    2: {"single_max": 700000.0, "daily_max": 3000000.0, "fee_3yr": 30000.0, "fee_5yr": 42000.0},
    3: {"single_max": 1000000.0, "daily_max": 6000000.0, "fee_3yr": 50000.0, "fee_5yr": 70000.0},
    4: {"single_max": 2000000.0, "daily_max": 12000000.0, "fee_3yr": 70000.0, "fee_5yr": 98000.0},
}


def get_active_tier(user_row) -> int:
    """Return user's active tier (0 if expired or none)."""
    tier = int(user_row.get("withdrawal_tier") or 0)
    if tier == 0:
        return 0
    expires_at = user_row.get("withdrawal_tier_expires_at")
    if not expires_at:
        return 0
    try:
        expiry = datetime.fromisoformat(str(expires_at))
        if datetime.now() > expiry:
            return 0
    except Exception:
        return 0
    return tier


def get_limits(user_row) -> dict:
    """Return active single_max and daily_max for user."""
    return TIERS[get_active_tier(user_row)]


def get_24h_withdrawn(db, user_id) -> float:
    """Sum of approved/pending withdrawals in last 24 hours."""
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    row = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM wallet_withdrawal_requests
        WHERE user_id = %s AND status IN ('pending', 'approved')
        AND requested_at >= %s
        """,
        (user_id, since),
    ).fetchone()
    return round_money(row["total"] if row else 0)


def max_withdrawable(wallet_row) -> float:
    """Max amount user can withdraw (total balance minus permanent lock)."""
    balance = round_money(wallet_row.get("balance") or 0)
    withdrawable = round_money(balance - PERMANENT_LOCK)
    return max(withdrawable, 0.0)


def validate_withdrawal(db, user_row, wallet_row, amount) -> str | None:
    """
    Validate a withdrawal request.
    Returns error string or None if valid.
    """
    amount = round_money(amount)
    limits = get_limits(user_row)

    withdrawable = max_withdrawable(wallet_row)
    if withdrawable <= 0:
        return "No withdrawable balance. Minimum Rs 30,000 security deposit must remain locked."

    if amount <= 0:
        return "Amount must be greater than 0."

    if amount > withdrawable:
        return f"Maximum withdrawable amount is Rs {withdrawable:,.0f} (balance minus Rs 30,000 security deposit)."

    if amount > limits["single_max"]:
        return f"Single withdrawal limit is Rs {limits['single_max']:,.0f}. Upgrade your limit to withdraw more."

    withdrawn_24h = get_24h_withdrawn(db, user_row["id"])
    remaining_daily = round_money(limits["daily_max"] - withdrawn_24h)
    if amount > remaining_daily:
        return f"Daily withdrawal limit reached. Remaining today: Rs {remaining_daily:,.0f}. Upgrade your limit or try tomorrow."

    return None
