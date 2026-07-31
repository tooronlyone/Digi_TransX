# Digi_TransX Tracking, Security, Audit, Analytics, and Operations Registry

## 1. Purpose and authority

This registry is the human-readable source for the current architecture, verified implementation status, ownership boundaries, compatibility findings, and future contracts for Digi_TransX tracking, security, business audit, general analytics, and operational monitoring.

| Field | Verified value |
| --- | --- |
| Inventory base SHA | `0d1b5b2de4b92ec642f39cfec26b09b3aefce571` |
| Verification date | 2026-07-31 |
| Repository | `tooronlyone/Digi_TransX` |
| Branch used for this registry | `chore/tracking-architecture-registry` |
| Environment inspected | Authorized Supabase TEST project `fysu…goev` |
| Database inspection mode | Read-only transactions; every inspection ended with `ROLLBACK` |
| Scheduler state during inspection | Disabled with `DIGITRANSX_ENABLE_SCHEDULER=0`; no scheduler process active |
| Phase | Phase 0 — inventory and registry |

> **Planning/documentation only.** This file creates no routes, tables, views, functions, triggers, policies, jobs, dashboards, providers, or runtime behavior. Any object or event marked Planned or Deferred does not exist merely because it appears here.

The Inventory base SHA identifies the code/database state inspected during Phase 0. It is not the SHA of the documentation commit that introduced or later corrected this registry.

Runtime implementation remains authoritative when this registry and code disagree. A disagreement is a defect: every future tracking-related change must update this file in the same commit. Phase 1B must add contract tests that detect code/document drift, including event-name, event-version, schema, writer-ownership, metadata-schema, and prohibited-field drift.

### Status vocabulary

| Status | Meaning |
| --- | --- |
| **Verified existing and standardized** | Present in code and TEST, with a clear owner and a reusable contract. |
| **Verified existing but unstandardized** | Present and used, but not compliant with the planned domain/envelope/validation contract. |
| **Partially implemented** | Some compatible building blocks exist, but required behavior or guarantees are missing. |
| **Planned** | Approved architecture for a future phase; not implemented. |
| **Deferred** | Intentionally postponed pending a prerequisite, provider, workflow, or review. |
| **Not implemented** | Verified absent from current code and TEST. |
| **Out of scope** | Must not be changed by the phase being discussed. |

### Last-verified migration and capability summary

The TEST database has 43 public tables and two public views. Its public table names and column sets match [`supabase/schema.sql`](../supabase/schema.sql). All ten repository migrations have their expected capabilities present, assessed by objects and constraints rather than by a migration-history table:

1. commission policies and Terms;
2. one-time payment foundation;
3. tokenized payout cards;
4. vehicle operating location;
5. everyday-user separation;
6. client-profile hardening;
7. dispatcher-role removal;
8. one-time trip completion lifecycle;
9. coordinate integrity;
10. shipment trip reviews.

The database also has the expected Auth-to-profile trigger on `auth.users`. Supabase-owned migration records exist in service schemas, but there is no application-owned public migration ledger; capability inspection is therefore mandatory.

### Known limitations and deferred features

- Full signup/login GPS, mandatory full-login Email OTP, risk scoring, device/session management, security cases, and security dashboards are **not implemented**.
- Current Flask authentication uses a signed cookie session, not the planned short-lived access token plus rotating refresh-token model.
- Current `trusted_devices` stores a long-lived raw device cookie token and enables MPIN fast login. It is not the planned non-invasive device registry.
- Current `ActivityTracker` captures broad request/response and form data and trusts frontend identity/event fields. It is **not** an acceptable standardized analytics, audit, security, or monitoring system.
- Email is direct SMTP with no delivery ledger or provider abstraction. SMS is absent and remains deferred.
- Payment processing uses `DummyCardProvider`; Raast QR and a real card/payment provider are deferred.
- There is no dedicated operational telemetry, health/readiness suite, incident store, outbox, or delivery ledger.
- Agreemental workflows exist, but Agreemental tracking is a future extension and must not alter One-Time behavior.
- Retention periods in this registry are internal planning baselines pending professional privacy/legal review; they are not statutory claims.

## 2. Phase 0 verification evidence

### Repository and process gate

- Repository URL, `HEAD`, local `main`, and `origin/main` matched the locked SHA.
- The pre-created feature branch had no unique commit, no staged/untracked work, and no `main...HEAD` diff.
- No remote branch with this name existed at the time of the initial gate.
- No Digi_TransX Flask, Vite, pytest, scheduler, migration, seeder, ActivityTracker/browser-automation, or audit process was active.
- No Flask, Vite, browser, pytest, scheduler, migration, seeder, or ActivityTracker process was started during Phase 0.

### Code-first inspection coverage

The inspection included repository-wide route/function/table/reference scans and targeted review of:

- authentication and session code in [`backend/auth/routes.py`](../backend/auth/routes.py), [`backend/auth/helpers.py`](../backend/auth/helpers.py), [`backend/profile/routes.py`](../backend/profile/routes.py), and [`backend/settings/routes.py`](../backend/settings/routes.py);
- database, Auth, Storage, and app initialization in [`backend/shared/db.py`](../backend/shared/db.py), [`backend/shared/supabase_client.py`](../backend/shared/supabase_client.py), [`backend/shared/storage.py`](../backend/shared/storage.py), and [`backend/app.py`](../backend/app.py);
- tracking in [`backend/tracking/routes.py`](../backend/tracking/routes.py), [`frontend-react/src/components/ActivityTracker.jsx`](../frontend-react/src/components/ActivityTracker.jsx), and [`frontend-react/src/hooks/useTracker.js`](../frontend-react/src/hooks/useTracker.js);
- orders, matching, checkout, trips, disputes, reviews, payments, wallet, commissions, Terms, notifications, chat, trucks, agreements, admin, and scheduler modules;
- all frontend API consumers and React route surfaces;
- all ten migrations, the canonical schema mirror, and PostgreSQL integration-test mirrors.

### TEST inspection safety

Every TEST catalog/count/anomaly query used a transaction reporting `transaction_read_only=on`, and every connection ended with `ROLLBACK`. No row values, personal identifiers, Auth UUIDs, emails, phone numbers, IP addresses, coordinates, payment references, document contents, tokens, or object paths were selected or printed.

## 3. Current runtime architecture inventory

### 3.1 Authentication, session, login, and device ownership

