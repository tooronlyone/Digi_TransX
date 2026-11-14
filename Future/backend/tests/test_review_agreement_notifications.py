"""Notification transactions and agreement accrual on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

from flask import request
import pytest

from agreements import helpers, routes
from shared.notifications import notify, notify_best_effort
from tests.remediation_harness import remediation_database_url, remediation_env


def seed_agreement(env, *, trips=1, payment_status="pending"):
    customer = env.user()
    owner = env.user("logistics_provider")
    with env.db() as db:
        truck_id = db.execute(
            "INSERT INTO vehicles(owner_user_id,truck_number,chassis_number,truck_type,capacity_tons,main_use,status) "
            "VALUES(%s,%s,%s,'Cargo',10,'Cargo','active') RETURNING id",
            (owner["id"], uuid4().hex, uuid4().hex),
        ).fetchone()["id"]
        post_id = db.execute(
            "INSERT INTO agreement_posts(client_user_id,title,cargo_type,service_area,status) "
            "VALUES(%s,'Review contract','Goods','Test area','active') RETURNING id", (customer["id"],),
        ).fetchone()["id"]
        agreement_id = db.execute(
            "INSERT INTO agreements(post_id,client_user_id,duration_months,cargo_type,service_area,start_date,end_date,"
            "company_share_percent_snapshot,transporter_share_percent_snapshot) "
            "VALUES(%s,%s,1,'Goods','Test area',CURRENT_DATE,CURRENT_DATE+30,20,80) RETURNING id",
            (post_id, customer["id"]),
        ).fetchone()["id"]
        agreement_truck_id = db.execute(
            "INSERT INTO agreement_trucks(agreement_id,truck_id,transporter_user_id,per_km_rate,minimum_monthly_guarantee) "
            "VALUES(%s,%s,%s,10,75000) RETURNING id", (agreement_id, truck_id, owner["id"]),
        ).fetchone()["id"]
        payment_id = db.execute(
            "INSERT INTO agreement_monthly_payments(agreement_id,agreement_truck_id,transporter_user_id,client_user_id,"
            "month_year,minimum_guarantee,final_amount,company_fee,transporter_amount,status,payment_due_date) "
            "VALUES(%s,%s,%s,%s,%s,75000,75000,15000,60000,%s,CURRENT_DATE) RETURNING id",
            (agreement_id, agreement_truck_id, owner["id"], customer["id"], date.today().strftime("%Y-%m"), payment_status),
        ).fetchone()["id"]
        trip_ids = []
        for _ in range(trips):
            trip_ids.append(db.execute(
                "INSERT INTO agreement_trips(agreement_id,agreement_truck_id,truck_id,transporter_user_id,"
                "pickup_description,trip_date,gps_start_lat,gps_start_lng,started_at,status) "
                "VALUES(%s,%s,%s,%s,'Test pickup',CURRENT_DATE,31,74,'2026-10-01T10:00:00+05:00','in_progress') RETURNING id",
                (agreement_id, agreement_truck_id, truck_id, owner["id"]),
            ).fetchone()["id"])
        db.execute(
            "INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
            "VALUES(%s,'client',50000,0,0,true),(%s,'transporter',30000,30000,30000,true)",
            (customer["id"], owner["id"]),
        )
    return SimpleNamespace(customer=customer, owner=owner, truck_id=truck_id, agreement_id=agreement_id,
                           agreement_truck_id=agreement_truck_id, payment_id=payment_id, trip_ids=trip_ids)


def test_generic_notifications_persist_and_stay_recipient_scoped(remediation_env):
    env = remediation_env
    recipient, outsider = env.user(), env.user()
    with env.db() as db:
        assert notify(db, None, None, recipient["id"], "withdrawal_approved", "Approved")
        notification_id = db.execute("SELECT id FROM shipment_notifications WHERE user_id=%s", (recipient["id"],)).fetchone()["id"]
    outsider_client, _ = env.login(outsider)
    assert outsider_client.get("/api/notifications").json["notifications"] == []
    outsider_client.post(f"/api/notifications/{notification_id}/read", headers=env.headers)
    recipient_client, _ = env.login(recipient)
    response = recipient_client.get("/api/notifications")
    assert response.status_code == 200
    assert response.json["unread_count"] == 1
    assert response.json["notifications"][0]["order_id"] is None
    assert recipient_client.post(f"/api/notifications/{notification_id}/read", headers=env.headers).status_code == 200
    assert recipient_client.get("/api/notifications").json["unread_count"] == 0


def test_failed_optional_notice_preserves_prior_writes_and_usable_transaction(remediation_env):
    env = remediation_env
    user = env.user()
    with env.db() as db:
        db.execute("UPDATE users SET full_name='Saved before notification' WHERE id=%s", (user["id"],))
        # Invalid shipment FK causes a real PostgreSQL error inside the savepoint.
        assert notify_best_effort(db, -1, None, user["id"], "withdrawal_approved", "Failure probe") is False
        assert db.execute("SELECT 1 AS usable").fetchone()["usable"] == 1
    with env.db() as db:
        assert db.execute("SELECT full_name FROM users WHERE id=%s", (user["id"],)).fetchone()["full_name"] == "Saved before notification"


def test_account_notification_migration_is_repeatable(remediation_env):
    migration = (Path(__file__).resolve().parents[2] / "supabase/migrations/20261029010000_account_notifications.sql").read_text()
    with remediation_env.db() as db:
        # An isolated copy represents the old column contract, without changing
        # any other test's notifications in the disposable canonical database.
        schema = "migration_" + uuid4().hex
        db.execute(f'CREATE SCHEMA "{schema}"')
        try:
            db.execute(f'CREATE TABLE "{schema}".shipment_notifications (order_id bigint NOT NULL)')
            sql = migration.replace("public.shipment_notifications", f'"{schema}".shipment_notifications')
            db.execute(sql)
            db.execute(sql)
            db.execute(f'INSERT INTO "{schema}".shipment_notifications VALUES (NULL)')
        finally:
            db.execute(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.mark.parametrize("operation,event", [("payment", "agreement_payment_failed"), ("penalty", "agreement_late_penalty")])
def test_agreement_sweeps_commit_financial_state_and_notice(remediation_env, operation, event):
    env = remediation_env
    graph = seed_agreement(env, payment_status="pending" if operation == "payment" else "failed")
    with env.app.app_context(), env.db() as db:
        if operation == "payment":
            helpers.run_process_payments(db)
        else:
            helpers.run_apply_penalties(db)
    with env.db() as db:
        payment = db.execute("SELECT * FROM agreement_monthly_payments WHERE id=%s", (graph.payment_id,)).fetchone()
        assert payment["status"] == "failed"
        assert payment["penalty_amount"] == (5000 if operation == "penalty" else 0)
        balance = db.execute("SELECT balance FROM wallets WHERE user_id=%s", (graph.customer["id"],)).fetchone()["balance"]
        assert balance == (45000 if operation == "penalty" else 50000)
        assert db.execute("SELECT count(*) AS n FROM shipment_notifications WHERE user_id=%s AND notification_type=%s",
                          (graph.customer["id"], event)).fetchone()["n"] == 1


def end_trip(env, graph, trip_id):
    with env.app.test_request_context("/review/end-trip", method="PUT", json={"gps_end_lat": 32, "gps_end_lng": 74}):
        request.current_user = {"id": graph.owner["id"], "role": "logistics_provider"}
        return routes.end_trip.__wrapped__(graph.agreement_id, trip_id)


@pytest.mark.parametrize("same_trip", [True, False])
def test_concurrent_completions_accrue_each_trip_once(remediation_env, monkeypatch, same_trip):
    env = remediation_env
    graph = seed_agreement(env, trips=1 if same_trip else 2)
    monkeypatch.setattr(routes, "open_db", env.db)
    monkeypatch.setattr(routes, "csrf_error", lambda: None)
    monkeypatch.setattr(routes, "haversine_km", lambda *args: 12.5)
    monkeypatch.setattr(routes, "insert_system_note_for_agreement", lambda *args: None)
    ids = [graph.trip_ids[0], graph.trip_ids[-1]]
    with env.db() as blocker, ThreadPoolExecutor(max_workers=2) as workers:
        if same_trip:
            blocker.execute("SELECT id FROM agreement_trips WHERE id=%s FOR UPDATE", (ids[0],))
        else:
            blocker.execute("SELECT id FROM agreement_monthly_payments WHERE id=%s FOR UPDATE", (graph.payment_id,))
        futures = [workers.submit(end_trip, env, graph, trip_id) for trip_id in ids]
        try:
            deadline = monotonic() + 10
            while monotonic() < deadline:
                with env.db() as observer:
                    waiting = observer.execute(
                        "SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'"
                    ).fetchone()["n"]
                if waiting >= 2:
                    break
                sleep(0.01)
            assert waiting >= 2, "Both completions must overlap at the locked source row"
        finally:
            blocker.commit()
        responses = [future.result(timeout=10) for future in futures]
    assert sorted(response.status_code for response in responses) == ([200, 400] if same_trip else [200, 200])
    with env.db() as db:
        assert db.execute("SELECT total_km FROM agreement_monthly_payments WHERE id=%s", (graph.payment_id,)).fetchone()["total_km"] == (12.5 if same_trip else 25)


def test_tracking_interval_preserves_start_instant(remediation_env, monkeypatch):
    env = remediation_env
    graph = seed_agreement(env)
    with env.db() as db:
        db.execute("UPDATE vehicles SET traccar_device_id='17' WHERE id=%s", (graph.truck_id,))
    calls = []
    monkeypatch.setattr(routes, "open_db", env.db)
    monkeypatch.setattr(routes, "csrf_error", lambda: None)
    monkeypatch.setattr(routes, "insert_system_note_for_agreement", lambda *args: None)
    monkeypatch.setattr(routes, "get_positions_between", lambda *args: calls.append(args) or [])
    assert end_trip(env, graph, graph.trip_ids[0]).status_code == 200
    assert calls[0][1] == "2026-10-01T05:00:00Z"
