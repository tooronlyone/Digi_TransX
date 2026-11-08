"""New fuel debt recovers from future legacy earnings without repricing history."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Event
from uuid import uuid4

import pytest

from agreements.helpers import process_payment_row, run_apply_penalties
from shared.payments import CheckoutError, release_one_time_payment
from tests.remediation_harness import remediation_database_url, remediation_env
from tests.test_business_fuel_credit import _redeem, _setup
from tests.test_driver_workflow_hardening import _graph, _set_status


def test_agreement_payment_history_does_not_expose_another_transporters_offsets(remediation_env,monkeypatch):
    from agreements import routes as agreement_routes
    env=remediation_env
    monkeypatch.setattr(agreement_routes,'open_db',env.db)
    env.app.register_blueprint(agreement_routes.agreements_blueprint)
    owner=_graph(env,kind='agreement')
    payment=_monthly_payment(env,owner)
    other=_graph(env)
    with env.db() as db:
        linked_truck=db.execute(
            'INSERT INTO agreement_trucks(agreement_id,truck_id,transporter_user_id,per_km_rate,minimum_monthly_guarantee) VALUES(%s,%s,%s,10,100) RETURNING id',
            (payment['agreement_id'],other.truck_id,other.owner['id']),
        ).fetchone()['id']
        foreign=db.execute(
            "INSERT INTO agreement_monthly_payments(agreement_id,agreement_truck_id,transporter_user_id,client_user_id,month_year,minimum_guarantee,final_amount,company_fee,transporter_amount,payment_due_date) "
            "VALUES(%s,%s,%s,%s,'2026-10',100,100,20,80,CURRENT_DATE) RETURNING id",
            (payment['agreement_id'],linked_truck,other.owner['id'],owner.customer['id']),
        ).fetchone()['id']
    own_response=owner.owner_client.get(f"/api/agreements/{payment['agreement_id']}/payments")
    assert own_response.status_code==200,own_response.json
    assert {row['id'] for row in own_response.json['payments']}=={payment['id']}
    other_response=other.owner_client.get(f"/api/agreements/{payment['agreement_id']}/payments")
    assert other_response.status_code==200,other_response.json
    assert {row['id'] for row in other_response.json['payments']}=={foreign}
    client,_=env.login(owner.customer)
    client_response=client.get(f"/api/agreements/{payment['agreement_id']}/payments")
    assert client_response.status_code==200
    assert {row['id'] for row in client_response.json['payments']}=={payment['id'],foreign}


def _legacy_payment(env, graph, *, gross='20000', fee='5000'):
    gross, fee = Decimal(gross), Decimal(fee)
    with env.db() as db:
        shipment = db.execute_exact('SELECT order_id FROM shipment_trips WHERE id=%s', (graph.trip_id,)).fetchone()['order_id']
        return db.execute_exact(
            "INSERT INTO payments(shipment_id,trip_id,invoice_number,client_user_id,transporter_user_id,"
            "bid_price,company_fee,transporter_amount,wallet_funded_amount,card_funded_amount,"
            "company_share_percent,transporter_share_percent,status,funding_source) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,0,25,75,'held','wallet') RETURNING *",
            (shipment, graph.trip_id, 'LEGACY-'+uuid4().hex, graph.customer['id'], graph.owner['id'],
             gross, fee, gross-fee, gross),
        ).fetchone()


def _monthly_payment(env, graph, *, gross='20000', fee='5000'):
    gross, fee = Decimal(gross), Decimal(fee)
    with env.db() as db:
        source = db.execute_exact('SELECT * FROM agreement_trips WHERE id=%s', (graph.trip_id,)).fetchone()
        db.execute("INSERT INTO wallets(user_id,role,balance,is_minimum_met) VALUES(%s,'client',%s,true)",
                   (graph.customer['id'], gross))
        return db.execute_exact(
            "INSERT INTO agreement_monthly_payments(agreement_id,agreement_truck_id,transporter_user_id,client_user_id,"
            "month_year,minimum_guarantee,total_earned,final_amount,company_fee,transporter_amount,"
            "company_share_percent,transporter_share_percent,payment_due_date) "
            "VALUES(%s,%s,%s,%s,'2026-10',%s,%s,%s,%s,%s,25,75,CURRENT_DATE) RETURNING *",
            (source['agreement_id'], source['agreement_truck_id'], graph.owner['id'], graph.customer['id'],
             gross, gross, gross, fee, gross-fee),
        ).fetchone()


def _assert_accounting(env, graph, station, *, due, recovered, credited, reference):
    with env.db() as db:
        account = db.execute_exact('SELECT * FROM fuel_credit_accounts WHERE transporter_user_id=%s', (graph.owner['id'],)).fetchone()
        assert account['outstanding_credit'] == Decimal(due)
        assert account['recovered_credit'] == Decimal(recovered)
        wallet = db.execute_exact('SELECT balance,locked_balance,minimum_required FROM wallets WHERE user_id=%s', (graph.owner['id'],)).fetchone()
        assert wallet == {'balance': Decimal('30000')+Decimal(credited), 'locked_balance': Decimal('30000'), 'minimum_required': Decimal('30000')}
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s', (station['id'],)).fetchone()['balance'] == Decimal('25000')
        assert db.execute_exact('SELECT count(*) AS n FROM fuel_credit_events WHERE reference=%s', ('recover:'+reference,)).fetchone()['n'] == 1
        assert db.execute_exact('SELECT coalesce(sum(amount),0) AS amount FROM financial_journal_lines WHERE account=%s',
                                ('fuel_credit_recovery:'+reference,)).fetchone()['amount'] == 0
        assert db.execute_exact('SELECT count(*) AS n FROM financial_journal WHERE idempotency_key=%s',
                                ('fuel_recovery_source:'+reference,)).fetchone()['n'] == 1


@pytest.mark.parametrize('fuel_status', ['completed', 'cancelled'])
@pytest.mark.parametrize('entitlement,expected_credit,expected_due', [('15000','0','0'), ('8000','0','7000'), ('18000','3000','0')])
def test_future_legacy_one_time_recovery_preserves_snapshots_and_replay(remediation_env, fuel_status, entitlement, expected_credit, expected_due):
    env = remediation_env
    fuel_graph, station, pump, data = _setup(env)
    _redeem(env, fuel_graph, station, pump, data)
    _set_status(env, fuel_graph, fuel_status)
    payout_graph = _graph(env, owner=fuel_graph.owner)
    payment = _legacy_payment(env, payout_graph, gross=str(Decimal(entitlement)+Decimal('5000')))
    snapshot_fields = ('bid_price','company_fee','transporter_amount','company_share_percent','transporter_share_percent','business_rules_version')
    original = {key: payment[key] for key in snapshot_fields}
    with env.db() as db:
        result = release_one_time_payment(db, payment['id'])
        assert result['transporter_entitlement'] == float(entitlement)
        assert result['wallet_credit_amount'] == result['payout_amount'] == float(expected_credit)
        assert result['fuel_credit_recovered'] == float(min(Decimal(entitlement), Decimal('15000')))
        assert {key: result['payment'][key] for key in snapshot_fields} == original
    with env.db() as db:
        replay = release_one_time_payment(db, payment['id'])
        assert replay['already_released'] and replay['wallet_credit_amount'] == float(expected_credit)
        assert replay['fuel_credit_recovered'] == result['fuel_credit_recovered']
    _assert_accounting(env, fuel_graph, station, due=expected_due,
                       recovered=str(min(Decimal(entitlement), Decimal('15000'))), credited=expected_credit,
                       reference=f"legacy_freight:{payment['id']}")


@pytest.mark.parametrize('fuel_status', ['completed', 'cancelled'])
@pytest.mark.parametrize('gross,fee,expected_credit,expected_due', [('20000','5000','0','0'), ('10000','2000','0','7000'), ('23000','5000','3000','0')])
def test_future_agreement_monthly_recovery_is_atomic_and_repeat_safe(remediation_env, fuel_status, gross, fee, expected_credit, expected_due):
    env = remediation_env
    graph, station, pump, data = _setup(env, kind='agreement')
    _redeem(env, graph, station, pump, data)
    _set_status(env, graph, fuel_status)
    payment = _monthly_payment(env, graph, gross=gross, fee=fee)
    snapshot_fields = ('final_amount','company_fee','transporter_amount','company_share_percent','transporter_share_percent')
    original = {key: payment[key] for key in snapshot_fields}
    barrier = Barrier(2)
    def settle(_):
        callback_payment = dict(payment)
        barrier.wait(10)
        with env.db() as db:
            assert process_payment_row(db, callback_payment)
        return callback_payment
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(settle, range(2)))
    recovered = min(Decimal(gross)-Decimal(fee), Decimal('15000'))
    for result in results:
        assert result['fuel_credit_recovered'] == recovered
        assert result['wallet_credit_amount'] == Decimal(expected_credit)
    with env.db() as db:
        saved = db.execute_exact('SELECT * FROM agreement_monthly_payments WHERE id=%s', (payment['id'],)).fetchone()
        assert saved['status'] == 'paid'
        assert {key: saved[key] for key in snapshot_fields} == original
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s', (graph.customer['id'],)).fetchone()['balance'] == 0
        assert db.execute_exact("SELECT count(*) AS n FROM wallet_transactions WHERE user_id=%s AND type='agreement_payment_paid' AND reference_id=%s",
                                (graph.customer['id'], str(payment['id']))).fetchone()['n'] == 1
    _assert_accounting(env, graph, station, due=expected_due, recovered=str(recovered), credited=expected_credit,
                       reference=f"agreement_monthly:{payment['id']}")


def test_monthly_recovery_failure_rolls_back_client_debit_and_preserves_debt(remediation_env):
    env = remediation_env
    graph, station, pump, data = _setup(env, kind='agreement')
    _redeem(env, graph, station, pump, data)
    payment = _monthly_payment(env, graph)
    with env.db() as db:
        db.execute("UPDATE wallets SET role='unverified' WHERE id=(SELECT wallet_id FROM fuel_platform_treasury)")
    with pytest.raises(CheckoutError, match='segregated'):
        with env.db() as db:
            process_payment_row(db, dict(payment))
    with env.db() as db:
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s', (graph.customer['id'],)).fetchone()['balance'] == 20000
        assert db.execute_exact('SELECT outstanding_credit FROM fuel_credit_accounts WHERE transporter_user_id=%s', (graph.owner['id'],)).fetchone()['outstanding_credit'] == 15000
        assert db.execute_exact('SELECT status FROM agreement_monthly_payments WHERE id=%s', (payment['id'],)).fetchone()['status'] == 'pending'


@pytest.mark.parametrize('kind', ['one_time','agreement'])
def test_legacy_payout_without_new_fuel_debt_keeps_original_credit(remediation_env, kind):
    env = remediation_env
    graph, station, pump, data = _setup(env, kind=kind)
    payment = _legacy_payment(env, graph) if kind == 'one_time' else _monthly_payment(env, graph)
    with env.db() as db:
        if kind == 'one_time':
            result = release_one_time_payment(db, payment['id'])
            assert result['payout_amount'] == 15000 and result['fuel_credit_recovered'] == 0
        else:
            assert process_payment_row(db, payment)
            assert payment['wallet_credit_amount'] == 15000 and payment['fuel_credit_recovered'] == 0
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s', (graph.owner['id'],)).fetchone()['balance'] == 55000
        assert db.execute_exact('SELECT count(*) AS n FROM fuel_credit_accounts WHERE transporter_user_id=%s', (graph.owner['id'],)).fetchone()['n'] == 0


def test_pre_cutover_schema_without_fuel_tables_keeps_legacy_payout(db):
    from tests.test_trip_lifecycle import seed_ready_order
    assert db.execute("SELECT to_regclass('fuel_credit_accounts') AS relation").fetchone()['relation'] is None
    seeded = seed_ready_order(db)
    result = release_one_time_payment(db, seeded['payment_id'])
    assert result['payout_amount'] == 8000 and result['fuel_credit_recovered'] == 0
    replay = release_one_time_payment(db, seeded['payment_id'])
    assert replay['already_released'] and replay['wallet_credit_amount'] == 8000
    assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s', (seeded['transporter']['id'],)).fetchone()['balance'] == 8000


def test_stale_legacy_penalty_candidate_rechecks_monthly_source_before_wallet(remediation_env):
    env = remediation_env
    graph, station, pump, data = _setup(env, kind='agreement', rating=None)
    payment = _monthly_payment(env, graph)
    with env.db() as db:
        db.execute("UPDATE agreement_monthly_payments SET status='failed' WHERE id=%s", (payment['id'],))
        db.execute('UPDATE wallets SET balance=25000 WHERE user_id=%s', (graph.customer['id'],))
    selected, resume = Event(), Event()

    class PauseAfterCandidates:
        def __init__(self, underlying):
            self.underlying = underlying

        def __getattr__(self, name):
            return getattr(self.underlying, name)

        def execute(self, sql, args=()):
            result = self.underlying.execute(sql, args)
            if "WHERE status = 'failed' AND payment_due_date" in sql:
                selected.set()
                assert resume.wait(10)
            return result

    def penalty_worker():
        with env.db() as db:
            return run_apply_penalties(PauseAfterCandidates(db))

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(penalty_worker)
        try:
            assert selected.wait(10)
            with env.db() as db:
                assert process_payment_row(db, dict(payment))
        finally:
            resume.set()
        assert pending.result(timeout=15)['penalties_applied'] == 0
    with env.db() as db:
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s', (graph.customer['id'],)).fetchone()['balance'] == 5000
        assert db.execute_exact('SELECT count(*) AS n FROM agreement_payment_penalties WHERE monthly_payment_id=%s', (payment['id'],)).fetchone()['n'] == 0


@pytest.mark.parametrize('kind', ['one_time','agreement'])
def test_new_credit_does_not_reopen_an_already_paid_legacy_entitlement(remediation_env, kind):
    env = remediation_env
    graph, station, pump, data = _setup(env, kind=kind)
    payment = _legacy_payment(env, graph) if kind == 'one_time' else _monthly_payment(env, graph)
    with env.db() as db:
        if kind == 'one_time':
            assert release_one_time_payment(db, payment['id'])['payout_amount'] == 15000
        else:
            assert process_payment_row(db, payment)
    _redeem(env, graph, station, pump, {**data, 'max_amount':'45000'}, liters='180')
    with env.db() as db:
        if kind == 'one_time':
            replay = release_one_time_payment(db, payment['id'])
            assert replay['already_released'] and replay['fuel_credit_recovered'] == 0
        else:
            assert process_payment_row(db, payment)
            assert payment['fuel_credit_recovered'] == 0
        assert db.execute_exact('SELECT outstanding_credit FROM fuel_credit_accounts WHERE transporter_user_id=%s',
                                (graph.owner['id'],)).fetchone()['outstanding_credit'] == 20000
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s', (graph.owner['id'],)).fetchone()['balance'] == 30000


@pytest.mark.parametrize('kind', ['one_time','agreement'])
def test_persisted_invoice_and_earnings_reads_show_recovery_without_repricing(remediation_env, monkeypatch, kind):
    from agreements import routes as agreement_routes
    from wallet import helpers as wallet_helpers
    from wallet.earnings import legacy_fuel_recovery_totals

    env = remediation_env
    monkeypatch.setattr(wallet_helpers, 'open_db', env.db)
    if kind == 'agreement':
        monkeypatch.setattr(agreement_routes, 'open_db', env.db)
        env.app.register_blueprint(agreement_routes.agreements_blueprint)
    graph, station, pump, data = _setup(env, kind=kind)
    _redeem(env, graph, station, pump, data)
    payment = (_legacy_payment(env, graph, gross='23000', fee='5000') if kind == 'one_time'
               else _monthly_payment(env, graph, gross='23000', fee='5000'))
    current_month = datetime.now(timezone.utc).strftime('%Y-%m')
    invoice_month = (datetime.now(timezone.utc)-timedelta(days=40)).strftime('%Y-%m')
    with env.db() as db:
        if kind == 'one_time':
            release_one_time_payment(db, payment['id'])
        else:
            # The late payout happens now, but belongs to the original invoice
            # month; its offset must not make this month's earnings negative.
            db.execute('UPDATE agreement_monthly_payments SET month_year=%s WHERE id=%s', (invoice_month, payment['id']))
            assert process_payment_row(db, dict(payment))
        current = legacy_fuel_recovery_totals(db, graph.owner['id'], current_month)
        assert current['total'] == 15000
        assert current['month'] == (15000 if kind == 'one_time' else 0)
        if kind == 'agreement':
            assert legacy_fuel_recovery_totals(db, graph.owner['id'], invoice_month)['month'] == 15000
    if kind == 'one_time':
        invoice_response = graph.owner_client.get(f"/api/orders/{payment['shipment_id']}")
        assert invoice_response.status_code == 200, invoice_response.json
        invoice = invoice_response.json['payment']
    else:
        invoice_response = graph.owner_client.get(f"/api/agreements/{payment['agreement_id']}/payments")
        assert invoice_response.status_code == 200, invoice_response.json
        invoice = next(row for row in invoice_response.json['payments'] if row['id'] == payment['id'])
    assert invoice['transporter_amount'] == 18000
    assert invoice['transporter_entitlement'] == '18000.00'
    assert invoice['fuel_credit_recovered'] == '15000.00'
    assert invoice['wallet_credit_amount'] == '3000.00'
    summary_response = graph.owner_client.get('/api/wallet/earnings-summary')
    assert summary_response.status_code == 200, summary_response.json
    summary = summary_response.json
    assert summary['lifetime_earnings'] == 3000
    assert summary['month_earnings'] == (3000 if kind == 'one_time' else 0)
    assert summary['legacy_fuel_credit_recovered'] == summary['total_fuel_credit_recovered'] == '15000.00'
    with env.db() as db:
        table = 'payments' if kind == 'one_time' else 'agreement_monthly_payments'
        saved = db.execute_exact(f'SELECT * FROM {table} WHERE id=%s', (payment['id'],)).fetchone()
        for field in ('company_fee','transporter_amount','company_share_percent','transporter_share_percent'):
            assert saved[field] == payment[field]
