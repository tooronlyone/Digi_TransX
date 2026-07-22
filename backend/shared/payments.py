"""Shared payment service — single source of truth for one-time order money.

Owns, for the whole backend:
  - money rounding (round_money) and every card-fee formula
  - the card processing fee (default 2.5%, centrally configured via the
    DIGITRANSX_CARD_FEE_PERCENT environment variable, snapshotted per payment)
  - wallet/card funding split for one-time checkout
  - dummy card validation and the replaceable payment-provider interface
  - payment quote generation and the commission/payment audit breakdown
  - the atomic checkout + start-trip workflows for one-time orders
  - saved payment methods (tokenized) and user payment preferences

One-time checkout math (additive fee — the wallet/hold receives exactly the
card-funded amount, never a grossed-up figure):
    processing_fee   = round(card_funded_amount * fee_percent / 100, 2)
    total_card_charge = card_funded_amount + processing_fee

Platform commission is computed only on the transporter's gross bid amount
via shared.commissions; the card processing fee is never commission and
never platform revenue.

Card data policy: full card numbers and CVC codes are validated in memory
only. They are never stored, never logged, and never returned. Persisted
saved methods carry only a generated provider token, brand, last four
digits, expiry and default flag. The provider token itself is backend-only:
it is never serialized into any API response.

Idempotency contract (also binding for a future real gateway):
  - Every checkout request carries a client-generated Idempotency-Key that is
    persisted on the payment row under a unique index and passed through to
    the provider's charge() call.
  - The provider MUST be idempotent per key: charging the same key twice
    returns the same charge (the dummy provider derives a deterministic
    reference from the key).
  - A real provider integration must additionally support reconciliation for
    the crash window where the provider charge succeeded but the local
    database transaction failed: on retry, look the charge up by idempotency
    key at the provider and attach it instead of charging again; a recovery
    job should sweep provider charges that have no matching payment row and
    refund or attach them.
"""

import hashlib
import os
import re
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

from auth.helpers import timestamp_bundle
from shared.commissions import (
    POLICY_TYPE_ONE_TIME,
    get_active_policy,
    get_current_terms_version,
    policy_company_share,
    split_final_amount,
    transporter_share_percent_for,
)
from shared.db import IntegrityError


TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")

DEFAULT_CARD_FEE_PERCENT = Decimal("2.5")
CARD_FEE_PERCENT_ENV = "DIGITRANSX_CARD_FEE_PERCENT"

# Wallet roles: everyday users have no wallet at all; business service
# seekers (and the legacy 'client' role) keep the existing wallet.
EVERYDAY_ROLES = {"everyday_user"}
BUSINESS_CLIENT_ROLES = {"service_seeker", "client"}


class CheckoutError(Exception):
    """Business-rule failure inside the payment workflows.

    Raising this aborts the surrounding transaction (the caller rolls back),
    so no partial mutations can survive a failed checkout.
    """

    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


# ---------------------------------------------------------------------------
# Money + fee math
# ---------------------------------------------------------------------------

