"""Closed shared-TEST harness for Phase 1B-2C4 logout-all verification."""

from contextlib import contextmanager
from dataclasses import dataclass
import base64
import hashlib
import json
import os
import secrets
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from flask import Flask
import psycopg2
from psycopg2.extras import RealDictCursor

from auth import logout_all_service, mpin_service, routes as auth_routes, step_up_service
import auth.helpers as auth_helpers
import events.writer as event_writer
from auth.session_service import session_event_reference, trusted_device_reference
from events.writer import write_security_event as canonical_write_security_event
from shared.db import Db


ACTIVATION_ENV = "DTX_SHARED_TEST_HARNESS"
PROJECT_ENV = "DTX_SHARED_TEST_PROJECT_REF"
URL_ENV = "SUPABASE_DB_URL"
EXPECTED_PROJECT_REF = "fysupkvuvhvtowbfgoev"
EXPECTED_HOST = "aws-0-ap-northeast-1.pooler.supabase.com"
PEPPER = base64.urlsafe_b64encode(b"L" * 32).decode("ascii")
CSRF = {"X-CSRF-Token": "logout-all-harness-csrf"}
PASSWORD = "logout-all-harness-password"


class SharedTestLogoutAllHarnessError(RuntimeError):
    pass


class ProbeAndCleanupError(SharedTestLogoutAllHarnessError):
    def __init__(self, probe_error, cleanup_error):
        super().__init__(
            f"probe failed with {type(probe_error).__name__}; "
            f"cleanup failed with {type(cleanup_error).__name__}"
        )
        self.probe_error = probe_error
        self.cleanup_error = cleanup_error


