"""Caller-transaction canonical event writers.

These writers never open a database connection and never commit or roll back.
The caller's authoritative mutation and event evidence therefore share one
transaction. Phase 1B-2A uses the security writer only from the bounded password
login/logout route integration.
"""

from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from .catalog import BUSINESS_AUDIT, SECURITY, get_writable_event_definition
from .contract import EventContext, EventData, validate_envelope_inputs
from .environment import derive_server_environment


_IDEMPOTENCY_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")


class EventIdempotencyConflict(ValueError):
    pass


@dataclass(frozen=True)
class EventWriteResult:
    event: dict
    replayed: bool


def _execute_fetchone(executor, statement, values):
    """Support both the production Db wrapper and a native psycopg2 cursor."""
    result = executor.execute(statement, values)
    return (executor if result is None else result).fetchone()


def _validate_idempotency(scope, key):
    if scope is None and key is None:
        return None, None
    if (
        not isinstance(scope, str)
        or not isinstance(key, str)
        or not _IDEMPOTENCY_RE.fullmatch(scope)
        or not _IDEMPOTENCY_RE.fullmatch(key)
    ):
        raise ValueError("Idempotency scope and key must be supplied together in canonical format.")
    return scope, key


def _fingerprint(envelope, environment):
    material = {**envelope, "environment": environment}
    encoded = json.dumps(
        material, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_event(
    executor,
    table,
    expected_category,
    event_name,
    context,
    data,
    idempotency_scope,
    idempotency_key,
):
    definition = get_writable_event_definition(event_name, expected_category)
    checked_definition, envelope = validate_envelope_inputs(event_name, context, data)
    if checked_definition != definition:
        raise RuntimeError("Canonical catalog lookup drift.")
    scope, key = _validate_idempotency(idempotency_scope, idempotency_key)
    environment = derive_server_environment()
    fingerprint = _fingerprint(envelope, environment)
    event_id = str(uuid.uuid4())

    related = envelope["related_entities"]
    columns = (
        "event_id",
        "event_name",
        "event_version",
        "category",
        "actor_type",
        "actor_id",
        "actor_role",
        "subject_user_id",
        *related.keys(),
        "request_id",
        "correlation_id",
        "session_ref",
        "device_ref",
        "source",
        "provider_mode",
        "environment",
        "before_state",
        "after_state",
        "reason_code",
        "metadata",
        "retention_class",
        "consent_category",
        "idempotency_scope",
        "idempotency_key",
        "fingerprint",
    )
    values = (
        event_id,
        envelope["event_name"],
        envelope["event_version"],
        envelope["category"],
        envelope["actor_type"],
        envelope["actor_id"],
        envelope["actor_role"],
        envelope["subject_user_id"],
        *related.values(),
        envelope["request_id"],
        envelope["correlation_id"],
        envelope["session_ref"],
        envelope["device_ref"],
        envelope["source"],
        envelope["provider_mode"],
        environment,
        json.dumps(envelope["before_state"], separators=(",", ":"), sort_keys=True),
        json.dumps(envelope["after_state"], separators=(",", ":"), sort_keys=True),
        envelope["reason_code"],
        json.dumps(envelope["metadata"], separators=(",", ":"), sort_keys=True),
        envelope["retention_class"],
        envelope["consent_category"],
        scope,
        key,
        fingerprint if key is not None else None,
    )
    placeholders = ", ".join(["%s"] * len(columns))
    sql = (
        f"INSERT INTO public.{table} ({', '.join(columns)}) VALUES ({placeholders}) "
        "ON CONFLICT (idempotency_scope, idempotency_key) "
        "WHERE idempotency_key IS NOT NULL DO NOTHING RETURNING *"
    )
    inserted = _execute_fetchone(executor, sql, values)
    if inserted:
        return EventWriteResult(event=dict(inserted), replayed=False)
    if key is None:
        raise RuntimeError("Canonical event insert returned no row.")
    existing = _execute_fetchone(
        executor,
        f"SELECT * FROM public.{table} "
        "WHERE idempotency_scope = %s AND idempotency_key = %s",
        (scope, key),
    )
    if not existing or existing["fingerprint"] != fingerprint:
        raise EventIdempotencyConflict(
            "Idempotency key was already used for a different canonical event."
        )
    return EventWriteResult(event=dict(existing), replayed=True)


def write_security_event(
    executor,
    event_name,
    context: EventContext,
    data: EventData | None = None,
    *,
    idempotency_scope=None,
    idempotency_key=None,
):
    return _write_event(
        executor,
        "security_events",
        SECURITY,
        event_name,
        context,
        data,
        idempotency_scope,
        idempotency_key,
    )

def write_business_audit_event(
    executor,
    event_name,
    context: EventContext,
    data: EventData | None = None,
    *,
    idempotency_scope=None,
    idempotency_key=None,
):
    return _write_event(
        executor,
        "business_audit_events",
        BUSINESS_AUDIT,
        event_name,
        context,
        data,
        idempotency_scope,
        idempotency_key,
    )
