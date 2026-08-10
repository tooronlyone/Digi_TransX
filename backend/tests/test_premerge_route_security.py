"""Bounded storage, GPS, and financial-alias security regressions."""

from contextlib import contextmanager
from io import BytesIO
import re

import pytest
from werkzeug.datastructures import FileStorage

import admin.routes as admin_routes
import agreements.routes as agreements_routes
import chat.routes as chat_routes
import auth.helpers as auth_helpers
import profile.routes as profile_routes
import shared.supabase_client as supabase_client
from chat.helpers import make_chat_upload_relative_path
import shared.storage as storage
import tracking.traccar as traccar
from trucks.helpers import make_upload_relative_path
import trucks.routes as trucks_routes


CSRF = {"X-CSRF-Token": "test-csrf-token"}


def _user(user_id, role="service_seeker"):
    return {
        "id": user_id,
        "full_name": f"User {user_id}",
        "email": f"user{user_id}@example.invalid",
        "phone": f"0300000000{user_id}",
        "cnic": f"{user_id:013d}",
        "role": role,
    }


def _register_chat_once(client):
    if "chat" not in client.application.blueprints:
        client.application.register_blueprint(chat_routes.chat_blueprint)


def _register_profile_once(client):
    if "profile" not in client.application.blueprints:
        client.application.register_blueprint(profile_routes.profile_blueprint)


def test_upload_keys_are_opaque_unique_and_reject_executable_extension(monkeypatch):
    uploaded = []
    monkeypatch.setattr(
        storage,
        "upload_file_storage",
        lambda path, _file: uploaded.append(path) or path,
    )
    original = "customer-name-secret-contract.JPG"
    chat_file = FileStorage(stream=BytesIO(b"image"), filename=original)
    chat_name = make_chat_upload_relative_path(7, chat_file)
    assert original.lower() not in chat_name.lower()
    assert re.fullmatch(r"7_[0-9a-f]{32}\.jpg", chat_name)

    truck_file_a = FileStorage(stream=BytesIO(b"image"), filename=original)
    truck_file_b = FileStorage(stream=BytesIO(b"image"), filename=original)
    path_a = make_upload_relative_path(9, truck_file_a)
    path_b = make_upload_relative_path(9, truck_file_b)
    assert path_a != path_b
    assert original.lower() not in path_a.lower()
    assert re.fullmatch(r"uploads/trucks/9_[0-9a-f]{32}\.jpg", path_a)
    with pytest.raises(ValueError):
        make_upload_relative_path(
            9, FileStorage(stream=BytesIO(b"<script>"), filename="payload.html")
        )


def test_chat_download_requires_exact_thread_relationship(client, monkeypatch):
    _register_chat_once(client)
    db = client.db
    for user_id in (1, 2, 3):
        client.login(_user(user_id))
    thread_id = db.execute(
        "insert into chat_threads(client_user_id,transporter_user_id,is_group_chat,admin_user_id) "
        "values(1,2,true,3) returning id"
    ).fetchone()["id"]
    db.execute(
        "insert into chat_messages(thread_id,sender_user_id,message_type,media_path) "
        "values(%s,1,'media','opaque.jpg')",
        (thread_id,),
    )
    db.commit()
    calls = []
    monkeypatch.setattr(storage, "download_bytes", lambda path: calls.append(path) or b"ok")

    anonymous = client.application.test_client()
    assert anonymous.get("/uploads/chat/opaque.jpg").status_code == 401
    assert calls == []
    client.login(_user(1))
    owner = client.get("/uploads/chat/opaque.jpg")
    assert owner.status_code == 200
    assert owner.headers["X-Content-Type-Options"] == "nosniff"
    client.login(_user(2, "logistics_provider"))
    assert client.get("/uploads/chat/opaque.jpg").status_code == 200
    client.login(_user(3, "platform_admin"))
    assert client.get("/uploads/chat/opaque.jpg").status_code == 200
    client.login(_user(4))
    assert client.get("/uploads/chat/opaque.jpg").status_code == 404
    assert calls == ["uploads/chat/opaque.jpg"] * 3


