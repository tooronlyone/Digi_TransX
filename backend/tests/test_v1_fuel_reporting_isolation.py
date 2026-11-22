"""Comprehensive V1 fuel reporting, read-only transporter history, financial parity, and V2 isolation proofs."""
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest

from auth import step_up_service
import scheduler as scheduler_mod
from shared.payments import approved_booking_financial_terms, release_one_time_payment
from tests.remediation_harness import remediation_database_url, remediation_env
from tests.test_trip_lifecycle import seed_ready_order


REPO_ROOT = Path(__file__).resolve().parents[2]


def _setup_driver_and_fleet(env):
    owner_a = env.user("logistics_provider")
    owner_b = env.user("transporter")
    customer = env.user("service_seeker")
    driver_a = env.user("driver")
    driver_b = env.user("driver")

    code_a = "DRV-" + uuid4().hex[:10].upper()
    code_b = "DRV-" + uuid4().hex[:10].upper()

    with env.db() as db:
        for uid, code in ((driver_a["id"], code_a), (driver_b["id"], code_b)):
            db.execute(
                "INSERT INTO driver_profiles(user_id,unique_driver_id,license_number) VALUES(%s,%s,'TEST-LIC')",
                (uid, code),
            )
            db.execute(
                "INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
                "VALUES(%s,'driver',20000,0,10000,true)",
                (uid,),
            )
        for uid in (owner_a["id"], owner_b["id"]):
            db.execute(
                "INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
                "VALUES(%s,'transporter',25000,0,0,true)",
                (uid,),
            )

        truck_a1 = db.execute(
            "INSERT INTO vehicles(owner_user_id,truck_number,truck_model,chassis_number,truck_type,capacity_tons,main_use,status) "
            "VALUES(%s,%s,'Hino 500',%s,'Cargo',10,'Cargo','active') RETURNING id",
            (owner_a["id"], f"LEA-{uuid4().hex[:6]}", uuid4().hex),
        ).fetchone()["id"]
        truck_a2 = db.execute(
            "INSERT INTO vehicles(owner_user_id,truck_number,truck_model,chassis_number,truck_type,capacity_tons,main_use,status) "
            "VALUES(%s,%s,'Isuzu FVR',%s,'Cargo',12,'Cargo','active') RETURNING id",
            (owner_a["id"], f"LHR-{uuid4().hex[:6]}", uuid4().hex),
        ).fetchone()["id"]
        truck_b = db.execute(
            "INSERT INTO vehicles(owner_user_id,truck_number,truck_model,chassis_number,truck_type,capacity_tons,main_use,status) "
            "VALUES(%s,%s,'Bedford',%s,'Cargo',8,'Cargo','active') RETURNING id",
            (owner_b["id"], f"KHI-{uuid4().hex[:6]}", uuid4().hex),
        ).fetchone()["id"]

        def _make_trip(owner_id, truck_id):
            sid = db.execute(
                "INSERT INTO shipments(client_user_id,pickup_city,dropoff_city,pickup_date,pickup_time,goods_type,goods_weight_tons,seeker_kind_snapshot,status) "
                "VALUES(%s,'Lahore','Karachi',CURRENT_DATE,'09:00','Steel',5,'business','ready_to_start') RETURNING id",
                (customer["id"],),
            ).fetchone()["id"]
            bid_id = db.execute(
                "INSERT INTO shipment_bids(order_id,transporter_user_id,truck_id,bid_price,status) VALUES(%s,%s,%s,50000,'accepted') RETURNING id",
                (sid, owner_id, truck_id),
            ).fetchone()["id"]
            tid = db.execute(
                "INSERT INTO shipment_trips(order_id,accepted_bid_id,transporter_user_id,truck_id,status) VALUES(%s,%s,%s,%s,'ready_to_start') RETURNING id",
                (sid, bid_id, owner_id, truck_id),
            ).fetchone()["id"]
            return tid

        trip_a1 = _make_trip(owner_a["id"], truck_a1)
        trip_a2 = _make_trip(owner_a["id"], truck_a2)
        trip_b = _make_trip(owner_b["id"], truck_b)

    owner_a_client, _ = env.login(owner_a)
    owner_b_client, _ = env.login(owner_b)
    driver_a_client, _ = env.login(driver_a)
    driver_b_client, _ = env.login(driver_b)
    customer_client, _ = env.login(customer)

    def _assign(owner_client, drv_client, code, truck_id, trip_id):
        res = owner_client.post(
            "/api/transporter/dispatch-driver",
            headers=env.headers,
            json={"unique_driver_id": code, "truck_id": truck_id, "offer_amount": "100.00", "trip_id": trip_id},
        )
        assert res.status_code == 200, res.json
        aid = res.json["assignment_id"]
        acc = drv_client.post(
            f"/api/driver/trips/{aid}/respond",
            headers=env.headers,
            json={"action": "accept"},
        )
        assert acc.status_code == 200, acc.json
        return aid

    asgn_a1 = _assign(owner_a_client, driver_a_client, code_a, truck_a1, trip_a1)
    # Complete trip_a1 so DB trigger releases driver_a for assignment to a second vehicle (truck_a2).
    with env.db() as db:
        db.execute("UPDATE shipment_trips SET status = 'completed' WHERE id = %s", (trip_a1,))
    asgn_a2 = _assign(owner_a_client, driver_a_client, code_a, truck_a2, trip_a2)
    asgn_b = _assign(owner_b_client, driver_b_client, code_b, truck_b, trip_b)

    return {
        "owner_a": owner_a,
        "owner_b": owner_b,
        "driver_a": driver_a,
        "driver_b": driver_b,
        "customer": customer,
        "owner_a_client": owner_a_client,
        "owner_b_client": owner_b_client,
        "driver_a_client": driver_a_client,
        "driver_b_client": driver_b_client,
        "customer_client": customer_client,
        "truck_a1": truck_a1,
        "truck_a2": truck_a2,
        "truck_b": truck_b,
        "trip_a1": trip_a1,
        "trip_a2": trip_a2,
        "trip_b": trip_b,
        "asgn_a1": asgn_a1,
        "asgn_a2": asgn_a2,
        "asgn_b": asgn_b,
    }


