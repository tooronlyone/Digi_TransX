PRAGMA foreign_keys = OFF;

DROP INDEX IF EXISTS idx_orders_client_status_created;
DROP INDEX IF EXISTS idx_orders_required_truck_status;
DROP INDEX IF EXISTS idx_order_bids_order_status_created;
DROP INDEX IF EXISTS idx_order_bids_transporter_created;
DROP INDEX IF EXISTS idx_order_cancellations_order_status;
DROP INDEX IF EXISTS idx_order_cancellations_deadline;

CREATE TABLE IF NOT EXISTS chat_threads_agreement_only (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_user_id INTEGER NOT NULL,
    transporter_user_id INTEGER NOT NULL,
    agreement_post_id INTEGER,
    agreement_bid_id INTEGER,
    is_group_chat INTEGER DEFAULT 0,
    admin_user_id INTEGER,
    dispute_trip_id INTEGER,
    last_message_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(agreement_post_id, transporter_user_id),
    FOREIGN KEY(client_user_id) REFERENCES users(id),
    FOREIGN KEY(transporter_user_id) REFERENCES users(id),
    FOREIGN KEY(agreement_post_id) REFERENCES agreement_posts(id),
    FOREIGN KEY(agreement_bid_id) REFERENCES agreement_bids(id)
);

INSERT OR IGNORE INTO chat_threads_agreement_only (
    id, client_user_id, transporter_user_id, agreement_post_id, agreement_bid_id,
    is_group_chat, admin_user_id, dispute_trip_id, last_message_at, created_at
)
SELECT
    id, client_user_id, transporter_user_id, agreement_post_id, agreement_bid_id,
    COALESCE(is_group_chat, 0), admin_user_id, dispute_trip_id, last_message_at, created_at
FROM chat_threads
WHERE agreement_post_id IS NOT NULL OR COALESCE(is_group_chat, 0) = 1;

DROP TABLE IF EXISTS chat_threads;
ALTER TABLE chat_threads_agreement_only RENAME TO chat_threads;

DROP TABLE IF EXISTS order_cancellations;
DROP TABLE IF EXISTS order_bids;
DROP TABLE IF EXISTS orders;

PRAGMA foreign_keys = ON;
