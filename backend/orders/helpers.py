import json

from auth.helpers import json_response
from wallet.helpers import round_money


def parse_truck_types(value):
    """required_truck_types is stored as a JSON array string.

    Single source of truth for reading that column, used by both the
    serializer and the order routes.
    """
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def serialize_order(order_dict, bid_count=0):
    """Serialize order for API response."""
    return {
        "id": order_dict.get("id"),
        "client_user_id": order_dict.get("client_user_id"),
        "pickup_city": order_dict.get("pickup_city"),
        "pickup_area": order_dict.get("pickup_area"),
        "dropoff_city": order_dict.get("dropoff_city"),
        "dropoff_area": order_dict.get("dropoff_area"),
        "pickup_location": order_dict.get("pickup_location") or order_dict.get("pickup_city"),
        "pickup_lat": order_dict.get("pickup_lat"),
        "pickup_lng": order_dict.get("pickup_lng"),
        "dropoff_location": order_dict.get("dropoff_location") or order_dict.get("dropoff_city"),
        "dropoff_lat": order_dict.get("dropoff_lat"),
        "dropoff_lng": order_dict.get("dropoff_lng"),
        "pickup_date": order_dict.get("pickup_date"),
        "pickup_time": order_dict.get("pickup_time"),
        "goods_type": order_dict.get("goods_type"),
        "goods_category": order_dict.get("goods_category"),
        "goods_form": order_dict.get("goods_form"),
        "goods_commodity": order_dict.get("goods_commodity"),
        "length_cm": order_dict.get("length_cm"),
        "width_cm": order_dict.get("width_cm"),
        "height_cm": order_dict.get("height_cm"),
        "volume_liters": round_money(order_dict.get("volume_liters")) if order_dict.get("volume_liters") else None,
        "quantity": order_dict.get("quantity"),
        "animal_count": order_dict.get("animal_count"),
        "temperature_c": order_dict.get("temperature_c"),
        "required_truck_types": parse_truck_types(order_dict.get("required_truck_types")),
        "is_refrigerated": bool(order_dict.get("is_refrigerated")),
        "is_hazardous": bool(order_dict.get("is_hazardous")),
        "is_food_grade": bool(order_dict.get("is_food_grade")),
        "goods_weight_tons": round_money(order_dict.get("goods_weight_tons", 0)),
        "goods_volume_cbm": round_money(order_dict.get("goods_volume_cbm")) if order_dict.get("goods_volume_cbm") else None,
        "estimated_budget": round_money(order_dict.get("estimated_budget")) if order_dict.get("estimated_budget") else None,
        "notes": order_dict.get("notes"),
        "status": order_dict.get("status"),
        "accepted_bid_id": order_dict.get("accepted_bid_id"),
        "payment_amount": round_money(order_dict.get("payment_amount")) if order_dict.get("payment_amount") else None,
        "payment_status": order_dict.get("payment_status"),
        "bid_count": bid_count,
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
    row = db.execute("SELECT * FROM shipments WHERE id = ?", (order_id,)).fetchone()
    return dict(row) if row else None


def fetch_bids_for_order(db, order_id):
    """Fetch all bids for an order."""
    rows = db.execute(
        "SELECT * FROM shipment_bids WHERE order_id = ? ORDER BY created_at ASC",
        (order_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def validate_order_creation(data):
    """Validate order creation data."""
    # NOTE: goods_weight_tons is validated in create_order based on the goods
    # taxonomy (liquids need volume, not weight), so it's not required here.
    # pickup_city / dropoff_city carry the single detailed location text.
    required_fields = [
        "pickup_city", "dropoff_city",
        "pickup_date", "pickup_time", "goods_type"
    ]

    for field in required_fields:
        value = (data.get(field) or "").strip() if isinstance(data.get(field), str) else data.get(field)
        if not value and field != "goods_volume_cbm" and field != "notes" and field != "estimated_budget":
            return json_response(
                {"success": False, "message": f"{field.replace('_', ' ').title()} is required."},
                400
            )

    return None


def _to_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# Small tolerance so exact-boundary loads (e.g. 25.0 t on a 25 t truck) pass.
_CAP_EPS = 1e-6

# Cargo-bed dimensions are entered by transporters in feet; goods dimensions are
# captured from clients in centimetres. Convert feet -> cm for comparison.
_FT_TO_CM = 30.48


def _fits_on_bed(order, truck):
    """Return None if the goods fit the truck bed, else a human message.

    Axis-aligned comparison: the load's length/width/height (cm, from the client)
    must each be <= the truck bed's matching length/width/height (feet -> cm). This
    matches how the fields are labelled, so a 20 ft steel bar (sariya) is compared
    against the bed's LENGTH, not stood upright. A truck-bed axis left blank/zero
    (e.g. the open top of a flatbed) is treated as unbounded and skipped, and a
    goods axis that wasn't provided is skipped too. This is what stops a long
    sariya/girder load from being matched to a short truck.
    """
    for axis, goods_key, bed_key in (
        ("length", "length_cm", "bed_length_ft"),
        ("width", "width_cm", "bed_width_ft"),
        ("height", "height_cm", "bed_height_ft"),
    ):
        g = _to_float(order.get(goods_key))
        b_ft = _to_float(truck.get(bed_key))
        if not g or g <= 0 or not b_ft or b_ft <= 0:
            continue
        b_cm = b_ft * _FT_TO_CM
        if g > b_cm + _CAP_EPS:
            return (
                f"The load's {axis} is {g / _FT_TO_CM:.1f} ft, but this truck's cargo bed "
                f"{axis} is only {b_ft:g} ft. Please use a bigger truck."
            )
    return None


def truck_order_mismatch(truck, required_types, order):
    """Return None if the truck can serve the order, else a human message.

    Checks, in order:
      1. Truck TYPE is one of the order's suitable/required truck types.
      2. Truck WEIGHT capacity (capacity_tons / payload_max_tons) >= order weight.
      3. Truck VOLUME capacity (volume_max_cbm) >= order volume, when both known.
    Capacity checks are skipped when the relevant figure is missing or zero
    (0 acts as "not specified", e.g. flatbeds/livestock carriers).
    """
    # 1) Type
    if required_types:
        key = (truck.get("catalog_type_key") or truck.get("truck_type") or "").strip()
        if key not in required_types:
            return "This truck type cannot carry these goods. Please use a suitable truck."

    # 2) Weight capacity
    weight = _to_float(order.get("goods_weight_tons")) or 0
    capacity = _to_float(truck.get("capacity_tons"))
    if capacity is None or capacity <= 0:
        capacity = _to_float(truck.get("payload_max_tons"))
    if weight > 0 and capacity is not None and capacity > 0 and weight > capacity + _CAP_EPS:
        return (
            f"This truck can carry up to {capacity:g} tons, but the load is {weight:g} tons. "
            "Please use a higher-capacity truck."
        )

    # 3) Volume capacity
    volume = _to_float(order.get("goods_volume_cbm")) or 0
    volume_max = _to_float(truck.get("volume_max_cbm"))
    if volume > 0 and volume_max is not None and volume_max > 0 and volume > volume_max + _CAP_EPS:
        return (
            f"This truck holds up to {volume_max:g} cbm, but the load needs {volume:g} cbm. "
            "Please use a larger truck."
        )

    # 4) Physical dimensions (length/width/height) fit on the cargo bed.
    dim_error = _fits_on_bed(order, truck)
    if dim_error:
        return dim_error

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
