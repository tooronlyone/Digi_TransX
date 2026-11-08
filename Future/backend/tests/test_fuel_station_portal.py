"""Fuel portal contracts against a disposable loopback database only."""
from types import SimpleNamespace

import pytest

from tests.remediation_harness import remediation_database_url, remediation_env


@pytest.fixture
def station(remediation_env):
    env = remediation_env
    user = env.user("fuel_station_manager")
    client, _ = env.login(user)
    with env.db() as db:
        db.execute(
            "INSERT INTO fuel_station_profiles(user_id,station_name,pumps_count,license_no) "
            "VALUES(%s,%s,%s,%s) ON CONFLICT(user_id) DO UPDATE SET station_name=EXCLUDED.station_name",
            (user["id"], "Isolated Test Station", "1", "TEST-LICENSE"),
        )
    created = client.post("/api/fuelstation/pumps", headers=env.headers, json={
        "pump_number": "TEST-PUMP", "fuel_type": "diesel", "price_per_liter": "282.50",
        "tank_capacity_liters": "500.00", "current_stock_liters": "200.00",
    })
    assert created.status_code == 200, created.json
    return SimpleNamespace(env=env, user=user, client=client, pump_id=created.json["pump_id"])


def _dispense(station):
    return station.client.post("/api/fuelstation/dispense", headers=station.env.headers, json={
        "pump_id": station.pump_id, "vehicle_plate": "TEST-786", "driver_name": "Test Driver",
        "driver_phone": "03009988776", "liters": "50.00", "payment_method": "cash",
        "notes": "Disposable fixture sale",
    })


def test_fuel_station_role_guard(remediation_env):
    env = remediation_env
    client, _ = env.login(env.user("logistics_provider"))
    result = client.get("/api/fuelstation/dashboard")
    assert result.status_code == 403
    assert "Fuel station manager access is required" in result.json["message"]


def test_fuel_station_dashboard_success(station):
    result = station.client.get("/api/fuelstation/dashboard")
    assert result.status_code == 200, result.json
    assert result.json["success"] is True
    assert {"metrics", "pumps", "recent_dispenses"} <= result.json.keys()
    assert any(pump["id"] == station.pump_id for pump in result.json["pumps"])


def test_fuel_station_pumps_list(station):
    result = station.client.get("/api/fuelstation/pumps")
    assert result.status_code == 200, result.json
    assert result.json["success"] is True
    assert [pump["id"] for pump in result.json["pumps"]] == [station.pump_id]
    assert result.json["pumps"][0]["current_stock_liters"] == 200


def test_fuel_station_dispense_validation(station):
    result = station.client.post("/api/fuelstation/dispense", headers=station.env.headers,
                                 json={"pump_id": station.pump_id, "liters": 0})
    assert result.status_code == 400
    assert "Vehicle registration plate is required" in result.json["message"]


def test_fuel_station_dispense_success(station):
    result = _dispense(station)
    assert result.status_code == 200, result.json
    assert result.json["success"] is True
    assert result.json["receipt"]["total_pkr"] == 14125.0
    assert result.json["receipt"]["vehicle_plate"] == "TEST-786"
    with station.env.db() as db:
        pump = db.execute("SELECT current_stock_liters FROM fuel_station_pumps WHERE id=%s AND user_id=%s",
                          (station.pump_id, station.user["id"])).fetchone()
        assert pump["current_stock_liters"] == 150


def test_fuel_station_dispenses_log(station):
    recorded = _dispense(station)
    assert recorded.status_code == 200, recorded.json
    result = station.client.get("/api/fuelstation/dispenses?search=TEST-786")
    assert result.status_code == 200, result.json
    assert result.json["success"] is True
    assert len(result.json["dispenses"]) == 1
    assert result.json["dispenses"][0]["vehicle_plate"] == "TEST-786"


def test_fuel_station_profile(station):
    result = station.client.get("/api/fuelstation/profile")
    assert result.status_code == 200, result.json
    assert result.json["success"] is True
    assert result.json["profile"]["station_name"] == "Isolated Test Station"
    updated = station.client.put("/api/fuelstation/profile", headers=station.env.headers, json={
        "station_name": "Updated Test Station", "license_no": "UPDATED-TEST", "pumps_count": "1",
        "city": "Lahore", "address": "Test fixture address", "phone": "03001234567",
    })
    assert updated.status_code == 200, updated.json
    assert station.client.get("/api/fuelstation/profile").json["profile"]["station_name"] == "Updated Test Station"
