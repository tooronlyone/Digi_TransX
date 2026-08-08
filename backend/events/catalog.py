"""Single machine-readable owner for the canonical event catalog."""

from dataclasses import dataclass
import re


SECURITY = "security"
BUSINESS_AUDIT = "business_audit"
OPERATIONS = "operations"

PLANNED = "planned"
DEFERRED = "deferred"

SECURITY_RETENTION = "security_12_months"
SECURITY_HIGH_RETENTION = "security_24_months"
BUSINESS_RETENTION = "business_24_months"
FINANCIAL_RETENTION = "financial_7_years"
OPERATIONS_RETENTION = "operations_90_days"


@dataclass(frozen=True)
class EventDefinition:
    name: str
    category: str
    version: int
    retention_class: str
    ownership_domain: str
    lifecycle_status: str
    writable: bool
    integrated: bool = False
    allowed_result_codes: frozenset[str] | None = None
    actor_policy: str = "generic"
    allowed_metadata_keys: frozenset[str] = frozenset()


_SECURITY_NAMES = (
    "security.signup.started",
    "security.signup.failed",
    "security.signup.gps_result_recorded",
    "security.signup.email_otp_sent",
    "security.signup.email_otp_failed",
    "security.signup.completed",
    "security.login.started",
    "security.login.failed",
    "security.login.gps_result_recorded",
    "security.login.email_otp_sent",
    "security.login.email_otp_failed",
    "security.login.succeeded",
    "security.login.new_device_detected",
    "security.login.suspicious_detected",
    "security.session.refreshed",
    "security.session.expired_inactivity",
    "security.session.revoked",
    "security.logout.completed",
    "security.password.changed",
    "security.password_reset.requested",
    "security.password_reset.completed",
    "security.trusted_device.added",
    "security.trusted_device.removed",
    "security.account.locked",
    "security.account.unlocked",
    "security.session.issued",
    "security.session.access_locked",
    "security.trusted_device.rotated",
    "security.mpin.enrolled",
    "security.mpin.changed",
    "security.mpin.disabled",
    "security.mpin.unlock_succeeded",
    "security.mpin.unlock_failed",
    "security.mpin.locked",
    "security.mpin.reset_completed",
    "security.mpin.step_up_succeeded",
    "security.mpin.step_up_failed",
)

_BUSINESS_NAMES = (
    "one_time.order.created",
    "one_time.order.updated",
    "one_time.order.cancelled",
    "one_time.order.expired",
    "one_time.order.reopened",
    "one_time.bid.submitted",
    "one_time.bid.updated",
    "one_time.bid.withdrawn",
    "one_time.bid.accepted",
    "one_time.bid.rejected",
    "one_time.bid.expired",
    "one_time.checkout.completed",
    "one_time.checkout.cancelled",
    "one_time.checkout.reversed",
    "one_time.payment.held",
    "one_time.payment.disputed",
    "one_time.payment.released",
    "one_time.payment.refunded",
    "one_time.payment.reversal_recorded",
    "one_time.payment.provider_webhook_applied",
    "wallet.topup.completed",
    "wallet.order_funding.debited",
    "wallet.card_shortfall.credited",
    "wallet.order_refund.credited",
    "wallet.transporter_payout.credited",
    "wallet.withdrawal.requested",
    "wallet.withdrawal.approved",
    "wallet.withdrawal.rejected",
    "wallet.security_lock.enabled",
    "wallet.security_lock.disabled",
    "commission.policy.created",
    "commission.policy.scheduled",
    "commission.policy.activated",
    "commission.policy.deactivated",
    "commission.policy.activation_cancelled",
    "terms.version.created",
    "terms.version.published",
    "terms.version.retired",
    "terms.version.publication_cancelled",
    "terms.acknowledgement.recorded",
    "terms.acknowledgement.reconfirmed",
    "one_time.trip.created",
    "one_time.trip.started",
    "one_time.delivery.completion_requested",
    "one_time.delivery.confirmed",
    "one_time.delivery.rejected",
    "one_time.delivery.confirmation_timed_out",
    "one_time.trip.completed",
    "one_time.trip.resolved_client",
    "one_time.dispute.opened",
    "one_time.dispute.transporter_statement_submitted",
    "one_time.dispute.admin_reviewed",
    "one_time.dispute.resolved_transporter_win",
    "one_time.dispute.resolved_client_win",
    "one_time.dispute.evidence_accessed",
    "one_time.chat.thread_created",
    "one_time.chat.message_sent",
    "one_time.chat.message_read",
    "one_time.chat.thread_closed",
    "one_time.review.submitted",
    "one_time.review.replay_detected",
    "one_time.review.moderated",
    "transporter.profile.created",
    "transporter.profile.updated",
    "transporter.profile.status_changed",
    "transporter.profile.verification_submitted",
    "transporter.profile.verified",
    "transporter.profile.verification_rejected",
    "transporter.profile.payout_method_changed",
    "transporter.truck.created",
    "transporter.truck.updated",
    "transporter.truck.activated",
    "transporter.truck.deactivated",
    "transporter.truck.location_updated",
    "transporter.truck.document_linked",
    "transporter.truck.archived",
    "transporter.truck.verification_changed",
    "transporter.driver.created",
    "transporter.driver.updated",
    "transporter.driver.activated",
    "transporter.driver.deactivated",
    "transporter.driver.assigned_to_truck",
    "transporter.driver.unassigned_from_truck",
    "transporter.driver.document_linked",
    "transporter.driver.verification_changed",
    "transporter.document.uploaded",
    "transporter.document.replaced",
    "transporter.document.verification_requested",
    "transporter.document.verified",
    "transporter.document.rejected",
    "transporter.document.expired",
    "transporter.document.archived",
    "transporter.document.accessed",
    "matching.bid_eligibility_validated",
    "matching.checkout_eligibility_revalidated",
    "matching.bid_attempt_rejected",
    "matching.policy_updated",
    "notification.created",
    "notification.delivery_attempted",
    "notification.sent",
    "notification.delivered",
    "notification.failed",
    "notification.retry_scheduled",
    "notification.failed_final",
    "notification.action_completed",
    "business.profile.created",
    "business.profile.updated",
    "business.profile.status_changed",
    "business.payment_method.added",
    "business.payment_method.default_changed",
    "business.payment_method.deactivated",
    "business.payment_method.expired",
    "business.payment_method.provider_revoked",
    "business.payment_preference.created",
    "business.payment_preference.updated",
    "business.payment_preference.auto_shortfall_enabled",
    "business.payment_preference.auto_shortfall_disabled",
    "business.payment_preference.default_method_changed",
)

