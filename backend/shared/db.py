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
  timestamps -> ISO strings preserving UTC offsets, dates -> 'YYYY-MM-DD',
  times -> 'HH:MM:SS', Decimal -> float, jsonb -> JSON string,
  memoryview -> bytes.
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
from threading import Lock
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import certifi
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

_pools = {}
_pool_init_lock = Lock()
_LOOPBACK_DB_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_INSECURE_DB_SSLMODES = frozenset({"disable", "allow", "prefer"})
_SECURE_DB_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})
_LOCAL_ENVIRONMENTS = frozenset({"local", "test"})
_PRIVILEGED_OWNER_ROLES = frozenset({"postgres", "supabase_admin"})

DB_ROLE_API = "api"
DB_ROLE_SCHEDULER = "scheduler"
DB_ROLE_AUDITOR = "auditor"
DB_ROLE_MIGRATION = "migration"

_ROLE_ENV_MAP = {
    DB_ROLE_API: "DIGITRANSX_API_DB_URL",
    DB_ROLE_SCHEDULER: "DIGITRANSX_SCHEDULER_DB_URL",
    DB_ROLE_AUDITOR: "DIGITRANSX_AUDITOR_DB_URL",
    DB_ROLE_MIGRATION: "DIGITRANSX_MIGRATION_DB_URL",
}


def _resolve_sslrootcert(value):
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if cleaned.lower() == "certifi":
        return certifi.where()
    return cleaned


def is_loopback_postgres_target(db_url):
    """Return True only when the PostgreSQL URI/conninfo stays strictly local."""

    raw = str(db_url or "").strip()
    if not raw:
        return False
    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"postgres", "postgresql"}:
            return False
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        raw_hosts = params.get("host") or parsed.hostname or ""
        raw_hostaddrs = params.get("hostaddr") or ""
        hosts = [h.strip().strip("[]").lower() for h in raw_hosts.split(",") if h.strip()]
        hostaddrs = [a.strip().strip("[]").lower() for a in raw_hostaddrs.split(",") if a.strip()]
        if not hosts and not hostaddrs:
            return True
        hosts_local = all(h in _LOOPBACK_DB_HOSTS or h.startswith("/") for h in hosts)
        addrs_local = all(a in _LOOPBACK_DB_HOSTS for a in hostaddrs)
        return hosts_local and addrs_local

    pairs = {}
    for match in re.finditer(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:'([^']*)'|(\S+))", raw):
        pairs[match.group(1).lower()] = match.group(2) if match.group(2) is not None else match.group(3)
    host = (pairs.get("host") or "").strip().strip("[]").lower()
    hostaddr = (pairs.get("hostaddr") or "").strip().strip("[]").lower()
    if not host and not hostaddr:
        return True
    hosts_local = all(h in _LOOPBACK_DB_HOSTS or h.startswith("/") for h in host.split(",") if h)
    addrs_local = all(a in _LOOPBACK_DB_HOSTS for a in hostaddr.split(",") if a)
    return hosts_local and addrs_local


