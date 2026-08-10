"""Phase 1B-2C1 durable server-session foundation proofs."""

import hashlib
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import errors
import pytest

from auth import session_service
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.test_canonical_event_acl_hardening import _semantic_signature as event_signature


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260801150000_durable_server_session_foundation.sql"
LOCKED_MAIN = "72316b0e568c388cf0c35366db49d4ed98cf4f28"
PRE_SCHEMA_REF = f"{LOCKED_MAIN}:supabase/schema.sql"
EVENT_SIGNATURE = "3d9b730408336c82629c25342ddc7ea2"


def _local_url():
    url = require_test_db_url()
    assert url != os.environ.get("SUPABASE_DB_URL", "").strip()
    assert urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"}
    return url


def _schema_at(ref):
    return subprocess.check_output(["git", "show", ref], cwd=REPO_ROOT, text=True)


def _foundation_signature(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            with items as (
                select format('column|%s|%s|%s|%s|%s', a.attnum, a.attname,
                    format_type(a.atttypid,a.atttypmod), a.attnotnull,
                    coalesce(pg_get_expr(d.adbin,d.adrelid),'')) item
                  from pg_attribute a left join pg_attrdef d
                    on d.adrelid=a.attrelid and d.adnum=a.attnum
                 where a.attrelid='public.user_sessions'::regclass
                   and a.attnum>0 and not a.attisdropped
                union all
                select format('constraint|%s|%s',c.conname,pg_get_constraintdef(c.oid,false))
                  from pg_constraint c where c.conrelid in
                    ('public.user_sessions'::regclass,'public.trusted_devices'::regclass)
                   and (c.conrelid='public.user_sessions'::regclass
                        or c.conname='trusted_devices_session_owner_unique')
                union all
                select format('index|%s|%s',indexname,indexdef) from pg_indexes
                 where schemaname='public' and tablename='user_sessions'
                union all
                select format('rls|%s|%s',relrowsecurity,relforcerowsecurity)
                  from pg_class where oid='public.user_sessions'::regclass
                union all
                select format('policy|%s|%s|%s|%s',policyname,roles,cmd,
                    coalesce(qual,'')||'|'||coalesce(with_check,''))
                  from pg_policies where schemaname='public' and tablename='user_sessions'
                union all
                select format('grant|%s|%s',grantee,privilege_type)
                  from information_schema.table_privileges
                 where table_schema='public' and table_name='user_sessions'
                   and grantee <> current_user
            ) select md5(string_agg(item,E'\n' order by item)) from items
            """
        )
        return cursor.fetchone()[0]


class _Result:
    rowcount = 1

    def fetchone(self):
        return {"session_id": "session-id"}


class _Executor:
    def __init__(self):
        self.calls = []

    def execute(self, statement, values=()):
        self.calls.append((statement, values))
        return _Result()


def test_service_hashes_tokens_and_is_the_only_runtime_route_owner(monkeypatch):
    raw = "A" * 43
    assert session_service.digest_opaque_token(raw) == hashlib.sha256(raw.encode()).digest()
    assert len(session_service.digest_opaque_token(raw)) == 32
    for invalid in (None, "short", "x" * 513):
        with pytest.raises(session_service.SessionFoundationError):
            session_service.digest_opaque_token(invalid)

    executor = _Executor()
    monkeypatch.setattr(session_service, "generate_opaque_token", lambda: raw)
    monkeypatch.setattr(session_service, "generate_access_proof", lambda: raw)
    returned, access_proof, session_id = session_service.create_session(
        executor, 7, trusted_device_id=9
    )
    assert returned == raw and access_proof == raw and session_id == "session-id"
    statement, values = executor.calls[0]
    assert raw not in statement and raw not in values
    assert values == (
        7,
        hashlib.sha256(raw.encode()).digest(),
        9,
        session_service.INACTIVITY_DAYS,
        session_service.ABSOLUTE_LIFETIME_DAYS,
        hashlib.sha256(raw.encode()).digest(),
        session_service.ACCESS_PROOF_LIFETIME_HOURS,
    )

    route_text = (REPO_ROOT / "backend" / "auth" / "routes.py").read_text(encoding="utf-8")
    helper_text = (REPO_ROOT / "backend" / "auth" / "helpers.py").read_text(encoding="utf-8")
    assert "from auth.session_service import" in route_text
    assert "from auth.session_service import" in helper_text
    assert "secrets.token_urlsafe" not in route_text
    assert "hashlib.sha256" not in route_text
    assert "hashlib.sha256" not in helper_text


def test_fresh_sequential_and_exact_reapplication_converge():
    sequential_url, sequential_cleanup = make_disposable(_local_url(), STUBS, _schema_at(PRE_SCHEMA_REF))
    fresh_url, fresh_cleanup = make_disposable(
        _local_url(), STUBS, _schema_at(PRE_SCHEMA_REF), MIGRATION.read_text(encoding="utf-8")
    )
    try:
        sequential = psycopg2.connect(sequential_url)
        fresh = psycopg2.connect(fresh_url)
        try:
            assert event_signature(sequential) == EVENT_SIGNATURE
            with sequential.cursor() as cursor:
                cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            sequential.commit()
            assert event_signature(sequential) == EVENT_SIGNATURE == event_signature(fresh)
            assert _foundation_signature(sequential) == _foundation_signature(fresh)
            for connection in (sequential, fresh):
                with connection.cursor() as cursor:
                    cursor.execute("select count(*) from public.user_sessions")
                    assert cursor.fetchone()[0] == 0
                    cursor.execute(MIGRATION.read_text(encoding="utf-8"))
                    cursor.execute(MIGRATION.read_text(encoding="utf-8"))
                connection.commit()
            assert _foundation_signature(sequential) == _foundation_signature(fresh)
        finally:
            sequential.close()
            fresh.close()
    finally:
        sequential_cleanup()
        fresh_cleanup()


def test_constraints_indexes_rls_and_minimum_privileges():
    url, cleanup = make_disposable(_local_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cursor:
                cursor.execute("insert into auth.users(id,email) values (gen_random_uuid(),'session-owner@example.invalid') returning id")
                auth_id = cursor.fetchone()[0]
                cursor.execute("select id from public.users where auth_id=%s", (auth_id,))
                user_id = cursor.fetchone()[0]
                cursor.execute("insert into public.users(email,cnic) values ('other@example.invalid','session-other') returning id")
                other_id = cursor.fetchone()[0]
                cursor.execute("insert into public.trusted_devices(token_digest,user_id) values (%s,%s) returning id", (b'd'*32,user_id))
                device_id = cursor.fetchone()[0]
                cursor.execute("insert into public.trusted_devices(token_digest,user_id) values (%s,%s) returning id", (b'e'*32,other_id))
                other_device_id = cursor.fetchone()[0]
                cursor.execute("select relrowsecurity from pg_class where oid='public.user_sessions'::regclass")
                assert cursor.fetchone()[0] is True
                cursor.execute("select indexname from pg_indexes where tablename='user_sessions'")
                indexes = {row[0] for row in cursor.fetchall()}
                assert {'idx_user_sessions_active_token','idx_user_sessions_user_revocable'} <= indexes
                cursor.execute("select privilege_type from information_schema.role_table_grants where table_name='user_sessions' and grantee='service_role'")
                assert {row[0] for row in cursor.fetchall()} == {'SELECT','INSERT','UPDATE'}
            conn.commit()

            digest = b"a" * 32
            with conn.cursor() as cursor:
                cursor.execute("insert into public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at) values (%s,%s,%s,now()+interval '7 days',now()+interval '30 days')", (user_id,digest,device_id))
            conn.commit()
            for statement, values, expected in (
                ("insert into public.user_sessions(user_id,token_digest,inactivity_expires_at,absolute_expires_at) values (%s,%s,now()+interval '7 days',now()+interval '30 days')", (user_id,digest), errors.UniqueViolation),
                ("insert into public.user_sessions(user_id,token_digest,inactivity_expires_at,absolute_expires_at) values (%s,%s,now()+interval '7 days',now()+interval '30 days')", (user_id,b'short'), errors.CheckViolation),
                ("insert into public.user_sessions(user_id,token_digest,trusted_device_id,inactivity_expires_at,absolute_expires_at) values (%s,%s,%s,now()+interval '7 days',now()+interval '30 days')", (user_id,b'b'*32,other_device_id), errors.ForeignKeyViolation),
                ("insert into public.user_sessions(user_id,token_digest,inactivity_expires_at,absolute_expires_at,access_locked) values (%s,%s,now()+interval '7 days',now()+interval '30 days',true)", (user_id,b'c'*32), errors.CheckViolation),
                ("insert into public.user_sessions(user_id,token_digest,inactivity_expires_at,absolute_expires_at,revoked_at,revocation_reason) values (%s,%s,now()+interval '7 days',now()+interval '30 days',now(),'unbounded')", (user_id,b'd'*32), errors.CheckViolation),
            ):
                with pytest.raises(expected):
                    with conn.cursor() as cursor:
                        cursor.execute(statement, values)
                conn.rollback()

            for role in ('anon','authenticated'):
                with pytest.raises(errors.InsufficientPrivilege):
                    with conn.cursor() as cursor:
                        cursor.execute(f"set local role {role}")
                        cursor.execute("select * from public.user_sessions")
                conn.rollback()
            with conn.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute("select count(*) from public.user_sessions")
                assert cursor.fetchone()[0] == 1
                with pytest.raises(errors.InsufficientPrivilege):
                    cursor.execute("delete from public.user_sessions")
            conn.rollback()
        finally:
            conn.close()
    finally:
        cleanup()


@pytest.mark.parametrize(
    "corruption",
    [
        "alter table public.user_sessions drop constraint user_sessions_token_digest_shape",
        "alter table public.user_sessions add column unexpected_state text",
        "alter table public.user_sessions alter column token_version set default 2",
        "alter table public.user_sessions drop constraint user_sessions_timestamp_order; alter table public.user_sessions add constraint user_sessions_timestamp_order check (true)",
        "alter table public.user_sessions disable row level security",
        "grant select on public.user_sessions to authenticated",
    ],
)
def test_partial_or_corrupt_states_abort_atomically(corruption):
    url, cleanup = make_disposable(_local_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cursor:
                cursor.execute(corruption)
            conn.commit()
            before = _foundation_signature(conn)
            with pytest.raises((psycopg2.Error, errors.RaiseException)):
                with conn.cursor() as cursor:
                    cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            conn.rollback()
            assert _foundation_signature(conn) == before
            with conn.cursor() as cursor:
                cursor.execute("select count(*) from public.user_sessions")
                assert cursor.fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        cleanup()


def test_migration_has_no_forbidden_data_or_catalog_changes():
    text = MIGRATION.read_text(encoding="utf-8").lower()
    assert "cascade" not in text
    assert "canonical_event_catalog_projection" not in text
    assert "insert into public.user_sessions" not in text
    assert not any(name in text for name in (
        "password_hash", "mpin_hash", "otp_hash", "csrf_token",
        "auth_access_token", "refresh_token", "payment_pan", "payment_cvc",
        "metadata json",
    ))
    assert MIGRATION.name > "20260801140000_device_session_mpin_event_contracts.sql"
