import json
from decimal import Decimal
from datetime import date, datetime

from flask import Blueprint, request
from werkzeug.security import generate_password_hash

from auth.helpers import csrf_error, json_response, login_required, normalize_email, require_admin_role, split_name, timestamp_bundle
from shared.commissions import (
    POLICY_TYPES,
    POLICY_TYPE_LABELS,
    get_active_policy,
    get_current_terms_version,
    list_policy_versions,
    list_terms_versions,
    parse_company_share_percent,
    publish_commission_change,
    serialize_policy,
    serialize_terms_version,
)
from shared.db import open_db
from shared.notifications import notify_best_effort as notify
from wallet.helpers import get_or_create_wallet_for_user, insert_wallet_transaction, round_money
from shared.payments import DummyCardProvider, get_payment_provider, parse_money_amount


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
            "pending_disputes": db.execute("SELECT COUNT(*) AS total FROM shipment_disputes WHERE status = 'open'").fetchone()["total"],
            "pending_withdrawals": db.execute("SELECT COUNT(*) AS total FROM wallet_withdrawal_requests WHERE status = 'pending'").fetchone()["total"],
        }
        disputes = db.execute(
            """
            SELECT d.id, d.shipment_id, d.created_at, s.pickup_city, s.dropoff_city
            FROM shipment_disputes d
            JOIN shipments s ON s.id = d.shipment_id
            WHERE d.status = 'open'
            ORDER BY d.created_at DESC
            LIMIT 5
            """
        ).fetchall()
    return json_response({
        "success": True,
        "stats": stats,
        "recent_disputes": [dict(row) for row in disputes],
    })


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
    return json_response({"success": True, "user": serialize_admin_user(user), "wallet": {"balance": round_money(wallet["balance"]), "locked_balance": round_money(wallet["locked_balance"])}, "truck_count": len(trucks), "trucks": [serialize_truck(row) for row in trucks]})


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
    try:
        simulated = isinstance(get_payment_provider(), DummyCardProvider)
    except CheckoutError:
        simulated = False
    if not simulated:
        return json_response({"success": False, "code": "payout_provider_unavailable",
                              "message": "Withdrawals are unavailable until payout processing is configured."}, 503)
    stamp = timestamp_bundle()
    with open_db() as db:
        req = rowdict(db.execute("SELECT * FROM wallet_withdrawal_requests WHERE id = %s FOR UPDATE", (request_id,)).fetchone())
        if not req:
            return json_response({"success": False, "message": "Withdrawal request not found."}, 404)
        if req["status"] != "pending":
            return json_response({"success": False, "message": "Withdrawal request is already resolved."}, 400)
        user = rowdict(db.execute("SELECT id, role, legacy_role FROM users WHERE id = %s", (req["user_id"],)).fetchone())
        if user is None:
            return json_response({"success": False, "message": "Account not found."}, 404)
        user["role"] = user.get("legacy_role") or user["role"]
        if user["role"] not in {"transporter", "logistics_provider"}:
            return json_response({"success": False, "message": "Transporter account required."}, 403)
        wallet, wallet_error = get_or_create_wallet_for_user(db, user)
        if wallet_error:
            return wallet_error
        wallet = rowdict(db.execute("SELECT * FROM wallets WHERE id=%s AND user_id=%s FOR UPDATE",
                                    (wallet["id"], req["user_id"])).fetchone())
        try:
            amount = parse_money_amount(req["amount"])
        except ValueError as exc:
            return json_response({"success": False, "message": str(exc)}, 400)
        from decimal import Decimal
        from wallet.withdrawal_limits import max_withdrawable
        if wallet is None or amount > Decimal(str(max_withdrawable(wallet))):
            return json_response({"success": False, "message": "Insufficient unreserved withdrawal balance."}, 400)
        wallet = rowdict(db.execute("UPDATE wallets SET balance=balance-%s,updated_at=%s WHERE id=%s RETURNING *",
                                    (amount, stamp["iso"], wallet["id"])).fetchone())
        db.execute("UPDATE wallet_withdrawal_requests SET status='approved',resolved_at=%s WHERE id=%s AND status='pending'",
                   (stamp["iso"],request_id))
        insert_wallet_transaction(db, wallet, req["user_id"], "withdrawal", -amount,
                                  description="Admin-approved simulated withdrawal; no bank transfer", reference_id=str(request_id))
        db.commit()
        notify(
            db,
            None,
            None,
            req["user_id"],
            "withdrawal_approved",
            f"Your withdrawal request #{request_id} for PKR {amount:,.2f} has been approved.",
        )
        db.commit()
    return json_response({"success": True, "simulated": True,
                          "message": "Simulated withdrawal approved; no bank transfer was made."})


