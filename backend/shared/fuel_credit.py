"""Trip-bound fuel authorization and future-earnings credit recovery.

No function reads or mutates Client wallets, booking escrow or security funds.
Lock order: source trip -> truck -> transporter wallet -> credit account ->
treasury row -> treasury wallet -> voucher -> pump -> station wallet. Caller
transactions own every lock and commit; exceptions roll back the entire action.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import secrets

from shared.financial_ledger import money, post_journal
from shared.payments import CheckoutError, parse_positive_id, validate_idempotency_key

FUEL_TYPES = frozenset({"diesel", "petrol", "hi_octane", "cng", "adblue"})
ZERO = Decimal("0.00")


def credit_limit(rating):
    if rating is None:
        return ZERO
    value = Decimal(str(rating))
    if not value.is_finite() or value < 0 or value > 5:
        return ZERO
    return Decimal("20000.00") if value >= 4 else Decimal("10000.00") if value >= 3 else ZERO


def _rating(db, user_id):
    from orders.market_pricing import verified_transporter_rating
    return verified_transporter_rating(db, user_id)


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).digest()


def _source(db, data, owner, *, active=True):
    trip = None if data.get("trip_id") is None else parse_positive_id(data["trip_id"], "Trip ID")
    if trip is None:
        raise CheckoutError("Select a shipment trip.", 400, "invalid_trip")
    truck_id = parse_positive_id(data.get("truck_id"), "Truck ID")
    row = db.execute_exact("SELECT * FROM shipment_trips WHERE id=%s AND transporter_user_id=%s AND truck_id=%s FOR UPDATE",
                           (trip, owner, truck_id)).fetchone()
    if not row:
        raise CheckoutError("Trip and truck were not found in your fleet.", 404, "fuel_trip_not_found")
    if active and row["status"] not in {"ready_to_start", "pending", "in_progress"}:
        raise CheckoutError("Fuel requires an active assigned trip.", 409, "fuel_trip_inactive")
    truck = db.execute_exact("SELECT * FROM vehicles WHERE id=%s AND owner_user_id=%s FOR UPDATE", (truck_id, owner)).fetchone()
    if not truck or truck["status"] not in {"active", "on_job"}:
        raise CheckoutError("An eligible owned or controlled truck is required.", 409, "fuel_truck_ineligible")
    return row, truck


def _wallet(db, user_id, role=None):
    if role:
        db.execute_exact("INSERT INTO wallets(user_id,role,is_minimum_met) VALUES(%s,%s,true) ON CONFLICT(user_id) DO NOTHING", (user_id, role))
    row = db.execute_exact("SELECT * FROM wallets WHERE user_id=%s FOR UPDATE", (user_id,)).fetchone()
    if not row:
        raise CheckoutError("Wallet unavailable.", 409, "fuel_wallet_unavailable")
    if role and row['role'] != role:
        raise CheckoutError("Wallet role does not match the authorized fuel account.",409,"fuel_wallet_role_mismatch")
    return row


def _spendable(wallet):
    floor = Decimal("30000.00") if wallet["role"] == "transporter" else ZERO
    reserve = max(wallet["locked_balance"], wallet["minimum_required"], floor)
    return max(ZERO, wallet["balance"] - reserve)


def _account(db, owner):
    db.execute_exact("INSERT INTO fuel_credit_accounts(transporter_user_id) VALUES(%s) ON CONFLICT DO NOTHING", (owner,))
    return db.execute_exact("SELECT * FROM fuel_credit_accounts WHERE transporter_user_id=%s FOR UPDATE", (owner,)).fetchone()


def _treasury(db, *, existing_authorization=False):
    treasury = db.execute_exact(
        "SELECT t.* FROM fuel_platform_treasury t JOIN users u ON u.id=t.verified_by "
        "WHERE t.singleton=true " + ("" if existing_authorization else "AND u.role='admin' ") + "FOR UPDATE OF t", (),
    ).fetchone()
    if not treasury:
        raise CheckoutError("Verified platform liquidity is not configured; wallet-funded fuel remains available.", 409, "fuel_liquidity_unverified")
    wallet = db.execute_exact("SELECT * FROM wallets WHERE id=%s FOR UPDATE", (treasury["wallet_id"],)).fetchone()
    if not wallet or wallet["role"] != "platform_fuel":
        raise CheckoutError("A segregated platform-controlled fuel wallet is required.", 409, "fuel_liquidity_unverified")
    return treasury, wallet


def _wallet_tx(db, wallet, kind, amount, reference):
    db.execute_exact(
        "INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,balance_after,reference_id,description) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (wallet["id"], wallet["user_id"], kind, amount, wallet["balance"], reference, "Trip fuel " + kind),
    )


def _mutate_wallet(db, wallet, *, balance=ZERO, locked=ZERO):
    if wallet["balance"] + balance < 0 or wallet["locked_balance"] + locked < 0:
        raise CheckoutError("Fuel wallet reservation is inconsistent.", 409, "fuel_reconciliation_failed")
    row = db.execute_exact(
        "UPDATE wallets SET balance=balance+%s,locked_balance=locked_balance+%s,updated_at=now() "
        "WHERE id=%s RETURNING *", (balance, locked, wallet["id"]),
    ).fetchone()
    wallet.update(row)


def _event(db, owner, voucher_id, kind, amount, reference):
    db.execute_exact("INSERT INTO fuel_credit_events(transporter_user_id,voucher_id,event_type,amount,reference) VALUES(%s,%s,%s,%s,%s)",
                     (owner, voucher_id, kind, amount, reference))


def _has_cancelled_debt(db, owner):
    return bool(db.execute_exact(
        "SELECT 1 FROM fuel_vouchers v LEFT JOIN shipment_trips s ON s.id=v.trip_id "
        "WHERE v.transporter_user_id=%s AND v.status='dispensed' AND v.credit_utilized> "
        "coalesce((SELECT sum(e.amount) FROM fuel_credit_events e WHERE e.voucher_id=v.id AND e.event_type='recover_allocation'),0) "
        "AND s.status IN('cancelled','resolved_client') LIMIT 1", (owner,),
    ).fetchone())


def safe_voucher(row):
    private = {"otp_digest", "redemption_digest", "request_hash", "idempotency_key"}
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in row.items() if key not in private}


def authorize_voucher(db, owner, data, key, *, now=None):
    key = validate_idempotency_key(key)
    if not isinstance(data, dict):
        raise CheckoutError("A JSON object is required.", 400, "invalid_request")
    cap = money(data.get("max_amount"))
    if not ZERO < cap <= Decimal("9999999999.99"):
        raise CheckoutError("A verifiable positive monetary authorization cap is required.", 400, "fuel_cap_required")
    mode = data.get("request_mode")
    fuel = data.get("fuel_type")
    liters = None if data.get("max_liters") in (None, "") else money(data["max_liters"])
    if mode not in {"tank_full", "liters", "amount"} or fuel not in FUEL_TYPES or (mode == "liters" and liters is None) or (liters is not None and liters <= 0):
        raise CheckoutError("Select an approved fuel type, request mode and quantity.", 400, "invalid_fuel_request")
    station = None if data.get("station_id") in (None, "") else parse_positive_id(data["station_id"], "Station ID")
    _trip, truck = _source(db, data, owner)
    canonical = [data.get("trip_id"), truck["id"], fuel, mode, str(cap), str(liters), station]
    fingerprint = hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()
    wallet = _wallet(db, owner, "transporter")
    # Establish attributable collateral before adding any fuel hold; otherwise
    # repeated holds could reuse the same reserve floor.
    from shared.reserves import ensure_security_reserve
    ensure_security_reserve(db, owner)
    wallet = _wallet(db, owner)
    account = _account(db, owner)
    prior = db.execute_exact("SELECT * FROM fuel_vouchers WHERE transporter_user_id=%s AND idempotency_key=%s", (owner, key)).fetchone()
    if prior:
        if prior["request_hash"] != fingerprint:
            raise CheckoutError("Idempotency key reused for a different fuel authorization.", 409, "idempotency_key_conflict")
        return {"voucher": safe_voucher(prior), "replayed": True, "otp": None}
    if station and not db.execute_exact("SELECT id FROM users WHERE id=%s AND role='fuel_station_manager'", (station,)).fetchone():
        raise CheckoutError("Fuel station not found.", 400, "fuel_station_invalid")
    funded = min(cap, _spendable(wallet))
    credit = cap - funded
    limit = credit_limit(_rating(db, owner))
    blocked = _has_cancelled_debt(db, owner)
    if credit and (blocked or account["cancellation_debt"]):
        raise CheckoutError("Outstanding cancelled-trip fuel credit must be recovered before new platform credit.", 409, "fuel_credit_debt_blocked")
    if credit and (limit == 0 or credit + account["reserved_credit"] + account["outstanding_credit"] > limit):
        raise CheckoutError("Insufficient wallet funds or aggregate verified-rating fuel credit limit exceeded.", 400, "fuel_credit_limit")
    treasury = platform_wallet = None
    if credit:
        treasury, platform_wallet = _treasury(db)
        if credit > min(_spendable(platform_wallet), treasury["verified_liquidity"] - platform_wallet["locked_balance"]):
            raise CheckoutError("Insufficient verified platform liquidity for fuel credit.", 409, "fuel_liquidity_insufficient")
    otp = secrets.token_urlsafe(18)
    # Operational expiry is explicit server config, independent of financial terms.
    import os
    expiry_seconds = int(os.environ.get("FUEL_VOUCHER_TTL_SECONDS", "900"))
    if not 60 <= expiry_seconds <= 86400:
        raise CheckoutError("Fuel voucher expiry configuration is invalid.", 503, "fuel_configuration_invalid")
    row = db.execute_exact(
        "INSERT INTO fuel_vouchers(transporter_user_id,trip_id,truck_id,truck_plate,fuel_type,request_mode,max_amount,max_liters,"
        "wallet_authorized,credit_authorized,restricted_station_id,otp_digest,idempotency_key,request_hash,expires_at) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (owner, data.get("trip_id"), truck["id"], truck["truck_number"], fuel, mode, cap, liters,
         funded, credit, station, _digest(otp), key, fingerprint, (now or datetime.now(timezone.utc)) + timedelta(seconds=expiry_seconds)),
    ).fetchone()
    reference = "fuel:" + str(row["id"])
    if funded:
        _mutate_wallet(db, wallet, locked=funded)
        _wallet_tx(db, wallet, "fuel_authorize", funded, reference)
        post_journal(db, reference + ":wallet_authorize", "fuel_authorize", reference,
                     [(f"wallet:{owner}", -funded), (f"fuel_authorization:{row['id']}:wallet", funded)])
    if credit:
        _mutate_wallet(db, platform_wallet, locked=credit)
        post_journal(db, reference + ":credit_authorize", "fuel_credit_authorize", reference,
                     [(f"wallet:{platform_wallet['user_id']}", -credit), (f"fuel_authorization:{row['id']}:platform", credit)])
        _event(db, owner, row["id"], "authorize", credit, reference + ":authorize")
    db.execute_exact("UPDATE fuel_credit_accounts SET authorized_limit=%s,reserved_credit=reserved_credit+%s,updated_at=now() WHERE transporter_user_id=%s",
                     (limit, credit, owner))
    return {"voucher": safe_voucher(row), "otp": otp, "replayed": False}


def _voucher_context(db, voucher_id):
    snapshot = db.execute_exact("SELECT * FROM fuel_vouchers WHERE id=%s", (voucher_id,)).fetchone()
    if not snapshot:
        raise CheckoutError("Voucher not found.", 404, "fuel_voucher_not_found")
    # Releasing old holds must remain possible after vehicle ownership,
    # eligibility, or source-trip lifecycle has changed.
    db.execute_exact("SELECT id FROM shipment_trips WHERE id=%s FOR UPDATE", (snapshot["trip_id"],))
    db.execute_exact("SELECT id FROM vehicles WHERE id=%s FOR UPDATE", (snapshot["truck_id"],))
    wallet = _wallet(db, snapshot["transporter_user_id"])
    account = _account(db, snapshot["transporter_user_id"])
    treasury, platform = _treasury(db,existing_authorization=True) if snapshot["credit_authorized"] else (None, None)
    voucher = db.execute_exact("SELECT *,expires_at<=now() AS expired FROM fuel_vouchers WHERE id=%s FOR UPDATE", (voucher_id,)).fetchone()
    return voucher, wallet, account, treasury, platform


def _check_active(db, voucher):
    source = db.execute_exact("SELECT status FROM shipment_trips WHERE id=%s", (voucher["trip_id"],)).fetchone()
    if not source or source["status"] not in {"ready_to_start", "pending", "in_progress"}:
        raise CheckoutError("Trip is no longer eligible for dispensing.", 409, "fuel_trip_inactive")
    if voucher["expired"]:
        raise CheckoutError("Fuel voucher has expired.", 409, "fuel_voucher_expired")
    truck = db.execute_exact("SELECT owner_user_id,truck_number,status FROM vehicles WHERE id=%s", (voucher["truck_id"],)).fetchone()
    current = db.execute_exact(f"SELECT transporter_user_id,truck_id FROM {table} WHERE id=%s", (target,)).fetchone()
    if (not truck or truck["owner_user_id"] != voucher["transporter_user_id"]
            or truck["truck_number"] != voucher["truck_plate"] or truck["status"] not in {"active","on_job"}
            or not current or current["transporter_user_id"] != voucher["transporter_user_id"] or current["truck_id"] != voucher["truck_id"]):
        raise CheckoutError("Trip or truck authority has changed. Cancel this authorization and request a new voucher.",409,"fuel_truck_changed")


def verify_voucher(db, station, otp, pump_id):
    if not isinstance(otp, str) or not 20 <= len(otp) <= 100:
        raise CheckoutError("Invalid or already used fuel voucher code.", 400, "fuel_voucher_invalid")
    snapshot = db.execute_exact("SELECT id FROM fuel_vouchers WHERE otp_digest=%s", (_digest(otp),)).fetchone()
    if not snapshot:
        raise CheckoutError("Invalid or already used fuel voucher code.", 400, "fuel_voucher_invalid")
    voucher, *_ = _voucher_context(db, snapshot["id"])
    _check_active(db, voucher)
    if voucher["status"] != "authorized":
        raise CheckoutError("Fuel voucher has already been used.", 409, "fuel_voucher_used")
    if voucher["restricted_station_id"] and voucher["restricted_station_id"] != station:
        raise CheckoutError("This voucher is restricted to another station.", 403, "fuel_station_mismatch")
    pump = db.execute_exact("SELECT * FROM fuel_station_pumps WHERE id=%s AND user_id=%s FOR UPDATE", (pump_id, station)).fetchone()
    if not pump or pump["status"] != "active" or pump["fuel_type"] != voucher["fuel_type"]:
        raise CheckoutError("Select an active owned pump with the authorized fuel type.", 400, "fuel_pump_mismatch")
    token = secrets.token_urlsafe(32)
    row = db.execute_exact("UPDATE fuel_vouchers SET status='verified',redeemed_station_id=%s,pump_id=%s,redemption_digest=%s,verified_at=now() WHERE id=%s RETURNING *",
                           (station, pump_id, _digest(token), voucher["id"])).fetchone()
    return {"voucher": safe_voucher(row), "redemption_token": token}


def dispense_voucher(db, station, voucher_id, data):
    voucher, wallet, account, treasury, platform = _voucher_context(db, voucher_id)
    token = data.get("redemption_token")
    if not isinstance(token, str) or not secrets.compare_digest(voucher["redemption_digest"] or b"", _digest(token)) or voucher["redeemed_station_id"] != station:
        raise CheckoutError("Voucher redemption is not authorized for this station.", 403, "fuel_redemption_unauthorized")
    liters = money(data.get("actual_liters"))
    if liters <= 0 or data.get("fuel_type") != voucher["fuel_type"] or str(data.get("truck_plate", "")).strip().upper() != voucher["truck_plate"].upper():
        raise CheckoutError("Dispense quantity, truck or fuel does not match the voucher.", 400, "fuel_dispense_mismatch")
    pump_id = parse_positive_id(data.get("pump_id"), "Pump ID")
    if pump_id != voucher["pump_id"]:
        raise CheckoutError("Pump differs from the verified dispense slip.", 400, "fuel_pump_mismatch")
    if voucher["status"] == "dispensed":
        if liters != voucher["actual_liters"]:
            raise CheckoutError("Finalized dispense does not match the retry.", 409, "idempotency_key_conflict")
        return {"voucher": safe_voucher(voucher), "replayed": True}
    _check_active(db, voucher)
    if voucher["status"] != "verified":
        raise CheckoutError("Voucher is not ready to dispense.", 409, "fuel_voucher_used")
    pump = db.execute_exact("SELECT * FROM fuel_station_pumps WHERE id=%s AND user_id=%s FOR UPDATE", (pump_id, station)).fetchone()
    if not pump or pump["status"] != "active" or pump["fuel_type"] != voucher["fuel_type"] or pump["price_per_liter"] <= 0:
        raise CheckoutError("Verified pump is unavailable.", 409, "fuel_pump_mismatch")
    amount = (liters * pump["price_per_liter"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0 or amount > voucher["max_amount"] or (voucher["max_liters"] is not None and liters > voucher["max_liters"]) or liters > pump["current_stock_liters"]:
        raise CheckoutError("Dispense exceeds authorization or available stock.", 400, "fuel_cap_exceeded")
    station_wallet = _wallet(db, station, "fuel_station")
    own_used = min(amount, voucher["wallet_authorized"])
    credit_used = amount - own_used
    reference = f"fuel:{voucher_id}"
    _mutate_wallet(db, wallet, balance=-own_used, locked=-voucher["wallet_authorized"])
    if own_used:
        _wallet_tx(db, wallet, "fuel_charge", -own_used, reference)
    if platform:
        _mutate_wallet(db, platform, balance=-credit_used, locked=-voucher["credit_authorized"])
        if credit_used:
            _wallet_tx(db, platform, "fuel_credit_funding", -credit_used, reference)
        db.execute_exact("UPDATE fuel_platform_treasury SET verified_liquidity=verified_liquidity-%s WHERE singleton=true", (credit_used,))
    _mutate_wallet(db, station_wallet, balance=amount)
    _wallet_tx(db, station_wallet, "fuel_sale", amount, reference)
    db.execute_exact("UPDATE fuel_credit_accounts SET reserved_credit=reserved_credit-%s,outstanding_credit=outstanding_credit+%s,"
                     "utilized_credit=utilized_credit+%s,released_credit=released_credit+%s,updated_at=now() WHERE transporter_user_id=%s",
                     (voucher["credit_authorized"], credit_used, credit_used, voucher["credit_authorized"]-credit_used, voucher["transporter_user_id"]))
    if credit_used:
        _event(db, voucher["transporter_user_id"], voucher_id, "utilize", credit_used, reference + ":utilize")
    if voucher["credit_authorized"] > credit_used:
        _event(db, voucher["transporter_user_id"], voucher_id, "release", voucher["credit_authorized"]-credit_used, reference + ":unused_credit")
    lines = [(f"wallet:{station}", amount)]
    if voucher["wallet_authorized"]:
        lines.extend([(f"fuel_authorization:{voucher_id}:wallet", -voucher["wallet_authorized"]),
                      (f"wallet:{voucher['transporter_user_id']}", voucher["wallet_authorized"]-own_used)])
    if platform:
        lines.extend([(f"fuel_authorization:{voucher_id}:platform", -voucher["credit_authorized"]),
                      (f"wallet:{platform['user_id']}", voucher["credit_authorized"]-credit_used)])
    post_journal(db, reference + ":dispense", "fuel_dispense", reference, lines)
    db.execute_exact("UPDATE fuel_station_pumps SET current_stock_liters=current_stock_liters-%s,updated_at=now() WHERE id=%s", (liters, pump_id))
    slip = db.execute_exact(
        "INSERT INTO fuel_station_dispenses(user_id,pump_id,vehicle_plate,fuel_type,liters,price_per_liter,total_pkr,payment_method,notes) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,'wallet',%s) RETURNING id",
        (station, pump_id, voucher["truck_plate"], voucher["fuel_type"], liters, pump["price_per_liter"], amount, reference),
    ).fetchone()
    row = db.execute_exact("UPDATE fuel_vouchers SET status='dispensed',actual_amount=%s,actual_liters=%s,wallet_utilized=%s,credit_utilized=%s,dispense_id=%s,finalized_at=now() WHERE id=%s RETURNING *",
                           (amount, liters, own_used, credit_used, slip["id"], voucher_id)).fetchone()
    return {"voucher": safe_voucher(row), "replayed": False, "platform_fee": "0.00"}


def cancel_voucher(db, voucher_id, owner=None, *, expired_only=False):
    voucher, wallet, account, _treasury_row, platform = _voucher_context(db, voucher_id)
    if owner is not None and owner != voucher["transporter_user_id"]:
        raise CheckoutError("Voucher not found.", 404, "fuel_voucher_not_found")
    if voucher["status"] not in {"authorized", "verified"} or (expired_only and not voucher["expired"]):
        return {"voucher": safe_voucher(voucher), "replayed": True}
    reference = f"fuel:{voucher_id}"
    own, credit = voucher["wallet_authorized"], voucher["credit_authorized"]
    if own:
        _mutate_wallet(db, wallet, locked=-own)
        _wallet_tx(db, wallet, "fuel_release", own, reference)
        post_journal(db, reference + ":wallet_release", "fuel_release", reference,
                     [(f"fuel_authorization:{voucher_id}:wallet", -own), (f"wallet:{voucher['transporter_user_id']}", own)])
    if credit:
        _mutate_wallet(db, platform, locked=-credit)
        db.execute_exact("UPDATE fuel_credit_accounts SET reserved_credit=reserved_credit-%s,released_credit=released_credit+%s,updated_at=now() WHERE transporter_user_id=%s",
                         (credit, credit, voucher["transporter_user_id"]))
        _event(db, voucher["transporter_user_id"], voucher_id, "release", credit, reference + ":cancel_release")
        post_journal(db, reference + ":credit_release", "fuel_credit_release", reference,
                     [(f"fuel_authorization:{voucher_id}:platform", -credit), (f"wallet:{platform['user_id']}", credit)])
    status = "expired" if voucher["expired"] else "cancelled"
    row = db.execute_exact("UPDATE fuel_vouchers SET status=%s,finalized_at=now() WHERE id=%s RETURNING *", (status, voucher_id)).fetchone()
    return {"voucher": safe_voucher(row), "replayed": False}


def recover_from_earnings(db, transporter_id, entitlement, reference):
    """Caller holds transporter wallet. Return debt recovered from payable only."""
    entitlement = money(entitlement)
    prior = db.execute_exact("SELECT amount FROM fuel_credit_events WHERE reference=%s", ("recover:" + reference,)).fetchone()
    if prior:
        return prior["amount"]
    account = _account(db, transporter_id)
    prior = db.execute_exact("SELECT amount FROM fuel_credit_events WHERE reference=%s", ("recover:" + reference,)).fetchone()
    if prior:
        return prior["amount"]
    recovered = min(entitlement, account["outstanding_credit"])
    if recovered <= 0:
        return ZERO
    _treasury_row, platform = _treasury(db,existing_authorization=True)
    _mutate_wallet(db, platform, balance=recovered)
    _wallet_tx(db, platform, "fuel_credit_recovery", recovered, reference)
    db.execute_exact("UPDATE fuel_platform_treasury SET verified_liquidity=verified_liquidity+%s WHERE singleton=true", (recovered,))
    db.execute_exact("UPDATE fuel_credit_accounts SET outstanding_credit=outstanding_credit-%s,recovered_credit=recovered_credit+%s,updated_at=now() WHERE transporter_user_id=%s",
                     (recovered, recovered, transporter_id))
    # FIFO provenance identifies which cancelled trip's debt has been repaid.
    remaining = recovered
    vouchers = db.execute_exact(
        "SELECT v.id,v.credit_utilized-coalesce((SELECT sum(e.amount) FROM fuel_credit_events e WHERE e.voucher_id=v.id AND e.event_type='recover_allocation'),0) AS due "
        "FROM fuel_vouchers v WHERE v.transporter_user_id=%s AND v.status='dispensed' AND v.credit_utilized>0 ORDER BY v.id", (transporter_id,),
    ).fetchall()
    for voucher in vouchers:
        amount = min(remaining, voucher["due"])
        if amount > 0:
            _event(db, transporter_id, voucher["id"], "recover_allocation", amount, f"recover_allocation:{reference}:{voucher['id']}")
            remaining -= amount
        if remaining == 0:
            break
    if remaining:
        raise CheckoutError("Fuel credit cannot be reconciled to utilized vouchers.", 409, "fuel_credit_reconciliation_failed")
    _event(db, transporter_id, None, "recover", recovered, "recover:" + reference)
    db.execute_exact("UPDATE fuel_credit_accounts SET cancellation_debt=%s WHERE transporter_user_id=%s", (_has_cancelled_debt(db, transporter_id), transporter_id))
    post_journal(db, "fuel_recovery:" + reference, "fuel_credit_recovery", reference,
                 [("fuel_credit_recovery:" + reference, -recovered), (f"wallet:{platform['user_id']}", recovered)])
    return recovered


def _legacy_credit_schema_present(db):
    # Pre-cutover lightweight installations cannot have this new credit debt.
    # A partially present credit schema must still fail rather than forgive debt.
    return bool(db.execute("SELECT to_regclass('fuel_credit_accounts') AS relation").fetchone()['relation'])


def legacy_earnings_recovery(db, reference):
    """Read an immutable recovery for a future legacy-contract payout."""
    if not _legacy_credit_schema_present(db):
        return ZERO
    row=db.execute_exact('SELECT amount FROM fuel_credit_events WHERE reference=%s',('recover:'+reference,)).fetchone()
    return row['amount'] if row else ZERO


def recover_legacy_earnings(db, transporter_id, entitlement, reference):
    """Offset approved new credit against future earnings, preserving old fees.

    Caller holds the original payment and Transporter wallet, guards payout
    replay and posts the source-payable to recovery-clearing journal bridge.
    No historical settlement, commission or earned-fare amount is recalculated.
    """
    if not _legacy_credit_schema_present(db):
        return ZERO
    account=db.execute_exact('SELECT outstanding_credit FROM fuel_credit_accounts WHERE transporter_user_id=%s FOR UPDATE',(transporter_id,)).fetchone()
    if not account:
        return ZERO
    prior=legacy_earnings_recovery(db,reference)
    if prior:
        return prior
    if account['outstanding_credit']<=0:
        return ZERO
    return recover_from_earnings(db,transporter_id,money(entitlement),reference)


def annotate_legacy_earnings(db, rows, source):
    """Batch invoice offsets without repricing original legacy snapshots."""
    if source != 'legacy_freight':
        raise ValueError('Unknown earnings source.')
    rows=[dict(row) for row in rows]
    eligible=[row for row in rows if row.get('status') in {'released','paid'}
              and (source!='legacy_freight' or row.get('business_rules_version') is None)]
    if not eligible or not _legacy_credit_schema_present(db):
        return rows
    references=['recover:'+source+':'+str(row['id']) for row in eligible]
    events=db.execute_exact('SELECT reference,amount FROM fuel_credit_events WHERE event_type=%s AND reference=ANY(%s)',('recover',references)).fetchall()
    amounts={event['reference']:event['amount'] for event in events}
    for row in eligible:
        recovered=amounts.get('recover:'+source+':'+str(row['id']),ZERO)
        if recovered:
            entitlement=Decimal(str(row['transporter_amount']))
            if recovered<0 or recovered>entitlement:
                raise CheckoutError('Legacy earnings recovery cannot be reconciled to its payable.',409,'fuel_credit_reconciliation_failed')
            row.update(transporter_entitlement=format(entitlement,'.2f'),fuel_credit_recovered=format(recovered,'.2f'),
                       wallet_credit_amount=format(entitlement-recovered,'.2f'))
    return rows
