from datetime import datetime, timedelta

from auth.helpers import json_response, timestamp_bundle
from trucks.helpers import TRUCK_TYPES, get_catalog_type
from wallet.helpers import (
    CLIENT_MINIMUM_REQUIRED,
    TRANSPORTER_MINIMUM_REQUIRED,
    adjust_wallet_balance,
    available_balance,
    ensure_wallet_unlocked_balance,
    get_or_create_wallet_for_user,
    round_money,
)


ORDER_STATUS_OPEN = "open"
ORDER_STATUS_ACCEPTED = "accepted"
ORDER_STATUS_IN_PROGRESS = "in_progress"
ORDER_STATUS_COMPLETED = "completed"
ORDER_STATUS_CANCELLED = "cancelled"
ORDER_STATUSES = {
    ORDER_STATUS_OPEN,
    ORDER_STATUS_ACCEPTED,
    ORDER_STATUS_IN_PROGRESS,
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_CANCELLED,
}
BID_STATUS_PENDING = "pending"
BID_STATUS_ACCEPTED = "accepted"
BID_STATUS_NOT_SELECTED = "not_selected"
BID_STATUS_WITHDRAWN = "withdrawn"
CLIENT_ORDER_ROLES = {"service_seeker", "everyday_user", "client"}
TRANSPORTER_ORDER_ROLES = {"logistics_provider", "transporter"}
MINIMUM_ORDER_WALLET_BALANCE = round_money(CLIENT_MINIMUM_REQUIRED)
TRIP_STAGE_NOT_STARTED = "not_started"
TRIP_STAGE_IN_CITY = "in_city"
TRIP_STAGE_LEFT_CITY = "left_city"
TRIP_STAGE_LOADED = "loaded"
TRIP_STAGE_COMPLETED = "completed"
TRIP_STAGES = [
    TRIP_STAGE_NOT_STARTED,
    TRIP_STAGE_IN_CITY,
    TRIP_STAGE_LEFT_CITY,
    TRIP_STAGE_LOADED,
    TRIP_STAGE_COMPLETED,
]
TRIP_STAGE_PROGRESS = {stage: index for index, stage in enumerate(TRIP_STAGES)}
PENALTY_TYPE_FIXED = "fixed"
PENALTY_TYPE_NEGOTIATED = "negotiated"
CANCELLATION_STATUS_PENDING = "pending"
CANCELLATION_STATUS_FINALIZED = "finalized"
CANCELLATION_STATUS_PAID = "paid"
NEGOTIATION_MIN_PERCENT = 10.0
NEGOTIATION_MAX_PERCENT = 25.0
NEGOTIATION_DEFAULT_HOURS = 48
TRUCK_TYPE_OPTIONS = [
    {"type_key": item["type_key"], "display_name": item["display_name"]}
    for item in TRUCK_TYPES
]


def normalize_role(role):
    return (role or "").strip().lower()


def require_client_role(user):
    if normalize_role(user.get("role")) not in CLIENT_ORDER_ROLES:
        return json_response({"success": False, "message": "Client account required."}, 403)
    return None


def require_transporter_role(user):
    if normalize_role(user.get("role")) not in TRANSPORTER_ORDER_ROLES:
        return json_response({"success": False, "message": "Transporter account required."}, 403)
    return None


def parse_required_text(data, field_name, label):
    value = (data.get(field_name) or "").strip()
    if not value:
        raise ValueError(f"{label} is required.")
    return value


def parse_optional_text(data, field_name):
    value = (data.get(field_name) or "").strip()
    return value or None


def parse_optional_float(data, field_name, label):
    value = data.get(field_name)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a valid number.")


def parse_required_positive_float(data, field_name, label):
    try:
        value = float(data.get(field_name))
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a valid number.")
    if value <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    return value


