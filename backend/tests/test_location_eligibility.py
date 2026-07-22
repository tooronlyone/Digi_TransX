"""Vehicle-level, location-aware order visibility.

Two tiers, matching the rest of the suite:

* Pure helper tests (no database) prove the single composed eligibility path
  (cargo + pickup distance) for every rule in the spec. These run with or
  without TEST_SUPABASE_DB_URL.
* PostgreSQL integration tests (skipped without a dedicated test database)
  prove the availability endpoint filters by location and that checkout
  re-validates the truck's location under the row lock BEFORE any wallet /
  provider mutation.

Distance uses the ONE shared Haversine helper; there is no second formula and
no second matching algorithm anywhere in these tests.
"""

import math

import pytest

from shared.geo import haversine_distance_km
from orders.helpers import (
    LOCATION_UNSET_REASON,
    truck_order_mismatch,
    truck_order_eligibility_mismatch,
    truck_pickup_location_mismatch,
    truck_distance_to_pickup_km,
    serialize_enriched_bid,
)

# --- Real Pakistani coordinates (also used by the fixtures) -----------------
GUJRANWALA = (32.1877, 74.1945)
LAHORE = (31.5204, 74.3587)
SIALKOT = (32.4945, 74.5229)
GUJRAT = (32.5731, 74.0789)
MULTAN = (30.1575, 71.5249)
KARACHI = (24.8607, 67.0011)

# A flatbed that can carry a heavy, dimensionless load.
FLATBED = {
    "catalog_type_key": "flatbed_trailer_open_semi_trailer",
    "capacity_tons": 45,
    "volume_max_cbm": 0,
    "bed_length_ft": 21, "bed_width_ft": 7, "bed_height_ft": 8,
    "status": "active",
}


def _truck(lat, lng, radius=100, city=None, **extra):
    t = dict(FLATBED)
    t.update({"current_lat": lat, "current_lng": lng, "service_radius_km": radius,
              "current_city": city})
    t.update(extra)
    return t


def _order(pickup, dropoff=None, required=None, weight=10, **extra):
    o = {
        "pickup_lat": pickup[0], "pickup_lng": pickup[1],
        "goods_weight_tons": weight,
        "required_truck_types": required,
    }
    if dropoff is not None:
        o["dropoff_lat"], o["dropoff_lng"] = dropoff[0], dropoff[1]
    o.update(extra)
    return o


REQUIRED = ["flatbed_trailer_open_semi_trailer"]


# ---------------------------------------------------------------------------
# 1-6: distance-based visibility, dropoff irrelevance
# ---------------------------------------------------------------------------

def test_1_gujranwala_truck_sees_gujranwala_pickup():
    assert truck_order_eligibility_mismatch(_truck(*GUJRANWALA), REQUIRED, _order(GUJRANWALA)) is None


def test_2_gujranwala_truck_sees_nearby_pickup_within_100km():
    # Sialkot (~46 km) and Gujrat (~44 km) are both < 100 km from Gujranwala.
    assert truck_distance_to_pickup_km(_truck(*GUJRANWALA), _order(SIALKOT)) < 100
    assert truck_order_eligibility_mismatch(_truck(*GUJRANWALA), REQUIRED, _order(SIALKOT)) is None
    assert truck_order_eligibility_mismatch(_truck(*GUJRANWALA), REQUIRED, _order(GUJRAT)) is None


def test_3_exact_radius_boundary_is_accepted():
    lat, lng = GUJRANWALA
    # A pickup due north at EXACTLY 100 km (great-circle along a meridian).
    boundary_lat = lat + math.degrees(100.0 / 6371.0)
    dist = haversine_distance_km(lat, lng, boundary_lat, lng)
    assert abs(dist - 100.0) < 1e-6
    assert truck_pickup_location_mismatch(_truck(lat, lng, radius=100), _order((boundary_lat, lng))) is None


def test_4_pickup_just_outside_radius_is_rejected():
    lat, lng = GUJRANWALA
    outside_lat = lat + math.degrees(100.5 / 6371.0)  # ~100.5 km, beyond the 0.05 km epsilon
    reason = truck_pickup_location_mismatch(_truck(lat, lng, radius=100), _order((outside_lat, lng)))
    assert reason is not None and "service radius" in reason


def test_5_gujranwala_truck_does_not_see_karachi_pickup():
    reason = truck_order_eligibility_mismatch(_truck(*GUJRANWALA), REQUIRED, _order(KARACHI))
    assert reason is not None
    # It fails on distance, not on cargo (the flatbed can carry the load).
    assert truck_order_mismatch(_truck(*GUJRANWALA), REQUIRED, _order(KARACHI)) is None