def normalize_postgres_dsn(db_url, environ=None):
    """Enforce secure TLS parameters on non-loopback PostgreSQL connections.

    Loopback/local test targets keep their local DSN untouched unless explicit
    TLS enforcement is enabled. Non-local targets reject ``disable``,
    ``allow``, and ``prefer`` and enforce at least ``require`` (or
    ``verify-full`` whenever a root certificate is provided).
    """

    raw = str(db_url or "").strip()
    if not raw:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set. Copy .env.example to .env and fill in "
            "your Supabase database connection string."
        )
    values = os.environ if environ is None else environ
    if is_loopback_postgres_target(raw) and str(values.get("DIGITRANSX_DB_REQUIRE_TLS", "")).strip().lower() != "true":
        return raw

    configured_mode = str(values.get("DIGITRANSX_DB_SSLMODE") or "").strip().lower()
    env_pg_mode = str(values.get("PGSSLMODE") or "").strip().lower()
    configured_root = _resolve_sslrootcert(
        values.get("DIGITRANSX_DB_SSLROOTCERT") or values.get("PGSSLROOTCERT") or ""
    )

    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"postgres", "postgresql"}:
            raise RuntimeError("SUPABASE_DB_URL must use a postgres:// or postgresql:// scheme.")
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        params = {k.lower(): v for k, v in query_items}
        explicit_mode = str(params.get("sslmode") or "").strip().lower()
        effective_mode = explicit_mode or configured_mode or env_pg_mode
        if effective_mode in _INSECURE_DB_SSLMODES:
            raise RuntimeError(
                "Non-local PostgreSQL connections must enforce TLS (sslmode=require, verify-ca, or verify-full)."
            )
        if effective_mode and effective_mode not in _SECURE_DB_SSLMODES:
            raise RuntimeError("Unsupported PostgreSQL sslmode configuration.")

        existing_root = _resolve_sslrootcert(params.get("sslrootcert") or "")
        effective_root = existing_root or configured_root
        target_mode = effective_mode or ("verify-full" if effective_root else "require")
        filtered_items = [(k, v) for k, v in query_items if k.lower() not in {"sslmode", "sslrootcert"}]
        filtered_items.append(("sslmode", target_mode))
        if effective_root:
            filtered_items.append(("sslrootcert", effective_root))
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(filtered_items), parsed.fragment)
        )

    pairs = {}
    for match in re.finditer(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:'([^']*)'|(\S+))", raw):
        pairs[match.group(1).lower()] = match.group(2) if match.group(2) is not None else match.group(3)
    explicit_mode = str(pairs.get("sslmode") or "").strip().lower()
    effective_mode = explicit_mode or configured_mode or env_pg_mode
    if effective_mode in _INSECURE_DB_SSLMODES:
        raise RuntimeError(
            "Non-local PostgreSQL connections must enforce TLS (sslmode=require, verify-ca, or verify-full)."
        )
    if effective_mode and effective_mode not in _SECURE_DB_SSLMODES:
        raise RuntimeError("Unsupported PostgreSQL sslmode configuration.")
    effective_root = _resolve_sslrootcert(pairs.get("sslrootcert") or "") or configured_root
    target_mode = effective_mode or ("verify-full" if effective_root else "require")
    suffix = []
    if not explicit_mode:
        suffix.append(f"sslmode={target_mode}")
    if effective_root and "sslrootcert" not in pairs:
        suffix.append(f"sslrootcert={effective_root}")
    return f"{raw} {' '.join(suffix)}".strip()


def extract_postgres_username(db_url):
    """Extract the PostgreSQL role name from a URI or libpq conninfo string."""

    raw = str(db_url or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.username:
            return unquote(parsed.username).strip()
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for key, value in params.items():
            if key.lower() == "user" and value:
                return value.strip()
        return ""
    for match in re.finditer(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:'([^']*)'|(\S+))", raw):
        if match.group(1).lower() == "user":
            return (match.group(2) if match.group(2) is not None else match.group(3)).strip()
    return ""


def is_owner_postgres_role(db_url):
    """Return True when the DSN connects as an owner/admin PostgreSQL role."""

    username = extract_postgres_username(db_url)
    if not username:
        return False
    base = username.split(".", 1)[0].strip().lower()
    return base in _PRIVILEGED_OWNER_ROLES


def resolve_database_dsn(purpose=DB_ROLE_API, environ=None):
    """Resolve and validate the PostgreSQL DSN for a scoped runtime purpose.

    Outside explicit ``local`` and ``test`` environments, each runtime role
    requires its own dedicated connection variable and rejects owner
    credentials or migration DSN fallback.
    """

    if purpose not in {DB_ROLE_API, DB_ROLE_SCHEDULER, DB_ROLE_AUDITOR}:
        raise ValueError(f"Unsupported runtime database purpose: {purpose}")

    values = os.environ if environ is None else environ
    env_name = str(values.get("DIGITRANSX_ENVIRONMENT") or "").strip().lower()
    explicit_local = env_name in _LOCAL_ENVIRONMENTS
    primary_env = _ROLE_ENV_MAP[purpose]
    dsn = str(values.get(primary_env) or "").strip()
    migration_dsn = str(values.get("DIGITRANSX_MIGRATION_DB_URL") or "").strip()

    if explicit_local and not dsn:
        if purpose in {DB_ROLE_SCHEDULER, DB_ROLE_AUDITOR}:
            dsn = str(values.get("DIGITRANSX_API_DB_URL") or "").strip()
        if not dsn:
            dsn = str(values.get("SUPABASE_DB_URL") or "").strip()

    if not dsn:
        if explicit_local:
            raise RuntimeError(
                f"{primary_env} (or SUPABASE_DB_URL in local/test) is not set."
            )
        raise RuntimeError(
            f"{primary_env} must be configured with a dedicated least-privilege PostgreSQL role outside local/test mode."
        )

    if not explicit_local:
        username = extract_postgres_username(dsn)
        if not username:
            raise RuntimeError(f"{primary_env} must specify an explicit PostgreSQL username.")
        if is_owner_postgres_role(dsn):
            raise RuntimeError(
                f"{primary_env} must not use privileged owner role credentials ({username})."
            )
        if migration_dsn and dsn == migration_dsn:
            raise RuntimeError(
                f"{primary_env} must not share DIGITRANSX_MIGRATION_DB_URL."
            )

    return normalize_postgres_dsn(dsn, environ=values)


