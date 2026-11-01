"""Resolve a password change only after an operator verifies provider completion.

This is a trusted server CLI, not a public recovery endpoint. A timeout must
first be checked in the identity provider's operation/audit logs. Never clear
the gate merely because a timeout elapsed or a new OTP was issued.
"""

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0,str(BACKEND_DIR))

from auth.credential_changes import _password_change_guard, finish_password_change
from shared.db import open_db


def reconcile(user_id,credentials_version,operator_reference):
    if user_id<=0 or credentials_version<=0:
        raise ValueError("A positive user ID and exact pending credential version are required.")
    if not operator_reference.strip() or len(operator_reference)>128:
        raise ValueError("A non-secret operator/ticket reference of 1–128 characters is required.")
    with _password_change_guard(user_id):
        with open_db() as db:
            owner=db.execute("SELECT * FROM users WHERE id=%s FOR UPDATE",(user_id,)).fetchone()
            if not owner:
                raise ValueError("User not found.")
            active_sessions=db.execute(
                "SELECT count(*) AS n FROM user_sessions WHERE user_id=%s AND revoked_at IS NULL",(user_id,),
            ).fetchone()["n"]
            active_devices=db.execute(
                "SELECT count(*) AS n FROM trusted_devices WHERE user_id=%s AND revoked_at IS NULL",(user_id,),
            ).fetchone()["n"]
            if active_sessions or active_devices:
                raise ValueError("Active authentication rows require investigation before reconciliation.")
            finish_password_change(db,user_id,owner["auth_id"],credentials_version)
            request_id=f"credential.reconcile.{uuid.uuid4().hex}"
            # The canonical admin event remains planned in this repository.
            # Use the existing server admin audit trail, atomically with the
            # gate change; never bypass that event catalog's runtime allowlist.
            db.execute(
                "INSERT INTO user_action_logs(user_id,user_email,user_role,action_type,action_name,page_url,payload_json,created_at) "
                "VALUES(%s,'','system','security_reconciliation','password_change_reconciled','',%s,now())",
                (str(user_id),json.dumps({"operation_id":request_id,"credentials_version":credentials_version,
                                         "operator_reference_digest":hashlib.sha256(operator_reference.encode("utf-8")).hexdigest()})),
            )


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id",type=int,required=True)
    parser.add_argument("--credentials-version",type=int,required=True)
    parser.add_argument("--operator-reference",required=True)
    parser.add_argument("--provider-operation-terminal",action="store_true",required=True,
                        help="Attest that provider logs confirm no pending/in-flight password write remains.")
    args=parser.parse_args()
    reconcile(args.user_id,args.credentials_version,args.operator_reference)
    print(f"Credential change reconciled for user {args.user_id}; old sessions/devices remain revoked. A fresh sign-in or OTP reset is required.")


if __name__=="__main__":
    main()
