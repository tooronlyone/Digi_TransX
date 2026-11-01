"""Exact, balanced postings; the caller owns the PostgreSQL transaction.

Accounts are operational subledger buckets, not invented historical balances.
Signed amounts describe movements between those buckets. Historical operations
retain their existing records; this journal starts at the versioned cutover.
"""
from collections import defaultdict
from decimal import Decimal
from decimal import InvalidOperation
import hashlib
import json

CENT = Decimal("0.01")


def money(value):
    if isinstance(value, (bool, float)):
        raise ValueError("Financial arithmetic requires decimal text, integers or Decimal.")
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Money must be valid decimal text.") from exc
    if not amount.is_finite() or amount != amount.quantize(CENT):
        raise ValueError("Money must be finite with at most two decimal places.")
    return amount.quantize(CENT)


def post_journal(db, key, kind, reference, lines):
    """Post once, reject incompatible replays and unbalanced transactions."""
    totals = defaultdict(lambda: Decimal("0.00"))
    for account, amount in lines:
        if not isinstance(account, str) or not 1 <= len(account) <= 200:
            raise ValueError("Invalid financial account.")
        totals[account] += money(amount)
    legs = sorted((account, amount) for account, amount in totals.items() if amount)
    if len(legs) < 2 or sum((amount for _, amount in legs), Decimal(0)) != 0:
        raise ValueError("A financial journal requires at least two balanced legs.")
    encoded = json.dumps([kind, str(reference), [(a, str(v)) for a, v in legs]], separators=(",", ":"))
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    row = db.execute_exact(
        "INSERT INTO financial_journal(idempotency_key,kind,reference,payload_hash) "
        "VALUES(%s,%s,%s,%s) ON CONFLICT(idempotency_key) DO NOTHING RETURNING id",
        (key, kind, str(reference), fingerprint),
    ).fetchone()
    if not row:
        prior = db.execute_exact("SELECT id,payload_hash FROM financial_journal WHERE idempotency_key=%s", (key,)).fetchone()
        if not prior or prior["payload_hash"] != fingerprint:
            raise ValueError("Financial idempotency key was reused for a different operation.")
        return prior["id"]
    for account, amount in legs:
        db.execute_exact("INSERT INTO financial_journal_lines(journal_id,account,amount) VALUES(%s,%s,%s)",
                         (row["id"], account, amount))
    return row["id"]
