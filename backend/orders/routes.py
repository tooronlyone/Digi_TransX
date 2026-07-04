from datetime import datetime, timedelta

from flask import Blueprint, request

from auth.helpers import json_response, login_required, require_csrf, timestamp_bundle
from chat.helpers import create_thread_for_bid
from shared.db import open_db
from trucks.helpers import get_catalog_type
from wallet.helpers import adjust_wallet_balance, available_balance, ensure_wallet_locked_balance, get_or_create_wallet, get_or_create_wallet_for_user, insert_wallet_transaction, round_money
from .helpers import (
    BID_STATUS_ACCEPTED,
    BID_STATUS_NOT_SELECTED,
    BID_STATUS_PENDING,
    BID_STATUS_WITHDRAWN,
    CANCELLATION_STATUS_PENDING,
    NEGOTIATION_DEFAULT_HOURS,
    NEGOTIATION_MAX_PERCENT,
    NEGOTIATION_MIN_PERCENT,
    MINIMUM_ORDER_WALLET_BALANCE,
    ORDER_STATUS_OPEN,
    ORDER_STATUS_ACCEPTED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_IN_PROGRESS,
    ORDER_STATUSES,
    PENALTY_TYPE_FIXED,
    PENALTY_TYPE_NEGOTIATED,
    TRIP_STAGE_COMPLETED,
    TRIP_STAGE_IN_CITY,
    TRIP_STAGE_LEFT_CITY,
    TRIP_STAGE_LOADED,
    TRIP_STAGE_NOT_STARTED,
    TRIP_STAGE_PROGRESS,
    TRANSPORTER_ORDER_ROLES,
    accepted_bid_lookup,
    calculate_cancellation_amounts,
    check_expired_negotiations,
    client_wallet_shortfall_response,
    determine_cancellation_context,
    get_order_cancellation,
    has_minimum_available_balance,
    parse_optional_float,
    parse_optional_text,
    parse_iso_datetime,
    parse_required_positive_float,
    parse_required_text,
    require_client_role,
    require_transporter_role,
    serialize_cancellation,
    serialize_bid,
    serialize_order,
    settle_cancellation_payment,
    validate_required_truck_type,
)


orders_blueprint = Blueprint("orders", __name__)
COMPANY_FEE_RATE = 0.20
TRANSPORTER_SHARE_RATE = 0.80
TRANSPORTER_LOCK_CAP = 70000.0


def progressive_trip_lock_percentage(completed_trips_count):
    if completed_trips_count <= 1:
        return 5.0
    if completed_trips_count == 2:
        return 4.0
    if completed_trips_count == 3:
        return 3.0
    return 2.0


