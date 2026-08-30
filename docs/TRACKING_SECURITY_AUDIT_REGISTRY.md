# Digi_TransX Tracking, Security, Audit, Analytics, and Operations Registry

## 1. Purpose and authority

This registry is the human-readable source for the current architecture, verified implementation status, ownership boundaries, compatibility findings, and future contracts for Digi_TransX tracking, security, business audit, general analytics, and operational monitoring.

| Field | Verified value |
| --- | --- |
| Inventory base SHA | `0d1b5b2de4b92ec642f39cfec26b09b3aefce571` |
| Verification date | 2026-07-31 |
| Latest capability-status reconciliation | 2026-08-30; Phase 1B-2C4 user-initiated logout-all is implemented on `main` and verified on authorized shared TEST. The bounded probe reconciled every fixture and fingerprint without reapplying migration `220000`; production remains undeployed. |
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
| Phase 1B-2C3B1 feature branch | `feature/phase-1b2c3b1-secure-mpin-backend` |
| Phase 1B-2C3B2 frontend feature branch | `feature/phase-1b2c3b2-mpin-frontend` |
| Phase 1B-2C3B2 responsive correction branch | `fix/phase-1b2c3b2-mobile-responsive-interface` |
| Phase 1B-2C3B2 completion reconciliation branch | `docs/phase-1b2c3b2-completion-status` |
| Phase 1B-2C3C1 feature branch | `feature/phase-1b2c3c1-mpin-step-up-foundation` |
| Environment inspected | Authorized Supabase TEST project `fysu…goev` |
| Database rollout/inspection mode | Immutable migrations through `210000` are applied; Phase 1B-2C3C1 used the exact committed migration blob in its own atomic transaction, pre/post reconciliation used explicit read-only transactions, and verification fixtures ended with `ROLLBACK` |
| Scheduler state during inspection | Disabled with `DIGITRANSX_ENABLE_SCHEDULER=0`; no scheduler process active |
| Phase | Phase 0 registry; Phase 1A through Phase 1B-2C3C2 implemented in main/shared TEST; Phase 1B-2C4 implemented in main and verified on authorized shared TEST; production remains undeployed |

> **Planning/documentation only.** This file creates no routes, tables, views, functions, triggers, policies, jobs, dashboards, providers, or runtime behavior. Any object or event marked Planned or Deferred does not exist merely because it appears here.

The Inventory base SHA identifies the code/database state inspected during Phase 0. It is not the SHA of the documentation commit that introduced or later corrected this registry.

Runtime implementation remains authoritative when this registry and code disagree. A disagreement is a defect: every future tracking-related change must update this file in the same commit. Phase 1B-1 adds foundation contract tests; Phase 1B-2A adds PostgreSQL route, transaction, privacy, failure, activation, and convergence proofs for exactly four auth events. Phase 1B-2C0 adds catalog/projection contracts only. Phase 1B-2C1 added the canonical `user_sessions` database/service foundation without runtime wiring; Phase 1B-2C3A now uses that foundation as the sole runtime authentication authority. Phase 1B-2C3B2 adds only the bounded frontend access-lock, signup-sensitive-state, MPIN-management, and responsive/navigation owners described below. Phase 1B-2C3C1 adds the backend step-up issuance/ledger foundation and two integrated issuance events without connecting a Category A mutation or frontend step-up owner.

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

The TEST database has 48 public tables and two public views. It contains the capabilities through the Phase 1B-2C3B1 secure-MPIN, reset-authorization-claim, and genuine-session-activity migrations, assessed by objects and constraints rather than by an application-owned migration-history table:

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
19. durable server-session runtime authority and two-event session integration;
20. secure MPIN credentials, software access lock, and eight-event integration;
21. one-shot OTP/reset-authorization claim hardening;
22. trusted genuine-session activity and `security.session.refreshed` integration.

The Phase 1B-1 foundation migration `20260731230000_canonical_event_foundation.sql` and forward ACL correction `20260731240000_canonical_event_acl_hardening.sql` are both applied to shared TEST. The initial foundation application exposed additive Supabase `service_role` default privileges; the applied correction validated the exact foundation, revoked the broad direct event-table grants, and restored only `DELETE`, `INSERT`, and `SELECT`. Final verification found signature `772212260b85fd6b5cd4aa35ca9ffdfb`, zero `service_role` projection access, zero `anon`/`authenticated`/`PUBLIC` event or projection access, and zero rows in both event tables. This capability assessment does not claim that an application-owned migration ledger exists.

The database also has the expected Auth-to-profile trigger on `auth.users`. Supabase-owned migration records exist in service schemas, but there is no application-owned public migration ledger; capability inspection is therefore mandatory.

### Known limitations and deferred features