def test_truck_download_classifies_public_image_and_sensitive_documents(
    client, monkeypatch
):
    db = client.db
    for user_id, role in ((1, "logistics_provider"), (2, "service_seeker"), (3, "platform_admin")):
        client.login(_user(user_id, role))
    vehicle_id = db.execute(
        "insert into vehicles(owner_user_id,truck_number,truck_photo_path,insurance_photo_path) "
        "values(1,'T-1','uploads/trucks/public.jpg','uploads/trucks/private.pdf') returning id"
    ).fetchone()["id"]
    db.execute(
        "insert into documents(owner_user_id,vehicle_id,doc_type,storage_path) values"
        "(1,%s,'vehicle_photo','uploads/trucks/public.jpg'),"
        "(1,%s,'insurance','uploads/trucks/private.pdf')",
        (vehicle_id, vehicle_id),
    )
    db.commit()
    calls = []
    monkeypatch.setattr(storage, "download_bytes", lambda path: calls.append(path) or b"ok")

    anonymous = client.application.test_client()
    assert anonymous.get("/uploads/trucks/private.pdf").status_code == 401
    client.login(_user(2))
    public_image = client.get("/uploads/trucks/public.jpg")
    assert public_image.status_code == 200
    assert public_image.headers.get("Content-Disposition") is None
    assert client.get("/uploads/trucks/private.pdf").status_code == 404
    client.login(_user(1, "logistics_provider"))
    sensitive = client.get("/uploads/trucks/private.pdf")
    assert sensitive.status_code == 200
    assert sensitive.mimetype == "application/octet-stream"
    assert sensitive.headers["Content-Disposition"].startswith("attachment")
    client.login(_user(3, "platform_admin"))
    assert client.get("/uploads/trucks/private.pdf").status_code == 200
    assert calls == [
        "uploads/trucks/public.jpg",
        "uploads/trucks/private.pdf",
        "uploads/trucks/private.pdf",
    ]


def test_storage_download_exceptions_are_sanitized(client, monkeypatch, caplog):
    _register_chat_once(client)
    db = client.db
    client.login(_user(1, "logistics_provider"))
    thread_id = db.execute(
        "insert into chat_threads(client_user_id,transporter_user_id) "
        "values(1,2) returning id"
    ).fetchone()["id"]
    db.execute(
        "insert into users(id,full_name,email,phone,cnic,role,legacy_role) "
        "values(2,'User 2','user2@example.invalid','03000000002','0000000000002',"
        "'customer','service_seeker')"
    )
    db.execute(
        "insert into chat_messages(thread_id,sender_user_id,message_type,media_path) "
        "values(%s,1,'media','download.jpg')",
        (thread_id,),
    )
    vehicle_id = db.execute(
        "insert into vehicles(owner_user_id,truck_number,insurance_photo_path) "
        "values(1,'T-DL','uploads/trucks/download.pdf') returning id"
    ).fetchone()["id"]
    db.execute(
        "insert into documents(owner_user_id,vehicle_id,doc_type,storage_path) "
        "values(1,%s,'insurance','uploads/trucks/download.pdf')",
        (vehicle_id,),
    )
    db.commit()
    sentinel = "SENTINEL_STORAGE_DOWNLOAD_SECRET"
    monkeypatch.setattr(
        storage,
        "download_bytes",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(sentinel)),
    )
    chat_response = client.get("/uploads/chat/download.jpg")
    truck_response = client.get("/uploads/trucks/download.pdf")
    assert chat_response.status_code == 503
    assert truck_response.status_code == 503
    assert sentinel not in chat_response.get_data(as_text=True)
    assert sentinel not in truck_response.get_data(as_text=True)
    assert sentinel not in caplog.text


def test_password_change_otp_is_one_shot_and_provider_failure_is_sanitized(
    client, monkeypatch, caplog
):
    _register_profile_once(client)
    user = _user(1)
    user["auth_id"] = "auth-user-1"
    client.login(user)
    client.db.execute("update users set auth_id=%s where id=1", (user["auth_id"],))
    client.db.commit()
    with client.application.app_context():
        auth_helpers.create_otp_record(
            1, "password_change", "456789", user["email"]
        )
    sentinel = "SENTINEL_PASSWORD_CHANGE_PROVIDER_SECRET"
    calls = []

    def provider(*_a, **_k):
        calls.append(True)
        raise RuntimeError(sentinel)

    monkeypatch.setattr(supabase_client, "supabase_update_password", provider)
    first = client.put(
        "/api/profile/password",
        json={"otp_code": "456789", "new_password": "replacement-1"},
        headers=CSRF,
    )
    replay = client.put(
        "/api/profile/password",
        json={"otp_code": "654321", "new_password": "replacement-1"},
        headers=CSRF,
    )
    assert first.status_code == 503 and replay.status_code == 400
    assert calls == [True]
    assert sentinel not in first.get_data(as_text=True)
    assert sentinel not in replay.get_data(as_text=True)
    assert sentinel not in caplog.text