def test_6_dropoff_distance_does_not_affect_visibility():
    # Same pickup (Gujranwala), dropoff in far Karachi vs near Lahore: both visible.
    near_pickup_far_drop = _order(GUJRANWALA, dropoff=KARACHI)
    near_pickup_near_drop = _order(GUJRANWALA, dropoff=LAHORE)
    assert truck_order_eligibility_mismatch(_truck(*GUJRANWALA), REQUIRED, near_pickup_far_drop) is None
    assert truck_order_eligibility_mismatch(_truck(*GUJRANWALA), REQUIRED, near_pickup_near_drop) is None


# ---------------------------------------------------------------------------
# 7-8: bidding gate (cargo vs distance)
# ---------------------------------------------------------------------------

def test_7_correct_cargo_but_distant_truck_cannot_bid():
    order = _order(KARACHI, required=REQUIRED, weight=33.7)
    truck = _truck(*GUJRANWALA)  # right type + capacity, wrong location
    assert truck_order_mismatch(truck, REQUIRED, order) is None            # cargo OK
    reason = truck_order_eligibility_mismatch(truck, REQUIRED, order)      # location fails
    assert reason is not None and "service radius" in reason


def test_8_nearby_truck_wrong_type_still_cannot_bid():
    order = _order(GUJRANWALA, required=["refrigerated_rigid_truck"], weight=5)
    truck = _truck(*GUJRANWALA)  # nearby, but a flatbed — wrong required type
    reason = truck_order_eligibility_mismatch(truck, order["required_truck_types"], order)
    assert reason is not None and "truck type" in reason.lower()


# ---------------------------------------------------------------------------
# 9-10: missing-coordinate behavior
# ---------------------------------------------------------------------------

def test_9_missing_truck_coordinates_no_nationwide_visibility():
    truck = _truck(None, None)  # active, but no operating location
    reason = truck_order_eligibility_mismatch(truck, REQUIRED, _order(GUJRANWALA))
    assert reason == LOCATION_UNSET_REASON


def test_10_missing_order_coordinates_allow_exact_city_fallback_only():
    order_no_coords = {"pickup_lat": None, "pickup_lng": None,
                       "pickup_city": "Gujranwala, Punjab, Pakistan",
                       "required_truck_types": REQUIRED, "goods_weight_tons": 10}
    # Exact normalized city match -> eligible.
    truck_match = _truck(*GUJRANWALA, city="Gujranwala")
    assert truck_order_eligibility_mismatch(truck_match, REQUIRED, order_no_coords) is None
    # Similarly-named but different city -> NOT eligible (no substring match).
    truck_gujrat = _truck(*GUJRAT, city="Gujrat")
    assert truck_order_eligibility_mismatch(truck_gujrat, REQUIRED, order_no_coords) is not None
    # No city on the truck -> ineligible, never nationwide.
    truck_no_city = _truck(*GUJRANWALA, city=None)
    assert truck_order_eligibility_mismatch(truck_no_city, REQUIRED, order_no_coords) is not None


# ---------------------------------------------------------------------------
# 11 + 13: bid comparison serialization (unavailable + no coord leak)
# ---------------------------------------------------------------------------

def _comparison_row(truck_lat, truck_lng, city, bid_status="pending"):
    """A single _BID_COMPARISON_SQL-shaped row for a flatbed bid."""
    return {
        "bid_id": 1, "order_id": 1, "transporter_user_id": 7, "truck_id": 12,
        "bid_price": 50000, "message": None, "bid_status": bid_status,
        "bid_created_at": None, "bid_updated_at": None,
        "transporter_display_name": "T", "transporter_company_name": "Fleet",
        "completed_trips": 0,
        "truck_row_id": 12, "truck_owner_user_id": 7,
        "truck_number": "DTX-MTCH-007", "truck_company": "DTX", "truck_model": "F",
        "truck_type": "Flatbed", "catalog_type_key": "flatbed_trailer_open_semi_trailer",
        "capacity_tons": 45, "payload_min_tons": 20, "payload_max_tons": 45,
        "volume_min_cbm": 0, "volume_max_cbm": 0,
        "bed_length_ft": 21, "bed_width_ft": 7, "bed_height_ft": 8,
        "body_style": "Open flatbed", "truck_photo_path": None, "truck_status": "active",
        "current_city": city, "current_lat": truck_lat, "current_lng": truck_lng,
        "service_radius_km": 100,
    }


def _open_flatbed_order(pickup):
    return {"id": 1, "status": "open", "required_truck_types": '["flatbed_trailer_open_semi_trailer"]',
            "goods_weight_tons": 10, "pickup_lat": pickup[0], "pickup_lng": pickup[1]}


def test_11_comparison_marks_distant_bid_unavailable():
    order = _open_flatbed_order(GUJRANWALA)
    row = _comparison_row(*KARACHI, city="Karachi")  # bid truck now far from pickup
    bid = serialize_enriched_bid(row, order)
    assert bid["can_checkout"] is False
    assert bid["unavailable_reason"] and "service radius" in bid["unavailable_reason"]


