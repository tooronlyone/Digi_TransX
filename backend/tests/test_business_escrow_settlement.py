"""Real PostgreSQL tests for the versioned Rules 1-4 financial lifecycle.

The fixture creates/drops only uniquely named databases on an explicit loopback
test server. It never falls back to application database credentials.
"""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
import pytest

from shared.db import Db
from shared.payments import CheckoutError,perform_checkout,release_one_time_payment
from shared.commissions import itemized_fee
from shared.reserves import ensure_security_reserve,progressive_contribution
from orders.business_lifecycle import (RULES_VERSION,issue_delivery_otp,delivery_otp_for_client,
    verify_delivery_otp,open_delivery_dispute,release_due_settlements,resolve_delivery_settlement)
from tests._life_helpers import make_disposable,require_test_db_url,SCHEMA_SQL,STUBS
from tests.test_trip_lifecycle import seed_ready_order

NOW=datetime(2026,10,26,12,0,tzinfo=timezone.utc)

@pytest.fixture(scope='module')
def business_db_url():
    base=require_test_db_url()
    if urlsplit(base).hostname not in {'127.0.0.1','localhost','::1'}:
        pytest.fail('Business financial integration requires isolated loopback PostgreSQL.')
    schema=SCHEMA_SQL.read_text(encoding='utf-8')
    extras=[]
    for name,marker in [('20261026000000_financial_journal.sql','public.financial_journal'),('20261026010000_market_pricing_fees.sql','public.market_reference'),('20261026020000_business_escrow_settlement.sql','public.delivery_otp_challenges'),('20261026030000_fuel_credit_owner_operator.sql','public.fuel_credit_accounts')]:
        sql=(SCHEMA_SQL.parent/'migrations'/name).read_text(encoding='utf-8')
        if marker not in schema.lower():extras.append(sql)
    url,cleanup=make_disposable(base,STUBS,schema,*extras)
    try:yield url
    finally:cleanup()

@pytest.fixture
def business_env(business_db_url,monkeypatch):
    monkeypatch.setenv('DIGITRANSX_DELIVERY_OTP_SECRET','isolated-delivery-otp-key-for-regression-only')
    @contextmanager
    def connect():
        conn=psycopg2.connect(business_db_url)
        try:
            yield Db(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:conn.close()
    return connect

def seed(db,*,gross=Decimal('100000.00'),open_order=False,client_balance=Decimal('0.00')):
    s=seed_ready_order(db,bid=gross,company_fee=(gross*Decimal('.20')).quantize(Decimal('.01')),wallet_funded=gross,client_wallet_balance=client_balance)
    db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) VALUES(%s,'transporter',30000,30000,30000,true)",(s['transporter']['id'],))
    ensure_security_reserve(db,s['transporter']['id'])
    if open_order:
        db.execute('DELETE FROM payments WHERE id=%s',(s['payment_id'],))
        db.execute('DELETE FROM shipment_trips WHERE id=%s',(s['trip_id'],))
        db.execute("UPDATE shipments SET status='open',accepted_bid_id=null,payment_status='pending' WHERE id=%s",(s['order_id'],))
        db.execute("UPDATE shipment_bids SET status='pending' WHERE id=%s",(s['bid_id'],))
        db.execute("UPDATE vehicles SET current_city='Lahore' WHERE id=%s",(s['truck_id'],))
    else:
        db.execute("UPDATE payments SET business_rules_version=%s,fee_breakdown=%s WHERE id=%s",(RULES_VERSION,json.dumps(itemized_fee(gross,'freight')),s['payment_id']))
        db.execute("UPDATE shipment_trips SET status='in_progress' WHERE id=%s",(s['trip_id'],))
        db.execute("UPDATE shipments SET status='in_progress' WHERE id=%s",(s['order_id'],))
    return s

def delivered(db,s,now=NOW):
    issue_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],now)
    code=delivery_otp_for_client(db,s['client'],s['order_id'],s['trip_id'],True,now)['otp']
    return verify_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],code,now)

