"""Comprehensive Sprint 1 security remediation tests (V1-SEC-001 .. V1-SEC-004).

All tests execute strictly against disposable local PostgreSQL instances via
TEST_SUPABASE_DB_URL. Remote environments and .env secrets are never touched.
"""

import ast
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
import re
from types import SimpleNamespace
import threading
from urllib.parse import urlsplit
from uuid import uuid4

from flask import Flask
import psycopg2
from psycopg2.extras import Json
import pytest

from auth import helpers as auth_helpers, mpin_service, routes as auth_routes, step_up_service
from auth.security_headers import build_html_csp, ensure_csp_nonce, install_security_headers
from chat import routes as chat_routes
from contact import routes as contact_routes
from driver import business_rules as driver_business_routes, routes as driver_routes
from orders import routes as order_routes
from profile import routes as profile_routes
from shared.db import Db
from shared.rate_limit import client_ip_from_request, enforce_rate_limits
import shared.storage as storage_mod
from trucks import routes as truck_routes
from wallet import helpers as wallet_helpers, routes as wallet_routes
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
MAIN_PAGE_JSX = REPO_ROOT / "frontend-react" / "src" / "pages" / "main" / "MainPage.jsx"
MPIN_PEPPER = base64.urlsafe_b64encode(b"sprint1-mpin-test-pepper-32bytes").decode("ascii").rstrip("=")


def _local_test_url():
    url = require_test_db_url()
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Sprint 1 tests require a loopback TEST_SUPABASE_DB_URL.")
    return url


@pytest.fixture(scope="module")
def sprint1_db_url():
    url, cleanup = make_disposable(
        _local_test_url(), STUBS, SCHEMA_SQL.read_text(encoding="utf-8")
    )
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def sprint1_env(sprint1_db_url, monkeypatch):
    @contextmanager
    def test_open_db():
        conn = psycopg2.connect(sprint1_db_url)
        try:
            wrapper = Db(conn)
            yield wrapper
            conn.commit()
        except Exception:
            if not conn.closed:
                conn.rollback()
            raise
        finally:
            conn.close()

    for module in (
        auth_helpers,
        auth_routes,
        contact_routes,
        driver_business_routes,
        driver_routes,
        order_routes,
        profile_routes,
        truck_routes,
        wallet_helpers,
        wallet_routes,
    ):
        monkeypatch.setattr(module, "open_db", test_open_db)

    sent_emails = []
    monkeypatch.setattr(
        auth_routes,
        "send_email",
        lambda subject, recipient, body_lines: sent_emails.append((subject, recipient, list(body_lines))),
    )
    monkeypatch.setattr(
        profile_routes,
        "send_email",
        lambda subject, recipient, body_lines: sent_emails.append((subject, recipient, list(body_lines))),
    )
    monkeypatch.setattr(
        contact_routes,
        "send_email",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    monkeypatch.setenv("DIGITRANSX_MPIN_PEPPER", MPIN_PEPPER)

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="sprint1-security-remediation-secret",
        SESSION_COOKIE_SECURE=False,
    )
    install_security_headers(app)
    for blueprint in (
        auth_routes.auth_blueprint,
        profile_routes.profile_blueprint,
        contact_routes.contact_blueprint,
        driver_routes.driver_blueprint,
        order_routes.orders_blueprint,
        wallet_routes.wallet_blueprint,
        truck_routes.trucks_blueprint,
        chat_routes.chat_blueprint,
    ):
        app.register_blueprint(blueprint)

    def seed_user(role="service_seeker", *, email=None, cnic=None):
        auth_id = str(uuid4())
        user_email = email or f"{uuid4().hex[:10]}@sprint1.invalid"
        user_cnic = cnic or f"35202{secrets_digits(8)}"
        with test_open_db() as db:
            db.execute(
                "INSERT INTO auth.users (id, email, raw_user_meta_data) VALUES (%s, %s, %s)",
                (
                    auth_id,
                    user_email,
                    Json({"legacy_role": role, "full_name": f"Sprint1 {role}", "cnic": user_cnic}),
                ),
            )
            user = dict(
                db.execute("SELECT * FROM users WHERE auth_id = %s", (auth_id,)).fetchone()
            )
            db.execute(
                "UPDATE users SET cnic = %s WHERE id = %s AND (cnic IS NULL OR cnic = '')",
                (user_cnic, user["id"]),
            )
            user = dict(db.execute("SELECT * FROM users WHERE id = %s", (user["id"],)).fetchone())
        return user

    def login_client(user, *, with_mpin=None):
        client = app.test_client()
        from auth.session_service import create_session
        from auth.trusted_device_service import create_trusted_device

        with test_open_db() as db:
            device, device_id = create_trusted_device(db, user["id"])
            token, proof, session_id = create_session(db, user["id"], trusted_device_id=device_id)
            if with_mpin:
                mpin_service.enroll(db, user["id"], with_mpin)
        client.set_cookie(auth_helpers.DEVICE_COOKIE_NAME, device)
        client.set_cookie(auth_helpers.SESSION_TOKEN_COOKIE_NAME, token)
        client.set_cookie(auth_helpers.ACCESS_PROOF_COOKIE_NAME, proof)
        with client.session_transaction() as sess:
            sess["csrf_token"] = "sprint1-valid-csrf"
        return client, session_id

    yield SimpleNamespace(
        app=app,
        db=test_open_db,
        url=sprint1_db_url,
        seed_user=seed_user,
        login_client=login_client,
        csrf={"X-CSRF-Token": "sprint1-valid-csrf"},
        sent_emails=sent_emails,
    )

    conn = psycopg2.connect(sprint1_db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "TRUNCATE public.http_rate_limits, public.password_reset_otps, public.reset_tokens, "
                    "public.security_events, public.business_audit_events, public.login_activity, "
                    "public.mpin_step_up_authorizations, public.mpin_credentials, "
                    "public.trusted_devices, public.user_action_logs, public.contact_messages, "
                    "public.driver_fuel_logs, public.driver_hire_contracts, public.driver_profiles, "
                    "public.vehicles, public.wallet_withdrawal_requests, public.wallet_transactions, "
                    "public.wallets, public.shipment_trips, public.shipment_bids, public.payments, "
                    "public.shipments, public.users, auth.users RESTART IDENTITY CASCADE"
                )
    finally:
        conn.close()


