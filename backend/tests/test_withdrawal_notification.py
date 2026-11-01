"""Test for LEDGER-018: withdrawal decisions notify requester with amount after commit."""
import pytest
from flask import Flask, request
from decimal import Decimal
import admin.routes as admin_routes
from shared.payments import DummyCardProvider


class FakeDb:
    def __init__(self, request_row, wallet_row, user_row):
        self.request_row = dict(request_row)
        self.wallet_row = dict(wallet_row)
        self.user_row = dict(user_row)
        self.committed = False
        self.commits_count = 0
        self.executed_queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, query, params=None):
        self.executed_queries.append((query, params))
        class Result:
            def __init__(self, data=None, rowcount=1):
                self._data = data
                self.rowcount = rowcount
            def fetchone(self):
                return self._data
            def fetchall(self):
                return [self._data] if self._data else []
        q = query.strip()
        if "SELECT * FROM wallet_withdrawal_requests" in q:
            return Result(self.request_row)
        if "SELECT id, role, legacy_role FROM users" in q:
            return Result(self.user_row)
        if "SELECT * FROM wallets WHERE" in q:
            return Result(self.wallet_row)
        if "UPDATE wallets SET balance" in q:
            return Result(self.wallet_row)
        if "UPDATE wallet_withdrawal_requests" in q:
            return Result(None, rowcount=1)
        if "INSERT INTO wallet_transactions" in q:
            return Result(None, rowcount=1)
        return Result(None)

    def execute_exact(self, query, params=None):
        return self.execute(query, params)

    def commit(self):
        self.committed = True
        self.commits_count += 1


def test_approve_withdrawal_calls_notify(monkeypatch):
    app = Flask(__name__)
    fake_db = FakeDb(
        request_row={"id": 1, "user_id": 42, "amount": "5000.00", "status": "pending"},
        wallet_row={"id": 10, "user_id": 42, "balance": Decimal("50000"), "locked_balance": Decimal("0")},
        user_row={"id": 42, "role": "transporter", "legacy_role": "transporter"},
    )
    monkeypatch.setattr(admin_routes, "open_db", lambda: fake_db)
    monkeypatch.setattr(admin_routes, "csrf_error", lambda: None)
    monkeypatch.setattr(admin_routes, "get_payment_provider", lambda: DummyCardProvider())
    monkeypatch.setattr(admin_routes, "get_or_create_wallet_for_user", lambda db, u: (fake_db.wallet_row, None))

    notifications_called = []
    commit_at_notify = []

    def fake_notify(db, order_id, trip_id, user_id, notification_type, message):
        notifications_called.append({
            "order_id": order_id,
            "trip_id": trip_id,
            "user_id": user_id,
            "type": notification_type,
            "message": message,
        })
        commit_at_notify.append(fake_db.committed)
        return True

    monkeypatch.setattr(admin_routes, "notify", fake_notify)

    with app.test_request_context("/api/admin/wallet/withdrawals/1/approve", method="POST"):
        request.current_user = {"id": 99, "role": "platform_admin"}
        res = admin_routes.approve_withdrawal.__wrapped__(1)

    assert res.status_code == 200
    assert len(notifications_called) == 1
    assert commit_at_notify[0] is True  # DB transaction succeeded before notify
    notif = notifications_called[0]
    assert notif["user_id"] == 42
    assert notif["type"] == "withdrawal_approved"
    assert "5,000.00" in notif["message"]


def test_reject_withdrawal_calls_notify(monkeypatch):
    app = Flask(__name__)
    fake_db = FakeDb(
        request_row={"id": 2, "user_id": 43, "amount": "2500.00", "status": "pending"},
        wallet_row={"id": 11, "user_id": 43, "balance": Decimal("5000"), "locked_balance": Decimal("0")},
        user_row={"id": 43, "role": "transporter", "legacy_role": "transporter"},
    )
    monkeypatch.setattr(admin_routes, "open_db", lambda: fake_db)
    monkeypatch.setattr(admin_routes, "csrf_error", lambda: None)

    notifications_called = []
    commit_at_notify = []

    def fake_notify(db, order_id, trip_id, user_id, notification_type, message):
        notifications_called.append({
            "order_id": order_id,
            "trip_id": trip_id,
            "user_id": user_id,
            "type": notification_type,
            "message": message,
        })
        commit_at_notify.append(fake_db.committed)
        return True

    monkeypatch.setattr(admin_routes, "notify", fake_notify)

    with app.test_request_context("/api/admin/wallet/withdrawals/2/reject", method="POST"):
        request.current_user = {"id": 99, "role": "platform_admin"}
        res = admin_routes.reject_withdrawal.__wrapped__(2)

    assert res.status_code == 200
    assert len(notifications_called) == 1
    assert commit_at_notify[0] is True  # DB transaction succeeded before notify
    notif = notifications_called[0]
    assert notif["user_id"] == 43
    assert notif["type"] == "withdrawal_rejected"
    assert "2,500.00" in notif["message"]