def settle_completed_order(db, order, accepted_bid):
    transporter_user = {"id": accepted_bid["transporter_user_id"], "role": accepted_bid.get("transporter_role") or "transporter"}
    transporter_wallet, wallet_error = get_or_create_wallet_for_user(db, transporter_user)
    if wallet_error:
        return None, wallet_error, None

    trip_total = round_money(accepted_bid["bid_price"])
    company_fee = round_money(trip_total * COMPANY_FEE_RATE)
    transporter_share = round_money(trip_total * TRANSPORTER_SHARE_RATE)
    completed_trips_count = int(transporter_wallet.get("completed_trips_count") or 0) + 1
    lock_percentage = progressive_trip_lock_percentage(completed_trips_count)
    current_locked = round_money(transporter_wallet["locked_balance"])
    remaining_lock_capacity = max(round_money(TRANSPORTER_LOCK_CAP - current_locked), 0)
    proposed_lock_amount = round_money(transporter_share * lock_percentage / 100)
    lock_amount = round_money(min(proposed_lock_amount, remaining_lock_capacity))

    balance_error = adjust_wallet_balance(
        db,
        transporter_wallet,
        accepted_bid["transporter_user_id"],
        transporter_share,
        "trip_income",
        description=f"Trip #{order['id']} income (80% share)",
        reference_id=str(order["id"]),
    )
    if balance_error:
        return None, balance_error, None

    stamp = timestamp_bundle()["display"]
    if lock_amount > 0:
        next_locked = round_money(current_locked + lock_amount)
        db.execute(
            """
            UPDATE wallets
            SET locked_balance = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (next_locked, stamp, transporter_wallet["id"], accepted_bid["transporter_user_id"]),
        )
        transporter_wallet["locked_balance"] = next_locked
        transporter_wallet["updated_at"] = stamp
        insert_wallet_transaction(
            db,
            transporter_wallet,
            accepted_bid["transporter_user_id"],
            "trip_lock",
            lock_amount,
            description=f"Trip #{completed_trips_count} security lock ({int(lock_percentage)}%)",
            reference_id=str(order["id"]),
        )

    db.execute(
        """
        UPDATE wallets
        SET completed_trips_count = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (completed_trips_count, stamp, transporter_wallet["id"], accepted_bid["transporter_user_id"]),
    )
    transporter_wallet["completed_trips_count"] = completed_trips_count
    transporter_wallet["updated_at"] = stamp
    insert_wallet_transaction(
        db,
        transporter_wallet,
        accepted_bid["transporter_user_id"],
        "company_fee_earned",
        company_fee,
        description=f"Company fee recorded for trip #{order['id']}",
        reference_id=str(order["id"]),
    )
    db.execute(
        "UPDATE orders SET trip_stage = ?, status = ?, updated_at = ? WHERE id = ?",
        (TRIP_STAGE_COMPLETED, ORDER_STATUS_COMPLETED, stamp, order["id"]),
    )
    updated = db.execute("SELECT * FROM orders WHERE id = ?", (order["id"],)).fetchone()
    settlement = {
        "trip_total": trip_total,
        "company_fee": company_fee,
        "transporter_share": transporter_share,
        "completed_trips_count": completed_trips_count,
        "lock_percentage": lock_percentage,
        "lock_amount": lock_amount,
    }
    return (dict(updated) if updated else None), None, settlement


def get_order_by_id(order_id):
    with open_db() as db:
        row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return dict(row) if row else None


def get_order_or_404(order_id):
    order = get_order_by_id(order_id)
    if not order:
        return None, json_response({"success": False, "message": "Order not found."}, 404)
    return order, None


def ensure_order_owner(order, user_id):
    if order["client_user_id"] != user_id:
        return json_response({"success": False, "message": "You are not allowed to access this order."}, 403)
    return None


def get_bid_by_id(order_id, bid_id):
    with open_db() as db:
        row = db.execute("SELECT * FROM order_bids WHERE id = ? AND order_id = ?", (bid_id, order_id)).fetchone()
    return dict(row) if row else None


def run_order_lazy_checks(db):
    check_expired_negotiations(db)


def can_manage_order_cancellation(order, accepted_bid, user_id):
    return order["client_user_id"] == user_id or ((accepted_bid or {}).get("transporter_user_id") == user_id)


def fetch_cancellation_with_order(db, order_id):
    row = db.execute(
        """
        SELECT oc.*, o.client_user_id, o.accepted_bid_id, o.accepted_at, o.trip_stage
        FROM order_cancellations oc
        JOIN orders o ON o.id = oc.order_id
        WHERE oc.order_id = ?
        ORDER BY oc.id DESC
        LIMIT 1
        """,
        (order_id,),
    ).fetchone()
    return dict(row) if row else None


