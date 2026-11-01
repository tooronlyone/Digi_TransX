"""Transactional marketplace checkout and customer-authorized handoff.

The caller owns the transaction. Financial failures raise CheckoutError so an
HTTP error can never accidentally commit a partial transfer.
"""

import hashlib
import hmac
import json
import re
import secrets
from decimal import Decimal

from flask import current_app

from shared.payments import CheckoutError, MAX_MONEY_AMOUNT, parse_money_amount, parse_positive_id, validate_idempotency_key
from shared.commissions import BUSINESS_FEE_VERSION, itemized_fee
from shared.financial_ledger import post_journal
from wallet.helpers import (
    adjust_wallet_balance,
    ensure_wallet_locked_balance,
    ensure_wallet_unlocked_balance,
    get_or_create_wallet_for_user,
)


class MarketplaceError(CheckoutError):
    pass


def _text(data, key, default="", limit=2000):
    value = data.get(key, default)
    if value is None:
        value = default
    if not isinstance(value, str) or len(value) > limit:
        raise MarketplaceError(f"Invalid {key.replace('_', ' ')}.", 400, "invalid_checkout_input")
    return value.strip()


def parse_checkout(data, user):
    if not isinstance(data, dict):
        raise MarketplaceError("A JSON object is required.", 400)
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise MarketplaceError("Choose between 1 and 100 cart items.", 400)
    parsed_items = []
    seen = set()
    try:
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Every cart item must be an object.")
            part_id = parse_positive_id(item.get("part_id"), "Part ID")
            quantity = parse_positive_id(item.get("quantity", 1), "Quantity")
            if quantity > 2147483647 or part_id in seen:
                raise ValueError("Each part must appear once with a valid quantity.")
            seen.add(part_id)
            parsed_items.append({"part_id": part_id, "quantity": quantity})
        vehicle_id = (None if data.get("vehicle_id") is None else
                      parse_positive_id(data["vehicle_id"], "Vehicle ID"))
    except ValueError as exc:
        raise MarketplaceError(str(exc), 400, "invalid_checkout_input") from exc
    delivery_type = _text(data, "delivery_type", "delivery", 20)
    if delivery_type not in {"delivery", "pickup"}:
        raise MarketplaceError("Delivery type must be delivery or pickup.", 400)
    payment_method = _text(data, "payment_method", "wallet_escrow", 30)
    if payment_method not in {"wallet_escrow", "cod"}:
        raise MarketplaceError("Choose wallet escrow or cash on delivery.", 400, "unsupported_payment_method")
    if payment_method == "cod":
        raise MarketplaceError("Cash on delivery requires an approved marketplace fee-collection policy. Use wallet escrow.",
                               409, "marketplace_cod_fee_policy_required")
    address = _text(data, "delivery_address", limit=2000)
    if delivery_type == "delivery" and not address:
        raise MarketplaceError("Delivery address is required.", 400)
    return {
        "items": sorted(parsed_items, key=lambda item: item["part_id"]),
        "delivery_type": delivery_type,
        "delivery_address": address,
        "contact_phone": _text(data, "contact_phone", str(user.get("phone") or ""), 50),
        "vehicle_id": vehicle_id,
        "buyer_notes": _text(data, "buyer_notes", limit=4000),
        "payment_method": payment_method,
    }


def _check_wallet_result(error, message):
    if error is not None:
        raise MarketplaceError(message, getattr(error, "status_code", 409), "wallet_operation_failed")


def _get_wallet(db, user):
    wallet, error = get_or_create_wallet_for_user(db, user)
    _check_wallet_result(error, "Wallet is unavailable for this account.")
    if wallet is None:
        raise MarketplaceError("Wallet is unavailable.", 409, "wallet_unavailable")
    return wallet


def _otp_digest(order_id, otp):
    key = current_app.secret_key
    if not key:
        raise MarketplaceError("Delivery confirmation is unavailable.", 503)
    key = key.encode("utf-8") if isinstance(key, str) else key
    return hmac.new(key, f"marketplace:{order_id}:{otp}".encode("ascii"), hashlib.sha256).hexdigest()


def _expires_utc(row):
    # Select AT TIME ZONE UTC so the shared DB serializer cannot strip an
    # unknown session timezone offset from this customer-facing expiry.
    return str(row["expires_at_utc"]).replace(" ", "T") + "Z"


