# Digi_TransX security and reliability remediation — 24 October 2026

This record describes the fixes requested after the original 75-finding audit.
It covers the owner's 20 priority items and closely related authorization,
reservation, numeric and authentication failures discovered while validating
them. It does not declare the remaining audit findings resolved or assign an
untested new system health score.

The [current PROJECT_AUDIT_REPORT.md](../PROJECT_AUDIT_REPORT.md) was reconciled
on 27 October and now lists remaining findings only. This dated record retains
the 24 October implementation and rollout evidence; use the
[27 October verification receipt](audit-evidence/2026-10-27/README.md) for the latest local status. Existing unrelated working-tree changes were
retained. No Git commit, production deployment or real payment was performed.

## 1. Database changes applied to the authorized test project

The owner explicitly confirmed that Supabase project `fysupkvuvhvtowbfgoev` is
for testing and contains no real customer data. Four forward migrations were
applied to that project. Already-applied files were kept byte-for-byte unchanged;
follow-up improvements use subsequent migrations.

| Migration | Result |
|---|---|
| `20261024010000_database_authorization_hardening.sql` | Safe Auth signup trigger; protected identity/role writes; RLS and browser ACL hardening; chat membership; nonrecursive agreements; hire-contract convergence; durable credential generation/pending gate |
| `20261024020000_marketplace_financial_controls.sql` | Backend-only HMAC delivery challenges, checkout idempotency constraints and wallet money invariants; invalidate exposed legacy plaintext OTPs |
| `20261024030000_private_operational_read_surfaces.sql` | Backend-only vehicle/tracker, agreement truck, RFQ and dependent RFQ-bid reads, including explicit column grants |
| `20261024040000_validate_wallet_money_invariants.sql` | Validate all existing wallets without rewriting their balances or reserves |

The canonical [schema.sql](../supabase/schema.sql) now includes the October
feature baseline and these corrections, so a fresh install does not depend on
manually created driver, fuel, marketplace or hire-contract tables.

Remote post-application evidence:

- **68 public tables, all 68 with RLS enabled; 112 RLS policies.** RLS coverage
  alone is not proof of authorization correctness; explicit role probes were
  also performed on the changed surfaces.
- **19 backend-only tables** deny browser-role SELECT/INSERT/UPDATE/DELETE while
  retaining explicit service-role access. Local service-role tests also work
  without BYPASSRLS.
- Both `anon` and `authenticated` receive PostgreSQL **42501** for direct role
  changes, private driver/OTP reads and the additional private operational reads.
- Agreement participant reads complete without recursive-policy errors.
- Existing table row counts and user `id/auth_id/role/legacy_role` bindings were
  preserved. **One exposed legacy delivery OTP was deliberately invalidated**;
  its buyer must request a new challenge. No account was relinked or promoted.
- Wallet preflight found zero violating legacy rows. The money constraint is
  now `convalidated=true`; hashes of wallet identities, balances, locked amounts
  and minimum requirements were unchanged.

Migration hashes, before/after counts and role results are in the versionable
[rollout receipt](audit-evidence/2026-10-24/database-hardening-rollout.json) and
[database verification record](audit-evidence/2026-10-24/database-verification.md).
They contain no credentials or application row contents. The configured pooler
uses session port 5432; the password-operation guard nevertheless uses a
transaction-scoped advisory lock so it also works with transaction pooling.

## 2. Requested issue-by-issue implementation status

