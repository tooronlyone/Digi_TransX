"""Shared client-role classification — the single source of truth for the
everyday-vs-business distinction.

`normalize_client_kind` lives here (not inside a payments or agreements module)
so every layer — signup, order creation, payments, agreements authorization —
classifies a client the same way with exactly one implementation. Transporter
and other non-client roles classify as None.
"""

# Everyday individuals: simple one-time orders only. No wallet, saved cards,
# auto-shortfall preference, or agreements.
EVERYDAY_ROLES = {"everyday_user"}

# Business service seekers (and the legacy 'client' role): wallet-first
# checkout, saved cards, auto-shortfall, one-time orders AND agreements.
BUSINESS_CLIENT_ROLES = {"service_seeker", "client"}

# Any client role (either kind) — the set allowed to post/track one-time orders.
CLIENT_ROLES = EVERYDAY_ROLES | BUSINESS_CLIENT_ROLES

# The two stable snapshot values written onto a shipment at creation time.
SEEKER_KIND_EVERYDAY = "everyday"
SEEKER_KIND_BUSINESS = "business"
SEEKER_KINDS = (SEEKER_KIND_EVERYDAY, SEEKER_KIND_BUSINESS)


def normalize_client_kind(role):
    """Return 'everyday', 'business', or None for a client-side role string.

    None means the role is not a client (e.g. transporter/admin) — callers use
    that to reject non-clients.
    """
    normalized = (role or "").strip().lower()
    if normalized in EVERYDAY_ROLES:
        return SEEKER_KIND_EVERYDAY
    if normalized in BUSINESS_CLIENT_ROLES:
        return SEEKER_KIND_BUSINESS
    return None


def is_business_client(role):
    """True only for business service seekers (wallet / cards / agreements)."""
    return normalize_client_kind(role) == SEEKER_KIND_BUSINESS


def is_everyday_client(role):
    """True only for everyday individual users."""
    return normalize_client_kind(role) == SEEKER_KIND_EVERYDAY
