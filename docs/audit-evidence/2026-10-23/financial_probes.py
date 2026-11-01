"""Offline source-isolated audit probes. Never imports app or opens a database."""
import ast
import copy
import hashlib
import json
import secrets
import re
import sys
import threading
import types
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def extract(path, names, env):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            node.decorator_list = []
            selected.append(node)
    exec(compile(ast.Module(body=selected, type_ignores=[]), path, "exec"), env)


env = dict(Decimal=Decimal, InvalidOperation=InvalidOperation,
           ROUND_HALF_UP=ROUND_HALF_UP, TWO_PLACES=Decimal(".01"),
           hashlib=hashlib, secrets=secrets)
extract("backend/shared/payments.py", {"round_money", "CheckoutError", "DummyCardProvider"}, env)
env["timestamp_bundle"] = lambda: {"display": "audit", "iso": "audit"}
env["json_response"] = lambda body, status=200: (body, status)
extract("backend/wallet/helpers.py", {
    "available_balance", "ensure_wallet_locked_balance", "ensure_wallet_unlocked_balance",
    "adjust_wallet_balance", "insert_wallet_transaction", "normalize_wallet_role",
    "minimum_required_for_role", "get_or_create_wallet_for_user"}, env)
env['TRANSPORTER_MINIMUM_REQUIRED'] = Decimal('30000')


class Db:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))


results = {}
charge = env["DummyCardProvider"]().charge(100000, card_summary={"card_last_four": "1111"})
assert charge["status"] == "succeeded"
results["provider_without_gateway"] = {"status": charge["status"], "provider": charge["provider"]}

db = Db()
buyer = {"id": 1, "user_id": 1, "balance": 0.0, "locked_balance": 0.0}
shop = {"id": 2, "user_id": 2, "balance": 0.0, "locked_balance": 0.0}
unlock = env["ensure_wallet_unlocked_balance"](db, buyer, 1, 1000)
debit = env["adjust_wallet_balance"](db, buyer, 1, -1000, "parts_purchase")
credit = env["adjust_wallet_balance"](db, shop, 2, 1000, "parts_sale")
assert unlock[1] == debit[1] == 400 and credit is None and shop["balance"] == 1000
results["ignored_settlement_errors"] = {"unlock_status": unlock[1], "debit_status": debit[1],
    "buyer_balance": buyer["balance"], "shop_balance": shop["balance"]}

initial = {"id": 1, "balance": 1000.0, "locked_balance": 0.0}
a, b = copy.deepcopy(initial), copy.deepcopy(initial)
db = Db()
assert env["ensure_wallet_locked_balance"](db, a, 1, 700) is None
assert env["ensure_wallet_locked_balance"](db, b, 1, 700) is None
updates = [params[0] for sql, params in db.calls if sql.startswith("UPDATE wallets")]
assert updates == [700.0, 700.0]
results["lost_update_reservations"] = {"funds_committed_to_orders": 1400, "last_stored_lock": updates[-1]}

env2 = {"round_money": env["round_money"], "PERMANENT_LOCK": 30000.0,
        "datetime": datetime, "TIERS": {0: {"single_max": 300000, "daily_max": 1000000}}}
extract("backend/wallet/withdrawal_limits.py", {"max_withdrawable", "get_active_tier"}, env2)
wallet = {"balance": 100000, "locked_balance": 90000}
assert env2["max_withdrawable"](wallet) == 70000
results["withdrawal_ignores_escrow"] = {"advertised_withdrawable": 70000,
    "spendable_without_breaking_locks": 10000, "post_withdrawal_balance": 30000,
    "unchanged_lock": 90000}

aware = datetime.now(timezone.utc).replace(year=2035).isoformat()
tier = env2["get_active_tier"]({"withdrawal_tier": 4, "withdrawal_tier_expires_at": aware})
assert tier == 0
results["aware_future_tier_expiry"] = {"stored_tier": 4, "computed_tier": tier}

env3 = {"Decimal": Decimal, "InvalidOperation": InvalidOperation,
        "PRODUCT_UNITS": {"liter", "piece"}, "DECIMAL_UNITS": {"liter"}}
extract("backend/shopkeeper/routes.py", {"_product_values"}, env3)
try:
    env3["_product_values"]({"name": "Oil", "price": "NaN", "stock_quantity": 1})
except InvalidOperation:
    results["nan_product_validation"] = "uncaught decimal.InvalidOperation"
else:
    raise AssertionError("Expected NaN comparison failure")

cent = Decimal(".01")
subtotals = [Decimal(".01") * Decimal(".5")] * 2
stored_items = sum(value.quantize(cent, rounding=ROUND_HALF_UP) for value in subtotals)
stored_total = sum(subtotals).quantize(cent, rounding=ROUND_HALF_UP)
assert stored_items == Decimal(".02") and stored_total == Decimal(".01")
results["pos_rounding_disagrees"] = {"stored_line_sum": str(stored_items), "stored_total": str(stored_total)}

