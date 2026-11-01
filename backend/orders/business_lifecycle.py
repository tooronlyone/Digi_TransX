"""Rules 1-4 delivery handshake and settlement for explicitly versioned bookings.

Existing bookings keep their original lifecycle. All new money is exact Decimal,
all writes share the caller's transaction, and source locks precede financial
locks. No worker, complaint, or completion claim can bypass the OTP handshake.
"""
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from shared.payments import CheckoutError
from shared import notifications as notif

RULES_VERSION = 'rules-1-4-v1'
INSURANCE_NOTICE = "Goods Insurance is recommended. Uninsured cargo is transported at shipper's own risk."
CENT = Decimal('0.01')
OTP_LIFETIME = timedelta(minutes=10)

def _now(value=None):
    return value or datetime.now(timezone.utc)

def _datetime(value):
    parsed = datetime.fromisoformat(value) if isinstance(value,str) else value
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)

def _exact(db,sql,args=()):
    return db.execute_exact(sql,args)

def payment_for_trip(db,trip_id,lock=False):
    return _exact(db,'SELECT * FROM payments WHERE trip_id=%s ORDER BY id DESC LIMIT 1'+(' FOR UPDATE' if lock else ''),(trip_id,)).fetchone()

def uses_business_rules(db,trip_id):
    # This discriminator carries no money and works with legacy instrumentation
    # wrappers; only the new financial service requires execute_exact.
    payment = db.execute('SELECT business_rules_version FROM payments WHERE trip_id=%s ORDER BY id DESC LIMIT 1',(trip_id,)).fetchone()
    return bool(payment and payment.get('business_rules_version') == RULES_VERSION)

def _source(db,order_id,trip_id):
    from .lifecycle import _lock_order_trip
    return _lock_order_trip(db,order_id,trip_id)

def _secret():
    key = os.environ.get('DIGITRANSX_DELIVERY_OTP_SECRET','')
    if len(key) < 32:
        raise CheckoutError('Delivery OTP channel is not configured. Contact support.',503,'delivery_otp_configuration_required')
    return key.encode('utf-8')

def _code(nonce):
    # The random 256-bit nonce and external secret permit an authorized in-app
    # reveal without storing plaintext codes or making offline DB guesses useful.
    digest = hmac.new(_secret(),('delivery-code:'+nonce).encode(),hashlib.sha256).digest()
    return str(int.from_bytes(digest,'big') % 100000000).zfill(8)

def _digest(code,nonce):
    return hmac.new(_secret(),('delivery-proof:'+nonce+':'+code).encode(),hashlib.sha256).hexdigest()

def issue_delivery_otp(db,user,order_id,trip_id,now=None):
    now = _now(now)
    order,trip = _source(db,order_id,trip_id)
    if trip['transporter_user_id'] != user['id']:
        raise CheckoutError('Access denied.',403)
    if trip['status'] not in {'in_progress','awaiting_client_confirmation'}:
        raise CheckoutError('Only an in-progress trip can request completion.',409,'trip_not_in_progress')
    payment = payment_for_trip(db,trip_id,True)
    if not payment or payment['status'] != 'held' or payment.get('business_rules_version') != RULES_VERSION:
        raise CheckoutError('A held booking escrow is required.',409,'payment_not_held')
    _secret() # Validate channel before any state mutation.
    current = _exact(db,'SELECT * FROM delivery_otp_challenges WHERE trip_id=%s FOR UPDATE',(trip_id,)).fetchone()
    if current and current.get('consumed_at') is None and _datetime(current['expires_at']) > now:
        return {'already':True,'otp_required':True,'trip':trip,'confirmation_deadline_at':current['expires_at']}
    nonce = secrets.token_urlsafe(32)
    expires = now+OTP_LIFETIME
    code = _code(nonce)
    _exact(db,"INSERT INTO delivery_otp_challenges(trip_id,client_user_id,transporter_user_id,nonce,code_digest,expires_at) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(trip_id) DO UPDATE SET nonce=excluded.nonce,code_digest=excluded.code_digest,expires_at=excluded.expires_at,attempts=0,revealed_at=null,consumed_at=null,created_at=now()",(trip_id,order['client_user_id'],user['id'],nonce,_digest(code,nonce),expires))
    from .lifecycle import _set_trip_and_shipment
    _set_trip_and_shipment(db,trip_id,order_id,'awaiting_client_confirmation',{'delivery_completion_requested_at':now,'confirmation_deadline_at':expires})
    notif.notify(db,order_id,trip_id,order['client_user_id'],notif.DELIVERY_CONFIRMATION_REQUESTED,'Inspect your cargo, then reveal and share the delivery OTP only when you accept delivery.')
    trip = db.execute('SELECT * FROM shipment_trips WHERE id=%s',(trip_id,)).fetchone()
    return {'already':False,'otp_required':True,'trip':trip,'confirmation_deadline_at':expires.isoformat()}

