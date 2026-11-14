"""Test for LEDGER-019: notify() called when late penalty is debited and monthly payment fails."""
import pytest
from decimal import Decimal
import agreements.helpers as helpers


class FakeDb:
    def __init__(self, payments=None):
        self.payments = [dict(p) for p in (payments or [])]
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))
        class Result:
            def __init__(self, data):
                self._data = data
            def fetchall(self):
                return self._data
            def fetchone(self):
                return self._data[0] if self._data else None
        q = query.strip()
        if "SELECT * FROM agreement_monthly_payments WHERE status = 'pending'" in q:
            return Result(self.payments)
        if "SELECT * FROM agreement_monthly_payments WHERE status = 'failed'" in q:
            return Result(self.payments)
        if "SELECT COUNT(*) AS total FROM agreement_payment_penalties" in q:
            return Result([{"total": 1}])
        if "SELECT * FROM agreement_monthly_payments WHERE id = %s" in q:
            return Result([])
        return Result([])

    def execute_exact(self, query, params=None):
        class Result:
            def __init__(self, data):
                self._data = data
            def fetchone(self):
                return self._data
            def fetchall(self):
                return [self._data] if self._data else []
        if "SELECT * FROM agreement_monthly_payments WHERE id=%s FOR UPDATE" in query:
            p = next((p for p in self.payments if p["id"] == params[0]), None)
            return Result(p)
        return Result(None)

    def commit(self):
        pass


def test_run_process_payments_notifies_on_failure(monkeypatch):
    fake_payment = {
        "id": 101,
        "agreement_id": 5,
        "client_user_id": 20,
        "transporter_user_id": 30,
        "month_year": "2026-10",
        "final_amount": "75000.00",
        "status": "pending",
        "payment_due_date": "2026-10-01",
    }
    db = FakeDb([fake_payment])

    # Simulate process_payment_row failing (insufficient balance)
    monkeypatch.setattr(helpers, "process_payment_row", lambda db, p: False)

    notifications = []
    def fake_notify(db, order_id, trip_id, user_id, notification_type, message):
        notifications.append({
            "order_id": order_id,
            "trip_id": trip_id,
            "user_id": user_id,
            "type": notification_type,
            "message": message,
        })
        return True

    monkeypatch.setattr(helpers, "notify", fake_notify)

    result = helpers.run_process_payments(db)
    assert result["failed"] == 1
    assert len(notifications) == 1
    n = notifications[0]
    assert n["user_id"] == 20
    assert n["type"] == "agreement_payment_failed"
    assert "75,000.00" in n["message"]
    assert "Agreement #5" in n["message"]


def test_run_apply_penalties_notifies_on_penalty_debit(monkeypatch):
    fake_payment = {
        "id": 102,
        "agreement_id": 6,
        "client_user_id": 21,
        "transporter_user_id": 31,
        "month_year": "2026-10",
        "final_amount": "50000.00",
        "status": "failed",
        "payment_due_date": "2026-10-01",
    }
    db = FakeDb([fake_payment])

    monkeypatch.setattr(helpers, "get_or_create_wallet_for_user", lambda db, u: ({"id": 1}, None))
    monkeypatch.setattr(helpers, "adjust_wallet_balance", lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, "process_payment_row", lambda db, p: True)

    notifications = []
    def fake_notify(db, order_id, trip_id, user_id, notification_type, message):
        notifications.append({
            "order_id": order_id,
            "trip_id": trip_id,
            "user_id": user_id,
            "type": notification_type,
            "message": message,
        })
        return True

    monkeypatch.setattr(helpers, "notify", fake_notify)

    result = helpers.run_apply_penalties(db)
    assert result["penalties_applied"] == 1
    assert len(notifications) == 1
    n = notifications[0]
    assert n["user_id"] == 21
    assert n["type"] == "agreement_late_penalty"
    assert "5,000.00" in n["message"]
    assert "Agreement #6" in n["message"]
