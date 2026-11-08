import json
from functools import wraps
from flask import Blueprint, request

from shared.db import open_db
from auth.helpers import json_response, login_required, csrf_error, require_admin_role
from shared.commissions import BUSINESS_FEE_VERSION, itemized_fee
from shared.payments import CheckoutError, parse_money_amount, parse_positive_id
from shared.roles import TRANSPORTER_ROLES
from shared.validation import bounded_count
from .service import (
    MarketplaceError,
    issue_buyer_delivery_challenge,
    perform_delivery_verification,
    perform_marketplace_checkout,
    perform_marketplace_refund,
    _text as validated_text,
)

marketplace_blueprint = Blueprint("marketplace", __name__)


@marketplace_blueprint.errorhandler(CheckoutError)
def marketplace_error(exc):
    return json_response({"success": False, "message": exc.message, "code": exc.code}, exc.status)


def shopkeeper_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if str(request.current_user.get("role") or "").strip().lower() != "shopkeeper":
            return json_response({"success": False, "message": "Shopkeeper account required."}, 403)
        return view(*args, **kwargs)
    return wrapped


def json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise MarketplaceError("A JSON object is required.", 400)
    return data


def string_list(data, key, *, maximum, item_limit):
    values = data.get(key, [])
    if (not isinstance(values, list) or len(values) > maximum
            or any(not isinstance(value, str) or len(value) > item_limit for value in values)):
        raise MarketplaceError(f"Invalid {key.replace('_', ' ')}.", 400)
    return json.dumps(values)


def parse_json_field(val):
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []


def serialize_part(p):
    if not p:
        return None
    return {
        "id": p["id"],
        "shop_user_id": p["shop_user_id"],
        "shop_name": p.get("shop_name") or "Verified Truck Spares",
        "title": p["title"],
        "part_number": p.get("part_number") or "",
        "brand": p.get("brand") or "",
        "category": p["category"],
        "condition": p["condition"],
        "price": float(p["price"]),
        "discounted_price": float(p["discounted_price"]) if p.get("discounted_price") is not None else None,
        "stock_quantity": p["stock_quantity"],
        "warranty_days": p.get("warranty_days") or 0,
        "images": parse_json_field(p.get("images")),
        "description": p.get("description") or "",
        "compatible_models": parse_json_field(p.get("compatible_models")),
        "city": p.get("city") or "",
        "is_active": p["is_active"],
        "created_at": p["created_at"],
    }


def serialize_order(o, items=None):
    if not o:
        return None
    return {
        "id": o["id"],
        "order_number": o["order_number"],
        "buyer_user_id": o["buyer_user_id"],
        "shop_user_id": o["shop_user_id"],
        "shop_name": o.get("shop_name") or "Verified Vendor",
        "vehicle_id": o.get("vehicle_id"),
        "truck_number": o.get("truck_number"),
        "delivery_type": o["delivery_type"],
        "delivery_address": o.get("delivery_address") or "",
        "contact_phone": o.get("contact_phone") or "",
        "total_parts_amount": float(o["total_parts_amount"]),
        "delivery_fee": float(o["delivery_fee"]),
        "net_total": float(o["net_total"]),
        "payment_method": o["payment_method"],
        "payment_status": o["payment_status"],
        "fulfillment_status": o["fulfillment_status"],
        "buyer_notes": o.get("buyer_notes") or "",
        "created_at": o["created_at"],
        "items": items or [],
        "business_fee_version": o.get("business_fee_version"),
        "commission_breakdown": itemized_fee(str(o["total_parts_amount"]), "marketplace")
            if o.get("business_fee_version") == BUSINESS_FEE_VERSION else None,
    }


# ============================================================================
# 1. CATALOG / STOREFRONT (PUBLIC & TRANSPORTER)
# ============================================================================

