"""Shared constants and helpers for the transporter-matching test fixtures.

Both ``seed_matching_test_fleet.py`` and ``audit_order_matching.py`` import
from here, so the test marker, the reserved-email scheme, the catalog-driven
truck distribution and the project-ref masking live in exactly one place —
there is no second copy of any of this logic.

Importing this module does NOT connect to the database or to Supabase: it only
reads the existing ``TRUCK_TYPES`` catalog (the single source of truth for
truck types). Callers that write do so through the existing shared Supabase
client and the existing ``shared.db`` wrapper.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import os  # noqa: E402

from trucks.helpers import TRUCK_TYPES, get_catalog_type  # noqa: E402

# --- Fixture identity -------------------------------------------------------
# The single source of truth for what a matching fixture row looks like.
# Cleanup keys off these EXACT values (email prefix AND settings marker) so it
# can never target a real account.
SEED_MARKER = "transporter-matching-v1"      # value stored in metadata/settings
SEED_TAG_KEY = "test_seed"                   # settings_json / metadata key
EMAIL_PREFIX = "dtx.matching.seed."
EMAIL_DOMAIN = "example.test"                # reserved TLD — never deliverable
ROLE = "transporter"
LEGACY_ROLE = "logistics_provider"
FLEET_COUNT = 50
PASSWORD_ENV = "DIGITRANSX_MATCHING_TEST_PASSWORD"

# The catalog has exactly 18 types; the distribution below relies on that.
CATALOG_TYPE_COUNT = len(TRUCK_TYPES)


# --- Deterministic per-transporter identifiers -----------------------------
# All reserved/synthetic so they can never collide with real user data.
def seed_email(n):
    return f"{EMAIL_PREFIX}{n:03d}@{EMAIL_DOMAIN}"


def email_like_pattern():
    """SQL LIKE pattern matching ONLY our reserved seed emails."""
    return f"{EMAIL_PREFIX}%@{EMAIL_DOMAIN}"


def is_seed_email(email):
    e = (email or "").lower()
    return e.startswith(EMAIL_PREFIX) and e.endswith("@" + EMAIL_DOMAIN)


def seed_cnic(n):
    # 13 digits, reserved 9999-prefix block: 9999 0000 + 5-digit index.
    return f"99990000{n:05d}"


def seed_phone(n):
    # 11-digit Pakistani mobile in a reserved 0300 000 xxxx block.
    return f"0300000{n:04d}"


def seed_truck_number(n):
    return f"DTX-MTCH-{n:03d}"


def seed_chassis(n):
    # Exactly 17 chars (VIN length): "DTXMATCHSEED" (12) + 5-digit index.
    value = f"DTXMATCHSEED{n:05d}"
    assert len(value) == 17, value
    return value


def seed_full_name(n):
    return f"DTX Matching Test Transporter {n:03d}"


def seed_company(n):
    return f"DTX Test Fleet {n:03d}"


def seed_metadata(n):
    """Supabase Auth user_metadata for transporter ``n``. The DB trigger reads
    legacy_role/role/full_name/phone/cnic from here to create public.users."""
    return {
        "full_name": seed_full_name(n),
        "phone": seed_phone(n),
        "cnic": seed_cnic(n),
        "role": ROLE,
        "legacy_role": LEGACY_ROLE,
        SEED_TAG_KEY: SEED_MARKER,
    }


# --- Truck distribution -----------------------------------------------------
def build_type_distribution():
    """Return a list of 50 catalog ``type_key`` values, one per transporter.

    Every one of the 18 catalog types appears at least twice (36); the
    remaining 14 vehicles go to the first 14 types. No invented keys.
    """
    keys = [t["type_key"] for t in TRUCK_TYPES]
    dist = keys * 2                          # 36: every type twice
    remaining = FLEET_COUNT - len(dist)      # 14
    dist += keys[:remaining]                 # first 14 types get a third
    assert len(dist) == FLEET_COUNT, len(dist)
    return dist


def build_fleet_plan():
    """(index, type_key, occurrence) for each of the 50 transporters, where
    ``occurrence`` is the 0-based ordinal of this vehicle among all vehicles of
    the same catalog type. The variant is driven off ``occurrence`` (not the
    index) so successive vehicles of the SAME type land on the upper / lower /
    midpoint of the catalog range — the type recurs every 18 slots, so an
    index-based variant would collapse to one value per type."""
    dist = build_type_distribution()
    seen = {}
    plan = []
    for i, type_key in enumerate(dist, start=1):
        occurrence = seen.get(type_key, 0)
        seen[type_key] = occurrence + 1
        plan.append({"index": i, "type_key": type_key, "occurrence": occurrence})
    return plan


# Cold-chain / hazmat / fragile capability by catalog type.
_REEFER_TYPES = {
    "refrigerated_rigid_truck",
    "reefer_trailer_reefer_container_carrier",
}
_HAZ_TYPES = {"fuel_oil_tanker", "chemical_tanker"}
_FRAGILE_TYPES = {
    "insulated_or_dry_box_truck",
    "refrigerated_rigid_truck",
    "light_truck_2_3_5_ton",
    "light_truck_3_5_5_ton",
}
_PROVINCE_SETS = [
    "Punjab,Sindh",
    "Punjab",
    "Sindh,Balochistan",
    "Khyber Pakhtunkhwa,Punjab",
    "Punjab,Sindh,Balochistan,Khyber Pakhtunkhwa",
]

# --- Operating-location fixtures --------------------------------------------
# THE single registry of realistic Pakistani operating cities + coordinates.
# Each city's coordinates appear exactly once here; both the vehicle fixture
# builder and location-aware tests read cities from this one list (no second
# city-coordinate registry anywhere).
OPERATING_CITIES = [
    {"city": "Gujranwala", "lat": 32.1877, "lng": 74.1945},
    {"city": "Lahore",     "lat": 31.5204, "lng": 74.3587},
    {"city": "Sialkot",    "lat": 32.4945, "lng": 74.5229},
    {"city": "Gujrat",     "lat": 32.5731, "lng": 74.0789},
    {"city": "Faisalabad", "lat": 31.4504, "lng": 73.1350},
    {"city": "Islamabad",  "lat": 33.6844, "lng": 73.0479},
    {"city": "Rawalpindi", "lat": 33.5651, "lng": 73.0169},
    {"city": "Multan",     "lat": 30.1575, "lng": 71.5249},
    {"city": "Karachi",    "lat": 24.8607, "lng": 67.0011},
    {"city": "Hyderabad",  "lat": 25.3960, "lng": 68.3578},
    {"city": "Peshawar",   "lat": 34.0151, "lng": 71.5805},
    {"city": "Quetta",     "lat": 30.1798, "lng": 66.9750},
]

DEFAULT_FIXTURE_RADIUS_KM = 100


def seed_location(n):
    """Deterministic operating city + coordinates for transporter ``n`` (1-based),
    cycling through the central OPERATING_CITIES registry. Service radius is the
    100 km default for every fixture vehicle."""
    city = OPERATING_CITIES[(n - 1) % len(OPERATING_CITIES)]
    return {
        "current_city": city["city"],
        "current_lat": city["lat"],
        "current_lng": city["lng"],
        "service_radius_km": DEFAULT_FIXTURE_RADIUS_KM,
    }


def _vary(lo, hi, variant):
    """Deterministically pick a boundary or midpoint value within [lo, hi]."""
    lo = float(lo)
    hi = float(hi)
    if hi <= lo:
        return hi
    if variant == 0:
        return round(hi, 2)              # upper boundary
    if variant == 1:
        return round(lo, 2)              # lower boundary
    return round((lo + hi) / 2, 2)       # midpoint


def _has_physical_bed(type_key):
    """Rigid/box/flatbed/dump bodies have a cargo bed whose dimensions matter;
    tankers and livestock carriers do not (their bed axes stay 0 = unbounded,
    matching production's skip behaviour)."""
    if "tanker" in type_key:
        return False
    return any(tok in type_key for tok in ("truck", "flatbed", "container", "low_bed", "dump"))


def build_vehicle_fields(n, type_key, occurrence=0):
    """Realistic, varied vehicle fields for transporter ``n`` of ``type_key``.

    ``occurrence`` (0-based ordinal among same-type vehicles) selects the
    upper / lower / midpoint variant, so values stay inside the catalog ranges
    but differ between vehicles of the same type — making weight, volume and
    dimension boundary cases exercisable for every type.
    """
    cat = get_catalog_type(type_key)
    if not cat:
        raise ValueError(f"Unknown catalog type_key: {type_key}")
    variant = occurrence % 3

    pmax = float(cat["payload_max_tons"])
    capacity = _vary(cat["payload_min_tons"], pmax, variant) if pmax > 0 else 0
    volume_max = (
        _vary(cat["volume_min_cbm"], cat["volume_max_cbm"], variant)
        if float(cat["volume_max_cbm"]) > 0
        else 0
    )

    if _has_physical_bed(type_key):
        bed_length = round(12 + (n % 25) + (2 if variant == 0 else 0), 1)  # ~12–38 ft
        bed_width = round(6 + (n % 3), 1)                                  # 6–8 ft
        bed_height = round(5 + (n % 4), 1)                                 # 5–8 ft
    else:
        bed_length = bed_width = bed_height = 0

    return {
        "truck_number": seed_truck_number(n),
        "truck_company": "DTX-Test",
        "truck_model": f"Fixture-{n:03d}",
        "truck_type": cat["display_name"],
        "catalog_type_key": type_key,
        "chassis_number": seed_chassis(n),
        "capacity_tons": capacity,
        "main_use": (cat["common_uses"] or ["General cargo"])[0],
        "payload_min_tons": float(cat["payload_min_tons"]),
        "payload_max_tons": pmax,
        "volume_min_cbm": float(cat["volume_min_cbm"]),
        "volume_max_cbm": volume_max,
        "bed_length_ft": bed_length,
        "bed_width_ft": bed_width,
        "bed_height_ft": bed_height,
        "body_style": cat["typical_body_style"],
        "operating_provinces": _PROVINCE_SETS[n % len(_PROVINCE_SETS)],
        "refrigeration_supported": type_key in _REEFER_TYPES,
        "hazardous_supported": type_key in _HAZ_TYPES,
        "fragile_supported": type_key in _FRAGILE_TYPES,
        "status": "active",
        # Vehicle-level current operating location (from the central registry).
        **seed_location(n),
    }


def vehicle_specs_marker(n, type_key):
    """catalog_specs_json payload — carries the seed marker so a test vehicle
    is self-identifying as a secondary safety guard (the authoritative link is
    still owner_user_id -> a marked user)."""
    return {SEED_TAG_KEY: SEED_MARKER, "seeded_index": n, "catalog_type_key": type_key}


# --- Safe row selection (used by both audit and cleanup) -------------------
def marked_users_where():
    """A WHERE fragment + params selecting ONLY seed users: the reserved email
    prefix AND the exact settings marker must both match. Returned as (sql,
    params) so callers can compose it and never widen it."""
    return (
        "email LIKE %s AND settings_json ->> %s = %s",
        [email_like_pattern(), SEED_TAG_KEY, SEED_MARKER],
    )


# --- Target (project ref / host) identification & masking ------------------
def project_ref_and_host():
    """Return (ref, host) derived from SUPABASE_URL. Never returns keys/URLs."""
    url = os.environ.get("SUPABASE_URL", "")
    host = urlparse(url).hostname or ""
    ref = host.split(".")[0] if host else ""
    return ref, host


def mask_ref(ref):
    if not ref:
        return "(unknown)"
    if len(ref) <= 6:
        return ref[0] + "***"
    return f"{ref[:4]}...{ref[-4:]}"


def mask_host(host):
    if not host:
        return "(unknown)"
    ref, _, rest = host.partition(".")
    return f"{mask_ref(ref)}.{rest}" if rest else mask_ref(ref)


def looks_like_test_target(ref, host):
    """Heuristic: is the target CLEARLY a development/staging/test project?"""
    hay = f"{ref} {host}".lower()
    tokens = ("dev", "stag", "test", "local", "127.0.0.1", "sandbox", "demo", "qa")
    return any(tok in hay for tok in tokens)