| Audit ID | Implemented correction | Main source / proof |
|---|---|---|
| DB-01 | Auth metadata cannot select an admin role. New signup cannot implicitly claim an existing profile by matching an email. Trusted admin provisioning performs explicit server promotion. | First migration; `backend/scripts/create_admin.py`; DB signup/identity tests |
| DB-02 | Browser table and column grants cannot edit authorization-sensitive user/profile state. Flask profile writes use an explicit field list. | First migration; browser role/column-grant probes |
| DB-03 | Missing RLS and direct-client privileges on the nine operational tables and related POS/workflow surfaces are closed. | First migration; DB fresh/upgrade/replay/role tests |
| DB-05 | Chat INSERT requires the authenticated identity to be the sender and a member of the target thread. | First migration; unrelated-thread insert denial |
| AUTH-04 | Password reset/change revokes all Digi_TransX sessions and devices before provider I/O. Credential generation and pending gates reject stale login proofs; unexpected provider outcomes remain closed pending verification. | `backend/auth/credential_changes.py`, auth/profile routes; auth/inventory and signup-race tests |
| FIN-01 | Dummy card processing requires an explicit test environment, or local/development plus explicit opt-in. Unknown/staging/production configurations cannot select it; unconfirmed adapter responses never fund a wallet. | `backend/shared/payments.py`; financial provider tests |
| FIN-02 | Generic/seller order serializers never contain delivery OTPs. HMAC challenges live in a backend-only table; only the owning buyer receives/reissues a plaintext challenge. | `backend/marketplace/routes.py`, `service.py`; second migration; buyer/seller/secret tests |
| FIN-03 | Marketplace hold release, buyer debit and seller credit are checked in one transaction; any failure raises and rolls back the whole settlement. | `backend/marketplace/service.py`; failed-debit and rollback tests |
| FIN-05 | Wallet helpers refresh rows under `FOR UPDATE`, mutate with SQL arithmetic and RETURNING, reject spending reservations and acquire multiple wallet locks in a stable order. First creation uses ON CONFLICT. | `backend/wallet/helpers.py`, marketplace service; real concurrent withdrawal/checkout/creation tests |
| FIN-15 | Dispensing locks an owned active pump, uses its stored rate and conditionally decrements sufficient stock. Receipt and stock changes commit together; insufficient stock returns 409. | `backend/fuelstation/routes.py`; two simultaneous 7-liter sales against 10 liters commit exactly one |
| FIN-17 | POS quantities for duplicate product IDs are merged before stock validation; products lock in ID order. A unique item line is persisted once. Each line rounds HALF_UP before totals are added. | `backend/shopkeeper/routes.py`; merged-stock and receipt-total tests |
| DB-07 | Missing hire-contract installations are created; the manually created remote shape is safely converged. Driver profile locking serializes competing acceptances. | First migration; `backend/driver/routes.py`; fresh/manual-shape tests |
| DB-06 | Agreement participant policy checks use a controlled security-definer bridge with a fixed search path and restricted execution. | First migration; participant reads plus recursion regressions |
| BE-04 | Tanker matching requires finite certified volume and payload limits independently. Tonnes are never substituted for CBM. | `backend/orders/helpers.py`; `test_location_eligibility.py` |
| BE-03 | Non-finite input is rejected at corrected shipment, truck/agreement, wallet/marketplace, POS, pump, GPS, hire and driver fuel boundaries. Fixed-scale/storage-bound checks additionally protect corrected financial, inventory and fuel-log fields. | `backend/shared/validation.py` and callers; numeric, location and financial tests |
| FE-001 | Every receipt string interpolated into HTML is escaped, including customer, shop, product, receipt and city values. The print window does not retain an opener. | `frontend-react/src/pages/shopkeeper/receiptPrinting.js`; executable hostile receipt tests |
| FE-002 | Marketplace mutations use the common `apiSend` CSRF transport. Checkout retries retain an account/payload-specific idempotency key. | `marketplaceApi.js`, marketplace pages; rendered checkout/header/retry tests |
| FE-003 | Driver and shared logout send CSRF, await authoritative server success, clear shared auth state and handle revocation/network failure visibly. | `frontend-react/src/auth/logout.js`, DriverLayout; rendered logout tests |
| FE-014 | AI history, memory and preferences are keyed by verified user identity. Identity changes tear down the assistant and cancel late response/microphone work. Unowned legacy storage is not imported. | AI components/library; account-switch and late-response tests |
| FE-016 | Vite disables recursive public copying and serves/emits only the two approved static SVG URLs. Imported assets continue through Vite's module graph. | `vite.config.js`, `build/staticAssets.mjs`; asset tests and production build |

