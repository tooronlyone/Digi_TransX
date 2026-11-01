"""Notification endpoint tests (FIX 4): list is own-scoped, mark-one/mark-all,
and server-side authorization. Uses the route-level app_env/client fixtures."""

CSRF = {"X-CSRF-Token": "test-csrf-token"}


def _seed(db):
    db.execute(
        "INSERT INTO users (id, full_name, email, cnic, role, legacy_role) VALUES "
        "(10, 'A', 'a@t', '1000000000010', 'customer', 'everyday_user'), "
        "(11, 'B', 'b@t', '1000000000011', 'customer', 'everyday_user')"
    )
    db.execute(
        "INSERT INTO shipment_notifications (order_id, trip_id, user_id, notification_type, message) VALUES "
        "(5, 1, 10, 'trip_started', 'Your trip started'), "
        "(5, 1, 10, 'delivery_confirmation_requested', 'Please confirm delivery'), "
        "(9, 2, 11, 'trip_started', 'Other user notification')"
    )
    db.commit()


def _unread(client):
    return client.get("/api/notifications").get_json()["unread_count"]


def test_notifications_are_owner_scoped(client):
    _seed(client.db)
    client.login({"id": 10, "role": "everyday_user"})
    body = client.get("/api/notifications").get_json()
    assert body["success"] is True
    assert body["unread_count"] == 2
    assert len(body["notifications"]) == 2
    # User A never sees user B's notification.
    assert all(n["message"] != "Other user notification" for n in body["notifications"])


def test_mark_one_and_mark_all_read(client):
    _seed(client.db)
    client.login({"id": 10, "role": "everyday_user"})
    assert _unread(client) == 2
    first = client.get("/api/notifications").get_json()["notifications"][0]["id"]
    assert client.post(f"/api/notifications/{first}/read", headers=CSRF).status_code == 200
    assert _unread(client) == 1
    assert client.post("/api/notifications/read-all", headers=CSRF).status_code == 200
    assert _unread(client) == 0


def test_mark_read_requires_csrf(client):
    _seed(client.db)
    client.login({"id": 10, "role": "everyday_user"})
    first = client.get("/api/notifications").get_json()["notifications"][0]["id"]
    resp = client.post(f"/api/notifications/{first}/read")   # no CSRF header
    assert resp.status_code == 403
    assert _unread(client) == 2                              # unchanged


def test_cannot_mark_another_users_notification(client):
    _seed(client.db)
    client.login({"id": 10, "role": "everyday_user"})
    # id 3 belongs to user B; A's UPDATE is scoped to user_id and affects nothing.
    client.post("/api/notifications/3/read", headers=CSRF)
    client.login({"id": 11, "role": "everyday_user"})
    assert _unread(client) == 1                              # B's notification still unread
