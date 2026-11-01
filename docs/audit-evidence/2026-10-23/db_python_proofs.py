"""Pure local demonstrations; never connect to configured databases."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier

os.environ["SUPABASE_DB_URL"] = "postgresql://invalid.invalid/no-network"
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
from shared import db

print("aware_utc_datetime:", db._normalize_value(datetime(2026, 10, 23, 12, tzinfo=timezone.utc)))
print("lost_numeric_cents:", repr(db._normalize_value(Decimal("9007199254740992.01"))))
print("binary_money_sum:", repr(db._normalize_value(Decimal("0.1")) + db._normalize_value(Decimal("0.2"))))

arrived = Barrier(2)
created = []


class FakePool:
    def __init__(self, *args, **kwargs):
        created.append(self)
        arrived.wait(timeout=5)


db._pool = None
db.psycopg2.pool.ThreadedConnectionPool = FakePool
with ThreadPoolExecutor(max_workers=2) as executor:
    futures = [executor.submit(db._get_pool) for _ in range(2)]
    for future in futures:
        future.result()
print("concurrent_first_access_created_pools:", len(created))