The finite-number correction is scoped to these verified boundaries. It is not
a claim that every unrelated route now accepts every malformed JSON type safely.

## 3. Related safeguards completed with these fixes

- Removed the worker-local authentication authority cache. Each protected request
  checks current durable session/device/user state, so another worker's revocation
  is observed immediately. Access-lock persistence now stays inside the checked-out
  database context rather than using a returned connection.
- Logout returns 503 when revocation or its mandatory event transaction fails;
  it retains local authentication for a visible retry rather than claiming
  successful server revocation. Authentication database outages also return 503
  without clearing cookies; they are not reported as an expired 401 session.
- Delayed signup cannot issue a session after an account's password generation
  changes, becomes pending or is blocked. Signup compensation refuses to delete
  an account subsequently claimed by a reset, login or trusted device.
- Session issuance independently rejects pending password changes, and protected
  requests reject an unexpectedly active session for a pending account.
- Generic wallet lock/unlock APIs return 403: reservations must come from an
  authorized resource workflow. Withdrawal capacity protects holds and the
  transporter security floor. Admin withdrawal approval locks the request and
  wallet and cannot approve it twice.
- Production withdrawals fail before mutation until a real payout executor is
  implemented. Explicit test withdrawals are labelled simulated and do not claim
  that a bank transfer occurred.
- Marketplace seller actions require the shopkeeper role. Checkout prices come
  from owned/locked inventory, not the browser. Delivery challenge lifetime is
  20 minutes, five wrong attempts exhaust a challenge and reissue has a 60-second
  cooldown. Verification checks the predecessor state and consumes once under
  lock; settlement cannot be replayed.
- Fuel POS requires an owned active pump and shows the server's stored rate.
  Cash and an externally processed station-terminal card payment are the supported
  recording modes. Unsupported wallet/voucher payment labels were removed.
- Frontend POS arithmetic uses exact scaled values and the same line-rounding
  rule as the server; an exact paid total such as 0.30 is not rejected by floating
  point comparison.
- The password-change UI ends shared authentication and carries the server's
  success/reconciliation message to the login page. OTP resend supplies the
  current password and surfaces server errors. Login preserves password whitespace
  exactly, closing the related FE-008 mismatch with password reset.
- Two tests that previously imported the global application, used hardcoded real
  IDs and could send email were converted to disposable accounts/databases and
  fake SMTP. They now exercise the actual authenticated endpoints safely.

## 4. Password provider failure and operator recovery

Successful changes clear authentication cookies and require a fresh sign-in on
every device. Revocation commits before the external provider call. A structured
terminal provider rejection can clear the pending gate, but never restores old
sessions/devices. A transport timeout, 5xx, malformed response, process loss or
database finalization failure leaves the gate closed. A new OTP alone cannot
overwrite an operation whose external outcome is unknown.

For a pending account, an authorized operator must inspect Supabase Auth operation
or audit evidence and establish that the original password write has reached a
terminal outcome and no delayed/in-flight write remains. Merely waiting, seeing
an exception, or issuing another OTP does not establish that fact. Identify the
exact user and current `credentials_version`, and run the trusted server CLI
[reconcile_password_change.py](../backend/scripts/reconcile_password_change.py)
with its required `--user-id`, `--credentials-version`, `--operator-reference`
and `--provider-operation-terminal` arguments. The last flag records the
operator's explicit attestation; the CLI cannot infer external completion.

The command refuses a stale generation, a missing/prematurely reopened gate or
unexpected active authentication rows. It clears only the confirmed generation,
preserves revocation and writes an audit row in the same transaction. The audit
stores a digest of the non-secret ticket/reference. It uses the existing server
admin audit trail; the repository's planned canonical admin event is not silently
enabled or misrepresented as integrated. The user can then sign in with the
provider's current password or request a new reset. Restrict this CLI and database
credentials to trusted operators.

