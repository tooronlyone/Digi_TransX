"""Database wrapper regressions without opening a database connection."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event, Lock
from unittest.mock import Mock

import pytest

from shared import db as database


def test_concurrent_first_use_constructs_one_pool(monkeypatch):
    first_constructor_started = Event()
    second_constructor_started = Event()
    second_caller_started = Event()
    release_constructor = Event()
    count_lock = Lock()
    pools = []

    def make_pool(*args, **kwargs):
        pool = object()
        with count_lock:
            pools.append(pool)
            if len(pools) == 1:
                first_constructor_started.set()
            else:
                second_constructor_started.set()
        assert release_constructor.wait(3)
        return pool

    def second_caller():
        second_caller_started.set()
        return database._get_pool()

    monkeypatch.setattr(database, "_pool", None)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://unused-test-database")
    monkeypatch.setattr(database.psycopg2.pool, "ThreadedConnectionPool", make_pool)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(database._get_pool)
        try:
            assert first_constructor_started.wait(3)
            second = executor.submit(second_caller)
            assert second_caller_started.wait(3)
            # Keep the first connection attempt in flight while another caller
            # enters. It must wait for that pool, not construct a second one.
            duplicate_constructor = second_constructor_started.wait(0.2)
        finally:
            release_constructor.set()
        assert first.result(timeout=3) is second.result(timeout=3)
    assert not duplicate_constructor
    assert len(pools) == 1


def test_pool_initialization_can_retry_after_connection_failure(monkeypatch):
    pool = object()
    constructor = Mock(side_effect=[database.psycopg2.OperationalError("offline"), pool])
    monkeypatch.setattr(database, "_pool", None)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://unused-test-database")
    monkeypatch.setattr(database.psycopg2.pool, "ThreadedConnectionPool", constructor)

    with pytest.raises(database.psycopg2.OperationalError, match="offline"):
        database._get_pool()

    assert database._pool is None
    assert database._get_pool() is pool
    assert database._get_pool() is pool
    assert constructor.call_count == 2


@pytest.mark.parametrize("offset_hours", [0, 5, -7])
@pytest.mark.parametrize("exact", [False, True])
def test_query_timestamp_preserves_the_instant_and_offset(offset_hours, exact):
    timestamp = datetime(2026, 10, 29, 0, 15, 42,
                         tzinfo=timezone(timedelta(hours=offset_hours)))
    cursor = Mock()
    cursor.description = [("occurred_at",)]
    cursor.rowcount = 1
    cursor.fetchall.return_value = [{"occurred_at": timestamp, "amount": Decimal("12.50")}]
    connection = Mock()
    connection.cursor.return_value = cursor
    wrapper = database.Db(connection)

    result = (wrapper.execute_exact if exact else wrapper.execute)("SELECT occurred_at, amount")
    row = result.fetchone()
    parsed = datetime.fromisoformat(row["occurred_at"])

    assert parsed == timestamp
    assert parsed.utcoffset() == timestamp.utcoffset()
    assert isinstance(row["amount"], Decimal if exact else float)
    cursor.close.assert_called_once()


def test_naive_legacy_timestamp_keeps_its_existing_format():
    assert database._normalize_value(datetime(2026, 10, 29, 12, 15, 42, 123456)) == (
        "2026-10-29T12:15:42"
    )
