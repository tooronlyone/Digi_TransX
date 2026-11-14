# Tracking Remaining Work Notes

> **27 October 2026 clarification:** these are tracking/event/operations plans, not a count of unfixed application bugs. Current implemented business rules, credential revocation and frontend authority must not be treated as absent merely because a corresponding canonical-event integration is still planned. Use [the current audit ledger](../AUDIT_LEDGER.md) for confirmed remaining defects; no deployment or tracking phase is declared complete by this review.

This is a living planning note for the tracking/security/analytics/operations work that is still not fully complete. It preserves the remaining areas from Hassan's planning notes so future implementation can continue in bounded phases without losing context.

This file is not runtime authority. `docs/TRACKING_SECURITY_AUDIT_REGISTRY.md` and the code/database state remain authoritative. Update the registry in the same commit when any item here becomes implemented.

## Current High-Level Remaining Areas

- Business audit runtime integrations
- Risk engine
- GPS login/location security
- Email/Gmail OTP security challenges
- Security dashboards and admin security cases
- Operational monitoring, performance, errors, health, incidents, and release monitoring
- Production deployment and deployment audit
- Trip live-GPS architecture
- Deferred QR events

## Business Audit

Status: mostly remaining.

Purpose: connect canonical business-audit evidence to real domain owners without weakening the already-built security foundation.

Remaining examples:

- One-Time order creation and changes
- Bid submission, withdrawal, selection, and rejection evidence
- Checkout and payment lifecycle business evidence
- Wallet credits, debits, holds, releases, refunds, and balance integrity evidence
- Commission policy and commission calculation evidence
- Terms acceptance/change evidence
- Trip start, delivery, completion, client confirmation, timeout, dispute, and admin resolution evidence
- Chat/review business evidence where appropriate
- Truck, driver, and transporter operations evidence
- Matching eligibility and matching decision evidence
- Business profile/preferences evidence
- Notification delivery/read evidence
- Scheduler/worker business actions
- Agreemental V2 tracking only after the archived workflow in `Future/` is redesigned and separately reviewed

Process:

1. Pick one domain owner at a time, such as wallet, checkout, bids, trip lifecycle, or disputes.
2. Inspect the current route/service/transaction owner before adding any event.
3. Confirm the canonical event already exists, is writable, and is allowed only when integrated.
4. Write events inside the same transaction as the authoritative domain mutation.
5. Keep provider I/O outside database locks where required, and reconcile ambiguous provider finalization without replay.
6. Add PostgreSQL-backed tests for success, rollback, idempotency, privacy, cross-user rejection, and duplicate-event rejection.
7. Update `docs/TRACKING_SECURITY_AUDIT_REGISTRY.md` in the same commit.
8. Verify on disposable PostgreSQL first; shared TEST only when explicitly authorized.

## Risk Engine

Status: not implemented.

Purpose: evaluate suspicious login/account behavior and produce challenge/deny/allow decisions without leaking identity or storing sensitive raw data.

Remaining:

- Login risk evaluation
- New-location detection
- New-device detection
- Suspicious IP/device behavior detection
- Risk score and score versioning
- Allow/challenge/deny decision owner
- Security challenge result owner
- Security case creation for high-risk activity
- Risk rollout state, likely disabled/shadow before enforcement

Process:

1. Define a disabled/shadow risk engine first; do not block users in the first implementation.
2. Use pseudonymous user/session/device references, not raw IP/GPS/user-agent strings in canonical metadata.
3. Keep the scoring version explicit so future score changes are auditable.
4. Separate risk evaluation from challenge delivery.
5. Add tests proving ordinary login still works, risk metadata is sanitized, and deny/challenge behavior is disabled until explicitly enabled.
6. Only later connect risk decisions to Email/Gmail OTP, GPS verification, or admin cases.

## GPS Login And Location Security

Status: not implemented.

Purpose: use GPS/location as security evidence for signup/login or high-risk flows, separate from trip live tracking.

Remaining:

- Signup/login GPS permission request flow
- GPS result recording
- GPS denied/unavailable handling
- Approximate login-location evidence
- New-location comparison
- Stronger verification path when GPS is unavailable or suspicious
- Privacy review for exact/approximate location retention

Process:

1. Treat GPS login security as a separate bounded phase from trip live GPS.
2. Decide whether stored evidence is exact, coarse, or referenced/fingerprinted only.
3. Never store exact GPS in generic analytics or operational logs.
4. Add frontend permission handling with clear fallback.
5. Add backend route/service that validates purpose, user/session/device, and CSRF.
6. Connect to risk engine only after risk engine has a stable disabled/shadow owner.

## Email/Gmail OTP Security Challenges

Status: partially related infrastructure exists, but mandatory security-challenge Email/Gmail OTP is not implemented.

Already related:

- Password reset/change OTP exists.
- OTP consumption has been hardened to be row-locked and one-shot.
- Provider details are sanitized in existing flows.
- OTP delivery planning is email/Gmail-only.

