"""Read-only reconciliation for the new operational journal and subledgers.

This checks internal records, not bank liquidity or pre-cutover wallet openings.
Run on an approved target explicitly: python -m scripts.reconcile_business_rules.
It never repairs or recalculates historical financial records.
"""
import json
from shared.db import open_db

CHECKS = {
    'unbalanced_journals': "SELECT j.id FROM financial_journal j LEFT JOIN financial_journal_lines l ON l.journal_id=j.id GROUP BY j.id HAVING count(l.account)<2 OR sum(l.amount)<>0",
    'freight_split_mismatches': "SELECT id FROM freight_settlements WHERE gross_amount<>company_fee+net_entitlement OR net_entitlement<>fuel_credit_recovered+reserve_contribution+tranche1_amount+tranche2_amount",
    'credit_account_mismatches': "SELECT transporter_user_id FROM fuel_credit_accounts WHERE outstanding_credit<>utilized_credit-recovered_credit OR reserved_credit<0 OR outstanding_credit<0",
    'credit_voucher_reservation_mismatches': "SELECT a.transporter_user_id FROM fuel_credit_accounts a LEFT JOIN fuel_vouchers v ON v.transporter_user_id=a.transporter_user_id AND v.status IN('authorized','verified') GROUP BY a.transporter_user_id,a.reserved_credit HAVING a.reserved_credit<>coalesce(sum(v.credit_authorized),0)",
    'credit_utilization_mismatches': "SELECT a.transporter_user_id FROM fuel_credit_accounts a LEFT JOIN fuel_vouchers v ON v.transporter_user_id=a.transporter_user_id AND v.status='dispensed' GROUP BY a.transporter_user_id,a.utilized_credit HAVING a.utilized_credit<>coalesce(sum(v.credit_utilized),0)",
    'credit_recovery_mismatches': "SELECT a.transporter_user_id FROM fuel_credit_accounts a LEFT JOIN fuel_credit_events e ON e.transporter_user_id=a.transporter_user_id AND e.event_type='recover' GROUP BY a.transporter_user_id,a.recovered_credit HAVING a.recovered_credit<>coalesce(sum(e.amount),0)",
    'credit_allocation_mismatches': "SELECT a.transporter_user_id FROM fuel_credit_accounts a LEFT JOIN fuel_credit_events e ON e.transporter_user_id=a.transporter_user_id AND e.event_type='recover_allocation' GROUP BY a.transporter_user_id,a.recovered_credit HAVING a.recovered_credit<>coalesce(sum(e.amount),0)",
    'underbacked_security_reserves': "SELECT r.user_id FROM security_reserves r LEFT JOIN wallets w ON w.user_id=r.user_id WHERE w.id IS NULL OR w.locked_balance<r.balance OR w.minimum_required<r.balance",
    'underbacked_fuel_wallet_holds': "SELECT v.transporter_user_id FROM fuel_vouchers v JOIN wallets w ON w.user_id=v.transporter_user_id LEFT JOIN security_reserves s ON s.user_id=w.user_id WHERE v.status IN('authorized','verified') GROUP BY v.transporter_user_id,w.locked_balance,w.minimum_required,s.balance HAVING w.locked_balance<coalesce(s.balance,w.minimum_required)+sum(v.wallet_authorized)",
    'underbacked_platform_holds': "SELECT t.wallet_id FROM fuel_platform_treasury t JOIN wallets w ON w.id=t.wallet_id WHERE w.balance<w.locked_balance OR t.verified_liquidity<w.locked_balance OR w.locked_balance<coalesce((SELECT sum(credit_authorized) FROM fuel_vouchers WHERE status IN('authorized','verified')),0)",
}


def reconcile(db):
    results = {name: db.execute_exact(query).fetchall() for name,query in CHECKS.items()}
    return {'consistent': not any(results.values()), 'failures': results,
            'scope': 'Internal Rules1-4 records only. External bank/platform liquidity and historical wallet opening reconciliation require independent evidence.'}


def main():
    with open_db() as db:
        db.execute('SET TRANSACTION READ ONLY')
        result = reconcile(db)
    print(json.dumps(result,default=str,indent=2))
    return 0 if result['consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
