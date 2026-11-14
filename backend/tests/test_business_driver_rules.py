"""Rule 4 owner-operator, collateral and incident authorization on real PG."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
from decimal import Decimal

import pytest

from tests.remediation_harness import remediation_database_url,remediation_env
from tests.test_driver_workflow_hardening import _graph,_invite,_accept,_driver


def test_investigation_read_authorization_and_immutable_evidence(remediation_env):
    import psycopg2
    env=remediation_env
    graph=_graph(env)
    assignment=_invite(env,graph)
    _accept(env,graph,assignment)
    report=graph.driver_client.post('/api/operational-incidents',headers=env.headers,json={
        'assignment_id':assignment,'incident_type':'emergency','description':'Vehicle safety emergency requires investigation.',
        'evidence':[{'authenticated_handoff_reference':'fixture-handoff-123'}],
    })
    assert report.status_code==200,report.json
    incident=report.json['incident_id']
    assert graph.driver_client.get('/api/admin/operational-incidents').status_code==403
    assert graph.owner_client.get(f'/api/operational-incidents/{incident}').status_code==200
    outsider,_=env.login(env.user('logistics_provider'))
    assert outsider.get(f'/api/operational-incidents/{incident}').status_code==404
    admin,_=env.login(_admin(env))
    listed=admin.get('/api/admin/operational-incidents')
    assert listed.status_code==200 and listed.headers['Cache-Control']=='no-store'
    saved=next(row for row in listed.json['incidents'] if row['id']==incident)
    assert saved['driver_user_id']==graph.driver['id']
    assert 'fixture-handoff-123' in saved['evidence']
    with pytest.raises(psycopg2.errors.CheckViolation):
        with env.db() as db: db.execute("UPDATE operational_incidents SET evidence='[]'::jsonb WHERE id=%s",(incident,))
    decision=admin.post(f'/api/admin/operational-incidents/{incident}/decision',headers=env.headers,
                        json={'status':'dismissed','decision_evidence':'Independent GPS, handoff and communications review cleared the Driver.'})
    assert decision.status_code==200,decision.json
    with pytest.raises(psycopg2.errors.CheckViolation):
        with env.db() as db: db.execute("UPDATE operational_incidents SET status='confirmed' WHERE id=%s",(incident,))

def _admin(env):
    # Public signup metadata must not grant administrator privileges. Only this
    # isolated fixture's privileged SQL establishes the independently verified
    # admin used for authenticated review routes.
    user=env.user()
    with env.db() as db:db.execute("UPDATE users SET role='admin',legacy_role='platform_admin' WHERE id=%s",(user['id'],))
    return user

def _credential(env,owner,*,client=None,expiry=None):
    if client is None:
        admin=_admin(env)
        client,_=env.login(admin)
    return client.post(f'/api/admin/owner-operator-credentials/{owner["id"]}',headers=env.headers,json={'license_number':'VERIFIED-LTV-123','license_expiry':(expiry or date.today()+timedelta(days=365)).isoformat(),'verification_evidence':'Independent licensing authority verification receipt 12345'})

def _self_payload(graph):
    return {'truck_id':graph.truck_id,'trip_id':graph.trip_id}

def test_verified_owner_operator_assignment_is_idempotent_and_role_scoped(remediation_env):
    env=remediation_env
    graph=_graph(env)
    assert _credential(env,graph.owner).status_code==200
    result=graph.owner_client.post('/api/transporter/drive-myself',headers=env.headers,json=_self_payload(graph))
    assert result.status_code==200,result.json
    assert graph.owner_client.post('/api/transporter/drive-myself',headers=env.headers,json=_self_payload(graph)).json['replayed']
    with env.db() as db:
        row=db.execute('SELECT driver_user_id,transporter_user_id,truck_id,assignment_mode,accepted_at FROM driver_trip_assignments WHERE id=%s',(result.json['assignment_id'],)).fetchone()
        assert row['driver_user_id']==row['transporter_user_id']==graph.owner['id']
        assert row['assignment_mode']=='owner_operator' and row['accepted_at'] is not None
    # GPS has a dedicated, narrow capability; unrelated Driver portal permissions
    # do not become available merely because the owner is driving this trip.
    ping=graph.owner_client.post('/api/transporter/owner-operator/gps',headers=env.headers,json={'lat':31.5,'lng':74.25})
    assert ping.status_code==200,ping.json
    assert ping.json['truck_id']==graph.truck_id
    assert graph.owner_client.get('/api/driver/me').status_code==403

def test_owner_operator_requires_admin_verified_current_credentials(remediation_env):
    env=remediation_env
    graph=_graph(env)
    result=graph.owner_client.post('/api/transporter/drive-myself',headers=env.headers,json=_self_payload(graph))
    assert result.status_code==409 and result.json['code']=='owner_operator_credentials_required'
    assert _credential(env,graph.owner,client=graph.owner_client).status_code==403
    assert _credential(env,graph.owner,expiry=date.today()-timedelta(days=1)).status_code==400
    assert _credential(env,graph.owner).status_code==200
    with env.db() as db:db.execute('UPDATE owner_operator_credentials SET license_expiry=CURRENT_DATE-1 WHERE user_id=%s',(graph.owner['id'],))
    assert graph.owner_client.post('/api/transporter/drive-myself',headers=env.headers,json=_self_payload(graph)).status_code==409

def test_owner_operator_cannot_take_foreign_trip_or_conflicting_driver_assignment(remediation_env):
    env=remediation_env
    graph=_graph(env)
    other=_graph(env)
    assert _credential(env,graph.owner).status_code==200
    assert graph.owner_client.post('/api/transporter/drive-myself',headers=env.headers,json=_self_payload(other)).status_code==409
    assignment=_invite(env,graph)
    _accept(env,graph,assignment)
    result=graph.owner_client.post('/api/transporter/drive-myself',headers=env.headers,json=_self_payload(graph))
    assert result.status_code==409 and result.json['code']=='assignment_conflict'

def test_simultaneous_owner_operator_assignments_cannot_double_book_driver(remediation_env):
    env=remediation_env
    owner=env.user('logistics_provider')
    graphs=[_graph(env,owner=owner) for _ in range(2)]
    assert _credential(env,owner).status_code==200
    def assign(graph):return graph.owner_client.post('/api/transporter/drive-myself',headers=env.headers,json=_self_payload(graph)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(assign,graphs))==[200,409]

def test_owner_operator_gps_rechecks_license_and_rejects_substitutions(remediation_env):
    env=remediation_env
    graph=_graph(env)
    assert _credential(env,graph.owner).status_code==200
    assert graph.owner_client.post('/api/transporter/drive-myself',headers=env.headers,json=_self_payload(graph)).status_code==200
    assert graph.owner_client.post('/api/transporter/owner-operator/gps',headers=env.headers,json={'lat':31,'lng':74,'truck_id':graph.truck_id+999}).status_code==404
    with env.db() as db:db.execute('UPDATE owner_operator_credentials SET license_expiry=CURRENT_DATE-1 WHERE user_id=%s',(graph.owner['id'],))
    result=graph.owner_client.post('/api/transporter/owner-operator/gps',headers=env.headers,json={'lat':31,'lng':74})
    assert result.status_code==409 and result.json['code']=='owner_operator_credentials_required'
    assert graph.driver_client.post('/api/transporter/owner-operator/gps',headers=env.headers,json={'lat':31,'lng':74}).status_code==403

def test_temporary_driver_requires_full_10000_frozen_reserve(remediation_env):
    env=remediation_env
    graph=_graph(env)
    assignment=_invite(env,graph)
    with env.db() as db:db.execute('UPDATE wallets SET balance=9999.99,minimum_required=10000 WHERE user_id=%s',(graph.driver['id'],))
    response=graph.driver_client.post(f'/api/driver/trips/{assignment}/respond',headers=env.headers,json={'action':'accept'})
    assert response.status_code==409,response.json
    with env.db() as db:
        assert db.execute('SELECT status FROM driver_trip_assignments WHERE id=%s',(assignment,)).fetchone()['status']=='requested'
        db.execute('UPDATE wallets SET balance=10000 WHERE user_id=%s',(graph.driver['id'],))
    _accept(env,graph,assignment)
    with env.db() as db:
        reserve=db.execute_exact('SELECT balance,reserve_kind FROM security_reserves WHERE user_id=%s',(graph.driver['id'],)).fetchone()
        assert reserve=={'balance':Decimal('10000'),'reserve_kind':'temporary_driver'}
        assert db.execute_exact('SELECT locked_balance FROM wallets WHERE user_id=%s',(graph.driver['id'],)).fetchone()['locked_balance']==Decimal('10000')

@pytest.mark.parametrize('kind',['abandonment','accident','theft','negligence','emergency'])
def test_incidents_and_confirmed_decisions_never_automatically_confiscate_funds(remediation_env,kind):
    env=remediation_env
    graph=_graph(env)
    assignment=_invite(env,graph)
    _accept(env,graph,assignment)
    response=graph.driver_client.post('/api/operational-incidents',headers=env.headers,json={'assignment_id':assignment,'incident_type':kind,'description':'Detailed authenticated safety report with evidence','evidence':['photo:authenticated-reference']})
    assert response.status_code==200,response.json
    incident=response.json['incident_id']
    with env.db() as db:
        assert db.execute('SELECT status FROM operational_incidents WHERE id=%s',(incident,)).fetchone()['status']=='investigating'
        assert db.execute_exact('SELECT balance,locked_balance FROM wallets WHERE user_id=%s',(graph.driver['id'],)).fetchone()=={'balance':Decimal('10000'),'locked_balance':Decimal('10000')}
        assert db.execute('SELECT status FROM driver_trip_assignments WHERE id=%s',(assignment,)).fetchone()['status']=='accepted'
    assert graph.owner_client.post(f'/api/admin/operational-incidents/{incident}/decision',headers=env.headers,json={'status':'confirmed','decision_evidence':'Verified investigation evidence'}).status_code==403
    admin=_admin(env)
    admin_client,_=env.login(admin)
    decision=admin_client.post(f'/api/admin/operational-incidents/{incident}/decision',headers=env.headers,json={'status':'confirmed','decision_evidence':'Verified investigation evidence and signed handoff'})
    assert decision.status_code==200,decision.json
    assert decision.json['financial_adjustment']=='blocked_pending_approved_penalty_policy'
    with env.db() as db:
        assert db.execute_exact('SELECT balance FROM security_reserves WHERE user_id=%s',(graph.driver['id'],)).fetchone()['balance']==Decimal('10000')
        assert db.execute('SELECT status FROM driver_trip_assignments WHERE id=%s',(assignment,)).fetchone()['status']=='accepted'

def test_only_transporter_can_initiate_assigned_trip_cancellation(remediation_env):
    env=remediation_env
    graph=_graph(env)
    assignment=_invite(env,graph)
    _accept(env,graph,assignment)
    endpoint=f'/api/transporter/trips/{assignment}/cancellation-request'
    payload={'reason':'Operational schedule change requires authorized cancellation review'}
    assert graph.driver_client.post(endpoint,headers=env.headers,json=payload).status_code==403
    result=graph.owner_client.post(endpoint,headers=env.headers,json=payload)
    assert result.status_code==200 and result.json['status']=='pending_policy_review'
    assert graph.owner_client.post(endpoint,headers=env.headers,json=payload).status_code==200
    with env.db() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM trip_cancellation_requests WHERE assignment_id=%s',(assignment,)).fetchone()['n']==1
        assert db.execute('SELECT status FROM driver_trip_assignments WHERE id=%s',(assignment,)).fetchone()['status']=='accepted'

def test_incidents_reject_foreign_and_unconsented_assignments(remediation_env):
    env=remediation_env
    graph=_graph(env)
    assignment=_invite(env,graph)
    payload={'assignment_id':assignment,'incident_type':'theft','description':'Detailed evidence report awaiting investigation','evidence':[]}
    assert graph.driver_client.post('/api/operational-incidents',headers=env.headers,json=payload).status_code==404
    _accept(env,graph,assignment)
    outsider=env.user('driver')
    client,_=env.login(outsider)
    assert client.post('/api/operational-incidents',headers=env.headers,json=payload).status_code==404
