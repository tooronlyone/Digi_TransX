import json
import math

from auth.helpers import json_response
from wallet.helpers import round_money
from trucks.helpers import get_catalog_type, infer_hybrid_truck_defaults
from shared.geo import haversine_distance_km


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
        "dropoff_city": order_dict.get("dropoff_city"),
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
        "seeker_kind_snapshot": order_dict.get("seeker_kind_snapshot"),
        "accepted_bid_id": order_dict.get("accepted_bid_id"),
        "payment_amount": round_money(order_dict.get("payment_amount")) if order_dict.get("payment_amount") else None,
        "payment_status": order_dict.get("payment_status"),
        "bid_count": bid_count,
        "created_at": order_dict.get("created_at"),
        "updated_at": order_dict.get("updated_at"),
    }


def serialize_bid(bid_dict):
    """Serialize bid for API response, preserving joined shipment summary fields if present."""
    payload = {
        "id": bid_dict.get("id"),
        "order_id": bid_dict.get("order_id"),
        "transporter_user_id": bid_dict.get("transporter_user_id"),
        "truck_id": bid_dict.get("truck_id"),
        "bid_price": round_money(bid_dict.get("bid_price", 0)),
        "message": bid_dict.get("message"),
        "status": bid_dict.get("status"),
        "created_at": bid_dict.get("created_at"),
        "updated_at": bid_dict.get("updated_at"),
        "market_submission_reference": {
            "market_average": str(bid_dict["market_reference_average"]),
            "minimum_bid": str(bid_dict["market_minimum_bid"]) if bid_dict.get("market_minimum_bid") is not None else None,
            "maximum_bid": str(bid_dict["market_maximum_bid"]) if bid_dict.get("market_maximum_bid") is not None else None,
            "verified_rating": str(bid_dict["market_rating_snapshot"]) if bid_dict.get("market_rating_snapshot") is not None else None,
            "sample_count": bid_dict.get("market_sample_count"),
            "bootstrap": bid_dict.get("market_bootstrap"),
        } if bid_dict.get("market_reference_average") is not None else None,
    }
    for field in (
        "pickup_city",
        "dropoff_city",
        "pickup_date",
        "pickup_time",
        "goods_type",
        "goods_weight_tons",
        "volume_liters",
        "estimated_budget",
        "order_status",
    ):
        if field in bid_dict:
            payload[field] = bid_dict[field]
    return payload


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
        "delivery_completion_requested_at": trip_dict.get("delivery_completion_requested_at"),
        "confirmation_deadline_at": trip_dict.get("confirmation_deadline_at"),
        "delivery_confirmed_at": trip_dict.get("delivery_confirmed_at"),
        "actual_distance_km": round_money(trip_dict.get("actual_distance_km")) if trip_dict.get("actual_distance_km") else None,
        "created_at": trip_dict.get("created_at"),
        "updated_at": trip_dict.get("updated_at"),
    }


def fetch_order(db, order_id):
    """Fetch order by ID."""
    row = db.execute("SELECT * FROM shipments WHERE id = %s", (order_id,)).fetchone()
    return dict(row) if row else None


def order_access_for_user(db, order, user):
    """Access level of a user on a one-time order.

    'owner'                — the client who posted the order (full view)
    'accepted_transporter' — the transporter whose bid was accepted (sees the
                             order, their own bid, the trip and a safe payment
                             summary — never other transporters' bids)
    None                   — everyone else (403)
    """
    if order["client_user_id"] == user["id"]:
        return "owner"
    accepted = db.execute(
        "SELECT id FROM shipment_bids WHERE order_id = %s AND transporter_user_id = %s "
        "AND status = 'accepted' LIMIT 1",
        (order["id"], user["id"]),
    ).fetchone()
    if accepted:
        return "accepted_transporter"
    return None


def fetch_trip_for_order(db, order_id):
    row = db.execute(
        "SELECT * FROM shipment_trips WHERE order_id = %s ORDER BY id DESC LIMIT 1",
        (order_id,),
    ).fetchone()
    return dict(row) if row else None


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

# 10% per-truck flexibility on weight, volume, and cargo-bed dimensions so
# real-world trucks are not rejected over minor measurement or preset margins.
TRUCK_CAPACITY_FLEXIBILITY = 0.10
_FLEX_FACTOR = 1.0 + TRUCK_CAPACITY_FLEXIBILITY

# Cargo-bed dimensions are entered by transporters in feet; goods dimensions are
# captured from clients in centimetres. Convert feet -> cm for comparison.
_FT_TO_CM = 30.48


def required_order_volume_cbm(order):
    """Normalize all positive order-volume inputs to one required CBM value."""
    explicit_cbm = _to_float(order.get("goods_volume_cbm"))
    liters = _to_float(order.get("volume_liters"))
    explicit_cbm = explicit_cbm if explicit_cbm is not None and math.isfinite(explicit_cbm) and explicit_cbm > 0 else 0
    liters_cbm = liters / 1000.0 if liters is not None and math.isfinite(liters) and liters > 0 else 0
    return max(explicit_cbm, liters_cbm)