@admin_blueprint.post("/wallet/withdrawals/<int:request_id>/reject")
@admin_required
def reject_withdrawal(request_id):
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        req = rowdict(db.execute("SELECT * FROM wallet_withdrawal_requests WHERE id = %s FOR UPDATE", (request_id,)).fetchone())
        if not req or req.get("status") != "pending":
            return json_response({"success": False, "message": "Pending withdrawal request not found."}, 404)
        result = db.execute("UPDATE wallet_withdrawal_requests SET status = 'rejected', resolved_at = %s WHERE id = %s AND status = 'pending'", (timestamp_bundle()["iso"], request_id))
        if result.rowcount == 0:
            return json_response({"success": False, "message": "Pending withdrawal request not found."}, 404)
        db.commit()
        amount = parse_money_amount(req["amount"])
        notify(
            db,
            None,
            None,
            req["user_id"],
            "withdrawal_rejected",
            f"Your withdrawal request #{request_id} for PKR {amount:,.2f} has been rejected.",
        )
        db.commit()
    return json_response({"success": True})


# ---------------------------------------------------------------------------
# Platform settings — versioned commission policies
# ---------------------------------------------------------------------------

@admin_blueprint.get("/platform-settings/commissions")
@admin_required
def commission_settings():
    """Current active one-time order commission policy and Terms version."""
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
    """Immutable one-time policy and Terms version history."""
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
    """Publish a new one-time order commission rate and Terms version.

    The transporter share is derived server-side and published atomically with
    the immutable Terms version.
    """
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    policy_type = (data.get("policy_type") or "").strip()
    if policy_type not in POLICY_TYPES:
        return json_response({"success": False, "message": "policy_type must be one_time_order."}, 400)
    change_summary = (data.get("change_summary") or "").strip()
    if not change_summary:
        return json_response({"success": False, "message": "A change summary explaining this update is required."}, 400)
    try:
        company_share = parse_company_share_percent(data.get("company_share_percent"))
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    if company_share != Decimal("20.00"):
        return json_response({"success": False, "code": "approved_fee_schedule_required",
                              "message": "The approved freight platform deduction is 20%, itemized as 10% + 5% + 3% + 2%. A different commission is not approved."}, 400)

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


# ---------------------------------------------------------------------------
# One-time delivery disputes (Phase H) + 6-hour deadline manual trigger
# ---------------------------------------------------------------------------
from orders.lifecycle import (  # noqa: E402
    process_overdue_delivery_confirmations,
    resolve_dispute_client_win,
    resolve_dispute_transporter_win,
    serialize_dispute,
)
from shared.payments import CheckoutError, serialize_payment_summary  # noqa: E402


def _one_time_dispute_row(db, dispute_id):
    row = db.execute(
        """
        SELECT d.*,
               COALESCE(NULLIF(trim(c.full_name), ''), c.email, 'Client') AS client_name,
               COALESCE(NULLIF(trim(t.full_name), ''), t.email, 'Transporter') AS transporter_name,
               s.pickup_city, s.dropoff_city, s.status AS shipment_status,
               tra.rating_average,
               COALESCE(tra.rating_count, 0) AS rating_count
        FROM shipment_disputes d
        JOIN users c ON c.id = d.client_user_id
        JOIN users t ON t.id = d.transporter_user_id
        JOIN shipments s ON s.id = d.shipment_id
        LEFT JOIN transporter_review_aggregates tra ON tra.transporter_user_id = d.transporter_user_id
        WHERE d.id = %s
        """,
        (dispute_id,),
    ).fetchone()
    return dict(row) if row else None