def require_authorized_shared_test_url(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get(ACTIVATION_ENV) != "1":
        raise SharedTestLogoutAllHarnessError("shared TEST harness is not enabled")
    if environ.get(PROJECT_ENV) != EXPECTED_PROJECT_REF:
        raise SharedTestLogoutAllHarnessError("shared TEST project is not authorized")
    raw_url = environ.get(URL_ENV, "").strip()
    if not raw_url:
        raise SharedTestLogoutAllHarnessError("shared TEST database URL is required")
    parsed = urlsplit(raw_url)
    if (parsed.hostname or "").lower() != EXPECTED_HOST:
        raise SharedTestLogoutAllHarnessError("target is not the authorized pooler")
    if parsed.path.rstrip("/") != "/postgres":
        raise SharedTestLogoutAllHarnessError("shared TEST database must be postgres")
    if parsed.username not in {"postgres", f"postgres.{EXPECTED_PROJECT_REF}"}:
        raise SharedTestLogoutAllHarnessError("shared TEST role is not authorized")
    return raw_url


_SNAPSHOT_QUERIES = (
    ("users", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.users t"),
    ("trusted_devices", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.trusted_devices t"),
    ("user_sessions", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.user_sessions t"),
    ("mpin_credentials", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.mpin_credentials t"),
    ("mpin_step_up_authorizations", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.mpin_step_up_authorizations t"),
    ("security_events", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.security_events t"),
)


def _state_snapshot(url):
    result = {}
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        for table, query in _SNAPSHOT_QUERIES:
            cursor.execute(query)
            count, fingerprint = cursor.fetchone()
            result[table] = (int(count), fingerprint)
        conn.rollback()
    return result


def _assert_request_namespace_clear(cursor, request_id):
    cursor.execute(
        "SELECT event_id FROM public.security_events WHERE request_id=%s",
        (request_id,),
    )
    if cursor.fetchone() is not None:
        raise SharedTestLogoutAllHarnessError(
            "runtime event correlation collision before mutation"
        )


def SharedTestLogoutAllLedger(url):
    """Build a sealed ledger exposing only fixed Phase 1B-2C4 operations."""

    seal = object()
    artifacts = ()
    control_rows = ()
    control_fingerprints = ()

    @dataclass(frozen=True)
    class UserReceipt:
        seal: object
        user_id: object
        email: str
        cnic: str
        full_name: str

    @dataclass(frozen=True)
    class DeviceReceipt:
        seal: object
        device_id: object
        user_id: object
        token_digest: bytes

    @dataclass(frozen=True)
    class SessionReceipt:
        seal: object
        session_id: object
        user_id: object
        device_id: object
        token_digest: bytes
        access_digest: bytes | None

    @dataclass(frozen=True)
    class CredentialReceipt:
        seal: object
        user_id: object
        salt: bytes
        generation: int

    @dataclass(frozen=True)
    class AuthorizationReceipt:
        seal: object
        authorization_id: object
        user_id: object
        session_id: object
        device_id: object
        generation: int
        proof_digest: bytes
        request_fingerprint: bytes

    @dataclass(frozen=True)
    class EventReceipt:
        seal: object
        event_id: object
        event_name: str
        request_id: str
        scope: str
        key: str
        fingerprint: str
        subject_user_id: object
        session_ref: str | None
        device_ref: str | None
        source: str

    @dataclass(frozen=True)
    class FingerprintReceipt:
        seal: object
        table: str
        key: object
        fingerprint: str

    def mint(receipt, *, control=False):
        nonlocal artifacts, control_rows
        if receipt.seal is not seal:
            raise SharedTestLogoutAllHarnessError("unsealed ownership receipt")
        if control:
            control_rows += (receipt,)
        else:
            artifacts += (receipt,)

    class Ledger:
        def __init__(self):
            self._url = url
            self._tag = f"dtx_shared_logout_all_{secrets.token_hex(8)}"
            self._closed = False
            self._graphs = {}
            self._provider_calls = 0
            self._cleanup_trace = []

        def __enter__(self):
            if self._closed:
                raise SharedTestLogoutAllHarnessError("closed ledger cannot reopen")
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            try:
                self.cleanup()
            except Exception as cleanup_error:
                if exc_value is not None:
                    raise ProbeAndCleanupError(exc_value, cleanup_error) from exc_value
                raise
            return False

        def _connect(self):
            return psycopg2.connect(self._url)

        def _ensure_open(self):
            if self._closed:
                raise SharedTestLogoutAllHarnessError("fixture ledger is closed")

        def _fingerprint(self, table, key):
            fixed = {
                "trusted_devices": "SELECT md5(row_to_json(t)::text) FROM public.trusted_devices t WHERE id=%s",
                "user_sessions": "SELECT md5(row_to_json(t)::text) FROM public.user_sessions t WHERE session_id=%s",
            }
            with self._connect() as conn, conn.cursor() as cursor:
                cursor.execute(fixed[table], (key,))
                row = cursor.fetchone()
                conn.rollback()
            if not row:
                raise SharedTestLogoutAllHarnessError("control row disappeared")
            return row[0]

        def _create_user(self, suffix, legacy_role, app_role, *, control=False):
            self._ensure_open()
            full_name = f"{self._tag}_{suffix}"
            email = f"{full_name}.{secrets.token_hex(4)}@example.invalid"
            cnic = str(int.from_bytes(secrets.token_bytes(7), "big"))[:13].zfill(13)
            with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT id FROM public.users WHERE email=%s OR cnic=%s OR full_name=%s",
                    (email, cnic, full_name),
                )
                if cursor.fetchone() is not None:
                    raise SharedTestLogoutAllHarnessError("user identity collision")
                cursor.execute(
                    "INSERT INTO public.users(full_name,email,cnic,role,legacy_role) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                    (full_name, email, cnic, app_role, legacy_role),
                )
                user_id = cursor.fetchone()["id"]
                cursor.execute(
                    "SELECT id FROM public.users WHERE id=%s AND email=%s AND cnic=%s AND full_name=%s AND role=%s AND legacy_role=%s",
                    (user_id, email, cnic, full_name, app_role, legacy_role),
                )
                if cursor.fetchone() is None:
                    raise SharedTestLogoutAllHarnessError("created user verification failed")
                conn.commit()
            mint(UserReceipt(seal, user_id, email, cnic, full_name), control=control)
            return {"id": user_id, "email": email, "auth_id": None, "role": legacy_role}

        def _create_chain(self, user, state="active", *, control=False):
            self._ensure_open()
            raw_device = secrets.token_urlsafe(32)
            raw_session = secrets.token_urlsafe(32)
            raw_access = secrets.token_urlsafe(32)
            device_digest = hashlib.sha256(raw_device.encode()).digest()
            session_digest = hashlib.sha256(raw_session.encode()).digest()
            access_digest = hashlib.sha256(raw_access.encode()).digest()
            with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT id FROM public.trusted_devices WHERE token_digest=%s OR previous_token_digest=%s",
                    (device_digest, device_digest),
                )
                if cursor.fetchone() is not None:
                    raise SharedTestLogoutAllHarnessError("device identity collision")
                if state == "expired":
                    cursor.execute(
                        "INSERT INTO public.trusted_devices(token_digest,user_id,created_at,last_used_at,expires_at) "
                        "VALUES(%s,%s,now()-interval '40 days',now()-interval '39 days',now()-interval '10 days') RETURNING id",
                        (device_digest, user["id"]),
                    )
                elif state == "revoked":
                    cursor.execute(
                        "INSERT INTO public.trusted_devices(token_digest,user_id,expires_at,revoked_at) "
                        "VALUES(%s,%s,now()+interval '30 days',now()) RETURNING id",
                        (device_digest, user["id"]),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO public.trusted_devices(token_digest,user_id,expires_at) "
                        "VALUES(%s,%s,now()+interval '30 days') RETURNING id",
                        (device_digest, user["id"]),
                    )
                device_id = cursor.fetchone()["id"]
                cursor.execute(
                    "SELECT session_id FROM public.user_sessions WHERE token_digest=%s OR access_proof_digest=%s",
                    (session_digest, access_digest),
                )
                if cursor.fetchone() is not None:
                    raise SharedTestLogoutAllHarnessError("session identity collision")
                if state == "expired":
                    cursor.execute(
                        "INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,created_at,authenticated_at,last_genuine_activity_at,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at,updated_at) "
                        "VALUES(%s,%s,%s,now()-interval '10 days',now()-interval '10 days',now()-interval '9 days',now()-interval '1 day',now()+interval '1 day',%s,now()+interval '1 hour',now()) RETURNING session_id",
                        (user["id"], session_digest, device_id, access_digest),
                    )
                elif state == "revoked":
                    cursor.execute(
                        "INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at,revoked_at,revocation_reason) "
                        "VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',%s,now()+interval '8 hours',now(),'logout') RETURNING session_id",
                        (user["id"], session_digest, device_id, access_digest),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at,access_proof_digest,access_proof_expires_at) "
                        "VALUES(%s,%s,%s,now()+interval '7 days',now()+interval '30 days',%s,now()+interval '8 hours') RETURNING session_id",
                        (user["id"], session_digest, device_id, access_digest),
                    )
                session_id = cursor.fetchone()["session_id"]
                cursor.execute(
                    "SELECT session_id FROM public.user_sessions WHERE session_id=%s AND user_id=%s AND trusted_device_id=%s AND token_digest=%s AND access_proof_digest=%s",
                    (session_id, user["id"], device_id, session_digest, access_digest),
                )
                if cursor.fetchone() is None:
                    raise SharedTestLogoutAllHarnessError("created chain verification failed")
                conn.commit()
            mint(DeviceReceipt(seal, device_id, user["id"], device_digest), control=control)
            mint(SessionReceipt(seal, session_id, user["id"], device_id, session_digest, access_digest), control=control)
            if control:
                nonlocal control_fingerprints
                control_fingerprints += (
                    FingerprintReceipt(seal, "trusted_devices", device_id, self._fingerprint("trusted_devices", device_id)),
                    FingerprintReceipt(seal, "user_sessions", session_id, self._fingerprint("user_sessions", session_id)),
                )
            return {
                "device_id": device_id, "session_id": session_id,
                "device_raw": raw_device, "session_raw": raw_session,
                "access_raw": raw_access,
            }

        def _create_credential(self, user):
            salt, verifier = mpin_service.build_credential("1234")
            with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT user_id FROM public.mpin_credentials WHERE user_id=%s OR salt=%s",
                    (user["id"], salt),
                )
                if cursor.fetchone() is not None:
                    raise SharedTestLogoutAllHarnessError("credential identity collision")
                cursor.execute(
                    "INSERT INTO public.mpin_credentials(user_id,verifier,salt,kdf_version) VALUES(%s,%s,%s,1) RETURNING credential_generation",
                    (user["id"], verifier, salt),
                )
                generation = cursor.fetchone()["credential_generation"]
                cursor.execute(
                    "SELECT user_id FROM public.mpin_credentials WHERE user_id=%s AND salt=%s AND credential_generation=%s",
                    (user["id"], salt, generation),
                )
                if cursor.fetchone() is None:
                    raise SharedTestLogoutAllHarnessError("credential verification failed")
                conn.commit()
            mint(CredentialReceipt(seal, user["id"], salt, generation))
            return generation

        def _issue_authorization(self, graph):
            descriptor = logout_all_service.LOGOUT_ALL_DESCRIPTOR
            raw_proof = secrets.token_urlsafe(step_up_service.PROOF_BYTES)
            authorization_id = uuid4()
            proof_digest = hashlib.sha256(raw_proof.encode("ascii")).digest()
            with self._connect() as conn:
                db = Db(conn)
                if db.execute(
                    "SELECT authorization_id FROM public.mpin_step_up_authorizations WHERE authorization_id=%s OR proof_digest=%s OR "
                    "(user_id=%s AND session_id=%s AND action_key='security.logout_all' AND resource_type='account_security' "
                    "AND resource_id=1 AND request_fingerprint=%s AND state='available')",
                    (str(authorization_id), proof_digest, graph["user"]["id"], graph["current"]["session_id"], descriptor["request_fingerprint"]),
                ).fetchone() is not None:
                    raise SharedTestLogoutAllHarnessError("authorization correlation collision")
                with patch.object(step_up_service, "uuid", SimpleNamespace(uuid4=lambda: authorization_id)), \
                        patch.object(step_up_service, "secrets", SimpleNamespace(token_urlsafe=lambda _size: raw_proof)):
                    issued = step_up_service.issue_authorization(
                        db, user_id=graph["user"]["id"],
                        session_id=graph["current"]["session_id"],
                        trusted_device_id=graph["current"]["device_id"],
                        credential_generation=graph["generation"], descriptor=descriptor,
                    )
                if not issued:
                    raise SharedTestLogoutAllHarnessError("authorization issuance failed")
                if str(issued["authorization_id"]) != str(authorization_id) or issued["proof"] != raw_proof:
                    raise SharedTestLogoutAllHarnessError("authorization identity mismatch")
                row = db.execute(
                    "SELECT authorization_id,proof_digest,request_fingerprint FROM public.mpin_step_up_authorizations "
                    "WHERE authorization_id=%s AND user_id=%s AND session_id=%s "
                    "AND trusted_device_id=%s AND credential_generation=%s AND proof_digest=%s "
                    "AND action_key='security.logout_all' AND resource_type='account_security' "
                    "AND resource_id=1 AND request_fingerprint=%s",
                    (issued["authorization_id"], graph["user"]["id"], graph["current"]["session_id"],
                     graph["current"]["device_id"], graph["generation"], proof_digest,
                     descriptor["request_fingerprint"]),
                ).fetchone()
                if row is None:
                    raise SharedTestLogoutAllHarnessError("authorization verification failed")
                conn.commit()
            receipt = AuthorizationReceipt(
                seal, issued["authorization_id"], graph["user"]["id"],
                graph["current"]["session_id"], graph["current"]["device_id"],
                graph["generation"], proof_digest, bytes(row["request_fingerprint"]),
            )
            mint(receipt)
            return {"proof": issued["proof"], "receipt": receipt}

        def setup_mpin_graph(self):
            self._ensure_open()
            if "mpin" in self._graphs:
                raise SharedTestLogoutAllHarnessError("MPIN graph already exists")
            user = self._create_user("mpin_subject", "service_seeker", "customer")
            current = self._create_chain(user)
            extra = self._create_chain(user)
            foreign_user = self._create_user("foreign_control", "platform_admin", "admin", control=True)
            graph = {
                "user": user, "current": current, "extra": extra,
                "foreign": self._create_chain(foreign_user, control=True),
                "revoked": self._create_chain(user, "revoked", control=True),
                "expired": self._create_chain(user, "expired", control=True),
                "generation": self._create_credential(user),
            }
            graph["authorization"] = self._issue_authorization(graph)
            self._graphs["mpin"] = graph

        def setup_password_graph(self):
            self._ensure_open()
            user = self._create_user("password_subject", "platform_admin", "admin")
            self._graphs["password"] = {
                "user": user, "current": self._create_chain(user),
                "extra": self._create_chain(user),
            }

        def setup_rollback_graph(self):
            self._ensure_open()
            user = self._create_user("rollback_subject", "platform_admin", "admin")
            self._graphs["rollback"] = {
                "user": user, "current": self._create_chain(user),
                "extra": self._create_chain(user),
            }

        @contextmanager
        def _bound_runtime(self, graph, *, fail_event_number=None):
            self._ensure_open()
            active = {"count": 0}
            captured = []
            writes = {"count": 0}

            @contextmanager
            def fixed_open_db():
                conn = self._connect()
                active["count"] += 1
                try:
                    db = Db(conn)
                    yield db
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    active["count"] -= 1
                    conn.close()

            def fixed_password_verifier(email, password, *, raise_provider_errors):
                if active["count"] != 0:
                    raise SharedTestLogoutAllHarnessError("provider verification ran inside a database transaction")
                if email != graph["user"]["email"] or password != PASSWORD or raise_provider_errors is not True:
                    raise SharedTestLogoutAllHarnessError("unexpected deterministic password invocation")
                self._provider_calls += 1
                return True

            def fixed_event_writer(*args, **kwargs):
                writes["count"] += 1
                if writes["count"] == fail_event_number:
                    raise RuntimeError("synthetic canonical event failure")
                result = canonical_write_security_event(*args, **kwargs)
                if result.replayed:
                    raise SharedTestLogoutAllHarnessError("unexpected event replay")
                captured.append(dict(result.event))
                return result

            with patch.object(auth_helpers, "open_db", fixed_open_db), \
                    patch.object(auth_routes, "open_db", fixed_open_db), \
                    patch.object(logout_all_service, "open_db", fixed_open_db), \
                    patch.object(logout_all_service, "supabase_verify_password", fixed_password_verifier), \
                    patch.object(logout_all_service, "write_security_event", fixed_event_writer), \
                    patch.object(event_writer, "write_security_event", fixed_event_writer):
                yield SimpleNamespace(events=captured, writes=writes, active=active)

        def _call_service(self, graph, *, request_id, proof="", password=None):
            with self._connect() as conn, conn.cursor() as cursor:
                _assert_request_namespace_clear(cursor, request_id)
                conn.rollback()
            return logout_all_service.logout_all(
                presented_user=graph["user"],
                presented_session={"session_id": graph["current"]["session_id"]},
                raw_session_token=graph["current"]["session_raw"],
                raw_device_token=graph["current"]["device_raw"],
                raw_access_proof=graph["current"]["access_raw"],
                raw_step_up_proof=proof,
                password=password,
                request_id=request_id,
            )

        def _assert_controls_unchanged(self):
            for receipt in control_fingerprints:
                if receipt.seal is not seal or self._fingerprint(receipt.table, receipt.key) != receipt.fingerprint:
                    raise SharedTestLogoutAllHarnessError("control fingerprint changed")

        def _capture_events(self, rows, graph, request_id, *, mpin):
            expected = {
                "security.session.revoked": 2,
                "security.trusted_device.removed": 2,
                "security.logout.completed": 1,
            }
            if mpin:
                expected["security.mpin.step_up_consumed"] = 1
            actual = {}
            for row in rows:
                actual[row["event_name"]] = actual.get(row["event_name"], 0) + 1
            if actual != expected:
                raise SharedTestLogoutAllHarnessError("canonical event cardinality mismatch")
            valid_session_refs = {
                session_event_reference(graph["current"]["session_id"]),
                session_event_reference(graph["extra"]["session_id"]),
            }
            valid_device_refs = {
                trusted_device_reference(graph["current"]["device_id"]),
                trusted_device_reference(graph["extra"]["device_id"]),
            }
            for row in rows:
                name = row["event_name"]
                metadata = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])
                if row["request_id"] != request_id or row["subject_user_id"] != graph["user"]["id"]:
                    raise SharedTestLogoutAllHarnessError("event ownership mismatch")
                if name == "security.session.revoked" and (row["session_ref"] not in valid_session_refs or metadata.get("result_code") != "logout_all"):
                    raise SharedTestLogoutAllHarnessError("session event contract mismatch")
                if name == "security.trusted_device.removed" and (row["device_ref"] not in valid_device_refs or metadata.get("result_code") != "logout_all"):
                    raise SharedTestLogoutAllHarnessError("device event contract mismatch")
                if name == "security.logout.completed" and metadata.get("result_code") != "completed":
                    raise SharedTestLogoutAllHarnessError("logout event contract mismatch")
                with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT event_id,event_name,request_id,idempotency_scope,idempotency_key,fingerprint,subject_user_id,session_ref,device_ref,source FROM public.security_events "
                        "WHERE event_id=%s AND event_name=%s AND request_id=%s AND idempotency_scope=%s AND idempotency_key=%s AND fingerprint=%s AND subject_user_id=%s AND source=%s",
                        (row["event_id"], name, request_id, row["idempotency_scope"], row["idempotency_key"], row["fingerprint"], graph["user"]["id"], row["source"]),
                    )
                    verified = cursor.fetchone()
                    conn.rollback()
                if verified is None:
                    raise SharedTestLogoutAllHarnessError("event exact verification failed")
                mint(EventReceipt(seal, row["event_id"], name, request_id, row["idempotency_scope"], row["idempotency_key"], row["fingerprint"], graph["user"]["id"], row["session_ref"], row["device_ref"], row["source"]))

        def _assert_revoked(self, graph):
            with self._connect() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM public.user_sessions WHERE user_id=%s AND session_id IN (%s,%s) AND revoked_at IS NOT NULL AND revocation_reason='logout_all'",
                    (graph["user"]["id"], graph["current"]["session_id"], graph["extra"]["session_id"]),
                )
                sessions = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT count(*) FROM public.trusted_devices WHERE user_id=%s AND id IN (%s,%s) AND revoked_at IS NOT NULL",
                    (graph["user"]["id"], graph["current"]["device_id"], graph["extra"]["device_id"]),
                )
                devices = cursor.fetchone()[0]
                conn.rollback()
            if (sessions, devices) != (2, 2):
                raise SharedTestLogoutAllHarnessError("logout-all population mismatch")
            return sessions, devices

        def _rotate_credential(self, graph):
            nonlocal artifacts
            old = next(item for item in artifacts if isinstance(item, CredentialReceipt) and item.user_id == graph["user"]["id"])
            with self._connect() as conn:
                db = Db(conn)
                row = db.execute(
                    "SELECT user_id FROM public.mpin_credentials WHERE user_id=%s AND salt=%s AND credential_generation=%s FOR UPDATE",
                    (old.user_id, old.salt, old.generation),
                ).fetchone()
                if row is None or not mpin_service.replace(db, old.user_id, "4321"):
                    raise SharedTestLogoutAllHarnessError("credential rotation failed")
                current = db.execute(
                    "SELECT salt,credential_generation FROM public.mpin_credentials WHERE user_id=%s",
                    (old.user_id,),
                ).fetchone()
                conn.commit()
            replacement = CredentialReceipt(seal, old.user_id, bytes(current["salt"]), current["credential_generation"])
            artifacts = tuple(replacement if item is old else item for item in artifacts)
            graph["generation"] = replacement.generation

        def run_mpin_matrix(self):
            graph = self._graphs["mpin"]
            base = f"logout.mpin.{self._tag}"
            with self._bound_runtime(graph) as bound:
                wrong = self._call_service(graph, request_id=f"{base}.wrong", proof="invalid-proof")
                if wrong.status != "mpin_required":
                    raise SharedTestLogoutAllHarnessError("stale proof did not fail closed")
                mismatch = logout_all_service.logout_all(
                    presented_user=graph["user"], presented_session={"session_id": graph["extra"]["session_id"]},
                    raw_session_token=graph["extra"]["session_raw"], raw_device_token=graph["extra"]["device_raw"],
                    raw_access_proof=graph["extra"]["access_raw"], raw_step_up_proof=graph["authorization"]["proof"],
                    password=None, request_id=f"{base}.mismatch",
                )
                if mismatch.status != "mpin_required":
                    raise SharedTestLogoutAllHarnessError("mismatched authorization did not fail closed")
                with self._connect() as conn, conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE public.mpin_step_up_authorizations SET issued_at=now()-interval '4 minutes',expires_at=now()-interval '1 minute' "
                        "WHERE authorization_id=%s AND user_id=%s AND proof_digest=%s",
                        (graph["authorization"]["receipt"].authorization_id, graph["user"]["id"], graph["authorization"]["receipt"].proof_digest),
                    )
                    if cursor.rowcount != 1:
                        raise SharedTestLogoutAllHarnessError("authorization expiry ownership mismatch")
                    conn.commit()
                expired = self._call_service(graph, request_id=f"{base}.expired", proof=graph["authorization"]["proof"])
                if expired.status != "mpin_required":
                    raise SharedTestLogoutAllHarnessError("expired authorization did not fail closed")
                rotated_proof = self._issue_authorization(graph)
                self._rotate_credential(graph)
                rotated = self._call_service(graph, request_id=f"{base}.rotated", proof=rotated_proof["proof"])
                if rotated.status != "mpin_required":
                    raise SharedTestLogoutAllHarnessError("rotated credential authorization did not fail closed")
                graph["authorization"] = self._issue_authorization(graph)
                request_id = f"{base}.success"
                result = self._call_service(graph, request_id=request_id, proof=graph["authorization"]["proof"])
                if (result.status, result.session_count, result.trusted_device_count) != ("success", 2, 2):
                    raise SharedTestLogoutAllHarnessError("MPIN logout-all result mismatch")
                counts = self._assert_revoked(graph)
                self._capture_events(bound.events, graph, request_id, mpin=True)
                before_replay = len(bound.events)
                replay = self._call_service(graph, request_id=f"{base}.replay", proof=graph["authorization"]["proof"])
                if replay.status != "authentication_required" or len(bound.events) != before_replay:
                    raise SharedTestLogoutAllHarnessError("replay was not inert")
            self._assert_controls_unchanged()
            return {"sessions": counts[0], "devices": counts[1], "events": 6}

        def run_password_route(self):
            graph = self._graphs["password"]
            request_hex = hashlib.sha256(f"{self._tag}.route".encode()).hexdigest()[:32]
            request_id = f"auth.logout_all.{request_hex}"
            route_errors = []
            canonical_logout_all = logout_all_service.logout_all

            def observed_logout_all(**kwargs):
                try:
                    return canonical_logout_all(**kwargs)
                except Exception as error:
                    route_errors.append(error)
                    raise

            with self._connect() as conn, conn.cursor() as cursor:
                _assert_request_namespace_clear(cursor, request_id)
                conn.rollback()
            with self._bound_runtime(graph) as bound, \
                    patch.object(auth_routes, "uuid", SimpleNamespace(uuid4=lambda: UUID(request_hex))), \
                    patch.object(auth_routes.logout_all_service, "logout_all", observed_logout_all):
                app = Flask(__name__)
                app.config.update(SECRET_KEY=f"{self._tag}-only", SESSION_COOKIE_SECURE=False, TESTING=True)
                app.register_blueprint(auth_routes.auth_blueprint)
                client = app.test_client()
                for name, value in (
                    (auth_helpers.DEVICE_COOKIE_NAME, graph["current"]["device_raw"]),
                    (auth_helpers.SESSION_TOKEN_COOKIE_NAME, graph["current"]["session_raw"]),
                    (auth_helpers.ACCESS_PROOF_COOKIE_NAME, graph["current"]["access_raw"]),
                ):
                    client.set_cookie(name, value)
                with client.session_transaction() as state:
                    state["csrf_token"] = CSRF["X-CSRF-Token"]
                challenged = client.post("/auth/logout-all", json={}, headers=CSRF)
                if challenged.status_code != 428 or challenged.get_json().get("code") != "current_password_required" or self._provider_calls != 0:
                    raise SharedTestLogoutAllHarnessError("password challenge contract mismatch")
                response = client.post("/auth/logout-all", json={"password": PASSWORD}, headers=CSRF)
                if response.status_code != 200 or response.get_json() != {"success": True, "session_count": 2, "trusted_device_count": 2}:
                    error = SharedTestLogoutAllHarnessError("password route result mismatch")
                    if route_errors:
                        raise error from route_errors[0]
                    raise error
                cookies = response.headers.getlist("Set-Cookie")
                required = (auth_helpers.SESSION_TOKEN_COOKIE_NAME, auth_helpers.DEVICE_COOKIE_NAME, auth_helpers.ACCESS_PROOF_COOKIE_NAME, app.config.get("SESSION_COOKIE_NAME", "session"))
                if any(not any(item.startswith(f"{name}=") and "Expires=" in item for item in cookies) for name in required):
                    raise SharedTestLogoutAllHarnessError("cookie clearing contract mismatch")
                if self._provider_calls != 1:
                    raise SharedTestLogoutAllHarnessError("deterministic verifier call mismatch")
                counts = self._assert_revoked(graph)
                self._capture_events(bound.events, graph, request_id, mpin=False)
            return {"sessions": counts[0], "devices": counts[1], "events": 5, "deterministic_verifier_calls": 1}

        def run_event_failure(self):
            graph = self._graphs["rollback"]
            before = {item.session_id: self._fingerprint("user_sessions", item.session_id) for item in artifacts if isinstance(item, SessionReceipt) and item.user_id == graph["user"]["id"]}
            request_id = f"logout.rollback.{self._tag}"
            with self._bound_runtime(graph, fail_event_number=2) as bound:
                try:
                    self._call_service(graph, request_id=request_id, password=PASSWORD)
                except RuntimeError as error:
                    if str(error) != "synthetic canonical event failure":
                        raise
                else:
                    raise SharedTestLogoutAllHarnessError("event failure was not raised")
                if bound.events:
                    with self._connect() as conn, conn.cursor() as cursor:
                        cursor.execute("SELECT event_id FROM public.security_events WHERE request_id=%s", (request_id,))
                        if cursor.fetchone() is not None:
                            raise SharedTestLogoutAllHarnessError("rolled-back event persisted")
                        conn.rollback()
            after = {key: self._fingerprint("user_sessions", key) for key in before}
            if before != after:
                raise SharedTestLogoutAllHarnessError("event failure partially revoked sessions")
            return {"rolled_back": True, "events": 0}

        def _delete_exact(self, receipt):
            if receipt.seal is not seal:
                raise SharedTestLogoutAllHarnessError("cleanup receipt seal mismatch")
            with self._connect() as conn, conn.cursor() as cursor:
                if isinstance(receipt, EventReceipt):
                    params = (receipt.event_id, receipt.event_name, receipt.request_id, receipt.scope, receipt.key, receipt.fingerprint, receipt.subject_user_id, receipt.session_ref, receipt.device_ref, receipt.source)
                    cursor.execute(
                        "SELECT event_id FROM public.security_events WHERE event_id=%s AND event_name=%s AND request_id=%s AND idempotency_scope=%s AND idempotency_key=%s AND fingerprint=%s AND subject_user_id=%s AND session_ref IS NOT DISTINCT FROM %s AND device_ref IS NOT DISTINCT FROM %s AND source=%s FOR UPDATE",
                        params,
                    )
                    if cursor.fetchone() is None:
                        raise SharedTestLogoutAllHarnessError("event cleanup ownership mismatch")
                    cursor.execute(
                        "DELETE FROM public.security_events WHERE event_id=%s AND event_name=%s AND request_id=%s AND idempotency_scope=%s AND idempotency_key=%s AND fingerprint=%s AND subject_user_id=%s AND session_ref IS NOT DISTINCT FROM %s AND device_ref IS NOT DISTINCT FROM %s AND source=%s",
                        params,
                    )
                elif isinstance(receipt, AuthorizationReceipt):
                    params = (receipt.authorization_id, receipt.user_id, receipt.session_id, receipt.device_id, receipt.generation, receipt.proof_digest, receipt.request_fingerprint)
                    cursor.execute(
                        "SELECT authorization_id FROM public.mpin_step_up_authorizations WHERE authorization_id=%s AND user_id=%s AND session_id=%s AND trusted_device_id=%s AND credential_generation=%s AND proof_digest=%s AND action_key='security.logout_all' AND resource_type='account_security' AND resource_id=1 AND request_fingerprint=%s FOR UPDATE",
                        params,
                    )
                    if cursor.fetchone() is None:
                        raise SharedTestLogoutAllHarnessError("authorization cleanup ownership mismatch")
                    cursor.execute(
                        "DELETE FROM public.mpin_step_up_authorizations WHERE authorization_id=%s AND user_id=%s AND session_id=%s AND trusted_device_id=%s AND credential_generation=%s AND proof_digest=%s AND action_key='security.logout_all' AND resource_type='account_security' AND resource_id=1 AND request_fingerprint=%s",
                        params,
                    )
                elif isinstance(receipt, SessionReceipt):
                    params = (receipt.session_id, receipt.user_id, receipt.device_id, receipt.token_digest, receipt.access_digest)
                    cursor.execute(
                        "SELECT session_id FROM public.user_sessions WHERE session_id=%s AND user_id=%s AND trusted_device_id=%s AND token_digest=%s AND access_proof_digest IS NOT DISTINCT FROM %s FOR UPDATE",
                        params,
                    )
                    if cursor.fetchone() is None:
                        raise SharedTestLogoutAllHarnessError("session cleanup ownership mismatch")
                    cursor.execute(
                        "DELETE FROM public.user_sessions WHERE session_id=%s AND user_id=%s AND trusted_device_id=%s AND token_digest=%s AND access_proof_digest IS NOT DISTINCT FROM %s",
                        params,
                    )
                elif isinstance(receipt, DeviceReceipt):
                    params = (receipt.device_id, receipt.user_id, receipt.token_digest)
                    cursor.execute(
                        "SELECT id FROM public.trusted_devices WHERE id=%s AND user_id=%s AND token_digest=%s FOR UPDATE",
                        params,
                    )
                    if cursor.fetchone() is None:
                        raise SharedTestLogoutAllHarnessError("device cleanup ownership mismatch")
                    cursor.execute(
                        "DELETE FROM public.trusted_devices WHERE id=%s AND user_id=%s AND token_digest=%s",
                        params,
                    )
                elif isinstance(receipt, CredentialReceipt):
                    params = (receipt.user_id, receipt.salt, receipt.generation)
                    cursor.execute(
                        "SELECT user_id FROM public.mpin_credentials WHERE user_id=%s AND salt=%s AND credential_generation=%s FOR UPDATE",
                        params,
                    )
                    if cursor.fetchone() is None:
                        raise SharedTestLogoutAllHarnessError("credential cleanup ownership mismatch")
                    cursor.execute(
                        "DELETE FROM public.mpin_credentials WHERE user_id=%s AND salt=%s AND credential_generation=%s",
                        params,
                    )
                elif isinstance(receipt, UserReceipt):
                    params = (receipt.user_id, receipt.email, receipt.cnic, receipt.full_name)
                    cursor.execute(
                        "SELECT id FROM public.users WHERE id=%s AND email=%s AND cnic=%s AND full_name=%s FOR UPDATE",
                        params,
                    )
                    if cursor.fetchone() is None:
                        raise SharedTestLogoutAllHarnessError("user cleanup ownership mismatch")
                    cursor.execute(
                        "DELETE FROM public.users WHERE id=%s AND email=%s AND cnic=%s AND full_name=%s",
                        params,
                    )
                else:
                    raise SharedTestLogoutAllHarnessError("unsupported cleanup receipt")
                if cursor.rowcount != 1:
                    raise SharedTestLogoutAllHarnessError("cleanup rowcount was not exactly one")
                conn.commit()
            self._cleanup_trace.append(type(receipt).__name__)

        def cleanup(self):
            if self._closed:
                return
            self._assert_controls_unchanged()
            dependency_order = (EventReceipt, AuthorizationReceipt, SessionReceipt, DeviceReceipt, CredentialReceipt, UserReceipt)
            for receipt_type in dependency_order:
                for receipt in reversed(tuple(item for item in artifacts if isinstance(item, receipt_type))):
                    self._delete_exact(receipt)
                for receipt in reversed(tuple(item for item in control_rows if isinstance(item, receipt_type))):
                    self._delete_exact(receipt)
            self._closed = True

        def sanitized_evidence(self):
            return {
                "deterministic_verifier_calls": self._provider_calls,
                "external_provider_calls": 0,
                "cleanup_trace": tuple(self._cleanup_trace),
                "closed": self._closed,
            }

    return Ledger()


