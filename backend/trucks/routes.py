import json
import re

from flask import Blueprint, Response, request

from auth.helpers import json_response, login_required, csrf_error, timestamp_bundle
from shared.db import IntegrityError, open_db
from tracking.traccar import register_device
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
    normalize_truck_model,
    parse_bool_flag,
    parse_optional_cnic,
    parse_optional_float,
    parse_optional_text,
)


trucks_blueprint = Blueprint("trucks", __name__)
CHASSIS_NUMBER_REGEX = re.compile(r"^[A-HJ-NPR-Z0-9]{11,17}$")
CHASSIS_NUMBER_MESSAGE = (
    "Chassis number must be 11-17 characters, letters and numbers only, and cannot "
    "contain I, O, or Q (these are excluded in standard VIN format to avoid confusion "
    "with 1, 0, and 9)."
)


def get_owned_truck_or_error(truck_id, owner_user_id):
    with open_db() as db:
        row = db.execute("SELECT * FROM vehicles WHERE id = %s", (truck_id,)).fetchone()
    if not row:
        return None, json_response({"success": False, "message": "Truck not found."}, 404)
    truck = dict(row)
    if truck["owner_user_id"] != owner_user_id:
        return None, json_response({"success": False, "message": "You are not allowed to access this truck."}, 403)
    return truck, None


def normalize_chassis_number(value):
    return (value or "").strip().upper()


def is_valid_chassis_number(value):
    return bool(CHASSIS_NUMBER_REGEX.fullmatch(value or ""))


def normalize_catalog_specs_json(value, fallback=None):
    cleaned = parse_optional_text(value)
    if not cleaned:
        return None
    if cleaned == "[object Object]":
        return fallback
    try:
        json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError from exc
    return cleaned


@trucks_blueprint.get("/api/catalog/truck-types")
def truck_types_catalog():
    return json_response({"success": True, "truck_types": TRUCK_TYPES})


@trucks_blueprint.get("/api/catalog/truck-types/<string:type_key>/fields")
def truck_type_fields(type_key):
    return json_response({"success": True, "fields": get_catalog_fields(type_key)})


@trucks_blueprint.get("/uploads/trucks/<path:filename>")
def serve_truck_upload(filename):
    from shared.storage import download_bytes, guess_content_type

    data = download_bytes(f"uploads/trucks/{filename}")
    if data is None:
        return json_response({"success": False, "message": "File not found."}, 404)
    return Response(data, mimetype=guess_content_type(filename))


