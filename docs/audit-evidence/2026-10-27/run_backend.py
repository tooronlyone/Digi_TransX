"""Reproduce the audit on disposable local PostgreSQL (port 15479) only.

Start an empty test cluster first. Never loads a remote database URL.
The suite owns its disposable child databases; this runner owns the base.
"""
import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import parse_dsn

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "backend"))
PORT = "15479"
BASE = "dtx_phase1b2c0_review_" + uuid4().hex[:12]
ADMIN = f"postgresql://postgres@127.0.0.1:{PORT}/postgres"
original_connect = psycopg2.connect


def local_connect(dsn=None, *args, **kwargs):
    options = parse_dsn(dsn) if dsn else {}
    options.update(kwargs)
    if options.get("host") != "127.0.0.1" or str(options.get("port")) != PORT:
        raise RuntimeError("Audit permits only its dedicated loopback PostgreSQL cluster.")
    return original_connect(dsn, *args, **kwargs)


psycopg2.connect = local_connect
os.environ.update(
    TEST_SUPABASE_DB_URL=f"postgresql://postgres@127.0.0.1:{PORT}/{BASE}",
    TEST_LOCAL_MAINTENANCE_DB_URL=ADMIN,
    SUPABASE_DB_URL="postgresql://invalid@127.0.0.1:1/disabled",
    SUPABASE_URL="http://127.0.0.1:1",
    SUPABASE_SERVICE_ROLE_KEY="audit-invalid-local-only",
    DIGITRANSX_ENVIRONMENT="test",
    DTX_SHARED_TEST_HARNESS="0",
    PGAPPNAME=BASE,
)

admin = local_connect(ADMIN)
admin.autocommit = True
with admin.cursor() as cur:
    cur.execute(sql.SQL("CREATE DATABASE {} OWNER postgres").format(sql.Identifier(BASE)))
try:
    import pytest
    result = pytest.main(sys.argv[1:] or ["backend/tests", "-q", "--tb=short"])
finally:
    with admin.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(BASE)))
        cur.execute("SELECT datname FROM pg_database WHERE datname LIKE 'dtx_%'")
        leftovers = cur.fetchall()
        print("Audit child databases remaining:", len(leftovers))
    admin.close()
sys.exit(result)