def delivery_otp_for_client(db,user,order_id,trip_id,reveal=False,now=None):
    now = _now(now)
    order,trip = _source(db,order_id,trip_id)
    if order['client_user_id'] != user['id']:
        raise CheckoutError('Access denied.',403)
    challenge = _exact(db,'SELECT * FROM delivery_otp_challenges WHERE trip_id=%s FOR UPDATE',(trip_id,)).fetchone()
    if not challenge or challenge.get('consumed_at') or _datetime(challenge['expires_at']) <= now or challenge['attempts'] >= 5:
        raise CheckoutError('No active delivery OTP. Ask the transporter to request a new code.',409,'delivery_otp_unavailable')
    if trip['status'] != 'awaiting_client_confirmation':
        raise CheckoutError('Delivery is not awaiting an OTP.',409,'delivery_otp_unavailable')
    result = {'available':True,'expires_at':challenge['expires_at'],'inspection_notice':'Inspect your cargo. Share this OTP only when delivery is accepted.'}
    if reveal:
        _exact(db,'UPDATE delivery_otp_challenges SET revealed_at=COALESCE(revealed_at,%s) WHERE trip_id=%s',(now,trip_id))
        result['otp'] = _code(challenge['nonce'])
    return result

def _wallet_credit(db,user_id,amount,kind,reference):
    if amount == 0:
        return
    row = _exact(db,'UPDATE wallets SET balance=balance+%s,updated_at=now() WHERE user_id=%s RETURNING id,balance',(amount,user_id)).fetchone()
    if not row:
        raise CheckoutError('Settlement wallet unavailable.',409,'wallet_unavailable')
    _exact(db,'INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,reference_id,balance_after,description) VALUES(%s,%s,%s,%s,%s,%s,%s)',(row['id'],user_id,kind,amount,reference,row['balance'],'Rules 1-4 freight settlement'))

def serialize_settlement(row):
    if not row:
        return None
    result = dict(row)
    for key,value in result.items():
        if isinstance(value,Decimal): result[key] = format(value,'.2f')
    if isinstance(result.get('fee_breakdown'),str):
        result['fee_breakdown'] = json.loads(result['fee_breakdown'])
    return result

