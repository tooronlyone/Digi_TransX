from flask import Blueprint, request
from datetime import datetime, timedelta

from auth.helpers import json_response, login_required, require_csrf, timestamp_bundle
from shared.db import open_db
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
)

orders_blueprint = Blueprint("orders", __name__)


@orders_blueprint.post("/api/orders")
@login_required
def create_order():
    """Client creates a new one-time order."""
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}

    # Validate wallet
    wallet, wallet_error = get_or_create_wallet(request.current_user)
    if wallet_error:
        return wallet_error

    # Validate order data
    validation_error = validate_order_creation(data)
    if validation_error:
        return validation_error

    try:
        pickup_date = datetime.fromisoformat(data.get("pickup_date")).date()
        if pickup_date < datetime.now().date():
            return json_response({"success": False, "message": "Pickup date must be in the future."}, 400)
    except (ValueError, TypeError):
        return json_response({"success": False, "message": "Invalid pickup date format."}, 400)

    try:
        goods_weight_tons = float(data.get("goods_weight_tons", 0))
        goods_volume_cbm = float(data.get("goods_volume_cbm") or 0)
        estimated_budget = float(data.get("estimated_budget") or 0)
        if goods_weight_tons <= 0:
            raise ValueError("Weight must be greater than 0")
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Invalid goods weight or budget."}, 400)

    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        db.execute(
            """
            INSERT INTO orders (
                client_user_id, pickup_city, pickup_area, dropoff_city, dropoff_area,
                pickup_date, pickup_time, goods_type, goods_weight_tons, goods_volume_cbm,
                estimated_budget, notes, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                request.current_user["id"],
                data.get("pickup_city", "").strip(),
                data.get("pickup_area", "").strip(),
                data.get("dropoff_city", "").strip(),
                data.get("dropoff_area", "").strip(),
                pickup_date.isoformat(),
                data.get("pickup_time", "").strip(),
                data.get("goods_type", "").strip(),
                goods_weight_tons,
                goods_volume_cbm if goods_volume_cbm > 0 else None,
                estimated_budget if estimated_budget > 0 else None,
                data.get("notes", "").strip() or None,
                stamp,
                stamp,
            ),
        )
        order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Add required truck types
        truck_types = data.get("required_truck_types") or []
        if not truck_types:
            db.rollback()
            return json_response({"success": False, "message": "At least one truck type is required."}, 400)

        for truck_type in truck_types:
            db.execute(
                "INSERT INTO order_required_trucks (order_id, truck_type, quantity) VALUES (?, ?, 1)",
                (order_id, truck_type.strip()),
            )

        db.commit()
        order = fetch_order(db, order_id)
        truck_reqs = db.execute(
            "SELECT * FROM order_required_trucks WHERE order_id = ?",
            (order_id,)
        ).fetchall()

    return json_response({
        "success": True,
        "message": "Order posted successfully. Transporters can now bid.",
        "order": serialize_order(order, [dict(t) for t in truck_reqs]),
    })


@orders_blueprint.get("/api/orders/available")
@login_required
def available_orders():
    """Transporter sees available orders matching their active trucks."""
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error

    with open_db() as db:
        # Get transporter's active truck types
        truck_rows = db.execute(
            """
            SELECT DISTINCT catalog_type_key
            FROM trucks
            WHERE owner_user_id = ? AND status = 'active' AND catalog_type_key IS NOT NULL
            """,
            (request.current_user["id"],),
        ).fetchall()

        truck_types = [row["catalog_type_key"] for row in truck_rows]
        if not truck_types:
            return json_response({"success": True, "orders": []})

        # Get open orders matching truck types
        placeholders = ",".join("?" for _ in truck_types)
        order_rows = db.execute(
            f"""
            SELECT o.*, COUNT(DISTINCT ob.id) AS bid_count
            FROM orders o
            LEFT JOIN order_bids ob ON ob.order_id = o.id AND ob.status != 'withdrawn'
            WHERE o.status = 'open'
              AND EXISTS (
                SELECT 1 FROM order_required_trucks ort
                WHERE ort.order_id = o.id AND ort.truck_type IN ({placeholders})
              )
            GROUP BY o.id
            ORDER BY o.created_at DESC
            """,
            tuple(truck_types),
        ).fetchall()

        orders = []
        for row in order_rows:
            row_dict = dict(row)
            truck_reqs = db.execute(
                "SELECT * FROM order_required_trucks WHERE order_id = ?",
                (row_dict["id"],),
            ).fetchall()
            orders.append(serialize_order(row_dict, [dict(t) for t in truck_reqs], row_dict.get("bid_count", 0)))

    return json_response({"success": True, "orders": orders})


@orders_blueprint.post("/api/orders/<int:order_id>/bids")
@login_required
def create_bid(order_id):
    """Transporter places a bid on an order."""
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

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
            "SELECT * FROM trucks WHERE id = ? AND owner_user_id = ? AND status = 'active'",
            (truck_id, request.current_user["id"]),
        ).fetchone()
        if not truck:
            return json_response({"success": False, "message": "Truck not found or not active."}, 404)

        # Check for duplicate bids
        existing_bid = db.execute(
            "SELECT id FROM order_bids WHERE order_id = ? AND transporter_user_id = ? AND status IN ('pending', 'accepted')",
            (order_id, request.current_user["id"]),
        ).fetchone()
        if existing_bid:
            return json_response({"success": False, "message": "You already have an active bid on this order."}, 400)

        stamp = timestamp_bundle()["display"]
        db.execute(
            """
            INSERT INTO order_bids (
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
        bid = db.execute("SELECT * FROM order_bids WHERE id = ?", (bid_id,)).fetchone()
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

        truck_reqs = db.execute(
            "SELECT * FROM order_required_trucks WHERE order_id = ?",
            (order_id,),
        ).fetchall()

        bids = fetch_bids_for_order(db, order_id)

    return json_response({
        "success": True,
        "order": serialize_order(order, [dict(t) for t in truck_reqs]),
        "bids": [serialize_bid(b) for b in bids],
    })


@orders_blueprint.post("/api/orders/<int:order_id>/accept-bid/<int:bid_id>")
@login_required
def accept_bid(order_id, bid_id):
    """Client accepts a bid and creates a trip."""
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        if order["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        if order["status"] != "open":
            return json_response({"success": False, "message": "Order is not open for bids."}, 400)

        bid = db.execute("SELECT * FROM order_bids WHERE id = ? AND order_id = ?", (bid_id, order_id)).fetchone()
        if not bid:
            return json_response({"success": False, "message": "Bid not found."}, 404)

        if bid["status"] != "pending":
            return json_response({"success": False, "message": "Bid cannot be accepted."}, 400)

        stamp = timestamp_bundle()["display"]

        # Update order status
        db.execute(
            "UPDATE orders SET status = 'accepted', accepted_bid_id = ?, payment_amount = ?, updated_at = ? WHERE id = ?",
            (bid_id, round_money(bid["bid_price"]), stamp, order_id),
        )

        # Update bid status
        db.execute(
            "UPDATE order_bids SET status = 'accepted', updated_at = ? WHERE id = ?",
            (stamp, bid_id),
        )

        # Reject other bids
        db.execute(
            "UPDATE order_bids SET status = 'rejected', updated_at = ? WHERE order_id = ? AND id != ?",
            (stamp, order_id, bid_id),
        )

        # Create trip
        db.execute(
            """
            INSERT INTO order_trips (
                order_id, accepted_bid_id, transporter_user_id, truck_id, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'accepted', ?, ?)
            """,
            (order_id, bid_id, bid["transporter_user_id"], bid["truck_id"], stamp, stamp),
        )
        trip_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create no-show tracking
        db.execute(
            "INSERT INTO order_no_show_tracking (trip_id, status, created_at, updated_at) VALUES (?, 'tracking', ?, ?)",
            (trip_id, stamp, stamp),
        )

        db.commit()

        trip = db.execute("SELECT * FROM order_trips WHERE id = ?", (trip_id,)).fetchone()
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
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    with open_db() as db:
        order = fetch_order(db, order_id)
        if not order:
            return json_response({"success": False, "message": "Order not found."}, 404)

        if order["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        trip = db.execute("SELECT * FROM order_trips WHERE id = ? AND order_id = ?", (trip_id, order_id)).fetchone()
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
            "UPDATE order_trips SET status = 'in_progress', trip_started_at = ?, updated_at = ? WHERE id = ?",
            (stamp, stamp, trip_id),
        )
        db.execute(
            "UPDATE orders SET payment_status = 'paid', updated_at = ? WHERE id = ?",
            (stamp, order_id),
        )

        db.commit()
        trip = db.execute("SELECT * FROM order_trips WHERE id = ?", (trip_id,)).fetchone()

    return json_response({
        "success": True,
        "message": "Payment processed. Trip started. Transporter can now pickup goods.",
        "trip": serialize_trip(dict(trip)),
    })


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/mark-completed")
@login_required
def mark_trip_completed(order_id, trip_id):
    """Transporter marks trip as completed."""
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    with open_db() as db:
        trip = db.execute("SELECT * FROM order_trips WHERE id = ? AND order_id = ?", (trip_id, order_id)).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)

        if trip["transporter_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Access denied."}, 403)

        if trip["status"] != "in_progress":
            return json_response({"success": False, "message": "Trip is not in progress."}, 400)

        stamp = timestamp_bundle()["display"]

        # Update trip status
        db.execute(
            "UPDATE order_trips SET status = 'delivery_claimed', trip_completed_at = ?, updated_at = ? WHERE id = ?",
            (stamp, stamp, trip_id),
        )

        # Create verification record
        db.execute(
            """
            INSERT INTO order_trip_verification (
                trip_id, transporter_claim_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (trip_id, stamp, stamp, stamp),
        )

        db.commit()
        trip = db.execute("SELECT * FROM order_trips WHERE id = ?", (trip_id,)).fetchone()

    return json_response({
        "success": True,
        "message": "Delivery marked as completed. Awaiting client verification.",
        "trip": serialize_trip(dict(trip)),
    })


@orders_blueprint.post("/api/orders/<int:order_id>/trips/<int:trip_id>/verify-delivery")
@login_required
def verify_delivery(order_id, trip_id):
    """Client verifies delivery."""
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

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

        trip = db.execute("SELECT * FROM order_trips WHERE id = ? AND order_id = ?", (trip_id, order_id)).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)

        if trip["status"] not in ("delivery_claimed", "first_response_pending"):
            return json_response({"success": False, "message": "Trip cannot be verified."}, 400)

        stamp = timestamp_bundle()["display"]

        # Get verification record
        verification = db.execute(
            "SELECT * FROM order_trip_verification WHERE trip_id = ?",
            (trip_id,),
        ).fetchone()

        if not verification:
            return json_response({"success": False, "message": "Verification record not found."}, 404)

        if response == "yes":
            # Payment successful
            trip_obj = dict(trip)
            transporter_wallet, _ = get_or_create_wallet({"id": trip_obj["transporter_user_id"], "role": "transporter"})

            payment_amount = round_money(order["payment_amount"])
            company_fee = round_money(payment_amount * 0.20)
            transporter_amount = round_money(payment_amount - company_fee)

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
                "UPDATE order_trips SET status = 'completed', delivery_confirmed_at = ?, updated_at = ? WHERE id = ?",
                (stamp, stamp, trip_id),
            )

            # Update verification
            db.execute(
                "UPDATE order_trip_verification SET client_first_response = 'yes', client_first_response_at = ?, final_verification_status = 'confirmed', updated_at = ? WHERE trip_id = ?",
                (stamp, stamp, trip_id),
            )

            # Create invoice
            db.execute(
                """
                INSERT INTO order_invoices (
                    trip_id, invoice_number, client_user_id, transporter_user_id,
                    bid_price, company_fee, transporter_amount, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trip_id,
                    f"ORD-{order_id}-{trip_id}-{datetime.now().strftime('%Y%m%d')}",
                    order["client_user_id"],
                    trip_obj["transporter_user_id"],
                    payment_amount,
                    company_fee,
                    transporter_amount,
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
                    "UPDATE order_trip_verification SET client_first_response = 'no', client_first_response_at = ?, updated_at = ? WHERE trip_id = ?",
                    (stamp, stamp, trip_id),
                )
                db.execute(
                    "UPDATE order_trips SET status = 'first_response_pending', updated_at = ? WHERE id = ?",
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
                    "UPDATE order_trip_verification SET client_second_response = 'no', client_second_response_at = ?, final_verification_status = 'pending_admin', updated_at = ? WHERE trip_id = ?",
                    (stamp, stamp, trip_id),
                )
                db.execute(
                    "UPDATE order_trips SET status = 'dispute_pending', updated_at = ? WHERE id = ?",
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
            "SELECT * FROM orders WHERE client_user_id = ? ORDER BY created_at DESC",
            (request.current_user["id"],),
        ).fetchall()

        result = []
        for order in orders:
            order_dict = dict(order)
            truck_reqs = db.execute(
                "SELECT * FROM order_required_trucks WHERE order_id = ?",
                (order_dict["id"],),
            ).fetchall()
            bid_count = db.execute(
                "SELECT COUNT(*) as count FROM order_bids WHERE order_id = ? AND status != 'withdrawn'",
                (order_dict["id"],),
            ).fetchone()["count"]
            result.append(serialize_order(order_dict, [dict(t) for t in truck_reqs], bid_count))

    return json_response({"success": True, "orders": result})


@orders_blueprint.get("/api/orders/my-bids")
@login_required
def get_my_bids():
    """Transporter views their bids."""
    with open_db() as db:
        bids = db.execute(
            """
            SELECT ob.*, o.pickup_city, o.dropoff_city, o.pickup_date, o.goods_type, o.estimated_budget
            FROM order_bids ob
            JOIN orders o ON o.id = ob.order_id
            WHERE ob.transporter_user_id = ?
            ORDER BY ob.created_at DESC
            """,
            (request.current_user["id"],),
        ).fetchall()

        result = [serialize_bid(dict(b)) for b in bids]

    return json_response({"success": True, "bids": result})