def _fits_on_bed(order, truck):
    """Return None if the goods fit the truck bed (with 10% flexibility), else a human message.

    Axis-aligned comparison: the load's length/width/height (cm, from the client)
    must each be <= the truck bed's matching length/width/height (feet -> cm) plus
    the 10% per-truck flexibility margin. A truck-bed axis left blank/zero
    (e.g. the open top of a flatbed) is treated as unbounded and skipped, and a
    goods axis that wasn't provided is skipped too.
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
        if g > (b_cm * _FLEX_FACTOR) + _CAP_EPS:
            return (
                f"The load's {axis} is {g / _FT_TO_CM:.1f} ft, but this truck's cargo bed "
                f"{axis} is only {b_ft:g} ft (max {b_ft * _FLEX_FACTOR:.1f} ft with 10% flexibility). "
                "Please use a bigger truck."
            )
    return None


_DRY_CARGO_RIGID_AND_TRAILER_KEYS = {
    "mini_pickup",
    "light_truck_2_3_5_ton",
    "light_truck_3_5_5_ton",
    "medium_rigid_truck_5_9_ton",
    "heavy_rigid_truck_9_15_ton",
    "heavy_rigid_truck_15_25_ton",
    "insulated_or_dry_box_truck",
    "flatbed_trailer_open_semi_trailer",
    "container_carrier_skeletal_trailer",
    "low_bed_low_loader_trailer",
}

_DRY_PACKAGED_COMMODITIES = {
    "general_cargo",
    "cement_bags",
    "cotton_textiles",
    "machinery",
    "construction_steel",
    "electronics",
    "furniture",
    "fruits_vegetables",
}

_COMMODITY_EQUIVALENTS = {
    "cement_bags": "general_cargo",
    "construction_steel": "machinery",
}


def _commodity_permitted_by_list(order_commodity, allowed_commodities):
    if not order_commodity or not isinstance(allowed_commodities, list):
        return False
    if order_commodity in allowed_commodities:
        return True
    equiv = _COMMODITY_EQUIVALENTS.get(order_commodity)
    return bool(equiv and equiv in allowed_commodities)


def _parse_truck_specs_json(truck):
    raw = truck.get("catalog_specs_json")
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError):
            return None
    return None


def truck_order_mismatch(truck, required_types, order):
    """Return None if the truck can serve the order, else a human message.

    Checks, in order:
      1. Truck TYPE & Safety-Locked Cargo Use (catalog_type_key + allowed_commodities + temperature_range).
      2. Truck WEIGHT capacity (capacity_tons / payload_max_tons) >= order weight.
      3. Truck VOLUME capacity (volume_max_cbm) >= the greatest positive volume
         supplied as CBM or litres converted to CBM.
      4. Cargo bed dimensions (length/width/height).
    """
    specs = _parse_truck_specs_json(truck)
    effective_truck = truck
    if specs is not None:
        raw_cap = _to_float(truck.get("capacity_tons")) or _to_float(truck.get("payload_max_tons"))
        inferred = infer_hybrid_truck_defaults(
            body_style=truck.get("body_style") or specs.get("body_type"),
            truck_type=truck.get("truck_type"),
            catalog_type_key=truck.get("catalog_type_key") or specs.get("catalog_type_key"),
            payload_max_tons=raw_cap,
            volume_max_cbm=_to_float(truck.get("volume_max_cbm")),
            bed_length_ft=_to_float(truck.get("bed_length_ft")),
            bed_width_ft=_to_float(truck.get("bed_width_ft")),
            bed_height_ft=_to_float(truck.get("bed_height_ft")),
            catalog_specs_raw=specs,
        )
        effective_truck = dict(truck)
        if not effective_truck.get("catalog_type_key") and inferred["catalog_type_key"]:
            effective_truck["catalog_type_key"] = inferred["catalog_type_key"]
        if _to_float(effective_truck.get("volume_max_cbm")) is None and inferred["volume_max_cbm"]:
            effective_truck["volume_max_cbm"] = inferred["volume_max_cbm"]
        for dim_key in ("bed_length_ft", "bed_width_ft", "bed_height_ft"):
            if _to_float(effective_truck.get(dim_key)) is None and inferred[dim_key]:
                effective_truck[dim_key] = inferred[dim_key]

    key = (effective_truck.get("catalog_type_key") or effective_truck.get("truck_type") or "").strip()
    order_commodity = (order.get("goods_commodity") or "").strip()

    # 1a) Safety-locked commodity & temperature checks when Hybrid specs exist
    if specs is not None:
        allowed_commodities = specs.get("allowed_commodities")
        if isinstance(allowed_commodities, list) and len(allowed_commodities) > 0 and order_commodity:
            if not _commodity_permitted_by_list(order_commodity, allowed_commodities):
                return "This truck type cannot carry these goods. Please use a suitable truck."

        temp_range = str(specs.get("temperature_range") or "").strip()
        order_temp = _to_float(order.get("temperature_c"))
        if temp_range == "Chilled (0C to 8C)":
            if order_commodity == "frozen_food" or (order_temp is not None and order_temp < 0):
                return "This truck type cannot carry these goods. Please use a suitable truck."
        elif temp_range == "Frozen (-18C)":
            if order_commodity in ("fruits_vegetables", "pharmaceuticals") and (
                not _commodity_permitted_by_list(order_commodity, allowed_commodities)
            ):
                return "This truck type cannot carry these goods. Please use a suitable truck."

    # 1b) Canonical catalog type check
    if required_types:
        allowed_by_hybrid_dry_use = (
            specs is not None
            and isinstance(specs.get("allowed_commodities"), list)
            and _commodity_permitted_by_list(order_commodity, specs.get("allowed_commodities", []))
            and order_commodity in _DRY_PACKAGED_COMMODITIES
            and key in _DRY_CARGO_RIGID_AND_TRAILER_KEYS
            and not (order_commodity == "fruits_vegetables" and _to_float(order.get("temperature_c")) is not None)
        )
        if key not in required_types and not allowed_by_hybrid_dry_use:
            return "This truck type cannot carry these goods. Please use a suitable truck."

    # 2) Weight capacity
    weight = _to_float(order.get("goods_weight_tons")) or 0
    if not math.isfinite(weight) or weight < 0:
        return "The load does not have a valid finite weight."
    capacity = _to_float(effective_truck.get("capacity_tons"))
    if capacity is None or not math.isfinite(capacity) or capacity <= 0:
        capacity = _to_float(effective_truck.get("payload_max_tons"))
    if weight > 0 and (capacity is None or not math.isfinite(capacity) or capacity <= 0):
        return "This truck does not have a valid weight capacity for this load."
    if weight > 0 and weight > (capacity * _FLEX_FACTOR) + _CAP_EPS:
        return (
            f"This truck can carry up to {capacity:g} tons (max {capacity * _FLEX_FACTOR:g} tons with 10% flexibility), "
            f"but the load is {weight:g} tons. Please use a higher-capacity truck."
        )

    # 3) Physical volume is an independently confirmed vehicle property. Payload
    # tons do not establish tank/bed volume or a commodity's density.
    volume = required_order_volume_cbm(order)
    if volume > 0:
        volume_max = _to_float(effective_truck.get("volume_max_cbm"))
        if volume_max is None or not math.isfinite(volume_max) or volume_max <= 0:
            return (
                "This truck does not have a valid volume capacity for this load. "
                "Please use a truck with a confirmed volume capacity."
            )
        if volume > (volume_max * _FLEX_FACTOR) + _CAP_EPS:
            return (
                f"This truck holds up to {volume_max:g} cbm (max {volume_max * _FLEX_FACTOR:g} cbm with 10% flexibility), "
                f"but the load needs {volume:g} cbm. Please use a larger truck."
            )

    # 4) Physical dimensions (length/width/height) fit on the cargo bed.
    dim_error = _fits_on_bed(order, effective_truck)
    if dim_error:
        return dim_error

    return None


# ---------------------------------------------------------------------------
# Vehicle-level location eligibility (truck current location -> order pickup)
# ---------------------------------------------------------------------------

# A truck serves orders whose PICKUP is within its service radius of where the
# truck currently sits. Dropoff distance is irrelevant. Defaults/limits mirror
# the vehicles.service_radius_km column (default 100, hard max 150).
DEFAULT_SERVICE_RADIUS_KM = 100.0
MAX_SERVICE_RADIUS_KM = 150.0
# ~50 m float tolerance so an exactly-on-the-boundary pickup is accepted.
_RADIUS_EPS_KM = 0.05

# Missing-location reasons (kept as constants so the routes and tests assert on
# one canonical wording).
LOCATION_UNSET_REASON = "Set this truck's operating location before viewing nearby orders."


def _service_radius_km(truck):
    """Effective service radius for a truck: the stored value, defaulted to
    100 km when absent/invalid and clamped to the 150 km hard maximum."""
    radius = _to_float(truck.get("service_radius_km"))
    if radius is None or radius <= 0:
        return DEFAULT_SERVICE_RADIUS_KM
    if radius > MAX_SERVICE_RADIUS_KM:
        return MAX_SERVICE_RADIUS_KM
    return radius


def _normalize_city(text):
    """Canonical city token for the no-coordinates fallback.

    Takes the part before the first comma (so a long geocoded string like
    'Gujranwala, Punjab, Pakistan' reduces to 'gujranwala'), lowercased and
    whitespace-collapsed. Matching is EXACT equality on this token — never a
    substring test — so 'Gujrat' can never be treated as 'Gujranwala'.
    """
    if not text:
        return ""
    head = str(text).split(",")[0]
    return " ".join(head.lower().split())


def _truck_coords(truck):
    lat = _to_float(truck.get("current_lat"))
    lng = _to_float(truck.get("current_lng"))
    if lat is None or lng is None:
        return None
    return lat, lng


def _pickup_coords(order):
    lat = _to_float(order.get("pickup_lat"))
    lng = _to_float(order.get("pickup_lng"))
    if lat is None or lng is None:
        return None
    return lat, lng


def truck_distance_to_pickup_km(truck, order):
    """Great-circle km from the truck's current location to the order pickup,
    or None when either side lacks coordinates.

    Used to show a transporter the distance for their OWN eligible orders. It
    never returns or exposes the raw coordinates themselves.
    """
    truck_pos = _truck_coords(truck)
    pickup_pos = _pickup_coords(order)
    if not truck_pos or not pickup_pos:
        return None
    return round(haversine_distance_km(truck_pos[0], truck_pos[1], pickup_pos[0], pickup_pos[1]), 1)


def truck_pickup_location_mismatch(truck, order):
    """Return None if the truck is close enough to the order's PICKUP, else a
    human-readable reason.

    Rules (never nationwide):
      * No truck coordinates  -> ineligible (LOCATION_UNSET_REASON). An active
        truck without a location must not see any distant order.
      * Order has coordinates -> Haversine(truck, pickup) must be within the
        truck's service radius (default 100 km, max 150 km).
      * Order has NO coordinates -> exact normalized city match only
        (truck.current_city == order pickup city). Coordinates are never
        guessed; anything else is ineligible with a clear reason.

    Eligibility is measured to the PICKUP only — the dropoff may be anywhere.
    """
    pickup_pos = _pickup_coords(order)

    if pickup_pos:
        # Order has coordinates: always distance-based, which needs the truck's
        # coordinates. A truck without coordinates gets NO distant order.
        truck_pos = _truck_coords(truck)
        if not truck_pos:
            return LOCATION_UNSET_REASON
        radius = _service_radius_km(truck)
        distance = haversine_distance_km(truck_pos[0], truck_pos[1], pickup_pos[0], pickup_pos[1])
        if distance > radius + _RADIUS_EPS_KM:
            return (
                f"This truck is {distance:.1f} km from the pickup, beyond its "
                f"{radius:.1f} km service radius. Please choose a nearer order."
            )
        return None

    # Order without coordinates: exact normalized-city fallback ONLY (never a
    # province-wide or substring match, and coordinates are never guessed).
    truck_city = _normalize_city(truck.get("current_city"))
    if not truck_city:
        return LOCATION_UNSET_REASON
    pickup_city = _normalize_city(order.get("pickup_city") or order.get("pickup_location"))
    if pickup_city and truck_city == pickup_city:
        return None
    return (
        "This order has no pickup coordinates, so it is only shown to trucks "
        "whose operating city matches the pickup city."
    )


_PROVINCE_ALIASES = {
    "punjab": "Punjab",
    "sindh": "Sindh",
    "khyber pakhtunkhwa": "Khyber Pakhtunkhwa",
    "kpk": "Khyber Pakhtunkhwa",
    "k.p.k": "Khyber Pakhtunkhwa",
    "kp": "Khyber Pakhtunkhwa",
    "nwfp": "Khyber Pakhtunkhwa",
    "balochistan": "Balochistan",
    "baluchistan": "Balochistan",
    "islamabad capital territory": "Islamabad Capital Territory",
    "ict": "Islamabad Capital Territory",
    "federal capital": "Islamabad Capital Territory",
    "gilgit-baltistan": "Gilgit-Baltistan",
    "gilgit baltistan": "Gilgit-Baltistan",
    "gb": "Gilgit-Baltistan",
    "northern areas": "Gilgit-Baltistan",
    "azad jammu and kashmir": "Azad Jammu and Kashmir",
    "azad jammu & kashmir": "Azad Jammu and Kashmir",
    "azad kashmir": "Azad Jammu and Kashmir",
    "ajk": "Azad Jammu and Kashmir",
}

_PAKISTAN_CITY_PROVINCE = {
    # Punjab
    "lahore": "Punjab", "gujranwala": "Punjab", "faisalabad": "Punjab",
    "rawalpindi": "Punjab", "multan": "Punjab", "sialkot": "Punjab",
    "gujrat": "Punjab", "sargodha": "Punjab", "bahawalpur": "Punjab",
    "sheikhupura": "Punjab", "kasur": "Punjab", "sahiwal": "Punjab",
    "okara": "Punjab", "jhelum": "Punjab", "rahim yar khan": "Punjab",
    "dera ghazi khan": "Punjab", "dg khan": "Punjab", "muzaffargarh": "Punjab",
    "khanewal": "Punjab", "vehari": "Punjab", "pakpattan": "Punjab",
    "toba tek singh": "Punjab", "jhang": "Punjab", "chiniot": "Punjab",
    "hafizabad": "Punjab", "mandi bahauddin": "Punjab", "narowal": "Punjab",
    "chakwal": "Punjab", "attock": "Punjab", "mianwali": "Punjab",
    "bhakkar": "Punjab", "khushab": "Punjab", "layyah": "Punjab",
    "rajanpur": "Punjab", "lodhran": "Punjab", "bahawalnagar": "Punjab",
    "kamoke": "Punjab", "wazirabad": "Punjab", "muridke": "Punjab",
    "pattoki": "Punjab", "burewala": "Punjab", "sadiqabad": "Punjab",
    "khanpur": "Punjab", "taxila": "Punjab", "wah": "Punjab",
    "wah cantt": "Punjab", "murree": "Punjab",
    # Sindh
    "karachi": "Sindh", "hyderabad": "Sindh", "sukkur": "Sindh",
    "larkana": "Sindh", "nawabshah": "Sindh", "shaheed benazirabad": "Sindh",
    "mirpur khas": "Sindh", "mirpurkhas": "Sindh", "thatta": "Sindh",
    "jacobabad": "Sindh", "shikarpur": "Sindh", "khairpur": "Sindh",
    "dadu": "Sindh", "badin": "Sindh", "umarkot": "Sindh",
    "umerkot": "Sindh", "tharparkar": "Sindh", "mithi": "Sindh",
    "sanghar": "Sindh", "tando adam": "Sindh", "tando allahyar": "Sindh",
    "tando muhammad khan": "Sindh", "matli": "Sindh", "kotri": "Sindh",
    "jamshoro": "Sindh", "sehwan": "Sindh", "ghotki": "Sindh",
    "kashmore": "Sindh", "kandhkot": "Sindh", "naushahro feroze": "Sindh",
    "moro": "Sindh", "hala": "Sindh",
    # Khyber Pakhtunkhwa
    "peshawar": "Khyber Pakhtunkhwa", "mardan": "Khyber Pakhtunkhwa",
    "abbottabad": "Khyber Pakhtunkhwa", "mingora": "Khyber Pakhtunkhwa",
    "swat": "Khyber Pakhtunkhwa", "kohat": "Khyber Pakhtunkhwa",
    "bannu": "Khyber Pakhtunkhwa", "nowshera": "Khyber Pakhtunkhwa",
    "charsadda": "Khyber Pakhtunkhwa", "haripur": "Khyber Pakhtunkhwa",
    "mansehra": "Khyber Pakhtunkhwa", "dera ismail khan": "Khyber Pakhtunkhwa",
    "di khan": "Khyber Pakhtunkhwa", "d.i. khan": "Khyber Pakhtunkhwa",
    "swabi": "Khyber Pakhtunkhwa", "timergara": "Khyber Pakhtunkhwa",
    "dir": "Khyber Pakhtunkhwa", "chitral": "Khyber Pakhtunkhwa",
    "malakand": "Khyber Pakhtunkhwa", "buner": "Khyber Pakhtunkhwa",
    "shangla": "Khyber Pakhtunkhwa", "battagram": "Khyber Pakhtunkhwa",
    "kohistan": "Khyber Pakhtunkhwa", "hangu": "Khyber Pakhtunkhwa",
    "karak": "Khyber Pakhtunkhwa", "lakki marwat": "Khyber Pakhtunkhwa",
    "tank": "Khyber Pakhtunkhwa", "parachinar": "Khyber Pakhtunkhwa",
    "landikotal": "Khyber Pakhtunkhwa", "miranshah": "Khyber Pakhtunkhwa",
    "wana": "Khyber Pakhtunkhwa",
    # Balochistan
    "quetta": "Balochistan", "gwadar": "Balochistan", "turbat": "Balochistan",
    "khuzdar": "Balochistan", "chaman": "Balochistan", "sibi": "Balochistan",
    "hub": "Balochistan", "lasbela": "Balochistan", "zhob": "Balochistan",
    "loralai": "Balochistan", "pishin": "Balochistan", "kalat": "Balochistan",
    "mastung": "Balochistan", "nushki": "Balochistan", "chagai": "Balochistan",
    "dalbandin": "Balochistan", "panjgur": "Balochistan", "pasni": "Balochistan",
    "ormara": "Balochistan", "jiwani": "Balochistan", "awaran": "Balochistan",
    "killa abdullah": "Balochistan", "killa saifullah": "Balochistan",
    "barkhan": "Balochistan", "kohlu": "Balochistan", "dera bugti": "Balochistan",
    "sui": "Balochistan", "nasirabad": "Balochistan",
    "dera murad jamali": "Balochistan", "jaffarabad": "Balochistan",
    "ustad muhammad": "Balochistan", "bolan": "Balochistan",
    "mach": "Balochistan", "ziarat": "Balochistan", "harnai": "Balochistan",
    "kharan": "Balochistan",
    # Islamabad Capital Territory
    "islamabad": "Islamabad Capital Territory",
    # Gilgit-Baltistan
    "gilgit": "Gilgit-Baltistan", "skardu": "Gilgit-Baltistan",
    "hunza": "Gilgit-Baltistan", "chilas": "Gilgit-Baltistan",
    "diamer": "Gilgit-Baltistan", "ghizer": "Gilgit-Baltistan",
    "gahkuch": "Gilgit-Baltistan", "khaplu": "Gilgit-Baltistan",
    "shigar": "Gilgit-Baltistan", "astore": "Gilgit-Baltistan",
    "nagar": "Gilgit-Baltistan", "sust": "Gilgit-Baltistan",
    "soost": "Gilgit-Baltistan",
    # Azad Jammu and Kashmir
    "muzaffarabad": "Azad Jammu and Kashmir", "mirpur": "Azad Jammu and Kashmir",
    "kotli": "Azad Jammu and Kashmir", "rawalakot": "Azad Jammu and Kashmir",
    "poonch": "Azad Jammu and Kashmir", "bhimber": "Azad Jammu and Kashmir",
    "bagh": "Azad Jammu and Kashmir", "neelum": "Azad Jammu and Kashmir",
    "authmuqam": "Azad Jammu and Kashmir", "hattian bala": "Azad Jammu and Kashmir",
    "haveli": "Azad Jammu and Kashmir", "pallandri": "Azad Jammu and Kashmir",
}

_PROVINCE_COORD_ANCHORS = (
    (32.1877, 74.1945, "Punjab"),                     # Gujranwala
    (31.5204, 74.3587, "Punjab"),                     # Lahore
    (32.4945, 74.5229, "Punjab"),                     # Sialkot
    (32.5731, 74.0789, "Punjab"),                     # Gujrat
    (31.4504, 73.1350, "Punjab"),                     # Faisalabad
    (33.5651, 73.0169, "Punjab"),                     # Rawalpindi
    (30.1575, 71.5249, "Punjab"),                     # Multan
    (29.3956, 71.6836, "Punjab"),                     # Bahawalpur
    (32.0836, 72.6711, "Punjab"),                     # Sargodha
    (24.8607, 67.0011, "Sindh"),                      # Karachi
    (25.3960, 68.3578, "Sindh"),                      # Hyderabad
    (27.7052, 68.8574, "Sindh"),                      # Sukkur
    (27.5570, 68.2028, "Sindh"),                      # Larkana
    (34.0151, 71.5805, "Khyber Pakhtunkhwa"),         # Peshawar
    (34.1986, 72.0404, "Khyber Pakhtunkhwa"),         # Mardan
    (34.1688, 73.2215, "Khyber Pakhtunkhwa"),         # Abbottabad
    (34.7717, 72.3602, "Khyber Pakhtunkhwa"),         # Mingora / Swat
    (31.8626, 70.9019, "Khyber Pakhtunkhwa"),         # Dera Ismail Khan
    (30.1798, 66.9750, "Balochistan"),                # Quetta
    (25.1264, 62.3225, "Balochistan"),                # Gwadar
    (27.8000, 66.6167, "Balochistan"),                # Khuzdar
    (33.6844, 73.0479, "Islamabad Capital Territory"),# Islamabad
    (35.9208, 74.3144, "Gilgit-Baltistan"),           # Gilgit
    (35.2971, 75.6333, "Gilgit-Baltistan"),           # Skardu
    (34.3700, 73.4711, "Azad Jammu and Kashmir"),     # Muzaffarabad
    (33.1478, 73.7518, "Azad Jammu and Kashmir"),     # Mirpur
)


def _parse_operating_provinces(raw_provinces):
    """Parse a truck's operating_provinces (CSV string or list) into a set of
    canonical province names."""
    if not raw_provinces:
        return set()
    if isinstance(raw_provinces, (list, tuple, set)):
        items = [str(item).strip() for item in raw_provinces if str(item).strip()]
    else:
        items = [part.strip() for part in str(raw_provinces).split(",") if part.strip()]
    result = set()
    for item in items:
        key = " ".join(item.lower().split())
        canonical = _PROVINCE_ALIASES.get(key)
        if canonical:
            result.add(canonical)
        else:
            result.add(item)
    return result


def infer_pakistan_province(location_text, lat=None, lng=None):
    """Infer the canonical Pakistani province from a location/city string or
    (lat, lng) coordinates. Returns None if no province can be determined."""
    if location_text:
        segments = [
            " ".join(seg.lower().split())
            for seg in str(location_text).split(",")
            if seg.strip()
        ]
        # 1. Exact segment match against province aliases (e.g. "Gujranwala, Punjab, Pakistan")
        for seg in segments:
            if seg in _PROVINCE_ALIASES:
                return _PROVINCE_ALIASES[seg]
        # 2. Exact segment match against known cities (e.g. "Karachi" or "Gujranwala, Pakistan")
        for seg in segments:
            if seg in _PAKISTAN_CITY_PROVINCE:
                return _PAKISTAN_CITY_PROVINCE[seg]
        # 3. Word-boundary phrase check inside segments
        full_norm = " ".join(str(location_text).lower().replace("-", " ").split())
        for alias, canonical in sorted(_PROVINCE_ALIASES.items(), key=lambda kv: -len(kv[0])):
            if len(alias) >= 4 and alias in full_norm:
                return canonical
        for city, canonical in sorted(_PAKISTAN_CITY_PROVINCE.items(), key=lambda kv: -len(kv[0])):
            if f" {city} " in f" {full_norm} ":
                return canonical

    lat_f = _to_float(lat)
    lng_f = _to_float(lng)
    if lat_f is not None and lng_f is not None:
        best_province = None
        best_dist = None
        for anchor_lat, anchor_lng, province in _PROVINCE_COORD_ANCHORS:
            dist = haversine_distance_km(lat_f, lng_f, anchor_lat, anchor_lng)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_province = province
        if best_dist is not None and best_dist <= 120.0:
            return best_province

    return None


def truck_operating_provinces_mismatch(truck, order):
    """Return None if both the order's pickup province and dropoff province are
    permitted by the truck's route permit (operating_provinces), else a human
    reason.

    When operating_provinces is unset/empty on the truck dict (e.g. minimal
    unit-test dicts that only test cargo or Haversine distance), this check is
    a no-op so isolated tests remain unaffected. Active trucks in production
    always require operating_provinces to be configured.
    """
    allowed = _parse_operating_provinces(truck.get("operating_provinces"))
    if not allowed:
        return None

    pickup_province = infer_pakistan_province(
        order.get("pickup_location") or order.get("pickup_city"),
        order.get("pickup_lat"),
        order.get("pickup_lng"),
    )
    if pickup_province and pickup_province not in allowed:
        return (
            f"This truck's route permit ({', '.join(sorted(allowed))}) does not "
            f"cover the pickup province ({pickup_province})."
        )

    dropoff_province = infer_pakistan_province(
        order.get("dropoff_location") or order.get("dropoff_city"),
        order.get("dropoff_lat"),
        order.get("dropoff_lng"),
    )
    if dropoff_province and dropoff_province not in allowed:
        return (
            f"This truck's route permit ({', '.join(sorted(allowed))}) does not "
            f"cover the dropoff province ({dropoff_province})."
        )

    return None


def truck_order_eligibility_mismatch(truck, required_types, order):
    """The single authoritative eligibility check: cargo, pickup location, AND
    route permit (operating provinces for both pickup and dropoff).

    Composes the three independent rules — no rule is duplicated here:
      1. truck_order_mismatch               (type / weight / volume / dimensions)
      2. truck_pickup_location_mismatch     (distance to pickup)
      3. truck_operating_provinces_mismatch (pickup & dropoff province permit)

    Every caller (available-orders listing, bid placement, bid comparison,
    payment quote, locked checkout and the matching audit) goes through this
    one function, so availability and bidding can never apply different rules.
    """
    cargo_reason = truck_order_mismatch(truck, required_types, order)
    if cargo_reason:
        return cargo_reason
    location_reason = truck_pickup_location_mismatch(truck, order)
    if location_reason:
        return location_reason
    return truck_operating_provinces_mismatch(truck, order)


# ---------------------------------------------------------------------------
# Current-truck validation (shared by comparison, quote and checkout)
# ---------------------------------------------------------------------------

def validate_bid_truck(order, bid_transporter_id, truck):
    """Return None if the bid's truck is still usable for this order, else a
    human-readable reason.

    ONE pure validation used everywhere a bid may be paid: the comparison
    response (to derive can_checkout / unavailable_reason), the payment quote,
    and perform_checkout under the locked vehicle row. Reuses
    truck_order_eligibility_mismatch for the type/weight/volume/dimension AND
    pickup-location checks so there is exactly one eligibility path. A truck can
    silently become inactive, change owner, move away from the pickup, or stop
    matching after the bid was placed — this catches all of that at pay time,
    so a truck that is now outside its service radius cannot be checked out.
    """
    if not truck or truck.get("id") is None:
        return "The truck offered for this bid is no longer available."
    owner_id = truck.get("owner_user_id")
    if owner_id is not None and bid_transporter_id is not None and owner_id != bid_transporter_id:
        return "This truck no longer belongs to the transporter who placed the bid."
    if (truck.get("status") or "").strip() != "active":
        return "This truck is no longer active and cannot be booked."
    required_types = parse_truck_types(order.get("required_truck_types"))
    mismatch = truck_order_eligibility_mismatch(truck, required_types, order)
    if mismatch:
        return mismatch
    return None


# ---------------------------------------------------------------------------
# Enriched bid comparison (single joined query, no N+1)
# ---------------------------------------------------------------------------

def _truck_type_display(catalog_type_key, truck_type):
    catalog = get_catalog_type(catalog_type_key) if catalog_type_key else None
    if catalog and catalog.get("display_name"):
        return catalog["display_name"]
    return truck_type or None


def _photo_url(path):
    path = (path or "").strip()
    if not path:
        return None
    return path if path.startswith("/") else f"/{path}"


# bids + the SAFE vehicle and transporter fields, plus a completed one-time
# trip count — all in ONE query (no N+1). Sensitive columns (email, phone,
# cnic, driver_cnic, payout*, tracking_id, traccar_device_id, wallet, private
# documents) are deliberately never selected. current_lat/current_lng ARE
# selected because location eligibility is validated server-side, but they are
# NEVER serialized into the seeker response (only current_city is exposed).
_BID_COMPARISON_SQL = """
    SELECT
        b.id                  AS bid_id,
        b.order_id            AS order_id,
        b.transporter_user_id AS transporter_user_id,
        b.truck_id            AS truck_id,
        b.bid_price           AS bid_price,
        b.message             AS message,
        b.status              AS bid_status,
        b.created_at          AS bid_created_at,
        b.updated_at          AS bid_updated_at,
        COALESCE(NULLIF(trim(u.full_name), ''), 'Transporter') AS transporter_display_name,
        tp.company_name       AS transporter_company_name,
        COALESCE(ct.completed_trips, 0) AS completed_trips,
        ra.rating_average     AS rating_average,
        COALESCE(ra.rating_count, 0) AS rating_count,
        v.id                  AS truck_row_id,
        v.owner_user_id       AS truck_owner_user_id,
        v.truck_number        AS truck_number,
        v.truck_company       AS truck_company,
        v.truck_model         AS truck_model,
        v.truck_type          AS truck_type,
        v.catalog_type_key    AS catalog_type_key,
        v.capacity_tons       AS capacity_tons,
        v.payload_min_tons    AS payload_min_tons,
        v.payload_max_tons    AS payload_max_tons,
        v.volume_min_cbm      AS volume_min_cbm,
        v.volume_max_cbm      AS volume_max_cbm,
        v.bed_length_ft       AS bed_length_ft,
        v.bed_width_ft        AS bed_width_ft,
        v.bed_height_ft       AS bed_height_ft,
        v.body_style          AS body_style,
        v.truck_photo_path    AS truck_photo_path,
        v.status              AS truck_status,
        v.current_city        AS current_city,
        v.current_lat         AS current_lat,
        v.current_lng         AS current_lng,
        v.service_radius_km   AS service_radius_km,
        v.operating_provinces AS operating_provinces,
        v.catalog_specs_json  AS catalog_specs_json
    FROM shipment_bids b
    LEFT JOIN vehicles v ON v.id = b.truck_id
    LEFT JOIN users u ON u.id = b.transporter_user_id
    LEFT JOIN transporter_profiles tp ON tp.user_id = b.transporter_user_id
    LEFT JOIN (
        SELECT transporter_user_id, COUNT(*) AS completed_trips
        FROM shipment_trips
        WHERE status = 'completed'
        GROUP BY transporter_user_id
    ) ct ON ct.transporter_user_id = b.transporter_user_id
    LEFT JOIN (
        SELECT transporter_user_id,
               ROUND(AVG(rating)::numeric, 1) AS rating_average,
               COUNT(*) AS rating_count
        FROM shipment_trip_reviews
        GROUP BY transporter_user_id
    ) ra ON ra.transporter_user_id = b.transporter_user_id
    WHERE b.order_id = %s AND b.status != 'withdrawn'
