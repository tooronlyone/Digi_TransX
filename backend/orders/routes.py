import json
import uuid
from flask import Blueprint, request
from .pickup_schedule import validate_pickup_schedule

from auth import step_up_service
from auth.helpers import json_response, login_required, csrf_error, timestamp_bundle
from shared.db import open_db
from shared.validation import finite_float, bounded_count
from decimal import Decimal
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
from .market_pricing import market_key, lock_market, market_reference, validate_bid_reference
from shared.commissions import fee_schedule
from shared.roles import normalize_client_kind
from shared.roles import TRANSPORTER_ROLES
from shared.coordinates import (
    CoordinateValidationError,
    parse_optional_coordinate_pair,
)
from shared.payments import (
    CheckoutError,
    build_payment_quote,
    get_active_payment_for_shipment,
    parse_money_amount,
    parse_positive_id,
    perform_checkout,
    perform_start_trip,
    public_quote,
    serialize_payment_summary,
    validate_idempotency_key,
)
from .lifecycle import (
    add_transporter_statement,
    perform_client_confirm,
    perform_complete_delivery,
    serialize_dispute,
)
from .reviews import (
    REVIEW_REQUIRED,
    fetch_pending_reviews,
    first_pending_review,
    get_review_for_trip,
    submit_pending_review,
    validate_review_payload,
)
from wallet.helpers import round_money
from shared.roles import require_client_role, require_transporter_role
from .helpers import (
    serialize_order,
    serialize_bid,
    serialize_trip,
    get_or_create_order_for_client,
    validate_order_creation,
    fetch_order,
    fetch_enriched_bids,
    fetch_trip_for_order,
    calculate_no_show_penalty,
    order_access_for_user,
    truck_order_mismatch,
    truck_order_eligibility_mismatch,
    truck_distance_to_pickup_km,
    parse_truck_types,
)

orders_blueprint = Blueprint("orders", __name__)


@orders_blueprint.route('/api/orders/<int:order_id>/trips/<int:trip_id>/delivery-otp',methods=['GET','POST'])
@login_required
def delivery_otp_channel(order_id,trip_id):
    """Client's authenticated in-app channel; POST reveal retains MPIN step-up when MPIN is configured."""
    from .business_lifecycle import delivery_otp_for_client,payment_for_trip
    reveal=request.method=='POST'
    if reveal:
        error=csrf_error()
        if error:return error
    gate=None
    descriptor=None
    with open_db() as db:
        try:
            order=fetch_order(db,order_id)
            payment=payment_for_trip(db,trip_id)
            if not order or order['client_user_id']!=request.current_user['id'] or not payment or payment['shipment_id']!=order_id:
                raise CheckoutError('Access denied.',403)
            if reveal:
                user_mpin=db.execute("SELECT mpin_hash FROM users WHERE id=%s",(request.current_user['id'],)).fetchone()
                has_mpin=bool(user_mpin and user_mpin.get('mpin_hash'))
                if has_mpin and normalize_client_kind(request.current_user.get('role'))=='business':
                    descriptor=step_up_service.normalize_descriptor({'action_key':'client.delivery.confirm_release','resource_type':'trip','resource_id':trip_id,'amount_minor':step_up_service.money_to_minor(payment['bid_price']),'currency':'PKR'})
                    gate=step_up_service.consume_current_request(db,request,descriptor)
                    error=step_up_service.gate_error_response(gate,descriptor)
                    if error:
                        db.rollback()
                        return error
            result=delivery_otp_for_client(db,request.current_user,order_id,trip_id,reveal)
            if reveal and gate and descriptor:
                step_up_service.write_consumed_event(db,request_id=f'delivery.otp.reveal.{uuid.uuid4().hex}',gate=gate,descriptor=descriptor)
            db.commit()
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
    response=json_response({'success':True,**result})
    response.headers['Cache-Control']='no-store'
    return response


@orders_blueprint.post('/api/orders/<int:order_id>/trips/<int:trip_id>/verify-delivery-otp')
@login_required
def verify_delivery_otp_route(order_id,trip_id):
    from .business_lifecycle import verify_delivery_otp
    error=require_transporter_role(request.current_user) or csrf_error()
    if error:return error
    data=request.get_json(silent=True) or {}
    with open_db() as db:
        try:
            result=verify_delivery_otp(db,request.current_user,order_id,trip_id,data.get('otp'))
            # Invalid-code attempts MUST commit; transaction rollback would allow
            # an attacker unlimited retries despite the five-attempt SQL limit.
            db.commit()
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
    if not result['verified']:
        return json_response({'success':False,**result},400)
    result['trip']=serialize_trip(result['trip'])
    return json_response({'success':True,**result})


