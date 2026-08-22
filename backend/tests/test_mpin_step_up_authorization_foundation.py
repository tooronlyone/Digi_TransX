"""Phase 1B-2C3C1 action-bound MPIN step-up foundation proofs."""

from contextlib import contextmanager
import hashlib
import os
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import errors
import pytest

import auth.helpers as auth_helpers
import auth.routes as auth_routes
from auth import session_service, step_up_service
from events.catalog import CATALOG, NonWritableEventName, get_writable_event_definition
from shared.db import Db
from tests._life_helpers import (
    STUBS, make_disposable, origin_main_schema_or_skip, require_test_db_url,
)
from tests.test_secure_mpin_access import (
    _authenticate, _csrf, _session_snapshot, mpin_client, mpin_database_url,
)


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20260801210000_mpin_step_up_authorization_foundation.sql"


def _action(**overrides):
    value = {
        "action_key": "one_time.checkout.wallet_only",
        "resource_type": "order",
        "resource_id": 41,
        "amount_minor": 12500,
        "currency": "PKR",
        "funding_source": "wallet",
    }
    value.update(overrides)
    return value


def _post(client, mpin="1234", action=None):
    return client.post(
        "/auth/mpin/step-up",
        json={"mpin": mpin, "action": action or _action()},
        headers=_csrf(),
    )


def _ledger_row(url):
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select *,expires_at-issued_at as lifetime "
                "from public.mpin_step_up_authorizations order by issued_at desc limit 1"
            )
            columns = [item.name for item in cursor.description]
            return dict(zip(columns, cursor.fetchone()))


def _step_up_persistence_counts(url):
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*) from public.mpin_step_up_authorizations")
            authorizations = cursor.fetchone()[0]
            cursor.execute(
                "select count(*) from public.security_events "
                "where event_name='security.mpin.step_up_succeeded'"
            )
            successes = cursor.fetchone()[0]
    return authorizations, successes


def _credential_failures(url, user_id):
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select failed_attempts from public.mpin_credentials where user_id=%s",
                (user_id,),
            )
            return cursor.fetchone()[0]


def _device_snapshot(url, device_id):
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select token_digest,previous_token_digest,last_used_at,expires_at,"
                "revoked_at,rotated_at from public.trusted_devices where id=%s",
                (device_id,),
            )
            return cursor.fetchone()


def _route_database_after(url, hook):
    @contextmanager
    def interleaved_open_db():
        hook()
        conn = psycopg2.connect(url)
        try:
            yield Db(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return interleaved_open_db


@pytest.mark.parametrize(
    "value",
    [
        {"action_key": "one_time.checkout.wallet_only", "resource_type": "order", "resource_id": 1, "amount_minor": 1, "currency": "PKR", "funding_source": "wallet"},
        {"action_key": "wallet.withdrawal.request", "resource_type": "wallet", "resource_id": 1, "amount_minor": 1, "currency": "PKR", "destination_fingerprint": "a" * 64},
        {"action_key": "wallet.withdrawal_limit.purchase", "resource_type": "wallet", "resource_id": 1, "amount_minor": 1, "currency": "PKR", "funding_source": "wallet"},
        {"action_key": "wallet.payout_destination.replace", "resource_type": "wallet", "resource_id": 1, "destination_fingerprint": "b" * 64},
        {"action_key": "agreement.finalize", "resource_type": "agreement", "resource_id": 1, "amount_minor": 1, "currency": "PKR"},
        {"action_key": "client.delivery.confirm_release", "resource_type": "trip", "resource_id": 1, "amount_minor": 1, "currency": "PKR"},
    ],
)
def test_exact_six_server_recognized_action_descriptors(value):
    normalized = step_up_service.normalize_descriptor(value)
    assert normalized["action_key"] == value["action_key"]
    assert len(normalized["request_fingerprint"]) == 32
    assert len(step_up_service.ACTION_POLICIES) == 6


def test_issuance_is_digest_only_exactly_three_minutes_and_does_not_refresh(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    before_session = _session_snapshot(url, auth["session_id"])
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select last_used_at,expires_at from public.trusted_devices where id=%s",
                (auth["device_id"],),
            )
            before_device = cursor.fetchone()

    response = _post(client)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.get_json()
    proof = payload["authorization_proof"]
    assert isinstance(proof, str) and len(proof) >= 43

    row = _ledger_row(url)
    assert bytes(row["proof_digest"]) == hashlib.sha256(proof.encode("ascii")).digest()
    assert row["lifetime"].total_seconds() == 180
    assert row["state"] == "available"
    assert _session_snapshot(url, auth["session_id"]) == before_session
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select last_used_at,expires_at from public.trusted_devices where id=%s",
                (auth["device_id"],),
            )
            assert cursor.fetchone() == before_device
            cursor.execute(
                "select event_name,metadata::text from public.security_events order by occurred_at"
            )
            events = cursor.fetchall()
    assert events[-1][0] == "security.mpin.step_up_succeeded"
    assert proof not in events[-1][1]
    assert set(__import__("json").loads(events[-1][1])) == {
        "authorization_ref", "action_key", "resource_type", "resource_id",
        "request_fingerprint_ref",
    }


