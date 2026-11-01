"""
Goods taxonomy - SINGLE SOURCE OF TRUTH (backend).

Two-level classification:  State (category) -> Commodity.
Each commodity maps to:
  - the physical form (packaged / bulk / none)
  - the measurement fields the client must provide
  - the truck catalog type_keys that can legally carry it (smart matching)
  - handling flags (refrigerated / hazardous / food_grade)

The frontend mirror lives in frontend-react/src/lib/goodsTaxonomy.js and MUST
stay in sync with this file. Truck type_keys come from trucks/helpers.py.
"""

# Field ids the form / backend understands.
# weight is always required. Others depend on the commodity.
FIELD_DIMENSIONS = "dimensions"      # length_cm, width_cm, height_cm
FIELD_WEIGHT = "weight"              # goods_weight_tons
FIELD_VOLUME_CBM = "volume_cbm"      # goods_volume_cbm
FIELD_VOLUME_LITERS = "volume_liters"
FIELD_QUANTITY = "quantity"
FIELD_ANIMAL_COUNT = "animal_count"
FIELD_TEMPERATURE = "temperature"    # temperature_c

CATEGORY_SOLID = "solid"
CATEGORY_LIQUID = "liquid"
CATEGORY_GAS = "gas"
CATEGORY_LIVESTOCK = "livestock"

# Base field sets per category / form.
_BASE_FIELDS = {
    ("solid", "packaged"): [FIELD_DIMENSIONS, FIELD_WEIGHT, FIELD_QUANTITY],
    ("solid", "bulk"): [FIELD_WEIGHT, FIELD_VOLUME_CBM],
    ("liquid", None): [FIELD_VOLUME_LITERS, FIELD_WEIGHT],
    ("gas", None): [FIELD_WEIGHT, FIELD_VOLUME_CBM],
    ("livestock", None): [FIELD_ANIMAL_COUNT, FIELD_WEIGHT],
}

# Fields that are strictly required (others are optional inputs).
_REQUIRED_FIELDS = {
    ("solid", "packaged"): [FIELD_DIMENSIONS, FIELD_WEIGHT],
    ("solid", "bulk"): [FIELD_WEIGHT],
    ("liquid", None): [FIELD_VOLUME_LITERS],
    ("gas", None): [FIELD_WEIGHT],
    ("livestock", None): [FIELD_ANIMAL_COUNT],
}


def _fields(category, form, extra=None):
    base = list(_BASE_FIELDS.get((category, form), [FIELD_WEIGHT]))
    for f in (extra or []):
        if f not in base:
            base.append(f)
    return base