@orders_blueprint.post('/api/orders/<int:order_id>/trips/<int:trip_id>/disputes')
@login_required
def open_delivery_dispute_route(order_id,trip_id):
    from .business_lifecycle import open_delivery_dispute
    error=csrf_error()
    if error:return error
    data=request.get_json(silent=True) or {}
    with open_db() as db:
        try:
            result=open_delivery_dispute(db,request.current_user,order_id,trip_id,data.get('reason'),data.get('evidence'))
            db.commit()
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
    return json_response({'success':True,**result})


@orders_blueprint.post('/api/admin/freight-settlements/<int:settlement_id>/resolve')
@login_required
def resolve_delivery_settlement_route(settlement_id):
    from auth.helpers import require_admin_role
    from .business_lifecycle import resolve_delivery_settlement
    error=require_admin_role(request.current_user) or csrf_error()
    if error:return error
    data=request.get_json(silent=True) or {}
    with open_db() as db:
        try:
            result=resolve_delivery_settlement(db,request.current_user,settlement_id,data.get('client_refund_amount'),data.get('notes'),data.get('evidence'),data.get('investigation_result'))
            db.commit()
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
    return json_response({'success':True,**result})


@orders_blueprint.get("/api/business-rules/fees")
@login_required
def approved_business_fees():
    return json_response({"success": True, **{kind: fee_schedule(kind)
                         for kind in ("freight", "client")}})


