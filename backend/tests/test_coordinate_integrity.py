"""Focused coordinate integrity tests for one-time orders and truck matching."""

from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal

import pytest
from flask import Flask
from psycopg2 import errors

from shared.coordinates import (
    CoordinateValidationError,
    parse_optional_coordinate_pair,
)


EVERYDAY = {"id": 7701, "role": "everyday_user"}
TRANSPORTER = {"id": 7702, "role": "logistics_provider"}


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (32.1877, 74.1945, (32.1877, 74.1945)),
        ("32.18770001", "74.19450001", (32.18770001, 74.19450001)),
        (-90, -180, (-90.0, -180.0)),
        (90, 180, (90.0, 180.0)),
        (None, None, (None, None)),
        ("", "  ", (None, None)),
    ],
)
def test_shared_coordinate_parser_accepts_valid_optional_pairs(
    latitude, longitude, expected
):
    actual = parse_optional_coordinate_pair(
        {"lat": latitude, "lng": longitude}, "lat", "lng", label="Test"
    )
    assert actual == expected


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (90.0000001, 0),
        (-90.0000001, 0),
        (0, 180.0000001),
        (0, -180.0000001),
        (32, None),
        (None, 74),
        (32, ""),
        ("", 74),
        (True, 74),
        (32, False),
        ("NaN", 74),
        (32, float("nan")),
        ("Infinity", 74),
        ("-Infinity", 74),
        (32, float("inf")),
        (32, float("-inf")),
        ("not-a-number", 74),
        ({"value": 32}, 74),
        (32, [74]),
    ],
)
def test_shared_coordinate_parser_rejects_invalid_pairs(latitude, longitude):
    with pytest.raises(CoordinateValidationError):
        parse_optional_coordinate_pair(
            {"lat": latitude, "lng": longitude}, "lat", "lng", label="Test"
        )


def _order_payload(**overrides):
    payload = {
        "pickup_location": "Gujranwala, Punjab, Pakistan",
        "pickup_lat": 32.1877,
        "pickup_lng": 74.1945,
        "dropoff_location": "Lahore, Punjab, Pakistan",
        "dropoff_lat": 31.5204,
        "dropoff_lng": 74.3587,
        "pickup_date": (date.today() + timedelta(days=2)).isoformat(),
        "pickup_time": "12:00",
        "goods_type": "General cargo",
        "goods_weight_tons": 2.5,
    }
    payload.update(overrides)
    return payload


def _post_order(client, **overrides):
    client.login(EVERYDAY)
    return client.post(
        "/api/orders",
        json=_order_payload(**overrides),
        headers={"X-CSRF-Token": "test-csrf-token"},
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {
            "pickup_lat": "-90",
            "pickup_lng": "-180",
            "dropoff_lat": "90",
            "dropoff_lng": "180",
        },
        {
            "pickup_lat": None,
            "pickup_lng": None,
            "dropoff_lat": None,
            "dropoff_lng": None,
        },
        {
            "pickup_lat": "",
            "pickup_lng": "",
            "dropoff_lat": "",
            "dropoff_lng": "",
        },
    ],
)
def test_order_api_accepts_valid_and_complete_optional_pairs(client, overrides):
    response = _post_order(client, **overrides)
    assert response.status_code == 200, response.get_data(as_text=True)


@pytest.mark.parametrize(
    "overrides",
    [
        {"pickup_lat": 90.000001},
        {"pickup_lat": -90.000001},
        {"pickup_lng": 180.000001},
        {"pickup_lng": -180.000001},
        {"pickup_lat": 32, "pickup_lng": None},
        {"pickup_lat": None, "pickup_lng": 74},
        {"pickup_lat": True},
        {"pickup_lng": False},
        {"pickup_lat": ""},
        {"pickup_lat": "NaN"},
        {"pickup_lat": "Infinity"},
        {"pickup_lat": "-Infinity"},
        {"pickup_lat": {"value": 32}},
        {"pickup_lng": [74]},
        {"pickup_lat": 32.1877, "dropoff_lat": 91},
        {"dropoff_lat": 31.5204, "dropoff_lng": None},
    ],
)
def test_order_api_rejects_invalid_coordinates_without_partial_writes(
    client, overrides
):
    db = client.db
    before = {
        table: db.execute(f"select count(*) c from {table}").fetchone()["c"]
        for table in (
            "shipments",
            "shipment_status_history",
            "shipment_notifications",
        )
    }
    response = _post_order(client, **overrides)
    assert response.status_code == 400, response.get_data(as_text=True)
    after = {
        table: db.execute(f"select count(*) c from {table}").fetchone()["c"]
        for table in before
    }
    assert after == before


def _create_truck_form(**overrides):
    form = {
        "truckNumber": "COORD-CREATE-1",
        "truckCompany": "Test Motors",
        "truckModel": "Model 1",
        "truckType": "Open Body",
        "chassisNumber": "ABCDEFGH123456789",
        "capacity": "5",
        "payload_min_tons": "1",
        "payload_max_tons": "5",
        "mainUse": "General cargo",
        "current_city": "Gujranwala",
        "current_lat": "32.1877",
        "current_lng": "74.1945",
        "service_radius_km": "100",
    }
    form.update(overrides)
    return form


@pytest.mark.parametrize(
    "overrides",
    [
        {"current_lat": "91"},
        {"current_lng": "181"},
        {"current_lat": "NaN"},
        {"current_lng": "Infinity"},
        {"current_lat": "", "current_lng": "74"},
        {"current_lat": "32", "current_lng": ""},
    ],
)
def test_truck_create_rejects_invalid_coordinates_before_insert(client, overrides):
    client.login(TRANSPORTER)
    before = client.db.execute("select count(*) c from vehicles").fetchone()["c"]
    response = client.post(
        "/api/trucks",
        data=_create_truck_form(**overrides),
        headers={"X-CSRF-Token": "test-csrf-token"},
    )
    assert response.status_code == 400, response.get_data(as_text=True)
    after = client.db.execute("select count(*) c from vehicles").fetchone()["c"]
    assert after == before


