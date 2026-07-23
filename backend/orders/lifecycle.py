"""Canonical one-time delivery lifecycle — the single transition/service layer.

Every status change for a one-time order flows through exactly one function
here (no status-changing SQL is scattered across routes). Each transition:

  * validates the actor / ownership and the current state;
  * takes row locks in one canonical order — shipment -> trip -> dispute ->
    payment -> wallet — so concurrent transitions serialize without deadlocking
    (every path acquires a prefix/suffix of this order, never a cycle);
  * is idempotent (a replay in the target state returns the existing result);
  * relies on the automatic shipment_status_history trigger for the audit trail
    (every transition also moves the shipment status, so history is recorded);
  * creates in-app notifications exactly once (idempotent per event);
  * refuses impossible / backward transitions.

Canonical states (trip and shipment share the same vocabulary):
    ready_to_start -> in_progress -> awaiting_client_confirmation
        -> completed                (client Yes / admin transporter-win)
        -> delivery_disputed        (client No)
        -> admin_review             (6-hour timeout)          -> resolved_client
Money (payments): held -> released (payout) | refunded (client-win). The payment
stays held through delivery_disputed and admin_review — no automatic payout or
refund ever happens outside the two canonical money services in shared.payments.
"""

from datetime import datetime, timedelta, timezone

from auth.helpers import timestamp_bundle
from shared.payments import (
    CheckoutError,
    get_active_payment_for_shipment,
    refund_one_time_payment,
    release_one_time_payment,
)
from shared import notifications as notif

CONFIRMATION_WINDOW = timedelta(hours=6)

# Canonical trip/shipment states.
READY_TO_START = "ready_to_start"
IN_PROGRESS = "in_progress"
AWAITING_CLIENT_CONFIRMATION = "awaiting_client_confirmation"
COMPLETED = "completed"
DELIVERY_DISPUTED = "delivery_disputed"
ADMIN_REVIEW = "admin_review"
RESOLVED_CLIENT = "resolved_client"


# ---------------------------------------------------------------------------
# Locking + small helpers
# ---------------------------------------------------------------------------

def _utcnow(now):
    return now or datetime.now(timezone.utc)


def _lock_order_trip(db, order_id, trip_id):
    """Lock the shipment then the trip (the canonical order). Returns
    (order, trip) dicts. Raises CheckoutError(404) when either is missing."""
    order_row = db.execute(
        "SELECT * FROM shipments WHERE id = %s FOR UPDATE", (order_id,)
    ).fetchone()
    if not order_row:
        raise CheckoutError("Order not found.", 404)
    trip_row = db.execute(
        "SELECT * FROM shipment_trips WHERE id = %s AND order_id = %s FOR UPDATE",
        (trip_id, order_id),
    ).fetchone()
    if not trip_row:
        raise CheckoutError("Trip not found.", 404)
    return dict(order_row), dict(trip_row)


def _held_payment(db, order_id):
    return get_active_payment_for_shipment(db, order_id, statuses=("held",))


def _set_trip_and_shipment(db, trip_id, order_id, status, trip_extra=None):
    """Move trip + shipment to `status` in one place. The shipment status change
    fires the automatic history trigger. trip_extra is {column: value} of extra
    trip columns to set (timestamps)."""
    stamp = timestamp_bundle()["display"]
    sets = ["status = %s", "updated_at = %s"]
    args = [status, stamp]
    for col, val in (trip_extra or {}).items():
        sets.append(f"{col} = %s")
        args.append(val)
    args.append(trip_id)
    db.execute(f"UPDATE shipment_trips SET {', '.join(sets)} WHERE id = %s", args)
    db.execute(
        "UPDATE shipments SET status = %s, updated_at = %s WHERE id = %s",
        (status, stamp, order_id),
    )


def _ensure_thread(db, order, trip):
    from chat.helpers import ensure_one_time_thread
    return ensure_one_time_thread(
        db, order["id"], trip["id"], order["client_user_id"], trip["transporter_user_id"]
    )


# ---------------------------------------------------------------------------
# Dispute helpers (one OPEN dispute per trip, DB-enforced)
# ---------------------------------------------------------------------------

def _get_open_dispute(db, trip_id):
    row = db.execute(
        "SELECT * FROM shipment_disputes WHERE trip_id = %s AND status = 'open' FOR UPDATE",
        (trip_id,),
    ).fetchone()
    return dict(row) if row else None


