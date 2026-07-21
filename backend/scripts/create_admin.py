"""Create or update a Digi_TransX platform admin (Supabase Auth + profile)."""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth.helpers import normalize_email, split_name, timestamp_bundle
from shared.db import open_db
from shared.supabase_client import supabase_create_user, supabase_update_password


def available_admin_cnic(db, current_user_id=None):
    base = "0000000000000"
    existing = db.execute("SELECT id FROM users WHERE cnic = %s", (base,)).fetchone()
    if not existing or existing["id"] == current_user_id:
        return base
    for suffix in range(1, 10000):
        value = f"000000000{suffix:04d}"[-13:]
        existing = db.execute("SELECT id FROM users WHERE cnic = %s", (value,)).fetchone()
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

    stamp = timestamp_bundle()["iso"]
    with open_db() as db:
        existing = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
        if existing:
            if existing["auth_id"]:
                supabase_update_password(existing["auth_id"], args.password)
            else:
                supabase_create_user(
                    email,
                    args.password,
                    {
                        "full_name": existing.get("full_name") or args.name,
                        "phone": existing.get("phone") or "",
                        "cnic": existing.get("cnic") or "",
                        "role": "admin",
                        "legacy_role": "platform_admin",
                    },
                )
            db.execute(
                """
                UPDATE users
                SET role = 'admin', legacy_role = 'platform_admin', cnic = %s, updated_at = %s
                WHERE id = %s
                """,
                (available_admin_cnic(db, existing["id"]), stamp, existing["id"]),
            )
            action = "updated"
            user_id = existing["id"]
        else:
            cnic = available_admin_cnic(db)
            supabase_create_user(
                email,
                args.password,
                {
                    "full_name": args.name.strip() or "Platform Admin",
                    "phone": "",
                    "cnic": cnic,
                    "role": "admin",
                    "legacy_role": "platform_admin",
                },
            )
            db.execute(
                """
                UPDATE users
                SET full_name = %s, role = 'admin',
                    legacy_role = 'platform_admin', city = '', updated_at = %s
                WHERE email = %s
                """,
                (args.name.strip() or "Platform Admin", stamp, email),
            )
            action = "created"
            user_id = db.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()["id"]
        db.commit()

    print(f"Platform admin {action}: id={user_id}, email={email}, role=platform_admin")


if __name__ == "__main__":
    main()