# This is a security-category event even though its namespace records that the
# actor is an administrator. It is not a wrapper for a domain business event.
_ADMIN_SECURITY_NAMES = ("admin.security_action.performed",)

_OPERATIONS_NAMES = (
    "system.job.started",
    "system.job.completed",
    "system.job.failed",
    "system.job.skipped",
    "system.job.lock_not_acquired",
    "system.job.manual_triggered",
)

DEFERRED_EVENT_NAMES = (
    "one_time.qr_payment.intent_created",
    "one_time.qr_payment.confirmed",
    "one_time.qr_payment.expired",
    "one_time.qr_payment.cancelled",
    "one_time.qr_payment.failed",
    "one_time.qr_payment.amount_mismatch",
    "one_time.qr_payment.refunded",
    "one_time.qr_payment.webhook_applied",
)

INTEGRATED_EVENT_NAMES = frozenset(
    {
        "security.login.started",
        "security.login.failed",
        "security.login.succeeded",
        "security.logout.completed",
        "security.signup.started",
        "security.signup.failed",
        "security.signup.completed",
        "security.trusted_device.added",
        "security.trusted_device.removed",
        "security.trusted_device.rotated",
    }
)

# Runtime event integration remains deliberately separate from catalog ownership.
# This narrow allowlist defines the future terminal-signup failure envelope without
# making the event writable at runtime.
SIGNUP_FAILURE_RESULT_CODES = frozenset(
    {
        "validation_failed",
        "account_conflict",
        "provider_unavailable",
        "persistence_failed",
        "reconciliation_required",
    }
)

_CONTRACTS = {
    "security.session.issued": ("authenticated_self", (), ()),
    "security.session.access_locked": (
        "service_subject",
        ("app_launch", "idle_lock", "security_action"),
        ("result_code",),
    ),
    "security.session.refreshed": ("authenticated_self", (), ()),
    "security.session.expired_inactivity": ("service_subject", (), ()),
    "security.session.revoked": (
        "authenticated_self_or_service",
        ("logout", "logout_all", "password_changed", "password_reset", "account_blocked", "device_removed", "security_action", "absolute_expiry"),
        ("result_code",),
    ),
    "security.trusted_device.added": ("authenticated_self", (), ()),
    "security.trusted_device.removed": (
        "authenticated_self_or_service",
        ("user_removed", "logout_all", "password_changed", "password_reset", "account_blocked", "inactivity_expired", "attempt_limit", "security_action"),
        ("result_code",),
    ),
    "security.trusted_device.rotated": (
        "authenticated_self_or_service",
        ("full_login", "scheduled_rotation", "security_action"),
        ("result_code",),
    ),
    "security.mpin.enrolled": ("authenticated_self", (), ()),
    "security.mpin.changed": ("authenticated_self", (), ()),
    "security.mpin.disabled": ("authenticated_self", (), ()),
    "security.mpin.unlock_succeeded": ("authenticated_self", (), ()),
    "security.mpin.unlock_failed": (
        "service_subject", ("invalid_mpin", "rate_limited"), ("result_code",)
    ),
    "security.mpin.locked": (
        "service_subject", ("attempt_limit", "security_action"), ("result_code",)
    ),
    "security.mpin.reset_completed": (
        "authenticated_self", ("user_reauthentication", "security_recovery"), ("result_code",)
    ),
    "security.mpin.step_up_succeeded": ("authenticated_self", (), ()),
    "security.mpin.step_up_failed": (
        "service_subject",
        ("invalid_mpin", "rate_limited", "challenge_expired", "challenge_mismatch"),
        ("result_code",),
    ),
}