def settle_verified_delivery(db,payment,now=None):
    """Called only after authoritative OTP completion; no arbitrary release API."""
    now = _now(now)
    existing = _exact(db,'SELECT * FROM freight_settlements WHERE payment_id=%s FOR UPDATE',(payment['id'],)).fetchone()
    if existing:
        return serialize_settlement(existing)
    if payment.get('business_rules_version') != RULES_VERSION or payment['status'] != 'held':
        raise CheckoutError('Payment is not eligible for this settlement.',409,'invalid_settlement_policy')
    trip = db.execute('SELECT status FROM shipment_trips WHERE id=%s',(payment['trip_id'],)).fetchone()
    proof = db.execute('SELECT consumed_at FROM delivery_otp_challenges WHERE trip_id=%s',(payment['trip_id'],)).fetchone()
    if not trip or trip['status'] != 'completed' or not proof or not proof.get('consumed_at'):
        raise CheckoutError('A verified delivery OTP is required before settlement.',409,'delivery_otp_required')
    transporter = payment['transporter_user_id']
    if not _exact(db,'SELECT id FROM wallets WHERE user_id=%s FOR UPDATE',(transporter,)).fetchone():
        raise CheckoutError('Transporter wallet unavailable.',409,'wallet_unavailable')
    from shared.fuel_credit import recover_from_earnings
    from shared.reserves import progressive_contribution
    from shared.financial_ledger import post_journal
    gross = Decimal(str(payment['bid_price']))
    commission = Decimal(str(payment['company_fee']))
    net = Decimal(str(payment['transporter_amount']))
    if commission+net != gross or commission != (gross*Decimal('.20')).quantize(CENT,rounding=ROUND_HALF_UP):
        raise CheckoutError('Commission snapshot does not match the approved booking policy.',409,'split_mismatch')
    recovered = recover_from_earnings(db,transporter,net,f'freight:{payment["id"]}')
    if recovered < 0 or recovered > net:
        raise CheckoutError('Fuel recovery exceeds payable earnings.',409,'fuel_recovery_mismatch')
    contribution,policy_state = progressive_contribution(db,transporter,net-recovered,f'freight:reserve:{payment["id"]}')
    payable = net-recovered-contribution
    first = (payable/2).quantize(CENT,rounding=ROUND_HALF_UP)
    second = payable-first
    _wallet_credit(db,transporter,first,'freight_tranche1',f'freight:{payment["id"]}:1')
    fees = payment.get('fee_breakdown') or {}
    if isinstance(fees,str): fees=json.loads(fees)
    settlement = _exact(db,"INSERT INTO freight_settlements(payment_id,trip_id,transporter_user_id,client_user_id,gross_amount,company_fee,net_entitlement,fuel_credit_recovered,reserve_contribution,tranche1_amount,tranche2_amount,fee_breakdown,reserve_policy_state,completed_at,dispute_deadline_at,release_eligible_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",(payment['id'],payment['trip_id'],transporter,payment['client_user_id'],gross,commission,net,recovered,contribution,first,second,json.dumps(fees),policy_state,now,now+timedelta(minutes=90),now+timedelta(minutes=120))).fetchone()
    post_journal(db,f'freight:settle:{payment["id"]}','freight_settlement',str(payment['id']),[(f'escrow:{payment["id"]}',-gross),('revenue:freight',commission),(f'wallet:{transporter}',first),(f'reserve:{transporter}',contribution),(f'freight_payable:{payment["id"]}',second),(f'fuel_credit_recovery:freight:{payment["id"]}',recovered)])
    return serialize_settlement(settlement)

