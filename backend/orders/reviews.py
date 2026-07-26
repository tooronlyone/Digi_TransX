from shared.payments import CheckoutError
from shared import notifications as notif


COMMENT_MAX_LENGTH = 1000
REVIEW_ALREADY_SUBMITTED = "review_already_submitted"
REVIEW_REQUIRED = "review_required"
REVIEW_NOT_ELIGIBLE = "review_not_eligible"


def _normalize_comment(comment):
    if comment is None:
        return None
    if not isinstance(comment, str):
        raise CheckoutError("Review comment must be text.", 400, "invalid_review_comment")
    text = comment
    text = text.strip()
    if not text:
        return None
    if len(text) > COMMENT_MAX_LENGTH:
        raise CheckoutError(
            f"Review comments must be {COMMENT_MAX_LENGTH} characters or fewer.",
            400,
            "review_comment_too_long",
        )
    return text


def validate_review_payload(payload):
    if not isinstance(payload, dict):
        raise CheckoutError("Review payload must be an object.", 400, "invalid_review_payload")
    rating = payload.get("rating")
    if isinstance(rating, bool):
        raise CheckoutError("Rating must be an integer from 1 to 5.", 400, "invalid_rating")
    if isinstance(rating, int):
        rating_value = rating
    elif isinstance(rating, str) and rating.strip() in {"1", "2", "3", "4", "5"}:
        rating_value = int(rating.strip())
    else:
        raise CheckoutError("Rating must be an integer from 1 to 5.", 400, "invalid_rating")
    if rating_value < 1 or rating_value > 5:
        raise CheckoutError("Rating must be an integer from 1 to 5.", 400, "invalid_rating")
    return {
        "rating": rating_value,
        "comment": _normalize_comment(payload.get("comment")),
    }


def serialize_review(row):
    return {
        "id": row.get("id"),
        "shipment_id": row.get("shipment_id"),
        "trip_id": row.get("trip_id"),
        "client_user_id": row.get("client_user_id"),
        "transporter_user_id": row.get("transporter_user_id"),
        "rating": int(row.get("rating")) if row.get("rating") is not None else None,
        "comment": row.get("comment"),
        "created_at": row.get("created_at"),
    }


def _review_row(db, trip_id):
    row = db.execute(
        "SELECT * FROM shipment_trip_reviews WHERE trip_id = %s FOR UPDATE",
        (trip_id,),
    ).fetchone()
    return dict(row) if row else None


def _client_win_dispute_exists(db, trip_id):
    row = db.execute(
        """
        SELECT 1 AS ok
        FROM shipment_disputes
        WHERE trip_id = %s
          AND (status = 'resolved_client' OR resolution = 'client_win')
        LIMIT 1
        """,
        (trip_id,),
    ).fetchone()
    return bool(row)


def _assert_reviewable(order, trip, *, allow_awaiting_confirmation=False):
    if trip["order_id"] != order["id"]:
        raise CheckoutError("Trip does not belong to this order.", 409, REVIEW_NOT_ELIGIBLE)
    eligible_statuses = {"completed"}
    if allow_awaiting_confirmation:
        eligible_statuses.add("awaiting_client_confirmation")
    if trip["status"] not in eligible_statuses:
        raise CheckoutError("This trip is not eligible for review.", 409, REVIEW_NOT_ELIGIBLE)


def _existing_replay_or_conflict(existing, payload):
    if not existing:
        return None
    existing_comment = (existing.get("comment") or "").strip() or None
    if int(existing["rating"]) == payload["rating"] and existing_comment == payload["comment"]:
        return {"already": True, "review": existing}
    raise CheckoutError(
        "A review has already been submitted for this trip.",
        409,
        REVIEW_ALREADY_SUBMITTED,
    )


