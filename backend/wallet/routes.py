from flask import Blueprint, request

from auth.helpers import json_response, login_required, csrf_error, timestamp_bundle
from shared.db import open_db
from shared.payments import (
    calculate_card_processing_fee,
    get_payment_provider,
    parse_money_amount,
    validate_dummy_card,
    validate_payout_card,
)
from .helpers import (
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


@wallet_blueprint.get("/api/wallet/earnings-summary")
@login_required
def earnings_summary():
    """Transporter earnings summary for the Earnings page."""
    from agreements.helpers import TRANSPORTER_AGREEMENT_ROLES
    user = request.current_user
    role = (user.get("role") or "").strip().lower()
    if role not in TRANSPORTER_AGREEMENT_ROLES:
        return json_response({"success": False, "message": "Transporter account required."}, 403)

    wallet, error = get_or_create_wallet(user)
    if error:
        return error

    with open_db() as db:
        # Total lifetime earnings from agreement payments
        lifetime_row = db.execute(
            """
            SELECT COALESCE(SUM(transporter_amount), 0) AS total
            FROM agreement_monthly_payments
            WHERE transporter_user_id = %s AND status = 'paid'
            """,
            (user["id"],),
        ).fetchone()

        # This month earnings
        current_month = __import__('datetime').date.today().strftime("%Y-%m")
        month_row = db.execute(
            """
            SELECT COALESCE(SUM(transporter_amount), 0) AS total
            FROM agreement_monthly_payments
            WHERE transporter_user_id = %s AND status = 'paid' AND month_year = %s
            """,
            (user["id"], current_month),
        ).fetchone()

        # Pending (payment due but not yet paid)
        pending_row = db.execute(
            """
            SELECT COALESCE(SUM(final_amount), 0) AS total
            FROM agreement_monthly_payments
            WHERE transporter_user_id = %s AND status = 'pending'
            """,
            (user["id"],),
        ).fetchone()

        # Completed trips count
        trips_row = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM agreement_trips
            WHERE transporter_user_id = %s AND status = 'completed'
            """,
            (user["id"],),
        ).fetchone()

        # Recent payment transactions (agreement_income type)
        tx_rows = db.execute(
            """
            SELECT * FROM wallet_transactions
            WHERE user_id = %s AND type = 'agreement_income'
            ORDER BY id DESC
            LIMIT 10
            """,
            (user["id"],),
        ).fetchall()

    transactions = [
        {
            "id": tx["id"],
            "amount": round_money(tx["amount"]),
            "description": tx["description"] or "",
            "reference_id": tx["reference_id"] or "",
            "created_at": tx["created_at"],
            "type": tx["type"],
        }
        for tx in tx_rows
    ]

    return json_response({
        "success": True,
        "wallet": serialize_wallet(wallet),
        "lifetime_earnings": round_money(lifetime_row["total"]),
        "month_earnings": round_money(month_row["total"]),
        "pending_earnings": round_money(pending_row["total"]),
        "completed_trips": int(trips_row["total"] or 0),
        "recent_transactions": transactions,
    })


@wallet_blueprint.post("/api/wallet/topup")
@login_required
def topup_wallet():
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    # Shared card validation: card data is checked in memory only and is
    # never persisted or logged.
    card_summary, card_error = validate_dummy_card(data)
    if card_error:
        return json_response({"success": False, "message": card_error}, 400)

    try:
        amount = float(parse_money_amount(data.get("amount"), "Amount"))
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    # Role-specific top-up semantics (explicit for backward compatibility):
    # - client/business wallets: the entered amount is the desired wallet
    #   credit. The card is charged amount + processing fee; the wallet is
    #   credited exactly the entered amount.
    # - transporter wallets: legacy gross semantics kept unchanged — the fee
    #   is deducted from the entered amount and the remainder is credited
    #   (the security-deposit/minimum rules depend on this behaviour).
    if wallet["role"] == "client":
        gateway_fee = calculate_card_processing_fee(amount)
        gross_amount = round_money(amount + gateway_fee)
        net_amount = amount
    else:
        gross_amount = amount
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

    # Dummy charge through the shared, replaceable provider interface.
    get_payment_provider().charge(gross_amount, card_summary=card_summary, description="Wallet top-up")

    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        current = db.execute("SELECT * FROM wallets WHERE user_id = %s", (request.current_user["id"],)).fetchone()
        wallet = dict(current) if current else wallet
        new_balance = round_money(wallet["balance"] + net_amount)
        is_minimum_met = bool(wallet["is_minimum_met"] or new_balance + 1e-9 >= wallet["minimum_required"])
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
            "UPDATE wallets SET is_minimum_met = %s, updated_at = %s WHERE id = %s AND user_id = %s",
            (is_minimum_met, stamp, wallet["id"], request.current_user["id"]),
        )
        wallet["is_minimum_met"] = is_minimum_met
        wallet["updated_at"] = stamp
        if should_restore_minimum_lock:
            target_lock = round_money(wallet["minimum_required"])
            lock_delta = round_money(target_lock - current_locked_balance)
            db.execute(
                "UPDATE wallets SET locked_balance = %s, updated_at = %s WHERE id = %s AND user_id = %s",
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
            WHERE user_id = %s AND wallet_id = %s
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (request.current_user["id"], wallet["id"], page_size, offset),
        ).fetchall()
        total_row = db.execute(
            "SELECT COUNT(*) AS total FROM wallet_transactions WHERE user_id = %s AND wallet_id = %s",
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
    err = csrf_error()
    if err:
        return err

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
    err = csrf_error()
    if err:
        return err

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
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Amount must be a valid number."}, 400)

    from wallet.withdrawal_limits import validate_withdrawal, get_limits, get_active_tier
    with open_db() as db:
        # request.current_user already carries the transporter_profiles fields
        # (withdrawal_tier, withdrawal_tier_expires_at) merged in by get_user_by_id.
        user_row = dict(request.current_user)
        error_msg = validate_withdrawal(db, user_row, wallet, amount)
        if error_msg:
            return json_response({"success": False, "message": error_msg}, 400)

        stamp = timestamp_bundle()
        rounded_amount = round_money(amount)
        limits = get_limits(user_row)
        active_tier = get_active_tier(user_row)
        within_limits = (
            rounded_amount <= limits["single_max"] and
            rounded_amount <= limits["daily_max"]
        )

        # Re-fetch wallet inside transaction for accuracy
        fresh_wallet = db.execute("SELECT * FROM wallets WHERE user_id = %s", (request.current_user["id"],)).fetchone()
        fresh_wallet = dict(fresh_wallet) if fresh_wallet else wallet

        if within_limits:
            # Auto-approve: deduct from balance only, preserve locked_balance
            new_balance = round_money(fresh_wallet["balance"] - rounded_amount)
            db.execute(
                "UPDATE wallets SET balance = %s, updated_at = %s WHERE user_id = %s",
                (new_balance, stamp["display"], request.current_user["id"]),
            )
            fresh_wallet["balance"] = new_balance
            db.execute(
                """
                INSERT INTO wallet_withdrawal_requests (user_id, amount, status, requested_at, resolved_at)
                VALUES (%s, %s, 'approved', %s, %s)
                """,
                (request.current_user["id"], rounded_amount, stamp["iso"], stamp["iso"]),
            )
            insert_wallet_transaction(
                db,
                fresh_wallet,
                request.current_user["id"],
                "withdrawal",
                -rounded_amount,
                description="Auto-approved withdrawal (within tier limit)",
                reference_id=f"tier_{active_tier}_auto",
            )
            db.commit()
            remaining = max(round_money(new_balance - 30000), 0)
            return json_response({
                "success": True,
                "auto_approved": True,
                "message": f"Rs {rounded_amount:,.0f} withdrawn successfully. Remaining withdrawable: Rs {remaining:,.0f}.",
                "withdrawn": rounded_amount,
                "remaining_withdrawable": remaining,
            })
        else:
            # Over tier limit → queue for admin approval
            db.execute(
                """
                INSERT INTO wallet_withdrawal_requests (user_id, amount, status, requested_at, resolved_at)
                VALUES (%s, %s, 'pending', %s, NULL)
                """,
                (request.current_user["id"], rounded_amount, stamp["iso"]),
            )
            db.commit()
            return json_response({
                "success": True,
                "auto_approved": False,
                "message": f"Rs {rounded_amount:,.0f} withdrawal request submitted. Admin approval required (amount exceeds tier limit).",
            })


@wallet_blueprint.get("/api/wallet/withdrawal-limits")
@login_required
def get_withdrawal_limits():
    """Return user's current withdrawal limits and tier info."""
    role_error = ensure_transporter_role()
    if role_error:
        return role_error

    from wallet.withdrawal_limits import TIERS, get_active_tier, get_limits, get_24h_withdrawn, max_withdrawable, PERMANENT_LOCK

    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    user_row = dict(request.current_user)
    with open_db() as db:
        withdrawn_24h = get_24h_withdrawn(db, request.current_user["id"])

    active_tier = get_active_tier(user_row)
    limits = get_limits(user_row)
    withdrawable = max_withdrawable(wallet)

    return json_response({
        "success": True,
        "active_tier": active_tier,
        "tier_expires_at": user_row.get("withdrawal_tier_expires_at"),
        "limits": limits,
        "withdrawn_24h": withdrawn_24h,
        "remaining_daily": round_money(limits["daily_max"] - withdrawn_24h),
        "max_withdrawable": withdrawable,
        "permanent_lock": PERMANENT_LOCK,
        "all_tiers": TIERS,
    })


@wallet_blueprint.post("/api/wallet/upgrade-limit")
@login_required
def upgrade_withdrawal_limit():
    """Purchase a withdrawal limit upgrade tier."""
    role_error = ensure_transporter_role()
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    from datetime import datetime, timedelta
    from wallet.withdrawal_limits import TIERS, PERMANENT_LOCK

    data = request.get_json(silent=True) or {}
    try:
        tier = int(data.get("tier"))
        duration = int(data.get("duration_years"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Invalid tier or duration."}, 400)

    if tier not in TIERS or tier == 0:
        return json_response({"success": False, "message": "Invalid tier selected."}, 400)
    if duration not in (3, 5):
        return json_response({"success": False, "message": "Duration must be 3 or 5 years."}, 400)

    tier_info = TIERS[tier]
    fee = round_money(tier_info["fee_3yr"] if duration == 3 else tier_info["fee_5yr"])
    days = 1095 if duration == 3 else 1825

    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    spendable = round_money(
        (wallet.get("balance") or 0) - (wallet.get("locked_balance") or 0)
    )
    if spendable + 1e-9 < fee:
        return json_response(
            {
                "success": False,
                "message": "Insufficient balance to purchase plan. Please top up your wallet.",
            },
            400,
        )

    expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    stamp = timestamp_bundle()["iso"]

    with open_db() as db:
        db.execute(
            "UPDATE wallets SET balance = balance - %s, updated_at = %s WHERE user_id = %s",
            (fee, stamp, request.current_user["id"]),
        )
        db.execute(
            """
            INSERT INTO wallet_transactions
            (wallet_id, user_id, type, amount, gross_amount, gateway_fee, description, reference_id, balance_after, created_at)
            SELECT id, user_id, 'plan_purchase', %s, %s, 0,
                   %s, %s, balance, %s
            FROM wallets WHERE user_id = %s
            """,
            (
                -fee,
                -fee,
                f"Withdrawal limit upgrade - Tier {tier} ({duration} years)",
                f"tier_{tier}_{duration}yr",
                stamp,
                request.current_user["id"],
            ),
        )
        db.execute(
            """
            INSERT INTO transporter_profiles (user_id, withdrawal_tier, withdrawal_tier_expires_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                withdrawal_tier = excluded.withdrawal_tier,
                withdrawal_tier_expires_at = excluded.withdrawal_tier_expires_at
            """,
            (request.current_user["id"], tier, expires_at),
        )
        db.commit()

    return json_response({
        "success": True,
        "message": f"Tier {tier} activated for {duration} years. New single limit: Rs {tier_info['single_max']:,.0f}.",
        "tier": tier,
        "expires_at": expires_at,
    })


@wallet_blueprint.get("/api/wallet/payout-card")
@login_required
def get_payout_card():
    role_error = ensure_transporter_role()
    if role_error:
        return role_error
    with open_db() as db:
        user = db.execute(
            "SELECT payout_card_brand, payout_card_last_four, payout_card_holder, "
            "payout_card_expiry, payout_card_bank FROM transporter_profiles WHERE user_id = %s",
            (request.current_user["id"],)
        ).fetchone()
    if not user or not user["payout_card_last_four"]:
        return json_response({"success": True, "card": None})
    return json_response({
        "success": True,
        "card": {
            "card_number_masked": "**** **** **** " + str(user["payout_card_last_four"]),
            "card_brand": user["payout_card_brand"] or "card",
            "card_holder": user["payout_card_holder"] or "",
            "card_expiry": user["payout_card_expiry"] or "",
            "bank": user["payout_card_bank"] or "",
        }
    })


@wallet_blueprint.post("/api/wallet/payout-card")
@login_required
def save_payout_card():
    """Store the payout destination as tokenized display data only.

    The full card number is validated in memory and immediately reduced to
    brand + last four + a generated provider token; it is never stored,
    logged or returned.
    """
    role_error = ensure_transporter_role()
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    summary, card_error = validate_payout_card(data)
    if card_error:
        return json_response({"success": False, "message": card_error}, 400)
    token = get_payment_provider().tokenize(summary)
    with open_db() as db:
        db.execute(
            """
            INSERT INTO transporter_profiles (
                user_id, payout_card_token, payout_card_brand, payout_card_last_four,
                payout_card_holder, payout_card_expiry, payout_card_bank
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                payout_card_token = excluded.payout_card_token,
                payout_card_brand = excluded.payout_card_brand,
                payout_card_last_four = excluded.payout_card_last_four,
                payout_card_holder = excluded.payout_card_holder,
                payout_card_expiry = excluded.payout_card_expiry,
                payout_card_bank = excluded.payout_card_bank
            """,
            (
                request.current_user["id"],
                token,
                summary["card_brand"],
                summary["card_last_four"],
                summary["card_holder"],
                summary["card_expiry"],
                summary["bank"],
            ),
        )
        db.commit()
    return json_response({"success": True, "message": "Payout card saved successfully."})