def test_locked_issuance_rejects_decorator_validated_proof_after_rotation(
    mpin_client, monkeypatch, caplog,
):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    original_route_db = auth_routes.open_db
    rotated = {}

    def rotate_before_locked_issuance():
        if rotated:
            return
        with psycopg2.connect(url) as conn:
            rotated["proof"] = session_service.rotate_access_proof(
                Db(conn), auth["session_id"]
            )
        rotated["session"] = _session_snapshot(url, auth["session_id"])
        rotated["device"] = _device_snapshot(url, auth["device_id"])

    monkeypatch.setattr(
        auth_routes, "open_db", _route_database_after(url, rotate_before_locked_issuance)
    )
    stale = _post(client)
    assert stale.status_code == 423
    assert stale.get_json() == {
        "success": False, "code": "access_locked", "message": "Access is locked."
    }
    assert _step_up_persistence_counts(url) == (0, 0)
    assert _credential_failures(url, auth["user_id"]) == 0
    assert _session_snapshot(url, auth["session_id"]) == rotated["session"]
    assert _device_snapshot(url, auth["device_id"]) == rotated["device"]
    assert auth["proof_raw"] not in stale.get_data(as_text=True)
    assert auth["proof_raw"] not in caplog.text

    monkeypatch.setattr(auth_routes, "open_db", original_route_db)
    client.set_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME, rotated["proof"])
    current = _post(client)
    assert current.status_code == 200
    assert _step_up_persistence_counts(url) == (1, 1)


def test_locked_issuance_rejects_proof_expired_after_decorator_validation(
    mpin_client, monkeypatch, caplog,
):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    expired = {}

    def expire_before_locked_issuance():
        if expired:
            return
        with psycopg2.connect(url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "update public.user_sessions "
                    "set access_proof_expires_at=authenticated_at+interval '1 microsecond',"
                    "updated_at=now() where session_id=%s",
                    (auth["session_id"],),
                )
        expired["session"] = _session_snapshot(url, auth["session_id"])
        expired["device"] = _device_snapshot(url, auth["device_id"])

    monkeypatch.setattr(
        auth_routes, "open_db", _route_database_after(url, expire_before_locked_issuance)
    )
    response = _post(client)
    assert response.status_code == 423
    assert response.get_json()["code"] == "access_locked"
    assert _step_up_persistence_counts(url) == (0, 0)
    assert _credential_failures(url, auth["user_id"]) == 0
    assert _session_snapshot(url, auth["session_id"]) == expired["session"]
    assert _device_snapshot(url, auth["device_id"]) == expired["device"]
    assert auth["proof_raw"] not in response.get_data(as_text=True)
    assert auth["proof_raw"] not in caplog.text


@pytest.mark.parametrize("presented", [None, "short", "x" * 43])
def test_missing_malformed_and_wrong_software_proofs_fail_before_mpin(
    mpin_client, presented,
):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    if presented is None:
        client.delete_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME)
    else:
        client.set_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME, presented)
    response = _post(client)
    assert response.status_code == 423
    assert response.get_json()["code"] == "access_locked"
    assert _step_up_persistence_counts(url) == (0, 0)
    assert _credential_failures(url, auth["user_id"]) == 0


