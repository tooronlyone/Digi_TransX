"""One-time data migration: SQLite (Database/digitransx_auth.db) -> Supabase.

What it does, in order:
  1. Copies every table's rows into Supabase PostgreSQL, keeping the original
     row ids (so all foreign keys stay valid).
  2. Creates a Supabase Auth account for every user (random password —
     werkzeug password hashes cannot be imported into Supabase Auth, so
     existing users must use "Forgot password" once to set a new password).
  3. Derives the new `drivers` and `customers` tables from legacy data.
  4. Uploads local files (backend/uploads/**) into the shipment-documents
     Storage bucket and records them in `documents`.
  5. Bumps every identity sequence past the imported max id.

Safe to re-run: inserts use ON CONFLICT DO NOTHING.

Usage:
    python backend/scripts/migrate_sqlite_to_supabase.py            # full run
    python backend/scripts/migrate_sqlite_to_supabase.py --dry-run  # counts only
"""

import argparse
import json
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import psycopg2
import psycopg2.extras

from shared.db import BASE_DIR  # loads .env
import os

SQLITE_PATH = BASE_DIR / "Database" / "digitransx_auth.db"
UPLOADS_DIR = BASE_DIR / "backend" / "uploads"

LEGACY_TO_APP_ROLE = {
    "platform_admin": "admin",
    "client": "customer",
    "service_seeker": "customer",
    "everyday_user": "customer",
    "transporter": "transporter",
    "logistics_provider": "transporter",
    "fuel_station_manager": "fuel_station_manager",
    "shopkeeper": "shopkeeper",
    "dispatcher": "dispatcher",
}
CLIENT_ROLES = {"client", "service_seeker", "everyday_user"}