def create_review_for_locked_trip(
    db,
    order,
    trip,
    user,
    payload,
    *,
    allow_awaiting_confirmation=False,
    allow_create=True,
):
    if order["client_user_id"] != user["id"]:
        raise CheckoutError("Access denied.", 403)
    if trip["transporter_user_id"] == user["id"]:
        raise CheckoutError("Transporters cannot review their own trip.", 403, REVIEW_NOT_ELIGIBLE)
    _assert_reviewable(
        order,
        trip,
        allow_awaiting_confirmation=allow_awaiting_confirmation,
    )
    if _client_win_dispute_exists(db, trip["id"]):
        raise CheckoutError(
            "Transporter reviews are not allowed for client-refunded trips.",
            409,
            REVIEW_NOT_ELIGIBLE,
        )

    existing = _review_row(db, trip["id"])
    replay = _existing_replay_or_conflict(existing, payload)
    if replay:
        return replay
    if not allow_create:
        raise CheckoutError(
            "This delivery can no longer be confirmed here.",
            409,
            "not_awaiting_confirmation",
        )

    inserted = db.execute(
        """
        INSERT INTO shipment_trip_reviews (
            shipment_id, trip_id, client_user_id, transporter_user_id, rating, comment
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (trip_id) DO NOTHING
        RETURNING *
        """,
        (
            order["id"],
            trip["id"],
            order["client_user_id"],
            trip["transporter_user_id"],
            payload["rating"],
            payload["comment"],
        ),
    ).fetchone()
    if inserted:
        return {"already": False, "review": dict(inserted)}

    existing = _review_row(db, trip["id"])
    replay = _existing_replay_or_conflict(existing, payload)
    if replay:
        return replay
    raise CheckoutError("Review could not be saved.", 500, "review_create_failed")


PENDING_REVIEW_SQL = """
    SELECT
        s.id AS shipment_id,
        t.id AS trip_id,
        COALESCE(NULLIF(trim(u.full_name), ''), u.email, 'Transporter') AS transporter_name,
        tp.company_name AS transporter_company_name,
        s.pickup_city,
        s.dropoff_city,
        s.goods_type,
        t.trip_completed_at
    FROM shipments s
    JOIN shipment_trips t ON t.order_id = s.id
    JOIN users u ON u.id = t.transporter_user_id
    LEFT JOIN transporter_profiles tp ON tp.user_id = t.transporter_user_id
    LEFT JOIN shipment_trip_reviews r ON r.trip_id = t.id
    WHERE s.client_user_id = %s
      AND t.status = 'completed'
      AND r.id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM shipment_disputes dx
          WHERE dx.trip_id = t.id
            AND (dx.status = 'resolved_client' OR dx.resolution = 'client_win')
      )
    ORDER BY COALESCE(t.trip_completed_at, t.updated_at, t.created_at) ASC, t.id ASC
"""


def fetch_pending_reviews(db, client_user_id):
    rows = db.execute(PENDING_REVIEW_SQL, (client_user_id,)).fetchall()
    return [
        {
            "shipment_id": row["shipment_id"],
            "trip_id": row["trip_id"],
            "transporter_name": row["transporter_company_name"] or row["transporter_name"],
            "pickup_city": row["pickup_city"],
            "dropoff_city": row["dropoff_city"],
            "goods_type": row["goods_type"],
            "trip_completed_at": row["trip_completed_at"],
        }
        for row in rows
    ]


def first_pending_review(db, client_user_id):
    rows = fetch_pending_reviews(db, client_user_id)
    return rows[0] if rows else None


def submit_pending_review(db, user, order_id, trip_id, payload):
    order_row = db.execute(
        "SELECT * FROM shipments WHERE id = %s FOR UPDATE",
        (order_id,),
    ).fetchone()
    if not order_row:
        raise CheckoutError("Order not found.", 404)
    trip_row = db.execute(
        "SELECT * FROM shipment_trips WHERE id = %s AND order_id = %s FOR UPDATE",
        (trip_id, order_id),
    ).fetchone()
    if not trip_row:
        raise CheckoutError("Trip not found.", 404)
    result = create_review_for_locked_trip(db, dict(order_row), dict(trip_row), user, payload)
    if not result["already"]:
        notif.notify(
            db,
            order_id,
            trip_id,
            trip_row["transporter_user_id"],
            notif.REVIEW_SUBMITTED,
            "A client submitted a transporter review for your completed delivery.",
        )
    return {
        "already": result["already"],
        "review": serialize_review(result["review"]),
    }


def get_review_for_trip(db, user, order_id, trip_id):
    role = (user.get("role") or "").strip().lower()
    target = db.execute(
        """
        SELECT s.client_user_id, t.transporter_user_id
        FROM shipments s
        JOIN shipment_trips t ON t.order_id = s.id
        WHERE s.id = %s AND t.id = %s
        """,
        (order_id, trip_id),
    ).fetchone()
    if not target:
        raise CheckoutError("Order or trip not found.", 404)
    if (
        role not in ("admin", "platform_admin")
        and target["client_user_id"] != user["id"]
        and target["transporter_user_id"] != user["id"]
    ):
        raise CheckoutError("Access denied.", 403)
    row = db.execute(
        """
        SELECT r.*
        FROM shipment_trip_reviews r
        WHERE r.shipment_id = %s AND r.trip_id = %s
        """,
        (order_id, trip_id),
    ).fetchone()
    return serialize_review(dict(row)) if row else None