def test_otp_handshake_and_5050_exact_settlement(business_env):
    with business_env() as db:
        s=seed(db)
        result=delivered(db,s)
        assert result['verified'] is True
        settlement=result['settlement']
        assert settlement['gross_amount']=='100000.00'
        assert settlement['company_fee']=='20000.00'
        assert settlement['tranche1_amount']==settlement['tranche2_amount']=='40000.00'
        assert settlement['reserve_contribution']=='0.00'
        assert settlement['reserve_policy_state']=='progressive_percentage_approval_required'
        wallet=db.execute_exact('SELECT balance,locked_balance FROM wallets WHERE user_id=%s',(s['transporter']['id'],)).fetchone()
        assert wallet=={'balance':Decimal('70000'),'locked_balance':Decimal('30000')}
        assert db.execute("SELECT status FROM payments WHERE id=%s",(s['payment_id'],)).fetchone()['status']=='held'

@pytest.mark.parametrize('minute,expected',[(119,0),(120,1),(121,1)])
def test_second_tranche_eligibility_and_idempotency(business_env,minute,expected):
    with business_env() as db:
        s=seed(db)
        delivered(db,s)
        assert release_due_settlements(db,NOW+timedelta(minutes=minute))['released_count']>=expected
        own=db.execute('SELECT status FROM freight_settlements WHERE trip_id=%s',(s['trip_id'],)).fetchone()
        assert own['status']==('released' if expected else 'pending_release')
        assert release_due_settlements(db,NOW+timedelta(minutes=minute))['released_count']==0

@pytest.mark.parametrize('minute,accepted',[(0,True),(89,True),(90,False),(100,False),(119,False)])
def test_dispute_90minute_cutoff_and_safety_buffer(business_env,minute,accepted):
    with business_env() as db:
        s=seed(db)
        delivered(db,s)
        if accepted:
            result=open_delivery_dispute(db,s['client'],s['order_id'],s['trip_id'],'Cargo damage',['authenticated/photo/1'],NOW+timedelta(minutes=minute))
            assert not result['already']
            release_due_settlements(db,NOW+timedelta(minutes=121))
            assert db.execute('SELECT status FROM freight_settlements WHERE trip_id=%s',(s['trip_id'],)).fetchone()['status']=='disputed'
            assert db.execute_exact('SELECT balance FROM security_reserves WHERE user_id=%s',(s['transporter']['id'],)).fetchone()['balance']==Decimal('30000')
        else:
            with pytest.raises(CheckoutError,match='90-minute'):open_delivery_dispute(db,s['client'],s['order_id'],s['trip_id'],'Late complaint',now=NOW+timedelta(minutes=minute))

def test_otp_authorization_expiry_replay_and_no_plaintext(business_env):
    with business_env() as db:
        s=seed(db)
        issue_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],NOW)
        with pytest.raises(CheckoutError,match='Access denied'):delivery_otp_for_client(db,s['transporter'],s['order_id'],s['trip_id'],True,NOW)
        code=delivery_otp_for_client(db,s['client'],s['order_id'],s['trip_id'],True,NOW)['otp']
        row=db.execute('SELECT * FROM delivery_otp_challenges WHERE trip_id=%s',(s['trip_id'],)).fetchone()
        assert code not in json.dumps(row)
        with pytest.raises(CheckoutError,match='expired'):verify_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],code,NOW+timedelta(minutes=10))
        assert verify_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],code,NOW)['verified']
        with pytest.raises(CheckoutError,match='already'):verify_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],code,NOW)

def test_failed_otp_attempts_persist_and_lock_at_five(business_env):
    with business_env() as db:
        s=seed(db)
        issue_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],NOW)
        code=delivery_otp_for_client(db,s['client'],s['order_id'],s['trip_id'],True,NOW)['otp']
    wrong='11111111' if code!='11111111' else '22222222'
    for attempt in range(5):
        with business_env() as db:
            result=verify_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],wrong,NOW)
            assert result['verified'] is False and result['remaining_attempts']==4-attempt
    with business_env() as db:
        with pytest.raises(CheckoutError,match='locked'):verify_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],code,NOW)

