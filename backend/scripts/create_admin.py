import argparse
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth.helpers import normalize_email, split_name, timestamp_bundle
from shared.db import init_db, open_db


def available_admin_cnic(db, current_user_id=None):
    base = "0000000000000"
    existing = db.execute("SELECT id FROM users WHERE cnic = ?", (base,)).fetchone()
    if not existing or existing["id"] == current_user_id:
        return base
    for suffix in range(1, 10000):
        value = f"000000000{suffix:04d}"[-13:]
        existing = db.execute("SELECT id FROM users WHERE cnic = ?", (value,)).fetchone()
        if not existing or existing["id"] == current_user_id:
            return value
    raise RuntimeError("Could not find an available placeholder CNIC.")


def main():
    parser = argparse.ArgumentParser(description="Create or update a Digi_TransX platform admin.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Platform Admin")
    args = parser.parse_args()

    email = normalize_email(args.email)
    if not email:
        raise SystemExit("Email is required.")
    if len(args.password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    init_db()
    stamp = timestamp_bundle()["display"]
    with open_db() as db:
        existing = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            db.execute(
                """
                UPDATE users
                SET password_hash = ?, role = 'platform_admin', cnic = ?, updated_at = ?
                WHERE id = ?
                """,
                (generate_password_hash(args.password), available_admin_cnic(db, existing["id"]), stamp, existing["id"]),
            )
            action = "updated"
            user_id = existing["id"]
        else:
            first_name, last_name = split_name(args.name)
            db.execute(
                """
                INSERT INTO users (
                    full_name, first_name, last_name, email, phone, cnic, password_hash, role,
                    city, mpin_hash, mpin_enabled, settings_json, created_at, updated_at, last_login_at
                ) VALUES (?, ?, ?, ?, '', ?, ?, 'platform_admin', '', NULL, 0, '{}', ?, ?, ?)
                """,
                (
                    args.name.strip() or "Platform Admin",
                    first_name,
                    last_name,
                    email,
                    available_admin_cnic(db),
                    generate_password_hash(args.password),
                    stamp,
                    stamp,
                    stamp,
                ),
            )
            action = "created"
            user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()

    print(f"Platform admin {action}: id={user_id}, email={email}, role=platform_admin")


if __name__ == "__main__":
    main()

