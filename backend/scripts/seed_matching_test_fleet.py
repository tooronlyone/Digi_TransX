"""Seed (or clean up) 50 clearly-tagged test transporters with one active
primary vehicle each, for exercising the production order/truck matching rules.

Safety model
------------
* Dry-run is the DEFAULT. Nothing is written and nothing connects to the
  database or Supabase unless you pass ``--apply`` (seed) or
  ``--cleanup --confirm-delete`` (delete).
* Writes require ``--confirm-project-ref <exact-ref>`` matching the project
  derived from SUPABASE_URL. Only a MASKED ref/host is ever displayed; keys,
  passwords and full DB URLs are never printed or logged.
* If the target is not clearly development/staging/test, the script stops and
  asks for an extra explicit ``--allow-nonobvious-target`` confirmation.
* The common test password is read from DIGITRANSX_MATCHING_TEST_PASSWORD and
  is never hard-coded, printed or committed.

Idempotency
-----------
Rerunning creates zero duplicate Auth users, public users, profiles or
vehicles. Existing seed rows (identified by the exact email prefix + settings
marker) are repaired/updated in place. If Auth creation succeeds but the DB
write for that same transporter fails, only that just-created Auth user is
compensated (deleted); accounts that existed before the run are never touched.

It reuses the existing shared Supabase client (``supabase_create_user`` /
service client) and the existing ``shared.db`` wrapper — no second
registration path, catalog, table, route or matching algorithm is introduced.
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import os  # noqa: E402

import matching_fixtures as fx  # noqa: E402

SEED_OUTPUT_DIR = BACKEND_DIR / "scripts" / "seed_output"


# --- Supabase Auth helpers (reuse the shared service client) ----------------
def _find_auth_user_by_email(client, email):
    """Page through the Auth admin user list to find one by email."""
    page = 1
    while True:
        try:
            users = client.auth.admin.list_users(page=page, per_page=200)
        except TypeError:
            users = client.auth.admin.list_users()
        if not users:
            return None
        for user in users:
            if (getattr(user, "email", "") or "").lower() == email.lower():
                return user
        if len(users) < 200:
            return None
        page += 1


def _get_or_create_auth_user(client, email, password, metadata):
    """Return (auth_user, created_bool). Idempotent: reuses an existing Auth
    user with the same email instead of failing."""
    try:
        response = client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": metadata,
            }
        )
        return response.user, True
    except Exception:
        existing = _find_auth_user_by_email(client, email)
        if existing is not None:
            return existing, False
        raise


def _compensate_orphan_auth(client, orphans):
    """Delete ONLY Auth users this run just created whose DB write then failed.
    Reports any it could not remove; never raises."""
    for email, auth_id in orphans:
        try:
            client.auth.admin.delete_user(str(auth_id))
            print(f"  compensated (deleted orphan Auth user): {email}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! could not remove orphan Auth user {email}: {exc}")


# --- Target gating ----------------------------------------------------------
def _resolve_target(args, need_write):
    ref, host = fx.project_ref_and_host()
    print(f"Target Supabase project (masked): ref={fx.mask_ref(ref)}  host={fx.mask_host(host)}")
    if not need_write:
        return ref, host
    if not ref:
        raise SystemExit("SUPABASE_URL is not configured; cannot determine the target project.")
    if args.confirm_project_ref != ref:
        raise SystemExit(
            "Refusing to write: --confirm-project-ref does not match the configured "
            "project. Re-run with the exact project ref for this environment."
        )
    if not fx.looks_like_test_target(ref, host) and not args.allow_nonobvious_target:
        raise SystemExit(
            "Refusing to write: the target does not clearly look like a "
            "development/staging/test project. If you are certain this is a "
            "disposable test target, re-run with --allow-nonobvious-target."
        )
    return ref, host


# --- Plan / dry-run ---------------------------------------------------------
def _distribution_counts(dist):
    counts = {}
    for key in dist:
        counts[key] = counts.get(key, 0) + 1
    return counts


def _print_plan(dist):
    counts = _distribution_counts(dist)
    print(f"\nPlan: {fx.FLEET_COUNT} test transporters, {fx.FLEET_COUNT} active primary vehicles.")
    print(f"Emails: {fx.seed_email(1)} .. {fx.seed_email(fx.FLEET_COUNT)}")
    print(f"Marker: settings/{fx.SEED_TAG_KEY} = {fx.SEED_MARKER}")
    print(f"\nTruck-type distribution ({fx.CATALOG_TYPE_COUNT} catalog types, each >= 2):")
    for key, count in counts.items():
        print(f"  {count}x  {key}")
    missing = [t["type_key"] for t in fx.TRUCK_TYPES if counts.get(t["type_key"], 0) < 2]
    if missing:
        raise SystemExit(f"Distribution invalid — types below 2: {missing}")
    print("\nDRY-RUN: nothing written. Re-run with --apply and --confirm-project-ref to seed.")


# --- Seed -------------------------------------------------------------------
def _upsert_transporter(db, n, type_key, occurrence):
    """Repair/insert public.users, transporter_profiles and the vehicle for one
    transporter. Returns a small manifest dict. Assumes the Auth user (and thus
    the trigger-created public.users row) already exists."""
    email = fx.seed_email(n)

    # Enforce the intended identity on public.users and stamp the safe marker.
    db.execute(
        "UPDATE users SET role = %s, legacy_role = %s, full_name = %s, phone = %s, "
        "cnic = %s, city = %s, "
        "settings_json = jsonb_set(coalesce(settings_json, '{}'::jsonb), %s, %s::jsonb, true), "
        "updated_at = now() WHERE email = %s",
        (
            fx.ROLE, fx.LEGACY_ROLE, fx.seed_full_name(n), fx.seed_phone(n),
            fx.seed_cnic(n), "Test City",
            "{" + fx.SEED_TAG_KEY + "}", json.dumps(fx.SEED_MARKER),
            email,
        ),
    )
    user_row = db.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
    if not user_row:
        raise RuntimeError(f"public.users row missing for {email} after Auth create/link")
    user_id = user_row["id"]

    # transporter_profiles: one row per user (idempotent upsert).
    prof = db.execute(
        "INSERT INTO transporter_profiles (user_id, company_name, fleet_size) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET company_name = excluded.company_name, "
        "fleet_size = excluded.fleet_size, updated_at = now() "
        "RETURNING (xmax = 0) AS inserted",
        (user_id, fx.seed_company(n), "1"),
    ).fetchone()
    profile_inserted = bool(prof and prof.get("inserted"))

    # Vehicle: one active primary vehicle, keyed by the deterministic truck no.
    fields = fx.build_vehicle_fields(n, type_key, occurrence)
    specs = json.dumps(fx.vehicle_specs_marker(n, type_key))
    existing = db.execute(
        "SELECT id FROM vehicles WHERE lower(trim(truck_number)) = lower(trim(%s))",
        (fields["truck_number"],),
    ).fetchone()

    columns = [
        "truck_company", "truck_model", "truck_type", "catalog_type_key",
        "chassis_number", "capacity_tons", "main_use", "payload_min_tons",
        "payload_max_tons", "volume_min_cbm", "volume_max_cbm", "bed_length_ft",
        "bed_width_ft", "bed_height_ft", "body_style", "operating_provinces",
        "refrigeration_supported", "hazardous_supported", "fragile_supported",
        "status",
    ]
    values = [fields[c] for c in columns]

    if existing:
        set_clause = ", ".join(f"{c} = %s" for c in columns)
        db.execute(
            f"UPDATE vehicles SET owner_user_id = %s, {set_clause}, "
            f"catalog_specs_json = %s::jsonb, updated_at = now() WHERE id = %s",
            [user_id, *values, specs, existing["id"]],
        )
        vehicle_inserted = False
        vehicle_id = existing["id"]
    else:
        placeholders = ", ".join(["%s"] * (len(columns) + 1))  # + owner
        veh = db.execute(
            f"INSERT INTO vehicles (owner_user_id, {', '.join(columns)}, catalog_specs_json) "
            f"VALUES ({placeholders}, %s::jsonb) RETURNING id",
            [user_id, *values, specs],
        ).fetchone()
        vehicle_inserted = True
        vehicle_id = veh["id"]

    return {
        "index": n,
        "email": email,
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "catalog_type_key": type_key,
        "truck_number": fields["truck_number"],
        "chassis_number": fields["chassis_number"],
        "profile_inserted": profile_inserted,
        "vehicle_inserted": vehicle_inserted,
    }


def run_seed(args):
    from shared.db import open_db
    from shared.supabase_client import get_service_client

    dist = fx.build_type_distribution()

    if not args.apply:
        _resolve_target(args, need_write=False)
        _print_plan(dist)
        return

    _resolve_target(args, need_write=True)
    password = os.environ.get(fx.PASSWORD_ENV, "")
    if not password:
        raise SystemExit(
            f"{fx.PASSWORD_ENV} is not set; refusing to create Auth users without a password."
        )

    client = get_service_client()
    summary = {
        "created_auth": 0, "reused_auth": 0,
        "profiles_inserted": 0, "profiles_updated": 0,
        "vehicles_inserted": 0, "vehicles_updated": 0,
    }
    manifest = []

    plan = fx.build_fleet_plan()
    with open_db() as db:
        for entry in plan:
            n, type_key, occurrence = entry["index"], entry["type_key"], entry["occurrence"]
            email = fx.seed_email(n)
            orphan = None
            try:
                auth_user, created = _get_or_create_auth_user(
                    client, email, password, fx.seed_metadata(n)
                )
                if created:
                    orphan = (email, auth_user.id)  # pending until we commit

                row = _upsert_transporter(db, n, type_key, occurrence)
                db.commit()  # durable per-transporter -> reruns skip completed work
                orphan = None

                summary["created_auth" if created else "reused_auth"] += 1
                summary["profiles_inserted" if row["profile_inserted"] else "profiles_updated"] += 1
                summary["vehicles_inserted" if row["vehicle_inserted"] else "vehicles_updated"] += 1
                manifest.append(row)
                print(
                    f"  [{n:02d}/{fx.FLEET_COUNT}] {email}  {type_key}  "
                    f"truck={row['truck_number']}  "
                    f"{'created' if created else 'reused'}"
                )
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                print(f"  ! failed on {email}: {exc}")
                if orphan is not None:
                    _compensate_orphan_auth(client, [orphan])
                raise

    _write_report(args, {"summary": summary, "transporters": manifest})
    print("\nSeed summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


# --- Cleanup ----------------------------------------------------------------
def run_cleanup(args):
    from shared.db import open_db
    from shared.supabase_client import get_service_client

    _resolve_target(args, need_write=args.confirm_delete)

    where_sql, where_params = fx.marked_users_where()
    with open_db() as db:
        rows = db.execute(
            f"SELECT id, auth_id, email FROM users WHERE {where_sql} ORDER BY email",
            where_params,
        ).fetchall()

        print(f"\n{len(rows)} marked test user(s) match the exact prefix + marker:")
        for r in rows:
            veh = db.execute(
                "SELECT count(*) AS c FROM vehicles WHERE owner_user_id = %s", (r["id"],)
            ).fetchone()["c"]
            auth_display = fx.mask_ref(str(r["auth_id"])) if r["auth_id"] else "(no auth)"
            print(f"  user_id={r['id']}  auth={auth_display}  {r['email']}  vehicles={veh}")

        if not rows:
            print("Nothing to clean up.")
            return

        if not args.confirm_delete:
            print("\nDRY-RUN: no rows deleted. Re-run with --confirm-delete (and "
                  "--confirm-project-ref) to remove exactly these users and their "
                  "cascaded profiles/vehicles.")
            return

        # Delete public.users (cascades transporter_profiles + vehicles). The
        # WHERE guard is re-applied on every DELETE so a non-marked row is
        # impossible to hit.
        deleted, auth_targets = [], []
        for r in rows:
            result = db.execute(
                f"DELETE FROM users WHERE id = %s AND {where_sql}",
                [r["id"], *where_params],
            )
            if result.rowcount == 1:
                deleted.append(r["id"])
                if r["auth_id"]:
                    auth_targets.append((r["email"], r["auth_id"]))
        db.commit()
        print(f"Deleted {len(deleted)} public user(s) (profiles/vehicles cascaded).")

        # Remove the corresponding Auth users; report any that resist removal.
        client = get_service_client()
        failed = []
        for email, auth_id in auth_targets:
            try:
                client.auth.admin.delete_user(str(auth_id))
            except Exception as exc:  # noqa: BLE001
                failed.append((email, str(exc)))
        print(f"Deleted {len(auth_targets) - len(failed)} Auth user(s).")
        if failed:
            print("Could NOT remove these Auth users (remove manually):")
            for email, err in failed:
                print(f"  {email}: {err}")


# --- Report -----------------------------------------------------------------
def _write_report(args, payload):
    if args.no_report:
        return
    SEED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(args.report) if args.report else SEED_OUTPUT_DIR / "seed_manifest.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Manifest written: {path}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform writes (seed). Default is dry-run.")
    parser.add_argument("--cleanup", action="store_true", help="Cleanup mode (dry-run unless --confirm-delete).")
    parser.add_argument("--confirm-delete", action="store_true", help="Second confirmation required to actually delete.")
    parser.add_argument("--confirm-project-ref", default=None, help="Exact project ref of the target; required for writes.")
    parser.add_argument("--allow-nonobvious-target", action="store_true",
                        help="Explicitly proceed when the target is not clearly dev/staging/test.")
    parser.add_argument("--report", default=None, help="Path for the JSON manifest (default: seed_output/).")
    parser.add_argument("--no-report", action="store_true", help="Do not write a manifest file.")
    return parser


def main():
    args = build_parser().parse_args()
    if args.cleanup:
        run_cleanup(args)
    else:
        run_seed(args)


if __name__ == "__main__":
    main()
