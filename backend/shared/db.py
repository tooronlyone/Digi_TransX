"""Database access layer — Supabase PostgreSQL.

Shared psycopg2 connection pool for the whole Flask backend. Exposes an
open_db() context manager yielding a Db wrapper with a cursor-style API:

    with open_db() as db:
        row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()

Contract:
- Queries are native psycopg2 SQL with %s placeholders.
- Inserts that need their generated key state it explicitly (RETURNING id).
- Rows come back as plain dicts keyed by column name.
- Every result exposes rowcount for UPDATE/DELETE affected-row checks.
- Values are normalized for the JSON API contract the app was built on:
  timestamps -> ISO strings, dates -> 'YYYY-MM-DD', times -> 'HH:MM:SS',
  Decimal -> float, jsonb -> JSON string, memoryview -> bytes.
- Display-format timestamp params ('20 Jul 2026 12:58:48 PM', produced by
  auth.helpers.timestamp_bundle) are parsed to real datetimes before being
  sent to PostgreSQL.
- Transactions: open_db() commits on clean exit and rolls back on any
  exception; Db.commit()/Db.rollback() remain available for explicit
  mid-block boundaries.

SUPABASE_DB_URL must be configured — there is no fallback engine.
"""

import json
import os
import re
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import IntegrityError  # noqa: F401  (imported by app modules)


BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIST = BASE_DIR / "frontend-react" / "dist"

# Load .env from the project root so every entry point gets configuration.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Karachi")

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        db_url = os.environ.get("SUPABASE_DB_URL", "")
        if not db_url:
            raise RuntimeError(
                "SUPABASE_DB_URL is not set. Copy .env.example to .env and fill in "
                "your Supabase database connection string."
            )
        _pool = psycopg2.pool.ThreadedConnectionPool(
            1,
            int(os.environ.get("SUPABASE_DB_POOL_MAX", "10")),
            dsn=db_url,
        )
    return _pool


_DISPLAY_TS_RE = re.compile(r"^\d{1,2} [A-Z][a-z]{2} \d{4} \d{1,2}:\d{2}:\d{2} [AP]M$")


def _normalize_value(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dt_time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def _normalize_param(value):
    if isinstance(value, str) and _DISPLAY_TS_RE.match(value):
        try:
            return datetime.strptime(value, "%d %b %Y %I:%M:%S %p")
        except ValueError:
            return value
    return value


class _Result:
    """Materialized query result: fetchone/fetchall plus the statement's rowcount."""

    def __init__(self, rows, rowcount=-1):
        self._rows = rows
        self._index = 0
        self.rowcount = rowcount

    def fetchone(self):
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None

    def fetchall(self):
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows


class Db:
    """Thin connection wrapper: execute native PostgreSQL, get dict rows back."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            if params is not None and len(params) > 0:
                cursor.execute(sql, [_normalize_param(p) for p in params])
            else:
                cursor.execute(sql)

            rows = []
            if cursor.description is not None:
                rows = [
                    {key: _normalize_value(val) for key, val in raw.items()}
                    for raw in cursor.fetchall()
                ]
            rowcount = cursor.rowcount if cursor.rowcount is not None else 0
            return _Result(rows, rowcount=rowcount)
        finally:
            cursor.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


@contextmanager
def open_db():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE %s", (APP_TIMEZONE,))
        wrapper = Db(conn)
        yield wrapper
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def check_connection():
    """Fail fast at startup with a clear message if the database is unreachable."""
    with open_db() as db:
        db.execute("SELECT 1")