stock, liters = Decimal("10"), Decimal("100")
assert max(Decimal("0"), stock - liters) == 0
results["fuel_oversell_clamps_stock"] = {"physical_stock": str(stock), "accepted_liters": str(liters),
    "recorded_stock": str(max(Decimal("0"), stock - liters))}

serialize_env = {}
extract("backend/marketplace/routes.py", {"serialize_order"}, serialize_env)
order = {"id": 1, "order_number": "audit", "buyer_user_id": 1, "shop_user_id": 2,
         "delivery_type": "pickup", "total_parts_amount": 1000, "delivery_fee": 0,
         "net_total": 1000, "payment_method": "wallet_escrow", "payment_status": "escrow_locked",
         "fulfillment_status": "placed", "delivery_otp": "1234", "created_at": "audit"}
assert serialize_env["serialize_order"](order)["delivery_otp"] == "1234"
results["seller_serializer_exposes_otp"] = True

# Supply an inert import module so the source service can be executed without
# importing application modules or resolving any production connection.
wallet_package = types.ModuleType('wallet')
wallet_package.__path__ = []
wallet_helpers = types.ModuleType('wallet.helpers')
wallet_helpers.adjust_wallet_balance = env['adjust_wallet_balance']
wallet_helpers.get_or_create_wallet_for_user = env['get_or_create_wallet_for_user']
sys.modules['wallet'] = wallet_package
sys.modules['wallet.helpers'] = wallet_helpers


class RefundSpy:
    def __init__(self):
        self.received_reference = 'not called'

    def refund(self, amount, reference=None, idempotency_key=None):
        self.received_reference = reference
        return {'status': 'refunded', 'reference': 'audit-refund'}


refund_payment = {'id': 22, 'status': 'held', 'trip_id': 1, 'client_user_id': 1,
                  'wallet_funded_amount': 0, 'total_card_charge': 100,
                  'provider_reference': 'original-charge-22', 'shipment_id': 1}
spy = RefundSpy()
refund_env = dict(env, _lock_payment=lambda db, payment_id: dict(refund_payment),
                  get_payment_provider=lambda: spy,
                  build_provider_idempotency_key=lambda *args: 'audit-key')
extract('backend/shared/payments.py', {'refund_one_time_payment'}, refund_env)
refund_env['refund_one_time_payment'](Db(), 22)
assert spy.received_reference is None
results['refund_discards_original_charge'] = {'stored': 'original-charge-22',
                                             'passed_to_provider': spy.received_reference}


class FakeUniqueViolation(Exception):
    pass


class ConcurrentWalletStore:
    def __init__(self):
        self.wallet = None
        self.barrier = threading.Barrier(2)
        self.lock = threading.Lock()

    def execute(self, sql, params=()):
        if sql.lstrip().startswith('SELECT'):
            with self.lock:
                snapshot = None if self.wallet is None else dict(self.wallet)
            if snapshot is None:
                self.barrier.wait(timeout=5)
            return types.SimpleNamespace(fetchone=lambda: snapshot)
        if 'INSERT INTO wallets' in sql:
            with self.lock:
                if self.wallet is not None and 'ON CONFLICT' not in sql:
                    raise FakeUniqueViolation('wallets_user_id_key')
                if self.wallet is None:
                    self.wallet = {'id': 1, 'user_id': params[0], 'role': params[1],
                                   'balance': 0, 'locked_balance': 0}
            return types.SimpleNamespace(fetchone=lambda: None)
        raise AssertionError(sql)


def concurrent_wallet_results(fn):
    store = ConcurrentWalletStore()
    outcomes = []
    def worker():
        try:
            wallet, error = fn(store, {'id': 1, 'role': 'client'})
            assert error is None and wallet['id'] == 1
            outcomes.append('success')
        except FakeUniqueViolation:
            outcomes.append('unique violation')
    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    return sorted(outcomes)


before = concurrent_wallet_results(env['get_or_create_wallet_for_user'])
assert before == ['success', 'unique violation']
markdown = (ROOT / 'PROJECT_AUDIT_REPORT.md').read_text(encoding='utf-8')
fin22 = markdown.split('### [FIN-22]', 1)[1].split('\n<a id=', 1)[0]
replacement = re.findall(r'```python\n(.*?)```', fin22, flags=re.S)[-1]
fixed_env = dict(env)
exec(compile(replacement, 'FIN22 corrected helper', 'exec'), fixed_env)
after = concurrent_wallet_results(fixed_env['get_or_create_wallet_for_user'])
assert after == ['success', 'success']
results['first_use_wallet_race'] = {'current_source': before, 'corrected_source': after}

print(json.dumps(results, indent=2))