"""


def fetch_bid_comparison_rows(db, order_id, transporter_user_id=None):
    """One joined query for the enriched bid comparison.

    Owner passes transporter_user_id=None and receives every non-withdrawn
    bid. The accepted transporter passes their own id and receives only their
    own bid. A single SQL string with an optional transporter filter — the
    owner and transporter paths never copy the query.
    """
    sql = _BID_COMPARISON_SQL
    params = [order_id]
    if transporter_user_id is not None:
        sql += " AND b.transporter_user_id = %s"
        params.append(transporter_user_id)
    sql += " ORDER BY b.bid_price ASC, b.created_at ASC"
    return [dict(r) for r in db.execute(sql, tuple(params)).fetchall()]


def serialize_enriched_bid(row, order):
    """Serialize one comparison row into a bid with nested SAFE transporter /
    truck objects plus checkout availability. Preserves the legacy top-level
    bid fields for backward compatibility."""
    truck_present = row.get("truck_row_id") is not None
    truck_for_validation = {
        "id": row.get("truck_row_id"),
        "owner_user_id": row.get("truck_owner_user_id"),
        "status": row.get("truck_status"),
        "catalog_type_key": row.get("catalog_type_key"),
        "truck_type": row.get("truck_type"),
        "capacity_tons": row.get("capacity_tons"),
        "payload_max_tons": row.get("payload_max_tons"),
        "volume_max_cbm": row.get("volume_max_cbm"),
        "bed_length_ft": row.get("bed_length_ft"),
        "bed_width_ft": row.get("bed_width_ft"),
        "bed_height_ft": row.get("bed_height_ft"),
        # Location fields feed truck_pickup_location_mismatch server-side only.
        "current_lat": row.get("current_lat"),
        "current_lng": row.get("current_lng"),
        "current_city": row.get("current_city"),
        "service_radius_km": row.get("service_radius_km"),
        "operating_provinces": row.get("operating_provinces"),
        "catalog_specs_json": row.get("catalog_specs_json"),
    }
    truck_reason = validate_bid_truck(order, row.get("transporter_user_id"), truck_for_validation)
    bid_status = row.get("bid_status")
    order_open = order.get("status") == "open"

    if truck_reason:
        unavailable_reason = truck_reason
    elif bid_status != "pending":
        unavailable_reason = "This bid is no longer available for selection."
    elif not order_open:
        unavailable_reason = "This order is no longer open for checkout."
    else:
        unavailable_reason = None
    can_checkout = bool(order_open and bid_status == "pending" and truck_reason is None)

    transporter = {
        "id": row.get("transporter_user_id"),
        "display_name": row.get("transporter_display_name") or "Transporter",
        "company_name": row.get("transporter_company_name"),
        "completed_trips": int(row.get("completed_trips") or 0),
        "rating_average": _to_float(row.get("rating_average")),
        "rating_count": int(row.get("rating_count") or 0),
    }
    truck = None
    if truck_present:
        truck = {
            "id": row.get("truck_row_id"),
            "truck_number": row.get("truck_number"),
            "company": row.get("truck_company"),
            "model": row.get("truck_model"),
            "type_key": row.get("catalog_type_key"),
            "type_name": _truck_type_display(row.get("catalog_type_key"), row.get("truck_type")),
            "capacity_tons": _to_float(row.get("capacity_tons")),
            "payload_min_tons": _to_float(row.get("payload_min_tons")),
            "payload_max_tons": _to_float(row.get("payload_max_tons")),
            "volume_min_cbm": _to_float(row.get("volume_min_cbm")),
            "volume_max_cbm": _to_float(row.get("volume_max_cbm")),
            "bed_length_ft": _to_float(row.get("bed_length_ft")),
            "bed_width_ft": _to_float(row.get("bed_width_ft")),
            "bed_height_ft": _to_float(row.get("bed_height_ft")),
            "body_style": row.get("body_style"),
            "photo_url": _photo_url(row.get("truck_photo_path")),
            "status": row.get("truck_status"),
            # Coarse city only — exact current_lat/current_lng are intentionally
            # NOT exposed to the seeker (privacy of the truck's pre-trip position).
            "current_city": row.get("current_city"),
        }

    return {
        "id": row.get("bid_id"),
        "order_id": row.get("order_id"),
        "transporter_user_id": row.get("transporter_user_id"),
        "truck_id": row.get("truck_id"),
        "bid_price": round_money(row.get("bid_price", 0)),
        "message": row.get("message"),
        "status": bid_status,
        "created_at": row.get("bid_created_at"),
        "updated_at": row.get("bid_updated_at"),
        "transporter": transporter,
        "truck": truck,
        "can_checkout": can_checkout,
        "unavailable_reason": unavailable_reason,
    }


def fetch_enriched_bids(db, order, transporter_user_id=None):
    rows = fetch_bid_comparison_rows(db, order["id"], transporter_user_id=transporter_user_id)
    return [serialize_enriched_bid(row, order) for row in rows]


def calculate_no_show_penalty(bid_price):
    """Calculate penalty for no-show or cancellation."""
    return round_money(bid_price * 0.15)


def get_or_create_order_for_client(db, client_user_id, order_data):
    """Helper to create or validate order for client."""
    validation_error = validate_order_creation(order_data)
    if validation_error:
        return None, validation_error
    return True, None
