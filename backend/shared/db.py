from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATABASE_PATH = BASE_DIR / "Database" / "digitransx_auth.db"
FRONTEND_DIST = BASE_DIR / "frontend-react" / "dist"
TRUCKS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS trucks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    truck_number TEXT NOT NULL UNIQUE COLLATE NOCASE,
    truck_type TEXT NOT NULL,
    catalog_type_key TEXT,
    chassis_number TEXT NOT NULL UNIQUE COLLATE NOCASE,
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
    status TEXT NOT NULL DEFAULT 'inactive',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    operating_provinces TEXT,
    per_km_rate REAL,
    waiting_charge_per_hour REAL,
    loading_charge REAL,
    refrigeration_supported INTEGER DEFAULT 0,
    hazardous_supported INTEGER DEFAULT 0,
    fragile_supported INTEGER DEFAULT 0,
    truck_photo_path TEXT,
    insurance_photo_path TEXT,
    rc_book_photo_path TEXT,
    status_reason_code TEXT,
    status_reason TEXT,
    FOREIGN KEY(owner_user_id) REFERENCES users(id)
);
"""
WALLETS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    role TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 0,
    locked_balance REAL NOT NULL DEFAULT 0,
    minimum_required REAL NOT NULL DEFAULT 0,
    is_minimum_met INTEGER NOT NULL DEFAULT 0,
    completed_trips_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""
WALLET_TRANSACTIONS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS wallet_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    gross_amount REAL,
    gateway_fee REAL DEFAULT 0,
    description TEXT,
    reference_id TEXT,
    balance_after REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(wallet_id) REFERENCES wallets(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""
ORDERS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_user_id INTEGER NOT NULL,
    pickup_city TEXT NOT NULL,
    pickup_area TEXT,
    dropoff_city TEXT NOT NULL,
    dropoff_area TEXT,
    pickup_date TEXT NOT NULL,
    pickup_time TEXT NOT NULL,
    goods_type TEXT NOT NULL,
    goods_weight_tons REAL NOT NULL,
    goods_volume_cbm REAL,
    required_truck_type TEXT NOT NULL,
    estimated_budget REAL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    accepted_bid_id INTEGER,
    trip_started_at TEXT,
    trip_stage TEXT DEFAULT 'not_started',
    accepted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(client_user_id) REFERENCES users(id)
);
"""
ORDER_BIDS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS order_bids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    transporter_user_id INTEGER NOT NULL,
    truck_id INTEGER NOT NULL,
    bid_price REAL NOT NULL,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(transporter_user_id) REFERENCES users(id),
    FOREIGN KEY(truck_id) REFERENCES trucks(id)
);
"""
ORDER_CANCELLATIONS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS order_cancellations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    cancelled_by TEXT NOT NULL,
    cancelled_by_user_id INTEGER NOT NULL,
    other_party_user_id INTEGER NOT NULL,
    trip_stage_at_cancellation TEXT NOT NULL,
    penalty_type TEXT NOT NULL,
    penalty_percent REAL,
    penalty_amount REAL,
    company_share_percent REAL,
    company_share_amount REAL,
    recipient_share_amount REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    negotiation_deadline TEXT,
    finalized_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    proposed_percent REAL,
    proposed_by_user_id INTEGER,
    proposed_at TEXT,
    FOREIGN KEY(order_id) REFERENCES orders(id)
);
"""
CHAT_THREADS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS chat_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    client_user_id INTEGER NOT NULL,
    transporter_user_id INTEGER NOT NULL,
    bid_id INTEGER,
    is_group_chat INTEGER DEFAULT 0,
    admin_user_id INTEGER,
    dispute_trip_id INTEGER,
    last_message_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(order_id, transporter_user_id),
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(client_user_id) REFERENCES users(id),
    FOREIGN KEY(transporter_user_id) REFERENCES users(id),
    FOREIGN KEY(bid_id) REFERENCES order_bids(id)
);
"""
CHAT_MESSAGES_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL,
    sender_user_id INTEGER NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'text',
    content TEXT,
    media_path TEXT,
    media_request_status TEXT,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(thread_id) REFERENCES chat_threads(id),
    FOREIGN KEY(sender_user_id) REFERENCES users(id)
);
"""
AGREEMENT_POSTS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreement_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    cargo_type TEXT NOT NULL,
    service_area TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(client_user_id) REFERENCES users(id)
);
"""
AGREEMENT_POST_TRUCKS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreement_post_trucks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    truck_type TEXT NOT NULL,
    capacity_tons REAL NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY(post_id) REFERENCES agreement_posts(id)
);
"""
AGREEMENT_BIDS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreement_bids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    transporter_user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(post_id) REFERENCES agreement_posts(id),
    FOREIGN KEY(transporter_user_id) REFERENCES users(id)
);
"""
AGREEMENT_BID_TRUCKS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreement_bid_trucks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_id INTEGER NOT NULL,
    truck_id INTEGER NOT NULL,
    per_km_rate REAL NOT NULL,
    minimum_monthly_guarantee REAL NOT NULL,
    FOREIGN KEY(bid_id) REFERENCES agreement_bids(id),
    FOREIGN KEY(truck_id) REFERENCES trucks(id)
);
"""
AGREEMENTS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    client_user_id INTEGER NOT NULL,
    duration_months INTEGER NOT NULL,
    cargo_type TEXT NOT NULL,
    service_area TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    contract_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(post_id) REFERENCES agreement_posts(id),
    FOREIGN KEY(client_user_id) REFERENCES users(id)
);
"""
AGREEMENT_TRUCKS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreement_trucks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agreement_id INTEGER NOT NULL,
    truck_id INTEGER NOT NULL,
    transporter_user_id INTEGER NOT NULL,
    per_km_rate REAL NOT NULL,
    minimum_monthly_guarantee REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY(agreement_id) REFERENCES agreements(id),
    FOREIGN KEY(truck_id) REFERENCES trucks(id),
    FOREIGN KEY(transporter_user_id) REFERENCES users(id)
);
"""
AGREEMENT_TRIPS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreement_trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agreement_id INTEGER NOT NULL,
    agreement_truck_id INTEGER NOT NULL,
    truck_id INTEGER NOT NULL,
    transporter_user_id INTEGER NOT NULL,
    pickup_description TEXT NOT NULL,
    pickup_location TEXT,
    dropoff_location TEXT,
    trip_date TEXT NOT NULL,
    gps_start_lat REAL,
    gps_start_lng REAL,
    gps_end_lat REAL,
    gps_end_lng REAL,
    distance_km REAL,
    started_at TEXT,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    client_acknowledged INTEGER DEFAULT 0,
    admin_decision TEXT,
    admin_note TEXT,
    admin_decided_at TEXT,
    admin_decided_by INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(agreement_id) REFERENCES agreements(id),
    FOREIGN KEY(agreement_truck_id) REFERENCES agreement_trucks(id),
    FOREIGN KEY(truck_id) REFERENCES trucks(id),
    FOREIGN KEY(transporter_user_id) REFERENCES users(id)
);
"""
AGREEMENT_MONTHLY_PAYMENTS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreement_monthly_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agreement_id INTEGER NOT NULL,
    agreement_truck_id INTEGER NOT NULL,
    transporter_user_id INTEGER NOT NULL,
    client_user_id INTEGER NOT NULL,
    month_year TEXT NOT NULL,
    total_km REAL NOT NULL DEFAULT 0,
    total_earned REAL NOT NULL DEFAULT 0,
    minimum_guarantee REAL NOT NULL,
    final_amount REAL NOT NULL,
    company_fee REAL NOT NULL,
    transporter_amount REAL NOT NULL,
    penalty_amount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    payment_due_date TEXT NOT NULL,
    paid_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(agreement_id) REFERENCES agreements(id),
    FOREIGN KEY(agreement_truck_id) REFERENCES agreement_trucks(id)
);
"""
AGREEMENT_PAYMENT_PENALTIES_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS agreement_payment_penalties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monthly_payment_id INTEGER NOT NULL,
    client_user_id INTEGER NOT NULL,
    penalty_amount REAL NOT NULL DEFAULT 5000,
    penalty_number INTEGER NOT NULL,
    applied_at TEXT NOT NULL,
    FOREIGN KEY(monthly_payment_id) REFERENCES agreement_monthly_payments(id)
);
"""
WALLET_WITHDRAWAL_REQUESTS_TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS wallet_withdrawal_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""


def open_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_column(db, table_name, column_name, definition):
    columns = [row[1] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def find_normalized_duplicates(db, table_name, column_name):
    return db.execute(
        f"""
        SELECT lower(trim({column_name})) AS normalized_value, COUNT(*) AS total
        FROM {table_name}
        WHERE {column_name} IS NOT NULL AND trim({column_name}) <> ''
        GROUP BY lower(trim({column_name}))
        HAVING COUNT(*) > 1
        """
    ).fetchall()


def ensure_unique_normalized_index(db, table_name, column_name, index_name):
    duplicates = find_normalized_duplicates(db, table_name, column_name)
    if duplicates:
        duplicate_values = ", ".join(f"{row['normalized_value']} ({row['total']})" for row in duplicates[:5])
        print(
            f"WARNING: Could not create unique index {index_name} because duplicate "
            f"{column_name} values already exist in {table_name}: {duplicate_values}. "
            "Please clean these records manually and rerun init_db()."
        )
        return
    db.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {index_name}
        ON {table_name} (trim({column_name}) COLLATE NOCASE)
        """
    )


