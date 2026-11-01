"""Read-only matching audit for a single order against the 50 seeded test
transporters.

Given ``--order-id``, it fetches the real shipment and the marked active test
vehicles, then runs the PRODUCTION ``orders.helpers.truck_order_mismatch``
directly against each one — it never reimplements type, weight, volume or
dimension matching. It prints which transporters/trucks match and the exact
production rejection reason for every non-match, plus totals by catalog type.

It exists because the current seeker UI does not list matched transporters,
yet matching is what controls a transporter's available-orders visibility and
bid validation. The script creates no bids and modifies nothing.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import matching_fixtures as fx  # noqa: E402
from orders.helpers import (  # noqa: E402
    parse_truck_types,
    truck_order_eligibility_mismatch,
    truck_distance_to_pickup_km,
)

SEED_OUTPUT_DIR = BACKEND_DIR / "scripts" / "seed_output"


def _fetch_order(db, order_id):
    row = db.execute("SELECT * FROM shipments WHERE id = %s", (order_id,)).fetchone()
    return dict(row) if row else None


def _fetch_marked_active_vehicles(db):
    """Only the marked active test vehicles (owner is a seed user), joined so a
    non-test vehicle can never enter the audit."""
    where_sql, where_params = fx.marked_users_where()
    rows = db.execute(
        "SELECT v.*, u.email AS owner_email, u.full_name AS owner_name "
        "FROM vehicles v JOIN users u ON u.id = v.owner_user_id "
        f"WHERE v.status = 'active' AND {where_sql} "
        "ORDER BY u.email",
        where_params,
    ).fetchall()
    return [dict(r) for r in rows]


def audit(order_id):
    from shared.db import open_db

    with open_db() as db:
        order = _fetch_order(db, order_id)
        if not order:
            raise SystemExit(f"Order {order_id} not found.")
        vehicles = _fetch_marked_active_vehicles(db)

    required_types = parse_truck_types(order.get("required_truck_types"))

    matches, non_matches = [], []
    totals = {}  # catalog_type_key -> {"total", "matched"}
    for v in vehicles:
        key = v.get("catalog_type_key") or v.get("truck_type") or "?"
        bucket = totals.setdefault(key, {"total": 0, "matched": 0})
        bucket["total"] += 1
        # The SAME production eligibility helper the app uses everywhere:
        # cargo (type/weight/volume/dimensions) composed with pickup location.
        reason = truck_order_eligibility_mismatch(v, required_types, order)
        record = {
            "vehicle_id": v["id"],
            "owner_email": v.get("owner_email"),
            "owner_name": v.get("owner_name"),
            "truck_number": v.get("truck_number"),
            "catalog_type_key": key,
            "capacity_tons": v.get("capacity_tons"),
            "volume_max_cbm": v.get("volume_max_cbm"),
            "bed_length_ft": v.get("bed_length_ft"),
            "bed_width_ft": v.get("bed_width_ft"),
            "bed_height_ft": v.get("bed_height_ft"),
            "current_city": v.get("current_city"),
            "distance_to_pickup_km": truck_distance_to_pickup_km(v, order),
            "reason": reason,
        }
        if reason is None:
            bucket["matched"] += 1
            matches.append(record)
        else:
            non_matches.append(record)

    return {
        "order": order,
        "required_types": required_types,
        "matches": matches,
        "non_matches": non_matches,
        "totals": totals,
        "vehicle_count": len(vehicles),
    }


def _print_report(result):
    order = result["order"]
    print("=" * 72)
    print(f"Order #{order.get('id')}  status={order.get('status')}")
    print(f"  commodity:      {order.get('goods_commodity') or order.get('goods_type')}")
    print(f"  pickup:         {order.get('pickup_city') or order.get('pickup_location')}")
    print(f"  pickup coords:  lat={order.get('pickup_lat')} lng={order.get('pickup_lng')}")
    print(f"  required types: {result['required_types'] or '(any)'}")
    print(f"  weight (tons):  {order.get('goods_weight_tons')}")
    print(f"  volume (cbm):   {order.get('goods_volume_cbm')}")
    print(f"  dimensions cm:  L={order.get('length_cm')} W={order.get('width_cm')} H={order.get('height_cm')}")
    print(f"  refrigerated={order.get('is_refrigerated')} hazardous={order.get('is_hazardous')} "
          f"food_grade={order.get('is_food_grade')}")
    print("=" * 72)

    print(f"\nMATCHED transporters ({len(result['matches'])} of {result['vehicle_count']}):")
    if not result["matches"]:
        print("  (none)")
    for m in result["matches"]:
        dist = m.get("distance_to_pickup_km")
        dist_str = f"{dist}km" if dist is not None else "city-match"
        print(f"  ✓ {m['owner_email']}  truck={m['truck_number']}  type={m['catalog_type_key']}  "
              f"cap={m['capacity_tons']}t  city={m.get('current_city')}  dist={dist_str}")

    print(f"\nNON-MATCHES ({len(result['non_matches'])}) with exact production reason:")
    for m in result["non_matches"]:
        print(f"  ✗ {m['owner_email']}  truck={m['truck_number']}  type={m['catalog_type_key']}")
        print(f"      → {m['reason']}")

    print("\nTotals by catalog type (matched / total):")
    for key, bucket in sorted(result["totals"].items()):
        print(f"  {bucket['matched']:>2} / {bucket['total']:>2}   {key}")


def _write_output(result, out_path, fmt):
    SEED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(out_path) if out_path else SEED_OUTPUT_DIR / f"audit_order_{result['order']['id']}.{fmt}"
    rows = result["matches"] + result["non_matches"]
    if fmt == "json":
        path.write_text(json.dumps(
            {
                "order_id": result["order"]["id"],
                "required_types": result["required_types"],
                "totals": result["totals"],
                "results": rows,
            },
            indent=2, default=str,
        ), encoding="utf-8")
    else:  # csv
        fieldnames = [
            "vehicle_id", "owner_email", "owner_name", "truck_number",
            "catalog_type_key", "capacity_tons", "volume_max_cbm",
            "bed_length_ft", "bed_width_ft", "bed_height_ft",
            "current_city", "distance_to_pickup_km", "reason",
        ]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k) for k in fieldnames})
    print(f"\nReport written: {path}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-id", required=True, type=int, help="Shipment/order id to audit.")
    parser.add_argument("--output", default=None, help="Optional report path (default: seed_output/).")
    parser.add_argument("--format", choices=("csv", "json"), default=None,
                        help="Write a CSV/JSON report in addition to the printout.")
    return parser


def main():
    args = build_parser().parse_args()
    result = audit(args.order_id)
    _print_report(result)
    if args.format or args.output:
        fmt = args.format or "json"
        _write_output(result, args.output, fmt)


if __name__ == "__main__":
    main()
