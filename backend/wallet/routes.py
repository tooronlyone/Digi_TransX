from flask import Blueprint, request

from auth.helpers import json_response, login_required, require_csrf, timestamp_bundle
from shared.db import open_db
from .helpers import (
    SUPPORTED_TOPUP_CARD_FIELDS,
    adjust_wallet_balance,
    available_balance,
    calculate_gateway_fee,
    calculate_required_gross_for_net,
    ensure_wallet_locked_balance,
    ensure_wallet_unlocked_balance,
    get_or_create_wallet,
    get_or_create_wallet_for_user,
    insert_wallet_transaction,
    round_money,
    serialize_wallet,
)


wallet_blueprint = Blueprint("wallet", __name__)


def ensure_transporter_role():
    role = (request.current_user.get("role") or "").strip().lower()
    if role not in {"transporter", "logistics_provider"}:
        return json_response({"success": False, "message": "Transporter account required."}, 403)
    return None


@wallet_blueprint.get("/api/wallet")
@login_required
def get_wallet():
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error
    return json_response({"success": True, "wallet": serialize_wallet(wallet)})


@wallet_blueprint.post("/api/wallet/topup")
@login_required
def topup_wallet():
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    for field in SUPPORTED_TOPUP_CARD_FIELDS:
        if not str(data.get(field) or "").strip():
            return json_response({"success": False, "message": f"{field.replace('_', ' ').title()} is required."}, 400)

    try:
        gross_amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Amount must be a valid number."}, 400)

    if gross_amount <= 0:
        return json_response({"success": False, "message": "Amount must be greater than 0."}, 400)

    gateway_fee, net_amount = calculate_gateway_fee(gross_amount)
    projected_balance = round_money(wallet["balance"] + net_amount)
    if not wallet["is_minimum_met"] and projected_balance + 1e-9 < wallet["minimum_required"]:
        net_shortfall = round_money(wallet["minimum_required"] - wallet["balance"])
        required_gross = calculate_required_gross_for_net(net_shortfall)
        return json_response(
            {
                "success": False,
                "message": f"Minimum balance of Rs {wallet['minimum_required']:.2f} required. Please add at least Rs {required_gross:.2f} to meet the minimum.",
            },
            400,
        )

    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        current = db.execute("SELECT * FROM wallets WHERE user_id = ?", (request.current_user["id"],)).fetchone()
        wallet = dict(current) if current else wallet
        new_balance = round_money(wallet["balance"] + net_amount)
        is_minimum_met = 1 if wallet["is_minimum_met"] or new_balance + 1e-9 >= wallet["minimum_required"] else 0
        current_locked_balance = round_money(wallet["locked_balance"])
        should_restore_minimum_lock = (
            wallet["role"] == "transporter"
            and new_balance + 1e-9 >= wallet["minimum_required"]
            and current_locked_balance + 1e-9 < round_money(wallet["minimum_required"])
        )
        balance_error = adjust_wallet_balance(
            db,
            wallet,
            request.current_user["id"],
            net_amount,
            "topup",
            description="Wallet top-up",
            gross_amount=gross_amount,
            gateway_fee=gateway_fee,
        )
        if balance_error:
            db.rollback()
            return balance_error
        db.execute(
            "UPDATE wallets SET is_minimum_met = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (is_minimum_met, stamp, wallet["id"], request.current_user["id"]),
        )
        wallet["is_minimum_met"] = is_minimum_met
        wallet["updated_at"] = stamp
        if should_restore_minimum_lock:
            target_lock = round_money(wallet["minimum_required"])
            lock_delta = round_money(target_lock - current_locked_balance)
            db.execute(
                "UPDATE wallets SET locked_balance = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (target_lock, stamp, wallet["id"], request.current_user["id"]),
            )
            wallet["locked_balance"] = target_lock
            wallet["updated_at"] = stamp
            insert_wallet_transaction(
                db,
                wallet,
                request.current_user["id"],
                "lock",
                lock_delta,
                description="Transporter minimum security deposit locked",
                reference_id="minimum_security_deposit",
            )
        db.commit()

    return json_response(
        {
            "success": True,
            "message": "Wallet topped up successfully",
            "transaction": {
                "gross_amount": round_money(gross_amount),
                "gateway_fee": gateway_fee,
                "net_amount": net_amount,
                "new_balance": new_balance,
            },
        }
    )


