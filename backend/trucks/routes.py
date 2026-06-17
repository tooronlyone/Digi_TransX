import json

from flask import Blueprint, request, send_from_directory

from auth.helpers import json_response, login_required, require_csrf, timestamp_bundle
from shared.db import open_db
from .helpers import (
    STATUS_OPTIONS,
    STATUS_REASON_LABELS,
    TRUCK_TYPES,
    UPLOADS_DIR,
    build_truck_payload,
    build_configuration_payload,
    get_catalog_fields,
    get_catalog_type,
    get_status_reason_label,
    make_upload_relative_path,
    parse_bool_flag,
    parse_optional_cnic,
    parse_optional_float,
    parse_optional_text,
)


trucks_blueprint = Blueprint("trucks", __name__)


def get_owned_truck_or_error(truck_id, owner_user_id):
    with open_db() as db:
        row = db.execute("SELECT * FROM trucks WHERE id = ?", (truck_id,)).fetchone()
    if not row:
        return None, json_response({"success": False, "message": "Truck not found."}, 404)
    truck = dict(row)
    if truck["owner_user_id"] != owner_user_id:
        return None, json_response({"success": False, "message": "You are not allowed to access this truck."}, 403)
    return truck, None


@trucks_blueprint.get("/api/catalog/truck-types")
def truck_types_catalog():
    return json_response({"success": True, "truck_types": TRUCK_TYPES})


@trucks_blueprint.get("/api/catalog/truck-types/<string:type_key>/fields")
def truck_type_fields(type_key):
    return json_response({"success": True, "fields": get_catalog_fields(type_key)})


@trucks_blueprint.get("/uploads/trucks/<path:filename>")
def serve_truck_upload(filename):
    return send_from_directory(UPLOADS_DIR, filename)


@trucks_blueprint.post("/api/trucks")
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


@trucks_blueprint.get("/api/trucks")
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


@trucks_blueprint.get("/api/trucks/<int:truck_id>")
@login_required
def get_truck(truck_id):
    truck, error = get_owned_truck_or_error(truck_id, request.current_user["id"])
    if error:
        return error
    return json_response({"success": True, "truck": build_truck_payload(truck)})


@trucks_blueprint.get("/api/trucks/<int:truck_id>/configuration")
@login_required
def get_truck_configuration(truck_id):
    truck, error = get_owned_truck_or_error(truck_id, request.current_user["id"])
    if error:
        return error
    return json_response({"success": True, "configuration": build_configuration_payload(truck)})


