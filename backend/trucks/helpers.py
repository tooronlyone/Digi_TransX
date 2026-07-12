import json
import time
from pathlib import Path

from auth.helpers import normalize_cnic
from shared.db import BASE_DIR


UPLOADS_DIR = BASE_DIR / "backend" / "uploads" / "trucks"
STATUS_REASON_LABELS = {
    "assigned_job": "On job / assigned to job",
    "maintenance": "Maintenance",
    "driver_unavailable": "Driver unavailable",
    "route_hold": "Route hold",
    "documents_pending": "Documents pending",
    "owner_hold": "Owner hold",
    "fuel_or_loading": "Fuel/loading wait",
    "repair": "Repair required",
    "weather_delay": "Weather delay",
    "blocked_by_admin": "Blocked by admin",
}
STATUS_OPTIONS = {"active", "inactive", "on_job", "maintenance", "blocked"}


TRUCK_TYPES = [
    { "type_key": "mini_pickup", "display_name": "Mini pickup", "common_uses": ["Last-mile retail supply", "Cartons"], "payload_min_kg": 0.5, "payload_max_kg": 0.7, "volume_min_cbm": 2, "volume_max_cbm": 3, "typical_body_style": "Low-side deck", "class_segment": "Small urban cargo" },
    { "type_key": "light_truck_2_3_5_ton", "display_name": "Light truck 2-3.5 ton", "common_uses": ["Branch replenishment", "Consumer goods"], "payload_min_kg": 2, "payload_max_kg": 3.5, "volume_min_cbm": 10, "volume_max_cbm": 18, "typical_body_style": "Open bed / dry box", "class_segment": "Light rigid truck" },
    { "type_key": "light_truck_3_5_5_ton", "display_name": "Light truck 3.5-5 ton", "common_uses": ["Retail distribution", "Packaging"], "payload_min_kg": 3.5, "payload_max_kg": 5, "volume_min_cbm": 15, "volume_max_cbm": 24, "typical_body_style": "Open bed / dry box", "class_segment": "Light rigid truck" },
    { "type_key": "medium_rigid_truck_5_9_ton", "display_name": "Medium rigid truck 5-9 ton", "common_uses": ["General cargo", "Textile"], "payload_min_kg": 5, "payload_max_kg": 9, "volume_min_cbm": 20, "volume_max_cbm": 36, "typical_body_style": "Rigid cargo body", "class_segment": "Medium rigid truck" },
    { "type_key": "heavy_rigid_truck_9_15_ton", "display_name": "Heavy rigid truck 9-15 ton", "common_uses": ["Long-route cargo", "Industrial goods"], "payload_min_kg": 9, "payload_max_kg": 15, "volume_min_cbm": 30, "volume_max_cbm": 55, "typical_body_style": "Rigid cargo body", "class_segment": "Heavy rigid truck" },
    { "type_key": "heavy_rigid_truck_15_25_ton", "display_name": "Heavy rigid truck 15-25 ton", "common_uses": ["Heavy cargo", "Bulk industrial loads"], "payload_min_kg": 15, "payload_max_kg": 25, "volume_min_cbm": 40, "volume_max_cbm": 70, "typical_body_style": "Rigid cargo body", "class_segment": "Heavy rigid truck" },
    { "type_key": "flatbed_trailer_open_semi_trailer", "display_name": "Flatbed trailer / open semi-trailer", "common_uses": ["Steel", "Machinery"], "payload_min_kg": 20, "payload_max_kg": 45, "volume_min_cbm": 0, "volume_max_cbm": 0, "typical_body_style": "Open flatbed", "class_segment": "Trailer-based heavy transport" },
    { "type_key": "container_carrier_skeletal_trailer", "display_name": "Container carrier / skeletal trailer", "common_uses": ["Container transport"], "payload_min_kg": 20, "payload_max_kg": 30, "volume_min_cbm": 0, "volume_max_cbm": 0, "typical_body_style": "Skeletal semi-trailer", "class_segment": "Trailer-based heavy transport" },
    { "type_key": "low_bed_low_loader_trailer", "display_name": "Low-bed / low-loader trailer", "common_uses": ["Heavy machinery", "Oversized loads"], "payload_min_kg": 25, "payload_max_kg": 60, "volume_min_cbm": 0, "volume_max_cbm": 0, "typical_body_style": "Low-bed trailer", "class_segment": "Trailer-based heavy transport" },
    { "type_key": "fuel_oil_tanker", "display_name": "Fuel / oil tanker", "common_uses": ["Petrol", "Diesel", "Furnace oil"], "payload_min_kg": 8, "payload_max_kg": 35, "volume_min_cbm": 10, "volume_max_cbm": 45, "typical_body_style": "Tanker", "class_segment": "Tanker vehicle" },
    { "type_key": "milk_tanker", "display_name": "Milk tanker", "common_uses": ["Raw milk", "Dairy liquids"], "payload_min_kg": 5, "payload_max_kg": 28, "volume_min_cbm": 6, "volume_max_cbm": 30, "typical_body_style": "Food-grade tanker", "class_segment": "Tanker vehicle" },
    { "type_key": "chemical_tanker", "display_name": "Chemical tanker", "common_uses": ["Industrial chemicals"], "payload_min_kg": 8, "payload_max_kg": 32, "volume_min_cbm": 10, "volume_max_cbm": 40, "typical_body_style": "Chemical tanker", "class_segment": "Tanker vehicle" },
    { "type_key": "refrigerated_rigid_truck", "display_name": "Refrigerated rigid truck", "common_uses": ["Frozen food", "Pharma", "Fresh produce"], "payload_min_kg": 1, "payload_max_kg": 12, "volume_min_cbm": 6, "volume_max_cbm": 40, "typical_body_style": "Insulated reefer body", "class_segment": "Cold-chain vehicle" },
    { "type_key": "reefer_trailer_reefer_container_carrier", "display_name": "Reefer trailer / reefer container carrier", "common_uses": ["Frozen exports", "Cold-chain bulk"], "payload_min_kg": 12, "payload_max_kg": 28, "volume_min_cbm": 40, "volume_max_cbm": 75, "typical_body_style": "Reefer trailer", "class_segment": "Cold-chain vehicle" },
    { "type_key": "insulated_or_dry_box_truck", "display_name": "Insulated or dry box truck", "common_uses": ["Sensitive packaged goods", "Dry groceries"], "payload_min_kg": 1, "payload_max_kg": 12, "volume_min_cbm": 8, "volume_max_cbm": 45, "typical_body_style": "Closed box body", "class_segment": "Enclosed cargo" },
    { "type_key": "dump_truck_tipper", "display_name": "Dump truck / tipper", "common_uses": ["Sand", "Gravel", "Construction materials"], "payload_min_kg": 5, "payload_max_kg": 25, "volume_min_cbm": 4, "volume_max_cbm": 16, "typical_body_style": "Tipper body", "class_segment": "Construction and bulk haulage" },
    { "type_key": "bulk_cement_tanker_powder_bulker", "display_name": "Bulk cement tanker / powder bulker", "common_uses": ["Bulk cement", "Fly ash"], "payload_min_kg": 15, "payload_max_kg": 35, "volume_min_cbm": 18, "volume_max_cbm": 45, "typical_body_style": "Pneumatic dry bulk tanker", "class_segment": "Construction and bulk haulage" },
    { "type_key": "livestock_carrier", "display_name": "Livestock carrier", "common_uses": ["Livestock", "Poultry"], "payload_min_kg": 0, "payload_max_kg": 0, "volume_min_cbm": 0, "volume_max_cbm": 0, "typical_body_style": "Ventilated body", "class_segment": "Specialized cargo" },
]


