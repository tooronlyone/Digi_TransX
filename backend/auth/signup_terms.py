"""Versioned role agreements shown after signup role selection."""

import json

SIGNUP_TERMS_VERSION = "signup-terms-2026-10-27-v1"
ROLE_TERMS = {
    "service_seeker": ("Service Seeker", "Provide accurate shipment details, lawful cargo information and pickup instructions. Review the transporter, agreed price and booking terms before accepting a bid."),
    "everyday_user": ("Everyday User", "Provide accurate pickup, delivery and goods details. Review the selected transporter, agreed price and booking terms before confirming personal transport."),
    "logistics_provider": ("Logistics Provider", "Keep fleet, driver and vehicle information accurate. Accept only work you can fulfil and follow the agreed transport, safety and delivery requirements."),
    "driver": ("Truck Driver", "Keep your identity and driving licence information accurate. Follow assigned trip, road safety and delivery requirements, and provide truthful trip updates."),
    "fuel_station_manager": ("Fuel Station Manager", "Keep station information accurate and record fuel dispensing and payment confirmations truthfully. Follow applicable fuel handling and safety requirements."),
    "shopkeeper": ("Shop Owner / Vendor", "Keep shop, product, stock and pricing information accurate. Honour confirmed orders and provide truthful sales and delivery records."),
}


def signup_terms_document(role):
    if role not in ROLE_TERMS:
        raise ValueError("Please select a valid role.")
    title, responsibilities = ROLE_TERMS[role]
    return {
        "version": SIGNUP_TERMS_VERSION,
        "role": role,
        "role_label": title,
        "sections": [
            {"title": "Your account", "text": "Provide accurate account information, protect your sign-in details and use Digi_TransX for lawful activities."},
            {"title": f"Your role: {title}", "text": responsibilities},
            {"title": "Bookings and fees", "text": "Review the applicable price, fees, payment, cancellation and delivery terms before confirming a transaction. Transaction-specific terms are shown in the relevant workflow."},
            {"title": "Goods insurance", "text": "Goods Insurance is recommended. Uninsured cargo is transported at shipper's own risk. This notice does not override mandatory legal obligations or liability established through verified misconduct. An insurance reminder does not purchase insurance or confirm coverage."},
        ],
    }


def signup_terms_error(data):
    if (data.get("signup_terms_accepted") is not True
            or data.get("signup_terms_version") != SIGNUP_TERMS_VERSION
            or data.get("signup_terms_role") != data.get("role")):
        return "Please read and accept the Terms & Conditions for your selected role."
    return None


def record_signup_terms(db, user_id, role):
    db.execute(
        "INSERT INTO signup_terms_acceptances "
        "(user_id, terms_version, role, document_snapshot) VALUES (%s,%s,%s,%s::jsonb)",
        (user_id, SIGNUP_TERMS_VERSION, role, json.dumps(signup_terms_document(role))),
    )
