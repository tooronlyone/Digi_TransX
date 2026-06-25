from datetime import date, datetime

from flask import Blueprint, request
from werkzeug.security import generate_password_hash

from agreements.helpers import PENALTY_AMOUNT, month_key, serialize_agreement, serialize_agreement_truck, serialize_payment, serialize_trip
from agreements.routes import fetch_agreement, fetch_agreement_trucks, process_payment_row, recalculate_payment_fields
from auth.helpers import json_response, login_required, normalize_email, require_admin_role, require_csrf, split_name, timestamp_bundle
from chat.routes import insert_chat_message
from shared.db import open_db
from wallet.helpers import adjust_wallet_balance, get_or_create_wallet_for_user, insert_wallet_transaction, round_money


admin_blueprint = Blueprint("admin", __name__, url_prefix="/api/admin")


def admin_required(view):
    @login_required
    def wrapped(*args, **kwargs):
        role_error = require_admin_role(request.current_user)
        if role_error:
            return role_error
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


def csrf_error():
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)
    return None


def pagination():
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.args.get("page_size", 50))
    except (TypeError, ValueError):
        page_size = 50
    page_size = min(max(page_size, 1), 100)
    return page, page_size, (page - 1) * page_size


def rowdict(row):
    return dict(row) if row else None


def user_display_sql(alias="u"):
    return f"COALESCE(NULLIF(trim({alias}.full_name), ''), trim(COALESCE({alias}.first_name, '') || ' ' || COALESCE({alias}.last_name, '')), {alias}.email, 'User')"


def serialize_admin_user(row):
    item = dict(row)
    return {
        "id": item.get("id"),
        "name": item.get("name") or item.get("full_name") or "",
        "full_name": item.get("full_name") or item.get("name") or "",
        "email": item.get("email") or "",
        "phone": item.get("phone") or "",
        "cnic": item.get("cnic") or "",
        "role": item.get("role") or "",
        "city": item.get("city") or "",
        "created_at": item.get("created_at") or "",
        "is_blocked": bool(item.get("is_blocked")),
        "block_reason": item.get("block_reason") or "",
    }


def serialize_truck(row):
    item = dict(row)
    return {
        "id": item.get("id"),
        "owner_user_id": item.get("owner_user_id"),
        "truck_number": item.get("truck_number") or "",
        "truck_type": item.get("catalog_type_key") or item.get("truck_type") or "",
        "chassis_number": item.get("chassis_number") or "",
        "capacity_tons": item.get("capacity_tons"),
        "status": item.get("status") or "",
        "tracking_id": item.get("tracking_id") or "",
        "gps_enabled": bool((item.get("tracking_id") or "").strip()),
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
        "owner_name": item.get("owner_name") or "",
        "owner_email": item.get("owner_email") or "",
        "configuration": {
            "operating_provinces": item.get("operating_provinces") or "",
            "per_km_rate": round_money(item.get("per_km_rate")),
            "waiting_charge_per_hour": round_money(item.get("waiting_charge_per_hour")),
            "loading_charge": round_money(item.get("loading_charge")),
            "refrigeration_supported": bool(item.get("refrigeration_supported")),
            "hazardous_supported": bool(item.get("hazardous_supported")),
            "fragile_supported": bool(item.get("fragile_supported")),
        },
    }


def available_admin_cnic(db):
    base = "0000000000000"
    if not db.execute("SELECT id FROM users WHERE cnic = ?", (base,)).fetchone():
        return base
    for suffix in range(1, 10000):
        value = f"000000000{suffix:04d}"[-13:]
        if not db.execute("SELECT id FROM users WHERE cnic = ?", (value,)).fetchone():
            return value
    return datetime.now().strftime("%y%m%d%H%M%S")[:13]