def test_no_legacy_release_bypass(business_env):
    from orders.lifecycle import perform_client_confirm
    with business_env() as db:
        s=seed(db)
        issue_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],NOW)
        with pytest.raises(CheckoutError,match='OTP'):release_one_time_payment(db,s['payment_id'])
        with pytest.raises(CheckoutError,match='OTP'):perform_client_confirm(db,s['client'],s['order_id'],s['trip_id'],'yes')

def test_admin_evidence_decision_allocates_remaining_hold_once(business_env):
    with business_env() as db:
        s=seed(db)
        result=delivered(db,s)
        open_delivery_dispute(db,s['client'],s['order_id'],s['trip_id'],'Inspection report discrepancy',['inspection/verified'],NOW)
        result=resolve_delivery_settlement(db,s['admin'],result['settlement']['id'],'15000.00','Reviewed signed inspection',['inspection/verified'],'verified_accident',NOW)
        assert result['resolution']['client_refund_amount']=='15000.00'
        assert result['resolution']['transporter_release_amount']=='25000.00'
        assert resolve_delivery_settlement(db,s['admin'],result['resolution']['settlement_id'],'15000.00','Reviewed signed inspection',['inspection/verified'],'verified_accident',NOW)['already']
        assert db.execute_exact('SELECT balance FROM security_reserves WHERE user_id=%s',(s['transporter']['id'],)).fetchone()['balance']==Decimal('30000')

def test_settlement_money_and_evidence_are_immutable(business_env):
    with business_env() as db:
        s=seed(db)
        delivered(db,s)
        db.commit()
        with pytest.raises(psycopg2.Error,match='immutable'):
            db.execute('UPDATE freight_settlements SET company_fee=company_fee+1 WHERE trip_id=%s',(s['trip_id'],))
        db.rollback()
        assert db.execute_exact('SELECT SUM(amount) AS total FROM financial_journal_lines WHERE journal_id IN (SELECT id FROM financial_journal WHERE reference=%s)',(str(s['payment_id']),)).fetchone()['total']==Decimal('0')

def test_concurrent_otp_verifications_settle_once(business_env):
    with business_env() as db:
        s=seed(db)
        issue_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],NOW)
        code=delivery_otp_for_client(db,s['client'],s['order_id'],s['trip_id'],True,NOW)['otp']
    def complete():
        try:
            with business_env() as db:return verify_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],code,NOW)['verified']
        except CheckoutError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(lambda _:complete(),range(2)))==[False,True]
    with business_env() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM wallet_transactions WHERE user_id=%s AND type=%s',(s['transporter']['id'],'freight_tranche1')).fetchone()['n']==1

def test_missing_otp_channel_configuration_blocks_before_mutation(business_env,monkeypatch):
    monkeypatch.delenv('DIGITRANSX_DELIVERY_OTP_SECRET',raising=False)
    with business_env() as db:
        s=seed(db)
        with pytest.raises(CheckoutError,match='not configured'):issue_delivery_otp(db,s['transporter'],s['order_id'],s['trip_id'],NOW)
        assert db.execute('SELECT status FROM shipment_trips WHERE id=%s',(s['trip_id'],)).fetchone()['status']=='in_progress'


ACCEPTANCE={'insurance_notice_accepted':True,'insurance_notice_version':RULES_VERSION}


def test_ambiguous_partial_legacy_hold_is_not_reclassified_as_collateral(business_env):
    with business_env() as db:
        s=seed_ready_order(db)
        db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) VALUES(%s,'transporter',60000,5000,30000,true)",(s['transporter']['id'],))
        with pytest.raises(CheckoutError) as failure:
            ensure_security_reserve(db,s['transporter']['id'])
        assert failure.value.code=='security_reserve_reconciliation_required'
        assert db.execute_exact('SELECT locked_balance FROM wallets WHERE user_id=%s',(s['transporter']['id'],)).fetchone()['locked_balance']==5000
        assert db.execute('SELECT count(*) AS n FROM security_reserves WHERE user_id=%s',(s['transporter']['id'],)).fetchone()['n']==0

