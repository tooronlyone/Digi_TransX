"""Geospatial helpers — the single Haversine implementation for the backend.

There is deliberately exactly ONE great-circle distance function in the whole
codebase. Route-distance accumulation in ``tracking.traccar`` and truck ->
pickup eligibility in ``orders.helpers`` both call ``haversine_distance_km``;
no other module reimplements the formula.
"""

import math

EARTH_RADIUS_KM = 6371.0


def haversine_distance_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in kilometres between two lat/lng points.

    Inputs are degrees (coerced to float). Uses the standard Haversine formula
    with a mean Earth radius of 6371 km — identical maths to the original
    per-segment route-distance calculation this replaced, so accumulated route
    distances are unchanged.
    """
    lat1 = math.radians(float(lat1))
    lng1 = math.radians(float(lng1))
    lat2 = math.radians(float(lat2))
    lng2 = math.radians(float(lng2))
    delta_lat = lat2 - lat1
    delta_lng = lng2 - lng1
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c
