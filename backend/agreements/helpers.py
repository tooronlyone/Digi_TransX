from datetime import date, datetime
from math import asin, cos, radians, sin, sqrt

from auth.helpers import json_response, timestamp_bundle
from trucks.helpers import get_catalog_type
from wallet.helpers import (
    adjust_wallet_balance,
    available_balance,
    get_or_create_wallet_for_user,
    round_money,
)


CLIENT_AGREEMENT_ROLES = {"service_seeker", "everyday_user", "client"}
TRANSPORTER_AGREEMENT_ROLES = {"logistics_provider", "transporter"}
# Commission rates are no longer hard-coded here: every agreement carries its
# own snapshot (see shared/commissions.py) saved when it was finalized.
PENALTY_AMOUNT = 5000.0


def normalize_role(role):
    return (role or "").strip().lower()


def require_client_role(user):
    if normalize_role(user.get("role")) not in CLIENT_AGREEMENT_ROLES:
        return json_response({"success": False, "message": "Client account required."}, 403)
    return None


def require_transporter_role(user):
    if normalize_role(user.get("role")) not in TRANSPORTER_AGREEMENT_ROLES:
        return json_response({"success": False, "message": "Transporter account required."}, 403)
    return None


def parse_required_text(data, field_name, label):
    value = (data.get(field_name) or "").strip()
    if not value:
        raise ValueError(f"{label} is required.")
    return value


def parse_optional_text(data, field_name):
    value = (data.get(field_name) or "").strip()
    return value or None


def parse_positive_float(value, label):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a valid number.")
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    return parsed


def parse_positive_int(value, label):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a valid number.")
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    return parsed


def parse_iso_date(value, label):
    raw = (value or "").strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"{label} must be in YYYY-MM-DD format.")


