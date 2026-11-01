"""Audit counterexamples. Passing means the documented defect was reproduced.

Run with run_backend.py, not against any shared/application database.
These are evidence probes, not desired-behavior regression tests.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from flask import Flask

from tests.remediation_harness import remediation_database_url, remediation_env


def test_new_profile_save_truncates_name_and_discards_business_fields(remediation_env):
    env = remediation_env
    user = env.user('service_seeker')
    client, _ = env.login(user)
    response = client.put('/api/profile', headers=env.headers, json={
        'first_name': 'Ali', 'last_name': 'Abbas', 'phone': '03001234567',
        'company_name': 'Audit Transport Buyer', 'contact_phone': '03007654321',
        'billing_address': 'Audit billing address', 'address': 'Audit billing address',
    })
    assert response.status_code == 200, response.json
    assert response.json['success'] is True
    assert response.json['user']['first_name'] == 'Ali'
    assert response.json['user']['last_name'] == ''
    assert response.json['user'].get('company_name') != 'Audit Transport Buyer'
    with env.db() as db:
        row = db.execute('SELECT full_name,address FROM users WHERE id=%s', (user['id'],)).fetchone()
        assert row['full_name'] == 'Ali'
        assert row['address'] != 'Audit billing address'


def test_be12_signed_in_contact_loses_user_attribution(remediation_env):
    env = remediation_env
    user = env.user()
    client, _ = env.login(user)
    response = client.post('/api/contact', headers=env.headers, json={
        'name': 'Audit User', 'email': 'audit@example.invalid',
        'subject': 'Audit attribution', 'message': 'Synthetic local inquiry',
    })
    assert response.status_code == 200, response.json
    with env.db() as db:
        ticket = db.execute('SELECT user_id FROM contact_messages WHERE id=%s', (response.json['ticket_id'],)).fetchone()
        assert ticket['user_id'] is None


def test_be09_two_same_day_worker_runs_charge_two_penalties(remediation_env):
    from agreements.helpers import run_apply_penalties, PENALTY_AMOUNT
    from tests.test_driver_workflow_hardening import _graph
    from tests.test_business_legacy_earnings_recovery import _monthly_payment
    env = remediation_env
    graph = _graph(env, kind='agreement')
    payment = _monthly_payment(env, graph, gross='1000000', fee='200000')
    initial = Decimal(str(PENALTY_AMOUNT)) * 3
    with env.db() as db:
        db.execute("UPDATE wallets SET balance=%s WHERE user_id=%s", (initial, graph.customer['id']))
        db.execute("UPDATE agreement_monthly_payments SET status='failed',payment_due_date=CURRENT_DATE-1 WHERE id=%s", (payment['id'],))
    for _ in range(2):
        with env.db() as db:
            assert run_apply_penalties(db)['penalties_applied'] == 1
    with env.db() as db:
        assert db.execute('SELECT count(*) AS n FROM agreement_payment_penalties WHERE monthly_payment_id=%s', (payment['id'],)).fetchone()['n'] == 2
        assert db.execute_exact('SELECT balance FROM wallets WHERE user_id=%s', (graph.customer['id'],)).fetchone()['balance'] == initial - Decimal(str(PENALTY_AMOUNT))*2


def test_auth06_signup_wrong_json_shape_and_name_still_raise(monkeypatch):
    from auth import routes
    monkeypatch.setattr(routes, '_record_signup_started', lambda *a: None)
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='audit-local')
    app.register_blueprint(routes.auth_blueprint)
    for payload in ([1], {'name': 123}):
        with pytest.raises(AttributeError):
            app.test_client().post('/auth/signup', json=payload)


def test_auth05_reset_issuance_has_no_resend_admission_limit(monkeypatch):
    from auth import routes
    sent, saved = [], []
    monkeypatch.setattr(routes, 'get_user_by_login', lambda _: ({'id': 1, 'email': 'audit@example.invalid'}, None, None))
    monkeypatch.setattr(routes, 'latest_otp_record', lambda *a: {'cooldown_until_iso': None})
    monkeypatch.setattr(routes, 'send_email', lambda *a: sent.append(1))
    monkeypatch.setattr(routes, 'create_otp_record', lambda *a: saved.append(1))
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='audit-local')
    app.register_blueprint(routes.auth_blueprint)
    client = app.test_client()
    for _ in range(6):
        response = client.post('/auth/forgot-password', json={'loginId': 'audit@example.invalid'})
        assert response.status_code == 200
        assert 'masked_email' in response.json
    assert len(sent) == len(saved) == 6


def test_be10_invoice_due_date_precedes_agreement_start():
    from agreements.helpers import due_date_for_month
    assert due_date_for_month(date(2026, 10, 27), 0) == date(2026, 10, 10)


def test_db09_db10_legacy_normalization_loses_offset_and_cents():
    from shared.db import _normalize_value
    assert _normalize_value(datetime(2026,10,27,12,tzinfo=timezone.utc)) == '2026-10-27T12:00:00'
    assert Decimal(str(_normalize_value(Decimal('9007199254740992.01')))) != Decimal('9007199254740992.01')


def test_db14_first_use_constructs_two_pools(monkeypatch):
    from shared import db
    gate = Barrier(2)
    pools = []
    def create(*a, **kw):
        value = object()
        pools.append(value)
        gate.wait(timeout=10)
        return value
    monkeypatch.setattr(db, '_pool', None)
    monkeypatch.setattr(db.psycopg2.pool, 'ThreadedConnectionPool', create)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: db._get_pool(), range(2)))
    assert len(pools) == 2 and results[0] is not results[1]