def ensure_trucks_status_default(db):
    row = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'trucks'").fetchone()
    if not row or not row["sql"]:
        return
    create_sql = row["sql"]
    if "status TEXT NOT NULL DEFAULT 'inactive'" in create_sql:
        return

    truck_number_duplicates = find_normalized_duplicates(db, "trucks", "truck_number")
    chassis_number_duplicates = find_normalized_duplicates(db, "trucks", "chassis_number")
    if truck_number_duplicates or chassis_number_duplicates:
        duplicate_messages = []
        if truck_number_duplicates:
            duplicate_messages.append(
                "truck_number duplicates: "
                + ", ".join(f"{row['normalized_value']} ({row['total']})" for row in truck_number_duplicates[:5])
            )
        if chassis_number_duplicates:
            duplicate_messages.append(
                "chassis_number duplicates: "
                + ", ".join(f"{row['normalized_value']} ({row['total']})" for row in chassis_number_duplicates[:5])
            )
        print(
            "WARNING: Could not rebuild trucks table to update status default because duplicate "
            + "; ".join(duplicate_messages)
            + ". Please clean these records manually and rerun init_db()."
        )
        return

    db.executescript(
        f"""
        ALTER TABLE trucks RENAME TO trucks_legacy_status_default;
        {TRUCKS_TABLE_DEFINITION.replace("CREATE TABLE IF NOT EXISTS trucks", "CREATE TABLE trucks")}
        INSERT INTO trucks (
            id, owner_user_id, truck_number, truck_type, catalog_type_key, chassis_number,
            capacity_tons, main_use, payload_min_kg, payload_max_kg, volume_min_cbm, volume_max_cbm,
            body_style, catalog_specs_json, driver_name, driver_cnic, tracking_id, status,
            created_at, updated_at, operating_provinces, per_km_rate, waiting_charge_per_hour,
            loading_charge, refrigeration_supported, hazardous_supported, fragile_supported,
            truck_photo_path, insurance_photo_path, rc_book_photo_path, status_reason_code, status_reason
        )
        SELECT
            id, owner_user_id, truck_number, truck_type, catalog_type_key, chassis_number,
            capacity_tons, main_use, payload_min_kg, payload_max_kg, volume_min_cbm, volume_max_cbm,
            body_style, catalog_specs_json, driver_name, driver_cnic, tracking_id, status,
            created_at, updated_at, operating_provinces, per_km_rate, waiting_charge_per_hour,
            loading_charge, refrigeration_supported, hazardous_supported, fragile_supported,
            truck_photo_path, insurance_photo_path, rc_book_photo_path, status_reason_code, status_reason
        FROM trucks_legacy_status_default;
        DROP TABLE trucks_legacy_status_default;
        """
    )


