"""Dedicated production scheduler worker — the SINGLE owner of all background jobs.

Runs the in-process scheduler with ALL THREE jobs and stays alive until it is
terminated:
  - agreement due-payment processing (daily 00:05)
  - agreement penalty processing (every 30 min)
  - one-time delivery overdue processing (every 10 min)

The two agreement jobs are NOT safe to run in more than one process (see
scheduler.py). Deploy EXACTLY ONE of these workers per environment.

Deployment contract:
  - Every web worker sets DIGITRANSX_ENABLE_SCHEDULER=0 (no auto-start).
  - This worker is the only process that runs the financial jobs; it calls
    start_scheduler(force=True), so it does not depend on the env flag.
  - Local development: run this as a SEPARATE process from the app, e.g.
        cd backend && python -m scripts.run_scheduler

scripts.process_overdue_confirmations is a one-off command that runs ONLY the
one-time confirmation-deadline sweep — it is NOT a replacement for this worker.
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
