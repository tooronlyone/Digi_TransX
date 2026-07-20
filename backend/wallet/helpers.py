from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from auth.helpers import json_response, timestamp_bundle
from shared.db import open_db


CLIENT_MINIMUM_REQUIRED = Decimal("20000")
TRANSPORTER_MINIMUM_REQUIRED = Decimal("30000")
GATEWAY_FEE_RATE = Decimal("0.025")
SUPPORTED_TOPUP_CARD_FIELDS = (
    "card_number",
    "card_expiry",
    "card_cvc",
    "card_holder_name",
)


def round_money(value):
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def normalize_wallet_role(user_role):
    role = (user_role or "").strip().lower()
    if role in {"client", "service_seeker", "everyday_user"}:
        return "client"
    if role in {"transporter", "logistics_provider"}:
        return "transporter"
    return None


def minimum_required_for_role(wallet_role):
    if wallet_role == "client":
        return round_money(CLIENT_MINIMUM_REQUIRED)
    if wallet_role == "transporter":
        return round_money(TRANSPORTER_MINIMUM_REQUIRED)
    return 0.0


def calculate_gateway_fee(gross_amount):
    gross = Decimal(str(gross_amount or 0))
    fee = (gross * GATEWAY_FEE_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = gross - fee
    return round_money(fee), round_money(net)


def calculate_required_gross_for_net(net_amount_needed):
    net = Decimal(str(max(net_amount_needed or 0, 0)))
    if net <= 0:
        return 0.0
    gross = (net / (Decimal("1") - GATEWAY_FEE_RATE)).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    fee, credited = calculate_gateway_fee(gross)
    while credited + 1e-9 < round_money(net):
        gross += Decimal("0.01")
        fee, credited = calculate_gateway_fee(gross)
    return round_money(gross)


def available_balance(wallet_row):
    return round_money((wallet_row.get("balance") or 0) - (wallet_row.get("locked_balance") or 0))


def serialize_wallet(wallet_row):
    balance = round_money(wallet_row.get("balance"))
    locked_balance = round_money(wallet_row.get("locked_balance"))
    return {
        "id": wallet_row.get("id"),
        "balance": balance,
        "locked_balance": locked_balance,
        "available_balance": round_money(balance - locked_balance),
        "minimum_required": round_money(wallet_row.get("minimum_required")),
        "is_minimum_met": bool(wallet_row.get("is_minimum_met")),
        "completed_trips_count": int(wallet_row.get("completed_trips_count") or 0),
        "role": wallet_row.get("role"),
        "created_at": wallet_row.get("created_at"),
        "updated_at": wallet_row.get("updated_at"),
    }


def get_or_create_wallet_for_user(db, user):
    wallet_role = normalize_wallet_role(user.get("role"))
    if not wallet_role:
        return None, json_response({"success": False, "message": "Wallet is not available for this account role."}, 403)

    row = db.execute("SELECT * FROM wallets WHERE user_id = ?", (user["id"],)).fetchone()
    if row:
        return dict(row), None

    stamp = timestamp_bundle()["display"]
    minimum_required = minimum_required_for_role(wallet_role)
    db.execute(
        """
        INSERT INTO wallets (
            user_id, role, balance, locked_balance, minimum_required, is_minimum_met, completed_trips_count, created_at, updated_at
        ) VALUES (?, ?, 0, 0, ?, false, 0, ?, ?)
        """,
        (user["id"], wallet_role, minimum_required, stamp, stamp),
    )
    row = db.execute("SELECT * FROM wallets WHERE user_id = ?", (user["id"],)).fetchone()
    return (dict(row) if row else None), None


def get_or_create_wallet(user):
    with open_db() as db:
        wallet, error = get_or_create_wallet_for_user(db, user)
        if error:
            return None, error
        db.commit()
        return wallet, None


def ensure_wallet_locked_balance(db, wallet, user_id, amount, reason="wallet_lock", reference_id=None):
    amount = round_money(amount)
    if amount <= 0:
        return json_response({"success": False, "message": "Amount must be greater than 0."}, 400)
    if available_balance(wallet) + 1e-9 < amount:
        return json_response({"success": False, "message": "Insufficient available balance"}, 400)

    stamp = timestamp_bundle()["display"]
    locked_balance = round_money(wallet["locked_balance"] + amount)
    db.execute(
        "UPDATE wallets SET locked_balance = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (locked_balance, stamp, wallet["id"], user_id),
    )
    wallet["locked_balance"] = locked_balance
    wallet["updated_at"] = stamp
    db.execute(
        """
        INSERT INTO wallet_transactions (
            wallet_id, user_id, type, amount, gross_amount, gateway_fee,
            description, reference_id, balance_after, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            wallet["id"],
            user_id,
            "lock",
            amount,
            None,
            0,
            reason or None,
            reference_id,
            round_money(wallet["balance"]),
            stamp,
        ),
    )
    return None


def insert_wallet_transaction(db, wallet, user_id, tx_type, amount, description="", reference_id=None, gross_amount=None, gateway_fee=0):
    stamp = timestamp_bundle()["display"]
    db.execute(
        """
        INSERT INTO wallet_transactions (
            wallet_id, user_id, type, amount, gross_amount, gateway_fee,
            description, reference_id, balance_after, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            wallet["id"],
            user_id,
            tx_type,
            round_money(amount),
            round_money(gross_amount) if gross_amount is not None else None,
            round_money(gateway_fee),
            description or None,
            reference_id,
            round_money(wallet["balance"]),
            stamp,
        ),
    )


def ensure_wallet_unlocked_balance(db, wallet, user_id, amount, reason="wallet_unlock", reference_id=None):
    amount = round_money(amount)
    if amount <= 0:
        return json_response({"success": False, "message": "Amount must be greater than 0."}, 400)
    if round_money(wallet["locked_balance"]) + 1e-9 < amount:
        return json_response({"success": False, "message": "Locked balance is lower than the requested amount"}, 400)

    stamp = timestamp_bundle()["display"]
    locked_balance = round_money(wallet["locked_balance"] - amount)
    db.execute(
        "UPDATE wallets SET locked_balance = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (locked_balance, stamp, wallet["id"], user_id),
    )
    wallet["locked_balance"] = locked_balance
    wallet["updated_at"] = stamp
    insert_wallet_transaction(
        db,
        wallet,
        user_id,
        "unlock",
        amount,
        description=reason,
        reference_id=reference_id,
    )
    return None


def adjust_wallet_balance(db, wallet, user_id, delta_amount, tx_type, description="", reference_id=None, gross_amount=None, gateway_fee=0):
    delta_amount = round_money(delta_amount)
    next_balance = round_money(wallet["balance"] + delta_amount)
    if next_balance < -1e-9:
        return json_response({"success": False, "message": "Insufficient wallet balance"}, 400)

    stamp = timestamp_bundle()["display"]
    db.execute(
        "UPDATE wallets SET balance = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (next_balance, stamp, wallet["id"], user_id),
    )
    wallet["balance"] = next_balance
    wallet["updated_at"] = stamp
    insert_wallet_transaction(
        db,
        wallet,
        user_id,
        tx_type,
        delta_amount,
        description=description,
        reference_id=reference_id,
        gross_amount=gross_amount,
        gateway_fee=gateway_fee,
    )
    return None
