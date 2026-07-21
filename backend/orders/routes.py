import json
from uuid import uuid4

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
from shared.commissions import snapshot_company_share, split_final_amount, transporter_share_percent_for
from shared.payments import (
    CheckoutError,
    build_payment_quote,
    get_active_payment_for_shipment,
    perform_checkout,
    perform_start_trip,
    public_quote,
    serialize_payment_summary,
)
from wallet.helpers import adjust_wallet_balance, get_or_create_wallet, round_money
from agreements.helpers import require_client_role, require_transporter_role
from .helpers import (
    serialize_order,
    serialize_bid,
    serialize_trip,
    get_or_create_order_for_client,
    validate_order_creation,
    fetch_order,
    fetch_bids_for_order,
    fetch_trip_for_order,
    calculate_no_show_penalty,
    order_access_for_user,
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

    # Posting an order needs no wallet and no advance payment: everyday users
    # never get a wallet, and business clients pay only when accepting a bid.

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
        order_id = db.execute(
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open',
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
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
        # both the goods' truck TYPE and its weight/volume CAPACITY.
        my_trucks = [
            dict(r)
            for r in db.execute(
                "SELECT catalog_type_key, truck_type, capacity_tons, payload_max_tons, volume_max_cbm, "
                "bed_length_ft, bed_width_ft, bed_height_ft "
                "FROM vehicles WHERE owner_user_id = %s AND status = 'active'",
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
            "SELECT * FROM vehicles WHERE id = %s AND owner_user_id = %s AND status = 'active'",
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
            "SELECT id FROM shipment_bids WHERE order_id = %s AND transporter_user_id = %s AND status IN ('pending', 'accepted')",
            (order_id, request.current_user["id"]),
        ).fetchone()
        if existing_bid:
            return json_response({"success": False, "message": "You already have an active bid on this order."}, 400)

        stamp = timestamp_bundle()["display"]
        bid_id = db.execute(
            """
            INSERT INTO shipment_bids (
                order_id, transporter_user_id, truck_id, bid_price, message, status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)
            RETURNING id
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
        ).fetchone()["id"]
        bid = db.execute("SELECT * FROM shipment_bids WHERE id = %s", (bid_id,)).fetchone()
        db.commit()

    return json_response({
        "success": True,
        "message": "Bid placed successfully.",
        "bid": serialize_bid(dict(bid)),
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
            bids = fetch_bids_for_order(db, order_id)
            payment_summary = serialize_payment_summary(payment, viewer="client")
        else:
            bids = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM shipment_bids WHERE order_id = %s AND transporter_user_id = %s",
                    (order_id, request.current_user["id"]),
                ).fetchall()
            ]
            payment_summary = serialize_payment_summary(payment, viewer="transporter")

    return json_response({
        "success": True,
        "access": access,
        "order": serialize_order(order),
        "bids": [serialize_bid(b) for b in bids],
        "trip": serialize_trip(trip) if trip else None,
        "payment": payment_summary,
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
        bid = db.execute(
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
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
    if not idempotency_key:
        idempotency_key = f"chk-{order_id}-{bid_id}-{uuid4().hex}"

    with open_db() as db:
        try:
            result = perform_checkout(
                db, request.current_user, order_id, bid_id,
                payload=payload, idempotency_key=idempotency_key,
            )
        except CheckoutError as exc:
            db.rollback()
            return _checkout_error_response(exc)
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


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/mark-completed")
@login_required
def mark_trip_completed(order_id, trip_id):
    """Transporter marks trip as completed."""
    err = csrf_error()
    if err:
        return err

    with open_db() as db:
        trip = db.execute("SELECT * FROM shipment_trips WHERE id = %s AND order_id = %s", (trip_id, order_id)).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)

        if trip["transporter_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        if trip["status"] != "in_progress":
            return json_response({"success": False, "message": "Trip is not in progress."}, 400)

        stamp = timestamp_bundle()["display"]

        # Update trip status
        db.execute(
            "UPDATE shipment_trips SET status = 'delivery_claimed', trip_completed_at = %s, updated_at = %s WHERE id = %s",
            (stamp, stamp, trip_id),
        )

        # Create verification record
        db.execute(
            """
            INSERT INTO shipment_trip_verification (
                trip_id, transporter_claim_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s)
            """,
            (trip_id, stamp, stamp, stamp),
        )

        db.commit()
        trip = db.execute("SELECT * FROM shipment_trips WHERE id = %s", (trip_id,)).fetchone()

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

        trip = db.execute("SELECT * FROM shipment_trips WHERE id = %s AND order_id = %s", (trip_id, order_id)).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)

        if trip["status"] not in ("delivery_claimed", "first_response_pending"):
            return json_response({"success": False, "message": "Trip cannot be verified."}, 400)

        stamp = timestamp_bundle()["display"]

        # Get verification record
        verification = db.execute(
            "SELECT * FROM shipment_trip_verification WHERE trip_id = %s",
            (trip_id,),
        ).fetchone()

        if not verification:
            return json_response({"success": False, "message": "Verification record not found."}, 404)

        # Orders paid through the new held-payment checkout release the payout
        # in the delivery-confirmation phase (not yet implemented). Only
        # legacy wallet-paid trips keep the old immediate-credit behaviour —
        # crediting a held-payment order here would double-pay.
        held_payment = get_active_payment_for_shipment(db, order_id, statuses=("processing", "held"))
        if held_payment:
            return json_response(
                {
                    "success": False,
                    "code": "payout_release_later_phase",
                    "message": "Delivery confirmation and payout release for this order are handled "
                               "in the upcoming delivery-verification flow.",
                },
                409,
            )

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
                "UPDATE shipment_trips SET status = 'completed', delivery_confirmed_at = %s, updated_at = %s WHERE id = %s",
                (stamp, stamp, trip_id),
            )

            # Update verification
            db.execute(
                "UPDATE shipment_trip_verification SET client_first_response = 'yes', client_first_response_at = %s, final_verification_status = 'confirmed', updated_at = %s WHERE trip_id = %s",
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    "UPDATE shipment_trip_verification SET client_first_response = 'no', client_first_response_at = %s, updated_at = %s WHERE trip_id = %s",
                    (stamp, stamp, trip_id),
                )
                db.execute(
                    "UPDATE shipment_trips SET status = 'first_response_pending', updated_at = %s WHERE id = %s",
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
                    "UPDATE shipment_trip_verification SET client_second_response = 'no', client_second_response_at = %s, final_verification_status = 'pending_admin', updated_at = %s WHERE trip_id = %s",
                    (stamp, stamp, trip_id),
                )
                db.execute(
                    "UPDATE shipment_trips SET status = 'dispute_pending', updated_at = %s WHERE id = %s",
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
            "SELECT * FROM shipments WHERE client_user_id = %s ORDER BY created_at DESC",
            (request.current_user["id"],),
        ).fetchall()

        result = []
        for order in orders:
            order_dict = dict(order)
            bid_count = db.execute(
                "SELECT COUNT(*) as count FROM shipment_bids WHERE order_id = %s AND status != 'withdrawn'",
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
            WHERE ob.transporter_user_id = %s
            ORDER BY ob.created_at DESC
            """,
            (request.current_user["id"],),
        ).fetchall()

        result = [serialize_bid(dict(b)) for b in bids]

    return json_response({"success": True, "bids": result})