@marketplace_blueprint.get("/api/marketplace/parts")
@login_required
def list_parts():
    """Browse catalog with filters for category, search query, brand, and vehicle model compatibility."""
    category = request.args.get("category", "").strip().lower()
    search = request.args.get("search", "").strip().lower()
    model = request.args.get("model", "").strip()
    city = request.args.get("city", "").strip()

    query = """
        SELECT p.*, COALESCE(sp.shop_name, u.full_name, 'Auto Parts Store') as shop_name
        FROM marketplace_parts p
        JOIN users u ON u.id = p.shop_user_id
        LEFT JOIN shopkeeper_profiles sp ON sp.user_id = p.shop_user_id
        WHERE p.is_active = true AND p.stock_quantity > 0
    """
    params = []

    if category and category != "all":
        query += " AND p.category = %s"
        params.append(category)

    if search:
        query += " AND (LOWER(p.title) LIKE %s OR LOWER(p.part_number) LIKE %s OR LOWER(p.brand) LIKE %s)"
        like_search = f"%{search}%"
        params.extend([like_search, like_search, like_search])

    if city and city != "all":
        query += " AND LOWER(p.city) = LOWER(%s)"
        params.append(city)

    query += " ORDER BY p.id DESC LIMIT 100"

    with open_db() as db:
        rows = db.execute(query, tuple(params)).fetchall()

    parts = [serialize_part(dict(r)) for r in rows]

    # Filter by vehicle model if requested
    if model:
        m_lower = model.lower()
        parts = [
            p for p in parts
            if not p["compatible_models"] or any(m_lower in str(cm).lower() for cm in p["compatible_models"])
        ]

    return json_response({"success": True, "parts": parts})


@marketplace_blueprint.get("/api/marketplace/parts/<int:part_id>")
@login_required
def get_part_detail(part_id):
    """Retrieve single part with seller details and compatibility specs."""
    query = """
        SELECT p.*, COALESCE(sp.shop_name, u.full_name, 'Auto Parts Store') as shop_name,
               u.phone as shop_phone
        FROM marketplace_parts p
        JOIN users u ON u.id = p.shop_user_id
        LEFT JOIN shopkeeper_profiles sp ON sp.user_id = p.shop_user_id
        WHERE p.id = %s
    """
    with open_db() as db:
        row = db.execute(query, (part_id,)).fetchone()
        if not row:
            return json_response({"success": False, "message": "Part not found"}, 404)
        return json_response({"success": True, "part": serialize_part(dict(row))})


# ============================================================================
# 2. CART & ORDER CHECKOUT (ESCROW LOCKING)
# ============================================================================

@marketplace_blueprint.post("/api/marketplace/orders")
@login_required
def create_order():
    """Reserve inventory and wallet funds exactly once for a checkout key."""
    err = csrf_error()
    if err:
        return err
    expected_actor = request.headers.get("X-DTX-Expected-User-Id")
    if expected_actor is None:
        raise MarketplaceError("Verify your account and reload the cart before checkout.",400,"checkout_account_required")
    try:
        expected_actor = parse_positive_id(expected_actor,"Expected checkout account")
    except ValueError as exc:
        raise MarketplaceError(str(exc),400,"checkout_account_required") from None
    if expected_actor != request.current_user["id"]:
        raise MarketplaceError("Account changed. Reload your cart before checkout.",409,"checkout_account_changed")
    with open_db() as db:
        result = perform_marketplace_checkout(
            db, request.current_user, request.get_json(silent=True),
            request.headers.get("Idempotency-Key"))
    return json_response({"success": True,
                          "message": "Order already placed." if result["replayed"] else "Order placed successfully!",
                          "replayed": result["replayed"], "order": result},
                         200 if result["replayed"] else 201)


@marketplace_blueprint.get("/api/marketplace/my-orders")
@login_required
def get_my_orders():
    """List orders placed by the current user."""
    user = request.current_user
    query = """
        SELECT o.*, COALESCE(sp.shop_name, u.full_name, 'Verified Shop') as shop_name,
               v.truck_number
        FROM marketplace_orders o
        JOIN users u ON u.id = o.shop_user_id
        LEFT JOIN shopkeeper_profiles sp ON sp.user_id = o.shop_user_id
        LEFT JOIN vehicles v ON v.id = o.vehicle_id
        WHERE o.buyer_user_id = %s
        ORDER BY o.id DESC
    """
    with open_db() as db:
        orders_rows = db.execute(query, (user["id"],)).fetchall()
        if not orders_rows:
            return json_response({"success": True, "orders": []})

        order_ids = [r["id"] for r in orders_rows]
        placeholders = ",".join(["%s"] * len(order_ids))
        items_rows = db.execute(
            f"SELECT * FROM marketplace_order_items WHERE order_id IN ({placeholders})",
            tuple(order_ids),
        ).fetchall()

    items_by_order = {}
    for item in items_rows:
        items_by_order.setdefault(item["order_id"], []).append(dict(item))

    orders = [serialize_order(dict(r), items_by_order.get(r["id"], [])) for r in orders_rows]
    return json_response({"success": True, "orders": orders})


