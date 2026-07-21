from datetime import date, datetime

from flask import Blueprint, request

from auth.helpers import json_response, login_required, csrf_error, timestamp_bundle
from chat.routes import insert_chat_message
from shared.db import open_db
from tracking.traccar import calculate_route_distance_km, get_positions_between
from shared.commissions import (
    POLICY_TYPE_AGREEMENT,
    get_active_policy,
    get_current_terms_version,
    policy_company_share,
    recalculate_payment_fields,
    transporter_share_percent_for,
)
from wallet.helpers import adjust_wallet_balance, available_balance, get_or_create_wallet_for_user, round_money
from .helpers import (
    PENALTY_AMOUNT,
    add_months,
    due_date_for_month,
    haversine_km,
    month_key,
    parse_iso_date,
    parse_optional_text,
    parse_positive_float,
    parse_positive_int,
    parse_required_text,
    require_client_role,
    require_transporter_role,
    serialize_agreement,
    serialize_agreement_truck,
    serialize_bid,
    serialize_bid_truck,
    serialize_payment,
    serialize_post,
    serialize_required_truck,
    serialize_trip,
    service_area_to_text,
    process_payment_row,
    run_process_payments,
    run_apply_penalties,
)


agreements_blueprint = Blueprint("agreements", __name__)


def fetch_post(db, post_id):
    row = db.execute("SELECT * FROM agreement_posts WHERE id = ?", (post_id,)).fetchone()
    return dict(row) if row else None


