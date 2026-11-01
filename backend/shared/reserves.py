"""Separate security collateral; policy gaps never produce guessed deductions."""
from decimal import Decimal, ROUND_HALF_UP
from shared.payments import CheckoutError

CENT = Decimal('0.01')

def _approved_bracket(db,count):
    return db.execute_exact("SELECT b.ceiling FROM security_reserve_brackets b LEFT JOIN users u ON u.id=b.approved_by WHERE b.truck_count=%s AND (b.truck_count IN (15,40,70,100,200) OR (b.approved_at<=CURRENT_TIMESTAMP AND u.role='admin' AND length(btrim(b.approval_evidence))>=10))",(count,)).fetchone()

def review_reserve_requirement(db,user_id):
    """Refresh only the review flag after a verified fleet change; never release."""
    count=db.execute_exact("SELECT COUNT(*) AS n FROM vehicles WHERE owner_user_id=%s AND status IN ('active','on_job')",(user_id,)).fetchone()['n']
    bracket=_approved_bracket(db,count)
    state='reference_point_reviewed' if bracket else 'fleet_range_approval_required'
    db.execute_exact('UPDATE security_reserves SET fleet_count=%s,policy_state=%s,updated_at=now() WHERE user_id=%s',(count,state,user_id))
    return {'fleet_count':count,'ceiling':format(Decimal(str(bracket['ceiling'])),'.2f') if bracket else None,'policy_state':state}

def ensure_security_reserve(db, user_id, role='transporter'):
    """Caller locks source trip before wallet. Does not commit or spend collateral."""
    kind = 'temporary_driver' if role in {'driver','temporary_driver'} else 'transporter'
    required = Decimal('10000') if kind == 'temporary_driver' else Decimal('30000')
    wallet = db.execute_exact('SELECT * FROM wallets WHERE user_id=%s FOR UPDATE',(user_id,)).fetchone()
    if not wallet or Decimal(str(wallet['balance'])) < required:
        raise CheckoutError(f'PKR {required:,.2f} must be funded and frozen in your security reserve before accepting a booking.',409,'security_reserve_required')
    existing = db.execute_exact('SELECT * FROM security_reserves WHERE user_id=%s FOR UPDATE',(user_id,)).fetchone()
    if existing:
        if Decimal(str(existing['balance'])) < required:
            raise CheckoutError('Security reserve must be restored before accepting a booking.',409,'security_reserve_required')
        if Decimal(str(wallet['locked_balance'])) < Decimal(str(existing['balance'])):
            raise CheckoutError('Security reserve backing is inconsistent. Reconciliation is required before accepting a booking.',409,'security_reserve_reconciliation_required')
        db.execute_exact('UPDATE wallets SET minimum_required=GREATEST(minimum_required,%s) WHERE user_id=%s',(existing['balance'],user_id))
        return existing
    # The transporter minimum was already included in aggregate locked_balance;
    # recognize that SAME collateral once, never create a competing second hold.
    floor = Decimal(str(wallet.get('minimum_required') or 0)) if kind == 'transporter' else Decimal('0')
    locked = Decimal(str(wallet['locked_balance']))
    if Decimal('0') < locked < min(floor,required):
        raise CheckoutError('The partial legacy wallet hold cannot be attributed safely. Reconcile existing holds before establishing the security reserve.',409,'security_reserve_reconciliation_required')
    represented = min(locked,floor,required)
    delta = required-represented
    if Decimal(str(wallet['balance']))-locked < delta:
        raise CheckoutError('Insufficient available balance to establish the security reserve.',409,'security_reserve_required')
    db.execute_exact('UPDATE wallets SET locked_balance=locked_balance+%s,minimum_required=GREATEST(minimum_required,%s),is_minimum_met=true,updated_at=now() WHERE user_id=%s',(delta,required,user_id))
    db.execute_exact('INSERT INTO security_reserves(user_id,reserve_kind,balance) VALUES(%s,%s,%s)',(user_id,kind,required))
    db.execute_exact("INSERT INTO security_reserve_entries(user_id,amount,entry_kind,reference) VALUES(%s,%s,'initial',%s)",(user_id,required,f'reserve:initial:{user_id}'))
    if delta:
        from shared.financial_ledger import post_journal
        post_journal(db,f'reserve:initial:{user_id}','security_reserve',str(user_id),[(f'wallet:{user_id}',-delta),(f'reserve:{user_id}',delta)])
    return {'user_id':user_id,'balance':str(required),'reserve_kind':kind}

def progressive_contribution(db,user_id,earnings,reference):
    """Returns exact contribution + explicit unresolved policy state."""
    previous=db.execute_exact('SELECT amount FROM security_reserve_entries WHERE reference=%s',(reference,)).fetchone()
    if previous:
        return Decimal(str(previous['amount'])),'already_contributed'
    reserve = db.execute_exact('SELECT * FROM security_reserves WHERE user_id=%s FOR UPDATE',(user_id,)).fetchone()
    if not reserve:
        return Decimal('0.00'),'reserve_not_established'
    count = db.execute_exact("SELECT COUNT(*) AS n FROM vehicles WHERE owner_user_id=%s AND status IN ('active','on_job')",(user_id,)).fetchone()['n']
    policy = db.execute_exact('SELECT * FROM security_reserve_policy WHERE id=true').fetchone()
    bracket = _approved_bracket(db,count)
    if not policy or policy.get('progressive_percent') is None or not policy.get('approved_at'):
        state = 'progressive_percentage_approval_required'
    elif not bracket:
        state = 'fleet_range_approval_required'
    else:
        remaining = max(Decimal('0'),Decimal(str(bracket['ceiling']))-Decimal(str(reserve['balance'])))
        contribution = min(remaining,(Decimal(str(earnings))*Decimal(str(policy['progressive_percent']))/100).quantize(CENT,rounding=ROUND_HALF_UP))
        state = 'ceiling_reached' if remaining == 0 else 'approved'
        if contribution:
            db.execute_exact('UPDATE wallets SET balance=balance+%s,locked_balance=locked_balance+%s,minimum_required=GREATEST(minimum_required,%s) WHERE user_id=%s',(contribution,contribution,Decimal(str(reserve['balance']))+contribution,user_id))
            db.execute_exact('UPDATE security_reserves SET balance=balance+%s,fleet_count=%s,policy_state=%s,updated_at=now() WHERE user_id=%s',(contribution,count,state,user_id))
            db.execute_exact("INSERT INTO security_reserve_entries(user_id,amount,entry_kind,reference) VALUES(%s,%s,'progressive',%s)",(user_id,contribution,reference))
            wallet=db.execute_exact('SELECT id,balance FROM wallets WHERE user_id=%s',(user_id,)).fetchone()
            db.execute_exact("INSERT INTO wallet_transactions(wallet_id,user_id,type,amount,reference_id,balance_after,description) VALUES(%s,%s,'reserve_contribution',%s,%s,%s,'Approved progressive security reserve contribution')",(wallet['id'],user_id,contribution,reference,wallet['balance']))
        return contribution,state
    db.execute_exact('UPDATE security_reserves SET fleet_count=%s,policy_state=%s,updated_at=now() WHERE user_id=%s',(count,state,user_id))
    return Decimal('0.00'),state