@orders_blueprint.post("/api/orders")
@login_required
def create_order():
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    try:
        pickup_city = parse_required_text(data, "pickup_city", "Pickup city")
        dropoff_city = parse_required_text(data, "dropoff_city", "Dropoff city")
        pickup_date = parse_required_text(data, "pickup_date", "Pickup date")
        pickup_time = parse_required_text(data, "pickup_time", "Pickup time")
        goods_type = parse_required_text(data, "goods_type", "Goods type")
        goods_weight_tons = parse_required_positive_float(data, "goods_weight_tons", "Goods weight")
        goods_volume_cbm = parse_optional_float(data, "goods_volume_cbm", "Goods volume")
        estimated_budget = parse_optional_float(data, "estimated_budget", "Estimated budget")
        required_truck_type = validate_required_truck_type(parse_required_text(data, "required_truck_type", "Required truck type"))
        pickup_area = parse_optional_text(data, "pickup_area")
        dropoff_area = parse_optional_text(data, "dropoff_area")
        notes = parse_optional_text(data, "notes")
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    wallet, error = get_or_create_wallet(request.current_user)
    if error:
        return error
    if not has_minimum_available_balance(wallet):
        return client_wallet_shortfall_response()

    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        db.execute(
            """
            INSERT INTO orders (
                client_user_id, pickup_city, pickup_area, dropoff_city, dropoff_area,
                pickup_date, pickup_time, goods_type, goods_weight_tons, goods_volume_cbm,
                required_truck_type, estimated_budget, notes, status, accepted_bid_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', NULL, ?, ?)
            """,
            (
                request.current_user["id"],
                pickup_city,
                pickup_area,
                dropoff_city,
                dropoff_area,
                pickup_date,
                pickup_time,
                goods_type,
                goods_weight_tons,
                goods_volume_cbm,
                required_truck_type,
                estimated_budget,
                notes,
                stamp,
                stamp,
            ),
        )
        order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        current_wallet = db.execute("SELECT * FROM wallets WHERE user_id = ?", (request.current_user["id"],)).fetchone()
        wallet_row = dict(current_wallet) if current_wallet else wallet
        lock_error = ensure_wallet_locked_balance(
            db,
            wallet_row,
            request.current_user["id"],
            MINIMUM_ORDER_WALLET_BALANCE,
            reason="order_placement",
            reference_id=str(order_id),
        )
        if lock_error:
            db.rollback()
            return lock_error
        db.commit()
        created = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    return json_response({"success": True, "order": serialize_order(dict(created))})


@orders_blueprint.get("/api/orders/mine")
@login_required
def list_my_orders():
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error

    requested_status = (request.args.get("status") or "").strip().lower()
    if requested_status and requested_status not in ORDER_STATUSES:
        return json_response({"success": False, "message": "Invalid order status filter."}, 400)

    query = """
        SELECT o.*, COUNT(ob.id) AS bid_count
        FROM orders o
        LEFT JOIN order_bids ob ON ob.order_id = o.id AND ob.status <> 'withdrawn'
        WHERE o.client_user_id = ?
    """
    params = [request.current_user["id"]]
    if requested_status:
        query += " AND o.status = ?"
        params.append(requested_status)
    query += " GROUP BY o.id ORDER BY o.id DESC"

    with open_db() as db:
        run_order_lazy_checks(db)
        rows = db.execute(query, tuple(params)).fetchall()

    return json_response({"success": True, "orders": [serialize_order(dict(row), row["bid_count"]) for row in rows]})


@orders_blueprint.get("/api/orders/<int:order_id>/bids")
@login_required
def list_order_bids(order_id):
    order, error = get_order_or_404(order_id)
    if error:
        return error
    owner_error = ensure_order_owner(order, request.current_user["id"])
    if owner_error:
        return owner_error

    with open_db() as db:
        run_order_lazy_checks(db)
        rows = db.execute(
            """
            SELECT
                ob.*,
                COALESCE(NULLIF(trim(u.full_name), ''), trim(COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '')), u.email, 'Transporter') AS transporter_name,
                NULL AS transporter_rating,
                t.truck_number,
                t.truck_type,
                t.catalog_type_key
            FROM order_bids ob
            JOIN users u ON u.id = ob.transporter_user_id
            JOIN trucks t ON t.id = ob.truck_id
            WHERE ob.order_id = ?
            ORDER BY
                CASE ob.status
                    WHEN 'accepted' THEN 0
                    WHEN 'pending' THEN 1
                    WHEN 'not_selected' THEN 2
                    ELSE 3
                END,
                ob.bid_price ASC,
                ob.id ASC
            """,
            (order_id,),
        ).fetchall()

    return json_response(
        {
            "success": True,
            "order": serialize_order(order),
            "bids": [serialize_bid(dict(row)) for row in rows],
        }
    )