@orders_blueprint.get("/api/orders/<int:order_id>/market-reference")
@login_required
def get_market_reference(order_id):
    with open_db() as db:
        order = db.execute_exact("SELECT * FROM shipments WHERE id=%s", (order_id,)).fetchone()
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)
        user = request.current_user
        transporter = str(user.get("role") or "").lower() in TRANSPORTER_ROLES
        access = order_access_for_user(db, order, user)
        if access is None and not (transporter and order["status"] == "open"):
            return json_response({"success": False, "message": "Access denied."}, 403)
        truck = None
        if transporter:
            truck_id = request.args.get("truck_id")
            try:
                truck_id = parse_positive_id(truck_id, "Truck ID") if truck_id is not None else None
            except ValueError as exc:
                return json_response({"success": False, "message": str(exc)}, 400)
            trucks = db.execute_exact(
                "SELECT * FROM vehicles WHERE owner_user_id=%s AND status='active' "
                "AND (%s::bigint IS NULL OR id=%s) ORDER BY id",
                (user["id"], truck_id, truck_id),
            ).fetchall()
            truck = next((v for v in trucks if not truck_order_eligibility_mismatch(
                v, parse_truck_types(order.get("required_truck_types")), order)), None)
            # Accepted transporters may view their own immutable category while
            # their truck is on_job; open-market viewers still need eligibility.
            if truck is None and access == "accepted_transporter":
                truck = db.execute_exact(
                    "SELECT v.* FROM shipment_bids b JOIN vehicles v ON v.id=b.truck_id "
                    "WHERE b.id=%s AND b.transporter_user_id=%s", (order["accepted_bid_id"], user["id"]),
                ).fetchone()
            if truck is None:
                return json_response({"success": False, "message": "An eligible owned truck is required for this market."}, 403)
        else:
            truck = db.execute_exact(
                "SELECT v.* FROM shipment_bids b JOIN vehicles v ON v.id=b.truck_id "
                "WHERE b.order_id=%s AND b.status IN ('pending','accepted') ORDER BY b.id LIMIT 1", (order_id,),
            ).fetchone()
            if truck is None:
                categories = parse_truck_types(order.get("required_truck_types"))
                truck = {"truck_type": categories[0] if categories else "unspecified"}
        result = market_reference(db, order, truck, user["id"] if transporter else None)
    return json_response({"success": True, **result})


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

    # Stable seeker-kind snapshot, derived server-side from the authenticated
    # role — never from the request body. Both kinds create shipments through
    # this one path; only the snapshot differs.
    seeker_kind = normalize_client_kind(request.current_user.get("role"))
    if seeker_kind is None:
        return json_response({"success": False, "message": "Client account required."}, 403)

    data = request.get_json(silent=True) or {}

    # Posting an order needs no wallet and no advance payment: everyday users
    # never get a wallet, and business clients pay only when accepting a bid.

    # ---- Single detailed location -> keep legacy city columns populated ----
    pickup_location = (data.get("pickup_location") or data.get("pickup_city") or "").strip()
    dropoff_location = (data.get("dropoff_location") or data.get("dropoff_city") or "").strip()
    data["pickup_city"] = pickup_location
    data["dropoff_city"] = dropoff_location

    try:
        pickup_lat, pickup_lng = parse_optional_coordinate_pair(
            data, "pickup_lat", "pickup_lng", label="Pickup"
        )
        dropoff_lat, dropoff_lng = parse_optional_coordinate_pair(
            data, "dropoff_lat", "dropoff_lng", label="Drop-off"
        )
    except CoordinateValidationError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

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

    try:
        pickup_date = validate_pickup_schedule(
            data.get("pickup_date"), (data.get("pickup_time") or "").strip()
        )
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    def _num(key):
        value = data.get(key)
        return finite_float(0 if value in (None, "") else value,key.replace("_", " "))

    try:
        goods_weight_tons = _num("goods_weight_tons")
        goods_volume_cbm = _num("goods_volume_cbm")
        estimated_budget = _num("estimated_budget")
        length_cm, width_cm, height_cm = (_num(key) for key in ("length_cm","width_cm","height_cm"))
        volume_liters = _num("volume_liters")
        quantity = bounded_count(data.get("quantity") or 0,"Quantity")
        animal_count = bounded_count(data.get("animal_count") or 0,"Animal count")
        temperature_raw = data.get("temperature_c")
        temperature_c = (None if temperature_raw in (None, "") else
                         finite_float(temperature_raw,"Temperature",minimum=Decimal("-273.15"),maximum=Decimal("1000")))
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

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

        if goods_category == "liquid":
            if volume_liters <= 0 and goods_weight_tons > 0:
                volume_liters = round(goods_weight_tons * 1000.0, 2)
            elif goods_weight_tons <= 0 and volume_liters > 0:
                goods_weight_tons = round(volume_liters / 1000.0, 3)
        elif goods_category == "livestock" and goods_weight_tons <= 0 and animal_count > 0:
            goods_weight_tons = round(max(0.3, animal_count * 0.35), 2)

        if goods_weight_tons > 100:
            return json_response({"success": False, "message": "Goods weight cannot exceed 100 tons per truck order."}, 400)
        if volume_liters > 100000:
            return json_response({"success": False, "message": "Liquid volume cannot exceed 100,000 liters (100 tons) per truck order."}, 400)

        reqs = goods_required_fields(commodity_key)
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
        pending = first_pending_review(db, request.current_user["id"])
        if pending:
            return json_response(
                {
                    "success": False,
                    "code": REVIEW_REQUIRED,
                    "message": "Please submit your pending transporter review before posting another one-time order.",
                    "pending_review": pending,
                },
                409,
            )
        order_id = db.execute(
            """
            INSERT INTO shipments (
                client_user_id, pickup_city, dropoff_city,
                pickup_date, pickup_time, goods_type, goods_weight_tons, goods_volume_cbm,
                estimated_budget, notes, status,
                goods_category, goods_form, goods_commodity,
                length_cm, width_cm, height_cm, volume_liters, quantity, animal_count,
                temperature_c, required_truck_types,
                is_refrigerated, is_hazardous, is_food_grade,
                pickup_location, pickup_lat, pickup_lng,
                dropoff_location, dropoff_lat, dropoff_lng,
                seeker_kind_snapshot,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open',
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                request.current_user["id"],
                pickup_location,
                dropoff_location,
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
                seeker_kind,
                stamp,
                stamp,
            ),
        ).fetchone()["id"]

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
        # the goods' truck TYPE, its weight/volume CAPACITY, cargo-bed
        # dimensions AND the truck's current location (for pickup proximity).
        my_trucks = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM vehicles WHERE owner_user_id = %s AND status = 'active' ORDER BY id DESC",
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

        # A truck with a set location lets us distinguish "no truck has a
        # location yet" (setup prompt) from "trucks are simply too far".
        active_truck_count = len(my_trucks)
        located_trucks = [t for t in my_trucks if t.get("current_lat") is not None]
        location_setup_required = active_truck_count > 0 and not located_trucks

        orders = []
        too_far_count = 0  # cargo would match, but every truck is out of range
        for row in order_rows:
            row_dict = dict(row)
            serialized = serialize_order(row_dict, row_dict.get("bid_count", 0))
            required = serialized.get("required_truck_types") or []
            # Single composed eligibility: show the order only if the transporter
            # owns at least one active truck that matches cargo AND is within its
            # service radius of the PICKUP. Availability and bidding use the exact
            # same helper, so they can never disagree.
            eligible = [
                t for t in my_trucks
                if truck_order_eligibility_mismatch(t, required, serialized) is None
            ]
            if not eligible:
                # Was it purely a distance miss (cargo matched on some truck)?
                cargo_ok = any(
                    truck_order_mismatch(t, required, serialized) is None for t in my_trucks
                )
                if cargo_ok:
                    too_far_count += 1
                continue
            # Nearest eligible truck's distance to the pickup, for display.
            distances = [
                d for d in (truck_distance_to_pickup_km(t, serialized) for t in eligible)
                if d is not None
            ]
            serialized["distance_to_pickup_km"] = min(distances) if distances else None
            serialized["eligible_truck_ids"] = [t["id"] for t in eligible if t.get("id") is not None]
            orders.append(serialized)

    return json_response({
        "success": True,
        "orders": orders,
        "location_setup_required": location_setup_required,
        "orders_out_of_range": too_far_count,
    })


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
        truck_id = parse_positive_id(data.get("truck_id"), "Truck ID")
    except ValueError:
        return json_response({"success": False, "message": "Invalid truck ID or bid price."}, 400)
    try:
        # Strict Decimal validation: finite, positive, max two decimals,
        # within numeric storage limits (rejects NaN/Infinity/0/negative).
        bid_price = parse_money_amount(data.get("bid_price"), "Bid price")
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        if order["status"] != "open":
            return json_response({"success": False, "message": "This order is not accepting bids."}, 400)

        # Verify truck ownership
        truck = db.execute(
            "SELECT * FROM vehicles WHERE id = %s AND owner_user_id = %s AND status = 'active'",
            (truck_id, request.current_user["id"]),
        ).fetchone()
        if not truck:
            return json_response({"success": False, "message": "Truck not found or not active."}, 404)

        # Single composed eligibility (same helper the availability list uses):
        # the truck must be a suitable TYPE with enough weight/volume/dimension
        # CAPACITY AND be within its service radius of the order PICKUP. A truck
        # that can carry the cargo but sits too far away cannot bid.
        required_trucks = parse_truck_types(order.get("required_truck_types"))
        mismatch = truck_order_eligibility_mismatch(dict(truck), required_trucks, dict(order))
        if mismatch:
            return json_response({"success": False, "message": mismatch}, 400)

        if order["client_user_id"] == request.current_user["id"]:
            return json_response({"success": False, "message": "You cannot bid on your own shipment."}, 403)

        # Market advisory lock precedes the shipment lock; withdrawal uses the
        # same order. Re-read the source after waiting so checkout cannot turn a
        # stale open-order check into a bid on an accepted shipment.
        key = market_key(order, dict(truck))
        lock_market(db, key)
        order = dict(db.execute_exact("SELECT * FROM shipments WHERE id=%s FOR UPDATE", (order_id,)).fetchone())
        if order["status"] != "open":
            return json_response({"success": False, "message": "This order is not accepting bids."}, 409)
        reference = market_reference(db, order, dict(truck), request.current_user["id"])
        try:
            validate_bid_reference(bid_price, reference)
        except ValueError as exc:
            return json_response({"success": False, "message": str(exc), "market_reference": reference}, 400)

        # Check for duplicate bids
        existing_bid = db.execute(
            "SELECT id FROM shipment_bids WHERE order_id = %s AND transporter_user_id = %s AND status IN ('pending', 'accepted')",
            (order_id, request.current_user["id"]),
        ).fetchone()
        if existing_bid:
            return json_response({"success": False, "message": "You already have an active bid on this order."}, 400)

        stamp = timestamp_bundle()["display"]
        bid_id = db.execute(
            """
            INSERT INTO shipment_bids (
                order_id, transporter_user_id, truck_id, bid_price, message, status, created_at, updated_at,
                market_key, market_reference_average, market_minimum_bid, market_maximum_bid,
                market_rating_snapshot, market_sample_count, market_bootstrap
            ) VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                order_id,
                request.current_user["id"],
                truck_id,
                bid_price,
                data.get("message", "").strip() or None,
                stamp,
                stamp,
                key,
                reference["reference_average_exact"] or bid_price,
                reference["minimum_bid"], reference["maximum_bid"],
                reference["verified_rating"], reference["sample_count"], reference["bootstrap"],
            ),
        ).fetchone()["id"]
        bid = db.execute_exact("SELECT * FROM shipment_bids WHERE id = %s", (bid_id,)).fetchone()
        published_reference = market_reference(db, order, dict(truck), request.current_user["id"])
        db.commit()

    return json_response({
        "success": True,
        "message": "Bid placed successfully.",
        "bid": serialize_bid(dict(bid)),
        "market_reference": published_reference,
    })


