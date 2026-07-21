"""Test fixtures for the commission-policy suite.

Uses an in-memory SQLite database that mimics the cursor-style surface of
shared.db.Db (execute with '?' placeholders, fetchone/fetchall dict-like
rows, SELECT last_insert_rowid(), INSERT OR IGNORE). This lets the shared
commission helpers run against a real SQL engine without touching the
remote Supabase database.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


SCHEMA = """
CREATE TABLE commission_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_type TEXT NOT NULL CHECK (policy_type IN ('one_time_order', 'agreement')),
    version_number INTEGER NOT NULL CHECK (version_number >= 1),
    company_share_percent REAL NOT NULL CHECK (company_share_percent >= 0 AND company_share_percent < 100),
    transporter_share_percent REAL NOT NULL,
    effective_at TEXT,
    change_summary TEXT NOT NULL CHECK (length(trim(change_summary)) > 0),
    created_by_admin_user_id INTEGER,
    created_at TEXT,
    UNIQUE (policy_type, version_number)
);

CREATE TABLE terms_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_number INTEGER NOT NULL UNIQUE CHECK (version_number >= 1),
    effective_at TEXT,
    change_summary TEXT NOT NULL,
    one_time_policy_id INTEGER NOT NULL REFERENCES commission_policies (id),
    agreement_policy_id INTEGER NOT NULL REFERENCES commission_policies (id),
    published_by_admin_user_id INTEGER,
    published_at TEXT
);

CREATE TABLE terms_acknowledgements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    terms_version_id INTEGER NOT NULL REFERENCES terms_versions (id),
    acknowledged_at TEXT,
    UNIQUE (user_id, terms_version_id)
);
"""


class FakeRow(dict):
    """Dict row that also supports positional access, like shared.db.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class FakeDb:
    """Minimal stand-in for shared.db.Db backed by in-memory SQLite."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = lambda cursor, row: FakeRow(
            {description[0]: row[index] for index, description in enumerate(cursor.description)}
        )
        self._conn.executescript(SCHEMA)

    def execute(self, sql, params=()):
        return self._conn.execute(sql, tuple(params))

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def seed_default_policies(db):
    """Mirror the migration seed: both types at 20/80 plus Terms v1."""
    from shared import commissions

    one_time = commissions.create_policy_version(
        db, commissions.POLICY_TYPE_ONE_TIME, "20.00",
        "Initial platform commission rate (20% company / 80% transporter).",
        None, "2026-07-21T00:00:00",
    )
    agreement = commissions.create_policy_version(
        db, commissions.POLICY_TYPE_AGREEMENT, "20.00",
        "Initial platform commission rate (20% company / 80% transporter).",
        None, "2026-07-21T00:00:00",
    )
    commissions.create_terms_version(
        db, one_time["id"], agreement["id"],
        "Initial platform Terms.", None, "2026-07-21T00:00:00",
    )
    db.commit()


@pytest.fixture
def db():
    fake = FakeDb()
    yield fake
    fake.close()


@pytest.fixture
def seeded_db(db):
    seed_default_policies(db)
    return db