def _run_probe_matrix(url):
    before = _state_snapshot(url)
    previous_environment = os.environ.get("DIGITRANSX_ENVIRONMENT")
    previous_pepper = os.environ.get("DIGITRANSX_MPIN_PEPPER")
    os.environ["DIGITRANSX_ENVIRONMENT"] = "test"
    os.environ["DIGITRANSX_MPIN_PEPPER"] = PEPPER
    ledgers = []
    probe_results = {}
    during = None
    probe_error = None
    cleanup_error = None
    try:
        mpin = SharedTestLogoutAllLedger(url)
        password = SharedTestLogoutAllLedger(url)
        rollback = SharedTestLogoutAllLedger(url)
        ledgers.extend((mpin, password, rollback))
        mpin.setup_mpin_graph()
        password.setup_password_graph()
        rollback.setup_rollback_graph()
        probe_results["mpin"] = mpin.run_mpin_matrix()
        probe_results["password"] = password.run_password_route()
        probe_results["rollback"] = rollback.run_event_failure()
        during = _state_snapshot(url)
    except Exception as error:
        probe_error = error
    finally:
        for ledger in reversed(ledgers):
            try:
                ledger.cleanup()
            except Exception as error:
                cleanup_error = error if cleanup_error is None else ProbeAndCleanupError(cleanup_error, error)
        if previous_environment is None:
            os.environ.pop("DIGITRANSX_ENVIRONMENT", None)
        else:
            os.environ["DIGITRANSX_ENVIRONMENT"] = previous_environment
        if previous_pepper is None:
            os.environ.pop("DIGITRANSX_MPIN_PEPPER", None)
        else:
            os.environ["DIGITRANSX_MPIN_PEPPER"] = previous_pepper
    if probe_error is not None and cleanup_error is not None:
        raise ProbeAndCleanupError(probe_error, cleanup_error) from probe_error
    if cleanup_error is not None:
        raise cleanup_error
    if probe_error is not None:
        raise probe_error
    after = _state_snapshot(url)
    if before != after:
        raise SharedTestLogoutAllHarnessError("exact post-probe reconciliation failed")
    created = {table: during[table][0] - before[table][0] for table, _query in _SNAPSHOT_QUERIES}
    return {
        "probes": probe_results,
        "before_counts": {table: value[0] for table, value in before.items()},
        "created_counts": created,
        "after_counts": {table: value[0] for table, value in after.items()},
        "fingerprints_equal": {table: before[table][1] == after[table][1] for table, _query in _SNAPSHOT_QUERIES},
        "external_provider_calls": 0,
        "deterministic_verifier_calls": sum(ledger.sanitized_evidence()["deterministic_verifier_calls"] for ledger in ledgers),
    }


def run_authorized_logout_all_probe_matrix(environ=None):
    return _run_probe_matrix(require_authorized_shared_test_url(environ))