def verify_delivery_otp(db,user,order_id,trip_id,code,now=None):
    now = _now(now)
    order,trip = _source(db,order_id,trip_id)
    if trip['transporter_user_id'] != user['id']:
        raise CheckoutError('Access denied.',403)
    if trip['status'] != 'awaiting_client_confirmation':
        raise CheckoutError('Delivery OTP has already been used or this trip is not awaiting delivery.',409,'delivery_otp_replayed')
    payment = payment_for_trip(db,trip_id,True)
    if not payment or payment.get('business_rules_version') != RULES_VERSION:
        raise CheckoutError('This booking uses its original delivery policy.',409,'legacy_delivery_policy')
    challenge = _exact(db,'SELECT * FROM delivery_otp_challenges WHERE trip_id=%s FOR UPDATE',(trip_id,)).fetchone()
    if not challenge or challenge.get('consumed_at') or _datetime(challenge['expires_at']) <= now or challenge['attempts'] >= 5:
        raise CheckoutError('Delivery OTP is expired, used, or locked.',409,'delivery_otp_unavailable')
    if not challenge.get('revealed_at'):
        raise CheckoutError('The client must authorize and reveal the delivery OTP first.',409,'delivery_otp_not_authorized')
    supplied = str(code or '')
    if len(supplied) != 8 or not supplied.isdigit() or not hmac.compare_digest(_digest(supplied,challenge['nonce']),challenge['code_digest']):
        _exact(db,'UPDATE delivery_otp_challenges SET attempts=attempts+1 WHERE trip_id=%s',(trip_id,))
        # Caller COMMITS this result so failed-attempt limits survive HTTP errors.
        return {'verified':False,'code':'delivery_otp_invalid','message':'Invalid delivery OTP.','remaining_attempts':4-challenge['attempts']}
    _exact(db,'UPDATE delivery_otp_challenges SET consumed_at=%s WHERE trip_id=%s',(now,trip_id))
    from .lifecycle import _set_trip_and_shipment
    _set_trip_and_shipment(db,trip_id,order_id,'completed',{'delivery_confirmed_at':now,'trip_completed_at':now})
    settlement = settle_verified_delivery(db,payment,now)
    notif.notify(db,order_id,trip_id,order['client_user_id'],notif.DELIVERY_CONFIRMED,'Delivery OTP verified. Your 90-minute delivery dispute window has started.')
    notif.notify(db,order_id,trip_id,user['id'],notif.DELIVERY_CONFIRMED,'Delivery verified. First settlement tranche is available; the remainder becomes eligible after 120 minutes, subject to disputes.')
    return {'verified':True,'trip':db.execute('SELECT * FROM shipment_trips WHERE id=%s',(trip_id,)).fetchone(),'settlement':settlement}

def open_delivery_dispute(db,user,order_id,trip_id,reason,evidence=None,now=None):
    now = _now(now)
    order,trip = _source(db,order_id,trip_id)
    if order['client_user_id'] != user['id']:
        raise CheckoutError('Access denied.',403)
    reason = (reason or '').strip()
    if not reason or len(reason)>10000:
        raise CheckoutError('A delivery dispute reason of 1-10000 characters is required.',400,'dispute_reason_required')
    if evidence is not None and (not isinstance(evidence,list) or len(evidence)>25 or len(json.dumps(evidence))>65536):
        raise CheckoutError('Evidence must be a bounded list of authenticated evidence references.',400,'invalid_evidence')
    from .lifecycle import _get_open_dispute,_ensure_thread,_open_or_reuse_dispute,serialize_dispute
    existing = _get_open_dispute(db,trip_id)
    if existing:
        return {'already':True,'dispute':serialize_dispute(existing)}
    payment = payment_for_trip(db,trip_id,True)
    settlement = _exact(db,'SELECT * FROM freight_settlements WHERE trip_id=%s FOR UPDATE',(trip_id,)).fetchone()
    if not settlement or settlement['status'] != 'pending_release' or now >= _datetime(settlement['dispute_deadline_at']):
        raise CheckoutError('The 90-minute delivery dispute window has closed.',409,'dispute_window_closed')
    dispute,_ = _open_or_reuse_dispute(db,order,trip,payment,'client_no',_ensure_thread(db,order,trip),reason)
    _exact(db,"UPDATE freight_settlements SET status='disputed' WHERE id=%s",(settlement['id'],))
    if evidence:
        _exact(db,'INSERT INTO delivery_incident_evidence(dispute_id,submitted_by,evidence) VALUES(%s,%s,%s)',(dispute['id'],user['id'],json.dumps(evidence)))
    notif.notify_admins(db,order_id,trip_id,notif.DELIVERY_DENIED,f'Investigate delivery dispute on order #{order_id}. No penalty has been applied.')
    notif.notify(db,order_id,trip_id,trip['transporter_user_id'],notif.DELIVERY_DENIED,'A delivery dispute is under investigation. The applicable unpaid tranche remains held; no penalty or reserve debit has been applied.')
    return {'already':False,'dispute':serialize_dispute(dispute)}

