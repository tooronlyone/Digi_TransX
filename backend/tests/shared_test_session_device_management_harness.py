"""Closed shared-TEST harness for Phase 1B-2C6 session/device management."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
import secrets
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID

from flask import Flask
import psycopg2
from psycopg2.extras import RealDictCursor

from auth import routes as auth_routes, session_device_management as management
import auth.helpers as auth_helpers
from auth.session_service import session_event_reference, trusted_device_reference
from events.writer import write_security_event as canonical_write_security_event
from shared.db import Db

ACTIVATION_ENV = "DTX_SHARED_TEST_HARNESS"
PROJECT_ENV = "DTX_SHARED_TEST_PROJECT_REF"
URL_ENV = "SUPABASE_DB_URL"
EXPECTED_PROJECT_REF = "fysupkvuvhvtowbfgoev"
EXPECTED_HOST = "aws-0-ap-northeast-1.pooler.supabase.com"
CSRF = {"X-CSRF-Token": "session-device-harness-csrf"}


class SharedTestSessionDeviceHarnessError(RuntimeError):
    pass


class ProbeAndCleanupError(SharedTestSessionDeviceHarnessError):
    def __init__(self, probe_error, cleanup_error):
        super().__init__(f"probe failed with {type(probe_error).__name__}; cleanup failed with {type(cleanup_error).__name__}")
        self.probe_error = probe_error
        self.cleanup_error = cleanup_error


def require_authorized_shared_test_url(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get(ACTIVATION_ENV) != "1":
        raise SharedTestSessionDeviceHarnessError("shared TEST harness is not enabled")
    if environ.get(PROJECT_ENV) != EXPECTED_PROJECT_REF:
        raise SharedTestSessionDeviceHarnessError("shared TEST project is not authorized")
    raw_url = environ.get(URL_ENV, "").strip()
    if not raw_url:
        raise SharedTestSessionDeviceHarnessError("shared TEST database URL is required")
    parsed = urlsplit(raw_url)
    if (parsed.hostname or "").lower() != EXPECTED_HOST:
        raise SharedTestSessionDeviceHarnessError("target is not the authorized pooler")
    if parsed.path.rstrip("/") != "/postgres":
        raise SharedTestSessionDeviceHarnessError("shared TEST database must be postgres")
    if parsed.username not in {"postgres", f"postgres.{EXPECTED_PROJECT_REF}"}:
        raise SharedTestSessionDeviceHarnessError("shared TEST role is not authorized")
    return raw_url


SNAPSHOT_QUERIES = (
    ("users", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.users t"),
    ("trusted_devices", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.trusted_devices t"),
    ("user_sessions", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.user_sessions t"),
    ("mpin_credentials", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.mpin_credentials t"),
    ("mpin_step_up_authorizations", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.mpin_step_up_authorizations t"),
    ("security_events", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.security_events t"),
)


def shared_test_state_snapshot(url):
    out = {}
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        for table, query in SNAPSHOT_QUERIES:
            cur.execute(query)
            count, fingerprint = cur.fetchone()
            out[table] = {"count": int(count), "fingerprint": fingerprint}
        conn.rollback()
    return out


def SharedTestSessionDeviceLedger(url):
    seal = object()
    rows = []
    controls = []
    control_fingerprints = []

    @dataclass(frozen=True)
    class UserReceipt:
        seal: object; user_id: object; email: str; cnic: str; full_name: str

    @dataclass(frozen=True)
    class DeviceReceipt:
        seal: object; device_id: object; user_id: object; token_digest: bytes

    @dataclass(frozen=True)
    class SessionReceipt:
        seal: object; session_id: object; user_id: object; device_id: object; token_digest: bytes; access_digest: bytes

    @dataclass(frozen=True)
    class EventReceipt:
        seal: object; event_id: object; event_name: str; request_id: str; scope: str; key: str; fingerprint: str; subject_user_id: object; session_ref: str | None; device_ref: str | None; source: str

    @dataclass(frozen=True)
    class FingerprintReceipt:
        seal: object; table: str; key: object; fingerprint: str

    def mint(receipt, *, control=False):
        if receipt.seal is not seal:
            raise SharedTestSessionDeviceHarnessError("unsealed ownership receipt")
        (controls if control else rows).append(receipt)

    class Ledger:
        def __init__(self):
            self.url = url
            self.tag = f"dtx_shared_2c6_{secrets.token_hex(8)}"
            self.closed = False
            self.graphs = {}
            self.cleanup_trace = []
            self.fail_after = None
            self.events_seen = 0

        def __enter__(self):
            self._ensure_open(); return self

        def __exit__(self, exc_type, exc_value, traceback):
            try:
                self.cleanup()
            except Exception as cleanup_error:
                if exc_value is not None:
                    raise ProbeAndCleanupError(exc_value, cleanup_error) from exc_value
                raise
            return False

        def _ensure_open(self):
            if self.closed:
                raise SharedTestSessionDeviceHarnessError("fixture ledger is closed")

        def _connect(self):
            return psycopg2.connect(self.url)

        def _fingerprint(self, table, key):
            fixed = {
                "trusted_devices": "SELECT md5(row_to_json(t)::text) FROM public.trusted_devices t WHERE id=%s",
                "user_sessions": "SELECT md5(row_to_json(t)::text) FROM public.user_sessions t WHERE session_id=%s",
            }
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(fixed[table], (key,))
                row = cur.fetchone(); conn.rollback()
            if not row:
                raise SharedTestSessionDeviceHarnessError("control row disappeared")
            return row[0]

        def _create_user(self, suffix, *, control=False):
            self._ensure_open()
            full_name = f"{self.tag}_{suffix}"
            email = f"{full_name}.{secrets.token_hex(4)}@example.invalid"
            cnic = str(int.from_bytes(secrets.token_bytes(7), "big"))[:13].zfill(13)
            with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM public.users WHERE email=%s OR cnic=%s OR full_name=%s", (email, cnic, full_name))
                if cur.fetchone() is not None:
                    raise SharedTestSessionDeviceHarnessError("user identity collision")
                cur.execute("INSERT INTO public.users(full_name,email,cnic,role,legacy_role) VALUES(%s,%s,%s,'customer','service_seeker') RETURNING id", (full_name, email, cnic))
                user_id = cur.fetchone()["id"]
                cur.execute("SELECT id FROM public.users WHERE id=%s AND email=%s AND cnic=%s AND full_name=%s AND legacy_role='service_seeker' FOR UPDATE", (user_id, email, cnic, full_name))
                if cur.fetchone() is None:
                    raise SharedTestSessionDeviceHarnessError("created user verification failed")
                conn.commit()
            mint(UserReceipt(seal, user_id, email, cnic, full_name), control=control)
            return {"id": user_id, "email": email, "auth_id": None, "role": "service_seeker", "legacy_role": "service_seeker"}

        def _create_chain(self, user, *, state="active", control=False):
            self._ensure_open()
            raw_device, raw_session, raw_access = (secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(32))
            dd, sd, ad = (hashlib.sha256(raw_device.encode()).digest(), hashlib.sha256(raw_session.encode()).digest(), hashlib.sha256(raw_access.encode()).digest())
            with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                if state == "expired":
                    cur.execute("INSERT INTO public.trusted_devices(token_digest,user_id,created_at,last_used_at,expires_at) VALUES(%s,%s,now()-interval '40 days',now()-interval '39 days',now()-interval '1 day') RETURNING id", (dd, user["id"]))
                elif state == "revoked":
                    cur.execute("INSERT INTO public.trusted_devices(token_digest,user_id,expires_at,revoked_at) VALUES(%s,%s,now()+interval '30 days',now()) RETURNING id", (dd, user["id"]))
                else:
                    cur.execute("INSERT INTO public.trusted_devices(token_digest,user_id,expires_at) VALUES(%s,%s,now()+interval '30 days') RETURNING id", (dd, user["id"]))
                device_id = cur.fetchone()["id"]
                if state == "expired":
                    cur.execute("INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,created_at,authenticated_at,last_genuine_activity_at,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at) VALUES(%s,%s,%s,now()-interval '10 days',now()-interval '10 days',now()-interval '9 days',now()-interval '1 day',now()+interval '1 day',%s,now()+interval '1 hour') RETURNING session_id", (user["id"], sd, device_id, ad))
                elif state == "revoked":
                    cur.execute("INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at,revoked_at,revocation_reason) VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',%s,now()+interval '8 hours',now(),'logout') RETURNING session_id", (user["id"], sd, device_id, ad))
                else:
                    cur.execute("INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at) VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',%s,now()+interval '8 hours') RETURNING session_id", (user["id"], sd, device_id, ad))
                session_id = cur.fetchone()["session_id"]
                cur.execute("SELECT session_id FROM public.user_sessions WHERE session_id=%s AND user_id=%s AND trusted_device_id=%s AND token_digest=%s AND access_proof_digest=%s FOR UPDATE", (session_id, user["id"], device_id, sd, ad))
                if cur.fetchone() is None:
                    raise SharedTestSessionDeviceHarnessError("created chain verification failed")
                conn.commit()
            mint(DeviceReceipt(seal, device_id, user["id"], dd), control=control)
            mint(SessionReceipt(seal, session_id, user["id"], device_id, sd, ad), control=control)
            if control:
                control_fingerprints.extend((
                    FingerprintReceipt(seal, "trusted_devices", device_id, self._fingerprint("trusted_devices", device_id)),
                    FingerprintReceipt(seal, "user_sessions", session_id, self._fingerprint("user_sessions", session_id)),
                ))
            return {"device_id": device_id, "session_id": session_id, "device_raw": raw_device, "session_raw": raw_session, "access_raw": raw_access}

        def _add_bound_session(self, user, device):
            raw_session, raw_access = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            sd, ad = hashlib.sha256(raw_session.encode()).digest(), hashlib.sha256(raw_access.encode()).digest()
            with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM public.trusted_devices WHERE id=%s AND user_id=%s FOR UPDATE", (device["device_id"], user["id"]))
                if cur.fetchone() is None:
                    raise SharedTestSessionDeviceHarnessError("bound device verification failed")
                cur.execute("INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at) VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',%s,now()+interval '8 hours') RETURNING session_id", (user["id"], sd, device["device_id"], ad))
                session_id = cur.fetchone()["session_id"]
                conn.commit()
            mint(SessionReceipt(seal, session_id, user["id"], device["device_id"], sd, ad))
            return {"session_id": session_id, "session_raw": raw_session, "access_raw": raw_access}

        def setup_graphs(self):
            self._ensure_open()
            owner = self._create_user("owner")
            foreign = self._create_user("foreign", control=True)
            current = self._create_chain(owner)
            session_target = self._create_chain(owner)
            device_target = self._create_chain(owner)
            bound = self._add_bound_session(owner, device_target)
            revoked = self._create_chain(owner, state="revoked")
            expired = self._create_chain(owner, state="expired")
            foreign_current = self._create_chain(foreign, control=True)
            rollback_user = self._create_user("rollback")
            rollback_current = self._create_chain(rollback_user)
            rollback_target = self._create_chain(rollback_user)
            rollback_bound = self._add_bound_session(rollback_user, rollback_target)
            logout_user = self._create_user("current_logout")
            logout_current = self._create_chain(logout_user)
            self.graphs = locals()

        @contextmanager
        def _runtime(self, user, *, fail_after=None):
            old_env = os.environ.get("DIGITRANSX_ENVIRONMENT")
            self.fail_after, self.events_seen = fail_after, 0
            captured = []

            def fixed_writer(executor, event_name, context, data, *, idempotency_scope, idempotency_key):
                if self.fail_after is not None and self.events_seen >= self.fail_after:
                    raise RuntimeError("synthetic canonical event failure")
                self.events_seen += 1
                result = canonical_write_security_event(executor, event_name, context, data, idempotency_scope=idempotency_scope, idempotency_key=idempotency_key)
                captured.append(result.event)
                return result

            @contextmanager
            def fixed_open_db():
                conn = psycopg2.connect(self.url)
                try:
                    yield Db(conn); conn.commit()
                except Exception:
                    conn.rollback(); raise
                finally:
                    conn.close()

            def fixed_user_by_id(user_id):
                return dict(user) if str(user_id) == str(user["id"]) else None

            old = (auth_helpers.open_db, auth_routes.open_db, auth_helpers.get_user_by_id, management.write_security_event, auth_routes.write_security_event)
            try:
                os.environ["DIGITRANSX_ENVIRONMENT"] = "test"
                auth_helpers.open_db = fixed_open_db
                auth_routes.open_db = fixed_open_db
                auth_helpers.get_user_by_id = fixed_user_by_id
                management.write_security_event = fixed_writer
                auth_routes.write_security_event = fixed_writer
                yield SimpleNamespace(events=captured)
            finally:
                auth_helpers.open_db, auth_routes.open_db, auth_helpers.get_user_by_id, management.write_security_event, auth_routes.write_security_event = old
                self.fail_after = None
                if old_env is None:
                    os.environ.pop("DIGITRANSX_ENVIRONMENT", None)
                else:
                    os.environ["DIGITRANSX_ENVIRONMENT"] = old_env

        def _authority(self, current):
            return {"current_session_id": current["session_id"], "current_device_id": current["device_id"], "raw_session_token": current["session_raw"], "raw_device_token": current["device_raw"], "raw_access_proof": current["access_raw"]}

        def _app(self):
            app = Flask(__name__); app.config["SECRET_KEY"] = f"{self.tag}-only"; return app

        def _session_ref(self, user, session_id):
            with self._app().app_context():
                return management.session_management_reference(user["id"], session_id)

        def _device_ref(self, user, device_id):
            with self._app().app_context():
                return management.device_management_reference(user["id"], device_id)

        def _call_session(self, user, current, ref, request_id):
            with self._app().app_context(), self._connect() as conn:
                result = management.revoke_session(Db(conn), user=user, management_ref=ref, request_id=request_id, **self._authority(current)); conn.commit(); return result

        def _call_device(self, user, current, ref, request_id):
            with self._app().app_context(), self._connect() as conn:
                result = management.revoke_device(Db(conn), user=user, management_ref=ref, request_id=request_id, **self._authority(current)); conn.commit(); return result

        def _capture_events(self, events):
            for row in events:
                rows.append(EventReceipt(seal, row["event_id"], row["event_name"], row["request_id"], row["idempotency_scope"], row["idempotency_key"], row["fingerprint"], row["subject_user_id"], row["session_ref"], row["device_ref"], row["source"]))

        def _assert_controls_unchanged(self):
            for receipt in control_fingerprints:
                if receipt.seal is not seal or self._fingerprint(receipt.table, receipt.key) != receipt.fingerprint:
                    raise SharedTestSessionDeviceHarnessError("foreign control fingerprint changed")

        def run_management_matrix(self):
            g, user, current = self.graphs, self.graphs["owner"], self.graphs["current"]
            with self._runtime(user) as bound:
                with self._app().app_context(), self._connect() as conn:
                    listed = management.list_active(Db(conn), user["id"], current_session_id=current["session_id"], current_device_id=current["device_id"]); conn.rollback()
                serialized = repr(listed)
                forbidden = (str(g["foreign_current"]["session_id"]), str(g["revoked"]["session_id"]), str(g["expired"]["session_id"]), current["session_raw"], current["device_raw"], current["access_raw"], "token_digest", "access_proof_digest", "ip_address", "user_agent", "provider", "password", "mpin")
                if any(value in serialized for value in forbidden):
                    raise SharedTestSessionDeviceHarnessError("unsafe listing projection")
                if [r["management_ref"] for r in listed["sessions"] if r["is_current"]] != [self._session_ref(user, current["session_id"])]:
                    raise SharedTestSessionDeviceHarnessError("current session marker mismatch")
                if [r["management_ref"] for r in listed["trusted_devices"] if r["is_current"]] != [self._device_ref(user, current["device_id"])]:
                    raise SharedTestSessionDeviceHarnessError("current device marker mismatch")
                stale_ref = self._session_ref(user, g["session_target"]["session_id"])
                forged = (self._session_ref(g["foreign"], g["foreign_current"]["session_id"]), self._device_ref(user, g["device_target"]["device_id"]), session_event_reference(g["session_target"]["session_id"]), "session_" + secrets.token_hex(16))
                if any(self._call_session(user, current, ref, f"{self.tag}.forged.{idx}")["status"] != "not_found" for idx, ref in enumerate(forged)):
                    raise SharedTestSessionDeviceHarnessError("forged reference did not fail closed")
                if self._call_session(user, current, self._session_ref(user, current["session_id"]), f"{self.tag}.current.session")["status"] != "not_found":
                    raise SharedTestSessionDeviceHarnessError("current session target was revocable")
                if self._call_device(user, current, self._device_ref(user, current["device_id"]), f"{self.tag}.current.device")["status"] != "not_found":
                    raise SharedTestSessionDeviceHarnessError("current device target was revocable")
                if self._call_session(user, current, stale_ref, f"{self.tag}.session.success") != {"status": "revoked", "session_count": 1}:
                    raise SharedTestSessionDeviceHarnessError("targeted session revoke mismatch")
                if self._call_session(user, current, stale_ref, f"{self.tag}.session.stale")["status"] != "not_found":
                    raise SharedTestSessionDeviceHarnessError("stale session reference did not fail closed")
                if self._call_device(user, current, self._device_ref(user, g["device_target"]["device_id"]), f"{self.tag}.device.success") != {"status": "revoked", "session_count": 2, "device_count": 1}:
                    raise SharedTestSessionDeviceHarnessError("targeted device revoke mismatch")
                event_count = len(bound.events)
                if self._call_device(user, current, self._device_ref(user, g["revoked"]["device_id"]), f"{self.tag}.revoked")["status"] != "not_found":
                    raise SharedTestSessionDeviceHarnessError("already revoked device changed")
                if self._call_session(user, current, self._session_ref(user, g["expired"]["session_id"]), f"{self.tag}.expired")["status"] != "not_found":
                    raise SharedTestSessionDeviceHarnessError("expired session changed")
                if len(bound.events) != event_count:
                    raise SharedTestSessionDeviceHarnessError("stale controls emitted duplicate evidence")
                self._capture_events(bound.events)
            self._assert_controls_unchanged()
            return {"sessions_listed": 3, "devices_listed": 3, "revoked_sessions": 3, "revoked_devices": 1, "events": 4}

        def run_current_logout_route(self):
            user, current = self.graphs["logout_user"], self.graphs["logout_current"]
            request_hex = hashlib.sha256(f"{self.tag}.logout".encode()).hexdigest()[:32]
            with self._runtime(user) as bound:
                app = self._app(); app.config.update(SESSION_COOKIE_SECURE=False, TESTING=True); app.register_blueprint(auth_routes.auth_blueprint)
                client = app.test_client()
                client.set_cookie(auth_helpers.SESSION_TOKEN_COOKIE_NAME, current["session_raw"])
                client.set_cookie(auth_helpers.DEVICE_COOKIE_NAME, current["device_raw"])
                client.set_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME, current["access_raw"])
                with client.session_transaction() as state:
                    state["csrf_token"] = CSRF["X-CSRF-Token"]
                old_uuid = auth_routes.uuid; auth_routes.uuid = SimpleNamespace(uuid4=lambda: UUID(request_hex))
                try:
                    response = client.post("/auth/logout", headers=CSRF)
                finally:
                    auth_routes.uuid = old_uuid
                if response.status_code != 200 or response.get_json().get("success") is not True:
                    raise SharedTestSessionDeviceHarnessError("canonical logout route failed")
                cookies = response.headers.getlist("Set-Cookie")
                if any(not any(item.startswith(f"{name}=") and "Expires=" in item for item in cookies) for name in (auth_helpers.SESSION_TOKEN_COOKIE_NAME, auth_helpers.DEVICE_COOKIE_NAME, auth_helpers.ACCESS_PROOF_COOKIE_NAME)):
                    raise SharedTestSessionDeviceHarnessError("canonical logout did not clear cookies")
                self._capture_events(bound.events)
            return {"current_logout": "canonical", "events": 2}

        def run_event_failure(self):
            g = self.graphs
            before = self._fingerprint("user_sessions", g["rollback_target"]["session_id"])
            with self._runtime(g["rollback_user"], fail_after=1) as bound:
                try:
                    self._call_device(g["rollback_user"], g["rollback_current"], self._device_ref(g["rollback_user"], g["rollback_target"]["device_id"]), f"{self.tag}.rollback")
                except RuntimeError as error:
                    if str(error) != "synthetic canonical event failure":
                        raise
                else:
                    raise SharedTestSessionDeviceHarnessError("event failure was not visible")
                if bound.events:
                    with self._connect() as conn, conn.cursor() as cur:
                        cur.execute("SELECT event_id FROM public.security_events WHERE request_id=%s", (f"{self.tag}.rollback",))
                        if cur.fetchone() is not None:
                            raise SharedTestSessionDeviceHarnessError("rolled-back event persisted")
                        conn.rollback()
            if before != self._fingerprint("user_sessions", g["rollback_target"]["session_id"]):
                raise SharedTestSessionDeviceHarnessError("event failure left partial mutation")
            return {"rolled_back": True, "events": 0}

        def _delete_exact(self, receipt):
            if receipt.seal is not seal:
                raise SharedTestSessionDeviceHarnessError("cleanup receipt seal mismatch")
            with self._connect() as conn, conn.cursor() as cur:
                if isinstance(receipt, EventReceipt):
                    params = (receipt.event_id, receipt.event_name, receipt.request_id, receipt.scope, receipt.key, receipt.fingerprint, receipt.subject_user_id, receipt.session_ref, receipt.device_ref, receipt.source)
                    cur.execute("SELECT event_id FROM public.security_events WHERE event_id=%s AND event_name=%s AND request_id=%s AND idempotency_scope=%s AND idempotency_key=%s AND fingerprint=%s AND subject_user_id=%s AND session_ref IS NOT DISTINCT FROM %s AND device_ref IS NOT DISTINCT FROM %s AND source=%s FOR UPDATE", params)
                    if cur.fetchone() is None:
                        raise SharedTestSessionDeviceHarnessError("event cleanup ownership mismatch")
                    cur.execute("DELETE FROM public.security_events WHERE event_id=%s AND event_name=%s AND request_id=%s AND idempotency_scope=%s AND idempotency_key=%s AND fingerprint=%s AND subject_user_id=%s AND session_ref IS NOT DISTINCT FROM %s AND device_ref IS NOT DISTINCT FROM %s AND source=%s", params)
                elif isinstance(receipt, SessionReceipt):
                    params = (receipt.session_id, receipt.user_id, receipt.device_id, receipt.token_digest, receipt.access_digest)
                    cur.execute("SELECT session_id FROM public.user_sessions WHERE session_id=%s AND user_id=%s AND trusted_device_id=%s AND token_digest=%s AND access_proof_digest=%s FOR UPDATE", params)
                    if cur.fetchone() is None:
                        raise SharedTestSessionDeviceHarnessError("session cleanup ownership mismatch")
                    cur.execute("DELETE FROM public.user_sessions WHERE session_id=%s AND user_id=%s AND trusted_device_id=%s AND token_digest=%s AND access_proof_digest=%s", params)
                elif isinstance(receipt, DeviceReceipt):
                    params = (receipt.device_id, receipt.user_id, receipt.token_digest)
                    cur.execute("SELECT id FROM public.trusted_devices WHERE id=%s AND user_id=%s AND token_digest=%s FOR UPDATE", params)
                    if cur.fetchone() is None:
                        raise SharedTestSessionDeviceHarnessError("device cleanup ownership mismatch")
                    cur.execute("DELETE FROM public.trusted_devices WHERE id=%s AND user_id=%s AND token_digest=%s", params)
                elif isinstance(receipt, UserReceipt):
                    params = (receipt.user_id, receipt.email, receipt.cnic, receipt.full_name)
                    cur.execute("SELECT id FROM public.users WHERE id=%s AND email=%s AND cnic=%s AND full_name=%s FOR UPDATE", params)
                    if cur.fetchone() is None:
                        raise SharedTestSessionDeviceHarnessError("user cleanup ownership mismatch")
                    cur.execute("DELETE FROM public.users WHERE id=%s AND email=%s AND cnic=%s AND full_name=%s", params)
                else:
                    raise SharedTestSessionDeviceHarnessError("unsupported cleanup receipt")
                if cur.rowcount != 1:
                    raise SharedTestSessionDeviceHarnessError("cleanup rowcount was not exactly one")
                conn.commit()
            self.cleanup_trace.append(type(receipt).__name__)

        def cleanup(self):
            if self.closed:
                return
            self._assert_controls_unchanged()
            for receipt_type in (EventReceipt, SessionReceipt, DeviceReceipt, UserReceipt):
                for receipt in reversed([item for item in rows if isinstance(item, receipt_type)]):
                    self._delete_exact(receipt)
                for receipt in reversed([item for item in controls if isinstance(item, receipt_type)]):
                    self._delete_exact(receipt)
            self.closed = True

        def sanitized_evidence(self):
            return {"closed": self.closed, "cleanup_trace": tuple(self.cleanup_trace), "external_provider_calls": 0}

    return Ledger()


def _run_probe_matrix(url):
    before = shared_test_state_snapshot(url)
    ledger = SharedTestSessionDeviceLedger(url)
    probe_error = cleanup_error = None
    try:
        ledger.setup_graphs()
        probes = {"management": ledger.run_management_matrix(), "current_logout": ledger.run_current_logout_route(), "event_failure": ledger.run_event_failure()}
        during = shared_test_state_snapshot(url)
    except Exception as error:
        probe_error = error; during = before
    finally:
        try:
            ledger.cleanup()
        except Exception as error:
            cleanup_error = error
    if probe_error is not None and cleanup_error is not None:
        raise ProbeAndCleanupError(probe_error, cleanup_error) from probe_error
    if cleanup_error is not None:
        raise cleanup_error
    if probe_error is not None:
        raise probe_error
    after = shared_test_state_snapshot(url)
    if before != after:
        changed = sorted(table for table in before if before[table] != after[table])
        raise SharedTestSessionDeviceHarnessError("exact post-probe reconciliation failed: " + ",".join(changed))
    return {"probes": probes, "before_counts": {t: v["count"] for t, v in before.items()}, "created_counts": {t: during[t]["count"] - before[t]["count"] for t in before}, "after_counts": {t: v["count"] for t, v in after.items()}, "fingerprints_equal": {t: before[t]["fingerprint"] == after[t]["fingerprint"] for t in before}, "external_provider_calls": 0, "cleanup": ledger.sanitized_evidence()}


def run_authorized_session_device_probe_matrix(environ=None):
    return _run_probe_matrix(require_authorized_shared_test_url(environ))