def test_insufficient_escrow_reports_exact_shortfall_without_partial_hold(business_env):
    with business_env() as db:
        s=seed(db,open_order=True,client_balance=Decimal('1234.56'))
        with pytest.raises(CheckoutError,match=r'Insufficient balance. Please top up PKR 98,765.44 to accept this bid.'):
            perform_checkout(db,s['client'],s['order_id'],s['bid_id'],ACCEPTANCE,'checkout-'+uuid.uuid4().hex)
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s',(s['client']['id'],)).fetchone()['balance']==Decimal('1234.56')
        assert db.execute('SELECT COUNT(*) AS n FROM payments WHERE shipment_id=%s',(s['order_id'],)).fetchone()['n']==0


def test_full_upfront_wallet_escrow_snapshots_approved_fees_and_replays_once(business_env):
    with business_env() as db:
        s=seed(db,open_order=True,client_balance=Decimal('100000'))
        key='checkout-'+uuid.uuid4().hex
        # Insurance is an optional reminder; no booking checkbox is required.
        result=perform_checkout(db,s['client'],s['order_id'],s['bid_id'],{},key)
        assert result['payment']['business_rules_version']==RULES_VERSION
        assert result['payment']['status']=='held'
        assert Decimal(str(result['payment']['wallet_funded_amount']))==Decimal('100000')
        assert Decimal(str(result['payment']['card_funded_amount']))==0
        assert Decimal(str(result['payment']['company_fee']))==Decimal('20000')
        assert result['payment'].get('insurance_notice_accepted_at') is None
        assert perform_checkout(db,s['client'],s['order_id'],s['bid_id'],ACCEPTANCE,key)['replayed']
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s',(s['client']['id'],)).fetchone()['balance']==0


def test_concurrent_booking_acceptance_cannot_double_spend_wallet(business_env):
    with business_env() as db:
        first=seed(db,open_order=True,client_balance=Decimal('100000'))
        second=seed(db,open_order=True)
        db.execute('UPDATE shipments SET client_user_id=%s WHERE id=%s',(first['client']['id'],second['order_id']))
    def accept(s):
        try:
            with business_env() as db:
                perform_checkout(db,first['client'],s['order_id'],s['bid_id'],ACCEPTANCE,'checkout-'+uuid.uuid4().hex)
                return True
        except CheckoutError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(accept,[first,second]))==[False,True]
    with business_env() as db:
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s',(first['client']['id'],)).fetchone()['balance']==0
        assert db.execute('SELECT COUNT(*) AS n FROM payments WHERE client_user_id=%s',(first['client']['id'],)).fetchone()['n']==1


def test_pending_escrow_refund_does_not_touch_fuel_debt_or_reserve(business_env):
    from shared.payments import refund_one_time_payment
    with business_env() as db:
        s=seed(db)
        db.execute('INSERT INTO fuel_credit_accounts(transporter_user_id,outstanding_credit,utilized_credit) VALUES(%s,7000,7000)',(s['transporter']['id'],))
        result=refund_one_time_payment(db,s['payment_id'])
        assert Decimal(str(result['wallet_refund_amount']))==Decimal('100000')
        assert db.execute_exact('SELECT outstanding_credit FROM fuel_credit_accounts WHERE transporter_user_id=%s',(s['transporter']['id'],)).fetchone()['outstanding_credit']==Decimal('7000')
        assert db.execute_exact('SELECT balance FROM security_reserves WHERE user_id=%s',(s['transporter']['id'],)).fetchone()['balance']==Decimal('30000')