def validate_required_truck_type(type_key):
    if not get_catalog_type(type_key):
        raise ValueError("Required truck type is invalid.")
    return type_key


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def accepted_bid_lookup(db, order):
    accepted_bid_id = order.get("accepted_bid_id")
    if not accepted_bid_id:
        return None
    row = db.execute(
        """
        SELECT ob.*, u.role AS transporter_role
        FROM order_bids ob
        LEFT JOIN users u ON u.id = ob.transporter_user_id
        WHERE ob.id = ? AND ob.order_id = ?
        """,
        (accepted_bid_id, order["id"]),
    ).fetchone()
    return dict(row) if row else None


def get_order_cancellation(db, order_id):
    row = db.execute("SELECT * FROM order_cancellations WHERE order_id = ? ORDER BY id DESC LIMIT 1", (order_id,)).fetchone()
    return dict(row) if row else None


def determine_cancellation_context(order, accepted_bid, cancelled_by, now=None):
    bid_price = round_money((accepted_bid or {}).get("bid_price"))
    trip_stage = (order.get("trip_stage") or TRIP_STAGE_NOT_STARTED).strip().lower() or TRIP_STAGE_NOT_STARTED
    current_time = now or datetime.now()
    if cancelled_by == "client":
        if trip_stage in {TRIP_STAGE_NOT_STARTED, TRIP_STAGE_IN_CITY}:
            penalty_percent = 8.0
            return {
                "case_code": "A",
                "penalty_type": PENALTY_TYPE_FIXED,
                "penalty_percent": penalty_percent,
                "company_share_percent": 3.0,
                "recipient_share_percent": penalty_percent - 3.0,
                "recipient_user_id": accepted_bid["transporter_user_id"],
                "recipient_role": "transporter",
                "bid_price": bid_price,
            }
        if trip_stage in {TRIP_STAGE_LEFT_CITY, TRIP_STAGE_LOADED}:
            return {
                "case_code": "B" if trip_stage == TRIP_STAGE_LEFT_CITY else "C",
                "penalty_type": PENALTY_TYPE_NEGOTIATED,
                "company_share_percent": 5.0,
                "recipient_user_id": accepted_bid["transporter_user_id"],
                "recipient_role": "transporter",
                "bid_price": bid_price,
            }
    elif cancelled_by == "transporter":
        accepted_at = parse_iso_datetime(order.get("accepted_at"))
        minutes_since_accept = ((current_time - accepted_at).total_seconds() / 60) if accepted_at else 999999
        if minutes_since_accept <= 30:
            penalty_percent = 10.0
            return {
                "case_code": "D",
                "penalty_type": PENALTY_TYPE_FIXED,
                "penalty_percent": penalty_percent,
                "company_share_percent": 5.0,
                "recipient_share_percent": penalty_percent - 5.0,
                "recipient_user_id": order["client_user_id"],
                "recipient_role": "client",
                "bid_price": bid_price,
            }
        return {
            "case_code": "E",
            "penalty_type": PENALTY_TYPE_NEGOTIATED,
            "company_share_percent": 7.0,
            "recipient_user_id": order["client_user_id"],
            "recipient_role": "client",
            "bid_price": bid_price,
        }
    return None


def calculate_cancellation_amounts(context, penalty_percent):
    percent = round_money(penalty_percent)
    bid_price = round_money(context["bid_price"])
    penalty_amount = round_money(bid_price * percent / 100)
    company_share_amount = round_money(bid_price * round_money(context["company_share_percent"]) / 100)
    recipient_share_amount = round_money(max(penalty_amount - company_share_amount, 0))
    return {
        "penalty_percent": percent,
        "penalty_amount": penalty_amount,
        "company_share_percent": round_money(context["company_share_percent"]),
        "company_share_amount": company_share_amount,
        "recipient_share_amount": recipient_share_amount,
    }


