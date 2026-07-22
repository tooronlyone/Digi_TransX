"""
Digi_TransX Payment Scheduler
Runs automatically when Flask app starts.
- Daily at 00:05 AM: process pending payments due today or earlier
- Every 30 minutes: apply Rs 5,000 penalty to failed payments
"""

import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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
    """Initialize and start the background scheduler. Call once at app startup."""
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
    logger.info(
        "[Scheduler] Started - process_payments daily 00:05, apply_penalties every 30 min, "
        "process_overdue_confirmations every 10 min"
    )
    return scheduler