def _open_or_reuse_dispute(db, order, trip, payment, trigger, thread_id, client_reason=None):
    """Create the one open dispute for this trip, or reuse the existing one.

    Uses INSERT ON CONFLICT DO NOTHING against uniq_open_dispute_per_trip (the
    partial unique index on trip_id WHERE status = 'open'), so a concurrent
    opener is a no-op rather than a unique-violation — the transaction is never
    aborted. Returns (dispute_dict, created_bool)."""
    existing = _get_open_dispute(db, trip["id"])
    if existing:
        if client_reason and not existing.get("client_reason"):
            db.execute(
                "UPDATE shipment_disputes SET client_reason = %s WHERE id = %s",
                (client_reason, existing["id"]),
            )
            existing["client_reason"] = client_reason
        return existing, False
    inserted = db.execute(
        """
        INSERT INTO shipment_disputes (
            shipment_id, trip_id, payment_id, client_user_id, transporter_user_id,
            chat_thread_id, trigger, status, client_reason
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s)
        ON CONFLICT (trip_id) WHERE status = 'open' DO NOTHING
        RETURNING *
        """,
        (
            order["id"], trip["id"], payment["id"] if payment else None,
            order["client_user_id"], trip["transporter_user_id"],
            thread_id, trigger, client_reason,
        ),
    ).fetchone()
    if inserted:
        return dict(inserted), True
    # A concurrent opener committed first — reuse their open dispute (locked).
    existing = _get_open_dispute(db, trip["id"])
    if not existing:
        raise CheckoutError("Dispute could not be created.", 500, "dispute_create_failed")
    return existing, False