@wallet_blueprint.get("/api/wallet/transactions")
@login_required
def wallet_transactions():
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.args.get("page_size", 20))
    except (TypeError, ValueError):
        page_size = 20
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size

    with open_db() as db:
        rows = db.execute(
            """
            SELECT * FROM wallet_transactions
            WHERE user_id = ? AND wallet_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (request.current_user["id"], wallet["id"], page_size, offset),
        ).fetchall()
        total_row = db.execute(
            "SELECT COUNT(*) AS total FROM wallet_transactions WHERE user_id = ? AND wallet_id = ?",
            (request.current_user["id"], wallet["id"]),
        ).fetchone()

    transactions = []
    for row in rows:
        tx = dict(row)
        transactions.append(
            {
                "id": tx["id"],
                "type": tx["type"],
                "amount": round_money(tx["amount"]),
                "gross_amount": round_money(tx["gross_amount"]) if tx["gross_amount"] is not None else None,
                "gateway_fee": round_money(tx["gateway_fee"]),
                "description": tx["description"] or "",
                "reference_id": tx["reference_id"] or "",
                "balance_after": round_money(tx["balance_after"]),
                "created_at": tx["created_at"],
            }
        )

    return json_response(
        {
            "success": True,
            "transactions": transactions,
            "page": page,
            "page_size": page_size,
            "total": int(total_row["total"] or 0),
        }
    )


@wallet_blueprint.post("/api/wallet/lock")
@login_required
def lock_wallet_balance():
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Amount must be a valid number."}, 400)

    if amount <= 0:
        return json_response({"success": False, "message": "Amount must be greater than 0."}, 400)

    if available_balance(wallet) + 1e-9 < amount:
        return json_response({"success": False, "message": "Insufficient available balance"}, 400)

    reason = (data.get("reason") or "").strip() or "wallet_lock"
    with open_db() as db:
        lock_error = ensure_wallet_locked_balance(
            db,
            wallet,
            request.current_user["id"],
            amount,
            reason=reason,
            reference_id=(data.get("reference_id") or None),
        )
        if lock_error:
            db.rollback()
            return lock_error
        db.commit()

    return json_response({"success": True, "wallet": serialize_wallet(wallet)})


@wallet_blueprint.post("/api/wallet/unlock")
@login_required
def unlock_wallet_balance():
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Amount must be a valid number."}, 400)

    if amount <= 0:
        return json_response({"success": False, "message": "Amount must be greater than 0."}, 400)

    if round_money(wallet["locked_balance"]) + 1e-9 < amount:
        return json_response({"success": False, "message": "Locked balance is lower than the requested amount"}, 400)

    reason = (data.get("reason") or "").strip() or "wallet_unlock"
    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        unlock_error = ensure_wallet_unlocked_balance(
            db,
            wallet,
            request.current_user["id"],
            amount,
            reason=reason,
        )
        if unlock_error:
            db.rollback()
            return unlock_error
        db.commit()

    return json_response({"success": True, "wallet": serialize_wallet(wallet)})


@wallet_blueprint.post("/api/wallet/withdraw-locked")
@login_required
def create_locked_withdrawal_request():
    role_error = ensure_transporter_role()
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Amount must be a valid number."}, 400)
    if amount <= 0:
        return json_response({"success": False, "message": "Amount must be greater than 0."}, 400)
    if round_money(amount) - round_money(wallet["locked_balance"]) > 1e-9:
        return json_response({"success": False, "message": "Requested amount exceeds your locked balance."}, 400)

    stamp = timestamp_bundle()["iso"]
    with open_db() as db:
        db.execute(
            """
            INSERT INTO wallet_withdrawal_requests (user_id, amount, status, requested_at, resolved_at)
            VALUES (?, ?, 'pending', ?, NULL)
            """,
            (request.current_user["id"], round_money(amount), stamp),
        )
        db.commit()

    return json_response(
        {"success": True, "message": "Withdrawal request submitted, pending admin approval."}
    )


@wallet_blueprint.post("/api/wallet/withdrawal-requests/<int:request_id>/approve")
@login_required
def approve_locked_withdrawal_request(request_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    stamp = timestamp_bundle()
    with open_db() as db:
        withdrawal_request = db.execute(
            "SELECT * FROM wallet_withdrawal_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if not withdrawal_request:
            return json_response({"success": False, "message": "Withdrawal request not found."}, 404)

        withdrawal_request = dict(withdrawal_request)
        if withdrawal_request["status"] != "pending":
            return json_response({"success": False, "message": "Withdrawal request is already resolved."}, 400)

        user_row = db.execute("SELECT id, role FROM users WHERE id = ?", (withdrawal_request["user_id"],)).fetchone()
        if not user_row:
            return json_response({"success": False, "message": "Withdrawal request user not found."}, 404)

        wallet, error = get_or_create_wallet_for_user(db, dict(user_row))
        if error:
            return error

        amount = round_money(withdrawal_request["amount"])
        if round_money(wallet["locked_balance"]) + 1e-9 < amount:
            return json_response({"success": False, "message": "Locked balance is lower than the requested withdrawal amount."}, 400)
        if round_money(wallet["balance"]) + 1e-9 < amount:
            return json_response({"success": False, "message": "Wallet balance is lower than the requested withdrawal amount."}, 400)

        wallet["locked_balance"] = round_money(wallet["locked_balance"] - amount)
        wallet["balance"] = round_money(wallet["balance"] - amount)
        db.execute(
            """
            UPDATE wallets
            SET locked_balance = ?, balance = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (wallet["locked_balance"], wallet["balance"], stamp["display"], wallet["id"], wallet["user_id"]),
        )
        db.execute(
            """
            UPDATE wallet_withdrawal_requests
            SET status = 'approved', resolved_at = ?
            WHERE id = ?
            """,
            (stamp["iso"], request_id),
        )
        insert_wallet_transaction(
            db,
            wallet,
            withdrawal_request["user_id"],
            "withdrawal",
            -amount,
            description="Approved locked withdrawal",
            reference_id=str(request_id),
        )
        db.commit()

    return json_response({"success": True, "message": "Withdrawal request approved."})