def parse_optional_text(value):
    cleaned = (value or "").strip()
    return cleaned or None


def parse_optional_cnic(value):
    cleaned = normalize_cnic(value)
    return cleaned or None


def parse_optional_float(value):
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    return float(cleaned)


def get_catalog_type(type_key):
    for item in TRUCK_TYPES:
        if item["type_key"] == type_key:
            return item
    return None


def get_catalog_fields(type_key):
    catalog = get_catalog_type(type_key)
    if not catalog:
        return []
    fields = []
    for key, label in (
        ("display_name", "Truck type"),
        ("class_segment", "Class segment"),
        ("typical_body_style", "Typical body style"),
        ("payload_min_kg", "Weight min (tons)"),
        ("payload_max_kg", "Weight max (tons)"),
        ("volume_min_cbm", "Volume min (cbm)"),
        ("volume_max_cbm", "Volume max (cbm)"),
    ):
        if catalog.get(key) not in (None, ""):
            fields.append({"field_key": key, "field_label": label, "value": catalog.get(key)})
    return fields


def build_truck_payload(row):
    catalog_specs = row["catalog_specs_json"]
    try:
        catalog_specs = json.loads(catalog_specs) if catalog_specs else None
    except json.JSONDecodeError:
        catalog_specs = None

    return {
        "id": row["id"],
        "owner_user_id": row["owner_user_id"],
        "truck_number": row["truck_number"],
        "truck_company": row["truck_company"],
        "truck_model": row["truck_model"],
        "truck_type": row["truck_type"],
        "catalog_type_key": row["catalog_type_key"],
        "chassis_number": row["chassis_number"],
        "capacity_tons": row["capacity_tons"],
        "max_capacity": row["capacity_tons"],
        "main_use": row["main_use"],
        "payload_min_kg": row["payload_min_kg"],
        "payload_min_tons": row["payload_min_kg"],
        "payload_max_kg": row["payload_max_kg"],
        "payload_max_tons": row["payload_max_kg"],
        "volume_min_cbm": row["volume_min_cbm"],
        "volume_max_cbm": row["volume_max_cbm"],
        "body_style": row["body_style"],
        "catalog_specs_json": catalog_specs,
        "driver_name": row["driver_name"],
        "driver_cnic": row["driver_cnic"],
        "tracking_id": row["tracking_id"],
        "operating_provinces": row["operating_provinces"],
        "refrigeration_supported": bool(row["refrigeration_supported"]),
        "hazardous_supported": bool(row["hazardous_supported"]),
        "fragile_supported": bool(row["fragile_supported"]),
        "truck_photo_path": row["truck_photo_path"],
        "insurance_photo_path": row["insurance_photo_path"],
        "rc_book_photo_path": row["rc_book_photo_path"],
        "photo": f"/{row['truck_photo_path']}" if row["truck_photo_path"] else "",
        "insurance_photo": f"/{row['insurance_photo_path']}" if row["insurance_photo_path"] else "",
        "rc_book_photo": f"/{row['rc_book_photo_path']}" if row["rc_book_photo_path"] else "",
        "status": row["status"],
        "status_reason_code": row.get("status_reason_code") if isinstance(row, dict) else row["status_reason_code"],
        "status_reason": row.get("status_reason") if isinstance(row, dict) else row["status_reason"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def build_configuration_payload(row):
    truck = build_truck_payload(row)
    operating_provinces = truck["operating_provinces"]
    if isinstance(operating_provinces, str):
        operating_provinces = [item.strip() for item in operating_provinces.split(",") if item.strip()]
    elif not operating_provinces:
        operating_provinces = []
    return {
        "truck_number": truck["truck_number"] or "",
        "truck_company": truck["truck_company"] or "",
        "truck_model": truck["truck_model"] or "",
        "truck_type": truck["truck_type"] or "",
        "catalog_type_key": truck["catalog_type_key"] or "",
        "max_capacity": truck["max_capacity"] or "",
        "chassis_number": truck["chassis_number"] or "",
        "operating_provinces": operating_provinces,
        "body_style": truck["body_style"] or "",
        "payload_min_kg": truck["payload_min_kg"] or "",
        "payload_min_tons": truck["payload_min_kg"] or "",
        "payload_max_kg": truck["payload_max_kg"] or "",
        "payload_max_tons": truck["payload_max_kg"] or "",
        "volume_min_cbm": truck["volume_min_cbm"] or "",
        "volume_max_cbm": truck["volume_max_cbm"] or "",
        "catalog_specs_json": truck["catalog_specs_json"] or "",
        "tracking_id": truck["tracking_id"] or "",
        "driver_name": truck["driver_name"] or "",
        "driver_cnic": truck["driver_cnic"] or "",
        "refrigeration_supported": bool(truck["refrigeration_supported"]),
        "hazardous_supported": bool(truck["hazardous_supported"]),
        "fragile_supported": bool(truck["fragile_supported"]),
        "photo": truck["photo"],
        "insurance_photo": truck["insurance_photo"],
        "rc_book_photo": truck["rc_book_photo"],
        "truck_photo_path": truck["truck_photo_path"] or "",
        "insurance_photo_path": truck["insurance_photo_path"] or "",
        "rc_book_photo_path": truck["rc_book_photo_path"] or "",
        "status": truck["status"] or "inactive",
        "status_reason_code": truck["status_reason_code"] or "",
        "status_reason": truck["status_reason"] or "",
    }


def parse_bool_flag(value):
    return 1 if str(value or "").strip() in {"1", "true", "True", "yes", "on"} else 0


def get_status_reason_label(reason_code):
    return STATUS_REASON_LABELS.get(reason_code or "", "")


def make_upload_relative_path(truck_id, file_storage):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    from werkzeug.utils import secure_filename

    original = secure_filename(file_storage.filename or "")
    filename = f"{truck_id}_{int(time.time())}_{original or 'upload.bin'}"
    destination = UPLOADS_DIR / filename
    file_storage.save(destination)
    return f"uploads/trucks/{filename}"
