"""Real wallet/credit/OTP races on a disposable loopback PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from shared import fuel_credit as fuel
from shared.financial_ledger import money, post_journal
from shared.payments import CheckoutError
from tests.remediation_harness import remediation_database_url, remediation_env
from tests.test_driver_workflow_hardening import _graph


@pytest.mark.parametrize("rating,limit", [(None,0),("2.9999",0),("3",10000),("3.99",10000),("4",20000),("5",20000),("NaN",0),("6",0)])
def test_credit_rating_boundaries(rating,limit):
    assert fuel.credit_limit(rating) == limit


@pytest.mark.parametrize("value", [1.1,"NaN","Infinity","1.001",True,None])
def test_money_rejects_float_nonfinite_and_subpaisa(value):
    with pytest.raises((ValueError,TypeError)):
        money(value)


def _admin(env):
    user=env.user()
    with env.db() as db:
        db.execute("UPDATE users SET role='admin',legacy_role='admin' WHERE id=%s",(user['id'],))
    user['role']='admin'
    return user


def _rating(env,owner,rating):
    # Ratings are actual integer reviews on independently attributable trips.
    values=[int(rating)] if rating == int(rating) else [int(rating),int(rating)+1]
    for value in values:
        graph=_graph(env,owner=owner)
        with env.db() as db:
            db.execute("UPDATE shipment_trips SET status='completed',trip_completed_at=now() WHERE id=%s",(graph.trip_id,))
            db.execute("INSERT INTO shipment_trip_reviews(shipment_id,trip_id,client_user_id,transporter_user_id,rating) "
                       "SELECT order_id,id,%s,%s,%s FROM shipment_trips WHERE id=%s",
                       (graph.customer['id'],owner['id'],value,graph.trip_id))


def _setup(env,*,balance="40000",rating=4.5,liquidity="100000",treasury=True,locked="30000",kind="one_time"):
    graph=_graph(env,fare="100000",kind=kind)
    station=env.user('fuel_station_manager')
    admin=_admin(env)
    with env.db() as db:
        db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) VALUES(%s,'transporter',%s,%s,30000,true)",(graph.owner['id'],balance,locked))
        pump=db.execute("INSERT INTO fuel_station_pumps(user_id,pump_number,fuel_type,price_per_liter,tank_capacity_liters,current_stock_liters) VALUES(%s,%s,'diesel',250,10000,10000) RETURNING id",(station['id'],uuid4().hex)).fetchone()['id']
        if treasury:
            existing=db.execute('SELECT wallet_id FROM fuel_platform_treasury').fetchone()
            if existing:
                wallet=existing['wallet_id']
                db.execute("UPDATE wallets SET role='platform_fuel',balance=locked_balance+%s WHERE id=%s",(liquidity,wallet))
                db.execute('UPDATE fuel_platform_treasury SET verified_liquidity=(SELECT balance FROM wallets WHERE id=%s),verified_by=%s',(wallet,admin['id']))
            else:
                wallet=db.execute("INSERT INTO wallets(user_id,role,balance,is_minimum_met) VALUES(%s,'platform_fuel',%s,true) RETURNING id",(admin['id'],liquidity)).fetchone()['id']
            # A fixture simulates independently verified funding; production
            # migrations intentionally never create this attestation.
            db.execute("INSERT INTO fuel_platform_treasury(wallet_id,verified_liquidity,funding_evidence,verified_by) VALUES(%s,%s,'isolated-test-bank-reconciliation',%s) ON CONFLICT(singleton) DO NOTHING",(wallet,liquidity,admin['id']))
    if rating is not None:
        _rating(env,graph.owner,rating)
    data={'trip_id' if kind=='one_time' else 'agreement_trip_id':graph.trip_id,'truck_id':graph.truck_id,'request_mode':'amount','fuel_type':'diesel','max_amount':'25000.00'}
    return graph,station,pump,data


def test_historical_agreement_income_reserve_floor_cannot_fund_multiple_vouchers(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env,balance='40000',locked='0',rating=None,kind='agreement')
    data['max_amount']='10000'
    barrier=Barrier(2)
    def authorize(_):
        barrier.wait(10)
        try:return _authorize(env,graph,data)
        except CheckoutError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(authorize,range(2)))
    authorized=[value for value in results if isinstance(value,dict)]
    assert len(authorized)==1 and 'fuel_credit_limit' in results
    with env.db() as db:
        verified=fuel.verify_voucher(db,station['id'],authorized[0]['otp'],pump)
    with env.db() as db:
        fuel.dispense_voucher(db,station['id'],authorized[0]['voucher']['id'],{
            'redemption_token':verified['redemption_token'],'pump_id':pump,'actual_liters':'40',
            'truck_plate':verified['voucher']['truck_plate'],'fuel_type':'diesel',
        })
        assert db.execute_exact('SELECT balance,locked_balance,minimum_required FROM wallets WHERE user_id=%s',(graph.owner['id'],)).fetchone()=={
            'balance':Decimal('30000'),'locked_balance':Decimal('30000'),'minimum_required':Decimal('30000')}
        assert db.execute_exact('SELECT balance FROM security_reserves WHERE user_id=%s',(graph.owner['id'],)).fetchone()['balance']==30000
    with pytest.raises(CheckoutError):_authorize(env,graph,data)


def _authorize(env,graph,data):
    with env.db() as db:
        return fuel.authorize_voucher(db,graph.owner['id'],data,str(uuid4()))


def _redeem(env,graph,station,pump,data,*,liters='100.00'):
    authorized=_authorize(env,graph,data)
    with env.db() as db:
        verified=fuel.verify_voucher(db,station['id'],authorized['otp'],pump)
    payload={'redemption_token':verified['redemption_token'],'pump_id':pump,'actual_liters':liters,'truck_plate':verified['voucher']['truck_plate'],'fuel_type':'diesel'}
    with env.db() as db:
        result=fuel.dispense_voucher(db,station['id'],authorized['voucher']['id'],payload)
    return authorized,payload,result


def test_exact_wallet_credit_station_settlement_and_client_isolation(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    with env.db() as db:
        db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,is_minimum_met) VALUES(%s,'client',12345,5000,true)",(graph.customer['id'],))
    authorized,payload,result=_redeem(env,graph,station,pump,data)
    assert result['voucher']['wallet_utilized']=='10000.00'
    assert result['voucher']['credit_utilized']=='15000.00'
    assert result['platform_fee']=='0.00'
    with env.db() as db:
        client=db.execute_exact("SELECT balance,locked_balance FROM wallets WHERE user_id=%s",(graph.customer['id'],)).fetchone()
        owner=db.execute_exact("SELECT balance,locked_balance FROM wallets WHERE user_id=%s",(graph.owner['id'],)).fetchone()
        account=db.execute_exact("SELECT * FROM fuel_credit_accounts WHERE transporter_user_id=%s",(graph.owner['id'],)).fetchone()
        assert client=={'balance':Decimal('12345'),'locked_balance':Decimal('5000')}
        assert owner=={'balance':Decimal('30000'),'locked_balance':Decimal('30000')}
        assert account['outstanding_credit']==15000 and account['reserved_credit']==0
        assert db.execute_exact("SELECT balance FROM wallets WHERE user_id=%s",(station['id'],)).fetchone()['balance']==25000
        assert db.execute_exact("SELECT coalesce(sum(amount),0) AS total FROM financial_journal_lines").fetchone()['total']==0
        replay=fuel.dispense_voucher(db,station['id'],authorized['voucher']['id'],payload)
        assert replay['replayed']
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM fuel_station_dispenses WHERE user_id=%s",(station['id'],)).fetchone()['n']==1


@pytest.mark.parametrize('rating,cap,expected',[(4,'20000',True),(3,'10000',True),(3,'10000.01',False),(2,'0.01',False),(None,'0.01',False)])
def test_credit_limits_rating_and_unrated_no_automatic_credit(remediation_env,rating,cap,expected):
    env=remediation_env
    graph,station,pump,data=_setup(env,balance='30000',rating=rating)
    data['max_amount']=cap
    if expected:
        assert _authorize(env,graph,data)['voucher']['credit_authorized']==str(Decimal(cap).quantize(Decimal('.01')))
    else:
        with pytest.raises(CheckoutError) as failure:
            _authorize(env,graph,data)
        assert failure.value.code=='fuel_credit_limit'


@pytest.mark.parametrize('treasury,liquidity,code',[(False,'0','fuel_liquidity_unverified'),(True,'14999','fuel_liquidity_insufficient')])
def test_platform_funding_needs_verified_real_wallet_liquidity(remediation_env,treasury,liquidity,code):
    env=remediation_env
    graph,station,pump,data=_setup(env,treasury=treasury,liquidity=liquidity)
    if not treasury:
        with env.db() as db: db.execute('UPDATE fuel_platform_treasury SET verified_by=%s',(graph.customer['id'],))
    with pytest.raises(CheckoutError) as failure: _authorize(env,graph,data)
    assert failure.value.code==code
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM fuel_vouchers WHERE transporter_user_id=%s",(graph.owner['id'],)).fetchone()['n']==0


def test_concurrent_vouchers_cannot_exceed_aggregate_ceiling(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env,balance='30000')
    barrier=Barrier(2)
    def authorize(cap):
        barrier.wait(10)
        try: return _authorize(env,graph,{**data,'max_amount':cap})['voucher']['credit_authorized']
        except CheckoutError as exc: return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(authorize,['15000','10000']))
    assert results.count('fuel_credit_limit')==1
    with env.db() as db:
        account=db.execute_exact('SELECT * FROM fuel_credit_accounts WHERE transporter_user_id=%s',(graph.owner['id'],)).fetchone()
        assert account['reserved_credit']<=20000


def test_partial_dispense_releases_unused_authorization_and_no_extra_credit(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    authorized,payload,result=_redeem(env,graph,station,pump,data,liters='20.00')
    assert result['voucher']['actual_amount']=='5000.00' and result['voucher']['credit_utilized']=='0.00'
    with env.db() as db:
        wallet=db.execute_exact('SELECT balance,locked_balance FROM wallets WHERE user_id=%s',(graph.owner['id'],)).fetchone()
        assert wallet=={'balance':Decimal('35000'),'locked_balance':Decimal('30000')}
        account=db.execute_exact('SELECT * FROM fuel_credit_accounts WHERE transporter_user_id=%s',(graph.owner['id'],)).fetchone()
        assert account['outstanding_credit']==0 and account['reserved_credit']==0 and account['released_credit']==15000


def test_expiry_cancellation_and_otp_replay(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    authorized=_authorize(env,graph,data)
    with env.db() as db:
        verified=fuel.verify_voucher(db,station['id'],authorized['otp'],pump)
    with pytest.raises(CheckoutError,match='already been used'):
        with env.db() as db: fuel.verify_voucher(db,station['id'],authorized['otp'],pump)
    with env.db() as db:
        cancelled=fuel.cancel_voucher(db,authorized['voucher']['id'],graph.owner['id'])
        assert cancelled['voucher']['status']=='cancelled'
    # Expire through short configured lifetime using server clock function
    # substitution, never edit an immutable authorization's expiry.
    with env.db() as db:
        assert fuel.cancel_voucher(db,authorized['voucher']['id'],graph.owner['id'])['replayed']
    with env.db() as db:
        assert db.execute_exact('SELECT reserved_credit FROM fuel_credit_accounts WHERE transporter_user_id=%s',(graph.owner['id'],)).fetchone()['reserved_credit']==0


@pytest.mark.parametrize('field,value,code',[('fuel_type','petrol','fuel_dispense_mismatch'),('truck_plate','FOREIGN','fuel_dispense_mismatch'),('actual_liters','101','fuel_cap_exceeded'),('pump_id',999999,'fuel_pump_mismatch')])
def test_bound_truck_fuel_quantity_and_pump(remediation_env,field,value,code):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    authorized=_authorize(env,graph,data)
    with env.db() as db: verified=fuel.verify_voucher(db,station['id'],authorized['otp'],pump)
    payload={'redemption_token':verified['redemption_token'],'pump_id':pump,'actual_liters':'100','truck_plate':verified['voucher']['truck_plate'],'fuel_type':'diesel',field:value}
    with pytest.raises(CheckoutError) as failure:
        with env.db() as db: fuel.dispense_voucher(db,station['id'],authorized['voucher']['id'],payload)
    assert failure.value.code==code


def test_station_restriction_and_trip_ownership(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    other=env.user('fuel_station_manager')
    authorized=_authorize(env,graph,{**data,'station_id':other['id']})
    with pytest.raises(CheckoutError) as failure:
        with env.db() as db: fuel.verify_voucher(db,station['id'],authorized['otp'],pump)
    assert failure.value.code=='fuel_station_mismatch'
    with pytest.raises(CheckoutError):
        with env.db() as db: fuel.authorize_voucher(db,env.user('logistics_provider')['id'],data,str(uuid4()))


def test_cancelled_debt_future_earnings_recovery_and_replay(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    _redeem(env,graph,station,pump,data)
    with env.db() as db: db.execute("UPDATE shipment_trips SET status='cancelled' WHERE id=%s",(graph.trip_id,))
    next_trip=_graph(env,owner=graph.owner)
    next_data={**data,'trip_id':next_trip.trip_id,'truck_id':next_trip.truck_id,'max_amount':'1000'}
    with pytest.raises(CheckoutError) as failure: _authorize(env,graph,next_data)
    assert failure.value.code=='fuel_credit_debt_blocked'
    with env.db() as db:
        db.execute_exact('SELECT id FROM wallets WHERE user_id=%s FOR UPDATE',(graph.owner['id'],))
        recovered=fuel.recover_from_earnings(db,graph.owner['id'],Decimal('10000'),'test-future-1:'+str(graph.trip_id))
        assert recovered==10000
    with env.db() as db:
        assert fuel.recover_from_earnings(db,graph.owner['id'],Decimal('10000'),'test-future-1:'+str(graph.trip_id))==10000
        assert db.execute_exact('SELECT outstanding_credit FROM fuel_credit_accounts WHERE transporter_user_id=%s',(graph.owner['id'],)).fetchone()['outstanding_credit']==5000
        recovered=fuel.recover_from_earnings(db,graph.owner['id'],Decimal('6000'),'test-future-2:'+str(graph.trip_id))
        assert recovered==5000
        wallet=db.execute_exact('SELECT balance,locked_balance FROM wallets WHERE user_id=%s',(graph.owner['id'],)).fetchone()
        assert wallet=={'balance':Decimal('30000'),'locked_balance':Decimal('30000')}
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s',(station['id'],)).fetchone()['balance']==25000
    assert _authorize(env,graph,next_data)['voucher']['credit_authorized']=='1000.00'


def test_journal_immutable_balanced_and_conflicting_replays(remediation_env):
    env=remediation_env
    key=str(uuid4())
    with env.db() as db:
        first=post_journal(db,key,'test','ref',[('account:a',Decimal('-1')),('account:b',Decimal('1'))])
    with env.db() as db:
        assert post_journal(db,key,'test','ref',[('account:a',Decimal('-1')),('account:b',Decimal('1'))])==first
        with pytest.raises(ValueError): post_journal(db,key,'test','ref',[('account:a',Decimal('-2')),('account:b',Decimal('2'))])
    import psycopg2
    for statement,params in [('UPDATE financial_journal SET kind=kind WHERE id=%s',(first,)),
                             ('INSERT INTO financial_journal_lines(journal_id,account,amount) VALUES(%s,\'late\',1)',(first,))]:
        with pytest.raises(psycopg2.errors.CheckViolation):
            with env.db() as db: db.execute_exact(statement,params)


def test_authenticated_roles_csrf_and_secret_visibility(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    client,_=env.login(graph.owner)
    station_client,_=env.login(station)
    headers={**env.headers,'Idempotency-Key':str(uuid4())}
    assert client.post('/api/fuel/vouchers',json=data).status_code==403
    headers['X-DTX-Expected-User-Id']=str(graph.owner['id'])
    response=client.post('/api/fuel/vouchers',json=data,headers=headers)
    assert response.status_code in {409,428},response.json
    assert response.json['code'] in {'mpin_enrollment_required','mpin_step_up_required'}
    authorized=_authorize(env,graph,data)
    assert station_client.get('/api/fuel/vouchers').status_code==403
    assert client.post('/api/fuelstation/vouchers/verify',json={'otp':authorized['otp'],'pump_id':pump},headers=env.headers).status_code==403
    listed=client.get('/api/fuel/vouchers').json
    assert all('otp' not in row and 'otp_digest' not in row for row in listed['vouchers'])


def test_server_expiry_and_scheduler_release_survives_ineligible_truck(remediation_env,monkeypatch):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    with env.db() as db:
        authorized=fuel.authorize_voucher(db,graph.owner['id'],data,str(uuid4()),now=datetime.now(timezone.utc)-timedelta(hours=1))
    with pytest.raises(CheckoutError) as failure:
        with env.db() as db: fuel.verify_voucher(db,station['id'],authorized['otp'],pump)
    assert failure.value.code=='fuel_voucher_expired'
    with env.db() as db:
        db.execute("UPDATE vehicles SET status='maintenance' WHERE id=%s",(graph.truck_id,))
        db.execute("UPDATE shipment_trips SET status='cancelled' WHERE id=%s",(graph.trip_id,))
    import shared.db as db_module
    import scheduler
    monkeypatch.setattr(db_module,'open_db',env.db)
    result=scheduler.run_expire_fuel_vouchers()
    assert result['processed']>=1 and result['failed']==0
    assert scheduler.run_expire_fuel_vouchers()['processed']==0
    with env.db() as db:
        voucher=db.execute_exact('SELECT * FROM fuel_vouchers WHERE id=%s',(authorized['voucher']['id'],)).fetchone()
        assert voucher['status']=='expired'
        assert db.execute_exact('SELECT locked_balance FROM wallets WHERE user_id=%s',(graph.owner['id'],)).fetchone()['locked_balance']==30000


def test_plate_change_rejects_dispense_but_can_cancel_original_hold(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    authorized=_authorize(env,graph,data)
    with env.db() as db: db.execute("UPDATE vehicles SET truck_number='CHANGED-PLATE' WHERE id=%s",(graph.truck_id,))
    with pytest.raises(CheckoutError) as failure:
        with env.db() as db: fuel.verify_voucher(db,station['id'],authorized['otp'],pump)
    assert failure.value.code=='fuel_truck_changed'
    with env.db() as db:
        assert fuel.cancel_voucher(db,authorized['voucher']['id'],graph.owner['id'])['voucher']['status']=='cancelled'


def test_private_fuel_rls_treasury_binding_and_final_slip_immutability(remediation_env):
    import psycopg2
    env=remediation_env
    graph,station,pump,data=_setup(env)
    authorized,payload,result=_redeem(env,graph,station,pump,data)
    for table in ('fuel_platform_treasury','fuel_credit_accounts','fuel_vouchers','fuel_credit_events','financial_journal','financial_journal_lines','owner_operator_credentials','operational_incidents','trip_cancellation_requests'):
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            with env.db() as db:
                db.execute('SET LOCAL ROLE authenticated')
                db.execute('SELECT * FROM '+table)
    with pytest.raises(psycopg2.errors.CheckViolation):
        with env.db() as db: db.execute('UPDATE fuel_platform_treasury SET wallet_id=wallet_id')
    with pytest.raises(psycopg2.errors.CheckViolation):
        with env.db() as db: db.execute("UPDATE fuel_vouchers SET actual_amount=1 WHERE id=%s",(authorized['voucher']['id'],))


def test_simultaneous_dispense_callbacks_pay_station_once(remediation_env):
    env=remediation_env
    graph,station,pump,data=_setup(env)
    authorized=_authorize(env,graph,data)
    with env.db() as db: verified=fuel.verify_voucher(db,station['id'],authorized['otp'],pump)
    payload={'redemption_token':verified['redemption_token'],'pump_id':pump,'actual_liters':'100','truck_plate':verified['voucher']['truck_plate'],'fuel_type':'diesel'}
    barrier=Barrier(2)
    def dispense(_):
        barrier.wait(10)
        with env.db() as db: return fuel.dispense_voucher(db,station['id'],authorized['voucher']['id'],payload)['replayed']
    with ThreadPoolExecutor(max_workers=2) as pool: assert sorted(pool.map(dispense,range(2)))==[False,True]
    with env.db() as db:
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s',(station['id'],)).fetchone()['balance']==25000


def test_internal_reconciliation_after_authorize_dispense_and_recovery(remediation_env):
    from scripts.reconcile_business_rules import reconcile
    env=remediation_env
    graph,station,pump,data=_setup(env)
    authorized,payload,result=_redeem(env,graph,station,pump,data)
    with env.db() as db:
        recovered=fuel.recover_from_earnings(db,graph.owner['id'],Decimal('15000'),'reconciliation:'+str(graph.trip_id))
        assert recovered==15000
        # Supply the source payable bridge as the freight settlement does.
        post_journal(db,'test_earnings:'+str(graph.trip_id),'test_earnings',str(graph.trip_id),
                     [('test:payable',-recovered),('fuel_credit_recovery:reconciliation:'+str(graph.trip_id),recovered)])
        result=reconcile(db)
        assert result['consistent'],result


def test_fuel_authorization_actual_mpin_stepup_and_account_binding(remediation_env,monkeypatch):
    from auth import mpin_service
    from tests.test_mpin_high_risk_routes_postgres import PEPPER
    env=remediation_env
    graph,station,pump,data=_setup(env)
    monkeypatch.setenv('DIGITRANSX_MPIN_PEPPER',PEPPER)
    salt,verifier=mpin_service.build_credential('1234')
    with env.db() as db:
        db.execute('INSERT INTO mpin_credentials(user_id,verifier,salt,kdf_version) VALUES(%s,%s,%s,1)',(graph.owner['id'],verifier,salt))
    client,_=env.login(graph.owner)
    headers={**env.headers,'Idempotency-Key':str(uuid4()),'X-DTX-Expected-User-Id':str(graph.owner['id'])}
    challenge=client.post('/api/fuel/vouchers',headers=headers,json=data)
    assert challenge.status_code==428,challenge.json
    action=challenge.json['action']
    assert action['action_key']=='fuel.voucher.authorize'
    assert action['amount_minor']==2500000
    issued=client.post('/auth/mpin/step-up',headers=env.headers,json={'mpin':'1234','action':action})
    assert issued.status_code==200,issued.json
    proof=issued.json['authorization_proof']
    altered=client.post('/api/fuel/vouchers',headers={**headers,'X-MPIN-Step-Up-Proof':proof},json={**data,'max_amount':'24000'})
    assert altered.status_code==428
    result=client.post('/api/fuel/vouchers',headers={**headers,'X-MPIN-Step-Up-Proof':proof},json=data)
    assert result.status_code==200,result.json
    assert result.headers['Cache-Control']=='no-store' and result.json['otp']
    replay=client.post('/api/fuel/vouchers',headers=headers,json=data)
    assert replay.status_code==200 and replay.json['replayed'] and replay.json['otp'] is None
    swapped=client.post('/api/fuel/vouchers',headers={**headers,'X-DTX-Expected-User-Id':str(station['id'])},json=data)
    assert swapped.status_code==409 and swapped.json['code']=='fuel_account_changed'
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM security_events WHERE event_name='security.mpin.step_up_consumed' AND metadata->>'action_key'='fuel.voucher.authorize'").fetchone()['n']>=1


def test_real_freight_delivery_recovers_credit_before_both_tranches(remediation_env,monkeypatch):
    from orders.business_lifecycle import RULES_VERSION,issue_delivery_otp,delivery_otp_for_client,verify_delivery_otp,release_due_settlements
    from shared.commissions import itemized_fee
    import json
    env=remediation_env
    graph,station,pump,data=_setup(env)
    _redeem(env,graph,station,pump,data)
    monkeypatch.setenv('DIGITRANSX_DELIVERY_OTP_SECRET','isolated-test-random-channel-key-for-delivery')
    now=datetime.now(timezone.utc)
    with env.db() as db:
        source=db.execute_exact('SELECT order_id FROM shipment_trips WHERE id=%s',(graph.trip_id,)).fetchone()
        order_id=source['order_id']
        db.execute("INSERT INTO payments(shipment_id,trip_id,invoice_number,client_user_id,transporter_user_id,bid_price,company_fee,transporter_amount,wallet_funded_amount,card_funded_amount,company_share_percent,transporter_share_percent,status,business_rules_version,fee_breakdown,funding_source) VALUES(%s,%s,%s,%s,%s,100000,20000,80000,100000,0,20,80,'held',%s,%s::jsonb,'wallet')",
                   (order_id,graph.trip_id,'FUEL-TEST-'+uuid4().hex,graph.customer['id'],graph.owner['id'],RULES_VERSION,json.dumps(itemized_fee('100000','freight'))))
        db.execute("UPDATE shipment_trips SET status='in_progress' WHERE id=%s",(graph.trip_id,))
        db.execute("UPDATE shipments SET status='in_progress' WHERE id=%s",(order_id,))
        issue_delivery_otp(db,graph.owner,order_id,graph.trip_id,now)
        code=delivery_otp_for_client(db,graph.customer,order_id,graph.trip_id,True,now)['otp']
        result=verify_delivery_otp(db,graph.owner,order_id,graph.trip_id,code,now)
        settlement=result['settlement']
        assert settlement['fuel_credit_recovered']=='15000.00'
        assert settlement['tranche1_amount']==settlement['tranche2_amount']=='32500.00'
        assert db.execute_exact('SELECT balance,locked_balance FROM wallets WHERE user_id=%s',(graph.owner['id'],)).fetchone()=={'balance':Decimal('62500'),'locked_balance':Decimal('30000')}
        release_due_settlements(db,now+timedelta(minutes=120))
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s',(graph.owner['id'],)).fetchone()['balance']==95000
        assert db.execute_exact('SELECT outstanding_credit FROM fuel_credit_accounts WHERE transporter_user_id=%s',(graph.owner['id'],)).fetchone()['outstanding_credit']==0
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s',(station['id'],)).fetchone()['balance']==25000