def release_due_settlements(db,now=None,limit=100):
    now = _now(now)
    candidates = _exact(db,"SELECT fs.id,fs.trip_id,p.shipment_id FROM freight_settlements fs JOIN payments p ON p.id=fs.payment_id WHERE fs.status='pending_release' AND fs.release_eligible_at<=%s ORDER BY fs.release_eligible_at,fs.id LIMIT %s",(now,limit)).fetchall()
    released=[]
    for candidate in candidates:
        # Skip locked source first: never invert source -> payment -> settlement.
        order = db.execute('SELECT id FROM shipments WHERE id=%s FOR UPDATE SKIP LOCKED',(candidate['shipment_id'],)).fetchone()
        if not order: continue
        db.execute('SELECT id FROM shipment_trips WHERE id=%s FOR UPDATE',(candidate['trip_id'],))
        from .lifecycle import _get_open_dispute
        dispute = _get_open_dispute(db,candidate['trip_id'])
        payment = payment_for_trip(db,candidate['trip_id'],True)
        settlement = _exact(db,'SELECT * FROM freight_settlements WHERE id=%s FOR UPDATE',(candidate['id'],)).fetchone()
        if dispute or settlement['status'] != 'pending_release' or _datetime(settlement['release_eligible_at'])>now:
            continue
        if payment['status'] != 'held':
            raise CheckoutError('Settlement payment status is inconsistent.',409,'settlement_payment_mismatch')
        _exact(db,'SELECT id FROM wallets WHERE user_id=%s FOR UPDATE',(settlement['transporter_user_id'],))
        amount = Decimal(str(settlement['tranche2_amount']))
        _wallet_credit(db,settlement['transporter_user_id'],amount,'freight_tranche2',f'freight:{payment["id"]}:2')
        from shared.financial_ledger import post_journal
        if amount:
            post_journal(db,f'freight:release:{payment["id"]}','freight_tranche2',str(payment['id']),[(f'freight_payable:{payment["id"]}',-amount),(f'wallet:{settlement["transporter_user_id"]}',amount)])
        _exact(db,"UPDATE freight_settlements SET status='released',second_released_at=%s WHERE id=%s",(now,settlement['id']))
        _exact(db,"UPDATE payments SET status='released',released_at=%s WHERE id=%s",(now,payment['id']))
        db.execute("UPDATE shipments SET payment_status='released',updated_at=now() WHERE id=%s",(candidate['shipment_id'],))
        released.append(settlement['id'])
    return {'released_count':len(released),'settlement_ids':released}