# ============================================================================
# 3. SHOPKEEPER ORDER MANAGEMENT & OTP RELEASE
# ============================================================================

@marketplace_blueprint.post("/api/marketplace/admin/orders/<int:order_id>/refund")
@login_required
def admin_refund_marketplace_order(order_id):
    denied = require_admin_role(request.current_user)
    if denied:
        return denied
    error = csrf_error()
    if error:
        return error
    with open_db() as db:
        result = perform_marketplace_refund(db, request.current_user, order_id,
            request.get_json(silent=True), request.headers.get("Idempotency-Key"))
    return json_response(result)

@marketplace_blueprint.get("/api/marketplace/shop/orders")
@login_required
@shopkeeper_required
def get_shop_orders():
    """List orders received by the current shopkeeper."""
    user = request.current_user
    query = """
        SELECT o.*, u.full_name as buyer_name, u.phone as buyer_phone, v.truck_number
        FROM marketplace_orders o
        JOIN users u ON u.id = o.buyer_user_id
        LEFT JOIN vehicles v ON v.id = o.vehicle_id
        WHERE o.shop_user_id = %s
        ORDER BY o.id DESC
    """
    with open_db() as db:
        orders_rows = db.execute(query, (user["id"],)).fetchall()
        if not orders_rows:
            return json_response({"success": True, "orders": []})

        order_ids = [r["id"] for r in orders_rows]
        placeholders = ",".join(["%s"] * len(order_ids))
        items_rows = db.execute(
            f"SELECT * FROM marketplace_order_items WHERE order_id IN ({placeholders})",
            tuple(order_ids),
        ).fetchall()

    items_by_order = {}
    for item in items_rows:
        items_by_order.setdefault(item["order_id"], []).append(dict(item))

    orders = [serialize_order(dict(r), items_by_order.get(r["id"], [])) for r in orders_rows]
    return json_response({"success": True, "orders": orders})


@marketplace_blueprint.post("/api/marketplace/shop/orders/<int:order_id>/status")
@login_required
@shopkeeper_required
def update_shop_order_status(order_id):
    """Apply only a valid predecessor transition while holding the order lock."""
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("status"), str):
        raise MarketplaceError("A valid status is required.", 400)
    new_status = data["status"].strip().lower()
    with open_db() as db:
        order = db.execute(
            "SELECT * FROM marketplace_orders WHERE id=%s AND shop_user_id=%s FOR UPDATE",
            (order_id, request.current_user["id"])).fetchone()
        if order is None:
            raise MarketplaceError("Order not found.", 404)
        old_status = order["fulfillment_status"]
        transitions = {"placed": {"confirmed"},
                       "confirmed": {"dispatched"} if order["delivery_type"] == "delivery" else {"ready_for_pickup"}}
        if new_status != old_status and new_status not in transitions.get(old_status, set()):
            raise MarketplaceError("Invalid fulfillment transition.", 409)
        if new_status not in {"confirmed", "dispatched", "ready_for_pickup"}:
            raise MarketplaceError("Invalid status update.", 400)
        if new_status != old_status:
            db.execute("UPDATE marketplace_orders SET fulfillment_status=%s,updated_at=now() WHERE id=%s",
                       (new_status, order_id))
    return json_response({"success": True, "message": f"Order marked as {new_status}"})


@marketplace_blueprint.post("/api/marketplace/shop/orders/<int:order_id>/verify-otp")
@login_required
@shopkeeper_required
def verify_delivery_otp(order_id):
    """Verify the buyer's expiring private delivery proof and atomically settle."""
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise MarketplaceError("A JSON object is required.", 400)
    with open_db() as db:
        result = perform_delivery_verification(db, request.current_user, order_id, data.get("otp"))
    status = result.pop("status", 200)
    return json_response(result, status)


@marketplace_blueprint.post("/api/marketplace/orders/<int:order_id>/delivery-otp")
@login_required
def request_delivery_otp(order_id):
    """Only the purchaser can request a fresh handoff code."""
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        result = issue_buyer_delivery_challenge(db, request.current_user, order_id)
    return json_response({"success": True, **result})