def create_admin_user(db, name, email, password):
    first_name, last_name = split_name(name)
    stamp = timestamp_bundle()["display"]
    db.execute(
        """
        INSERT INTO users (
            full_name, first_name, last_name, email, phone, cnic, password_hash, role,
            city, mpin_hash, mpin_enabled, settings_json, created_at, updated_at, last_login_at
        ) VALUES (?, ?, ?, ?, '', ?, ?, 'platform_admin', '', NULL, 0, '{}', ?, ?, ?)
        """,
        (name, first_name, last_name, email, available_admin_cnic(db), generate_password_hash(password), stamp, stamp, stamp),
    )
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


@admin_blueprint.get("/dashboard")
@admin_required
def dashboard():
    with open_db() as db:
        stats = {
            "total_users": db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"],
            "active_agreements": db.execute("SELECT COUNT(*) AS total FROM agreements WHERE status = 'active'").fetchone()["total"],
            "pending_disputes": db.execute("SELECT COUNT(*) AS total FROM agreement_trips WHERE status = 'disputed'").fetchone()["total"],
            "pending_withdrawals": db.execute("SELECT COUNT(*) AS total FROM wallet_withdrawal_requests WHERE status = 'pending'").fetchone()["total"],
            "failed_payments": db.execute("SELECT COUNT(*) AS total FROM agreement_monthly_payments WHERE status = 'failed'").fetchone()["total"],
        }
        disputes = db.execute(
            f"""
            SELECT atr.*, a.id AS agreement_id, t.truck_number,
                   {user_display_sql('client')} AS client_name,
                   {user_display_sql('transporter')} AS transporter_name
            FROM agreement_trips atr
            JOIN agreements a ON a.id = atr.agreement_id
            JOIN users client ON client.id = a.client_user_id
            JOIN users transporter ON transporter.id = atr.transporter_user_id
            JOIN trucks t ON t.id = atr.truck_id
            WHERE atr.status = 'disputed'
            ORDER BY atr.created_at DESC
            LIMIT 5
            """
        ).fetchall()
        payments = db.execute(
            f"""
            SELECT amp.*, t.truck_number,
                   {user_display_sql('client')} AS client_name,
                   {user_display_sql('transporter')} AS transporter_name
            FROM agreement_monthly_payments amp
            JOIN agreement_trucks at ON at.id = amp.agreement_truck_id
            JOIN trucks t ON t.id = at.truck_id
            JOIN users client ON client.id = amp.client_user_id
            JOIN users transporter ON transporter.id = amp.transporter_user_id
            WHERE amp.status = 'failed'
            ORDER BY amp.payment_due_date DESC
            LIMIT 5
            """
        ).fetchall()
    return json_response({"success": True, "stats": stats, "recent_disputes": [serialize_trip(dict(r)) for r in disputes], "recent_failed_payments": [serialize_payment(dict(r)) | {"client_name": r["client_name"], "transporter_name": r["transporter_name"]} for r in payments]})


