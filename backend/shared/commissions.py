"""Shared commission-policy helpers.

Single source of truth for platform commission math and for reading/creating
the immutable, versioned commission policies + Terms versions.

The active V1 policy type is ``one_time_order`` for shipment/order flows.

Business rules enforced here:
  - company share is validated as >= 0 and < 100 with at most 2 decimal places
  - transporter share is always derived server-side as 100 - company share
  - all money math uses Decimal (never binary floats)
  - policy versions are append-only; a change creates a new version and a new
    Terms version in the same database transaction (see publish flow in
    admin/routes.py)
  - accepted orders keep their saved snapshot forever;
    rows created before this feature fall back to the legacy 20/80 split
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


POLICY_TYPE_ONE_TIME = "one_time_order"
POLICY_TYPES = (POLICY_TYPE_ONE_TIME,)

POLICY_TYPE_LABELS = {
    POLICY_TYPE_ONE_TIME: "One-time Order",
}

# Legacy fallback: split used before commission policies existed. Existing
# rows are backfilled to these values by the migration; this constant only
# protects rows that somehow still have a NULL snapshot.
DEFAULT_COMPANY_SHARE_PERCENT = Decimal("20.00")

TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")

# Approved Rules 1–4 schedule. Versioned legacy commission policies remain
# readable for historical snapshots; new business-rule settlements use this
# explicit schedule rather than an unrelated mutable administrative rate.
BUSINESS_FEE_VERSION = "rules_1_4_v1"
FEE_COMPONENTS = {
    "freight": (
        ("core", "Digi_TransX Core Platform & Software Licensing Fee", "10"),
        ("tracking", "Live Satellite GPS Tracking & Fleet Security Services", "5"),
        ("payments", "Digital Payment Gateway & Secure Wallet Processing", "3"),
        ("protection", "Escrow Guarantee & Dispute Protection Fund", "2"),
    ),
    "marketplace": (
        ("infrastructure", "Marketplace Listing & Tech Infrastructure", "6"),
        ("visibility", "Digital Catalog & Search Visibility", "2"),
        ("protection", "Escrow Protection & Fraud Settlement", "2"),
    ),
    "fuel": (),
    "client": (),
}


def fee_schedule(kind):
    """Authoritative, presentation-safe approved fee schedule."""
    components = FEE_COMPONENTS[kind]
    return {
        "version": BUSINESS_FEE_VERSION,
        "percentage": format(sum((Decimal(p) for _, _, p in components), Decimal(0)), ".2f"),
        "components": [{"code": code, "label": label, "percentage": format(Decimal(percent), ".2f")}
                       for code, label, percent in components],
    }


def itemized_fee(gross_amount, kind):
    """Exact HALF_UP total with reconciled component allocation.

    Each component except the last rounds HALF_UP; the last receives the
    remainder of the rounded aggregate. Thus components always equal the total
    fee even for a one-paisa sale. All amounts are decimal strings at the API
    boundary; callers may parse them as Decimal for database arithmetic.
    """
    gross = Decimal(str(gross_amount))
    if not gross.is_finite() or gross < 0 or gross != gross.quantize(TWO_PLACES):
        raise ValueError("Fee base must be a nonnegative amount with at most two decimal places.")
    schedule = fee_schedule(kind)
    total_fee = (gross * Decimal(schedule["percentage"]) / HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    remaining = total_fee
    components = []
    for index, component in enumerate(schedule["components"]):
        amount = (remaining if index == len(schedule["components"]) - 1 else
                  min(remaining, (gross * Decimal(component["percentage"]) / HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)))
        remaining -= amount
        components.append({**component, "amount": format(amount, ".2f")})
    return {**schedule, "gross_amount": format(gross, ".2f"),
            "total_fee": format(total_fee, ".2f"), "net_amount": format(gross - total_fee, ".2f"),
            "components": components}


# ---------------------------------------------------------------------------
# Percent validation / derivation
# ---------------------------------------------------------------------------

def parse_company_share_percent(value):
    """Validate an admin-supplied company share percentage.

    Returns a Decimal quantized to 2 decimal places. Raises ValueError with a
    user-facing message on any invalid input. The transporter share is never
    accepted from the caller — use transporter_share_percent_for().
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("Company share percent is required.")
    if isinstance(value, bool):
        raise ValueError("Company share percent must be a number.")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError("Company share percent must be a valid number.")
    if not parsed.is_finite():
        raise ValueError("Company share percent must be a valid number.")
    if parsed < 0 or parsed >= 100:
        raise ValueError("Company share percent must be at least 0 and below 100.")
    if parsed != parsed.quantize(TWO_PLACES):
        raise ValueError("Company share percent supports at most two decimal places.")
    return parsed.quantize(TWO_PLACES)