def test_password_change_email_exception_is_sanitized(client, monkeypatch, caplog):
    _register_profile_once(client)
    client.login(_user(1))
    monkeypatch.setattr(
        supabase_client, "supabase_verify_password", lambda *_a, **_k: True
    )
    sentinel = "SENTINEL_PASSWORD_CHANGE_EMAIL_SECRET"
    monkeypatch.setattr(
        profile_routes,
        "send_email",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(sentinel)),
    )
    response = client.post(
        "/api/profile/password/request-otp",
        json={"current_password": "valid-password"},
        headers=CSRF,
    )
    assert response.status_code == 503
    assert sentinel not in response.get_data(as_text=True)
    assert sentinel not in caplog.text


def test_chat_storage_upload_exception_is_sanitized(client, monkeypatch, caplog):
    _register_chat_once(client)
    db = client.db
    client.login(_user(1))
    db.execute(
        "insert into users(id,full_name,email,phone,cnic,role,legacy_role) "
        "values(2,'User 2','user2@example.invalid','03000000002','0000000000002','transporter','logistics_provider')"
    )
    thread_id = db.execute(
        "insert into chat_threads(client_user_id,transporter_user_id) values(1,2) returning id"
    ).fetchone()["id"]
    db.execute(
        "insert into chat_messages(thread_id,sender_user_id,message_type,media_request_status) "
        "values(%s,1,'media_request','approved')",
        (thread_id,),
    )
    db.commit()
    sentinel = "SENTINEL_STORAGE_PROVIDER_SECRET"
    monkeypatch.setattr(
        chat_routes,
        "get_thread_or_error",
        lambda *_a, **_k: ({"client_user_id": 1, "transporter_user_id": 2}, None),
    )
    monkeypatch.setattr(
        chat_routes,
        "get_pending_media_request_for_sender",
        lambda *_a, **_k: {"id": 1},
    )
    monkeypatch.setattr(
        storage,
        "upload_file_storage",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(sentinel)),
    )
    response = client.post(
        f"/api/chat/threads/{thread_id}/messages/media",
        data={"media": (BytesIO(b"image"), "private-name.jpg")},
        headers=CSRF,
        content_type="multipart/form-data",
    )
    assert response.status_code == 503
    assert sentinel not in response.get_data(as_text=True)
    assert sentinel not in caplog.text