def _wallet_snapshot(db, user_id):
    row = db.execute("SELECT balance, locked_balance FROM wallets WHERE user_id = %s", (user_id,)).fetchone()
    return (Decimal(str(row["balance"])), Decimal(str(row["locked_balance"]))) if row else None


def test_driver_fuel_logs_ownership_vehicle_filter_bounds_and_zero_financial_side_effects(remediation_env):
    env = remediation_env
    s = _setup_driver_and_fleet(env)
    drv_a = s["driver_a_client"]

    trips_res = drv_a.get("/api/driver/trips-for-fuel")
    assert trips_res.status_code == 200
    assert "registered_pumps" not in trips_res.json
    returned_trip_ids = {row["trip_id"] for row in trips_res.json["trips"]}
    assert returned_trip_ids == {s["trip_a1"], s["trip_a2"]}

    with env.db() as db:
        before_drv_wallet = _wallet_snapshot(db, s["driver_a"]["id"])
        before_owner_wallet = _wallet_snapshot(db, s["owner_a"]["id"])
        before_tx_count = db.execute("SELECT count(*) AS n FROM wallet_transactions").fetchone()["n"]

    # Create logs across two owned assignments/vehicles for driver_a
    r1 = drv_a.post(
        "/api/driver/fuel-logs",
        headers=env.headers,
        json={
            "assignment_id": s["asgn_a1"],
            "pump_name": "PSO Motorway",
            "city": "Lahore",
            "fuel_type": "diesel",
            "liters": "100",
            "price_per_liter": "280",
            "payment_mode": "cash",
            "odometer_km": "10500",
            "trip_distance_km": "450",
            "fuel_date": "2026-11-10",
        },
    )
    assert r1.status_code == 200, r1.json
    assert r1.json["fuel_average_km_per_liter"] == 4.5

    r2 = drv_a.post(
        "/api/driver/fuel-logs",
        headers=env.headers,
        json={
            "assignment_id": s["asgn_a2"],
            "pump_name": "Shell Korangi",
            "city": "Karachi",
            "fuel_type": "diesel",
            "liters": "50",
            "price_per_liter": "300",
            "payment_mode": "company_card",
            "fuel_date": "2026-11-11",
        },
    )
    assert r2.status_code == 200, r2.json

    # Driver fuel logs never mutate wallets, locked funds, or financial transactions
    with env.db() as db:
        assert _wallet_snapshot(db, s["driver_a"]["id"]) == before_drv_wallet
        assert _wallet_snapshot(db, s["owner_a"]["id"]) == before_owner_wallet
        assert db.execute("SELECT count(*) AS n FROM wallet_transactions").fetchone()["n"] == before_tx_count

    # Rejects client-supplied mismatched truck_id / trip_id (IDOR/BOLA protection)
    forged_truck = drv_a.post(
        "/api/driver/fuel-logs",
        headers=env.headers,
        json={
            "assignment_id": s["asgn_a1"],
            "truck_id": s["truck_b"],
            "pump_name": "Forged Truck",
            "city": "Lahore",
            "fuel_type": "diesel",
            "liters": "10",
            "price_per_liter": "280",
        },
    )
    assert forged_truck.status_code == 403

    forged_trip = drv_a.post(
        "/api/driver/fuel-logs",
        headers=env.headers,
        json={
            "assignment_id": s["asgn_a1"],
            "trip_id": s["trip_b"],
            "pump_name": "Forged Trip",
            "city": "Lahore",
            "fuel_type": "diesel",
            "liters": "10",
            "price_per_liter": "280",
        },
    )
    assert forged_trip.status_code == 403

    # Rejects another driver's assignment_id
    other_asgn = drv_a.post(
        "/api/driver/fuel-logs",
        headers=env.headers,
        json={
            "assignment_id": s["asgn_b"],
            "pump_name": "Other Driver",
            "city": "Karachi",
            "fuel_type": "diesel",
            "liters": "10",
            "price_per_liter": "280",
        },
    )
    assert other_asgn.status_code == 404

    # Rejects invalid numeric bounds, NaN, bad enum values, invalid dates, and non-driver role
    for bad_payload in (
        {"pump_name": "Bad", "city": "LHR", "fuel_type": "diesel", "liters": "NaN", "price_per_liter": "280"},
        {"pump_name": "Bad", "city": "LHR", "fuel_type": "diesel", "liters": "-5", "price_per_liter": "280"},
        {"pump_name": "Bad", "city": "LHR", "fuel_type": "jetfuel", "liters": "10", "price_per_liter": "280"},
        {"pump_name": "Bad", "city": "LHR", "fuel_type": "diesel", "liters": "10", "price_per_liter": "280", "payment_mode": "fuel_credit"},
        {"pump_name": "Bad", "city": "LHR", "fuel_type": "diesel", "liters": "10", "price_per_liter": "280", "odometer_km": "-1"},
        {"pump_name": "Bad", "city": "LHR", "fuel_type": "diesel", "liters": "10", "price_per_liter": "280", "fuel_date": "11-10-2026"},
    ):
        assert drv_a.post("/api/driver/fuel-logs", headers=env.headers, json=bad_payload).status_code == 400

    assert s["owner_a_client"].post(
        "/api/driver/fuel-logs",
        headers=env.headers,
        json={"pump_name": "Owner", "city": "LHR", "fuel_type": "diesel", "liters": "10", "price_per_liter": "280"},
    ).status_code == 403

    # Driver cannot edit or delete logs
    assert drv_a.put("/api/driver/fuel-logs", headers=env.headers, json={}).status_code == 405
    assert drv_a.delete("/api/driver/fuel-logs", headers=env.headers).status_code == 405

    # Full history + vehicle-wise filtering
    all_logs = drv_a.get("/api/driver/fuel-logs")
    assert all_logs.status_code == 200
    assert len(all_logs.json["logs"]) == 2
    assert {v["truck_id"] for v in all_logs.json["vehicles"]} == {s["truck_a1"], s["truck_a2"]}
    assert all(log.get("truck_model") in {"Hino 500", "Isuzu FVR"} for log in all_logs.json["logs"])

    filtered = drv_a.get(f"/api/driver/fuel-logs?truck_id={s['truck_a1']}")
    assert filtered.status_code == 200
    assert len(filtered.json["logs"]) == 1
    assert filtered.json["logs"][0]["truck_id"] == s["truck_a1"]
    assert filtered.json["stats"]["total_liters"] == 100.0
    assert filtered.json["stats"]["total_fuel_spent"] == 28000.0
    assert {v["truck_id"] for v in filtered.json["vehicles"]} == {s["truck_a1"], s["truck_a2"]}

    # Cross-driver/unrelated vehicle filter exposes nothing and invalid truck_id rejects with 400
    other_filter = drv_a.get(f"/api/driver/fuel-logs?truck_id={s['truck_b']}")
    assert other_filter.status_code == 200
    assert other_filter.json["logs"] == []
    assert drv_a.get("/api/driver/fuel-logs?truck_id=abc").status_code == 400
    assert drv_a.get("/api/driver/fuel-logs?truck_id=0").status_code == 400