def test_13_exact_truck_coordinates_absent_from_seeker_json():
    order = _open_flatbed_order(GUJRANWALA)
    for pos, city in ((GUJRANWALA, "Gujranwala"), (KARACHI, "Karachi")):
        bid = serialize_enriched_bid(_comparison_row(*pos, city=city), order)
        truck = bid["truck"]
        assert truck is not None
        # The coarse city is exposed; the exact pre-trip coordinates are NOT.
        assert truck.get("current_city") == city
        assert "current_lat" not in truck
        assert "current_lng" not in truck
    # And a nearby, pending bid on an open order is checkout-eligible.
    near = serialize_enriched_bid(_comparison_row(*GUJRANWALA, city="Gujranwala"), order)
    assert near["can_checkout"] is True
    assert near["unavailable_reason"] is None


# ---------------------------------------------------------------------------
# 12 (quote portion): quote rejects a distant truck before any db/provider use
# ---------------------------------------------------------------------------

def test_12_quote_rejects_truck_outside_radius_before_mutation():
    from shared.payments import build_payment_quote, CheckoutError

    order = {"id": 1, "status": "open", "required_truck_types": '["flatbed_trailer_open_semi_trailer"]',
             "goods_weight_tons": 10, "pickup_lat": GUJRANWALA[0], "pickup_lng": GUJRANWALA[1]}
    bid = {"id": 1, "truck_id": 12, "transporter_user_id": 7, "bid_price": 50000}
    user = {"id": 2, "role": "service_seeker"}
    distant_truck = _truck(*KARACHI, city="Karachi")
    distant_truck.update({"id": 12, "owner_user_id": 7})

    # db is passed but never reached: validate_bid_truck fails first, so no
    # wallet is read and no provider is charged. Passing db=None proves it.
    with pytest.raises(CheckoutError) as exc:
        build_payment_quote(None, order, bid, user, wallet=None, truck=distant_truck)
    assert exc.value.status == 409
    assert exc.value.code == "bid_truck_unavailable"


# ---------------------------------------------------------------------------
# 14: the matching audit uses the SAME production eligibility helper
# ---------------------------------------------------------------------------

def test_14_matching_audit_uses_production_eligibility_helper():
    import sys
    from pathlib import Path
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import audit_order_matching as audit
    import orders.helpers as helpers
    assert audit.truck_order_eligibility_mismatch is helpers.truck_order_eligibility_mismatch


# ---------------------------------------------------------------------------
# 16: tracking route-distance is unchanged after sharing the Haversine helper
# ---------------------------------------------------------------------------

def test_16_tracking_route_distance_unchanged_and_single_impl():
    from tracking.traccar import calculate_route_distance_km
    import tracking.traccar as traccar

    points = [{"lat": 30.41, "lon": 71.0}, {"lat": 30.03, "lon": 72.15}, {"lat": 31.55, "lon": 74.34}]
    expected = sum(
        haversine_distance_km(p["lat"], p["lon"], c["lat"], c["lon"])
        for p, c in zip(points, points[1:])
    )
    assert calculate_route_distance_km(points) == pytest.approx(expected, abs=1e-12)
    # Degenerate inputs keep their old, safe behavior.
    assert calculate_route_distance_km([]) == 0.0
    assert calculate_route_distance_km([{"lat": 1, "lon": 1}]) == 0.0
    # The route calculator uses the shared helper — there is no second formula.
    assert traccar.haversine_distance_km is haversine_distance_km


# ===========================================================================
# PostgreSQL integration tests (skipped without a dedicated test database)
# ===========================================================================

def _make_user(db, role, email):
    return db.execute(
        "INSERT INTO users (full_name, email, role) VALUES (%s, %s, %s) RETURNING id",
        (email, email, role),
    ).fetchone()["id"]


def _make_flatbed(db, owner_id, lat, lng, city, radius=100, status="active"):
    return db.execute(
        "INSERT INTO vehicles (owner_user_id, truck_number, truck_type, catalog_type_key, "
        "capacity_tons, payload_max_tons, volume_max_cbm, bed_length_ft, bed_width_ft, bed_height_ft, "
        "current_city, current_lat, current_lng, service_radius_km, status) "
        "VALUES (%s, %s, 'Flatbed', 'flatbed_trailer_open_semi_trailer', 45, 45, 0, 21, 7, 8, "
        "%s, %s, %s, %s, %s) RETURNING id",
        (owner_id, f"T-{owner_id}", city, lat, lng, radius, status),
    ).fetchone()["id"]