def secrets_digits(count):
    import secrets
    return "".join(secrets.choice("0123456789") for _ in range(count))


def _extract_otp_from_email(sent_email_tuple):
    _, _, lines = sent_email_tuple
    for line in lines:
        if "code is:" in line:
            return line.rsplit(":", 1)[-1].strip()
    raise AssertionError(f"OTP not found in email body: {lines}")


# ---------------------------------------------------------------------------
# V1-SEC-001: CSRF Protection
# ---------------------------------------------------------------------------


def test_driver_and_hire_post_routes_enforce_csrf(sprint1_env):
    transporter = sprint1_env.seed_user("logistics_provider")
    driver = sprint1_env.seed_user("driver")
    with sprint1_env.db() as db:
        db.execute(
            "INSERT INTO driver_profiles (user_id, unique_driver_id, license_number, employment_type, rating) "
            "VALUES (%s, 'DRV-9001', 'LHR-9001', 'freelance', 4.9)",
            (driver["id"],),
        )
        db.execute(
            "INSERT INTO vehicles (owner_user_id, truck_number, truck_company, truck_model, truck_type, "
            "chassis_number, capacity_tons, main_use, status) "
            "VALUES (%s, 'LEA-9001', 'Hino', '500', 'Open Body', 'CHS90010000000001', 10, 'goods', 'active')",
            (transporter["id"],),
        )

    t_client, _ = sprint1_env.login_client(transporter)
    d_client, _ = sprint1_env.login_client(driver)

    # 1. POST /api/transporter/hire-driver-permanent
    hire_payload = {"unique_driver_id": "DRV-9001", "monthly_salary": "45000.00", "contract_months": 12}
    assert t_client.post("/api/transporter/hire-driver-permanent", json=hire_payload).status_code == 403
    assert t_client.post(
        "/api/transporter/hire-driver-permanent", headers={"X-CSRF-Token": "wrong"}, json=hire_payload
    ).status_code == 403
    ok_hire = t_client.post("/api/transporter/hire-driver-permanent", headers=sprint1_env.csrf, json=hire_payload)
    assert ok_hire.status_code == 200, ok_hire.get_json()
    contract_id = ok_hire.get_json()["contract_id"]

    # 2. POST /api/driver/hire-contracts/<id>/respond
    respond_url = f"/api/driver/hire-contracts/{contract_id}/respond"
    assert d_client.post(respond_url, json={"action": "accept"}).status_code == 403
    assert d_client.post(respond_url, headers={"X-CSRF-Token": "wrong"}, json={"action": "accept"}).status_code == 403
    ok_respond = d_client.post(respond_url, headers=sprint1_env.csrf, json={"action": "accept"})
    assert ok_respond.status_code == 200, ok_respond.get_json()

    # 3. POST /api/driver/fuel-logs
    fuel_payload = {
        "pump_name": "PSO Model Town",
        "city": "Lahore",
        "fuel_type": "diesel",
        "liters": "25.00",
        "price_per_liter": "280.00",
    }
    assert d_client.post("/api/driver/fuel-logs", json=fuel_payload).status_code == 403
    assert d_client.post("/api/driver/fuel-logs", headers={"X-CSRF-Token": "wrong"}, json=fuel_payload).status_code == 403
    ok_fuel = d_client.post("/api/driver/fuel-logs", headers=sprint1_env.csrf, json=fuel_payload)
    assert ok_fuel.status_code == 200, ok_fuel.get_json()