def test_transporter_read_only_fuel_history_ownership_and_no_pii_or_mutations(remediation_env):
    env = remediation_env
    s = _setup_driver_and_fleet(env)

    # Log one entry on truck_a1 and one on truck_b
    assert s["driver_a_client"].post(
        "/api/driver/fuel-logs",
        headers=env.headers,
        json={"assignment_id": s["asgn_a1"], "pump_name": "PSO North", "city": "Lahore", "fuel_type": "diesel", "liters": "60", "price_per_liter": "285"},
    ).status_code == 200
    assert s["driver_b_client"].post(
        "/api/driver/fuel-logs",
        headers=env.headers,
        json={"assignment_id": s["asgn_b"], "pump_name": "Attock South", "city": "Multan", "fuel_type": "diesel", "liters": "40", "price_per_liter": "290"},
    ).status_code == 200

    # Authorized transporter gets owned truck logs + summary stats without sensitive driver PII
    owned = s["owner_a_client"].get(f"/api/trucks/{s['truck_a1']}/fuel-logs")
    assert owned.status_code == 200, owned.json
    assert owned.json["success"] is True
    assert len(owned.json["logs"]) == 1
    row = owned.json["logs"][0]
    assert row["pump_name"] == "PSO North"
    assert "driver_name" in row
    for forbidden_key in ("phone", "email", "cnic", "driver_phone", "driver_cnic"):
        assert forbidden_key not in row
    assert owned.json["stats"]["total_refuels"] == 1
    assert owned.json["stats"]["total_liters"] == 60.0
    assert owned.json["stats"]["total_fuel_spent"] == 17100.0

    # Cross-transporter IDOR/BOLA blocked with 403
    assert s["owner_b_client"].get(f"/api/trucks/{s['truck_a1']}/fuel-logs").status_code == 403
    assert s["owner_a_client"].get(f"/api/trucks/{s['truck_b']}/fuel-logs").status_code == 403

    # Non-transporter roles blocked with 403
    assert s["driver_a_client"].get(f"/api/trucks/{s['truck_a1']}/fuel-logs").status_code == 403
    assert s["customer_client"].get(f"/api/trucks/{s['truck_a1']}/fuel-logs").status_code == 403

    # Nonexistent truck returns 404
    assert s["owner_a_client"].get("/api/trucks/999999/fuel-logs").status_code == 404

    # Strict read-only: write verbs return 405, and dead /fuel route returns 404
    for method in ("post", "put", "patch", "delete"):
        resp = getattr(s["owner_a_client"], method)(f"/api/trucks/{s['truck_a1']}/fuel-logs", headers=env.headers, json={})
        assert resp.status_code == 405
    assert s["owner_a_client"].get(f"/api/trucks/{s['truck_a1']}/fuel").status_code == 404


