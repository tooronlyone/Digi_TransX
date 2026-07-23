"""
Digi_TransX in-process background scheduler.

Jobs (all idempotent; each wraps a single production service):
- Daily 00:05  : process due agreement payments
- Every 30 min : apply the late penalty to overdue failed agreement payments
- Every 10 min : escalate one-time deliveries past their 6-hour confirmation window

Ownership / safety (see start_scheduler):
- ONE scheduler instance per process (module-level singleton); repeated
  start_scheduler() calls reuse the running instance instead of adding a second
  set of jobs.
- Gated by the DIGITRANSX_ENABLE_SCHEDULER env switch (default on).
- Skipped in the Werkzeug debug-reloader PARENT process so the reloader can't
  run two schedulers.

PRODUCTION must run exactly ONE scheduler owner: either a single app process
with DIGITRANSX_ENABLE_SCHEDULER=1 (all other web workers set it to 0), OR the
external worker `python -m scripts.process_overdue_confirmations` on a cron with
the in-process scheduler disabled everywhere. Never both, or jobs double-fire.
"""

import logging
import os
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# The single per-process scheduler instance (None until started).
_scheduler = None


def scheduler_enabled():
    """The scheduler runs unless DIGITRANSX_ENABLE_SCHEDULER is a falsy value."""
    return os.environ.get("DIGITRANSX_ENABLE_SCHEDULER", "1").strip().lower() not in (
        "0", "false", "no", "off", ""
    )


def _in_reloader_parent():
    """True in the Werkzeug debug-reloader PARENT (which re-execs a child that
    actually serves). Starting jobs there would double them."""
    return bool(os.environ.get("FLASK_DEBUG")) and os.environ.get("WERKZEUG_RUN_MAIN") != "true"


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


def start_scheduler():
    """Start the single background scheduler for this process, or reuse it.

    Idempotent: repeated calls return the already-running instance (no duplicate
    jobs). Returns None when the scheduler is disabled by env or when called in
    the debug-reloader parent."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    if not scheduler_enabled():
        logger.info("[Scheduler] Disabled via DIGITRANSX_ENABLE_SCHEDULER.")
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