def fetch_post_trucks(db, post_id):
    rows = db.execute(
        "SELECT * FROM agreement_post_trucks WHERE post_id = ? ORDER BY id ASC",
        (post_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_agreement(db, agreement_id):
    row = db.execute(
        """
        SELECT
            a.*,
            COALESCE(NULLIF(trim(u.full_name), ''), u.email, 'Client') AS client_name,
            COUNT(DISTINCT at.id) AS truck_count
        FROM agreements a
        JOIN users u ON u.id = a.client_user_id
        LEFT JOIN agreement_trucks at ON at.agreement_id = a.id
        WHERE a.id = ?
        GROUP BY a.id, u.id
        """,
        (agreement_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_agreement_trucks(db, agreement_id):
    rows = db.execute(
        """
        SELECT
            at.*,
            t.truck_number,
            t.truck_type,
            t.catalog_type_key,
            t.truck_photo_path,
            COALESCE(NULLIF(trim(u.full_name), ''), u.email, 'Transporter') AS transporter_name
        FROM agreement_trucks at
        JOIN vehicles t ON t.id = at.truck_id
        JOIN users u ON u.id = at.transporter_user_id
        WHERE at.agreement_id = ?
        ORDER BY at.id ASC
        """,
        (agreement_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def user_can_access_agreement(db, agreement, user):
    if agreement["client_user_id"] == user["id"]:
        return True
    row = db.execute(
        "SELECT id FROM agreement_trucks WHERE agreement_id = ? AND transporter_user_id = ? LIMIT 1",
        (agreement["id"], user["id"]),
    ).fetchone()
    return bool(row)


def active_gps_truck_where():
    return "status = 'active' AND tracking_id IS NOT NULL AND trim(tracking_id) <> ''"


def create_agreement_thread(db, post, transporter_user_id, bid_id=None):
    stamp = timestamp_bundle()["iso"]
    db.execute(
        """
        INSERT OR IGNORE INTO chat_threads (
            client_user_id, transporter_user_id, agreement_post_id, agreement_bid_id, last_message_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (post["client_user_id"], transporter_user_id, post["id"], bid_id, stamp, stamp),
    )
    db.execute(
        """
        UPDATE chat_threads
        SET agreement_bid_id = COALESCE(agreement_bid_id, ?), last_message_at = COALESCE(last_message_at, ?)
        WHERE agreement_post_id = ? AND transporter_user_id = ?
        """,
        (bid_id, stamp, post["id"], transporter_user_id),
    )
    row = db.execute(
        "SELECT id FROM chat_threads WHERE agreement_post_id = ? AND transporter_user_id = ?",
        (post["id"], transporter_user_id),
    ).fetchone()
    return row["id"] if row else None


def insert_system_note_for_agreement(db, agreement_id, transporter_user_id, content):
    agreement = fetch_agreement(db, agreement_id)
    if not agreement:
        return
    thread = db.execute(
        "SELECT id FROM chat_threads WHERE agreement_post_id = ? AND transporter_user_id = ?",
        (agreement["post_id"], transporter_user_id),
    ).fetchone()
    if thread:
        insert_chat_message(db, thread["id"], agreement["client_user_id"], "system", content=content)


@agreements_blueprint.post("/api/agreements/posts")
@login_required
def create_post():
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        title = parse_required_text(data, "title", "Title")
        cargo_type = parse_required_text(data, "cargo_type", "Cargo type")
        pickup_location = parse_required_text(data, "pickup_location", "Pickup location")
        dropoff_location = parse_required_text(data, "dropoff_location", "Dropoff location")
        service_area = service_area_to_text(data.get("service_area"))
        if not service_area:
            raise ValueError("Service area is required.")
        trucks = data.get("trucks") or []
        if not isinstance(trucks, list) or not trucks:
            raise ValueError("At least one truck requirement is required.")
        parsed_trucks = []
        for item in trucks:
            truck_type = parse_required_text(item, "truck_type", "Truck type")
            parsed_trucks.append(
                {
                    "truck_type": truck_type,
                    "capacity_tons": parse_positive_float(item.get("capacity_tons"), "Capacity"),
                    "quantity": parse_positive_int(item.get("quantity"), "Quantity"),
                }
            )
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        db.execute(
            """
            INSERT INTO agreement_posts (
                client_user_id, title, cargo_type, service_area, pickup_location, dropoff_location,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (request.current_user["id"], title, cargo_type, service_area, pickup_location, dropoff_location, stamp, stamp),
        )
        post_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for truck in parsed_trucks:
            db.execute(
                """
                INSERT INTO agreement_post_trucks (post_id, truck_type, capacity_tons, quantity)
                VALUES (?, ?, ?, ?)
                """,
                (post_id, truck["truck_type"], truck["capacity_tons"], truck["quantity"]),
            )
        db.commit()
        post = fetch_post(db, post_id)
        required = fetch_post_trucks(db, post_id)

    return json_response({"success": True, "post": serialize_post(post, [serialize_required_truck(row) for row in required])})


@agreements_blueprint.get("/api/agreements/posts/available")
@login_required
def available_posts():
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    with open_db() as db:
        truck_type_rows = db.execute(
            f"""
            SELECT DISTINCT catalog_type_key
            FROM vehicles
            WHERE owner_user_id = ? AND {active_gps_truck_where()}
              AND catalog_type_key IS NOT NULL AND trim(catalog_type_key) <> ''
            """,
            (request.current_user["id"],),
        ).fetchall()
        types = [row["catalog_type_key"] for row in truck_type_rows]
        if not types:
            return json_response({"success": True, "posts": []})
        placeholders = ",".join("?" for _ in types)
        rows = db.execute(
            f"""
            SELECT ap.*, COUNT(DISTINCT ab.id) AS bid_count
            FROM agreement_posts ap
            JOIN agreement_post_trucks apt ON apt.post_id = ap.id
            LEFT JOIN agreement_bids ab ON ab.post_id = ap.id AND ab.status <> 'withdrawn'
            WHERE ap.status = 'open' AND apt.truck_type IN ({placeholders})
            GROUP BY ap.id
            ORDER BY ap.id DESC
            """,
            tuple(types),
        ).fetchall()
        post_ids = [row["id"] for row in rows]
        requirements = {}
        if post_ids:
            req_rows = db.execute(
                f"SELECT * FROM agreement_post_trucks WHERE post_id IN ({','.join('?' for _ in post_ids)}) ORDER BY id ASC",
                tuple(post_ids),
            ).fetchall()
            for req in req_rows:
                requirements.setdefault(req["post_id"], []).append(serialize_required_truck(dict(req)))
    return json_response({"success": True, "posts": [serialize_post(dict(row), requirements.get(row["id"], []), row["bid_count"]) for row in rows]})


@agreements_blueprint.post("/api/agreements/posts/<int:post_id>/bids")
@login_required
def create_bid(post_id):
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    truck_items = data.get("trucks") or []
    if not isinstance(truck_items, list) or not truck_items:
        return json_response({"success": False, "message": "At least one truck is required."}, 400)

    try:
        message = parse_optional_text(data, "message")
        parsed = []
        for item in truck_items:
            parsed.append(
                {
                    "truck_id": parse_positive_int(item.get("truck_id"), "Truck"),
                    "per_km_rate": parse_positive_float(item.get("per_km_rate"), "Per KM rate"),
                    "minimum_monthly_guarantee": parse_positive_float(item.get("minimum_monthly_guarantee"), "Monthly minimum"),
                }
            )
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    with open_db() as db:
        post = fetch_post(db, post_id)
        if not post:
            return json_response({"success": False, "message": "Agreement post not found."}, 404)
        if post["status"] != "open":
            return json_response({"success": False, "message": "This post is not accepting bids."}, 400)
        existing = db.execute(
            "SELECT id FROM agreement_bids WHERE post_id = ? AND transporter_user_id = ? AND status IN ('pending', 'invited')",
            (post_id, request.current_user["id"]),
        ).fetchone()
        if existing:
            return json_response({"success": False, "message": "You already have an active bid on this post."}, 400)
        required_types = {row["truck_type"] for row in fetch_post_trucks(db, post_id)}
        truck_ids = [item["truck_id"] for item in parsed]
        rows = db.execute(
            f"""
            SELECT * FROM vehicles
            WHERE id IN ({','.join('?' for _ in truck_ids)})
              AND owner_user_id = ? AND {active_gps_truck_where()}
            """,
            (*truck_ids, request.current_user["id"]),
        ).fetchall()
        trucks = {row["id"]: dict(row) for row in rows}
        if len(trucks) != len(set(truck_ids)):
            return json_response({"success": False, "message": "All selected trucks must be your active GPS-enabled trucks."}, 400)
        for item in parsed:
            truck = trucks[item["truck_id"]]
            if (truck.get("catalog_type_key") or "").strip() not in required_types:
                return json_response({"success": False, "message": "Selected trucks must match the post's required truck types."}, 400)

        stamp = timestamp_bundle()["display"]
        db.execute(
            """
            INSERT INTO agreement_bids (post_id, transporter_user_id, status, message, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?, ?)
            """,
            (post_id, request.current_user["id"], message, stamp, stamp),
        )
        bid_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for item in parsed:
            db.execute(
                """
                INSERT INTO agreement_bid_trucks (bid_id, truck_id, per_km_rate, minimum_monthly_guarantee)
                VALUES (?, ?, ?, ?)
                """,
                (bid_id, item["truck_id"], item["per_km_rate"], item["minimum_monthly_guarantee"]),
        )
        db.commit()
        created = db.execute("SELECT * FROM agreement_bids WHERE id = ?", (bid_id,)).fetchone()
        truck_rows = db.execute(
            """
            SELECT abt.*, t.truck_number, t.truck_type, t.catalog_type_key, t.capacity_tons, t.truck_photo_path
            FROM agreement_bid_trucks abt
            JOIN vehicles t ON t.id = abt.truck_id
            WHERE abt.bid_id = ?
            ORDER BY abt.id ASC
            """,
            (bid_id,),
        ).fetchall()

    return json_response(
        {
            "success": True,
            "bid": serialize_bid(dict(created), [serialize_bid_truck(dict(row)) for row in truck_rows]),
        }
    )


@agreements_blueprint.get("/api/agreements/posts/<int:post_id>/bids")
@login_required
def list_bids(post_id):
    with open_db() as db:
        post = fetch_post(db, post_id)
        if not post:
            return json_response({"success": False, "message": "Agreement post not found."}, 404)
        if post["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "You are not allowed to view these bids."}, 403)
        required = fetch_post_trucks(db, post_id)
        required_counts = {}
        for item in required:
            required_counts[item["truck_type"]] = required_counts.get(item["truck_type"], 0) + int(item["quantity"] or 0)
        rows = db.execute(
            """
            SELECT
                ab.*,
                COALESCE(NULLIF(trim(u.full_name), ''), u.email, 'Transporter') AS transporter_name,
                NULL AS transporter_rating,
                AVG(abt.per_km_rate) AS average_per_km_rate
            FROM agreement_bids ab
            JOIN users u ON u.id = ab.transporter_user_id
            LEFT JOIN agreement_bid_trucks abt ON abt.bid_id = ab.id
            WHERE ab.post_id = ?
            GROUP BY ab.id, u.id
            """,
            (post_id,),
        ).fetchall()
        bid_ids = [row["id"] for row in rows]
        truck_map = {}
        if bid_ids:
            truck_rows = db.execute(
                f"""
                SELECT abt.*, t.truck_number, t.truck_type, t.catalog_type_key, t.capacity_tons, t.truck_photo_path
                FROM agreement_bid_trucks abt
                JOIN vehicles t ON t.id = abt.truck_id
                WHERE abt.bid_id IN ({','.join('?' for _ in bid_ids)})
                ORDER BY abt.id ASC
                """,
                tuple(bid_ids),
            ).fetchall()
            for row in truck_rows:
                truck_map.setdefault(row["bid_id"], []).append(dict(row))
    bids = []
    for row in rows:
        item = dict(row)
        proposed_counts = {}
        for truck in truck_map.get(item["id"], []):
            key = truck.get("catalog_type_key") or truck.get("truck_type")
            proposed_counts[key] = proposed_counts.get(key, 0) + 1
        item["exact_match"] = all(proposed_counts.get(key, 0) >= count for key, count in required_counts.items())
        bids.append(serialize_bid(item, [serialize_bid_truck(truck) for truck in truck_map.get(item["id"], [])]))
    bids.sort(key=lambda bid: (not bid["exact_match"], bid["average_per_km_rate"], bid["id"]))
    return json_response({"success": True, "post": serialize_post(post, [serialize_required_truck(row) for row in required]), "bids": bids})


@agreements_blueprint.post("/api/agreements/posts/<int:post_id>/bids/<int:bid_id>/invite")
@login_required
def invite_bid(post_id, bid_id):
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        post = fetch_post(db, post_id)
        if not post:
            return json_response({"success": False, "message": "Agreement post not found."}, 404)
        if post["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "You are not allowed to invite for this post."}, 403)
        bid = db.execute("SELECT * FROM agreement_bids WHERE id = ? AND post_id = ?", (bid_id, post_id)).fetchone()
        if not bid:
            return json_response({"success": False, "message": "Bid not found."}, 404)
        stamp = timestamp_bundle()["display"]
        db.execute(
            "UPDATE agreement_bids SET status = 'invited', updated_at = ? WHERE id = ?",
            (stamp, bid_id),
        )
        create_agreement_thread(db, post, bid["transporter_user_id"], bid_id=bid_id)
        db.commit()
    return json_response({"success": True})


@agreements_blueprint.post("/api/agreements/finalize")
@login_required
def finalize_agreement():
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        post_id = parse_positive_int(data.get("post_id"), "Post")
        duration_months = parse_positive_int(data.get("duration_months"), "Duration")
        start_date = parse_iso_date(data.get("start_date"), "Start date")
        end_date = add_months(start_date, duration_months)
        cargo_type = parse_required_text(data, "cargo_type", "Cargo type")
        service_area = service_area_to_text(data.get("service_area"))
        selected = data.get("selected_trucks") or []
        if not selected:
            raise ValueError("At least one selected truck is required.")
        contract_text = parse_optional_text(data, "contract_text")
        parsed_selected = [
            {
                "bid_id": parse_positive_int(item.get("bid_id"), "Bid"),
                "truck_id": parse_positive_int(item.get("truck_id"), "Truck"),
            }
            for item in selected
        ]
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    with open_db() as db:
        post = fetch_post(db, post_id)
        if not post:
            return json_response({"success": False, "message": "Agreement post not found."}, 404)
        if post["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "You are not allowed to finalize this post."}, 403)
        stamp = timestamp_bundle()["display"]
        # Snapshot the active agreement commission: this agreement keeps this
        # split for its entire lifetime, regardless of later policy changes.
        active_policy = get_active_policy(db, POLICY_TYPE_AGREEMENT)
        current_terms = get_current_terms_version(db)
        company_share = policy_company_share(active_policy)
        transporter_share = transporter_share_percent_for(company_share)
        db.execute(
            """
            INSERT INTO agreements (
                post_id, client_user_id, duration_months, cargo_type, service_area,
                start_date, end_date, status, contract_text,
                company_share_percent_snapshot, transporter_share_percent_snapshot,
                commission_policy_id, terms_version_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id, request.current_user["id"], duration_months, cargo_type, service_area,
                start_date.isoformat(), end_date.isoformat(), contract_text,
                float(company_share), float(transporter_share),
                active_policy["id"] if active_policy else None,
                current_terms["id"] if current_terms else None,
                stamp, stamp,
            ),
        )
        agreement_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        accepted_bid_ids = set()
        for item in parsed_selected:
            row = db.execute(
                """
                SELECT abt.*, ab.transporter_user_id
                FROM agreement_bid_trucks abt
                JOIN agreement_bids ab ON ab.id = abt.bid_id
                WHERE abt.bid_id = ? AND abt.truck_id = ? AND ab.post_id = ?
                """,
                (item["bid_id"], item["truck_id"], post_id),
            ).fetchone()
            if not row:
                db.rollback()
                return json_response({"success": False, "message": "Selected truck is not part of the selected bid."}, 400)
            accepted_bid_ids.add(item["bid_id"])
            db.execute(
                """
                INSERT INTO agreement_trucks (
                    agreement_id, truck_id, transporter_user_id, per_km_rate,
                    minimum_monthly_guarantee, status
                ) VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (agreement_id, item["truck_id"], row["transporter_user_id"], row["per_km_rate"], row["minimum_monthly_guarantee"]),
            )
            agreement_truck_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            for month_index in range(duration_months):
                due_date = due_date_for_month(start_date, month_index)
                _, final_amount, company_fee, transporter_amount = recalculate_payment_fields(
                    0, row["per_km_rate"], row["minimum_monthly_guarantee"], company_share,
                )
                db.execute(
                    """
                    INSERT INTO agreement_monthly_payments (
                        agreement_id, agreement_truck_id, transporter_user_id, client_user_id,
                        month_year, total_km, total_earned, minimum_guarantee, final_amount,
                        company_fee, transporter_amount,
                        company_share_percent, transporter_share_percent, commission_policy_id,
                        penalty_amount, status, payment_due_date, paid_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', ?, NULL, ?)
                    """,
                    (
                        agreement_id,
                        agreement_truck_id,
                        row["transporter_user_id"],
                        request.current_user["id"],
                        due_date.strftime("%Y-%m"),
                        row["minimum_monthly_guarantee"],
                        final_amount,
                        company_fee,
                        transporter_amount,
                        float(company_share),
                        float(transporter_share),
                        active_policy["id"] if active_policy else None,
                        due_date.isoformat(),
                        stamp,
                    ),
                )
        if accepted_bid_ids:
            db.execute(
                f"UPDATE agreement_bids SET status = 'accepted', updated_at = ? WHERE post_id = ? AND id IN ({','.join('?' for _ in accepted_bid_ids)})",
                (stamp, post_id, *accepted_bid_ids),
            )
        db.execute(
            "UPDATE agreement_bids SET status = 'rejected', updated_at = ? WHERE post_id = ? AND status NOT IN ('accepted', 'withdrawn')",
            (stamp, post_id),
        )
        db.execute("UPDATE agreement_posts SET status = 'active', updated_at = ? WHERE id = ?", (stamp, post_id))
        db.commit()
        agreement = fetch_agreement(db, agreement_id)
        trucks = fetch_agreement_trucks(db, agreement_id)
    return json_response({"success": True, "agreement": serialize_agreement(agreement, [serialize_agreement_truck(row) for row in trucks])})


@agreements_blueprint.post("/api/agreements/<int:agreement_id>/trips")
@login_required
def start_trip(agreement_id):
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        truck_id = parse_positive_int(data.get("truck_id"), "Truck")
        pickup_description = parse_required_text(data, "pickup_description", "Pickup description")
        gps_start_lat = float(data.get("gps_start_lat"))
        gps_start_lng = float(data.get("gps_start_lng"))
    except (TypeError, ValueError) as exc:
        return json_response({"success": False, "message": str(exc) or "GPS start coordinates are required."}, 400)

    with open_db() as db:
        agreement = fetch_agreement(db, agreement_id)
        if not agreement or agreement["status"] != "active":
            return json_response({"success": False, "message": "Active agreement not found."}, 404)
        agreement_truck = db.execute(
            """
            SELECT at.*, t.truck_number
            FROM agreement_trucks at
            JOIN vehicles t ON t.id = at.truck_id
            WHERE at.agreement_id = ? AND at.truck_id = ? AND at.transporter_user_id = ? AND at.status = 'active'
            """,
            (agreement_id, truck_id, request.current_user["id"]),
        ).fetchone()
        if not agreement_truck:
            return json_response({"success": False, "message": "Truck is not active in this agreement."}, 403)
        existing = db.execute(
            "SELECT id FROM agreement_trips WHERE agreement_id = ? AND truck_id = ? AND status = 'in_progress' LIMIT 1",
            (agreement_id, truck_id),
        ).fetchone()
        if existing:
            return json_response({"success": False, "message": "This truck already has a trip in progress."}, 400)
        stamp = timestamp_bundle()
        db.execute(
            """
            INSERT INTO agreement_trips (
                agreement_id, agreement_truck_id, truck_id, transporter_user_id,
                pickup_description, trip_date, gps_start_lat, gps_start_lng,
                started_at, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_progress', ?)
            """,
            (agreement_id, agreement_truck["id"], truck_id, request.current_user["id"], pickup_description, date.today().isoformat(), gps_start_lat, gps_start_lng, stamp["iso"], stamp["iso"]),
        )
        trip_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        insert_system_note_for_agreement(db, agreement_id, request.current_user["id"], f"Truck {agreement_truck['truck_number']} started trip: {pickup_description}")
        db.commit()
        trip = db.execute(
            "SELECT atr.*, t.truck_number FROM agreement_trips atr JOIN vehicles t ON t.id = atr.truck_id WHERE atr.id = ?",
            (trip_id,),
        ).fetchone()
    return json_response({"success": True, "trip": serialize_trip(dict(trip))})


@agreements_blueprint.put("/api/agreements/<int:agreement_id>/trips/<int:trip_id>/end")
@login_required
def end_trip(agreement_id, trip_id):
    role_error = require_transporter_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        gps_end_lat = float(data.get("gps_end_lat"))
        gps_end_lng = float(data.get("gps_end_lng"))
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "GPS end coordinates are required."}, 400)

    with open_db() as db:
        trip = db.execute(
            """
            SELECT atr.*, at.per_km_rate, t.truck_number
            FROM agreement_trips atr
            JOIN agreement_trucks at ON at.id = atr.agreement_truck_id
            JOIN vehicles t ON t.id = atr.truck_id
            WHERE atr.id = ? AND atr.agreement_id = ? AND atr.transporter_user_id = ?
            """,
            (trip_id, agreement_id, request.current_user["id"]),
        ).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)
        if trip["status"] != "in_progress":
            return json_response({"success": False, "message": "Only in-progress trips can be ended."}, 400)
        distance_km = None
        distance_source = "haversine"

        truck_row = db.execute("SELECT traccar_device_id FROM vehicles WHERE id = ?", (trip["truck_id"],)).fetchone()
        traccar_device_id = truck_row["traccar_device_id"] if truck_row else None
        if traccar_device_id:
            try:
                started_at = trip["started_at"]
                from_dt = started_at.replace(" ", "T") + "Z" if "T" not in started_at else started_at + "Z"
                positions = get_positions_between(
                    int(traccar_device_id),
                    from_dt,
                    datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
                if positions and len(positions) >= 2:
                    distance_km = calculate_route_distance_km(positions)
                    distance_source = "gps_provider"
            except Exception:
                pass

        if distance_km is None:
            distance_km = haversine_km(trip["gps_start_lat"], trip["gps_start_lng"], gps_end_lat, gps_end_lng)
            distance_source = "haversine"

        stamp = timestamp_bundle()["iso"]
        db.execute(
            """
            UPDATE agreement_trips
            SET gps_end_lat = ?, gps_end_lng = ?, distance_km = ?, distance_source = ?, ended_at = ?, status = 'completed'
            WHERE id = ?
            """,
            (gps_end_lat, gps_end_lng, distance_km, distance_source, stamp, trip_id),
        )
        trip_month = datetime.strptime(trip["trip_date"], "%Y-%m-%d").strftime("%Y-%m")
        payment = db.execute(
            """
            SELECT amp.*, at.per_km_rate, a.company_share_percent_snapshot
            FROM agreement_monthly_payments amp
            JOIN agreement_trucks at ON at.id = amp.agreement_truck_id
            JOIN agreements a ON a.id = amp.agreement_id
            WHERE amp.agreement_id = ? AND amp.agreement_truck_id = ? AND amp.month_year = ?
            LIMIT 1
            """,
            (agreement_id, trip["agreement_truck_id"], trip_month),
        ).fetchone()
        if payment and payment["status"] in {"pending", "failed"}:
            total_km = round_money(payment["total_km"] + distance_km)
            total_earned, final_amount, company_fee, transporter_amount = recalculate_payment_fields(
                total_km,
                payment["per_km_rate"],
                payment["minimum_guarantee"],
                payment["company_share_percent_snapshot"],
            )
            db.execute(
                """
                UPDATE agreement_monthly_payments
                SET total_km = ?, total_earned = ?, final_amount = ?, company_fee = ?, transporter_amount = ?
                WHERE id = ?
                """,
                (total_km, total_earned, final_amount, company_fee, transporter_amount, payment["id"]),
            )
        insert_system_note_for_agreement(db, agreement_id, request.current_user["id"], f"Truck {trip['truck_number']} completed trip: {distance_km:.2f} km")
        db.commit()
        updated = db.execute(
            "SELECT atr.*, t.truck_number FROM agreement_trips atr JOIN vehicles t ON t.id = atr.truck_id WHERE atr.id = ?",
            (trip_id,),
        ).fetchone()
    return json_response({"success": True, "trip": serialize_trip(dict(updated)), "distance_km": distance_km, "distance_source": distance_source})


@agreements_blueprint.get("/api/agreements/trips/<int:trip_id>/live-location")
@login_required
def trip_live_location(trip_id):
    """Return current GPS position from Traccar for an active trip."""
    from tracking.traccar import get_latest_position

    with open_db() as db:
        trip = db.execute(
            """
            SELECT atr.*, t.traccar_device_id
            FROM agreement_trips atr
            JOIN vehicles t ON t.id = atr.truck_id
            WHERE atr.id = ?
            """,
            (trip_id,),
        ).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)
        trip = dict(trip)
        agreement = fetch_agreement(db, trip["agreement_id"])
        if not agreement or not user_can_access_agreement(db, agreement, request.current_user):
            return json_response({"success": False, "message": "Not authorized."}, 403)

    traccar_device_id = trip.get("traccar_device_id")
    if not traccar_device_id:
        return json_response({"success": True, "traccar_available": False})

    try:
        position = get_latest_position(int(traccar_device_id))
    except Exception:
        position = None
    if not position:
        return json_response({"success": True, "traccar_available": False})

    return json_response(
        {
            "success": True,
            "traccar_available": True,
            "lat": position["lat"],
            "lon": position["lon"],
            "speed": position.get("speed"),
            "timestamp": position.get("timestamp"),
        }
    )


@agreements_blueprint.post("/api/agreements/trips/<int:trip_id>/dispute")
@login_required
def dispute_trip(trip_id):
    """Client marks a completed trip as disputed."""
    role_error = require_client_role(request.current_user)
    if role_error:
        return role_error
    err = csrf_error()
    if err:
        return err

    with open_db() as db:
        trip = db.execute(
            """
            SELECT atr.*, a.client_user_id
            FROM agreement_trips atr
            JOIN agreements a ON a.id = atr.agreement_id
            WHERE atr.id = ?
            """,
            (trip_id,),
        ).fetchone()
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)
        if trip["client_user_id"] != request.current_user["id"]:
            return json_response({"success": False, "message": "Not authorized."}, 403)
        if trip["status"] != "completed":
            return json_response({"success": False, "message": "Only completed trips can be disputed."}, 400)
        stamp = timestamp_bundle()["iso"]
        db.execute(
            "UPDATE agreement_trips SET status = 'disputed', updated_at = ? WHERE id = ?",
            (stamp, trip_id),
        )
        db.commit()
        updated = db.execute(
            "SELECT atr.*, t.truck_number FROM agreement_trips atr JOIN vehicles t ON t.id = atr.truck_id WHERE atr.id = ?",
            (trip_id,),
        ).fetchone()
    return json_response({"success": True, "trip": serialize_trip(dict(updated))})


@agreements_blueprint.get("/api/agreements/<int:agreement_id>/trips")
@login_required
def list_trips(agreement_id):
    with open_db() as db:
        agreement = fetch_agreement(db, agreement_id)
        if not agreement:
            return json_response({"success": False, "message": "Agreement not found."}, 404)
        if not user_can_access_agreement(db, agreement, request.current_user):
            return json_response({"success": False, "message": "You are not allowed to view this agreement."}, 403)
        params = [agreement_id]
        query = """
            SELECT atr.*, t.truck_number
            FROM agreement_trips atr
            JOIN vehicles t ON t.id = atr.truck_id
            WHERE atr.agreement_id = ?
        """
        truck_id = request.args.get("truck_id")
        if truck_id:
            query += " AND atr.truck_id = ?"
            params.append(truck_id)
        query += " ORDER BY atr.id DESC"
        rows = db.execute(query, tuple(params)).fetchall()
    return json_response({"success": True, "trips": [serialize_trip(dict(row)) for row in rows]})


@agreements_blueprint.get("/api/agreements/my")
@login_required
def my_agreements():
    user_id = request.current_user["id"]
    role = (request.current_user.get("role") or "").strip().lower()
    current_month = month_key()
    with open_db() as db:
        if role in {"service_seeker", "everyday_user", "client"}:
            rows = db.execute(
                """
                SELECT a.*, COALESCE(NULLIF(trim(u.full_name), ''), u.email, 'Client') AS client_name,
                       COUNT(DISTINCT at.id) AS truck_count,
                       SUM(CASE WHEN amp.month_year = ? THEN amp.total_km ELSE 0 END) AS current_month_km,
                       SUM(CASE WHEN amp.month_year = ? THEN amp.transporter_amount ELSE 0 END) AS current_month_earnings
                FROM agreements a
                JOIN users u ON u.id = a.client_user_id
                LEFT JOIN agreement_trucks at ON at.agreement_id = a.id
                LEFT JOIN agreement_monthly_payments amp ON amp.agreement_id = a.id
                WHERE a.client_user_id = ?
                GROUP BY a.id, u.id
                ORDER BY a.id DESC
                """,
                (current_month, current_month, user_id),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT a.*, COALESCE(NULLIF(trim(u.full_name), ''), u.email, 'Client') AS client_name,
                       COUNT(DISTINCT at.id) AS truck_count,
                       SUM(CASE WHEN amp.month_year = ? THEN amp.total_km ELSE 0 END) AS current_month_km,
                       SUM(CASE WHEN amp.month_year = ? THEN amp.transporter_amount ELSE 0 END) AS current_month_earnings
                FROM agreements a
                JOIN users u ON u.id = a.client_user_id
                JOIN agreement_trucks at ON at.agreement_id = a.id AND at.transporter_user_id = ?
                LEFT JOIN agreement_monthly_payments amp ON amp.agreement_truck_id = at.id
                GROUP BY a.id, u.id
                ORDER BY a.id DESC
                """,
                (current_month, current_month, user_id),
            ).fetchall()
        agreement_ids = [row["id"] for row in rows]
        trucks_by_agreement = {}
        if agreement_ids:
            for truck in db.execute(
                f"""
                SELECT at.*, t.truck_number, t.truck_type, t.catalog_type_key, t.truck_photo_path,
                       COALESCE(NULLIF(trim(u.full_name), ''), u.email, 'Transporter') AS transporter_name
                FROM agreement_trucks at
                JOIN vehicles t ON t.id = at.truck_id
                JOIN users u ON u.id = at.transporter_user_id
                WHERE at.agreement_id IN ({','.join('?' for _ in agreement_ids)})
                ORDER BY at.id ASC
                """,
                tuple(agreement_ids),
            ).fetchall():
                trucks_by_agreement.setdefault(truck["agreement_id"], []).append(serialize_agreement_truck(dict(truck)))
    return json_response({"success": True, "agreements": [serialize_agreement(dict(row), trucks_by_agreement.get(row["id"], [])) for row in rows]})


@agreements_blueprint.get("/api/agreements/<int:agreement_id>/payments")
@login_required
def list_payments(agreement_id):
    with open_db() as db:
        agreement = fetch_agreement(db, agreement_id)
        if not agreement:
            return json_response({"success": False, "message": "Agreement not found."}, 404)
        if not user_can_access_agreement(db, agreement, request.current_user):
            return json_response({"success": False, "message": "You are not allowed to view these payments."}, 403)
        rows = db.execute(
            """
            SELECT amp.*, t.truck_number
            FROM agreement_monthly_payments amp
            JOIN agreement_trucks at ON at.id = amp.agreement_truck_id
            JOIN vehicles t ON t.id = at.truck_id
            WHERE amp.agreement_id = ?
            ORDER BY amp.payment_due_date ASC, amp.id ASC
            """,
            (agreement_id,),
        ).fetchall()
    return json_response({"success": True, "payments": [serialize_payment(dict(row)) for row in rows]})


@agreements_blueprint.get("/api/agreements/<int:agreement_id>")
@login_required
def agreement_detail(agreement_id):
    with open_db() as db:
        agreement = fetch_agreement(db, agreement_id)
        if not agreement:
            return json_response({"success": False, "message": "Agreement not found."}, 404)
        if not user_can_access_agreement(db, agreement, request.current_user):
            return json_response({"success": False, "message": "You are not allowed to view this agreement."}, 403)
        trucks = fetch_agreement_trucks(db, agreement_id)
    return json_response({"success": True, "agreement": serialize_agreement(agreement, [serialize_agreement_truck(row) for row in trucks])})


@agreements_blueprint.post("/api/agreements/process-payments")
@login_required
def process_payments():
    from auth.helpers import require_admin_role
    role_error = require_admin_role(request.current_user)
    if role_error:
        return role_error
    with open_db() as db:
        result = run_process_payments(db)
    return json_response({"success": True, **result})


@agreements_blueprint.post("/api/agreements/apply-penalties")
@login_required
def apply_penalties():
    from auth.helpers import require_admin_role
    role_error = require_admin_role(request.current_user)
    if role_error:
        return role_error
    with open_db() as db:
        result = run_apply_penalties(db)
    return json_response({"success": True, **result})
