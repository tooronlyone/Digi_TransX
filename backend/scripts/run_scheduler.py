"""Dedicated production scheduler worker — the SINGLE owner of background jobs.

Runs the in-process scheduler for one-time delivery deadlines and settlement
release, and stays alive until it is terminated. Deploy exactly one scheduler
worker per environment.

Deployment contract:
  - Every web worker sets DIGITRANSX_ENABLE_SCHEDULER=0 (no auto-start).
  - This worker is the only process that runs scheduled lifecycle jobs; it calls
    start_scheduler(force=True), so it does not depend on the env flag.
  - Local development: run this as a SEPARATE process from the app, e.g.
        cd backend && python -m scripts.run_scheduler

scripts.process_overdue_confirmations is a one-off command for the same
one-time delivery lifecycle sweep.
"""

import signal
import sys
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main():
    from scheduler import start_scheduler

    scheduler = start_scheduler(force=True)
    if scheduler is None:
        # Only possible if a scheduler is already running in this process.
        print("[run_scheduler] a scheduler is already running in this process; nothing to do.")
        return 0

    stop = threading.Event()

    def _shutdown(_signum, _frame):
        stop.set()

    # Clean shutdown on Ctrl-C (SIGINT) and container stop (SIGTERM).
    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                signal.signal(sig, _shutdown)
            except (ValueError, OSError):
                # Not in the main thread / unsupported on this platform.
                pass

    job_ids = sorted(job.id for job in scheduler.get_jobs())
    print(f"[run_scheduler] started; owning jobs: {job_ids}")
    try:
        stop.wait()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.shutdown(wait=False)
        print("[run_scheduler] scheduler stopped cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