@pytest.mark.parametrize(
    ("state_kind", "expected_status"),
    [
        ("session_revoked", 401),
        ("session_expired", 401),
        ("device_revoked", 401),
        ("device_expired", 401),
        ("device_mismatched", 401),
        ("software_locked", 423),
    ],
)
def test_step_up_rejects_inactive_session_device_and_software_state(
    mpin_client, state_kind, expected_status,
):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            if state_kind == "session_revoked":
                cursor.execute(
                    "update public.user_sessions set revoked_at=now(),"
                    "revocation_reason='security_action',updated_at=now() "
                    "where session_id=%s",
                    (auth["session_id"],),
                )
            elif state_kind == "session_expired":
                cursor.execute(
                    "update public.user_sessions set inactivity_expires_at="
                    "last_genuine_activity_at+interval '1 microsecond',updated_at=now() "
                    "where session_id=%s",
                    (auth["session_id"],),
                )
            elif state_kind == "device_revoked":
                cursor.execute(
                    "update public.trusted_devices set revoked_at=now() where id=%s",
                    (auth["device_id"],),
                )
            elif state_kind == "device_expired":
                cursor.execute(
                    "update public.trusted_devices set expires_at="
                    "created_at+interval '1 microsecond' where id=%s",
                    (auth["device_id"],),
                )
            elif state_kind == "software_locked":
                cursor.execute(
                    "update public.user_sessions set access_locked=true,"
                    "access_locked_at=now(),access_proof_digest=null,"
                    "access_proof_expires_at=null,updated_at=now() where session_id=%s",
                    (auth["session_id"],),
                )
    if state_kind == "device_mismatched":
        client.set_cookie(auth_helpers.DEVICE_COOKIE_NAME, secrets.token_urlsafe(32))
    response = _post(client)
    assert response.status_code == expected_status
    if expected_status == 423:
        assert response.get_json()["code"] == "access_locked"
    assert _step_up_persistence_counts(url) == (0, 0)
    assert _credential_failures(url, auth["user_id"]) == 0


def test_concurrent_rotation_serializes_before_locked_step_up_issuance(
    mpin_client, monkeypatch,
):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    waiting_for_session_lock = threading.Event()
    original_lock = auth_routes._lock_current_authentication

    def signal_then_lock(db):
        waiting_for_session_lock.set()
        return original_lock(db)

    monkeypatch.setattr(auth_routes, "_lock_current_authentication", signal_then_lock)
    contender = client.application.test_client()
    for cookie_name in (
        auth_helpers.DEVICE_COOKIE_NAME,
        auth_helpers.SESSION_TOKEN_COOKIE_NAME,
        auth_helpers.ACCESS_PROOF_COOKIE_NAME,
    ):
        contender.set_cookie(cookie_name, client.get_cookie(cookie_name).value)
    with contender.session_transaction() as state:
        state["csrf_token"] = "mpin-csrf"

    rotation_conn = psycopg2.connect(url)
    try:
        rotation_db = Db(rotation_conn)
        session_service.lock_session_by_id(
            rotation_db, auth["session_id"], auth["user_id"]
        )
        current_proof = session_service.rotate_access_proof(
            rotation_db, auth["session_id"]
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_post, contender)
            assert waiting_for_session_lock.wait(timeout=5)
            assert not future.done()
            rotation_conn.commit()
            stale = future.result(timeout=5)
    finally:
        rotation_conn.close()

    assert stale.status_code == 423
    assert stale.get_json()["code"] == "access_locked"
    assert _step_up_persistence_counts(url) == (0, 0)
    assert _credential_failures(url, auth["user_id"]) == 0
    contender.set_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME, current_proof)
    assert _post(contender).status_code == 200
    assert _step_up_persistence_counts(url) == (1, 1)


def test_step_up_is_the_only_route_consumer_of_cached_access_proof_verdict():
    route_source = (ROOT / "backend/auth/routes.py").read_text(encoding="utf-8")
    assert "request.current_session.get(\"access_proof_valid\")" not in route_source


def test_wrong_mpin_reuses_one_counter_and_fifth_failure_locks_without_disclosure(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    for attempt in range(1, 6):
        response = _post(client, mpin="9999")
        assert response.status_code == (423 if attempt == 5 else 401)
        body = response.get_json()
        assert "remaining" not in str(body).lower()
        assert "attempt" not in str(body).lower()
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select failed_attempts,permanently_locked from public.mpin_credentials where user_id=%s",
                (auth["user_id"],),
            )
            assert cursor.fetchone() == (5, True)
            cursor.execute(
                "select count(*) from public.security_events where event_name='security.mpin.step_up_failed'"
            )
            assert cursor.fetchone()[0] == 5