def test_chat_storage_provider_runs_without_database_context(client, monkeypatch):
    _register_chat_once(client)
    db = client.db
    client.login(_user(1))
    db.execute(
        "insert into users(id,full_name,email,phone,cnic,role,legacy_role) "
        "values(2,'User 2','user2@example.invalid','03000000002','0000000000002',"
        "'transporter','logistics_provider')"
    )
    thread_id = db.execute(
        "insert into chat_threads(client_user_id,transporter_user_id) "
        "values(1,2) returning id"
    ).fetchone()["id"]
    request_id = db.execute(
        "insert into chat_messages(thread_id,sender_user_id,message_type,media_request_status) "
        "values(%s,1,'media_request','approved') returning id",
        (thread_id,),
    ).fetchone()["id"]
    db.commit()
    original = chat_routes.open_db
    active = 0

    @contextmanager
    def tracked_open_db():
        nonlocal active
        active += 1
        try:
            with original() as executor:
                yield executor
        finally:
            active -= 1

    provider_calls = []

    def provider(*_a, **_k):
        assert active == 0
        provider_calls.append(True)
        return "opaque-upload.jpg"

    monkeypatch.setattr(chat_routes, "open_db", tracked_open_db)
    monkeypatch.setattr(
        chat_routes,
        "get_thread_or_error",
        lambda *_a, **_k: ({"client_user_id": 1, "transporter_user_id": 2}, None),
    )
    monkeypatch.setattr(
        chat_routes,
        "get_pending_media_request_for_sender",
        lambda *_a, **_k: {"id": request_id},
    )
    monkeypatch.setattr(chat_routes, "make_chat_upload_relative_path", provider)
    response = client.post(
        f"/api/chat/threads/{thread_id}/messages/media",
        data={"media": (BytesIO(b"image"), "private-name.jpg")},
        headers=CSRF,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert provider_calls == [True]
    assert active == 0


def test_gps_provider_runs_without_db_and_final_write_revalidates_state(
    client, monkeypatch, caplog
):
    db = client.db
    client.login(_user(1, "logistics_provider"))
    vehicle_id = db.execute(
        "insert into vehicles(owner_user_id,truck_number,tracking_id) "
        "values(1,'GPS-1','imei-1') returning id"
    ).fetchone()["id"]
    db.commit()
    original = trucks_routes.open_db
    active = 0

    @contextmanager
    def tracked_open_db():
        nonlocal active
        active += 1
        try:
            with original() as executor:
                yield executor
        finally:
            active -= 1

    def provider(imei, number):
        assert active == 0
        assert (imei, number) == ("imei-1", "GPS-1")
        return "provider-device-1"

    monkeypatch.setattr(trucks_routes, "open_db", tracked_open_db)
    monkeypatch.setattr(trucks_routes, "register_device", provider)
    assert not trucks_routes._register_and_link_gps_device(
        vehicle_id, 1, "imei-1", "GPS-1"
    )
    assert active == 0
    assert db.execute(
        "select traccar_device_id from vehicles where id=%s", (vehicle_id,)
    ).fetchone()["traccar_device_id"] == "provider-device-1"

    db.execute("update vehicles set tracking_id='changed-concurrently' where id=%s", (vehicle_id,))
    db.commit()
    assert trucks_routes._register_and_link_gps_device(
        vehicle_id, 1, "imei-1", "GPS-1"
    )
    assert "provider-device-1" not in caplog.text
    assert "imei-1" not in caplog.text


def test_latest_position_provider_exception_is_sanitized(client, monkeypatch, caplog):
    db = client.db
    client.login(_user(1, "logistics_provider"))
    vehicle_id = db.execute(
        "insert into vehicles(owner_user_id,truck_number,traccar_device_id) "
        "values(1,'GPS-2','device-2') returning id"
    ).fetchone()["id"]
    db.commit()
    sentinel = "SENTINEL_GPS_PROVIDER_SECRET"
    monkeypatch.setattr(traccar, "GPS_PROVIDER_ENABLED", True)
    monkeypatch.setattr(
        traccar,
        "get_latest_position",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(sentinel)),
    )
    response = client.get(f"/api/trucks/{vehicle_id}/live-location")
    assert response.status_code == 200
    assert response.get_json()["reason"] == "fetch_error"
    assert sentinel not in response.get_data(as_text=True)
    assert sentinel not in caplog.text


def test_financial_aliases_and_canonical_routes_share_csrf_contract(
    client, monkeypatch
):
    if "admin" not in client.application.blueprints:
        client.application.register_blueprint(admin_routes.admin_blueprint)
    client.login(_user(1, "platform_admin"))
    calls = []

    def process(_db):
        calls.append("process")
        return {"processed": 0, "failed": 0}

    def penalties(_db):
        calls.append("penalties")
        return {"penalties_applied": 0}

    monkeypatch.setattr(agreements_routes, "run_process_payments", process)
    monkeypatch.setattr(agreements_routes, "run_apply_penalties", penalties)
    monkeypatch.setattr(admin_routes, "run_process_payments", process)
    monkeypatch.setattr(admin_routes, "run_apply_penalties", penalties)
    paths = (
        "/api/agreements/process-payments",
        "/api/agreements/apply-penalties",
        "/api/admin/payments/process",
        "/api/admin/payments/apply-penalties",
    )
    before = client.db.execute(
        "select (select count(*) from payments) p,"
        "(select count(*) from wallet_transactions) w,"
        "(select count(*) from shipment_notifications) n"
    ).fetchone()
    for path in paths:
        assert client.post(path).status_code == 403
        assert client.post(path, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    after = client.db.execute(
        "select (select count(*) from payments) p,"
        "(select count(*) from wallet_transactions) w,"
        "(select count(*) from shipment_notifications) n"
    ).fetchone()
    assert before == after and calls == []
    for path in paths:
        assert client.post(path, headers=CSRF).status_code == 200
    assert calls == ["process", "penalties", "process", "penalties"]