def test_all_authenticated_mutating_routes_require_csrf_statically():
    public_or_retired_allowlist = {
        ("auth\\routes.py", "signup"),
        ("auth\\routes.py", "login"),
        ("auth\\routes.py", "forgot_password"),
        ("auth\\routes.py", "verify_password_reset_otp"),
        ("auth\\routes.py", "reset_password"),
        ("auth\\routes.py", "fast_login_mpin"),
        ("orders\\routes.py", "accept_bid"),
        ("orders\\routes.py", "process_trip_payment"),
    }
    unprotected = []
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        if "tests" in path.parts or "scripts" in path.parts:
            continue
        source_text = path.read_text(encoding="utf-8")
        tree = ast.parse(source_text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            mutating = False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    if dec.func.attr.lower() in {"post", "put", "patch", "delete"}:
                        mutating = True
                    elif dec.func.attr == "route":
                        for kw in dec.keywords:
                            if kw.arg == "methods" and any(
                                isinstance(el, ast.Constant)
                                and str(el.value).upper() in {"POST", "PUT", "PATCH", "DELETE"}
                                for el in getattr(kw.value, "elts", [])
                            ):
                                mutating = True
            if not mutating:
                continue
            rel = str(path.relative_to(BACKEND_DIR)).replace("/", "\\")
            if (rel, node.name) in public_or_retired_allowlist:
                continue
            segment = ast.get_source_segment(source_text, node) or ""
            if not any(tok in segment for tok in ("csrf_error", "require_csrf", "mutate(")):
                unprotected.append(f"{rel}:{node.lineno}:{node.name}")
    assert unprotected == []


# ---------------------------------------------------------------------------
# V1-SEC-002: Password-Reset Non-Enumeration & OTP Abuse Protections
# ---------------------------------------------------------------------------


def test_password_reset_forgot_and_verify_are_non_enumerating(sprint1_env):
    user = sprint1_env.seed_user(email="real.recovery@sprint1.invalid")
    client = sprint1_env.app.test_client()

    # Forgot password response must be identical for unknown vs existent accounts, with no masked_email
    r_unknown = client.post("/auth/forgot-password", json={"loginId": "unknown.recovery@sprint1.invalid"})
    r_known = client.post("/auth/forgot-password", json={"loginId": user["email"]})
    assert r_unknown.status_code == 200
    assert r_known.status_code == 200
    assert r_unknown.get_json() == r_known.get_json()
    assert "masked_email" not in r_known.get_json()

    # Cross-alias (CNIC) request inside cooldown must stay silent 200 and send no extra email
    email_count_before = len(sprint1_env.sent_emails)
    r_alias = client.post("/auth/forgot-password", json={"loginId": user["cnic"]})
    assert r_alias.status_code == 200
    assert r_alias.get_json() == r_known.get_json()
    assert len(sprint1_env.sent_emails) == email_count_before

    # Verify OTP must return uniform 400 (never 404) for unknown account vs wrong OTP
    v_unknown = client.post(
        "/auth/password-reset/verify-otp",
        json={"loginId": "unknown.recovery@sprint1.invalid", "otp": "000000"},
    )
    v_wrong = client.post(
        "/auth/password-reset/verify-otp",
        json={"loginId": user["email"], "otp": "000000"},
    )
    assert v_unknown.status_code == 400
    assert v_wrong.status_code == 400
    assert v_unknown.get_json() == v_wrong.get_json() == {
        "success": False,
        "message": "Invalid or expired OTP.",
    }

    # Lock real user after 5 total wrong guesses; still returns identical 400 and silent 200 on forgot
    for _ in range(4):
        resp = client.post(
            "/auth/password-reset/verify-otp",
            json={"loginId": user["email"], "otp": "000000"},
        )
        assert resp.status_code == 400
        assert resp.get_json() == v_unknown.get_json()

    # Even submitting the real OTP after 5 wrong guesses must still return uniform 400
    issued_code = _extract_otp_from_email(sprint1_env.sent_emails[-1])
    v_locked_real = client.post(
        "/auth/password-reset/verify-otp",
        json={"loginId": user["email"], "otp": issued_code},
    )
    assert v_locked_real.status_code == 400
    assert v_locked_real.get_json() == v_unknown.get_json()


def test_otp_resend_cooldown_hourly_cap_supersession_and_attempt_preservation(sprint1_env):
    user = sprint1_env.seed_user(email="otp.hardening@sprint1.invalid")
    client = sprint1_env.app.test_client()

    # First request succeeds (unknown also behaves identically -> cooldown 429 on resend)
    assert client.post("/auth/forgot-password", json={"loginId": "missing.x@sprint1.invalid"}).status_code == 200
    r_unregistered_cooldown = client.post("/auth/forgot-password", json={"loginId": "missing.x@sprint1.invalid"})
    assert r_unregistered_cooldown.status_code == 429
    assert int(r_unregistered_cooldown.headers["Retry-After"]) >= 1

    assert client.post("/auth/forgot-password", json={"loginId": user["email"]}).status_code == 200
    otp_1 = _extract_otp_from_email(sprint1_env.sent_emails[-1])

    # Immediate resend hits uniform 429 without sending another email
    r_cooldown = client.post("/auth/forgot-password", json={"loginId": user["email"]})
    assert r_cooldown.status_code == 429
    assert r_cooldown.get_json()["code"] == "rate_limited"
    assert len(sprint1_env.sent_emails) == 1

    # Accumulate 4 wrong guesses on OTP #1
    for _ in range(4):
        res = client.post("/auth/password-reset/verify-otp", json={"loginId": user["email"], "otp": "999999"})
        assert res.status_code == 400

    # Simulate 65 seconds elapsing beyond resend cooldown and HTTP cooldown bucket expiry
    with sprint1_env.db() as db:
        past_iso = (auth_helpers.now_local() - timedelta(seconds=65)).isoformat(timespec="seconds")
        db.execute(
            "UPDATE password_reset_otps SET created_at_iso = %s, created_at = NOW() - INTERVAL '65 seconds' WHERE user_id = %s",
            (past_iso, user["id"]),
        )
        db.execute("DELETE FROM http_rate_limits WHERE bucket_key LIKE 'auth.forgot_password.cooldown:%'")

    # Regenerate OTP #2
    r_regen = client.post("/auth/forgot-password", json={"loginId": user["email"]})
    assert r_regen.status_code == 200
    assert len(sprint1_env.sent_emails) == 2
    otp_2 = _extract_otp_from_email(sprint1_env.sent_emails[-1])

    with sprint1_env.db() as db:
        rows = db.execute(
            "SELECT id, attempts, verified, superseded_at, cooldown_until_iso FROM password_reset_otps WHERE user_id = %s ORDER BY id",
            (user["id"],),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["verified"] == 1 and rows[0]["superseded_at"] is not None
        assert rows[1]["attempts"] == 4 and rows[1]["superseded_at"] is None

    # Superseded OTP #1 cannot be verified even though it was never marked failed individually
    if otp_1 != otp_2:
        assert client.post(
            "/auth/password-reset/verify-otp", json={"loginId": user["email"], "otp": otp_1}
        ).status_code == 400

    # Single wrong guess on OTP #2 completes attempt 5 and locks out OTP #2
    assert client.post(
        "/auth/password-reset/verify-otp", json={"loginId": user["email"], "otp": "888888"}
    ).status_code == 400
    assert client.post(
        "/auth/password-reset/verify-otp", json={"loginId": user["email"], "otp": otp_2}
    ).status_code == 400

    # Hourly request limit (5 / hour) blocks 6th request even if cooldown bucket elapsed
    with sprint1_env.app.app_context():
        user2 = sprint1_env.seed_user(email="hourly.cap@sprint1.invalid")
        for idx in range(5):
            assert client.post("/auth/forgot-password", json={"loginId": user2["email"]}).status_code == 200
            with sprint1_env.db() as db:
                back = (auth_helpers.now_local() - timedelta(minutes=2 * (5 - idx))).isoformat(timespec="seconds")
                db.execute(
                    "UPDATE password_reset_otps SET created_at_iso = %s, created_at = NOW() - INTERVAL '2 minutes' WHERE user_id = %s AND id = (SELECT MAX(id) FROM password_reset_otps WHERE user_id = %s)",
                    (back, user2["id"], user2["id"]),
                )
                db.execute("DELETE FROM http_rate_limits WHERE bucket_key LIKE 'auth.forgot_password.cooldown:%'")
        r_hourly = client.post("/auth/forgot-password", json={"loginId": user2["email"]})
        assert r_hourly.status_code == 429


def test_concurrent_otp_verification_is_atomic(sprint1_env):
    user = sprint1_env.seed_user(email="race.otp@sprint1.invalid")
    with sprint1_env.app.app_context():
        auth_helpers.create_otp_record(user["id"], "password_reset", "246810", user["email"])

    barrier = threading.Barrier(6)

    def try_verify(_idx):
        barrier.wait(timeout=10)
        with sprint1_env.app.app_context():
            _, err, token = auth_helpers.consume_otp_for_user(
                user["id"], "password_reset", "246810", issue_reset_authorization=True
            )
            return token if not err and token else None

    with ThreadPoolExecutor(max_workers=6) as pool:
        tokens = [t for t in pool.map(try_verify, range(6)) if t]

    assert len(tokens) == 1
    with sprint1_env.db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM reset_tokens WHERE user_id = %s", (user["id"],)).fetchone()["n"] == 1


# ---------------------------------------------------------------------------
# V1-SEC-003: Global HTTP Security Headers, CSP Nonce, HSTS, Download CSP
# ---------------------------------------------------------------------------


def test_global_security_headers_csp_nonce_and_download_sandbox_preserved(sprint1_env, monkeypatch):
    app = sprint1_env.app

    @app.get("/_test/html-bootstrap")
    def _test_html_bootstrap():
        nonce = ensure_csp_nonce()
        resp = app.response_class(
            f"<html><head><script nonce=\"{nonce}\">window.__BOOTSTRAP__={{}};</script></head><body>ok</body></html>",
            mimetype="text/html",
        )
        return resp

    client = app.test_client()

    # Non-HTML JSON API response headers
    api_resp = client.get("/auth/csrf-token")
    assert api_resp.headers["X-Frame-Options"] == "DENY"
    assert api_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert api_resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert api_resp.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "Strict-Transport-Security" not in api_resp.headers

    # HTML SPA bootstrap gets nonce-bound script-src (no unsafe-inline scripts) + unique per-request nonce
    h1 = client.get("/_test/html-bootstrap")
    h2 = client.get("/_test/html-bootstrap")
    csp1 = h1.headers["Content-Security-Policy"]
    csp2 = h2.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp1
    assert "object-src 'none'" in csp1
    assert "'unsafe-inline'" not in csp1.split("script-src", 1)[1].split(";", 1)[0]
    assert csp1 != csp2
    nonce1 = csp1.split("'nonce-", 1)[1].split("'", 1)[0]
    assert f'<script nonce="{nonce1}">' in h1.get_data(as_text=True)

    # Download routes preserve stricter "sandbox; default-src 'none'" CSP
    owner = sprint1_env.seed_user("logistics_provider")
    o_client, _ = sprint1_env.login_client(owner)
    with sprint1_env.db() as db:
        db.execute(
            "INSERT INTO vehicles (owner_user_id, truck_number, truck_company, truck_model, truck_type, "
            "chassis_number, capacity_tons, main_use, status, truck_photo_path) "
            "VALUES (%s, 'CSP-100', 'Hino', '500', 'Open Body', 'CHS10000000000001', 10, 'goods', 'active', 'uploads/trucks/sample.png')",
            (owner["id"],),
        )
    monkeypatch.setattr(
        storage_mod,
        "download_bytes",
        lambda _path: b"\x89PNG\r\n\x1a\n",
    )
    dl = o_client.get("/uploads/trucks/sample.png")
    assert dl.status_code == 200
    assert dl.headers["Content-Security-Policy"] == "sandbox; default-src 'none'"
    assert dl.headers["X-Content-Type-Options"] == "nosniff"
    assert dl.headers["X-Frame-Options"] == "DENY"


def test_hsts_only_emitted_for_nonlocal_https_deployments():
    app = Flask(__name__)
    install_security_headers(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    # 1. Explicit local/test (SESSION_COOKIE_SECURE=False) never emits HSTS even over https://
    app.config["SESSION_COOKIE_SECURE"] = False
    c = app.test_client()
    assert "Strict-Transport-Security" not in c.get("/ping", base_url="https://app.example.invalid").headers

    # 2. Non-local (SESSION_COOKIE_SECURE=True) over plain HTTP omits HSTS
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["TRUST_PROXY_COUNT"] = 0
    assert "Strict-Transport-Security" not in c.get("/ping", base_url="http://127.0.0.1").headers
    # Spoofed X-Forwarded-Proto when TRUST_PROXY_COUNT=0 must NOT trigger HSTS on plain HTTP
    assert "Strict-Transport-Security" not in c.get(
        "/ping", base_url="http://127.0.0.1", headers={"X-Forwarded-Proto": "https"}
    ).headers

    # 3. Non-local direct HTTPS emits HSTS
    direct_https = c.get("/ping", base_url="https://app.example.invalid")
    assert direct_https.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

    # 4. Non-local trusted 1-hop HTTPS proxy emits HSTS
    app.config["TRUST_PROXY_COUNT"] = 1
    proxied_https = c.get(
        "/ping", base_url="http://backend.internal", headers={"X-Forwarded-Proto": "http, https"}
    )
    assert proxied_https.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_main_page_jsx_has_no_dangerously_set_inner_html_or_inline_handlers():
    content = MAIN_PAGE_JSX.read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in content
    assert not re.search(r"\bon[a-z]+\s*=\s*['\"]", content, re.IGNORECASE)
    assert "window.switchTab" not in content


# ---------------------------------------------------------------------------
# V1-SEC-004: Shared PostgreSQL Rate Limiting & Safe Proxy IP Parsing
# ---------------------------------------------------------------------------


def test_shared_pg_rate_limiter_enforces_across_independent_connections(sprint1_db_url):
    @contextmanager
    def worker_a_db():
        with psycopg2.connect(sprint1_db_url) as conn:
            yield Db(conn)

    @contextmanager
    def worker_b_db():
        with psycopg2.connect(sprint1_db_url) as conn:
            yield Db(conn)

    app = Flask(__name__)
    with app.test_request_context("/"):
        # Worker A consumes 2 of 3 slots; Worker B consumes slot 3; Worker A's 4th fails 429
        assert enforce_rate_limits(worker_a_db, [("test.shared", "acct-1", (3, 60))]) is None
        assert enforce_rate_limits(worker_a_db, [("test.shared", "acct-1", (3, 60))]) is None
        assert enforce_rate_limits(worker_b_db, [("test.shared", "acct-1", (3, 60))]) is None
        blocked = enforce_rate_limits(worker_a_db, [("test.shared", "acct-1", (3, 60))])
        assert blocked is not None
        assert blocked.status_code == 429
        assert blocked.get_json()["code"] == "rate_limited"
        assert int(blocked.headers["Retry-After"]) >= 1

    # Clean table for subsequent tests
    conn = psycopg2.connect(sprint1_db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public.http_rate_limits")
    finally:
        conn.close()


def test_proxy_ip_extraction_blocks_xff_spoofing():
    app = Flask(__name__)
    app.config["TRUST_PROXY_COUNT"] = 0
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "198.51.100.10"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    ):
        assert client_ip_from_request() == "198.51.100.10"

    app.config["TRUST_PROXY_COUNT"] = 1
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "10.0.0.5"},
        headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.55"},
    ):
        assert client_ip_from_request() == "203.0.113.55"

    # Malformed X-Forwarded-For falls back safely to remote_addr
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "10.0.0.5"},
        headers={"X-Forwarded-For": "not-an-ip"},
    ):
        assert client_ip_from_request() == "10.0.0.5"


