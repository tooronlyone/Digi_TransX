# Deferred V2 Fuel Station dispense hardening tests (archived from V1 active suite).

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
import pytest

from tests.remediation_harness import remediation_database_url, remediation_env


def _fuel_pump(env,stock="10"):
    user=env.user("fuel_station_manager")
    client,_=env.login(user)
    response=client.post("/api/fuelstation/pumps",headers=env.headers,json={
        "pump_number":"Test pump","fuel_type":"diesel","price_per_liter":"100.00",
        "tank_capacity_liters":"100.00","current_stock_liters":stock,
    })
    assert response.status_code==200,response.json
    return user,client,response.json["pump_id"]


def test_fuel_sale_cannot_oversell_or_override_stored_rate(remediation_env):
    env=remediation_env
    user,client,pump_id=_fuel_pump(env)
    payload={"pump_id":pump_id,"vehicle_plate":"TEST-123","liters":"6","price_per_liter":"0.01"}
    response=client.post("/api/fuelstation/dispense",headers=env.headers,json=payload)
    assert response.status_code==200,response.json
    assert response.json["receipt"]["total_pkr"]==600
    assert client.post("/api/fuelstation/dispense",headers=env.headers,json=payload).status_code==409
    with env.db() as db:
        assert db.execute("SELECT current_stock_liters FROM fuel_station_pumps WHERE id=%s",(pump_id,)).fetchone()["current_stock_liters"]==4
        assert db.execute("SELECT count(*) AS n FROM fuel_station_dispenses WHERE user_id=%s",(user["id"],)).fetchone()["n"]==1


def test_concurrent_fuel_sales_commit_only_one_available_stock_claim(remediation_env):
    env=remediation_env
    user,_,pump_id=_fuel_pump(env)
    clients=[env.login(user)[0] for _ in range(2)]
    barrier=Barrier(2)
    def sale(client):
        barrier.wait(timeout=10)
        return client.post("/api/fuelstation/dispense",headers=env.headers,
                           json={"pump_id":pump_id,"vehicle_plate":"RACE-123","liters":"7"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(sale,clients))==[200,409]


@pytest.mark.parametrize("value",["NaN","Infinity","-1","0.001"])
def test_fuel_rejects_nonfinite_negative_and_unsupported_quantity_scale(remediation_env,value):
    env=remediation_env
    _,client,pump_id=_fuel_pump(env)
    assert client.post("/api/fuelstation/dispense",headers=env.headers,
                       json={"pump_id":pump_id,"vehicle_plate":"INVALID-1","liters":value}).status_code==400

