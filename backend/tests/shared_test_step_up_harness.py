"""Opt-in, test-only harness for authorized shared TEST step-up probes.

No application imports this module. It refuses every target except the
explicitly configured authorized TEST project and patches provider behavior only
inside an in-process test context.
"""
from contextlib import contextmanager
import base64
import hashlib
import os
import secrets
from urllib.parse import urlsplit

import psycopg2
from flask import Flask

from auth import mpin_service
import auth.helpers as auth_helpers
import auth.routes as auth_routes
import agreements.routes as agreements_routes
import orders.routes as orders_routes
import wallet.helpers as wallet_helpers
import wallet.routes as wallet_routes
from shared.db import Db
from shared.payments import PaymentProviderRejected

ACTIVATION_ENV = "DTX_SHARED_TEST_HARNESS"
PROJECT_ENV = "DTX_SHARED_TEST_PROJECT_REF"
URL_ENV = "SUPABASE_DB_URL"
EXPECTED_PROJECT_REF = "fysupkvuvhvtowbfgoev"
EXPECTED_HOST = "aws-0-ap-northeast-1.pooler.supabase.com"
PEPPER = base64.urlsafe_b64encode(b"S" * 32).decode()

class SharedTestHarnessError(RuntimeError):
    pass

def require_authorized_shared_test_url(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get(ACTIVATION_ENV) != "1":
        raise SharedTestHarnessError("shared TEST harness is not explicitly enabled")
    if environ.get(PROJECT_ENV) != EXPECTED_PROJECT_REF:
        raise SharedTestHarnessError("shared TEST project identity is not authorized")
    raw_url = environ.get(URL_ENV, "").strip()
    if not raw_url:
        raise SharedTestHarnessError("SUPABASE_DB_URL is required for shared TEST")
    parsed = urlsplit(raw_url)
    host = (parsed.hostname or "").lower()
    if host != EXPECTED_HOST:
        raise SharedTestHarnessError("target is not an authorized Supabase pooler")
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise SharedTestHarnessError("loopback is not a shared TEST target")
    if parsed.path.rstrip("/") != "/postgres":
        raise SharedTestHarnessError("shared TEST database must be postgres")
    if parsed.username != "postgres":
        raise SharedTestHarnessError("shared TEST runner must be the approved postgres role")
    return raw_url

class DeterministicPayoutProvider:
    """In-process provider boundary used only by the opt-in test runner."""
    def __init__(self, outcome):
        if outcome not in {"success", "reject", "ambiguous"}:
            raise ValueError("unknown deterministic provider outcome")
        self.outcome = outcome
        self.calls = 0
    def tokenize(self, summary):
        self.calls += 1
        if self.outcome == "reject":
            raise PaymentProviderRejected("test-only definite rejection")
        if self.outcome == "ambiguous":
            raise RuntimeError("test-only ambiguous provider outcome")
        return f"shared-test-{secrets.token_hex(16)}"

@contextmanager
def deterministic_payout_provider(outcome):
    """Patch the route's imported provider accessor for one test only."""
    provider = DeterministicPayoutProvider(outcome)
    original = wallet_routes.get_payment_provider
    wallet_routes.get_payment_provider = lambda: provider
    try:
        yield provider
    finally:
        wallet_routes.get_payment_provider = original

class SharedTestFixtureLedger:
    """Exact-row fixture bookkeeping; never truncates or bypasses RLS."""
    def __init__(self, url):
        self.url = url
        self.tag = f"dtx_shared_step_up_{secrets.token_hex(8)}"
        self.rows = []
    def connect(self):
        return psycopg2.connect(self.url)
    def record(self, table, key_column, key_value):
        if not table.replace("_", "").isalnum() or not key_column.replace("_", "").isalnum():
            raise SharedTestHarnessError("fixture identifiers must be static SQL identifiers")
        self.rows.append((table, key_column, key_value))
    def cleanup(self):
        with self.connect() as conn:
            with conn.cursor() as cursor:
                for table, key_column, key_value in reversed(self.rows):
                    cursor.execute(f"DELETE FROM public.{table} WHERE {key_column}=%s", (key_value,))
            conn.commit()
        self.rows.clear()
    def create_user(self, *, legacy_role, app_role):
        with self.connect() as conn, conn.cursor() as cursor:
            email = f"{self.tag}.{secrets.token_hex(4)}@example.invalid"
            cnic = (secrets.token_hex(7))[:13]
            cursor.execute(
                "INSERT INTO public.users(full_name,email,cnic,role,legacy_role) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (self.tag, email, cnic, app_role, legacy_role),
            )
            user_id = cursor.fetchone()[0]
            conn.commit()
        self.record("users", "id", user_id)
        return user_id
    def attach_authentication(self, user_id):
        device_raw = secrets.token_urlsafe(32)
        session_raw = secrets.token_urlsafe(32)
        access_raw = secrets.token_urlsafe(32)
        with self.connect() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.trusted_devices(token_digest,user_id,expires_at) VALUES(%s,%s,now()+interval '30 days') RETURNING id",
                (hashlib.sha256(device_raw.encode()).digest(), user_id),
            )
            device_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at) VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',%s,now()+interval '8 hours') RETURNING session_id",
                (user_id, hashlib.sha256(session_raw.encode()).digest(), device_id, hashlib.sha256(access_raw.encode()).digest()),
            )
            session_id = cursor.fetchone()[0]
            salt, verifier = mpin_service.build_credential("1234")
            cursor.execute(
                "INSERT INTO public.mpin_credentials(user_id,verifier,salt,kdf_version) VALUES(%s,%s,%s,1)",
                (user_id, verifier, salt),
            )
            conn.commit()
        self.record("mpin_credentials", "user_id", user_id)
        self.record("user_sessions", "session_id", session_id)
        self.record("trusted_devices", "id", device_id)
        return {"device_id": device_id, "session_id": session_id, "device_raw": device_raw, "session_raw": session_raw, "access_raw": access_raw}

@contextmanager
def shared_test_route_app(monkeypatch, fixture):
    """Patch route DB ownership to the authorized shared TEST connection."""
    url = require_authorized_shared_test_url()
    @contextmanager
    def test_open_db():
        conn = psycopg2.connect(url)
        try:
            yield Db(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    for module in (agreements_routes, auth_helpers, auth_routes, orders_routes, wallet_helpers, wallet_routes):
        monkeypatch.setattr(module, "open_db", test_open_db)
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    monkeypatch.setenv("DIGITRANSX_MPIN_PEPPER", PEPPER)
    app = Flask(__name__)
    app.config.update(SECRET_KEY=f"{fixture.tag}-test-only", SESSION_COOKIE_SECURE=False, TESTING=True)
    app.register_blueprint(auth_routes.auth_blueprint)
    app.register_blueprint(orders_routes.orders_blueprint)
    app.register_blueprint(wallet_routes.wallet_blueprint)
    app.register_blueprint(agreements_routes.agreements_blueprint)
    yield app

def open_shared_test_fixture():
    return SharedTestFixtureLedger(require_authorized_shared_test_url())

