import json

from auth.helpers import normalize_cnic


TRUCK_TYPES = [
    { "type_key": "mini_pickup", "display_name": "Mini pickup", "common_uses": ["Last-mile retail supply", "Cartons"], "payload_min_kg": 500, "payload_max_kg": 700, "volume_min_cbm": 2, "volume_max_cbm": 3, "typical_body_style": "Low-side deck", "class_segment": "Small urban cargo" },
    { "type_key": "one_ton_pickup", "display_name": "One-ton pickup", "common_uses": ["Field deliveries", "Agri-inputs"], "payload_min_kg": 900, "payload_max_kg": 1300, "volume_min_cbm": 3, "volume_max_cbm": 5, "typical_body_style": "Open bed", "class_segment": "Small urban cargo" },
    { "type_key": "cargo_van_panel_van", "display_name": "Cargo van / panel van", "common_uses": ["Parcel movement", "Pharmacy stock"], "payload_min_kg": 400, "payload_max_kg": 800, "volume_min_cbm": 2.5, "volume_max_cbm": 4.5, "typical_body_style": "Closed metal van", "class_segment": "Small enclosed cargo" },
    { "type_key": "mini_truck_high_deck_mini_truck", "display_name": "Mini truck / high-deck mini truck", "common_uses": ["City cargo", "Market supply"], "payload_min_kg": 1000, "payload_max_kg": 2000, "volume_min_cbm": 5, "volume_max_cbm": 10, "typical_body_style": "High deck / open bed", "class_segment": "Light rigid truck" },
    { "type_key": "light_truck_2_3_5_ton", "display_name": "Light truck 2-3.5 ton", "common_uses": ["Branch replenishment", "Consumer goods"], "payload_min_kg": 2000, "payload_max_kg": 3500, "volume_min_cbm": 10, "volume_max_cbm": 18, "typical_body_style": "Open bed / dry box", "class_segment": "Light rigid truck" },
    { "type_key": "light_truck_3_5_5_ton", "display_name": "Light truck 3.5-5 ton", "common_uses": ["Retail distribution", "Packaging"], "payload_min_kg": 3500, "payload_max_kg": 5000, "volume_min_cbm": 15, "volume_max_cbm": 24, "typical_body_style": "Open bed / dry box", "class_segment": "Light rigid truck" },
    { "type_key": "medium_rigid_truck_5_9_ton", "display_name": "Medium rigid truck 5-9 ton", "common_uses": ["General cargo", "Textile"], "payload_min_kg": 5000, "payload_max_kg": 9000, "volume_min_cbm": 20, "volume_max_cbm": 36, "typical_body_style": "Rigid cargo body", "class_segment": "Medium rigid truck" },
    { "type_key": "heavy_rigid_truck_9_15_ton", "display_name": "Heavy rigid truck 9-15 ton", "common_uses": ["Long-route cargo", "Industrial goods"], "payload_min_kg": 9000, "payload_max_kg": 15000, "volume_min_cbm": 30, "volume_max_cbm": 55, "typical_body_style": "Rigid cargo body", "class_segment": "Heavy rigid truck" },
    { "type_key": "heavy_rigid_truck_15_25_ton", "display_name": "Heavy rigid truck 15-25 ton", "common_uses": ["Heavy cargo", "Bulk industrial loads"], "payload_min_kg": 15000, "payload_max_kg": 25000, "volume_min_cbm": 40, "volume_max_cbm": 70, "typical_body_style": "Rigid cargo body", "class_segment": "Heavy rigid truck" },
    { "type_key": "flatbed_trailer_open_semi_trailer", "display_name": "Flatbed trailer / open semi-trailer", "common_uses": ["Steel", "Machinery"], "payload_min_kg": 20000, "payload_max_kg": 45000, "volume_min_cbm": 0, "volume_max_cbm": 0, "typical_body_style": "Open flatbed", "class_segment": "Trailer-based heavy transport" },
    { "type_key": "container_carrier_skeletal_trailer", "display_name": "Container carrier / skeletal trailer", "common_uses": ["Container transport"], "payload_min_kg": 20000, "payload_max_kg": 30000, "volume_min_cbm": 0, "volume_max_cbm": 0, "typical_body_style": "Skeletal semi-trailer", "class_segment": "Trailer-based heavy transport" },
    { "type_key": "low_bed_low_loader_trailer", "display_name": "Low-bed / low-loader trailer", "common_uses": ["Heavy machinery", "Oversized loads"], "payload_min_kg": 25000, "payload_max_kg": 60000, "volume_min_cbm": 0, "volume_max_cbm": 0, "typical_body_style": "Low-bed trailer", "class_segment": "Trailer-based heavy transport" },
    { "type_key": "fuel_oil_tanker", "display_name": "Fuel / oil tanker", "common_uses": ["Petrol", "Diesel", "Furnace oil"], "payload_min_kg": 8000, "payload_max_kg": 35000, "volume_min_cbm": 10, "volume_max_cbm": 45, "typical_body_style": "Tanker", "class_segment": "Tanker vehicle" },
    { "type_key": "milk_tanker", "display_name": "Milk tanker", "common_uses": ["Raw milk", "Dairy liquids"], "payload_min_kg": 5000, "payload_max_kg": 28000, "volume_min_cbm": 6, "volume_max_cbm": 30, "typical_body_style": "Food-grade tanker", "class_segment": "Tanker vehicle" },
    { "type_key": "chemical_tanker", "display_name": "Chemical tanker", "common_uses": ["Industrial chemicals"], "payload_min_kg": 8000, "payload_max_kg": 32000, "volume_min_cbm": 10, "volume_max_cbm": 40, "typical_body_style": "Chemical tanker", "class_segment": "Tanker vehicle" },
    { "type_key": "refrigerated_rigid_truck", "display_name": "Refrigerated rigid truck", "common_uses": ["Frozen food", "Pharma", "Fresh produce"], "payload_min_kg": 1000, "payload_max_kg": 12000, "volume_min_cbm": 6, "volume_max_cbm": 40, "typical_body_style": "Insulated reefer body", "class_segment": "Cold-chain vehicle" },
    { "type_key": "reefer_trailer_reefer_container_carrier", "display_name": "Reefer trailer / reefer container carrier", "common_uses": ["Frozen exports", "Cold-chain bulk"], "payload_min_kg": 12000, "payload_max_kg": 28000, "volume_min_cbm": 40, "volume_max_cbm": 75, "typical_body_style": "Reefer trailer", "class_segment": "Cold-chain vehicle" },
    { "type_key": "insulated_or_dry_box_truck", "display_name": "Insulated or dry box truck", "common_uses": ["Sensitive packaged goods", "Dry groceries"], "payload_min_kg": 1000, "payload_max_kg": 12000, "volume_min_cbm": 8, "volume_max_cbm": 45, "typical_body_style": "Closed box body", "class_segment": "Enclosed cargo" },
    { "type_key": "dump_truck_tipper", "display_name": "Dump truck / tipper", "common_uses": ["Sand", "Gravel", "Construction materials"], "payload_min_kg": 5000, "payload_max_kg": 25000, "volume_min_cbm": 4, "volume_max_cbm": 16, "typical_body_style": "Tipper body", "class_segment": "Construction and bulk haulage" },
    { "type_key": "bulk_cement_tanker_powder_bulker", "display_name": "Bulk cement tanker / powder bulker", "common_uses": ["Bulk cement", "Fly ash"], "payload_min_kg": 15000, "payload_max_kg": 35000, "volume_min_cbm": 18, "volume_max_cbm": 45, "typical_body_style": "Pneumatic dry bulk tanker", "class_segment": "Construction and bulk haulage" },
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
        "truck_type": row["truck_type"],
        "catalog_type_key": row["catalog_type_key"],
        "chassis_number": row["chassis_number"],
        "capacity_tons": row["capacity_tons"],
        "main_use": row["main_use"],
        "payload_min_kg": row["payload_min_kg"],
        "payload_max_kg": row["payload_max_kg"],
        "volume_min_cbm": row["volume_min_cbm"],
        "volume_max_cbm": row["volume_max_cbm"],
        "body_style": row["body_style"],
        "catalog_specs_json": catalog_specs,
        "driver_name": row["driver_name"],
        "driver_cnic": row["driver_cnic"],
        "tracking_id": row["tracking_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

