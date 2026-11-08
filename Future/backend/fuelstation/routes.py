from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, request

from auth.helpers import csrf_error, json_response, login_required, timestamp_bundle
from shared.db import open_db
from shared.validation import finite_decimal
from shared.payments import parse_positive_id

fuelstation_blueprint = Blueprint("fuelstation", __name__, url_prefix="/api/fuelstation")

# Register against the same protected portal blueprint; no competing app entry.
from fuelstation.vouchers import register_voucher_routes
register_voucher_routes(fuelstation_blueprint)

FUEL_TYPES = {
    "diesel": "High Speed Diesel (HSD)",
    "petrol": "Super Petrol (Euro 5)",
    "hi_octane": "Hi-Octane 97",
    "cng": "Compressed Natural Gas (CNG)",
    "adblue": "AdBlue / DEF Fluid",
}


def _pump_numbers(data, existing=None):
    existing = existing or {}
    price = finite_decimal(data.get("price_per_liter",existing.get("price_per_liter","280.00")),
                           "Price per liter",minimum=Decimal("0.01"),maximum=Decimal("99999999.99"),scale=2)
    capacity = finite_decimal(data.get("tank_capacity_liters",existing.get("tank_capacity_liters","25000.00")),
                              "Tank capacity",minimum=Decimal("0.01"),scale=2)
    stock = finite_decimal(data.get("current_stock_liters",existing.get("current_stock_liters",capacity)),
                           "Current stock",scale=2)
    if stock > capacity:
        raise ValueError("Current stock cannot exceed tank capacity.")
    return price,capacity,stock


def _fuel_station_only():
    role = str(request.current_user.get("role") or "").strip().lower()
    if role != "fuel_station_manager":
        return json_response({"success": False, "message": "Fuel station manager access is required."}, 403)
    return None


