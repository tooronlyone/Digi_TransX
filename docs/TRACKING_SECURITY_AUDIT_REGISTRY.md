# Digi_TransX Tracking, Security, Audit, Analytics, and Operations Registry

## 1. Purpose and authority

This registry is the human-readable source for the current architecture, verified implementation status, ownership boundaries, compatibility findings, and future contracts for Digi_TransX tracking, security, business audit, general analytics, and operational monitoring.

| Field | Verified value |
| --- | --- |
| Inventory base SHA | `0d1b5b2de4b92ec642f39cfec26b09b3aefce571` |
| Verification date | 2026-07-31 |
| Latest capability-status reconciliation | 2026-08-10; Phase 1A through Phase 1B-2C3A are implemented in main and authorized shared TEST. Phase 1B-2C3A was integrated at `3771b5e21f02dab1048e90e14131a00db90baf08`; it is not deployed to production. |
| Repository | `tooronlyone/Digi_TransX` |
| Branch used for this registry | `chore/tracking-architecture-registry` |
| Phase 1A implementation branch | `security/phase-1a-legacy-tracking-containment` |
| Phase 1A starting SHA | `68177dbcc2b891a0f5360e693755dead26b8d67d` |
| Baseline correction branch | `fix/schema-trigger-rls-baseline` |
| Phase 1B-1 implementation branch | `feature/phase-1b-canonical-event-foundation` |
| Phase 1B-1 ACL correction branch | `fix/phase-1b-service-role-event-acl` |
| Phase 1B-2A implementation branch | `feature/phase-1b2a-auth-events` |
| Phase 1B-2C0 feature branch | `feature/phase-1b2c0-device-session-mpin-contracts` |
| Phase 1B-2C1 feature branch | `feature/phase-1b2c1-durable-session-foundation` |
| Phase 1B-2C3A feature branch | `feature/phase-1b2c3a-durable-session-runtime` |
| Environment inspected | Authorized Supabase TEST project `fysu…goev` |
| Database inspection mode | Read-only transactions; every inspection ended with `ROLLBACK` |
| Scheduler state during inspection | Disabled with `DIGITRANSX_ENABLE_SCHEDULER=0`; no scheduler process active |
| Phase | Phase 0 registry; Phase 1A through Phase 1B-2C3A implemented in main and authorized shared TEST |

> **Planning/documentation only.** This file creates no routes, tables, views, functions, triggers, policies, jobs, dashboards, providers, or runtime behavior. Any object or event marked Planned or Deferred does not exist merely because it appears here.

The Inventory base SHA identifies the code/database state inspected during Phase 0. It is not the SHA of the documentation commit that introduced or later corrected this registry.

Runtime implementation remains authoritative when this registry and code disagree. A disagreement is a defect: every future tracking-related change must update this file in the same commit. Phase 1B-1 adds foundation contract tests; Phase 1B-2A adds PostgreSQL route, transaction, privacy, failure, activation, and convergence proofs for exactly four auth events. Phase 1B-2C0 adds catalog/projection contracts only. Phase 1B-2C1 added the canonical `user_sessions` database/service foundation without runtime wiring; Phase 1B-2C3A now uses that foundation as the sole runtime authentication authority.

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

The TEST database has 47 public tables and two public views. It contains the capabilities through the Phase 1B-2C3A durable-session runtime event migration, assessed by objects and constraints rather than by an application-owned migration-history table:

1. commission policies and Terms;
2. one-time payment foundation;
3. tokenized payout cards;
4. vehicle operating location;
5. everyday-user separation;
6. client-profile hardening;
7. dispatcher-role removal;
8. one-time trip completion lifecycle;
9. coordinate integrity;
10. shipment trip reviews;
11. schema-trigger/RLS baseline correction;
12. canonical event foundation;
13. canonical event ACL hardening;
14. password-login/logout event activation and integrated guard;
15. bounded signup event integration;
16. device/session/MPIN event contracts;
17. durable server-session foundation;
18. trusted-device hardening and three-event integration.
19. durable server-session runtime authority and two-event session integration.

The Phase 1B-1 foundation migration `20260731230000_canonical_event_foundation.sql` and forward ACL correction `20260731240000_canonical_event_acl_hardening.sql` are both applied to shared TEST. The initial foundation application exposed additive Supabase `service_role` default privileges; the applied correction validated the exact foundation, revoked the broad direct event-table grants, and restored only `DELETE`, `INSERT`, and `SELECT`. Final verification found signature `772212260b85fd6b5cd4aa35ca9ffdfb`, zero `service_role` projection access, zero `anon`/`authenticated`/`PUBLIC` event or projection access, and zero rows in both event tables. This capability assessment does not claim that an application-owned migration ledger exists.

The database also has the expected Auth-to-profile trigger on `auth.users`. Supabase-owned migration records exist in service schemas, but there is no application-owned public migration ledger; capability inspection is therefore mandatory.

### Known limitations and deferred features