def test_http_rate_limiting_stops_contact_login_and_financial_bursts(sprint1_env, monkeypatch):
    # 1. Contact endpoint enforces real default 5-per-window limit cleanly and blocks 6th
    c = sprint1_env.app.test_client()
    with c.session_transaction() as sess:
        sess["csrf_token"] = sprint1_env.csrf["X-CSRF-Token"]
    for i in range(5):
        resp = c.post(
            "/api/contact",
            headers=sprint1_env.csrf,
            json={
                "name": "Test User",
                "email": f"sender{i}@sprint1.invalid",
                "subject": "Support",
                "message": f"Hello {i}",
            },
        )
        assert resp.status_code == 200, resp.get_json()
    sixth = c.post(
        "/api/contact",
        headers=sprint1_env.csrf,
        json={
            "name": "Test User",
            "email": "sender5@sprint1.invalid",
            "subject": "Support",
            "message": "Burst 6",
        },
    )
    assert sixth.status_code == 429
    assert int(sixth.headers["Retry-After"]) >= 1
    with sprint1_env.db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM contact_messages").fetchone()["n"] == 5

    # 2. Login rate limit blocks brute force on same identifier & unknown identifier identically with 429
    monkeypatch.setattr(auth_routes, "supabase_verify_password", lambda *_a, **_k: False)
    user = sprint1_env.seed_user(email="brute.target@sprint1.invalid")
    sprint1_env.app.config["RATE_LIMIT_OVERRIDES"] = {
        "auth.login.identifier": (3, 60),
        "auth.login.ip": (50, 60),
        "finance.topup.user": (2, 60),
        "auth.mpin.unlock.user": (2, 60),
    }
    for identifier in (user["email"], "nonexistent.target@sprint1.invalid"):
        for _ in range(3):
            assert c.post("/auth/login", json={"loginId": identifier, "password": "wrong"}).status_code == 401
        throttled = c.post("/auth/login", json={"loginId": identifier, "password": "wrong"})
        assert throttled.status_code == 429
        assert int(throttled.headers["Retry-After"]) >= 1

    # 3. Financial topup & MPIN unlock bursts are throttled 429 without extra wallet credits
    t_client, session_id = sprint1_env.login_client(user, with_mpin="1234")
    card_payload = {
        "amount": 100,
        "card_number": "4242424242424242",
        "card_holder_name": "Sprint One",
        "card_cvc": "123",
        "card_expiry": "12/30",
    }
    for idx in range(2):
        ok = t_client.post(
            "/api/wallet/topup",
            headers={**sprint1_env.csrf, "Idempotency-Key": f"topup-rate-{idx}"},
            json=card_payload,
        )
        assert ok.status_code == 200, ok.get_json()
    limited_topup = t_client.post(
        "/api/wallet/topup",
        headers={**sprint1_env.csrf, "Idempotency-Key": "topup-rate-2"},
        json=card_payload,
    )
    assert limited_topup.status_code == 429

    # Lock session proof then burst MPIN unlock
    from auth.session_service import lock_access_once

    with sprint1_env.db() as db:
        assert lock_access_once(db, session_id) == 1
    for _ in range(2):
        assert t_client.post("/auth/mpin/unlock", headers=sprint1_env.csrf, json={"mpin": "9999"}).status_code == 401
    assert t_client.post("/auth/mpin/unlock", headers=sprint1_env.csrf, json={"mpin": "9999"}).status_code == 429