- Full signup/login GPS, mandatory full-login Email OTP, risk scoring, security cases, and admin security dashboards are **not implemented**. Owner-scoped active session/trusted-device management is implemented in the 2C6 feature branch and is not deployed.
- Flask signed state is non-authoritative and retains only bounded CSRF/presentation state; durable `user_sessions` plus the exact active same-user trusted device are the runtime authentication authority.
- Phase 1B-2C2 is implemented in main and authorized shared TEST: it stores only exact 32-byte SHA-256 token digests, preserves stable device/user ownership, enforces absolute expiry and explicit revocation, and rotates credentials under a row lock. A trusted device remains recognition evidence only, never an authenticated session.
- Historical `ActivityTracker` behavior captured broad request/response and form data and trusted frontend identity/event fields. Phase 1A contains the current client to one authenticated safe page-visit contract, but historical rows remain unclassified and the legacy table is still not the planned analytics foundation.
- Email is direct SMTP with no delivery ledger or provider abstraction. SMS is not a supported or planned communication channel.
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
| Signup | Phase 1B-2C3B1 durable issuance implemented in main/shared TEST; Phase 1B-2C3B2 frontend sensitive-state lifecycle implemented in repository main | [`signup()`](../backend/auth/routes.py) commits anonymous `security.signup.started` before external Auth creation. Its terminal caller-owned transaction atomically persists the public user/profile, successful `login_activity`, trusted-device mutation and event, durable session, `security.signup.completed`, and `security.session.issued`; session/device/access-proof cookies and CSRF state issue only after commit. Mandatory failure rolls back terminal success evidence and uses bounded Auth compensation/reconciliation. The frontend has one route-scoped signup-wizard password owner: failure, cancellation, route departure, logout, completion, and provider teardown clear sensitive state, while stale or abandoned operations cannot affect a newer wizard generation. No production module-global password singleton or browser-persistent password owner remains. | Main and shared TEST backend state: `security_events`, `auth.users`, `users`, one role-profile table, `login_activity`, hardened `trusted_devices`, `user_sessions`; shared TEST has 23 integrated definitions and empty event tables after rolled-back verification. Frontend password state remains process-memory-only and route-scoped. | GPS and verified Email OTP security flows remain Planned and unintegrated; provider messages, identity fields, credentials, and form values are excluded from canonical evidence. |
| Password login | Phase 1B-2C3B1 durable runtime and transaction correction implemented in main and shared TEST | [`login()`](../backend/auth/routes.py) independently commits `security.login.started`, performs remote password verification with no PostgreSQL transaction or pooled connection held, then locks and revalidates the current user before atomically persisting successful activity, applicable `last_login_at`, trusted-device mutation and event, one durable session, terminal login evidence, and `security.session.issued`. The committed transaction-owned user snapshot builds the response without a mandatory post-commit read; cookies and CSRF state issue only after commit. | Main and shared TEST: `security_events`, `login_activity`, `users`, hardened `trusted_devices`, `user_sessions`; shared TEST has 23 integrations | Provider failures are sanitized. GPS, mandatory Email OTP, risk engine, session limits, and high-risk restrictions remain Planned. |
| Logout | Phase 1B-2C3A current-session revocation and Phase 1B-2C4 logout-all are implemented in main and verified on authorized shared TEST; not deployed | [`logout()`](../backend/auth/routes.py) retains current-session behavior. [`logout_all()`](../backend/auth/routes.py) delegates to the sole [`logout_all_service.py`](../backend/auth/logout_all_service.py) owner: it requires CSRF plus active action-bound MPIN proof, or current-password provider verification for no/locked/ineligible MPIN; provider I/O holds no PostgreSQL connection. The final transaction revalidates the exact session/user/device/access proof/account/confirmation generation, locks the active same-user populations deterministically, revokes all active sessions and trusted devices, and writes one exact per-row event plus the existing logout completion contract. | `user_sessions`, `trusted_devices`, `mpin_credentials`, `mpin_step_up_authorizations`, `security_events`, canonical auth/device/proof/Flask cookies | Current access is included and all browser authentication/presentation state is cleared on success. Expired/already-revoked and cross-user rows remain unchanged. No list/revoke-one API, schema migration, catalog change, shared-TEST SQL application, production access, or deployment is part of 2C4. |
| Password reset | Partially implemented; one-shot replay/claim correction implemented in main and shared TEST | Forgot-password sends a six-digit Email OTP and stores only its password hash. The latest challenge is consumed once under a row lock, exactly one signed high-entropy reset authorization is created in the same transaction, only its SHA-256 digest is stored, and one atomic claim wins before provider I/O. Provider failure/finalization ambiguity leaves a non-replayable explicit `reconciliation_required` state. | `password_reset_otps`, hardened `reset_tokens` claim lifecycle | OTP expiry remains 10 minutes, not the locked five; no 60-second resend control or HMAC/device-bound challenge; reset does not revoke sessions/devices. Raw OTP/reset/provider details are excluded from canonical metadata and sanitized from responses/logs. Broader OTP delivery/revocation requirements remain Planned. |
| Password change | Partially implemented; one-shot correction implemented in main | [`request_password_change_otp()`](../backend/profile/routes.py#L59) and [`change_password()`](../backend/profile/routes.py#L95) reuse the row-locked one-shot OTP consumer; wrong or replayed values cannot invoke the Auth provider again. | `password_reset_otps` | No session revocation or security-event contract; delivery infrastructure and the future device-bound OTP contract remain Planned. |
| Login activity | Verified existing but unstandardized; transaction ownership narrowed in Phase 1B-2A | [`record_login_activity()`](../backend/auth/helpers.py) still records identifier, method, status, failure reason, IP, and user agent. Password-login and signup terminal writes use their route-owned transactions. | `login_activity` | Transitional evidence is not weakened or repurposed; its raw identifier/IP fields remain outside canonical event payloads. |
| Trusted device / fast login | Phase 1B-2C3B1 implemented in main and authorized shared TEST; 2C6 management implemented on feature branch | [`trusted_device_service.py`](../backend/auth/trusted_device_service.py) remains the single transaction-participating owner for credential lifecycle; [`session_device_management.py`](../backend/auth/session_device_management.py) owns owner-scoped listing and one-target management revocation. | Hardened digest-only `trusted_devices`; invalidated legacy `users.mpin_hash`/`users.mpin_enabled`; stable `(trusted_device_id,user_id)` binding | Previous digests and legacy MPIN credentials do not authenticate; 2C6 changes are not deployed. |
| Secure MPIN / software access lock | Phase 1B-2C3B1 backend and Phase 1B-2C3C1 step-up foundation implemented in main/shared TEST; Phase 1B-2C3B2 access-lock UX in main; Phase 1B-2C3C2 six-operation integration implemented in main and authorized shared TEST; not deployed | [`mpin_service.py`](../backend/auth/mpin_service.py) owns exact MPIN validation, memory-hard verification, the shared atomic failure counter, and fifth-failure lockout. [`step_up_service.py`](../backend/auth/step_up_service.py) recognizes exactly six approved action descriptors and owns digest-only three-minute issuance plus verify/claim/consume/reconciliation primitives. The six reviewed routes rebuild authoritative descriptors, consume or claim the exact proof, and atomically couple local mutation with evidence. `/auth/me` exposes only opaque session/device/access-proof references so the frontend cancels pending step-up work when user, session, trusted device, or proof generation changes. | A generation-bearing `mpin_credentials` row, digest-only software proof in `user_sessions`, and the `mpin_step_up_authorizations` ledger. The separate step-up proof binds the exact user/session/device/generation/action/resource/request and is returned raw once with `no-store`; ambiguous payout finalization reconnects to classify committed `consumed` versus uncommitted `claimed` state without repeating provider or domain work. | Eligible roles remain exactly `logistics_provider`, `service_seeker`, and `everyday_user`. Exactly wallet-only checkout, withdrawal request, withdrawal-limit purchase, payout-destination replacement, agreement finalization, and client Yes delivery release are connected through the in-memory `StepUpProvider`. Shared TEST has been reconciled; production remains unchanged. |
| Genuine session inactivity | Implemented in main and authorized shared TEST; not deployed | [`GenuineActivity.jsx`](../frontend-react/src/components/GenuineActivity.jsx) accepts only visible, trusted pointer/touch/keyboard events and sends an empty same-origin CSRF-backed signal. [`record_genuine_activity()`](../backend/auth/session_service.py) revalidates and locks the exact session, user, and same-user device, requires the access proof, and advances only genuine activity/inactivity timestamps at most once per 12 hours; [`genuine_session_activity()`](../backend/auth/routes.py) writes `security.session.refreshed` in the same transaction. | Exact `user_sessions` row plus one digest-referenced canonical event per durable refresh | The deadline is database-now plus seven days, capped by immutable 30-day absolute expiry, and cannot shorten an already later valid deadline. Scroll, mousemove, focus/visibility, page views, `/auth/me`, polling, notifications, chat refresh, ActivityTracker, scheduler activity, background timers, failed requests, and synthetic events do not refresh. `security.session.expired_inactivity` remains Planned/unintegrated. |
| Flask session | Phase 1B-2C3B1 non-authoritative compatibility state implemented in main | [`build_auth_success_response()`](../backend/auth/helpers.py) retains only bounded CSRF and presentation activity state. [`login_required()`](../backend/auth/helpers.py) requires the durable-session and exact trusted-device cookies, then derives `request.current_user`, role, and profile relationships from PostgreSQL. | `user_sessions` is authoritative; Flask state contains no authoritative user ID, role, profile identity, authentication flag, or durable token | Forged signed identity cannot authenticate. Passive `/auth/me` and Flask presentation timestamps do not update durable genuine activity. |
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
- Flask signing configuration fails startup on a missing, short, or known-placeholder secret outside explicit `local`/`test` mode. Unidentified, staging, production, and unknown deployment modes force Secure Flask/authentication/trusted-device/access-proof cookies; explicit `local` additionally requires a loopback host. Deprecated `FLASK_ENV` cannot downgrade this boundary.
- The legacy MPIN authentication bypass remains disabled. Secure enrollment/unlock/password-unlock/change/disable/reset, software access lock, and the Phase 1B-2C3C1 action-bound issuance/ledger foundation are implemented in main/shared TEST. Phase 1B-2C3C2 connects exactly six Category A mutations and the frontend `StepUpProvider` in main/shared TEST, including opaque authority-context cancellation and non-replaying payout reconciliation. Phase 1B-2C4 user-initiated logout-all is implemented in main and verified on authorized shared TEST. Phase 1B-2C6 owner-scoped active session/trusted-device management is implemented only on its feature branch. `.expired_inactivity`, password/account/admin/incident mass revocation, admin security dashboards, GPS, and Email OTP remain Planned; production remains unchanged.

Phase 1B-2C3B1 bounded correction evidence:

- Password verification executes before the terminal database transaction. The terminal transaction re-reads and locks the current account before atomically mutating login activity, applicable login time, trusted-device state/evidence, durable session, access proof, and terminal canonical evidence; it returns the authoritative user snapshot, so no mandatory failure-prone post-commit user read precedes cookie issuance.
- Verified OTP consumption is row-locked and one-shot. Exactly one request can create a digest-only reset authorization, exactly one atomic claim can win, no PostgreSQL connection or lock spans provider I/O, and provider/finalization uncertainty becomes non-replayable `reconciliation_required` state. Raw OTP/reset/provider details are neither returned/logged nor admitted to canonical metadata.
- Private chat media requires the exact message/thread relationship plus participant or assigned group-admin access. Sensitive truck media requires the truck owner or platform admin; the authenticated inline catalog-image exception remains explicit and bounded. URL possession or a guessed path is insufficient.
- Upload object keys are opaque UUID-based names without original filenames. Local extension/10-MB validation alone raises `TruckUploadValidationError` and returns bounded 400; every Storage provider/SDK exception, including `ValueError`, returns stable sanitized 503, with raw provider text absent from responses and application logs. Ownership, validation rules, storage paths, and valid uploads are unchanged.
- Browser-cookie-authenticated agreement payment and penalty aliases enforce the same CSRF gate and delegate to the canonical domain helpers. Auth, SMTP, GPS, Storage, and scheduler failures use stable sanitized responses/logging without provider payload, URL, credentials, recipient, token, or stack text.

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
- Phase 1B-1 envelope schemas, canonical catalog/writers, explicit environment separation, RLS, idempotency, contract tests, and bounded `service_role` ACL hardening are **Implemented in main and shared TEST**. Later phases integrate seven signup/login/logout definitions, three trusted-device definitions, two durable-session definitions, access lock, seven non-step-up MPIN definitions, `security.session.refreshed`, and exactly the two step-up issuance outcomes: 23 total. The guard permits only integrated+writable definitions.

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
| Documents | Private download/upload correction implemented in main; broader evidence remains partial | Chat media requires an exact message-to-thread mapping plus participant or assigned group-admin authorization. Sensitive truck documents require the owning user or platform admin; deliberately inline vehicle images remain authenticated catalog media. New storage keys use opaque UUID-based names without original filenames, chat provider upload runs outside PostgreSQL before row-locked terminal revalidation, and provider errors are sanitized. `TruckUploadValidationError` alone represents bounded application validation and returns 400; every provider/SDK failure, including `ValueError`, returns a stable sanitized 503 without raw response/log text. | [`backend/shared/storage.py`](../backend/shared/storage.py), [`backend/trucks/helpers.py`](../backend/trucks/helpers.py), `chat_messages`, `chat_threads`, `documents`, `vehicles`, private `shipment-documents` bucket | Access evidence/events, private orphan reconciliation, and a broader document-classification lifecycle remain incomplete; URL possession alone is not authorization. Upload ownership, extension/size rules, opaque paths, and valid behavior are preserved. |
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
- Twenty-four forward migrations exist under [`supabase/migrations`](../supabase/migrations) in main and authorized shared TEST; the deterministic Phase 1B-2C3B1 tail is `20260801180000`, `20260801190000`, then `20260801200000`. `20260801150000_durable_server_session_foundation.sql` is merged through commit `682b2dcf53ef10b3f56b6ed6b2395955442a0904` and applied to authorized shared TEST with Git-blob SHA-256 `11b32c6d7cbd70dd16fb3f2854d3eb615d922fcd58049c0462917f635e9ada20`; `20260801160000_trusted_device_hardening.sql` is merged through `eb10d8eff93499a67e424bea5a60fd0245d46c4f` and applied with SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`.
- PostgreSQL integration mirrors in [`backend/tests/conftest.py`](../backend/tests/conftest.py) and `test_migration*.py` use isolated/disposable PostgreSQL databases or schemas and never fall back from `TEST_SUPABASE_DB_URL` to the shared application URL.
- Tests cover payment constraints, RLS, lifecycle integrity, coordinate integrity, everyday separation, dispatcher removal, review concurrency/integrity, schema-trigger convergence, effective shipment/trip role visibility, the 162 + 8 catalog projection, strict envelopes, migration convergence, caller-owned writers, idempotency/concurrency, append-only enforcement, and event-table privileges.

## 4. Actual TEST database capability inventory

### 4.1 Catalog summary

| Object kind | Count | Notes |
| --- | ---: | --- |
| Public tables | 48 | Every table has RLS enabled; `FORCE ROW LEVEL SECURITY` is not enabled. |
| Public views | 2 | `saved_payment_methods_safe`, `transporter_review_aggregates` |
| Constraints | 290 | Includes primary, foreign, unique, and CHECK constraints. |
| Indexes | 151 | Includes lifecycle, financial, MPIN/reset-claim, and canonical-event idempotency/uniqueness indexes. |
| Non-internal public triggers | 28 | Includes updated-at, immutable-version, profile-separation, shipment-history, and canonical-event contract/append-only triggers. |
| Public functions | 13 | Includes the baseline authorization helper and three canonical-event validator/enforcement functions. |
| RLS policies | 97 | Admin and party/owner policies cover current tables; the event, session, trusted-device, MPIN, and reset-authorization tables have narrow server policies. |
| Public enum | 1 | `app_role`: `admin`, `customer`, `transporter`, `fuel_station_manager`, `shopkeeper`; no dispatcher. |

The Auth trigger `auth.users.trg_on_auth_user_created` is present. The Storage bucket `shipment-documents` is private and contained zero objects. The only Storage object policy found was `shipment_docs_admin_all`.

The baseline application added exactly `trg_transporter_profiles_updated_at`, `trg_fuel_station_profiles_updated_at`, and `trg_shopkeeper_profiles_updated_at` to shared TEST by reusing `set_updated_at()`. It also installed the non-recursive shipment authorization helper/policy. Post-application reconciliation retained 43 tables, two views, 218 constraints, 122 indexes, and 94 policies; function count became 10 and non-internal trigger count became 24. All business row counts, safe financial totals, and existing profile `updated_at` values remained unchanged.

Shared TEST has empty event tables, 172 catalog rows, 164 Planned, 8 Deferred, 158 writable, 23 integrated, 141 Planned-unintegrated, 135 writable-unintegrated, six Operations, and signature `82bd918f68377090324c3a15da210769`. Phase 1B-2C3C1 advanced the exact locked pre-state of 170/162/8/156/21/141/135/6 and signature `b57a59369062e678a7b269cd61d4e01e`; migration and rollback-probe reconciliation retained empty event tables.

Phase 1B-2C3C2 activates `.step_up_consumed` and `.step_up_reconciliation_required` in repository code because reviewed domain owners now emit them. The caller-owned transaction couples database mutations with consumption evidence. Payout-destination tokenization uses claim/finalize; an uncertain provider or persistence outcome reconnects with every original binding, leaves an already committed `consumed` claim consumed, or moves a surviving `claimed` row to terminal `reconciliation_required`, then writes idempotent reconciliation evidence without repeating provider or domain work. Shared TEST now has the reconciled 25-integration state after the separately authorized `220000` rollout. `.expired_inactivity` remains rejected.

Phase 1B-2C2 migration `20260801160000_trusted_device_hardening.sql` was integrated at `eb10d8eff93499a67e424bea5a60fd0245d46c4f` and applied to authorized shared TEST from the immutable Git blob with SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`. Trusted-device rows remained 31 to 31; stable IDs/user ownership and the zero-row `user_sessions` same-user binding were preserved. Eligible legacy credentials were converted server-side to exact 32-byte SHA-256 digests without returning token values, and the raw `device_token` column was removed. Null, duplicate, invalid-length, and broken-owner counts were zero.

Phase 1B-2C3A is implemented in main and authorized shared TEST. `user_sessions` is the sole runtime authentication authority: full password signup/login atomically creates one digest-only session bound to the exact active same-user trusted device, then returns the raw opaque credential only in the separate HttpOnly `dtx_session_token` cookie (SameSite=Lax, path `/`, Secure outside explicit local development, 30-day bound). Flask's signed session retains only non-authoritative CSRF and presentation activity state; browser-supplied user ID, role, and profile identity are ignored. `/auth/me` validates without refreshing `last_genuine_activity_at`. Current-session logout locks and revokes exactly that session and writes `security.session.revoked` with `security.logout.completed` in the same transaction, while local cookies are cleared even if persistence fails.

Phase 1B-2C3A integration commit `3771b5e21f02dab1048e90e14131a00db90baf08` and migration `20260801170000_durable_session_runtime_events.sql` remain implemented in main and authorized shared TEST. The applied `20260801180000_secure_mpin_access_lock.sql` has immutable SHA-256 `33365c7486301dee906c4171c823e13e457660f67576762df980484e2c24d006`; it changed the event signature from `87c1377e1404933c69b1a90ac9962937` to `8dcc0c1ecaf1df3fdad9d0be30f6be03` and created no MPIN/session/event fixture. Applied `20260801190000_reset_authorization_claims.sql` has immutable SHA-256 `b3f2b18270588e8046651fb1776b1704938a292e3c3ca105334cd0be38ed690e` and activates no event. Applied `20260801200000_genuine_session_activity.sql` has immutable SHA-256 `0f1f0be3d18c8693e396c3b699fc8442dd8361f2c976b30656a6e03a3c852e71`; it activates only `security.session.refreshed`, changed the signature to `b57a59369062e678a7b269cd61d4e01e`, and created no fixture. Category A step-up mutations/frontend integration are implemented only on the unrolled C3C2 feature branch. Logout-all, password/reset/account-block mass revocation, expiry-event processing, the device/session management dashboard, GPS, and OTP security flows remain Planned.

The applied Phase 1B-2C3C1 migration `20260801210000_mpin_step_up_authorization_foundation.sql` has Git blob `6ea935b8033ddccc12e870b6104961f7758dc2a8` and immutable SHA-256 `736b38ea1844b6f0c9a7087a7ff2441a1b7214b08d968352d52e147d68ee7dc5`. It is guarded by the exact pre/post event signatures and two accepted physical foundation signatures arising from fresh versus historical additive column layout. Disposable PostgreSQL verification proved convergence, exact valid-state reapplication, abort on injected ledger-column corruption, and zero fixtures. Authorized shared TEST received only this exact committed blob in one atomic transaction, without a fabricated migration-ledger row or reapplication of an earlier migration.

Shared-TEST rollback probes verified the ledger's 14 constraints, six indexes, enabled non-forced RLS, one permissive `service_role` all-rows policy, and direct privileges of only `SELECT`/`INSERT`/`UPDATE` on the ledger plus `SELECT`/`USAGE` on its sequence. `PUBLIC`, `anon`, and `authenticated` have zero prohibited access. Proof issuance persisted only a SHA-256 digest with an exact 180-second lifetime; current, rotated-stale, expired, cross-user/session/device/generation/action/resource/fingerprint, amount, currency, and destination boundaries behaved fail-closed. Change/reset/disable invalidated available authorizations, the canonical fifth failure locked, one issuance/claim winner remained usable, exactly the two integrated events were accepted, all 149 unintegrated definitions were rejected, and no raw MPIN/proof/provider sentinel or Category A mutation persisted.

Post-rollout reconciliation found zero `mpin_credentials`, `user_sessions`, reset authorizations, step-up authorizations, and event rows; no Auth or business fixture and no replacement MPIN credential were created. All 48 pre-existing public-table row counts, checked financial aggregates, and unrelated schema/object fingerprints were unchanged, and legacy MPIN active/hash state remained zero. `mpin_credentials` has RLS enabled; `service_role` has exactly `SELECT`, `INSERT`, `UPDATE`, and `DELETE`, while `PUBLIC`, `anon`, and `authenticated` have no prohibited access. Reset authorization storage grants its service owner exactly `SELECT`, `INSERT`, and `UPDATE`, its sequence exactly `SELECT` and `USAGE`, and rollback-only probes persisted no rows.

Only the current digest resolves an active trusted device. `previous_token_digest` never authenticates; it exists only for bounded conflict/replay handling, is overwritten by later rotation, and remains bounded by revocation and absolute expiry. Rotation immediately invalidates the previous raw credential and concurrent rotations serialize under row locking. Expired and revoked devices fail closed, revoked rows cannot be silently reactivated, and maximum lifetime is 30 days. The migrated table has RLS enabled, one bounded `service_role` all-rows policy, seven expected constraints, and three expected unique indexes. `PUBLIC`, `anon`, and `authenticated` have zero privileges; `service_role` has exactly `SELECT`, `INSERT`, `UPDATE`, and `DELETE`, with no `TRUNCATE`, `REFERENCES`, `TRIGGER`, or `MAINTAIN`. Current-digest uniqueness and stable `(id,user_id)` ownership are enforced.

### 4.2 Tables, views, and safe aggregate row counts

| Domain | Objects with verified TEST row counts |
| --- | --- |
| Identity/security | `users` 19; `login_activity` 44; `trusted_devices` 31; `password_reset_otps` 0; `reset_tokens` 0; `user_sessions` 0; `mpin_credentials` 0 |
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

The full 48-table column set was compared programmatically with the canonical schema and matched exactly. Important shapes are:

| Object | Verified key capability |
| --- | --- |
| `users` | Auth UUID link; enum role plus legacy role; contact/profile fields; invalidated legacy MPIN hash/flag columns; JSON settings; block fields; timestamps. |
| `login_activity` | Optional user; raw login identifier/method; status/failure reason; raw IP/user agent; timestamp. |
| `trusted_devices` | Unique 32-byte `token_digest`; optional 32-byte previous rotation digest; user FK and stable `(id,user_id)` session binding; created/last-used/absolute-expiry/revoked/rotated timestamps; service-role-only table access. |
| `user_sessions` | Unique 32-byte session-token digest, exact same-user trusted-device binding, immutable 30-day absolute expiry, sliding seven-day inactivity boundary, access-lock state, digest-only access proof with an eight-hour maximum, and recent password-verification time. |
| `mpin_credentials` | One user-owned versioned scrypt verifier with a unique 32-byte salt, bounded attempt state, permanent fifth-failure lock, RLS, and service-role-only access; no pepper or raw MPIN column. |
| `reset_tokens` | Digest-only authorization, bounded one-winner claim/finalization state, explicit `reconciliation_required` outcome, and no raw reset token. |
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
| `20260801180000_secure_mpin_access_lock.sql` | Adds the canonical MPIN credential table, three access-proof/password-verification session fields, strict RLS/ACL/constraints, invalidates legacy verifier state, and activates exactly eight events | Implemented in main and applied to authorized shared TEST; immutable SHA-256 `33365c7486301dee906c4171c823e13e457660f67576762df980484e2c24d006`; signature `87c1377e1404933c69b1a90ac9962937` to `8dcc0c1ecaf1df3fdad9d0be30f6be03`; sequential/fresh/reapply/corrupt paths and rollout created zero credential/session/event fixtures |
| `20260801190000_reset_authorization_claims.sql` | Forward-only reset-authorization claim lifecycle, legacy authorization invalidation, strict state constraints, digest uniqueness, and service-role-only ACL/RLS | Implemented in main and applied to authorized shared TEST; immutable SHA-256 `b3f2b18270588e8046651fb1776b1704938a292e3c3ca105334cd0be38ed690e`; sequential/fresh/reapply/partial/corrupt paths passed; it activates no canonical event and left zero reset authorizations. |
| `20260801200000_genuine_session_activity.sql` | Activates exactly `security.session.refreshed` for the transaction-owned genuine-activity runtime; no table change or fixtures | Implemented in main and applied to authorized shared TEST; immutable SHA-256 `0f1f0be3d18c8693e396c3b699fc8442dd8361f2c976b30656a6e03a3c852e71`; signature `8dcc0c1ecaf1df3fdad9d0be30f6be03` to `b57a59369062e678a7b269cd61d4e01e`; sequential/fresh/reapply/partial/corrupt paths passed and created no fixtures. |
| `20260801210000_mpin_step_up_authorization_foundation.sql` | Adds credential generation, exact session/device binding, a digest-only three-minute step-up ledger, narrow ACL/RLS, and exactly two integrated issuance outcomes | Fast-forwarded into main through feature SHA `48f5fbc9a260ef74dfc6bfa4e5004edd78835f44` and applied as exact Git blob `6ea935b8033ddccc12e870b6104961f7758dc2a8` to authorized shared TEST; immutable SHA-256 `736b38ea1844b6f0c9a7087a7ff2441a1b7214b08d968352d52e147d68ee7dc5`; signature `b57a59369062e678a7b269cd61d4e01e` to `82bd918f68377090324c3a15da210769`; final ledger/event/session/MPIN fixture rows zero. |
| `20260801220000_mpin_step_up_high_risk_integration.sql` | Adds exact wallet funding-source binding and activates consumption/reconciliation evidence for the six reviewed domain owners | Applied once to authorized shared TEST from the immutable Git blob; SHA-256 `0CA345DB3A3CF3DC0221B54FC0F0F34E3A5ED58A56CE6D75B8326F8C008F6C2E`; Git blob `ae38c8cd7962f32a341924fa7f4fc476dbab6292`; production remains undeployed. |

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

- [`backend/events/catalog.py`](../backend/events/catalog.py) remains the only machine-readable catalog owner. Main and shared TEST have 23 integrated Planned security definitions: the preceding twelve plus access-lock, seven non-step-up MPIN integrations, exactly `security.session.refreshed`, and exactly `security.mpin.step_up_succeeded`/`.failed`.
- [`backend/events/contract.py`](../backend/events/contract.py) owns the shared typed envelope. The maximum encoded envelope is 8,192 bytes; metadata is 2,048 bytes; each before/after object is 1,024 bytes; objects are flat, have at most 16 keys, use explicit type maps, and permit strings of at most 128 contract characters.
- [`backend/events/environment.py`](../backend/events/environment.py) derives only `local`, `test`, `staging`, or `production` from server configuration and fails closed when configuration is absent/unknown.
- [`backend/events/writer.py`](../backend/events/writer.py) exposes one security writer and one business-audit writer. Each accepts the caller's existing production `Db` transaction executor or native cursor, opens no connection, and never commits or rolls back. The database supplies `occurred_at`; catalog/context supply category/version/actor/retention/environment.
- `canonical_event_catalog_projection` is migration-owned enforcement metadata generated from the Python catalog, not a third event store or a second semantic owner. Main and authorized shared TEST contain exactly 25 integrated security definitions. Deterministic bidirectional tests reject missing, extra, duplicate, or drifted definitions.
- Scoped `(idempotency_scope, idempotency_key)` uniqueness uses a SHA-256 envelope fingerprint. Same-key/same-fingerprint calls replay the existing row; same-key/different-fingerprint calls fail without aborting the transaction; concurrent duplicates create one row.
- `security_events` and `business_audit_events` each retain 43 columns, a UUID primary key, 16 named CHECK constraints, an UPDATE-blocking trigger, a catalog-contract INSERT trigger, and scoped idempotency uniqueness. Security has five explicit secondary/unique indexes plus its primary-key index; business audit has eleven plus its primary-key index. The database rejects unknown/non-writable names, table/category, version or retention drift, and user/admin actors missing either server-owned ID or role.
- All three Phase 1B tables have RLS. `anon`, `authenticated`, and `PUBLIC` have no event-table privileges or policies. The applied ACL correction leaves `service_role` exactly `DELETE`, `INSERT`, and `SELECT` on each event table and no projection access; UPDATE remains blocked by privilege and append-only trigger.
- Migration reapplication first computes one OID-independent semantic signature over exact columns/types/nullability/defaults, constraints, indexes, triggers, function definitions, RLS, policies, non-owner privileges, and all projection tuples. Only zero owned objects or the exact completed foundation may proceed; every partial or incompatible state aborts before migration DDL and preserves existing rows/objects.
- The migration creates zero event rows, performs no backfill, alters no legacy table, and creates no `analytics_events`, operations table, or `event_outbox`.

There is no current asynchronous consumer or delivery requirement, so an outbox would be unused speculative state. `event_outbox` is deferred until a proven consumer exists; any future outbox must share the authoritative mutation transaction and must not become a second audit owner.

### 6.2 Phase 1B-1 verification evidence

- Full sequence `20260731220000` then `20260731230000`, safe foundation reapplication, and fresh `schema.sql` convergence passed on disposable PostgreSQL. The forward ACL correction additionally proves convergence among old migration plus new migration, corrected fresh `schema.sql`, and an already-correct narrow database.
- Migration/fresh schema produces zero event rows. In main and shared TEST, the integrated guard admits exactly 21 definitions and rejects the remaining 135 writable-but-unintegrated Planned definitions.
- Fresh, partial and exact-reapply migration tests prove fail-closed preservation for wrong column names/types/nullability/defaults, weakened CHECKs, missing indexes/triggers/policies, wrong RLS/grants and drifted helper definitions. Phase 1B-2B pre-merge verification passed the complete PostgreSQL backend suite with 678 tests and zero failures/skips; its explicit no-DB run passed 302 while safely skipping 376 PostgreSQL-dependent tests.
- Phase 1B-1 remains **Implemented in the repository and shared TEST**: `20260731230000_canonical_event_foundation.sql` and `20260731240000_canonical_event_acl_hardening.sql` are both applied. Its foundation and ACL guarantees are unchanged.
- Phase 1B-2C0 verification passed 682 PostgreSQL tests with zero failures/skips, explicit no-DB mode passed 304 with only 378 expected PostgreSQL skips, and fresh/sequential/reapply/partial/corruption projection paths converged. The migration is merged into main and applied to authorized shared TEST; no runtime emitter was added.
- Phase 1B-2C1 feature verification passed 692 PostgreSQL tests with zero failures/skips and explicit no-DB mode passed 306 with only 386 expected PostgreSQL skips. Fresh schema, sequential migration, exact reapplication, relationship/state/privilege enforcement, and partial/corrupt-state rejection converge without changing the `3d9b730408336c82629c25342ddc7ea2` event signature or creating session/event rows.
- Phase 1B-2C2 verification passed 699 PostgreSQL tests with zero failures/skips; explicit no-DB mode passed 308 with 391 expected PostgreSQL skips. Migration `20260801160000_trusted_device_hardening.sql` has SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`; fresh/sequential/reapplication/corrupt-state, ACL, auth rollback, MPIN fail-closed, and prior-domain suites passed. The migration was then applied to authorized shared TEST, where reconciliation preserved every unrelated count/fingerprint and rollback-only token/event/role probes left zero persisted rows.
- Phase 1B-2C3B1 pre-rollout verification passed 746 PostgreSQL-backed tests with zero failures/skips and explicit disconnected mode passed 332 with 414 expected database skips. All 14 frontend Node/static tests, test-source ESLint, production build, Python compileall, migration immutability, fresh/sequential/exact-reapply/corrupt convergence, duplicate, sensitive-log, legacy-SQL-dialect, catalog/registry, and ACL checks passed. Repository-wide frontend lint still has its unchanged pre-existing baseline outside this backend phase. Those checks preceded the separately authorized shared-TEST rollout; no production access or deployment occurred.

### 6.3 Phase 1B-2A/2B bounded auth integration

Phase 1B-2A and Phase 1B-2B are implemented in main and authorized shared TEST. Exactly `security.login.started`, `security.login.failed`, `security.login.succeeded`, `security.logout.completed`, `security.signup.started`, `security.signup.failed`, and `security.signup.completed` were integrated by those phases. The Phase 1B-2B migration is applied through `20260801130000_security_signup_event_integration.sql` (SHA-256 `915c7937fd36e8dae19ab0f45b4a1cd10fade3a52c9bca959ffd49ca59f909e5`), changing the then-current signature from `993b1de965a1791a2a84ccff5fcfbdf9` to `371c7010a0553c7953708dea164ed0bc`. At Phase 1B-2B completion the other 143 Planned definitions and all 8 Deferred QR definitions were unintegrated; later authorized phases advanced the current totals to 23 integrated and 141 Planned-unintegrated while every Deferred QR definition remains unintegrated.

- One server-generated request ID owns each request. Login-start and terminal events use separate scopes; exact replay is idempotent and conflicting terminal reuse fails closed. Client identity, correlation/request IDs, time, environment, session/device references, and event names cannot replace server-owned values.
- Valid password login commits `started` in its own short route-owned transaction before credential verification; failure to persist it prevents the provider call. Terminal `login_activity`, `last_login_at` on genuine success, trusted-device persistence, and the terminal canonical event share a separate route-owned PostgreSQL transaction. Terminal failure leaves exactly the durable `started` evidence, rolls back every terminal mutation, and prevents Flask session issuance.
- Phase 1B-2B uses the same caller-owned writer discipline: a server request ID commits anonymous signup-start before external Auth creation; public user/profile, success activity, trusted device, and completed evidence share one public transaction. On public failure, only an Auth identity proved by the server request metadata can be compensated. Proven cleanup records `persistence_failed`; an unproven or failed cleanup records `reconciliation_required`; neither path issues a session, CSRF state, or device cookie.
- The password provider adapter classifies only the installed Auth client's exact structured `invalid_credentials` code as an ordinary rejection. It does not match exception messages. Transport, timeout, malformed-response, retryable, other API, and provider-unavailability failures become one sanitized `provider_unavailable` result. Blocked, unknown, and wrong-password outcomes have the same public status, field, shape, and message; the known blocked case remains internally `account_unavailable`.
- Failed events remain anonymous and contain only `validation_failed`, `invalid_credentials`, `account_unavailable`, or `provider_unavailable` in allowlisted metadata. They contain no login identifier, email, CNIC, phone, IP, GPS, User-Agent, password, token, raw provider exception, request body, session or device reference.
- Authenticated CSRF-valid logout derives the server actor before clearing and emits `security.logout.completed`. Anonymous and invalid-CSRF calls emit none. Audit failure is sanitized in server logs and cannot prevent local session clearing.
- [`20260801100000_security_login_event_integration.sql`](../supabase/migrations/20260801100000_security_login_event_integration.sql) requires the exact prior signature `772212260b85fd6b5cd4aa35ca9ffdfb`, empty event tables on first activation, and either zero or the complete four-row activation state. It relaxes only the integrated constraint, changes only the four integrated flags, rejects partial state, is idempotent, and converges on `f5168975e0605fe0f7b84c1276a0082a` with fresh `schema.sql`. The applied [`20260801110000_canonical_event_integrated_guard.sql`](../supabase/migrations/20260801110000_canonical_event_integrated_guard.sql) requires that exact activation state and hardens the existing guard to require `writable`, `integrated`, and Planned lifecycle before insert, producing `7b8157021244549cfed79416b40ab662`.
- Focused Phase 1B-2B post-merge validation passed 100 signup/auth/canonical tests; the complete pre-merge backend PostgreSQL suite passed 678 with zero failures/skips. The explicit no-DB run passed 302 and skipped 376 database-dependent tests. The production build passes; this frontend package has no test script and no frontend file changed, so changed-file ESLint is not applicable.
- Signup runtime integration is implemented in main and shared TEST: start commits before external provider creation; public user, correct role profile, success activity, trusted-device mutation/event, durable session, completed evidence, and `security.session.issued` share the terminal public-database transaction; session/device/access-proof cookies and CSRF state issue only after commit. Failure uses one anonymous `security.signup.failed` event with an approved coarse result code and rolls back terminal success evidence. Cleanup deletes only an Auth identity provably created by that request; ambiguous or failed cleanup records `reconciliation_required`. Canonical metadata never includes password, token, digest, cookie, CSRF, OTP, CNIC, email, provider error text, or another sensitive value. Secure non-step-up MPIN, access-lock runtime, trusted genuine-session refresh, and the step-up issuance foundation are implemented; password/reset mass revocation, Category A mutation/frontend step-up integration, OTP delivery security flows, GPS security flows, risk, `security.session.expired_inactivity`, business, analytics, and Operations integrations remain Planned.

### 6.4 Phase 1B-2C3B2 frontend completion evidence

Phase 1B-2C3B2 and its bounded responsive/navigation corrections advanced repository main by fast-forward only from `209f3bab8d0c3b9a71181e6a2f04b82e49264126` to `c3e260427ab640240f4df904e3fa57c5320982df`. The integrated range contains five linear commits and zero merge commits. It is frontend-only except for two backend test-file corrections; it changes no backend runtime, API, schema, migration, database object, scheduler behavior, or event catalog. No shared-TEST/database change was required or performed, and no production access, rollout, public launch, or deployment occurred.

The repository-main frontend now provides:

- one canonical seven-state access-lock owner that recognizes only structured `423` with `code=access_locked`, sends ordinary `401` to full login, and blocks/inerts protected content while locked;
- a fail-closed, generation-bound, one-shot, path-only replay descriptor whose exact approved allowlist contains only `GET /api/platform/terms/current`;
- one route-scoped signup-wizard password owner that clears sensitive state on failure, cancellation, route departure, logout, completion, and provider teardown, and prevents stale or abandoned operations from affecting a newer wizard generation;
- no production module-global signup-password singleton and no password/MPIN browser persistence, history, analytics, URL, or log owner;
- one shared MPIN-management frontend for exactly `logistics_provider`, `service_seeker`, and `everyday_user`, retaining one accessible masked input with four presentation-only digit slots; and
- Hassan's explicit real-Chrome PASS for responsive presentation and physical-keyboard typing, Backspace correction, paste, non-digit rejection, Enter submission, Escape resistance, focus containment, password fallback, logout, and authoritative unlock.

The responsive/mobile completion removes the hamburger, More destination/sheet, and standalone mobile-header logout. The avatar opens Account/Profile; canonical Security and Logout live within Account/Profile; the notification control sits beside the avatar. Shared bounded owners provide distinct mobile/desktop typography, compact MPIN digit visuals, separate desktop-sidebar and mobile-bottom-navigation behavior, and responsive containment across all reviewed routes.

Role navigation remains permission-bounded:

- `service_seeker`: **Dashboard**, **Post Order**, **Wallet**, **Messages**. Post Order contextually exposes **One-Time Order**, **Agreemental Order**, **My Orders**, and **My Agreements**.
- `logistics_provider`: **Dashboard**, **Trucks**, **Bids**, **Messages**.
- `everyday_user`: **Dashboard**, **Post Order**, **My Orders**, **Messages**. Wallet and Agreemental destinations are not exposed.

The Phase 1B-2C3B2 frontend verification passed 74/74 Node/static tests, changed-file ESLint, a 754-module production build, and the responsive containment matrix at 320, 360, 375, 390, 414, 768, 1024, and 1440 pixels plus 667×320 landscape; the manual real-Chrome responsive/native-keyboard gate passed. At that phase boundary the six high-risk mutations and `StepUpProvider` were still Planned. Phase 1B-2C3C2 later implemented those exact six connections in main/shared TEST without changing the remaining logout-all, GPS/security, mandatory OTP, device/session-dashboard, operational-integration, or deployment classifications. The product remains under development/private testing.

## 7. Security and login locked contract

Everything in this section is **Planned** unless explicitly cross-referenced as current.

Phase 1B-2A is the main/shared-TEST cross-reference for login/logout events. Phase 1B-2C3B1 integrates access-lock, seven non-step-up MPIN names, and session refresh; Phase 1B-2C3C1 integrates step-up issuance success/failure. Phase 1B-2C3C2 feature code additionally integrates `.step_up_consumed` and `.step_up_reconciliation_required`; shared TEST has the reconciled post-rollout state. `.expired_inactivity` remains rejected.

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
- GPS-denied and untrusted-device full-login flows use verified Email OTP only; SMS is neither a fallback nor a second factor.
- SMS has zero supported runtime, provider, configuration, preference, catalog, database, or roadmap surface. Phone fields remain legitimate identity/contact data only.
- A verified email address is the mandatory external security identity. Signup Email OTP and password-plus-Email-OTP reset of a locked MPIN remain Planned; password reset and password change already use Email OTP.
- Full login on an untrusted device requires password plus verified Email OTP when that dedicated flow is implemented. MPIN remains only a trusted-session software unlock and the approved Category A step-up factor; it never replaces full-login or locked-MPIN recovery requirements.
- Security and payment notices require both in-app and email delivery once the email delivery ledger/provider contract exists. Order, trip, agreement, chat, and other operational email copies are user-optional; their in-app records remain authoritative. Marketing is optional email only.
- Email policy is provider-neutral: Gmail, Outlook, Yahoo, company domains, and other syntactically valid providers are eligible under the same future verification contract. The dedicated organization portal has no backend route owner and remains Planned: every `/org/*` location fails closed, clears legacy organization tokens, collects no credentials, and directs companies and business service seekers to the canonical account flow.
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
| Auth event evidence | Password-login/logout and signup routes plus transitional helper | Shared TEST: `login_activity` and empty `security_events`; all integrations through Phase 1B-2C3B1 applied | Main/shared TEST integrate exactly 21 canonical security events; only integrated+writable names are insertable | Login and signup starts commit before external provider operations; terminal public evidence owns activity, trusted device where applicable, and terminal event; canonical payload excludes legacy identifier/IP/device-credential fields | Any additional event, raw failure/identity field, duplicate start, or split terminal commit |
| Device registry | Canonical [`auth/trusted_device_service.py`](../backend/auth/trusted_device_service.py) | Hardened `trusted_devices` in main/shared TEST | Exact 32-byte current digest only; raw-token column removed; stable IDs/owners, 30-day maximum expiry, revocation, and locked rotation enforced | Canonical service reusable; trusted-device evidence still does not authenticate a Flask/server session | Preserve current-digest-only resolution; add management/revocation integrations in separately reviewed phases | Any previous digest authenticates, raw credential persists, or revoked/expired row resolves/reactivates |
| Sessions | Canonical [`auth/session_service.py`](../backend/auth/session_service.py); Flask cookie is presentation/CSRF-only | Main/shared TEST durable `user_sessions` with proof digest/expiry and recent password-verification time | Durable session plus exact trusted device is authoritative. The access proof is evaluated separately, transitions atomically to 423 software lock once, and rotates without refreshing authentication or genuine activity. Trusted activity advances only the current session's inactivity boundary and integrates `security.session.refreshed` | Canonical foundation, proof owner, and activity owner are reused; raw session/proof values remain browser-memory cookies only | User-initiated logout-all reuses this authority on its 2C4 feature branch; keep expiry-event processing, dashboard, GPS, OTP delivery, and non-user mass revocation separate | Any raw token persistence, proof in browser storage/JSON, expiry extension, or access-lock bypass |
| OTP | Auth/profile helpers | `password_reset_otps`, hardened `reset_tokens` | Has hashed OTP, bounded attempts/purpose, row-locked one-shot consumption, and atomic digest-only reset claims | Replay/claim correction is implemented; 10-minute expiry/text timestamps/no device binding/HMAC remain | New delivery/challenge contract; preserve the corrected reset flow until cutover | Provider/domain, resend, or future device-bound delivery controls absent |
| Risk/security cases | None | None | Absent | Missing | Disabled → shadow foundation first | Any enforcement before shadow validation |
| Generic tracking | Contained ActivityTracker/API | `user_action_logs` | Historical arbitrary JSON retained; new writes restricted to one safe page-visit shape | Phase 1A containment implemented; table remains incompatible for the four canonical domains | Keep endpoint-local sanitizer; future consent-aware analytics replacement; retain/administer legacy data | Sensitive-field inventory or retention unknown |
| Shipment status history | DB trigger | `shipment_status_history` | Present and consistent | Reuse as status evidence; not full audit | Reference from business events; avoid duplicate generic events | Trigger semantics drift or missing actor context not addressed |
| Shipment/trip direct-client RLS | PostgreSQL policies | `shipments`, `shipment_trips` | Shared TEST has all three profile triggers and the corrected non-recursive helper/policy; role probes have no `42P17` | Former trigger/policy drift is resolved | Preserve the helper contract and role matrix | Any additional drift, helper privilege broadening, recursive dependency, or role-visibility regression |
| Canonical event foundation | `backend/events` catalog/contract/writers | Shared TEST `security_events`, `business_audit_events`, and `canonical_event_catalog_projection` | Shared TEST is at the applied empty-table, 172-definition, 23-integration state with narrow ACL and signature `82bd918f68377090324c3a15da210769` | Access-lock, seven non-step-up MPIN events, `.refreshed`, and step-up `.succeeded`/`.failed` are integrated; `.expired_inactivity`, `.step_up_consumed`, and `.step_up_reconciliation_required` remain rejected | Continue only through separately reviewed domain-owner changes using the existing writer/caller transaction | Any direct route table write, client identity/time, second catalog, partial activation, or guard regression |
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
| MPIN/password/reset/device | Auth routes plus canonical MPIN/session/trusted-device/step-up services | Main/shared TEST `mpin_credentials`, access-proof fields in `user_sessions`, hardened reset claims, hardened `trusted_devices`, and zero-row `mpin_step_up_authorizations`; main/shared TEST code adds no fixture | Legacy fast-login authentication and legacy verifier activation remain disabled; the forward migrations created no replacement credential/session/authorization fixtures; shared TEST retains zero credentials, sessions, reset authorizations, and step-up authorizations | Access-lock, seven non-step-up MPIN events, trusted genuine-session refresh, step-up issuance `.succeeded`/`.failed`, exactly six Category A mutations, consumed/reconciliation writers, authority-context cancellation, `StepUpProvider`, and user-initiated logout-all are implemented in main/shared TEST | Password/reset/block/admin/incident mass revocation, expiry-event processing, the device/session security dashboard, GPS, and OTP delivery security remain Planned; the C3C2 migration is applied in shared TEST and was not reapplied for 2C4 |
| Legacy page tracking | `tracking/routes.py`; browser contract fixed to page visits | `/api/track` inserts `user_action_logs` and owns its commit | Route owns validation/insert/commit; no domain lock | Future General Analytics, not either canonical table | **Do not attach/redirect**; legacy containment remains separate |
| Orders and bids | `orders/routes.py`; legacy accept/process-payment endpoints refuse old flow | Direct `shipments` and `shipment_bids` writes | Route owns commit; validation reads truck/order state, with checkout revalidation later | `one_time.order.*`, `one_time.bid.*`, `matching.*` | Technically caller-transaction compatible, but integration remains Planned |
| Checkout/payment hold | `shared/payments.perform_checkout`; routes are commit owners | Shipment, bid, vehicle, wallet, wallet-transaction, payment, trip, tracking and chat writes | Existing cursor transaction; locks order, then bid, vehicle and wallet before state transitions; helper does not commit | One-Time checkout/payment plus wallet funding owners | Compatible with caller-owned writer after a dedicated integration review |
| Release/refund | `shared/payments.release_one_time_payment` / `refund_one_time_payment` | Payment, wallet and wallet-transaction writes | Caller owns commit; payment then relevant wallet rows are locked | `one_time.payment.released/refunded`, canonical wallet credit | Compatible, not connected |
| Delivery/dispute/review | `orders/lifecycle.py` and `orders/reviews.py`; completion/confirmation route aliases converge on these services | Shipment, trip, dispute, payment, wallet, review, notification and chat writes | Caller owns commit; canonical lock order is shipment → trip → dispute → payment → wallet | Specific One-Time trip/delivery/dispute/review events | Compatible, not connected; no generic duplicate status wrapper allowed |
| Wallet/withdrawal | `wallet/helpers.py`, wallet routes, payments, agreements and admin routes | Wallet, wallet-transaction and withdrawal tables | Multiple current commit owners; row locks exist in payment paths but ownership remains distributed | `wallet.*` | **Stop before integration** until each direct writer is assigned and replay/lock behavior is unified |
| Fleet/profile/documents | Profile/truck routes and shared Storage helper | Users/profile/vehicle/document tables plus Storage | Route commits DB work; Storage is external and not one DB transaction. Private-download authorization, opaque upload keys, and sanitized provider failures are implemented; application validation alone uses `TruckUploadValidationError`/400 and provider failures use stable 503 | `transporter.*`, `business.profile.*` | DB-only transitions may attach later; upload evidence still needs separately reviewed external-failure events |
| Commission/Terms/admin decisions | Shared commission helpers and admin routes; actor envelope replaces wrapper aliases | Version tables/domain state; commission publication also writes legacy `user_action_logs` | Admin route owns DB transaction/commit; immutable version triggers protect published rows | `commission.*`, `terms.*`, specific business owner; `admin.security_action.performed` only as fallback | Compatible for domain rows after removing mixed legacy audit ownership in a separately authorized phase |
| Notifications and scheduled transitions | `shared/notifications.py`, lifecycle services, scheduler/manual admin trigger | Idempotent `shipment_notifications` plus business transitions | Notification helper never commits; lifecycle/admin/scheduler caller owns transaction and locks | Business transition event plus separate `notification.*`; future `system.job.*` remains non-writable until operations persistence | Business notifications are attachable later; scheduler run evidence needs its separate operations phase |

Phase 1B-1 does not change a domain owner. Phase 1B-2A attaches the existing cursor-level security writer to four password-login/logout outcomes. Phase 1B-2B attaches three signup outcomes in main and shared TEST. Phase 1B-2C2 attaches the three trusted-device outcomes in main and authorized shared TEST. Phase 1B-2C3A attaches issued/revoked session outcomes in main and authorized shared TEST. Phase 1B-2C3B1 attaches access-lock and seven non-step-up MPIN outcomes, and the bounded genuine-activity correction attaches exactly `security.session.refreshed`. Phase 1B-2C3C1 attaches only step-up issuance success/failure; C3C2 later attaches Category A consumption/reconciliation and 2C4 reuses existing logout/session/device/step-up contracts without catalog activation. GPS, OTP delivery security, non-user mass revocation, expiry-event processing, and the security dashboard remain future bounded changes.

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
3. **Phase 1B-1 — Canonical event foundation and ACL hardening (Implemented in repository and shared TEST)** — both Phase 1B-1 migrations are applied; the two event tables are present and empty, the foundation's initial 158-definition projection has been extended forward to the current 172-definition catalog, and the narrow ACL/signature is verified.
4. **Phase 1B-2A — Password login/logout security events (Implemented in main and authorized shared TEST; not deployed)** — exactly four definitions are integrated with caller-owned terminal transactions; the activation and integrated-state guard migrations are applied, and only integrated+writable names are insertable.
5. **Phase 1B-2B — bounded signup events (Implemented in main and authorized shared TEST; not deployed)** — exactly three signup definitions are integrated through `20260801130000_security_signup_event_integration.sql` and a compensation-aware external-Auth saga; GPS and Email OTP remain Planned and unintegrated.
6. **Phase 1B-2C0 — device/session/MPIN event contracts (Implemented in main and authorized shared TEST; not deployed)** — migration `20260801140000_device_session_mpin_event_contracts.sql` added twelve contracts and formalized five existing contracts. At Phase 1B-2C0 completion all seventeen were unintegrated; later phases integrated trusted-device, session, secure-MPIN/access-lock, genuine-activity, and step-up issuance definitions. Category A payment/action consumption, expiry-event processing, GPS, and Email OTP security flows remain Planned, and no payment or wallet behavior changed.
7. **Phase 1B-2C1 — durable server-session foundation (Implemented in main and authorized shared TEST; not deployed)** — one zero-row `user_sessions` table and the canonical session service established the digest-only token model, genuine activity, lock, expiry, rotation, and revocation state. At 2C1 completion the service was intentionally unused; Phase 1B-2C3A made it the sole runtime authentication authority, Phase 1B-2C3B1 added MPIN/access-lock and genuine-activity behavior, and Phase 1B-2C3C1 added the step-up foundation. Category A mutation/frontend integration, logout-all/remote and password/account-block mass revocation, expiry-event processing, the device/session management dashboard, GPS, and Email OTP security flows remain Planned.
8. **Phase 1B-2C2 — trusted-device hardening (Implemented in main and authorized shared TEST; not deployed)** — integration commit `eb10d8eff93499a67e424bea5a60fd0245d46c4f` and migration `20260801160000_trusted_device_hardening.sql` (SHA-256 `016c99fbf924e6eb578f563f6611a757fe1228293e8bc31f40e1282d63753609`) migrated 31 eligible rows in place to exact 32-byte SHA-256 digests while preserving stable IDs, user ownership, and same-user session binding. It removed raw-token storage, added 30-day maximum absolute expiry plus revocation/locked-rotation state, centralized runtime ownership, integrated exactly the three trusted-device events, and disabled the legacy MPIN authentication bypass while retaining then-legacy MPIN data. Later phases activated durable-session authority, invalidated legacy MPIN verifier state, implemented secure MPIN/genuine activity, and added action/resource-bound step-up grants. Category A consumers/frontend integration, logout-all/remote management, password/reset/block mass revocation, expiry-event processing, the security dashboard, GPS, and Email OTP security flows remain Planned.
9. **Phase 1B-2C3A — durable server-session runtime authority (Implemented in main and authorized shared TEST; not deployed)** — integration commit `3771b5e21f02dab1048e90e14131a00db90baf08` makes `public.user_sessions` the sole runtime authentication authority through the canonical session service. Password signup/login issue one digest-only session bound to the exact active same-user trusted device in the terminal caller-owned transaction; all protected routes resolve current identity/role/profile relationships from the durable row and current database state. Flask signed state is bounded CSRF/presentation-only. Current logout revokes exactly its locked session and leaves all other sessions untouched. Migration `20260801170000_durable_session_runtime_events.sql` (SHA-256 `fe4d8440ad683396b31da7ec8da0e335ceaa8936c1fb1c4d5f51a24058f57aeb`) historically advanced main/shared TEST to 12 integrations and signature `87c1377e1404933c69b1a90ac9962937`; Phase 1B-2C3B1 subsequently advanced them to 21 integrations. Logout-all/revocation triggers, expiry-event processing, dashboard, GPS, and OTP delivery security remain Planned.
10. **Phase 1B-2C3B1 — secure MPIN, software access lock, bounded security corrections, and genuine activity (Implemented in main and authorized shared TEST; not deployed)** — one canonical user-owned MPIN row uses exact four-ASCII-digit validation, unique 32-byte random salt, mandatory decoded 32-byte no-default environment pepper, versioned memory-hard scrypt, atomic failures, and permanent fifth-failure lockout for exactly `logistics_provider`, `service_seeker`, and `everyday_user`. A separate at-least-256-bit proof is stored raw only in memory and an HttpOnly non-persistent cookie and as a session-owned SHA-256 digest with an at-most-eight-hour server lifetime. Login/signup issue it only after terminal commit; unlock rotation extends neither session/device expiry nor genuine activity, and password unlock creates no session. Legacy verifier state is cleared and never activated. Deterministic mutation order is session → user → trusted device → MPIN credential → canonical event. Visible trusted pointer/touch/keyboard interaction refreshes inactivity at most once per twelve hours to database-now plus seven days, capped by immutable absolute expiry without shortening a later valid boundary; passive/synthetic/background activity does not count. OTP/reset claims are one-shot. Password, Auth, email, GPS, Storage, scheduler, private-file authorization, upload naming/validation, and agreement-alias CSRF corrections are implemented and sanitized. The Phase 1B-2C3C1 step-up foundation is now implemented separately; Category A mutations, logout-all, `.expired_inactivity`, dashboard, GPS security flows, and OTP delivery security flows remain Planned.
11. **Phase 1B-2C3B2 — secure MPIN frontend, software-lock UX, and bounded responsive/navigation corrections (Implemented in repository main; not deployed)** — main advanced by fast-forward only from `209f3bab8d0c3b9a71181e6a2f04b82e49264126` to `c3e260427ab640240f4df904e3fa57c5320982df` through five linear commits and zero merges. One centralized React access-state owner derives seven states from `/auth/me` and canonical MPIN status, recognizes only `423` with `code=access_locked`, requires full login for ordinary `401`, blocks and inerts protected content, keeps canonical CSRF logout and password recovery available, and permits one generation-bound one-shot path-only replay for exactly `GET /api/platform/terms/current`. One accessible masked four-digit control and one canonical management component serve transporter, Business/service-seeker, and Everyday surfaces; other roles receive no management route. One route-scoped signup-wizard password owner clears every terminal/abandonment path, and stale or abandoned operations cannot affect a newer generation. MPIN/password values remain non-persistent process state and never enter URLs, browser persistence, analytics, or logs. Responsive corrections remove the mobile hamburger, More sheet, and header logout; avatar-owned Account/Profile contains canonical Security and Logout, while permission-bounded role navigation and contextual order/agreement destinations remain reachable. Hassan explicitly passed the real-Chrome responsive/native-keyboard gate. This frontend-only integration changed no backend runtime, API, schema, migration, database object, scheduler, event catalog, or shared TEST state. At the B2 phase boundary `StepUpProvider` and Category A consumers remained Planned; the later C3C2 feature branch implements them while logout-all/device dashboard, expiry-event processing, GPS, OTP, production deployment, and public launch remain Planned or unimplemented.
12. **Phase 1B-2C3C1 — MPIN high-risk step-up authorization foundation (Merged into main and applied to authorized shared TEST; not deployed)** — main fast-forwarded from `bfafc6820b29e8c894e9bd3e017418a15636603a` to feature SHA `48f5fbc9a260ef74dfc6bfa4e5004edd78835f44` through exactly two linear commits and zero merges. One strict forward migration, generation-bound digest-only ledger, canonical service, authenticated CSRF-backed issuance route, and locked-session raw-proof revalidation establish a three-minute one-use authorization contract for exactly six server-recognized Category A descriptors. Success/failure events have real emitters and are integrated; consumption/reconciliation definitions remain rejected. No Category A business mutation, financial UI, provider call, scheduler, or frontend `StepUpProvider` is connected in this phase. Shared TEST moved from signature `b57a59369062e678a7b269cd61d4e01e` and catalog 170/162/8/156/21/141/135/6 to `82bd918f68377090324c3a15da210769` and 172/164/8/158/23/141/135/6, with exact ACL/RLS and zero credential/session/event/authorization probe rows after reconciliation.
13. **Phase 1B-2C3C2 — six-operation high-risk step-up integration (Implemented in main and authorized shared TEST; not deployed)** — exactly wallet-only checkout, withdrawal request, withdrawal-limit purchase, payout-destination replacement, agreement finalization, and client Yes delivery release consume action-bound proof. Authoritative server amounts, resources, funding source, and digest-only destination fingerprints are rebuilt and revalidated before mutation. Local mutations and consumed evidence share the caller-owned transaction. Payout-destination tokenization first makes the authorization non-replayable and performs provider I/O with no database connection or lock held. After an ambiguous final commit, a bound reconnect classifies the exact claim: committed `consumed` remains consumed; surviving `claimed` becomes terminal `reconciliation_required`; both paths write idempotent reconciliation evidence and never repeat provider or domain work. The current `DummyCardProvider` remains explicitly simulated and does not establish production payout capability. One centralized in-memory React `StepUpProvider` permits only the initial authoritative 428, explicit MPIN completion, and one generation-bound proof-bearing mutation. Opaque `/auth/me` references cause pending work to cancel when user, session, trusted device, or access-proof generation changes; timeout, 5xx, ambiguity, route teardown, logout/auth change, and stale generations cannot trigger another attempt. Card/mixed checkout, top-up, saved-card, dispute, admin, scheduler, refund, GPS, OTP, logout-all, and provider-backed unrelated paths remain outside scope.

    The forward migration `20260801220000_mpin_step_up_high_risk_integration.sql` was applied once to authorized shared TEST and has SHA-256 `0CA345DB3A3CF3DC0221B54FC0F0F34E3A5ED58A56CE6D75B8326F8C008F6C2E` and Git blob `ae38c8cd7962f32a341924fa7f4fc476dbab6292`. It adds zero definitions and integrates exactly `security.mpin.step_up_consumed` and `security.mpin.step_up_reconciliation_required`, advancing only the local disposable final state from 23 to 25 integrations and semantic signature `82bd918f68377090324c3a15da210769` to `a2adfe352aaf6e3fa55347b284655714`. Shared TEST totals are 172/164/8/158/25/139/133/6 (total/Planned/Deferred/writable/integrated/Planned-unintegrated/writable-unintegrated/Operations); all relevant fixture tables remain empty and RLS remains enabled. Fresh/sequential convergence, valid reapplication, corrupt-state rejection, ACL/RLS, one-use/concurrency, negative binding/expiry/generation/session/device/access-proof cases, rollback, ambiguous-commit classification, sensitive-data guards, and real PostgreSQL success paths through all six protected routes passed on isolated loopback PostgreSQL 16: complete backend 878 passed with zero skips and two unrelated deprecation warnings. Frontend Node/static/responsive/accessibility tests passed 77/77; changed-file ESLint passed; the 735-module production build passed with the existing chunk-size advisory. Canonical `supabase/schema.sql` SHA-256 is `0D60D9EC3BD80697CB73E470F9C44126A9D9A014122BE3B07622F4885472C9DF` (Git blob `3a6af7251ba4a8af55c67a1848768e74ddec693b`).
14. **Phase 1B-2C4 — user-initiated logout-all revocation (Implemented in main and verified on authorized shared TEST; not deployed)** — implementation commit `01076f7921ef4b3202cd4502398098d2cece4484` and closed-harness commit `2f2d58f742f10d3b5d5679de4595bcd4db473018` provide one authenticated CSRF-backed route and one canonical orchestration owner. Active eligible unlocked MPIN requires the honest `security.logout_all` / `account_security` action descriptor and exact session/device/generation/request-bound one-use proof; no/locked/ineligible MPIN uses current-password verification outside every PostgreSQL transaction and pooled connection. The final transaction revalidates current durable authority and account/confirmation state, then locks the same-user active session population by `session_id` and active trusted-device population by `id` while holding the user lock, revokes exactly those rows, emits one `security.session.revoked` and one `security.trusted_device.removed` per newly changed row with `result_code=logout_all`, consumes MPIN evidence when applicable, and writes the existing `security.logout.completed` envelope. Event failure rolls back proof consumption and every revocation. The shared Security page adds one accessible responsive danger action with explicit confirmation, canonical StepUpProvider routing, memory-only masked password recovery, no network retry loop, complete local CSRF/presentation cleanup, and full-login navigation. No migration or catalog/projection change was required: totals remain 172/164/8/158/25/139/133/6 and semantic signature remains `a2adfe352aaf6e3fa55347b284655714`. Prior local verification passed focused logout-all 6/6, complete backend 904 with one expected skip, disconnected mode 408 with 497 expected database skips, frontend Node/static 81/81, changed-file ESLint, production build, compileall, and safety scans. The new ownership suite passed 8 tests with one explicit shared gate skipped locally. Its single authorized shared-TEST matrix then passed MPIN and deterministic-password logout-all, stale/expired/rotated/mismatched/replayed authorization failure, exact per-row evidence, event-failure rollback, current-session and cookie contracts, and unchanged foreign/revoked/expired controls with zero external provider calls. It created and removed exactly 4 users, 9 trusted devices, 9 sessions, 1 credential, 3 authorizations, and 11 events; every relevant count and fingerprint returned to the exact pre-probe state (19 users, 31 trusted devices, and zero sessions, credentials, authorizations, or events). Migration `20260801220000_mpin_step_up_high_risk_integration.sql` was not reapplied; no production access, SQL application, deployment, PR, list/revoke-one control, expiry processing, OTP/SMS/GPS/risk/notification work, or non-user mass revocation occurred.
15. **Phase 1B-2C6 — active sessions and trusted devices management (Implemented on feature branch; not deployed)** — one owner-scoped service lists safe active session/device projections and revokes exactly one non-current session or one non-current trusted device. Device revocation atomically cascades `device_removed` session revocations, locks in session → user → trusted-device order, checks exact affected-row counts, and writes only the existing `security.session.revoked` and `security.trusted_device.removed` contracts. Management references are opaque `session_`/`device_` references; raw tokens, digests, IP addresses, and user-agent values are not returned or stored. The Security page adds responsive Active Sessions and Trusted Devices sections, reliable current markers, confirmation, stale-state handling, and canonical current-session logout. No migration or catalog change is required; shared TEST, production, deployment, merge, PR, and complete-suite verification remain out of scope until separately authorized.
13. **Communication-channel and dead organization-portal corrections (Merged into main; no database application required; not deployed)** — main fast-forwarded from `37f124325a22f7fc857da885d0a2a9a3f246f959` through the three linear `fix/remove-sms-channel-policy` commits to feature SHA `bdf9782db326fa89d2c3b312605f57cfcba02819`, with zero merge commits. The obsolete settings API preference and transporter SMS control are removed, legacy SMS preference keys are omitted from API projections and later settings saves, and no SMS provider/configuration/dependency/runtime owner remains. The unowned `/api/org/*` and `/api/organization/*` callers, fake organization credential/session state, and unreachable prototype pages are removed; every `/org/*` route now fails closed through one owner and directs real companies/service seekers to the canonical account flow. No SMS event definition or database projection row existed, no `220000` migration was created, and catalog 172/164/8/158/23/141/135/6 plus signature `82bd918f68377090324c3a15da210769` remain unchanged. Legitimate phone/CNIC/contact data, provider-neutral email acceptance, canonical company authentication, and public partner contact email remain unchanged. Existing password-reset/password-change Email OTP is distinguished from Planned verified-email signup, untrusted-device login, locked-MPIN recovery, external notification delivery, and the dedicated organization backend. No shared-TEST SQL or production access occurred.
14. **Phase 1B-2 remaining runtime event integration (Planned)** — attach canonical writers only through separately reviewed domain-owner changes.
12. **Security** — observation first; risk shadow mode and alerts/cases; later Email OTP after provider/domain readiness. Durable current-session runtime, secure MPIN/runtime access locking, one-shot reset claims, trusted genuine-session activity, and the bounded step-up authorization foundation are implemented in main and authorized shared TEST, with no production deployment. The six-operation Category A consumption/frontend owner and user-initiated logout-all are implemented in main and authorized shared TEST. Password/account/admin/incident mass revocation, expiry-event processing, and device/session management remain later dedicated security workstreams.
13. **One-Time Business Audit** — attach same-transaction events to canonical One-Time services and prove idempotency/lock behavior.
14. **General Analytics** — replace broad tracker with consent-aware, allowlisted, idempotent analytics.
15. **Operational Monitoring** — structured errors/latency/health/provider/scheduler/release telemetry and incident lifecycle.
16. **Dashboards and retention** — device/session and administrator security dashboards, KPI/funnel views, deletion/aggregation jobs, access audits.
17. **Final audit and freeze** — drift, privilege, retention, volume, performance, privacy, and integrity review.
18. **GPS tracking architecture afterward** — separate bounded architecture after the event foundations are stable.

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
- 15 logical data objects in main/shared TEST: two event tables, `user_sessions`, zero-row `mpin_credentials`, and zero-row `mpin_step_up_authorizations` implemented; 10 remain Not implemented.

The catalog contains 164 Planned-lifecycle events plus 8 Deferred QR-payment events (172 combined), of which 158 are writable. Main and authorized shared TEST have exactly 25 integrated Planned security definitions, 139 Planned-unintegrated definitions, and 133 writable-unintegrated definitions. The six Operations definitions remain non-writable and unintegrated. Phase 1B-2C4 adds no definition, integration, projection, schema, or migration change. The current semantic signature is `a2adfe352aaf6e3fa55347b284655714`; the Phase 1B-2C3C1 pre-rollout shared-TEST signature was `b57a59369062e678a7b269cd61d4e01e`. No production deployment occurred.