def _make_open_order(db, client_id, pickup, dropoff=KARACHI):
    return db.execute(
        "INSERT INTO shipments (client_user_id, status, goods_type, goods_weight_tons, "
        "required_truck_types, pickup_city, pickup_lat, pickup_lng, dropoff_lat, dropoff_lng) "
        "VALUES (%s, 'open', 'Cotton', 33.7, '[\"flatbed_trailer_open_semi_trailer\"]', "
        "'Gujranwala', %s, %s, %s, %s) RETURNING id",
        (client_id, pickup[0], pickup[1], dropoff[0], dropoff[1]),
    ).fetchone()["id"]


def test_available_orders_filters_by_location(client):
    """Availability endpoint: a near truck sees the order (with distance); a far
    truck does not; a truck with no location triggers the setup prompt."""
    db = client.db
    seeker_id = _make_user(db, "service_seeker", "seeker@test")
    transporter_id = _make_user(db, "transporter", "carrier@test")
    order_id = _make_open_order(db, seeker_id, GUJRANWALA)
    db.commit()

    transporter = {"id": transporter_id, "role": "transporter"}

    # (a) Far truck (Karachi) -> order hidden.
    far_truck = _make_flatbed(db, transporter_id, *KARACHI, city="Karachi")
    db.commit()
    client.login(transporter)
    resp = client.get("/api/orders/available").get_json()
    assert resp["success"] is True
    assert all(o["id"] != order_id for o in resp["orders"])
    assert resp["orders_out_of_range"] >= 1

    # (b) Add a near truck (Gujranwala) -> order visible with a distance.
    _make_flatbed(db, transporter_id, *GUJRANWALA, city="Gujranwala")
    db.commit()
    resp = client.get("/api/orders/available").get_json()
    listed = [o for o in resp["orders"] if o["id"] == order_id]
    assert listed and listed[0]["distance_to_pickup_km"] is not None
    assert listed[0]["distance_to_pickup_km"] < 1.0


def test_available_orders_prompts_when_no_truck_location(client):
    db = client.db
    seeker_id = _make_user(db, "service_seeker", "seeker2@test")
    transporter_id = _make_user(db, "transporter", "carrier2@test")
    _make_open_order(db, seeker_id, GUJRANWALA)
    # Active truck with NO coordinates.
    _make_flatbed(db, transporter_id, None, None, city=None)
    db.commit()

    client.login({"id": transporter_id, "role": "transporter"})
    resp = client.get("/api/orders/available").get_json()
    assert resp["location_setup_required"] is True
    assert resp["orders"] == []


def test_checkout_rejects_truck_moved_outside_radius(client):
    """A bid placed while near is checked out after the truck moves far away:
    checkout must reject it (409) with no trip and no payment created."""
    import json as _json

    db = client.db
    seeker_id = _make_user(db, "service_seeker", "seeker3@test")
    transporter_id = _make_user(db, "transporter", "carrier3@test")
    order_id = _make_open_order(db, seeker_id, GUJRANWALA)
    truck_id = _make_flatbed(db, transporter_id, *GUJRANWALA, city="Gujranwala")
    db.commit()

    # Transporter bids while the truck is near the pickup.
    client.login({"id": transporter_id, "role": "transporter"})
    bid_resp = client.post(
        f"/api/orders/{order_id}/bids",
        data=_json.dumps({"truck_id": truck_id, "bid_price": 50000}),
        content_type="application/json",
        headers={"X-CSRF-Token": "test-csrf-token"},
    )
    assert bid_resp.status_code == 200, bid_resp.get_data(as_text=True)
    bid_id = db.execute("SELECT id FROM shipment_bids WHERE order_id = %s", (order_id,)).fetchone()["id"]

    # The truck moves to Karachi (outside its 100 km radius of the pickup).
    db.execute("UPDATE vehicles SET current_lat = %s, current_lng = %s, current_city = 'Karachi' WHERE id = %s",
               (KARACHI[0], KARACHI[1], truck_id))
    db.commit()

    # Client attempts checkout -> rejected before any wallet/provider mutation.
    client.login({"id": seeker_id, "role": "service_seeker"})
    resp = client.post(
        f"/api/orders/{order_id}/bids/{bid_id}/checkout",
        data=_json.dumps({}),
        content_type="application/json",
        headers={"X-CSRF-Token": "test-csrf-token", "Idempotency-Key": "loc-test-key-0001"},
    )
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["code"] == "bid_truck_unavailable"
    # Nothing was created.
    assert db.execute("SELECT count(*) AS c FROM shipment_trips WHERE order_id = %s", (order_id,)).fetchone()["c"] == 0
    assert db.execute("SELECT count(*) AS c FROM payments WHERE shipment_id = %s", (order_id,)).fetchone()["c"] == 0
    # And the order is still open (bid not accepted).
    assert db.execute("SELECT status FROM shipments WHERE id = %s", (order_id,)).fetchone()["status"] == "open"
