"""Owner-operator consent, credential checks and evidence-based safety reports."""
import json
from flask import request

from auth.helpers import csrf_error, json_response, login_required
from shared.db import open_db
from shared.payments import CheckoutError, parse_positive_id
from shared.roles import TRANSPORTER_ROLES


def register_driver_business_routes(blueprint):
    def mutate(operation, roles):
        if request.current_user.get("role") not in roles:
            return json_response({"success": False, "message": "This action is not permitted for your role."}, 403)
        err = csrf_error()
        if err:
            return err
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return json_response({"success": False, "message": "A JSON object is required."}, 400)
        try:
            with open_db() as db:
                result = operation(db, data)
            return json_response({"success": True, **result})
        except CheckoutError as exc:
            return json_response({"success": False, "message": str(exc), "code": exc.code}, exc.status)
        except (ValueError, TypeError) as exc:
            return json_response({"success": False, "message": str(exc)}, 400)

    @blueprint.post("/api/transporter/drive-myself")
    @login_required
    def drive_myself():
        def assign(db, data):
            from driver.routes import _lock_source_trip, _source_is_active
            owner = request.current_user["id"]
            trip_id = None if data.get("trip_id") is None else parse_positive_id(data["trip_id"], "Trip ID")
            agreement_id = None if data.get("agreement_trip_id") is None else parse_positive_id(data["agreement_trip_id"], "Agreement trip ID")
            truck_id = parse_positive_id(data.get("truck_id"), "Truck ID")
            if (trip_id is None) == (agreement_id is None):
                raise ValueError("Select exactly one trip.")
            source = _lock_source_trip(db, trip_id, agreement_id, owner, truck_id)
            if not source or not _source_is_active({"agreement_trip_id": agreement_id}, source):
                raise CheckoutError("An eligible owned trip and truck are required.", 409, "owner_operator_trip_invalid")
            truck = db.execute_exact("SELECT * FROM vehicles WHERE id=%s AND owner_user_id=%s FOR UPDATE", (truck_id, owner)).fetchone()
            if not truck or truck["status"] not in {"active", "on_job"}:
                raise CheckoutError("An eligible owned or controlled truck is required.", 409, "owner_operator_truck_invalid")
            credential = db.execute_exact(
                "SELECT c.* FROM owner_operator_credentials c JOIN users u ON u.id=c.verified_by "
                "WHERE c.user_id=%s AND c.license_expiry>=CURRENT_DATE AND u.role='admin' FOR SHARE OF c", (owner,),
            ).fetchone()
            if not credential:
                raise CheckoutError("Verified current driving credentials are required. Request an authorized credential review.", 409, "owner_operator_credentials_required")
            db.execute_exact(
                "INSERT INTO driver_profiles(user_id,unique_driver_id,license_number,license_expiry,verified_status,employment_type) "
                "VALUES(%s,%s,%s,%s,'verified','owner_operator') ON CONFLICT(user_id) DO NOTHING",
                (owner, f"OOP-{owner}", credential["license_number"], credential["license_expiry"]),
            )
            profile = db.execute_exact("SELECT * FROM driver_profiles WHERE user_id=%s FOR UPDATE", (owner,)).fetchone()
            existing = db.execute_exact("SELECT * FROM driver_trip_assignments WHERE driver_user_id=%s AND status IN('accepted','in_progress')", (owner,)).fetchone()
            if existing and existing["assignment_mode"] == "owner_operator" and existing["truck_id"] == truck_id and existing["trip_id"] == trip_id and existing["agreement_trip_id"] == agreement_id:
                return {"assignment_id": existing["id"], "replayed": True}
            busy = db.execute_exact(
                "SELECT 1 FROM driver_trip_assignments WHERE status IN('accepted','in_progress') "
                "AND (driver_user_id=%s OR truck_id=%s OR trip_id=%s OR agreement_trip_id=%s) LIMIT 1",
                (owner, truck_id, trip_id, agreement_id),
            ).fetchone()
            if busy or not profile["is_available"]:
                raise CheckoutError("Driver, truck or trip already has an active assignment.", 409, "assignment_conflict")
            result = db.execute_exact(
                "INSERT INTO driver_trip_assignments(driver_user_id,transporter_user_id,truck_id,trip_type,trip_id,agreement_trip_id,offer_amount,status,accepted_at,assignment_mode) "
                "VALUES(%s,%s,%s,%s,%s,%s,0,'accepted',now(),'owner_operator') RETURNING id",
                (owner, owner, truck_id, "agreement" if agreement_id else "one_time", trip_id, agreement_id),
            ).fetchone()
            db.execute_exact("UPDATE driver_profiles SET current_truck_id=%s,is_available=false,license_number=%s,license_expiry=%s,updated_at=now() WHERE user_id=%s",
                             (truck_id, credential["license_number"], credential["license_expiry"], owner))
            db.execute_exact("UPDATE vehicles SET driver_name=u.full_name,driver_cnic=u.cnic,updated_at=now() FROM users u WHERE vehicles.id=%s AND u.id=%s", (truck_id, owner))
            return {"assignment_id": result["id"], "assignment_mode": "owner_operator", "replayed": False}
        return mutate(assign, TRANSPORTER_ROLES)

    @blueprint.post("/api/admin/owner-operator-credentials/<int:user_id>")
    @login_required
    def verify_owner_credentials(user_id):
        def verify(db, data):
            from datetime import date
            license_number = str(data.get("license_number", "")).strip()
            evidence = str(data.get("verification_evidence", "")).strip()
            expiry = date.fromisoformat(str(data.get("license_expiry", "")))
            if not 1 <= len(license_number) <= 64 or len(evidence) < 10 or len(evidence) > 4000 or expiry < date.today():
                raise ValueError("Current license and documented independent credential verification are required.")
            user = db.execute_exact("SELECT id FROM users WHERE id=%s AND role='transporter'", (user_id,)).fetchone()
            if not user:
                raise CheckoutError("Transporter not found.", 404, "transporter_not_found")
            db.execute_exact(
                "INSERT INTO owner_operator_credentials(user_id,license_number,license_expiry,verified_by,verification_evidence) "
                "VALUES(%s,%s,%s,%s,%s) ON CONFLICT(user_id) DO UPDATE SET license_number=excluded.license_number,"
                "license_expiry=excluded.license_expiry,verified_by=excluded.verified_by,verification_evidence=excluded.verification_evidence,verified_at=now()",
                (user_id, license_number, expiry, request.current_user["id"], evidence),
            )
            return {"message": "Driving credentials recorded after authorized verification."}
        return mutate(verify, {"platform_admin"})

    @blueprint.post("/api/operational-incidents")
    @login_required
    def report_operational_incident():
        def report(db, data):
            assignment_id = parse_positive_id(data.get("assignment_id"), "Assignment ID")
            actor = request.current_user["id"]
            assignment = db.execute_exact("SELECT * FROM driver_trip_assignments WHERE id=%s AND (driver_user_id=%s OR transporter_user_id=%s) FOR SHARE", (assignment_id, actor, actor)).fetchone()
            if not assignment or assignment["accepted_at"] is None:
                raise CheckoutError("Consented assignment not found.", 404, "assignment_not_found")
            kind = data.get("incident_type")
            description = str(data.get("description", "")).strip()
            evidence = data.get("evidence", [])
            if kind not in {"abandonment", "accident", "theft", "negligence", "emergency", "other"} or not 10 <= len(description) <= 10000 or not isinstance(evidence, list) or len(evidence) > 50 or len(json.dumps(evidence)) > 50000:
                raise ValueError("Provide the incident type, detailed report and bounded evidence list.")
            # Persist immutable assignment and latest authoritative GPS evidence.
            gps = db.execute_exact("SELECT id,lat,lng,recorded_at FROM driver_gps_pings WHERE driver_user_id=%s AND truck_id=%s AND trip_id IS NOT DISTINCT FROM %s AND agreement_trip_id IS NOT DISTINCT FROM %s ORDER BY recorded_at DESC LIMIT 1", (assignment["driver_user_id"], assignment["truck_id"],assignment['trip_id'],assignment['agreement_trip_id'])).fetchone()
            snapshot = {"submitted": evidence, "assignment": {k: assignment[k] for k in ("id", "driver_user_id", "transporter_user_id", "trip_id", "agreement_trip_id", "truck_id", "accepted_at")}, "latest_gps": {k: str(v) for k, v in gps.items()} if gps else None}
            row = db.execute_exact("INSERT INTO operational_incidents(assignment_id,reporter_user_id,incident_type,description,evidence) VALUES(%s,%s,%s,%s,%s::jsonb) RETURNING id", (assignment_id, actor, kind, description, json.dumps(snapshot))).fetchone()
            if assignment["trip_id"]:
                source = db.execute_exact("SELECT order_id FROM shipment_trips WHERE id=%s", (assignment["trip_id"],)).fetchone()
                for user_id in {assignment["driver_user_id"], assignment["transporter_user_id"]}:
                    db.execute_exact("INSERT INTO shipment_notifications(order_id,trip_id,user_id,notification_type,message) VALUES(%s,%s,%s,%s,%s)",
                                     (source["order_id"], assignment["trip_id"], user_id, f"operational_incident:{row['id']}", "An operational incident requires evidence-based review. No financial penalty has been applied."))
                from shared.notifications import notify_admins
                notify_admins(db,source['order_id'],assignment['trip_id'],f"operational_incident:{row['id']}",f"Operational incident #{row['id']} requires authorized investigation.")
            return {"incident_id": row["id"], "status": "investigating", "message": "Incident recorded for authorized investigation. No automatic penalty or reserve deduction was applied."}
        return mutate(report, TRANSPORTER_ROLES | {"driver"})

    @blueprint.post("/api/admin/operational-incidents/<int:incident_id>/decision")
    @login_required
    def decide_operational_incident(incident_id):
        def decide(db, data):
            status = data.get("status")
            evidence = str(data.get("decision_evidence", "")).strip()
            if status not in {"confirmed", "dismissed"} or not 10 <= len(evidence) <= 10000:
                raise ValueError("An evidence-based investigation decision is required.")
            row = db.execute_exact("SELECT * FROM operational_incidents WHERE id=%s FOR UPDATE", (incident_id,)).fetchone()
            if not row:
                raise CheckoutError("Incident not found.", 404, "incident_not_found")
            if row["status"] != "investigating":
                raise CheckoutError("Incident already has an authorized decision.", 409, "incident_decided")
            db.execute_exact("UPDATE operational_incidents SET status=%s,decision_by=%s,decision_evidence=%s,decision_at=now() WHERE id=%s", (status, request.current_user["id"], evidence, incident_id))
            return {"status": status, "financial_adjustment": "blocked_pending_approved_penalty_policy"}
        return mutate(decide, {"platform_admin"})

    @blueprint.get("/api/admin/operational-incidents")
    @login_required
    def list_operational_investigations():
        if request.current_user.get('role') != 'platform_admin':
            return json_response({'success':False,'message':'Admin investigation access required.'},403)
        status=request.args.get('status','investigating')
        if status not in {'investigating','confirmed','dismissed'}:
            return json_response({'success':False,'message':'Invalid investigation status.'},400)
        try:
            limit=min(100,parse_positive_id(request.args.get('limit','50'),'Limit'))
        except ValueError as exc:
            return json_response({'success':False,'message':str(exc)},400)
        with open_db() as db:
            rows=db.execute_exact(
                "SELECT i.*,a.driver_user_id,a.transporter_user_id,a.trip_id,a.agreement_trip_id,a.truck_id,"
                "d.full_name AS driver_name,t.full_name AS transporter_name "
                "FROM operational_incidents i JOIN driver_trip_assignments a ON a.id=i.assignment_id "
                "JOIN users d ON d.id=a.driver_user_id JOIN users t ON t.id=a.transporter_user_id "
                "WHERE i.status=%s ORDER BY i.created_at,i.id LIMIT %s",(status,limit),
            ).fetchall()
        response=json_response({'success':True,'incidents':rows})
        response.headers['Cache-Control']='no-store'
        return response

    @blueprint.get("/api/operational-incidents/<int:incident_id>")
    @login_required
    def read_operational_investigation(incident_id):
        with open_db() as db:
            row=db.execute_exact(
                "SELECT i.*,a.driver_user_id,a.transporter_user_id,a.trip_id,a.agreement_trip_id,a.truck_id "
                "FROM operational_incidents i JOIN driver_trip_assignments a ON a.id=i.assignment_id "
                "WHERE i.id=%s AND (%s OR a.driver_user_id=%s OR a.transporter_user_id=%s)",
                (incident_id,request.current_user.get('role')=='platform_admin',request.current_user['id'],request.current_user['id']),
            ).fetchone()
        if not row:
            return json_response({'success':False,'message':'Incident not found.'},404)
        response=json_response({'success':True,'incident':row})
        response.headers['Cache-Control']='no-store'
        return response

    @blueprint.post("/api/transporter/trips/<int:assignment_id>/cancellation-request")
    @login_required
    def request_trip_cancellation(assignment_id):
        def initiate(db, data):
            assignment = db.execute_exact("SELECT id FROM driver_trip_assignments WHERE id=%s AND transporter_user_id=%s AND status IN('accepted','in_progress') FOR UPDATE", (assignment_id, request.current_user["id"])).fetchone()
            reason = str(data.get("reason", "")).strip()
            if not assignment:
                raise CheckoutError("Active assigned trip not found in your fleet.", 404, "assignment_not_found")
            if not 10 <= len(reason) <= 4000:
                raise ValueError("A cancellation reason is required.")
            row = db.execute_exact("INSERT INTO trip_cancellation_requests(assignment_id,transporter_user_id,reason) VALUES(%s,%s,%s) ON CONFLICT(assignment_id) DO NOTHING RETURNING id", (assignment_id, request.current_user["id"], reason)).fetchone()
            return {"request_id": row["id"] if row else None, "status": "pending_policy_review", "message": "Cancellation requested. Financial cancellation requires an approved refund policy; fuel debt cannot reduce Client escrow."}
        return mutate(initiate, TRANSPORTER_ROLES)
