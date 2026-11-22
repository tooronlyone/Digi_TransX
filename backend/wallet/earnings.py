"""Versioned freight earnings reporting from posted credits and remaining holds.

No balance changes occur here. An immediate tranche must not remain in pending
earnings merely because its parent escrow payment is still held until tranche 2.
"""
RULES_VERSION = 'rules-1-4-v1'


def versioned_freight_earnings(db,user_id,current_month):
    credits=db.execute_exact(
        "SELECT COALESCE(SUM(amount),0) AS lifetime_credited, "
        "COALESCE(SUM(amount) FILTER(WHERE TO_CHAR(created_at AT TIME ZONE 'UTC','YYYY-MM')=%s),0) AS month_credited "
        "FROM wallet_transactions WHERE user_id=%s "
        "AND type IN ('freight_tranche1','freight_tranche2','reserve_contribution')",
        (current_month,user_id),
    ).fetchone()
    holds=db.execute_exact(
        "SELECT COALESCE(SUM(CASE WHEN fs.id IS NULL THEN p.transporter_amount "
        "WHEN fs.status IN ('pending_release','disputed') THEN fs.tranche2_amount ELSE 0 END),0) AS pending "
        "FROM payments p LEFT JOIN freight_settlements fs ON fs.payment_id=p.id "
        "WHERE p.transporter_user_id=%s AND p.business_rules_version=%s AND p.status IN ('held','disputed')",
        (user_id,RULES_VERSION),
    ).fetchone()
    earned=db.execute_exact(
        "SELECT COALESCE(SUM(net_entitlement),0) AS net_entitlement, "
        "COALESCE(SUM(reserve_contribution),0) AS reserve_contributed "
        "FROM freight_settlements WHERE transporter_user_id=%s",
        (user_id,),
    ).fetchone()
    return {**credits,**holds,**earned}
