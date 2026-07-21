import json
from flask import Blueprint, request
from datetime import datetime, timedelta, time

from auth.helpers import json_response, login_required, csrf_error, timestamp_bundle
from shared.db import open_db
from .goods_taxonomy import (
    get_commodity,
    required_fields as goods_required_fields,
    required_truck_types as goods_required_trucks,
    commodity_flags,
    FIELD_DIMENSIONS,
    FIELD_VOLUME_LITERS,
    FIELD_WEIGHT,
    FIELD_ANIMAL_COUNT,
)
from shared.commissions import (
    POLICY_TYPE_ONE_TIME,
    get_active_policy,
    get_current_terms_version,
    policy_company_share,
    snapshot_company_share,
    split_final_amount,
    transporter_share_percent_for,
)
from wallet.helpers import get_or_create_wallet, round_money, available_balance, adjust_wallet_balance
from agreements.helpers import require_client_role, require_transporter_role
from .helpers import (
    serialize_order,
    serialize_bid,
    serialize_trip,
    get_or_create_order_for_client,
    validate_order_creation,
    fetch_order,
    fetch_bids_for_order,
    calculate_no_show_penalty,
    truck_order_mismatch,
    parse_truck_types,
)

orders_blueprint = Blueprint("orders", __name__)


@orders_blueprint.post("/api/orders")
@login_required
def create_order():
    """Client creates a new one-time order."""
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}

    # Validate wallet
    wallet, wallet_error = get_or_create_wallet(request.current_user)
    if wallet_error:
        return wallet_error

    # ---- Single detailed location -> keep legacy city columns populated ----
    pickup_location = (data.get("pickup_location") or data.get("pickup_city") or "").strip()
    dropoff_location = (data.get("dropoff_location") or data.get("dropoff_city") or "").strip()
    data["pickup_city"] = pickup_location
    data["dropoff_city"] = dropoff_location

    def _coord(key):
        try:
            v = data.get(key)
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    pickup_lat = _coord("pickup_lat")
    pickup_lng = _coord("pickup_lng")
    dropoff_lat = _coord("dropoff_lat")
    dropoff_lng = _coord("dropoff_lng")

    # ---- Goods taxonomy: derive category / commodity / required trucks ----
    commodity_key = (data.get("goods_commodity") or "").strip()
    commodity = get_commodity(commodity_key)
    if commodity:
        # goods_type kept for backward compatibility / display
        data["goods_type"] = commodity["label"]

    # Validate common order data (pickup fields, goods_type, weight presence)
    validation_error = validate_order_creation(data)
    if validation_error:
        return validation_error

    # Client must give the transporter at least this long to prepare the truck.
    PICKUP_LEAD_MINUTES = 20
    try:
        pickup_date = datetime.fromisoformat(data.get("pickup_date")).date()
    except (ValueError, TypeError):
        return json_response({"success": False, "message": "Invalid pickup date format."}, 400)

    pickup_time_raw = (data.get("pickup_time") or "").strip()
    try:
        # Accept HH:MM or HH:MM:SS
        t_parts = [int(p) for p in pickup_time_raw.split(":")[:2]]
        pickup_dt = datetime.combine(pickup_date, time(t_parts[0], t_parts[1]))
    except (ValueError, TypeError, IndexError):
        return json_response({"success": False, "message": "Invalid pickup time format."}, 400)

    earliest = datetime.now() + timedelta(minutes=PICKUP_LEAD_MINUTES)
    if pickup_dt < earliest:
        return json_response(
            {"success": False,
             "message": f"Pickup must be at least {PICKUP_LEAD_MINUTES} minutes from now so the transporter can prepare."},
            400,
        )

    def _num(key):
        try:
            return float(data.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _int(key):
        try:
            return int(float(data.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    goods_weight_tons = _num("goods_weight_tons")
    goods_volume_cbm = _num("goods_volume_cbm")
    estimated_budget = _num("estimated_budget")
    length_cm = _num("length_cm")
    width_cm = _num("width_cm")
    height_cm = _num("height_cm")
    volume_liters = _num("volume_liters")
    quantity = _int("quantity")
    animal_count = _int("animal_count")
    temperature_c = data.get("temperature_c")
    try:
        temperature_c = float(temperature_c) if temperature_c not in (None, "") else None
    except (TypeError, ValueError):
        temperature_c = None

    # Defaults (legacy orders with no commodity keep old, unrestricted behaviour)
    goods_category = goods_form = None
    goods_commodity = None
    required_trucks = []
    is_refrigerated = is_hazardous = is_food_grade = False

    if commodity:
        goods_category = commodity["category"]
        goods_form = commodity.get("form")
        goods_commodity = commodity_key
        required_trucks = goods_required_trucks(commodity_key)
        flags = commodity_flags(commodity_key)
        is_refrigerated = bool(flags.get("refrigerated"))
        is_hazardous = bool(flags.get("hazardous"))
        is_food_grade = bool(flags.get("food_grade"))

        reqs = goods_required_fields(commodity_key)
        if FIELD_DIMENSIONS in reqs and not (length_cm > 0 and width_cm > 0 and height_cm > 0):
            return json_response({"success": False, "message": "Length, width and height are required for packaged solid goods."}, 400)
        if FIELD_VOLUME_LITERS in reqs and not volume_liters > 0:
            return json_response({"success": False, "message": "Volume (liters) is required for liquid goods."}, 400)
        if FIELD_WEIGHT in reqs and not goods_weight_tons > 0:
            return json_response({"success": False, "message": "Goods weight (tons) is required."}, 400)
        if FIELD_ANIMAL_COUNT in reqs and not animal_count > 0:
            return json_response({"success": False, "message": "Number of animals is required for livestock."}, 400)
    else:
        # Legacy path: weight must be provided
        if goods_weight_tons <= 0:
            return json_response({"success": False, "message": "Goods weight (tons) is required."}, 400)

    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        db.execute(
            """
            INSERT INTO shipments (
                client_user_id, pickup_city, pickup_area, dropoff_city, dropoff_area,
                pickup_date, pickup_time, goods_type, goods_weight_tons, goods_volume_cbm,
                estimated_budget, notes, status,
                goods_category, goods_form, goods_commodity,
                length_cm, width_cm, height_cm, volume_liters, quantity, animal_count,
                temperature_c, required_truck_types,
                is_refrigerated, is_hazardous, is_food_grade,
                pickup_location, pickup_lat, pickup_lng,
                dropoff_location, dropoff_lat, dropoff_lng,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open',
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.current_user["id"],
                pickup_location,
                (data.get("pickup_area") or "").strip(),
                dropoff_location,
                (data.get("dropoff_area") or "").strip(),
                pickup_date.isoformat(),
                data.get("pickup_time", "").strip(),
                data.get("goods_type", "").strip(),
                goods_weight_tons,
                goods_volume_cbm if goods_volume_cbm > 0 else None,
                estimated_budget if estimated_budget > 0 else None,
                data.get("notes", "").strip() or None,
                goods_category,
                goods_form,
                goods_commodity,
                length_cm if length_cm > 0 else None,
                width_cm if width_cm > 0 else None,
                height_cm if height_cm > 0 else None,
                volume_liters if volume_liters > 0 else None,
                quantity if quantity > 0 else None,
                animal_count if animal_count > 0 else None,
                temperature_c,
                json.dumps(required_trucks) if required_trucks else None,
                is_refrigerated,
                is_hazardous,
                is_food_grade,
                pickup_location,
                pickup_lat,
                pickup_lng,
                dropoff_location,
                dropoff_lat,
                dropoff_lng,
                stamp,
                stamp,
            ),
        )
        order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.commit()
        order = fetch_order(db, order_id)

    return json_response({
        "success": True,
        "message": "Order posted successfully. Transporters can now bid.",
        "order": serialize_order(order),
    })


@orders_blueprint.get("/api/orders/available")
@login_required
def available_orders():
    """Transporter sees open orders available for bidding."""
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error

    with open_db() as db:
        # Active trucks this transporter owns, with the specs needed to match
        # both the goods' truck TYPE and its weight/volume CAPACITY.
        my_trucks = [
            dict(r)
            for r in db.execute(
                "SELECT catalog_type_key, truck_type, capacity_tons, payload_max_tons, volume_max_cbm, "
                "bed_length_ft, bed_width_ft, bed_height_ft "
                "FROM vehicles WHERE owner_user_id = ? AND status = 'active'",
                (request.current_user["id"],),
            ).fetchall()
        ]

        order_rows = db.execute(
            """
            SELECT o.*, COUNT(DISTINCT ob.id) AS bid_count
            FROM shipments o
            LEFT JOIN shipment_bids ob ON ob.order_id = o.id AND ob.status != 'withdrawn'
            WHERE o.status = 'open'
            GROUP BY o.id
            ORDER BY o.created_at DESC
            """
        ).fetchall()

        orders = []
        for row in order_rows:
            row_dict = dict(row)
            serialized = serialize_order(row_dict, row_dict.get("bid_count", 0))
            required = serialized.get("required_truck_types") or []
            # Smart matching: show the order only if the transporter owns at least
            # one active truck of a suitable TYPE whose weight/volume CAPACITY can
            # actually carry this load.
            if not any(truck_order_mismatch(t, required, serialized) is None for t in my_trucks):
                continue
            orders.append(serialized)

    return json_response({"success": True, "orders": orders})


@orders_blueprint.post("/api/orders/<int:order_id>/bids")
@login_required
def create_bid(order_id):
    """Transporter places a bid on an order."""
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}

    try:
        truck_id = int(data.get("truck_id"))
        bid_price = float(data.get("bid_price"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Invalid truck ID or bid price."}, 400)

    if bid_price <= 0:
        return json_response({"success": False, "message": "Bid price must be greater than 0."}, 400)

    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        if order["status"] != "open":
            return json_response({"success": False, "message": "This order is not accepting bids."}, 400)

        # Verify truck ownership
        truck = db.execute(
            "SELECT * FROM vehicles WHERE id = ? AND owner_user_id = ? AND status = 'active'",
            (truck_id, request.current_user["id"]),
        ).fetchone()
        if not truck:
            return json_response({"success": False, "message": "Truck not found or not active."}, 404)

        # Smart matching: the truck must be a suitable TYPE for the goods AND have
        # enough weight/volume CAPACITY to carry this specific load.
        required_trucks = parse_truck_types(order.get("required_truck_types"))
        mismatch = truck_order_mismatch(dict(truck), required_trucks, dict(order))
        if mismatch:
            return json_response({"success": False, "message": mismatch}, 400)

        # Check for duplicate bids
        existing_bid = db.execute(
            "SELECT id FROM shipment_bids WHERE order_id = ? AND transporter_user_id = ? AND status IN ('pending', 'accepted')",
            (order_id, request.current_user["id"]),
        ).fetchone()
        if existing_bid:
            return json_response({"success": False, "message": "You already have an active bid on this order."}, 400)

        stamp = timestamp_bundle()["display"]
        db.execute(
            """
            INSERT INTO shipment_bids (
                order_id, transporter_user_id, truck_id, bid_price, message, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                order_id,
                request.current_user["id"],
                truck_id,
                round_money(bid_price),
                data.get("message", "").strip() or None,
                stamp,
                stamp,
            ),
        )
        bid_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        bid = db.execute("SELECT * FROM shipment_bids WHERE id = ?", (bid_id,)).fetchone()
        db.commit()

    return json_response({
        "success": True,
        "message": "Bid placed successfully.",
        "bid": serialize_bid(dict(bid)),
    })


@orders_blueprint.get("/api/orders/<int:order_id>")
@login_required
def get_order_details(order_id):
    """Get order details with all bids."""
    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        # Check access
        if order["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        bids = fetch_bids_for_order(db, order_id)

    return json_response({
        "success": True,
        "order": serialize_order(order),
        "bids": [serialize_bid(b) for b in bids],
    })


@orders_blueprint.post("/api/orders/<int:order_id>/accept-bid/<int:bid_id>")
@login_required
def accept_bid(order_id, bid_id):
    """Client accepts a bid and creates a trip."""
    err = csrf_error()
    if err:
        return err

    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        if order["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        if order["status"] != "open":
            return json_response({"success": False, "message": "Order is not open for bids."}, 400)

        bid = db.execute("SELECT * FROM shipment_bids WHERE id = ? AND order_id = ?", (bid_id, order_id)).fetchone()
        if not bid:
            return json_response({"success": False, "message": "Bid not found."}, 404)

        if bid["status"] != "pending":
            return json_response({"success": False, "message": "Bid cannot be accepted."}, 400)

        stamp = timestamp_bundle()["display"]

        # Snapshot the active one-time commission: this order keeps this split
        # for its entire lifetime, regardless of later policy changes.
        active_policy = get_active_policy(db, POLICY_TYPE_ONE_TIME)
        current_terms = get_current_terms_version(db)
        company_share = policy_company_share(active_policy)
        transporter_share = transporter_share_percent_for(company_share)

        # Update order status
        db.execute(
            """
            UPDATE shipments
            SET status = 'accepted', accepted_bid_id = ?, payment_amount = ?,
                company_share_percent_snapshot = ?, transporter_share_percent_snapshot = ?,
                commission_policy_id = ?, terms_version_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                bid_id,
                round_money(bid["bid_price"]),
                float(company_share),
                float(transporter_share),
                active_policy["id"] if active_policy else None,
                current_terms["id"] if current_terms else None,
                stamp,
                order_id,
            ),
        )

        # Update bid status
        db.execute(
            "UPDATE shipment_bids SET status = 'accepted', updated_at = ? WHERE id = ?",
            (stamp, bid_id),
        )

        # Reject other bids
        db.execute(
            "UPDATE shipment_bids SET status = 'rejected', updated_at = ? WHERE order_id = ? AND id != ?",
            (stamp, order_id, bid_id),
        )

        # Create trip
        db.execute(
            """
            INSERT INTO shipment_trips (
                order_id, accepted_bid_id, transporter_user_id, truck_id, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'accepted', ?, ?)
            """,
            (order_id, bid_id, bid["transporter_user_id"], bid["truck_id"], stamp, stamp),
        )
        trip_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create no-show tracking
        db.execute(
            "INSERT INTO shipment_no_show_tracking (trip_id, status, created_at, updated_at) VALUES (?, 'tracking', ?, ?)",
            (trip_id, stamp, stamp),
        )

        db.commit()

        trip = db.execute("SELECT * FROM shipment_trips WHERE id = ?", (trip_id,)).fetchone()
        updated_order = fetch_order(db, order_id)

    return json_response({
        "success": True,
        "message": "Bid accepted. Trip created. Awaiting payment confirmation.",
        "order": serialize_order(updated_order),
        "trip": serialize_trip(dict(trip)),
    })


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/process-payment")
@login_required
def process_trip_payment(order_id, trip_id):
    """Process payment when client confirms and payment is ready."""
    err = csrf_error()
    if err:
        return err

    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        if order["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        trip = db.execute("SELECT * FROM shipment_trips WHERE id = ? AND order_id = ?", (trip_id, order_id)).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)

        if trip["status"] != "accepted":
            return json_response({"success": False, "message": "Trip cannot process payment."}, 400)

        # Check wallet balance
        wallet, wallet_error = get_or_create_wallet(request.current_user)
        if wallet_error:
            return wallet_error

        payment_amount = round_money(order["payment_amount"])
        if available_balance(wallet) + 1e-9 < payment_amount:
            return json_response({
                "success": False,
                "message": f"Insufficient wallet balance. Required: PKR {payment_amount:,.2f}",
            }, 400)

        stamp = timestamp_bundle()["display"]

        # Deduct from client wallet
        debit_error = adjust_wallet_balance(
            db,
            wallet,
            request.current_user["id"],
            -payment_amount,
            "order_payment",
            description=f"Payment for order #{order_id}",
            reference_id=str(trip_id),
        )
        if debit_error:
            db.rollback()
            return debit_error

        # Update trip and order status
        db.execute(
            "UPDATE shipment_trips SET status = 'in_progress', trip_started_at = ?, updated_at = ? WHERE id = ?",
            (stamp, stamp, trip_id),
        )
        db.execute(
            "UPDATE shipments SET payment_status = 'paid', updated_at = ? WHERE id = ?",
            (stamp, order_id),
        )

        db.commit()
        trip = db.execute("SELECT * FROM shipment_trips WHERE id = ?", (trip_id,)).fetchone()

    return json_response({
        "success": True,
        "message": "Payment processed. Trip started. Transporter can now pickup goods.",
        "trip": serialize_trip(dict(trip)),
    })


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/mark-completed")
@login_required
def mark_trip_completed(order_id, trip_id):
    """Transporter marks trip as completed."""
    err = csrf_error()
    if err:
        return err

    with open_db() as db:
        trip = db.execute("SELECT * FROM shipment_trips WHERE id = ? AND order_id = ?", (trip_id, order_id)).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)

        if trip["transporter_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        if trip["status"] != "in_progress":
            return json_response({"success": False, "message": "Trip is not in progress."}, 400)

        stamp = timestamp_bundle()["display"]

        # Update trip status
        db.execute(
            "UPDATE shipment_trips SET status = 'delivery_claimed', trip_completed_at = ?, updated_at = ? WHERE id = ?",
            (stamp, stamp, trip_id),
        )

        # Create verification record
        db.execute(
            """
            INSERT INTO shipment_trip_verification (
                trip_id, transporter_claim_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (trip_id, stamp, stamp, stamp),
        )

        db.commit()
        trip = db.execute("SELECT * FROM shipment_trips WHERE id = ?", (trip_id,)).fetchone()

    return json_response({
        "success": True,
        "message": "Delivery marked as completed. Awaiting client verification.",
        "trip": serialize_trip(dict(trip)),
    })


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/verify-delivery")
@login_required
def verify_delivery(order_id, trip_id):
    """Client verifies delivery."""
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    response = data.get("response")  # 'yes' or 'no'

    if response not in ("yes", "no"):
        return json_response({"success": False, "message": "Invalid response."}, 400)

    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        if order["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        trip = db.execute("SELECT * FROM shipment_trips WHERE id = ? AND order_id = ?", (trip_id, order_id)).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)

        if trip["status"] not in ("delivery_claimed", "first_response_pending"):
            return json_response({"success": False, "message": "Trip cannot be verified."}, 400)

        stamp = timestamp_bundle()["display"]

        # Get verification record
        verification = db.execute(
            "SELECT * FROM shipment_trip_verification WHERE trip_id = ?",
            (trip_id,),
        ).fetchone()

        if not verification:
            return json_response({"success": False, "message": "Verification record not found."}, 404)

        if response == "yes":
            # Payment successful
            trip_obj = dict(trip)
            transporter_wallet, _ = get_or_create_wallet({"id": trip_obj["transporter_user_id"], "role": "transporter"})

            # Always split with the commission snapshot saved at bid acceptance
            # (legacy orders without a snapshot fall back to the 20/80 split
            # they were accepted under).
            payment_amount = round_money(order["payment_amount"])
            company_share = snapshot_company_share(order)
            company_fee, transporter_amount = split_final_amount(payment_amount, company_share)

            # Credit transporter
            adjust_wallet_balance(
                db,
                transporter_wallet,
                trip_obj["transporter_user_id"],
                transporter_amount,
                "order_income",
                description=f"Payment received for order #{order_id}",
                reference_id=str(trip_id),
            )

            # Update trip
            db.execute(
                "UPDATE shipment_trips SET status = 'completed', delivery_confirmed_at = ?, updated_at = ? WHERE id = ?",
                (stamp, stamp, trip_id),
            )

            # Update verification
            db.execute(
                "UPDATE shipment_trip_verification SET client_first_response = 'yes', client_first_response_at = ?, final_verification_status = 'confirmed', updated_at = ? WHERE trip_id = ?",
                (stamp, stamp, trip_id),
            )

            # Create invoice (records the applied split for the audit trail)
            db.execute(
                """
                INSERT INTO payments (
                    trip_id, invoice_number, client_user_id, transporter_user_id,
                    bid_price, company_fee, transporter_amount,
                    company_share_percent, transporter_share_percent, commission_policy_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trip_id,
                    f"ORD-{order_id}-{trip_id}-{datetime.now().strftime('%Y%m%d')}",
                    order["client_user_id"],
                    trip_obj["transporter_user_id"],
                    payment_amount,
                    company_fee,
                    transporter_amount,
                    float(company_share),
                    float(transporter_share_percent_for(company_share)),
                    order.get("commission_policy_id"),
                    stamp,
                ),
            )

            db.commit()
            return json_response({
                "success": True,
                "message": "Delivery confirmed. Payment released to transporter.",
            })
        else:
            # Client says NO
            if verification["client_first_response"] is None:
                # First NO - set 10 min reminder
                db.execute(
                    "UPDATE shipment_trip_verification SET client_first_response = 'no', client_first_response_at = ?, updated_at = ? WHERE trip_id = ?",
                    (stamp, stamp, trip_id),
                )
                db.execute(
                    "UPDATE shipment_trips SET status = 'first_response_pending', updated_at = ? WHERE id = ?",
                    (stamp, trip_id),
                )
                db.commit()
                return json_response({
                    "success": True,
                    "message": "Your response has been recorded. You will receive a reminder in 10 minutes.",
                })
            else:
                # Second NO or timeout - admin review
                db.execute(
                    "UPDATE shipment_trip_verification SET client_second_response = 'no', client_second_response_at = ?, final_verification_status = 'pending_admin', updated_at = ? WHERE trip_id = ?",
                    (stamp, stamp, trip_id),
                )
                db.execute(
                    "UPDATE shipment_trips SET status = 'dispute_pending', updated_at = ? WHERE id = ?",
                    (stamp, trip_id),
                )
                db.commit()
                return json_response({
                    "success": True,
                    "message": "Admin will review this dispute and determine the outcome.",
                })


@orders_blueprint.get("/api/orders/my-orders")
@login_required
def get_my_orders():
    """Client views their orders."""
    with open_db() as db:
        orders = db.execute(
            "SELECT * FROM shipments WHERE client_user_id = ? ORDER BY created_at DESC",
            (request.current_user["id"],),
        ).fetchall()

        result = []
        for order in orders:
            order_dict = dict(order)
            bid_count = db.execute(
                "SELECT COUNT(*) as count FROM shipment_bids WHERE order_id = ? AND status != 'withdrawn'",
                (order_dict["id"],),
            ).fetchone()["count"]
            result.append(serialize_order(order_dict, bid_count))

    return json_response({"success": True, "orders": result})


@orders_blueprint.get("/api/orders/my-bids")
@login_required
def get_my_bids():
    """Transporter views their bids."""
    with open_db() as db:
        bids = db.execute(
            """
            SELECT ob.*, o.pickup_city, o.dropoff_city, o.pickup_date, o.goods_type, o.estimated_budget
            FROM shipment_bids ob
            JOIN shipments o ON o.id = ob.order_id
            WHERE ob.transporter_user_id = ?
            ORDER BY ob.created_at DESC
            """,
            (request.current_user["id"],),
        ).fetchall()

        result = [serialize_bid(dict(b)) for b in bids]

    return json_response({"success": True, "bids": result})
