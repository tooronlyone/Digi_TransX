"""Focused PostgreSQL proof for Phase 1B-2C0 catalog-contract convergence."""

import os
import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import errors
import pytest

from events.catalog import CATALOG, INTEGRATED_EVENT_NAMES, catalog_projection_rows
from events.contract import EventContext, EventContractError, EventData, validate_catalog_event_contract
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260801140000_device_session_mpin_event_contracts.sql"
PRE_SCHEMA_REF = "9944bd5fa6c8acbe790e55c39edc8b3b951c6ef8:supabase/schema.sql"
PRE_SIGNATURE = "371c7010a0553c7953708dea164ed0bc"
POST_SIGNATURE = "3d9b730408336c82629c25342ddc7ea2"
NEW_EVENTS = {
    "security.session.issued", "security.session.access_locked", "security.trusted_device.rotated",
    "security.mpin.enrolled", "security.mpin.changed", "security.mpin.disabled",
    "security.mpin.unlock_succeeded", "security.mpin.unlock_failed", "security.mpin.locked",
    "security.mpin.reset_completed", "security.mpin.step_up_succeeded", "security.mpin.step_up_failed",
}
FORMALIZED_EVENTS = {
    "security.session.refreshed", "security.session.expired_inactivity", "security.session.revoked",
    "security.trusted_device.added", "security.trusted_device.removed",
}


def _local_url():
    url = require_test_db_url()
    assert url != os.environ.get("SUPABASE_DB_URL", "").strip()
    assert urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"}
    return url


def _schema_at(ref):
    return subprocess.check_output(["git", "show", ref], cwd=REPO_ROOT, text=True)


def _signature_function_sql():
    text = MIGRATION.read_text(encoding="utf-8")
    return text[text.index("create or replace function pg_temp.canonical_event_semantic_signature()"):text.index("\ndo $migration$")]


def _signature(conn):
    with conn.cursor() as cursor:
        cursor.execute(_signature_function_sql())
        cursor.execute("select pg_temp.canonical_event_semantic_signature()")
        return cursor.fetchone()[0]


def _projection(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            "select event_name,event_version,category,ownership_domain,retention_class,"
            "lifecycle_status,writable,integrated,event_contract from "
            "public.canonical_event_catalog_projection order by event_name"
        )
        return [(*row[:8], row[8]) for row in cursor.fetchall()]


def _expected_projection():
    return [(*row[:8], row[8]) for row in catalog_projection_rows()]


def _context(policy):
    if policy == "service_subject":
        return EventContext("slice2.service", "test", "system", subject_user_id=23)
    return EventContext("slice2.user", "test", "user", actor_id=23, actor_role="user", subject_user_id=23)


def _metadata(definition):
    values = {
        "result_code": sorted(definition.allowed_result_codes or ("invalid_mpin",))[0],
        "authorization_ref": "authorization_" + "a" * 32,
        "action_key": "agreement.finalize",
        "resource_type": "agreement",
        "resource_id": 23,
        "request_fingerprint_ref": "request_" + "b" * 64,
    }
    return {key: values[key] for key in definition.allowed_metadata_keys}


def test_python_contracts_are_complete_and_sensitive_metadata_is_rejected():
    assert len(CATALOG) == 172
    assert sum(item.lifecycle_status == "planned" for item in CATALOG.values()) == 164
    assert sum(item.writable for item in CATALOG.values()) == 158
    assert sum(item.integrated for item in CATALOG.values()) == 25
    assert NEW_EVENTS | FORMALIZED_EVENTS <= set(CATALOG)
    for name in NEW_EVENTS | FORMALIZED_EVENTS:
        definition = CATALOG[name]
        data = EventData(metadata=_metadata(definition))
        validate_catalog_event_contract(name, _context(definition.actor_policy), data)
        with pytest.raises(EventContractError):
            validate_catalog_event_contract(name, _context(definition.actor_policy), EventData(metadata={"email": "x"}))
    with pytest.raises(EventContractError):
        validate_catalog_event_contract("security.mpin.unlock_failed", _context("authenticated_self"), EventData(metadata={"result_code": "invalid_mpin"}))
    with pytest.raises(EventContractError):
        validate_catalog_event_contract("security.mpin.unlock_failed", _context("service_subject"), EventData(metadata={"result_code": "wrong"}))


