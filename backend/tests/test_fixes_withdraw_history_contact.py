"""Contact/history/withdrawal regressions with no application-database access."""
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.remediation_harness import remediation_database_url, remediation_env


@pytest.fixture
def client(remediation_env):
    client = remediation_env.app.test_client()
    with client.session_transaction() as state:
        state["csrf_token"] = "remediation-csrf"
    return client


@pytest.fixture
def pending_bid(remediation_env):
    env = remediation_env
    customer = env.user("everyday_user")
    transporter = env.user("logistics_provider")
    outsider = env.user("logistics_provider")
    suffix = uuid4().hex[:12]
    with env.db() as db:
        truck_id = db.execute(
            "INSERT INTO vehicles(owner_user_id,truck_number,truck_type,chassis_number,capacity_tons,main_use,status) "
            "VALUES(%s,%s,'flatbed',%s,20,'general','active') RETURNING id",
            (transporter["id"], f"TEST-{suffix}", f"CHASSIS-{suffix}"),
        ).fetchone()["id"]
        order_id = db.execute(
            "INSERT INTO shipments(client_user_id,status,pickup_city,dropoff_city,pickup_date,pickup_time,"
            "goods_type,goods_weight_tons,goods_volume_cbm,estimated_budget,seeker_kind_snapshot) "
            "VALUES(%s,'open','Lahore','Karachi',%s,'10:00','General',5,10,50000,'everyday') RETURNING id",
            (customer["id"], date.today() + timedelta(days=7)),
        ).fetchone()["id"]
        bid_id = db.execute(
            "INSERT INTO shipment_bids(order_id,transporter_user_id,truck_id,bid_price,status) "
            "VALUES(%s,%s,%s,48000,'pending') RETURNING id",
            (order_id, transporter["id"], truck_id),
        ).fetchone()["id"]
    return SimpleNamespace(env=env, owner=transporter, outsider=outsider,
                           order_id=order_id, bid_id=bid_id,
                           url=f"/api/orders/{order_id}/bids/{bid_id}/withdraw")


def test_contact_submit_validation(client, remediation_env):
    cases = [
        ({}, "Full name is required"),
        ({"name": "Ali"}, "Valid email address is required"),
        ({"name": "Ali", "email": "ali@example.test"}, "Subject is required"),
        ({"name": "Ali", "email": "ali@example.test", "subject": "Support"}, "Message cannot be empty"),
    ]
    for payload, expected in cases:
        result = client.post("/api/contact", json=payload, headers=remediation_env.headers)
        assert result.status_code == 400, result.json
        assert expected in result.json["message"]


def test_contact_submit_success(client, remediation_env):
    email = f"contact-{uuid4().hex}@example.test"
    payload = {"name": "Tariq Mahmood", "email": email, "phone": "03001234567",
               "subject": "Payment Problem", "message": "Payment was not credited to my wallet."}
    result = client.post("/api/contact", json=payload, headers=remediation_env.headers)
    assert result.status_code == 200, result.json
    assert result.json["success"] is True
    assert "sent successfully" in result.json["message"]
    with remediation_env.db() as db:
        message = db.execute("SELECT * FROM contact_messages WHERE id=%s", (result.json["ticket_id"],)).fetchone()
    assert message is not None
    assert message["email"] == email
    assert message["name"] == "Tariq Mahmood"
    assert message["subject"] == "Payment Problem"
    assert message["status"] == "new"


def test_account_history_endpoint_unauthorized(client):
    assert client.get("/api/history/account").status_code == 401


def test_withdraw_bid_unauthorized(client, pending_bid):
    assert client.post(pending_bid.url, headers=pending_bid.env.headers).status_code == 401


def test_withdraw_bid_logic(pending_bid):
    fixture = pending_bid
    outsider_client, _ = fixture.env.login(fixture.outsider)
    denied = outsider_client.post(fixture.url, headers=fixture.env.headers)
    assert denied.status_code == 403, denied.json
    owner_client, _ = fixture.env.login(fixture.owner)
    accepted = owner_client.post(fixture.url, headers=fixture.env.headers)
    assert accepted.status_code == 200, accepted.json
    with fixture.env.db() as db:
        row = db.execute("SELECT status FROM shipment_bids WHERE id=%s", (fixture.bid_id,)).fetchone()
        assert row["status"] == "withdrawn"
    repeat = owner_client.post(fixture.url, headers=fixture.env.headers)
    assert repeat.status_code == 400, repeat.json