def resolve_delivery_settlement(db,admin,settlement_id,client_refund_amount,notes,evidence,investigation_result,now=None):
    """Explicit allocation of still-held money; never invents a penalty/clawback.

    This is not a liability limit. Any remedy beyond held funds needs a separate
    authorized recovery decision and cannot be guessed by this endpoint.
    """
    from auth.helpers import require_admin_role
    if require_admin_role(admin):
        raise CheckoutError('Administrator access required.',403)
    if not isinstance(notes,str) or not notes.strip() or len(notes)>20000 or not isinstance(evidence,list) or not evidence or len(json.dumps(evidence))>65536:
        raise CheckoutError('An evidence-based investigation result, notes and evidence references are required.',400,'investigation_required')
    if investigation_result not in {'verified_accident','verified_misconduct','unsubstantiated','delivery_accepted','other_verified'}:
        raise CheckoutError('A verified investigation decision is required.',400,'investigation_required')
    try:
        if isinstance(client_refund_amount,(bool,float)):
            raise ValueError()
        refund=Decimal(str(client_refund_amount))
        if not refund.is_finite() or refund<0 or refund!=refund.quantize(CENT):raise ValueError()
    except (ValueError,ArithmeticError):
        raise CheckoutError('Client refund amount must be exact nonnegative money.',400,'invalid_refund_amount')
    now=_now(now)
    candidate=_exact(db,'SELECT fs.trip_id,p.shipment_id FROM freight_settlements fs JOIN payments p ON p.id=fs.payment_id WHERE fs.id=%s',(settlement_id,)).fetchone()
    if not candidate:raise CheckoutError('Settlement not found.',404)
    order,trip=_source(db,candidate['shipment_id'],candidate['trip_id'])
    from .lifecycle import _get_open_dispute
    dispute=_get_open_dispute(db,trip['id'])
    payment=payment_for_trip(db,trip['id'],True)
    settlement=_exact(db,'SELECT * FROM freight_settlements WHERE id=%s FOR UPDATE',(settlement_id,)).fetchone()
    prior=_exact(db,'SELECT * FROM freight_settlement_resolutions WHERE settlement_id=%s',(settlement_id,)).fetchone()
    if prior:
        if Decimal(str(prior['client_refund_amount']))!=refund or prior['notes']!=notes.strip() or prior['investigation_result']!=investigation_result:
            raise CheckoutError('Settlement was already resolved with a different allocation.',409,'resolution_conflict')
        return {'already':True,'resolution':serialize_settlement(prior)}
    if not dispute or settlement['status']!='disputed':
        raise CheckoutError('Only an investigated open settlement dispute can be resolved.',409,'settlement_not_disputed')
    held=Decimal(str(settlement['tranche2_amount']))
    if refund>held:
        raise CheckoutError('The requested refund exceeds funds still held. A separate authorized recovery decision is required; no reserve or paid earnings are automatically confiscated.',409,'additional_recovery_authorization_required')
    release=held-refund
    # Lock both recipients in stable ID order before credits.
    _exact(db,'SELECT id FROM wallets WHERE user_id=ANY(%s) ORDER BY user_id FOR UPDATE',([order['client_user_id'],trip['transporter_user_id']],))
    _wallet_credit(db,order['client_user_id'],refund,'freight_dispute_refund',f'freight:{payment["id"]}:dispute')
    _wallet_credit(db,trip['transporter_user_id'],release,'freight_tranche2',f'freight:{payment["id"]}:2')
    if held:
        from shared.financial_ledger import post_journal
        post_journal(db,f'freight:resolve:{payment["id"]}','freight_dispute_resolution',str(payment['id']),[(f'freight_payable:{payment["id"]}',-held),(f'wallet:{order["client_user_id"]}',refund),(f'wallet:{trip["transporter_user_id"]}',release)])
    result=_exact(db,'INSERT INTO freight_settlement_resolutions(settlement_id,dispute_id,admin_user_id,client_refund_amount,transporter_release_amount,investigation_result,notes,evidence) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(settlement_id,dispute['id'],admin['id'],refund,release,investigation_result,notes.strip(),json.dumps(evidence))).fetchone()
    status='resolved_client' if refund else 'released'
    _exact(db,'UPDATE freight_settlements SET status=%s,second_released_at=%s WHERE id=%s',(status,now,settlement_id))
    _exact(db,"UPDATE payments SET status='released',released_at=%s WHERE id=%s",(now,payment['id']))
    db.execute("UPDATE shipments SET payment_status='released',updated_at=now() WHERE id=%s",(order['id'],))
    db.execute('UPDATE shipment_disputes SET status=%s,resolution=%s,admin_user_id=%s,admin_notes=%s,resolved_at=%s WHERE id=%s',('resolved_client' if refund else 'resolved_transporter','client_win' if refund else 'transporter_win',admin['id'],notes.strip(),now,dispute['id']))
    notif.notify(db,order['id'],trip['id'],order['client_user_id'],'settlement_resolved',f'An administrator resolved the delivery investigation. Refund from held funds: PKR {refund:,.2f}.')
    notif.notify(db,order['id'],trip['id'],trip['transporter_user_id'],'settlement_resolved',f'An administrator resolved the delivery investigation. Remaining release: PKR {release:,.2f}.')
    return {'already':False,'resolution':serialize_settlement(result)}