## 5. Validation and practical limits

The database hardening suite passed **64/64** on real disposable PostgreSQL.
The frontend's Node suites passed **97/97**, and rendered component suites passed
**34/34**, including seven password-lifecycle regressions. The final frontend
production build completed successfully in 18.73 seconds: **14 files,
3,014,482 bytes** in `dist`; it contains no copied `node_modules`. Targeted lint
checks report zero errors; the final lifecycle selection retains one existing
dependency warning. The previous approximately 148 MiB copied dependency tree
is no longer shipped. The large JavaScript chunk and Browserslist warnings remain;
this is not a claim of a clean whole-repository lint run. See the
[frontend verification record](audit-evidence/2026-10-24/frontend-verification.txt).

The final focused backend selection passed **143/143** across auth/inventory,
location/vehicle eligibility, signup credential races and financial marketplace
tests. Four subsequent auth-outage/logout/cookie checks passed after the final
503-versus-401 handling change. The existing three auth suites ran **115 passed,
one obsolete text assertion failed**; the corrected reconciliation assertion and
provider-failure case passed on rerun, and the corrected logout failure/retry
contract also passed. There are no unresolved failures in that scoped auth check.
The isolated financial and existing payment/route/commission selection previously
passed **252 tests**. These are overlapping selections, not additive counts of
unique coverage. The [focused log](audit-evidence/2026-10-24/focused-regression.txt)
and [auth record](audit-evidence/2026-10-24/auth-regression.txt) retain their exact
results. Final all-backend syntax parsing covered **161 Python files with zero
syntax errors**, and `git diff --check` passed.

The broad backend run completed **1,124 passed, 5 failed and 3 skipped** in
1,448.74 seconds. All five failures were investigated and their current
counterparts passed together: **5/5 in 22.30 seconds**. They concerned obsolete
password-recovery/replay expectations, response wording and the exact static
emitter inventory; the corrections preserve the new revocation/reconciliation
contracts and strengthen the assertions. The three skips are explicit shared-
project opt-in probes, kept separate from the isolated run; they are not counted
as passes. The local versions of their matrices and the separate Supabase
migration/role probes were exercised. A second complete broad run was not
performed after those focused corrections. Exact IDs, causes, reruns and skip
reasons are retained in the [backend regression receipt](audit-evidence/2026-10-24/backend-regression-verification.md).

The synthetic PostgreSQL test service on port 15477 was stopped after all checks.
Automatic approval review blocked recursive deletion of its temporary local data
directory with the stated reason `blocked by policy`, so the stopped directory
`.codex-logs/db-hardening-pg` remains locally. No Supabase data or unrelated local
database service was removed. Application source checksums for the frozen tree
are recorded in [source-sha256.json](audit-evidence/2026-10-24/source-sha256.json).
The compact machine-readable result is [verification-summary.json](audit-evidence/2026-10-24/verification-summary.json).

All backend integration runs use synthetic disposable loopback databases and
fake external provider/SMTP boundaries. `SUPABASE_DB_URL` is deliberately invalid
inside the test process so a missed override cannot mutate the configured shared
Supabase project. Remote migration checks are separately scoped to the owner-
authorized test project. The local runner can disable durability settings for
speed; these runs prove locking/transaction behavior, not crash durability or
production performance.

The local `.env` explicitly marks this workspace `local` and opts into simulated
payments for testing. `.env.example` defaults the opt-in to false. Any deployed
environment must declare its actual environment; production/staging cannot select
the dummy adapter even by setting the opt-in flag. Secure checkout needs HTTPS
(or browser-recognized localhost) for Web Crypto.

Real gateway collection, bank payouts, webhook reconciliation, a double-entry
ledger, resource-specific escrow accounts, an outbox and the full dynamic pricing
redesign remain implementation work described in the original audit. The current
aggregate wallet hold model has been protected, not replaced with that ledger.
This remediation is not a claim of production readiness with real funds, proof
of every external physical handoff, or closure of all 75 original findings.
