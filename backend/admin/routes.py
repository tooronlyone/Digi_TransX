import json
from datetime import date, datetime

from flask import Blueprint, request
from werkzeug.security import generate_password_hash

from agreements.helpers import (
    PENALTY_AMOUNT,
    month_key,
    run_apply_penalties,
    run_process_payments,
    serialize_agreement,
    serialize_agreement_truck,
    serialize_payment,
    serialize_trip,
)
from agreements.routes import fetch_agreement, fetch_agreement_trucks
from auth.helpers import csrf_error, json_response, login_required, normalize_email, require_admin_role, split_name, timestamp_bundle
from chat.routes import insert_chat_message
from shared.commissions import (
    POLICY_TYPES,
    POLICY_TYPE_LABELS,
    get_active_policy,
    get_current_terms_version,
    list_policy_versions,
    list_terms_versions,
    parse_company_share_percent,
    publish_commission_change,
    recalculate_payment_fields,
    serialize_policy,
    serialize_terms_version,
)
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
    return f"COALESCE(NULLIF(trim({alias}.full_name), ''), {alias}.email, 'User')"


def serialize_admin_user(row):
    item = dict(row)
    return {
        "id": item.get("id"),
        "name": item.get("name") or item.get("full_name") or "",
        "full_name": item.get("full_name") or item.get("name") or "",
        "email": item.get("email") or "",
        "phone": item.get("phone") or "",
        "cnic": item.get("cnic") or "",
        "role": item.get("legacy_role") or item.get("role") or "",
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
    if not db.execute("SELECT id FROM users WHERE cnic = %s", (base,)).fetchone():
        return base
    for suffix in range(1, 10000):
        value = f"000000000{suffix:04d}"[-13:]
        if not db.execute("SELECT id FROM users WHERE cnic = %s", (value,)).fetchone():
            return value
    return datetime.now().strftime("%y%m%d%H%M%S")[:13]


def create_admin_user(db, name, email, password):
    """Create a platform admin in Supabase Auth + profile row (via DB trigger)."""
    from shared.supabase_client import supabase_create_user

    stamp = timestamp_bundle()["iso"]
    cnic = available_admin_cnic(db)
    supabase_create_user(
        email,
        password,
        {"full_name": name, "phone": "", "cnic": cnic, "role": "admin", "legacy_role": "platform_admin"},
    )
    db.execute(
        """
        UPDATE users
        SET full_name = %s, cnic = %s, legacy_role = 'platform_admin',
            role = 'admin', city = '', updated_at = %s
        WHERE email = %s
        """,
        (name, cnic, stamp, email),
    )
    return db.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()["id"]


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
            JOIN vehicles t ON t.id = atr.truck_id
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
            JOIN vehicles t ON t.id = at.truck_id
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
        clauses.append("COALESCE(legacy_role, role::text) = %s")
        params.append(role)
    if search:
        clauses.append("(full_name ILIKE %s OR email ILIKE %s OR cnic ILIKE %s)")
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
            LIMIT %s OFFSET %s
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
        if db.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone():
            return json_response({"success": False, "message": "Email is already registered."}, 409)
        user_id = create_admin_user(db, name, email, password)
        db.commit()
        user = db.execute(f"SELECT *, {user_display_sql('users')} AS name FROM users WHERE id = %s", (user_id,)).fetchone()
    return json_response({"success": True, "user": serialize_admin_user(user)}, 201)


@admin_blueprint.get("/users/<int:user_id>")
@admin_required
def user_detail(user_id):
    with open_db() as db:
        user = db.execute(f"SELECT *, {user_display_sql('users')} AS name FROM users WHERE id = %s", (user_id,)).fetchone()
        if not user:
            return json_response({"success": False, "message": "User not found."}, 404)
        wallet = rowdict(db.execute("SELECT balance, locked_balance FROM wallets WHERE user_id = %s", (user_id,)).fetchone()) or {"balance": 0, "locked_balance": 0}
        trucks = db.execute("SELECT * FROM vehicles WHERE owner_user_id = %s ORDER BY created_at DESC", (user_id,)).fetchall()
        agreement_count = db.execute(
            """
            SELECT COUNT(DISTINCT a.id) AS total
            FROM agreements a
            LEFT JOIN agreement_trucks at ON at.agreement_id = a.id
            WHERE a.client_user_id = %s OR at.transporter_user_id = %s
            """,
            (user_id, user_id),
        ).fetchone()["total"]
    return json_response({"success": True, "user": serialize_admin_user(user), "wallet": {"balance": round_money(wallet["balance"]), "locked_balance": round_money(wallet["locked_balance"])}, "truck_count": len(trucks), "trucks": [serialize_truck(row) for row in trucks], "agreement_count": agreement_count})


@admin_blueprint.put("/users/<int:user_id>/block")
@admin_required
def block_user(user_id):
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    blocked = bool(data.get("blocked"))
    reason = (data.get("reason") or "").strip()
    with open_db() as db:
        result = db.execute("UPDATE users SET is_blocked = %s, block_reason = %s, updated_at = %s WHERE id = %s", (blocked, reason if blocked else None, timestamp_bundle()["display"], user_id))
        if result.rowcount == 0:
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
            clauses.append(f"{column} = %s")
            params.append(value)
    search = (request.args.get("search") or "").strip()
    if search:
        clauses.append("(t.truck_number ILIKE %s OR t.chassis_number ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with open_db() as db:
        rows = db.execute(
            f"""
            SELECT t.*, {user_display_sql('u')} AS owner_name, u.email AS owner_email
            FROM vehicles t
            JOIN users u ON u.id = t.owner_user_id
            {where}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (*params, page_size, offset),
        ).fetchall()
        total = db.execute(f"SELECT COUNT(*) AS total FROM vehicles t JOIN users u ON u.id = t.owner_user_id {where}", tuple(params)).fetchone()["total"]
    return json_response({"success": True, "trucks": [serialize_truck(row) for row in rows], "page": page, "page_size": page_size, "total": total})


@admin_blueprint.get("/trucks/<int:truck_id>")
@admin_required
def truck_detail(truck_id):
    with open_db() as db:
        row = db.execute(
            f"""
            SELECT t.*, {user_display_sql('u')} AS owner_name, u.email AS owner_email
            FROM vehicles t
            JOIN users u ON u.id = t.owner_user_id
            WHERE t.id = %s
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
    where = "WHERE wwr.status = %s" if status else ""
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
            LIMIT %s OFFSET %s
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
        req = rowdict(db.execute("SELECT * FROM wallet_withdrawal_requests WHERE id = %s", (request_id,)).fetchone())
        if not req:
            return json_response({"success": False, "message": "Withdrawal request not found."}, 404)
        if req["status"] != "pending":
            return json_response({"success": False, "message": "Withdrawal request is already resolved."}, 400)
        user = rowdict(db.execute("SELECT id, role FROM users WHERE id = %s", (req["user_id"],)).fetchone())
        wallet, wallet_error = get_or_create_wallet_for_user(db, user)
        if wallet_error:
            return wallet_error
        amount = round_money(req["amount"])
        if round_money(wallet["balance"]) + 1e-9 < amount:
            return json_response({"success": False, "message": "Wallet balance is lower than the requested withdrawal amount."}, 400)
        wallet["balance"] = round_money(wallet["balance"] - amount)
        db.execute("UPDATE wallets SET balance = %s, updated_at = %s WHERE id = %s", (wallet["balance"], stamp["display"], wallet["id"]))
        db.execute("UPDATE wallet_withdrawal_requests SET status = 'approved', resolved_at = %s WHERE id = %s", (stamp["iso"], request_id))
        insert_wallet_transaction(db, wallet, req["user_id"], "withdrawal", -amount, description="Approved withdrawal", reference_id=str(request_id))
        db.commit()
    return json_response({"success": True})


@admin_blueprint.post("/wallet/withdrawals/<int:request_id>/reject")
@admin_required
def reject_withdrawal(request_id):
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        result = db.execute("UPDATE wallet_withdrawal_requests SET status = 'rejected', resolved_at = %s WHERE id = %s AND status = 'pending'", (timestamp_bundle()["iso"], request_id))
        if result.rowcount == 0:
            return json_response({"success": False, "message": "Pending withdrawal request not found."}, 404)
        db.commit()
    return json_response({"success": True})


@admin_blueprint.get("/agreements")
@admin_required
def agreements():
    page, page_size, offset = pagination()
    status = (request.args.get("status") or "").strip()
    where = "WHERE a.status = %s" if status else ""
    params = [status] if status else []
    current_month = month_key()
    with open_db() as db:
        rows = db.execute(
            f"""
            SELECT a.*, {user_display_sql('u')} AS client_name,
                   COUNT(DISTINCT at.id) AS truck_count,
                   SUM(CASE WHEN amp.month_year = %s THEN amp.total_km ELSE 0 END) AS current_month_km
            FROM agreements a
            JOIN users u ON u.id = a.client_user_id
            LEFT JOIN agreement_trucks at ON at.agreement_id = a.id
            LEFT JOIN agreement_monthly_payments amp ON amp.agreement_id = a.id
            {where}
            GROUP BY a.id, u.id
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
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
        payments = db.execute("SELECT amp.*, t.truck_number FROM agreement_monthly_payments amp JOIN agreement_trucks at ON at.id = amp.agreement_truck_id JOIN vehicles t ON t.id = at.truck_id WHERE amp.agreement_id = %s ORDER BY amp.payment_due_date ASC", (agreement_id,)).fetchall()
        trips = db.execute("SELECT atr.*, t.truck_number FROM agreement_trips atr JOIN vehicles t ON t.id = atr.truck_id WHERE atr.agreement_id = %s ORDER BY atr.created_at DESC", (agreement_id,)).fetchall()
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
            JOIN vehicles t ON t.id = atr.truck_id
            WHERE atr.status = 'disputed'
            ORDER BY atr.created_at DESC
            """
        ).fetchall()
    return json_response({"success": True, "disputes": [dict(row) for row in rows]})


def add_trip_km_to_payment(db, trip):
    trip_month = datetime.strptime(trip["trip_date"], "%Y-%m-%d").strftime("%Y-%m")
    payment = db.execute(
        """
        SELECT amp.*, at.per_km_rate, a.company_share_percent_snapshot
        FROM agreement_monthly_payments amp
        JOIN agreement_trucks at ON at.id = amp.agreement_truck_id
        JOIN agreements a ON a.id = amp.agreement_id
        WHERE amp.agreement_id = %s AND amp.agreement_truck_id = %s AND amp.month_year = %s
        LIMIT 1
        """,
        (trip["agreement_id"], trip["agreement_truck_id"], trip_month),
    ).fetchone()
    if payment and payment["status"] in {"pending", "failed"}:
        total_km = round_money(payment["total_km"] + round_money(trip["distance_km"]))
        total_earned, final_amount, company_fee, transporter_amount = recalculate_payment_fields(
            total_km, payment["per_km_rate"], payment["minimum_guarantee"],
            payment["company_share_percent_snapshot"],
        )
        db.execute(
            """
            UPDATE agreement_monthly_payments
            SET total_km = %s, total_earned = %s, final_amount = %s, company_fee = %s, transporter_amount = %s
            WHERE id = %s
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
        trip = rowdict(db.execute("SELECT * FROM agreement_trips WHERE id = %s", (trip_id,)).fetchone())
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)
        if trip["status"] != "disputed":
            return json_response({"success": False, "message": "Only disputed trips can be resolved."}, 400)
        agreement = rowdict(db.execute("SELECT client_user_id FROM agreements WHERE id = %s", (trip["agreement_id"],)).fetchone())
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
            SET status = 'completed', admin_decision = %s, admin_note = %s,
                admin_decided_at = %s, admin_decided_by = %s{distance_sql}
            WHERE id = %s
            """,
            values,
        )
        db.commit()
        updated = db.execute("SELECT atr.*, t.truck_number FROM agreement_trips atr JOIN vehicles t ON t.id = atr.truck_id WHERE atr.id = %s", (trip_id,)).fetchone()
    return json_response({"success": True, "trip": serialize_trip(dict(updated))})


@admin_blueprint.post("/disputes/<int:trip_id>/group-chat")
@admin_required
def create_group_chat(trip_id):
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        trip = rowdict(db.execute("SELECT atr.*, a.client_user_id FROM agreement_trips atr JOIN agreements a ON a.id = atr.agreement_id WHERE atr.id = %s", (trip_id,)).fetchone())
        if not trip:
            return json_response({"success": False, "message": "Trip not found."}, 404)
        existing = db.execute("SELECT id FROM chat_threads WHERE is_group_chat = true AND dispute_trip_id = %s", (trip_id,)).fetchone()
        if existing:
            return json_response({"success": True, "thread_id": existing["id"]})
        stamp = timestamp_bundle()["iso"]
        thread_id = db.execute(
            """
            INSERT INTO chat_threads (
                client_user_id, transporter_user_id, is_group_chat,
                admin_user_id, dispute_trip_id, last_message_at, created_at
            ) VALUES (%s, %s, true, %s, %s, %s, %s)
            RETURNING id
            """,
            (trip["client_user_id"], trip["transporter_user_id"], request.current_user["id"], trip_id, stamp, stamp),
        ).fetchone()["id"]
        insert_chat_message(db, thread_id, request.current_user["id"], "system", content=f"Admin created this group chat to resolve the dispute for Trip #{trip_id} - {trip.get('pickup_description') or ''} - {round_money(trip.get('distance_km'))} km")
        db.commit()
    return json_response({"success": True, "thread_id": thread_id})


@admin_blueprint.get("/disputes/<int:trip_id>/group-chat")
@admin_required
def get_group_chat(trip_id):
    with open_db() as db:
        row = db.execute("SELECT * FROM chat_threads WHERE is_group_chat = true AND dispute_trip_id = %s ORDER BY id DESC LIMIT 1", (trip_id,)).fetchone()
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
        clauses.append("amp.status = %s")
        params.append(status)
    if month:
        clauses.append("amp.month_year = %s")
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
            JOIN vehicles t ON t.id = at.truck_id
            JOIN users client ON client.id = amp.client_user_id
            JOIN users transporter ON transporter.id = amp.transporter_user_id
            {where}
            ORDER BY amp.payment_due_date DESC
            LIMIT %s OFFSET %s
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
    with open_db() as db:
        result = run_process_payments(db)
    return json_response({"success": True, **result})


@admin_blueprint.post("/payments/apply-penalties")
@admin_required
def apply_penalties():
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        result = run_apply_penalties(db)
    return json_response({"success": True, **result})


# ---------------------------------------------------------------------------
# Platform settings — versioned commission policies
# ---------------------------------------------------------------------------

@admin_blueprint.get("/platform-settings/commissions")
@admin_required
def commission_settings():
    """Current active policy for each commission type + current Terms version."""
    with open_db() as db:
        policies = {ptype: serialize_policy(get_active_policy(db, ptype)) for ptype in POLICY_TYPES}
        terms = get_current_terms_version(db)
    return json_response({
        "success": True,
        "policies": policies,
        "terms_version": serialize_terms_version(terms),
    })


@admin_blueprint.get("/platform-settings/commissions/history")
@admin_required
def commission_history():
    """Immutable version history for both policy types and Terms versions."""
    with open_db() as db:
        policy_rows = list_policy_versions(db)
        terms_rows = list_terms_versions(db)
        admin_ids = {row.get("created_by_admin_user_id") for row in policy_rows}
        admin_ids |= {row.get("published_by_admin_user_id") for row in terms_rows}
        admin_ids.discard(None)
        admin_names = {}
        if admin_ids:
            placeholders = ",".join("%s" for _ in admin_ids)
            for row in db.execute(
                f"SELECT id, {user_display_sql('users')} AS name FROM users WHERE id IN ({placeholders})",
                tuple(admin_ids),
            ).fetchall():
                admin_names[row["id"]] = row["name"]
    policies = []
    for row in policy_rows:
        item = serialize_policy(row)
        item["created_by_name"] = admin_names.get(row.get("created_by_admin_user_id"), "")
        policies.append(item)
    terms = []
    for row in terms_rows:
        item = serialize_terms_version(row)
        item["published_by_name"] = admin_names.get(row.get("published_by_admin_user_id"), "")
        terms.append(item)
    return json_response({"success": True, "policies": policies, "terms_versions": terms})


@admin_blueprint.post("/platform-settings/commissions")
@admin_required
def publish_commission():
    """Publish a new commission rate for ONE policy type.

    Creates a new immutable policy version and a new Terms version in the same
    database transaction. The transporter share is always derived server-side;
    a transporter percentage sent by the browser is ignored. The unchanged
    policy for the other commission type is retained as-is.
    """
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    policy_type = (data.get("policy_type") or "").strip()
    if policy_type not in POLICY_TYPES:
        return json_response({"success": False, "message": "policy_type must be one_time_order or agreement."}, 400)
    change_summary = (data.get("change_summary") or "").strip()
    if not change_summary:
        return json_response({"success": False, "message": "A change summary explaining this update is required."}, 400)
    try:
        company_share = parse_company_share_percent(data.get("company_share_percent"))
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    stamp = timestamp_bundle()["iso"]
    admin_user = request.current_user
    with open_db() as db:
        try:
            result = publish_commission_change(
                db, policy_type, company_share, change_summary, admin_user["id"], stamp,
            )
        except ValueError as exc:
            db.rollback()
            return json_response({"success": False, "message": str(exc)}, 400)
        old_policy = result["old_policy"]
        new_policy = result["new_policy"]
        terms_version = result["terms_version"]
        # Admin audit trail (in addition to the immutable version rows).
        db.execute(
            """
            INSERT INTO user_action_logs (
                user_id, user_email, user_role, action_type, action_name, page_url, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(admin_user["id"]),
                admin_user.get("email") or "",
                "platform_admin",
                "admin_platform_settings",
                f"commission_update_{policy_type}",
                "/admin/platform-settings",
                json.dumps({
                    "policy_type": policy_type,
                    "old_company_share_percent": old_policy["company_share_percent"] if old_policy else None,
                    "new_company_share_percent": new_policy["company_share_percent"],
                    "new_policy_version": new_policy["version_number"],
                    "new_terms_version": terms_version["version_number"],
                    "change_summary": change_summary,
                }),
                stamp,
            ),
        )
        db.commit()
    label = POLICY_TYPE_LABELS[policy_type]
    return json_response({
        "success": True,
        "message": f"{label} commission updated. Terms version {terms_version['version_number']} published.",
        "policy_type": policy_type,
        "old_policy": serialize_policy(old_policy),
        "new_policy": serialize_policy(new_policy),
        "terms_version": serialize_terms_version(terms_version),
    })
