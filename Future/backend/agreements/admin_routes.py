"""Archived V1 Agreemental admin endpoints preserved for V2 reference.

Extracted from pre-retirement backend/admin/routes.py (commit 47fbc4b^).
These endpoints are intentionally unmounted in V1 and require full V2
re-audit for tenant/participant authorization and schema compatibility
before any re-integration.
"""

from datetime import datetime

from flask import request

from agreements.commissions import recalculate_payment_fields
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
from auth.helpers import csrf_error, json_response, timestamp_bundle
from chat.routes import insert_chat_message
from shared.db import open_db
from wallet.helpers import adjust_wallet_balance, get_or_create_wallet_for_user, round_money

# Admin blueprint/helpers from active V1 admin.routes:
#   admin_blueprint, admin_required, pagination, rowdict, user_display_sql


# Former admin dashboard() Agreemental queries (removed from V1 dashboard):
#   stats["active_agreements"] = db.execute(
#       "SELECT COUNT(*) AS total FROM agreements WHERE status = 'active'"
#   ).fetchone()["total"]
#   stats["pending_disputes"] = db.execute(
#       "SELECT COUNT(*) AS total FROM agreement_trips WHERE status = 'disputed'"
#   ).fetchone()["total"]
#   stats["failed_payments"] = db.execute(
#       "SELECT COUNT(*) AS total FROM agreement_monthly_payments WHERE status = 'failed'"
#   ).fetchone()["total"]
#
# Former admin user_detail() query (removed from V1 user_detail):
#   agreement_count = db.execute(
#       """
#       SELECT COUNT(DISTINCT a.id) AS total
#       FROM agreements a
#       LEFT JOIN agreement_trucks at ON at.agreement_id = a.id
#       WHERE a.client_user_id = %s OR at.transporter_user_id = %s
#       """,
#       (user_id, user_id),
#   ).fetchone()["total"]


def register_archived_agreement_admin_routes(admin_blueprint, admin_required, pagination, rowdict, user_display_sql):
    """Reference binder showing the retired Agreemental admin route handlers."""

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
            from shared.fuel_credit import annotate_legacy_earnings
            payments = annotate_legacy_earnings(db, payments, "agreement_monthly")
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
            from shared.fuel_credit import annotate_legacy_earnings
            rows = annotate_legacy_earnings(db, rows, "agreement_monthly")
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
            total_km,
            payment["per_km_rate"],
            payment["minimum_guarantee"],
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
