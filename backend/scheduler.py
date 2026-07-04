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
        from agreements.routes import process_payment_row
        from wallet.helpers import round_money

        today = date.today().isoformat()
        processed = 0
        failed = 0

        with open_db() as db:
            rows = db.execute(
                """
                SELECT * FROM agreement_monthly_payments
                WHERE status = 'pending' AND payment_due_date <= ?
                ORDER BY id ASC
                """,
                (today,),
            ).fetchall()
            for row in rows:
                ok = process_payment_row(db, dict(row))
                if ok:
                    processed += 1
                else:
                    failed += 1
            db.commit()

        logger.info(f"[Scheduler] process_payments: processed={processed}, failed={failed}")
    except Exception as exc:
        logger.error(f"[Scheduler] process_payments error: {exc}")


def run_apply_penalties():
    """Apply Rs 5,000 penalty to all failed payments that are overdue."""
    try:
        from shared.db import open_db
        from agreements.routes import process_payment_row
        from agreements.helpers import PENALTY_AMOUNT
        from auth.helpers import timestamp_bundle
        from wallet.helpers import adjust_wallet_balance, get_or_create_wallet_for_user

        today = date.today().isoformat()
        penalties_applied = 0

        with open_db() as db:
            rows = db.execute(
                """
                SELECT * FROM agreement_monthly_payments
                WHERE status = 'failed' AND payment_due_date <= ?
                ORDER BY id ASC
                """,
                (today,),
            ).fetchall()
            for row in rows:
                payment = dict(row)
                client_wallet, wallet_error = get_or_create_wallet_for_user(
                    db, {"id": payment["client_user_id"], "role": "client"}
                )
                if wallet_error:
                    continue
                penalty_error = adjust_wallet_balance(
                    db,
                    client_wallet,
                    payment["client_user_id"],
                    -PENALTY_AMOUNT,
                    "agreement_late_penalty",
                    description=f"Agreement #{payment['agreement_id']} late payment penalty",
                    reference_id=str(payment["id"]),
                )
                if penalty_error:
                    continue
                current_count = db.execute(
                    "SELECT COUNT(*) AS total FROM agreement_payment_penalties WHERE monthly_payment_id = ?",
                    (payment["id"],),
                ).fetchone()["total"]
                stamp = timestamp_bundle()["iso"]
                db.execute(
                    """
                    INSERT INTO agreement_payment_penalties (
                        monthly_payment_id, client_user_id, penalty_amount, penalty_number, applied_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (payment["id"], payment["client_user_id"], PENALTY_AMOUNT, int(current_count or 0) + 1, stamp),
                )
                db.execute(
                    "UPDATE agreement_monthly_payments SET penalty_amount = penalty_amount + ? WHERE id = ?",
                    (PENALTY_AMOUNT, payment["id"]),
                )
                penalties_applied += 1
                refreshed = db.execute(
                    "SELECT * FROM agreement_monthly_payments WHERE id = ?", (payment["id"],)
                ).fetchone()
                if refreshed:
                    process_payment_row(db, dict(refreshed))
            db.commit()

        logger.info(f"[Scheduler] apply_penalties: penalties_applied={penalties_applied}")
    except Exception as exc:
        logger.error(f"[Scheduler] apply_penalties error: {exc}")


def run_expire_negotiations():
    """Auto-finalize cancellation negotiations that have passed their 48-hour deadline."""
    try:
        from shared.db import open_db
        from orders.helpers import check_expired_negotiations

        with open_db() as db:
            check_expired_negotiations(db)
            db.commit()

        logger.info("[Scheduler] run_expire_negotiations: completed")
    except Exception as exc:
        logger.error(f"[Scheduler] run_expire_negotiations error: {exc}")


def start_scheduler():
    """Initialize and start the background scheduler. Call once at app startup."""
    scheduler = BackgroundScheduler(daemon=True)

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

    # Every hour - auto-finalize expired cancellation negotiations (48-hour window passed)
    scheduler.add_job(
        run_expire_negotiations,
        trigger=IntervalTrigger(hours=1),
        id="expire_negotiations_hourly",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.start()
    logger.info("[Scheduler] Started — process_payments daily 00:05, apply_penalties every 30 min, expire_negotiations every 1 hour")
    return scheduler