@fuelstation_blueprint.get("/dashboard")
@login_required
def fuel_dashboard():
    denied = _fuel_station_only()
    if denied:
        return denied

    user_id = request.current_user["id"]
    with open_db() as db:
        # Today's metrics
        today_stats = db.execute(
            """
            SELECT
                COALESCE(SUM(liters), 0) AS today_liters,
                COALESCE(SUM(total_pkr), 0) AS today_revenue,
                COUNT(*) AS today_transactions
            FROM fuel_station_dispenses
            WHERE user_id = %s AND created_at >= CURRENT_DATE
            """,
            (user_id,),
        ).fetchone()

        # All-time metrics
        all_stats = db.execute(
            """
            SELECT
                COALESCE(SUM(liters), 0) AS total_liters,
                COALESCE(SUM(total_pkr), 0) AS total_revenue,
                COUNT(*) AS total_transactions
            FROM fuel_station_dispenses
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()

        # Pumps count
        pumps_stats = db.execute(
            """
            SELECT
                COUNT(*) AS total_pumps,
                COUNT(CASE WHEN status = 'active' THEN 1 END) AS active_pumps
            FROM fuel_station_pumps
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()

        # Recent 5 dispenses
        recent_rows = db.execute(
            """
            SELECT d.*, p.pump_number
            FROM fuel_station_dispenses d
            LEFT JOIN fuel_station_pumps p ON d.pump_id = p.id
            WHERE d.user_id = %s
            ORDER BY d.id DESC
            LIMIT 5
            """,
            (user_id,),
        ).fetchall()

        # Pumps live rates
        pumps = db.execute(
            """
            SELECT id, pump_number, fuel_type, price_per_liter, status, tank_capacity_liters, current_stock_liters
            FROM fuel_station_pumps
            WHERE user_id = %s
            ORDER BY id ASC
            """,
            (user_id,),
        ).fetchall()

    recent_dispenses = [
        {
            "id": r["id"],
            "pump_id": r["pump_id"],
            "pump_number": r["pump_number"] or "Direct Dispenser",
            "vehicle_plate": r["vehicle_plate"],
            "driver_name": r["driver_name"] or "N/A",
            "driver_phone": r["driver_phone"] or "",
            "fuel_type": r["fuel_type"],
            "fuel_type_label": FUEL_TYPES.get(r["fuel_type"], r["fuel_type"]),
            "liters": float(r["liters"]),
            "price_per_liter": float(r["price_per_liter"]),
            "total_pkr": float(r["total_pkr"]),
            "payment_method": r["payment_method"],
            "created_at": r["created_at"],
        }
        for r in recent_rows
    ]

    pumps_list = [
        {
            "id": p["id"],
            "pump_number": p["pump_number"],
            "fuel_type": p["fuel_type"],
            "fuel_type_label": FUEL_TYPES.get(p["fuel_type"], p["fuel_type"]),
            "price_per_liter": float(p["price_per_liter"]),
            "status": p["status"],
            "tank_capacity_liters": float(p["tank_capacity_liters"]),
            "current_stock_liters": float(p["current_stock_liters"]),
        }
        for p in pumps
    ]

    return json_response({
        "success": True,
        "metrics": {
            "today_liters": float(today_stats["today_liters"]),
            "today_revenue": float(today_stats["today_revenue"]),
            "today_transactions": int(today_stats["today_transactions"]),
            "total_liters": float(all_stats["total_liters"]),
            "total_revenue": float(all_stats["total_revenue"]),
            "total_transactions": int(all_stats["total_transactions"]),
            "active_pumps": int(pumps_stats["active_pumps"]),
            "total_pumps": int(pumps_stats["total_pumps"]),
        },
        "recent_dispenses": recent_dispenses,
        "pumps": pumps_list,
    })


@fuelstation_blueprint.get("/pumps")
@login_required
def get_pumps():
    denied = _fuel_station_only()
    if denied:
        return denied

    user_id = request.current_user["id"]
    with open_db() as db:
        rows = db.execute(
            """
            SELECT id, pump_number, fuel_type, price_per_liter, status, tank_capacity_liters, current_stock_liters, created_at, updated_at
            FROM fuel_station_pumps
            WHERE user_id = %s
            ORDER BY id ASC
            """,
            (user_id,),
        ).fetchall()

    pumps = [
        {
            "id": r["id"],
            "pump_number": r["pump_number"],
            "fuel_type": r["fuel_type"],
            "fuel_type_label": FUEL_TYPES.get(r["fuel_type"], r["fuel_type"]),
            "price_per_liter": float(r["price_per_liter"]),
            "status": r["status"],
            "tank_capacity_liters": float(r["tank_capacity_liters"]),
            "current_stock_liters": float(r["current_stock_liters"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return json_response({"success": True, "pumps": pumps})


@fuelstation_blueprint.post("/pumps")
@login_required
def create_pump():
    denied = _fuel_station_only()
    if denied:
        return denied
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    pump_number = str(data.get("pump_number") or "").strip()
    fuel_type = str(data.get("fuel_type") or "diesel").strip().lower()

    if not pump_number:
        return json_response({"success": False, "message": "Pump number or bay name is required."}, 400)
    if fuel_type not in FUEL_TYPES:
        return json_response({"success": False, "message": "Please select a valid fuel type."}, 400)

    try:
        price,capacity,stock = _pump_numbers(data)
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    user_id = request.current_user["id"]
    stamp = timestamp_bundle()["display"]

    with open_db() as db:
        new_id = db.execute(
            """
            INSERT INTO fuel_station_pumps (
                user_id, pump_number, fuel_type, price_per_liter, status,
                tank_capacity_liters, current_stock_liters, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, pump_number, fuel_type, price, capacity, stock, stamp, stamp),
        ).fetchone()["id"]
        db.commit()

    return json_response({"success": True, "message": "Pump added successfully.", "pump_id": new_id})


@fuelstation_blueprint.put("/pumps/<int:pump_id>")
@login_required
def update_pump(pump_id):
    denied = _fuel_station_only()
    if denied:
        return denied
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    user_id = request.current_user["id"]

    with open_db() as db:
        existing = db.execute(
            "SELECT * FROM fuel_station_pumps WHERE id = %s AND user_id = %s FOR UPDATE",
            (pump_id, user_id),
        ).fetchone()
        if not existing:
            return json_response({"success": False, "message": "Pump not found."}, 404)

        pump_number = str(data.get("pump_number") or existing["pump_number"]).strip()
        fuel_type = str(data.get("fuel_type") or existing["fuel_type"]).strip().lower()
        status = str(data.get("status") or existing["status"]).strip().lower()

        if not pump_number or fuel_type not in FUEL_TYPES or status not in {"active","inactive","maintenance"}:
            return json_response({"success": False, "message": "Enter a pump number, valid fuel type and pump status."}, 400)
        try:
            price,capacity,stock = _pump_numbers(data,existing)
        except ValueError as exc:
            return json_response({"success": False, "message": str(exc)}, 400)

        stamp = timestamp_bundle()["display"]
        db.execute(
            """
            UPDATE fuel_station_pumps
            SET pump_number = %s, fuel_type = %s, price_per_liter = %s, status = %s,
                tank_capacity_liters = %s, current_stock_liters = %s, updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (pump_number, fuel_type, price, status, capacity, stock, stamp, pump_id, user_id),
        )
        db.commit()

    return json_response({"success": True, "message": "Pump updated successfully."})


@fuelstation_blueprint.post("/dispense")
@login_required
def record_dispense():
    denied = _fuel_station_only()
    if denied:
        return denied
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    vehicle_plate = str(data.get("vehicle_plate") or "").strip().upper()
    driver_name = str(data.get("driver_name") or "").strip()
    driver_phone = str(data.get("driver_phone") or "").strip()
    payment_method = str(data.get("payment_method") or "cash").strip().lower()
    notes = str(data.get("notes") or "").strip()
    pump_id = data.get("pump_id")

    if not vehicle_plate:
        return json_response({"success": False, "message": "Vehicle registration plate is required."}, 400)
    if payment_method not in {"cash","card"}:
        return json_response({"success": False, "message": "Record cash or payment collected at the station card terminal. Wallet/voucher settlement is not configured."}, 400)

    try:
        liters = finite_decimal(data.get("liters"),"Liters dispensed",minimum=Decimal("0.01"),
                                maximum=Decimal("99999999.99"),scale=2)
        pump_id = parse_positive_id(pump_id,"Pump ID")
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        pump = db.execute(
            "SELECT * FROM fuel_station_pumps WHERE id = %s AND user_id = %s FOR UPDATE",
            (pump_id, user_id),
        ).fetchone()
        if not pump:
            return json_response({"success": False, "message": "Selected pump not found."}, 404)
        if pump["status"] != "active" or pump["fuel_type"] not in FUEL_TYPES:
            return json_response({"success": False, "message": "Select an active pump before dispensing."}, 409)
        try:
            price_per_liter,_,stock = _pump_numbers({},pump)
            total_pkr = (liters * price_per_liter).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            finite_decimal(total_pkr,"Fuel sale total",scale=2)
        except ValueError as exc:
            return json_response({"success": False, "message": str(exc)}, 409)
        if liters > stock:
            return json_response({"success": False, "message": "The pump does not have enough fuel in stock."}, 409)
        fuel_type = pump["fuel_type"]
        stamp = timestamp_bundle()["display"]

        # Claim inventory before writing the receipt. The context rolls both
        # back if the INSERT fails; no clamping can hide an oversale.
        changed = db.execute(
            "UPDATE fuel_station_pumps SET current_stock_liters=current_stock_liters-%s,updated_at=%s "
            "WHERE id=%s AND user_id=%s AND status='active' AND current_stock_liters>=%s RETURNING id",
            (liters,stamp,pump_id,user_id,liters),
        ).fetchone()
        if not changed:
            return json_response({"success": False, "message": "Pump stock changed. Reload and try again."}, 409)

        # Insert dispense record
        dispense_id = db.execute(
            """
            INSERT INTO fuel_station_dispenses (
                user_id, pump_id, vehicle_plate, driver_name, driver_phone,
                fuel_type, liters, price_per_liter, total_pkr, payment_method, notes, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                pump_id or None,
                vehicle_plate,
                driver_name or None,
                driver_phone or None,
                fuel_type,
                liters,
                price_per_liter,
                total_pkr,
                payment_method,
                notes or None,
                stamp,
            ),
        ).fetchone()["id"]

        db.commit()

    return json_response({
        "success": True,
        "message": "Fuel dispensed and logged successfully.",
        "receipt": {
            "id": dispense_id,
            "vehicle_plate": vehicle_plate,
            "driver_name": driver_name or "N/A",
            "fuel_type": fuel_type,
            "fuel_type_label": FUEL_TYPES.get(fuel_type, fuel_type),
            "liters": float(liters),
            "price_per_liter": float(price_per_liter),
            "total_pkr": float(total_pkr),
            "payment_method": payment_method,
            "date": stamp,
        },
    })


@fuelstation_blueprint.get("/dispenses")
@login_required
def get_dispenses():
    denied = _fuel_station_only()
    if denied:
        return denied

    user_id = request.current_user["id"]
    fuel_filter = str(request.args.get("fuel_type") or "").strip().lower()
    search = str(request.args.get("search") or "").strip()

    sql = """
        SELECT d.*, p.pump_number
        FROM fuel_station_dispenses d
        LEFT JOIN fuel_station_pumps p ON d.pump_id = p.id
        WHERE d.user_id = %s
    """
    params = [user_id]

    if fuel_filter and fuel_filter in FUEL_TYPES:
        sql += " AND d.fuel_type = %s"
        params.append(fuel_filter)

    if search:
        sql += " AND (d.vehicle_plate ILIKE %s OR d.driver_name ILIKE %s OR d.driver_phone ILIKE %s)"
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    sql += " ORDER BY d.id DESC LIMIT 200"

    with open_db() as db:
        rows = db.execute(sql, tuple(params)).fetchall()

    dispenses = [
        {
            "id": r["id"],
            "pump_id": r["pump_id"],
            "pump_number": r["pump_number"] or "Bay Dispenser",
            "vehicle_plate": r["vehicle_plate"],
            "driver_name": r["driver_name"] or "N/A",
            "driver_phone": r["driver_phone"] or "",
            "fuel_type": r["fuel_type"],
            "fuel_type_label": FUEL_TYPES.get(r["fuel_type"], r["fuel_type"]),
            "liters": float(r["liters"]),
            "price_per_liter": float(r["price_per_liter"]),
            "total_pkr": float(r["total_pkr"]),
            "payment_method": r["payment_method"],
            "notes": r["notes"] or "",
            "created_at": r["created_at"],
        }
        for r in rows
    ]

    return json_response({"success": True, "dispenses": dispenses})


@fuelstation_blueprint.get("/profile")
@login_required
def get_profile():
    denied = _fuel_station_only()
    if denied:
        return denied

    user_id = request.current_user["id"]
    with open_db() as db:
        profile = db.execute(
            """
            SELECT p.*, u.full_name, u.email, u.phone, u.city, u.address
            FROM fuel_station_profiles p
            JOIN users u ON u.id = p.user_id
            WHERE p.user_id = %s
            """,
            (user_id,),
        ).fetchone()

    if not profile:
        return json_response({"success": False, "message": "Profile not found."}, 404)

    return json_response({
        "success": True,
        "profile": {
            "station_name": profile["station_name"] or "",
            "pumps_count": profile["pumps_count"] or "",
            "license_no": profile["license_no"] or "",
            "full_name": profile["full_name"] or "",
            "email": profile["email"] or "",
            "phone": profile["phone"] or "",
            "city": profile["city"] or "",
            "address": profile["address"] or "",
        },
    })


@fuelstation_blueprint.put("/profile")
@login_required
def update_profile():
    denied = _fuel_station_only()
    if denied:
        return denied
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    station_name = str(data.get("station_name") or "").strip()
    license_no = str(data.get("license_no") or "").strip()
    pumps_count = str(data.get("pumps_count") or "").strip()
    city = str(data.get("city") or "").strip()
    address = str(data.get("address") or "").strip()
    phone = str(data.get("phone") or "").strip()

    if not station_name:
        return json_response({"success": False, "message": "Station name is required."}, 400)

    user_id = request.current_user["id"]
    stamp = timestamp_bundle()["display"]

    with open_db() as db:
        db.execute(
            """
            UPDATE fuel_station_profiles
            SET station_name = %s, license_no = %s, pumps_count = %s, updated_at = %s
            WHERE user_id = %s
            """,
            (station_name, license_no, pumps_count, stamp, user_id),
        )
        db.execute(
            """
            UPDATE users
            SET city = %s, address = %s, phone = %s, updated_at = %s
            WHERE id = %s
            """,
            (city, address, phone, stamp, user_id),
        )
        db.commit()

    return json_response({"success": True, "message": "Profile updated successfully."})
