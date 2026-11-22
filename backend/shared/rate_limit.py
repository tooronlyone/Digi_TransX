"""Durable PostgreSQL-backed HTTP rate limiting and safe client-IP resolution."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import ipaddress
import os
import secrets
import time

from flask import current_app, has_app_context, jsonify, request


DEFAULT_POLICIES = {
    "auth.login.ip": (25, 300),
    "auth.login.identifier": (10, 900),
    "auth.signup.ip": (10, 3600),
    "auth.forgot_password.ip": (20, 3600),
    "auth.forgot_password.cooldown": (1, 60),
    "auth.forgot_password.hourly": (5, 3600),
    "auth.verify_otp.ip": (25, 900),
    "auth.verify_otp.identifier": (10, 900),
    "auth.reset_password.ip": (15, 900),
    "auth.mpin.unlock.user": (20, 900),
    "auth.mpin.step_up.user": (20, 900),
    "auth.mpin.password_unlock.user": (20, 900),
    "admin.step_up.user": (15, 900),
    "profile.password_otp.cooldown": (1, 60),
    "profile.password_otp.hourly": (5, 3600),
    "contact.submit.ip": (5, 900),
    "finance.checkout.user": (20, 60),
    "finance.topup.user": (20, 60),
    "finance.withdraw.user": (20, 60),
    "finance.upgrade_limit.user": (20, 60),
    "finance.payout_card.user": (20, 60),
}


def trusted_proxy_hops():
    """Return the configured number of trusted reverse-proxy hops (default 0)."""
    raw = None
    if has_app_context() and "TRUST_PROXY_COUNT" in current_app.config:
        raw = current_app.config.get("TRUST_PROXY_COUNT")
    if raw is None:
        raw = os.environ.get("DIGITRANSX_TRUST_PROXY_COUNT", "0")
    try:
        hops = int(raw)
    except (TypeError, ValueError):
        return 0
    return hops if hops > 0 else 0


def _normalize_ip(raw_ip):
    text = str(raw_ip or "").strip()
    if not text:
        return None
    try:
        parsed = ipaddress.ip_address(text)
    except ValueError:
        return None
    if getattr(parsed, "ipv4_mapped", None) is not None:
        return str(parsed.ipv4_mapped)
    return str(parsed)


def client_ip_from_request(req=None):
    """Extract client IP safely, trusting X-Forwarded-For only for N configured hops."""
    active_req = req or request
    remote = _normalize_ip(getattr(active_req, "remote_addr", None)) or "0.0.0.0"
    hops = trusted_proxy_hops()
    if hops <= 0:
        return remote

    forwarded = ""
    headers = getattr(active_req, "headers", None)
    if headers is not None:
        forwarded = headers.get("X-Forwarded-For", "") or ""
    if not forwarded.strip():
        return remote

    raw_parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(raw_parts) < hops:
        return remote
    candidate = _normalize_ip(raw_parts[-hops])
    return candidate or remote


def normalized_identifier_digest(value):
    """Return a stable SHA-256 digest for an identifier without storing PII."""
    normalized = " ".join(str(value or "").strip().lower().split())
    return sha256(normalized.encode("utf-8")).hexdigest()


def _resolve_policy(policy):
    if isinstance(policy, tuple):
        return int(policy[0]), int(policy[1])
    if has_app_context():
        overrides = current_app.config.get("RATE_LIMIT_OVERRIDES") or {}
        if policy in overrides:
            limit, window_seconds = overrides[policy]
            return int(limit), int(window_seconds)
    limit, window_seconds = DEFAULT_POLICIES[policy]
    return int(limit), int(window_seconds)


def check_rate_limit(db, *, scope, key, limit, window_seconds, now_ts=None):
    """Increment and evaluate a durable PostgreSQL bucket.

    Single-shot cooldown policies (`limit == 1`) use a true sliding expiration
    interval (`TIMESTAMPTZ 'epoch'` sentinel + `expires_at = NOW() + window_seconds`)
    so callers cannot bypass cooldowns across wall-clock boundary ticks.
    Multi-request windows use epoch-aligned fixed buckets.
    """
    if limit <= 0 or window_seconds <= 0:
        raise ValueError("Rate limit threshold and window must be positive integers.")
    digest = sha256(str(key).encode("utf-8")).hexdigest()
    bucket_key = f"{scope}:{digest}"

    if limit == 1:
        row = db.execute(
            """
            INSERT INTO http_rate_limits (bucket_key, window_start, request_count, expires_at)
            VALUES (%s, TIMESTAMPTZ 'epoch', 1, NOW() + (%s * INTERVAL '1 second'))
            ON CONFLICT (bucket_key, window_start)
            DO UPDATE SET
                request_count = CASE
                    WHEN http_rate_limits.expires_at <= NOW() THEN 1
                    ELSE http_rate_limits.request_count + 1
                END,
                expires_at = CASE
                    WHEN http_rate_limits.expires_at <= NOW()
                        THEN NOW() + (%s * INTERVAL '1 second')
                    ELSE http_rate_limits.expires_at
                END
            RETURNING
                request_count,
                GREATEST(1, CEIL(EXTRACT(EPOCH FROM (expires_at - NOW())))::integer) AS retry_after
            """,
            (bucket_key, window_seconds, window_seconds),
        ).fetchone()
        count = int(row["request_count"])
        retry_after = int(row["retry_after"])
    else:
        ts = int(time.time()) if now_ts is None else int(now_ts)
        bucket_start_ts = (ts // window_seconds) * window_seconds
        window_start = datetime.fromtimestamp(bucket_start_ts, tz=timezone.utc)
        expires_at = window_start + timedelta(seconds=window_seconds * 2)

        row = db.execute(
            """
            INSERT INTO http_rate_limits (bucket_key, window_start, request_count, expires_at)
            VALUES (%s, %s, 1, %s)
            ON CONFLICT (bucket_key, window_start)
            DO UPDATE SET
                request_count = http_rate_limits.request_count + 1,
                expires_at = GREATEST(http_rate_limits.expires_at, EXCLUDED.expires_at)
            RETURNING request_count
            """,
            (bucket_key, window_start, expires_at),
        ).fetchone()
        count = int(row["request_count"])
        retry_after = max(1, int(window_seconds - (ts % window_seconds)))

    # Bounded amortized cleanup so expired buckets do not accumulate indefinitely.
    if secrets.randbelow(100) == 0:
        db.execute("DELETE FROM http_rate_limits WHERE expires_at < NOW()")

    return count <= limit, retry_after, count


def rate_limited_response(retry_after, message=None):
    """Build a uniform non-enumerating HTTP 429 JSON response with Retry-After."""
    response = jsonify(
        {
            "success": False,
            "code": "rate_limited",
            "message": message or "Too many requests. Please wait before trying again.",
        }
    )
    response.status_code = 429
    response.headers["Retry-After"] = str(max(1, int(retry_after)))
    return response


def enforce_rate_limits(open_db_fn, checks, *, message=None):
    """Run one or more durable rate-limit checks in a single committed transaction.

    `checks` is an iterable of `(scope, raw_key, policy_key_or_tuple)`.
    Increments are always committed even when rejecting so abusive callers
    cannot evade throttling via downstream rollbacks.
    """
    resolved = []
    for scope, raw_key, policy in checks:
        limit, window_seconds = _resolve_policy(policy)
        resolved.append((scope, raw_key, limit, window_seconds))
    resolved.sort(key=lambda item: (item[0], str(item[1])))

    blocked_retry_after = 0
    with open_db_fn() as db:
        for scope, raw_key, limit, window_seconds in resolved:
            allowed, retry_after, _ = check_rate_limit(
                db,
                scope=scope,
                key=raw_key,
                limit=limit,
                window_seconds=window_seconds,
            )
            if not allowed:
                blocked_retry_after = max(blocked_retry_after, retry_after)
        db.commit()

    if blocked_retry_after > 0:
        return rate_limited_response(blocked_retry_after, message=message)
    return None