# ============================================================================
# 4. SHOPKEEPER PARTS INVENTORY MANAGEMENT (CRUD)
# ============================================================================

@marketplace_blueprint.get("/api/marketplace/shop/parts")
@login_required
@shopkeeper_required
def get_shop_parts():
    """List parts belonging to the current shopkeeper."""
    user = request.current_user
    with open_db() as db:
        rows = db.execute(
            "SELECT * FROM marketplace_parts WHERE shop_user_id = %s ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
        parts = [serialize_part(dict(r)) for r in rows]
    return json_response({"success": True, "parts": parts})


@marketplace_blueprint.post("/api/marketplace/shop/parts")
@login_required
@shopkeeper_required
def add_shop_part():
    """Add a new part to the shop inventory and marketplace."""
    err = csrf_error()
    if err:
        return err

    user = request.current_user
    data = json_object()

    title = validated_text(data,"title",limit=200)
    category = validated_text(data,"category","engine",50).lower()
    try:
        price = parse_money_amount(data.get("price"),"Price")
        stock = bounded_count(data.get("stock_quantity",1),"Stock quantity",maximum=2147483647)
        warranty_days = bounded_count(data.get("warranty_days",0),"Warranty days",maximum=36500)
    except ValueError as exc:
        raise MarketplaceError(str(exc),400) from exc
    if not title or not category:
        raise MarketplaceError("A title and category are required.",400)

    part_number = validated_text(data,"part_number",limit=100)
    brand = validated_text(data,"brand",limit=100)
    condition = validated_text(data,"condition","new_oem",30).lower()
    if condition not in {"new_oem","new_aftermarket","kabli","refurbished"}:
        raise MarketplaceError("Invalid part condition.",400)
    description = validated_text(data,"description",limit=4000)
    city = validated_text(data,"city",str(user.get("city") or "Lahore"),100)
    compatible_models = string_list(data,"compatible_models",maximum=100,item_limit=100)
    images = string_list(data,"images",maximum=20,item_limit=2000)

    with open_db() as db:
        cur = db.execute(
            """
            INSERT INTO marketplace_parts (
                shop_user_id, title, part_number, brand, category, condition,
                price, stock_quantity, warranty_days, description, compatible_models,
                images, city, is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, NOW(), NOW())
            RETURNING id
            """,
            (
                user["id"], title, part_number, brand, category, condition,
                price, stock, warranty_days, description, compatible_models,
                images, city,
            ),
        )
        part_id = cur.fetchone()["id"]
        db.commit()

    return json_response({"success": True, "message": "Part listed successfully!", "part_id": part_id}, 201)


@marketplace_blueprint.delete("/api/marketplace/shop/parts/<int:part_id>")
@login_required
@shopkeeper_required
def delete_shop_part(part_id):
    """Remove a part from shop inventory."""
    err = csrf_error()
    if err:
        return err

    user = request.current_user
    with open_db() as db:
        db.execute(
            "DELETE FROM marketplace_parts WHERE id = %s AND shop_user_id = %s",
            (part_id, user["id"]),
        )
        db.commit()

    return json_response({"success": True, "message": "Part removed"})


# ============================================================================
# 5. RFQ / "PART REQUIRED" BROADCAST (EMERGENCY BREAKDOWN)
# ============================================================================

@marketplace_blueprint.post("/api/marketplace/rfq")
@login_required
def create_rfq():
    """Transporter broadcasts a request for a part that they cannot find in the store."""
    err = csrf_error()
    if err:
        return err

    user = request.current_user
    if str(user.get("role") or "").strip().lower() not in TRANSPORTER_ROLES:
        raise MarketplaceError("Transporter account required.",403)
    data = json_object()

    part_name = validated_text(data,"part_name",limit=200)
    city = validated_text(data,"city",str(user.get("city") or ""),100)
    if not part_name or not city:
        return json_response({"success": False, "message": "Part name and city are required"}, 400)

    category = validated_text(data,"category",limit=50)
    description = validated_text(data,"description",limit=4000)
    urgency = validated_text(data,"urgency","normal",30).lower()
    if urgency not in {"low","normal","breakdown_emergency"}:
        raise MarketplaceError("Invalid urgency.",400)
    try:
        vehicle_id = None if data.get("vehicle_id") is None else parse_positive_id(data["vehicle_id"],"Vehicle ID")
    except ValueError as exc:
        raise MarketplaceError(str(exc),400) from exc

    with open_db() as db:
        if vehicle_id is not None and db.execute(
                "SELECT id FROM vehicles WHERE id=%s AND owner_user_id=%s",(vehicle_id,user["id"])).fetchone() is None:
            raise MarketplaceError("Vehicle not found in your fleet.",404)
        cur = db.execute(
            """
            INSERT INTO part_rfqs (
                transporter_user_id, vehicle_id, part_name, category, description,
                urgency, city, status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', NOW(), NOW())
            RETURNING id
            """,
            (user["id"], vehicle_id, part_name, category, description, urgency, city),
        )
        rfq_id = cur.fetchone()["id"]
        db.commit()

    return json_response({"success": True, "message": "Request broadcast to nearby verified shops!", "rfq_id": rfq_id}, 201)


@marketplace_blueprint.get("/api/marketplace/rfq")
@login_required
def get_rfqs():
    """List open RFQs for shopkeepers to bid, or transporter's own RFQs."""
    user = request.current_user
    role = str(user.get("role") or "").strip().lower()
    if role not in TRANSPORTER_ROLES and role != "shopkeeper":
        raise MarketplaceError("Transporter or shopkeeper account required.",403)

    with open_db() as db:
        if role in TRANSPORTER_ROLES:
            rows = db.execute(
                """
                SELECT r.*, v.truck_number,
                       (SELECT COUNT(*) FROM part_rfq_bids b WHERE b.rfq_id = r.id) as bids_count
                FROM part_rfqs r
                LEFT JOIN vehicles v ON v.id = r.vehicle_id
                WHERE r.transporter_user_id = %s
                ORDER BY r.id DESC
                """,
                (user["id"],),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT r.*, v.truck_number, u.full_name as transporter_name,
                       (SELECT COUNT(*) FROM part_rfq_bids b WHERE b.rfq_id = r.id) as bids_count
                FROM part_rfqs r
                JOIN users u ON u.id = r.transporter_user_id
                LEFT JOIN vehicles v ON v.id = r.vehicle_id
                WHERE r.status = 'open'
                ORDER BY r.id DESC LIMIT 50
                """
            ).fetchall()

    return json_response({"success": True, "rfqs": [dict(r) for r in rows]})


@marketplace_blueprint.post("/api/marketplace/rfq/<int:rfq_id>/bid")
@login_required
@shopkeeper_required
def submit_rfq_bid(rfq_id):
    """Shopkeeper submits a price quote for a requested part."""
    err = csrf_error()
    if err:
        return err

    user = request.current_user
    data = json_object()

    try:
        offered_price = parse_money_amount(data.get("offered_price"),"Offered price")
        delivery_time_hours = bounded_count(data.get("delivery_time_hours",2),"Delivery time",maximum=720)
        warranty_days = bounded_count(data.get("warranty_days",0),"Warranty days",maximum=36500)
    except ValueError as exc:
        raise MarketplaceError(str(exc),400) from exc
    if delivery_time_hours == 0:
        raise MarketplaceError("Delivery time must be greater than zero.",400)
    condition = validated_text(data,"condition","new_oem",30).lower()
    if condition not in {"new_oem","new_aftermarket","kabli","refurbished"}:
        raise MarketplaceError("Invalid part condition.",400)
    brand = validated_text(data,"brand",limit=100)
    note = validated_text(data,"note",limit=4000)

    with open_db() as db:
        rfq = db.execute("SELECT * FROM part_rfqs WHERE id = %s FOR SHARE", (rfq_id,)).fetchone()
        if not rfq or rfq["status"] != "open":
            return json_response({"success": False, "message": "This request is no longer open"}, 400)

        cur = db.execute(
            """
            INSERT INTO part_rfq_bids (
                rfq_id, shop_user_id, offered_price, condition, brand,
                warranty_days, delivery_time_hours, note, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'submitted', NOW())
            RETURNING id
            """,
            (rfq_id, user["id"], offered_price, condition, brand, warranty_days, delivery_time_hours, note),
        )
        bid_id = cur.fetchone()["id"]
        db.commit()

    return json_response({"success": True, "message": "Quote submitted to transporter!", "bid_id": bid_id}, 201)