Remaining:

- Mandatory full-login Email/Gmail OTP challenge
- Untrusted-device login challenge
- Locked-MPIN recovery challenge
- Delivery ledger/provider abstraction
- Email/Gmail OTP success/failure canonical evidence
- Resend/cooldown/abuse controls for security OTP
- Device/session binding of challenge where required

Process:

1. Reuse the one-shot OTP consumption pattern, but keep security challenges separate from password reset/change.
2. Store only OTP hashes/digests, never raw OTPs.
3. Keep provider payloads and recipient details out of canonical metadata.
4. Add resend and cooldown controls before enabling mandatory challenge flows.
5. Add tests for replay, race, expiry, wrong code, provider failure, and ambiguous finalization.

## Security Dashboards And Admin Cases

Status: mostly not implemented. The 2C6 feature branch has owner-scoped active sessions/trusted devices management locally verified, but it is not integrated into `main`, shared TEST, or production yet.

Remaining:

- User login history view
- Active sessions and trusted devices dashboard integration to `main`
- Revoke device/session controls integration and shared TEST verification
- Suspicious login warnings
- Admin security cases
- Admin search/filter over security events
- Risk decision visibility
- Incident/security case lifecycle

Process:

1. Finish 2C6 integration separately if authorized: review, shared TEST verification, then main integration.
2. Keep user dashboard owner-scoped; never expose raw session tokens, device tokens, digests, IP addresses, or raw user-agent strings.
3. Add admin dashboards only after role/permission boundaries are reviewed.
4. Add search/filter on references and safe metadata, not raw sensitive fields.

## Operational Monitoring

Status: mostly planned, not runtime-integrated.

Purpose: monitor technical health separately from security, business audit, and general analytics.

Planned layers:

- Logs: sanitized technical occurrence
- Metrics: counts, rates, latency, health
- Traces: request path across frontend, API, database, and provider
- Incidents: confirmed operational problem and resolution

Planned namespaces:

- `operational.frontend.*`
- `operational.api.*`
- `operational.database.*`
- `operational.provider.*`
- `operational.webhook.*`
- `operational.incident.*`

Frontend monitoring remaining:

- Runtime/React error capture
- Unhandled promise rejection capture
- Route/chunk load failure capture
- API request failure capture
- Resource load failure capture
- Offline/recovered state
- Web Vitals and route performance metrics

Initial frontend targets:

- LCP <= 2.5 seconds
- INP <= 200 ms
- CLS <= 0.1
- Route transition preferably <= 1 second
- Critical modal open preferably <= 500 ms after data
- UI crash-free sessions >= 99.5% initial target

API/backend monitoring remaining:

- Unexpected 5xx
- Slow endpoint thresholds
- Rate limits
- Dependency failures
- Validation-failure spikes
- Unexpected transaction rollbacks
- Recovery events

Request optimization and loading UX remaining:

- Reduce startup/loading request volume after login.
- Audit and deduplicate repeated frontend requests, especially repeated `/api/chat/threads` calls seen during local manual testing.
- Add safe client-side caching for stable/current-user resources where privacy and freshness allow it.
- Organize startup requests so critical secure-access checks finish first and non-critical widgets load later.
- Parallelize independent requests deliberately, while avoiding duplicate calls from multiple components mounting at once.
- Add request cancellation/debounce where navigation or repeated mounting triggers stale requests.
- Improve the "Checking secure access" experience with clearer staged loading and bounded timeout/retry messaging.
- Measure perceived login-to-dashboard time separately from backend API duration.
- Account for remote Supabase Auth/DB latency in local/shared TEST expectations.
- Keep production optimization separate from local hardware assumptions; better hardware may help slightly, but remote dependency latency and duplicate requests are the main current suspects.
- Handle or quiet missing AI assistant startup endpoints so they do not create noisy 404/405 logs:
  - `POST /api/ai-assistant/preferences` currently returns 405.
  - `GET /api/ai-assistant/capabilities` currently returns 404.

Initial API targets:

- Normal reads p95 <= 500 ms
- Normal DB mutations p95 <= 1 second
- Matching/available orders p95 <= 1 second
- Checkout internal processing p95 <= 1.5 seconds excluding provider
- Webhook acknowledgement preferably <= 5 seconds
- Health endpoint <= 250 ms

Database monitoring remaining:

- Slow query fingerprint
- Connection-pool saturation
- Connection failure
- Deadlock and lock timeout
- Transaction rollback
- Constraint violation spike
- RLS denial spike
- Long-running transaction
- Storage/size growth
- Migration failure
- Replica/backup issue when hosting support exists

Provider/webhook monitoring remaining:

- Email/Gmail OTP
- Card payment
- Raast QR
- Storage
- Map/geocoding
- Future GPS vendors
- Push notifications
- Webhook signature results
- Duplicate webhook detection
- Amount/status mismatch detection

Scheduler monitoring remaining:

- Last successful run
- Next expected run
- Run duration
- Consecutive failures
- Rows examined/changed
- Lock acquisition
- Duplicate owner detection
- Scheduler disabled status
- Worker heartbeat

Health endpoint plan:

- `/health/live`: fast liveness only; no detailed DB/provider checks.
- `/health/ready`: readiness for serving requests; database, schema capability/version, config, migration compatibility, essential dependency readiness.
- Restricted internal health endpoint: DB pool, scheduler status, provider health, queue/backlog, latest successful jobs, release version.

Incident severity plan:

- P0 Critical: financial duplication, data corruption, security breach.
- P1 High: login, checkout, payout, or trip lifecycle unavailable.
- P2 Medium: degraded feature or intermittent provider.
- P3 Low: minor UI/performance regression.

Incident lifecycle plan:

- `incident.opened`
- `incident.acknowledged`
- `incident.mitigated`
- `incident.resolved`
- `incident.reopened`
- `incident.postmortem_completed`

Release monitoring remaining:

- Git SHA
- Environment
- Deployment timestamp
- Migration versions
- Build version
- Error rate before/after
- API latency before/after
- Frontend vitals before/after
- Rollback status
- Deployer identity

Privacy and volume rules:

- Do not store request/response bodies by default.
- Do not store passwords, OTPs, PAN/CVC, authorization headers, provider credentials, or raw tokens.
- Use route templates, fingerprints, safe references, and categories.
- Financial/security integrity errors are 100%.
- Unhandled frontend/backend errors are 100%.
- Provider/webhook failures are 100%.
- Routine successful API requests are aggregated or sampled.
- Duplicate bursts are grouped.
- P0 evidence must not be dropped by sampling.

Process:

1. Inspect existing Flask logging, error handlers, `/api/track`, `ActivityTracker`, scheduler logs, provider wrappers, health routes, frontend error boundaries, build/source-map settings, deployment config, and Supabase monitoring capability.
2. Do not add a second competing logger/tracker blindly.
3. Introduce health endpoints first because they are low-volume and bounded.
4. Add API error/latency instrumentation next with body-free sanitized metadata.
5. Audit login/dashboard startup requests and remove duplicate or non-critical blocking calls.
6. Add frontend error boundary and Web Vitals collection with sampling.
7. Add provider/webhook monitoring around existing provider abstraction points.
8. Add scheduler heartbeat/status monitoring.
9. Add incident records and release monitoring after basic health/error telemetry exists.
10. Update the registry in the same commit.

## Production Deployment

Status: not performed.

Remaining:

- Deployment process definition
- Environment readiness
- Migration compatibility gate
- Production secrets/config review
- Release audit event/record
- Rollback plan
- Post-release monitoring
- Production shared dashboard/health verification

Process:

1. Treat Git merge as not equal to deployment.
2. Define deployment command/process and approval boundary.
3. Verify migrations and config compatibility before deployment.
4. Record release SHA, migration versions, deployer identity, and timestamp.
5. Monitor health, errors, latency, and critical flows after deployment.
6. Keep production data inspection minimal, authorized, and privacy-safe.

## Trip Live-GPS Architecture

Status: not implemented; separate from canonical audit/security tracking.

Remaining:

- Driver tracking URL/token
- Mobile GPS permission
- Location heartbeat
- Stale-location detection
- Trip-bound device authorization
- Physical GPS provider integration
- Falcon or other GPS provider API integration
- GPS device credentials/token security
- Live map
- Route deviation alerts
- Future Digi_TransX mobile app integration

Process:

1. Keep trip live GPS separate from login GPS security and general analytics.
2. Define trip-bound authorization and token lifecycle first.
3. Decide retention and precision rules for exact GPS.
4. Add mobile/web heartbeat with stale-location detection.
5. Add live map only after backend heartbeat contract is stable.
6. Add physical provider integration behind a provider abstraction.
7. Add route deviation alerts after route/waypoint rules are defined.
8. Add audit/business events only for authoritative trip lifecycle facts, not every high-volume GPS ping.

## Deferred QR

Status: deferred.

Notes:

- Deferred QR events remain separate until QR provider/payment workflow is ready.
- OTP delivery remains email/Gmail-only.

## Suggested Future Implementation Order

1. Finish or integrate Phase 1B-2C6 active sessions/trusted devices management if authorized.
2. Operational health endpoints and minimal sanitized API error/latency monitoring.
3. Login/dashboard startup request optimization, safe caching, duplicate-call cleanup, and "Checking secure access" UX improvement.
4. Security dashboard/user session history.
5. Email/Gmail OTP security challenge foundation.
6. Risk engine in disabled/shadow mode.
7. GPS login/location security.
8. Business audit events domain by domain.
9. Provider/webhook monitoring.
10. Scheduler monitoring.
11. Incident and release monitoring.
12. Production deployment process and audit.
13. Trip live-GPS architecture.
14. Deferred QR only when provider/workflow decisions exist.