def test_issuance_requires_enrollment_csrf_and_current_software_proof(mpin_client):
    client, url = mpin_client
    _authenticate(client, url)
    assert _post(client).status_code == 409
    assert client.post(
        "/auth/mpin/step-up", json={"mpin": "1234", "action": _action()}
    ).status_code == 403

    # Start a clean enrolled authentication, then remove only the software proof.
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("truncate public.security_events,public.trusted_devices,public.users restart identity cascade")
    client.delete_cookie(auth_helpers.DEVICE_COOKIE_NAME)
    client.delete_cookie(auth_helpers.SESSION_TOKEN_COOKIE_NAME)
    client.delete_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME)
    _authenticate(client, url, with_mpin="1234")
    client.delete_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME)
    locked = _post(client)
    assert locked.status_code == 423
    assert locked.get_json()["code"] == "access_locked"
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*) from public.mpin_step_up_authorizations")
            assert cursor.fetchone()[0] == 0


def test_one_use_consume_fails_closed_across_every_binding(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    response = _post(client)
    proof = response.get_json()["authorization_proof"]
    descriptor = step_up_service.normalize_descriptor(_action())
    row = _ledger_row(url)
    binding = dict(
        raw_proof=proof, user_id=auth["user_id"], session_id=auth["session_id"],
        trusted_device_id=auth["device_id"],
        credential_generation=row["credential_generation"], descriptor=descriptor,
    )
    conn = psycopg2.connect(url)
    try:
        db = Db(conn)
        wrong = {**binding, "descriptor": step_up_service.normalize_descriptor(
            _action(amount_minor=12501)
        )}
        assert step_up_service.consume_authorization(db, **wrong) is None
        consumed = step_up_service.consume_authorization(db, **binding)
        assert consumed and consumed["state"] == "consumed"
        assert step_up_service.consume_authorization(db, **binding) is None
        conn.commit()
    finally:
        conn.close()


def test_concurrent_identical_issuance_returns_exactly_one_proof_and_row(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    descriptor = step_up_service.normalize_descriptor(_action())
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select credential_generation from public.mpin_credentials where user_id=%s",
                (auth["user_id"],),
            )
            generation = cursor.fetchone()[0]

    def issue():
        conn = psycopg2.connect(url)
        try:
            result = step_up_service.issue_authorization(
                Db(conn), user_id=auth["user_id"], session_id=auth["session_id"],
                trusted_device_id=auth["device_id"],
                credential_generation=generation, descriptor=descriptor,
            )
            conn.commit()
            return result
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: issue(), range(2)))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    assert len(winners[0]["proof"]) >= 43
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*) from public.mpin_step_up_authorizations")
            assert cursor.fetchone()[0] == 1


def test_expired_proof_cannot_refresh_and_transitions_once_to_expired(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    proof = _post(client).get_json()["authorization_proof"]
    row = _ledger_row(url)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "update public.mpin_step_up_authorizations set issued_at=issued_at-interval '4 minutes',expires_at=expires_at-interval '4 minutes' where authorization_id=%s",
                (row["authorization_id"],),
            )
    binding = dict(
        raw_proof=proof, user_id=auth["user_id"], session_id=auth["session_id"],
        trusted_device_id=auth["device_id"],
        credential_generation=row["credential_generation"],
        descriptor=step_up_service.normalize_descriptor(_action()),
    )
    conn = psycopg2.connect(url)
    try:
        assert step_up_service.consume_authorization(Db(conn), **binding) is None
        conn.commit()
    finally:
        conn.close()
    assert _ledger_row(url)["state"] == "expired"


def test_change_rolls_generation_and_invalidates_available_proof(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    issued = _post(client).get_json()
    before = _ledger_row(url)
    changed = client.post(
        "/auth/mpin/change",
        json={"current_mpin": "1234", "new_mpin": "5678"}, headers=_csrf(),
    )
    assert changed.status_code == 200
    after = _ledger_row(url)
    assert after["state"] == "invalidated"
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select credential_generation from public.mpin_credentials where user_id=%s",
                (auth["user_id"],),
            )
            new_generation = cursor.fetchone()[0]
    assert new_generation > before["credential_generation"]
    assert issued["authorization_proof"] not in repr(after)


def test_change_and_disable_wrong_mpin_share_the_canonical_failure_counter(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    changed = client.post(
        "/auth/mpin/change",
        json={"current_mpin": "9999", "new_mpin": "5678"}, headers=_csrf(),
    )
    disabled = client.post(
        "/auth/mpin/disable", json={"current_mpin": "9999"}, headers=_csrf(),
    )
    assert (changed.status_code, disabled.status_code) == (401, 401)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select failed_attempts,permanently_locked from public.mpin_credentials where user_id=%s",
                (auth["user_id"],),
            )
            assert cursor.fetchone() == (2, False)


