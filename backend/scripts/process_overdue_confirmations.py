"""One-off CLI for the 6-hour delivery-confirmation deadline sweep ONLY.

Runs the single production function `process_overdue_delivery_confirmations`
once and exits, printing the processed count/IDs as JSON. Safe to run repeatedly
(idempotent) and concurrently (FOR UPDATE SKIP LOCKED). Uses the app database via
shared.db — no secrets are read or printed here.

SCOPE: this command processes the one-time order confirmation timeouts ONLY. It
does NOT run the agreement due-payment or agreement penalty jobs. The full set of
background jobs is owned by the dedicated scheduler worker:

    cd backend && python -m scripts.run_scheduler

Use THIS one-off command only for the delivery-confirmation sweep, e.g. a crontab
line every 10 minutes on a host where run_scheduler is not the owner:

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
