"""CLI/worker entry point for the 6-hour delivery-confirmation deadline sweep.

Runs the single production function once and exits, printing the processed
count/IDs as JSON. Safe to run repeatedly (idempotent) and concurrently
(FOR UPDATE SKIP LOCKED). Uses the app database via shared.db — no secrets are
read or printed here.

Production scheduling: the Flask app already runs this every 10 minutes in-process
(scheduler.run_process_overdue_confirmations). To run it as an external cron/worker
instead (e.g. a container or systemd timer), invoke from the backend directory:

    python -m scripts.process_overdue_confirmations

e.g. a crontab line every 10 minutes:

    */10 * * * * cd /path/to/Digi_TransX/backend && python -m scripts.process_overdue_confirmations
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main():
    from shared.db import open_db
    from orders.lifecycle import process_overdue_delivery_confirmations

    with open_db() as db:
        result = process_overdue_delivery_confirmations(db)
        db.commit()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