@admin_blueprint.get("/one-time-disputes")
@admin_required
def list_one_time_disputes():
    """Open one-time delivery disputes queue (client_no + confirmation_timeout)."""
    status = (request.args.get("status") or "open").strip().lower()
    with open_db() as db:
        if status == "all":
            rows = db.execute(
                """
                SELECT d.*, s.pickup_city, s.dropoff_city,
                       COALESCE(NULLIF(trim(c.full_name), ''), c.email, 'Client') AS client_name,
                       COALESCE(NULLIF(trim(t.full_name), ''), t.email, 'Transporter') AS transporter_name
                FROM shipment_disputes d
                JOIN users c ON c.id = d.client_user_id
                JOIN users t ON t.id = d.transporter_user_id
                JOIN shipments s ON s.id = d.shipment_id
                ORDER BY d.created_at DESC
                """
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT d.*, s.pickup_city, s.dropoff_city,
                       COALESCE(NULLIF(trim(c.full_name), ''), c.email, 'Client') AS client_name,
                       COALESCE(NULLIF(trim(t.full_name), ''), t.email, 'Transporter') AS transporter_name
                FROM shipment_disputes d
                JOIN users c ON c.id = d.client_user_id
                JOIN users t ON t.id = d.transporter_user_id
                JOIN shipments s ON s.id = d.shipment_id
                WHERE d.status = %s
                ORDER BY d.created_at DESC
                """,
                (status,),
            ).fetchall()
    disputes = []
    for row in rows:
        row = dict(row)
        disputes.append(serialize_dispute(row) | {
            "client_name": row.get("client_name"),
            "transporter_name": row.get("transporter_name"),
            "pickup_city": row.get("pickup_city"),
            "dropoff_city": row.get("dropoff_city"),
        })
    return json_response({"success": True, "disputes": disputes})


@admin_blueprint.get("/one-time-disputes/<int:dispute_id>")
@admin_required
def one_time_dispute_detail(dispute_id):
    """Full order / trip / payment / chat / audit context for one dispute."""
    with open_db() as db:
        row = _one_time_dispute_row(db, dispute_id)
        if not row:
            return json_response({"success": False, "message": "Dispute not found."}, 404)
        from orders.business_lifecycle import serialize_settlement
        business_settlement=serialize_settlement(db.execute_exact('SELECT * FROM freight_settlements WHERE trip_id=%s',(row['trip_id'],)).fetchone())
        incident_evidence=db.execute('SELECT submitted_by,evidence,created_at FROM delivery_incident_evidence WHERE dispute_id=%s ORDER BY id',(dispute_id,)).fetchall()
        payment = None
        if row.get("payment_id"):
            p = db.execute("SELECT * FROM payments WHERE id = %s", (row["payment_id"],)).fetchone()
            payment = serialize_payment_summary(dict(p), viewer="client") if p else None
        trip = db.execute("SELECT * FROM shipment_trips WHERE id = %s", (row["trip_id"],)).fetchone()
        messages = []
        if row.get("chat_thread_id"):
            messages = [
                dict(m) for m in db.execute(
                    """
                    SELECT cm.id, cm.sender_user_id, cm.message_type, cm.content, cm.created_at,
                           COALESCE(NULLIF(trim(u.full_name), ''), u.email, 'User') AS sender_name
                    FROM chat_messages cm JOIN users u ON u.id = cm.sender_user_id
                    WHERE cm.thread_id = %s ORDER BY cm.id ASC
                    """,
                    (row["chat_thread_id"],),
                ).fetchall()
            ]
        history = [
            dict(h) for h in db.execute(
                "SELECT old_status, new_status, created_at FROM shipment_status_history "
                "WHERE shipment_id = %s ORDER BY id ASC",
                (row["shipment_id"],),
            ).fetchall()
        ]
    detail = serialize_dispute(row) | {
        "client_name": row.get("client_name"),
        "transporter_name": row.get("transporter_name"),
        "transporter_rating_average": row.get("rating_average"),
        "transporter_rating_count": int(row.get("rating_count") or 0),
        "pickup_city": row.get("pickup_city"),
        "dropoff_city": row.get("dropoff_city"),
        "shipment_status": row.get("shipment_status"),
        "trip_status": trip["status"] if trip else None,
        "payment": payment,
        "settlement": business_settlement,
        "evidence": incident_evidence,
        "chat_messages": messages,
        "status_history": history,
    }
    return json_response({"success": True, "dispute": detail})


@admin_blueprint.post("/one-time-disputes/<int:dispute_id>/resolve")
@admin_required
def resolve_one_time_dispute(dispute_id):
    """Resolve a one-time dispute (transporter_win releases payout, client_win
    refunds). Requires admin notes. Idempotent."""
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    resolution = (data.get("resolution") or "").strip().lower()
    notes = data.get("notes")
    if resolution not in ("transporter_win", "client_win"):
        return json_response(
            {"success": False, "message": "resolution must be 'transporter_win' or 'client_win'."}, 400
        )
    with open_db() as db:
        try:
            if resolution == "transporter_win":
                result = resolve_dispute_transporter_win(db, request.current_user, dispute_id, notes)
            else:
                result = resolve_dispute_client_win(db, request.current_user, dispute_id, notes)
        except CheckoutError as exc:
            db.rollback()
            return json_response({"success": False, "message": exc.message, "code": exc.code}, exc.status)
        db.commit()
    return json_response({
        "success": True,
        "already": result["already"],
        "message": "Dispute resolved.",
        "dispute": result["dispute"],
    })


@admin_blueprint.post("/delivery-confirmations/process-overdue")
@admin_required
def trigger_overdue_delivery_sweep():
    """Admin-only manual trigger for the 6-hour confirmation deadline processor
    (the same production function the scheduler runs). For testing/ops."""
    err = csrf_error()
    if err:
        return err
    with open_db() as db:
        result = process_overdue_delivery_confirmations(db)
        db.commit()
    return json_response({"success": True, **result})