def resolve_migration_dsn(environ=None):
    """Resolve the schema migration DSN (for migration scripts/runners only)."""

    values = os.environ if environ is None else environ
    env_name = str(values.get("DIGITRANSX_ENVIRONMENT") or "").strip().lower()
    dsn = str(values.get("DIGITRANSX_MIGRATION_DB_URL") or "").strip()
    if not dsn and env_name in _LOCAL_ENVIRONMENTS:
        dsn = str(values.get("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        raise RuntimeError("DIGITRANSX_MIGRATION_DB_URL is not set.")
    return normalize_postgres_dsn(dsn, environ=values)


def reset_db_pools():
    """Close and clear cached PostgreSQL connection pools (primarily for tests)."""

    with _pool_init_lock:
        for pool in _pools.values():
            try:
                pool.closeall()
            except Exception:
                pass
        _pools.clear()


def _get_pool(purpose=DB_ROLE_API):
    db_url = resolve_database_dsn(purpose=purpose)
    cache_key = (purpose, db_url)
    pool = _pools.get(cache_key)
    if pool is None:
        # The pool's own lock only protects an already-created pool. Opening
        # its initial connection can release the GIL, so singleton creation
        # also needs synchronization when requests arrive together at startup.
        with _pool_init_lock:
            pool = _pools.get(cache_key)
            if pool is None:
                pool = psycopg2.pool.ThreadedConnectionPool(
                    1,
                    int(os.environ.get("SUPABASE_DB_POOL_MAX", "10")),
                    dsn=db_url,
                )
                _pools[cache_key] = pool
    return pool


_DISPLAY_TS_RE = re.compile(r"^\d{1,2} [A-Z][a-z]{2} \d{4} \d{1,2}:\d{2}:\d{2} [AP]M$")


def _normalize_value(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
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
        return self._execute(sql, params, exact=False)

    def execute_exact(self, sql, params=()):
        """Financial service reads: retain PostgreSQL NUMERIC as Decimal.

        Legacy API serialization remains unchanged in execute(). New ledger
        code must use this method so arithmetic never round-trips through float.
        Timestamps retain their UTC offset instead of losing timezone data.
        """
        return self._execute(sql, params, exact=True)

    def _execute(self, sql, params, *, exact):
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            if params is not None and len(params) > 0:
                cursor.execute(sql, [_normalize_param(p) for p in params])
            else:
                cursor.execute(sql)

            rows = []
            if cursor.description is not None:
                rows = [
                    {key: (val if isinstance(val, Decimal) else
                           val.isoformat() if exact and isinstance(val, datetime) else
                           _normalize_value(val)) if exact else _normalize_value(val)
                     for key, val in raw.items()}
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
def open_db(role=DB_ROLE_API):
    pool = _get_pool(purpose=role)
    conn = pool.getconn()
    try:
        wrapper = Db(conn)
        yield wrapper
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def open_scheduler_db():
    """Open a transaction using the dedicated scheduler worker database role."""

    with open_db(role=DB_ROLE_SCHEDULER) as db:
        yield db


@contextmanager
def open_auditor_db():
    """Open a read-only reconciliation transaction using the auditor role."""

    with open_db(role=DB_ROLE_AUDITOR) as db:
        db.execute("SET TRANSACTION READ ONLY")
        yield db


def check_connection():
    """Fail fast at startup with a clear message if the database is unreachable."""
    with open_db() as db:
        db.execute("SELECT 1")