def serialize_dispute(row):
    return {
        "id": row.get("id"),
        "shipment_id": row.get("shipment_id"),
        "trip_id": row.get("trip_id"),
        "payment_id": row.get("payment_id"),
        "client_user_id": row.get("client_user_id"),
        "transporter_user_id": row.get("transporter_user_id"),
        "chat_thread_id": row.get("chat_thread_id"),
        "trigger": row.get("trigger"),
        "status": row.get("status"),
        "client_reason": row.get("client_reason"),
        "transporter_statement": row.get("transporter_statement"),
        "admin_notes": row.get("admin_notes"),
        "resolution": row.get("resolution"),
        "resolved_at": row.get("resolved_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Phase E — transporter requests delivery completion
# ---------------------------------------------------------------------------

def perform_complete_delivery(db, user, order_id, trip_id, now=None):
    """Transporter marks the goods delivered and opens the 6-hour client
    confirmation window. Payment stays held. Idempotent (replay returns the same
    deadline). Caller commits."""
    now = _utcnow(now)
    order, trip = _lock_order_trip(db, order_id, trip_id)
    if trip["transporter_user_id"] != user["id"]:
        raise CheckoutError("Access denied.", 403)

    if trip["status"] == AWAITING_CLIENT_CONFIRMATION:
        return {  # idempotent replay — same deadline
            "already": True,
            "trip": trip,
            "confirmation_deadline_at": trip["confirmation_deadline_at"],
        }
    if trip["status"] != IN_PROGRESS:
        raise CheckoutError(
            "Only an in-progress trip can request delivery completion.",
            409, "trip_not_in_progress",
        )

    payment = _held_payment(db, order_id)
    if not payment or payment["trip_id"] != trip_id:
        raise CheckoutError("Payment for this order is not held.", 409, "payment_not_held")

    deadline = now + CONFIRMATION_WINDOW
    # A completion CLAIM is not a completed trip: record the request time and the
    # 6-hour window only. trip_completed_at is set later, and only on a genuine
    # completion (client Yes / admin transporter-win).
    _set_trip_and_shipment(
        db, trip_id, order_id, AWAITING_CLIENT_CONFIRMATION,
        trip_extra={
            "delivery_completion_requested_at": now,
            "confirmation_deadline_at": deadline,
        },
    )
    _ensure_thread(db, order, trip)
    notif.notify(
        db, order_id, trip_id, order["client_user_id"],
        notif.DELIVERY_CONFIRMATION_REQUESTED,
        "The transporter marked your delivery complete. Please confirm within 6 hours.",
    )
    updated = dict(db.execute("SELECT * FROM shipment_trips WHERE id = %s", (trip_id,)).fetchone())
    return {"already": False, "trip": updated,
            "confirmation_deadline_at": updated["confirmation_deadline_at"]}


# ---------------------------------------------------------------------------
# Phase F — client confirms (Yes) or denies (No)
# ---------------------------------------------------------------------------

def perform_client_confirm(db, user, order_id, trip_id, decision, reason=None, now=None):
    """Client answers the delivery-completion request. decision in {'yes','no'}.
    'yes' releases the payout once; 'no' opens a dispute. Caller commits."""
    if decision not in ("yes", "no"):
        raise CheckoutError("Invalid response.", 400, "invalid_decision")
    now = _utcnow(now)
    order, trip = _lock_order_trip(db, order_id, trip_id)
    if order["client_user_id"] != user["id"]:
        raise CheckoutError("Access denied.", 403)

    # Idempotent replays of a decision already applied.
    if decision == "yes" and trip["status"] == COMPLETED:
        return {"decision": "yes", "already": True, "trip": trip}
    if decision == "no" and trip["status"] == DELIVERY_DISPUTED:
        dispute = _get_open_dispute(db, trip_id)
        return {"decision": "no", "already": True, "trip": trip,
                "dispute": serialize_dispute(dispute) if dispute else None}

    if trip["status"] != AWAITING_CLIENT_CONFIRMATION:
        # After a 6-hour escalation (admin_review) the client can no longer
        # decide; any other state is simply not confirmable.
        raise CheckoutError(
            "This delivery can no longer be confirmed here.", 409, "not_awaiting_confirmation",
        )

    payment = _held_payment(db, order_id)
    if not payment or payment["trip_id"] != trip_id:
        raise CheckoutError("Payment for this order is not held.", 409, "payment_not_held")

    if decision == "yes":
        release = release_one_time_payment(db, payment["id"], now_iso=now.isoformat())
        # Genuine completion: stamp both the client-confirmation time and the
        # trip completion time.
        _set_trip_and_shipment(
            db, trip_id, order_id, COMPLETED,
            trip_extra={"delivery_confirmed_at": now, "trip_completed_at": now},
        )
        notif.notify(db, order_id, trip_id, order["client_user_id"],
                     notif.DELIVERY_CONFIRMED, "You confirmed delivery. Payment released to the transporter.")
        notif.notify(db, order_id, trip_id, trip["transporter_user_id"],
                     notif.DELIVERY_CONFIRMED, "The client confirmed delivery. Your payout has been released.")
        updated = dict(db.execute("SELECT * FROM shipment_trips WHERE id = %s", (trip_id,)).fetchone())
        return {"decision": "yes", "already": False, "trip": updated,
                "payout_amount": release.get("payout_amount")}

    # decision == "no": open a dispute, keep the money held, no payout/refund.
    thread_id = _ensure_thread(db, order, trip)
    dispute, _created = _open_or_reuse_dispute(
        db, order, trip, payment, trigger="client_no", thread_id=thread_id,
        client_reason=(reason or "").strip() or None,
    )
    _set_trip_and_shipment(db, trip_id, order_id, DELIVERY_DISPUTED)
    notif.notify(db, order_id, trip_id, trip["transporter_user_id"],
                 notif.DELIVERY_DENIED, "The client reported a problem with the delivery. An admin will review it.")
    notif.notify_admins(db, order_id, trip_id, notif.DELIVERY_DENIED,
                        f"Delivery disputed by the client on order #{order_id}.")
    updated = dict(db.execute("SELECT * FROM shipment_trips WHERE id = %s", (trip_id,)).fetchone())
    return {"decision": "no", "already": False, "trip": updated,
            "dispute": serialize_dispute(dispute)}


# ---------------------------------------------------------------------------
# Phase I — 6-hour deadline processor
# ---------------------------------------------------------------------------

def process_overdue_delivery_confirmations(db, now=None):
    """Escalate every awaiting-confirmation trip whose 6-hour deadline has
    passed to admin_review, keeping the payment held and opening/reusing exactly
    one dispute. Concurrency-safe (locks each shipment with SKIP LOCKED in the
    canonical order, re-validates under the lock) and idempotent across repeated
    sweeps. Returns {'processed_count', 'processed_trip_ids'}. Caller commits."""
    now = _utcnow(now)
    candidates = db.execute(
        "SELECT id, order_id FROM shipment_trips "
        "WHERE status = %s AND confirmation_deadline_at IS NOT NULL "
        "AND confirmation_deadline_at <= %s ORDER BY id",
        (AWAITING_CLIENT_CONFIRMATION, now),
    ).fetchall()

    processed = []
    for cand in candidates:
        # Lock the shipment first (canonical order). SKIP LOCKED means a trip
        # currently being confirmed by its client is left for the next sweep.
        order_row = db.execute(
            "SELECT * FROM shipments WHERE id = %s FOR UPDATE SKIP LOCKED",
            (cand["order_id"],),
        ).fetchone()
        if not order_row:
            continue
        order = dict(order_row)
        trip = dict(db.execute(
            "SELECT * FROM shipment_trips WHERE id = %s FOR UPDATE", (cand["id"],)
        ).fetchone())
        # Re-validate status + deadline under the lock, in SQL (correct tz
        # handling), since state/deadline may have changed since the candidate read.
        still_due = db.execute(
            "SELECT 1 AS ok FROM shipment_trips WHERE id = %s AND status = %s "
            "AND confirmation_deadline_at IS NOT NULL AND confirmation_deadline_at <= %s",
            (cand["id"], AWAITING_CLIENT_CONFIRMATION, now),
        ).fetchone()
        if not still_due:
            continue

        payment = _held_payment(db, order["id"])
        thread_id = _ensure_thread(db, order, trip)
        _open_or_reuse_dispute(
            db, order, trip, payment, trigger="confirmation_timeout", thread_id=thread_id,
        )
        _set_trip_and_shipment(db, trip["id"], order["id"], ADMIN_REVIEW)
        notif.notify(db, order["id"], trip["id"], order["client_user_id"],
                     notif.CONFIRMATION_OVERDUE,
                     "You did not respond within 6 hours. An admin will now review the delivery.")
        notif.notify(db, order["id"], trip["id"], trip["transporter_user_id"],
                     notif.CONFIRMATION_OVERDUE,
                     "The client did not confirm within 6 hours. An admin will review the delivery.")
        notif.notify_admins(db, order["id"], trip["id"], notif.CONFIRMATION_OVERDUE,
                            f"Delivery confirmation timed out on order #{order['id']}.")
        processed.append(trip["id"])

    return {"processed_count": len(processed), "processed_trip_ids": processed}


# ---------------------------------------------------------------------------
# Phase H — admin dispute resolution
# ---------------------------------------------------------------------------

def _lock_dispute(db, dispute_id):
    row = db.execute(
        "SELECT * FROM shipment_disputes WHERE id = %s FOR UPDATE", (dispute_id,)
    ).fetchone()
    if not row:
        raise CheckoutError("Dispute not found.", 404, "dispute_not_found")
    return dict(row)


def _read_dispute_ids(db, dispute_id):
    """Non-locking read of a dispute's shipment/trip ids ONLY, used to discover
    which shipment+trip to lock first. Nothing here is trusted after the locks
    are taken — every field is revalidated once the dispute row is locked."""
    row = db.execute(
        "SELECT id, shipment_id, trip_id FROM shipment_disputes WHERE id = %s",
        (dispute_id,),
    ).fetchone()
    if not row:
        raise CheckoutError("Dispute not found.", 404, "dispute_not_found")
    return dict(row)


def add_transporter_statement(db, user, dispute_id, statement):
    """Transporter appends their written complaint/statement to an open dispute.
    Only the case transporter, only while the dispute is open. Locks only the
    dispute row (the tail of the canonical lock order), so it can never deadlock
    against an admin resolution that holds shipment+trip and wants the dispute.
    Caller commits."""
    text = (statement or "").strip()
    if not text:
        raise CheckoutError("A statement is required.", 400, "statement_required")
    dispute = _lock_dispute(db, dispute_id)
    if dispute["transporter_user_id"] != user["id"]:
        raise CheckoutError("Access denied.", 403)
    if dispute["status"] != "open":
        raise CheckoutError("This dispute is already resolved.", 409, "dispute_closed")
    db.execute(
        "UPDATE shipment_disputes SET transporter_statement = %s WHERE id = %s",
        (text, dispute_id),
    )
    return serialize_dispute(_lock_dispute(db, dispute_id))


def _lock_for_resolution(db, dispute_id, notes):
    """Acquire the canonical lock order shipment -> trip -> dispute for an admin
    resolution, revalidating everything under the locks. Returns (order, trip,
    dispute, notes). Never trusts the initial non-locking id read."""
    notes = (notes or "").strip()
    if not notes:
        raise CheckoutError("Admin notes are required to resolve a dispute.", 400, "notes_required")
    ids = _read_dispute_ids(db, dispute_id)          # discovery only, no lock
    order, trip = _lock_order_trip(db, ids["shipment_id"], ids["trip_id"])  # 1) shipment 2) trip
    dispute = _lock_dispute(db, dispute_id)          # 3) dispute
    # Revalidate the dispute against the freshly locked shipment/trip.
    if dispute["shipment_id"] != order["id"] or dispute["trip_id"] != trip["id"]:
        raise CheckoutError("Dispute does not match this order/trip.", 409, "dispute_mismatch")
    return order, trip, dispute, notes


def resolve_dispute_transporter_win(db, admin_user, dispute_id, notes, now=None):
    """Admin resolves in the transporter's favour: release via the SAME canonical
    payout service as Client-Yes, complete the trip/shipment. Idempotent. Locks
    in the canonical order shipment -> trip -> dispute -> payment -> wallet."""
    now = _utcnow(now)
    order, trip, dispute, notes = _lock_for_resolution(db, dispute_id, notes)
    if dispute["status"] == "resolved_transporter":
        return {"already": True, "dispute": serialize_dispute(dispute)}
    if dispute["status"] != "open":
        raise CheckoutError("This dispute is already resolved.", 409, "dispute_closed")
    if not dispute["payment_id"]:
        raise CheckoutError("This dispute has no payment to release.", 409, "no_payment")

    release_one_time_payment(db, dispute["payment_id"], now_iso=now.isoformat())  # 4) payment 5) wallet
    # Admin transporter-win is a genuine completion: stamp both timestamps.
    _set_trip_and_shipment(db, trip["id"], order["id"], COMPLETED,
                           trip_extra={"delivery_confirmed_at": now, "trip_completed_at": now})
    db.execute(
        "UPDATE shipment_disputes SET status = 'resolved_transporter', resolution = 'transporter_win', "
        "admin_user_id = %s, admin_notes = %s, resolved_at = %s WHERE id = %s",
        (admin_user["id"], notes, now, dispute_id),
    )
    notif.notify(db, order["id"], trip["id"], order["client_user_id"],
                 notif.DISPUTE_RESOLVED_TRANSPORTER,
                 "An admin resolved the dispute in the transporter's favour; the payment was released.")
    notif.notify(db, order["id"], trip["id"], trip["transporter_user_id"],
                 notif.DISPUTE_RESOLVED_TRANSPORTER,
                 "An admin resolved the dispute in your favour; your payout has been released.")
    return {"already": False, "dispute": serialize_dispute(_lock_dispute(db, dispute_id))}


def resolve_dispute_client_win(db, admin_user, dispute_id, notes, now=None):
    """Admin resolves in the client's favour: refund via the canonical refund
    service (no payout), mark the trip/shipment resolved_client (NOT completed,
    so trip_completed_at stays NULL). Idempotent. Locks in the canonical order
    shipment -> trip -> dispute -> payment -> wallet."""
    now = _utcnow(now)
    order, trip, dispute, notes = _lock_for_resolution(db, dispute_id, notes)
    if dispute["status"] == "resolved_client":
        return {"already": True, "dispute": serialize_dispute(dispute)}
    if dispute["status"] != "open":
        raise CheckoutError("This dispute is already resolved.", 409, "dispute_closed")
    if not dispute["payment_id"]:
        raise CheckoutError("This dispute has no payment to refund.", 409, "no_payment")

    refund = refund_one_time_payment(db, dispute["payment_id"], now_iso=now.isoformat())  # 4) payment 5) wallet
    _set_trip_and_shipment(db, trip["id"], order["id"], RESOLVED_CLIENT)
    db.execute(
        "UPDATE shipment_disputes SET status = 'resolved_client', resolution = 'client_win', "
        "admin_user_id = %s, admin_notes = %s, resolved_at = %s WHERE id = %s",
        (admin_user["id"], notes, now, dispute_id),
    )
    notif.notify(db, order["id"], trip["id"], order["client_user_id"],
                 notif.DISPUTE_RESOLVED_CLIENT,
                 "An admin resolved the dispute in your favour; your payment has been refunded.")
    notif.notify(db, order["id"], trip["id"], trip["transporter_user_id"],
                 notif.DISPUTE_RESOLVED_CLIENT,
                 "An admin resolved the dispute in the client's favour; the payment was refunded.")
    return {"already": False, "dispute": serialize_dispute(_lock_dispute(db, dispute_id)),
            "refund": {k: refund.get(k) for k in ("wallet_refund_amount", "card_refund_amount")}}