def test_http_rate_limits_table_rls_and_privileges_are_locked_down(sprint1_db_url):
    with psycopg2.connect(sprint1_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.http_rate_limits'::regclass")
            assert cur.fetchone() == (True,)
            for role in ("anon", "authenticated"):
                cur.execute(
                    "SELECT has_table_privilege(%s, 'public.http_rate_limits', 'SELECT'), "
                    "has_table_privilege(%s, 'public.http_rate_limits', 'INSERT'), "
                    "has_table_privilege(%s, 'public.http_rate_limits', 'UPDATE'), "
                    "has_table_privilege(%s, 'public.http_rate_limits', 'DELETE')",
                    (role, role, role, role),
                )
                assert cur.fetchone() == (False, False, False, False)


def test_real_flask_app_entrypoint_serves_nonce_csp_and_global_headers(sprint1_db_url):
    import json
    import os
    import subprocess
    import sys

    probe = """
import json
import app as app_module

client = app_module.app.test_client()
root_resp = client.get("/")
api_resp = client.get("/auth/csrf-token")
print(json.dumps({
    "root_status": root_resp.status_code,
    "root_mimetype": root_resp.mimetype,
    "root_headers": dict(root_resp.headers),
    "root_body": root_resp.get_data(as_text=True),
    "api_status": api_resp.status_code,
    "api_headers": dict(api_resp.headers),
}))
"""
    env = dict(os.environ)
    env["SUPABASE_DB_URL"] = sprint1_db_url
    env["DIGITRANSX_ENVIRONMENT"] = "test"
    env["FLASK_HOST"] = "127.0.0.1"
    env["DIGITRANSX_ENABLE_SCHEDULER"] = "false"
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["root_status"] == 200
    assert data["root_headers"]["X-Frame-Options"] == "DENY"
    assert data["root_headers"]["X-Content-Type-Options"] == "nosniff"
    assert data["root_headers"]["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" not in data["root_headers"]
    if data["root_mimetype"] == "text/html":
        csp = data["root_headers"]["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp
        nonce = csp.split("'nonce-", 1)[1].split("'", 1)[0]
        assert f'<script nonce="{nonce}">' in data["root_body"]
        assert data["root_headers"]["Cache-Control"] == "no-store"
    assert data["api_status"] == 200
    assert data["api_headers"]["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert data["api_headers"]["X-Frame-Options"] == "DENY"