- Full signup/login GPS, mandatory full-login Email OTP, risk scoring, device/session management, security cases, and security dashboards are **not implemented**.
- Flask signed state is non-authoritative and retains only bounded CSRF/presentation state; durable `user_sessions` plus the exact active same-user trusted device are the runtime authentication authority.
- Phase 1B-2C2 is implemented in main and authorized shared TEST: it stores only exact 32-byte SHA-256 token digests, preserves stable device/user ownership, enforces absolute expiry and explicit revocation, and rotates credentials under a row lock. A trusted device remains recognition evidence only, never an authenticated session.
- Historical `ActivityTracker` behavior captured broad request/response and form data and trusted frontend identity/event fields. Phase 1A contains the current client to one authenticated safe page-visit contract, but historical rows remain unclassified and the legacy table is still not the planned analytics foundation.
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
| Signup | Phase 1B-2C3A durable issuance implemented in main and shared TEST | [`signup()`](../backend/auth/routes.py) commits anonymous `security.signup.started` before external Auth creation. Its terminal caller-owned transaction atomically persists the public user/profile, successful `login_activity`, trusted-device mutation and event, durable session, `security.signup.completed`, and `security.session.issued`; session/device cookies and CSRF state issue only after commit. Mandatory failure rolls back terminal success evidence and uses bounded Auth compensation/reconciliation. | Main and shared TEST: `security_events`, `auth.users`, `users`, one role-profile table, `login_activity`, hardened `trusted_devices`, `user_sessions`; shared TEST has 12 integrated definitions and empty event tables after rolled-back verification | GPS and Email/SMS OTP remain Planned and unintegrated; provider messages, identity fields, credentials, and form values are excluded from canonical evidence. |
| Password login | Phase 1B-2C3A durable runtime implemented in main and shared TEST | [`login()`](../backend/auth/routes.py) independently commits `security.login.started` before provider verification, then atomically persists successful activity, applicable `last_login_at`, trusted-device mutation and event, one durable session, terminal login evidence, and `security.session.issued`. Cookies and CSRF state issue only after commit; terminal failure rolls back all success evidence. | Main and shared TEST: `security_events`, `login_activity`, `users`, hardened `trusted_devices`, `user_sessions`; shared TEST has 12 integrations | Public account-enumeration resistance and provider sanitization are unchanged. GPS, mandatory Email OTP, risk engine, session limits, and high-risk restrictions remain Planned. |
| Logout | Phase 1B-2C3A current-session revocation implemented in main and shared TEST | [`logout()`](../backend/auth/routes.py) validates durable authentication and CSRF, locks and revokes exactly the current session, and atomically writes `security.session.revoked` with `security.logout.completed`; local authentication state is cleared even if server persistence fails. | `user_sessions`, `security_events`, durable/device/Flask cookies | Other sessions are unaffected; logout-all remains Planned for 2C4. Anonymous/invalid-CSRF requests emit no logout event. |
| Password reset | Partially implemented | Forgot-password sends a six-digit Email OTP, stores a password hash of the OTP, enforces five attempts and a 15-minute cooldown, issues a signed reset token, and updates Supabase Auth. | `password_reset_otps`, `reset_tokens` | OTP expiry is 10 minutes, not the locked five; no 60-second resend control or HMAC challenge; reset does not revoke sessions/devices. |
| Password change | Partially implemented | [`request_password_change_otp()`](../backend/profile/routes.py#L59) and [`change_password()`](../backend/profile/routes.py#L95) reuse the OTP helpers. | Same OTP table | No session revocation or security-event contract. |
| Login activity | Verified existing but unstandardized; transaction ownership narrowed in Phase 1B-2A | [`record_login_activity()`](../backend/auth/helpers.py) still records identifier, method, status, failure reason, IP, and user agent. Password-login terminal writes can now use the route-owned transaction; signup and MPIN compatibility retain the existing standalone behavior. | `login_activity` | Transitional evidence is not weakened or repurposed; its raw identifier/IP fields remain outside canonical event payloads. |
| Trusted device / fast login | Phase 1B-2C2 implemented in main and authorized shared TEST | [`trusted_device_service.py`](../backend/auth/trusted_device_service.py) is the single transaction-participating owner for secure generation, SHA-256 digestion, current-digest-only resolution, creation, locked rotation, and revocation. The `dtx_device_token` cookie is HttpOnly, SameSite=Lax, path `/`, bounded to at most 30 days, and Secure outside explicit local development. Legacy MPIN authentication routes fail closed and clear the device cookie. | Hardened `trusted_devices`; retained `users.mpin_hash` and `users.mpin_enabled`; zero-row `user_sessions` keeps the stable `(trusted_device_id,user_id)` binding | Previous digests do not authenticate; secure MPIN enrollment/unlock/step-up remains Planned for 2C3, and device/session management UI remains Planned for 2C6. |
| Flask session | Phase 1B-2C3A non-authoritative compatibility state implemented in main | [`build_auth_success_response()`](../backend/auth/helpers.py) retains only bounded CSRF and presentation activity state. [`login_required()`](../backend/auth/helpers.py) requires the durable-session and exact trusted-device cookies, then derives `request.current_user`, role, and profile relationships from PostgreSQL. | `user_sessions` is authoritative; Flask state contains no authoritative user ID, role, profile identity, authentication flag, or durable token | Forged signed identity cannot authenticate. Passive `/auth/me` does not update durable genuine activity; inactivity enforcement remains Planned for 2C5. |
| Supabase session use | Verified existing but unstandardized | [`supabase_verify_password()`](../backend/shared/supabase_client.py) signs in with the anon client only to validate credentials, then signs out; returned Supabase tokens are discarded. Its strict password-login mode recognizes the installed Auth client's structured `invalid_credentials` code without parsing provider messages; unavailable, malformed, transport, timeout, and other provider failures fail closed. | Supabase Auth credential verification plus durable `user_sessions`; Flask state is CSRF/presentation-only | Supabase Auth sessions and Flask signed state are not the application session owner. Existing boolean-only callers retain their compatibility behavior. |
| Account block | Partially implemented | Login checks `users.is_blocked`; admin can toggle it with CSRF. | `users.is_blocked`, `users.block_reason` | No lock/unlock event, re-authentication, mandatory reason on unlock, case, alert, or session revocation. |
| GPS and risk | Not implemented | No signup/login GPS route, distance comparison, IP intelligence, score, tier, or rollout-state owner exists. | None | Must be introduced behind disabled/shadow states after data and privacy review. |

Security-sensitive current facts:

- `login_activity` has 44 rows; all 44 contain a login identifier and IP field.
- `trusted_devices` has 31 digest-only rows; no user exceeds five rows.
- `password_reset_otps` and `reset_tokens` each had zero rows at verification.
- Auth and public profiles both had 19 rows, with zero missing links in either direction.
- `public.user_sessions` is the sole runtime authentication authority, and [`backend/auth/session_service.py`](../backend/auth/session_service.py) is the canonical session-token owner. Session credentials use 32 bytes of secure randomness; PostgreSQL stores only their exact SHA-256 digest.
- Authentication requires both a valid durable session and its exact active, unexpired, unrevoked same-user trusted device. Trusted-device-only, session-only, forged Flask identity, unknown, expired, revoked, blocked, and cross-user states fail closed with one generic unauthorized response and local authentication-cookie clearing; invalid state never silently creates or repairs a session.
- The separate `dtx_session_token` cookie contains no identity, is HttpOnly, SameSite=Lax, path `/`, bounded to the database's 30-day absolute lifetime, and Secure outside explicit local development. Frontend JavaScript cannot read it. CSRF remains separate from authentication identity.
- The legacy MPIN authentication bypass remains disabled. Secure four-digit MPIN enrollment/unlock/attempt limits/lockout/change/disable/reset/action-bound step-up, `security.session.access_locked`, `.refreshed`, `.expired_inactivity`, logout-all, password/reset/block mass revocation, seven-day genuine-inactivity enforcement, session/device management UI, GPS, and Email/SMS OTP remain Planned.

### 3.2 Existing tracking and overlapping evidence

| Mechanism | Status | Writer/consumer | Finding |
| --- | --- | --- | --- |
| `POST /api/track` | Phase 1A containment implemented; still legacy | [`api_track()`](../backend/tracking/routes.py) plus the centralized [`contract.py`](../backend/tracking/contract.py) | Requires verified durable authentication and CSRF, does not refresh genuine user activity, accepts only the fixed `page_visit`/`page_view` contract, derives user ID/role from current database relationships, stores no analytics email/IP/User-Agent/session token, and rejects malformed, unknown, sensitive, or oversized payloads before opening the database. |
| `ActivityTracker` | Phase 1A containment implemented; still legacy | [`ActivityTracker.jsx`](../frontend-react/src/components/ActivityTracker.jsx) mounted in [`App.jsx`](../frontend-react/src/App.jsx#L352) | Emits authenticated router page visits only. It no longer patches `window.fetch`, reads request/response bodies, observes form values, or installs click/form listeners. |
| Legacy tracking client | Phase 1A containment implemented; still legacy | [`useTracker.js`](../frontend-react/src/hooks/useTracker.js) | Builds one fixed page-visit payload, removes query strings/fragments, sends CSRF only as a request header, and sends no claimed browser identity. No arbitrary `useTracker()` event API remains. |
| `user_action_logs` | Verified existing but unstandardized; writes contained | `/api/track` and the unchanged admin commission route | Historical TEST evidence remains 1,899 rows/five action types/138 names with broad payloads. New analytics writes are sanitized page visits only. The separate admin audit writer remains temporarily mixed until an explicitly authorized Phase 1B migration. |
| `login_activity` | Verified existing but unstandardized | Auth helper and settings security-activity route | Transitional security evidence only; must not become general audit/analytics storage. |
| `shipment_status_history` | Verified existing and standardized for its narrow purpose | `trg_shipments_status_history` / `log_shipment_status_change()` | Reliable shipment-status transition history, but not a general business event ledger and not sufficient for monetary or non-status changes. |
| Domain tables | Verified existing and standardized for state | Payment, wallet, lifecycle, dispute, review, chat, notification, policy, and Terms services | Authoritative business state. They are not an append-only common audit envelope. |

The four event domains defined later must not be collapsed into `user_action_logs`.

#### Phase 1A implemented legacy contract

Phase 1A is a bounded containment, not the canonical event foundation:

- allowed anonymous events: none; the client defines no anonymous event contract, and direct anonymous calls receive `401`;
- allowed authenticated event: `action_type=page_visit`, `action_name=page_view`;
- required safe fields: sanitized relative `page_url` and `metadata.navigation_source=router`;
- `page_url` is at most 255 characters, uses a restricted path character set, and has query strings/fragments removed;
- request body limit: 2,048 bytes; generic strings: at most 512 characters; object depth: at most two; object keys: at most eight; arrays are rejected;
- unknown event names, fields, metadata keys/values, non-object JSON, malformed JSON, wrong content type, and sensitive keys at any depth are rejected with a safe `4xx`;
- user ID and role come from verified durable authentication and the current database-derived user lookup; analytics email, IP, User-Agent, session ID, and CSRF value are not stored;
- rejected requests perform no tracking insert or commit, leave no partial analytics row, and do not log submitted values;
- endpoint authentication uses the existing session owner without refreshing `last_active_at`, so passive page analytics cannot create genuine user activity;
- the analytics sanitizer is endpoint-local and does not alter the existing admin commission audit writer.

Implementation files:

- `backend/tracking/contract.py`
- `backend/tracking/routes.py`
- `backend/auth/helpers.py`
- `frontend-react/src/hooks/useTracker.js`
- `frontend-react/src/components/ActivityTracker.jsx`

Focused tests:

- `backend/tests/test_tracking_containment.py`
- `backend/tests/test_coordinate_integrity.py`
- `frontend-react/tests/legacyTracking.test.mjs`

Phase 1A validation evidence:

- read-only TEST reinspection confirmed `transaction_read_only=on` and ended with `ROLLBACK`; no row values were selected;
- `user_action_logs` retained its existing nine-column shape, RLS-enabled/non-forced status, public insert/admin-all policies, and broad effective `anon`/`authenticated` grants;
- safe aggregates remained 1,899 rows, five action types, 138 action names, 1,899 payloads/session-ID keys, 1,738 input-data keys, 1,600 output-result/API-endpoint keys, 113 element-text keys, and a maximum observed payload size of 1,850 bytes;
- focused backend containment validation passed 47 tests;
- the complete backend run passed 275 tests and safely skipped 295 PostgreSQL tests because `TEST_SUPABASE_DB_URL` was not configured; the suite did not fall back to the shared application URL;
- all 14 frontend Node tests passed, changed-file ESLint was clean, and the production build completed with only bundle-size/plugin-timing warnings;
- Python compileall, `git diff --check`, duplicate route/contract/writer scans, broad-capture scans, sensitive-value scans, local-link/heading validation, catalog reconciliation, and SQLite/legacy-dialect scans passed.

Remaining legacy limitations:

- historical `user_action_logs` rows are preserved unchanged pending separately authorized classification/retention work;
- the table still mixes contained analytics with the existing admin commission audit writer;
- effective TEST grants remain broader than the application endpoint contract;
- no distributed rate limiter was added; authentication, CSRF, strict request size, and schema validation are the bounded abuse controls;
- Phase 1B-1 envelope schemas, canonical catalog/writers, explicit environment separation, RLS, idempotency, contract tests, and bounded `service_role` ACL hardening are **Implemented in main and shared TEST**. Phase 1B-2A activates exactly four password-login/logout definitions; Phase 1B-2B activates exactly `security.signup.started`, `security.signup.failed`, and `security.signup.completed` through `20260801130000_security_signup_event_integration.sql`. Those seven auth definitions and the three Phase 1B-2C2 trusted-device definitions are integrated in main and shared TEST, and the guard permits only integrated+writable definitions.

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
- Twenty forward migrations exist under [`supabase/migrations`](../supabase/migrations) in main. `20260801150000_durable_server_session_foundation.sql` is merged through commit `682b2dcf53ef10b3f56b6ed6b2395955442a0904` and applied to authorized shared TEST with Git-blob SHA-256 `11b32c6d7cbd70dd16fb3f2854d3eb615d922fcd58049c0462917f635e9ada20`; `20260801160000_trusted_device_hardening.sql` is merged through `eb10d8eff93499a67e424bea5a60fd0245d46c4f` and applied with SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`.
- PostgreSQL integration mirrors in [`backend/tests/conftest.py`](../backend/tests/conftest.py) and `test_migration*.py` use isolated/disposable PostgreSQL databases or schemas and never fall back from `TEST_SUPABASE_DB_URL` to the shared application URL.
- Tests cover payment constraints, RLS, lifecycle integrity, coordinate integrity, everyday separation, dispatcher removal, review concurrency/integrity, schema-trigger convergence, effective shipment/trip role visibility, the 162 + 8 catalog projection, strict envelopes, migration convergence, caller-owned writers, idempotency/concurrency, append-only enforcement, and event-table privileges.

## 4. Actual TEST database capability inventory

### 4.1 Catalog summary

| Object kind | Count | Notes |
| --- | ---: | --- |
| Public tables | 46 | Every table has RLS enabled; `FORCE ROW LEVEL SECURITY` is not enabled. |
| Public views | 2 | `saved_payment_methods_safe`, `transporter_review_aggregates` |
| Constraints | 261 | Includes primary, foreign, unique, and CHECK constraints. |
| Indexes | 141 | Includes lifecycle, financial, and canonical-event idempotency/uniqueness indexes. |
| Non-internal public triggers | 28 | Includes updated-at, immutable-version, profile-separation, shipment-history, and canonical-event contract/append-only triggers. |
| Public functions | 13 | Includes the baseline authorization helper and three canonical-event validator/enforcement functions. |
| RLS policies | 96 | Admin and party/owner policies cover current tables; the two event tables have server-writer policies. |
| Public enum | 1 | `app_role`: `admin`, `customer`, `transporter`, `fuel_station_manager`, `shopkeeper`; no dispatcher. |

The Auth trigger `auth.users.trg_on_auth_user_created` is present. The Storage bucket `shipment-documents` is private and contained zero objects. The only Storage object policy found was `shipment_docs_admin_all`.

The baseline application added exactly `trg_transporter_profiles_updated_at`, `trg_fuel_station_profiles_updated_at`, and `trg_shopkeeper_profiles_updated_at` to shared TEST by reusing `set_updated_at()`. It also installed the non-recursive shipment authorization helper/policy. Post-application reconciliation retained 43 tables, two views, 218 constraints, 122 indexes, and 94 policies; function count became 10 and non-internal trigger count became 24. All business row counts, safe financial totals, and existing profile `updated_at` values remained unchanged.

Shared TEST contains empty `security_events` and `business_audit_events` tables plus the 170-row `canonical_event_catalog_projection`; 162 definitions are Planned, 8 Deferred QR, 156 writable, and exactly 12 definitions are `integrated=true`. Phase 1B-2C2 changed the semantic signature from `3d9b730408336c82629c25342ddc7ea2` to `11043982605bef207d3b9a5626bd86d8` by integrating only the three trusted-device events; Phase 1B-2C3A then changed it to `87c1377e1404933c69b1a90ac9962937` by integrating only `security.session.issued` and `security.session.revoked`. `event_outbox` remains absent. `service_role` has exactly `DELETE`, `INSERT`, and `SELECT` on each event table and zero projection access; `anon`, `authenticated`, and `PUBLIC` have zero event or projection access. Only integrated+writable definitions are insertable; 144 writable-but-unintegrated Planned definitions, all six Operations definitions, and all eight Deferred QR definitions are rejected. Python and database projections reconcile exactly. Rolled-back verification left both event tables empty and created no TEST Auth account, session, device, login-activity, or business row.

The Phase 1B-2C3A current-final projection is implemented in main and authorized shared TEST with 170 rows: 162 Planned, 8 Deferred QR, 156 writable, 12 integrated definitions, 150 Planned-unintegrated definitions, 144 writable-unintegrated definitions, and six Operations definitions. Its semantic signature is `87c1377e1404933c69b1a90ac9962937`. The prior seven auth, three trusted-device, and two session definitions are integrated; all MPIN definitions and the remaining session definitions stay unintegrated.

Phase 1B-2C0 added `security.session.issued`, `security.session.access_locked`, `security.trusted_device.rotated`, `security.mpin.enrolled`, `security.mpin.changed`, `security.mpin.disabled`, `security.mpin.unlock_succeeded`, `security.mpin.unlock_failed`, `security.mpin.locked`, `security.mpin.reset_completed`, `security.mpin.step_up_succeeded`, and `security.mpin.step_up_failed`; it formalized contracts for the existing `security.session.refreshed`, `security.session.expired_inactivity`, `security.session.revoked`, `security.trusted_device.added`, and `security.trusted_device.removed`. Phase 1B-2C2 integrated exactly the three trusted-device names; Phase 1B-2C3A integrated exactly `security.session.issued` and `.revoked`. `security.session.refreshed`, `.expired_inactivity`, `.access_locked`, and all MPIN definitions remain Planned, writable, and unintegrated.

Phase 1B-2C2 migration `20260801160000_trusted_device_hardening.sql` was integrated at `eb10d8eff93499a67e424bea5a60fd0245d46c4f` and applied to authorized shared TEST from the immutable Git blob with SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`. Trusted-device rows remained 31 to 31; stable IDs/user ownership and the zero-row `user_sessions` same-user binding were preserved. Eligible legacy credentials were converted server-side to exact 32-byte SHA-256 digests without returning token values, and the raw `device_token` column was removed. Null, duplicate, invalid-length, and broken-owner counts were zero.

Phase 1B-2C3A is implemented in main and authorized shared TEST. `user_sessions` is the sole runtime authentication authority: full password signup/login atomically creates one digest-only session bound to the exact active same-user trusted device, then returns the raw opaque credential only in the separate HttpOnly `dtx_session_token` cookie (SameSite=Lax, path `/`, Secure outside explicit local development, 30-day bound). Flask's signed session retains only non-authoritative CSRF and presentation activity state; browser-supplied user ID, role, and profile identity are ignored. `/auth/me` validates without refreshing `last_genuine_activity_at`. Current-session logout locks and revokes exactly that session and writes `security.session.revoked` with `security.logout.completed` in the same transaction, while local cookies are cleared even if persistence fails.

Phase 1B-2C3A integration commit `3771b5e21f02dab1048e90e14131a00db90baf08` and migration `20260801170000_durable_session_runtime_events.sql` (immutable SHA-256 `fe4d8440ad683396b31da7ec8da0e335ceaa8936c1fb1c4d5f51a24058f57aeb`) are implemented in main and authorized shared TEST. The migration integrates exactly `security.session.issued` and `security.session.revoked`, changing the signature from `11043982605bef207d3b9a5626bd86d8` to `87c1377e1404933c69b1a90ac9962937`. Shared TEST retained `user_sessions` 0, `trusted_devices` 31, `security_events` 0, `business_audit_events` 0, `login_activity` 44, and `users` 19; all 47 public-table counts, financial aggregates, and unrelated fingerprints remained unchanged. The migration created no session, device, event, user, login-activity, or business fixture. `security.session.refreshed`, `.expired_inactivity`, and `.access_locked` remain Planned and rejected, as do all MPIN events. MPIN runtime remains Planned for 2C3B; logout-all and security/password/reset/account-block revocation for 2C4; seven-day genuine-inactivity processing for 2C5; the session/device dashboard for 2C6; GPS and mandatory Email/SMS OTP remain Planned.

Only the current digest resolves an active trusted device. `previous_token_digest` never authenticates; it exists only for bounded conflict/replay handling, is overwritten by later rotation, and remains bounded by revocation and absolute expiry. Rotation immediately invalidates the previous raw credential and concurrent rotations serialize under row locking. Expired and revoked devices fail closed, revoked rows cannot be silently reactivated, and maximum lifetime is 30 days. The migrated table has RLS enabled, one bounded `service_role` all-rows policy, seven expected constraints, and three expected unique indexes. `PUBLIC`, `anon`, and `authenticated` have zero privileges; `service_role` has exactly `SELECT`, `INSERT`, `UPDATE`, and `DELETE`, with no `TRUNCATE`, `REFERENCES`, `TRIGGER`, or `MAINTAIN`. Current-digest uniqueness and stable `(id,user_id)` ownership are enforced.

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
| `trusted_devices` | Unique 32-byte `token_digest`; optional 32-byte previous rotation digest; user FK and stable `(id,user_id)` session binding; created/last-used/absolute-expiry/revoked/rotated timestamps; service-role-only table access. |
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

All current public tables have RLS enabled. Owner/party/admin policies exist for the major business tables. Base-table privileges for `saved_payment_methods` and `user_payment_preferences` are restricted to server roles, while the safe view is available to client roles. Broad Supabase default grants still exist on many legacy objects, so effective role behavior must be tested rather than inferred from grant names.

The baseline audit reproduced PostgreSQL `42P17` under real `anon` and `authenticated` roles. `shipments_transporter_read` queried RLS-protected `shipment_trips`, while `trips_client_read` queried RLS-protected `shipments`, forming a policy cycle. The repository correction replaces the first cross-table policy subquery with the single boolean-only `is_transporter_assigned_to_shipment(bigint)` authorization helper. It is `STABLE`, `SECURITY DEFINER`, has `search_path=pg_catalog`, uses qualified relations and no dynamic SQL, returns no row content, is revoked from `PUBLIC`, and among client roles is executable only by `anon` and `authenticated`.

Disposable PostgreSQL tests and post-application real-role probes prove that the correction produces no `42P17`: anonymous and unrelated authenticated users see no protected shipment/trip rows; an owning client sees only its shipment/trip; an assigned transporter sees its related protected shipment/trip plus the pre-existing legitimate open-order surface; another transporter cannot see those protected rows; and a platform admin retains full access. The helper returns false outside a genuine transporter identity and cannot be used to enumerate another user's assignments. Shared TEST now has this corrected policy/helper state.

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
| `20260731220000_schema_trigger_rls_baseline.sql` | Three profile `updated_at` triggers plus non-recursive shipment/trip authorization helper and policy | Verified present in shared TEST; row/timestamp/financial reconciliation unchanged |
| `20260731230000_canonical_event_foundation.sql` | Two append-only event tables, catalog projection, bounded JSON validator, contract/UPDATE guards, indexes, RLS/service policy and grants | Verified applied in shared TEST with zero event rows; its additive `service_role` default-table ACL issue is corrected by the applied forward migration |
| `20260731240000_canonical_event_acl_hardening.sql` | Fail-closed foundation/signature validation followed only by event-table `service_role` revoke and narrow re-grant | Verified applied in shared TEST; final event-table privileges are exactly `DELETE`, `INSERT`, and `SELECT`, with signature `772212260b85fd6b5cd4aa35ca9ffdfb` |
| `20260801140000_device_session_mpin_event_contracts.sql` | Forward-only projection of bounded device/session/trusted-device/MPIN contracts; no event integration or runtime emitter | Merged into main and applied to authorized shared TEST; Git-blob SHA-256 `653a5859cefea10705b8b547519f73892059294d11e9da5e773f1e278d777bba`; signature `371c7010a0553c7953708dea164ed0bc` to `3d9b730408336c82629c25342ddc7ea2` |
| `20260801150000_durable_server_session_foundation.sql` | Canonical `user_sessions` relation, strict digest/ownership/lifecycle constraints, narrow service-role access, and unused caller-transaction-owned session service | Merged into main at `682b2dcf53ef10b3f56b6ed6b2395955442a0904` and applied to authorized shared TEST; SHA-256 `11b32c6d7cbd70dd16fb3f2854d3eb615d922fcd58049c0462917f635e9ada20`; zero session/event/fixture rows or business backfill created; no runtime session behavior activated |
| `20260801160000_trusted_device_hardening.sql` | Digest-only trusted-device storage, bounded expiry/revocation/locked rotation, narrow service-role access, and exactly three trusted-device event integrations | Merged into main at `eb10d8eff93499a67e424bea5a60fd0245d46c4f` and applied to authorized shared TEST; SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`; 31 rows preserved; signature `3d9b730408336c82629c25342ddc7ea2` to `11043982605bef207d3b9a5626bd86d8`; zero event/session/probe rows persisted |
| `20260801170000_durable_session_runtime_events.sql` | Activates only durable-session issuance and current-session revocation event contracts; no table change or fixtures | Integrated in main at `3771b5e21f02dab1048e90e14131a00db90baf08` and applied to authorized shared TEST; immutable SHA-256 `fe4d8440ad683396b31da7ec8da0e335ceaa8936c1fb1c4d5f51a24058f57aeb`; signature `11043982605bef207d3b9a5626bd86d8` to `87c1377e1404933c69b1a90ac9962937`; zero session/device/event/user/business fixtures created |

No partial or out-of-order foundation capability was detected. The former three-trigger/RLS drift and additive `service_role` event-table ACL issue are corrected. Stop if a future inspection finds a named capability missing, an unexpected extra application table/column, a migration only partially represented, or a migration ledger that conflicts with observed capability.

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

| Domain | Purpose | Foundation owner/status | Must not contain |
| --- | --- | --- | --- |
| Security events | Authentication, verification, device/session, risk, account protection, security administration | `security_events` implemented in repository and present empty in shared TEST; ACL hardening is applied and runtime integration remains Planned | General product clicks, business state history, raw secrets |
| Business audit events | Committed domain changes and immutable business evidence | `business_audit_events` implemented in repository and present empty in shared TEST; caller transaction pairs future mutations/events without an outbox today | Failed attempts presented as successful history, chat bodies, arbitrary frontend events |
| General analytics | Consent-aware product usage, attribution, funnels, and aggregate behavior | `analytics_events` | Passwords/OTP/payment secrets, private content, exact background GPS |
| Operational monitoring | Reliability, performance, failures, dependency health, incidents, release monitoring | Operational telemetry and `operational_incidents` | Business payload bodies, auth headers, DB URLs, user-visible raw stack traces |

The logical object plan is:

`security_events`, `user_devices`, `user_sessions`, `otp_challenges`, `security_cases`, `security_case_events`, `security_alert_deliveries`, `admin_security_actions`, `business_audit_events`, `analytics_events`, `operational_incidents`, `event_outbox`, and `notification_deliveries`.

`security_events`, `business_audit_events`, and `user_sessions` are implemented in main and present in shared TEST. `user_sessions` contains zero rows and remains unused by runtime authentication. The other ten logical objects remain **Not implemented**. These names describe responsibilities, not a mandate to create thirteen tables.

## 6. Phase 1B-1 common event envelope foundation

The strict envelope is **Implemented in the repository** for the two canonical writers. Event emission from auth/business routes remains **Planned**:

| Field | Contract |
| --- | --- |
| Event ID | Server-assigned globally unique ID; supports idempotency. |
| Canonical event name | Allowlisted stable name following `<domain>.<aggregate>.<past-tense action>`; no arbitrary frontend names. |
| Event version | Positive schema version tied to contract tests. |
| Category | `security` or `business_audit` for current persistence; operations names are catalogued but non-writable until their separate store exists. |
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
| Consent category | Null for security/business evidence; future analytics consent remains a separate contract. |

Canonical names are stable, lowercase, and dot-separated. Multiword aggregates or actions use lowercase snake case inside their segment. Examples are `one_time.payment.released`, `wallet.withdrawal.approved`, and `security.login.succeeded`. A rename requires an explicit versioned transition; do not silently invent aliases. The exact locked compact families `matching.<compound-past-tense-action>` and `notification.<past-tense-action>` are the only catalog exceptions to the three-segment form. The required Deferred outcome `one_time.qr_payment.amount_mismatch` is the sole noun-outcome exception to the past-tense action segment. These explicit names remain stable contracts and must not acquire invented aliases; every new family must follow the three-segment rule.

One committed business action has exactly one canonical domain owner even when an admin, scheduler, or provider performs it. The actor/source fields record that a platform admin, job, or provider caused the action; wrapper events must not restate the same outcome under another namespace. A separate admin-security event is allowed only when no more specific security or business event owns the action.

Arbitrary frontend event names and arbitrary metadata are forbidden. The server derives identity, role, environment, session/device reference, and authoritative timestamps.

### 6.1 Implemented Phase 1B-1 objects and writers

- [`backend/events/catalog.py`](../backend/events/catalog.py) remains the only machine-readable catalog owner. Main and authorized shared TEST have 12 integrated Planned security definitions: the prior seven auth definitions, three trusted-device definitions, and `security.session.issued` plus `.revoked`. The other 150 Planned definitions remain unintegrated.
- [`backend/events/contract.py`](../backend/events/contract.py) owns the shared typed envelope. The maximum encoded envelope is 8,192 bytes; metadata is 2,048 bytes; each before/after object is 1,024 bytes; objects are flat, have at most 16 keys, use explicit type maps, and permit strings of at most 128 contract characters.
- [`backend/events/environment.py`](../backend/events/environment.py) derives only `local`, `test`, `staging`, or `production` from server configuration and fails closed when configuration is absent/unknown.
- [`backend/events/writer.py`](../backend/events/writer.py) exposes one security writer and one business-audit writer. Each accepts the caller's existing production `Db` transaction executor or native cursor, opens no connection, and never commits or rolls back. The database supplies `occurred_at`; catalog/context supply category/version/actor/retention/environment.
- `canonical_event_catalog_projection` is migration-owned enforcement metadata generated from the Python catalog, not a third event store or a second semantic owner. Main and authorized shared TEST contain exactly the seven integrated auth rows plus three integrated trusted-device rows. Deterministic bidirectional tests reject missing, extra, duplicate, or drifted definitions.
- Scoped `(idempotency_scope, idempotency_key)` uniqueness uses a SHA-256 envelope fingerprint. Same-key/same-fingerprint calls replay the existing row; same-key/different-fingerprint calls fail without aborting the transaction; concurrent duplicates create one row.
- `security_events` and `business_audit_events` each retain 43 columns, a UUID primary key, 16 named CHECK constraints, an UPDATE-blocking trigger, a catalog-contract INSERT trigger, and scoped idempotency uniqueness. Security has five explicit secondary/unique indexes plus its primary-key index; business audit has eleven plus its primary-key index. The database rejects unknown/non-writable names, table/category, version or retention drift, and user/admin actors missing either server-owned ID or role.
- All three Phase 1B tables have RLS. `anon`, `authenticated`, and `PUBLIC` have no event-table privileges or policies. The applied ACL correction leaves `service_role` exactly `DELETE`, `INSERT`, and `SELECT` on each event table and no projection access; UPDATE remains blocked by privilege and append-only trigger.
- Migration reapplication first computes one OID-independent semantic signature over exact columns/types/nullability/defaults, constraints, indexes, triggers, function definitions, RLS, policies, non-owner privileges, and all projection tuples. Only zero owned objects or the exact completed foundation may proceed; every partial or incompatible state aborts before migration DDL and preserves existing rows/objects.
- The migration creates zero event rows, performs no backfill, alters no legacy table, and creates no `analytics_events`, operations table, or `event_outbox`.

There is no current asynchronous consumer or delivery requirement, so an outbox would be unused speculative state. `event_outbox` is deferred until a proven consumer exists; any future outbox must share the authoritative mutation transaction and must not become a second audit owner.

### 6.2 Phase 1B-1 verification evidence

- Full sequence `20260731220000` then `20260731230000`, safe foundation reapplication, and fresh `schema.sql` convergence passed on disposable PostgreSQL. The forward ACL correction additionally proves convergence among old migration plus new migration, corrected fresh `schema.sql`, and an already-correct narrow database.
- Migration/fresh schema produces zero event rows. In main and authorized shared TEST, the integrated guard admits the 12 integrated definitions and rejects the remaining 144 writable-but-unintegrated Planned definitions.
- Fresh, partial and exact-reapply migration tests prove fail-closed preservation for wrong column names/types/nullability/defaults, weakened CHECKs, missing indexes/triggers/policies, wrong RLS/grants and drifted helper definitions. Phase 1B-2B pre-merge verification passed the complete PostgreSQL backend suite with 678 tests and zero failures/skips; its explicit no-DB run passed 302 while safely skipping 376 PostgreSQL-dependent tests.
- Phase 1B-1 remains **Implemented in the repository and shared TEST**: `20260731230000_canonical_event_foundation.sql` and `20260731240000_canonical_event_acl_hardening.sql` are both applied. Its foundation and ACL guarantees are unchanged.
- Phase 1B-2C0 verification passed 682 PostgreSQL tests with zero failures/skips, explicit no-DB mode passed 304 with only 378 expected PostgreSQL skips, and fresh/sequential/reapply/partial/corruption projection paths converged. The migration is merged into main and applied to authorized shared TEST; no runtime emitter was added.
- Phase 1B-2C1 feature verification passed 692 PostgreSQL tests with zero failures/skips and explicit no-DB mode passed 306 with only 386 expected PostgreSQL skips. Fresh schema, sequential migration, exact reapplication, relationship/state/privilege enforcement, and partial/corrupt-state rejection converge without changing the `3d9b730408336c82629c25342ddc7ea2` event signature or creating session/event rows.
- Phase 1B-2C2 verification passed 699 PostgreSQL tests with zero failures/skips; explicit no-DB mode passed 308 with 391 expected PostgreSQL skips. Migration `20260801160000_trusted_device_hardening.sql` has SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`; fresh/sequential/reapplication/corrupt-state, ACL, auth rollback, MPIN fail-closed, and prior-domain suites passed. The migration was then applied to authorized shared TEST, where reconciliation preserved every unrelated count/fingerprint and rollback-only token/event/role probes left zero persisted rows.

### 6.3 Phase 1B-2A/2B bounded auth integration

Phase 1B-2A and Phase 1B-2B are implemented in main and authorized shared TEST. Exactly `security.login.started`, `security.login.failed`, `security.login.succeeded`, `security.logout.completed`, `security.signup.started`, `security.signup.failed`, and `security.signup.completed` are integrated there. The Phase 1B-2B migration is applied through `20260801130000_security_signup_event_integration.sql` (SHA-256 `915c7937fd36e8dae19ab0f45b4a1cd10fade3a52c9bca959ffd49ca59f909e5`), changing the signature from `993b1de965a1791a2a84ccff5fcfbdf9` to `371c7010a0553c7953708dea164ed0bc`. The other 143 Planned definitions and all 8 Deferred QR definitions remain unintegrated.

- One server-generated request ID owns each request. Login-start and terminal events use separate scopes; exact replay is idempotent and conflicting terminal reuse fails closed. Client identity, correlation/request IDs, time, environment, session/device references, and event names cannot replace server-owned values.
- Valid password login commits `started` in its own short route-owned transaction before credential verification; failure to persist it prevents the provider call. Terminal `login_activity`, `last_login_at` on genuine success, trusted-device persistence, and the terminal canonical event share a separate route-owned PostgreSQL transaction. Terminal failure leaves exactly the durable `started` evidence, rolls back every terminal mutation, and prevents Flask session issuance.
- Phase 1B-2B uses the same caller-owned writer discipline: a server request ID commits anonymous signup-start before external Auth creation; public user/profile, success activity, trusted device, and completed evidence share one public transaction. On public failure, only an Auth identity proved by the server request metadata can be compensated. Proven cleanup records `persistence_failed`; an unproven or failed cleanup records `reconciliation_required`; neither path issues a session, CSRF state, or device cookie.
- The password provider adapter classifies only the installed Auth client's exact structured `invalid_credentials` code as an ordinary rejection. It does not match exception messages. Transport, timeout, malformed-response, retryable, other API, and provider-unavailability failures become one sanitized `provider_unavailable` result. Blocked, unknown, and wrong-password outcomes have the same public status, field, shape, and message; the known blocked case remains internally `account_unavailable`.
- Failed events remain anonymous and contain only `validation_failed`, `invalid_credentials`, `account_unavailable`, or `provider_unavailable` in allowlisted metadata. They contain no login identifier, email, CNIC, phone, IP, GPS, User-Agent, password, token, raw provider exception, request body, session or device reference.
- Authenticated CSRF-valid logout derives the server actor before clearing and emits `security.logout.completed`. Anonymous and invalid-CSRF calls emit none. Audit failure is sanitized in server logs and cannot prevent local session clearing.
- [`20260801100000_security_login_event_integration.sql`](../supabase/migrations/20260801100000_security_login_event_integration.sql) requires the exact prior signature `772212260b85fd6b5cd4aa35ca9ffdfb`, empty event tables on first activation, and either zero or the complete four-row activation state. It relaxes only the integrated constraint, changes only the four integrated flags, rejects partial state, is idempotent, and converges on `f5168975e0605fe0f7b84c1276a0082a` with fresh `schema.sql`. The applied [`20260801110000_canonical_event_integrated_guard.sql`](../supabase/migrations/20260801110000_canonical_event_integrated_guard.sql) requires that exact activation state and hardens the existing guard to require `writable`, `integrated`, and Planned lifecycle before insert, producing `7b8157021244549cfed79416b40ab662`.
- Focused Phase 1B-2B post-merge validation passed 100 signup/auth/canonical tests; the complete pre-merge backend PostgreSQL suite passed 678 with zero failures/skips. The explicit no-DB run passed 302 and skipped 376 database-dependent tests. The production build passes; this frontend package has no test script and no frontend file changed, so changed-file ESLint is not applicable.
- Signup runtime integration is implemented in main and shared TEST: start commits before external provider creation; public user, correct role profile, success activity, trusted-device mutation/event, durable session, completed evidence, and `security.session.issued` share the terminal public-database transaction; session/device cookies and CSRF state issue only after commit. Failure uses one anonymous `security.signup.failed` event with an approved coarse result code and rolls back terminal success evidence. Cleanup deletes only an Auth identity provably created by that request; ambiguous or failed cleanup records `reconciliation_required`. Canonical metadata never includes password, token, digest, cookie, CSRF, OTP, CNIC, email, provider error text, or another sensitive value. MPIN, password/reset mass revocation, OTP, GPS, risk, session refresh/inactivity/access-lock, business, analytics, and Operations integrations remain Planned.

## 7. Security and login locked contract

Everything in this section is **Planned** unless explicitly cross-referenced as current.

Phase 1B-2A is that explicit cross-reference for `security.login.started`, `security.login.failed`, `security.login.succeeded`, and `security.logout.completed`: their lifecycle classification remains Planned in the branch-local 150 count, while their repository `integrated` flag is true. All other names below remain unintegrated.

### 7.1 Authentication event catalog

| Planned canonical event |
| --- |
| `security.signup.started` |
| `security.signup.failed` |
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

Phase 1A contains `ActivityTracker` to the temporary authenticated page-visit contract; it is not the planned consent-aware analytics system and must not simply be redirected to `analytics_events`. Phase 4 must replace it with the full allowlisted, consent-aware, idempotent analytics design.

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
| Auth event evidence | Password-login/logout and signup routes plus transitional helper | Shared TEST: `login_activity` and empty `security_events`; activation, guard, signup, and trusted-device integration applied | Phase 1B-2A/2B integrate exactly seven canonical auth events and Phase 1B-2C2 integrates exactly three trusted-device events; only integrated+writable names are insertable | Login and signup starts commit before external provider operations; terminal public evidence owns activity, trusted device where applicable, and terminal event; canonical payload excludes legacy identifier/IP/device-credential fields | Any additional event, raw failure/identity field, duplicate start, or split terminal commit |
| Device registry | Canonical [`auth/trusted_device_service.py`](../backend/auth/trusted_device_service.py) | Hardened `trusted_devices` in main/shared TEST | Exact 32-byte current digest only; raw-token column removed; stable IDs/owners, 30-day maximum expiry, revocation, and locked rotation enforced | Canonical service reusable; trusted-device evidence still does not authenticate a Flask/server session | Preserve current-digest-only resolution; add management/revocation integrations in separately reviewed phases | Any previous digest authenticates, raw credential persists, or revoked/expired row resolves/reactivates |
| Sessions | Flask cookie; canonical [`auth/session_service.py`](../backend/auth/session_service.py) is implemented but unused | Main/shared TEST `user_sessions`; zero rows | Runtime still uses only the Flask signed cookie; the implemented foundation stores only a 32-byte SHA-256 token digest and enforces exact user/optional same-user trusted-device binding, genuine-activity/expiry boundaries, access lock, rotation, and bounded revocation state | Canonical foundation reusable; no route currently calls it | Integrate only in a separately reviewed phase while preserving login/signup/logout transactions and distinguishing polling from genuine activity | Any raw token persistence, browser grant, duplicate session owner, or unreviewed runtime activation |
| OTP | Auth/profile helpers | `password_reset_otps` | Has hashed OTP, attempts, purpose | Partial reuse; 10-minute expiry/text timestamps/no device binding/HMAC | New challenge contract; preserve reset flow until cutover | Provider/domain controls or replay/resend controls absent |
| Risk/security cases | None | None | Absent | Missing | Disabled → shadow foundation first | Any enforcement before shadow validation |
| Generic tracking | Contained ActivityTracker/API | `user_action_logs` | Historical arbitrary JSON retained; new writes restricted to one safe page-visit shape | Phase 1A containment implemented; table remains incompatible for the four canonical domains | Keep endpoint-local sanitizer; future consent-aware analytics replacement; retain/administer legacy data | Sensitive-field inventory or retention unknown |
| Shipment status history | DB trigger | `shipment_status_history` | Present and consistent | Reuse as status evidence; not full audit | Reference from business events; avoid duplicate generic events | Trigger semantics drift or missing actor context not addressed |
| Shipment/trip direct-client RLS | PostgreSQL policies | `shipments`, `shipment_trips` | Shared TEST has all three profile triggers and the corrected non-recursive helper/policy; role probes have no `42P17` | Former trigger/policy drift is resolved | Preserve the helper contract and role matrix | Any additional drift, helper privilege broadening, recursive dependency, or role-visibility regression |
| Canonical event foundation | `backend/events` catalog/contract/writers | Shared TEST `security_events`, `business_audit_events`, and `canonical_event_catalog_projection` | Shared TEST is at the applied empty-table, 170-definition, ten-integration state with narrow ACL | Foundation plus seven integrated auth and three integrated trusted-device definitions; fourteen Phase 1B-2C0 session/MPIN contracts remain unintegrated | Continue only through separately reviewed domain-owner changes using the existing writer/caller transaction | Any direct route table write, client identity/time, second catalog, partial activation, or guard regression |
| Business event transactionality | Domain services plus Phase 1B-1 writer | Domain tables; shared TEST event tables are present and empty | Strong transaction boundaries in key flows; writer atomic rollback proven | Writer is ready but intentionally unattached; no outbox consumer exists | Add inside existing transactions after each writer/lock owner is revalidated | Any mutation has multiple uncoordinated writers |
| Checkout/payment | `shared/payments.py` | Payment/wallet/trip tables | Constraints and anomalies clean | High-value reuse | Emit from canonical service only | Dummy/real provider ambiguity or provider crash reconciliation unresolved |
| Wallet | Shared helper plus route/admin/agreement writers | Wallet tables | Present, integrity indexes present | Writer overlap | Establish allowed-writer contract before events | Unmapped direct SQL writer |
| Delivery/dispute/review | `orders/lifecycle.py`, `orders/reviews.py` | Lifecycle tables | Strong exact FKs/unique constraints | High-value reuse | Same-transaction events, canonical lock order | Any route bypasses lifecycle service |
| Matching | `orders/helpers.py` and order routes | Shipment/bid/vehicle state | Current decisions consistent; no anomaly | Helper reusable; no policy version/evidence snapshot | Version rule set and snapshot decisive evidence only | Code and SQL policy disagree |
| Notifications | Shared helper | `shipment_notifications` | In-app idempotency for trip events | Reuse in-app intent; no delivery ledger | Separate notification intent from provider deliveries | Multiple provider sends without idempotency |
| Email | Direct SMTP helper | None | No delivery state | Incompatible for security OTP reliability | Provider abstraction plus delivery ledger before Email OTP | SPF/DKIM/DMARC/mailbox/provider not complete |
| Admin audit | Admin routes | `user_action_logs` plus domain state | One commission audit writer only; unchanged by Phase 1A | Mixed owner and incomplete coverage; deliberately bypasses the analytics sanitizer | Domain business events + separate admin security actions in a later authorized phase | Admin mutation lacks re-auth/reason |
| Commission/Terms | Shared commission service | Versioned tables | Immutable and capability-complete | Reuse | Add content hash/role acknowledgment contract forward-only | Existing snapshots could be rewritten |
| Saved methods/preferences | Payment service/routes | Tokenized tables/safe view | Present; cross-user anomaly zero | Reuse; re-auth/events missing | Add sensitive-action re-auth and events | Effective RLS/grants not proven under client roles |
| Operational monitoring | Basic scheduler logging | None | No incident/telemetry objects | Missing | Structured redacted telemetry and health contracts | Body/header/secret collection cannot be excluded |
| Analytics | Contained ActivityTracker | `user_action_logs` | One authenticated safe page-visit write shape; broad historical rows retained | Existing data may support limited historical aggregates only | New consent-aware allowlisted pipeline | Attempt to migrate arbitrary payloads without classification |
| Agreemental tracking | Agreement routes/helpers/scheduler | Agreement tables | Workflow exists; tables empty in TEST | Future extension | Reuse shared infrastructure, separate Agreemental event rules | Any change alters One-Time contract |

### 13.1 Current writer and transaction registry

| Mutation family | Canonical runtime owner / compatibility aliases | Current direct persistence writers | Transaction, commit and lock owner | Future canonical event owner | Same-transaction attachment status |
| --- | --- | --- | --- | --- | --- |
| Password login/logout | Auth route plus canonical session/trusted-device services; no event aliases | Supabase Auth verification plus `users.last_login_at`, `login_activity`, `security_events`, hardened `trusted_devices`, `user_sessions`, and non-authoritative Flask state | Login-start commits before provider verification. Terminal activity/events, applicable login timestamp, trusted-device mutation, and durable-session issuance use one caller-owned DB transaction; cookies/CSRF follow commit. Logout validates CSRF, locks and revokes only the current session, and records session-revoked/logout-completed atomically; local clearing is fail-safe. | Phase 1B-2A login/logout events plus Phase 1B-2C3A `security.session.issued`/`.revoked` | **Main-integrated and TEST-guarded**; no cross-system atomicity is claimed for Supabase Auth verification |
| Signup | Auth route plus canonical session/trusted-device services in main | Supabase Auth plus `users`, one role profile, `login_activity`, hardened `trusted_devices`, `user_sessions`, and `security_events` | Start commits before external Auth. Public user/profile, activity, trusted-device mutation/event, durable session, completed event, and session-issued event share one public transaction; cookies/CSRF follow commit. Proven Auth compensation is bounded to the request-owned identity. | `security.signup.started`, `.failed`, `.completed`, trusted-device event, and `security.session.issued` | **Main-integrated and TEST-guarded** |
| MPIN/password/reset/device | Auth/profile routes plus canonical trusted-device service | Supabase Auth plus OTP/reset and hardened `trusted_devices` | Raw-token MPIN authentication bypass is disabled fail-closed; existing MPIN data is retained | Trusted-device added/removed/rotated are integrated in main and authorized shared TEST | MPIN enrollment/unlock/attempt limits/lockout/reset/step-up remain Planned for 2C3; password/reset/block and logout-all revocation remain Planned for 2C4 |
| Legacy page tracking | `tracking/routes.py`; browser contract fixed to page visits | `/api/track` inserts `user_action_logs` and owns its commit | Route owns validation/insert/commit; no domain lock | Future General Analytics, not either canonical table | **Do not attach/redirect**; legacy containment remains separate |
| Orders and bids | `orders/routes.py`; legacy accept/process-payment endpoints refuse old flow | Direct `shipments` and `shipment_bids` writes | Route owns commit; validation reads truck/order state, with checkout revalidation later | `one_time.order.*`, `one_time.bid.*`, `matching.*` | Technically caller-transaction compatible, but integration remains Planned |
| Checkout/payment hold | `shared/payments.perform_checkout`; routes are commit owners | Shipment, bid, vehicle, wallet, wallet-transaction, payment, trip, tracking and chat writes | Existing cursor transaction; locks order, then bid, vehicle and wallet before state transitions; helper does not commit | One-Time checkout/payment plus wallet funding owners | Compatible with caller-owned writer after a dedicated integration review |
| Release/refund | `shared/payments.release_one_time_payment` / `refund_one_time_payment` | Payment, wallet and wallet-transaction writes | Caller owns commit; payment then relevant wallet rows are locked | `one_time.payment.released/refunded`, canonical wallet credit | Compatible, not connected |
| Delivery/dispute/review | `orders/lifecycle.py` and `orders/reviews.py`; completion/confirmation route aliases converge on these services | Shipment, trip, dispute, payment, wallet, review, notification and chat writes | Caller owns commit; canonical lock order is shipment → trip → dispute → payment → wallet | Specific One-Time trip/delivery/dispute/review events | Compatible, not connected; no generic duplicate status wrapper allowed |
| Wallet/withdrawal | `wallet/helpers.py`, wallet routes, payments, agreements and admin routes | Wallet, wallet-transaction and withdrawal tables | Multiple current commit owners; row locks exist in payment paths but ownership remains distributed | `wallet.*` | **Stop before integration** until each direct writer is assigned and replay/lock behavior is unified |
| Fleet/profile/documents | Profile/truck routes and shared Storage helper | Users/profile/vehicle/document tables plus Storage | Route commits DB work; Storage is external and not one DB transaction | `transporter.*`, `business.profile.*` | DB-only transitions may attach later; upload evidence needs explicit external-failure semantics |
| Commission/Terms/admin decisions | Shared commission helpers and admin routes; actor envelope replaces wrapper aliases | Version tables/domain state; commission publication also writes legacy `user_action_logs` | Admin route owns DB transaction/commit; immutable version triggers protect published rows | `commission.*`, `terms.*`, specific business owner; `admin.security_action.performed` only as fallback | Compatible for domain rows after removing mixed legacy audit ownership in a separately authorized phase |
| Notifications and scheduled transitions | `shared/notifications.py`, lifecycle services, scheduler/manual admin trigger | Idempotent `shipment_notifications` plus business transitions | Notification helper never commits; lifecycle/admin/scheduler caller owns transaction and locks | Business transition event plus separate `notification.*`; future `system.job.*` remains non-writable until operations persistence | Business notifications are attachable later; scheduler run evidence needs its separate operations phase |

Phase 1B-1 does not change a domain owner. Phase 1B-2A attaches the existing cursor-level security writer to four password-login/logout outcomes. Phase 1B-2B attaches three signup outcomes in main and shared TEST. Phase 1B-2C2 attaches the three trusted-device outcomes in main and authorized shared TEST. Phase 1B-2C3A attaches issued/revoked session outcomes in main and authorized shared TEST; GPS, OTP, and MPIN runtime remain future bounded changes.

## 14. Architecture and rollout

0. **Inventory and registry** — this file only.
1. **Phase 1A — Legacy tracking containment (Implemented)** — completed as the first runtime phase, before broader event-foundation work:
   - stop logging request and response bodies;
   - stop generic form-field capture;
   - stop placing CSRF/token-shaped values in analytics payloads;
   - stop trusting frontend-supplied user identity;
   - restrict event names and metadata;
   - add size and redaction guards;
   - preserve existing `user_action_logs` rows until a separately authorized classification/retention decision;
   - do not silently redirect current arbitrary payloads into a new analytics table;
   - prove no current business route depends on unsafe tracker behavior.
2. **Schema-trigger/RLS baseline correction (Implemented in repository and shared TEST)** — forward-only convergence for three profile timestamp triggers and non-recursive shipment/trip role visibility.
3. **Phase 1B-1 — Canonical event foundation and ACL hardening (Implemented in repository and shared TEST)** — both Phase 1B-1 migrations are applied; the two event tables are present and empty, the 158-definition catalog projection is present, and the narrow ACL/signature is verified.
4. **Phase 1B-2A — Password login/logout security events (Implemented in main and authorized shared TEST; not deployed)** — exactly four definitions are integrated with caller-owned terminal transactions; the activation and integrated-state guard migrations are applied, and only integrated+writable names are insertable.
5. **Phase 1B-2B — bounded signup events (Implemented in main and authorized shared TEST; not deployed)** — exactly three signup definitions are integrated through `20260801130000_security_signup_event_integration.sql` and a compensation-aware external-Auth saga; GPS and Email/SMS OTP remain Planned and unintegrated.
6. **Phase 1B-2C0 — device/session/MPIN event contracts (Implemented in main and authorized shared TEST; not deployed)** — migration `20260801140000_device_session_mpin_event_contracts.sql` added twelve contracts and formalized five existing contracts. At Phase 1B-2C0 completion all seventeen were unintegrated; Phase 1B-2C2 later integrated the three trusted-device definitions and Phase 1B-2C3A later integrated session issued/revoked. Software MPIN unlock, high-risk payment/action MPIN step-up, seven-day genuine-inactivity enforcement, GPS, Email OTP, and SMS OTP remain Planned, and no payment or wallet behavior changed.
7. **Phase 1B-2C1 — durable server-session foundation (Implemented in main and authorized shared TEST; not deployed)** — one zero-row `user_sessions` table and the canonical session service established the digest-only token model, genuine activity, lock, expiry, rotation, and revocation state. At 2C1 completion the service was intentionally unused; Phase 1B-2C3A now makes it the sole runtime authentication authority. The foundation added one table, four indexes, nine table constraints, and one service-role policy; its RLS and narrow service privileges remain unchanged. MPIN enrollment/unlock/lockout/reset/step-up, logout-all/remote and password/account-block mass revocation, seven-day genuine-inactivity enforcement, automatic access locking, management APIs/dashboard, GPS, and Email/SMS OTP remain Planned.
8. **Phase 1B-2C2 — trusted-device hardening (Implemented in main and authorized shared TEST; not deployed)** — integration commit `eb10d8eff93499a67e424bea5a60fd0245d46c4f` and migration `20260801160000_trusted_device_hardening.sql` (SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`) migrated 31 eligible rows in place to exact 32-byte SHA-256 digests while preserving stable IDs, user ownership, and same-user session binding. It removed raw-token storage, added 30-day maximum absolute expiry plus revocation/locked-rotation state, centralized runtime ownership, integrated exactly the three trusted-device events, and disabled the legacy MPIN authentication bypass while retaining MPIN data. Phase 1B-2C3A later activated durable-session issuance/enforcement and removed Flask signed-cookie authentication authority. Secure MPIN enrollment/unlock/attempt limits/lockout/reset/step-up and action/resource-bound grants remain Planned for 2C3B; logout-all/remote management and password/reset/block mass revocation for 2C4; seven-day genuine inactivity for 2C5; the security dashboard for 2C6; GPS and Email/SMS OTP remain Planned.
9. **Phase 1B-2C3A — durable server-session runtime authority (Implemented in main and authorized shared TEST; not deployed)** — integration commit `3771b5e21f02dab1048e90e14131a00db90baf08` makes `public.user_sessions` the sole runtime authentication authority through the canonical session service. Password signup/login issue one digest-only session bound to the exact active same-user trusted device in the terminal caller-owned transaction; all protected routes resolve current identity/role/profile relationships from the durable row and current database state. Flask signed state is bounded CSRF/presentation-only. Current logout revokes exactly its locked session and leaves all other sessions untouched. Migration `20260801170000_durable_session_runtime_events.sql` (SHA-256 `fe4d8440ad683396b31da7ec8da0e335ceaa8936c1fb1c4d5f51a24058f57aeb`) integrates exactly `security.session.issued` and `.revoked`, advancing main/shared TEST to 12 integrations and signature `87c1377e1404933c69b1a90ac9962937`. MPIN 2C3B, logout-all/revocation triggers 2C4, inactivity processing 2C5, dashboard 2C6, GPS, and OTP remain Planned.
8. **Phase 1B-2 remaining runtime event integration (Planned)** — attach canonical writers only through separately reviewed domain-owner changes.
9. **Security** — observation first; risk shadow mode and alerts/cases; later Email OTP after provider/domain readiness. Durable current-session runtime is implemented; secure MPIN runtime, logout-all/security-triggered mass revocation, inactivity processing, and device/session management remain later dedicated security workstreams.
10. **One-Time Business Audit** — attach same-transaction events to canonical One-Time services and prove idempotency/lock behavior.
11. **General Analytics** — replace broad tracker with consent-aware, allowlisted, idempotent analytics.
12. **Operational Monitoring** — structured errors/latency/health/provider/scheduler/release telemetry and incident lifecycle.
13. **Dashboards and retention** — user/admin security surfaces, KPI/funnel views, deletion/aggregation jobs, access audits.
14. **Final audit and freeze** — drift, privilege, retention, volume, performance, privacy, and integrity review.
15. **GPS tracking architecture afterward** — separate bounded architecture after the event foundations are stable.

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

Historical `ActivityTracker` rows may reflect broad bodies/responses and a CSRF token-shaped `session_id`. Phase 1A removes those capture paths from current runtime behavior, preserves existing rows, and keeps the legacy system explicitly separate from the future approved analytics precedent.

## 17. Post-foundation integration blockers and mandatory stop conditions

Stop any runtime event integration if any of the following is unresolved:

1. A mutation's current writer/commit/lock owner differs from the registry, or distributed wallet/admin writers have not been reconciled for that event.
2. Effective `anon`/`authenticated` privileges and RLS behavior are not proven in disposable PostgreSQL/Supabase-compatible tests.
3. Any migration, reuse, or retention change for existing `user_action_logs` lacks an approved sensitive-field classification and access plan.
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

- 36 planned Security authentication/session/device/account events in main and shared TEST;
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
- 13 logical data objects: 2 event tables plus zero-row `user_sessions` implemented in main and present in shared TEST; 10 still Not implemented.

The catalog contains 162 Planned-lifecycle events plus 8 Deferred QR-payment events (170 combined), of which 156 are writable. Main and authorized shared TEST have exactly 12 integrated Planned security definitions: the prior seven auth names, the three trusted-device names, and `security.session.issued` plus `security.session.revoked`. The other 150 Planned definitions remain unintegrated; 144 of those are writable. The six Operations definitions remain non-writable and unintegrated. The final semantic signature is `87c1377e1404933c69b1a90ac9962937`, advanced from `11043982605bef207d3b9a5626bd86d8` only by the two durable-session integrations.
