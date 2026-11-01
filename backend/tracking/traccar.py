"""
GPS Provider Integration for Digi_TransX.
Currently: stub/unconfigured mode.
When a GPS provider (Falcon-i, TPL Trakker, etc.) gives API credentials,
update GPS_PROVIDER_* constants below and implement the three functions.
All functions return None / [] on failure - never crash the app.
"""

from shared.geo import haversine_distance_km

# =============================================================
# GPS PROVIDER CONFIG - update these when you get API access
# =============================================================
GPS_PROVIDER_NAME = "unconfigured"   # e.g. "falcon-i", "tpl-trakker"
GPS_PROVIDER_API_URL = ""            # e.g. "https://api.falcon-i.com/v1"
GPS_PROVIDER_API_KEY = ""            # API key from provider
GPS_PROVIDER_ENABLED = False         # Set True only when credentials are set
REQUEST_TIMEOUT = 5


def register_device(imei: str, name: str) -> str | None:
    """
    Register a GPS device with the provider.
    Returns a provider device ID (string) or None.

    When GPS_PROVIDER_ENABLED is False: return imei as-is so the truck
    still saves its IMEI in DB for future use.

    When implementing for a real provider:
    - Call provider's register/add-device API
    - Return the provider's device identifier
    """
    try:
        imei = (imei or "").strip()
        if not imei:
            return None
        if not GPS_PROVIDER_ENABLED:
            # Store IMEI directly - provider not configured yet
            return imei
        # TODO: implement provider-specific registration
        # Example structure:
        # response = requests.post(
        #     f"{GPS_PROVIDER_API_URL}/devices",
        #     headers={"Authorization": f"Bearer {GPS_PROVIDER_API_KEY}"},
        #     json={"imei": imei, "name": name},
        #     timeout=REQUEST_TIMEOUT,
        # )
        # response.raise_for_status()
        # return str(response.json()["device_id"])
        return imei
    except Exception:
        return None


def get_latest_position(device_id: str) -> dict | None:
    """
    Fetch latest GPS position for a device.
    Returns {lat, lon, speed, timestamp} or None.

    When GPS_PROVIDER_ENABLED is False: return None (no data available).

    When implementing for a real provider:
    - Call provider's latest-position or current-location API
    - Map response fields to {lat, lon, speed, timestamp}
    """
    try:
        if not GPS_PROVIDER_ENABLED or not device_id:
            return None
        # TODO: implement provider-specific position fetch
        # Example structure:
        # response = requests.get(
        #     f"{GPS_PROVIDER_API_URL}/positions/latest",
        #     headers={"Authorization": f"Bearer {GPS_PROVIDER_API_KEY}"},
        #     params={"device_id": device_id},
        #     timeout=REQUEST_TIMEOUT,
        # )
        # response.raise_for_status()
        # data = response.json()
        # return {
        #     "lat": data["latitude"],
        #     "lon": data["longitude"],
        #     "speed": data.get("speed"),
        #     "timestamp": data.get("timestamp"),
        # }
        return None
    except Exception:
        return None


def get_positions_between(device_id: str, from_dt: str, to_dt: str) -> list:
    """
    Fetch GPS positions between two ISO timestamps.
    Returns list of {lat, lon, timestamp} dicts. Returns [] on failure.

    When GPS_PROVIDER_ENABLED is False: return [] (no data available).

    When implementing for a real provider:
    - Call provider's history/route API with time range
    - Map each point to {lat, lon, timestamp}
    """
    try:
        if not GPS_PROVIDER_ENABLED or not device_id:
            return []
        # TODO: implement provider-specific history fetch
        return []
    except Exception:
        return []


def calculate_route_distance_km(positions: list) -> float:
    """
    Calculate total route distance using haversine formula.
    Input: list of {lat, lon} dicts.
    Returns distance in km as float.

    Sums the shared ``haversine_distance_km`` over consecutive points — the one
    Haversine implementation in the codebase — so the accumulated distance is
    identical to the previous inline formula.
    """
    try:
        if len(positions) < 2:
            return 0.0
        total_km = 0.0
        for previous, current in zip(positions, positions[1:]):
            total_km += haversine_distance_km(
                previous["lat"], previous["lon"], current["lat"], current["lon"]
            )
        return total_km
    except Exception:
        return 0.0
