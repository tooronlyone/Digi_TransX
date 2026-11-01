"""Authoritative coordinate parsing for one-time order and truck write paths."""

import math


class CoordinateValidationError(ValueError):
    """Raised when a supplied optional coordinate pair is malformed."""


def _is_missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _parse_coordinate(value, label, axis, minimum, maximum):
    if isinstance(value, bool) or isinstance(value, (dict, list, tuple, set)):
        raise CoordinateValidationError(
            f"{label} {axis} must be a valid finite number."
        )
    try:
        parsed = float(value.strip() if isinstance(value, str) else value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CoordinateValidationError(
            f"{label} {axis} must be a valid finite number."
        ) from exc
    if not math.isfinite(parsed):
        raise CoordinateValidationError(
            f"{label} {axis} must be a valid finite number."
        )
    if not minimum <= parsed <= maximum:
        raise CoordinateValidationError(
            f"{label} {axis} must be between {minimum:g} and {maximum:g}."
        )
    return parsed


def parse_optional_coordinate_pair(
    values,
    latitude_key,
    longitude_key,
    *,
    label="Location",
):
    """Return a validated ``(latitude, longitude)`` pair or ``(None, None)``.

    Coordinates remain optional. When either member is supplied, both are
    required. Numeric strings are accepted to preserve the existing API/form
    contract; booleans, containers, malformed values, NaN and infinities are
    rejected. Latitude and longitude boundaries are inclusive.
    """

    latitude_raw = values.get(latitude_key)
    longitude_raw = values.get(longitude_key)
    latitude_missing = _is_missing(latitude_raw)
    longitude_missing = _is_missing(longitude_raw)
    if latitude_missing and longitude_missing:
        return None, None
    if latitude_missing != longitude_missing:
        raise CoordinateValidationError(
            f"{label} needs both latitude and longitude, or neither."
        )
    latitude = _parse_coordinate(
        latitude_raw, label, "latitude", -90.0, 90.0
    )
    longitude = _parse_coordinate(
        longitude_raw, label, "longitude", -180.0, 180.0
    )
    return latitude, longitude
