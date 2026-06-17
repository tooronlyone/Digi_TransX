from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATABASE_PATH = BASE_DIR / "Database" / "digitransx_auth.db"
FRONTEND_DIST = BASE_DIR / "frontend-react" / "dist"


def open_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_column(db, table_name, column_name, definition):
    columns = [row[1] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db():
    with open_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                cnic TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                company_name TEXT,
                business_type TEXT,
                city TEXT,
                fleet_size TEXT,
                transport_need TEXT,
                station_name TEXT,
                pumps_count TEXT,
                license_no TEXT,
                shop_name TEXT,
                address TEXT,
                about TEXT,
                mpin_hash TEXT,
                mpin_enabled INTEGER NOT NULL DEFAULT 0,
                settings_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS login_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                login_identifier TEXT,
                login_method TEXT,
                status TEXT NOT NULL,
                failure_reason TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                created_at_iso TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS password_reset_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                purpose TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                expires_at_iso TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_at_iso TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5,
                verified INTEGER NOT NULL DEFAULT 0,
                cooldown_until_iso TEXT,
                delivery_target TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                purpose TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at_iso TEXT NOT NULL,
                created_at_iso TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS trusted_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_token TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS user_action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_email TEXT,
                user_role TEXT,
                action_type TEXT,
                action_name TEXT,
                page_url TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trucks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                truck_number TEXT NOT NULL,
                truck_type TEXT NOT NULL,
                catalog_type_key TEXT,
                chassis_number TEXT NOT NULL,
                capacity_tons REAL NOT NULL,
                main_use TEXT NOT NULL,
                payload_min_kg REAL,
                payload_max_kg REAL,
                volume_min_cbm REAL,
                volume_max_cbm REAL,
                body_style TEXT,
                catalog_specs_json TEXT,
                driver_name TEXT,
                driver_cnic TEXT,
                tracking_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(owner_user_id) REFERENCES users(id)
            );
            """
        )
        ensure_column(db, "trucks", "operating_provinces", "TEXT")
        ensure_column(db, "trucks", "per_km_rate", "REAL")
        ensure_column(db, "trucks", "waiting_charge_per_hour", "REAL")
        ensure_column(db, "trucks", "loading_charge", "REAL")
        ensure_column(db, "trucks", "refrigeration_supported", "INTEGER DEFAULT 0")
        ensure_column(db, "trucks", "hazardous_supported", "INTEGER DEFAULT 0")
        ensure_column(db, "trucks", "fragile_supported", "INTEGER DEFAULT 0")
        ensure_column(db, "trucks", "truck_photo_path", "TEXT")
        ensure_column(db, "trucks", "insurance_photo_path", "TEXT")
        ensure_column(db, "trucks", "rc_book_photo_path", "TEXT")
        ensure_column(db, "trucks", "status_reason_code", "TEXT")
        ensure_column(db, "trucks", "status_reason", "TEXT")
        db.commit()
