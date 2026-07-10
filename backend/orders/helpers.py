from auth.helpers import json_response
from trucks.helpers import get_catalog_type
from wallet.helpers import round_money


def serialize_order(order_dict, truck_requirements=None, bid_count=0):
    """Serialize order for API response."""
    if truck_requirements is None:
        truck_requirements = []

    return {
        "id": order_dict.get("id"),
        "client_user_id": order_dict.get("client_user_id"),
        "pickup_city": order_dict.get("pickup_city"),
        "pickup_area": order_dict.get("pickup_area"),
        "dropoff_city": order_dict.get("dropoff_city"),
        "dropoff_area": order_dict.get("dropoff_area"),
        "pickup_date": order_dict.get("pickup_date"),
        "pickup_time": order_dict.get("pickup_time"),
        "goods_type": order_dict.get("goods_type"),
        "goods_weight_tons": round_money(order_dict.get("goods_weight_tons", 0)),
        "goods_volume_cbm": round_money(order_dict.get("goods_volume_cbm")) if order_dict.get("goods_volume_cbm") else None,
        "estimated_budget": round_money(order_dict.get("estimated_budget")) if order_dict.get("estimated_budget") else None,
        "notes": order_dict.get("notes"),
        "status": order_dict.get("status"),
        "accepted_bid_id": order_dict.get("accepted_bid_id"),
        "payment_amount": round_money(order_dict.get("payment_amount")) if order_dict.get("payment_amount") else None,
        "payment_status": order_dict.get("payment_status"),
        "bid_count": bid_count,
        "required_truck_types": truck_requirements,
        "created_at": order_dict.get("created_at"),
        "updated_at": order_dict.get("updated_at"),
    }


def serialize_bid(bid_dict):
    """Serialize bid for API response."""
    return {
        "id": bid_dict.get("id"),
        "order_id": bid_dict.get("order_id"),
        "transporter_user_id": bid_dict.get("transporter_user_id"),
        "truck_id": bid_dict.get("truck_id"),
        "bid_price": round_money(bid_dict.get("bid_price", 0)),
        "message": bid_dict.get("message"),
        "status": bid_dict.get("status"),
        "created_at": bid_dict.get("created_at"),
        "updated_at": bid_dict.get("updated_at"),
    }


def serialize_trip(trip_dict):
    """Serialize trip for API response."""
    return {
        "id": trip_dict.get("id"),
        "order_id": trip_dict.get("order_id"),
        "accepted_bid_id": trip_dict.get("accepted_bid_id"),
        "transporter_user_id": trip_dict.get("transporter_user_id"),
        "truck_id": trip_dict.get("truck_id"),
        "status": trip_dict.get("status"),
        "trip_started_at": trip_dict.get("trip_started_at"),
        "trip_completed_at": trip_dict.get("trip_completed_at"),
        "delivery_confirmed_at": trip_dict.get("delivery_confirmed_at"),
        "actual_distance_km": round_money(trip_dict.get("actual_distance_km")) if trip_dict.get("actual_distance_km") else None,
        "created_at": trip_dict.get("created_at"),
        "updated_at": trip_dict.get("updated_at"),
    }


def fetch_order(db, order_id):
    """Fetch order by ID."""
    row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return dict(row) if row else None


def fetch_bids_for_order(db, order_id):
    """Fetch all bids for an order."""
    rows = db.execute(
        "SELECT * FROM order_bids WHERE order_id = ? ORDER BY created_at ASC",
        (order_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def validate_order_creation(data):
    """Validate order creation data."""
    required_fields = [
        "pickup_city", "pickup_area", "dropoff_city", "dropoff_area",
        "pickup_date", "pickup_time", "goods_type", "goods_weight_tons",
        "required_truck_types"
    ]

    for field in required_fields:
        value = (data.get(field) or "").strip() if isinstance(data.get(field), str) else data.get(field)
        if not value and field != "goods_volume_cbm" and field != "notes" and field != "estimated_budget":
            return json_response(
                {"success": False, "message": f"{field.replace('_', ' ').title()} is required."},
                400
            )

    # Validate truck types
    truck_types = data.get("required_truck_types")
    if not isinstance(truck_types, list) or len(truck_types) == 0:
        return json_response(
            {"success": False, "message": "At least one truck type is required."},
            400
        )

    return None


def calculate_no_show_penalty(bid_price):
    """Calculate penalty for no-show or cancellation."""
    return round_money(bid_price * 0.15)


def get_or_create_order_for_client(db, client_user_id, order_data):
    """Helper to create or validate order for client."""
    validation_error = validate_order_creation(order_data)
    if validation_error:
        return None, validation_error
    return True, None
