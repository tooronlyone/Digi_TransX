"""In-app notifications for delivery and account events.

Single writer for public.shipment_notifications (which had no producer before).
Notifications are idempotent per (trip, recipient, event type): the unique index
uniq_notification_event backs the ON CONFLICT DO NOTHING, so replayed
transitions and repeated deadline sweeps can never create duplicate rows.

No external email/push is sent in this phase. This owner persists only the
current in-app surface; required external email delivery remains planned.
"""

import logging


logger = logging.getLogger(__name__)

# Canonical lifecycle event types (also the notification_type stored per row).
TRIP_STARTED = "trip_started"
DELIVERY_CONFIRMATION_REQUESTED = "delivery_confirmation_requested"
DELIVERY_DENIED = "delivery_denied"
CONFIRMATION_OVERDUE = "confirmation_overdue"
DELIVERY_CONFIRMED = "delivery_confirmed"
DISPUTE_RESOLVED_TRANSPORTER = "dispute_resolved_transporter"
DISPUTE_RESOLVED_CLIENT = "dispute_resolved_client"
REVIEW_REQUIRED = "review_required"
REVIEW_SUBMITTED = "review_submitted"


def notify(db, order_id, trip_id, user_id, notification_type, message):
    """Idempotently persist one notification. Returns True if a row was created,
    False if it already existed (same trip + recipient + type). Never commits."""
    if user_id is None:
        return False
    row = db.execute(
        """
        INSERT INTO shipment_notifications (order_id, trip_id, user_id, notification_type, message)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (trip_id, user_id, notification_type) WHERE trip_id IS NOT NULL
        DO NOTHING
        RETURNING id
        """,
        (order_id, trip_id, user_id, notification_type, message),
    ).fetchone()
    return bool(row)


def notify_best_effort(db, order_id, trip_id, user_id, notification_type, message):
    """Persist an optional notice without aborting the caller's transaction.

    Catching a PostgreSQL insert error alone leaves the transaction aborted.
    A savepoint preserves payment/penalty updates if notification delivery fails.
    Like notify(), this helper never commits.
    """
    db.execute("SAVEPOINT optional_notification")
    try:
        created = notify(db, order_id, trip_id, user_id, notification_type, message)
    except Exception:
        db.execute("ROLLBACK TO SAVEPOINT optional_notification")
        logger.exception("Unable to persist optional %s notification", notification_type)
        created = False
    finally:
        db.execute("RELEASE SAVEPOINT optional_notification")
    return created


def notify_admins(db, order_id, trip_id, notification_type, message):
    """Fan a lifecycle event out to every platform admin (idempotent per admin).
    Returns the number of admin notifications created."""
    admins = db.execute("SELECT id FROM users WHERE role = 'admin'").fetchall()
    created = 0
    for admin in admins:
        if notify(db, order_id, trip_id, admin["id"], notification_type, message):
            created += 1
    return created


def serialize_notification(row):
    return {
        "id": row.get("id"),
        "order_id": row.get("order_id"),
        "trip_id": row.get("trip_id"),
        "type": row.get("notification_type"),
        "message": row.get("message"),
        "is_read": bool(row.get("is_read")),
        "created_at": row.get("created_at"),
    }