| Capability | Status | Current owner and behavior | Current persistence | Compatibility finding |
| --- | --- | --- | --- | --- |
| Signup | Verified existing but unstandardized | [`signup()`](../backend/auth/routes.py#L53) creates a confirmed Supabase Auth user, then updates `users` and one role-profile table. It logs only a final signup success. | `auth.users`, `users`, role-profile tables, `login_activity` | No signup-start, GPS, signup OTP, risk, or staged session. Auth creation and public-profile updates are not one database transaction. |
| Password login | Verified existing but unstandardized | [`login()`](../backend/auth/routes.py#L194) resolves email/CNIC, checks `is_blocked`, verifies through Supabase Auth, records activity, and immediately creates a Flask session. | `login_activity`, `users.last_login_at`, Flask cookie | No GPS, mandatory Email OTP, risk engine, device/session limits, or high-risk restrictions. |
| Logout | Partially implemented | [`logout()`](../backend/auth/routes.py#L244) validates CSRF for an authenticated session and clears the Flask cookie session. | Client cookie only | No server session exists to revoke; current device token remains trusted. |
| Password reset | Partially implemented | Forgot-password sends a six-digit Email OTP, stores a password hash of the OTP, enforces five attempts and a 15-minute cooldown, issues a signed reset token, and updates Supabase Auth. | `password_reset_otps`, `reset_tokens` | OTP expiry is 10 minutes, not the locked five; no 60-second resend control or HMAC challenge; reset does not revoke sessions/devices. |
| Password change | Partially implemented | [`request_password_change_otp()`](../backend/profile/routes.py#L59) and [`change_password()`](../backend/profile/routes.py#L95) reuse the OTP helpers. | Same OTP table | No session revocation or security-event contract. |
| Login activity | Verified existing but unstandardized | [`record_login_activity()`](../backend/auth/helpers.py#L313) records identifier, method, status, failure reason, IP, and user agent. | `login_activity` | Useful transitional security evidence, but contains raw identifier/IP, lacks canonical event/version/correlation/risk/retention fields, and covers only selected auth outcomes. |
| Trusted device / fast login | Verified existing but unstandardized | [`upsert_trusted_device()`](../backend/auth/helpers.py#L338) stores a raw random cookie token; MPIN routes use it for fast login. Cookie lifetime is 180 days. | `trusted_devices`, `users.mpin_hash`, `users.mpin_enabled` | Not the planned device model; raw token storage, no per-device revocation UI, no maximum-five enforcement, and trusted device currently bypasses password/full-login checks via MPIN. |
| Flask session | Verified existing but unstandardized | [`build_auth_success_response()`](../backend/auth/helpers.py#L357) sets `user_id`, CSRF token, and `last_active_at` in Flask's signed cookie. [`login_required()`](../backend/auth/helpers.py#L286) refreshes `last_active_at` on every authenticated request. | Signed cookie, no `user_sessions` table | No 15-minute access token, rotating refresh token, replay detection, seven-day inactivity enforcement, or 30-day absolute lifetime. Polling requests currently count as activity. |
| Supabase session use | Verified existing but unstandardized | [`supabase_verify_password()`](../backend/shared/supabase_client.py#L51) signs in with the anon client only to validate credentials, then signs out; returned Supabase tokens are discarded. | Supabase Auth plus Flask cookie | Supabase Auth sessions are not the application session owner. |
| Account block | Partially implemented | Login checks `users.is_blocked`; admin can toggle it with CSRF. | `users.is_blocked`, `users.block_reason` | No lock/unlock event, re-authentication, mandatory reason on unlock, case, alert, or session revocation. |
| GPS and risk | Not implemented | No signup/login GPS route, distance comparison, IP intelligence, score, tier, or rollout-state owner exists. | None | Must be introduced behind disabled/shadow states after data and privacy review. |

Security-sensitive current facts:

- `login_activity` has 44 rows; all 44 contain a login identifier and IP field.
- `trusted_devices` has 31 token rows; no user exceeds five rows.
- `password_reset_otps` and `reset_tokens` each had zero rows at verification.
- Auth and public profiles both had 19 rows, with zero missing links in either direction.

### 3.2 Existing tracking and overlapping evidence

| Mechanism | Status | Writer/consumer | Finding |
| --- | --- | --- | --- |
| `POST /api/track` | Verified existing but unstandardized | [`api_track()`](../backend/tracking/routes.py#L13) | Unauthenticated; accepts arbitrary frontend identity, event names, page URL, and metadata; commits directly to `user_action_logs`. |
| `ActivityTracker` | Verified existing but unstandardized | [`ActivityTracker.jsx`](../frontend-react/src/components/ActivityTracker.jsx) mounted in [`App.jsx`](../frontend-react/src/App.jsx#L352) | Globally patches `window.fetch`, captures up to 2,000 characters of request bodies and response bodies, captures form fields with only name-based redaction, and captures button/link text. |
| `useTracker` | Verified existing but unstandardized | [`useTracker.js`](../frontend-react/src/hooks/useTracker.js) | Sends session-stored user email/role/id and places the CSRF token into a field called `session_id`; event names and details are arbitrary. |
| `user_action_logs` | Verified existing but unstandardized | `/api/track` and the admin commission route | Mixes general analytics and one admin audit use. TEST has 1,899 rows, five action types, 138 action names, payload JSON on every row, and a `session_id` key on every payload. |
| `login_activity` | Verified existing but unstandardized | Auth helper and settings security-activity route | Transitional security evidence only; must not become general audit/analytics storage. |
| `shipment_status_history` | Verified existing and standardized for its narrow purpose | `trg_shipments_status_history` / `log_shipment_status_change()` | Reliable shipment-status transition history, but not a general business event ledger and not sufficient for monetary or non-status changes. |
| Domain tables | Verified existing and standardized for state | Payment, wallet, lifecycle, dispute, review, chat, notification, policy, and Terms services | Authoritative business state. They are not an append-only common audit envelope. |

The four event domains defined later must not be collapsed into `user_action_logs`.

### 3.3 Notifications, email, scheduler, logging, and health

| Area | Current owner | Status and finding |
| --- | --- | --- |
| In-app notifications | [`backend/shared/notifications.py`](../backend/shared/notifications.py), notification routes in [`backend/orders/routes.py`](../backend/orders/routes.py#L864) | `shipment_notifications` is idempotent per `(trip_id, user_id, notification_type)` when `trip_id` is present. It has no provider/delivery-attempt ledger. |
| Email | [`send_email()`](../backend/auth/helpers.py#L113) | Direct synchronous SMTP only. No provider abstraction, template/version registry, idempotency key, bounce/delivery status, retry policy, or `notification_deliveries`. |
| Payment provider | [`DummyCardProvider`](../backend/shared/payments.py#L375) | Replaceable interface with scoped idempotency keys, but the current provider is dummy-only. |
| GPS provider | [`backend/tracking/traccar.py`](../backend/tracking/traccar.py) | Stubbed provider functions; no configured provider calls. The current truck code accepts IMEI-like input, which is unrelated to the planned non-invasive login device ID and must not be reused for it. |
| Scheduler | [`backend/scheduler.py`](../backend/scheduler.py) | Three jobs: overdue delivery confirmation every 10 minutes, agreement payments daily at 00:05, and agreement penalties every 30 minutes. Default-off web-process gate and per-process singleton exist. Agreement jobs are not multi-owner safe. |
| Logging | [`backend/scheduler.py`](../backend/scheduler.py#L33) | Only basic Python logging is configured. Some exception strings may be logged. There is no structured redaction, request/correlation ID, sampling, trace, or incident integration. |
| Error handlers | None | No Flask application error-handler registry was found. Default error handling is authoritative. |
| Health | [`check_connection()`](../backend/shared/db.py#L172), root route in [`backend/app.py`](../backend/app.py#L58) | Database connectivity is checked at import/startup. `/` is a frontend/root response, not a liveness/readiness contract. No internal dependency health route exists. |

### 3.4 One-Time orders, matching, checkout, payments, and wallet

| Area | Current runtime owner | Current TEST objects | Verified behavior |
| --- | --- | --- | --- |
| Order creation and listing | [`backend/orders/routes.py`](../backend/orders/routes.py) | `shipments` | Everyday and business clients can create One-Time orders; a pending mandatory transporter review blocks another order. |
| Bid validation | [`create_bid()`](../backend/orders/routes.py#L358), [`truck_order_eligibility_mismatch()`](../backend/orders/helpers.py#L388) | `shipment_bids`, `vehicles` | Active owned truck required; duplicate active bid rejected before insert; capacity/type/location rules rechecked. |
| Matching | [`backend/orders/helpers.py`](../backend/orders/helpers.py#L172) | `shipments`, `vehicles` | Exact capacity is eligible; larger compatible capacity is eligible; smaller capacity is rejected; liquid volume is `max(explicit CBM, litres/1000)`; missing volume capacity fails closed; pickup coordinates/radius or exact normalized city drive eligibility. |
| Availability | [`available_orders()`](../backend/orders/routes.py#L280) | Same | Filters in memory through the same eligibility helper. It correctly avoids creating one audit row per truck shown. |
| Checkout | [`perform_checkout()`](../backend/shared/payments.py#L826) | `shipments`, `shipment_bids`, `shipment_trips`, `payments`, `wallets`, `wallet_transactions`, `shipment_no_show_tracking`, `chat_threads` | Locks and revalidates order/bid/truck, uses an idempotency key, holds payment, accepts one bid, rejects competing pending bids, creates one trip, snapshots commission/Terms, and updates shipment atomically. |
| Payment equations | [`backend/shared/payments.py`](../backend/shared/payments.py), database CHECK constraints | `payments` | `wallet + card = bid`; `company fee + transporter = bid`; total card charge is card funding plus processing fee; processing fee is outside commission. |
| Release/refund | [`release_one_time_payment()`](../backend/shared/payments.py#L1354), [`refund_one_time_payment()`](../backend/shared/payments.py#L1422) | `payments`, `wallets`, `wallet_transactions` | Row-locked, status-guarded, replay-safe services. A held payment can become released or refunded, not both. |
| Wallet | [`backend/wallet/helpers.py`](../backend/wallet/helpers.py), [`backend/wallet/routes.py`](../backend/wallet/routes.py) | `wallets`, `wallet_transactions`, `wallet_withdrawal_requests` | Shared balance writers exist, but wallet routes also contain separate direct SQL paths. The transporter permanent Rs 30,000 rule is implemented in [`withdrawal_limits.py`](../backend/wallet/withdrawal_limits.py#L9). |
| Saved methods/preferences | [`backend/payments/routes.py`](../backend/payments/routes.py), [`backend/shared/payments.py`](../backend/shared/payments.py#L456) | `saved_payment_methods`, `saved_payment_methods_safe`, `user_payment_preferences` | Business-only; token/brand/last-four/expiry stored; removal deactivates. No PAN/CVC columns exist. Sensitive preference mutations use login+CSRF but not re-authentication. |

Current duplication/overlap:

- `/complete-delivery` and `/mark-completed` are aliases for one transition; `/confirm-delivery` and `/verify-delivery` are aliases for another.
- `/accept-bid` and `/process-payment` remain as compatibility endpoints that refuse the legacy flow and direct callers to checkout.
- `shipment_status_history` records generic status changes while lifecycle tables record richer state. Future specific business events must own semantic transitions; generic duplicate `status_changed` events are discouraged.
- Payment state ownership is mostly centralized in `shared/payments.py`, but wallet mutations also exist in `wallet/helpers.py`, `wallet/routes.py`, `agreements/helpers.py`, and admin routes. Phase 1B contracts must identify allowed writers before any event outbox is attached.
- The four `rejected` bid rows in TEST are competing bids changed to rejected after a successful checkout; they are not rejected bid attempts. A future `matching.bid_attempt_rejected` event must not create a `shipment_bids` row.

### 3.5 Trip, delivery, disputes, chat, reviews, and notifications

[`backend/orders/lifecycle.py`](../backend/orders/lifecycle.py) is the current canonical One-Time transition layer. It documents and follows the lock order `shipment → trip → dispute → payment → wallet`.

- A transporter completion request moves the trip/shipment to `awaiting_client_confirmation`; it does not set `trip_completed_at`.
- Client Yes requires a valid review in the same transaction, releases payment once, and stamps genuine completion.
- Client No opens/reuses one open dispute and keeps payment held.
- A six-hour timeout moves to `admin_review`, opens/reuses one dispute, and does not pay or refund.
- Transporter-win resolution releases once, creates a later review requirement, and stamps genuine completion.
- Client-win resolution refunds once, sets `resolved_client`, leaves `trip_completed_at` null, and creates no review requirement.
- Composite foreign keys enforce exact shipment/trip/payment/client/transporter/chat relationships.
- One review per trip and one open dispute per trip are database-enforced.
- Chat text and media belong to `chat_messages`/Storage; they must never be copied into analytics or generic audit metadata.

### 3.6 Transporter, truck, driver, document, and business-profile surfaces

| Surface | Status | Current owner/persistence | Finding |
| --- | --- | --- | --- |
| Transporter profile | Partially implemented | Signup/profile attachment and payout routes; `transporter_profiles` | Company/fleet and payout-card summary exist. No canonical profile event family. |
| Trucks | Verified existing but unstandardized | [`backend/trucks/routes.py`](../backend/trucks/routes.py), `vehicles` | Create/configure/status/location/doc upload routes exist; no business audit events. |
| Drivers | Partially implemented | `drivers` table; `vehicles.driver_id`; also duplicated `vehicles.driver_name/driver_cnic` | No driver routes were found. Duplicate embedded driver fields create transition risk. |
| Documents | Partially implemented | [`backend/shared/storage.py`](../backend/shared/storage.py), `documents`, private `shipment-documents` bucket | Truck and chat upload paths exist; metadata/audit/evidence-access events are incomplete. |
| Business profile | Partially implemented | Signup writes `service_seeker_profiles`; common profile route updates `users` | No dedicated business-profile update service or event family. |
| Everyday profile | Verified existing and standardized for separation | `everyday_user_profiles` and role guards | No wallet/agreement/saved-method UI or backend access is intended. |
| Payment methods/preferences | Verified existing but unstandardized | Payment routes and tables | Business-only ownership and tokenization exist; re-auth and events are missing. |

### 3.7 Admin and authorization

[`admin_required()`](../backend/admin/routes.py#L40) combines Flask login with `platform_admin` role validation. State-changing admin routes generally require CSRF, but there is no general admin re-authentication contract and reasons are inconsistent:

- user block accepts an optional reason;
- withdrawal approval/rejection has no admin reason;
- agreement dispute resolution uses a note;
- commission publication requires a change summary and writes a second, mixed-purpose row to `user_action_logs`;
- One-Time dispute resolution requires admin notes and uses the canonical lifecycle/payment services.

No dispatcher role exists in the enum, code, or TEST policies. No new dispatcher-like role is permitted.

### 3.8 Frontend/API ownership

The implemented tracking/security/business consumers are concentrated in:

- auth pages and guards (`Login`, `Signup`, `ResetPassword`, `Unlock`, `useAuth`, `useClientAuth`, `useEverydayAuth`);
- client/everyday order, checkout, wallet, Terms, notification, chat, and review pages;
- transporter truck, matching, trip, wallet, settings, chat, and agreement pages;
- admin users, trucks, withdrawals, agreements, disputes, payments, and platform-settings pages;
- the globally mounted `ActivityTracker`.

| Domain | Verified frontend consumers |
| --- | --- |
| Authentication/session | [`Login.jsx`](../frontend-react/src/pages/auth/Login.jsx), [`ResetPassword.jsx`](../frontend-react/src/pages/auth/ResetPassword.jsx), [`Unlock.jsx`](../frontend-react/src/pages/auth/Unlock.jsx), role-detail submission helper, auth hooks, and role guards/layout logout handlers |
| Orders/matching/checkout | `PostOrder`, `MyOrders`, `ClientOrderDetail`, `BidCheckout`, `AvailableBids`, `MyBids`, `OrderTracking`, and `PendingTransporterReviewGate` |
| Wallet/methods/preferences | [`WalletWorkspace.jsx`](../frontend-react/src/components/wallet/WalletWorkspace.jsx), `BidCheckout`, transporter `earning.jsx`, transporter `settings.jsx`, and client wallet/dashboard pages |
| Delivery/dispute/review | `ClientOrderDetail`, `OrderTracking`, `PendingTransporterReviewGate`, `AdminDisputes`, and `AdminDisputeChat` |
| Chat/notifications | [`ChatWindow.jsx`](../frontend-react/src/components/chat/ChatWindow.jsx), [`NotificationBell.jsx`](../frontend-react/src/components/common/NotificationBell.jsx), client/transporter message pages, and unread-count polling in both main layouts |
| Trucks/location/documents | `add_truck`, `truck_configuration`, `truck_details`, `My Truck`, `track_truck`, transporter dashboard, and `AgreementTripMap` |
| Commission/Terms | `AdminPlatformSettings`, `PlatformFeesSection`, `TermsUpdateNotice`, and client/transporter Terms pages |
| Agreemental | Client/transporter Agreement pages plus `AdminAgreements`; tracked here as current workflow consumers, not as implemented Agreemental event tracking |
| Generic tracking | [`ActivityTracker.jsx`](../frontend-react/src/components/ActivityTracker.jsx) and [`useTracker.js`](../frontend-react/src/hooks/useTracker.js) |

Repository scans also found frontend calls for organization, shopkeeper, maintenance, fuel, predictions, about/contact, ratings, and other future/legacy APIs with no corresponding Flask blueprint in this repository. These calls are not verified capabilities and must not be treated as implemented analytics or audit owners.

### 3.9 Schema, migrations, and test mirrors

- [`supabase/schema.sql`](../supabase/schema.sql) is the canonical fresh-install mirror.
- Ten forward migrations exist under [`supabase/migrations`](../supabase/migrations).
- PostgreSQL integration mirrors in [`backend/tests/conftest.py`](../backend/tests/conftest.py) and `test_migration*.py` use isolated/disposable PostgreSQL databases or schemas and never fall back from `TEST_SUPABASE_DB_URL` to the shared application URL.
- Tests cover payment constraints, RLS, lifecycle integrity, coordinate integrity, everyday separation, dispatcher removal, and review concurrency/integrity.
- No tracking-registry contract tests exist yet; those are Phase 1B.

## 4. Actual TEST database capability inventory

### 4.1 Catalog summary

| Object kind | Count | Notes |
| --- | ---: | --- |
| Public tables | 43 | Every table has RLS enabled; `FORCE ROW LEVEL SECURITY` is not enabled. |
| Public views | 2 | `saved_payment_methods_safe`, `transporter_review_aggregates` |
| Constraints | 218 | Includes primary, foreign, unique, and CHECK constraints. |
| Indexes | 122 | Includes lifecycle and financial idempotency/uniqueness indexes. |
| Non-internal public triggers | 21 | Includes updated-at, immutable-version, profile-separation, and shipment-history triggers. |
| Public functions | 9 | `current_app_role`, `current_app_user_id`, `enforce_single_client_profile`, `handle_new_auth_user`, `is_admin`, `log_shipment_status_change`, `prevent_version_mutation`, `rls_auto_enable`, `set_updated_at` |
| RLS policies | 94 | Admin and party/owner policies cover current tables. |
| Public enum | 1 | `app_role`: `admin`, `customer`, `transporter`, `fuel_station_manager`, `shopkeeper`; no dispatcher. |

The Auth trigger `auth.users.trg_on_auth_user_created` is present. The Storage bucket `shipment-documents` is private and contained zero objects. The only Storage object policy found was `shipment_docs_admin_all`.

### 4.2 Tables, views, and safe aggregate row counts

| Domain | Objects with verified TEST row counts |
| --- | --- |
| Identity/security | `users` 19; `login_activity` 44; `trusted_devices` 31; `password_reset_otps` 0; `reset_tokens` 0 |
| Client/transporter profiles | `service_seeker_profiles` 2; `everyday_user_profiles` 2; `transporter_profiles` 14; `fuel_station_profiles` 0; `shopkeeper_profiles` 0 |
| Fleet/documents | `drivers` 0; `vehicles` 42; `documents` 0 |
| One-Time | `shipments` 26; `shipment_bids` 26; `shipment_trips` 18; `shipment_status_history` 90; `shipment_no_show_tracking` 18; `shipment_cancellations` 0 |
| Money | `payments` 18; `wallets` 6; `wallet_transactions` 18; `wallet_withdrawal_requests` 0; `saved_payment_methods` 1; `user_payment_preferences` 1 |
| Delivery/dispute/review | `shipment_disputes` 9; `shipment_trip_reviews` 8; `shipment_notifications` 63 |
| Chat | `chat_threads` 18; `chat_messages` 2 |
| Commission/Terms | `commission_policies` 2; `terms_versions` 1; `terms_acknowledgements` 0 |
| Agreemental | All nine Agreemental tables currently have 0 rows. |
| Existing generic tracking | `user_action_logs` 1,899 |

Verified status aggregates:

- shipments: 8 open, 4 ready-to-start, 1 in-progress, 2 admin-review, 1 delivery-disputed, 8 completed, 2 resolved-client;
- bids: 18 accepted, 4 pending, 4 rejected;
- trips: 4 ready-to-start, 1 in-progress, 2 admin-review, 1 delivery-disputed, 8 completed, 2 resolved-client;
- payments: 8 held, 8 released, 2 refunded;
- disputes: 3 open, 4 resolved-transporter, 2 resolved-client;
- wallet transactions: 3 top-up, 2 card-shortfall top-up, 5 order-payment, 8 order-payout;
- notifications: 60 unread.

### 4.3 Relevant column and default capability

The full 43-table column set was compared programmatically with the canonical schema and matched exactly. Important shapes are:

| Object | Verified key capability |
| --- | --- |
| `users` | Auth UUID link; enum role plus legacy role; contact/profile fields; MPIN hash/flag; JSON settings; block fields; timestamps. |
| `login_activity` | Optional user; raw login identifier/method; status/failure reason; raw IP/user agent; timestamp. |
| `trusted_devices` | Unique raw `device_token`; user FK; created/last-seen timestamps. |
| `user_action_logs` | Text identity/role/type/name/page; arbitrary nullable JSONB payload; timestamp. No event ID/version/category/correlation/retention/consent columns. |
| `shipments` | Client, pickup/drop-off text and optional coordinate pairs, cargo/dimensions, required truck types, status, accepted bid, payment state, seeker/commission/Terms snapshots. |
| `shipment_trips` | Exact accepted bid/transporter/truck; status; genuine-completion and confirmation timestamps; optional route coordinates/distance. |
| `payments` | Exact trip/shipment/client/transporter; immutable amount/funding/commission/Terms snapshots; provider/idempotency fields; held/released/refunded timestamps. |
| `wallet_transactions` | Wallet/user/type/amount/balance; optional gross/fee/reference/provider fields. |
| `shipment_disputes` | Exact shipment/trip/payment/client/transporter/chat; trigger/status/statements/admin resolution fields. |
| `shipment_trip_reviews` | Exact shipment/trip/client/transporter; rating 1–5; optional comment; timestamp. |
| `vehicles` | Owner/optional driver, capacities, body/feature compatibility, operating city/coordinates/radius, provider tracking IDs, embedded driver fields, document paths, status. |
| `saved_payment_methods` | User, provider token, brand, last four, expiry, default/status, timestamps. No PAN/CVC field. |
| `user_payment_preferences` | User, owned default-method composite FK, auto-shortfall flag, timestamps. |

Defaults and nullability match [`supabase/schema.sql`](../supabase/schema.sql); future migrations must update that mirror in the same commit.

### 4.4 Constraints, indexes, triggers, functions, RLS, grants, and safe views

Important verified integrity capabilities include:

- financial CHECK constraints for nonnegative amounts, funding split, commission split, total card charge, processing-fee range, and snapshot sums;
- `uniq_payments_active_per_shipment`, `uniq_payments_idempotency_key`, `uniq_wallet_lifecycle_txn`, and `uniq_wallet_topup_idempotency`;
- exact composite relationship constraints across accepted bid, trip, payment, dispute, client, transporter, and chat;
- `uniq_open_dispute_per_trip`, `uniq_chat_thread_one_time`, `shipment_trip_reviews_trip_unique`, and `uniq_notification_event`;
- coordinate pair/range/finite checks and vehicle service-radius bounds;
- one service-seeker/everyday profile per user plus mutual-exclusion triggers;
- immutable commission-policy and Terms triggers;
- private provider-token base tables with a token-free `saved_payment_methods_safe` view;
- `transporter_review_aggregates`, which exposes aggregate rating/count only.

All current public tables have RLS enabled. Owner/party/admin policies exist for the major business tables. Base-table privileges for `saved_payment_methods` and `user_payment_preferences` are restricted to server roles, while the safe view is available to client roles. Because broad Supabase default grants exist on many objects and the safe view reports more grant types than SELECT, Phase 1B must prove effective privileges under `anon` and `authenticated` roles rather than inferring safety from grant names alone.

### 4.5 Capability-based migration assessment

| Repository migration | TEST capability | Assessment |
| --- | --- | --- |
| `20260721000000_commission_policies_and_terms.sql` | Tables, foreign keys, unique/check constraints, immutable triggers, indexes, policies | Verified present |
| `20260721120000_one_time_payment_foundation.sql` | Payment columns, method/preference tables, safe view, idempotency indexes, RLS/grants | Verified present |
| `20260721130000_tokenize_payout_cards.sql` | Token/brand/last-four payout fields and unique token index | Verified present |
| `20260722090000_vehicle_operating_location.sql` | City/lat/lng/radius columns and checks | Verified present |
| `20260723090000_everyday_user_separation.sql` | Separate profile tables and seeker snapshot | Verified present |
| `20260723100000_everyday_profile_hardening.sql` | Mutual-exclusion function/triggers and hardened policies | Verified present |
| `20260723110000_remove_dispatcher_role.sql` | Dispatcher absent from enum, function, policies, and current user roles | Verified present |
| `20260723120000_one_time_trip_completion_lifecycle.sql` | Lifecycle/dispute columns, exact relationship constraints, payment checks, unique indexes | Verified present |
| `20260724190000_one_time_coordinate_integrity.sql` | Pair/range/finite coordinate constraints | Verified present |
| `20260726200000_shipment_trip_reviews.sql` | Review table, exact FKs, one-per-trip uniqueness, view, RLS | Verified present |

No partial or out-of-order capability was detected. Stop if a future inspection finds a named capability missing, an unexpected extra application table/column, a migration only partially represented, or a migration ledger that conflicts with observed capability.

### 4.6 Safe anomaly and sensitive-column findings

All of the following aggregate anomaly counts were zero:

- payment funding, commission, and total-card-charge equation mismatches;
- a payment with both released and refunded timestamps;
- duplicate active payments, trips, order payouts, order refunds, reviews, or open disputes;
- payment, trip, bid, review, or dispute relationship/orphan mismatches;
- cross-user default payment methods;
- accepted bids without their matching trip;
- accepted bids with a basic weight/volume capacity mismatch;
- users over five current trusted-device rows;
- dispatcher/unknown current roles;
- users present in both client profile tables.

Sensitive-data risk exists by column design even where the data is legitimate:

- login identifiers, IPs, user agents, email/phone/CNIC/address;
- exact shipment/trip/vehicle coordinates and textual locations;
- device tokens, OTP/reset-token hashes and delivery target;
- provider/payment references and tokenized payment-method fields;
- chat/dispute/review/notification text and document/storage paths;
- arbitrary `user_action_logs.payload_json`.

There are no public columns named as raw PAN/card-number/CVC/CVV storage. This is a name/schema check, not proof that arbitrary text/JSON never contains such data.

## 5. Four separate event domains

| Domain | Purpose | Planned logical owner | Must not contain |
| --- | --- | --- | --- |
| Security events | Authentication, verification, device/session, risk, account protection, security administration | `security_events` plus security-specific supporting objects | General product clicks, business state history, raw secrets |
| Business audit events | Committed domain changes and immutable business evidence | `business_audit_events`, transactionally paired with the mutation via `event_outbox` as needed | Failed attempts presented as successful history, chat bodies, arbitrary frontend events |
| General analytics | Consent-aware product usage, attribution, funnels, and aggregate behavior | `analytics_events` | Passwords/OTP/payment secrets, private content, exact background GPS |
| Operational monitoring | Reliability, performance, failures, dependency health, incidents, release monitoring | Operational telemetry and `operational_incidents` | Business payload bodies, auth headers, DB URLs, user-visible raw stack traces |

Planned logical objects, all **Not implemented** in TEST:

`security_events`, `user_devices`, `user_sessions`, `otp_challenges`, `security_cases`, `security_case_events`, `security_alert_deliveries`, `admin_security_actions`, `business_audit_events`, `analytics_events`, `operational_incidents`, `event_outbox`, and `notification_deliveries`.

These names describe logical responsibilities, not a mandate to create thirteen exact tables. Phase 1B must first prove compatibility, reuse opportunities, RLS, retention, expected volume, and transactional ownership.

## 6. Planned common event envelope

This envelope is **Planned**, not implemented:

| Field | Contract |
| --- | --- |
| Event ID | Server-assigned globally unique ID; supports idempotency. |
| Canonical event name | Allowlisted stable name following `<domain>.<aggregate>.<past-tense action>`; no arbitrary frontend names. |
| Event version | Positive schema version tied to contract tests. |
| Category | One of security, business audit, analytics, or operations; never ambiguous. |
| Actor | Server-derived user ID and role, or explicit system/provider actor. |
| Subject user | Optional affected user, distinct from actor. |
| Related entities | Typed IDs for order, bid, trip, payment, wallet transaction, dispute, chat, review, policy, notification, etc. |
| Request/correlation ID | Server-issued request ID and optional workflow/provider correlation. |
| Session/device references | Opaque safe IDs only; never raw session, CSRF, refresh, device, or provider tokens. |
| Source | Allowlisted server route/service, job, provider webhook, or validated client surface. |
| Environment | Explicit TEST/production separation. |
| Safe before/after state | Allowlisted minimal fields; no object dumps. |
| Reason code | Allowlisted stable code; free text separately restricted. |
| Metadata | Strict event-version schema; reject unknown keys, excessive size, and sensitive fields. |
| Timestamp | Server UTC timestamp; client time may be auxiliary and untrusted. |
| Retention class | Required class mapped to deletion/aggregation rules. |
| Consent category | Required where analytics/optional processing depends on consent. |

Canonical names are stable, lowercase, and dot-separated. Multiword aggregates or actions use lowercase snake case inside their segment. Examples are `one_time.payment.released`, `wallet.withdrawal.approved`, and `security.login.succeeded`. A rename requires an explicit versioned transition; do not silently invent aliases. The exact locked compact families `matching.<compound-past-tense-action>` and `notification.<past-tense-action>` are the only catalog exceptions to the three-segment form. The required Deferred outcome `one_time.qr_payment.amount_mismatch` is the sole noun-outcome exception to the past-tense action segment. These explicit names remain stable contracts and must not acquire invented aliases; every new family must follow the three-segment rule.

One committed business action has exactly one canonical domain owner even when an admin, scheduler, or provider performs it. The actor/source fields record that a platform admin, job, or provider caused the action; wrapper events must not restate the same outcome under another namespace. A separate admin-security event is allowed only when no more specific security or business event owns the action.

Arbitrary frontend event names and arbitrary metadata are forbidden. The server must derive identity, role, environment, session/device reference, and authoritative timestamps.

## 7. Security and login locked contract

Everything in this section is **Planned** unless explicitly cross-referenced as current.

### 7.1 Authentication event catalog

| Planned canonical event |
| --- |
| `security.signup.started` |
| `security.signup.gps_result_recorded` |
| `security.signup.email_otp_sent` |
| `security.signup.email_otp_failed` |
| `security.signup.completed` |
| `security.login.started` |
| `security.login.failed` |
| `security.login.gps_result_recorded` |
| `security.login.email_otp_sent` |
| `security.login.email_otp_failed` |
| `security.login.succeeded` |
| `security.login.new_device_detected` |
| `security.login.suspicious_detected` |
| `security.session.refreshed` |
| `security.session.expired_inactivity` |
| `security.session.revoked` |
| `security.logout.completed` |
| `security.password.changed` |
| `security.password_reset.requested` |
| `security.password_reset.completed` |
| `security.trusted_device.added` |
| `security.trusted_device.removed` |
| `security.account.locked` |
| `security.account.unlocked` |

Authentication failure metadata must use safe reason codes. It must not reveal whether an account exists to an unauthenticated caller or store submitted passwords/OTP values.

### 7.2 GPS and OTP

- Attempt GPS on every signup and every full login.
- Email OTP is mandatory on every full login, including GPS accuracy within 100 metres.
- GPS denied/unavailable raises risk but may proceed after verified Email OTP unless combined risk reaches a direct-block condition.
- Future GPS-denied flow requires Email OTP plus SMS OTP.
- SMS remains Deferred and disabled until a real provider exists. There must be no fake SMS endpoint or fake success.
- Planned sender: `security@digitransx.d-hag.com`.
- Mailbox/subdomain ownership plus SPF, DKIM, DMARC, and provider setup must be complete before Email OTP implementation.
- OTP is six digits from a cryptographically secure generator, expires in five minutes, allows at most five attempts, and has a 60-second resend cooldown.
- Challenge is purpose- and device-bound; storage is HMAC-protected. Plain OTP is never stored or logged.
- A full authenticated session is issued only after every required verification succeeds.

### 7.3 Risk engine

- Score range: 0–100.
- Low: 0–29; Medium: 30–59; High: 60–79; Critical: 80–100.
- Direct-block conditions are separate from the numeric score and must be versioned.
- Rollout: `disabled → shadow → alert_only → step_up → enforced`.
- Shadow mode precedes enforcement and records outcomes without changing access.
- GPS/IP differences are risk signals, not standalone proof.
- Trusted devices never skip GPS or OTP.
- High-risk sessions restrict sensitive actions under a versioned policy.

### 7.4 Devices and sessions

- Use a random non-invasive device ID. Do not use IMEI, SIM number, or invasive fingerprinting.
- Maintain one independently revocable session per device.
- Access token lifetime: 15 minutes.
- Refresh tokens rotate and are stored only as hashes; replay revokes the token family and raises security evidence.
- Seven days of genuine inactivity requires full login.
- Background polling, `ActivityTracker`, and scheduler activity never refresh genuine user activity.
- Absolute session lifetime: 30 days.
- Maximum five active devices.
- Provide user device/session listing and revocation plus a “This wasn’t me” response.
- Logout immediately revokes the current session.
- Password reset revokes every session.

### 7.5 Security dashboards and administration

Planned User Security Center:

- sessions/devices with masked IP and approximate location;
- login/verification history;
- revoke, trusted-device removal, and “This wasn’t me” actions;
- mandatory critical alerts that cannot be disabled.

Planned Admin Security Console:

- risk events, security cases, alert delivery, session/device actions, and sensitive-action freeze;
- exact GPS only for authorized purpose, with every access audited;
- admin re-authentication and mandatory reason for security actions;
- no password, OTP, raw token, or secret visibility.

### 7.6 Security retention baselines

- Exact login GPS: 90 days.
- IP/device/security details: 12 months.
- High-risk, account-lock, and admin-security evidence: 24 months.

These are internal baselines pending professional privacy/legal review.

## 8. Business Audit locked contract

Business events represent committed business changes. The business event/outbox row must be created in the same transaction as its mutation. Failed attempts belong to sanitized operational or security evidence, not successful business history.

### 8.1 One-Time orders, bids, and checkout

| Planned canonical event | Ownership note |
| --- | --- |
| `one_time.order.created` | Committed order insert |
| `one_time.order.updated` | Material committed edit |
| `one_time.order.cancelled` | Canonical cancellation |
| `one_time.order.expired` | Expiry transition owner |
| `one_time.order.reopened` | Reopen transition owner |
| `one_time.bid.submitted` | Successful bid insert only |
| `one_time.bid.updated` | Material bid update |
| `one_time.bid.withdrawn` | Successful withdrawal |
| `one_time.bid.accepted` | Paid checkout transaction |
| `one_time.bid.rejected` | Competing stored bid changed to rejected |
| `one_time.bid.expired` | Stored bid expiry |
| `one_time.checkout.completed` | Atomic held-payment/accept/trip result |
| `one_time.checkout.cancelled` | Cancelled checkout intent/workflow |
| `one_time.checkout.reversed` | Compensating business reversal |

Generic duplicate `status_changed` events are discouraged when a specific canonical transition owns the change.

### 8.2 Payments, wallet, commission, payout, and refund

Planned events:

- `one_time.payment.held`
- `one_time.payment.disputed`
- `one_time.payment.released`
- `one_time.payment.refunded`
- `one_time.payment.reversal_recorded`
- `one_time.payment.provider_webhook_applied`
- `wallet.topup.completed`
- `wallet.order_funding.debited`
- `wallet.card_shortfall.credited`
- `wallet.order_refund.credited`
- `wallet.transporter_payout.credited`
- `wallet.withdrawal.requested`
- `wallet.withdrawal.approved`
- `wallet.withdrawal.rejected`
- `wallet.security_lock.enabled`
- `wallet.security_lock.disabled`
- `commission.policy.created`
- `commission.policy.scheduled`
- `commission.policy.activated`
- `commission.policy.deactivated`
- `commission.policy.activation_cancelled`
- `terms.version.created`
- `terms.version.published`
- `terms.version.retired`
- `terms.version.publication_cancelled`
- `terms.acknowledgement.recorded`
- `terms.acknowledgement.reconfirmed`

Locked equations and invariants:

- wallet funded + card funded = bid;
- company fee + transporter amount = bid;
- total card charge = card funded + processing fee;
- processing fee is excluded from commission;
- payment can be released or refunded, never both;
- checkout-time commission snapshots are immutable;
- the existing transporter Rs 30,000 rule must not be overwritten;
- wallet transaction and withdrawal numerical limits will be updated only in a separate bounded task.

Current payment/wallet tables and canonical services are strong reuse candidates. Future events must reference, not duplicate, their authoritative amounts and IDs.

### 8.3 Trip, delivery, dispute, chat, and review

Planned events:

- `one_time.trip.created`
- `one_time.trip.started`
- `one_time.delivery.completion_requested`
- `one_time.delivery.confirmed`
- `one_time.delivery.rejected`
- `one_time.delivery.confirmation_timed_out`
- `one_time.trip.completed`
- `one_time.trip.resolved_client`
- `one_time.dispute.opened`
- `one_time.dispute.transporter_statement_submitted`
- `one_time.dispute.admin_reviewed`
- `one_time.dispute.resolved_transporter_win`
- `one_time.dispute.resolved_client_win`
- `one_time.dispute.evidence_accessed`
- `one_time.chat.thread_created`
- `one_time.chat.message_sent`
- `one_time.chat.message_read`
- `one_time.chat.thread_closed`
- `one_time.review.submitted`
- `one_time.review.replay_detected`
- `one_time.review.moderated`

Locked behavior:

- a completion request is not genuine completion;
- `trip_completed_at` represents genuine completion only;
- Client Yes requires the mandatory review atomically;
- Client No opens exactly one dispute;
- six-hour timeout enters admin review without automatic payout or refund;
- transporter win releases once and requires a later review;
- client win refunds once and creates no review requirement;
- preserve exact order/trip/payment/client/transporter/chat relationships;
- lock in order `shipment → trip → dispute → payment → wallet`;
- never duplicate chat message text into analytics or audit metadata.

### 8.4 Transporter operations and matching

Planned transporter-operation families:

- `transporter.profile.created`
- `transporter.profile.updated`
- `transporter.profile.status_changed`
- `transporter.profile.verification_submitted`
- `transporter.profile.verified`
- `transporter.profile.verification_rejected`
- `transporter.profile.payout_method_changed`
- `transporter.truck.created`
- `transporter.truck.updated`
- `transporter.truck.activated`
- `transporter.truck.deactivated`
- `transporter.truck.location_updated`
- `transporter.truck.document_linked`
- `transporter.truck.archived`
- `transporter.truck.verification_changed`
- `transporter.driver.created`
- `transporter.driver.updated`
- `transporter.driver.activated`
- `transporter.driver.deactivated`
- `transporter.driver.assigned_to_truck`
- `transporter.driver.unassigned_from_truck`
- `transporter.driver.document_linked`
- `transporter.driver.verification_changed`
- `transporter.document.uploaded`
- `transporter.document.replaced`
- `transporter.document.verification_requested`
- `transporter.document.verified`
- `transporter.document.rejected`
- `transporter.document.expired`
- `transporter.document.archived`
- `transporter.document.accessed`

All transporter-operation events above are **Planned**. The current profile, truck, driver, and document capabilities described in section 3.6 remain unchanged and must not be interpreted as implementing this catalog.

Planned matching events:

- `matching.bid_eligibility_validated`
- `matching.checkout_eligibility_revalidated`
- `matching.bid_attempt_rejected`
- `matching.policy_updated`

Locked matching principles:

- required capacity may use a larger compatible truck;
- exact-capacity truck is eligible;
- smaller capacity is rejected;
- liquid required volume is `max(explicit CBM, litres/1000)`;
- missing/invalid truck capacity fails closed when capacity is required;
- pickup location drives discovery;
- service radius is enforced;
- important bid/checkout decisions snapshot policy version and safe eligibility evidence;
- do not create one business-audit row per truck shown in an availability list.

### 8.5 Admin, commission, Terms, notifications, and scheduler

The only planned admin fallback event is:

- `admin.security_action.performed`

It applies only to a genuine admin-security action for which no more specific canonical security or business event exists. Admin account lock/unlock uses `security.account.locked` or `security.account.unlocked`. Wallet withdrawal decisions use the wallet withdrawal events. One-Time dispute decisions use the two specific dispute-resolution events. Commission actions use the commission-policy family. The actor envelope records the platform admin; competing `admin.withdrawal.*`, `admin.dispute.*`, and `admin.commission_policy.*` wrapper events are forbidden.

Planned notification family:

- `notification.created`
- `notification.delivery_attempted`
- `notification.sent`
- `notification.delivered`
- `notification.failed`
- `notification.retry_scheduled`
- `notification.failed_final`
- `notification.action_completed`

Planned scheduler/worker run family:

- `system.job.started`
- `system.job.completed`
- `system.job.failed`
- `system.job.skipped`
- `system.job.lock_not_acquired`
- `system.job.manual_triggered`

Contract:

- admin mutation requires re-authentication and a reason;
- no dispatcher-like role;
- commission policies are versioned and immutable;
- existing transactions retain old snapshots;
- published Terms versions are immutable;
- Terms acknowledgement links user, role, version, and content hash;
- notification delivery is idempotent;
- scheduler job events are separate from business transition events;
- exactly one scheduler owner; web-process scheduler remains default-off.

Scheduler/worker run events describe execution, failure, skip, and ownership outcomes. They never replace or duplicate the canonical business transition caused by a successful job.

Current Terms acknowledgements link user and version but do not store actor role or content hash, so the locked contract is only Partially implemented.

### 8.6 Business profile, wallet preferences, and saved methods

Planned events:

- `business.profile.created`, `business.profile.updated`, `business.profile.status_changed`;
- `business.payment_method.added`
- `business.payment_method.default_changed`
- `business.payment_method.deactivated`
- `business.payment_method.expired`
- `business.payment_method.provider_revoked`
- `business.payment_preference.created`
- `business.payment_preference.updated`
- `business.payment_preference.auto_shortfall_enabled`
- `business.payment_preference.auto_shortfall_disabled`
- `business.payment_preference.default_method_changed`

These events are **Planned**. Current tokenized saved-method and preference routes remain Verified existing but unstandardized; listing this family does not promote them to an implemented event contract.

Contract:

- saved methods/preferences are business-only;
- everyday users have no wallet/agreement/saved-method surface;
- never store PAN, CVC, or raw provider tokens;
- deactivate tokenized methods rather than destroying financial history;
- sensitive preference changes require re-authentication;
- reuse current wallet events rather than duplicating them.

### 8.7 Future Raast QR payment

**Deferred** until real merchant-provider onboarding.

- Dynamic Raast P2M QR is preferred.
- Card and QR are separate payment methods.
- Everyday full-QR and Business wallet-plus-QR shortfall are planned.
- QR cannot auto-charge.
- QR payload contains a provider-generated/signed opaque reference, never plaintext internal user/order/trip data.
- Intent initially binds client + order + bid.
- Trip/payment are created only after verified provider confirmation.
- Provider webhook/API is authoritative; screenshots are not proof.
- Verify exact amount, currency, merchant, and reference.
- Partial, over, late, and mismatched payments enter reconciliation.
- QR fee policy remains pending provider contract and then-current regulation.
- Card processing fee must not be copied automatically to QR.

Deferred One-Time QR-payment outcomes:

- `one_time.qr_payment.intent_created`
- `one_time.qr_payment.confirmed`
- `one_time.qr_payment.expired`
- `one_time.qr_payment.cancelled`
- `one_time.qr_payment.failed`
- `one_time.qr_payment.amount_mismatch`
- `one_time.qr_payment.refunded`
- `one_time.qr_payment.webhook_applied`

These events remain **Deferred**. Provider-specific sub-events may be added only after a real merchant contract defines authoritative provider states; they must not replace or compete with these One-Time business-domain outcomes.

## 9. General Analytics locked contract

General Analytics is **Planned** as a separate system.

Allowed ownership:

- genuine page views and navigation;
- safe search/filter/sort;
- important CTA and feature usage;
- form start, validation, step, and abandonment without field values;
- referrer/UTM attribution;
- non-invasive device/display context;
- a separate 30-minute analytics session;
- idempotent client event IDs;
- consent categories;
- strict TEST/production separation.

Explicitly prohibited:

- keystroke logging;
- clipboard reading;
- browser/search-history access;
- hidden camera/microphone access;
- password, OTP, PAN, or CVC capture;
- full session replay by default;
- private chat or document contents;
- exact background GPS;
- invasive cross-site fingerprinting.

Current `ActivityTracker` does not meet this contract and must not simply be redirected to `analytics_events`. Phase 4 must replace or constrain it behind allowlists, consent, schemas, redaction, size limits, and client-event idempotency.

Retention baselines:

- raw analytics: 13 months;
- sanitized aggregates: 3 years.

## 10. Funnels, KPIs, and integrity guardrails

Planned funnels:

1. Everyday One-Time order: order start → valid submission → eligible discovery → bid → checkout → trip → delivery decision → mandatory review.
2. Transporter: profile/truck ready → eligible order viewed → bid attempted → bid accepted → trip started → delivery resolved → payout/review.
3. Business One-Time wallet/payment: order → bid → quote → wallet/card funding → held payment → resolution.
4. Card/wallet/QR: method selected → intent/charge → authoritative confirmation → held funding → release/refund/reconciliation.
5. Dispute: completion request → client No/timeout → case evidence → admin decision → release/refund.
6. Mandatory review: genuine completion → review required → review submitted; client-win exits with no review requirement.

Every KPI definition must include:

- numerator;
- denominator;
- time window;
- entity grain;
- included/excluded statuses;
- environment;
- dummy/real payment distinction;
- metric version;
- owner;
- last validation date.

Zero-tolerance guardrails:

- duplicate active payments;
- duplicate trips;
- duplicate payouts/refunds;
- released and refunded timestamps on the same payment;
- rejected bid attempt creating a bid row;
- cross-user payment method use;
- orphan relationships;
- raw PAN/CVC findings;
- unauthorized role access;
- duplicate mandatory review;
- invalid matching acceptance.

The 2026-07-31 TEST aggregate checks were zero for every database-checkable guardrail listed above. Unauthorized runtime access and arbitrary JSON/text contamination require contract/security tests and cannot be proven from catalog counts alone.

## 11. Operational Monitoring locked contract

Operational Monitoring is **Planned** separately from analytics and business history:

- frontend errors and unhandled rejections;
- route/resource/API failures;
- Web Vitals and frontend performance;
- backend/API failures and latency;
- database errors, locks, and pool health;
- provider and webhook health;
- scheduler heartbeat and single-owner detection;
- liveness, readiness, and internal health;
- P0–P3 incident lifecycle;
- release monitoring;
- sampling and deduplication.

Initial Web Vitals targets:

- LCP ≤ 2.5 seconds;
- INP ≤ 200 ms;
- CLS ≤ 0.1.

Initial internal API p95 planning baselines:

- ordinary authenticated reads: ≤ 500 ms;
- ordinary validated writes without an external provider: ≤ 750 ms;
- checkout, payout/refund, and lifecycle transactions: ≤ 1.5 seconds excluding external-provider time;
- external-provider and webhook handling: ≤ 2 seconds for local processing, with provider latency reported separately.

These are internal planning baselines, not public SLAs. They must be split by route, environment, cache state, payload class, and dummy/real provider before enforcement.

Forbidden in operational telemetry:

- request/response bodies;
- secrets and tokens;
- DB URLs;
- authorization/cookie headers;
- raw provider payloads;
- raw stack traces exposed to users.

## 12. Retention matrix

| Data/evidence class | Internal baseline | Status |
| --- | ---: | --- |
| Exact login GPS | 90 days | Planned; legal/privacy review pending |
| IP/device/security details | 12 months | Planned |
| High-risk/account-lock/admin-security evidence | 24 months | Planned |
| Raw analytics | 13 months | Planned |
| Sanitized analytics aggregates | 3 years | Planned |
| Routine operational logs | 30–90 days | Planned by source/severity |
| Detailed traces | 14–30 days | Planned |
| Performance metrics | 13 months | Planned |
| Aggregated performance trends | 3 years | Planned |
| Routine scheduler health | 90 days | Planned |
| P0/P1 incidents | 3 years | Planned |
| Financial-integrity evidence | 7-year business baseline | Planned; professional legal/accounting review pending |

Retention jobs must be observable, retryable, scoped by environment, and proven on disposable PostgreSQL before shared TEST. Retention must never silently delete business state needed for financial or dispute integrity.

## 13. Code/database compatibility matrix

| Area | Current runtime owner | Current object | Actual TEST capability | Reuse / missing / duplication | Safe future strategy | Stop condition |
| --- | --- | --- | --- | --- | --- | --- |
| Auth event evidence | Auth routes/helper | `login_activity` | Present; 44 rows; RLS | Reuse as transitional source only; raw identifier/IP and narrow schema | Dual-write validated security events, then migrate readers; do not overload table | Unknown consumers, unclassified sensitive fields, or inconsistent timestamps |
| Device registry | Auth helper | `trusted_devices` | Present; unique raw token | Concept reusable; storage/session model incompatible | Introduce opaque device ID and hashed credential separately; explicit transition | Any path silently invalidates or trusts existing devices |
| Sessions | Flask cookie | None | No `user_sessions` | Not reusable as durable session store | Add server session/token-family model behind disabled state | Cannot distinguish polling from genuine activity |
| OTP | Auth/profile helpers | `password_reset_otps` | Has hashed OTP, attempts, purpose | Partial reuse; 10-minute expiry/text timestamps/no device binding/HMAC | New challenge contract; preserve reset flow until cutover | Provider/domain controls or replay/resend controls absent |
| Risk/security cases | None | None | Absent | Missing | Disabled → shadow foundation first | Any enforcement before shadow validation |
| Generic tracking | ActivityTracker/API | `user_action_logs` | Present; arbitrary JSON | Incompatible for all four canonical domains | Stop broad capture; allowlisted analytics replacement; retain/administer legacy data | Sensitive-field inventory or retention unknown |
| Shipment status history | DB trigger | `shipment_status_history` | Present and consistent | Reuse as status evidence; not full audit | Reference from business events; avoid duplicate generic events | Trigger semantics drift or missing actor context not addressed |
| Business event transactionality | Domain services | Domain tables only | Strong transaction boundaries in key flows | Missing append-only business envelope/outbox | Add within existing transactions after writer map/locks are proven | Any mutation has multiple uncoordinated writers |
| Checkout/payment | `shared/payments.py` | Payment/wallet/trip tables | Constraints and anomalies clean | High-value reuse | Emit from canonical service only | Dummy/real provider ambiguity or provider crash reconciliation unresolved |
| Wallet | Shared helper plus route/admin/agreement writers | Wallet tables | Present, integrity indexes present | Writer overlap | Establish allowed-writer contract before events | Unmapped direct SQL writer |
| Delivery/dispute/review | `orders/lifecycle.py`, `orders/reviews.py` | Lifecycle tables | Strong exact FKs/unique constraints | High-value reuse | Same-transaction events, canonical lock order | Any route bypasses lifecycle service |
| Matching | `orders/helpers.py` and order routes | Shipment/bid/vehicle state | Current decisions consistent; no anomaly | Helper reusable; no policy version/evidence snapshot | Version rule set and snapshot decisive evidence only | Code and SQL policy disagree |
| Notifications | Shared helper | `shipment_notifications` | In-app idempotency for trip events | Reuse in-app intent; no delivery ledger | Separate notification intent from provider deliveries | Multiple provider sends without idempotency |
| Email | Direct SMTP helper | None | No delivery state | Incompatible for security OTP reliability | Provider abstraction plus delivery ledger before Email OTP | SPF/DKIM/DMARC/mailbox/provider not complete |
| Admin audit | Admin routes | `user_action_logs` plus domain state | One commission audit writer only | Mixed owner and incomplete coverage | Domain business events + separate admin security actions | Admin mutation lacks re-auth/reason |
| Commission/Terms | Shared commission service | Versioned tables | Immutable and capability-complete | Reuse | Add content hash/role acknowledgment contract forward-only | Existing snapshots could be rewritten |
| Saved methods/preferences | Payment service/routes | Tokenized tables/safe view | Present; cross-user anomaly zero | Reuse; re-auth/events missing | Add sensitive-action re-auth and events | Effective RLS/grants not proven under client roles |
| Operational monitoring | Basic scheduler logging | None | No incident/telemetry objects | Missing | Structured redacted telemetry and health contracts | Body/header/secret collection cannot be excluded |
| Analytics | ActivityTracker | `user_action_logs` | Broad legacy capture | Existing data may support limited historical aggregates only | New consent-aware allowlisted pipeline | Attempt to migrate arbitrary payloads without classification |
| Agreemental tracking | Agreement routes/helpers/scheduler | Agreement tables | Workflow exists; tables empty in TEST | Future extension | Reuse shared infrastructure, separate Agreemental event rules | Any change alters One-Time contract |

## 14. Architecture and rollout

0. **Inventory and registry** — this file only.
1. **Phase 1A — Legacy tracking containment (Planned)** — the first runtime phase, before broader event-foundation work:
   - stop logging request and response bodies;
   - stop generic form-field capture;
   - stop placing CSRF/token-shaped values in analytics payloads;
   - stop trusting frontend-supplied user identity;
   - restrict event names and metadata;
   - add size and redaction guards;
   - preserve existing `user_action_logs` rows until a separately authorized classification/retention decision;
   - do not silently redirect current arbitrary payloads into a new analytics table;
   - prove no current business route depends on unsafe tracker behavior.
2. **Phase 1B — Canonical event foundation (Planned)** — envelope schemas, writer registry, outbox decision, environment separation, and contract tests.
3. **Security** — observation first; risk shadow mode and alerts/cases; later Email OTP after provider/domain readiness. Device/session and raw-token migration is a later dedicated security workstream and must preserve or deliberately migrate MPIN compatibility.
4. **One-Time Business Audit** — attach same-transaction events to canonical One-Time services and prove idempotency/lock behavior.
5. **General Analytics** — replace broad tracker with consent-aware, allowlisted, idempotent analytics.
6. **Operational Monitoring** — structured errors/latency/health/provider/scheduler/release telemetry and incident lifecycle.
7. **Dashboards and retention** — user/admin security surfaces, KPI/funnel views, deletion/aggregation jobs, access audits.
8. **Final audit and freeze** — drift, privilege, retention, volume, performance, privacy, and integrity review.
9. **GPS tracking architecture afterward** — separate bounded architecture after the event foundations are stable.

Agreemental tracking remains a clearly marked future extension. It may reuse common security, analytics, operations, envelope, outbox, and delivery infrastructure, but must add separate Agreemental business rules only after Agreemental workflow implementation is reviewed. It must never overwrite One-Time behavior.

## 15. Code/database safety rules

- Inspect current code before any future database edit.
- Inspect the actual target database read-only afterward.
- Build an exact code/database compatibility matrix.
- Reuse correct existing structures.
- Stop on partial, incompatible, or unexplained state.
- Use forward-only migrations; never edit an applied migration.
- Use expand–migrate–contract for removals and renames.
- Never silently repair, delete, or recalculate data.
- Prove migrations and rollback/failure behavior on disposable PostgreSQL before TEST.
- Shared TEST requires explicit authorization.
- Update the schema mirror and this registry in the same commit.
- Require zero-reference proof before cleanup.
- Never force-push.

## 16. Do not log or store

- Passwords, plain OTPs, reset/session/refresh/CSRF/device tokens, service keys, Auth tokens, API keys, or authorization headers.
- PAN, CVC/CVV, magnetic-stripe data, raw provider payment tokens, or QR payload secrets.
- Full request/response bodies or automatic object serialization.
- Private chat message text, document contents, or unrestricted filenames/paths in analytics/audit/operations.
- Exact GPS except in the purpose-limited security or trip owner with access auditing and retention.
- Full IP/device details in user-facing views.
- Keystrokes, clipboard data, browser/search history, hidden camera/microphone data, full replay by default, or cross-site fingerprints.
- Raw stack traces in user responses, database URLs, or credentials in any telemetry.
- Arbitrary frontend event names or arbitrary metadata.

The current `ActivityTracker` violates the spirit of several of these prohibitions by capturing broad bodies/responses and a CSRF token-shaped `session_id`; it is explicitly classified as legacy/unstandardized and must not be treated as approved precedent.

## 17. Phase 1A/1B blockers and mandatory stop conditions

Stop implementation if any of the following is unresolved:

1. The exact writer registry for payment, wallet, admin, shipment, and notification mutations is incomplete.
2. Effective `anon`/`authenticated` privileges and RLS behavior are not proven in disposable PostgreSQL/Supabase-compatible tests.
3. Existing `user_action_logs` sensitive-field classification, retention, and access plan is not approved.
4. Polling/genuine-activity separation is not designed before inactivity enforcement.
5. Device/session credential hashing, rotation, replay, revocation, and migration behavior is not specified.
6. Email mailbox, DNS authentication, provider, delivery/retry, and abuse controls are incomplete.
7. Risk features, weights, direct blocks, and shadow evaluation dataset are not versioned.
8. An event cannot be written in the same transaction as its authoritative business mutation.
9. Dummy versus real payment/provider evidence is ambiguous.
10. A migration capability is partial, unexplained, or inconsistent with the schema mirror.
11. Retention would delete evidence required by disputes, financial integrity, or professional legal/accounting advice.
12. Any proposal mixes the four domains into `user_action_logs`.

## 18. Update checklist for every future tracking commit

- [ ] Identify the domain and single runtime owner.
- [ ] Add/update canonical event name, version, schema, status, and retention class here.
- [ ] Update the writer/consumer and code/database compatibility rows.
- [ ] Prove server-derived actor, role, environment, time, and correlation.
- [ ] Prove metadata allowlist, redaction, size limit, and prohibited-field rejection.
- [ ] Prove idempotency and same-transaction behavior where business state changes.
- [ ] Prove RLS, grants, safe views, and admin access.
- [ ] Prove TEST/production separation and dummy/real provider distinction.
- [ ] Update forward migration and `supabase/schema.sql` together when schema changes.
- [ ] Add contract tests for registry/code/schema drift.
- [ ] Add safe aggregate anomaly checks and rollback/failure tests.
- [ ] Re-run secret, PII, PAN/CVC, token, URL, and raw-body scans.
- [ ] Verify no unrelated files or behavior changed.
- [ ] Record verification date, Inventory base SHA, environment, limitations, and deferred work.

## 19. Registry catalog counts

At this verification point the registry explicitly names:

- 24 planned Security authentication/session/device/account events;
- 14 planned One-Time order/bid/checkout events;
- 27 planned payment/wallet/commission/Terms events;
- 21 planned trip/delivery/dispute/chat/review events;
- 31 planned transporter profile/truck/driver/document events;
- 4 planned matching events;
- 1 planned admin-security fallback event;
- 13 planned business-profile/payment-method/preference events;
- 8 planned notification events;
- 6 planned scheduler/worker run events;
- 8 Deferred One-Time QR-payment events;
- 13 planned logical data objects, all currently absent.

The canonical catalog therefore contains 149 Planned events plus 8 Deferred QR-payment events. Deferred events are reported separately and excluded from the Planned total. Counts describe registry entries, not implemented capabilities.
