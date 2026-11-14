import uuid
from datetime import datetime,timezone
from decimal import Decimal

from flask import Blueprint, current_app, request

from auth import step_up_service
from auth.helpers import json_response, login_required, csrf_error, timestamp_bundle
from shared.db import open_db
from shared.payments import (
    CheckoutError,
    DummyCardProvider,
    PaymentProviderRejected,
    get_payment_provider,
    perform_wallet_topup,
    parse_money_amount,
    validate_payout_card,
)
from .helpers import (
    available_balance,
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


def _step_up_request_id(action_key):
    return f"{action_key}.{uuid.uuid4().hex}"


def _withdrawal_simulator_enabled():
    """Only explicitly selected local/test money may use the legacy simulator."""
    try:
        return isinstance(get_payment_provider(), DummyCardProvider)
    except CheckoutError:
        return False


def _mark_payout_reconciliation(gate, descriptor, request_id):
    with open_db() as db:
        reconciled = step_up_service.reconcile_claim_after_uncertain_outcome(
            db, gate=gate, descriptor=descriptor
        )
        if not reconciled:
            raise RuntimeError("Exact payout claim could not be reconciled.")
        step_up_service.write_reconciliation_event(
            db, request_id=request_id, gate=gate, descriptor=descriptor
        )
        db.commit()
        return reconciled["observed_state"]


def _payout_reconciliation_response():
    return json_response(
        {
            "success": False,
            "code": "reconciliation_required",
            "message": "Payout destination outcome requires reconciliation.",
        },
        503,
    )


def _mark_payout_rejected(gate):
    with open_db() as db:
        step_up_service.finalize_claim(
            db,
            authorization_id=gate.authorization["authorization_id"],
            raw_claim=gate.claim_proof,
            provider_rejected=True,
        )
        db.commit()


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
    user = request.current_user
    role = (user.get("role") or "").strip().lower()
    if role not in {"transporter", "logistics_provider"}:
        return json_response({"success": False, "message": "Transporter account required."}, 403)

    wallet, error = get_or_create_wallet(user)
    if error:
        return error

    with open_db() as db:
        order_lifetime_row = db.execute_exact(
            """
            SELECT COALESCE(SUM(transporter_amount), 0) AS total
            FROM payments
            WHERE transporter_user_id = %s AND status = 'released' AND business_rules_version IS NULL
            """,
            (user["id"],),
        ).fetchone()

        # This month earnings
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        order_month_row = db.execute_exact(
            """
            SELECT COALESCE(SUM(transporter_amount), 0) AS total
            FROM payments
            WHERE transporter_user_id = %s AND status = 'released' AND business_rules_version IS NULL AND TO_CHAR(released_at, 'YYYY-MM') = %s
            """,
            (user["id"], current_month),
        ).fetchone()

        # Pending (payment held/due but not yet released)
        order_pending_row = db.execute_exact(
            """
            SELECT COALESCE(SUM(transporter_amount), 0) AS total
            FROM payments
            WHERE transporter_user_id = %s AND status = 'held' AND business_rules_version IS NULL
            """,
            (user["id"],),
        ).fetchone()

        from .earnings import versioned_freight_earnings,legacy_fuel_recovery_totals
        freight=versioned_freight_earnings(db,user['id'],current_month)
        legacy_recovery=legacy_fuel_recovery_totals(db,user['id'],current_month)

        # Completed one-time shipment trips.
        order_trips_row = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM shipment_trips
            WHERE transporter_user_id = %s AND status = 'completed'
            """,
            (user["id"],),
        ).fetchone()

        # Recent shipment payment transactions.
        tx_rows = db.execute(
            """
            SELECT * FROM wallet_transactions
            WHERE user_id = %s AND type IN ('order_payout','freight_tranche1','freight_tranche2','reserve_contribution')
            ORDER BY id DESC
            LIMIT 10
            """,
            (user["id"],),
        ).fetchall()

    lifetime_total = round_money((order_lifetime_row["total"] if order_lifetime_row else Decimal('0'))+freight['lifetime_credited']-legacy_recovery['total'])
    month_total = round_money((order_month_row["total"] if order_month_row else Decimal('0'))+freight['month_credited']-legacy_recovery['month'])
    pending_total = round_money((order_pending_row["total"] if order_pending_row else Decimal('0'))+freight['pending'])
    completed_trips = int(order_trips_row["total"] if order_trips_row else 0)

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
        "lifetime_earnings": lifetime_total,
        "month_earnings": month_total,
        "pending_earnings": pending_total,
        "completed_trips": completed_trips,
        "recent_transactions": transactions,
        "freight_earnings_basis":'Actual wallet credits, including approved reserve credits; pending contains only unreleased earnings. Fuel-credit recovery is reported separately.',
        "freight_net_entitlement_before_adjustments":format(freight['net_entitlement'],'.2f'),
        "freight_fuel_credit_recovered":format(freight['fuel_credit_recovered'],'.2f'),
        "legacy_fuel_credit_recovered":format(legacy_recovery['total'],'.2f'),
        "total_fuel_credit_recovered":format(freight['fuel_credit_recovered']+legacy_recovery['total'],'.2f'),
        "freight_reserve_contributed":format(freight['reserve_contributed'],'.2f'),
    })


@wallet_blueprint.post("/api/wallet/topup")
@login_required
def topup_wallet():
    """HTTP wrapper around the atomic wallet top-up service.

    Handles CSRF/auth/input; the whole atomic operation — key validation,
    replay/conflict detection, provider charge and wallet credit — lives in
    the shared payment service (perform_wallet_topup) so the route and the
    concurrency tests exercise exactly the same code.
    """
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_response({"success": False, "message": "A JSON object is required."}, 400)
    with open_db() as db:
        try:
            result = perform_wallet_topup(
                db, request.current_user,
                data.get("amount"), data, request.headers.get("Idempotency-Key"),
            )
        except CheckoutError as exc:
            db.rollback()
            return json_response({"success": False, "message": exc.message, "code": exc.code}, exc.status)
        db.commit()

    return json_response(
        {
            "success": True,
            "message": result["message"],
            "replayed": result["replayed"],
            "transaction": {
                "gross_amount": result["gross_amount"],
                "gateway_fee": result["gateway_fee"],
                "net_amount": result["net_amount"],
                "new_balance": result["new_balance"],
            },
        }
    )


@wallet_blueprint.get("/api/wallet/transactions")
@wallet_blueprint.get("/api/history/account")
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
                "reference": tx["reference_id"] or "",
                "status": "completed",
                "date": tx["created_at"],
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

    return json_response({"success": False, "code": "reservation_workflow_required",
                          "message": "Funds are reserved by their associated order workflow."}, 403)


@wallet_blueprint.post("/api/wallet/unlock")
@login_required
def unlock_wallet_balance():
    err = csrf_error()
    if err:
        return err

    return json_response({"success": False, "code": "reservation_workflow_required",
                          "message": "Reserved funds are released by their associated order workflow."}, 403)


@wallet_blueprint.post("/api/wallet/withdraw-locked")
@login_required
def create_locked_withdrawal_request():
    role_error = ensure_transporter_role()
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    if not _withdrawal_simulator_enabled():
        return json_response({"success": False, "code": "payout_provider_unavailable",
                              "message": "Withdrawals are unavailable until payout processing is configured."}, 503)

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return json_response({"success": False, "message": "A JSON object is required."}, 400)
    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error

    try:
        amount = parse_money_amount(data.get("amount"))
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    rounded_amount = float(amount)
    with open_db() as db:
        destination = db.execute(
            "SELECT payout_card_token FROM transporter_profiles WHERE user_id=%s",
            (request.current_user["id"],),
        ).fetchone()
    if not destination or not destination["payout_card_token"]:
        return json_response(
            {"success": False, "message": "A payout destination is required."}, 409
        )
    descriptor = step_up_service.normalize_descriptor({
        "action_key": "wallet.withdrawal.request",
        "resource_type": "wallet",
        "resource_id": wallet["id"],
        "amount_minor": step_up_service.money_to_minor(rounded_amount),
        "currency": "PKR",
        "destination_fingerprint": step_up_service.stored_payout_destination_fingerprint(
            destination["payout_card_token"]
        ),
    })
    request_id = _step_up_request_id("wallet.withdrawal.request")

    from wallet.withdrawal_limits import validate_withdrawal, get_limits, get_active_tier
    with open_db() as db:
        gate = step_up_service.consume_current_request(db, request, descriptor)
        gate_error = step_up_service.gate_error_response(gate, descriptor)
        if gate_error:
            db.rollback()
            return gate_error
        locked_destination = db.execute(
            "SELECT payout_card_token FROM transporter_profiles "
            "WHERE user_id=%s FOR UPDATE",
            (request.current_user["id"],),
        ).fetchone()
        fresh_wallet_row = db.execute(
            "SELECT * FROM wallets WHERE id=%s AND user_id=%s FOR UPDATE",
            (wallet["id"], request.current_user["id"]),
        ).fetchone()
        if not locked_destination or not fresh_wallet_row:
            db.rollback()
            return json_response({"success": False, "message": "Wallet not found."}, 404)
        if step_up_service.stored_payout_destination_fingerprint(
            locked_destination["payout_card_token"]
        ) != descriptor["destination_fingerprint"]:
            db.rollback()
            return json_response(
                {"success": False, "message": "The payout destination changed. Try again."},
                409,
            )
        fresh_wallet = dict(fresh_wallet_row)
        # request.current_user already carries the transporter_profiles fields
        # (withdrawal_tier, withdrawal_tier_expires_at) merged in by get_user_by_id.
        user_row = dict(request.current_user)
        error_msg = validate_withdrawal(db, user_row, fresh_wallet, rounded_amount)
        if error_msg:
            db.rollback()
            return json_response({"success": False, "message": error_msg}, 400)

        stamp = timestamp_bundle()
        limits = get_limits(user_row)
        active_tier = get_active_tier(user_row)
        within_limits = (
            rounded_amount <= limits["single_max"] and
            rounded_amount <= limits["daily_max"]
        )

        if within_limits:
            # Auto-approve: deduct from balance only, preserve locked_balance
            from decimal import Decimal
            new_balance = Decimal(str(fresh_wallet["balance"])) - amount
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
                description="Simulated withdrawal; no bank transfer (within tier limit)",
                reference_id=f"tier_{active_tier}_auto",
            )
            step_up_service.write_consumed_event(
                db, request_id=request_id, gate=gate, descriptor=descriptor
            )
            db.commit()
            from wallet.withdrawal_limits import max_withdrawable
            remaining = max_withdrawable(fresh_wallet)
            return json_response({
                "success": True,
                "auto_approved": True,
                "simulated": True,
                "message": f"Simulated Rs {rounded_amount:,.0f} withdrawal; no bank transfer was made. Remaining withdrawable: Rs {remaining:,.0f}.",
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
            step_up_service.write_consumed_event(
                db, request_id=request_id, gate=gate, descriptor=descriptor
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

    from datetime import datetime, timedelta, timezone
    from wallet.withdrawal_limits import TIERS, PERMANENT_LOCK

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_response({"success": False, "message": "A JSON object is required."}, 400)
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

    spendable = available_balance(wallet)
    if spendable + 1e-9 < fee:
        return json_response(
            {
                "success": False,
                "message": "Insufficient balance to purchase plan. Please top up your wallet.",
            },
            400,
        )

    expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    stamp = timestamp_bundle()["iso"]
    descriptor = step_up_service.normalize_descriptor({
        "action_key": "wallet.withdrawal_limit.purchase",
        "resource_type": "wallet",
        "resource_id": wallet["id"],
        "amount_minor": step_up_service.money_to_minor(fee),
        "currency": "PKR",
        "funding_source": "wallet",
    })
    request_id = _step_up_request_id("wallet.withdrawal_limit.purchase")

    with open_db() as db:
        gate = step_up_service.consume_current_request(db, request, descriptor)
        gate_error = step_up_service.gate_error_response(gate, descriptor)
        if gate_error:
            db.rollback()
            return gate_error
        locked_wallet = db.execute(
            "SELECT * FROM wallets WHERE id=%s AND user_id=%s FOR UPDATE",
            (wallet["id"], request.current_user["id"]),
        ).fetchone()
        if not locked_wallet:
            db.rollback()
            return json_response({"success": False, "message": "Wallet not found."}, 404)
        locked_spendable = available_balance(dict(locked_wallet))
        if locked_spendable + 1e-9 < fee:
            db.rollback()
            return json_response(
                {"success": False, "message": "Insufficient balance to purchase plan. Please top up your wallet."},
                400,
            )
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
        step_up_service.write_consumed_event(
            db, request_id=request_id, gate=gate, descriptor=descriptor
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
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_response({"success": False, "message": "A JSON object is required."}, 400)
    summary, card_error = validate_payout_card(data)
    if card_error:
        return json_response({"success": False, "message": card_error}, 400)
    wallet, wallet_error = get_or_create_wallet(request.current_user)
    if wallet_error:
        return wallet_error
    descriptor = step_up_service.normalize_descriptor({
        "action_key": "wallet.payout_destination.replace",
        "resource_type": "wallet",
        "resource_id": wallet["id"],
        "destination_fingerprint": step_up_service.payout_destination_input_fingerprint(data),
    })
    request_id = _step_up_request_id("wallet.payout_destination.replace")
    with open_db() as db:
        gate = step_up_service.claim_current_request(db, request, descriptor)
        gate_error = step_up_service.gate_error_response(gate, descriptor)
        if gate_error:
            db.rollback()
            return gate_error
        db.commit()
    try:
        token = get_payment_provider().tokenize(summary)
    except PaymentProviderRejected:
        _mark_payout_rejected(gate)
        return json_response(
            {
                "success": False,
                "code": "payout_destination_rejected",
                "message": "The payout destination was rejected.",
            },
            422,
        )
    except Exception:
        current_app.logger.error("Payout destination tokenization outcome is uncertain.")
        _mark_payout_reconciliation(gate, descriptor, request_id)
        return _payout_reconciliation_response()
    needs_reconciliation = False
    try:
        with open_db() as db:
            finalized = step_up_service.lock_and_finalize_current_request_claim(
                db, request, gate=gate, descriptor=descriptor
            )
            locked_wallet = db.execute(
                "SELECT id FROM wallets WHERE id=%s AND user_id=%s FOR UPDATE",
                (wallet["id"], request.current_user["id"]),
            ).fetchone()
            if not locked_wallet or not finalized:
                db.rollback()
                needs_reconciliation = True
            else:
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
                step_up_service.write_consumed_event(
                    db, request_id=request_id, gate=gate, descriptor=descriptor
                )
                db.commit()
    except Exception:
        current_app.logger.error("Payout destination persistence outcome is uncertain.")
        needs_reconciliation = True
    if needs_reconciliation:
        _mark_payout_reconciliation(gate, descriptor, request_id)
        return _payout_reconciliation_response()
    return json_response({"success": True, "message": "Payout card saved successfully."})