@orders_blueprint.post("/api/orders/<int:order_id>/bids/<int:bid_id>/withdraw")
@login_required
def withdraw_bid(order_id, bid_id):
    """Transporter withdraws their pending bid."""
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    with open_db() as db:
        candidate = db.execute(
            "SELECT b.*,row_to_json(s) AS shipment,row_to_json(v) AS truck "
            "FROM shipment_bids b JOIN shipments s ON s.id=b.order_id "
            "JOIN vehicles v ON v.id=b.truck_id WHERE b.id=%s AND b.order_id=%s",
            (bid_id, order_id),
        ).fetchone()
        if candidate:
            shipment = json.loads(candidate["shipment"]) if isinstance(candidate["shipment"], str) else candidate["shipment"]
            vehicle = json.loads(candidate["truck"]) if isinstance(candidate["truck"], str) else candidate["truck"]
            lock_market(db, market_key(shipment, vehicle))
        # Checkout locks shipment -> bid -> vehicle. Use the same order so a
        # withdrawal cannot overwrite an accepted bid or deadlock checkout.
        order = db.execute(
            "SELECT id, status FROM shipments WHERE id = %s FOR UPDATE", (order_id,),
        ).fetchone()
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)
        bid = db.execute(
            "SELECT * FROM shipment_bids WHERE id = %s AND order_id = %s FOR UPDATE",
            (bid_id, order_id),
        ).fetchone()

        if not bid:
            return json_response({"success": False, "message": "Bid not found."}, 404)

        if bid["transporter_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "You can only withdraw your own bids."}, 403)

        if bid["status"] != "pending":
            return json_response(
                {"success": False, "message": f"Cannot withdraw a bid that is already {bid['status']}."},
                400,
            )
        if order["status"] != "open":
            return json_response({"success": False,"message": "This order is no longer open."},409)

        stamp = timestamp_bundle()["display"]
        changed = db.execute(
            "UPDATE shipment_bids SET status = 'withdrawn', updated_at = %s "
            "WHERE id = %s AND order_id = %s AND transporter_user_id = %s AND status = 'pending' RETURNING id",
            (stamp, bid_id, order_id, request.current_user["id"]),
        ).fetchone()
        if not changed:
            return json_response({"success": False,"message": "The bid changed. Refresh before retrying."},409)
        db.commit()

    return json_response({
        "success": True,
        "message": "Bid withdrawn successfully.",
    })


@orders_blueprint.get("/api/orders/<int:order_id>")
@login_required
def get_order_details(order_id):
    """Order details, scoped by access level.

    Owner: full order, all bids, trip and payment summary.
    Accepted transporter: order, ONLY their accepted bid, trip and a safe
    payment summary (never competing bids, never card/funding details).
    Everyone else: 403.
    """
    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        access = order_access_for_user(db, order, request.current_user)
        if access is None:
            return json_response({"success": False, "message": "Access denied."}, 403)

        trip = fetch_trip_for_order(db, order_id)
        payment = get_active_payment_for_shipment(
            db, order_id, statuses=("processing", "held", "released", "disputed", "refunded")
        )

        if access == "owner":
            # Owner: every non-withdrawn bid, enriched with safe transporter /
            # truck data and per-bid checkout availability.
            bids = fetch_enriched_bids(db, order)
            payment_summary = serialize_payment_summary(payment, viewer="client")
        else:
            # Accepted transporter: the SAME enriched shape but scoped to only
            # their own bid (never competing bids).
            bids = fetch_enriched_bids(db, order, transporter_user_id=request.current_user["id"])
            payment_summary = serialize_payment_summary(payment, viewer="transporter")

        # Lifecycle context: the current dispute (if any) and the one-time chat
        # thread so both parties get an Open Chat action and dispute state.
        dispute = None
        chat_thread_id = None
        review = None
        if trip:
            dispute_row = db.execute(
                "SELECT * FROM shipment_disputes WHERE trip_id = %s ORDER BY id DESC LIMIT 1",
                (trip["id"],),
            ).fetchone()
            dispute = serialize_dispute(dict(dispute_row)) if dispute_row else None
            review = get_review_for_trip(db, request.current_user, order_id, trip["id"])
        thread_row = db.execute(
            "SELECT id FROM chat_threads WHERE shipment_id = %s", (order_id,)
        ).fetchone()
        chat_thread_id = thread_row["id"] if thread_row else None
        delivery_policy = None
        settlement = None
        if payment and payment.get('business_rules_version') == 'rules-1-4-v1':
            from .business_lifecycle import serialize_settlement
            delivery_policy={'version':'rules-1-4-v1','dispute_window_minutes':90,'release_minutes':120,'otp_digits':8}
            settlement=serialize_settlement(db.execute_exact('SELECT * FROM freight_settlements WHERE payment_id=%s',(payment['id'],)).fetchone())

    return json_response({
        "success": True,
        "access": access,
        "order": serialize_order(order),
        "bids": bids,
        "trip": serialize_trip(trip) if trip else None,
        "payment": payment_summary,
        "dispute": dispute,
        "review": review,
        "chat_thread_id": chat_thread_id,
        "delivery_policy": delivery_policy,
        "settlement": settlement,
    })


def _checkout_error_response(exc):
    payload = {"success": False, "message": exc.message}
    if exc.code:
        payload["code"] = exc.code
    return json_response(payload, exc.status)


@orders_blueprint.get("/api/orders/<int:order_id>/bids/<int:bid_id>/payment-quote")
@login_required
def bid_payment_quote(order_id, bid_id):
    """Server-calculated quote for paying one bid (client owner only)."""
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error

    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)
        if order["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)
        if order["status"] != "open":
            return json_response({"success": False, "message": "This order is no longer open for checkout."}, 409)
        bid = db.execute_exact(
            "SELECT * FROM shipment_bids WHERE id = %s AND order_id = %s", (bid_id, order_id)
        ).fetchone()
        if not bid:
            return json_response({"success": False, "message": "Bid not found."}, 404)
        if bid["status"] != "pending":
            return json_response({"success": False, "message": "This bid can no longer be accepted."}, 409)
        try:
            quote = build_payment_quote(db, order, dict(bid), request.current_user)
        except CheckoutError as exc:
            return _checkout_error_response(exc)

    return json_response({"success": True, "quote": public_quote(quote)})


@orders_blueprint.post("/api/orders/<int:order_id>/bids/<int:bid_id>/checkout")
@login_required
def checkout_bid(order_id, bid_id):
    """Pay for a bid and accept it in one atomic server-controlled workflow.

    The bid is never accepted before the payment succeeds; on any failure the
    whole transaction rolls back (no trip, no bid change, no wallet change,
    no payment record). A repeated request with the same Idempotency-Key
    returns the original result without charging again.
    """
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    # The client generates ONE key per checkout attempt and reuses it for
    # retries; a missing/invalid key is rejected inside perform_checkout —
    # the server never invents one (that would defeat idempotency).
    idempotency_key = request.headers.get("Idempotency-Key")

    descriptor = None
    gate = None
    request_id = f"one_time.checkout.wallet_only.{uuid.uuid4().hex}"
    with open_db() as db:
        try:
            idempotency_key = validate_idempotency_key(idempotency_key)
            existing_replay = db.execute(
                "SELECT id FROM payments WHERE idempotency_key=%s AND client_user_id=%s",
                (idempotency_key, request.current_user["id"]),
            ).fetchone()
            # A previously funded payment is a read-only replay. Its original
            # owner/order/bid binding is checked again by perform_checkout;
            # a later wallet balance or truck state cannot invalidate it.
            if normalize_client_kind(request.current_user.get("role")) == "business" and not existing_replay:
                order = fetch_order(db, order_id)
                if not order:
                    return json_response({"success": False, "message": "Order not found."}, 404)
                if order["client_user_id"] != request.current_user["id"]:
                    return json_response({"success": False, "message": "Access denied."}, 403)
                bid = db.execute(
                    "SELECT * FROM shipment_bids WHERE id=%s AND order_id=%s",
                    (bid_id, order_id),
                ).fetchone()
                if not bid:
                    return json_response({"success": False, "message": "Bid not found."}, 404)
                quote = build_payment_quote(
                    db, order, dict(bid), request.current_user
                )
                if Decimal(quote.get('wallet_shortfall','0')) > 0:
                    raise CheckoutError(f"Insufficient balance. Please top up PKR {Decimal(quote['wallet_shortfall']):,.2f} to accept this bid.",400,'insufficient_wallet_balance')
                if quote["card_funded_amount"] <= 0:
                    descriptor = step_up_service.normalize_descriptor({
                        "action_key": "one_time.checkout.wallet_only",
                        "resource_type": "order",
                        "resource_id": order_id,
                        "amount_minor": step_up_service.money_to_minor(
                            quote["bid_amount"]
                        ),
                        "currency": "PKR",
                        "funding_source": "wallet",
                    })
                    gate = step_up_service.consume_current_request(
                        db, request, descriptor
                    )
                    gate_error = step_up_service.gate_error_response(
                        gate, descriptor
                    )
                    if gate_error:
                        db.rollback()
                        return gate_error
            result = perform_checkout(
                db, request.current_user, order_id, bid_id,
                payload=payload, idempotency_key=idempotency_key,
                expected_step_up_descriptor=descriptor,
            )
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
        if gate and result["replayed"]:
            db.rollback()
        else:
            if gate:
                step_up_service.write_consumed_event(
                    db, request_id=request_id, gate=gate, descriptor=descriptor
                )
            db.commit()

    return json_response({
        "success": True,
        "message": "Payment held and bid accepted. The transporter can now start the trip."
        if not result["replayed"] else "Checkout already completed for this order.",
        "replayed": result["replayed"],
        "idempotency_key": idempotency_key,
        "order": serialize_order(result["order"]),
        "trip": serialize_trip(result["trip"]),
        "payment": serialize_payment_summary(result["payment"], viewer="client"),
        "quote": result.get("quote"),
    })


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/start")
@login_required
def start_trip(order_id, trip_id):
    """Accepted transporter starts a paid, ready trip (idempotent)."""
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    with open_db() as db:
        try:
            result = perform_start_trip(db, request.current_user, order_id, trip_id)
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
        db.commit()

    return json_response({
        "success": True,
        "message": "Trip already started." if result["already_started"] else "Trip started.",
        "already_started": result["already_started"],
        "trip": serialize_trip(result["trip"]),
    })


@orders_blueprint.post("/api/orders/<int:order_id>/accept-bid/<int:bid_id>")
@login_required
def accept_bid(order_id, bid_id):
    """Removed pre-payment acceptance flow.

    Bids are now accepted only through the atomic paid checkout — a bid can
    never be accepted before its payment succeeds.
    """
    return json_response(
        {
            "success": False,
            "code": "payment_required_checkout",
            "message": "Accepting a bid now requires payment. Use the checkout endpoint instead.",
            "checkout_endpoint": f"/api/orders/{order_id}/bids/{bid_id}/checkout",
            "quote_endpoint": f"/api/orders/{order_id}/bids/{bid_id}/payment-quote",
        },
        409,
    )


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/process-payment")
@login_required
def process_trip_payment(order_id, trip_id):
    """Removed post-acceptance payment flow.

    Payment now happens inside checkout before the bid is accepted, and the
    transporter starts the trip through the start endpoint.
    """
    return json_response(
        {
            "success": False,
            "code": "payment_required_checkout",
            "message": "This payment flow has been replaced. Payment is taken during bid checkout; "
                       "the transporter starts the trip once payment is held.",
            "start_endpoint": f"/api/orders/{order_id}/trips/{trip_id}/start",
        },
        409,
    )


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/complete-delivery")
@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/mark-completed")
@login_required
def complete_delivery(order_id, trip_id):
    """Transporter marks the goods delivered and opens the 6-hour client
    confirmation window. Payment stays held; no payout occurs. Idempotent.

    /mark-completed is kept as a backward-compatible alias for the one canonical
    handler (both hit the single lifecycle service — no duplicated logic)."""
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    with open_db() as db:
        try:
            result = perform_complete_delivery(db, request.current_user, order_id, trip_id)
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
        db.commit()

    return json_response({
        "success": True,
        "already": result["already"],
        "message": ("Delivery completion already requested."
                    if result["already"]
                    else ("Delivery OTP sent to the client. Ask the client to inspect cargo and share the authorized code." if result.get('otp_required') else "Delivery marked complete. Waiting for the client to confirm within 6 hours.")),
        "otp_required": bool(result.get('otp_required')),
        "trip": serialize_trip(result["trip"]),
        "confirmation_deadline_at": result["confirmation_deadline_at"],
    })


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/confirm-delivery")
@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/verify-delivery")
@login_required
def confirm_delivery(order_id, trip_id):
    """Client confirms delivery (Yes) or reports a problem (No).

    Yes releases the held payout once through the canonical release service; No
    opens exactly one dispute and keeps the money held. There is no legacy
    branch and no `payout_release_later_phase` response any more — this is the
    single client confirmation endpoint. /verify-delivery is a compatibility
    alias for the same handler (it accepts the legacy `response` field too)."""
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    decision = (data.get("decision") or data.get("response") or "").strip().lower()
    reason = data.get("reason")
    review_payload = None
    if decision == "yes":
        try:
            review_payload = validate_review_payload(data)
        except CheckoutError as exc:
            return _checkout_error_response(exc)

    descriptor = None
    gate = None
    request_id = f"client.delivery.confirm_release.{uuid.uuid4().hex}"
    with open_db() as db:
        try:
            if decision == "yes":
                current = db.execute(
                    "SELECT st.status, s.client_user_id, p.bid_price "
                    "FROM shipment_trips st JOIN shipments s ON s.id=st.order_id "
                    "LEFT JOIN payments p ON p.shipment_id=s.id AND p.trip_id=st.id "
                    "AND p.status='held' "
                    "WHERE st.id=%s AND st.order_id=%s",
                    (trip_id, order_id),
                ).fetchone()
                if (
                    current
                    and current["status"] != "completed"
                    and current["client_user_id"] == request.current_user["id"]
                    and current["bid_price"] is not None
                ):
                    descriptor = step_up_service.normalize_descriptor({
                        "action_key": "client.delivery.confirm_release",
                        "resource_type": "trip",
                        "resource_id": trip_id,
                        "amount_minor": step_up_service.money_to_minor(
                            current["bid_price"]
                        ),
                        "currency": "PKR",
                    })
                    gate = step_up_service.consume_current_request(
                        db, request, descriptor
                    )
                    gate_error = step_up_service.gate_error_response(
                        gate, descriptor
                    )
                    if gate_error:
                        db.rollback()
                        return gate_error
            result = perform_client_confirm(
                db, request.current_user, order_id, trip_id, decision,
                reason=reason, review_payload=review_payload,
                expected_release_descriptor=descriptor,
            )
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
        if gate and result["already"]:
            db.rollback()
        else:
            if gate:
                step_up_service.write_consumed_event(
                    db, request_id=request_id, gate=gate, descriptor=descriptor
                )
            db.commit()

    payload = {
        "success": True,
        "decision": result["decision"],
        "already": result["already"],
        "trip": serialize_trip(result["trip"]),
    }
    if result["decision"] == "yes":
        payload["message"] = "Delivery confirmed. Payment released to the transporter and your review was submitted."
        payload["payout_amount"] = result.get("payout_amount")
        payload["review"] = result.get("review")
    else:
        payload["message"] = "We recorded that there is a problem. An admin will review this delivery."
        payload["dispute"] = result.get("dispute")
    return json_response(payload)


@orders_blueprint.get("/api/reviews/pending")
@login_required
def list_pending_reviews():
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    with open_db() as db:
        pending = fetch_pending_reviews(db, request.current_user["id"])
    return json_response({"success": True, "pending_reviews": pending})


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/review")
@login_required
def submit_trip_review(order_id, trip_id):
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err
    try:
        payload = validate_review_payload(request.get_json(silent=True) or {})
    except CheckoutError as exc:
        return _checkout_error_response(exc)

    with open_db() as db:
        try:
            result = submit_pending_review(db, request.current_user, order_id, trip_id, payload)
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
        db.commit()
    return json_response(
        {
            "success": True,
            "already": result["already"],
            "message": "Review already submitted." if result["already"] else "Review submitted successfully.",
            "review": result["review"],
        }
    )


@orders_blueprint.get("/api/orders/<int:order_id>/trips/<int:trip_id>/review")
@login_required
def fetch_trip_review(order_id, trip_id):
    with open_db() as db:
        try:
            review = get_review_for_trip(db, request.current_user, order_id, trip_id)
        except CheckoutError as exc:
            return _checkout_error_response(exc)
    return json_response({"success": True, "review": review})


@orders_blueprint.post("/api/disputes/<int:dispute_id>/statement")
@login_required
def submit_dispute_statement(dispute_id):
    """Transporter adds a written complaint/statement to their open dispute."""
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    with open_db() as db:
        try:
            dispute = add_transporter_statement(
                db, request.current_user, dispute_id, data.get("statement")
            )
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
        db.commit()
    return json_response({"success": True, "dispute": dispute})


@orders_blueprint.get("/api/orders/my-orders")
@login_required
def get_my_orders():
    """Client views their orders."""
    with open_db() as db:
        orders = db.execute(
            """
            SELECT s.*, count(b.id) AS bid_count
            FROM shipments s
            LEFT JOIN shipment_bids b ON b.order_id = s.id AND b.status <> 'withdrawn'
            WHERE s.client_user_id = %s
            GROUP BY s.id
            ORDER BY s.created_at DESC, s.id DESC
            """,
            (request.current_user["id"],),
        ).fetchall()

        result = [serialize_order(dict(order), order["bid_count"]) for order in orders]

    return json_response({"success": True, "orders": result})


@orders_blueprint.get("/api/orders/my-bids")
@login_required
def get_my_bids():
    """Transporter views their bids."""
    with open_db() as db:
        bids = db.execute(
            """
            SELECT ob.*, o.pickup_city, o.dropoff_city, o.pickup_date, o.pickup_time,
                   o.goods_type, o.goods_weight_tons, o.volume_liters, o.estimated_budget,
                   o.status AS order_status
            FROM shipment_bids ob
            JOIN shipments o ON o.id = ob.order_id
            WHERE ob.transporter_user_id = %s
            ORDER BY ob.created_at DESC
            """,
            (request.current_user["id"],),
        ).fetchall()

        result = [serialize_bid(dict(b)) for b in bids]

    return json_response({"success": True, "bids": result})


# ---------------------------------------------------------------------------
# In-app lifecycle notifications (extends shipment_notifications; no new table)
# ---------------------------------------------------------------------------
from shared.notifications import serialize_notification  # noqa: E402


@orders_blueprint.get("/api/notifications")
@login_required
def list_notifications():
    """Current user's lifecycle notifications (most recent first)."""
    with open_db() as db:
        rows = db.execute(
            "SELECT * FROM shipment_notifications WHERE user_id = %s ORDER BY id DESC LIMIT 100",
            (request.current_user["id"],),
        ).fetchall()
        unread = db.execute(
            "SELECT COUNT(*) AS c FROM shipment_notifications WHERE user_id = %s AND is_read = false",
            (request.current_user["id"],),
        ).fetchone()["c"]
    return json_response({
        "success": True,
        "unread_count": int(unread),
        "notifications": [serialize_notification(dict(r)) for r in rows],
    })


@orders_blueprint.post("/api/notifications/<int:notification_id>/read")
@login_required
def mark_notification_read(notification_id):
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        db.execute(
            "UPDATE shipment_notifications SET is_read = true WHERE id = %s AND user_id = %s",
            (notification_id, request.current_user["id"]),
        )
        db.commit()
    return json_response({"success": True})


@orders_blueprint.post("/api/notifications/read-all")
@login_required
def mark_all_notifications_read():
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        db.execute(
            "UPDATE shipment_notifications SET is_read = true WHERE user_id = %s AND is_read = false",
            (request.current_user["id"],),
        )
        db.commit()
    return json_response({"success": True})