def test_v1_settlement_and_financial_terms_exclude_fuel_credit_recovery(remediation_env):
    env = remediation_env
    terms = approved_booking_financial_terms({})
    assert terms["rules_version"]
    assert "fuel" not in str(terms).lower() or "50" in terms["tranche_split"]

    with env.db() as db:
        seeded = seed_ready_order(db, bid=Decimal("10000"), company_fee=Decimal("2000"))
        db.execute(
            "INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
            "VALUES(%s,'transporter',0,0,0,true)",
            (seeded["transporter"]["id"],),
        )
        released = release_one_time_payment(db, seeded["payment_id"])
        assert "fuel_credit_recovered" not in released
        assert Decimal(str(released["payout_amount"])) == Decimal("8000")
        assert Decimal(str(released["transporter_entitlement"])) == Decimal("8000")
        assert Decimal(str(released["wallet_credit_amount"])) == Decimal("8000")
        assert Decimal(str(released["company_fee"])) == Decimal("2000")
        bal = db.execute("SELECT balance FROM wallets WHERE user_id = %s", (seeded["transporter"]["id"],)).fetchone()["balance"]
        assert Decimal(str(bal)) == Decimal("8000")


def test_v2_fuel_routes_roles_scheduler_step_up_schema_and_archive_isolation(remediation_env, monkeypatch):
    env = remediation_env
    client = env.app.test_client()

    # Deferred V2 routes are not registered in active Flask V1 app
    assert client.get("/api/fuelstation/dashboard").status_code == 404
    assert client.post("/api/fuelstation/pumps", json={}).status_code == 404
    assert client.get("/api/fuel/vouchers").status_code == 404

    # Fuel station manager role is retired from active V1 signup & terms
    assert client.get("/auth/signup-terms?role=fuel_station_manager").status_code == 400

    # Scheduler and MPIN step-up policies exclude deferred V2 jobs/actions
    assert not hasattr(scheduler_mod, "run_expire_fuel_vouchers")
    assert scheduler_mod._scheduler is None
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", "true")
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    sched = scheduler_mod.start_scheduler(force=True)
    try:
        assert {job.id for job in sched.get_jobs()} == {"process_overdue_confirmations_interval"}
    finally:
        if sched is not None:
            sched.shutdown(wait=False)
        scheduler_mod._scheduler = None
    assert "fuel.voucher.authorize" not in step_up_service.ACTION_POLICIES

    # Excluded V2 tables and columns are absent from cleaned local V1 schema
    with env.db() as db:
        for table in (
            "fuel_station_profiles",
            "fuel_station_pumps",
            "fuel_station_dispenses",
            "fuel_platform_treasury",
            "fuel_credit_accounts",
            "fuel_vouchers",
            "fuel_credit_events",
        ):
            assert db.execute("SELECT to_regclass(%s) AS rel", (f"public.{table}",)).fetchone()["rel"] is None
        cols = {
            r["column_name"]
            for r in db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='freight_settlements'"
            ).fetchall()
        }
        assert "fuel_credit_recovered" not in cols
        with pytest.raises(psycopg2.errors.InvalidTextRepresentation):
            db.execute(
                "INSERT INTO users(email,cnic,role,legacy_role) VALUES('badfuel@example.invalid','3520299999999','fuel_station_manager','fuel_station_manager')"
            )

    # V2 files are preserved in Future/
    for archive_path in (
        REPO_ROOT / "Future/backend/shared/fuel_credit.py",
        REPO_ROOT / "Future/supabase/fuel-v2-reference.sql",
        REPO_ROOT / "Future/backend/tests/test_fuel_station_dispense_deferred.py",
        REPO_ROOT / "Future/README.md",
    ):
        assert archive_path.exists() and archive_path.stat().st_size > 0
