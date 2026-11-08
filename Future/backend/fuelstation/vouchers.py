"""Authenticated fuel voucher APIs; response secrets are never persisted in logs."""
from flask import request
import hashlib
import json
import uuid
from auth import step_up_service

from auth.helpers import csrf_error, json_response, login_required
from shared.db import open_db
from shared.payments import CheckoutError, parse_positive_id
from shared.roles import TRANSPORTER_ROLES
from shared import fuel_credit


def register_voucher_routes(blueprint):
    def transporter():
        return str(request.current_user.get("role", "")).lower() in TRANSPORTER_ROLES

    def station():
        return request.current_user.get("role") == "fuel_station_manager"

    def run(operation):
        err = csrf_error()
        if err:
            return err
        try:
            with open_db() as db:
                data = request.get_json(silent=True)
                if not isinstance(data, dict):
                    raise ValueError("A JSON object is required.")
                result = operation(db, data)
            response = json_response({"success": True, **result})
            response.headers["Cache-Control"] = "no-store"
            return response
        except CheckoutError as exc:
            return json_response({"success": False, "message": str(exc), "code": exc.code}, exc.status)
        except (ValueError, TypeError, ArithmeticError) as exc:
            return json_response({"success": False, "message": str(exc), "code": "invalid_fuel_request"}, 400)

    # This blueprint has /api/fuelstation prefix. Transporter endpoints are
    # separately registered on the root driver blueprint by register_owner_routes.
    @blueprint.post("/vouchers/verify")
    @login_required
    def fuel_voucher_verify():
        if not station():
            return json_response({"success": False, "message": "Fuel station access required."}, 403)
        return run(lambda db, data: fuel_credit.verify_voucher(db, request.current_user["id"], data.get("otp"), parse_positive_id(data.get("pump_id"), "Pump ID")))

    @blueprint.post("/vouchers/<int:voucher_id>/dispense")
    @login_required
    def fuel_voucher_dispense(voucher_id):
        if not station():
            return json_response({"success": False, "message": "Fuel station access required."}, 403)
        return run(lambda db, data: fuel_credit.dispense_voucher(db, request.current_user["id"], voucher_id, data))

    return run, transporter


def register_owner_routes(blueprint):
    def owner_required():
        if str(request.current_user.get("role", "")).lower() not in TRANSPORTER_ROLES:
            return json_response({"success": False, "message": "Transporter access required."}, 403)
        return None

    def mutation(operation, *, authorize=False):
        denied = owner_required()
        if denied:
            return denied
        err = csrf_error()
        if err:
            return err
        try:
            with open_db() as db:
                data = request.get_json(silent=True) or {}
                gate = descriptor = None
                if authorize:
                    expected_user = request.headers.get("X-DTX-Expected-User-Id", "")
                    if expected_user != str(request.current_user["id"]):
                        return json_response({"success":False,"code":"fuel_account_changed","message":"The verified account changed. Reload before authorizing fuel."},409)
                    if not isinstance(data, dict):
                        raise ValueError("A JSON object is required.")
                    resource_id = parse_positive_id(data.get("trip_id") or data.get("agreement_trip_id"), "Trip ID")
                    cap = fuel_credit.money(data.get("max_amount"))
                    fingerprint = hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
                    descriptor = step_up_service.normalize_descriptor({
                        "action_key":"fuel.voucher.authorize","resource_type":"trip","resource_id":resource_id,
                        "amount_minor":step_up_service.money_to_minor(cap),"currency":"PKR",
                        "funding_source":"wallet_and_credit","destination_fingerprint":fingerprint,
                    })
                    prior = db.execute_exact("SELECT id FROM fuel_vouchers WHERE transporter_user_id=%s AND idempotency_key=%s",
                                              (request.current_user["id"],request.headers.get("Idempotency-Key"))).fetchone()
                    if not prior:
                        gate = step_up_service.consume_current_request(db,request,descriptor)
                        gate_error = step_up_service.gate_error_response(gate,descriptor)
                        if gate_error:
                            db.rollback()
                            return gate_error
                result = operation(db, data)
                if gate:
                    step_up_service.write_consumed_event(db,request_id="fuel.authorize."+uuid.uuid4().hex,gate=gate,descriptor=descriptor)
            response = json_response({"success": True, **result})
            response.headers["Cache-Control"] = "no-store"
            return response
        except CheckoutError as exc:
            return json_response({"success": False, "message": str(exc), "code": exc.code}, exc.status)
        except (ValueError, TypeError, ArithmeticError) as exc:
            return json_response({"success": False, "message": str(exc), "code": "invalid_fuel_request"}, 400)

    @blueprint.post("/api/fuel/vouchers")
    @login_required
    def fuel_voucher_create():
        return mutation(lambda db, data: fuel_credit.authorize_voucher(db, request.current_user["id"], data, request.headers.get("Idempotency-Key")),authorize=True)

    @blueprint.get("/api/fuel/vouchers")
    @login_required
    def fuel_voucher_list():
        denied = owner_required()
        if denied:
            return denied
        with open_db() as db:
            rows = db.execute_exact("SELECT * FROM fuel_vouchers WHERE transporter_user_id=%s ORDER BY id DESC LIMIT 100", (request.current_user["id"],)).fetchall()
            account = db.execute_exact("SELECT * FROM fuel_credit_accounts WHERE transporter_user_id=%s", (request.current_user["id"],)).fetchone()
        response = json_response({"success": True, "vouchers": [fuel_credit.safe_voucher(row) for row in rows],
                                  "credit_account": {k: str(v) if k.endswith("credit") or k == "authorized_limit" else v for k, v in account.items()} if account else None})
        response.headers["Cache-Control"] = "no-store"
        return response

    @blueprint.post("/api/fuel/vouchers/<int:voucher_id>/cancel")
    @login_required
    def fuel_voucher_cancel(voucher_id):
        return mutation(lambda db, data: fuel_credit.cancel_voucher(db, voucher_id, request.current_user["id"]))