def _issue_challenge(db, order_id):
    otp = f"{secrets.randbelow(1_000_000):06d}"
    row = db.execute(
        """
        INSERT INTO marketplace_delivery_secrets
          (order_id,otp_digest,expires_at,failed_attempts,consumed_at,created_at)
        VALUES(%s,%s,now()+interval '20 minutes',0,NULL,now())
        ON CONFLICT(order_id) DO UPDATE SET
          otp_digest=excluded.otp_digest,expires_at=excluded.expires_at,
          failed_attempts=0,consumed_at=NULL,created_at=excluded.created_at
        RETURNING expires_at AT TIME ZONE 'UTC' AS expires_at_utc
        """,
        (order_id, _otp_digest(order_id, otp)),
    ).fetchone()
    return {"delivery_otp": otp, "expires_at": _expires_utc(row)}


def perform_marketplace_checkout(db, user, payload, client_key):
    key = validate_idempotency_key(client_key)
    data = parse_checkout(payload, user)
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # The stable parent row also serializes first-use creation and retries
    # before any inventory or balance mutation.
    if db.execute("SELECT id FROM users WHERE id=%s FOR NO KEY UPDATE", (user["id"],)).fetchone() is None:
        raise MarketplaceError("Account not found.", 404)
    existing = db.execute(
        "SELECT * FROM marketplace_orders WHERE buyer_user_id=%s AND checkout_key=%s",
        (user["id"], key),
    ).fetchone()
    if existing is not None:
        if existing["request_fingerprint"] != fingerprint:
            raise MarketplaceError("This checkout key was used for a different cart.", 409, "idempotency_key_conflict")
        return {"id": existing["id"], "order_number": existing["order_number"],
                "net_total": float(existing["net_total"]), "payment_status": existing["payment_status"],
                "replayed": True}
    if data["vehicle_id"] is not None:
        vehicle = db.execute("SELECT id FROM vehicles WHERE id=%s AND owner_user_id=%s FOR SHARE",
                             (data["vehicle_id"], user["id"])).fetchone()
        if vehicle is None:
            raise MarketplaceError("Vehicle not found in your fleet.", 404)
    ids = [item["part_id"] for item in data["items"]]
    placeholders = ",".join(["%s"] * len(ids))
    parts = db.execute(
        f"SELECT * FROM marketplace_parts WHERE id IN ({placeholders}) AND is_active=true ORDER BY id FOR UPDATE",
        tuple(ids),
    ).fetchall()
    if len(parts) != len(ids):
        raise MarketplaceError("Some parts are no longer available.", 409)
    shop_id = parts[0]["shop_user_id"]
    if shop_id == user["id"] or any(part["shop_user_id"] != shop_id for part in parts):
        raise MarketplaceError("Order from one other shop at a time.", 400)
    shop = db.execute("SELECT role,legacy_role FROM users WHERE id=%s", (shop_id,)).fetchone()
    if shop is None or (shop.get("legacy_role") or shop["role"]) != "shopkeeper":
        raise MarketplaceError("This shop is unavailable.", 409)
    quantities = {item["part_id"]: item["quantity"] for item in data["items"]}
    total = Decimal("0.00")
    prepared = []
    for part in parts:
        qty = quantities[part["id"]]
        if part["stock_quantity"] < qty:
            raise MarketplaceError(f"Insufficient stock for '{part['title']}'.", 409)
        try:
            unit_price = parse_money_amount(
                part["discounted_price"] if part["discounted_price"] is not None else part["price"], "Part price")
        except ValueError as exc:
            raise MarketplaceError("A part has an invalid price; ask the seller to update it.", 409) from exc
        subtotal = unit_price * qty
        total += subtotal
        if total > MAX_MONEY_AMOUNT:
            raise MarketplaceError("Cart total exceeds the supported limit.", 400)
        prepared.append((part, qty, unit_price, subtotal))
    delivery_fee = Decimal("500.00") if data["delivery_type"] == "delivery" else Decimal("0.00")
    net_total = total + delivery_fee
    if net_total > MAX_MONEY_AMOUNT:
        raise MarketplaceError("Cart total exceeds the supported limit.", 400)
    order_number = f"DTX-PRT-{secrets.token_hex(12).upper()}"
    status = "pending"
    if data["payment_method"] == "wallet_escrow":
        wallet = _get_wallet(db, user)
        _check_wallet_result(ensure_wallet_locked_balance(
            db, wallet, user["id"], net_total, reason="marketplace_escrow", reference_id=order_number),
            "Insufficient unreserved wallet balance for this order.")
        status = "escrow_locked"
    row = db.execute(
        """
        INSERT INTO marketplace_orders(
          order_number,buyer_user_id,shop_user_id,vehicle_id,delivery_type,
          delivery_address,contact_phone,total_parts_amount,delivery_fee,net_total,
          payment_method,payment_status,fulfillment_status,delivery_otp,buyer_notes,
          checkout_key,request_fingerprint,business_fee_version)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'placed',NULL,%s,%s,%s,%s)
        RETURNING id
        """,
        (order_number,user["id"],shop_id,data["vehicle_id"],data["delivery_type"],
         data["delivery_address"],data["contact_phone"],total,delivery_fee,net_total,
         data["payment_method"],status,data["buyer_notes"],key,fingerprint,BUSINESS_FEE_VERSION),
    ).fetchone()
    order_id = row["id"]
    if data["payment_method"] == "wallet_escrow":
        post_journal(db, f"marketplace:hold:{order_id}", "marketplace_escrow", str(order_id),
                     [(f"wallet:{user['id']}", -net_total), (f"market_escrow:{order_id}", net_total)])
    for part, qty, unit_price, subtotal in prepared:
        changed = db.execute(
            "UPDATE marketplace_parts SET stock_quantity=stock_quantity-%s,updated_at=now() "
            "WHERE id=%s AND stock_quantity>=%s", (qty, part["id"], qty))
        if changed.rowcount != 1:
            raise MarketplaceError("Stock changed during checkout.", 409)
        db.execute(
            "INSERT INTO marketplace_order_items(order_id,part_id,part_title,part_number,unit_price,quantity,warranty_days,subtotal) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (order_id,part["id"],part["title"],part["part_number"],unit_price,qty,part["warranty_days"] or 0,subtotal))
    challenge = _issue_challenge(db, order_id)
    return {"id": order_id, "order_number": order_number, "net_total": float(net_total),
            "payment_status": status, "replayed": False, "delivery_otp": challenge["delivery_otp"],
            "delivery_otp_expires_at": challenge["expires_at"]}


def issue_buyer_delivery_challenge(db, user, order_id):
    order = db.execute("SELECT * FROM marketplace_orders WHERE id=%s AND buyer_user_id=%s FOR UPDATE",
                       (order_id, user["id"])).fetchone()
    if order is None:
        raise MarketplaceError("Order not found.", 404)
    if order["fulfillment_status"] not in {"dispatched", "ready_for_pickup"}:
        raise MarketplaceError("Request a delivery code when the order is ready for handoff.", 409)
    current = db.execute(
        "SELECT created_at<=now()-interval '60 seconds' AS can_reissue "
        "FROM marketplace_delivery_secrets WHERE order_id=%s FOR UPDATE", (order_id,)).fetchone()
    if current is not None and not current["can_reissue"]:
        raise MarketplaceError("Wait one minute before requesting another delivery code.", 429, "otp_reissue_limited")
    return _issue_challenge(db, order_id)


def _settle_escrow(db, order):
    # Create missing wallets in a consistent user order, then lock the complete
    # transfer set by wallet ID. Re-entrant helper locks keep these same locks.
    if order["buyer_user_id"] == order["shop_user_id"]:
        raise MarketplaceError("Self-purchase payment requires reconciliation.", 409)
    accounts = [(order["buyer_user_id"], None), (order["shop_user_id"], "shopkeeper")]
    wallets = {}
    for user_id, role in sorted(accounts):
        if role is None:
            owner = db.execute("SELECT role,legacy_role FROM users WHERE id=%s", (user_id,)).fetchone()
            if owner is None:
                raise MarketplaceError("Buyer account is unavailable.", 409)
            role = owner.get("legacy_role") or owner["role"]
        wallets[user_id] = _get_wallet(db, {"id": user_id, "role": role})
    ids = sorted(wallet["id"] for wallet in wallets.values())
    locked = db.execute("SELECT * FROM wallets WHERE id IN (%s,%s) ORDER BY id FOR UPDATE", tuple(ids)).fetchall()
    for row in locked:
        wallets[row["user_id"]].update(row)
    buyer_wallet, shop_wallet = wallets[order["buyer_user_id"]], wallets[order["shop_user_id"]]
    exact = db.execute_exact("SELECT net_total,total_parts_amount,business_fee_version FROM marketplace_orders WHERE id=%s", (order["id"],)).fetchone()
    try:
        amount = parse_money_amount(exact["net_total"], "Order total")
    except ValueError as exc:
        raise MarketplaceError("Order total requires reconciliation.", 409) from exc
    reference = order["order_number"]
    invoice = itemized_fee(exact["total_parts_amount"], "marketplace") if exact["business_fee_version"] == BUSINESS_FEE_VERSION else None
    commission = Decimal(invoice["total_fee"]) if invoice else Decimal("0.00")
    seller_amount = amount - commission
    _check_wallet_result(ensure_wallet_unlocked_balance(
        db,buyer_wallet,order["buyer_user_id"],amount,reason="marketplace_escrow_release",reference_id=reference),
        "The order reservation requires reconciliation; no funds were transferred.")
    _check_wallet_result(adjust_wallet_balance(
        db,buyer_wallet,order["buyer_user_id"],-amount,"parts_purchase",
        description=f"Parts order #{reference}",reference_id=reference),
        "The buyer balance requires reconciliation; no funds were transferred.")
    _check_wallet_result(adjust_wallet_balance(
        db,shop_wallet,order["shop_user_id"],seller_amount,"parts_sale",
        description=f"Parts order #{reference}",reference_id=reference),
        "The seller wallet requires reconciliation; no funds were transferred.")
    if invoice:
        db.execute("INSERT INTO marketplace_financial_events(order_id,event_type,idempotency_key,gross_amount,eligible_sale_amount,platform_fee,seller_amount,fee_breakdown) "
                   "VALUES(%s,'settlement',%s,%s,%s,%s,%s,%s::jsonb)",
                   (order["id"], f"settlement:{order['id']}", amount, exact["total_parts_amount"], commission, seller_amount, json.dumps(invoice)))
        post_journal(db, f"marketplace:settlement:{order['id']}", "marketplace_settlement", str(order["id"]),
                     [(f"market_escrow:{order['id']}", -amount), (f"wallet:{order['shop_user_id']}", seller_amount),
                      ("revenue:marketplace", commission)])


def perform_delivery_verification(db, seller, order_id, otp):
    if str(seller.get("role") or "").strip().lower() != "shopkeeper":
        raise MarketplaceError("Shopkeeper account required.", 403)
    if not isinstance(otp, str) or re.fullmatch(r"[0-9]{6}", otp) is None:
        raise MarketplaceError("Enter a valid 6-digit delivery code.", 400)
    order = db.execute("SELECT * FROM marketplace_orders WHERE id=%s AND shop_user_id=%s FOR UPDATE",
                       (order_id, seller["id"])).fetchone()
    if order is None:
        raise MarketplaceError("Order not found.", 404)
    if order["fulfillment_status"] == "delivered":
        return {"success": True, "already_delivered": True, "message": "Order was already delivered."}
    expected = "dispatched" if order["delivery_type"] == "delivery" else "ready_for_pickup"
    if order["fulfillment_status"] != expected:
        raise MarketplaceError("Order is not ready for delivery confirmation.", 409)
    challenge = db.execute(
        "SELECT *,expires_at>now() AS challenge_active FROM marketplace_delivery_secrets "
        "WHERE order_id=%s FOR UPDATE", (order_id,)).fetchone()
    if (challenge is None or challenge["consumed_at"] is not None or not challenge["challenge_active"]
            or challenge["failed_attempts"] >= 5):
        raise MarketplaceError("Ask the buyer to request a new delivery code.", 409, "delivery_code_unavailable")
    if not hmac.compare_digest(challenge["otp_digest"], _otp_digest(order_id, otp)):
        # Return an error result rather than raise: only the attempt counter is
        # committed. No wallet mutation is reachable on this branch.
        db.execute("UPDATE marketplace_delivery_secrets SET failed_attempts=failed_attempts+1 WHERE order_id=%s",
                   (order_id,))
        return {"success": False, "code": "delivery_code_invalid", "message": "Incorrect delivery code.", "status": 400}
    if order["payment_method"] == "wallet_escrow":
        if order["payment_status"] != "escrow_locked":
            raise MarketplaceError("Order payment requires reconciliation.", 409)
        _settle_escrow(db, order)
        payment_status = "released"
    elif order["payment_method"] == "cod":
        payment_status = order["payment_status"]
    else:
        raise MarketplaceError("This payment method requires reconciliation.", 409)
    db.execute("UPDATE marketplace_delivery_secrets SET consumed_at=now() WHERE order_id=%s", (order_id,))
    db.execute("UPDATE marketplace_orders SET fulfillment_status='delivered',payment_status=%s,updated_at=now() "
               "WHERE id=%s", (payment_status, order_id))
    return {"success": True, "already_delivered": False,
            "message": "Delivery confirmed and escrow settled." if payment_status == "released"
            else "Delivery confirmed. Cash payment is recorded separately."}


def perform_marketplace_refund(db, actor, order_id, payload, client_key):
    """Execute an explicit authorized refund decision, never infer entitlement.

    Before handoff only a complete escrow cancellation is supported. After
    settlement the decision supplies both the cash refund and the eligible
    merchandise portion; cumulative fee reversal prevents rounding drift and
    duplicate callback charges. A seller must fund their own refund share from
    available funds. Reserves, client freight escrow and fuel credit are never
    sources. Restocking delivered goods requires a separate verified process.
    """
    if str(actor.get("role") or "").lower() not in {"admin", "platform_admin"}:
        raise MarketplaceError("Administrator decision required.", 403)
    key = validate_idempotency_key(client_key)
    if not isinstance(payload, dict):
        raise MarketplaceError("A JSON object is required.", 400)
    try:
        amount = parse_money_amount(payload.get("amount"), "Approved refund")
        eligible = Decimal(str(payload.get("eligible_sale_amount")))
        if not eligible.is_finite() or eligible < 0 or eligible != eligible.quantize(Decimal("0.01")) or eligible > amount:
            raise ValueError("Eligible sale refund must be between zero and the approved cash refund.")
    except (ValueError, ArithmeticError) as exc:
        raise MarketplaceError(str(exc), 400) from exc
    reason = _text(payload, "reason", limit=4000)
    decision = _text(payload, "decision_reference", limit=200)
    if not reason or not decision:
        raise MarketplaceError("An evidence-based decision reference and refund reason are required.", 400)
    fingerprint = hashlib.sha256(json.dumps({"order_id": order_id, "amount": str(amount), "eligible": str(eligible),
                                            "reason": reason, "decision": decision}, sort_keys=True).encode()).hexdigest()
    order = db.execute_exact("SELECT * FROM marketplace_orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
    if order is None:
        raise MarketplaceError("Order not found.", 404)
    event_key = f"refund:{order_id}:{key}"
    prior = db.execute("SELECT * FROM marketplace_financial_events WHERE idempotency_key=%s", (event_key,)).fetchone()
    if prior:
        if prior["request_fingerprint"] != fingerprint:
            raise MarketplaceError("Refund key was used for a different decision.", 409, "idempotency_key_conflict")
        return {"success": True, "replayed": True, "refund_event_id": prior["id"]}
    if order["business_fee_version"] != BUSINESS_FEE_VERSION or order["payment_method"] != "wallet_escrow":
        raise MarketplaceError("Historical or externally paid orders require explicit reconciliation.", 409)
    paid = order["payment_status"] == "released"
    if not paid and (order["payment_status"] != "escrow_locked" or
                     order["fulfillment_status"] not in {"placed", "confirmed"} or
                     amount != order["net_total"] or eligible != order["total_parts_amount"]):
        raise MarketplaceError("Only a full pre-dispatch escrow cancellation is supported before settlement.", 409)
    refunded = db.execute_exact(
        "SELECT coalesce(sum(gross_amount),0) AS gross,coalesce(sum(eligible_sale_amount),0) AS sale,"
        "coalesce(sum(platform_fee),0) AS fee FROM marketplace_financial_events WHERE order_id=%s AND event_type IN('refund','escrow_return')",
        (order_id,),
    ).fetchone()
    if amount + refunded["gross"] > order["net_total"] or eligible + refunded["sale"] > order["total_parts_amount"]:
        raise MarketplaceError("Refund exceeds the unrefunded order entitlement.", 409)
    if amount - eligible + refunded["gross"] - refunded["sale"] > order["delivery_fee"]:
        raise MarketplaceError("Non-merchandise refund exceeds the unrefunded delivery amount.", 409)
    remaining_sale = order["total_parts_amount"] - refunded["sale"] - eligible
    # The original minus the remaining fee is the cumulative reversed fee.
    original = itemized_fee(order["total_parts_amount"], "marketplace")
    remaining = itemized_fee(remaining_sale, "marketplace")
    fee_return = (Decimal(original["total_fee"]) - Decimal(remaining["total_fee"]) - refunded["fee"]) if paid else Decimal("0.00")
    seller_return = amount - fee_return
    items = []
    if not paid:
        # Checkout takes inventory before wallets. Restocking follows the same
        # order, otherwise a simultaneous new order could deadlock this return.
        items = db.execute("SELECT part_id,quantity FROM marketplace_order_items WHERE order_id=%s ORDER BY part_id", (order_id,)).fetchall()
        part_ids = [item["part_id"] for item in items if item["part_id"] is not None]
        if part_ids:
            db.execute("SELECT id FROM marketplace_parts WHERE id=ANY(%s) ORDER BY id FOR UPDATE", (part_ids,))
    owners = [(order["buyer_user_id"], None)] + ([(order["shop_user_id"], "shopkeeper")] if paid else [])
    wallets = {}
    for owner_id, role in sorted(owners):
        if role is None:
            owner = db.execute("SELECT role,legacy_role FROM users WHERE id=%s", (owner_id,)).fetchone()
            role = owner.get("legacy_role") or owner["role"]
        wallets[owner_id] = _get_wallet(db, {"id": owner_id, "role": role})
    wallet_ids = sorted(w["id"] for w in wallets.values())
    db.execute("SELECT id FROM wallets WHERE id=ANY(%s) ORDER BY id FOR UPDATE", (wallet_ids,))
    if paid:
        _check_wallet_result(adjust_wallet_balance(db, wallets[order["shop_user_id"]], order["shop_user_id"], -seller_return,
            "parts_refund_recovery", description=reason, reference_id=event_key), "Seller has insufficient available funds for this refund decision.")
        _check_wallet_result(adjust_wallet_balance(db, wallets[order["buyer_user_id"]], order["buyer_user_id"], amount,
            "parts_refund", description=reason, reference_id=event_key), "Buyer refund failed.")
        journal = [(f"wallet:{order['shop_user_id']}", -seller_return), ("revenue:marketplace", -fee_return),
                   (f"wallet:{order['buyer_user_id']}", amount)]
    else:
        _check_wallet_result(ensure_wallet_unlocked_balance(db, wallets[order["buyer_user_id"]], order["buyer_user_id"], amount,
            reason="marketplace_escrow_return", reference_id=event_key), "Escrow reservation requires reconciliation.")
        journal = [(f"market_escrow:{order_id}", -amount), (f"wallet:{order['buyer_user_id']}", amount)]
        for item in items:
            db.execute("UPDATE marketplace_parts SET stock_quantity=stock_quantity+%s,updated_at=now() WHERE id=%s", (item["quantity"], item["part_id"]))
        db.execute("UPDATE marketplace_orders SET fulfillment_status='cancelled',payment_status='refunded',updated_at=now() WHERE id=%s", (order_id,))
        db.execute("UPDATE marketplace_delivery_secrets SET consumed_at=now() WHERE order_id=%s AND consumed_at IS NULL", (order_id,))
    if paid and amount + refunded["gross"] == order["net_total"]:
        db.execute("UPDATE marketplace_orders SET payment_status='refunded',updated_at=now() WHERE id=%s", (order_id,))
    event = db.execute("INSERT INTO marketplace_financial_events(order_id,event_type,idempotency_key,request_fingerprint,gross_amount,eligible_sale_amount,platform_fee,seller_amount,fee_breakdown,actor_user_id,decision_reference,reason) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) RETURNING id",
        (order_id,"refund" if paid else "escrow_return",event_key,fingerprint,amount,eligible,fee_return,seller_return,
         json.dumps({"original": original, "remaining": remaining, "fee_reversed": str(fee_return)}),actor["id"],decision,reason)).fetchone()
    post_journal(db, f"marketplace:{event_key}", "marketplace_refund", str(order_id), journal)
    return {"success": True, "replayed": False, "refund_event_id": event["id"], "amount": str(amount), "fee_reversed": str(fee_return)}
