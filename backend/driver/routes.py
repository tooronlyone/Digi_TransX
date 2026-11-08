import math
from datetime import date, datetime
from flask import Blueprint, jsonify, request
from auth.helpers import csrf_error, json_response, login_required, timestamp_bundle
from shared.db import open_db
from shared.payments import round_money
from shared.roles import DRIVER_ROLES, TRANSPORTER_ROLES
from shared.validation import finite_decimal, finite_float, bounded_count
from shared.coordinates import parse_optional_coordinate_pair, CoordinateValidationError
from decimal import Decimal, ROUND_HALF_UP
from wallet.helpers import adjust_wallet_balance, get_or_create_wallet_for_user

driver_blueprint = Blueprint("driver", __name__)

from driver.business_rules import register_driver_business_routes
register_driver_business_routes(driver_blueprint)


def _positive_id(value, label):
    number = bounded_count(value, label, maximum=2**63-1)
    if number < 1:
        raise ValueError(f"{label} must be a positive whole number.")
    return number


def _optional_id(data, key):
    return None if data.get(key) in (None, "") else _positive_id(data[key], key)


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required.")
    return data


def _text(data, key, *, default="", maximum=2000):
    value = data.get(key, default)
    if value is None:
        value = default
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{key} must be text of at most {maximum} characters.")
    return value.strip()


def _lock_source_trip(db, trip_id, agreement_trip_id, transporter_user_id, truck_id):
    if trip_id is not None and agreement_trip_id is None:
        return db.execute("SELECT * FROM shipment_trips WHERE id=%s AND transporter_user_id=%s AND truck_id=%s FOR UPDATE", (trip_id,transporter_user_id,truck_id)).fetchone()
    if agreement_trip_id is not None and trip_id is None:
        return db.execute("SELECT * FROM agreement_trips WHERE id=%s AND transporter_user_id=%s AND truck_id=%s FOR UPDATE", (agreement_trip_id,transporter_user_id,truck_id)).fetchone()
    return None


def _source_matches(assignment, source, truck):
    expected_type = "agreement" if assignment.get("agreement_trip_id") is not None else "one_time"
    return bool(source and truck and assignment.get("trip_type") == expected_type
                and source["truck_id"] == assignment["truck_id"] == truck["id"]
                and source["transporter_user_id"] == assignment["transporter_user_id"] == truck["owner_user_id"])


def _source_is_active(assignment, source):
    states = {"pending", "in_progress"} if assignment.get("agreement_trip_id") is not None else {"ready_to_start", "in_progress"}
    return bool(source and source["status"] in states)


def _lock_assignment_context(db, snapshot):
    """Lock source trip -> truck -> driver profile -> exact assignment.

    Source lifecycle triggers acquire driver/profile rows after the source trip.
    Never reverse that order when accepting, tracking or reviewing an assignment.
    """
    source = _lock_source_trip(db, snapshot.get("trip_id"), snapshot.get("agreement_trip_id"),snapshot["transporter_user_id"],snapshot["truck_id"])
    truck = db.execute("SELECT id,owner_user_id FROM vehicles WHERE id=%s FOR UPDATE", (snapshot["truck_id"],)).fetchone()
    profile = db.execute("SELECT * FROM driver_profiles WHERE user_id=%s FOR UPDATE", (snapshot["driver_user_id"],)).fetchone()
    assignment = db.execute("SELECT * FROM driver_trip_assignments WHERE id=%s FOR UPDATE", (snapshot["id"],)).fetchone()
    keys = ("driver_user_id", "transporter_user_id", "truck_id", "trip_type", "trip_id", "agreement_trip_id")
    if not assignment or any(assignment.get(key) != snapshot.get(key) for key in keys):
        return None, None, None, None
    return source, truck, profile, assignment


def ensure_driver_role(user):
    role = (user.get("role") or "").strip().lower()
    if role not in DRIVER_ROLES:
        return json_response({"success": False, "message": "Driver account required."}, 403)
    return None


