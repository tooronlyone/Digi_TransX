import json

from flask import Blueprint, request

from auth.helpers import json_response, login_required, require_csrf, timestamp_bundle
from shared.db import open_db
from .helpers import (
    TRUCK_TYPES,
    build_truck_payload,
    get_catalog_type,
    parse_optional_cnic,
    parse_optional_float,
    parse_optional_text,
)


trucks_blueprint = Blueprint("trucks", __name__, url_prefix="/api")


@trucks_blueprint.get("/catalog/truck-types")
def truck_types_catalog():
    return json_response({"success": True, "truck_types": TRUCK_TYPES})


@trucks_blueprint.post("/trucks")
@login_required
def create_truck():
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    form = request.form
    truck_number = (form.get("truckNumber") or "").strip()
    truck_type = (form.get("truckType") or form.get("truck_type") or "").strip()
    chassis_number = (form.get("chassisNumber") or "").strip()
    capacity_raw = (form.get("capacity") or "").strip()
    main_use = (form.get("mainUse") or "").strip()

    if not truck_number:
        return json_response({"success": False, "message": "Truck number is required."}, 400)
    if not truck_type:
        return json_response({"success": False, "message": "Truck type is required."}, 400)
    if not chassis_number:
        return json_response({"success": False, "message": "Chassis number is required."}, 400)
    if not main_use:
        return json_response({"success": False, "message": "Main use is required."}, 400)

    try:
        capacity = float(capacity_raw)
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Capacity must be a valid number."}, 400)

    if capacity <= 0:
        return json_response({"success": False, "message": "Capacity must be greater than 0."}, 400)
    if not 11 <= len(chassis_number) <= 17:
        return json_response({"success": False, "message": "Chassis number must be 11 to 17 characters."}, 400)

    catalog_type_key = parse_optional_text(form.get("catalog_type_key"))
    catalog_type = get_catalog_type(catalog_type_key) if catalog_type_key else None
    catalog_specs_raw = parse_optional_text(form.get("catalog_specs_json"))
    if catalog_specs_raw:
      try:
        json.loads(catalog_specs_raw)
      except json.JSONDecodeError:
        return json_response({"success": False, "message": "Catalog specs format is invalid."}, 400)

    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute(
            """
            INSERT INTO trucks (
                owner_user_id, truck_number, truck_type, catalog_type_key,
                chassis_number, capacity_tons, main_use,
                payload_min_kg, payload_max_kg, volume_min_cbm, volume_max_cbm,
                body_style, catalog_specs_json, driver_name, driver_cnic, tracking_id,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                request.current_user["id"],
                truck_number,
                truck_type,
                catalog_type_key,
                chassis_number,
                capacity,
                main_use,
                parse_optional_float(form.get("payload_min_kg")) if form.get("payload_min_kg") is not None else (catalog_type.get("payload_min_kg") if catalog_type else None),
                parse_optional_float(form.get("payload_max_kg")) if form.get("payload_max_kg") is not None else (catalog_type.get("payload_max_kg") if catalog_type else None),
                parse_optional_float(form.get("volume_min_cbm")) if form.get("volume_min_cbm") is not None else (catalog_type.get("volume_min_cbm") if catalog_type else None),
                parse_optional_float(form.get("volume_max_cbm")) if form.get("volume_max_cbm") is not None else (catalog_type.get("volume_max_cbm") if catalog_type else None),
                parse_optional_text(form.get("body_style")) or (catalog_type.get("typical_body_style") if catalog_type else None),
                catalog_specs_raw,
                parse_optional_text(form.get("driverName")),
                parse_optional_cnic(form.get("driverCnic")),
                parse_optional_text(form.get("trackingId")),
                stamp["display"],
                stamp["display"],
            ),
        )
        db.commit()

    return json_response({"success": True, "message": "Truck registered successfully"})


@trucks_blueprint.get("/trucks")
@login_required
def list_trucks():
    with open_db() as db:
        rows = db.execute(
            """
            SELECT * FROM trucks
            WHERE owner_user_id = ?
            ORDER BY id DESC
            """,
            (request.current_user["id"],),
        ).fetchall()

    return json_response({"success": True, "trucks": [build_truck_payload(dict(row)) for row in rows]})