@trucks_blueprint.put("/api/trucks/<int:truck_id>/configuration")
@login_required
def update_truck_configuration(truck_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)
    truck, error = get_owned_truck_or_error(truck_id, request.current_user["id"])
    if error:
        return error

    form = request.form
    truck_number = (form.get("truck_number") or "").strip()
    truck_type = (form.get("truck_type") or "").strip()
    catalog_type_key = (form.get("catalog_type_key") or "").strip()
    max_capacity_raw = (form.get("max_capacity") or "").strip()
    chassis_number = (form.get("chassis_number") or "").strip()
    operating_provinces_raw = (form.get("operating_provinces") or "").strip()
    per_km_rate_raw = (form.get("per_km_rate") or "").strip()
    waiting_charge_raw = (form.get("waiting_charge_per_hour") or "").strip()
    loading_charge_raw = (form.get("loading_charge") or "").strip()

    if not truck_number:
        return json_response({"success": False, "message": "Truck number is required."}, 400)
    if not truck_type and not catalog_type_key:
        return json_response({"success": False, "message": "Truck type is required."}, 400)
    if not max_capacity_raw:
        return json_response({"success": False, "message": "Truck capacity is required."}, 400)
    if not chassis_number:
        return json_response({"success": False, "message": "Chassis number is required."}, 400)
    if not operating_provinces_raw:
        return json_response({"success": False, "message": "At least one operating province is required."}, 400)
    if not per_km_rate_raw:
        return json_response({"success": False, "message": "Per KM rate is required."}, 400)
    if not waiting_charge_raw:
        return json_response({"success": False, "message": "Waiting charge per hour is required."}, 400)

    try:
        max_capacity = float(max_capacity_raw)
        per_km_rate = float(per_km_rate_raw)
        waiting_charge_per_hour = float(waiting_charge_raw)
        loading_charge = float(loading_charge_raw) if loading_charge_raw else None
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Numeric fields contain invalid values."}, 400)

    if max_capacity <= 0:
        return json_response({"success": False, "message": "Truck capacity must be greater than 0."}, 400)
    if per_km_rate <= 0:
        return json_response({"success": False, "message": "Per KM rate must be greater than 0."}, 400)
    if waiting_charge_per_hour <= 0:
        return json_response({"success": False, "message": "Waiting charge per hour must be greater than 0."}, 400)
    if loading_charge is not None and loading_charge < 0:
        return json_response({"success": False, "message": "Loading charge cannot be negative."}, 400)
    if not 11 <= len(chassis_number) <= 17:
        return json_response({"success": False, "message": "Chassis number must be 11 to 17 characters."}, 400)

    operating_provinces = ",".join([item.strip() for item in operating_provinces_raw.split(",") if item.strip()])
    if not operating_provinces:
        return json_response({"success": False, "message": "At least one operating province is required."}, 400)

    truck_photo_path = truck.get("truck_photo_path")
    insurance_photo_path = truck.get("insurance_photo_path")
    rc_book_photo_path = truck.get("rc_book_photo_path")
    if request.files.get("truck_photo") and request.files["truck_photo"].filename:
        truck_photo_path = make_upload_relative_path(truck_id, request.files["truck_photo"])
    if request.files.get("insurance_photo") and request.files["insurance_photo"].filename:
        insurance_photo_path = make_upload_relative_path(truck_id, request.files["insurance_photo"])
    if request.files.get("rc_book_photo") and request.files["rc_book_photo"].filename:
        rc_book_photo_path = make_upload_relative_path(truck_id, request.files["rc_book_photo"])

    status_reason_code = truck.get("status_reason_code") or ""
    status_reason = truck.get("status_reason") or ""
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute(
            """
            UPDATE trucks
            SET truck_number = ?, truck_type = ?, catalog_type_key = ?, chassis_number = ?,
                capacity_tons = ?, operating_provinces = ?, body_style = ?, payload_min_kg = ?, payload_max_kg = ?,
                volume_min_cbm = ?, volume_max_cbm = ?, catalog_specs_json = ?, tracking_id = ?, driver_name = ?,
                driver_cnic = ?, per_km_rate = ?, waiting_charge_per_hour = ?, loading_charge = ?,
                refrigeration_supported = ?, hazardous_supported = ?, fragile_supported = ?,
                truck_photo_path = ?, insurance_photo_path = ?, rc_book_photo_path = ?,
                updated_at = ?, status_reason_code = ?, status_reason = ?
            WHERE id = ? AND owner_user_id = ?
            """,
            (
                truck_number,
                truck_type or (get_catalog_type(catalog_type_key) or {}).get("display_name") or truck.get("truck_type"),
                parse_optional_text(catalog_type_key),
                chassis_number,
                max_capacity,
                operating_provinces,
                parse_optional_text(form.get("body_style")),
                parse_optional_float(form.get("payload_min_kg")),
                parse_optional_float(form.get("payload_max_kg")),
                parse_optional_float(form.get("volume_min_cbm")),
                parse_optional_float(form.get("volume_max_cbm")),
                parse_optional_text(form.get("catalog_specs_json")),
                parse_optional_text(form.get("tracking_id")),
                parse_optional_text(form.get("driver_name")),
                parse_optional_cnic(form.get("driver_cnic")),
                per_km_rate,
                waiting_charge_per_hour,
                loading_charge,
                parse_bool_flag(form.get("refrigeration_supported")),
                parse_bool_flag(form.get("hazardous_supported")),
                parse_bool_flag(form.get("fragile_supported")),
                truck_photo_path,
                insurance_photo_path,
                rc_book_photo_path,
                stamp["display"],
                status_reason_code,
                status_reason,
                truck_id,
                request.current_user["id"],
            ),
        )
        db.commit()
        updated = db.execute("SELECT * FROM trucks WHERE id = ? AND owner_user_id = ?", (truck_id, request.current_user["id"])).fetchone()

    return json_response({"success": True, "truck": build_configuration_payload(dict(updated))})


@trucks_blueprint.put("/api/trucks/<int:truck_id>/status")
@login_required
def update_truck_status(truck_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)
    truck, error = get_owned_truck_or_error(truck_id, request.current_user["id"])
    if error:
        return error

    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    reason_code = (data.get("reason_code") or "").strip()
    if status not in STATUS_OPTIONS:
        return json_response({"success": False, "message": "Invalid truck status."}, 400)

    required_for_active = [
        truck.get("truck_number"),
        truck.get("truck_type"),
        truck.get("capacity_tons"),
        truck.get("chassis_number"),
        truck.get("operating_provinces"),
        truck.get("per_km_rate"),
        truck.get("waiting_charge_per_hour"),
    ]
    if status == "active":
        if any(value in (None, "", []) for value in required_for_active):
            return json_response({"success": False, "message": "Configuration incomplete, cannot activate"}, 400)
        status_reason_code = ""
        status_reason = ""
    else:
        if not reason_code or reason_code not in STATUS_REASON_LABELS:
            return json_response({"success": False, "message": "A valid reason is required for non-active truck status."}, 400)
        status_reason_code = reason_code
        status_reason = get_status_reason_label(reason_code)

    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute(
            """
            UPDATE trucks
            SET status = ?, status_reason_code = ?, status_reason = ?, updated_at = ?
            WHERE id = ? AND owner_user_id = ?
            """,
            (status, status_reason_code, status_reason, stamp["display"], truck_id, request.current_user["id"]),
        )
        db.commit()
        updated = db.execute("SELECT * FROM trucks WHERE id = ? AND owner_user_id = ?", (truck_id, request.current_user["id"])).fetchone()

    return json_response({"success": True, "truck": build_configuration_payload(dict(updated))})