def transporter_share_percent_for(company_share_percent):
    """Transporter share is always derived: 100 - company share."""
    return (HUNDRED - Decimal(str(company_share_percent))).quantize(TWO_PLACES)


# ---------------------------------------------------------------------------
# Money math (Decimal-safe)
# ---------------------------------------------------------------------------

def _round2(value):
    return Decimal(str(value or 0)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def split_final_amount(final_amount, company_share_percent=None):
    """Split a settled amount into (company_fee, transporter_amount).

    Both values are returned as 2-decimal floats. The company fee is rounded
    half-up from the percentage; the transporter amount is the exact
    remainder, so the two parts always sum to the (rounded) total.
    A None company share falls back to the legacy 20% split.
    """
    total = _round2(final_amount)
    share = (
        DEFAULT_COMPANY_SHARE_PERCENT
        if company_share_percent is None
        else Decimal(str(company_share_percent))
    )
    company_fee = (total * share / HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    transporter_amount = total - company_fee
    return float(company_fee), float(transporter_amount)


def policy_company_share(policy):
    """Company share of a policy row; a missing policy -> legacy 20% default."""
    if not policy:
        return DEFAULT_COMPANY_SHARE_PERCENT
    return Decimal(str(policy["company_share_percent"])).quantize(TWO_PLACES)


def snapshot_company_share(row):
    """Company share saved on a shipment row (legacy rows -> 20)."""
    value = (row or {}).get("company_share_percent_snapshot")
    if value is None:
        return DEFAULT_COMPANY_SHARE_PERCENT
    return Decimal(str(value)).quantize(TWO_PLACES)


# ---------------------------------------------------------------------------
# Policy / Terms persistence (append-only versions)
# ---------------------------------------------------------------------------

def get_active_policy(db, policy_type):
    """Latest published policy version for one type (None if unseeded)."""
    row = db.execute(
        "SELECT * FROM commission_policies WHERE policy_type = %s "
        "ORDER BY version_number DESC LIMIT 1",
        (policy_type,),
    ).fetchone()
    return dict(row) if row else None


def get_policy_by_id(db, policy_id):
    if not policy_id:
        return None
    row = db.execute("SELECT * FROM commission_policies WHERE id = %s", (policy_id,)).fetchone()
    return dict(row) if row else None


def list_policy_versions(db, policy_type=None):
    if policy_type:
        rows = db.execute(
            "SELECT * FROM commission_policies WHERE policy_type = %s "
            "ORDER BY version_number DESC",
            (policy_type,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM commission_policies ORDER BY policy_type ASC, version_number DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def create_policy_version(db, policy_type, company_share_percent, change_summary,
                          admin_user_id, effective_at_iso):
    """Append a new immutable policy version. Does NOT commit."""
    if policy_type not in POLICY_TYPES:
        raise ValueError("Policy type must be one_time_order.")
    company = Decimal(str(company_share_percent)).quantize(TWO_PLACES)
    transporter = transporter_share_percent_for(company)
    current = db.execute(
        "SELECT COALESCE(MAX(version_number), 0) AS latest FROM commission_policies "
        "WHERE policy_type = %s",
        (policy_type,),
    ).fetchone()
    next_version = int(current["latest"] or 0) + 1
    new_id = db.execute(
        """
        INSERT INTO commission_policies (
            policy_type, version_number, company_share_percent, transporter_share_percent,
            effective_at, change_summary, created_by_admin_user_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            policy_type,
            next_version,
            float(company),
            float(transporter),
            effective_at_iso,
            (change_summary or "").strip(),
            admin_user_id,
            effective_at_iso,
        ),
    ).fetchone()["id"]
    return get_policy_by_id(db, new_id)


def get_current_terms_version(db):
    row = db.execute(
        "SELECT * FROM terms_versions ORDER BY version_number DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_terms_version_by_number(db, version_number):
    row = db.execute(
        "SELECT * FROM terms_versions WHERE version_number = %s", (version_number,)
    ).fetchone()
    return dict(row) if row else None


def list_terms_versions(db):
    rows = db.execute("SELECT * FROM terms_versions ORDER BY version_number DESC").fetchall()
    return [dict(row) for row in rows]


def create_terms_version(db, one_time_policy_id, change_summary,
                         admin_user_id, published_at_iso):
    """Append an immutable Terms version for the one-time policy. Does NOT commit."""
    current = db.execute(
        "SELECT COALESCE(MAX(version_number), 0) AS latest FROM terms_versions"
    ).fetchone()
    next_version = int(current["latest"] or 0) + 1
    new_id = db.execute(
        """
        INSERT INTO terms_versions (
            version_number, effective_at, change_summary,
            one_time_policy_id,
            published_by_admin_user_id, published_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            next_version,
            published_at_iso,
            (change_summary or "").strip(),
            one_time_policy_id,
            admin_user_id,
            published_at_iso,
        ),
    ).fetchone()["id"]
    row = db.execute("SELECT * FROM terms_versions WHERE id = %s", (new_id,)).fetchone()
    return dict(row) if row else None


def publish_commission_change(db, policy_type, company_share_percent, change_summary,
                              admin_user_id, stamp_iso):
    """Publish a one-time commission rate and matching Terms version.

    Creates both immutable versions in the same open transaction. Does NOT
    commit — the caller owns the transaction.

    Returns {"old_policy", "new_policy", "terms_version"}.
    Raises ValueError for unknown types or a no-op rate.
    """
    if policy_type not in POLICY_TYPES:
        raise ValueError("Policy type must be one_time_order.")
    company = Decimal(str(company_share_percent)).quantize(TWO_PLACES)

    old_policy = get_active_policy(db, policy_type)
    if old_policy is not None and Decimal(str(old_policy["company_share_percent"])).quantize(TWO_PLACES) == company:
        raise ValueError(
            f"The {POLICY_TYPE_LABELS[policy_type]} company share is already "
            f"{company}% — nothing to publish."
        )

    new_policy = create_policy_version(
        db, policy_type, company, change_summary, admin_user_id, stamp_iso
    )

    terms_version = create_terms_version(
        db, new_policy["id"], change_summary, admin_user_id, stamp_iso
    )
    return {"old_policy": old_policy, "new_policy": new_policy, "terms_version": terms_version}


# ---------------------------------------------------------------------------
# Terms acknowledgements
# ---------------------------------------------------------------------------

def record_acknowledgement(db, user_id, terms_version_id, stamp_iso):
    """Idempotently record that a user reviewed a Terms version. Does NOT commit.

    Repeat acknowledgements hit the (user_id, terms_version_id) unique
    constraint and are skipped, so no duplicate rows are ever created.
    """
    db.execute(
        "INSERT INTO terms_acknowledgements (user_id, terms_version_id, acknowledged_at) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, terms_version_id) DO NOTHING",
        (user_id, terms_version_id, stamp_iso),
    )


def has_acknowledged(db, user_id, terms_version_id):
    row = db.execute(
        "SELECT id FROM terms_acknowledgements WHERE user_id = %s AND terms_version_id = %s",
        (user_id, terms_version_id),
    ).fetchone()
    return bool(row)


def changed_policy_types(current_terms, previous_terms):
    """Which policy types differ between two Terms versions."""
    if not current_terms or not previous_terms:
        return set()
    changed = set()
    if current_terms.get("one_time_policy_id") != previous_terms.get("one_time_policy_id"):
        changed.add(POLICY_TYPE_ONE_TIME)
    return changed


def requires_acknowledgement(role, terms_version_number, changed_types, acknowledged):
    """Should this user see the 'terms changed' review notice?

    - the seed version (v1) never demands review
    - already-acknowledged versions never demand review
    - only client/transporter roles are targeted at all
    """
    normalized = (role or "").strip().lower()
    affected_roles = {
        "service_seeker", "everyday_user", "client",
        "logistics_provider", "transporter",
    }
    if normalized not in affected_roles:
        return False
    if int(terms_version_number or 0) <= 1:
        return False
    if acknowledged:
        return False
    return True


def serialize_policy(policy):
    if not policy:
        return None
    return {
        "id": policy.get("id"),
        "policy_type": policy.get("policy_type"),
        "version_number": policy.get("version_number"),
        "company_share_percent": float(policy.get("company_share_percent") or 0),
        "transporter_share_percent": float(policy.get("transporter_share_percent") or 0),
        "effective_at": policy.get("effective_at"),
        "change_summary": policy.get("change_summary") or "",
        "created_by_admin_user_id": policy.get("created_by_admin_user_id"),
        "created_at": policy.get("created_at"),
    }


def serialize_terms_version(terms):
    if not terms:
        return None
    return {
        "id": terms.get("id"),
        "version_number": terms.get("version_number"),
        "effective_at": terms.get("effective_at"),
        "change_summary": terms.get("change_summary") or "",
        "one_time_policy_id": terms.get("one_time_policy_id"),
        "published_by_admin_user_id": terms.get("published_by_admin_user_id"),
        "published_at": terms.get("published_at"),
    }