# commodity_key -> definition
GOODS_TAXONOMY = {
    # ---------------- SOLID / PACKAGED ----------------
    "general_cargo": {
        "label": "General / mixed cargo",
        "category": CATEGORY_SOLID, "form": "packaged",
        "trucks": [
            "mini_pickup", "light_truck_2_3_5_ton", "light_truck_3_5_5_ton",
            "medium_rigid_truck_5_9_ton", "heavy_rigid_truck_9_15_ton",
            "heavy_rigid_truck_15_25_ton", "container_carrier_skeletal_trailer",
            "insulated_or_dry_box_truck",
        ],
        "flags": {},
    },
    "cotton_textiles": {
        "label": "Cotton / textiles / bales",
        "category": CATEGORY_SOLID, "form": "packaged",
        "trucks": [
            "medium_rigid_truck_5_9_ton", "heavy_rigid_truck_9_15_ton",
            "heavy_rigid_truck_15_25_ton", "flatbed_trailer_open_semi_trailer",
            "container_carrier_skeletal_trailer",
        ],
        "flags": {},
    },
    "machinery": {
        "label": "Machinery / heavy equipment",
        "category": CATEGORY_SOLID, "form": "packaged",
        "trucks": [
            "flatbed_trailer_open_semi_trailer", "low_bed_low_loader_trailer",
            "heavy_rigid_truck_15_25_ton", "container_carrier_skeletal_trailer",
        ],
        "flags": {},
    },
    "electronics": {
        "label": "Electronics / appliances",
        "category": CATEGORY_SOLID, "form": "packaged",
        "trucks": [
            "insulated_or_dry_box_truck", "container_carrier_skeletal_trailer",
            "light_truck_3_5_5_ton", "medium_rigid_truck_5_9_ton",
        ],
        "flags": {},
    },
    "furniture": {
        "label": "Furniture / household goods",
        "category": CATEGORY_SOLID, "form": "packaged",
        "trucks": [
            "insulated_or_dry_box_truck", "container_carrier_skeletal_trailer",
            "light_truck_2_3_5_ton", "light_truck_3_5_5_ton",
            "medium_rigid_truck_5_9_ton",
        ],
        "flags": {},
    },
    "frozen_food": {
        "label": "Frozen / chilled food (meat, dairy, ice cream)",
        "category": CATEGORY_SOLID, "form": "packaged",
        "trucks": ["refrigerated_rigid_truck", "reefer_trailer_reefer_container_carrier"],
        "flags": {"refrigerated": True},
        "extra_fields": [FIELD_TEMPERATURE],
    },
    "fruits_vegetables": {
        "label": "Fruits / vegetables (perishable)",
        "category": CATEGORY_SOLID, "form": "packaged",
        "trucks": [
            "refrigerated_rigid_truck", "reefer_trailer_reefer_container_carrier",
            "insulated_or_dry_box_truck",
        ],
        "flags": {"refrigerated": True},
        "extra_fields": [FIELD_TEMPERATURE],
    },
    "pharmaceuticals": {
        "label": "Pharmaceuticals (temperature-controlled)",
        "category": CATEGORY_SOLID, "form": "packaged",
        "trucks": ["refrigerated_rigid_truck", "insulated_or_dry_box_truck"],
        "flags": {"refrigerated": True},
        "extra_fields": [FIELD_TEMPERATURE],
    },

    # ---------------- SOLID / BULK ----------------
    "cement": {
        "label": "Cement (bulk / powder)",
        "category": CATEGORY_SOLID, "form": "bulk",
        "trucks": ["bulk_cement_tanker_powder_bulker"],
        "flags": {},
    },
    "sand_gravel": {
        "label": "Sand / gravel / aggregate",
        "category": CATEGORY_SOLID, "form": "bulk",
        "trucks": ["dump_truck_tipper"],
        "flags": {},
    },
    "grain": {
        "label": "Grain / wheat / rice (bulk)",
        "category": CATEGORY_SOLID, "form": "bulk",
        "trucks": ["dump_truck_tipper", "bulk_cement_tanker_powder_bulker"],
        "flags": {},
    },
    "coal_minerals": {
        "label": "Coal / minerals / ore",
        "category": CATEGORY_SOLID, "form": "bulk",
        "trucks": ["dump_truck_tipper"],
        "flags": {},
    },
    "waste": {
        "label": "Garbage / construction waste",
        "category": CATEGORY_SOLID, "form": "bulk",
        "trucks": ["dump_truck_tipper"],
        "flags": {},
    },

    # ---------------- LIQUID ----------------
    "milk": {
        "label": "Milk / dairy liquid",
        "category": CATEGORY_LIQUID, "form": None,
        "trucks": ["milk_tanker"],
        "flags": {"food_grade": True, "refrigerated": True},
        "extra_fields": [FIELD_TEMPERATURE],
    },
    "water": {
        "label": "Water (potable)",
        "category": CATEGORY_LIQUID, "form": None,
        "trucks": ["milk_tanker"],
        "flags": {"food_grade": True},
    },
    "fuel": {
        "label": "Petrol / diesel / fuel",
        "category": CATEGORY_LIQUID, "form": None,
        "trucks": ["fuel_oil_tanker"],
        "flags": {"hazardous": True},
    },
    "edible_oil": {
        "label": "Edible / cooking oil",
        "category": CATEGORY_LIQUID, "form": None,
        "trucks": ["fuel_oil_tanker"],
        "flags": {"food_grade": True},
    },
    "chemicals_liquid": {
        "label": "Chemicals / industrial liquid",
        "category": CATEGORY_LIQUID, "form": None,
        "trucks": ["chemical_tanker"],
        "flags": {"hazardous": True},
    },

    # ---------------- GAS ----------------
    "lpg_cng": {
        "label": "LPG / CNG / industrial gas",
        "category": CATEGORY_GAS, "form": None,
        "trucks": ["chemical_tanker"],
        "flags": {"hazardous": True},
    },

    # ---------------- LIVESTOCK ----------------
    "livestock": {
        "label": "Livestock (cattle, goats, sheep, poultry)",
        "category": CATEGORY_LIVESTOCK, "form": None,
        "trucks": ["livestock_carrier"],
        "flags": {},
    },
}


