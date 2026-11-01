"""Bounded numeric input at HTTP and inventory boundaries.

Reject non-finite values before comparisons/SQL. Fixed-scale inputs are rejected
instead of being silently rounded by PostgreSQL numeric columns.
"""

from decimal import Decimal, InvalidOperation


def finite_decimal(value, label, *, minimum=Decimal("0"), maximum=Decimal("9999999999.99"), scale=None):
    if isinstance(value, bool) or value is None or (isinstance(value,str) and len(value)>128):
        raise ValueError(f"{label} must be a valid finite number.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a valid finite number.") from None
    if not number.is_finite() or not minimum <= number <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    if scale is not None:
        quantum = Decimal(1).scaleb(-scale)
        try:
            quantized = number.quantize(quantum)
        except InvalidOperation:
            raise ValueError(f"{label} has unsupported precision.") from None
        if number != quantized:
            raise ValueError(f"{label} supports at most {scale} decimal places.")
    return number


def finite_float(value, label, *, minimum=Decimal("0"), maximum=Decimal("1000000000")):
    return float(finite_decimal(value,label,minimum=minimum,maximum=maximum))


def bounded_count(value, label, *, maximum=1_000_000):
    return int(finite_decimal(value,label,maximum=Decimal(maximum),scale=0))
