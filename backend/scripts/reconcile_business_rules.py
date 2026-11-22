"""Read-only reconciliation for the new operational journal and subledgers.

This checks internal records, not bank liquidity or pre-cutover wallet openings.
Run on an approved target explicitly: python -m scripts.reconcile_business_rules.
It never repairs or recalculates historical financial records.
"""
import json
from shared.db import open_auditor_db

CHECKS = {
    'unbalanced_journals': "SELECT j.id FROM financial_journal j LEFT JOIN financial_journal_lines l ON l.journal_id=j.id GROUP BY j.id HAVING count(l.account)<2 OR sum(l.amount)<>0",
    'freight_split_mismatches': "SELECT id FROM freight_settlements WHERE gross_amount<>company_fee+net_entitlement OR net_entitlement<>reserve_contribution+tranche1_amount+tranche2_amount",
    'underbacked_security_reserves': "SELECT r.user_id FROM security_reserves r LEFT JOIN wallets w ON w.user_id=r.user_id WHERE w.id IS NULL OR w.balance<r.balance OR w.locked_balance<r.balance OR w.minimum_required<r.balance",
    'wallet_transaction_owner_mismatches': "SELECT wt.id FROM wallet_transactions wt LEFT JOIN wallets w ON w.id=wt.wallet_id WHERE w.id IS NULL OR w.user_id<>wt.user_id",
    'security_reserve_entry_mismatches': "SELECT r.user_id FROM security_reserves r LEFT JOIN (SELECT user_id, COALESCE(sum(amount),0) AS total FROM security_reserve_entries GROUP BY user_id) e ON e.user_id=r.user_id WHERE coalesce(e.total,0)>0 AND r.balance<e.total",
    'settlement_resolution_mismatches': "SELECT fsr.settlement_id FROM freight_settlement_resolutions fsr LEFT JOIN freight_settlements fs ON fs.id=fsr.settlement_id WHERE fs.id IS NULL OR fsr.client_refund_amount+fsr.transporter_release_amount<>fs.tranche2_amount OR fs.status NOT IN ('resolved_client','released')",
}


def reconcile(db):
    results = {name: db.execute_exact(query).fetchall() for name,query in CHECKS.items()}
    return {'consistent': not any(results.values()), 'failures': results,
            'scope': 'Internal Rules1-4 records only. External bank/platform liquidity and historical wallet opening reconciliation require independent evidence.'}


def main():
    with open_auditor_db() as db:
        db.execute('SET TRANSACTION READ ONLY')
        result = reconcile(db)
    print(json.dumps(result,default=str,indent=2))
    return 0 if result['consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