def ensure_truck_catalog_type_keys(db):
    db.execute(
        """
        UPDATE trucks
        SET catalog_type_key = truck_type
        WHERE (catalog_type_key IS NULL OR trim(catalog_type_key) = '')
          AND truck_type IS NOT NULL
          AND trim(truck_type) <> ''
        """
    )


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
            """
        )
        db.executescript(TRUCKS_TABLE_DEFINITION)
        db.executescript(WALLETS_TABLE_DEFINITION)
        db.executescript(WALLET_TRANSACTIONS_TABLE_DEFINITION)
        db.executescript(WALLET_WITHDRAWAL_REQUESTS_TABLE_DEFINITION)
        db.executescript(ORDERS_TABLE_DEFINITION)
        db.executescript(ORDER_BIDS_TABLE_DEFINITION)
        db.executescript(ORDER_CANCELLATIONS_TABLE_DEFINITION)
        db.executescript(CHAT_THREADS_TABLE_DEFINITION)
        db.executescript(CHAT_MESSAGES_TABLE_DEFINITION)
        db.executescript(AGREEMENT_POSTS_TABLE_DEFINITION)
        db.executescript(AGREEMENT_POST_TRUCKS_TABLE_DEFINITION)
        db.executescript(AGREEMENT_BIDS_TABLE_DEFINITION)
        db.executescript(AGREEMENT_BID_TRUCKS_TABLE_DEFINITION)
        db.executescript(AGREEMENTS_TABLE_DEFINITION)
        db.executescript(AGREEMENT_TRUCKS_TABLE_DEFINITION)
        db.executescript(AGREEMENT_TRIPS_TABLE_DEFINITION)
        db.executescript(AGREEMENT_MONTHLY_PAYMENTS_TABLE_DEFINITION)
        db.executescript(AGREEMENT_PAYMENT_PENALTIES_TABLE_DEFINITION)
        ensure_column(db, "wallets", "completed_trips_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "users", "is_blocked", "INTEGER DEFAULT 0")
        ensure_column(db, "users", "block_reason", "TEXT")
        ensure_column(db, "orders", "trip_started_at", "TEXT")
        ensure_column(db, "orders", "trip_stage", "TEXT DEFAULT 'not_started'")
        ensure_column(db, "orders", "accepted_at", "TEXT")
        ensure_column(db, "order_cancellations", "proposed_percent", "REAL")
        ensure_column(db, "order_cancellations", "proposed_by_user_id", "INTEGER")
        ensure_column(db, "order_cancellations", "proposed_at", "TEXT")
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
        ensure_column(db, "chat_threads", "bid_id", "INTEGER")
        ensure_column(db, "chat_threads", "agreement_post_id", "INTEGER")
        ensure_column(db, "chat_threads", "agreement_bid_id", "INTEGER")
        ensure_column(db, "chat_threads", "is_group_chat", "INTEGER DEFAULT 0")
        ensure_column(db, "chat_threads", "admin_user_id", "INTEGER")
        ensure_column(db, "chat_threads", "dispute_trip_id", "INTEGER")
        ensure_column(db, "chat_threads", "last_message_at", "TEXT")
        ensure_column(db, "chat_messages", "message_type", "TEXT NOT NULL DEFAULT 'text'")
        ensure_column(db, "chat_messages", "content", "TEXT")
        ensure_column(db, "chat_messages", "media_path", "TEXT")
        ensure_column(db, "chat_messages", "media_request_status", "TEXT")
        ensure_column(db, "chat_messages", "is_read", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "agreement_trips", "admin_decision", "TEXT")
        ensure_column(db, "agreement_trips", "admin_note", "TEXT")
        ensure_column(db, "agreement_trips", "admin_decided_at", "TEXT")
        ensure_column(db, "agreement_trips", "admin_decided_by", "INTEGER")
        ensure_column(db, "trucks", "traccar_device_id", "TEXT")
        ensure_column(db, "agreement_trips", "distance_source", "TEXT")
        ensure_column(db, "agreement_trips", "updated_at", "TEXT")
        ensure_column(db, "users", "withdrawal_tier", "INTEGER DEFAULT 0")
        ensure_column(db, "users", "withdrawal_tier_expires_at", "TEXT")
        ensure_column(db, "wallet_withdrawal_requests", "processed_at", "TEXT")
        ensure_column(db, "users", "payout_card_number", "TEXT")
        ensure_column(db, "users", "payout_card_holder", "TEXT")
        ensure_column(db, "users", "payout_card_expiry", "TEXT")
        ensure_column(db, "users", "payout_card_bank", "TEXT")
        ensure_trucks_status_default(db)
        ensure_truck_catalog_type_keys(db)
        ensure_unique_normalized_index(db, "trucks", "truck_number", "idx_trucks_truck_number_unique_normalized")
        ensure_unique_normalized_index(db, "trucks", "chassis_number", "idx_trucks_chassis_number_unique_normalized")
        db.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_created ON wallet_transactions(user_id, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_wallet_created ON wallet_transactions(wallet_id, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_wallet_withdrawal_requests_user_status ON wallet_withdrawal_requests(user_id, status, requested_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_orders_client_status_created ON orders(client_user_id, status, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_orders_required_truck_status ON orders(required_truck_type, status, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_order_bids_order_status_created ON order_bids(order_id, status, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_order_bids_transporter_created ON order_bids(transporter_user_id, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_order_cancellations_order_status ON order_cancellations(order_id, status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_order_cancellations_deadline ON order_cancellations(status, negotiation_deadline)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_chat_threads_client_last ON chat_threads(client_user_id, last_message_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_chat_threads_transporter_last ON chat_threads(transporter_user_id, last_message_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_created ON chat_messages(thread_id, id ASC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_read ON chat_messages(thread_id, is_read, sender_user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_agreement_posts_client_status ON agreement_posts(client_user_id, status, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_agreement_post_trucks_post_type ON agreement_post_trucks(post_id, truck_type)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_agreement_bids_post_transporter ON agreement_bids(post_id, transporter_user_id, status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_agreement_trucks_agreement_transporter ON agreement_trucks(agreement_id, transporter_user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_agreement_trips_agreement_truck ON agreement_trips(agreement_id, truck_id, status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_agreement_payments_due_status ON agreement_monthly_payments(status, payment_due_date)")
        db.commit()