def round_money(value):
    return float(Decimal(str(value or 0)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


# Largest amount the numeric(12,2) audit columns can hold.
MAX_MONEY_AMOUNT = Decimal("9999999999.99")


def parse_money_amount(value, label="Amount"):
    """Strict Decimal-based money parser for user-supplied amounts.

    Accepts finite, positive numbers with at most two decimal places, within
    the numeric storage limit. Rejects None, booleans, NaN, Infinity, zero,
    negatives, more than two decimals and oversized values. Returns a Decimal
    quantized to two places; raises ValueError with a user-facing message.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{label} is required.")
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a valid number.")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a valid number.")
    if not parsed.is_finite():
        raise ValueError(f"{label} must be a valid number.")
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    if parsed > MAX_MONEY_AMOUNT:
        raise ValueError(f"{label} is too large.")
    if parsed != parsed.quantize(TWO_PLACES):
        raise ValueError(f"{label} supports at most two decimal places.")
    return parsed.quantize(TWO_PLACES)


def parse_positive_id(value, label="Id"):
    """Strict positive-integer id parser (rejects booleans, floats, strings
    that are not plain integers)."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive whole number.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        parsed = int(value.strip())
    else:
        raise ValueError(f"{label} must be a positive whole number.")
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive whole number.")
    return parsed


def parse_optional_bool(value, label="Value", default=False):
    """Strict optional-boolean parser.

    Only a real JSON boolean (`true`/`false`) is accepted. Missing/None falls
    back to `default`; strings ("true"/"false"), numbers (0/1), arrays and
    objects are rejected. This is what stops `save_card: "false"` from being
    read as truthy (or a stray `"true"` from granting permission).
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{label} must be true or false.")


def build_provider_idempotency_key(scope, *parts):
    """Build a fixed-length, backend-scoped provider idempotency key.

    The raw client Idempotency-Key is never sent to the provider directly.
    Instead it is combined with a logical scope and non-sensitive identifiers
    (user id, order/bid ids) and hashed, so:
      - the same client key used by two users maps to different provider keys
      - the same client key used for checkout vs wallet top-up cannot collide
    Only non-sensitive identifiers are hashed — never PAN, CVC, tokens or
    other secrets. Returns 64 hex chars (well within provider length limits).
    """
    raw = ":".join([str(scope)] + [str(part) for part in parts])
    return hashlib.sha256(raw.encode()).hexdigest()


def provider_request_fingerprint(*parts):
    """Safe fingerprint of the charge parameters (amount, scope) used by the
    provider to detect a reused key with incompatible parameters. Contains no
    card data."""
    raw = ":".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")


def validate_idempotency_key(raw):
    """Validate the client-supplied Idempotency-Key header.

    Returns the key, or raises CheckoutError(400). The key is required — a
    fresh random key per retry would defeat idempotency entirely, so the
    server never invents one on the client's behalf.
    """
    key = (raw or "").strip()
    if not key:
        raise CheckoutError(
            "Idempotency-Key header is required for checkout. Generate one key per "
            "checkout attempt and reuse it for retries.",
            400, "idempotency_key_required",
        )
    if not IDEMPOTENCY_KEY_RE.fullmatch(key):
        raise CheckoutError(
            "Idempotency-Key must be 8-128 characters of letters, digits, '_', '.', ':' or '-'.",
            400, "idempotency_key_invalid",
        )
    return key


def card_processing_fee_percent():
    """Configured dummy card fee percent (default 2.5)."""
    raw = os.environ.get(CARD_FEE_PERCENT_ENV, "").strip()
    if raw:
        try:
            value = Decimal(raw)
            if value.is_finite() and 0 <= value < 100:
                return value.quantize(TWO_PLACES)
        except InvalidOperation:
            pass
    return DEFAULT_CARD_FEE_PERCENT.quantize(TWO_PLACES)


def calculate_card_processing_fee(card_funded_amount, fee_percent=None):
    """processing_fee = round(card_funded_amount * fee%, 2). Additive fee."""
    percent = Decimal(str(fee_percent)) if fee_percent is not None else card_processing_fee_percent()
    amount = Decimal(str(card_funded_amount or 0))
    fee = (amount * percent / HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return float(fee)


def calculate_total_card_charge(card_funded_amount, fee_percent=None):
    """Return (processing_fee, total_card_charge) for a card-funded amount."""
    fee = calculate_card_processing_fee(card_funded_amount, fee_percent)
    total = round_money(Decimal(str(card_funded_amount or 0)) + Decimal(str(fee)))
    return fee, total


def split_funding(bid_amount, wallet_available):
    """Split a bid into (wallet_funded, card_funded); wallet money first."""
    bid = Decimal(str(bid_amount or 0)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    available = Decimal(str(max(wallet_available or 0, 0))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    wallet_funded = min(bid, available)
    card_funded = bid - wallet_funded
    return float(wallet_funded), float(card_funded)


def calculate_gateway_fee(gross_amount):
    """Top-up semantics (existing wallet flow): fee is taken OUT of the gross
    amount and the wallet is credited with the remainder."""
    gross = Decimal(str(gross_amount or 0))
    rate = card_processing_fee_percent() / HUNDRED
    fee = (gross * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    net = gross - fee
    return round_money(fee), round_money(net)


def calculate_required_gross_for_net(net_amount_needed):
    """Top-up semantics: smallest gross that credits at least the target net."""
    net = Decimal(str(max(net_amount_needed or 0, 0)))
    if net <= 0:
        return 0.0
    rate = card_processing_fee_percent() / HUNDRED
    gross = (net / (Decimal("1") - rate)).quantize(TWO_PLACES, rounding=ROUND_CEILING)
    fee, credited = calculate_gateway_fee(gross)
    while credited + 1e-9 < round_money(net):
        gross += TWO_PLACES
        fee, credited = calculate_gateway_fee(gross)
    return round_money(gross)


# ---------------------------------------------------------------------------
# Dummy card validation + replaceable provider interface
# ---------------------------------------------------------------------------

_CARD_BRAND_PREFIXES = (
    ("4", "visa"),
    ("5", "mastercard"),
    ("34", "amex"),
    ("37", "amex"),
    ("6", "discover"),
)


def detect_card_brand(card_number_digits):
    for prefix, brand in _CARD_BRAND_PREFIXES:
        if card_number_digits.startswith(prefix):
            return brand
    return "card"


def parse_card_expiry(raw):
    """Parse an MM/YY (or MM/YYYY) expiry. Single source of truth for expiry
    validation, reused by both the checkout and payout card validators.

    Returns (month, year, None) on success or (None, None, error_message) for
    an unparseable or already-expired card.
    """
    match = re.fullmatch(r"(\d{1,2})\s*/\s*(\d{2}|\d{4})", str(raw or "").strip())
    if not match:
        return None, None, "Card expiry must be in MM/YY format."
    month = int(match.group(1))
    year = int(match.group(2))
    if year < 100:
        year += 2000
    if not 1 <= month <= 12:
        return None, None, "Card expiry month is invalid."
    today = date.today()
    if (year, month) < (today.year, today.month):
        return None, None, "This card has expired."
    return month, year, None


def validate_dummy_card(card_data):
    """Validate raw dummy-card input.

    Returns (card_summary, None) on success or (None, error_message).
    The summary NEVER contains the card number or CVC — only brand, last
    four, expiry and holder name.
    """
    data = card_data or {}
    number = re.sub(r"\D", "", str(data.get("card_number") or ""))
    if not 12 <= len(number) <= 19:
        return None, "Enter a valid card number."
    holder = str(data.get("card_holder_name") or "").strip()
    if not holder:
        return None, "Card holder name is required."
    cvc = str(data.get("card_cvc") or "").strip()
    if not re.fullmatch(r"\d{3,4}", cvc):
        return None, "Enter a valid card security code."
    month, year, expiry_error = parse_card_expiry(data.get("card_expiry"))
    if expiry_error:
        return None, expiry_error
    return (
        {
            "card_brand": detect_card_brand(number),
            "card_last_four": number[-4:],
            "expiry_month": month,
            "expiry_year": year,
            "card_holder_name": holder,
        },
        None,
    )


def validate_payout_card(card_data):
    """Validate a transporter payout-card entry (no CVC is collected for
    payout destinations). Returns (summary, None) or (None, error).

    Reuses the same number/expiry rules as validate_dummy_card; the summary
    never contains the card number — only brand, last four, expiry and the
    display labels.
    """
    data = card_data or {}
    number = re.sub(r"\D", "", str(data.get("card_number") or ""))
    if not 12 <= len(number) <= 19:
        return None, "Valid card number required (12-19 digits)."
    holder = str(data.get("card_holder") or "").strip()
    if not holder:
        return None, "Card holder name required."
    _month, _year, expiry_error = parse_card_expiry(data.get("card_expiry"))
    if expiry_error:
        return None, expiry_error
    return (
        {
            "card_brand": detect_card_brand(number),
            "card_last_four": number[-4:],
            "card_holder": holder,
            "card_expiry": str(data.get("card_expiry") or "").strip(),
            "bank": str(data.get("bank") or "").strip(),
        },
        None,
    )


class DummyCardProvider:
    """Placeholder processor. A real gateway later only needs to implement
    this same interface (tokenize + charge) and be returned from
    get_payment_provider().

    Idempotency: a scoped idempotency key is bound to a safe request
    fingerprint (never card data). The same scoped key with the same
    fingerprint returns the same charge reference (safe retry after a
    provider-success/DB-failure). The same scoped key with a DIFFERENT
    fingerprint is rejected rather than silently returning the old charge —
    the contract a real gateway must also honour server-side.
    """

    name = "dummycard"

    def __init__(self):
        # scoped_key -> fingerprint seen for that key (in-process record; a
        # real provider keeps this server-side).
        self._seen_fingerprints = {}

    def reset(self):
        """Test hook: clear the in-process idempotency record."""
        self._seen_fingerprints = {}

    def tokenize(self, card_summary):
        """Create a provider token for a validated card. The token is random —
        it encodes nothing about the card number."""
        return f"dummytok_{secrets.token_hex(12)}"

    def charge(self, amount, token=None, card_summary=None, description="",
               idempotency_key=None, fingerprint=None):
        """Charge a card (saved token or validated one-off card)."""
        if amount <= 0:
            return {"provider": self.name, "reference": None, "status": "skipped"}
        if token is None and card_summary is None:
            raise CheckoutError("A card is required for this charge.", 400, "card_required")
        if idempotency_key:
            fp = fingerprint or ""
            prior = self._seen_fingerprints.get(idempotency_key)
            if prior is not None and prior != fp:
                raise CheckoutError(
                    "This idempotency key was already used with different charge parameters.",
                    409, "provider_idempotency_conflict",
                )
            self._seen_fingerprints[idempotency_key] = fp
            digest = hashlib.sha256(f"{self.name}:{idempotency_key}".encode()).hexdigest()[:24]
            reference = f"dummych_{digest}"
        else:
            reference = f"dummych_{secrets.token_hex(12)}"
        return {
            "provider": self.name,
            "reference": reference,
            "status": "succeeded",
        }


_provider = DummyCardProvider()


def get_payment_provider():
    return _provider


# ---------------------------------------------------------------------------
# Saved payment methods + preferences
# ---------------------------------------------------------------------------

def serialize_saved_method(row):
    if not row:
        return None
    return {
        "id": row.get("id"),
        "provider_name": row.get("provider_name"),
        "card_brand": row.get("card_brand"),
        "card_last_four": row.get("card_last_four"),
        "expiry_month": row.get("expiry_month"),
        "expiry_year": row.get("expiry_year"),
        "is_default": bool(row.get("is_default")),
        "created_at": row.get("created_at"),
    }


def list_saved_methods(db, user_id):
    rows = db.execute(
        "SELECT * FROM saved_payment_methods WHERE user_id = %s AND status = 'active' "
        "ORDER BY is_default DESC, id DESC",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_saved_method(db, user_id, method_id):
    row = db.execute(
        "SELECT * FROM saved_payment_methods WHERE id = %s AND user_id = %s AND status = 'active'",
        (method_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def get_default_saved_method(db, user_id):
    row = db.execute(
        "SELECT * FROM saved_payment_methods WHERE user_id = %s AND status = 'active' AND is_default "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def create_saved_method(db, user_id, card_summary, set_default=False):
    """Persist a validated card as a tokenized saved method. Does NOT commit."""
    provider = get_payment_provider()
    token = provider.tokenize(card_summary)
    stamp = timestamp_bundle()["iso"]
    has_active = db.execute(
        "SELECT id FROM saved_payment_methods WHERE user_id = %s AND status = 'active' LIMIT 1",
        (user_id,),
    ).fetchone()
    make_default = bool(set_default or not has_active)
    if make_default:
        db.execute(
            "UPDATE saved_payment_methods SET is_default = false, updated_at = %s "
            "WHERE user_id = %s AND is_default",
            (stamp, user_id),
        )
    new_id = db.execute(
        """
        INSERT INTO saved_payment_methods (
            user_id, provider_name, provider_token, card_brand, card_last_four,
            expiry_month, expiry_year, is_default, status, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
        RETURNING id
        """,
        (
            user_id,
            provider.name,
            token,
            card_summary["card_brand"],
            card_summary["card_last_four"],
            card_summary["expiry_month"],
            card_summary["expiry_year"],
            make_default,
            stamp,
            stamp,
        ),
    ).fetchone()["id"]
    return get_saved_method(db, user_id, new_id)


def get_payment_preferences(db, user_id):
    row = db.execute(
        "SELECT * FROM user_payment_preferences WHERE user_id = %s", (user_id,)
    ).fetchone()
    if row:
        return dict(row)
    return {
        "user_id": user_id,
        "default_payment_method_id": None,
        "auto_shortfall_charge_enabled": False,
    }


def upsert_payment_preferences(db, user_id, auto_enabled=None, default_method_id=None,
                               clear_default=False):
    """Create/update the user's payment preferences. Does NOT commit."""
    stamp = timestamp_bundle()["iso"]
    current = get_payment_preferences(db, user_id)
    next_auto = current["auto_shortfall_charge_enabled"] if auto_enabled is None else bool(auto_enabled)
    if clear_default:
        next_default = None
    elif default_method_id is not None:
        next_default = default_method_id
    else:
        next_default = current["default_payment_method_id"]
    db.execute(
        """
        INSERT INTO user_payment_preferences (
            user_id, default_payment_method_id, auto_shortfall_charge_enabled, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            default_payment_method_id = excluded.default_payment_method_id,
            auto_shortfall_charge_enabled = excluded.auto_shortfall_charge_enabled,
            updated_at = excluded.updated_at
        """,
        (user_id, next_default, next_auto, stamp, stamp),
    )
    return get_payment_preferences(db, user_id)


def _method_expired(method):
    today = date.today()
    return (int(method["expiry_year"]), int(method["expiry_month"])) < (today.year, today.month)


# ---------------------------------------------------------------------------
# Quote
# ---------------------------------------------------------------------------

def normalize_client_kind(role):
    """'everyday' | 'business' | None for a client-side role string."""
    normalized = (role or "").strip().lower()
    if normalized in EVERYDAY_ROLES:
        return "everyday"
    if normalized in BUSINESS_CLIENT_ROLES:
        return "business"
    return None


def build_payment_quote(db, order, bid, user, wallet=None, truck=None):
    """Server-calculated quote for paying one bid. Never trusts client input.

    `wallet` may be passed when the caller already holds a locked row;
    otherwise the wallet is read here (business clients only).

    `truck` may be passed when the caller already holds the locked vehicle row
    (checkout); otherwise it is read here (the quote endpoint). Either way the
    truck is revalidated against the current order — an inactive, re-owned or
    no-longer-matching truck raises CheckoutError(bid_truck_unavailable, 409)
    so a quote can never be built for an unpayable bid.
    """
    # One shared validation for the comparison view, the quote and checkout.
    from orders.helpers import validate_bid_truck

    kind = normalize_client_kind(user.get("role"))
    if kind is None:
        raise CheckoutError("Client account required.", 403)

    if truck is None:
        truck_row = db.execute(
            "SELECT * FROM vehicles WHERE id = %s", (bid["truck_id"],)
        ).fetchone()
        truck = dict(truck_row) if truck_row else None
    truck_reason = validate_bid_truck(order, bid["transporter_user_id"], truck)
    if truck_reason:
        raise CheckoutError(truck_reason, 409, "bid_truck_unavailable")

    bid_amount = round_money(bid["bid_price"])
    wallet_available = 0.0
    if kind == "business":
        if wallet is None:
            row = db.execute(
                "SELECT * FROM wallets WHERE user_id = %s", (user["id"],)
            ).fetchone()
            wallet = dict(row) if row else None
        if wallet:
            wallet_available = round_money(
                (wallet.get("balance") or 0) - (wallet.get("locked_balance") or 0)
            )

    wallet_funded, card_funded = split_funding(bid_amount, wallet_available)
    fee_percent = card_processing_fee_percent()
    processing_fee, total_card_charge = calculate_total_card_charge(card_funded, fee_percent)

    policy = get_active_policy(db, POLICY_TYPE_ONE_TIME)
    company_share = policy_company_share(policy)
    commission_amount, transporter_payout = split_final_amount(bid_amount, company_share)

    default_method = None
    can_auto_charge = False
    preferences = None
    if kind == "business":
        preferences = get_payment_preferences(db, user["id"])
        default_method = get_default_saved_method(db, user["id"])
        can_auto_charge = bool(
            preferences["auto_shortfall_charge_enabled"]
            and default_method
            and not _method_expired(default_method)
        )

    return {
        "bid_id": bid["id"],
        "order_id": order["id"],
        "client_kind": kind,
        "bid_amount": bid_amount,
        "wallet_available": wallet_available,
        "wallet_funded_amount": wallet_funded,
        "card_funded_amount": card_funded,
        "processing_fee_percent": float(fee_percent),
        "processing_fee_amount": processing_fee,
        "total_card_charge": total_card_charge,
        "platform_commission_amount": commission_amount,
        "transporter_payout_amount": transporter_payout,
        "company_share_percent": float(company_share),
        "transporter_share_percent": float(transporter_share_percent_for(company_share)),
        "requires_card": card_funded > 0,
        "can_auto_charge": can_auto_charge,
        "auto_shortfall_charge_enabled": bool(preferences["auto_shortfall_charge_enabled"]) if preferences else False,
        "default_card": serialize_saved_method(default_method),
        "_policy": policy,          # internal: reused by checkout, stripped by routes
        "_wallet": wallet,          # internal
    }


def public_quote(quote):
    """Quote payload safe to return to the browser."""
    return {key: value for key, value in quote.items() if not key.startswith("_")}


# ---------------------------------------------------------------------------
# Checkout (atomic bid payment + acceptance)
# ---------------------------------------------------------------------------

def serialize_payment_summary(payment, viewer="client"):
    """Payment summary without any card data. Transporters see only the
    amounts that concern them; funding details stay with the payer."""
    if not payment:
        return None
    base = {
        "id": payment.get("id"),
        "invoice_number": payment.get("invoice_number"),
        "status": payment.get("status"),
        "bid_amount": round_money(payment.get("bid_price")),
        "held_at": payment.get("held_at"),
        "released_at": payment.get("released_at"),
    }
    if viewer == "transporter":
        base["transporter_amount"] = round_money(payment.get("transporter_amount"))
        return base
    base.update({
        "funding_source": payment.get("funding_source"),
        "wallet_funded_amount": round_money(payment.get("wallet_funded_amount")),
        "card_funded_amount": round_money(payment.get("card_funded_amount")),
        "processing_fee_percent": float(payment.get("processing_fee_percent") or 0),
        "processing_fee_amount": round_money(payment.get("processing_fee_amount")),
        "total_card_charge": round_money(payment.get("total_card_charge")) if payment.get("total_card_charge") is not None else None,
        "company_fee": round_money(payment.get("company_fee")),
        "transporter_amount": round_money(payment.get("transporter_amount")),
        "provider_name": payment.get("provider_name"),
        "provider_reference": payment.get("provider_reference"),
        "refunded_at": payment.get("refunded_at"),
    })
    return base


def get_active_payment_for_shipment(db, shipment_id, statuses=("processing", "held", "released")):
    placeholders = ",".join("%s" for _ in statuses)
    row = db.execute(
        f"SELECT * FROM payments WHERE shipment_id = %s AND status IN ({placeholders}) "
        "ORDER BY id DESC LIMIT 1",
        (shipment_id, *statuses),
    ).fetchone()
    return dict(row) if row else None


def _checkout_result(db, order_id, payment, replayed=False):
    order_row = db.execute("SELECT * FROM shipments WHERE id = %s", (order_id,)).fetchone()
    trip_row = db.execute(
        "SELECT * FROM shipment_trips WHERE id = %s", (payment["trip_id"],)
    ).fetchone()
    return {
        "order": dict(order_row) if order_row else None,
        "trip": dict(trip_row) if trip_row else None,
        "payment": dict(payment),
        "replayed": replayed,
    }


def _resolve_card_charge(db, user, kind, quote, payload, provider_key=None, fingerprint=None):
    """Decide how the card-funded portion is charged. Returns
    (charge_result, saved_method_used, card_summary_or_None).

    Never mutates money — only validates and performs the dummy charge.
    Raises CheckoutError when confirmation or card data is missing/invalid.
    `provider_key` is the backend-scoped provider idempotency key (never the
    raw client key).
    """
    provider = get_payment_provider()
    payload = payload or {}
    card_funded = quote["card_funded_amount"]
    total_charge = quote["total_card_charge"]
    raw_card = payload.get("card")

    if raw_card:
        card_summary, error = validate_dummy_card(raw_card)
        if error:
            raise CheckoutError(error, 400, "invalid_card")
        charge = provider.charge(total_charge, card_summary=card_summary,
                                 description=f"One-time order shortfall {card_funded}",
                                 idempotency_key=provider_key, fingerprint=fingerprint)
        saved = None
        if kind == "business" and payload.get("save_card"):
            saved = create_saved_method(db, user["id"], card_summary,
                                        set_default=bool(payload.get("set_default")))
        return charge, saved, card_summary

    if kind == "everyday":
        raise CheckoutError("Card details are required to pay for this order.", 400, "card_required")

    method = None
    explicit = False
    if payload.get("saved_method_id") is not None:
        try:
            method_id = parse_positive_id(payload.get("saved_method_id"), "Saved card")
        except ValueError as exc:
            raise CheckoutError(str(exc), 400, "invalid_saved_method")
        method = get_saved_method(db, user["id"], method_id)
        if not method:
            raise CheckoutError("Saved card not found.", 404, "card_not_found")
        explicit = True
    else:
        method = quote["default_card"] and get_saved_method(db, user["id"], quote["default_card"]["id"])
        if not method:
            raise CheckoutError(
                "A card is required for the remaining amount. Add a card or enter card details.",
                402, "card_required",
            )
    if _method_expired(method):
        raise CheckoutError("The selected card has expired.", 400, "card_expired")
    if not explicit and not quote["can_auto_charge"] and not payload.get("confirm_card_charge"):
        raise CheckoutError(
            "Automatic card charging is disabled. Confirm the card charge to continue.",
            402, "card_confirmation_required",
        )
    charge = provider.charge(total_charge, token=method["provider_token"],
                             description=f"One-time order shortfall {card_funded}",
                             idempotency_key=provider_key, fingerprint=fingerprint)
    return charge, method, None


def _find_replay(db, user, order_id, bid_id, idempotency_key):
    """Look up a previous checkout for this idempotency key.

    Returns the payment row for a legitimate replay, None when the key is
    unused, and raises 409 when the key was used for a DIFFERENT checkout
    (different client, shipment, or accepted bid/trip).
    """
    existing = db.execute(
        "SELECT * FROM payments WHERE idempotency_key = %s", (idempotency_key,)
    ).fetchone()
    if not existing:
        return None
    existing = dict(existing)
    trip = db.execute(
        "SELECT * FROM shipment_trips WHERE id = %s", (existing["trip_id"],)
    ).fetchone()
    if (
        existing["client_user_id"] != user["id"]
        or existing["shipment_id"] != order_id
        or not trip
        or trip["accepted_bid_id"] != bid_id
    ):
        raise CheckoutError(
            "This Idempotency-Key was already used for a different checkout.",
            409, "idempotency_key_conflict",
        )
    return existing


def perform_checkout(db, user, order_id, bid_id, payload=None, idempotency_key=None):
    """Atomic pay-and-accept workflow for a one-time order bid.

    Runs entirely inside the caller's open transaction; the caller commits.
    Any CheckoutError (or database error) leaves every row untouched once the
    caller rolls back. Returns {"order", "trip", "payment", "quote", "replayed"}.
    """
    from wallet.helpers import adjust_wallet_balance, get_or_create_wallet_for_user

    payload = dict(payload or {})
    kind = normalize_client_kind(user.get("role"))
    if kind is None:
        raise CheckoutError("Client account required.", 403)
    idempotency_key = validate_idempotency_key(idempotency_key)

    # Strict JSON booleans: "false"/"true"/0/1 are rejected so a string can
    # never be read as confirmation or permission to save a card.
    try:
        payload["save_card"] = parse_optional_bool(payload.get("save_card"), "save_card")
        payload["set_default"] = parse_optional_bool(payload.get("set_default"), "set_default")
        payload["confirm_card_charge"] = parse_optional_bool(
            payload.get("confirm_card_charge"), "confirm_card_charge"
        )
    except ValueError as exc:
        raise CheckoutError(str(exc), 400, "invalid_boolean")

    # Idempotent replay (fast path): a repeated successful request returns
    # the original result without charging again.
    replay = _find_replay(db, user, order_id, bid_id, idempotency_key)
    if replay:
        result = _checkout_result(db, order_id, replay, replayed=True)
        result["quote"] = None
        return result

    # 1-5. Lock and validate the shipment + bid.
    order_row = db.execute(
        "SELECT * FROM shipments WHERE id = %s FOR UPDATE", (order_id,)
    ).fetchone()
    if not order_row:
        raise CheckoutError("Order not found.", 404)
    order = dict(order_row)
    if order["client_user_id"] != user["id"]:
        raise CheckoutError("Access denied.", 403)

    # Recheck idempotency AFTER acquiring the shipment lock: a concurrent
    # request with the same key may have committed while we waited, and must
    # be replayed instead of failing on "order not open".
    replay = _find_replay(db, user, order_id, bid_id, idempotency_key)
    if replay:
        result = _checkout_result(db, order_id, replay, replayed=True)
        result["quote"] = None
        return result

    if order["status"] != "open":
        raise CheckoutError("This order is no longer open for checkout.", 409, "order_not_open")

    bid_row = db.execute(
        "SELECT * FROM shipment_bids WHERE id = %s AND order_id = %s FOR UPDATE",
        (bid_id, order_id),
    ).fetchone()
    if not bid_row:
        raise CheckoutError("Bid not found.", 404)
    bid = dict(bid_row)
    if bid["status"] != "pending":
        raise CheckoutError("This bid can no longer be accepted.", 409, "bid_not_pending")

    # Lock the selected vehicle row THIRD and revalidate it under the lock,
    # before any provider charge or wallet mutation. A truck that became
    # inactive / re-owned / no-longer-matching since the bid was placed aborts
    # here with 409 bid_truck_unavailable — no charge, no wallet change, no
    # accepted bid, no trip, no payment. build_payment_quote runs the shared
    # validation on this exact locked row (no duplicated validation logic).
    from orders.helpers import validate_bid_truck
    truck_row = db.execute(
        "SELECT * FROM vehicles WHERE id = %s FOR UPDATE", (bid["truck_id"],)
    ).fetchone()
    truck = dict(truck_row) if truck_row else None
    truck_reason = validate_bid_truck(order, bid["transporter_user_id"], truck)
    if truck_reason:
        raise CheckoutError(truck_reason, 409, "bid_truck_unavailable")

    # 6-7. Recalculate the full quote server-side (wallet + vehicle rows locked).
    wallet = None
    if kind == "business":
        wallet, wallet_error = get_or_create_wallet_for_user(db, user)
        if wallet_error is not None or wallet is None:
            raise CheckoutError("Wallet is not available for this account.", 403)
        locked = db.execute(
            "SELECT * FROM wallets WHERE user_id = %s FOR UPDATE", (user["id"],)
        ).fetchone()
        wallet = dict(locked)
    quote = build_payment_quote(db, order, bid, user, wallet=wallet, truck=truck)

    stamp = timestamp_bundle()
    policy = quote["_policy"]
    terms = get_current_terms_version(db)
    company_share = policy_company_share(policy)
    transporter_share = transporter_share_percent_for(company_share)

    # 8. Dummy card funding where required (validation errors abort before any
    # money moves). The provider gets a backend-scoped key, not the raw client
    # key, so the same client key can never collide across users or flows.
    charge = None
    if quote["card_funded_amount"] > 0:
        provider_key = build_provider_idempotency_key(
            "checkout", user["id"], order_id, bid_id, idempotency_key,
        )
        fingerprint = provider_request_fingerprint(
            "checkout", user["id"], order_id, bid_id, quote["total_card_charge"],
        )
        charge, _method, _summary = _resolve_card_charge(
            db, user, kind, quote, payload, provider_key=provider_key, fingerprint=fingerprint,
        )

    # Wallet mutations (business only): credit exactly the card-funded
    # shortfall, then deduct the full bid amount into the platform hold.
    if kind == "business":
        if quote["card_funded_amount"] > 0:
            credit_error = adjust_wallet_balance(
                db, wallet, user["id"], quote["card_funded_amount"], "card_shortfall_topup",
                description=f"Card shortfall funding for order #{order_id}",
                reference_id=idempotency_key,
                gross_amount=quote["total_card_charge"],
                gateway_fee=quote["processing_fee_amount"],
            )
            if credit_error is not None:
                raise CheckoutError("Card funding could not be credited.", 500)
        debit_error = adjust_wallet_balance(
            db, wallet, user["id"], -quote["bid_amount"], "order_payment",
            description=f"Payment held for order #{order_id}",
            reference_id=idempotency_key,
        )
        if debit_error is not None:
            raise CheckoutError("Insufficient wallet balance for this order.", 400)

    # 11-13. Accept the bid, reject the others, create exactly one trip.
    db.execute(
        "UPDATE shipment_bids SET status = 'accepted', updated_at = %s WHERE id = %s",
        (stamp["display"], bid_id),
    )
    db.execute(
        "UPDATE shipment_bids SET status = 'rejected', updated_at = %s "
        "WHERE order_id = %s AND id != %s AND status = 'pending'",
        (stamp["display"], order_id, bid_id),
    )
    trip_id = db.execute(
        """
        INSERT INTO shipment_trips (
            order_id, accepted_bid_id, transporter_user_id, truck_id, status, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, 'ready_to_start', %s, %s)
        RETURNING id
        """,
        (order_id, bid_id, bid["transporter_user_id"], bid["truck_id"], stamp["display"], stamp["display"]),
    ).fetchone()["id"]
    db.execute(
        "INSERT INTO shipment_no_show_tracking (trip_id, status, created_at, updated_at) "
        "VALUES (%s, 'tracking', %s, %s)",
        (trip_id, stamp["display"], stamp["display"]),
    )

    # 14. Shipment snapshot + status.
    db.execute(
        """
        UPDATE shipments
        SET status = 'ready_to_start', accepted_bid_id = %s, payment_amount = %s,
            payment_status = 'held',
            company_share_percent_snapshot = %s, transporter_share_percent_snapshot = %s,
            commission_policy_id = %s, terms_version_id = %s, updated_at = %s
        WHERE id = %s
        """,
        (
            bid_id,
            quote["bid_amount"],
            float(company_share),
            float(transporter_share),
            policy["id"] if policy else None,
            terms["id"] if terms else None,
            stamp["display"],
            order_id,
        ),
    )

    # 9-10. Held payment/audit record with commission, Terms and fee snapshots.
    funding_source = (
        "wallet" if quote["card_funded_amount"] <= 0
        else ("card" if quote["wallet_funded_amount"] <= 0 else "wallet_card")
    )
    provider = get_payment_provider()
    try:
        payment_id = db.execute(
            """
            INSERT INTO payments (
                trip_id, shipment_id, invoice_number, client_user_id, transporter_user_id,
                bid_price, company_fee, transporter_amount,
                company_share_percent, transporter_share_percent, commission_policy_id,
                terms_version_id,
                wallet_funded_amount, card_funded_amount,
                processing_fee_percent, processing_fee_amount, total_card_charge,
                funding_source, provider_name, provider_reference, idempotency_key,
                payment_method, status, held_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, 'held', %s, %s)
            RETURNING id
            """,
            (
                trip_id,
                order_id,
                f"ORD-{order_id}-{trip_id}-{datetime.now().strftime('%Y%m%d')}",
                user["id"],
                bid["transporter_user_id"],
                quote["bid_amount"],
                quote["platform_commission_amount"],
                quote["transporter_payout_amount"],
                float(company_share),
                float(transporter_share),
                policy["id"] if policy else None,
                terms["id"] if terms else None,
                quote["wallet_funded_amount"],
                quote["card_funded_amount"],
                quote["processing_fee_percent"],
                quote["processing_fee_amount"],
                quote["total_card_charge"] if quote["card_funded_amount"] > 0 else None,
                funding_source,
                provider.name if charge else None,
                (charge or {}).get("reference"),
                idempotency_key,
                funding_source,
                stamp["iso"],
                stamp["display"],
            ),
        ).fetchone()["id"]
    except IntegrityError:
        # Partial unique indexes: an active payment already exists for this
        # shipment or the idempotency key raced another request.
        raise CheckoutError("A payment for this order is already in progress.", 409, "duplicate_payment")

    payment_row = dict(db.execute("SELECT * FROM payments WHERE id = %s", (payment_id,)).fetchone())
    result = _checkout_result(db, order_id, payment_row)
    result["quote"] = public_quote(quote)
    return result


# ---------------------------------------------------------------------------
# Start trip (transporter)
# ---------------------------------------------------------------------------

def perform_start_trip(db, user, order_id, trip_id):
    """Transporter starts a paid, ready trip. Idempotent. Caller commits.

    Verifies, under row locks: the trip belongs to the order AND to the
    authenticated accepted transporter, it is the order's accepted trip/bid,
    the held payment is for exactly this shipment AND this trip, and both the
    shipment and trip are ready_to_start. Never releases the payout.
    """
    # Lock the shipment first (same order as checkout, avoiding deadlocks),
    # then the trip.
    order_row = db.execute(
        "SELECT * FROM shipments WHERE id = %s FOR UPDATE", (order_id,)
    ).fetchone()
    if not order_row:
        raise CheckoutError("Order not found.", 404)
    order = dict(order_row)

    trip_row = db.execute(
        "SELECT * FROM shipment_trips WHERE id = %s AND order_id = %s FOR UPDATE",
        (trip_id, order_id),
    ).fetchone()
    if not trip_row:
        raise CheckoutError("Trip not found.", 404)
    trip = dict(trip_row)
    if trip["transporter_user_id"] != user["id"]:
        raise CheckoutError("Access denied.", 403)

    # The trip must be the order's accepted trip (bid accepted via checkout).
    if order.get("accepted_bid_id") != trip["accepted_bid_id"]:
        raise CheckoutError("This trip is not the accepted trip for the order.", 409, "trip_not_accepted")
    accepted_bid = db.execute(
        "SELECT id, status, transporter_user_id FROM shipment_bids WHERE id = %s AND order_id = %s",
        (trip["accepted_bid_id"], order_id),
    ).fetchone()
    if not accepted_bid or accepted_bid["status"] != "accepted" \
            or accepted_bid["transporter_user_id"] != user["id"]:
        raise CheckoutError("This trip is not the accepted trip for the order.", 409, "trip_not_accepted")

    if trip["status"] == "in_progress":
        return {"trip": trip, "already_started": True}
    if trip["status"] != "ready_to_start":
        raise CheckoutError("This trip cannot be started.", 409, "trip_not_ready")
    if order["status"] != "ready_to_start":
        raise CheckoutError("This order is not ready to start.", 409, "order_not_ready")

    payment = get_active_payment_for_shipment(
        db, order_id, statuses=("processing", "held", "disputed", "released")
    )
    if not payment or payment["status"] != "held":
        raise CheckoutError("Payment for this order is not held yet.", 409, "payment_not_held")
    # The held payment must be for exactly this shipment and this trip.
    if payment["shipment_id"] != order_id or payment["trip_id"] != trip_id:
        raise CheckoutError("The held payment does not match this trip.", 409, "payment_trip_mismatch")

    stamp = timestamp_bundle()["display"]
    db.execute(
        "UPDATE shipment_trips SET status = 'in_progress', trip_started_at = %s, updated_at = %s "
        "WHERE id = %s",
        (stamp, stamp, trip_id),
    )
    db.execute(
        "UPDATE shipments SET status = 'in_progress', updated_at = %s WHERE id = %s",
        (stamp, order_id),
    )
    updated = dict(db.execute("SELECT * FROM shipment_trips WHERE id = %s", (trip_id,)).fetchone())
    return {"trip": updated, "already_started": False}


# ---------------------------------------------------------------------------
# Wallet top-up (atomic, idempotent) — single production service
# ---------------------------------------------------------------------------

def _topup_requested_amount(row, wallet_role):
    """The originally requested amount stored on a top-up transaction, per
    role semantics: business/client stores the credited amount, transporter
    stores the gross charge."""
    if wallet_role == "client":
        return round_money(row["amount"])
    return round_money(row["gross_amount"])


def _serialize_topup(row, replayed):
    return {
        "replayed": replayed,
        "gross_amount": round_money(row["gross_amount"]),
        "gateway_fee": round_money(row["gateway_fee"]),
        "net_amount": round_money(row["amount"]),
        "new_balance": round_money(row["balance_after"]),
        "provider_name": row.get("provider_name"),
        "provider_reference": row.get("provider_reference"),
    }


def _find_topup_replay(db, user_id, wallet_role, client_key, requested_amount):
    """Look up a prior top-up for this user + client key.

    Returns a serialized replay result, None if unused, or raises 409 when the
    key was used with a different amount (incompatible request).
    """
    row = db.execute(
        "SELECT * FROM wallet_transactions WHERE user_id = %s AND type = 'topup' AND reference_id = %s",
        (user_id, client_key),
    ).fetchone()
    if not row:
        return None
    row = dict(row)
    if _topup_requested_amount(row, wallet_role) != round_money(requested_amount):
        raise CheckoutError(
            "This Idempotency-Key was already used for a top-up with a different amount.",
            409, "idempotency_key_conflict",
        )
    return _serialize_topup(row, replayed=True)


def perform_wallet_topup(db, user, amount_raw, card_data, client_key):
    """Atomic, idempotent wallet top-up. Runs in the caller's transaction.

    Ordering guarantees (no mutation before validation):
      1. The Idempotency-Key is validated FIRST — before the wallet is
         created or any row is touched.
      2. The requested amount is parsed.
      3. A prior top-up for (user, key) is looked up: a same-amount replay
         returns the stored result WITHOUT requiring card data again; a
         different amount raises 409 idempotency_key_conflict with no charge.
      4. Only for a genuinely new top-up is card validation mandatory.
      5. The wallet is created/locked, the record re-checked under the lock,
         the provider charged with a backend-scoped key, and the credit +
         transaction written.

    Returns the structured result from _serialize_topup (+ "message").
    """
    from wallet.helpers import (
        adjust_wallet_balance,
        calculate_gateway_fee,
        calculate_required_gross_for_net,
        get_or_create_wallet_for_user,
        insert_wallet_transaction,
        normalize_wallet_role,
    )

    # 1. Idempotency key first — before any wallet creation or mutation.
    client_key = validate_idempotency_key(client_key)

    # 2. Stable requested amount + role semantics (no DB yet).
    try:
        amount = float(parse_money_amount(amount_raw, "Amount"))
    except ValueError as exc:
        raise CheckoutError(str(exc), 400, "invalid_amount")
    wallet_role = normalize_wallet_role(user.get("role"))
    if wallet_role is None:
        raise CheckoutError("Wallet is not available for this account role.", 403)
    user_id = user["id"]

    # 3. Replay / conflict check (read-only; never creates a wallet). A valid
    # same-amount replay returns here without needing card data.
    replay = _find_topup_replay(db, user_id, wallet_role, client_key, amount)
    if replay:
        replay["message"] = "Wallet top-up already processed."
        return replay

    # 4. New top-up: card validation is mandatory before any charge.
    card_summary, card_error = validate_dummy_card(card_data)
    if card_error:
        raise CheckoutError(card_error, 400, "invalid_card")

    # 5. Create + lock the wallet, then re-check the record under the lock.
    wallet, wallet_error = get_or_create_wallet_for_user(db, user)
    if wallet_error is not None or wallet is None:
        raise CheckoutError("Wallet is not available for this account role.", 403)
    locked = db.execute("SELECT * FROM wallets WHERE user_id = %s FOR UPDATE", (user_id,)).fetchone()
    wallet = dict(locked)

    replay = _find_topup_replay(db, user_id, wallet_role, client_key, amount)
    if replay:
        replay["message"] = "Wallet top-up already processed."
        return replay

    # Role-specific amounts from the locked wallet row.
    if wallet["role"] == "client":
        # Business/client: entered amount is the desired credit; card is
        # charged amount + processing fee.
        gateway_fee = calculate_card_processing_fee(amount)
        gross_amount = round_money(amount + gateway_fee)
        net_amount = amount
    else:
        # Transporter: legacy gross semantics kept unchanged.
        gross_amount = amount
        gateway_fee, net_amount = calculate_gateway_fee(gross_amount)
        projected_balance = round_money(wallet["balance"] + net_amount)
        if not wallet["is_minimum_met"] and projected_balance + 1e-9 < wallet["minimum_required"]:
            net_shortfall = round_money(wallet["minimum_required"] - wallet["balance"])
            required_gross = calculate_required_gross_for_net(net_shortfall)
            raise CheckoutError(
                f"Minimum balance of Rs {wallet['minimum_required']:.2f} required. "
                f"Please add at least Rs {required_gross:.2f} to meet the minimum.",
                400, "minimum_balance_required",
            )

    # Charge the provider with a backend-scoped key (never the raw client key)
    # bound to a safe fingerprint.
    provider = get_payment_provider()
    provider_key = build_provider_idempotency_key("wallet-topup", user_id, client_key)
    fingerprint = provider_request_fingerprint("wallet-topup", user_id, gross_amount)
    charge = provider.charge(
        gross_amount, card_summary=card_summary,
        description="Wallet top-up", idempotency_key=provider_key, fingerprint=fingerprint,
    )

    stamp = timestamp_bundle()["display"]
    new_balance = round_money(wallet["balance"] + net_amount)
    is_minimum_met = bool(wallet["is_minimum_met"] or new_balance + 1e-9 >= wallet["minimum_required"])
    current_locked_balance = round_money(wallet["locked_balance"])
    should_restore_minimum_lock = (
        wallet["role"] == "transporter"
        and new_balance + 1e-9 >= wallet["minimum_required"]
        and current_locked_balance + 1e-9 < round_money(wallet["minimum_required"])
    )
    balance_error = adjust_wallet_balance(
        db, wallet, user_id, net_amount, "topup",
        description="Wallet top-up", reference_id=client_key,
        gross_amount=gross_amount, gateway_fee=gateway_fee,
        provider_name=charge.get("provider"), provider_reference=charge.get("reference"),
    )
    if balance_error is not None:
        raise CheckoutError("Wallet top-up could not be credited.", 500, "topup_failed")
    db.execute(
        "UPDATE wallets SET is_minimum_met = %s, updated_at = %s WHERE id = %s AND user_id = %s",
        (is_minimum_met, stamp, wallet["id"], user_id),
    )
    wallet["is_minimum_met"] = is_minimum_met
    wallet["updated_at"] = stamp
    if should_restore_minimum_lock:
        target_lock = round_money(wallet["minimum_required"])
        lock_delta = round_money(target_lock - current_locked_balance)
        db.execute(
            "UPDATE wallets SET locked_balance = %s, updated_at = %s WHERE id = %s AND user_id = %s",
            (target_lock, stamp, wallet["id"], user_id),
        )
        wallet["locked_balance"] = target_lock
        wallet["updated_at"] = stamp
        insert_wallet_transaction(
            db, wallet, user_id, "lock", lock_delta,
            description="Transporter minimum security deposit locked",
            reference_id="minimum_security_deposit",
        )

    return {
        "replayed": False,
        "message": "Wallet topped up successfully",
        "gross_amount": round_money(gross_amount),
        "gateway_fee": round_money(gateway_fee),
        "net_amount": round_money(net_amount),
        "new_balance": new_balance,
        "provider_name": charge.get("provider"),
        "provider_reference": charge.get("reference"),
    }