def test_approved_reserve_percentage_never_invents_fleet_brackets_or_exceeds_ceiling(business_env):
    with business_env() as db:
        s=seed(db)
        db.execute('UPDATE security_reserve_policy SET progressive_percent=3,approved_at=now(),approved_by=%s WHERE id=true',(s['admin']['id'],))
        amount,state=progressive_contribution(db,s['transporter']['id'],Decimal('100.00'),'reserve:'+uuid.uuid4().hex)
        assert amount==0 and state=='fleet_range_approval_required'
        prefix=uuid.uuid4().hex
        db.execute("INSERT INTO vehicles(owner_user_id,truck_number,chassis_number,truck_type,capacity_tons,main_use,status) SELECT %s,%s||n::text,%s||n::text,'flatbed',20,'general','active' FROM generate_series(1,14) n",(s['transporter']['id'],'TRK-'+prefix,'CHS-'+prefix))
        db.execute("UPDATE vehicles SET status='on_job' WHERE id=%s",(s['truck_id'],))
        db.execute('UPDATE wallets SET balance=200000,locked_balance=199999.99,minimum_required=199999.99 WHERE user_id=%s',(s['transporter']['id'],))
        db.execute('UPDATE security_reserves SET balance=199999.99 WHERE user_id=%s',(s['transporter']['id'],))
        reference='reserve:'+uuid.uuid4().hex
        amount,state=progressive_contribution(db,s['transporter']['id'],Decimal('100.00'),reference)
        assert amount==Decimal('.01') and state=='approved'
        assert progressive_contribution(db,s['transporter']['id'],Decimal('100.00'),reference)[0]==Decimal('.01')
        assert db.execute_exact('SELECT balance FROM security_reserves WHERE user_id=%s',(s['transporter']['id'],)).fetchone()['balance']==Decimal('200000.00')
        assert db.execute_exact('SELECT minimum_required FROM wallets WHERE user_id=%s',(s['transporter']['id'],)).fetchone()['minimum_required']==Decimal('200000.00')
        # Keep the shared fixture policy unapproved for other independent tests.
        db.execute('UPDATE security_reserve_policy SET progressive_percent=null,approved_at=null,approved_by=null WHERE id=true')


def test_concurrent_due_workers_release_one_second_tranche(business_env):
    with business_env() as db:
        s=seed(db)
        delivered(db,s)
    def release():
        with business_env() as db:return release_due_settlements(db,NOW+timedelta(minutes=120))
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:release(),range(2)))
    with business_env() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM wallet_transactions WHERE user_id=%s AND type=%s',(s['transporter']['id'],'freight_tranche2')).fetchone()['n']==1


def test_browser_roles_cannot_read_otp_or_write_financial_tables(business_env):
    with business_env() as db:
        db.execute('SET LOCAL ROLE authenticated')
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            db.execute('SELECT nonce,code_digest FROM delivery_otp_challenges')
        db.rollback()
        db.execute('SET LOCAL ROLE authenticated')
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            db.execute('UPDATE security_reserves SET balance=0')
        db.rollback()


def test_legacy_commission_terms_cannot_override_immutable_approved_booking_terms(business_env):
    from shared.commissions import create_policy_version,create_terms_version
    from shared.payments import serialize_payment_summary
    with business_env() as db:
        s=seed(db,open_order=True,client_balance=Decimal('100000'))
        legacy=create_policy_version(db,'one_time_order',Decimal('12.50'),'Legacy administrative rate',s['admin']['id'],NOW.isoformat())
        general_terms=create_terms_version(db,legacy['id'],'General legacy terms reference',s['admin']['id'],NOW.isoformat())
        result=perform_checkout(db,s['client'],s['order_id'],s['bid_id'],ACCEPTANCE,'terms-'+uuid.uuid4().hex)
        summary=serialize_payment_summary(result['payment'])
        snapshot=summary['financial_terms_snapshot']
        assert summary['general_terms_version_id']==general_terms['id']
        assert summary['financial_policy_source']=='financial_terms_snapshot'
        assert snapshot['rules_version']==RULES_VERSION
        assert snapshot['freight_fees']['percentage']=='20.00'
        assert snapshot['client_platform_commission_percent']=='0.00'
        assert snapshot['settlement_tranches_percent']==['50.00','50.00']
        assert snapshot['dispute_window_minutes']==90 and snapshot['release_eligibility_minutes']==120
        assert snapshot['insurance_notice_version']==RULES_VERSION
        assert Decimal(str(result['payment']['company_fee']))==Decimal('20000')
        db.commit()
        with pytest.raises(psycopg2.Error,match='immutable'):
            db.execute("UPDATE payments SET financial_terms_snapshot='{}'::jsonb WHERE id=%s",(result['payment']['id'],))
        db.rollback()