def test_projection_migration_converges_is_idempotent_and_rejects_drift():
    sequential_url, sequential_cleanup = make_disposable(_local_url(), STUBS, _schema_at(PRE_SCHEMA_REF))
    fresh_url, fresh_cleanup = make_disposable(
        _local_url(), STUBS, _schema_at(PRE_SCHEMA_REF), MIGRATION.read_text(encoding="utf-8")
    )
    try:
        sequential = psycopg2.connect(sequential_url)
        fresh = psycopg2.connect(fresh_url)
        try:
            assert _signature(sequential) == PRE_SIGNATURE
            with sequential.cursor() as cursor:
                cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            sequential.commit()
            assert _signature(sequential) == POST_SIGNATURE == _signature(fresh)
            # This migration's exact historical post-state intentionally has seven
            # integrated events; the current Python catalog advances to ten in 2C2.
            assert _projection(sequential) == _projection(fresh)
            for _ in range(2):
                with sequential.cursor() as cursor:
                    cursor.execute(MIGRATION.read_text(encoding="utf-8"))
                sequential.commit()
            with fresh.cursor() as cursor:
                cursor.execute("alter table public.security_events disable trigger trg_security_events_contract")
            fresh.commit()
            with pytest.raises((psycopg2.Error, errors.RaiseException)):
                with fresh.cursor() as cursor:
                    cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            fresh.rollback()
        finally:
            sequential.close()
            fresh.close()
    finally:
        sequential_cleanup()
        fresh_cleanup()


def test_direct_sql_accepts_only_existing_integrated_events():
    url, cleanup = make_disposable(_local_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cursor:
                for index, definition in enumerate(sorted(
                    (item for item in CATALOG.values() if item.integrated),
                    key=lambda item: item.name,
                )):
                    name = definition.name
                    service = definition.actor_policy == "service_subject"
                    authenticated = definition.actor_policy in {
                        "authenticated_self", "authenticated_self_or_service"
                    }
                    metadata = json.dumps(_metadata(definition))
                    cursor.execute(
                        "insert into public.security_events (event_name,event_version,category,actor_type,actor_id,actor_role,subject_user_id,request_id,source,provider_mode,environment,retention_class,metadata) values (%s,1,'security',%s,%s,%s,%s,%s,'test','none','test','security_12_months',%s::jsonb)",
                        (
                            name,
                            'system' if service else ('user' if authenticated else 'anonymous'),
                            1 if authenticated else None,
                            'service_seeker' if authenticated else None,
                            1 if (service or authenticated) else None,
                            f"slice2.accepted.{index}",
                            metadata,
                        ),
                    )
            conn.commit()
            rejected_names = (
                NEW_EVENTS | FORMALIZED_EVENTS | {
                    "security.signup.gps_result_recorded", "security.login.email_otp_sent",
                    "system.job.started", "one_time.qr_payment.intent_created",
                }
            ) - set(INTEGRATED_EVENT_NAMES)
            for index, name in enumerate(sorted(rejected_names)):
                with pytest.raises(errors.CheckViolation):
                    with conn.cursor() as cursor:
                        cursor.execute("savepoint reject_event")
                        cursor.execute("insert into public.security_events (event_name,event_version,category,actor_type,request_id,source,provider_mode,environment,retention_class) values (%s,1,'security','anonymous',%s,'test','none','test','security_12_months')", (name, f"slice2.reject.{index}"))
                conn.rollback()
        finally:
            conn.close()
    finally:
        cleanup()