def get_commodity(commodity_key):
    """Return the taxonomy entry for a commodity key, or None."""
    return GOODS_TAXONOMY.get((commodity_key or "").strip())


def commodity_fields(commodity_key):
    """List of field ids the client should provide for this commodity."""
    entry = get_commodity(commodity_key)
    if not entry:
        return [FIELD_WEIGHT]
    return _fields(entry["category"], entry.get("form"), entry.get("extra_fields"))


def required_fields(commodity_key):
    """Strictly required field ids for this commodity."""
    entry = get_commodity(commodity_key)
    if not entry:
        return [FIELD_WEIGHT]
    reqs = list(_REQUIRED_FIELDS.get((entry["category"], entry.get("form")), [FIELD_WEIGHT]))
    if FIELD_WEIGHT not in reqs and entry["category"] != CATEGORY_LIQUID:
        reqs.append(FIELD_WEIGHT)
    return reqs


def required_truck_types(commodity_key):
    """Allowed truck catalog type_keys for this commodity."""
    entry = get_commodity(commodity_key)
    return list(entry["trucks"]) if entry else []


def commodity_flags(commodity_key):
    entry = get_commodity(commodity_key)
    flags = {"refrigerated": False, "hazardous": False, "food_grade": False}
    if entry:
        flags.update(entry.get("flags", {}))
    return flags


def build_category_tree():
    """
    Nested structure for UI cascading selects:
    [{key, label, forms?[{key,label,commodities[]}], commodities?[]}]
    Kept here so the shape is documented; the frontend has its own copy.
    """
    return _CATEGORY_TREE


_CATEGORY_LABELS = {
    CATEGORY_SOLID: "Solid",
    CATEGORY_LIQUID: "Liquid",
    CATEGORY_GAS: "Gas",
    CATEGORY_LIVESTOCK: "Livestock",
}
_FORM_LABELS = {"packaged": "Packaged / unit", "bulk": "Bulk / loose"}


def _build_tree():
    tree = {}
    for key, entry in GOODS_TAXONOMY.items():
        cat = entry["category"]
        cat_node = tree.setdefault(cat, {"key": cat, "label": _CATEGORY_LABELS[cat], "forms": {}, "commodities": []})
        item = {"key": key, "label": entry["label"]}
        form = entry.get("form")
        if form:
            fnode = cat_node["forms"].setdefault(form, {"key": form, "label": _FORM_LABELS.get(form, form), "commodities": []})
            fnode["commodities"].append(item)
        else:
            cat_node["commodities"].append(item)
    out = []
    for cat in (CATEGORY_SOLID, CATEGORY_LIQUID, CATEGORY_GAS, CATEGORY_LIVESTOCK):
        node = tree.get(cat)
        if not node:
            continue
        forms = list(node["forms"].values())
        out.append({"key": node["key"], "label": node["label"], "forms": forms, "commodities": node["commodities"]})
    return out


_CATEGORY_TREE = _build_tree()
