"""Database access layer — Supabase PostgreSQL.

Replaces the old SQLite layer. Exposes the same open_db() context manager
and cursor-style API the app modules already use, backed by a psycopg2
connection pool pointed at the Supabase Postgres database.

Compatibility notes (kept so the 7k-line app code keeps working unchanged):
- '?' placeholders are translated to psycopg2's '%s'.
- 'INSERT OR IGNORE' becomes 'INSERT ... ON CONFLICT DO NOTHING'.
- 'SELECT last_insert_rowid()' is intercepted: every INSERT automatically
  gets 'RETURNING id' appended and the id is cached on the wrapper.
- Rows come back as dict-like Row objects (also indexable by position).
- Values are normalized to what the app expects from SQLite:
  timestamps -> ISO strings, dates -> 'YYYY-MM-DD', Decimal -> float,
  jsonb -> JSON string.
- Legacy display-format timestamp params ('20 Jul 2026 12:58:48 PM') are
  parsed to real datetimes before hitting Postgres.
- db.total_changes mirrors sqlite3's connection attribute (last rowcount).

There is NO SQLite fallback. SUPABASE_DB_URL must be configured.
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


class Row(dict):
    """Dict row that also supports positional access like sqlite3.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


_DISPLAY_TS_RE = re.compile(r"^\d{1,2} [A-Z][a-z]{2} \d{4} \d{1,2}:\d{2}:\d{2} [AP]M$")
_LASTROWID_RE = re.compile(r"^\s*SELECT\s+last_insert_rowid\s*\(\s*\)\s*;?\s*$", re.IGNORECASE)
_INSERT_IGNORE_RE = re.compile(r"INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE)


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


def _translate_sql(sql, has_params):
    on_conflict_ignore = False
    if _INSERT_IGNORE_RE.search(sql):
        sql = _INSERT_IGNORE_RE.sub("INSERT INTO", sql)
        on_conflict_ignore = True
    if has_params:
        sql = sql.replace("%", "%%").replace("?", "%s")
    stripped = sql.lstrip().upper()
    if stripped.startswith("INSERT") and "RETURNING" not in stripped:
        suffix = " ON CONFLICT DO NOTHING" if on_conflict_ignore else ""
        sql = sql.rstrip().rstrip(";") + suffix + " RETURNING id"
    return sql


class _Result:
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
    """Connection wrapper mimicking the sqlite3 connection surface the app uses."""

    def __init__(self, conn):
        self._conn = conn
        self._last_insert_id = None
        self._total_changes = 0

    @property
    def total_changes(self):
        return self._total_changes

    def execute(self, sql, params=()):
        if _LASTROWID_RE.match(sql):
            return _Result([Row({"last_insert_rowid": self._last_insert_id})])

        has_params = params is not None and len(params) > 0
        translated = _translate_sql(sql, has_params)
        is_insert = translated.lstrip().upper().startswith("INSERT")

        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            if has_params:
                cursor.execute(translated, [_normalize_param(p) for p in params])
            else:
                cursor.execute(translated)

            rows = []
            if cursor.description is not None:
                rows = [
                    Row({key: _normalize_value(val) for key, val in raw.items()})
                    for raw in cursor.fetchall()
                ]
            self._total_changes = cursor.rowcount if cursor.rowcount is not None else 0
            if is_insert:
                if rows and "id" in rows[0]:
                    self._last_insert_id = rows[0]["id"]
                return _Result([], rowcount=self._total_changes)
            return _Result(rows, rowcount=self._total_changes)
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