@trucks_blueprint.post("/api/trucks")
@login_required
def create_truck():
    err = csrf_error()
    if err:
        return err

    form = request.form
    truck_number = (form.get("truckNumber") or "").strip()
    truck_company = parse_optional_text(form.get("truckCompany") or form.get("truck_company"))
    truck_model = normalize_truck_model(truck_company, form.get("truckModel") or form.get("truck_model"))
    truck_type = (form.get("truckType") or form.get("truck_type") or "Truck").strip()
    chassis_number = normalize_chassis_number(form.get("chassisNumber"))
    capacity_raw = (form.get("capacity") or form.get("payload_max_tons") or "0").strip()
    main_use = (form.get("mainUse") or truck_type).strip()

    if not truck_number:
        return json_response({"success": False, "message": "Truck number is required."}, 400)
    if not chassis_number:
        return json_response({"success": False, "message": "Chassis number is required."}, 400)

    try:
        capacity = float(capacity_raw)
        payload_min_tons = parse_optional_float(form.get("payload_min_tons"))
        payload_max_tons = parse_optional_float(form.get("payload_max_tons"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Weight capacity must be a valid ton value."}, 400)

    if capacity < 0:
        return json_response({"success": False, "message": "Weight capacity cannot be negative."}, 400)
    if payload_min_tons is None or payload_max_tons is None:
        return json_response({"success": False, "message": "Weight capacity min and max are required in tons."}, 400)
    if payload_min_tons < 0 or payload_max_tons <= 0:
        return json_response({"success": False, "message": "Weight capacity must be greater than 0 tons."}, 400)
    if payload_min_tons > payload_max_tons:
        return json_response({"success": False, "message": "Weight capacity min cannot be greater than max."}, 400)
    capacity = payload_max_tons
    if not is_valid_chassis_number(chassis_number):
        return json_response({"success": False, "message": CHASSIS_NUMBER_MESSAGE}, 400)

    catalog_type_key = parse_optional_text(form.get("catalog_type_key"))
    body_style = parse_optional_text(form.get("body_style"))
    try:
        catalog_specs_raw = normalize_catalog_specs_json(form.get("catalog_specs_json"))
    except ValueError:
        return json_response({"success": False, "message": "Body type details format is invalid."}, 400)

    # Cargo-bed dimensions in feet (used to match long/wide/tall goods).
    try:
        bed_length_ft = parse_optional_float(form.get("bed_length_ft"))
        bed_width_ft = parse_optional_float(form.get("bed_width_ft"))
        bed_height_ft = parse_optional_float(form.get("bed_height_ft"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Cargo bed dimensions must be valid numbers (in feet)."}, 400)
    for dim in (bed_length_ft, bed_width_ft, bed_height_ft):
        if dim is not None and dim < 0:
            return json_response({"success": False, "message": "Cargo bed dimensions cannot be negative."}, 400)

    stamp = timestamp_bundle()
    with open_db() as db:
        existing_truck_number = db.execute(
            "SELECT id FROM vehicles WHERE lower(trim(truck_number)) = lower(trim(%s)) LIMIT 1",
            (truck_number,),
        ).fetchone()
        if existing_truck_number:
            return json_response({"success": False, "message": "This truck number is already registered in the system."}, 409)

        existing_chassis_number = db.execute(
            "SELECT id FROM vehicles WHERE lower(trim(chassis_number)) = lower(trim(%s)) LIMIT 1",
            (chassis_number,),
        ).fetchone()
        if existing_chassis_number:
            return json_response({"success": False, "message": "This chassis number is already registered in the system."}, 409)

        try:
            truck_id = db.execute(
                """
                INSERT INTO vehicles (
                    owner_user_id, truck_number, truck_company, truck_model, truck_type, catalog_type_key,
                    chassis_number, capacity_tons, main_use, payload_min_tons, payload_max_tons,
                    bed_length_ft, bed_width_ft, bed_height_ft,
                    body_style, catalog_specs_json, driver_name, driver_cnic, tracking_id,
                    status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'inactive', %s, %s)
                RETURNING id
                """,
                (
                    request.current_user["id"],
                    truck_number,
                    truck_company,
                    truck_model,
                    truck_type,
                    catalog_type_key,
                    chassis_number,
                    capacity,
                    main_use,
                    payload_min_tons,
                    payload_max_tons,
                    bed_length_ft,
                    bed_width_ft,
                    bed_height_ft,
                    body_style,
                    catalog_specs_raw,
                    parse_optional_text(form.get("driverName")),
                    parse_optional_cnic(form.get("driverCnic")),
                    parse_optional_text(form.get("trackingId")),
                    stamp["display"],
                    stamp["display"],
                ),
            ).fetchone()["id"]
            db.commit()
            try:
                imei = parse_optional_text(form.get("trackingId"))
                if imei is not None and imei.strip() != "":
                    gps_device_id = register_device(imei.strip(), truck_number)
                    if gps_device_id is not None:
                        db.execute(
                            "UPDATE vehicles SET traccar_device_id = %s WHERE id = %s",
                            (str(gps_device_id), truck_id),
                        )
                        db.commit()
            except Exception:
                pass
        except IntegrityError:
            db.rollback()
            duplicate_truck_number = db.execute(
                "SELECT id FROM vehicles WHERE lower(trim(truck_number)) = lower(trim(%s)) LIMIT 1",
                (truck_number,),
            ).fetchone()
            if duplicate_truck_number:
                return json_response({"success": False, "message": "This truck number is already registered in the system."}, 409)

            duplicate_chassis_number = db.execute(
                "SELECT id FROM vehicles WHERE lower(trim(chassis_number)) = lower(trim(%s)) LIMIT 1",
                (chassis_number,),
            ).fetchone()
            if duplicate_chassis_number:
                return json_response({"success": False, "message": "This chassis number is already registered in the system."}, 409)
            raise

    return json_response({"success": True, "message": "Truck registered successfully"})


@trucks_blueprint.get("/api/trucks")
@login_required
def list_trucks():
    with open_db() as db:
        rows = db.execute(
            """
            SELECT * FROM vehicles
            WHERE owner_user_id = %s
            ORDER BY id DESC
            """,
            (request.current_user["id"],),
        ).fetchall()

    return json_response({"success": True, "trucks": [build_truck_payload(dict(row)) for row in rows]})


@trucks_blueprint.get("/api/trucks/stats")
@login_required
def truck_stats():
    with open_db() as db:
        row = db.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS available,
                SUM(CASE WHEN status = 'on_job' THEN 1 ELSE 0 END) AS on_job,
                SUM(CASE WHEN status = 'maintenance' THEN 1 ELSE 0 END) AS maintenance,
                SUM(CASE WHEN status IN ('inactive', 'blocked') THEN 1 ELSE 0 END) AS inactive
            FROM vehicles
            WHERE owner_user_id = %s
            """,
            (request.current_user["id"],),
        ).fetchone()

    return json_response(
        {
            "success": True,
            "stats": {
                "total": int(row["total"] or 0),
                "available": int(row["available"] or 0),
                "onJob": int(row["on_job"] or 0),
                "maintenance": int(row["maintenance"] or 0),
                "inactive": int(row["inactive"] or 0),
            },
        }
    )


@trucks_blueprint.get("/api/trucks/<int:truck_id>")
@login_required
def get_truck(truck_id):
    truck, error = get_owned_truck_or_error(truck_id, request.current_user["id"])
    if error:
        return error
    return json_response({"success": True, "truck": build_truck_payload(truck)})


@trucks_blueprint.get("/api/trucks/<int:truck_id>/live-location")
@login_required
def truck_live_location(truck_id):
    from tracking.traccar import get_latest_position, GPS_PROVIDER_ENABLED
    truck, error = get_owned_truck_or_error(truck_id, request.current_user["id"])
    if error:
        return error

    traccar_device_id = truck.get("traccar_device_id")
    if not traccar_device_id:
        return json_response({
            "success": True,
            "gps_available": False,
            "reason": "no_device",
            "message": "No GPS device (IMEI) configured for this truck.",
        })

    if not GPS_PROVIDER_ENABLED:
        return json_response({
            "success": True,
            "gps_available": False,
            "reason": "provider_not_configured",
            "message": "GPS provider is not connected yet. Location will be available once a GPS provider is set up.",
        })

    try:
        position = get_latest_position(traccar_device_id)
    except Exception as exc:
        return json_response({
            "success": True,
            "gps_available": False,
            "reason": "fetch_error",
            "message": f"GPS fetch error: {exc}",
        })

    if not position:
        return json_response({
            "success": True,
            "gps_available": False,
            "reason": "no_data",
            "message": "GPS device has not sent any location data yet.",
        })

    return json_response({
        "success": True,
        "gps_available": True,
        "lat": position["lat"],
        "lon": position["lon"],
        "speed": position.get("speed"),
        "timestamp": position.get("timestamp"),
    })


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
    err = csrf_error()
    if err:
        return err
    truck, error = get_owned_truck_or_error(truck_id, request.current_user["id"])
    if error:
        return error

    form = request.form
    truck_number = (form.get("truck_number") or "").strip()
    truck_company = parse_optional_text(form.get("truck_company"))
    truck_model = normalize_truck_model(truck_company, form.get("truck_model"))
    truck_type = (form.get("truck_type") or "").strip()
    catalog_type_key = parse_optional_text(form.get("catalog_type_key"))
    body_style = parse_optional_text(form.get("body_style"))
    try:
        catalog_specs_raw = normalize_catalog_specs_json(form.get("catalog_specs_json"), fallback=truck.get("catalog_specs_json"))
    except ValueError:
        return json_response({"success": False, "message": "Body type details format is invalid."}, 400)
    try:
        bed_length_ft = parse_optional_float(form.get("bed_length_ft"))
        bed_width_ft = parse_optional_float(form.get("bed_width_ft"))
        bed_height_ft = parse_optional_float(form.get("bed_height_ft"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Cargo bed dimensions must be valid numbers (in feet)."}, 400)
    for dim in (bed_length_ft, bed_width_ft, bed_height_ft):
        if dim is not None and dim < 0:
            return json_response({"success": False, "message": "Cargo bed dimensions cannot be negative."}, 400)
    max_capacity_raw = (form.get("max_capacity") or "").strip()
    chassis_number = normalize_chassis_number(form.get("chassis_number"))
    operating_provinces_raw = (form.get("operating_provinces") or "").strip()

    if not truck_number:
        return json_response({"success": False, "message": "Truck number is required."}, 400)
    if not truck_company:
        return json_response({"success": False, "message": "Truck company is required."}, 400)
    if not truck_model:
        return json_response({"success": False, "message": "Truck model is required."}, 400)
    if not truck_type and not catalog_type_key:
        return json_response({"success": False, "message": "Truck type is required."}, 400)
    if not max_capacity_raw:
        return json_response({"success": False, "message": "Truck capacity is required."}, 400)
    if not chassis_number:
        return json_response({"success": False, "message": "Chassis number is required."}, 400)
    if not operating_provinces_raw:
        return json_response({"success": False, "message": "At least one operating province is required."}, 400)

    try:
        max_capacity = float(max_capacity_raw)
        payload_min_tons = parse_optional_float(form.get("payload_min_tons"))
        payload_max_tons = parse_optional_float(form.get("payload_max_tons"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Weight capacity must be a valid ton value."}, 400)

    if payload_min_tons is None or payload_max_tons is None:
        return json_response({"success": False, "message": "Weight capacity min and max are required in tons."}, 400)
    if payload_min_tons < 0 or payload_max_tons <= 0:
        return json_response({"success": False, "message": "Weight capacity must be greater than 0 tons."}, 400)
    if payload_min_tons > payload_max_tons:
        return json_response({"success": False, "message": "Weight capacity min cannot be greater than max."}, 400)
    max_capacity = payload_max_tons
    if not is_valid_chassis_number(chassis_number):
        return json_response({"success": False, "message": CHASSIS_NUMBER_MESSAGE}, 400)

    operating_provinces = ",".join([item.strip() for item in operating_provinces_raw.split(",") if item.strip()])
    if not operating_provinces:
        return json_response({"success": False, "message": "At least one operating province is required."}, 400)

    truck_photo_path = truck.get("truck_photo_path")
    insurance_photo_path = truck.get("insurance_photo_path")
    rc_book_photo_path = truck.get("rc_book_photo_path")
    new_documents = []
    if request.files.get("truck_photo") and request.files["truck_photo"].filename:
        truck_photo_path = make_upload_relative_path(truck_id, request.files["truck_photo"])
        new_documents.append((truck_photo_path, "vehicle_photo", request.files["truck_photo"]))
    if request.files.get("insurance_photo") and request.files["insurance_photo"].filename:
        insurance_photo_path = make_upload_relative_path(truck_id, request.files["insurance_photo"])
        new_documents.append((insurance_photo_path, "insurance", request.files["insurance_photo"]))
    if request.files.get("rc_book_photo") and request.files["rc_book_photo"].filename:
        rc_book_photo_path = make_upload_relative_path(truck_id, request.files["rc_book_photo"])
        new_documents.append((rc_book_photo_path, "rc_book", request.files["rc_book_photo"]))

    status_reason_code = truck.get("status_reason_code") or ""
    status_reason = truck.get("status_reason") or ""
    stamp = timestamp_bundle()
    with open_db() as db:
        db.execute(
            """
            UPDATE vehicles
            SET truck_number = %s, truck_company = %s, truck_model = %s, truck_type = %s, catalog_type_key = %s, chassis_number = %s,
                capacity_tons = %s, operating_provinces = %s, body_style = %s, payload_min_tons = %s, payload_max_tons = %s,
                bed_length_ft = %s, bed_width_ft = %s, bed_height_ft = %s,
                volume_min_cbm = %s, volume_max_cbm = %s, catalog_specs_json = %s, tracking_id = %s, driver_name = %s,
                driver_cnic = %s,
                refrigeration_supported = %s, hazardous_supported = %s, fragile_supported = %s,
                truck_photo_path = %s, insurance_photo_path = %s, rc_book_photo_path = %s,
                updated_at = %s, status_reason_code = %s, status_reason = %s
            WHERE id = %s AND owner_user_id = %s
            """,
            (
                truck_number,
                truck_company,
                truck_model,
                truck_type or (get_catalog_type(catalog_type_key) or {}).get("display_name") or truck.get("truck_type"),
                catalog_type_key,
                chassis_number,
                max_capacity,
                operating_provinces,
                parse_optional_text(form.get("body_style")),
                payload_min_tons,
                payload_max_tons,
                bed_length_ft,
                bed_width_ft,
                bed_height_ft,
                parse_optional_float(form.get("volume_min_cbm")),
                parse_optional_float(form.get("volume_max_cbm")),
                catalog_specs_raw,
                parse_optional_text(form.get("tracking_id")),
                parse_optional_text(form.get("driver_name")),
                parse_optional_cnic(form.get("driver_cnic")),
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
        from shared.storage import record_document

        for storage_path, doc_type, file_storage in new_documents:
            record_document(
                db,
                request.current_user["id"],
                storage_path,
                doc_type,
                vehicle_id=truck_id,
                file_name=file_storage.filename,
                mime_type=file_storage.mimetype,
            )
        db.commit()
        try:
            imei = parse_optional_text(form.get("tracking_id"))
            if imei is not None and imei.strip() != "":
                gps_device_id = register_device(imei.strip(), truck_number)
                if gps_device_id is not None:
                    db.execute(
                        "UPDATE vehicles SET traccar_device_id = %s WHERE id = %s",
                        (str(gps_device_id), truck_id),
                    )
                    db.commit()
        except Exception:
            pass
        updated = db.execute("SELECT * FROM vehicles WHERE id = %s AND owner_user_id = %s", (truck_id, request.current_user["id"])).fetchone()

    return json_response({"success": True, "truck": build_configuration_payload(dict(updated))})


@trucks_blueprint.put("/api/trucks/<int:truck_id>/status")
@login_required
def update_truck_status(truck_id):
    err = csrf_error()
    if err:
        return err
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
        truck.get("truck_company"),
        truck.get("truck_model"),
        truck.get("truck_type"),
        truck.get("capacity_tons"),
        truck.get("chassis_number"),
        truck.get("operating_provinces"),
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
            UPDATE vehicles
            SET status = %s, status_reason_code = %s, status_reason = %s, updated_at = %s
            WHERE id = %s AND owner_user_id = %s
            """,
            (status, status_reason_code, status_reason, stamp["display"], truck_id, request.current_user["id"]),
        )
        db.commit()
        updated = db.execute("SELECT * FROM vehicles WHERE id = %s AND owner_user_id = %s", (truck_id, request.current_user["id"])).fetchone()

    return json_response({"success": True, "truck": build_configuration_payload(dict(updated))})
