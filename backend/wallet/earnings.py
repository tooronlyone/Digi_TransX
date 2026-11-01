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
        "COALESCE(SUM(fuel_credit_recovered),0) AS fuel_credit_recovered, "
        "COALESCE(SUM(reserve_contribution),0) AS reserve_contributed "
        "FROM freight_settlements WHERE transporter_user_id=%s",
        (user_id,),
    ).fetchone()
    return {**credits,**holds,**earned}


def legacy_fuel_recovery_totals(db,user_id,current_month):
    """Offset new recovery using each legacy source's existing reporting month."""
    from decimal import Decimal
    if not db.execute("SELECT to_regclass('fuel_credit_accounts') AS relation").fetchone()['relation']:
        return {'total':Decimal('0.00'),'month':Decimal('0.00')}
    return db.execute_exact(
        "SELECT COALESCE(SUM(e.amount),0) AS total,COALESCE(SUM(e.amount) FILTER(WHERE "
        "(p.id IS NOT NULL AND TO_CHAR(p.released_at AT TIME ZONE 'UTC','YYYY-MM')=%s) "
        "OR (a.id IS NOT NULL AND a.month_year=%s)),0) AS month "
        "FROM fuel_credit_events e "
        "LEFT JOIN payments p ON e.reference='recover:legacy_freight:'||p.id::text AND p.transporter_user_id=e.transporter_user_id AND p.status='released' "
        "LEFT JOIN agreement_monthly_payments a ON e.reference='recover:agreement_monthly:'||a.id::text AND a.transporter_user_id=e.transporter_user_id AND a.status='paid' "
        "WHERE e.transporter_user_id=%s AND e.event_type='recover' AND (p.id IS NOT NULL OR a.id IS NOT NULL)",
        (current_month,current_month,user_id),
    ).fetchone()