def test_custom_fleet_reserve_configuration_requires_explicit_approval_and_reference_points_are_immutable(business_env):
    from shared.reserves import review_reserve_requirement
    with business_env() as db:
        s=seed(db)
        db.execute('SAVEPOINT custom_reserve_test')
        db.execute('INSERT INTO security_reserve_brackets(truck_count,ceiling) VALUES(1,30000) ON CONFLICT(truck_count) DO NOTHING')
        assert review_reserve_requirement(db,s['transporter']['id'])['policy_state']=='fleet_range_approval_required'
        db.execute('UPDATE security_reserve_brackets SET approved_at=now(),approved_by=%s,approval_evidence=%s WHERE truck_count=1',(s['admin']['id'],'Isolated business approval fixture explicitly authorizes this configuration'))
        assert review_reserve_requirement(db,s['transporter']['id'])['ceiling']=='30000.00'
        db.execute('SAVEPOINT approved_bracket_change')
        with pytest.raises(psycopg2.Error,match='immutable'):
            db.execute('UPDATE security_reserve_brackets SET ceiling=35000 WHERE truck_count=1')
        db.execute('ROLLBACK TO SAVEPOINT approved_bracket_change')
        db.execute('ROLLBACK TO SAVEPOINT custom_reserve_test')
        db.commit()
        with pytest.raises(psycopg2.Error,match='immutable'):
            db.execute('UPDATE security_reserve_brackets SET ceiling=199999 WHERE truck_count=15')
        db.rollback()


def test_earnings_summary_counts_only_unreleased_tranche_as_pending_and_shows_actual_credits(business_env,monkeypatch):
    from flask import Flask,request
    from wallet import routes as wallet_routes,helpers as wallet_helpers
    from wallet.earnings import versioned_freight_earnings
    app=Flask(__name__)
    monkeypatch.setattr(wallet_routes,'open_db',business_env)
    monkeypatch.setattr(wallet_helpers,'open_db',business_env)
    with business_env() as db:
        s=seed(db)
        result=delivered(db,s)
        db.commit()
        stats=versioned_freight_earnings(db,s['transporter']['id'],datetime.now(timezone.utc).strftime('%Y-%m'))
        assert stats['lifetime_credited']==Decimal('40000') and stats['pending']==Decimal('40000')
    with app.test_request_context('/api/wallet/earnings-summary'):
        request.current_user=s['transporter']
        summary=wallet_routes.earnings_summary.__wrapped__().get_json()
        assert summary['lifetime_earnings']==40000 and summary['pending_earnings']==40000
        assert summary['month_earnings']==40000
        assert summary['recent_transactions'][0]['type']=='freight_tranche1'
    with business_env() as db:release_due_settlements(db,NOW+timedelta(minutes=120))
    with app.test_request_context('/api/wallet/earnings-summary'):
        request.current_user=s['transporter']
        summary=wallet_routes.earnings_summary.__wrapped__().get_json()
        assert summary['lifetime_earnings']==80000 and summary['pending_earnings']==0
        assert summary['recent_transactions'][0]['type']=='freight_tranche2'


def test_earnings_summary_preserves_legacy_null_version_payment_totals(business_env,monkeypatch):
    from flask import Flask,request
    from wallet import routes as wallet_routes,helpers as wallet_helpers
    app=Flask(__name__)
    monkeypatch.setattr(wallet_routes,'open_db',business_env)
    monkeypatch.setattr(wallet_helpers,'open_db',business_env)
    with business_env() as db:
        s=seed_ready_order(db)
    with app.test_request_context('/api/wallet/earnings-summary'):
        request.current_user=s['transporter']
        summary=wallet_routes.earnings_summary.__wrapped__().get_json()
        assert summary['lifetime_earnings']==0 and summary['pending_earnings']==8000
    with business_env() as db:db.execute("UPDATE payments SET status='released',released_at=now() WHERE id=%s",(s['payment_id'],))
    with app.test_request_context('/api/wallet/earnings-summary'):
        request.current_user=s['transporter']
        summary=wallet_routes.earnings_summary.__wrapped__().get_json()
        assert summary['lifetime_earnings']==8000 and summary['pending_earnings']==0
