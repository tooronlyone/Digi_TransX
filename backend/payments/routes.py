"""Saved payment methods + payment preferences (business service seekers).

Everyday users pay with an unsaved dummy card at checkout and cannot manage
saved cards. All card data is validated in memory only — the stored method
holds a provider token, brand, last four digits and expiry, never the full
number or CVC.
"""

from flask import Blueprint, request

from auth.helpers import csrf_error, json_response, login_required, timestamp_bundle
from shared.db import open_db
from shared.payments import (
    create_saved_method,
    get_payment_preferences,
    get_saved_method,
    list_saved_methods,
    normalize_client_kind,
    parse_optional_bool,
    parse_positive_id,
    serialize_saved_method,
    upsert_payment_preferences,
    validate_dummy_card,
)


payments_blueprint = Blueprint("payments", __name__)


def _business_only():
    """Saved cards and auto-shortfall settings are for business service
    seekers; everyday users (and non-clients) are rejected."""
    kind = normalize_client_kind(request.current_user.get("role"))
    if kind != "business":
        return json_response(
            {"success": False, "message": "Saved payment methods are available for business accounts only."},
            403,
        )
    return None


def _preferences_payload(db, user_id):
    preferences = get_payment_preferences(db, user_id)
    default_method = None
    if preferences.get("default_payment_method_id"):
        default_method = get_saved_method(db, user_id, preferences["default_payment_method_id"])
    if default_method is None:
        row = db.execute(
            "SELECT * FROM saved_payment_methods WHERE user_id = %s AND status = 'active' AND is_default "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        default_method = dict(row) if row else None
    return {
        "auto_shortfall_charge_enabled": bool(preferences["auto_shortfall_charge_enabled"]),
        "default_payment_method_id": default_method["id"] if default_method else None,
        "default_card": serialize_saved_method(default_method),
    }


@payments_blueprint.get("/api/payment-methods")
@login_required
def get_payment_methods():
    error = _business_only()
    if error:
        return error
    with open_db() as db:
        methods = list_saved_methods(db, request.current_user["id"])
    return json_response({"success": True, "methods": [serialize_saved_method(m) for m in methods]})


@payments_blueprint.post("/api/payment-methods")
@login_required
def add_payment_method():
    error = _business_only()
    if error:
        return error
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    card_summary, card_error = validate_dummy_card(data)
    if card_error:
        return json_response({"success": False, "message": card_error}, 400)
    try:
        set_default = parse_optional_bool(data.get("set_default"), "set_default")
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)
    with open_db() as db:
        method = create_saved_method(
            db, request.current_user["id"], card_summary,
            set_default=set_default,
        )
        if method and method.get("is_default"):
            upsert_payment_preferences(db, request.current_user["id"], default_method_id=method["id"])
        db.commit()
    return json_response({"success": True, "method": serialize_saved_method(method)}, 201)


@payments_blueprint.put("/api/payment-methods/<int:method_id>")
@login_required
def update_payment_method(method_id):
    error = _business_only()
    if error:
        return error
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        is_default = parse_optional_bool(data.get("is_default"), "is_default")
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)
    if not is_default:
        return json_response({"success": False, "message": "Only setting a card as default is supported."}, 400)
    stamp = timestamp_bundle()["iso"]
    with open_db() as db:
        method = get_saved_method(db, request.current_user["id"], method_id)
        if not method:
            return json_response({"success": False, "message": "Saved card not found."}, 404)
        db.execute(
            "UPDATE saved_payment_methods SET is_default = false, updated_at = %s "
            "WHERE user_id = %s AND is_default",
            (stamp, request.current_user["id"]),
        )
        db.execute(
            "UPDATE saved_payment_methods SET is_default = true, updated_at = %s WHERE id = %s",
            (stamp, method_id),
        )
        upsert_payment_preferences(db, request.current_user["id"], default_method_id=method_id)
        db.commit()
        method = get_saved_method(db, request.current_user["id"], method_id)
    return json_response({"success": True, "method": serialize_saved_method(method)})


@payments_blueprint.delete("/api/payment-methods/<int:method_id>")
@login_required
def remove_payment_method(method_id):
    error = _business_only()
    if error:
        return error
    err = csrf_error()
    if err:
        return err
    stamp = timestamp_bundle()["iso"]
    with open_db() as db:
        method = get_saved_method(db, request.current_user["id"], method_id)
        if not method:
            return json_response({"success": False, "message": "Saved card not found."}, 404)
        db.execute(
            "UPDATE saved_payment_methods SET status = 'removed', is_default = false, updated_at = %s "
            "WHERE id = %s",
            (stamp, method_id),
        )
        preferences = get_payment_preferences(db, request.current_user["id"])
        if preferences.get("default_payment_method_id") == method_id:
            upsert_payment_preferences(db, request.current_user["id"], clear_default=True)
        db.commit()
    return json_response({"success": True, "message": "Card removed."})


@payments_blueprint.get("/api/payment-preferences")
@login_required
def get_preferences():
    error = _business_only()
    if error:
        return error
    with open_db() as db:
        payload = _preferences_payload(db, request.current_user["id"])
    return json_response({"success": True, "preferences": payload})


@payments_blueprint.put("/api/payment-preferences")
@login_required
def update_preferences():
    error = _business_only()
    if error:
        return error
    err = csrf_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    # Strict JSON boolean: "true"/"false"/0/1 are rejected.
    try:
        auto_enabled = parse_optional_bool(
            data.get("auto_shortfall_charge_enabled"), "auto_shortfall_charge_enabled", default=None,
        )
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)
    default_method_id = data.get("default_payment_method_id")
    if default_method_id is not None:
        try:
            default_method_id = parse_positive_id(default_method_id, "Payment method")
        except ValueError as exc:
            return json_response({"success": False, "message": str(exc)}, 400)
    with open_db() as db:
        if default_method_id is not None:
            method = get_saved_method(db, request.current_user["id"], default_method_id)
            if not method:
                return json_response({"success": False, "message": "Saved card not found."}, 404)
            stamp = timestamp_bundle()["iso"]
            db.execute(
                "UPDATE saved_payment_methods SET is_default = false, updated_at = %s "
                "WHERE user_id = %s AND is_default",
                (stamp, request.current_user["id"]),
            )
            db.execute(
                "UPDATE saved_payment_methods SET is_default = true, updated_at = %s WHERE id = %s",
                (stamp, default_method_id),
            )
        upsert_payment_preferences(
            db,
            request.current_user["id"],
            auto_enabled=auto_enabled if auto_enabled is not None else None,
            default_method_id=default_method_id,
        )
        payload = _preferences_payload(db, request.current_user["id"])
        db.commit()
    return json_response({"success": True, "preferences": payload})