@admin_blueprint.get("/users")
@admin_required
def list_users():
    page, page_size, offset = pagination()
    clauses = []
    params = []
    role = (request.args.get("role") or "").strip()
    search = (request.args.get("search") or "").strip()
    if role:
        clauses.append("role = ?")
        params.append(role)
    if search:
        clauses.append("(full_name LIKE ? OR email LIKE ? OR cnic LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with open_db() as db:
        rows = db.execute(
            f"""
            SELECT *, {user_display_sql('users')} AS name
            FROM users
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        total = db.execute(f"SELECT COUNT(*) AS total FROM users {where}", tuple(params)).fetchone()["total"]
    return json_response({"success": True, "users": [serialize_admin_user(row) for row in rows], "page": page, "page_size": page_size, "total": total})


@admin_blueprint.post("/users")
@admin_required
def create_admin():
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = normalize_email(data.get("email"))
    password = data.get("password") or ""
    if not name or not email or len(password) < 8:
        return json_response({"success": False, "message": "Name, valid email, and 8+ character password are required."}, 400)
    with open_db() as db:
        if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            return json_response({"success": False, "message": "Email is already registered."}, 409)
        user_id = create_admin_user(db, name, email, password)
        db.commit()
        user = db.execute(f"SELECT *, {user_display_sql('users')} AS name FROM users WHERE id = ?", (user_id,)).fetchone()
    return json_response({"success": True, "user": serialize_admin_user(user)}, 201)


@admin_blueprint.get("/users/<int:user_id>")
@admin_required
def user_detail(user_id):
    with open_db() as db:
        user = db.execute(f"SELECT *, {user_display_sql('users')} AS name FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return json_response({"success": False, "message": "User not found."}, 404)
        wallet = rowdict(db.execute("SELECT balance, locked_balance FROM wallets WHERE user_id = ?", (user_id,)).fetchone()) or {"balance": 0, "locked_balance": 0}
        trucks = db.execute("SELECT * FROM trucks WHERE owner_user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        order_count = db.execute("SELECT COUNT(*) AS total FROM orders WHERE client_user_id = ?", (user_id,)).fetchone()["total"]
        agreement_count = db.execute(
            """
            SELECT COUNT(DISTINCT a.id) AS total
            FROM agreements a
            LEFT JOIN agreement_trucks at ON at.agreement_id = a.id
            WHERE a.client_user_id = ? OR at.transporter_user_id = ?
            """,
            (user_id, user_id),
        ).fetchone()["total"]
    return json_response({"success": True, "user": serialize_admin_user(user), "wallet": {"balance": round_money(wallet["balance"]), "locked_balance": round_money(wallet["locked_balance"])}, "truck_count": len(trucks), "trucks": [serialize_truck(row) for row in trucks], "order_count": order_count, "agreement_count": agreement_count})


@admin_blueprint.put("/users/<int:user_id>/block")
@admin_required
def block_user(user_id):
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    blocked = 1 if data.get("blocked") else 0
    reason = (data.get("reason") or "").strip()
    with open_db() as db:
        db.execute("UPDATE users SET is_blocked = ?, block_reason = ?, updated_at = ? WHERE id = ?", (blocked, reason if blocked else None, timestamp_bundle()["display"], user_id))
        if db.total_changes == 0:
            return json_response({"success": False, "message": "User not found."}, 404)
        db.commit()
    return json_response({"success": True})


@admin_blueprint.get("/trucks")
@admin_required
def list_trucks():
    page, page_size, offset = pagination()
    clauses = []
    params = []
    for field in ("status", "truck_type"):
        value = (request.args.get(field) or "").strip()
        if value:
            column = "COALESCE(t.catalog_type_key, t.truck_type)" if field == "truck_type" else "t.status"
            clauses.append(f"{column} = ?")
            params.append(value)
    search = (request.args.get("search") or "").strip()
    if search:
        clauses.append("(t.truck_number LIKE ? OR t.chassis_number LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with open_db() as db:
        rows = db.execute(
            f"""
            SELECT t.*, {user_display_sql('u')} AS owner_name, u.email AS owner_email
            FROM trucks t
            JOIN users u ON u.id = t.owner_user_id
            {where}
            ORDER BY t.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        total = db.execute(f"SELECT COUNT(*) AS total FROM trucks t JOIN users u ON u.id = t.owner_user_id {where}", tuple(params)).fetchone()["total"]
    return json_response({"success": True, "trucks": [serialize_truck(row) for row in rows], "page": page, "page_size": page_size, "total": total})


@admin_blueprint.get("/trucks/<int:truck_id>")
@admin_required
def truck_detail(truck_id):
    with open_db() as db:
        row = db.execute(
            f"""
            SELECT t.*, {user_display_sql('u')} AS owner_name, u.email AS owner_email
            FROM trucks t
            JOIN users u ON u.id = t.owner_user_id
            WHERE t.id = ?
            """,
            (truck_id,),
        ).fetchone()
    if not row:
        return json_response({"success": False, "message": "Truck not found."}, 404)
    return json_response({"success": True, "truck": serialize_truck(row)})


@admin_blueprint.get("/wallet/withdrawals")
@admin_required
def withdrawals():
    page, page_size, offset = pagination()
    status = (request.args.get("status") or "").strip()
    where = "WHERE wwr.status = ?" if status else ""
    params = [status] if status else []
    with open_db() as db:
        rows = db.execute(
            f"""
            SELECT wwr.*, {user_display_sql('u')} AS user_name, u.email, COALESCE(w.locked_balance, 0) AS current_locked_balance
            FROM wallet_withdrawal_requests wwr
            JOIN users u ON u.id = wwr.user_id
            LEFT JOIN wallets w ON w.user_id = wwr.user_id
            {where}
            ORDER BY wwr.requested_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        total = db.execute(f"SELECT COUNT(*) AS total FROM wallet_withdrawal_requests wwr {where}", tuple(params)).fetchone()["total"]
    return json_response({"success": True, "withdrawals": [dict(row) for row in rows], "page": page, "page_size": page_size, "total": total})


@admin_blueprint.post("/wallet/withdrawals/<int:request_id>/approve")
@admin_required
def approve_withdrawal(request_id):
    err = csrf_error()
    if err:
        return err
    stamp = timestamp_bundle()
    with open_db() as db:
        req = rowdict(db.execute("SELECT * FROM wallet_withdrawal_requests WHERE id = ?", (request_id,)).fetchone())
        if not req:
            return json_response({"success": False, "message": "Withdrawal request not found."}, 404)
        if req["status"] != "pending":
            return json_response({"success": False, "message": "Withdrawal request is already resolved."}, 400)
        user = rowdict(db.execute("SELECT id, role FROM users WHERE id = ?", (req["user_id"],)).fetchone())
        wallet, wallet_error = get_or_create_wallet_for_user(db, user)
        if wallet_error:
            return wallet_error
        amount = round_money(req["amount"])
        if round_money(wallet["locked_balance"]) + 1e-9 < amount or round_money(wallet["balance"]) + 1e-9 < amount:
            return json_response({"success": False, "message": "Wallet balance is lower than the requested withdrawal amount."}, 400)
        wallet["locked_balance"] = round_money(wallet["locked_balance"] - amount)
        wallet["balance"] = round_money(wallet["balance"] - amount)
        db.execute("UPDATE wallets SET locked_balance = ?, balance = ?, updated_at = ? WHERE id = ?", (wallet["locked_balance"], wallet["balance"], stamp["display"], wallet["id"]))
        db.execute("UPDATE wallet_withdrawal_requests SET status = 'approved', resolved_at = ? WHERE id = ?", (stamp["iso"], request_id))
        insert_wallet_transaction(db, wallet, req["user_id"], "withdrawal", -amount, description="Approved locked withdrawal", reference_id=str(request_id))
        db.commit()
    return json_response({"success": True})


@admin_blueprint.post("/wallet/withdrawals/<int:request_id>/reject")
@admin_required
def reject_withdrawal(request_id):
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        db.execute("UPDATE wallet_withdrawal_requests SET status = 'rejected', resolved_at = ? WHERE id = ? AND status = 'pending'", (timestamp_bundle()["iso"], request_id))
        if db.total_changes == 0:
            return json_response({"success": False, "message": "Pending withdrawal request not found."}, 404)
        db.commit()
    return json_response({"success": True})


@admin_blueprint.get("/agreements")
@admin_required
def agreements():
    page, page_size, offset = pagination()
    status = (request.args.get("status") or "").strip()
    where = "WHERE a.status = ?" if status else ""
    params = [status] if status else []
    current_month = month_key()
    with open_db() as db:
        rows = db.execute(
            f"""
            SELECT a.*, {user_display_sql('u')} AS client_name,
                   COUNT(DISTINCT at.id) AS truck_count,
                   SUM(CASE WHEN amp.month_year = ? THEN amp.total_km ELSE 0 END) AS current_month_km
            FROM agreements a
            JOIN users u ON u.id = a.client_user_id
            LEFT JOIN agreement_trucks at ON at.agreement_id = a.id
            LEFT JOIN agreement_monthly_payments amp ON amp.agreement_id = a.id
            {where}
            GROUP BY a.id
            ORDER BY a.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (current_month, *params, page_size, offset),
        ).fetchall()
        total = db.execute(f"SELECT COUNT(*) AS total FROM agreements a {where}", tuple(params)).fetchone()["total"]
    return json_response({"success": True, "agreements": [serialize_agreement(dict(row)) for row in rows], "page": page, "page_size": page_size, "total": total})


@admin_blueprint.get("/agreements/<int:agreement_id>")
@admin_required
def agreement_detail(agreement_id):
    with open_db() as db:
        agreement = fetch_agreement(db, agreement_id)
        if not agreement:
            return json_response({"success": False, "message": "Agreement not found."}, 404)
        trucks = fetch_agreement_trucks(db, agreement_id)
        payments = db.execute("SELECT amp.*, t.truck_number FROM agreement_monthly_payments amp JOIN agreement_trucks at ON at.id = amp.agreement_truck_id JOIN trucks t ON t.id = at.truck_id WHERE amp.agreement_id = ? ORDER BY amp.payment_due_date ASC", (agreement_id,)).fetchall()
        trips = db.execute("SELECT atr.*, t.truck_number FROM agreement_trips atr JOIN trucks t ON t.id = atr.truck_id WHERE atr.agreement_id = ? ORDER BY atr.created_at DESC", (agreement_id,)).fetchall()
    return json_response({"success": True, "agreement": serialize_agreement(agreement, [serialize_agreement_truck(row) for row in trucks]), "payments": [serialize_payment(dict(row)) for row in payments], "trips": [serialize_trip(dict(row)) for row in trips]})


@admin_blueprint.get("/disputes")
@admin_required
def disputes():
    with open_db() as db:
        rows = db.execute(
            f"""
            SELECT atr.*, a.client_user_id, t.truck_number,
                   {user_display_sql('client')} AS client_name,
                   {user_display_sql('transporter')} AS transporter_name
            FROM agreement_trips atr
            JOIN agreements a ON a.id = atr.agreement_id
            JOIN users client ON client.id = a.client_user_id
            JOIN users transporter ON transporter.id = atr.transporter_user_id
            JOIN trucks t ON t.id = atr.truck_id
            WHERE atr.status = 'disputed'
            ORDER BY atr.created_at DESC
            """
        ).fetchall()
    return json_response({"success": True, "disputes": [dict(row) for row in rows]})


def add_trip_km_to_payment(db, trip):
    trip_month = datetime.strptime(trip["trip_date"], "%Y-%m-%d").strftime("%Y-%m")
    payment = db.execute(
        """
        SELECT amp.*, at.per_km_rate
        FROM agreement_monthly_payments amp
        JOIN agreement_trucks at ON at.id = amp.agreement_truck_id
        WHERE amp.agreement_id = ? AND amp.agreement_truck_id = ? AND amp.month_year = ?
        LIMIT 1
        """,
        (trip["agreement_id"], trip["agreement_truck_id"], trip_month),
    ).fetchone()
    if payment and payment["status"] in {"pending", "failed"}:
        total_km = round_money(payment["total_km"] + round_money(trip["distance_km"]))
        total_earned, final_amount, company_fee, transporter_amount = recalculate_payment_fields(total_km, payment["per_km_rate"], payment["minimum_guarantee"])
        db.execute(
            """
            UPDATE agreement_monthly_payments
            SET total_km = ?, total_earned = ?, final_amount = ?, company_fee = ?, transporter_amount = ?
            WHERE id = ?
            """,
            (total_km, total_earned, final_amount, company_fee, transporter_amount, payment["id"]),
        )


@admin_blueprint.post("/disputes/<int:trip_id>/resolve")
@admin_required
def resolve_dispute(trip_id):
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    decision = (data.get("decision") or "").strip()
    if decision not in {"km_approved", "km_rejected"}:
        return json_response({"success": False, "message": "Decision must be km_approved or km_rejected."}, 400)
    note = (data.get("admin_note") or "").strip()
    with open_db() as db:
        trip = rowdict(db.execute("SELECT * FROM agreement_trips WHERE id = ?", (trip_id,)).fetchone())
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)
        if trip["status"] != "disputed":
            return json_response({"success": False, "message": "Only disputed trips can be resolved."}, 400)
        agreement = rowdict(db.execute("SELECT client_user_id FROM agreements WHERE id = ?", (trip["agreement_id"],)).fetchone())
        penalty_user_id = agreement["client_user_id"] if decision == "km_approved" else trip["transporter_user_id"]
        penalty_role = "client" if decision == "km_approved" else "transporter"
        wallet, wallet_error = get_or_create_wallet_for_user(db, {"id": penalty_user_id, "role": penalty_role})
        if not wallet_error:
            adjust_wallet_balance(db, wallet, penalty_user_id, -PENALTY_AMOUNT, "dispute_penalty", description=f"Trip #{trip_id} dispute penalty", reference_id=str(trip_id))
        stamp = timestamp_bundle()["iso"]
        if decision == "km_approved":
            add_trip_km_to_payment(db, trip)
            distance_sql = ""
            values = (decision, note, stamp, request.current_user["id"], trip_id)
        else:
            distance_sql = ", distance_km = 0"
            values = (decision, note, stamp, request.current_user["id"], trip_id)
        db.execute(
            f"""
            UPDATE agreement_trips
            SET status = 'completed', admin_decision = ?, admin_note = ?,
                admin_decided_at = ?, admin_decided_by = ?{distance_sql}
            WHERE id = ?
            """,
            values,
        )
        db.commit()
        updated = db.execute("SELECT atr.*, t.truck_number FROM agreement_trips atr JOIN trucks t ON t.id = atr.truck_id WHERE atr.id = ?", (trip_id,)).fetchone()
    return json_response({"success": True, "trip": serialize_trip(dict(updated))})


@admin_blueprint.post("/disputes/<int:trip_id>/group-chat")
@admin_required
def create_group_chat(trip_id):
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        trip = rowdict(db.execute("SELECT atr.*, a.client_user_id FROM agreement_trips atr JOIN agreements a ON a.id = atr.agreement_id WHERE atr.id = ?", (trip_id,)).fetchone())
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)
        existing = db.execute("SELECT id FROM chat_threads WHERE is_group_chat = 1 AND dispute_trip_id = ?", (trip_id,)).fetchone()
        if existing:
            return json_response({"success": True, "thread_id": existing["id"]})
        stamp = timestamp_bundle()["iso"]
        db.execute(
            """
            INSERT INTO chat_threads (
                order_id, client_user_id, transporter_user_id, bid_id, is_group_chat,
                admin_user_id, dispute_trip_id, last_message_at, created_at
            ) VALUES (?, ?, ?, NULL, 1, ?, ?, ?, ?)
            """,
            (-(trip_id + 1000000), trip["client_user_id"], trip["transporter_user_id"], request.current_user["id"], trip_id, stamp, stamp),
        )
        thread_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        insert_chat_message(db, thread_id, request.current_user["id"], "system", content=f"Admin ne ye group chat dispute resolve karne ke liye create ki hai. Trip #{trip_id} - {trip.get('pickup_description') or ''} - {round_money(trip.get('distance_km'))} km")
        db.commit()
    return json_response({"success": True, "thread_id": thread_id})