@orders_blueprint.post("/api/orders/<int:order_id>/bids/<int:bid_id>/accept")
@login_required
def accept_bid(order_id, bid_id):
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    order, error = get_order_or_404(order_id)
    if error:
        return error
    owner_error = ensure_order_owner(order, request.current_user["id"])
    if owner_error:
        return owner_error
    if order["status"] != ORDER_STATUS_OPEN:
        return json_response({"success": False, "message": "Only open orders can accept bids."}, 400)

    bid = get_bid_by_id(order_id, bid_id)
    if not bid:
        return json_response({"success": False, "message": "Bid not found."}, 404)
    if bid["status"] != BID_STATUS_PENDING:
        return json_response({"success": False, "message": "Only pending bids can be accepted."}, 400)

    # Risk 1 fix: client ka available balance >= bid price hona chahiye
    client_wallet, wallet_error = get_or_create_wallet(request.current_user)
    if wallet_error:
        return wallet_error
    bid_price = round_money(bid["bid_price"])
    client_available = available_balance(client_wallet)
    if client_available + 1e-9 < bid_price:
        shortfall = round_money(bid_price - client_available)
        return json_response(
            {
                "success": False,
                "message": f"Insufficient wallet balance to accept this bid. Bid amount is Rs {bid_price:,.0f} but your available balance is Rs {client_available:,.0f}. Please add Rs {shortfall:,.0f} to your wallet.",
                "bid_price": bid_price,
                "available_balance": client_available,
                "shortfall": shortfall,
            },
            400,
        )

    stamp = timestamp_bundle()["display"]
    accepted_at = timestamp_bundle()["iso"]
    with open_db() as db:
        db.execute(
            """
            UPDATE orders
            SET status = 'accepted', accepted_bid_id = ?, accepted_at = ?, trip_stage = ?, updated_at = ?
            WHERE id = ? AND client_user_id = ?
            """,
            (bid_id, accepted_at, TRIP_STAGE_NOT_STARTED, stamp, order_id, request.current_user["id"]),
        )
        db.execute(
            "UPDATE order_bids SET status = 'accepted', updated_at = ? WHERE id = ? AND order_id = ?",
            (stamp, bid_id, order_id),
        )
        db.execute(
            "UPDATE order_bids SET status = 'not_selected', updated_at = ? WHERE order_id = ? AND id <> ? AND status = 'pending'",
            (stamp, order_id, bid_id),
        )
        db.commit()
        updated = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    return json_response(
        {
            "success": True,
            "order": serialize_order(dict(updated)),
            "message": "Bid accepted successfully",
        }
    )


@orders_blueprint.get("/api/orders/available")
@login_required
def list_available_orders():
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error

    with open_db() as db:
        run_order_lazy_checks(db)
        truck_type_rows = db.execute(
            """
            SELECT DISTINCT catalog_type_key
            FROM trucks
            WHERE owner_user_id = ? AND status = 'active' AND catalog_type_key IS NOT NULL AND trim(catalog_type_key) <> ''
            """,
            (request.current_user["id"],),
        ).fetchall()
        truck_type_keys = [row["catalog_type_key"] for row in truck_type_rows]
        if not truck_type_keys:
            return json_response({"success": True, "orders": []})

        placeholders = ",".join("?" for _ in truck_type_keys)
        rows = db.execute(
            f"""
            SELECT o.*, COUNT(ob.id) AS bid_count
            FROM orders o
            LEFT JOIN order_bids ob ON ob.order_id = o.id AND ob.status <> 'withdrawn'
            WHERE o.status = 'open' AND o.required_truck_type IN ({placeholders})
            GROUP BY o.id
            ORDER BY o.id DESC
            """,
            tuple(truck_type_keys),
        ).fetchall()

    return json_response({"success": True, "orders": [serialize_order(dict(row), row["bid_count"]) for row in rows]})


