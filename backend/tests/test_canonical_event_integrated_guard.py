"""Forward-only proof for the Phase 1B-2A integrated catalog guard."""

import hashlib
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import errors
import pytest

from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from tests.test_canonical_event_acl_hardening import _semantic_signature


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO_ROOT / "supabase" / "migrations" / "20260801110000_canonical_event_integrated_guard.sql"
)
EXPECTED_PRE_SIGNATURE = "f5168975e0605fe0f7b84c1276a0082a"
EXPECTED_POST_SIGNATURE = "7b8157021244549cfed79416b40ab662"
PRE_GUARD_SCHEMA_SHA = "7e6f154be7227317a83cbfbb2f088ac306cd578b"
POST_GUARD_SCHEMA_SHA = "4f6be1035a8b9b80a0c474eb157b4a7c48c4bb2d"
LOCKED_HASHES = {
    "supabase/migrations/20260731230000_canonical_event_foundation.sql": (
        "9D9C7A9AA8C674EE1A58A96C7AC5ECE831D51C0EABF4C96BD81B37EB79093151"
    ),
    "supabase/migrations/20260731240000_canonical_event_acl_hardening.sql": (
        "AD2C21874AA3401B081534E56EB4FE18085DC6CCC39C9CCB47AB992BF49D5348"
    ),
    "supabase/migrations/20260801100000_security_login_event_integration.sql": (
        "24B9E78501E57DEE56B3E53155A2A2EE248607D12056362723ADF375519ACBC7"
    ),
}


def _local_url():
    url = require_test_db_url()
    parsed = urlsplit(url)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert parsed.path.lstrip("/").startswith("dtx_phase1b2c0_")
    assert url != os.environ.get("SUPABASE_DB_URL", "").strip()
    return url


def _pre_guard_schema():
    """Return the immutable Phase 1B-2A activation state, never mutable main."""
    return subprocess.check_output(
        ["git", "show", f"{PRE_GUARD_SCHEMA_SHA}:supabase/schema.sql"],
        cwd=REPO_ROOT,
        text=True,
    )


def _post_guard_schema():
    """Return the immutable final state of this migration, never mutable main."""
    return subprocess.check_output(
        ["git", "show", f"{POST_GUARD_SCHEMA_SHA}:supabase/schema.sql"],
        cwd=REPO_ROOT,
        text=True,
    )


def _insert_integrated_event(conn, request_id):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            insert into public.security_events
                (event_name, event_version, category, actor_type, request_id,
                 source, provider_mode, environment, retention_class)
            values
                ('security.login.started', 1, 'security', 'anonymous', %s,
                 'test', 'none', 'test', 'security_12_months')
            """,
            (request_id,),
        )
    conn.commit()


def test_applied_migrations_remain_byte_identical_in_git():
    for path, expected in LOCKED_HASHES.items():
        if path.endswith("20260801100000_security_login_event_integration.sql"):
            content = subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=REPO_ROOT)
        else:
            # The two older files have their locked CRLF checkout bytes; Git
            # stores their normalized blobs, so inspect the immutable checkout.
            content = (REPO_ROOT / path).read_bytes()
        assert hashlib.sha256(content).hexdigest().upper() == expected


def test_integrated_guard_migration_converges_and_is_idempotent_after_event_rows():
    migration = MIGRATION.read_text(encoding="utf-8")
    observed = []
    for blocks, needs_migration in (
        ((STUBS, _pre_guard_schema()), True),
        ((STUBS, _post_guard_schema()), False),
    ):
        url, cleanup = make_disposable(_local_url(), *blocks)
        try:
            conn = psycopg2.connect(url)
            try:
                assert _semantic_signature(conn) == (
                    EXPECTED_PRE_SIGNATURE if needs_migration else EXPECTED_POST_SIGNATURE
                )
                if needs_migration:
                    with conn.cursor() as cursor:
                        cursor.execute(migration)
                    conn.commit()
                _insert_integrated_event(conn, "request.integrated.guard.idempotent")
                for _ in range(2):
                    with conn.cursor() as cursor:
                        cursor.execute(migration)
                    conn.commit()
                with conn.cursor() as cursor:
                    cursor.execute(
                        "select count(*) from public.security_events where event_name='security.login.started'"
                    )
                    rows = cursor.fetchone()[0]
                observed.append((_semantic_signature(conn), rows))
            finally:
                conn.close()
        finally:
            cleanup()
    assert observed == [(EXPECTED_POST_SIGNATURE, 1), (EXPECTED_POST_SIGNATURE, 1)]


def test_integrated_guard_rejects_partial_state_without_repair():
    url, cleanup = make_disposable(_local_url(), STUBS, _pre_guard_schema())
    try:
        conn = psycopg2.connect(url)
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute("alter table public.security_events disable trigger trg_security_events_contract")
            before = _semantic_signature(conn)
            assert before != EXPECTED_PRE_SIGNATURE
            with pytest.raises((psycopg2.Error, errors.RaiseException)):
                with conn.cursor() as cursor:
                    cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            conn.rollback()
            assert _semantic_signature(conn) == before
            with conn.cursor() as cursor:
                cursor.execute(
                    "select tgenabled from pg_trigger where tgname='trg_security_events_contract'"
                )
                assert cursor.fetchone()[0] == "D"
        finally:
            conn.close()
    finally:
        cleanup()