@admin_blueprint.get("/disputes/<int:trip_id>/group-chat")
@admin_required
def get_group_chat(trip_id):
    with open_db() as db:
        row = db.execute("SELECT * FROM chat_threads WHERE is_group_chat = 1 AND dispute_trip_id = ? ORDER BY id DESC LIMIT 1", (trip_id,)).fetchone()
    return json_response({"success": True, "thread": dict(row) if row else None})


@admin_blueprint.get("/payments")
@admin_required
def payments():
    page, page_size, offset = pagination()
    clauses = []
    params = []
    status = (request.args.get("status") or "").strip()
    month = (request.args.get("month_year") or "").strip()
    if status:
        clauses.append("amp.status = ?")
        params.append(status)
    if month:
        clauses.append("amp.month_year = ?")
        params.append(month)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with open_db() as db:
        rows = db.execute(
            f"""
            SELECT amp.*, t.truck_number,
                   {user_display_sql('client')} AS client_name,
                   {user_display_sql('transporter')} AS transporter_name
            FROM agreement_monthly_payments amp
            JOIN agreement_trucks at ON at.id = amp.agreement_truck_id
            JOIN trucks t ON t.id = at.truck_id
            JOIN users client ON client.id = amp.client_user_id
            JOIN users transporter ON transporter.id = amp.transporter_user_id
            {where}
            ORDER BY amp.payment_due_date DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        total = db.execute(f"SELECT COUNT(*) AS total FROM agreement_monthly_payments amp {where}", tuple(params)).fetchone()["total"]
    return json_response({"success": True, "payments": [serialize_payment(dict(row)) | {"client_name": row["client_name"], "transporter_name": row["transporter_name"]} for row in rows], "page": page, "page_size": page_size, "total": total})


@admin_blueprint.post("/payments/process")
@admin_required
def process_payments():
    err = csrf_error()
    if err:
        return err
    today = date.today().isoformat()
    processed = 0
    failed = 0
    with open_db() as db:
        rows = db.execute("SELECT * FROM agreement_monthly_payments WHERE status = 'pending' AND payment_due_date <= ? ORDER BY id ASC", (today,)).fetchall()
        for row in rows:
            if process_payment_row(db, dict(row)):
                processed += 1
            else:
                failed += 1
        db.commit()
    return json_response({"success": True, "processed": processed, "failed": failed})


@admin_blueprint.post("/payments/apply-penalties")
@admin_required
def apply_penalties():
    err = csrf_error()
    if err:
        return err
    today = date.today().isoformat()
    penalties_applied = 0
    with open_db() as db:
        rows = db.execute("SELECT * FROM agreement_monthly_payments WHERE status = 'failed' AND payment_due_date <= ? ORDER BY id ASC", (today,)).fetchall()
        for row in rows:
            payment = dict(row)
            client_wallet, wallet_error = get_or_create_wallet_for_user(db, {"id": payment["client_user_id"], "role": "client"})
            if wallet_error:
                continue
            if adjust_wallet_balance(db, client_wallet, payment["client_user_id"], -PENALTY_AMOUNT, "agreement_late_penalty", description=f"Agreement #{payment['agreement_id']} late payment penalty", reference_id=str(payment["id"])):
                continue
            current_count = db.execute("SELECT COUNT(*) AS total FROM agreement_payment_penalties WHERE monthly_payment_id = ?", (payment["id"],)).fetchone()["total"]
            stamp = timestamp_bundle()["iso"]
            db.execute("INSERT INTO agreement_payment_penalties (monthly_payment_id, client_user_id, penalty_amount, penalty_number, applied_at) VALUES (?, ?, ?, ?, ?)", (payment["id"], payment["client_user_id"], PENALTY_AMOUNT, int(current_count or 0) + 1, stamp))
            db.execute("UPDATE agreement_monthly_payments SET penalty_amount = penalty_amount + ? WHERE id = ?", (PENALTY_AMOUNT, payment["id"]))
            penalties_applied += 1
            refreshed = db.execute("SELECT * FROM agreement_monthly_payments WHERE id = ?", (payment["id"],)).fetchone()
            if refreshed:
                process_payment_row(db, dict(refreshed))
        db.commit()
    return json_response({"success": True, "penalties_applied": penalties_applied})
