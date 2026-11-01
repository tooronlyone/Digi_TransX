"""Phase 1B-2C2 trusted-device hardening proofs."""

import hashlib
import os
import subprocess
from pathlib import Path

import psycopg2
from psycopg2 import errors
import pytest
from flask import Flask

from auth import trusted_device_service as service
from auth.routes import auth_blueprint
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20260801160000_trusted_device_hardening.sql"
LEGACY_SCHEMA = subprocess.check_output(
    ["git", "show", "eb10d8eff93499a67e424bea5a60fd0245d46c4f^:supabase/schema.sql"],
    cwd=ROOT,
    text=True,
)


def _url():
    url = require_test_db_url()
    assert "127.0.0.1" in url or "localhost" in url
    assert url != os.environ.get("SUPABASE_DB_URL")
    return url


def _columns(conn):
    with conn.cursor() as cur:
        cur.execute("""select column_name,data_type,is_nullable from information_schema.columns
                        where table_schema='public' and table_name='trusted_devices'
                        order by column_name""")
        return cur.fetchall()


def test_fresh_and_sequential_schema_converge_and_reapply_exactly():
    sequential, clean_seq = make_disposable(_url(), STUBS, LEGACY_SCHEMA)
    fresh, clean_fresh = make_disposable(_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    sql = MIGRATION.read_text(encoding="utf-8")
    try:
        with psycopg2.connect(sequential) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(sql)
        with psycopg2.connect(sequential) as a, psycopg2.connect(fresh) as b:
            assert _columns(a) == _columns(b)
            assert [c[0] for c in _columns(a)] == sorted([
                "id", "token_digest", "previous_token_digest", "user_id", "created_at", "last_used_at",
                "expires_at", "revoked_at", "rotated_at",
            ])
    finally:
        clean_seq(); clean_fresh()


def test_eligible_legacy_token_is_hashed_without_changing_owner_or_id():
    url, cleanup = make_disposable(_url(), STUBS, LEGACY_SCHEMA)
    raw = "A" * 43
    try:
        with psycopg2.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("insert into public.users(full_name,email,cnic,role) values ('x','x@example.test','1111111111111','customer') returning id")
                user_id = cur.fetchone()[0]
                cur.execute("insert into public.trusted_devices(device_token,user_id) values (%s,%s) returning id", (raw,user_id))
                device_id = cur.fetchone()[0]
                cur.execute(MIGRATION.read_text(encoding="utf-8"))
                cur.execute("select id,user_id,token_digest,expires_at>created_at from public.trusted_devices")
                row = cur.fetchone()
                assert (row[0], row[1], bytes(row[2]), row[3]) == (
                    device_id, user_id, hashlib.sha256(raw.encode()).digest(), True
                )
    finally:
        cleanup()


@pytest.mark.parametrize("bad", [None, "weak"])
def test_invalid_legacy_state_aborts_atomically(bad):
    url, cleanup = make_disposable(_url(), STUBS, LEGACY_SCHEMA)
    try:
        with psycopg2.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("insert into public.users(full_name,email,cnic,role) values ('x','x@example.test','1111111111111','customer') returning id")
                user_id = cur.fetchone()[0]
                if bad is None:
                    cur.execute("alter table public.trusted_devices alter column device_token drop not null")
                cur.execute("insert into public.trusted_devices(device_token,user_id) values (%s,%s)", (bad,user_id))
            conn.commit()
            with pytest.raises(psycopg2.Error):
                with conn.cursor() as cur:
                    cur.execute(MIGRATION.read_text(encoding="utf-8"))
            conn.rollback()
            assert any(c[0] == "device_token" for c in _columns(conn))
            assert not any(c[0] == "token_digest" for c in _columns(conn))
    finally:
        cleanup()


def test_final_acl_digest_shape_and_duplicate_rejection():
    url, cleanup = make_disposable(_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        with psycopg2.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("select count(*) from information_schema.column_privileges where table_schema='public' and table_name='trusted_devices' and grantee in ('PUBLIC','anon','authenticated')")
                assert cur.fetchone()[0] == 0
                cur.execute("select array_agg(privilege_type order by privilege_type) from information_schema.role_table_grants where table_schema='public' and table_name='trusted_devices' and grantee='service_role'")
                assert cur.fetchone()[0] == "{DELETE,INSERT,SELECT,UPDATE}"
                cur.execute("insert into public.users(full_name,email,cnic,role) values ('x','x@example.test','1111111111111','customer') returning id")
                uid = cur.fetchone()[0]
                digest = b"x" * 32
                cur.execute("insert into public.trusted_devices(token_digest,user_id) values (%s,%s)", (digest,uid))
                with pytest.raises(errors.UniqueViolation):
                    cur.execute("insert into public.trusted_devices(token_digest,user_id) values (%s,%s)", (digest,uid))
            conn.rollback()
    finally:
        cleanup()


def test_token_contract_and_lifetime(monkeypatch):
    raw = service.generate_raw_token()
    assert len(hashlib.sha256(raw.encode()).digest()) == 32
    assert len(service.digest_token(raw)) == 32
    monkeypatch.setenv("DIGITRANSX_TRUSTED_DEVICE_DAYS", "31")
    with pytest.raises(service.TrustedDeviceError):
        service.trusted_device_lifetime_days()


def test_legacy_mpin_routes_fail_closed_and_clear_cookie():
    app = Flask(__name__)
    app.secret_key = "test-only"
    app.config["SESSION_COOKIE_SECURE"] = False
    app.register_blueprint(auth_blueprint)
    client = app.test_client()
    client.set_cookie("dtx_device_token", "A" * 43)
    options = client.get("/auth/fast-login/options")
    assert options.status_code == 200 and options.get_json() == {"success": True, "available": False}
    response = client.post("/auth/fast-login/mpin", json={"mpin": "1234"})
    assert response.status_code == 401
    assert response.get_json() == {"success": False, "message": "Full login is required."}
    assert any("dtx_device_token=;" in value and "HttpOnly" in value and "SameSite=Lax" in value for value in response.headers.getlist("Set-Cookie"))