def add_months(value, months):
    year = value.year + ((value.month - 1 + months) // 12)
    month = ((value.month - 1 + months) % 12) + 1
    day = min(value.day, days_in_month(year, month))
    return date(year, month, day)


def days_in_month(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def due_date_for_month(start_date, month_index):
    month_start = add_months(date(start_date.year, start_date.month, 1), month_index)
    return date(month_start.year, month_start.month, min(10, days_in_month(month_start.year, month_start.month)))


def haversine_km(start_lat, start_lng, end_lat, end_lng):
    lat1, lng1, lat2, lng2 = map(radians, [start_lat, start_lng, end_lat, end_lng])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return round_money(6371.0 * 2 * asin(sqrt(value)))


def service_area_to_text(value):
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return ",".join(part.strip() for part in str(value or "").split(",") if part.strip())


def split_service_area(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def truck_type_name(type_key):
    catalog = get_catalog_type(type_key)
    return catalog.get("display_name") if catalog else (type_key or "")


def serialize_post(row, trucks=None, bid_count=0):
    return {
        "id": row.get("id"),
        "client_user_id": row.get("client_user_id"),
        "title": row.get("title"),
        "cargo_type": row.get("cargo_type"),
        "service_area": split_service_area(row.get("service_area")),
        "service_area_text": row.get("service_area") or "",
        "pickup_location": row.get("pickup_location") or "",
        "dropoff_location": row.get("dropoff_location") or "",
        "status": row.get("status"),
        "trucks": trucks or [],
        "bid_count": int(bid_count or row.get("bid_count") or 0),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def serialize_required_truck(row):
    return {
        "id": row.get("id"),
        "post_id": row.get("post_id"),
        "truck_type": row.get("truck_type"),
        "truck_type_name": truck_type_name(row.get("truck_type")),
        "capacity_tons": row.get("capacity_tons"),
        "quantity": int(row.get("quantity") or 0),
    }


def serialize_bid(row, trucks=None):
    return {
        "id": row.get("id"),
        "post_id": row.get("post_id"),
        "transporter_user_id": row.get("transporter_user_id"),
        "transporter_name": row.get("transporter_name") or "Transporter",
        "transporter_rating": row.get("transporter_rating"),
        "status": row.get("status"),
        "message": row.get("message") or "",
        "trucks": trucks or [],
        "exact_match": bool(row.get("exact_match")),
        "average_per_km_rate": round_money(row.get("average_per_km_rate")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def serialize_bid_truck(row):
    truck_photo_path = row.get("truck_photo_path") or ""
    return {
        "id": row.get("id"),
        "bid_id": row.get("bid_id"),
        "truck_id": row.get("truck_id"),
        "truck_number": row.get("truck_number") or "",
        "truck_type": row.get("catalog_type_key") or row.get("truck_type") or "",
        "truck_type_name": truck_type_name(row.get("catalog_type_key") or row.get("truck_type")),
        "truck_photo_path": truck_photo_path,
        "photo": f"/{truck_photo_path}" if truck_photo_path else "",
        "capacity_tons": row.get("capacity_tons"),
        "per_km_rate": round_money(row.get("per_km_rate")),
        "minimum_monthly_guarantee": round_money(row.get("minimum_monthly_guarantee")),
    }


def serialize_agreement(row, trucks=None):
    return {
        "id": row.get("id"),
        "post_id": row.get("post_id"),
        "client_user_id": row.get("client_user_id"),
        "client_name": row.get("client_name") or "Client",
        "duration_months": int(row.get("duration_months") or 0),
        "cargo_type": row.get("cargo_type"),
        "service_area": split_service_area(row.get("service_area")),
        "service_area_text": row.get("service_area") or "",
        "start_date": row.get("start_date"),
        "end_date": row.get("end_date"),
        "status": row.get("status"),
        "contract_text": row.get("contract_text") or "",
        "truck_count": int(row.get("truck_count") or len(trucks or [])),
        "current_month_km": round_money(row.get("current_month_km")),
        "current_month_earnings": round_money(row.get("current_month_earnings")),
        "trucks": trucks or [],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def serialize_agreement_truck(row):
    truck_photo_path = row.get("truck_photo_path") or ""
    return {
        "id": row.get("id"),
        "agreement_id": row.get("agreement_id"),
        "truck_id": row.get("truck_id"),
        "transporter_user_id": row.get("transporter_user_id"),
        "transporter_name": row.get("transporter_name") or "Transporter",
        "truck_number": row.get("truck_number") or "",
        "truck_type": row.get("catalog_type_key") or row.get("truck_type") or "",
        "truck_type_name": truck_type_name(row.get("catalog_type_key") or row.get("truck_type")),
        "truck_photo_path": truck_photo_path,
        "photo": f"/{truck_photo_path}" if truck_photo_path else "",
        "per_km_rate": round_money(row.get("per_km_rate")),
        "minimum_monthly_guarantee": round_money(row.get("minimum_monthly_guarantee")),
        "status": row.get("status"),
    }


def serialize_trip(row):
    return {
        "id": row.get("id"),
        "agreement_id": row.get("agreement_id"),
        "agreement_truck_id": row.get("agreement_truck_id"),
        "truck_id": row.get("truck_id"),
        "truck_number": row.get("truck_number") or "",
        "transporter_user_id": row.get("transporter_user_id"),
        "pickup_description": row.get("pickup_description") or "",
        "pickup_location": row.get("pickup_location") or "",
        "dropoff_location": row.get("dropoff_location") or "",
        "trip_date": row.get("trip_date"),
        "gps_start_lat": row.get("gps_start_lat"),
        "gps_start_lng": row.get("gps_start_lng"),
        "gps_end_lat": row.get("gps_end_lat"),
        "gps_end_lng": row.get("gps_end_lng"),
        "distance_km": round_money(row.get("distance_km")),
        "started_at": row.get("started_at"),
        "ended_at": row.get("ended_at"),
        "status": row.get("status"),
        "client_acknowledged": bool(row.get("client_acknowledged")),
        "created_at": row.get("created_at"),
    }


def serialize_payment(row):
    return {
        "id": row.get("id"),
        "agreement_id": row.get("agreement_id"),
        "agreement_truck_id": row.get("agreement_truck_id"),
        "transporter_user_id": row.get("transporter_user_id"),
        "client_user_id": row.get("client_user_id"),
        "truck_number": row.get("truck_number") or "",
        "month_year": row.get("month_year"),
        "total_km": round_money(row.get("total_km")),
        "total_earned": round_money(row.get("total_earned")),
        "minimum_guarantee": round_money(row.get("minimum_guarantee")),
        "final_amount": round_money(row.get("final_amount")),
        "company_fee": round_money(row.get("company_fee")),
        "transporter_amount": round_money(row.get("transporter_amount")),
        "penalty_amount": round_money(row.get("penalty_amount")),
        "status": row.get("status"),
        "payment_due_date": row.get("payment_due_date"),
        "paid_at": row.get("paid_at"),
        "created_at": row.get("created_at"),
    }


def month_key(value=None):
    current = value or datetime.now()
    return current.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Agreement monthly-payment processing
# ---------------------------------------------------------------------------
# Single source of truth for settling agreement payments and applying late
# penalties. Called by the admin routes, the client/agreement routes, and the
# background scheduler so the logic lives in exactly one place.

def process_payment_row(db, payment):
    """Settle one monthly payment: debit client, credit transporter.

    Returns True on success. On insufficient client balance the payment is
    marked 'failed' and False is returned. Does NOT commit.
    """
    client_wallet, client_error = get_or_create_wallet_for_user(db, {"id": payment["client_user_id"], "role": "client"})
    if client_error:
        return False
    if available_balance(client_wallet) + 1e-9 < round_money(payment["final_amount"]):
        db.execute("UPDATE agreement_monthly_payments SET status = 'failed' WHERE id = ?", (payment["id"],))
        return False

    transporter_wallet, transporter_error = get_or_create_wallet_for_user(
        db,
        {"id": payment["transporter_user_id"], "role": "transporter"},
    )
    if transporter_error:
        return False
    debit_error = adjust_wallet_balance(
        db,
        client_wallet,
        payment["client_user_id"],
        -round_money(payment["final_amount"]),
        "agreement_payment_paid",
        description=f"Agreement #{payment['agreement_id']} monthly payment {payment['month_year']}",
        reference_id=str(payment["id"]),
    )
    if debit_error:
        return False
    credit_error = adjust_wallet_balance(
        db,
        transporter_wallet,
        payment["transporter_user_id"],
        round_money(payment["transporter_amount"]),
        "agreement_income",
        description=f"Agreement #{payment['agreement_id']} monthly income {payment['month_year']}",
        reference_id=str(payment["id"]),
    )
    if credit_error:
        return False
    stamp = timestamp_bundle()["iso"]
    db.execute(
        "UPDATE agreement_monthly_payments SET status = 'paid', paid_at = ? WHERE id = ?",
        (stamp, payment["id"]),
    )
    return True


def run_process_payments(db):
    """Process every pending payment due today or earlier. Commits.

    Returns {"processed": int, "failed": int}.
    """
    today = date.today().isoformat()
    processed = 0
    failed = 0
    rows = db.execute(
        "SELECT * FROM agreement_monthly_payments "
        "WHERE status = 'pending' AND payment_due_date <= ? ORDER BY id ASC",
        (today,),
    ).fetchall()
    for row in rows:
        if process_payment_row(db, dict(row)):
            processed += 1
        else:
            failed += 1
    db.commit()
    return {"processed": processed, "failed": failed}


def run_apply_penalties(db):
    """Apply the late penalty to every overdue failed payment, then retry it. Commits.

    Returns {"penalties_applied": int}.
    """
    today = date.today().isoformat()
    penalties_applied = 0
    rows = db.execute(
        "SELECT * FROM agreement_monthly_payments "
        "WHERE status = 'failed' AND payment_due_date <= ? ORDER BY id ASC",
        (today,),
    ).fetchall()
    for row in rows:
        payment = dict(row)
        client_wallet, wallet_error = get_or_create_wallet_for_user(
            db, {"id": payment["client_user_id"], "role": "client"}
        )
        if wallet_error:
            continue
        penalty_error = adjust_wallet_balance(
            db,
            client_wallet,
            payment["client_user_id"],
            -PENALTY_AMOUNT,
            "agreement_late_penalty",
            description=f"Agreement #{payment['agreement_id']} late payment penalty",
            reference_id=str(payment["id"]),
        )
        if penalty_error:
            continue
        current_count = db.execute(
            "SELECT COUNT(*) AS total FROM agreement_payment_penalties WHERE monthly_payment_id = ?",
            (payment["id"],),
        ).fetchone()["total"]
        stamp = timestamp_bundle()["iso"]
        db.execute(
            "INSERT INTO agreement_payment_penalties ("
            "monthly_payment_id, client_user_id, penalty_amount, penalty_number, applied_at"
            ") VALUES (?, ?, ?, ?, ?)",
            (payment["id"], payment["client_user_id"], PENALTY_AMOUNT, int(current_count or 0) + 1, stamp),
        )
        db.execute(
            "UPDATE agreement_monthly_payments SET penalty_amount = penalty_amount + ? WHERE id = ?",
            (PENALTY_AMOUNT, payment["id"]),
        )
        penalties_applied += 1
        refreshed = db.execute(
            "SELECT * FROM agreement_monthly_payments WHERE id = ?", (payment["id"],)
        ).fetchone()
        if refreshed:
            process_payment_row(db, dict(refreshed))
    db.commit()
    return {"penalties_applied": penalties_applied}
