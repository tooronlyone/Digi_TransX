"""
Digi_TransX in-process background scheduler.

Jobs (each wraps a single production service):
- Daily 00:05  : process due agreement payments
- Every 30 min : apply the late penalty to overdue failed agreement payments
- Every 10 min : escalate one-time deliveries past their 6-hour confirmation window

CONCURRENCY WARNING: the two agreement jobs are NOT safe to run in more than one
process at a time. run_process_payments selects due payments without distributed
ownership, and run_apply_penalties can charge a second Rs 5,000 penalty if two
processes run the same interval. Only the one-time overdue-confirmation sweep is
idempotent/concurrency-safe. Exactly ONE process must own these jobs.

DEPLOYMENT CONTRACT (single owner):
- Every WEB worker sets DIGITRANSX_ENABLE_SCHEDULER=0 (the default is also OFF —
  an absent flag never starts financial jobs on a web worker at import time).
- Exactly ONE dedicated scheduler worker owns ALL THREE jobs. Start it with:
      cd backend && python -m scripts.run_scheduler
  (that entry point calls start_scheduler(force=True)).
- Local development: run the scheduler worker as a SEPARATE process from the app.
- scripts.process_overdue_confirmations is a one-off command for the one-time
  confirmation-deadline sweep ONLY; it is NOT a replacement for the agreement
  payment/penalty jobs.

Safety layers:
- Auto-start is disabled by default and gated by DIGITRANSX_ENABLE_SCHEDULER.
- A per-process singleton (module-level _scheduler) is kept as a SECOND safety
  layer so repeated start_scheduler() calls in one process never add a second
  set of jobs. It does NOT protect across processes — the contract above does.
"""

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# The single per-process scheduler instance (None until started).
_scheduler = None

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off", ""}


def env_flag(name, default=False):
    """Parse an environment variable as a boolean truth value.

    Accepted (case-insensitive, trimmed):
      true  -> 1, true, yes, on
      false -> 0, false, no, off, empty
    Absent variable -> `default`. An unrecognized value -> `default` (never a
    silent surprise-enable of financial jobs)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return default


def scheduler_enabled():
    """Auto-start gate for the in-process scheduler.

    DISABLED BY DEFAULT: when DIGITRANSX_ENABLE_SCHEDULER is absent, importing
    the web app must NOT silently start financial background jobs. Only an
    explicit true value (1/true/yes/on) enables the auto-start path."""
    return env_flag("DIGITRANSX_ENABLE_SCHEDULER", default=False)


def _in_reloader_parent():
    """True only in the Werkzeug debug-reloader PARENT (which re-execs a serving
    child). Uses proper truth parsing so FLASK_DEBUG=0/false/no/off is NOT
    treated as debug. In the serving child WERKZEUG_RUN_MAIN == 'true'."""
    return env_flag("FLASK_DEBUG", default=False) and os.environ.get("WERKZEUG_RUN_MAIN") != "true"


def run_process_payments():
    """Process all pending agreement payments that are due."""
    try:
        from shared.db import open_db
        from agreements.helpers import run_process_payments as process_due_payments

        with open_db() as db:
            result = process_due_payments(db)
        logger.info(f"[Scheduler] process_payments: {result}")
    except Exception as exc:
        logger.error(f"[Scheduler] process_payments error: {exc}")


def run_apply_penalties():
    """Apply the late penalty to all failed payments that are overdue."""
    try:
        from shared.db import open_db
        from agreements.helpers import run_apply_penalties as apply_overdue_penalties

        with open_db() as db:
            result = apply_overdue_penalties(db)
        logger.info(f"[Scheduler] apply_penalties: {result}")
    except Exception as exc:
        logger.error(f"[Scheduler] apply_penalties error: {exc}")


def run_process_overdue_confirmations():
    """Escalate one-time deliveries whose 6-hour client-confirmation window has
    lapsed to admin_review (payment stays held). Wraps the single production
    function used by the manual admin trigger and the tests."""
    try:
        from shared.db import open_db
        from orders.lifecycle import process_overdue_delivery_confirmations

        with open_db() as db:
            result = process_overdue_delivery_confirmations(db)
            db.commit()
        logger.info(f"[Scheduler] process_overdue_confirmations: {result}")
        return result
    except Exception as exc:
        logger.error(f"[Scheduler] process_overdue_confirmations error: {exc}")
        return {"processed_count": 0, "processed_trip_ids": [], "error": str(exc)}


def start_scheduler(force=False):
    """Start the single background scheduler for this process, or reuse it.

    `force=True` is used ONLY by the dedicated scheduler worker
    (scripts.run_scheduler): it bypasses the env gate and the reloader check
    because that process is the explicit single owner. The web-app auto-start
    path calls start_scheduler() (force=False), which starts nothing unless
    DIGITRANSX_ENABLE_SCHEDULER is explicitly true.

    Idempotent within the process: repeated calls return the already-running
    instance (no duplicate jobs). Returns None when disabled/skipped."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    if not force:
        if not scheduler_enabled():
            logger.info("[Scheduler] Auto-start disabled (DIGITRANSX_ENABLE_SCHEDULER not true).")
            return None
        if _in_reloader_parent():
            logger.info("[Scheduler] Skipped in the debug-reloader parent process.")
            return None

    scheduler = BackgroundScheduler(daemon=True)

    # Every 10 minutes - escalate overdue one-time delivery confirmations.
    scheduler.add_job(
        run_process_overdue_confirmations,
        trigger=IntervalTrigger(minutes=10),
        id="process_overdue_confirmations_interval",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Daily at 00:05 AM - process due payments
    scheduler.add_job(
        run_process_payments,
        trigger=CronTrigger(hour=0, minute=5),
        id="process_payments_daily",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Every 30 minutes - apply penalties to failed payments
    scheduler.add_job(
        run_apply_penalties,
        trigger=IntervalTrigger(minutes=30),
        id="apply_penalties_interval",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "[Scheduler] Started - process_payments daily 00:05, apply_penalties every 30 min, "
        "process_overdue_confirmations every 10 min"
    )
    return scheduler
