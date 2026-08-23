"""Opt-in, test-only harness for authorized shared TEST step-up probes."""
from contextlib import contextmanager
import base64
from dataclasses import dataclass
import hashlib
import os
import secrets
from urllib.parse import urlsplit

import psycopg2
from flask import Flask

from auth import mpin_service, step_up_service
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

class ProbeAndCleanupError(SharedTestHarnessError):
    def __init__(self, probe_error, cleanup_error):
        super().__init__(
            f"probe failed with {type(probe_error).__name__}; "
            f"fixture cleanup failed with {type(cleanup_error).__name__}"
        )
        self.probe_error = probe_error
        self.cleanup_error = cleanup_error

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
    if parsed.username not in {
        "postgres",
        f"postgres.{EXPECTED_PROJECT_REF}",
    }:
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

def SharedTestFixtureLedger(url):
    """Build a fixture ledger whose ownership evidence has no caller write path."""
    ownership_seal = object()
    owned_rows = ()

    @dataclass(frozen=True)
    class OwnedUser:
        seal: object
        user_id: object
        email: str

    @dataclass(frozen=True)
    class OwnedTrustedDevice:
        seal: object
        device_id: object
        user_id: object
        token_digest: bytes

    @dataclass(frozen=True)
    class OwnedSession:
        seal: object
        session_id: object
        user_id: object
        trusted_device_id: object
        token_digest: bytes
        access_proof_digest: bytes

    @dataclass(frozen=True)
    class OwnedMpinCredential:
        seal: object
        user_id: object
        created_at: object

    @dataclass(frozen=True)
    class OwnedAuthorization:
        seal: object
        authorization_id: object
        user_id: object
        session_id: object
        trusted_device_id: object
        credential_generation: int
        proof_digest: bytes
        action_key: str
        resource_type: str
        resource_id: int
        amount_minor: object
        currency: object
        destination_digest: object
        funding_source: object
        request_fingerprint: bytes

    @dataclass(frozen=True)
    class OwnedConsumedEvent:
        seal: object
        event_id: object
        request_id: str
        fingerprint: str
        subject_user_id: object
        authorization_ref: str
        action_key: str
        resource_type: str
        resource_id: int
        request_fingerprint_ref: str

    @dataclass(frozen=True)
    class OwnedReconciliationEvent:
        seal: object
        event_id: object
        request_id: str
        fingerprint: str
        subject_user_id: object
        authorization_ref: str
        action_key: str
        resource_type: str
        resource_id: int
        request_fingerprint_ref: str

    current_user = None
    current_device = None
    current_session = None
    current_credential = None
    current_authorization = None
    current_raw_proof = None
    current_descriptor = None
    consumed_event_request_id = None
    reconciliation_event_request_id = None

    def issue_fixed(ledger, descriptor):
        nonlocal owned_rows, current_authorization, current_raw_proof
        nonlocal current_descriptor
        if ledger._cleaned:
            raise SharedTestHarnessError("cleaned fixture ledger is closed")
        if not all((current_user, current_device, current_session, current_credential)):
            raise SharedTestHarnessError("authentication fixture is incomplete")
        with ledger.connect() as conn:
            db = Db(conn)
            collision_params = (
                current_user.user_id, current_session.session_id,
                descriptor["action_key"], descriptor["resource_type"],
                descriptor["resource_id"], descriptor["request_fingerprint"],
            )
            existing = db.execute(
                "SELECT authorization_id "
                "FROM public.mpin_step_up_authorizations "
                "WHERE user_id=%s AND session_id=%s AND action_key=%s "
                "AND resource_type=%s AND resource_id=%s "
                "AND request_fingerprint=%s AND state='available'",
                collision_params,
            ).fetchone()
            if existing is not None:
                raise SharedTestHarnessError(
                    "authorization correlation collision before creation"
                )
            issued = step_up_service.issue_authorization(
                db,
                user_id=current_user.user_id,
                session_id=current_session.session_id,
                trusted_device_id=current_device.device_id,
                credential_generation=current_credential["credential_generation"],
                descriptor=descriptor,
            )
            if issued is None:
                raise SharedTestHarnessError(
                    "authorization creation returned no stable identity"
                )
            proof_digest = hashlib.sha256(
                issued["proof"].encode("ascii")
            ).digest()
            verify_params = (
                issued["authorization_id"], current_user.user_id,
                current_session.session_id, current_device.device_id,
                current_credential["credential_generation"], proof_digest,
                descriptor["action_key"], descriptor["resource_type"],
                descriptor["resource_id"], descriptor["request_fingerprint"],
                descriptor["amount_minor"], descriptor["currency"],
                descriptor["destination_digest"], descriptor["funding_source"],
            )
            verified = db.execute(
                "SELECT authorization_id "
                "FROM public.mpin_step_up_authorizations "
                "WHERE authorization_id=%s AND user_id=%s "
                "AND session_id=%s AND trusted_device_id=%s "
                "AND credential_generation=%s AND proof_digest=%s "
                "AND action_key=%s AND resource_type=%s "
                "AND resource_id=%s AND request_fingerprint=%s "
                "AND amount_minor IS NOT DISTINCT FROM %s "
                "AND currency IS NOT DISTINCT FROM %s "
                "AND destination_digest IS NOT DISTINCT FROM %s "
                "AND funding_source IS NOT DISTINCT FROM %s "
                "AND state='available'",
                verify_params,
            ).fetchone()
            if verified is None:
                raise SharedTestHarnessError(
                    "created authorization ownership verification failed"
                )
            evidence = OwnedAuthorization(
                ownership_seal, issued["authorization_id"],
                current_user.user_id, current_session.session_id,
                current_device.device_id,
                current_credential["credential_generation"], proof_digest,
                descriptor["action_key"], descriptor["resource_type"],
                descriptor["resource_id"], descriptor["amount_minor"],
                descriptor["currency"], descriptor["destination_digest"],
                descriptor["funding_source"], descriptor["request_fingerprint"],
            )
            owned_rows += (evidence,)
            current_authorization = evidence
            current_raw_proof = issued["proof"]
            current_descriptor = descriptor
            conn.commit()

    def current_binding():
        if current_authorization is None or current_raw_proof is None:
            raise SharedTestHarnessError("no harness-owned authorization is active")
        return {
            "raw_proof": current_raw_proof,
            "user_id": current_user.user_id,
            "session_id": current_session.session_id,
            "trusted_device_id": current_device.device_id,
            "credential_generation": current_authorization.credential_generation,
            "descriptor": current_descriptor,
        }

    def current_gate():
        return step_up_service.ConsumptionGate(
            "authorized",
            authorization={
                "authorization_id": current_authorization.authorization_id,
            },
            user={"id": current_user.user_id, "role": "customer"},
        )

    def capture_consumed_event(ledger, *, replay):
        nonlocal owned_rows, consumed_event_request_id
        request_id = (
            consumed_event_request_id
            or f"dtx.stepup.consumed.{secrets.token_hex(16)}"
        )
        with ledger.connect() as conn:
            db = Db(conn)
            collision = db.execute(
                "SELECT event_id FROM public.security_events "
                "WHERE idempotency_scope='security.mpin.step_up_consumed' "
                "AND idempotency_key=%s",
                (request_id,),
            ).fetchone()
            if not replay and collision is not None:
                raise SharedTestHarnessError(
                    "consumed-event correlation collision before creation"
                )
            result = step_up_service.write_consumed_event(
                db, request_id=request_id, gate=current_gate(),
                descriptor=current_descriptor,
            )
            if replay:
                if not result.replayed:
                    raise SharedTestHarnessError(
                        "consumed event replay created a second row"
                    )
                conn.rollback()
                return
            if result.replayed:
                raise SharedTestHarnessError("foreign consumed event was replayed")
            row = result.event
            authorization_ref = step_up_service.authorization_reference(
                current_authorization.authorization_id
            )
            request_ref = step_up_service.request_fingerprint_reference(
                current_descriptor["request_fingerprint"]
            )
            verify_params = (
                row["event_id"], request_id, request_id, row["fingerprint"],
                current_user.user_id, authorization_ref,
                current_descriptor["action_key"],
                current_descriptor["resource_type"],
                str(current_descriptor["resource_id"]), request_ref,
            )
            verified = db.execute(
                "SELECT event_id FROM public.security_events "
                "WHERE event_id=%s "
                "AND event_name='security.mpin.step_up_consumed' "
                "AND request_id=%s "
                "AND idempotency_scope='security.mpin.step_up_consumed' "
                "AND idempotency_key=%s AND fingerprint=%s "
                "AND subject_user_id=%s "
                "AND metadata->>'authorization_ref'=%s "
                "AND metadata->>'action_key'=%s "
                "AND metadata->>'resource_type'=%s "
                "AND metadata->>'resource_id'=%s "
                "AND metadata->>'request_fingerprint_ref'=%s "
                "AND source='domain_service' AND environment='test'",
                verify_params,
            ).fetchone()
            if verified is None:
                raise SharedTestHarnessError(
                    "created consumed event ownership verification failed"
                )
            owned_rows += (
                OwnedConsumedEvent(
                    ownership_seal, row["event_id"], request_id,
                    row["fingerprint"], current_user.user_id,
                    authorization_ref, current_descriptor["action_key"],
                    current_descriptor["resource_type"],
                    current_descriptor["resource_id"], request_ref,
                ),
            )
            consumed_event_request_id = request_id
            conn.commit()

    def capture_reconciliation_event(ledger, *, replay):
        nonlocal owned_rows, reconciliation_event_request_id
        request_id = (
            reconciliation_event_request_id
            or f"dtx.stepup.reconcile.{secrets.token_hex(16)}"
        )
        with ledger.connect() as conn:
            db = Db(conn)
            collision = db.execute(
                "SELECT event_id FROM public.security_events "
                "WHERE idempotency_scope="
                "'security.mpin.step_up_reconciliation_required' "
                "AND idempotency_key=%s",
                (request_id,),
            ).fetchone()
            if not replay and collision is not None:
                raise SharedTestHarnessError(
                    "reconciliation-event correlation collision before creation"
                )
            result = step_up_service.write_reconciliation_event(
                db, request_id=request_id, gate=current_gate(),
                descriptor=current_descriptor,
            )
            if replay:
                if not result.replayed:
                    raise SharedTestHarnessError(
                        "reconciliation replay created a second row"
                    )
                conn.rollback()
                return
            if result.replayed:
                raise SharedTestHarnessError(
                    "foreign reconciliation event was replayed"
                )
            row = result.event
            authorization_ref = step_up_service.authorization_reference(
                current_authorization.authorization_id
            )
            request_ref = step_up_service.request_fingerprint_reference(
                current_descriptor["request_fingerprint"]
            )
            verify_params = (
                row["event_id"], request_id, request_id, row["fingerprint"],
                current_user.user_id, authorization_ref,
                current_descriptor["action_key"],
                current_descriptor["resource_type"],
                str(current_descriptor["resource_id"]), request_ref,
            )
            verified = db.execute(
                "SELECT event_id FROM public.security_events "
                "WHERE event_id=%s "
                "AND event_name="
                "'security.mpin.step_up_reconciliation_required' "
                "AND request_id=%s "
                "AND idempotency_scope="
                "'security.mpin.step_up_reconciliation_required' "
                "AND idempotency_key=%s AND fingerprint=%s "
                "AND subject_user_id=%s "
                "AND metadata->>'authorization_ref'=%s "
                "AND metadata->>'action_key'=%s "
                "AND metadata->>'resource_type'=%s "
                "AND metadata->>'resource_id'=%s "
                "AND metadata->>'request_fingerprint_ref'=%s "
                "AND source='domain_service' AND environment='test'",
                verify_params,
            ).fetchone()
            if verified is None:
                raise SharedTestHarnessError(
                    "created reconciliation event ownership verification failed"
                )
            owned_rows += (
                OwnedReconciliationEvent(
                    ownership_seal, row["event_id"], request_id,
                    row["fingerprint"], current_user.user_id,
                    authorization_ref, current_descriptor["action_key"],
                    current_descriptor["resource_type"],
                    current_descriptor["resource_id"], request_ref,
                ),
            )
            reconciliation_event_request_id = request_id
            conn.commit()

    class Ledger:
        def __init__(self):
            self.url = url
            self.tag = f"dtx_shared_step_up_{secrets.token_hex(8)}"
            self._cleaned = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            try:
                self.cleanup()
            except Exception as cleanup_error:
                if exc_value is not None:
                    raise ProbeAndCleanupError(exc_value, cleanup_error) from exc_value
                raise
            return False

        def connect(self):
            return psycopg2.connect(self.url)

        def cleanup(self):
            nonlocal owned_rows
            if self._cleaned:
                return
            with self.connect() as conn:
                with conn.cursor() as cursor:
                    for owned in reversed(owned_rows):
                        if getattr(owned, "seal", None) is not ownership_seal:
                            raise SharedTestHarnessError(
                                "fixture ownership evidence is not harness-issued"
                            )
                        if isinstance(owned, OwnedConsumedEvent):
                            label = f"security_events:{owned.event_id}"
                            owner_params = (
                                owned.event_id, owned.request_id, owned.request_id,
                                owned.fingerprint, owned.subject_user_id,
                                owned.authorization_ref, owned.action_key,
                                owned.resource_type, str(owned.resource_id),
                                owned.request_fingerprint_ref,
                            )
                            cursor.execute(
                                "SELECT event_id FROM public.security_events "
                                "WHERE event_id=%s "
                                "AND event_name='security.mpin.step_up_consumed' "
                                "AND request_id=%s "
                                "AND idempotency_scope='security.mpin.step_up_consumed' "
                                "AND idempotency_key=%s AND fingerprint=%s "
                                "AND subject_user_id=%s "
                                "AND metadata->>'authorization_ref'=%s "
                                "AND metadata->>'action_key'=%s "
                                "AND metadata->>'resource_type'=%s "
                                "AND metadata->>'resource_id'=%s "
                                "AND metadata->>'request_fingerprint_ref'=%s "
                                "AND source='domain_service' AND environment='test' "
                                "FOR UPDATE",
                                owner_params,
                            )
                            delete_sql = (
                                "DELETE FROM public.security_events "
                                "WHERE event_id=%s "
                                "AND event_name='security.mpin.step_up_consumed' "
                                "AND request_id=%s "
                                "AND idempotency_scope='security.mpin.step_up_consumed' "
                                "AND idempotency_key=%s AND fingerprint=%s "
                                "AND subject_user_id=%s "
                                "AND metadata->>'authorization_ref'=%s "
                                "AND metadata->>'action_key'=%s "
                                "AND metadata->>'resource_type'=%s "
                                "AND metadata->>'resource_id'=%s "
                                "AND metadata->>'request_fingerprint_ref'=%s "
                                "AND source='domain_service' AND environment='test'"
                            )
                        elif isinstance(owned, OwnedReconciliationEvent):
                            label = f"security_events:{owned.event_id}"
                            owner_params = (
                                owned.event_id, owned.request_id, owned.request_id,
                                owned.fingerprint, owned.subject_user_id,
                                owned.authorization_ref, owned.action_key,
                                owned.resource_type, str(owned.resource_id),
                                owned.request_fingerprint_ref,
                            )
                            cursor.execute(
                                "SELECT event_id FROM public.security_events "
                                "WHERE event_id=%s "
                                "AND event_name='security.mpin.step_up_reconciliation_required' "
                                "AND request_id=%s "
                                "AND idempotency_scope="
                                "'security.mpin.step_up_reconciliation_required' "
                                "AND idempotency_key=%s AND fingerprint=%s "
                                "AND subject_user_id=%s "
                                "AND metadata->>'authorization_ref'=%s "
                                "AND metadata->>'action_key'=%s "
                                "AND metadata->>'resource_type'=%s "
                                "AND metadata->>'resource_id'=%s "
                                "AND metadata->>'request_fingerprint_ref'=%s "
                                "AND source='domain_service' AND environment='test' "
                                "FOR UPDATE",
                                owner_params,
                            )
                            delete_sql = (
                                "DELETE FROM public.security_events "
                                "WHERE event_id=%s "
                                "AND event_name='security.mpin.step_up_reconciliation_required' "
                                "AND request_id=%s "
                                "AND idempotency_scope="
                                "'security.mpin.step_up_reconciliation_required' "
                                "AND idempotency_key=%s AND fingerprint=%s "
                                "AND subject_user_id=%s "
                                "AND metadata->>'authorization_ref'=%s "
                                "AND metadata->>'action_key'=%s "
                                "AND metadata->>'resource_type'=%s "
                                "AND metadata->>'resource_id'=%s "
                                "AND metadata->>'request_fingerprint_ref'=%s "
                                "AND source='domain_service' AND environment='test'"
                            )
                        elif isinstance(owned, OwnedAuthorization):
                            label = (
                                "mpin_step_up_authorizations:"
                                f"{owned.authorization_id}"
                            )
                            owner_params = (
                                owned.authorization_id, owned.user_id, owned.session_id,
                                owned.trusted_device_id, owned.credential_generation,
                                owned.proof_digest, owned.action_key, owned.resource_type,
                                owned.resource_id, owned.request_fingerprint,
                                owned.amount_minor, owned.currency,
                                owned.destination_digest, owned.funding_source,
                            )
                            cursor.execute(
                                "SELECT authorization_id "
                                "FROM public.mpin_step_up_authorizations "
                                "WHERE authorization_id=%s AND user_id=%s "
                                "AND session_id=%s AND trusted_device_id=%s "
                                "AND credential_generation=%s AND proof_digest=%s "
                                "AND action_key=%s AND resource_type=%s "
                                "AND resource_id=%s AND request_fingerprint=%s "
                                "AND amount_minor IS NOT DISTINCT FROM %s "
                                "AND currency IS NOT DISTINCT FROM %s "
                                "AND destination_digest IS NOT DISTINCT FROM %s "
                                "AND funding_source IS NOT DISTINCT FROM %s "
                                "FOR UPDATE",
                                owner_params,
                            )
                            delete_sql = (
                                "DELETE FROM public.mpin_step_up_authorizations "
                                "WHERE authorization_id=%s AND user_id=%s "
                                "AND session_id=%s AND trusted_device_id=%s "
                                "AND credential_generation=%s AND proof_digest=%s "
                                "AND action_key=%s AND resource_type=%s "
                                "AND resource_id=%s AND request_fingerprint=%s "
                                "AND amount_minor IS NOT DISTINCT FROM %s "
                                "AND currency IS NOT DISTINCT FROM %s "
                                "AND destination_digest IS NOT DISTINCT FROM %s "
                                "AND funding_source IS NOT DISTINCT FROM %s"
                            )
                        elif isinstance(owned, OwnedMpinCredential):
                            label = f"mpin_credentials:{owned.user_id}"
                            owner_params = (owned.user_id, owned.created_at)
                            cursor.execute(
                                "SELECT user_id FROM public.mpin_credentials "
                                "WHERE user_id=%s AND created_at=%s FOR UPDATE",
                                owner_params,
                            )
                            delete_sql = (
                                "DELETE FROM public.mpin_credentials "
                                "WHERE user_id=%s AND created_at=%s"
                            )
                        elif isinstance(owned, OwnedSession):
                            label = f"user_sessions:{owned.session_id}"
                            owner_params = (
                                owned.session_id, owned.user_id, owned.trusted_device_id,
                                owned.token_digest, owned.access_proof_digest,
                            )
                            cursor.execute(
                                "SELECT session_id FROM public.user_sessions "
                                "WHERE session_id=%s AND user_id=%s AND trusted_device_id=%s "
                                "AND token_digest=%s AND access_proof_digest=%s FOR UPDATE",
                                owner_params,
                            )
                            delete_sql = (
                                "DELETE FROM public.user_sessions "
                                "WHERE session_id=%s AND user_id=%s AND trusted_device_id=%s "
                                "AND token_digest=%s AND access_proof_digest=%s"
                            )
                        elif isinstance(owned, OwnedTrustedDevice):
                            label = f"trusted_devices:{owned.device_id}"
                            owner_params = (
                                owned.device_id, owned.user_id, owned.token_digest,
                            )
                            cursor.execute(
                                "SELECT id FROM public.trusted_devices "
                                "WHERE id=%s AND user_id=%s AND token_digest=%s FOR UPDATE",
                                owner_params,
                            )
                            delete_sql = (
                                "DELETE FROM public.trusted_devices "
                                "WHERE id=%s AND user_id=%s AND token_digest=%s"
                            )
                        elif isinstance(owned, OwnedUser):
                            label = f"users:{owned.user_id}"
                            owner_params = (owned.user_id, owned.email, self.tag)
                            cursor.execute(
                                "SELECT id FROM public.users "
                                "WHERE id=%s AND email=%s AND full_name=%s FOR UPDATE",
                                owner_params,
                            )
                            delete_sql = (
                                "DELETE FROM public.users "
                                "WHERE id=%s AND email=%s AND full_name=%s"
                            )
                        else:
                            raise SharedTestHarnessError(
                                "unsupported fixture ownership evidence"
                            )
                        if cursor.fetchone() is None:
                            raise SharedTestHarnessError(
                                f"ownership uncertain for {label}"
                            )
                        cursor.execute(delete_sql, owner_params)
                        if cursor.rowcount != 1:
                            raise SharedTestHarnessError(
                                f"owned fixture delete was not exact for {label}"
                            )
                conn.commit()
            owned_rows = ()
            self._cleaned = True

        def create_user(self, *, legacy_role, app_role):
            nonlocal owned_rows, current_user
            if self._cleaned:
                raise SharedTestHarnessError("cleaned fixture ledger is closed")
            if current_user is not None:
                raise SharedTestHarnessError("fixture ledger already owns a user")
            with self.connect() as conn, conn.cursor() as cursor:
                email = f"{self.tag}.{secrets.token_hex(4)}@example.invalid"
                cnic = secrets.token_hex(7)[:13]
                cursor.execute(
                    "INSERT INTO public.users(full_name,email,cnic,role,legacy_role) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                    (self.tag, email, cnic, app_role, legacy_role),
                )
                user_id = cursor.fetchone()[0]
                conn.commit()
            current_user = OwnedUser(
                ownership_seal, user_id, email,
            )
            owned_rows += (current_user,)
            return user_id

        def attach_authentication(self):
            nonlocal owned_rows, current_device, current_session
            nonlocal current_credential
            if self._cleaned:
                raise SharedTestHarnessError("cleaned fixture ledger is closed")
            if current_user is None:
                raise SharedTestHarnessError("user fixture is required")
            if current_session is not None:
                raise SharedTestHarnessError(
                    "fixture ledger already owns authentication"
                )
            user_id = current_user.user_id
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
                    "INSERT INTO public.mpin_credentials(user_id,verifier,salt,kdf_version) "
                    "VALUES(%s,%s,%s,1) "
                    "RETURNING credential_generation,created_at",
                    (user_id, verifier, salt),
                )
                credential_row = cursor.fetchone()
                conn.commit()
            current_device = OwnedTrustedDevice(
                ownership_seal, device_id, user_id, device_digest,
            )
            current_session = OwnedSession(
                ownership_seal, session_id, user_id, device_id,
                session_digest, access_digest,
            )
            current_credential = {
                "credential_generation": credential_row[0],
                "created_at": credential_row[1],
            }
            owned_rows += (
                current_device,
                current_session,
                OwnedMpinCredential(
                    ownership_seal, user_id, credential_row[1],
                ),
            )
            return {
                "device_id": device_id,
                "session_id": session_id,
                "device_raw": device_raw,
                "session_raw": session_raw,
                "access_raw": access_raw,
            }

        def issue_checkout_authorization(self):
            descriptor = step_up_service.normalize_descriptor({
                "action_key": "one_time.checkout.wallet_only",
                "resource_type": "order",
                "resource_id": current_user.user_id,
                "amount_minor": 12500,
                "currency": "PKR",
                "funding_source": "wallet",
            })
            issue_fixed(self, descriptor)

        def issue_payout_authorization(self):
            descriptor = step_up_service.normalize_descriptor({
                "action_key": "wallet.payout_destination.replace",
                "resource_type": "wallet",
                "resource_id": current_user.user_id,
                "destination_fingerprint": hashlib.sha256(
                    f"{self.tag}.destination".encode("ascii")
                ).hexdigest(),
            })
            issue_fixed(self, descriptor)

        def write_consumed_evidence(self):
            capture_consumed_event(self, replay=False)

        def replay_consumed_evidence(self):
            capture_consumed_event(self, replay=True)

        def write_reconciliation_evidence(self):
            capture_reconciliation_event(self, replay=False)

        def replay_reconciliation_evidence(self):
            capture_reconciliation_event(self, replay=True)

        def run_pending_probe_matrix(self):
            nonlocal current_credential

            def consume(binding):
                with self.connect() as conn:
                    result = step_up_service.consume_authorization(
                        Db(conn), **binding
                    )
                    conn.commit()
                    return result

            self.issue_checkout_authorization()
            wrong_binding = {
                **current_binding(),
                "descriptor": step_up_service.normalize_descriptor({
                    "action_key": "one_time.checkout.wallet_only",
                    "resource_type": "order",
                    "resource_id": current_user.user_id,
                    "amount_minor": 12501,
                    "currency": "PKR",
                    "funding_source": "wallet",
                }),
            }
            if consume(wrong_binding) is not None:
                raise SharedTestHarnessError("binding mismatch unexpectedly consumed")

            exact_binding = current_binding()
            consumed = consume(exact_binding)
            if not consumed or consumed["state"] != "consumed":
                raise SharedTestHarnessError("exact authorization was not consumed")
            if consume(exact_binding) is not None:
                raise SharedTestHarnessError("authorization replay unexpectedly succeeded")
            self.write_consumed_evidence()
            self.replay_consumed_evidence()

            self.issue_checkout_authorization()
            with self.connect() as conn:
                db = Db(conn)
                expired = db.execute(
                    "UPDATE public.mpin_step_up_authorizations "
                    "SET issued_at=issued_at-interval '4 minutes', "
                    "expires_at=expires_at-interval '4 minutes' "
                    "WHERE authorization_id=%s AND user_id=%s "
                    "AND session_id=%s AND trusted_device_id=%s "
                    "AND proof_digest=%s AND request_fingerprint=%s "
                    "AND state='available'",
                    (
                        current_authorization.authorization_id,
                        current_authorization.user_id,
                        current_authorization.session_id,
                        current_authorization.trusted_device_id,
                        current_authorization.proof_digest,
                        current_authorization.request_fingerprint,
                    ),
                )
                if expired.rowcount != 1:
                    raise SharedTestHarnessError(
                        "expiry proof did not update exactly one owned authorization"
                    )
                conn.commit()
            if consume(current_binding()) is not None:
                raise SharedTestHarnessError("expired authorization was consumed")
            with self.connect() as conn:
                state = Db(conn).execute(
                    "SELECT state FROM public.mpin_step_up_authorizations "
                    "WHERE authorization_id=%s AND user_id=%s "
                    "AND session_id=%s AND trusted_device_id=%s "
                    "AND proof_digest=%s AND request_fingerprint=%s",
                    (
                        current_authorization.authorization_id,
                        current_authorization.user_id,
                        current_authorization.session_id,
                        current_authorization.trusted_device_id,
                        current_authorization.proof_digest,
                        current_authorization.request_fingerprint,
                    ),
                ).fetchone()
                conn.rollback()
            if not state or state["state"] != "expired":
                raise SharedTestHarnessError(
                    "expired authorization did not reach expired state"
                )

            self.issue_checkout_authorization()
            old_generation = current_credential["credential_generation"]
            with self.connect() as conn:
                db = Db(conn)
                changed = mpin_service.replace(
                    db, current_user.user_id, "5678",
                    environ={"DIGITRANSX_MPIN_PEPPER": PEPPER},
                )
                if not changed:
                    raise SharedTestHarnessError("MPIN generation rotation failed")
                credential = db.execute(
                    "SELECT credential_generation,created_at "
                    "FROM public.mpin_credentials "
                    "WHERE user_id=%s AND created_at=%s",
                    (
                        current_user.user_id,
                        current_credential["created_at"],
                    ),
                ).fetchone()
                authorization = db.execute(
                    "SELECT state FROM public.mpin_step_up_authorizations "
                    "WHERE authorization_id=%s AND user_id=%s "
                    "AND session_id=%s AND trusted_device_id=%s "
                    "AND proof_digest=%s AND request_fingerprint=%s",
                    (
                        current_authorization.authorization_id,
                        current_authorization.user_id,
                        current_authorization.session_id,
                        current_authorization.trusted_device_id,
                        current_authorization.proof_digest,
                        current_authorization.request_fingerprint,
                    ),
                ).fetchone()
                if (
                    not credential
                    or credential["credential_generation"] <= old_generation
                    or not authorization
                    or authorization["state"] != "invalidated"
                ):
                    raise SharedTestHarnessError(
                        "MPIN rotation did not invalidate the exact authorization"
                    )
                current_credential = credential
                conn.commit()

            self.issue_checkout_authorization()
            changed_funding = {
                **current_binding(),
                "descriptor": {
                    **current_descriptor,
                    "funding_source": None,
                },
            }
            if consume(changed_funding) is not None:
                raise SharedTestHarnessError(
                    "wallet funding-source change unexpectedly consumed"
                )
            if consume(current_binding()) is None:
                raise SharedTestHarnessError(
                    "funding-source control authorization did not consume"
                )

            self.issue_payout_authorization()
            with self.connect() as conn:
                claimed = step_up_service.claim_authorization(
                    Db(conn), **current_binding()
                )
                if not claimed:
                    raise SharedTestHarnessError(
                        "provider-rejection authorization was not claimed"
                    )
                claimed_row, raw_claim = claimed
                conn.commit()
            with deterministic_payout_provider("reject") as rejected_provider:
                try:
                    rejected_provider.tokenize({})
                except PaymentProviderRejected:
                    pass
                else:
                    raise SharedTestHarnessError(
                        "deterministic provider did not reject"
                    )
            with self.connect() as conn:
                rejected = step_up_service.finalize_claim(
                    Db(conn),
                    authorization_id=claimed_row["authorization_id"],
                    raw_claim=raw_claim,
                    provider_rejected=True,
                )
                if not rejected or rejected["state"] != "invalidated":
                    raise SharedTestHarnessError(
                        "definite provider rejection was not terminal"
                    )
                conn.commit()

            self.issue_payout_authorization()
            with self.connect() as conn:
                claimed = step_up_service.claim_authorization(
                    Db(conn), **current_binding()
                )
                if not claimed:
                    raise SharedTestHarnessError(
                        "provider-ambiguity authorization was not claimed"
                    )
                claimed_row, raw_claim = claimed
                conn.commit()
            with deterministic_payout_provider("ambiguous") as ambiguous_provider:
                try:
                    ambiguous_provider.tokenize({})
                except RuntimeError:
                    pass
                else:
                    raise SharedTestHarnessError(
                        "deterministic provider was not ambiguous"
                    )
            with self.connect() as conn:
                reconciled = step_up_service.finalize_claim(
                    Db(conn),
                    authorization_id=claimed_row["authorization_id"],
                    raw_claim=raw_claim,
                    reconciliation_required=True,
                )
                if (
                    not reconciled
                    or reconciled["state"] != "reconciliation_required"
                ):
                    raise SharedTestHarnessError(
                        "ambiguous provider outcome was not reconciled"
                    )
                conn.commit()
            self.write_reconciliation_evidence()

            self.replay_reconciliation_evidence()
            return {
                "binding_mismatch": "rejected",
                "replay": "rejected",
                "expiry": "expired",
                "mpin_generation_rotation": "invalidated",
                "wallet_funding_source_change": "rejected",
                "provider_rejection": "invalidated",
                "provider_ambiguity": "reconciliation_required",
                "evidence_replay": "idempotent",
                "deterministic_provider_calls": (
                    rejected_provider.calls + ambiguous_provider.calls
                ),
                "external_provider_calls": 0,
            }

    return Ledger()

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

