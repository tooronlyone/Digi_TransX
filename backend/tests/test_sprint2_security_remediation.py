"""Comprehensive verification tests for Digi_TransX V1 Security Remediation Sprint 2."""

from concurrent.futures import ThreadPoolExecutor
import base64
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

from flask import Flask
from PIL import Image
import psycopg2
from psycopg2.extras import Json
import pytest

from admin import routes as admin_routes
from auth import credential_changes, helpers as auth_helpers, mpin_service, routes as auth_routes, step_up_service
from auth.session_service import create_session
from auth.trusted_device_service import create_trusted_device
from chat import helpers as chat_helpers, routes as chat_routes
from driver import business_rules as driver_business_routes, routes as driver_routes
from orders import business_lifecycle as order_lifecycle, routes as order_routes
from scripts.reconcile_business_rules import reconcile
from shared import storage
from shared.db import Db
from shared.upload_validation import validate_and_sanitize_upload
from trucks import helpers as truck_helpers, routes as truck_routes
from wallet import helpers as wallet_helpers, routes as wallet_routes, withdrawal_limits
from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url


BACKEND_DIR = Path(__file__).resolve().parent.parent


def _jpeg_with_exif_bytes():
    img = Image.new("RGB", (24, 24), color=(12, 85, 200))
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneVendor"
    exif[0x0110] = "TrackerCam-99"
    exif[0x0131] = "DeviceOS 1.0"
    exif[0x013B] = "PrivateAuthor"
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _valid_png_bytes():
    buf = BytesIO()
    Image.new("RGBA", (16, 16), color=(10, 200, 120, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _valid_webp_bytes():
    buf = BytesIO()
    Image.new("RGB", (16, 16), color=(200, 120, 10)).save(buf, format="WEBP")
    return buf.getvalue()


def _valid_mp4_bytes():
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"


def _valid_mov_bytes():
    return b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  "


def _valid_pdf_bytes():
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


@pytest.fixture(scope="module")
def sprint2_db_url():
    base = require_test_db_url()
    url, cleanup = make_disposable(base, STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def sprint2_env(sprint2_db_url, monkeypatch):
    @contextmanager
    def database():
        conn = psycopg2.connect(sprint2_db_url)
        try:
            yield Db(conn)
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
        admin_routes,
        credential_changes,
        order_routes,
        wallet_routes,
        wallet_helpers,
        truck_routes,
        chat_routes,
        driver_routes,
        driver_business_routes,
    ):
        monkeypatch.setattr(module, "open_db", database)

    monkeypatch.setattr(admin_routes, "supabase_verify_password", lambda *_a, **_k: True)
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT", "test")
    monkeypatch.setenv("DIGITRANSX_MPIN_PEPPER", base64.urlsafe_b64encode(b"P" * 32).decode())

    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="sprint2-remediation-secret", SESSION_COOKIE_SECURE=False)
    for blueprint in (
        auth_routes.auth_blueprint,
        admin_routes.admin_blueprint,
        order_routes.orders_blueprint,
        wallet_routes.wallet_blueprint,
        truck_routes.trucks_blueprint,
        chat_routes.chat_blueprint,
        driver_routes.driver_blueprint,
    ):
        app.register_blueprint(blueprint)

    def create_user(role="service_seeker", *, admin=False):
        auth_id = str(uuid4())
        email = f"{uuid4().hex}@sprint2.invalid"
        with database() as db:
            db.execute(
                "INSERT INTO auth.users(id, email, raw_user_meta_data) VALUES(%s, %s, %s)",
                (auth_id, email, Json({"legacy_role": role, "full_name": "Sprint2 User"})),
            )
            user = dict(db.execute("SELECT * FROM users WHERE auth_id = %s", (auth_id,)).fetchone())
            if admin:
                db.execute(
                    "UPDATE users SET role = 'admin', legacy_role = 'platform_admin' WHERE id = %s",
                    (user["id"],),
                )
                user = dict(db.execute("SELECT * FROM users WHERE id = %s", (user["id"],)).fetchone())
            return user

    def login_client(user):
        client = app.test_client()
        with database() as db:
            device_token, device_id = create_trusted_device(db, user["id"])
            session_token, access_proof, session_id = create_session(
                db, user["id"], trusted_device_id=device_id
            )
        client.set_cookie("dtx_device_token", device_token)
        client.set_cookie("dtx_session_token", session_token)
        client.set_cookie("dtx_access_proof", access_proof)
        with client.session_transaction() as sess:
            sess["csrf_token"] = "sprint2-csrf"
        return {
            "client": client,
            "session_id": session_id,
            "device_id": device_id,
            "device_token": device_token,
            "session_token": session_token,
            "access_proof": access_proof,
            "csrf": "sprint2-csrf",
        }

    def headers_for(auth_bundle, *, step_up_proof=None, idempotency_key=None, mpin_proof=None):
        hdrs = {"X-CSRF-Token": auth_bundle["csrf"]}
        if step_up_proof:
            hdrs["X-Admin-Step-Up-Proof"] = step_up_proof
        if idempotency_key:
            hdrs["Idempotency-Key"] = idempotency_key
        if mpin_proof:
            hdrs["X-MPIN-Step-Up-Proof"] = mpin_proof
        return hdrs

    def issue_admin_proof(auth_bundle, action_descriptor):
        resp = auth_bundle["client"].post(
            "/api/admin/step-up",
            headers=headers_for(auth_bundle),
            json={"password": "StrongAdminPass123!", "action": action_descriptor},
        )
        assert resp.status_code == 200, resp.json
        return resp.json["step_up_proof"]

    def issue_mpin_proof(user, auth_bundle, descriptor):
        with database() as db:
            cred = db.execute(
                "SELECT credential_generation FROM mpin_credentials WHERE user_id = %s",
                (user["id"],),
            ).fetchone()
            if not cred:
                mpin_service.enroll(db, user["id"], "2580")
                cred = db.execute(
                    "SELECT credential_generation FROM mpin_credentials WHERE user_id = %s",
                    (user["id"],),
                ).fetchone()
            return step_up_service.issue_authorization(
                db,
                user_id=user["id"],
                session_id=auth_bundle["session_id"],
                trusted_device_id=auth_bundle["device_id"],
                credential_generation=cred["credential_generation"],
                descriptor=descriptor,
            )["proof"]

    return SimpleNamespace(
        app=app,
        db=database,
        url=sprint2_db_url,
        create_user=create_user,
        login_client=login_client,
        headers_for=headers_for,
        issue_admin_proof=issue_admin_proof,
        issue_mpin_proof=issue_mpin_proof,
    )


def test_sec005_block_revokes_sessions_and_devices_and_unblock_keeps_them_dead(sprint2_env):
    admin = sprint2_env.create_user(admin=True)
    transporter = sprint2_env.create_user("logistics_provider")
    admin_auth = sprint2_env.login_client(admin)
    victim_auth = sprint2_env.login_client(transporter)

    assert victim_auth["client"].get("/api/wallet/withdrawal-limits").status_code == 200

    # Block requires admin step-up; verify 428 challenge -> verify -> 200
    challenge = admin_auth["client"].put(
        f"/api/admin/users/{transporter['id']}/block",
        headers=sprint2_env.headers_for(admin_auth),
        json={"blocked": True, "reason": "Compromised credential audit"},
    )
    assert challenge.status_code == 428 and challenge.json["code"] == "admin_step_up_required"
    proof = sprint2_env.issue_admin_proof(admin_auth, challenge.json["action"])
    block_resp = admin_auth["client"].put(
        f"/api/admin/users/{transporter['id']}/block",
        headers=sprint2_env.headers_for(admin_auth, step_up_proof=proof),
        json={"blocked": True, "reason": "Compromised credential audit"},
    )
    assert block_resp.status_code == 200, block_resp.json

    # Active cookies are dead immediately
    assert victim_auth["client"].get("/api/wallet/withdrawal-limits").status_code == 401

    with sprint2_env.db() as db:
        u_row = db.execute(
            "SELECT is_blocked, credentials_version FROM users WHERE id = %s", (transporter["id"],)
        ).fetchone()
        assert u_row["is_blocked"] is True
        assert u_row["credentials_version"] == transporter["credentials_version"] + 1
        s_row = db.execute(
            "SELECT revoked_at, revocation_reason, access_locked, access_proof_digest "
            "FROM user_sessions WHERE session_id = %s",
            (str(victim_auth["session_id"]),),
        ).fetchone()
        assert s_row["revoked_at"] is not None
        assert s_row["revocation_reason"] == "account_blocked"
        assert s_row["access_locked"] is True
        assert s_row["access_proof_digest"] is None
        d_row = db.execute(
            "SELECT revoked_at FROM trusted_devices WHERE id = %s", (victim_auth["device_id"],)
        ).fetchone()
        assert d_row["revoked_at"] is not None
        sec_events = db.execute(
            "SELECT event_name FROM security_events WHERE subject_user_id = %s ORDER BY occurred_at",
            (transporter["id"],),
        ).fetchall()
        assert {e["event_name"] for e in sec_events} >= {
            "security.session.revoked",
            "security.trusted_device.removed",
        }
        admin_logs = db.execute(
            "SELECT action_name FROM user_action_logs WHERE action_name = 'block_user' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert admin_logs["action_name"] == "block_user"

    # Unblock with a separate step-up bound specifically to blocked=False
    unblock_challenge = admin_auth["client"].put(
        f"/api/admin/users/{transporter['id']}/block",
        headers=sprint2_env.headers_for(admin_auth),
        json={"blocked": False, "reason": ""},
    )
    assert unblock_challenge.status_code == 428
    # Proof from wrong target (blocked=True) must NOT work for blocked=False
    wrong_proof = sprint2_env.issue_admin_proof(admin_auth, challenge.json["action"])
    wrong_target = admin_auth["client"].put(
        f"/api/admin/users/{transporter['id']}/block",
        headers=sprint2_env.headers_for(admin_auth, step_up_proof=wrong_proof),
        json={"blocked": False, "reason": ""},
    )
    assert wrong_target.status_code == 428

    unblock_proof = sprint2_env.issue_admin_proof(admin_auth, unblock_challenge.json["action"])
    unblock_resp = admin_auth["client"].put(
        f"/api/admin/users/{transporter['id']}/block",
        headers=sprint2_env.headers_for(admin_auth, step_up_proof=unblock_proof),
        json={"blocked": False, "reason": ""},
    )
    assert unblock_resp.status_code == 200

    # Pre-block cookies MUST stay dead even after unblock
    assert victim_auth["client"].get("/api/wallet/withdrawal-limits").status_code == 401

    # Fresh login after unblock works cleanly
    fresh_auth = sprint2_env.login_client(transporter)
    assert fresh_auth["client"].get("/api/wallet/withdrawal-limits").status_code == 200


def test_sec006_all_sensitive_admin_endpoints_require_single_use_bound_step_up(sprint2_env, monkeypatch):
    admin1 = sprint2_env.create_user(admin=True)
    admin2 = sprint2_env.create_user(admin=True)
    shipper = sprint2_env.create_user("service_seeker")
    transporter = sprint2_env.create_user("logistics_provider")
    a1 = sprint2_env.login_client(admin1)
    a2 = sprint2_env.login_client(admin2)
    shipper_auth = sprint2_env.login_client(shipper)

    # Non-admin cannot issue admin step-up proof
    forbidden_step_up = shipper_auth["client"].post(
        "/api/admin/step-up",
        headers=sprint2_env.headers_for(shipper_auth),
        json={"password": "StrongAdminPass123!", "action": {"action_key": "admin.delivery_overdue.process", "resource_id": 1}},
    )
    assert forbidden_step_up.status_code == 403

    # Wrong password is rejected cleanly
    monkeypatch.setattr(admin_routes, "supabase_verify_password", lambda *_a, **_k: False)
    bad_pw = a1["client"].post(
        "/api/admin/step-up",
        headers=sprint2_env.headers_for(a1),
        json={"password": "WrongPassword123!", "action": {"action_key": "admin.delivery_overdue.process", "resource_id": 1}},
    )
    assert bad_pw.status_code == 401
    monkeypatch.setattr(admin_routes, "supabase_verify_password", lambda *_a, **_k: True)

    with sprint2_env.db() as db:
        w, err = wallet_helpers.get_or_create_wallet_for_user(
            db, {"id": transporter["id"], "role": "logistics_provider"}
        )
        assert err is None
        db.execute("UPDATE wallets SET balance = 50000.00 WHERE id = %s", (w["id"],))
        r1 = db.execute(
            "INSERT INTO wallet_withdrawal_requests(user_id, wallet_id, amount, status) "
            "VALUES(%s, %s, 1000.00, 'pending') RETURNING id",
            (transporter["id"], w["id"]),
        ).fetchone()["id"]
        r2 = db.execute(
            "INSERT INTO wallet_withdrawal_requests(user_id, wallet_id, amount, status) "
            "VALUES(%s, %s, 1000.00, 'pending') RETURNING id",
            (transporter["id"], w["id"]),
        ).fetchone()["id"]

    # Every protected admin endpoint returns 428 when X-Admin-Step-Up-Proof is omitted
    calls = [
        ("POST", "/api/admin/users", {"name": "New Admin", "email": "new@sprint2.invalid", "password": "ValidAdminPass123!"}),
        ("PUT", f"/api/admin/users/{shipper['id']}/block", {"blocked": True, "reason": "test"}),
        ("POST", f"/api/admin/wallet/withdrawals/{r1}/approve", {}),
        ("POST", f"/api/admin/wallet/withdrawals/{r1}/reject", {}),
        ("POST", "/api/admin/platform-settings/commissions", {"policy_type": "one_time_order", "company_share_percent": 20, "change_summary": "Audit review"}),
        ("POST", "/api/admin/one-time-disputes/999/resolve", {"resolution": "client_win", "notes": "Valid resolution note"}),
        ("POST", "/api/admin/delivery-confirmations/process-overdue", {}),
        ("POST", "/api/admin/freight-settlements/999/resolve", {"client_refund_amount": 0, "notes": "Test note"}),
        ("POST", f"/api/admin/owner-operator-credentials/{transporter['id']}", {"license_number": "LIC-999", "license_expiry": (date.today() + timedelta(days=365)).isoformat(), "verification_evidence": "Verified copy 12345"}),
        ("POST", "/api/admin/operational-incidents/999/decision", {"status": "confirmed", "decision_evidence": "Detailed independent evidence"}),
    ]
    for method, path, payload in calls:
        res = a1["client"].open(path, method=method, headers=sprint2_env.headers_for(a1), json=payload)
        assert res.status_code == 428, f"{method} {path} returned {res.status_code}: {res.json}"
        assert res.json["code"] == "admin_step_up_required"

    # Proof bound to withdrawal r1 approve cannot approve r2 or reject r1 or be used by admin2
    ch1 = a1["client"].post(f"/api/admin/wallet/withdrawals/{r1}/approve", headers=sprint2_env.headers_for(a1), json={})
    proof_r1 = sprint2_env.issue_admin_proof(a1, ch1.json["action"])

    assert a1["client"].post(
        f"/api/admin/wallet/withdrawals/{r2}/approve",
        headers=sprint2_env.headers_for(a1, step_up_proof=proof_r1),
        json={},
    ).status_code == 428
    assert a1["client"].post(
        f"/api/admin/wallet/withdrawals/{r1}/reject",
        headers=sprint2_env.headers_for(a1, step_up_proof=proof_r1),
        json={},
    ).status_code == 428
    assert a2["client"].post(
        f"/api/admin/wallet/withdrawals/{r1}/approve",
        headers=sprint2_env.headers_for(a2, step_up_proof=proof_r1),
        json={},
    ).status_code == 428

    # Expired proof is rejected (428)
    with sprint2_env.db() as db:
        db.execute(
            "UPDATE admin_step_up_authorizations SET issued_at = now() - interval '5 minutes', expires_at = now() - interval '2 minutes' "
            "WHERE user_id = %s AND state = 'available'",
            (admin1["id"],),
        )
    assert a1["client"].post(
        f"/api/admin/wallet/withdrawals/{r1}/approve",
        headers=sprint2_env.headers_for(a1, step_up_proof=proof_r1),
        json={},
    ).status_code == 428

    # Concurrent single-use replay race on process-overdue: at most one succeeds (200), one gets 428
    overdue_ch = a1["client"].post("/api/admin/delivery-confirmations/process-overdue", headers=sprint2_env.headers_for(a1), json={})
    race_proof = sprint2_env.issue_admin_proof(a1, overdue_ch.json["action"])

    def _fire_overdue(_i):
        c = sprint2_env.app.test_client()
        c.set_cookie("dtx_device_token", a1["device_token"])
        c.set_cookie("dtx_session_token", a1["session_token"])
        c.set_cookie("dtx_access_proof", a1["access_proof"])
        with c.session_transaction() as sess:
            sess["csrf_token"] = a1["csrf"]
        return c.post(
            "/api/admin/delivery-confirmations/process-overdue",
            headers=sprint2_env.headers_for(a1, step_up_proof=race_proof),
            json={},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(_fire_overdue, range(2)))
    assert outcomes == [200, 428]


def test_sec006_admin_creation_rejects_client_roles_weak_passwords_and_rolls_back_auth(sprint2_env, monkeypatch):
    admin = sprint2_env.create_user(admin=True)
    a_auth = sprint2_env.login_client(admin)

    # Rejects client-supplied privilege fields
    for forbidden in ({"role": "admin"}, {"legacy_role": "platform_admin"}, {"is_blocked": False}, {"auth_id": str(uuid4())}):
        payload = {"name": "Evil Admin", "email": f"{uuid4().hex}@sprint2.invalid", "password": "StrongAdminPass123!", **forbidden}
        resp = a_auth["client"].post("/api/admin/users", headers=sprint2_env.headers_for(a_auth), json=payload)
        assert resp.status_code == 400

    # Rejects weak or non-compliant admin passwords
    for bad_pw in ("short1!", "onlylettersonlyletters", "   StrongAdminPass123!", "A" * 129 + "1!"):
        resp = a_auth["client"].post(
            "/api/admin/users",
            headers=sprint2_env.headers_for(a_auth),
            json={"name": "Bad Pw", "email": f"{uuid4().hex}@sprint2.invalid", "password": bad_pw},
        )
        assert resp.status_code == 400

    # Compensation check: when DB profile link fails after supabase_create_user, supabase_delete_user is called
    deleted_auth_ids = []
    orphan_auth_id = str(uuid4())
    monkeypatch.setattr(
        admin_routes,
        "supabase_create_user",
        lambda *_a, **_k: type("U", (), {"id": orphan_auth_id})(),
    )
    monkeypatch.setattr(
        admin_routes,
        "supabase_delete_user",
        lambda aid: deleted_auth_ids.append(aid) or True,
    )
    target_email = f"{uuid4().hex}@sprint2.invalid"
    fail_ch = a_auth["client"].post(
        "/api/admin/users",
        headers=sprint2_env.headers_for(a_auth),
        json={"name": "Roll Back", "email": target_email, "password": "StrongAdminPass123!"},
    )
    assert fail_ch.status_code == 428
    proof = sprint2_env.issue_admin_proof(a_auth, fail_ch.json["action"])
    fail_res = a_auth["client"].post(
        "/api/admin/users",
        headers=sprint2_env.headers_for(a_auth, step_up_proof=proof),
        json={"name": "Roll Back", "email": target_email, "password": "StrongAdminPass123!"},
    )
    assert fail_res.status_code == 500
    assert deleted_auth_ids == [orphan_auth_id]

    # Genuine creation works cleanly when auth trigger creates the public user row
    good_email = f"{uuid4().hex}@sprint2.invalid"
    good_auth_id = str(uuid4())

    def _create_with_trigger(email, _pw, meta):
        with sprint2_env.db() as db:
            db.execute(
                "INSERT INTO auth.users(id, email, raw_user_meta_data) VALUES(%s, %s, %s)",
                (good_auth_id, email, Json({"full_name": meta["full_name"], "legacy_role": "service_seeker"})),
            )
        return type("U", (), {"id": good_auth_id})()

    monkeypatch.setattr(admin_routes, "supabase_create_user", _create_with_trigger)
    good_ch = a_auth["client"].post(
        "/api/admin/users",
        headers=sprint2_env.headers_for(a_auth),
        json={"name": "Trusted Ops", "email": good_email, "password": "StrongAdminPass123!"},
    )
    good_proof = sprint2_env.issue_admin_proof(a_auth, good_ch.json["action"])
    good_res = a_auth["client"].post(
        "/api/admin/users",
        headers=sprint2_env.headers_for(a_auth, step_up_proof=good_proof),
        json={"name": "Trusted Ops", "email": good_email, "password": "StrongAdminPass123!"},
    )
    assert good_res.status_code == 201, good_res.json
    assert good_res.json["user"]["role"] == "platform_admin"


def test_sec009_upload_magic_bytes_exif_stripping_and_storage_headers(sprint2_env, monkeypatch):
    from werkzeug.datastructures import FileStorage

    def _sanitize_raw(raw_bytes, ext, allowed):
        fs = FileStorage(stream=BytesIO(raw_bytes), filename=f"sample{ext}")
        _name, sanitized_fs = validate_and_sanitize_upload(
            fs, owner_prefix="sec009", allowed_extensions=allowed
        )
        sanitized_fs.stream.seek(0)
        return sanitized_fs.stream.read()

    # Direct sanitizer verification: JPEG EXIF camera/software/author metadata must be stripped
    exif_jpg = _jpeg_with_exif_bytes()
    assert b"SecretPhoneVendor" in exif_jpg
    sanitized_jpg = _sanitize_raw(exif_jpg, ".jpg", {"jpg", "jpeg", "png", "webp", "pdf"})
    assert b"SecretPhoneVendor" not in sanitized_jpg
    assert b"TrackerCam-99" not in sanitized_jpg
    assert b"PrivateAuthor" not in sanitized_jpg
    reopened = Image.open(BytesIO(sanitized_jpg))
    assert len(reopened.getexif()) == 0

    # Valid alternative formats pass
    assert _sanitize_raw(_valid_png_bytes(), ".png", {"png"})
    assert _sanitize_raw(_valid_webp_bytes(), ".webp", {"webp"})
    assert _sanitize_raw(_valid_pdf_bytes(), ".pdf", {"pdf"}) == _valid_pdf_bytes()
    assert _sanitize_raw(_valid_mp4_bytes(), ".mp4", {"mp4"}) == _valid_mp4_bytes()
    assert _sanitize_raw(_valid_mov_bytes(), ".mov", {"mov"}) == _valid_mov_bytes()

    # Spoofed/active payloads fail closed
    spoof_cases = [
        (b"MZ\x90\x00evil-pe", ".jpg", {"jpg"}),
        (b"<html><script>alert(1)</script></html>", ".png", {"png"}),
        (b"not-a-pdf-at-all", ".pdf", {"pdf"}),
        (b"%PDF-1.4\n<< /Catalog >>\nmissing-eof", ".pdf", {"pdf"}),
        (b"%PDF-1.4\n<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>\n%%EOF", ".pdf", {"pdf"}),
        (b"<html>not mp4</html>", ".mp4", {"mp4"}),
        (b"\x00\x00\x00\x18ftypexe \x00\x00\x00\x00", ".mov", {"mov"}),
    ]
    for raw_bytes, ext, allowed in spoof_cases:
        with pytest.raises(ValueError):
            _sanitize_raw(raw_bytes, ext, allowed)

    # Pixel-limit bomb guard (monkeypatch low threshold to verify fail-closed guard quickly)
    monkeypatch.setattr("shared.upload_validation.MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ValueError):
        _sanitize_raw(exif_jpg, ".jpg", {"jpg"})  # 24x24 = 576 > 100
    monkeypatch.setattr("shared.upload_validation.MAX_IMAGE_PIXELS", 25_000_000)

    # Route-level integration: chat media rejects spoofed .jpg with 400 and preserves sanitized upload + security headers
    client_u = sprint2_env.create_user("service_seeker")
    transporter_u = sprint2_env.create_user("logistics_provider")
    c_auth = sprint2_env.login_client(client_u)
    with sprint2_env.db() as db:
        thread_id = db.execute(
            "INSERT INTO chat_threads(client_user_id, transporter_user_id) VALUES(%s, %s) RETURNING id",
            (client_u["id"], transporter_u["id"]),
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO chat_messages(thread_id, sender_user_id, message_type, media_request_status) "
            "VALUES(%s, %s, 'media_request', 'approved')",
            (thread_id, client_u["id"]),
        )

    uploaded_blobs = []
    monkeypatch.setattr(storage, "upload_file_storage", lambda rel, fs: uploaded_blobs.append(rel) or rel)
    spoof_resp = c_auth["client"].post(
        f"/api/chat/threads/{thread_id}/messages/media",
        headers=sprint2_env.headers_for(c_auth),
        data={"media": (BytesIO(b"MZ_NOT_AN_IMAGE"), "fake.jpg")},
        content_type="multipart/form-data",
    )
    assert spoof_resp.status_code == 400
    assert uploaded_blobs == []

    # Valid upload strips EXIF inside chat & truck upload helpers before Supabase storage write
    captured_bytes = []

    def _capture_storage(rel, fs):
        fs.stream.seek(0)
        captured_bytes.append((rel, fs.mimetype, fs.stream.read()))
        fs.stream.seek(0)
        return rel

    monkeypatch.setattr(storage, "upload_file_storage", _capture_storage)
    ok_chat = c_auth["client"].post(
        f"/api/chat/threads/{thread_id}/messages/media",
        headers=sprint2_env.headers_for(c_auth),
        data={"media": (BytesIO(exif_jpg), "photo-with-gps.jpg")},
        content_type="multipart/form-data",
    )
    assert ok_chat.status_code == 200, ok_chat.json
    assert len(captured_bytes) == 1
    assert b"SecretPhoneVendor" not in captured_bytes[0][2]
    assert len(Image.open(BytesIO(captured_bytes[0][2])).getexif()) == 0

    truck_fs = FileStorage(stream=BytesIO(exif_jpg), filename="reg-doc.jpg", content_type="image/jpeg")
    truck_rel = truck_helpers.make_upload_relative_path(transporter_u["id"], truck_fs)
    assert truck_rel.endswith(".jpg") and len(captured_bytes) == 2
    assert b"SecretPhoneVendor" not in captured_bytes[1][2]

    # Private download sandbox headers check
    monkeypatch.setattr(storage, "download_bytes", lambda _rel: sanitized_jpg)
    admin_u = sprint2_env.create_user(admin=True)
    a_auth = sprint2_env.login_client(admin_u)
    t_auth = sprint2_env.login_client(transporter_u)
    with sprint2_env.db() as db:
        db.execute(
            "INSERT INTO vehicles(owner_user_id, truck_number, truck_type, chassis_number, capacity_tons, main_use, rc_book_photo_path) "
            "VALUES(%s, 'TRK-S2', 'Flatbed', 'CH-S2-001', 10, 'freight', %s)",
            (transporter_u["id"], "uploads/trucks/sample/reg.jpg"),
        )
    dl = t_auth["client"].get("/uploads/trucks/sample/reg.jpg")
    assert dl.status_code == 200
    assert dl.headers["Content-Security-Policy"].startswith("sandbox")
    assert dl.headers["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in dl.headers["Cache-Control"]
    # Admin authorized, non-owner denied
    assert a_auth["client"].get("/uploads/trucks/sample/reg.jpg").status_code == 200
    assert c_auth["client"].get("/uploads/trucks/sample/reg.jpg").status_code == 404


def test_sec010_pending_withdrawal_accounting_decimal_precision_idempotency_and_reconcile(sprint2_env):
    admin = sprint2_env.create_user(admin=True)
    transporter = sprint2_env.create_user("logistics_provider")
    a_auth = sprint2_env.login_client(admin)
    t_auth = sprint2_env.login_client(transporter)

    with sprint2_env.db() as db:
        wallet, w_err = wallet_helpers.get_or_create_wallet_for_user(
            db, {"id": transporter["id"], "role": "logistics_provider"}
        )
        assert w_err is None
        db.execute("UPDATE wallets SET balance = 60000.01, locked_balance = 30000.00 WHERE id = %s", (wallet["id"],))
        db.execute(
            """
            INSERT INTO transporter_profiles(
                user_id, withdrawal_tier, withdrawal_tier_expires_at,
                payout_card_brand, payout_card_last_four, payout_card_holder,
                payout_card_expiry, payout_card_bank, payout_card_token
            ) VALUES(%s, 1, '2099-01-01T00:00:00Z', 'Visa', '4242', 'Transporter', '12/29', 'HBL', 'tok_sprint2')
            ON CONFLICT (user_id) DO UPDATE SET
                withdrawal_tier = 1,
                withdrawal_tier_expires_at = '2099-01-01T00:00:00Z',
                payout_card_token = 'tok_sprint2'
            """,
            (transporter["id"],),
        )

    # Insert an unresolved pending withdrawal request of 10000.01 (leaves exact 20000.00 free above 30k lock + pending)
    with sprint2_env.db() as db:
        req_id = db.execute(
            "INSERT INTO wallet_withdrawal_requests(user_id, wallet_id, amount, status) "
            "VALUES(%s, %s, 10000.01, 'pending') RETURNING id",
            (transporter["id"], wallet["id"]),
        ).fetchone()["id"]

    # withdrawal-limits must subtract cumulative pending requests accurately
    limits = t_auth["client"].get("/api/wallet/withdrawal-limits")
    assert limits.status_code == 200
    assert Decimal(str(limits.json["pending_withdrawals"])) == Decimal("10000.01")
    assert Decimal(str(limits.json["max_withdrawable"])) == Decimal("20000.00")

    # Exceeding remaining 20000.00 by 0.01 fails cleanly (exact Decimal precision, no float 1e-9 epsilon bypass)
    d2 = step_up_service.normalize_descriptor({
        "action_key": "wallet.withdrawal.request",
        "resource_type": "wallet",
        "resource_id": wallet["id"],
        "amount_minor": 2000001,
        "currency": "PKR",
        "destination_fingerprint": step_up_service.stored_payout_destination_fingerprint("tok_sprint2"),
    })
    p2 = sprint2_env.issue_mpin_proof(transporter, t_auth, d2)
    w2 = t_auth["client"].post(
        "/api/wallet/withdraw-locked",
        headers=sprint2_env.headers_for(t_auth, mpin_proof=p2, idempotency_key="w2-key"),
        json={"amount": "20000.01"},
    )
    assert w2.status_code == 400

    # Tier 2 upgrade costs 30,000, but only 20,000 is unreserved -> must be rejected!
    du_fail = step_up_service.normalize_descriptor({
        "action_key": "wallet.withdrawal_limit.purchase",
        "resource_type": "wallet",
        "resource_id": wallet["id"],
        "amount_minor": 3000000,
        "currency": "PKR",
        "funding_source": "wallet",
    })
    pu_fail = sprint2_env.issue_mpin_proof(transporter, t_auth, du_fail)
    up_fail = t_auth["client"].post(
        "/api/wallet/upgrade-limit",
        headers=sprint2_env.headers_for(t_auth, mpin_proof=pu_fail, idempotency_key="up-fail-key"),
        json={"tier": 2, "duration_years": 3},
    )
    assert up_fail.status_code == 400

    # Exact 20000.00 Tier 1 renewal fits right in the remaining 20000.00 headroom + Idempotency-Key deduplicates!
    du_ok = step_up_service.normalize_descriptor({
        "action_key": "wallet.withdrawal_limit.purchase",
        "resource_type": "wallet",
        "resource_id": wallet["id"],
        "amount_minor": 2000000,
        "currency": "PKR",
        "funding_source": "wallet",
    })
    pu_ok = sprint2_env.issue_mpin_proof(transporter, t_auth, du_ok)
    up1 = t_auth["client"].post(
        "/api/wallet/upgrade-limit",
        headers=sprint2_env.headers_for(t_auth, mpin_proof=pu_ok, idempotency_key="up-idem-1"),
        json={"tier": 1, "duration_years": 3},
    )
    assert up1.status_code == 200, up1.json
    # Replay same Idempotency-Key returns replayed=True without consuming second fee
    up_replay = t_auth["client"].post(
        "/api/wallet/upgrade-limit",
        headers=sprint2_env.headers_for(t_auth, idempotency_key="up-idem-1"),
        json={"tier": 1, "duration_years": 3},
    )
    assert up_replay.status_code == 200 and up_replay.json["replayed"] is True
    # Different payload under same Idempotency-Key -> 409
    assert t_auth["client"].post(
        "/api/wallet/upgrade-limit",
        headers=sprint2_env.headers_for(t_auth, idempotency_key="up-idem-1"),
        json={"tier": 2, "duration_years": 3},
    ).status_code == 409

    # Remaining balance is now 40000.01 (30k security floor + 10000.01 pending -> 0.00 free)
    # Admin approval succeeds once and debits 10000.01; second attempt sees resolved (400), no double debit
    ch = a_auth["client"].post(f"/api/admin/wallet/withdrawals/{req_id}/approve", headers=sprint2_env.headers_for(a_auth), json={})
    proof_b = sprint2_env.issue_admin_proof(a_auth, ch.json["action"])
    app1 = a_auth["client"].post(
        f"/api/admin/wallet/withdrawals/{req_id}/approve",
        headers=sprint2_env.headers_for(a_auth, step_up_proof=proof_b),
        json={},
    )
    assert app1.status_code == 200, app1.json

    ch2 = a_auth["client"].post(f"/api/admin/wallet/withdrawals/{req_id}/approve", headers=sprint2_env.headers_for(a_auth), json={})
    proof_c = sprint2_env.issue_admin_proof(a_auth, ch2.json["action"])
    app2 = a_auth["client"].post(
        f"/api/admin/wallet/withdrawals/{req_id}/approve",
        headers=sprint2_env.headers_for(a_auth, step_up_proof=proof_c),
        json={},
    )
    assert app2.status_code == 400

    with sprint2_env.db() as db:
        bal = db.execute("SELECT balance FROM wallets WHERE user_id = %s", (transporter["id"],)).fetchone()["balance"]
        assert Decimal(str(bal)) == Decimal("30000.00")
        rec = reconcile(db)
        assert rec["consistent"] is True, rec

    # Concurrent pending withdrawal race + reject restoration check on separate fresh transporter
    t2 = sprint2_env.create_user("logistics_provider")
    t2_auth_a = sprint2_env.login_client(t2)
    t2_auth_b = sprint2_env.login_client(t2)
    with sprint2_env.db() as db:
        w2_row, w2_err = wallet_helpers.get_or_create_wallet_for_user(
            db, {"id": t2["id"], "role": "logistics_provider"}
        )
        assert w2_err is None
        db.execute("UPDATE wallets SET balance = 45000.00, locked_balance = 30000.00 WHERE id = %s", (w2_row["id"],))
        db.execute(
            """
            INSERT INTO transporter_profiles(
                user_id, withdrawal_tier, withdrawal_tier_expires_at,
                payout_card_brand, payout_card_last_four, payout_card_holder,
                payout_card_expiry, payout_card_bank, payout_card_token
            ) VALUES(%s, 1, '2099-01-01T00:00:00Z', 'Visa', '1111', 'T2', '12/29', 'HBL', 'tok_t2')
            ON CONFLICT (user_id) DO UPDATE SET withdrawal_tier = 1, payout_card_token = 'tok_t2'
            """,
            (t2["id"],),
        )

    race_desc = step_up_service.normalize_descriptor({
        "action_key": "wallet.withdrawal.request",
        "resource_type": "wallet",
        "resource_id": w2_row["id"],
        "amount_minor": 1000000,
        "currency": "PKR",
        "destination_fingerprint": step_up_service.stored_payout_destination_fingerprint("tok_t2"),
    })
    proof_r_a = sprint2_env.issue_mpin_proof(t2, t2_auth_a, race_desc)
    proof_r_b = sprint2_env.issue_mpin_proof(t2, t2_auth_b, race_desc)

    def _race_withdraw(args):
        idx, bundle, m_proof = args
        c = sprint2_env.app.test_client()
        c.set_cookie("dtx_device_token", bundle["device_token"])
        c.set_cookie("dtx_session_token", bundle["session_token"])
        c.set_cookie("dtx_access_proof", bundle["access_proof"])
        with c.session_transaction() as sess:
            sess["csrf_token"] = bundle["csrf"]
        return c.post(
            "/api/wallet/withdraw-locked",
            headers=sprint2_env.headers_for(bundle, mpin_proof=m_proof, idempotency_key=f"race-w-{idx}"),
            json={"amount": "10000.00"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        w_outcomes = sorted(
            pool.map(_race_withdraw, [(0, t2_auth_a, proof_r_a), (1, t2_auth_b, proof_r_b)])
        )
    assert w_outcomes == [200, 400]

    # After 10,000 approved above, 5,000 free remains; add a pending 5,000 request, then verify admin reject restores 5,000 headroom
    with sprint2_env.db() as db:
        pend_id = db.execute(
            "INSERT INTO wallet_withdrawal_requests(user_id, wallet_id, amount, status) "
            "VALUES(%s, %s, 5000.00, 'pending') RETURNING id",
            (t2["id"], w2_row["id"]),
        ).fetchone()["id"]
    lim_mid = t2_auth_a["client"].get("/api/wallet/withdrawal-limits")
    assert Decimal(str(lim_mid.json["pending_withdrawals"])) == Decimal("5000.00")
    assert Decimal(str(lim_mid.json["max_withdrawable"])) == Decimal("0.00")

    rej_ch = a_auth["client"].post(
        f"/api/admin/wallet/withdrawals/{pend_id}/reject",
        headers=sprint2_env.headers_for(a_auth),
        json={},
    )
    rej_proof = sprint2_env.issue_admin_proof(a_auth, rej_ch.json["action"])
    assert a_auth["client"].post(
        f"/api/admin/wallet/withdrawals/{pend_id}/reject",
        headers=sprint2_env.headers_for(a_auth, step_up_proof=rej_proof),
        json={},
    ).status_code == 200
    lim_after = t2_auth_a["client"].get("/api/wallet/withdrawal-limits")
    assert Decimal(str(lim_after.json["pending_withdrawals"])) == Decimal("0.00")
    assert Decimal(str(lim_after.json["max_withdrawable"])) == Decimal("5000.00")


def test_sec011_static_path_containment_and_admin_authorization(sprint2_env, tmp_path):
    # Verify blocked platform_admin cannot use admin_required or is_admin_user
    blocked_admin = sprint2_env.create_user(admin=True)
    ba_auth = sprint2_env.login_client(blocked_admin)
    with sprint2_env.db() as db:
        db.execute("UPDATE users SET is_blocked = TRUE WHERE id = %s", (blocked_admin["id"],))
    assert ba_auth["client"].get("/api/admin/operational-incidents").status_code == 401
    assert auth_helpers.is_admin_user({"role": "platform_admin", "is_blocked": True}) is False
    assert auth_helpers.is_admin_user("platform_admin") is False
    assert auth_helpers.is_admin_user({"role": "platform_admin", "is_blocked": False}) is True

    # Real Flask app static path containment via isolated subprocess pointing to sprint2_db_url
    dist = tmp_path / "dist"
    assets = dist / "assets"
    uploads = dist / "uploads"
    assets.mkdir(parents=True)
    uploads.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>SPA_INDEX</body></html>", encoding="utf-8")
    (assets / "main.js").write_text("console.log('ok');", encoding="utf-8")
    (uploads / "leak.txt").write_text("UPLOAD_LEAK", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET_ENV=DO_NOT_LEAK", encoding="utf-8")

    probe = f"""
import json
from pathlib import Path
import app as app_module

app_module.FRONTEND_DIST = Path({str(dist)!r})
c = app_module.app.test_client()
paths = [
    "/assets/main.js",
    "/admin/dashboard",
    "/../.env",
    "/..%2f.env",
    "/..%252f.env",
    "/uploads/leak.txt",
    "/UPLOADS/leak.txt",
    "/assets/missing.js",
    "/.env",
    "/foo\\\\..\\\\.env",
]
out = {{p: {{"status": c.get(p).status_code, "body": c.get(p).get_data(as_text=True)}} for p in paths}}
print(json.dumps(out))
"""
    env = dict(os.environ)
    env["SUPABASE_DB_URL"] = sprint2_env.url
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
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    assert res["/assets/main.js"]["status"] == 200
    assert "console.log('ok')" in res["/assets/main.js"]["body"]
    assert res["/admin/dashboard"]["status"] == 200
    assert "SPA_INDEX" in res["/admin/dashboard"]["body"]
    for blocked_path in (
        "/../.env",
        "/..%2f.env",
        "/..%252f.env",
        "/uploads/leak.txt",
        "/UPLOADS/leak.txt",
        "/assets/missing.js",
        "/.env",
        "/foo\\..\\.env",
    ):
        assert res[blocked_path]["status"] == 404, (blocked_path, res[blocked_path])
        assert "DO_NOT_LEAK" not in res[blocked_path]["body"]
        assert "UPLOAD_LEAK" not in res[blocked_path]["body"]
        assert "SPA_INDEX" not in res[blocked_path]["body"]