@orders_blueprint.post("/api/orders/<int:order_id>/bids")
@login_required
def create_bid(order_id):
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    order, error = get_order_or_404(order_id)
    if error:
        return error
    if order["status"] != ORDER_STATUS_OPEN:
        return json_response({"success": False, "message": "This order is no longer accepting bids"}, 400)

    try:
        truck_id = int(data.get("truck_id"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Truck is required."}, 400)

    try:
        bid_price = parse_required_positive_float(data, "bid_price", "Bid price")
        message = parse_optional_text(data, "message")
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    with open_db() as db:
        wallet_row = db.execute("SELECT * FROM wallets WHERE user_id = ?", (request.current_user["id"],)).fetchone()
        if wallet_row:
            transporter_wallet = dict(wallet_row)
        else:
            transporter_wallet, wallet_error = get_or_create_wallet_for_user(db, request.current_user)
            if wallet_error:
                return wallet_error
        if round_money(transporter_wallet["locked_balance"]) + 1e-9 < round_money(transporter_wallet["minimum_required"]):
            return json_response(
                {
                    "success": False,
                    "message": "Your security deposit is below the required minimum. Please top up your wallet before placing a bid.",
                },
                400,
            )

        truck_row = db.execute("SELECT * FROM trucks WHERE id = ?", (truck_id,)).fetchone()
        if not truck_row:
            return json_response({"success": False, "message": "Selected truck not found."}, 404)
        truck = dict(truck_row)
        if truck["owner_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "You can only bid with your own truck."}, 403)
        if truck["status"] != "active":
            return json_response({"success": False, "message": "Selected truck must be active to place a bid."}, 400)
        if (truck.get("catalog_type_key") or "").strip() != order["required_truck_type"]:
            required = get_catalog_type(order["required_truck_type"])
            return json_response(
                {
                    "success": False,
                    "message": f"Selected truck type does not match this order. Required: {required.get('display_name') if required else order['required_truck_type']}.",
                },
                400,
            )

        existing_bid = db.execute(
            """
            SELECT id FROM order_bids
            WHERE order_id = ? AND transporter_user_id = ? AND status = 'pending'
            LIMIT 1
            """,
            (order_id, request.current_user["id"]),
        ).fetchone()
        if existing_bid:
            return json_response(
                {
                    "success": False,
                    "message": "You already have a pending bid on this order, withdraw it first to bid again",
                },
                400,
            )

        stamp = timestamp_bundle()["display"]
        db.execute(
            """
            INSERT INTO order_bids (
                order_id, transporter_user_id, truck_id, bid_price, message, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (order_id, request.current_user["id"], truck_id, bid_price, message, stamp, stamp),
        )
        bid_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        create_thread_for_bid(db, order, request.current_user["id"], bid_id=bid_id)
        db.commit()
        created = db.execute(
            """
            SELECT
                ob.*,
                COALESCE(NULLIF(trim(u.full_name), ''), trim(COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '')), u.email, 'Transporter') AS transporter_name,
                NULL AS transporter_rating,
                t.truck_number,
                t.truck_type,
                t.catalog_type_key
            FROM order_bids ob
            JOIN users u ON u.id = ob.transporter_user_id
            JOIN trucks t ON t.id = ob.truck_id
            WHERE ob.id = ?
            """,
            (bid_id,),
        ).fetchone()

    return json_response({"success": True, "bid": serialize_bid(dict(created))})


@orders_blueprint.get("/api/orders/my-bids")
@login_required
def list_my_bids():
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error

    with open_db() as db:
        run_order_lazy_checks(db)
        rows = db.execute(
            """
            SELECT
                ob.*,
                o.pickup_city,
                o.pickup_area,
                o.dropoff_city,
                o.dropoff_area,
                o.pickup_date,
                o.pickup_time,
                o.goods_type,
                o.goods_weight_tons,
                o.required_truck_type,
                o.status AS order_status,
                o.trip_stage,
                o.trip_started_at,
                o.accepted_at,
                t.truck_number,
                t.truck_type,
                t.catalog_type_key
            FROM order_bids ob
            JOIN orders o ON o.id = ob.order_id
            JOIN trucks t ON t.id = ob.truck_id
            WHERE ob.transporter_user_id = ?
            ORDER BY ob.id DESC
            """,
            (request.current_user["id"],),
        ).fetchall()

    bids = []
    for row in rows:
        item = dict(row)
        payload = serialize_bid(item)
        payload["order"] = {
            "id": item["order_id"],
            "pickup_city": item["pickup_city"],
            "pickup_area": item["pickup_area"] or "",
            "dropoff_city": item["dropoff_city"],
            "dropoff_area": item["dropoff_area"] or "",
            "pickup_date": item["pickup_date"],
            "pickup_time": item["pickup_time"],
            "goods_type": item["goods_type"],
            "goods_weight_tons": item["goods_weight_tons"],
            "required_truck_type": item["required_truck_type"],
            "required_truck_type_name": (get_catalog_type(item["required_truck_type"]) or {}).get("display_name", item["required_truck_type"]),
            "status": item["order_status"],
            "trip_stage": item["trip_stage"] or TRIP_STAGE_NOT_STARTED,
            "trip_started_at": item["trip_started_at"],
            "accepted_at": item["accepted_at"],
        }
        bids.append(payload)

    return json_response({"success": True, "bids": bids})


@orders_blueprint.post("/api/orders/<int:order_id>/trip/start")
@login_required
def start_trip(order_id):
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    order, error = get_order_or_404(order_id)
    if error:
        return error
    if order["status"] != ORDER_STATUS_ACCEPTED:
        return json_response({"success": False, "message": "Trip can only start after order acceptance."}, 400)

    with open_db() as db:
        accepted_bid = accepted_bid_lookup(db, order)
        if not accepted_bid or accepted_bid["transporter_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Only the accepted transporter can start this trip."}, 403)

        stamp = timestamp_bundle()
        db.execute(
            """
            UPDATE orders
            SET trip_started_at = ?, trip_stage = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (stamp["iso"], TRIP_STAGE_IN_CITY, ORDER_STATUS_IN_PROGRESS, stamp["display"], order_id),
        )
        db.commit()
        updated = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    return json_response({"success": True, "order": serialize_order(dict(updated))})


@orders_blueprint.put("/api/orders/<int:order_id>/trip/stage")
@login_required
def update_trip_stage(order_id):
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    stage = (data.get("stage") or "").strip().lower()
    if stage not in {TRIP_STAGE_LEFT_CITY, TRIP_STAGE_LOADED, TRIP_STAGE_COMPLETED}:
        return json_response({"success": False, "message": "Invalid trip stage."}, 400)

    order, error = get_order_or_404(order_id)
    if error:
        return error
    if order["status"] not in {ORDER_STATUS_ACCEPTED, ORDER_STATUS_IN_PROGRESS}:
        return json_response({"success": False, "message": "Trip stage cannot be updated for this order."}, 400)

    with open_db() as db:
        accepted_bid = accepted_bid_lookup(db, order)
        if not accepted_bid or accepted_bid["transporter_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Only the accepted transporter can update trip stage."}, 403)

        current_stage = (order.get("trip_stage") or TRIP_STAGE_NOT_STARTED).strip().lower()
        if TRIP_STAGE_PROGRESS.get(stage, -1) <= TRIP_STAGE_PROGRESS.get(current_stage, -1):
            return json_response({"success": False, "message": "Trip stage can only move forward."}, 400)

        if stage == TRIP_STAGE_COMPLETED:
            if current_stage != TRIP_STAGE_LOADED:
                return json_response({"success": False, "message": "Trip can only be completed after it reaches loaded stage."}, 400)
            updated, settle_error, settlement = settle_completed_order(db, order, accepted_bid)
            if settle_error:
                db.rollback()
                return settle_error
            db.commit()
            return json_response({"success": True, "order": serialize_order(updated), "settlement": settlement})

        stamp = timestamp_bundle()["display"]
        db.execute(
            "UPDATE orders SET trip_stage = ?, status = ?, updated_at = ? WHERE id = ?",
            (stage, ORDER_STATUS_IN_PROGRESS, stamp, order_id),
        )
        db.commit()
        updated = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    return json_response({"success": True, "order": serialize_order(dict(updated))})


@orders_blueprint.post("/api/orders/<int:order_id>/complete")
@login_required
def complete_order(order_id):
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    order, error = get_order_or_404(order_id)
    if error:
        return error
    if order["status"] != ORDER_STATUS_IN_PROGRESS:
        return json_response({"success": False, "message": "Only in-progress orders can be completed."}, 400)
    if (order.get("trip_stage") or "").strip().lower() != TRIP_STAGE_LOADED:
        return json_response({"success": False, "message": "Order must be at loaded stage before completion."}, 400)

    with open_db() as db:
        accepted_bid = accepted_bid_lookup(db, order)
        if not accepted_bid or accepted_bid["transporter_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Only the accepted transporter can complete this order."}, 403)

        updated, settle_error, settlement = settle_completed_order(db, order, accepted_bid)
        if settle_error:
            db.rollback()
            return settle_error
        db.commit()

    return json_response({"success": True, "order": serialize_order(updated), "settlement": settlement})