def test_truck_update_rejects_invalid_coordinates_without_mutation(client):
    client.login(TRANSPORTER)
    truck_id = client.db.execute(
        "insert into vehicles "
        "(owner_user_id,truck_number,truck_company,truck_model,truck_type,"
        "capacity_tons,payload_min_tons,payload_max_tons,current_city,"
        "current_lat,current_lng,service_radius_km,status) "
        "values (%s,'COORD-UP-1','Test Motors','Model 1','Open Body',"
        "5,1,5,'Gujranwala',32.1877,74.1945,100,'active') returning id",
        (TRANSPORTER["id"],),
    ).fetchone()["id"]
    client.db.commit()
    form = {
        "truck_number": "COORD-UP-1",
        "truck_company": "Test Motors",
        "truck_model": "Model 1",
        "truck_type": "Open Body",
        "max_capacity": "5",
        "payload_min_tons": "1",
        "payload_max_tons": "5",
        "chassis_number": "ABCDEFGH123456789",
        "operating_provinces": "Punjab",
        "current_city": "Gujranwala",
        "current_lat": "NaN",
        "current_lng": "74.1945",
        "service_radius_km": "100",
    }
    response = client.put(
        f"/api/trucks/{truck_id}/configuration",
        data=form,
        headers={"X-CSRF-Token": "test-csrf-token"},
    )
    assert response.status_code == 400, response.get_data(as_text=True)
    row = client.db.execute(
        "select current_lat,current_lng from vehicles where id=%s", (truck_id,)
    ).fetchone()
    assert row == {"current_lat": 32.1877, "current_lng": 74.1945}


def test_direct_sql_rejects_invalid_shipment_insert(db):
    with pytest.raises(errors.CheckViolation):
        db.execute(
            "insert into shipments "
            "(client_user_id,pickup_lat,pickup_lng,dropoff_lat,dropoff_lng) "
            "values (1,91,0,0,0)"
        )


def test_direct_sql_rejects_invalid_shipment_update(db):
    order_id = db.execute(
        "insert into shipments "
        "(client_user_id,pickup_lat,pickup_lng,dropoff_lat,dropoff_lng) "
        "values (1,0,0,0,0) returning id"
    ).fetchone()["id"]
    with pytest.raises(errors.CheckViolation):
        db.execute(
            "update shipments set dropoff_lng='Infinity'::double precision "
            "where id=%s",
            (order_id,),
        )


def test_direct_sql_rejects_invalid_vehicle_insert(db):
    with pytest.raises(errors.CheckViolation):
        db.execute(
            "insert into vehicles "
            "(owner_user_id,current_lat,current_lng,service_radius_km) "
            "values (1,'NaN'::double precision,0,100)"
        )


def test_direct_sql_rejects_invalid_vehicle_update(db):
    truck_id = db.execute(
        "insert into vehicles "
        "(owner_user_id,current_lat,current_lng,service_radius_km) "
        "values (1,0,0,100) returning id"
    ).fetchone()["id"]
    with pytest.raises(errors.CheckViolation):
        db.execute(
            "update vehicles set current_lat=0,current_lng='-Infinity'::double precision "
            "where id=%s",
            (truck_id,),
        )


def test_direct_sql_allows_missing_location_truck(db):
    truck_id = db.execute(
        "insert into vehicles "
        "(owner_user_id,current_lat,current_lng,service_radius_km) "
        "values (1,null,null,100) returning id"
    ).fetchone()["id"]
    row = db.execute(
        "select current_lat,current_lng from vehicles where id=%s", (truck_id,)
    ).fetchone()
    assert row == {"current_lat": None, "current_lng": None}


def test_invalid_tracking_event_cannot_update_matching_coordinates(monkeypatch):
    """The analytics track endpoint is not a vehicle-location update surface."""

    import tracking.routes as tracking_routes

    statements = []

    class FakeDb:
        def execute(self, query, params=()):
            statements.append(query)
            return self

        def commit(self):
            return None

    @contextmanager
    def fake_open_db():
        yield FakeDb()

    monkeypatch.setattr(tracking_routes, "open_db", fake_open_db)
    app = Flask(__name__)
    app.register_blueprint(tracking_routes.tracking_blueprint)
    response = app.test_client().post(
        "/api/track", json={"latitude": 999, "longitude": 999}
    )
    assert response.status_code == 200
    assert statements
    assert all("vehicles" not in statement.lower() for statement in statements)


def test_double_precision_boundary_semantics_are_explicit(db):
    result = db.execute(
        "select "
        "('NaN'::double precision between -90 and 90) nan_in_range,"
        "('Infinity'::double precision between -90 and 90) pos_inf_in_range,"
        "('-Infinity'::double precision between -90 and 90) neg_inf_in_range,"
        "('NaN'::double precision = 'NaN'::double precision) nan_equals_nan"
    ).fetchone()
    assert result == {
        "nan_in_range": False,
        "pos_inf_in_range": False,
        "neg_inf_in_range": False,
        "nan_equals_nan": True,
    }


def test_coordinate_decimal_precision_is_preserved():
    latitude = Decimal("32.187700123")
    longitude = Decimal("74.194500987")
    parsed = parse_optional_coordinate_pair(
        {"lat": latitude, "lng": longitude}, "lat", "lng"
    )
    assert parsed == (32.187700123, 74.194500987)
