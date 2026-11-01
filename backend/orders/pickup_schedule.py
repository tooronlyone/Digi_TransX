"""One-time pickups use Pakistan time and a rolling 24-hour window."""

from datetime import date, datetime, time, timedelta, timezone

PICKUP_TIMEZONE = timezone(timedelta(hours=5), name="Asia/Karachi")
PICKUP_LEAD_MINUTES = 20
PICKUP_WINDOW_HOURS = 24


def validate_pickup_schedule(date_value, time_value, *, now=None):
    try:
        pickup_date = date.fromisoformat(date_value)
    except (ValueError, TypeError):
        raise ValueError("Invalid pickup date format.") from None
    try:
        pickup_time = time.fromisoformat(time_value)
        if pickup_time.tzinfo is not None:
            raise ValueError
        pickup = datetime.combine(pickup_date, pickup_time, PICKUP_TIMEZONE)
    except (ValueError, TypeError):
        raise ValueError("Invalid pickup time format.") from None

    current = now if now is not None else datetime.now(PICKUP_TIMEZONE)
    if pickup < current + timedelta(minutes=PICKUP_LEAD_MINUTES):
        raise ValueError(
            f"Pickup must be at least {PICKUP_LEAD_MINUTES} minutes from now so the transporter can prepare."
        )
    if pickup > current + timedelta(hours=PICKUP_WINDOW_HOURS):
        raise ValueError("Pickup must be within the next 24 hours (Pakistan time).")
    return pickup_date
