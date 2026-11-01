"""Platform Terms endpoints (all authenticated roles).

Serves the published, versioned platform Terms — including the current
commission splits for both policy types — and records per-user
acknowledgements of a Terms version.
"""

from flask import Blueprint, request

from auth.helpers import csrf_error, json_response, login_required, timestamp_bundle
from shared.commissions import (
    changed_policy_types,
    get_policy_by_id,
    get_current_terms_version,
    get_terms_version_by_number,
    has_acknowledged,
    list_terms_versions,
    record_acknowledgement,
    requires_acknowledgement,
    serialize_policy,
    serialize_terms_version,
)
from shared.db import open_db


terms_blueprint = Blueprint("platform_terms", __name__)


def _terms_with_policies(db, terms):
    """Serialize a Terms version together with both referenced policies."""
    if not terms:
        return None
    payload = serialize_terms_version(terms)
    payload["one_time"] = serialize_policy(get_policy_by_id(db, terms.get("one_time_policy_id")))
    payload["agreement"] = serialize_policy(get_policy_by_id(db, terms.get("agreement_policy_id")))
    return payload


@terms_blueprint.get("/api/platform/terms/current")
@login_required
def current_terms():
    """Current published Terms + whether the logged-in user has reviewed them."""
    user = request.current_user
    with open_db() as db:
        terms = get_current_terms_version(db)
        if not terms:
            return json_response({"success": True, "terms": None})
        payload = _terms_with_policies(db, terms)
        previous = get_terms_version_by_number(db, int(terms["version_number"]) - 1)
        changed = changed_policy_types(terms, previous)
        acknowledged = has_acknowledged(db, user["id"], terms["id"])
        payload["previous"] = _terms_with_policies(db, previous)
        payload["changed_policy_types"] = sorted(changed)
        payload["acknowledged"] = acknowledged
        payload["requires_acknowledgement"] = requires_acknowledgement(
            user.get("role"), terms["version_number"], changed, acknowledged,
        )
    return json_response({"success": True, "terms": payload})


@terms_blueprint.get("/api/platform/terms/history")
@login_required
def terms_history():
    """Immutable history of published Terms versions with their commission splits."""
    with open_db() as db:
        versions = [_terms_with_policies(db, row) for row in list_terms_versions(db)]
    return json_response({"success": True, "versions": versions})


@terms_blueprint.post("/api/platform/terms/<int:terms_version_id>/acknowledge")
@login_required
def acknowledge_terms(terms_version_id):
    """Record that the logged-in user reviewed a Terms version (idempotent)."""
    err = csrf_error()
    if err:
        return err
    user = request.current_user
    with open_db() as db:
        exists = db.execute(
            "SELECT id FROM terms_versions WHERE id = %s", (terms_version_id,)
        ).fetchone()
        if not exists:
            return json_response({"success": False, "message": "Terms version not found."}, 404)
        record_acknowledgement(db, user["id"], terms_version_id, timestamp_bundle()["iso"])
        db.commit()
    return json_response({"success": True, "acknowledged": True, "terms_version_id": terms_version_id})
