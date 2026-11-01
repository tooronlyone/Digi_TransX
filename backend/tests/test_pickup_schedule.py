from datetime import datetime, timedelta

import pytest
from flask import Flask, request

from orders.pickup_schedule import PICKUP_TIMEZONE, validate_pickup_schedule


NOW = datetime(2026, 10, 27, 23, 0, tzinfo=PICKUP_TIMEZONE)


@pytest.mark.parametrize("minutes", [20, 60, 720, 1440])
def test_pickup_accepts_window_including_midnight_and_exact_boundaries(minutes):
    pickup = NOW + timedelta(minutes=minutes)
    assert validate_pickup_schedule(
        pickup.date().isoformat(), pickup.time().isoformat(), now=NOW
    ) == pickup.date()


@pytest.mark.parametrize("minutes", [-1, 0, 19, 1441, 2880])
def test_pickup_rejects_past_short_notice_and_more_than_24_hours(minutes):
    pickup = NOW + timedelta(minutes=minutes)
    with pytest.raises(ValueError):
        validate_pickup_schedule(
            pickup.date().isoformat(), pickup.time().isoformat(), now=NOW
        )


@pytest.mark.parametrize("date_value,time_value", [
    (None, "12:00"), ("2026-02-30", "12:00"),
    ("2026-10-28", "25:00"), ("2026-10-28", "12:00+03:00"),
])
def test_pickup_rejects_invalid_dates_times_and_timezone_overrides(date_value, time_value):
    with pytest.raises(ValueError):
        validate_pickup_schedule(date_value, time_value, now=NOW)


def test_order_endpoint_rejects_future_pickup_before_writing(monkeypatch):
    import orders.routes as routes

    monkeypatch.setattr(routes, "require_client_role", lambda user: None)
    monkeypatch.setattr(routes, "csrf_error", lambda: None)
    monkeypatch.setattr(routes, "validate_order_creation", lambda data: None)

    def unexpected_database_access():
        pytest.fail("An invalid pickup must be rejected before database writes")

    monkeypatch.setattr(routes, "open_db", unexpected_database_access)
    future = datetime.now(PICKUP_TIMEZONE) + timedelta(hours=25)
    app = Flask(__name__)
    with app.test_request_context("/api/orders", method="POST", json={
        "pickup_date": future.date().isoformat(),
        "pickup_time": future.strftime("%H:%M"),
    }):
        request.current_user = {"id": 1, "role": "service_seeker"}
        response = routes.create_order.__wrapped__()
        assert response.status_code == 400
        assert "next 24 hours" in response.get_json()["message"]