def serialize_cancellation(row):
    if not row:
        return None
    return {
        "id": row.get("id"),
        "order_id": row.get("order_id"),
        "cancelled_by": row.get("cancelled_by"),
        "cancelled_by_user_id": row.get("cancelled_by_user_id"),
        "other_party_user_id": row.get("other_party_user_id"),
        "trip_stage_at_cancellation": row.get("trip_stage_at_cancellation"),
        "penalty_type": row.get("penalty_type"),
        "penalty_percent": round_money(row.get("penalty_percent")) if row.get("penalty_percent") is not None else None,
        "penalty_amount": round_money(row.get("penalty_amount")) if row.get("penalty_amount") is not None else None,
        "company_share_percent": round_money(row.get("company_share_percent")) if row.get("company_share_percent") is not None else None,
        "company_share_amount": round_money(row.get("company_share_amount")) if row.get("company_share_amount") is not None else None,
        "recipient_share_amount": round_money(row.get("recipient_share_amount")) if row.get("recipient_share_amount") is not None else None,
        "status": row.get("status"),
        "negotiation_deadline": row.get("negotiation_deadline"),
        "finalized_at": row.get("finalized_at"),
        "proposed_percent": round_money(row.get("proposed_percent")) if row.get("proposed_percent") is not None else None,
        "proposed_by_user_id": row.get("proposed_by_user_id"),
        "proposed_at": row.get("proposed_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def settle_cancellation_payment(db, order, cancellation, context, penalty_percent, finalized_at=None, auto_finalize=False):
    final_stamp = timestamp_bundle()
    finalized_value = finalized_at or final_stamp["iso"]
    amounts = calculate_cancellation_amounts(context, penalty_percent)
    cancelling_user_id = cancellation["cancelled_by_user_id"]
    recipient_user_id = context["recipient_user_id"]

    cancelling_user = {"id": cancelling_user_id, "role": "client" if cancellation["cancelled_by"] == "client" else "transporter"}
    recipient_user = {"id": recipient_user_id, "role": context["recipient_role"]}
    payer_wallet, payer_error = get_or_create_wallet_for_user(db, cancelling_user)
    if payer_error:
        return None, payer_error
    recipient_wallet, recipient_error = get_or_create_wallet_for_user(db, recipient_user)
    if recipient_error:
        return None, recipient_error

    hold_amount = round_money(CLIENT_MINIMUM_REQUIRED if cancellation["cancelled_by"] == "client" else TRANSPORTER_MINIMUM_REQUIRED)
    unlock_amount = min(round_money(payer_wallet["locked_balance"]), hold_amount)
    if unlock_amount > 0:
        unlock_error = ensure_wallet_unlocked_balance(
            db,
            payer_wallet,
            cancelling_user_id,
            unlock_amount,
            reason="cancellation_penalty_unlock",
            reference_id=str(order["id"]),
        )
        if unlock_error:
            return None, unlock_error

    deduct_error = adjust_wallet_balance(
        db,
        payer_wallet,
        cancelling_user_id,
        -amounts["penalty_amount"],
        "penalty_paid",
        description=f"Cancellation penalty for order #{order['id']}",
        reference_id=str(order["id"]),
    )
    if deduct_error:
        return None, deduct_error
    if amounts["recipient_share_amount"] > 0:
        credit_error = adjust_wallet_balance(
            db,
            recipient_wallet,
            recipient_user_id,
            amounts["recipient_share_amount"],
            "penalty_received",
            description=f"Cancellation penalty received for order #{order['id']}",
            reference_id=str(order["id"]),
        )
        if credit_error:
            return None, credit_error

    db.execute(
        """
        UPDATE order_cancellations
        SET penalty_percent = ?, penalty_amount = ?, company_share_percent = ?, company_share_amount = ?,
            recipient_share_amount = ?, status = ?, finalized_at = ?, updated_at = ?,
            proposed_percent = COALESCE(proposed_percent, ?)
        WHERE id = ?
        """,
        (
            amounts["penalty_percent"],
            amounts["penalty_amount"],
            amounts["company_share_percent"],
            amounts["company_share_amount"],
            amounts["recipient_share_amount"],
            CANCELLATION_STATUS_FINALIZED,
            finalized_value,
            final_stamp["iso"],
            amounts["penalty_percent"] if auto_finalize else None,
            cancellation["id"],
        ),
    )
    db.execute(
        "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
        (ORDER_STATUS_CANCELLED, final_stamp["display"], order["id"]),
    )
    updated = get_order_cancellation(db, order["id"])
    return updated, None


def check_expired_negotiations(db):
    current_time = datetime.now()
    rows = db.execute(
        """
        SELECT oc.*, o.client_user_id, o.accepted_bid_id, o.accepted_at, o.trip_stage
        FROM order_cancellations oc
        JOIN orders o ON o.id = oc.order_id
        WHERE oc.status = ? AND oc.negotiation_deadline IS NOT NULL
        ORDER BY oc.id ASC
        """,
        (CANCELLATION_STATUS_PENDING,),
    ).fetchall()
    for row in rows:
        cancellation = dict(row)
        deadline = parse_iso_datetime(cancellation.get("negotiation_deadline"))
        if not deadline or deadline > current_time:
            continue
        order = {
            "id": cancellation["order_id"],
            "client_user_id": cancellation["client_user_id"],
            "accepted_bid_id": cancellation["accepted_bid_id"],
            "accepted_at": cancellation["accepted_at"],
            "trip_stage": cancellation["trip_stage"],
        }
        accepted_bid = accepted_bid_lookup(db, order)
        if not accepted_bid:
            continue
        context = determine_cancellation_context(order, accepted_bid, cancellation["cancelled_by"], now=current_time)
        if not context:
            continue
        settle_cancellation_payment(db, order, cancellation, context, NEGOTIATION_MIN_PERCENT, auto_finalize=True)


def serialize_order(row, bid_count=0):
    catalog = get_catalog_type(row.get("required_truck_type"))
    return {
        "id": row.get("id"),
        "client_user_id": row.get("client_user_id"),
        "pickup_city": row.get("pickup_city"),
        "pickup_area": row.get("pickup_area") or "",
        "dropoff_city": row.get("dropoff_city"),
        "dropoff_area": row.get("dropoff_area") or "",
        "pickup_date": row.get("pickup_date"),
        "pickup_time": row.get("pickup_time"),
        "goods_type": row.get("goods_type"),
        "goods_weight_tons": row.get("goods_weight_tons"),
        "goods_volume_cbm": row.get("goods_volume_cbm"),
        "required_truck_type": row.get("required_truck_type"),
        "required_truck_type_name": catalog.get("display_name") if catalog else row.get("required_truck_type"),
        "estimated_budget": round_money(row.get("estimated_budget")) if row.get("estimated_budget") is not None else None,
        "notes": row.get("notes") or "",
        "status": row.get("status"),
        "accepted_bid_id": row.get("accepted_bid_id"),
        "trip_started_at": row.get("trip_started_at"),
        "trip_stage": row.get("trip_stage") or TRIP_STAGE_NOT_STARTED,
        "accepted_at": row.get("accepted_at"),
        "bid_count": int(bid_count or row.get("bid_count") or 0),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def serialize_bid(row):
    return {
        "id": row.get("id"),
        "order_id": row.get("order_id"),
        "transporter_user_id": row.get("transporter_user_id"),
        "transporter_name": row.get("transporter_name") or "Transporter",
        "transporter_rating": row.get("transporter_rating"),
        "truck_id": row.get("truck_id"),
        "truck_number": row.get("truck_number") or "",
        "truck_type": row.get("truck_type") or "",
        "catalog_type_key": row.get("catalog_type_key") or "",
        "bid_price": round_money(row.get("bid_price")),
        "message": row.get("message") or "",
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def client_wallet_shortfall_response():
    return json_response(
        {
            "success": False,
            "message": "Minimum wallet balance of Rs 20,000 required to place an order. Please top up your wallet.",
        },
        400,
    )


def has_minimum_available_balance(wallet):
    return available_balance(wallet) + 1e-9 >= MINIMUM_ORDER_WALLET_BALANCE