def test_reset_disable_and_reenroll_each_invalidate_or_advance_generation(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    assert _post(client).status_code == 200
    first_generation = _ledger_row(url)["credential_generation"]
    reset = client.post(
        "/auth/mpin/reset",
        json={"new_mpin": "5678", "password": "valid"}, headers=_csrf(),
    )
    assert reset.status_code == 200
    assert _ledger_row(url)["state"] == "invalidated"
    assert _post(client, mpin="5678", action=_action(resource_id=42)).status_code == 200
    second = _ledger_row(url)
    assert second["credential_generation"] > first_generation
    disabled = client.post(
        "/auth/mpin/disable", json={"current_mpin": "5678"}, headers=_csrf(),
    )
    assert disabled.status_code == 200
    assert _ledger_row(url)["state"] == "invalidated"
    enrolled = client.post(
        "/auth/mpin/enroll",
        json={"mpin": "2468", "password": "valid"}, headers=_csrf(),
    )
    assert enrolled.status_code == 200
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select credential_generation from public.mpin_credentials where user_id=%s",
                (auth["user_id"],),
            )
            assert cursor.fetchone()[0] > second["credential_generation"]


def test_claim_and_reconciliation_are_one_shot_and_events_are_now_integrated(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    response = _post(client)
    proof = response.get_json()["authorization_proof"]
    row = _ledger_row(url)
    descriptor = step_up_service.normalize_descriptor(_action())
    binding = dict(raw_proof=proof, user_id=auth["user_id"],
                   session_id=auth["session_id"], trusted_device_id=auth["device_id"],
                   credential_generation=row["credential_generation"], descriptor=descriptor)
    conn = psycopg2.connect(url)
    try:
        db = Db(conn)
        claimed, claim = step_up_service.claim_authorization(db, **binding)
        assert step_up_service.claim_authorization(db, **binding) is None
        assert step_up_service.finalize_claim(
            db, authorization_id=claimed["authorization_id"], raw_claim="x" * 43,
            reconciliation_required=True,
        ) is None
        reconciled = step_up_service.finalize_claim(
            db, authorization_id=claimed["authorization_id"], raw_claim=claim,
            reconciliation_required=True,
        )
        assert reconciled["state"] == "reconciliation_required"
        assert step_up_service.finalize_claim(
            db, authorization_id=claimed["authorization_id"], raw_claim=claim,
        ) is None
        conn.commit()
    finally:
        conn.close()
    for name in (
        "security.mpin.step_up_consumed",
        "security.mpin.step_up_reconciliation_required",
    ):
        assert CATALOG[name].integrated
        assert get_writable_event_definition(name).integrated


def test_provider_rejection_is_definite_nonreplayable_invalidation(mpin_client):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    proof = _post(client).get_json()["authorization_proof"]
    row = _ledger_row(url)
    descriptor = step_up_service.normalize_descriptor(_action())
    binding = dict(
        raw_proof=proof,
        user_id=auth["user_id"],
        session_id=auth["session_id"],
        trusted_device_id=auth["device_id"],
        credential_generation=row["credential_generation"],
        descriptor=descriptor,
    )
    with psycopg2.connect(url) as conn:
        db = Db(conn)
        claimed, claim = step_up_service.claim_authorization(db, **binding)
        rejected = step_up_service.finalize_claim(
            db,
            authorization_id=claimed["authorization_id"],
            raw_claim=claim,
            provider_rejected=True,
        )
        assert rejected["state"] == "invalidated"
        assert rejected["invalidated_at"] is not None
        assert step_up_service.finalize_claim(
            db, authorization_id=claimed["authorization_id"], raw_claim=claim
        ) is None
        assert step_up_service.claim_authorization(db, **binding) is None


def test_provider_success_finalization_revalidates_auth_chain_and_exact_binding(
    mpin_client,
):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    proof = _post(client).get_json()["authorization_proof"]
    row = _ledger_row(url)
    descriptor = step_up_service.normalize_descriptor(_action())
    binding = dict(
        raw_proof=proof,
        user_id=auth["user_id"],
        session_id=auth["session_id"],
        trusted_device_id=auth["device_id"],
        credential_generation=row["credential_generation"],
        descriptor=descriptor,
    )
    with psycopg2.connect(url) as conn:
        db = Db(conn)
        claimed, claim = step_up_service.claim_authorization(db, **binding)
        with conn.cursor() as cursor:
            cursor.execute("select * from public.users where id=%s", (auth["user_id"],))
            columns = [item.name for item in cursor.description]
            user = dict(zip(columns, cursor.fetchone()))
        request_object = SimpleNamespace(
            current_user=user,
            current_session={"session_id": auth["session_id"]},
            cookies={
                auth_helpers.DEVICE_COOKIE_NAME: auth["device_raw"],
                auth_helpers.SESSION_TOKEN_COOKIE_NAME: auth["session_raw"],
                auth_helpers.ACCESS_PROOF_COOKIE_NAME: auth["proof_raw"],
            },
        )
        gate = step_up_service.ConsumptionGate(
            "authorized", authorization=dict(claimed), claim_proof=claim
        )
        wrong = step_up_service.normalize_descriptor(_action(amount_minor=12501))
        assert step_up_service.lock_and_finalize_current_request_claim(
            db, request_object, gate=gate, descriptor=wrong
        ) is None
        finalized = step_up_service.lock_and_finalize_current_request_claim(
            db, request_object, gate=gate, descriptor=descriptor
        )
        assert finalized["state"] == "consumed"


def test_provider_success_after_access_proof_rotation_requires_reconciliation(
    mpin_client,
):
    client, url = mpin_client
    auth = _authenticate(client, url, with_mpin="1234")
    proof = _post(client).get_json()["authorization_proof"]
    row = _ledger_row(url)
    descriptor = step_up_service.normalize_descriptor(_action())
    binding = dict(
        raw_proof=proof,
        user_id=auth["user_id"],
        session_id=auth["session_id"],
        trusted_device_id=auth["device_id"],
        credential_generation=row["credential_generation"],
        descriptor=descriptor,
    )
    with psycopg2.connect(url) as conn:
        db = Db(conn)
        claimed, claim = step_up_service.claim_authorization(db, **binding)
        conn.commit()
    with psycopg2.connect(url) as conn:
        conn.cursor().execute(
            "update public.user_sessions set access_proof_digest=%s where session_id=%s",
            (hashlib.sha256(b"rotated-proof-that-is-long-enough-0000").digest(), auth["session_id"]),
        )
    request_object = SimpleNamespace(
        current_user={"id": auth["user_id"]},
        current_session={"session_id": auth["session_id"]},
        cookies={
            auth_helpers.DEVICE_COOKIE_NAME: auth["device_raw"],
            auth_helpers.SESSION_TOKEN_COOKIE_NAME: auth["session_raw"],
            auth_helpers.ACCESS_PROOF_COOKIE_NAME: auth["proof_raw"],
        },
    )
    gate = step_up_service.ConsumptionGate(
        "authorized", authorization=dict(claimed), claim_proof=claim
    )
    with psycopg2.connect(url) as conn:
        db = Db(conn)
        assert step_up_service.lock_and_finalize_current_request_claim(
            db, request_object, gate=gate, descriptor=descriptor
        ) is None
        reconciled = step_up_service.finalize_claim(
            db,
            authorization_id=claimed["authorization_id"],
            raw_claim=claim,
            reconciliation_required=True,
        )
        assert reconciled["state"] == "reconciliation_required"


def test_forward_migration_converges_reapplies_and_rejects_corruption():
    url = require_test_db_url()
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert url != os.environ.get("SUPABASE_DB_URL", "").strip()
    child, cleanup = make_disposable(
        url, STUBS, origin_main_schema_or_skip(), MIGRATION.read_text(encoding="utf-8")
    )
    try:
        conn = psycopg2.connect(child)
        try:
            migration = MIGRATION.read_text(encoding="utf-8")
            with conn.cursor() as cursor:
                cursor.execute(migration)
                cursor.execute(
                    "select count(*),count(*) filter(where integrated),count(*) filter(where writable and not integrated) from public.canonical_event_catalog_projection"
                )
                assert cursor.fetchone() == (172, 23, 135)
                cursor.execute("select count(*) from public.mpin_step_up_authorizations")
                assert cursor.fetchone()[0] == 0
            conn.commit()
            with conn.cursor() as cursor:
                cursor.execute("alter table public.mpin_step_up_authorizations add column corrupt text")
            conn.commit()
            with pytest.raises((psycopg2.Error, errors.ObjectNotInPrerequisiteState)):
                with conn.cursor() as cursor:
                    cursor.execute(migration)
            conn.rollback()
        finally:
            conn.close()
    finally:
        cleanup()