_HIGH_SECURITY_NAMES = {
    "security.login.suspicious_detected",
    "security.account.locked",
    "security.account.unlocked",
    "admin.security_action.performed",
}

_FINANCIAL_PREFIXES = (
    "one_time.payment.",
    "wallet.",
    "commission.",
    "terms.",
    "business.payment_method.",
    "business.payment_preference.",
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,3}$")


def _ownership_domain(name):
    return name.split(".", 1)[0]


def _retention(name, category):
    if category == SECURITY:
        return SECURITY_HIGH_RETENTION if name in _HIGH_SECURITY_NAMES else SECURITY_RETENTION
    if category == OPERATIONS:
        return OPERATIONS_RETENTION
    if name.startswith(_FINANCIAL_PREFIXES):
        return FINANCIAL_RETENTION
    return BUSINESS_RETENTION


def _definition(name, category, status=PLANNED, writable=True):
    actor_policy, result_codes, metadata_keys = _CONTRACTS.get(name, ("generic", None, ()))
    return EventDefinition(
        name=name,
        category=category,
        version=1,
        retention_class=_retention(name, category),
        ownership_domain=_ownership_domain(name),
        lifecycle_status=status,
        writable=writable,
        integrated=name in INTEGRATED_EVENT_NAMES,
        allowed_result_codes=(
            SIGNUP_FAILURE_RESULT_CODES
            if name == "security.signup.failed"
            else frozenset(result_codes) if result_codes else None
        ),
        actor_policy=actor_policy,
        allowed_metadata_keys=(
            frozenset({"result_code"})
            if name == "security.signup.failed"
            else frozenset(metadata_keys)
        ),
    )


_DEFINITIONS = (
    *(_definition(name, SECURITY) for name in _SECURITY_NAMES),
    *(_definition(name, SECURITY) for name in _ADMIN_SECURITY_NAMES),
    *(_definition(name, BUSINESS_AUDIT) for name in _BUSINESS_NAMES),
    *(_definition(name, OPERATIONS, writable=False) for name in _OPERATIONS_NAMES),
    *(
        _definition(name, BUSINESS_AUDIT, status=DEFERRED, writable=False)
        for name in DEFERRED_EVENT_NAMES
    ),
)

CATALOG = {definition.name: definition for definition in _DEFINITIONS}
PLANNED_EVENT_NAMES = tuple(
    definition.name
    for definition in _DEFINITIONS
    if definition.lifecycle_status == PLANNED
)


class UnknownEventName(ValueError):
    pass


class NonWritableEventName(ValueError):
    pass


def get_event_definition(name):
    try:
        return CATALOG[name]
    except (KeyError, TypeError):
        raise UnknownEventName("Unknown canonical event name.") from None


def get_writable_event_definition(name, expected_category=None):
    definition = get_event_definition(name)
    if not definition.writable or not definition.integrated:
        raise NonWritableEventName(
            "This canonical event is not integrated for runtime persistence."
        )
    if expected_category and definition.category != expected_category:
        raise NonWritableEventName("Canonical event category does not match this writer.")
    return definition


def catalog_projection_contract(definition):
    """Return the database projection contract from the sole Python catalog owner."""
    return {
        "actor_policy": definition.actor_policy,
        "allowed_metadata_keys": sorted(definition.allowed_metadata_keys),
        "allowed_result_codes": sorted(definition.allowed_result_codes or ()),
    }


def catalog_projection_rows():
    """Stable catalog-derived rows used to verify the database projection."""
    return tuple(
        (
            definition.name,
            definition.version,
            definition.category,
            definition.ownership_domain,
            definition.retention_class,
            definition.lifecycle_status,
            definition.writable,
            definition.integrated,
            catalog_projection_contract(definition),
        )
        for definition in sorted(_DEFINITIONS, key=lambda item: item.name)
    )


def _assert_catalog_integrity():
    if len(_DEFINITIONS) != len(CATALOG):
        raise RuntimeError("Canonical event catalog contains duplicate names.")
    if len(PLANNED_EVENT_NAMES) != 162 or len(DEFERRED_EVENT_NAMES) != 8:
        raise RuntimeError("Canonical event catalog totals do not match the locked registry.")
    for definition in _DEFINITIONS:
        if not _NAME_RE.fullmatch(definition.name):
            raise RuntimeError(f"Invalid canonical event name: {definition.name}")
        if definition.version <= 0:
            raise RuntimeError(f"Invalid foundation state for: {definition.name}")
    integrated = {definition.name for definition in _DEFINITIONS if definition.integrated}
    if integrated != INTEGRATED_EVENT_NAMES:
        raise RuntimeError("Canonical event integrations do not match the locked Phase 1B scope.")


_assert_catalog_integrity()