@driver_blueprint.get("/api/driver/me")
@login_required
def get_driver_profile():
    err = ensure_driver_role(request.current_user)
    if err:
        return err

    user_id = request.current_user["id"]
    with open_db() as db:
        profile = db.execute(
            """
            SELECT dp.*, u.full_name, u.email, u.phone, u.city,
                   v.truck_number, v.truck_model, v.truck_type
            FROM driver_profiles dp
            JOIN users u ON u.id = dp.user_id
            LEFT JOIN vehicles v ON v.id = dp.current_truck_id
            WHERE dp.user_id = %s
            """,
            (user_id,),
        ).fetchone()

        if not profile:
            return json_response({"success": False, "message": "Driver profile not found."}, 404)

        # Active or requested trips
        assignments = db.execute(
            """
            SELECT dta.*, v.truck_number, v.truck_model, u.full_name AS transporter_name, u.phone AS transporter_phone
            FROM driver_trip_assignments dta
            JOIN vehicles v ON v.id = dta.truck_id
            JOIN users u ON u.id = dta.transporter_user_id
            WHERE dta.driver_user_id = %s
            ORDER BY dta.id DESC
            LIMIT 10
            """,
            (user_id,),
        ).fetchall()

        # Reviews & incidents count
        incidents = db.execute(
            """
            SELECT id, incident_type, severity, description, status, created_at
            FROM driver_incidents
            WHERE driver_user_id = %s
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()

    return json_response({
        "success": True,
        "driver": dict(profile),
        "recent_trips": [dict(a) for a in assignments],
        "incidents": [dict(i) for i in incidents],
    })


@driver_blueprint.post("/api/driver/gps/ping")
@driver_blueprint.post("/api/transporter/owner-operator/gps")
@login_required
def post_gps_ping():
    """Stream live GPS location from driver's smartphone or web app."""
    owner_mode = request.path == "/api/transporter/owner-operator/gps"
    if owner_mode and request.current_user.get('role') not in TRANSPORTER_ROLES:
        return json_response({'success':False,'message':'Transporter account required for owner-operator tracking.'},403)
    err = None if owner_mode else ensure_driver_role(request.current_user)
    if err:
        return err
    err = csrf_error()
    if err:
        return err
    try:
        data = _payload()
        lat = finite_float(data.get("lat"),"Latitude",minimum=Decimal("-90"),maximum=Decimal("90"))
        lng = finite_float(data.get("lng"),"Longitude",minimum=Decimal("-180"),maximum=Decimal("180"))
        speed_kmh = finite_float(data.get("speed_kmh",0),"Speed",maximum=Decimal("250"))
        heading = finite_float(data.get("heading",0),"Heading",maximum=Decimal("360")) % 360
        altitude = (None if data.get("altitude") is None else
                    finite_float(data["altitude"],"Altitude",minimum=Decimal("-1000"),maximum=Decimal("100000")))
        battery = None if data.get("battery_level") is None else bounded_count(data["battery_level"],"Battery level",maximum=100)
        supplied_ids = {key: _optional_id(data,key) for key in ("trip_id", "agreement_trip_id", "truck_id", "assignment_id")}
    except (ValueError, TypeError) as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        snapshots = db.execute(
            "SELECT * FROM driver_trip_assignments WHERE driver_user_id=%s "
            "AND status IN ('accepted','in_progress') ORDER BY id LIMIT 2", (user_id,),
        ).fetchall()
        if len(snapshots) != 1:
            return json_response({"success": False,"message": "An active accepted assignment is required for tracking."},409)
        source, truck, profile, assignment = _lock_assignment_context(db,snapshots[0])
        if owner_mode and (not assignment or assignment.get("assignment_mode") != "owner_operator" or assignment["transporter_user_id"] != user_id):
            return json_response({"success":False,"message":"An active owner-operator assignment is required."},403)
        if owner_mode and not db.execute('SELECT 1 FROM owner_operator_credentials c JOIN users u ON u.id=c.verified_by WHERE c.user_id=%s AND c.license_expiry>=CURRENT_DATE AND u.role=%s',(user_id,'admin')).fetchone():
            return json_response({'success':False,'message':'Verified current driving credentials are required for owner-operator tracking.','code':'owner_operator_credentials_required'},409)
        if (not assignment or assignment["status"] not in {"accepted","in_progress"}
                or not _source_matches(assignment,source,truck) or not _source_is_active(assignment,source)
                or not profile or profile["current_truck_id"] != truck["id"] or profile["is_available"] is not False):
            return json_response({"success": False,"message": "The assignment is no longer active for tracking."},409)
        expected = {"trip_id":assignment["trip_id"],"agreement_trip_id":assignment["agreement_trip_id"],
                    "truck_id":truck["id"],"assignment_id":assignment["id"]}
        if any(value is not None and value != expected[key] for key,value in supplied_ids.items()):
            return json_response({"success": False,"message": "Tracking identifiers do not match your active assignment."},404)
        truck_id,trip_id,agreement_trip_id = truck["id"],assignment["trip_id"],assignment["agreement_trip_id"]

        # Insert live GPS ping
        db.execute(
            """
            INSERT INTO driver_gps_pings (
                driver_user_id, truck_id, trip_id, agreement_trip_id,
                lat, lng, speed_kmh, heading, altitude, battery_level
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, truck_id, trip_id, agreement_trip_id, lat, lng, speed_kmh, heading, altitude, battery),
        )

        # Only the truck bound to this accepted assignment may move.
        db.execute(
            """
            UPDATE vehicles
            SET current_lat = %s, current_lng = %s, updated_at = NOW()
            WHERE id = %s AND owner_user_id = %s
            """,
            (lat, lng, truck_id, assignment["transporter_user_id"]),
        )
        db.commit()

    return json_response({"success": True, "message": "GPS ping recorded.", "lat": lat, "lng": lng,
                          "assignment_id":assignment["id"],"truck_id":truck_id,"trip_id":trip_id,"agreement_trip_id":agreement_trip_id})


@driver_blueprint.post("/api/driver/trips/<int:assignment_id>/respond")
@login_required
def respond_trip_assignment(assignment_id):
    """Driver accepts or rejects a trip dispatch request."""
    err = ensure_driver_role(request.current_user)
    if err:
        return err
    err = csrf_error()
    if err:
        return err
    try:
        data = _payload()
        action = _text(data,"action",maximum=16).lower()
    except ValueError as exc:
        return json_response({"success":False,"message":str(exc)},400)
    if action not in {"accept", "reject"}:
        return json_response({"success": False, "message": "Action must be 'accept' or 'reject'."}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        snapshot = db.execute(
            "SELECT * FROM driver_trip_assignments WHERE id = %s AND driver_user_id = %s",
            (assignment_id, user_id),
        ).fetchone()
        if not snapshot:
            return json_response({"success": False, "message": "Trip request not found."}, 404)
        source,truck,profile,assignment = _lock_assignment_context(db,snapshot)
        if not assignment or not profile:
            return json_response({"success":False,"message":"Trip request changed. Reload and retry."},409)
        if assignment["status"] != "requested":
            return json_response({"success": False, "message": f"Trip already {assignment['status']}."}, 409)

        if action == "accept":
            if not _source_matches(assignment,source,truck) or not _source_is_active(assignment,source):
                return json_response({"success":False,"message":"This trip is no longer available in the dispatcher's fleet."},409)
            if profile["is_available"] is not True:
                return json_response({"success":False,"message":"You already have an active assignment."},409)
            busy = db.execute(
                "SELECT 1 AS busy FROM driver_trip_assignments WHERE status IN ('accepted','in_progress') "
                "AND (driver_user_id=%s OR truck_id=%s OR trip_id=%s OR agreement_trip_id=%s) LIMIT 1",
                (user_id,truck["id"],assignment["trip_id"],assignment["agreement_trip_id"]),
            ).fetchone()
            if busy:
                return json_response({"success":False,"message":"Driver, truck or trip already has an active assignment."},409)
            if profile.get("employment_type") in {"per_trip", "temporary"}:
                from shared.reserves import ensure_security_reserve
                from shared.payments import CheckoutError
                try:
                    ensure_security_reserve(db, user_id, role="temporary_driver")
                except CheckoutError as exc:
                    return json_response({"success":False,"message":str(exc),"code":exc.code},exc.status)

        new_status = "accepted" if action == "accept" else "rejected"
        db.execute(
            "UPDATE driver_trip_assignments SET status = %s, "
            "accepted_at = CASE WHEN %s='accepted' THEN now() ELSE accepted_at END, "
            "updated_at = NOW() WHERE id = %s AND status='requested'",
            (new_status,new_status,assignment_id),
        )

        if action == "accept":
            # Assign current truck to driver
            db.execute(
                "UPDATE driver_profiles SET current_truck_id = %s, is_available = FALSE, updated_at = NOW() WHERE user_id = %s",
                (assignment["truck_id"], user_id),
            )
            db.execute(
                "UPDATE vehicles SET driver_name=u.full_name,driver_cnic=u.cnic,updated_at=now() "
                "FROM users u WHERE vehicles.id=%s AND vehicles.owner_user_id=%s AND u.id=%s",
                (assignment["truck_id"],assignment["transporter_user_id"],user_id),
            )
        db.commit()

    return json_response({"success": True, "status": new_status})


@driver_blueprint.get("/api/driver/lookup/<unique_id>")
@login_required
def lookup_driver(unique_id):
    """Transporter looks up a driver by their Unique Driver ID (e.g. DRV-84920)."""
    if (request.current_user.get("role") or "").strip().lower() not in TRANSPORTER_ROLES:
        return json_response({"success":False,"message":"Transporter account required."},403)
    unique_code = unique_id.strip().upper()
    with open_db() as db:
        driver = db.execute(
            """
            SELECT dp.user_id, dp.unique_driver_id, dp.license_number, dp.experience_years,
                   dp.rating, dp.rating_count, dp.total_trips, dp.verified_status, dp.is_available,
                   u.full_name, u.phone, u.city
            FROM driver_profiles dp
            JOIN users u ON u.id = dp.user_id
            WHERE dp.unique_driver_id = %s
            """,
            (unique_code,),
        ).fetchone()

        if not driver:
            return json_response({"success": False, "message": f"Driver with ID '{unique_code}' not found."}, 404)

        # Fetch recent reviews & incidents for trust verification
        incidents = db.execute(
            """
            SELECT incident_type, severity, description, status, created_at
            FROM driver_incidents
            WHERE driver_user_id = %s AND status = 'confirmed' AND assignment_id IS NOT NULL
            ORDER BY id DESC
            """,
            (driver["user_id"],),
        ).fetchall()

        reviews = db.execute(
            """
            SELECT dr.rating, dr.comment, dr.created_at, u.full_name AS reviewer_name
            FROM driver_reviews dr
            JOIN users u ON u.id = dr.reviewer_user_id
            WHERE dr.driver_user_id = %s AND dr.assignment_id IS NOT NULL
            ORDER BY dr.id DESC
            LIMIT 5
            """,
            (driver["user_id"],),
        ).fetchall()

    return json_response({
        "success": True,
        "driver": dict(driver),
        "incidents": [dict(i) for i in incidents],
        "reviews": [dict(r) for r in reviews],
    })


@driver_blueprint.get("/api/transporter/driver-assignments")
@login_required
def list_transporter_driver_assignments():
    """List consent/review state for one trip owned by the current fleet."""
    user_id = request.current_user["id"]
    if (request.current_user.get("role") or "").strip().lower() not in TRANSPORTER_ROLES:
        return json_response({"success":False,"message":"Transporter account required."},403)
    try:
        trip_id = _optional_id(request.args,"trip_id")
        agreement_trip_id = _optional_id(request.args,"agreement_trip_id")
        if (trip_id is None) == (agreement_trip_id is None):
            raise ValueError("Select exactly one shipment trip or agreement trip.")
    except ValueError as exc:
        return json_response({"success":False,"message":str(exc)},400)
    with open_db() as db:
        if trip_id is not None:
            source = db.execute(
                "SELECT t.id,t.truck_id,t.status FROM shipment_trips t JOIN vehicles v ON v.id=t.truck_id "
                "WHERE t.id=%s AND t.transporter_user_id=%s AND v.owner_user_id=%s",
                (trip_id,user_id,user_id),
            ).fetchone()
        else:
            source = db.execute(
                "SELECT t.id,t.truck_id,t.status FROM agreement_trips t JOIN vehicles v ON v.id=t.truck_id "
                "WHERE t.id=%s AND t.transporter_user_id=%s AND v.owner_user_id=%s",
                (agreement_trip_id,user_id,user_id),
            ).fetchone()
        if not source:
            return json_response({"success":False,"message":"Trip not found in your fleet."},404)
        rows = db.execute(
            "SELECT a.id,a.driver_user_id,u.full_name AS driver_name,p.unique_driver_id,a.status,a.offer_amount,a.notes,"
            "a.accepted_at,a.created_at,a.completed_at,a.assignment_mode,EXISTS(SELECT 1 FROM driver_reviews r WHERE r.assignment_id=a.id) AS reviewed "
            "FROM driver_trip_assignments a JOIN users u ON u.id=a.driver_user_id "
            "JOIN driver_profiles p ON p.user_id=a.driver_user_id "
            "WHERE a.transporter_user_id=%s AND a.truck_id=%s "
            "AND a.trip_id IS NOT DISTINCT FROM %s AND a.agreement_trip_id IS NOT DISTINCT FROM %s "
            "ORDER BY CASE WHEN a.status IN ('accepted','in_progress') THEN 0 WHEN a.status='completed' THEN 1 "
            "WHEN a.status='requested' THEN 2 ELSE 3 END,a.id DESC LIMIT 100",
            (user_id,source["truck_id"],trip_id,agreement_trip_id),
        ).fetchall()
    assignments = [dict(row,can_review=(row["status"]=="completed" and source["status"]=="completed" and not row["reviewed"])) for row in rows]
    shape = {"agreement_trip_id":agreement_trip_id}
    can_dispatch = _source_is_active(shape,source) and not any(row["status"] in {"accepted","in_progress"} for row in rows)
    return json_response({"success":True,"assignments":assignments,"trip_id":trip_id,"agreement_trip_id":agreement_trip_id,
                          "truck_id":source["truck_id"],"trip_status":source["status"],"can_dispatch":can_dispatch})


@driver_blueprint.post("/api/transporter/dispatch-driver")
@login_required
def dispatch_trip_to_driver():
    """Transporter dispatches an order/trip to a driver using their unique driver ID."""
    role = (request.current_user.get("role") or "").strip().lower()
    if role not in TRANSPORTER_ROLES:
        return json_response({"success": False, "message": "Transporter account required."}, 403)
    err = csrf_error()
    if err:
        return err
    try:
        data = _payload()
        unique_id = _text(data,"unique_driver_id",maximum=32).upper()
        truck_id = _positive_id(data.get("truck_id"),"Truck")
        offer_amount = finite_decimal(data.get("offer_amount",0),"Offer amount",scale=2)
        notes = _text(data,"notes",maximum=4000)
        trip_id = _optional_id(data,"trip_id")
        agreement_trip_id = _optional_id(data,"agreement_trip_id")
        if (trip_id is None) == (agreement_trip_id is None):
            raise ValueError("Select exactly one shipment trip or agreement trip.")
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    if not unique_id or not truck_id:
        return json_response({"success": False, "message": "unique_driver_id and truck_id are required."}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        source = _lock_source_trip(db,trip_id,agreement_trip_id,user_id,truck_id)
        if not source:
            return json_response({"success":False,"message":"Trip not found in your fleet."},404)
        candidate = {"trip_id":trip_id,"agreement_trip_id":agreement_trip_id,
                     "trip_type":"agreement" if agreement_trip_id is not None else "one_time",
                     "transporter_user_id":user_id,"truck_id":truck_id}
        if not _source_is_active(candidate,source):
            return json_response({"success":False,"message":"Only an active trip can receive a driver invitation."},409)
        # Verify truck belongs to transporter
        truck = db.execute(
            "SELECT id, truck_number FROM vehicles WHERE id = %s AND owner_user_id = %s FOR UPDATE",
            (truck_id, user_id),
        ).fetchone()
        if not truck:
            return json_response({"success": False, "message": "Truck not found in your fleet."}, 404)

        # Find driver
        driver = db.execute(
            "SELECT user_id, is_available FROM driver_profiles WHERE unique_driver_id = %s FOR UPDATE",
            (unique_id,),
        ).fetchone()
        if not driver:
            return json_response({"success": False, "message": f"Driver '{unique_id}' not found."}, 404)
        if driver["is_available"] is not True:
            return json_response({"success":False,"message":"This driver is not available for another assignment."},409)
        busy = db.execute(
            "SELECT 1 AS busy FROM driver_trip_assignments WHERE status IN ('accepted','in_progress') "
            "AND (driver_user_id=%s OR truck_id=%s OR trip_id=%s OR agreement_trip_id=%s) LIMIT 1",
            (driver["user_id"],truck_id,trip_id,agreement_trip_id),
        ).fetchone()
        if busy:
            return json_response({"success":False,"message":"Driver, truck or trip already has an active assignment."},409)
        existing = db.execute(
            "SELECT id FROM driver_trip_assignments WHERE driver_user_id=%s AND transporter_user_id=%s "
            "AND truck_id=%s AND status='requested' AND trip_id IS NOT DISTINCT FROM %s "
            "AND agreement_trip_id IS NOT DISTINCT FROM %s ORDER BY id LIMIT 1",
            (driver["user_id"],user_id,truck_id,trip_id,agreement_trip_id),
        ).fetchone()
        if existing:
            return json_response({"success":True,"message":"This driver invitation is already pending.",
                                  "assignment_id":existing["id"],"replayed":True})

        assignment_id = db.execute(
            """
            INSERT INTO driver_trip_assignments (
                driver_user_id, transporter_user_id, truck_id,
                trip_type, trip_id, agreement_trip_id, offer_amount, notes, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'requested')
            RETURNING id
            """,
            (
                driver["user_id"],
                user_id,
                truck_id,
                "agreement" if agreement_trip_id else "one_time",
                trip_id,
                agreement_trip_id,
                offer_amount,
                notes,
            ),
        ).fetchone()["id"]
        db.commit()

    return json_response({
        "success": True,
        "message": f"Trip dispatch request sent to Driver {unique_id}.",
        "assignment_id": assignment_id,
    })


@driver_blueprint.post("/api/driver/rate")
@login_required
def rate_driver():
    """One review by the hiring transporter after a proven completed trip."""
    role = (request.current_user.get("role") or "").strip().lower()
    if role not in TRANSPORTER_ROLES:
        return json_response({"success":False,"message":"Transporter account required."},403)
    err = csrf_error()
    if err:
        return err
    try:
        data = _payload()
        driver_user_id = _positive_id(data.get("driver_user_id"),"Driver")
        assignment_id = _positive_id(data.get("assignment_id"),"Completed assignment")
        rating = bounded_count(data.get("rating"),"Rating",maximum=5)
        if rating < 1:
            raise ValueError("Rating must be between 1 and 5.")
        comment = _text(data,"comment")
        incident_type = _text(data,"incident_type",maximum=64).lower()
        description = _text(data,"incident_description",maximum=4000)
        if incident_type and incident_type not in {"theft","damage","misconduct","delay","other"}:
            raise ValueError("Unsupported incident type.")
        if bool(incident_type) != bool(description):
            raise ValueError("An incident needs both a type and description.")
    except (TypeError, ValueError) as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        snapshot = db.execute(
            "SELECT * FROM driver_trip_assignments WHERE id=%s AND driver_user_id=%s AND transporter_user_id=%s",
            (assignment_id,driver_user_id,user_id),
        ).fetchone()
        if not snapshot:
            return json_response({"success":False,"message":"Completed assignment not found."},404)
        source,truck,profile,assignment = _lock_assignment_context(db,snapshot)
        if (not assignment or not profile or not _source_matches(assignment,source,truck)
                or assignment["status"] != "completed" or source["status"] != "completed"):
            return json_response({"success":False,"message":"A genuinely completed assignment is required before review."},409)
        duplicate = db.execute("SELECT id FROM driver_reviews WHERE assignment_id=%s",(assignment_id,)).fetchone()
        if duplicate:
            return json_response({"success":False,"message":"This assignment has already been reviewed."},409)
        # Record review
        db.execute(
            """
            INSERT INTO driver_reviews (driver_user_id, reviewer_user_id, assignment_id,trip_id,agreement_trip_id,rating, comment)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (driver_user_id,user_id,assignment_id,assignment["trip_id"],assignment["agreement_trip_id"],rating,comment),
        )

        # If incident reported
        if incident_type and description:
            severity = "critical" if incident_type == "theft" else "medium"
            db.execute(
                """
                INSERT INTO driver_incidents (
                    driver_user_id,reporter_user_id,assignment_id,trip_id,agreement_trip_id,incident_type,severity,description,status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'investigating')
                """,
                (driver_user_id,user_id,assignment_id,assignment["trip_id"],assignment["agreement_trip_id"],incident_type,severity,description),
            )

        # Recalculate average rating & incidents penalty
        stats = db.execute(
            """
            SELECT AVG(rating)::numeric(3,2) AS avg_rating, COUNT(*) AS count
            FROM driver_reviews WHERE driver_user_id = %s AND assignment_id IS NOT NULL
            """,
            (driver_user_id,),
        ).fetchone()

        theft_count = db.execute(
            "SELECT COUNT(*) AS count FROM driver_incidents WHERE driver_user_id = %s AND status = 'confirmed' AND assignment_id IS NOT NULL",
            (driver_user_id,),
        ).fetchone()["count"]

        # Drop rating by 0.5 per confirmed incident
        final_rating = max(1.0, float(stats["avg_rating"] or 5.0) - (theft_count * 0.5))

        db.execute(
            """
            UPDATE driver_profiles
            SET rating = %s, rating_count = %s, updated_at = NOW()
            WHERE user_id = %s
            """,
            (final_rating, stats["count"], driver_user_id),
        )
        db.commit()

    return json_response({"success": True, "message": "Driver rating recorded.", "new_rating": final_rating,
                          "incident_status":"investigating" if incident_type else None})


@driver_blueprint.post("/api/transporter/hire-driver-permanent")
@login_required
def offer_permanent_hire():
    """Transporter sends a permanent monthly employment invitation to a high-rated driver."""
    role = (request.current_user.get("role") or "").strip().lower()
    if role not in TRANSPORTER_ROLES:
        return json_response({"success": False, "message": "Transporter account required."}, 403)

    data = request.get_json(silent=True) or {}
    unique_driver_id = (data.get("unique_driver_id") or "").strip().upper()
    try:
        monthly_salary = finite_decimal(data.get("monthly_salary"),"Monthly salary",minimum=Decimal("0.01"),
                                        maximum=Decimal("999999999999.99"),scale=2)
        contract_months = bounded_count(data.get("contract_months",12),"Contract months",maximum=60)
        if contract_months < 1:
            raise ValueError("Contract months must be between 1 and 60.")
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)
    terms = (data.get("terms") or "").strip()

    if not unique_driver_id or monthly_salary <= 0:
        return json_response({"success": False, "message": "Unique driver ID and positive monthly salary are required."}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        driver = db.execute(
            "SELECT user_id, rating, employment_type FROM driver_profiles WHERE unique_driver_id = %s",
            (unique_driver_id,),
        ).fetchone()

        if not driver:
            return json_response({"success": False, "message": f"Driver '{unique_driver_id}' not found."}, 404)

        if driver["employment_type"] == "permanent":
            return json_response({"success": False, "message": "This driver is already permanently employed."}, 400)

        contract_id = db.execute(
            """
            INSERT INTO driver_hire_contracts (
                driver_user_id, transporter_user_id, monthly_salary, contract_months, terms, status
            ) VALUES (%s, %s, %s, %s, %s, 'offered')
            RETURNING id
            """,
            (driver["user_id"], user_id, monthly_salary, contract_months, terms),
        ).fetchone()["id"]
        db.commit()

    return json_response({
        "success": True,
        "message": f"Permanent employment contract invitation sent to Driver {unique_driver_id}.",
        "contract_id": contract_id,
    })


@driver_blueprint.get("/api/driver/hire-contracts")
@login_required
def get_driver_hire_contracts():
    """Driver views their permanent employment contract invitations."""
    err = ensure_driver_role(request.current_user)
    if err:
        return err

    user_id = request.current_user["id"]
    with open_db() as db:
        contracts = db.execute(
            """
            SELECT dhc.*, u.full_name AS transporter_name, u.phone AS transporter_phone, u.email AS transporter_email
            FROM driver_hire_contracts dhc
            JOIN users u ON u.id = dhc.transporter_user_id
            WHERE dhc.driver_user_id = %s
            ORDER BY dhc.id DESC
            """,
            (user_id,),
        ).fetchall()

    return json_response({"success": True, "contracts": [dict(c) for c in contracts]})


@driver_blueprint.post("/api/driver/hire-contracts/<int:contract_id>/respond")
@login_required
def respond_hire_contract(contract_id):
    """Driver accepts or declines a permanent monthly employment invitation."""
    err = ensure_driver_role(request.current_user)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip().lower()
    if action not in {"accept", "decline"}:
        return json_response({"success": False, "message": "Action must be 'accept' or 'decline'."}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        # Serialize accept/decline across all offers for one driver, before any
        # individual contract lock. A sibling offer cannot win concurrently.
        driver = db.execute("SELECT * FROM driver_profiles WHERE user_id=%s FOR UPDATE",(user_id,)).fetchone()
        if not driver:
            return json_response({"success": False,"message":"Driver profile not found."},404)
        contract = db.execute(
            "SELECT * FROM driver_hire_contracts WHERE id = %s AND driver_user_id = %s FOR UPDATE",
            (contract_id, user_id),
        ).fetchone()

        if not contract:
            return json_response({"success": False, "message": "Contract invitation not found."}, 404)

        if contract["status"] != "offered":
            return json_response({"success": False, "message": f"Contract invitation is already {contract['status']}."}, 400)

        if action == "accept":
            active = db.execute("SELECT id FROM driver_hire_contracts WHERE driver_user_id=%s AND status='active'",(user_id,)).fetchone()
            if active:
                return json_response({"success":False,"message":"An active hire contract already exists."},409)
            db.execute(
                "UPDATE driver_hire_contracts SET status = 'active', accepted_at = NOW() WHERE id = %s",
                (contract_id,),
            )
            # Upgrade driver to permanent
            db.execute(
                "UPDATE driver_profiles SET employment_type = 'permanent', updated_at = NOW() WHERE user_id = %s",
                (user_id,),
            )
            # Decline any other pending offers
            db.execute(
                "UPDATE driver_hire_contracts SET status = 'declined' WHERE driver_user_id = %s AND id != %s AND status = 'offered'",
                (user_id, contract_id),
            )
            db.commit()
            return json_response({"success": True, "message": "Congratulations! You are now a permanent monthly hired driver."})
        else:
            db.execute(
                "UPDATE driver_hire_contracts SET status = 'declined' WHERE id = %s",
                (contract_id,),
            )
            db.commit()
            return json_response({"success": True, "message": "Permanent hire invitation declined."})


# ---------------------------------------------------------------------------
# Driver Fuel Expense & Consumption Log System
# ---------------------------------------------------------------------------

@driver_blueprint.get("/api/driver/trips-for-fuel")
@login_required
def get_driver_trips_for_fuel():
    """Returns accepted/in-progress/completed trips so driver can select which trip fuel was purchased for."""
    err = ensure_driver_role(request.current_user)
    if err:
        return err

    user_id = request.current_user["id"]
    with open_db() as db:
        trips = db.execute(
            """
            SELECT dta.id AS assignment_id, dta.truck_id, dta.trip_id, dta.status AS assignment_status,
                   v.truck_number, v.truck_model,
                   s.pickup_city, s.dropoff_city, s.pickup_location, s.dropoff_location,
                   st.actual_distance_km
            FROM driver_trip_assignments dta
            JOIN vehicles v ON v.id = dta.truck_id AND v.owner_user_id = dta.transporter_user_id
            LEFT JOIN shipment_trips st ON st.id = dta.trip_id AND st.truck_id=dta.truck_id AND st.transporter_user_id=dta.transporter_user_id
            LEFT JOIN agreement_trips atr ON atr.id=dta.agreement_trip_id AND atr.truck_id=dta.truck_id AND atr.transporter_user_id=dta.transporter_user_id
            LEFT JOIN shipments s ON s.id = st.order_id
            WHERE dta.driver_user_id = %s AND dta.accepted_at IS NOT NULL
              AND dta.status IN ('accepted','in_progress','completed','cancelled')
              AND ((dta.trip_type='one_time' AND st.id IS NOT NULL) OR (dta.trip_type='agreement' AND atr.id IS NOT NULL))
            ORDER BY dta.id DESC
            LIMIT 25
            """,
            (user_id,),
        ).fetchall()

        # Also get registered fuel pumps on the platform if available
        registered_pumps = db.execute(
            """
            SELECT fsp.user_id, fsp.station_name, u.city, u.address, u.phone
            FROM fuel_station_profiles fsp
            JOIN users u ON u.id = fsp.user_id
            ORDER BY fsp.station_name ASC
            """
        ).fetchall()

    return json_response({
        "success": True,
        "trips": [dict(t) for t in trips],
        "registered_pumps": [dict(p) for p in registered_pumps],
    })


@driver_blueprint.get("/api/driver/fuel-logs")
@login_required
def get_driver_fuel_logs():
    """Retrieve driver's fuel expenditure and consumption records."""
    err = ensure_driver_role(request.current_user)
    if err:
        return err

    user_id = request.current_user["id"]
    with open_db() as db:
        logs = db.execute(
            """
            SELECT dfl.*, v.truck_number, v.truck_model,
                   s.pickup_city, s.dropoff_city
            FROM driver_fuel_logs dfl
            LEFT JOIN vehicles v ON v.id = dfl.truck_id
            LEFT JOIN driver_trip_assignments dta ON dta.id = dfl.assignment_id
            LEFT JOIN shipment_trips st ON st.id = dfl.trip_id AND st.id=dta.trip_id
                AND st.transporter_user_id=dta.transporter_user_id AND st.truck_id=dta.truck_id
                AND dta.accepted_at IS NOT NULL
            LEFT JOIN shipments s ON s.id = st.order_id
            WHERE dfl.driver_user_id = %s
            ORDER BY dfl.fuel_date DESC, dfl.id DESC
            """,
            (user_id,),
        ).fetchall()

        # Summary statistics
        stats = db.execute(
            """
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_fuel_spent,
                COALESCE(SUM(liters), 0) AS total_liters,
                COALESCE(AVG(NULLIF(fuel_average_km_per_liter, 0)), 0) AS avg_km_per_liter,
                COUNT(*) AS total_refuels
            FROM driver_fuel_logs
            WHERE driver_user_id = %s
            """,
            (user_id,),
        ).fetchone()

    return json_response({
        "success": True,
        "logs": [dict(log) for log in logs],
        "stats": {
            "total_fuel_spent": round_money(stats["total_fuel_spent"] or 0),
            "total_liters": round(float(stats["total_liters"] or 0), 2),
            "avg_km_per_liter": round(float(stats["avg_km_per_liter"] or 0), 2),
            "total_refuels": int(stats["total_refuels"] or 0),
        },
    })


@driver_blueprint.post("/api/driver/fuel-logs")
@login_required
def create_driver_fuel_log():
    """Record a fuel refuel log with exact pump name, brand, city, area/location, liters, cash/total, and trip calculation."""
    err = ensure_driver_role(request.current_user)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    if not isinstance(data,dict):
        return json_response({"success": False, "message": "A JSON object is required."},400)
    text_fields = ("pump_name","city","area_landmark","fuel_type","pump_brand","payment_mode","notes")
    if any(data.get(key) is not None and not isinstance(data[key],str) for key in text_fields):
        return json_response({"success": False, "message": "Fuel log text fields must be strings."},400)
    text_limits={"pump_name":150,"city":100,"area_landmark":150,"fuel_type":50,"pump_brand":50,"payment_mode":50,"notes":4000}
    if any(len(data.get(key) or "")>limit for key,limit in text_limits.items()):
        return json_response({"success": False,"message": "A fuel log field exceeds its supported length."},400)
    pump_name = (data.get("pump_name") or "").strip()
    city = (data.get("city") or "").strip()
    area_landmark = (data.get("area_landmark") or "").strip() # e.g. "D Ground, Faisalabad"
    fuel_type = (data.get("fuel_type") or "diesel").strip().lower()
    pump_brand = (data.get("pump_brand") or "Other").strip() # PSO, Shell, Total, etc.
    payment_mode = (data.get("payment_mode") or "cash").strip().lower()
    notes = (data.get("notes") or "").strip()
    fuel_date = data.get("fuel_date") or None

    try:
        liters = finite_decimal(data.get("liters"),"Liters",minimum=Decimal("0.01"),maximum=Decimal("99999999.99"),scale=2)
        price_per_liter = finite_decimal(data.get("price_per_liter"),"Price per liter",minimum=Decimal("0.01"),maximum=Decimal("99999999.99"),scale=2)
        total_amount = (liters*price_per_liter).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        finite_decimal(total_amount,"Fuel total",maximum=Decimal("9999999999.99"),scale=2)
        pump_lat,pump_lng = parse_optional_coordinate_pair(data,"pump_location_lat","pump_location_lng",label="Fuel station")
        odometer_km = None if data.get("odometer_km") in (None,"") else finite_decimal(data["odometer_km"],"Odometer",scale=2)
        trip_distance_km = None if data.get("trip_distance_km") in (None,"") else finite_decimal(data["trip_distance_km"],"Trip distance",maximum=Decimal("99999999.99"),scale=2)
        assignment_id = None if data.get("assignment_id") in (None,"") else bounded_count(data["assignment_id"],"Assignment ID",maximum=2**63-1)
        if assignment_id is not None and assignment_id<=0:
            raise ValueError("Assignment ID must be positive.")
        if fuel_date is not None:
            fuel_date = date.fromisoformat(fuel_date).isoformat()
    except (ValueError, TypeError):
        return json_response({"success": False, "message": "Liters and price per liter must be valid numbers."}, 400)

    if not pump_name or not city:
        return json_response({"success": False, "message": "Pump name and city are required."}, 400)
    if liters <= 0 or price_per_liter <= 0:
        return json_response({"success": False, "message": "Liters and price per liter must be greater than 0."}, 400)


    user_id = request.current_user["id"]
    with open_db() as db:
        # Resolve truck and trip if assignment selected
        truck_id = None
        trip_id = None
        agreement_trip_id = None
        if assignment_id:
            asgn = db.execute(
                """
                SELECT dta.truck_id, dta.trip_id, dta.agreement_trip_id, st.actual_distance_km
                FROM driver_trip_assignments dta
                JOIN vehicles v ON v.id=dta.truck_id AND v.owner_user_id=dta.transporter_user_id
                LEFT JOIN shipment_trips st ON st.id = dta.trip_id AND st.truck_id=dta.truck_id AND st.transporter_user_id=dta.transporter_user_id
                LEFT JOIN agreement_trips atr ON atr.id=dta.agreement_trip_id AND atr.truck_id=dta.truck_id AND atr.transporter_user_id=dta.transporter_user_id
                WHERE dta.id = %s AND dta.driver_user_id = %s AND dta.accepted_at IS NOT NULL
                  AND dta.status IN ('accepted','in_progress','completed','cancelled')
                  AND ((dta.trip_type='one_time' AND st.id IS NOT NULL) OR (dta.trip_type='agreement' AND atr.id IS NOT NULL))
                """,
                (assignment_id, user_id),
            ).fetchone()
            if not asgn:
                return json_response({"success": False,"message": "Assignment not found for this driver."},404)
            truck_id = asgn["truck_id"]
            trip_id = asgn["trip_id"]
            agreement_trip_id = asgn["agreement_trip_id"]
            if trip_distance_km is None and asgn["actual_distance_km"] is not None:
                try:
                    trip_distance_km = finite_decimal(asgn["actual_distance_km"],"Trip distance",maximum=Decimal("99999999.99"),scale=2)
                except ValueError as exc:
                    return json_response({"success": False,"message": str(exc)},400)

        # If driver has an active truck in profile and no assignment truck
        if not truck_id:
            drv = db.execute("SELECT current_truck_id FROM driver_profiles WHERE user_id = %s", (user_id,)).fetchone()
            if drv and drv["current_truck_id"]:
                truck_id = drv["current_truck_id"]

        # Calculate average fuel consumption (km / liter) if distance is available
        fuel_avg = None
        if trip_distance_km and trip_distance_km > 0 and liters > 0:
            fuel_avg = (trip_distance_km / liters).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            if fuel_avg > Decimal("9999.99"):
                return json_response({"success": False,"message": "Fuel average exceeds the supported range. Verify liters and trip distance."},400)

        log_id = db.execute(
            """
            INSERT INTO driver_fuel_logs (
                driver_user_id, truck_id, assignment_id, trip_id, agreement_trip_id,
                pump_name, pump_brand, city, area_landmark,
                pump_location_lat, pump_location_lng,
                fuel_type, liters, price_per_liter, total_amount, payment_mode,
                odometer_km, trip_distance_km, fuel_average_km_per_liter,
                notes, fuel_date
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, COALESCE(%s, CURRENT_DATE)
            ) RETURNING id
            """,
            (
                user_id, truck_id, assignment_id, trip_id, agreement_trip_id,
                pump_name, pump_brand, city, area_landmark,
                pump_lat, pump_lng,
                fuel_type, liters, price_per_liter, total_amount, payment_mode,
                odometer_km, trip_distance_km, fuel_avg,
                notes, fuel_date
            ),
        ).fetchone()["id"]
        db.commit()

    return json_response({
        "success": True,
        "message": f"Fuel refuel record added successfully! Total: Rs {total_amount:,.2f}",
        "log_id": log_id,
        "fuel_average_km_per_liter": float(fuel_avg) if fuel_avg is not None else None,
    })
