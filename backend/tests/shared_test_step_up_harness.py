"""Opt-in, test-only harness for authorized shared TEST step-up probes."""
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
    provider = DeterministicPayoutProvider(outcome)
    original = wallet_routes.get_payment_provider
    wallet_routes.get_payment_provider = lambda: provider
    try:
        yield provider
    finally:
        wallet_routes.get_payment_provider = original

class SharedTestFixtureLedger:
    """Owned fixture ledger with exact-row, ownership-checked cleanup."""
    _SUPPORTED = {"users", "trusted_devices", "user_sessions", "mpin_credentials"}

    def __init__(self, url):
        self.url = url
        self.tag = f"dtx_shared_step_up_{secrets.token_hex(8)}"
        self._owned_rows = []
        self._cleaned = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.cleanup()
        except Exception as cleanup_error:
            if exc_value is not None:
                raise ExceptionGroup("probe and fixture cleanup failed", [exc_value, cleanup_error])
            raise
        return False

    def connect(self):
        return psycopg2.connect(self.url)

    def _register_owned(self, table, key_column, key_value, owner_sql, owner_params):
        if table not in self._SUPPORTED:
            raise SharedTestHarnessError("unsupported fixture table")
        self._owned_rows.append((table, key_column, key_value, owner_sql, tuple(owner_params)))

    def cleanup(self):
        if self._cleaned:
            return
        with self.connect() as conn:
            with conn.cursor() as cursor:
                for table, key_column, key_value, owner_sql, owner_params in reversed(self._owned_rows):
                    cursor.execute(owner_sql, owner_params)
                    if cursor.fetchone() is None:
                        raise SharedTestHarnessError(f"ownership uncertain for {table}:{key_value}")
                    cursor.execute(f"DELETE FROM public.{table} WHERE {key_column}=%s", (key_value,))
                    if cursor.rowcount != 1:
                        raise SharedTestHarnessError(f"owned fixture delete was not exact for {table}:{key_value}")
            conn.commit()
        self._owned_rows.clear()
        self._cleaned = True

    def create_user(self, *, legacy_role, app_role):
        with self.connect() as conn, conn.cursor() as cursor:
            email = f"{self.tag}.{secrets.token_hex(4)}@example.invalid"
            cnic = secrets.token_hex(7)[:13]
            cursor.execute(
                "INSERT INTO public.users(full_name,email,cnic,role,legacy_role) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (self.tag, email, cnic, app_role, legacy_role),
            )
            user_id = cursor.fetchone()[0]
            conn.commit()
        self._register_owned("users", "id", user_id,
                             "SELECT id FROM public.users WHERE id=%s AND email=%s AND full_name=%s",
                             (user_id, email, self.tag))
        return user_id

    def attach_authentication(self, user_id):
        device_raw = secrets.token_urlsafe(32)
        session_raw = secrets.token_urlsafe(32)
        access_raw = secrets.token_urlsafe(32)
        device_digest = hashlib.sha256(device_raw.encode()).digest()
        session_digest = hashlib.sha256(session_raw.encode()).digest()
        access_digest = hashlib.sha256(access_raw.encode()).digest()
        with self.connect() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.trusted_devices(token_digest,user_id,expires_at) VALUES(%s,%s,now()+interval '30 days') RETURNING id",
                (device_digest, user_id),
            )
            device_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at) VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',%s,now()+interval '8 hours') RETURNING session_id",
                (user_id, session_digest, device_id, access_digest),
            )
            session_id = cursor.fetchone()[0]
            salt, verifier = mpin_service.build_credential("1234")
            cursor.execute(
                "INSERT INTO public.mpin_credentials(user_id,verifier,salt,kdf_version) VALUES(%s,%s,%s,1)",
                (user_id, verifier, salt),
            )
            conn.commit()
        self._register_owned("mpin_credentials", "user_id", user_id,
                             "SELECT user_id FROM public.mpin_credentials WHERE user_id=%s AND verifier=%s AND salt=%s",
                             (user_id, verifier, salt))
        self._register_owned("user_sessions", "session_id", session_id,
                             "SELECT session_id FROM public.user_sessions WHERE session_id=%s AND user_id=%s AND token_digest=%s AND access_proof_digest=%s",
                             (session_id, user_id, session_digest, access_digest))
        self._register_owned("trusted_devices", "id", device_id,
                             "SELECT id FROM public.trusted_devices WHERE id=%s AND user_id=%s AND token_digest=%s",
                             (device_id, user_id, device_digest))
        return {"device_id": device_id, "session_id": session_id, "device_raw": device_raw, "session_raw": session_raw, "access_raw": access_raw}

@contextmanager
def shared_test_route_app(monkeypatch, fixture):
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