def shared_test_state_snapshot():
    snapshot_queries = (
        ("users", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.users t"),
        ("trusted_devices", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.trusted_devices t"),
        ("user_sessions", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.user_sessions t"),
        ("mpin_credentials", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.mpin_credentials t"),
        ("mpin_step_up_authorizations", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.mpin_step_up_authorizations t"),
        ("security_events", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.security_events t"),
        ("business_audit_events", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.business_audit_events t"),
        ("wallets", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.wallets t"),
        ("wallet_transactions", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.wallet_transactions t"),
        ("wallet_withdrawal_requests", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.wallet_withdrawal_requests t"),
        ("payments", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.payments t"),
        ("transporter_profiles", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.transporter_profiles t"),
        ("shipments", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.shipments t"),
        ("shipment_bids", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.shipment_bids t"),
        ("shipment_trips", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.shipment_trips t"),
        ("agreements", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.agreements t"),
        ("agreement_posts", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.agreement_posts t"),
        ("agreement_bids", "SELECT count(*),md5(coalesce(string_agg(md5(row_to_json(t)::text),'|' ORDER BY md5(row_to_json(t)::text)),'') ) FROM public.agreement_bids t"),
    )
    url = require_authorized_shared_test_url()
    result = {}
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        for table, query in snapshot_queries:
            cursor.execute(query)
            count, fingerprint = cursor.fetchone()
            result[table] = {
                "count": int(count),
                "fingerprint": fingerprint,
            }
        conn.rollback()
    return result

def run_authorized_pending_probe_matrix():
    before = shared_test_state_snapshot()
    previous_environment = os.environ.get("DIGITRANSX_ENVIRONMENT")
    previous_pepper = os.environ.get("DIGITRANSX_MPIN_PEPPER")
    try:
        os.environ["DIGITRANSX_ENVIRONMENT"] = "test"
        os.environ["DIGITRANSX_MPIN_PEPPER"] = PEPPER
        with open_shared_test_fixture() as ledger:
            ledger.create_user(
                legacy_role="service_seeker", app_role="customer",
            )
            ledger.attach_authentication()
            proofs = ledger.run_pending_probe_matrix()
            during = shared_test_state_snapshot()
    finally:
        if previous_environment is None:
            os.environ.pop("DIGITRANSX_ENVIRONMENT", None)
        else:
            os.environ["DIGITRANSX_ENVIRONMENT"] = previous_environment
        if previous_pepper is None:
            os.environ.pop("DIGITRANSX_MPIN_PEPPER", None)
        else:
            os.environ["DIGITRANSX_MPIN_PEPPER"] = previous_pepper
    after = shared_test_state_snapshot()
    if after != before:
        changed = sorted(
            table for table in before if before[table] != after[table]
        )
        raise SharedTestHarnessError(
            "shared TEST did not reconcile exact pre-probe state: "
            + ",".join(changed)
        )
    created = {
        table: during[table]["count"] - before[table]["count"]
        for table in before
        if during[table]["count"] != before[table]["count"]
    }
    return {
        "proofs": proofs,
        "created_row_deltas": created,
        "before": before,
        "after": after,
        "exact_reconciliation": True,
    }