@orders_blueprint.post("/api/orders/<int:order_id>/cancel")
@login_required
def cancel_order(order_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    order, error = get_order_or_404(order_id)
    if error:
        return error
    if order["status"] not in {ORDER_STATUS_ACCEPTED, ORDER_STATUS_IN_PROGRESS}:
        return json_response({"success": False, "message": "Only accepted or in-progress orders can be cancelled."}, 400)

    with open_db() as db:
        accepted_bid = accepted_bid_lookup(db, order)
        if not accepted_bid:
            return json_response({"success": False, "message": "Accepted bid not found for this order."}, 400)
        if not can_manage_order_cancellation(order, accepted_bid, request.current_user["id"]):
            return json_response({"success": False, "message": "You are not allowed to cancel this order."}, 403)
        existing = get_order_cancellation(db, order_id)
        if existing:
            return json_response({"success": False, "message": "Cancellation already exists for this order."}, 400)

        cancelled_by = "client" if order["client_user_id"] == request.current_user["id"] else "transporter"
        other_party_user_id = accepted_bid["transporter_user_id"] if cancelled_by == "client" else order["client_user_id"]
        context = determine_cancellation_context(order, accepted_bid, cancelled_by)
        if not context:
            return json_response({"success": False, "message": "Unable to determine cancellation penalty."}, 400)

        stamp = timestamp_bundle()
        negotiation_deadline = None
        status = CANCELLATION_STATUS_PENDING
        penalty_percent = None
        penalty_amount = None
        company_share_percent = round_money(context["company_share_percent"])
        company_share_amount = None
        recipient_share_amount = None
        finalized_at = None
        if context["penalty_type"] == PENALTY_TYPE_FIXED:
            status = "finalized"
            computed = calculate_cancellation_amounts(context, context["penalty_percent"])
            penalty_percent = computed["penalty_percent"]
            penalty_amount = computed["penalty_amount"]
            company_share_amount = computed["company_share_amount"]
            recipient_share_amount = computed["recipient_share_amount"]
            finalized_at = stamp["iso"]
        else:
            negotiation_deadline = (datetime.now() + timedelta(hours=NEGOTIATION_DEFAULT_HOURS)).isoformat(timespec="seconds")

        db.execute(
            """
            INSERT INTO order_cancellations (
                order_id, cancelled_by, cancelled_by_user_id, other_party_user_id,
                trip_stage_at_cancellation, penalty_type, penalty_percent, penalty_amount,
                company_share_percent, company_share_amount, recipient_share_amount, status,
                negotiation_deadline, finalized_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                cancelled_by,
                request.current_user["id"],
                other_party_user_id,
                (order.get("trip_stage") or TRIP_STAGE_NOT_STARTED),
                context["penalty_type"],
                penalty_percent,
                penalty_amount,
                company_share_percent,
                company_share_amount,
                recipient_share_amount,
                status,
                negotiation_deadline,
                finalized_at,
                stamp["iso"],
                stamp["iso"],
            ),
        )
        if context["penalty_type"] == PENALTY_TYPE_FIXED:
            cancellation = get_order_cancellation(db, order_id)
            finalized, settle_error = settle_cancellation_payment(db, order, cancellation, context, context["penalty_percent"], finalized_at=stamp["iso"])
            if settle_error:
                db.rollback()
                return settle_error
            db.commit()
            return json_response(
                {
                    "success": True,
                    "cancellation": serialize_cancellation(finalized),
                    "message": f"Order cancelled. Penalty of Rs {finalized['penalty_amount']:.2f} applied.",
                }
            )

        db.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (ORDER_STATUS_CANCELLED, stamp["display"], order_id))
        db.commit()
        cancellation = get_order_cancellation(db, order_id)

    return json_response(
        {
            "success": True,
            "cancellation": serialize_cancellation(cancellation),
            "message": "Order cancelled. Penalty negotiation required - you have 48 hours to agree on a percentage between 10% and 25%.",
        }
    )


@orders_blueprint.post("/api/orders/<int:order_id>/cancellation/propose")
@login_required
def propose_cancellation(order_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    try:
        percent = float(data.get("percent"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Percent must be a valid number."}, 400)
    if percent < NEGOTIATION_MIN_PERCENT or percent > NEGOTIATION_MAX_PERCENT:
        return json_response({"success": False, "message": "Percent must be between 10 and 25."}, 400)

    with open_db() as db:
        cancellation = fetch_cancellation_with_order(db, order_id)
        if not cancellation or cancellation["status"] != CANCELLATION_STATUS_PENDING:
            return json_response({"success": False, "message": "No pending cancellation negotiation found."}, 404)

        order = get_order_by_id(order_id)
        accepted_bid = accepted_bid_lookup(db, order) if order else None
        if not order or not can_manage_order_cancellation(order, accepted_bid, request.current_user["id"]):
            return json_response({"success": False, "message": "You are not allowed to access this negotiation."}, 403)

        stamp = timestamp_bundle()["iso"]
        db.execute(
            """
            UPDATE order_cancellations
            SET proposed_percent = ?, proposed_by_user_id = ?, proposed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (round_money(percent), request.current_user["id"], stamp, stamp, cancellation["id"]),
        )
        db.commit()

    return json_response({"success": True, "message": "Proposal sent"})


@orders_blueprint.post("/api/orders/<int:order_id>/cancellation/accept")
@login_required
def accept_cancellation(order_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    with open_db() as db:
        cancellation = fetch_cancellation_with_order(db, order_id)
        if not cancellation or cancellation["status"] != CANCELLATION_STATUS_PENDING:
            return json_response({"success": False, "message": "No pending cancellation negotiation found."}, 404)
        if cancellation.get("proposed_percent") is None or not cancellation.get("proposed_by_user_id"):
            return json_response({"success": False, "message": "No proposal is available to accept."}, 400)
        if cancellation["proposed_by_user_id"] == request.current_user["id"]:
            return json_response({"success": False, "message": "Only the other party can accept this proposal."}, 403)

        order = get_order_by_id(order_id)
        accepted_bid = accepted_bid_lookup(db, order) if order else None
        if not order or not can_manage_order_cancellation(order, accepted_bid, request.current_user["id"]):
            return json_response({"success": False, "message": "You are not allowed to access this negotiation."}, 403)

        context = determine_cancellation_context(order, accepted_bid, cancellation["cancelled_by"])
        finalized, settle_error = settle_cancellation_payment(
            db,
            order,
            cancellation,
            context,
            cancellation["proposed_percent"],
            finalized_at=timestamp_bundle()["iso"],
        )
        if settle_error:
            db.rollback()
            return settle_error
        db.commit()

    return json_response({"success": True, "message": "Cancellation finalized", "cancellation": serialize_cancellation(finalized)})


@orders_blueprint.get("/api/orders/<int:order_id>/cancellation")
@login_required
def get_cancellation(order_id):
    order, error = get_order_or_404(order_id)
    if error:
        return error

    with open_db() as db:
        run_order_lazy_checks(db)
        accepted_bid = accepted_bid_lookup(db, order)
        if not accepted_bid or not can_manage_order_cancellation(order, accepted_bid, request.current_user["id"]):
            return json_response({"success": False, "message": "You are not allowed to access this cancellation."}, 403)

        cancellation = get_order_cancellation(db, order_id)
        if not cancellation:
            return json_response({"success": False, "message": "Cancellation record not found."}, 404)

    return json_response({"success": True, "cancellation": serialize_cancellation(cancellation)})


@orders_blueprint.post("/api/orders/<int:order_id>/bids/<int:bid_id>/withdraw")
@login_required
def withdraw_bid(order_id, bid_id):
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    bid = get_bid_by_id(order_id, bid_id)
    if not bid:
        return json_response({"success": False, "message": "Bid not found."}, 404)
    if bid["transporter_user_id"] != request.current_user["id"]:
        return json_response({"success": False, "message": "You are not allowed to withdraw this bid."}, 403)
    if bid["status"] == BID_STATUS_ACCEPTED:
        return json_response({"success": False, "message": "Cannot withdraw, bid already accepted"}, 400)
    if bid["status"] != BID_STATUS_PENDING:
        return json_response({"success": False, "message": "Bid no longer active"}, 400)

    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        db.execute(
            "UPDATE order_bids SET status = 'withdrawn', updated_at = ? WHERE id = ? AND order_id = ?",
            (stamp, bid_id, order_id),
        )
        db.commit()

    return json_response({"success": True, "message": "Bid withdrawn successfully"})
