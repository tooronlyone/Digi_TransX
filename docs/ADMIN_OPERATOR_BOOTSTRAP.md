# Digi_TransX V1 — Platform Administrator Bootstrap & Step-Up Authentication

This document describes how platform administrators (`platform_admin` / `role='admin'`) are provisioned, how consumer MPIN exclusion is preserved, and how sensitive administrative operations enforce fresh password reauthentication (`V1-SEC-006`).

## 1. Initial Administrator Bootstrap

Unprivileged user signup routes and Supabase signup metadata cannot assign administrator privileges; `public.users` triggers reject self-assigned `admin`/`platform_admin` roles. Initial administrators must be provisioned out-of-band using the server CLI with Supabase service-role credentials:

```bash
python backend/scripts/create_admin.py --email admin@example.com --password "<strong-password>" --name "Platform Admin"
```

Requirements enforced by both the CLI and `POST /api/admin/users`:
- Password length must be **12 to 128 characters** with no leading/trailing whitespace or control characters.
- Password must include alphabetic characters and at least one digit or special symbol.
- If local `public.users` promotion fails after creating the Supabase Auth identity, the server automatically compensates by deleting the newly created Auth user (`supabase_delete_user`).

## 2. Admin Step-Up Reauthentication Model (`X-Admin-Step-Up-Proof`)

Consumer 4-digit MPIN enrollment (`backend/auth/mpin_service.py`) explicitly excludes `platform_admin` accounts. Instead, administrators reauthenticate with their **password** for sensitive actions:

1. Calling a sensitive admin endpoint without `X-Admin-Step-Up-Proof` returns **HTTP `428 Precondition Required`**:
   ```json
   {
     "success": false,
     "code": "admin_step_up_required",
     "message": "Fresh administrator reauthentication is required for this action.",
     "action": {
       "action_key": "admin.withdrawal.approve",
       "resource_type": "withdrawal_request",
       "resource_id": 42,
       "label": "Approve wallet withdrawal request",
       "request_fingerprint": "<64-hex-sha256>",
       "request_fingerprint_ref": "<16-hex-prefix>"
     }
   }
   ```
2. The client prompts the admin for their password (`AdminStepUpModal`) and sends `POST /api/admin/step-up` with the password, `X-CSRF-Token`, and the challenge `action` descriptor (or `{action_key, resource_id, target}`).
3. Upon Supabase Auth password verification (`supabase_verify_password`) and active session/device lock verification, the backend issues a **3-minute, single-use** proof bound strictly to:
   - Administrator `user_id`
   - Active `session_id` and `trusted_device_id`
   - Current `credentials_version`
   - Exact `action_key`, `resource_type`, `resource_id`, and `request_fingerprint`
4. The client retries the original request once with `X-Admin-Step-Up-Proof: <proof>`. The proof is consumed atomically via `SELECT ... FOR UPDATE` in `public.admin_step_up_authorizations`.

## 3. Protected Operations

- `POST /api/admin/users` (`admin.user.create`)
- `PUT /api/admin/users/<id>/block` (`admin.user.block_status`)
- `POST /api/admin/wallet/withdrawals/<id>/approve` (`admin.withdrawal.approve`)
- `POST /api/admin/wallet/withdrawals/<id>/reject` (`admin.withdrawal.reject`)
- `POST /api/admin/platform-settings/commissions` (`admin.commission.publish`)
- `POST /api/admin/one-time-disputes/<id>/resolve` (`admin.dispute.resolve`)
- `POST /api/admin/delivery-confirmations/process-overdue` (`admin.delivery_overdue.process`)
- `POST /api/admin/freight-settlements/<id>/resolve` (`admin.settlement.resolve`)
- `POST /api/admin/owner-operator-credentials/<id>` (`admin.owner_operator.verify`)
- `POST /api/admin/operational-incidents/<id>/decision` (`admin.incident.decide`)