def parse_ts(value):
    """Parse legacy timestamp strings (display or ISO). Returns datetime or None."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    for fmt in ("%d %b %Y %I:%M:%S %p", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def ts_or_now(value):
    return parse_ts(value) or datetime.now()


def as_bool(value):
    return bool(value)


def as_json(value, default=None):
    if value is None or str(value).strip() == "":
        return default
    try:
        json.loads(value)
        return str(value)
    except (ValueError, TypeError):
        return default


class Migrator:
    def __init__(self, dry_run=False):
        if not SQLITE_PATH.exists():
            raise SystemExit(f"SQLite database not found: {SQLITE_PATH}")
        self.dry_run = dry_run
        self.sq = sqlite3.connect(SQLITE_PATH)
        self.sq.row_factory = sqlite3.Row
        db_url = os.environ.get("SUPABASE_DB_URL", "")
        if not db_url:
            raise SystemExit("SUPABASE_DB_URL is not set (.env).")
        self.pg = psycopg2.connect(db_url)
        self.pg.autocommit = False
        self.report = {}

    # ------------------------------------------------------------------
    def rows(self, table):
        try:
            return [dict(r) for r in self.sq.execute(f"SELECT * FROM {table}").fetchall()]
        except sqlite3.OperationalError:
            return []

    def insert(self, table, row):
        cols = list(row.keys())
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join(['%s'] * len(cols))}) ON CONFLICT DO NOTHING"
        )
        with self.pg.cursor() as cur:
            cur.execute(sql, [row[c] for c in cols])
            return cur.rowcount

    def copy(self, src_table, dst_table, transform):
        rows = self.rows(src_table)
        copied = 0
        for row in rows:
            mapped = transform(row)
            if mapped is None:
                continue
            if not self.dry_run:
                copied += self.insert(dst_table, mapped)
            else:
                copied += 1
        self.report[dst_table] = f"{copied}/{len(rows)}"
        print(f"  {src_table} -> {dst_table}: {copied}/{len(rows)}")

    def bump_sequence(self, table):
        with self.pg.cursor() as cur:
            cur.execute(
                f"select setval(pg_get_serial_sequence('public.{table}', 'id'), "
                f"coalesce((select max(id) from public.{table}), 0) + 1, false)"
            )

    # ------------------------------------------------------------------
    def migrate_users(self):
        def t(u):
            legacy = (u.get("role") or "").strip().lower()
            return {
                "id": u["id"],
                "full_name": u.get("full_name") or "",
                "first_name": u.get("first_name"),
                "last_name": u.get("last_name"),
                "email": (u.get("email") or "").strip().lower(),
                "phone": u.get("phone") or "",
                "cnic": u.get("cnic") or f"PENDING-{u['id']}",
                "role": LEGACY_TO_APP_ROLE.get(legacy, "customer"),
                "legacy_role": legacy or None,
                "company_name": u.get("company_name"),
                "business_type": u.get("business_type"),
                "city": u.get("city"),
                "fleet_size": u.get("fleet_size"),
                "transport_need": u.get("transport_need"),
                "station_name": u.get("station_name"),
                "pumps_count": u.get("pumps_count"),
                "license_no": u.get("license_no"),
                "shop_name": u.get("shop_name"),
                "address": u.get("address"),
                "about": u.get("about"),
                "mpin_hash": u.get("mpin_hash"),
                "mpin_enabled": as_bool(u.get("mpin_enabled")),
                "settings_json": as_json(u.get("settings_json"), "{}"),
                "is_blocked": as_bool(u.get("is_blocked")),
                "block_reason": u.get("block_reason"),
                "withdrawal_tier": int(u.get("withdrawal_tier") or 0),
                "withdrawal_tier_expires_at": u.get("withdrawal_tier_expires_at"),
                "payout_card_number": u.get("payout_card_number"),
                "payout_card_holder": u.get("payout_card_holder"),
                "payout_card_expiry": u.get("payout_card_expiry"),
                "payout_card_bank": u.get("payout_card_bank"),
                "created_at": ts_or_now(u.get("created_at")),
                "updated_at": ts_or_now(u.get("updated_at")),
                "last_login_at": parse_ts(u.get("last_login_at")),
            }

        self.copy("users", "users", t)

    def create_auth_accounts(self):
        """Create Supabase Auth users and link auth_id. Passwords are random —
        existing users must reset via 'Forgot password'."""
        if self.dry_run:
            print("  (dry-run) skipping Supabase Auth account creation")
            return
        from shared.supabase_client import get_service_client

        client = get_service_client()
        created = linked = failed = 0
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, email, full_name, phone, cnic, role, legacy_role FROM users WHERE auth_id IS NULL")
            pending = cur.fetchall()
        for user in pending:
            try:
                auth_user = client.auth.admin.create_user(
                    {
                        "email": user["email"],
                        "password": secrets.token_urlsafe(24),
                        "email_confirm": True,
                        "user_metadata": {
                            "full_name": user["full_name"],
                            "phone": user["phone"],
                            "cnic": user["cnic"],
                            "role": user["role"],
                            "legacy_role": user["legacy_role"],
                        },
                    }
                ).user
                with self.pg.cursor() as cur:
                    cur.execute("UPDATE users SET auth_id = %s WHERE id = %s", (auth_user.id, user["id"]))
                created += 1
            except Exception as exc:
                message = str(exc)
                if "already" in message.lower():
                    linked += 1
                else:
                    failed += 1
                    print(f"    ! auth create failed for {user['email']}: {message}")
        self.pg.commit()
        print(f"  Supabase Auth: {created} created, {linked} already existed, {failed} failed")
        if created:
            print("  NOTE: migrated users have random passwords — they must use 'Forgot password' once.")

    # ------------------------------------------------------------------
    def migrate_vehicles(self):
        def t(r):
            return {
                "id": r["id"],
                "owner_user_id": r["owner_user_id"],
                "truck_number": r.get("truck_number") or f"TRUCK-{r['id']}",
                "truck_company": r.get("truck_company"),
                "truck_model": r.get("truck_model"),
                "truck_type": r.get("truck_type") or "Truck",
                "catalog_type_key": r.get("catalog_type_key"),
                "chassis_number": r.get("chassis_number") or f"CHASSIS-{r['id']}",
                "capacity_tons": r.get("capacity_tons") or 0,
                "main_use": r.get("main_use") or "",
                "payload_min_tons": r.get("payload_min_tons"),
                "payload_max_tons": r.get("payload_max_tons"),
                "volume_min_cbm": r.get("volume_min_cbm"),
                "volume_max_cbm": r.get("volume_max_cbm"),
                "bed_length_ft": r.get("bed_length_ft"),
                "bed_width_ft": r.get("bed_width_ft"),
                "bed_height_ft": r.get("bed_height_ft"),
                "body_style": r.get("body_style"),
                "catalog_specs_json": as_json(r.get("catalog_specs_json")),
                "driver_name": r.get("driver_name"),
                "driver_cnic": r.get("driver_cnic"),
                "tracking_id": r.get("tracking_id"),
                "traccar_device_id": r.get("traccar_device_id"),
                "status": r.get("status") or "inactive",
                "status_reason_code": r.get("status_reason_code"),
                "status_reason": r.get("status_reason"),
                "operating_provinces": r.get("operating_provinces"),
                "per_km_rate": r.get("per_km_rate"),
                "waiting_charge_per_hour": r.get("waiting_charge_per_hour"),
                "loading_charge": r.get("loading_charge"),
                "refrigeration_supported": as_bool(r.get("refrigeration_supported")),
                "hazardous_supported": as_bool(r.get("hazardous_supported")),
                "fragile_supported": as_bool(r.get("fragile_supported")),
                "truck_photo_path": r.get("truck_photo_path"),
                "insurance_photo_path": r.get("insurance_photo_path"),
                "rc_book_photo_path": r.get("rc_book_photo_path"),
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            }

        self.copy("trucks", "vehicles", t)

    def derive_drivers_and_customers(self):
        if self.dry_run:
            print("  (dry-run) skipping drivers/customers derivation")
            return
        with self.pg.cursor() as cur:
            # drivers from vehicle driver fields
            cur.execute(
                """
                INSERT INTO drivers (owner_user_id, full_name, cnic, status)
                SELECT DISTINCT owner_user_id, trim(driver_name), driver_cnic, 'active'
                FROM vehicles
                WHERE driver_name IS NOT NULL AND trim(driver_name) <> ''
                ON CONFLICT DO NOTHING
                """
            )
            cur.execute(
                """
                UPDATE vehicles v
                SET driver_id = d.id
                FROM drivers d
                WHERE v.driver_id IS NULL
                  AND d.owner_user_id = v.owner_user_id
                  AND d.full_name = trim(v.driver_name)
                """
            )
            # customers profile rows for client-side users
            cur.execute(
                """
                INSERT INTO customers (user_id, customer_type, company_name, business_type)
                SELECT id,
                       CASE WHEN company_name IS NOT NULL AND trim(company_name) <> '' THEN 'business' ELSE 'individual' END,
                       company_name, business_type
                FROM users
                WHERE COALESCE(legacy_role, '') IN ('client', 'service_seeker', 'everyday_user')
                ON CONFLICT (user_id) DO NOTHING
                """
            )
        print("  drivers + customers derived")

    # ------------------------------------------------------------------
    def migrate_shipments_domain(self):
        def t_order(r):
            return {
                "id": r["id"],
                "client_user_id": r["client_user_id"],
                "pickup_city": r.get("pickup_city") or "",
                "pickup_area": r.get("pickup_area") or "",
                "pickup_location": r.get("pickup_location"),
                "pickup_lat": r.get("pickup_lat"),
                "pickup_lng": r.get("pickup_lng"),
                "dropoff_city": r.get("dropoff_city") or "",
                "dropoff_area": r.get("dropoff_area") or "",
                "dropoff_location": r.get("dropoff_location"),
                "dropoff_lat": r.get("dropoff_lat"),
                "dropoff_lng": r.get("dropoff_lng"),
                "pickup_date": r.get("pickup_date") or "1970-01-01",
                "pickup_time": r.get("pickup_time") or "",
                "goods_type": r.get("goods_type") or "",
                "goods_category": r.get("goods_category"),
                "goods_form": r.get("goods_form"),
                "goods_commodity": r.get("goods_commodity"),
                "goods_weight_tons": r.get("goods_weight_tons") or 0,
                "goods_volume_cbm": r.get("goods_volume_cbm"),
                "length_cm": r.get("length_cm"),
                "width_cm": r.get("width_cm"),
                "height_cm": r.get("height_cm"),
                "volume_liters": r.get("volume_liters"),
                "quantity": r.get("quantity"),
                "animal_count": r.get("animal_count"),
                "temperature_c": r.get("temperature_c"),
                "required_truck_types": r.get("required_truck_types"),
                "is_refrigerated": as_bool(r.get("is_refrigerated")),
                "is_hazardous": as_bool(r.get("is_hazardous")),
                "is_food_grade": as_bool(r.get("is_food_grade")),
                "estimated_budget": r.get("estimated_budget"),
                "notes": r.get("notes"),
                "status": r.get("status") or "open",
                "accepted_bid_id": None,  # linked after bids are copied
                "payment_amount": r.get("payment_amount"),
                "payment_status": r.get("payment_status") or "pending",
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            }

        self.copy("orders", "shipments", t_order)

        def t_bid(r):
            return {
                "id": r["id"],
                "order_id": r["order_id"],
                "transporter_user_id": r["transporter_user_id"],
                "truck_id": r["truck_id"],
                "bid_price": r.get("bid_price") or 0,
                "message": r.get("message"),
                "status": r.get("status") or "pending",
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            }

        self.copy("order_bids", "shipment_bids", t_bid)

        if not self.dry_run:
            for r in self.rows("orders"):
                if r.get("accepted_bid_id"):
                    with self.pg.cursor() as cur:
                        cur.execute(
                            "UPDATE shipments SET accepted_bid_id = %s WHERE id = %s",
                            (r["accepted_bid_id"], r["id"]),
                        )

        def t_trip(r):
            return {
                "id": r["id"],
                "order_id": r["order_id"],
                "accepted_bid_id": r["accepted_bid_id"],
                "transporter_user_id": r["transporter_user_id"],
                "truck_id": r["truck_id"],
                "status": r.get("status") or "accepted",
                "trip_started_at": parse_ts(r.get("trip_started_at")),
                "trip_completed_at": parse_ts(r.get("trip_completed_at")),
                "delivery_confirmed_at": parse_ts(r.get("delivery_confirmed_at")),
                "pickup_location_lat": r.get("pickup_location_lat"),
                "pickup_location_lng": r.get("pickup_location_lng"),
                "dropoff_location_lat": r.get("dropoff_location_lat"),
                "dropoff_location_lng": r.get("dropoff_location_lng"),
                "actual_distance_km": r.get("actual_distance_km"),
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            }

        self.copy("order_trips", "shipment_trips", t_trip)

        def t_verify(r):
            return {
                "id": r["id"],
                "trip_id": r["trip_id"],
                "transporter_claim_at": parse_ts(r.get("transporter_claim_at")),
                "client_first_response": r.get("client_first_response"),
                "client_first_response_at": parse_ts(r.get("client_first_response_at")),
                "client_second_response": r.get("client_second_response"),
                "client_second_response_at": parse_ts(r.get("client_second_response_at")),
                "final_verification_status": r.get("final_verification_status"),
                "admin_decision_by": r.get("admin_decision_by"),
                "admin_decision": r.get("admin_decision"),
                "admin_decided_at": parse_ts(r.get("admin_decided_at")),
                "admin_note": r.get("admin_note"),
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            }

        self.copy("order_trip_verification", "shipment_trip_verification", t_verify)

        def t_noshow(r):
            return {
                "id": r["id"],
                "trip_id": r["trip_id"],
                "notification_count": r.get("notification_count") or 0,
                "call_count": r.get("call_count") or 0,
                "last_notification_at": parse_ts(r.get("last_notification_at")),
                "last_call_at": parse_ts(r.get("last_call_at")),
                "order_deactivated_at": parse_ts(r.get("order_deactivated_at")),
                "status": r.get("status") or "tracking",
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            }

        self.copy("order_no_show_tracking", "shipment_no_show_tracking", t_noshow)

        def t_cancel(r):
            return {
                "id": r["id"],
                "order_id": r["order_id"],
                "cancelled_by": r.get("cancelled_by") or "",
                "reason": r.get("reason"),
                "refund_amount": r.get("refund_amount"),
                "penalty_amount": r.get("penalty_amount"),
                "status": r.get("status") or "pending",
                "created_at": ts_or_now(r.get("created_at")),
            }

        self.copy("order_cancellations", "shipment_cancellations", t_cancel)

        def t_notif(r):
            return {
                "id": r["id"],
                "order_id": r["order_id"],
                "trip_id": r.get("trip_id"),
                "user_id": r["user_id"],
                "notification_type": r.get("notification_type") or "",
                "message": r.get("message"),
                "is_read": as_bool(r.get("is_read")),
                "created_at": ts_or_now(r.get("created_at")),
            }

        self.copy("order_notifications", "shipment_notifications", t_notif)

        def t_invoice(r):
            return {
                "id": r["id"],
                "trip_id": r["trip_id"],
                "invoice_number": r.get("invoice_number") or f"INV-{r['id']}",
                "client_user_id": r["client_user_id"],
                "transporter_user_id": r["transporter_user_id"],
                "bid_price": r.get("bid_price") or 0,
                "company_fee": r.get("company_fee") or 0,
                "transporter_amount": r.get("transporter_amount") or 0,
                "payment_method": r.get("payment_method") or "wallet",
                "pdf_path": r.get("pdf_path"),
                "status": "paid",
                "created_at": ts_or_now(r.get("created_at")),
            }

        self.copy("order_invoices", "payments", t_invoice)

    # ------------------------------------------------------------------
    def migrate_wallets(self):
        def t_wallet(r):
            return {
                "id": r["id"],
                "user_id": r["user_id"],
                "role": r.get("role") or "",
                "balance": r.get("balance") or 0,
                "locked_balance": r.get("locked_balance") or 0,
                "minimum_required": r.get("minimum_required") or 0,
                "is_minimum_met": as_bool(r.get("is_minimum_met")),
                "completed_trips_count": int(r.get("completed_trips_count") or 0),
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            }

        self.copy("wallets", "wallets", t_wallet)

        def t_tx(r):
            return {
                "id": r["id"],
                "wallet_id": r["wallet_id"],
                "user_id": r["user_id"],
                "type": r.get("type") or "",
                "amount": r.get("amount") or 0,
                "gross_amount": r.get("gross_amount"),
                "gateway_fee": r.get("gateway_fee") or 0,
                "description": r.get("description"),
                "reference_id": r.get("reference_id"),
                "balance_after": r.get("balance_after") or 0,
                "created_at": ts_or_now(r.get("created_at")),
            }

        self.copy("wallet_transactions", "wallet_transactions", t_tx)

        def t_wd(r):
            return {
                "id": r["id"],
                "user_id": r["user_id"],
                "amount": r.get("amount") or 0,
                "status": r.get("status") or "pending",
                "requested_at": ts_or_now(r.get("requested_at")),
                "resolved_at": parse_ts(r.get("resolved_at")),
                "processed_at": parse_ts(r.get("processed_at")),
            }

        self.copy("wallet_withdrawal_requests", "wallet_withdrawal_requests", t_wd)

    # ------------------------------------------------------------------
    def migrate_chat(self):
        def t_thread(r):
            return {
                "id": r["id"],
                "client_user_id": r["client_user_id"],
                "transporter_user_id": r["transporter_user_id"],
                "agreement_post_id": r.get("agreement_post_id"),
                "agreement_bid_id": r.get("agreement_bid_id"),
                "is_group_chat": as_bool(r.get("is_group_chat")),
                "admin_user_id": r.get("admin_user_id"),
                "dispute_trip_id": r.get("dispute_trip_id"),
                "last_message_at": parse_ts(r.get("last_message_at")),
                "created_at": ts_or_now(r.get("created_at")),
            }

        self.copy("chat_threads", "chat_threads", t_thread)

        def t_msg(r):
            return {
                "id": r["id"],
                "thread_id": r["thread_id"],
                "sender_user_id": r["sender_user_id"],
                "message_type": r.get("message_type") or "text",
                "content": r.get("content"),
                "media_path": r.get("media_path"),
                "media_request_status": r.get("media_request_status"),
                "is_read": as_bool(r.get("is_read")),
                "created_at": ts_or_now(r.get("created_at")),
            }

        self.copy("chat_messages", "chat_messages", t_msg)

    # ------------------------------------------------------------------
    def migrate_agreements(self):
        self.copy(
            "agreement_posts",
            "agreement_posts",
            lambda r: {
                "id": r["id"],
                "client_user_id": r["client_user_id"],
                "title": r.get("title") or "",
                "cargo_type": r.get("cargo_type") or "",
                "service_area": r.get("service_area") or "",
                "pickup_location": r.get("pickup_location"),
                "dropoff_location": r.get("dropoff_location"),
                "status": r.get("status") or "open",
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            },
        )
        self.copy(
            "agreement_post_trucks",
            "agreement_post_trucks",
            lambda r: {
                "id": r["id"],
                "post_id": r["post_id"],
                "truck_type": r.get("truck_type") or "",
                "capacity_tons": r.get("capacity_tons") or 0,
                "quantity": int(r.get("quantity") or 0),
            },
        )
        self.copy(
            "agreement_bids",
            "agreement_bids",
            lambda r: {
                "id": r["id"],
                "post_id": r["post_id"],
                "transporter_user_id": r["transporter_user_id"],
                "status": r.get("status") or "pending",
                "message": r.get("message"),
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            },
        )
        self.copy(
            "agreement_bid_trucks",
            "agreement_bid_trucks",
            lambda r: {
                "id": r["id"],
                "bid_id": r["bid_id"],
                "truck_id": r["truck_id"],
                "per_km_rate": r.get("per_km_rate") or 0,
                "minimum_monthly_guarantee": r.get("minimum_monthly_guarantee") or 0,
            },
        )
        self.copy(
            "agreements",
            "agreements",
            lambda r: {
                "id": r["id"],
                "post_id": r["post_id"],
                "client_user_id": r["client_user_id"],
                "duration_months": int(r.get("duration_months") or 0),
                "cargo_type": r.get("cargo_type") or "",
                "service_area": r.get("service_area") or "",
                "start_date": r.get("start_date") or "1970-01-01",
                "end_date": r.get("end_date") or "1970-01-01",
                "status": r.get("status") or "active",
                "contract_text": r.get("contract_text"),
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": ts_or_now(r.get("updated_at")),
            },
        )
        self.copy(
            "agreement_trucks",
            "agreement_trucks",
            lambda r: {
                "id": r["id"],
                "agreement_id": r["agreement_id"],
                "truck_id": r["truck_id"],
                "transporter_user_id": r["transporter_user_id"],
                "per_km_rate": r.get("per_km_rate") or 0,
                "minimum_monthly_guarantee": r.get("minimum_monthly_guarantee") or 0,
                "status": r.get("status") or "active",
            },
        )
        self.copy(
            "agreement_trips",
            "agreement_trips",
            lambda r: {
                "id": r["id"],
                "agreement_id": r["agreement_id"],
                "agreement_truck_id": r["agreement_truck_id"],
                "truck_id": r["truck_id"],
                "transporter_user_id": r["transporter_user_id"],
                "pickup_description": r.get("pickup_description") or "",
                "pickup_location": r.get("pickup_location"),
                "dropoff_location": r.get("dropoff_location"),
                "trip_date": r.get("trip_date") or "1970-01-01",
                "gps_start_lat": r.get("gps_start_lat"),
                "gps_start_lng": r.get("gps_start_lng"),
                "gps_end_lat": r.get("gps_end_lat"),
                "gps_end_lng": r.get("gps_end_lng"),
                "distance_km": r.get("distance_km"),
                "distance_source": r.get("distance_source"),
                "started_at": parse_ts(r.get("started_at")),
                "ended_at": parse_ts(r.get("ended_at")),
                "status": r.get("status") or "pending",
                "client_acknowledged": as_bool(r.get("client_acknowledged")),
                "admin_decision": r.get("admin_decision"),
                "admin_note": r.get("admin_note"),
                "admin_decided_at": parse_ts(r.get("admin_decided_at")),
                "admin_decided_by": r.get("admin_decided_by"),
                "created_at": ts_or_now(r.get("created_at")),
                "updated_at": parse_ts(r.get("updated_at")),
            },
        )
        self.copy(
            "agreement_monthly_payments",
            "agreement_monthly_payments",
            lambda r: {
                "id": r["id"],
                "agreement_id": r["agreement_id"],
                "agreement_truck_id": r["agreement_truck_id"],
                "transporter_user_id": r["transporter_user_id"],
                "client_user_id": r["client_user_id"],
                "month_year": r.get("month_year") or "",
                "total_km": r.get("total_km") or 0,
                "total_earned": r.get("total_earned") or 0,
                "minimum_guarantee": r.get("minimum_guarantee") or 0,
                "final_amount": r.get("final_amount") or 0,
                "company_fee": r.get("company_fee") or 0,
                "transporter_amount": r.get("transporter_amount") or 0,
                "penalty_amount": r.get("penalty_amount") or 0,
                "status": r.get("status") or "pending",
                "payment_due_date": r.get("payment_due_date") or "1970-01-01",
                "paid_at": parse_ts(r.get("paid_at")),
                "created_at": ts_or_now(r.get("created_at")),
            },
        )
        self.copy(
            "agreement_payment_penalties",
            "agreement_payment_penalties",
            lambda r: {
                "id": r["id"],
                "monthly_payment_id": r["monthly_payment_id"],
                "client_user_id": r["client_user_id"],
                "penalty_amount": r.get("penalty_amount") or 5000,
                "penalty_number": int(r.get("penalty_number") or 1),
                "applied_at": ts_or_now(r.get("applied_at")),
            },
        )

    # ------------------------------------------------------------------
    def migrate_misc(self):
        self.copy(
            "login_activity",
            "login_activity",
            lambda r: {
                "id": r["id"],
                "user_id": r.get("user_id"),
                "login_identifier": r.get("login_identifier"),
                "login_method": r.get("login_method"),
                "status": r.get("status") or "",
                "failure_reason": r.get("failure_reason"),
                "ip_address": r.get("ip_address"),
                "user_agent": r.get("user_agent"),
                "created_at": ts_or_now(r.get("created_at_iso") or r.get("created_at")),
            },
        )
        self.copy(
            "trusted_devices",
            "trusted_devices",
            lambda r: {
                "id": r["id"],
                "device_token": r["device_token"],
                "user_id": r["user_id"],
                "created_at": ts_or_now(r.get("created_at")),
                "last_seen_at": ts_or_now(r.get("last_seen_at")),
            },
        )
        self.copy(
            "user_action_logs",
            "user_action_logs",
            lambda r: {
                "id": r["id"],
                "user_id": str(r.get("user_id") or ""),
                "user_email": r.get("user_email"),
                "user_role": r.get("user_role"),
                "action_type": r.get("action_type"),
                "action_name": r.get("action_name"),
                "page_url": r.get("page_url"),
                "payload_json": as_json(r.get("payload_json")),
                "created_at": ts_or_now(r.get("created_at")),
            },
        )

    # ------------------------------------------------------------------
    def upload_files(self):
        if self.dry_run:
            print("  (dry-run) skipping file uploads")
            return
        if not UPLOADS_DIR.exists():
            print("  no local uploads directory — nothing to upload")
            return
        from shared.storage import guess_content_type, upload_bytes

        uploaded = 0
        for sub in ("trucks", "chat"):
            folder = UPLOADS_DIR / sub
            if not folder.exists():
                continue
            for path in folder.iterdir():
                if not path.is_file():
                    continue
                key = f"uploads/{sub}/{path.name}"
                try:
                    upload_bytes(key, path.read_bytes(), guess_content_type(path.name))
                    uploaded += 1
                except Exception as exc:
                    print(f"    ! upload failed {key}: {exc}")
        print(f"  files uploaded to Storage: {uploaded}")

        # Record truck document metadata
        with self.pg.cursor() as cur:
            for column, doc_type in (
                ("truck_photo_path", "vehicle_photo"),
                ("insurance_photo_path", "insurance"),
                ("rc_book_photo_path", "rc_book"),
            ):
                cur.execute(
                    f"""
                    INSERT INTO documents (owner_user_id, vehicle_id, doc_type, storage_path)
                    SELECT owner_user_id, id, %s, {column}
                    FROM vehicles
                    WHERE {column} IS NOT NULL AND trim({column}) <> ''
                    ON CONFLICT DO NOTHING
                    """,
                    (doc_type,),
                )

    # ------------------------------------------------------------------
    def bump_sequences(self):
        if self.dry_run:
            return
        for table in (
            "users", "customers", "drivers", "vehicles", "shipments", "shipment_bids",
            "shipment_trips", "shipment_trip_verification", "shipment_no_show_tracking",
            "shipment_cancellations", "shipment_notifications", "shipment_status_history",
            "documents", "payments", "wallets", "wallet_transactions",
            "wallet_withdrawal_requests", "chat_threads", "chat_messages",
            "agreement_posts", "agreement_post_trucks", "agreement_bids",
            "agreement_bid_trucks", "agreements", "agreement_trucks", "agreement_trips",
            "agreement_monthly_payments", "agreement_payment_penalties",
            "login_activity", "trusted_devices", "user_action_logs",
        ):
            self.bump_sequence(table)
        print("  identity sequences aligned")

    # ------------------------------------------------------------------
    def run(self):
        print(f"Migrating {SQLITE_PATH} -> Supabase" + (" (DRY RUN)" if self.dry_run else ""))
        print("[1/8] users")
        self.migrate_users()
        if not self.dry_run:
            self.pg.commit()
        print("[2/8] Supabase Auth accounts")
        self.create_auth_accounts()
        print("[3/8] vehicles")
        self.migrate_vehicles()
        print("[4/8] shipments domain")
        self.migrate_shipments_domain()
        print("[5/8] wallets")
        self.migrate_wallets()
        print("[6/8] chat + agreements + audit")
        self.migrate_chat()
        self.migrate_agreements()
        self.migrate_misc()
        if not self.dry_run:
            self.pg.commit()
        print("[7/8] derived tables + files")
        self.derive_drivers_and_customers()
        self.upload_files()
        print("[8/8] sequences")
        self.bump_sequences()
        if not self.dry_run:
            self.pg.commit()
        print("Done.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Count rows without writing anything")
    args = parser.parse_args()
    Migrator(dry_run=args.dry_run).run()


if __name__ == "__main__":
    main()
