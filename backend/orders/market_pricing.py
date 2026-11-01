"""Conservative comparable-market mean and pre-insert bid corridors.

Every eligible observation has weight one: each distinct active bid, plus
every independently verified completed trip fare. Uniqueness permits only one
active bid per transporter per shipment. There are no historical coefficients,
cross-shipment author weights, or inferred weight bands.
Exact route addresses, cargo weight/characteristics and vehicle category must
match. Sparse markets bootstrap instead of broadening comparability silently.
"""
import hashlib
import json
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from .helpers import truck_order_eligibility_mismatch, parse_truck_types

CENT = Decimal("0.01")
ROUTE_FIELDS = ("pickup_city", "pickup_location", "dropoff_city", "dropoff_location",
                "goods_type", "goods_category", "goods_commodity")


def _text(value):
    return " ".join(str(value or "").strip().lower().split())


def market_key(order, truck):
    route = {field: _text(order.get(field)) for field in ROUTE_FIELDS}
    route["pickup_location"] = route["pickup_location"] or route["pickup_city"]
    route["dropoff_location"] = route["dropoff_location"] or route["dropoff_city"]
    route["weight_tons"] = str(Decimal(str(order["goods_weight_tons"])).normalize())
    route["vehicle_category"] = _text(truck.get("catalog_type_key") or truck.get("truck_type"))
    for field in ("is_refrigerated", "is_hazardous", "is_food_grade"):
        route[field] = bool(order.get(field))
    return hashlib.sha256(json.dumps(route, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def lock_market(db, key):
    """Serialize market mutations before shipment/bid row locks."""
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("bid-market:" + key,))


def verified_transporter_rating(db, transporter_id):
    """Only reviews whose actual client and completed trip agree are trusted."""
    row = db.execute_exact(
        """SELECT avg(r.rating)::numeric AS rating, count(*) AS review_count
           FROM shipment_trip_reviews r
           JOIN shipment_trips t ON t.id=r.trip_id AND t.order_id=r.shipment_id
             AND t.transporter_user_id=r.transporter_user_id
           JOIN shipments s ON s.id=t.order_id AND s.client_user_id=r.client_user_id
           WHERE r.transporter_user_id=%s AND t.status='completed'
             AND t.trip_completed_at IS NOT NULL AND r.client_user_id<>r.transporter_user_id""",
        (transporter_id,),
    ).fetchone()
    return Decimal(str(row["rating"])) if row and row["review_count"] else None


def _candidate_rows(db, order):
    # The exact key below also checks addresses, weight, cargo and category;
    # city predicates keep this candidate query bounded to the relevant route.
    return db.execute_exact(
        """SELECT b.*, row_to_json(s) AS shipment, row_to_json(v) AS truck
           FROM shipment_bids b JOIN shipments s ON s.id=b.order_id
           JOIN vehicles v ON v.id=b.truck_id
           WHERE lower(regexp_replace(btrim(s.pickup_city),'[[:space:]]+',' ','g'))=%s
             AND lower(regexp_replace(btrim(s.dropoff_city),'[[:space:]]+',' ','g'))=%s
             AND s.goods_weight_tons=%s
             AND ((b.status='pending' AND s.status='open') OR
                  (b.status='accepted' AND EXISTS(
                    SELECT 1 FROM shipment_trips t WHERE t.accepted_bid_id=b.id
                     AND t.order_id=s.id AND t.transporter_user_id=b.transporter_user_id
                     AND t.truck_id=b.truck_id AND t.status='completed'
                     AND t.trip_completed_at IS NOT NULL)))
           ORDER BY b.created_at,b.id""",
        (_text(order["pickup_city"]), _text(order["dropoff_city"]), order["goods_weight_tons"]),
    ).fetchall()


def _object(value):
    return json.loads(value, parse_float=Decimal) if isinstance(value, str) else value


def market_reference(db, order, truck, transporter_id=None):
    key = market_key(order, truck)
    values = []
    for candidate in _candidate_rows(db, order):
        shipment, vehicle = _object(candidate["shipment"]), _object(candidate["truck"])
        if market_key(shipment, vehicle) != key:
            continue
        if (candidate["transporter_user_id"] == shipment["client_user_id"]
                or candidate["transporter_user_id"] != vehicle["owner_user_id"]
                or candidate.get("market_ineligible_reason")):
            continue
        price = Decimal(str(candidate["bid_price"]))
        if not price.is_finite() or price <= 0 or price != price.quantize(CENT):
            continue
        if candidate["status"] == "pending":
            if vehicle["status"] != "active" or truck_order_eligibility_mismatch(
                    vehicle, parse_truck_types(shipment.get("required_truck_types")), shipment):
                continue
        values.append(price)
    rating = verified_transporter_rating(db, transporter_id) if transporter_id is not None else None
    return reference_from_values(values, rating, key)


def reference_from_values(values, rating=None, key=None):
    """Pure exact mean and inclusive two-decimal corridor bounds."""
    values = [Decimal(str(value)) for value in values]
    mean = sum(values, Decimal(0)) / len(values) if values else None
    premium = rating is not None and Decimal(str(rating)) >= Decimal("4.5")
    lower = (mean * Decimal("0.80")).quantize(CENT, rounding=ROUND_CEILING) if mean is not None else None
    upper = (mean * (Decimal("1.40") if premium else Decimal("1.20"))).quantize(CENT, rounding=ROUND_FLOOR) if mean is not None else None
    return {"market_key": key, "market_average": format(mean.quantize(CENT, rounding=ROUND_HALF_UP), ".2f") if mean is not None else None,
            "reference_average_exact": str(mean) if mean is not None else None,
            "minimum_bid": format(lower, ".2f") if lower is not None else None,
            "maximum_bid": format(upper, ".2f") if upper is not None else None,
            "bootstrap": mean is None, "premium": premium,
            "verified_rating": str(rating) if rating is not None else None,
            "sample_count": len(values), "currency": "PKR"}


def validate_bid_reference(price, reference):
    if reference["bootstrap"]:
        return
    if not Decimal(reference["minimum_bid"]) <= price <= Decimal(reference["maximum_bid"]):
        raise ValueError(f"Bid must be between PKR {reference['minimum_bid']} and PKR {reference['maximum_bid']} based on the current market reference.")
