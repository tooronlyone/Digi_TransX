import os
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ['SUPABASE_DB_URL'] = 'postgresql://audit:audit@127.0.0.1:1/audit?connect_timeout=1'
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'backend'))
from flask import Flask
from auth import helpers
from auth.session_cache import clear_all_cached_auth
from agreements.helpers import parse_positive_float, due_date_for_month

app = Flask(__name__)
app.config.update(SECRET_KEY='audit-local-test-secret', SESSION_COOKIE_SECURE=False)
durable = {'user_id': 1, 'session_id': 'audit-session', 'access_locked': False, 'access_proof_valid': True}
user = {'id': 1, 'role': 'service_seeker'}
calls = {'lookups': 0}

@contextmanager
def db_context():
    yield object()

def find(*args, **kwargs):
    calls['lookups'] += 1
    return dict(durable)

@helpers.login_required(refresh_activity=False)
def protected():
    return helpers.json_response({'authorized': True})

clear_all_cached_auth()
with patch.object(helpers, 'open_db', db_context), patch.object(helpers, 'find_session_by_token', find), patch.object(helpers, 'get_user_by_id_with_executor', lambda *a: dict(user)):
    with app.test_request_context(headers={'Cookie': 'dtx_session_token=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; dtx_device_token=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb; dtx_access_proof=cccccccccccccccccccccccccccccccc'}):
        assert protected().status_code == 200
    durable.update(revoked_at='now', access_proof_valid=False)
    with app.test_request_context(headers={'Cookie': 'dtx_session_token=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; dtx_device_token=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb; dtx_access_proof=cccccccccccccccccccccccccccccccc'}):
        assert protected().status_code == 200
    assert calls['lookups'] == 1
print('PASS: cached authorization skips fresh revoked-session lookup')

clear_all_cached_auth()
state = {'inside': False, 'escaped': False}
@contextmanager
def guarded_db():
    state['inside'] = True
    try:
        yield object()
    finally:
        state['inside'] = False

def lock(*args):
    state['escaped'] = not state['inside']
    raise RuntimeError('connection is no longer checked out')

with patch.object(helpers, 'open_db', guarded_db), patch.object(helpers, 'find_session_by_token', lambda *a, **k: dict(durable)), patch.object(helpers, 'get_user_by_id_with_executor', lambda *a: dict(user)), patch.object(helpers, 'lock_session_user_and_device', lock):
    with app.test_request_context(headers={'Cookie': 'dtx_session_token=dddddddddddddddddddddddddddddddd; dtx_device_token=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'}):
        assert protected().status_code == 503
assert state['escaped']
print('PASS: access-lock SQL is attempted after open_db exits')

for value in ('NaN', 'Infinity'):
    result = parse_positive_float(value, 'Rate')
    print('PASS: parse_positive_float accepts', str(result))
assert due_date_for_month(date(2026, 10, 23), 0) == date(2026, 10, 10)
print('PASS: first agreement payment is due before the agreement starts')

from auth.routes import auth_blueprint
app.register_blueprint(auth_blueprint)
app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
with app.test_client() as client:
    response = client.post('/auth/login', json={'loginId': 123, 'password': 'abcdefgh'})
    assert response.status_code == 500
print('PASS: wrong JSON scalar type produces unhandled HTTP500 before provider lookup')
