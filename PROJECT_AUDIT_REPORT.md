# Digi_TransX current frontend/backend audit

Final reconciliation completed **28 October 2026 (Asia/Karachi)**; test execution and source evidence below were captured on 27 October.

Revalidated **27 October 2026 (Asia/Karachi)** against working-tree HEAD `47c8adba44185626fa45e993709560e5c40cc126` plus the owner's existing uncommitted changes. Only audit documentation/evidence was changed by this review; application fixes are separate work.

## Current status

**57 of the original 75 finding IDs have verified local corrections and have been removed from this report's active bug list.** Eighteen original IDs still have residual work; FIN-19 is merged into AUTH-06, leaving **17 distinct original finding groups**. This review adds **2 product findings** (REVIEW-001/002) and **2 test-maintenance blockers** (TEST-03/04).

The separate [integration/notification report](FINAL_REPORT.md) contains **10 additional product findings** and **3 explicit feature gaps**. Across these two reports there are **29 active product finding groups and 2 test blockers**. Feature gaps, optional cleanup and rejected suspicions are not included in that count. Old 28/100 health scoring and Critical issue totals have been removed rather than presented as current measurements.

This is a source and local-test audit. Remote Supabase policy state, deployed migrations, real card/payout execution, physical GPS/fuel evidence and production load were not reverified. A local source closure does not certify a deployed environment. Dated rollout/implementation receipts remain historical evidence.

The [revalidation receipt](docs/audit-evidence/2026-10-27/README.md) records closure rationale, commands, raw results, source hashes and practical limits. Existing user code edits were retained. Test traffic used an isolated loopback PostgreSQL cluster and synthetic fixtures.

## Active product findings

| ID | Severity | Current finding |
|---|---|---|
| [AUTH-05](#auth-05) | High | Password-reset issuance still has no resend admission limit |
| [AUTH-06](#auth-06) | Medium | Wrong JSON shapes still crash signup, profile, contact and wallet entry points |
| [BE-06](#be-06) | High | Agreement trip completion still races monthly distance accrual |
| [BE-07](#be-07) | High | Agreement billing still trusts transporter-supplied start/end coordinates |
| [BE-09](#be-09) | High | Every repeated late-fee sweep can charge the same overdue invoice again |
| [BE-10](#be-10) | High | Agreement due dates and service periods still exclude valid work |
| [BE-11](#be-11) | Medium | Agreement bids and active trips still use unprotected check-then-insert |
| [DB-09](#db-09) | Medium | Legacy database reads discard timestamp offsets |
| [DB-10](#db-10) | Medium | Legacy database reads still convert exact NUMERIC amounts to float |
| [DB-14](#db-14) | Medium | Concurrent first use can construct two database pools |
| [DB-15](#db-15) | Medium | Driver signup still fails on a random driver-code collision |
| [FE-012](#fe-012) | High | POS retry can repeat an already committed sale after receipt loading fails |
| [FE-011](#fe-011) | Medium | POS quantity controls cannot safely choose fractional units |
| [FE-015](#fe-015) | Medium | Wallet displays still misclassify signed debits and reservation movements |
| [FIN-21](#fin-21) | Medium | Legacy card refunds still omit the original provider charge reference |
| [PERF-01](#perf-01) | Medium | Available-order matching still reads an unbounded candidate set |
| [BE-12](#be-12) | Low | Authenticated contact tickets still lose user attribution |
| [REVIEW-001](#review-001) | Medium | Profile save truncates last names and ignores editable business fields |
| [REVIEW-002](#review-002) | Medium | Post Order has lost the expected order-mode and records navigation |

<a id="auth-05"></a>
### AUTH-05 — Password-reset issuance still has no resend admission limit

- **Severity:** High
- **Current source:** `backend/auth/routes.py:1055`; `backend/auth/routes.py:505`
- **Verification:** A local Flask probe submitted six consecutive reset requests for one synthetic account. All six returned 200 and invoked the mocked email and OTP writers. The only reset cooldown follows incorrect OTP attempts. Login likewise has no application admission limiter before provider/evidence work. Existing-account responses include masked_email, unlike nonexistent-account responses.
- **Impact:** Repeated requests can send mail and invalidate earlier challenges. Response differences disclose account existence. No live mailbox, provider load test or deployed edge-rate-limit inspection was performed.
- **Required correction:** Apply bounded account/source admission controls before provider/SMTP I/O, add resend cooldown, and return equivalent public responses.

<a id="auth-06"></a>
### AUTH-06 — Wrong JSON shapes still crash signup, profile, contact and wallet entry points

- **Severity:** Medium
- **Current source:** `backend/auth/helpers.py:748`; `backend/auth/routes.py:353`; `backend/profile/routes.py:36`; `backend/contact/routes.py:13`; `backend/wallet/routes.py:239`
- **Verification:** The original login scalar example is FIXED: login now checks string types. Residual counterexamples are signup JSON [1] and {"name":123}; both raise AttributeError in current validation after a mocked signup-start event. Wallet topup still calls data.get on a nonempty array inside open_db; profile/contact have equivalent shape assumptions. FIN-19 is merged here because its remaining financial JSON-shape failure has the same cause. Corrected NaN, POS-limit and GPS parsers are no longer listed as broken.
- **Impact:** Malformed requests can produce HTTP 500 rather than a validation response. The signup probe bypassed only the event writer; it did not create an account.
- **Required correction:** Validate an object and explicit field types before access/normalization. Preserve the finite-money and corrected login/reset validators.

<a id="be-06"></a>
### BE-06 — Agreement trip completion still races monthly distance accrual

- **Severity:** High
- **Current source:** `backend/agreements/routes.py:722`
- **Verification:** Source trace: the trip is read without a row lock, its completion UPDATE has only an ID predicate, and the monthly payment is read then overwritten without locking. Two requests can both observe in_progress; the second can reread the first accumulated total and add the same trip again. Different trips can overwrite a shared earlier total. Driver-allocation triggers do not lock the initial trip/payment reads.
- **Impact:** Monthly kilometers and client charges can be duplicated or lost. This exact interleaving was not restaged in the current run; the unsafe read/write sequence is still present.
- **Required correction:** Serialize the agreement truck, trip and billing row; make completion replay idempotent and update accrued distance once.

<a id="be-07"></a>
### BE-07 — Agreement billing still trusts transporter-supplied start/end coordinates

- **Severity:** High
- **Current source:** `backend/agreements/routes.py:662`; `backend/agreements/routes.py:722`; `backend/tracking/traccar.py:17`
- **Verification:** The provider remains disabled; no provider history makes end_trip fall back to haversine_km over request-supplied coordinates. That distance is added to the monthly payment. Browser driver-assignment/GPS hardening does not make this separate agreement billing route independently verified.
- **Impact:** A payee can claim distance without a verified journey. Physical travel and provider deployment were not tested.
- **Required correction:** Require independently validated trip evidence or an explicit client-approved distance before billable accrual; separate estimates from payable distance.

<a id="be-09"></a>
### BE-09 — Every repeated late-fee sweep can charge the same overdue invoice again

- **Severity:** High
- **Current source:** `backend/agreements/helpers.py:444`
- **Verification:** Real disposable PostgreSQL probe: an overdue failed invoice with insufficient principal funding was processed twice on the same day. Two penalty rows were inserted and the client balance decreased twice. The invoice row lock now prevents stale concurrent settlement, but there is still no date/period uniqueness or assessment cap.
- **Impact:** Retries or repeated manual runs charge extra penalties while the principal remains unpaid.
- **Required correction:** Introduce an approved penalty period/cap and unique assessment key; debit once per eligible assessment in the same transaction.

<a id="be-10"></a>
### BE-10 — Agreement due dates and service periods still exclude valid work

- **Severity:** High
- **Current source:** `backend/agreements/helpers.py:134`; `backend/agreements/routes.py:722`
- **Verification:** Current helper returns 2026-10-10 for a 2026-10-27 start, confirmed by executable probe. Finalization creates duration_months calendar-month invoices; end_trip only updates a matching pending/failed month. Paying an invoice early prevents later trips in that month accruing to it; a partial final month can have no matching invoice.
- **Impact:** Invoices can be overdue before service begins, and valid trip earnings can be omitted.
- **Required correction:** Define explicit service periods, accrue until closure and set due dates after closure. Reconcile existing paid/missing-period rows without silently repricing them.

<a id="be-11"></a>
### BE-11 — Agreement bids and active trips still use unprotected check-then-insert

- **Severity:** Medium
- **Current source:** `backend/agreements/routes.py:291`; `backend/agreements/routes.py:662`; `supabase/schema.sql:1334`; `supabase/schema.sql:1336`
- **Verification:** Agreement bid and trip routes check for an existing active row then insert without serializing the business key. Their schema indexes are non-unique. The one-time shipment bid case is FIXED by shipment_bids_one_active_transporter and shipment locking and is removed from this finding. Driver allocation uniqueness covers assignments, not agreement trip creation.
- **Impact:** Concurrent agreement requests can create duplicate active bids or in-progress trips. Source/constraint finding; the precise duplicate agreement-request race was not rerun.
- **Required correction:** Enforce active agreement business keys with appropriate uniqueness and consistent row locks; return a controlled conflict.

<a id="db-09"></a>
### DB-09 — Legacy database reads discard timestamp offsets

- **Severity:** Medium
- **Current source:** `backend/shared/db.py:77`; `backend/shared/db.py:132`
- **Verification:** Executable probe: 2026-10-27 12:00 UTC becomes 2026-10-27T12:00:00 through _normalize_value. Ordinary execute uses that conversion. execute_exact now preserves the offset, so new exact-ledger callers are excluded from the old blanket claim. APP_TIMEZONE is not applied by the pool/legacy normalizer.
- **Impact:** Browsers can interpret a UTC wall time as local time, shifting display by five hours in Pakistan; date-based legacy reports can use a different day boundary.
- **Required correction:** Return offset-bearing timestamps consistently and make business-day interpretation explicit across SQL and UI.

<a id="db-10"></a>
### DB-10 — Legacy database reads still convert exact NUMERIC amounts to float

- **Severity:** Medium
- **Current source:** `backend/shared/db.py:77`; `backend/shared/db.py:132`; `backend/wallet/routes.py:281`
- **Verification:** Executable probe: Decimal("9007199254740992.01") loses its cents through _normalize_value. execute_exact now keeps Decimal, and wallet finite/reservation constraints exist; those portions of the original finding are removed. Ordinary execute and legacy financial/API consumers still cross the float boundary.
- **Impact:** Exact amounts can be rounded before downstream formatting/calculation. This is a precision defect, not evidence of an observed real customer loss.
- **Required correction:** Use exact reads for financial logic and an explicit decimal-string/minor-unit serialization contract.

<a id="db-14"></a>
### DB-14 — Concurrent first use can construct two database pools

- **Severity:** Medium
- **Current source:** `backend/shared/db.py:57`
- **Verification:** A two-thread constructor/barrier probe created two distinct pool objects after both callers observed _pool is None. No real connection was used in that probe. There is no synchronization around singleton creation.
- **Impact:** Cold concurrent startup can lose ownership of one pool and exceed the intended connection budget.
- **Required correction:** Initialize the pool once at startup or protect lazy creation with a lock and explicit lifecycle ownership.

<a id="db-15"></a>
### DB-15 — Driver signup still fails on a random driver-code collision

- **Severity:** Medium
- **Current source:** `backend/auth/routes.py:279`; `supabase/schema.sql:3323`
- **Verification:** Signup chooses one random five-digit code. INSERT handles only ON CONFLICT(user_id), while unique_driver_id has its own uniqueness constraint; it does not retry a collision. This is a deterministic code/constraint path, not a production registration experiment.
- **Impact:** An otherwise valid driver signup can roll back merely because another driver received the same code.
- **Required correction:** Allocate from a sequence or retry bounded unique-code generation, with explicit namespace exhaustion handling.

<a id="fe-012"></a>
### FE-012 — POS retry can repeat an already committed sale after receipt loading fails

- **Severity:** High
- **Current source:** `frontend-react/src/pages/shopkeeper/POSPage.jsx:75`; `backend/shopkeeper/routes.py:198`
- **Verification:** Rendered counterexample: mocked sale POST commits successfully, the following receipt GET fails, the UI shows a retry error and enables Confirm with the same cart, and clicking it issues a second sale POST. The server already returns a complete sale; the extra GET is unnecessary. Neither this submission nor the backend sale insert has an idempotency contract.
- **Impact:** A receipt/network failure can lead to duplicate sales and stock deductions.
- **Required correction:** Immediately accept the committed POST result, make receipt refresh separate, and add a stable server-enforced sale idempotency key.

<a id="fe-011"></a>
### FE-011 — POS quantity controls cannot safely choose fractional units

- **Severity:** Medium
- **Current source:** `frontend-react/src/pages/shopkeeper/POSPage.jsx:49`; `frontend-react/src/pages/shopkeeper/POSPage.jsx:229`
- **Verification:** Rendered probe: selecting a product with 0.5 liters available posts quantity 1. Cart additions and +/- controls use increments of one; there is no direct fractional quantity input. Repeated product-card additions can also go from 1 to 2 when stock is 1.5.
- **Impact:** Valid partial-liter/kg/meter sales cannot be intentionally entered, and the UI can submit more than available stock. Backend stock checks reject the over-sale.
- **Required correction:** Provide unit-aware decimal quantity entry and compare the resulting quantity with authoritative stock.

<a id="fe-015"></a>
### FE-015 — Wallet displays still misclassify signed debits and reservation movements

- **Severity:** Medium
- **Current source:** `frontend-react/src/components/wallet/WalletWorkspace.jsx:51`; `frontend-react/src/pages/transporter/ac_history.jsx:69`
- **Verification:** WalletWorkspace assigns signs using only deduct/penalty/payout type names. A negative agreement_payment_paid receives a leading plus. Account History counts every positive amount as credit, including lock/unlock movements, and totals only its first 100 loaded records.
- **Impact:** Transaction labels and reported credits/net income can be incorrect even when the underlying wallet balance is correct.
- **Required correction:** Use the signed-amount/transaction-kind contract, exclude reservations from income and label or paginate aggregate coverage.

<a id="fin-21"></a>
### FIN-21 — Legacy card refunds still omit the original provider charge reference

- **Severity:** Medium
- **Current source:** `backend/shared/payments.py:1684`
- **Verification:** refund_one_time_payment calls provider.refund with amount and idempotency key but omits reference=payment["provider_reference"], although the provider interface accepts it. The old claim that production always selects the dummy provider is removed: production now rejects the simulator. This residual concerns the legacy card-funded refund branch.
- **Impact:** A future real refund adapter cannot reliably locate the original charge from this call. No live gateway refund was attempted.
- **Required correction:** Pass the stored charge reference, reject a missing reference for card-funded refunds and verify provider outcome before marking refunded.

<a id="perf-01"></a>
### PERF-01 — Available-order matching still reads an unbounded candidate set

- **Severity:** Medium
- **Current source:** `backend/orders/routes.py:408`
- **Verification:** The feed loads all active owned trucks and all open shipments, then performs nested eligibility checks while the database context remains open. My Orders grouped counts and shop-sale batching are FIXED and removed from the original claim.
- **Impact:** Work grows with orders times trucks and occupies a pooled connection during matching. This is a proven query shape; production latency was not benchmarked.
- **Required correction:** Add bounded candidate pagination/spatial filtering while retaining authoritative eligibility checks.

<a id="be-12"></a>
### BE-12 — Authenticated contact tickets still lose user attribution

- **Severity:** Low
- **Current source:** `backend/contact/routes.py:41`
- **Verification:** Real authenticated Flask/PostgreSQL probe returned a successful ticket whose user_id was NULL. The public route has no login decorator and imports the nonexistent resolve_active_session helper inside a swallowed exception.
- **Impact:** Support cannot reliably associate a signed-in user with their submitted inquiry.
- **Required correction:** Use the existing optional durable-session lookup and attach only server-verified identity; keep anonymous contact supported.

<a id="review-001"></a>
### REVIEW-001 — Profile save truncates last names and ignores editable business fields

- **Severity:** Medium
- **Current source:** `frontend-react/src/pages/client/ClientAccount.jsx:73`; `backend/profile/routes.py:36`
- **Verification:** NEW. Real authenticated probe submitted first_name="Ali", last_name="Abbas", company_name, contact_phone and billing_address. HTTP 200 reported success, but users.full_name became "Ali", returned last_name was empty and company/address values were not saved. The route assigns first_name directly to full_name and only writes full_name/phone/city/about (plus optional shop_name).
- **Impact:** Saving the Client/Everyday account can erase a last name; business edits disappear despite a success message.
- **Required correction:** Align the frontend/backend profile contract, compose the full name correctly and explicitly persist or reject each editable role-owned field.

<a id="review-002"></a>
### REVIEW-002 — Post Order has lost the expected order-mode and records navigation

- **Severity:** Medium
- **Current source:** `frontend-react/src/pages/client/PostOrder.jsx:216`; `frontend-react/src/components/client/ClientLayout.jsx:24`; `frontend-react/src/components/client/OrderWorkspaceNavigation.jsx:3`; `frontend-react/tests/responsiveInterface.test.mjs:73`
- **Verification:** NEW regression against the existing responsive contract. PostOrder no longer imports/renders OrderWorkspaceNavigation. Its title actions show My Orders only for /everyday. The service-seeker mobile menu exposes Dashboard/Post Order/Wallet/Messages, while the contextual Agreemental Order/My Orders/My Agreements controls are absent from this screen. The corresponding Node test fails.
- **Impact:** A mobile user on Post Order loses the intended route to switching booking modes and contextual records. The pages still exist; this is not a claim that every alternate route is unreachable. If this removal was intentional, the navigation contract and replacement entry points need an explicit update.
- **Required correction:** Restore the business-client workspace navigation or provide equivalent visible mobile entry points and update the contract test to match the accepted UX.

## Test-maintenance blockers

| ID | Severity | Current finding |
|---|---|---|
| [TEST-03](#test-03) | Low | Public signup terms endpoint is missing from the static security-test allowlist |
| [TEST-04](#test-04) | Low | Checkout component test still expects the removed insurance checkbox |

<a id="test-03"></a>
### TEST-03 — Public signup terms endpoint is missing from the static security-test allowlist

- **Severity:** Low
- **Current source:** `backend/tests/test_route_security_static.py:105`; `backend/auth/routes.py:342`
- **Verification:** NEW test-maintenance failure: the suite reports GET /auth/signup-terms as undecorated. The endpoint returns public role/version text needed before signup; it does not return account data. Dedicated signup-terms tests exist.
- **Impact:** The backend test gate remains red. This failure does not establish an authorization leak.
- **Required correction:** Add this exact public endpoint to the explicit allowlist with a documented public contract; retain deny-by-default checks for other routes.

<a id="test-04"></a>
### TEST-04 — Checkout component test still expects the removed insurance checkbox

- **Severity:** Low
- **Current source:** `frontend-react/tests/businessRules.test.jsx:41`; `backend/shared/payments.py:1223`
- **Verification:** NEW test-maintenance failure: the wallet-shortfall test clicks a checkbox no longer rendered by BidCheckout. Current signup-role terms capture acceptance and checkout source explicitly avoids fabricating a new acceptance. The test already found the expected shortfall message before failing.
- **Impact:** The component suite is red on a stale interaction. This failure alone does not show that insufficient-balance checkout is enabled.
- **Required correction:** Remove the stale interaction and retain direct assertions for server shortfall, disabled checkout and absent card inputs.

## Current verification

| Check | Current result |
|---|---|
| Backend, no DB | 544 passed, 1 failed, 878 skipped. Failure: TEST-03. Skips are not passes. |
| Backend, disposable PostgreSQL | 1,419 passed, 1 failed, 3 explicitly disabled shared-TEST probes skipped (1,423 collected), 0 errors; 29m07s. Failure: TEST-03. |
| Frontend Node tests | 103 passed, 1 failed (104 total). Failure: REVIEW-002. |
| Frontend rendered component tests | 96 passed, 1 failed (97 total). Failure: TEST-04. |
| Audit backend counterexamples | 8 passed: defects reproduced, including 3 real PostgreSQL/HTTP probes. These are not fixed-behavior tests. |
| Audit rendered counterexamples | 3 passed: POS retry, fractional quantity and fuel-voucher remount defects reproduced. |
| Production build | Passed, 20.89 seconds; main JS 1,665.40 kB / 432.74 kB gzip. Large-chunk warning remains. |
| Frontend source/build-config lint | 195 files; 0 errors, 2 warnings, 0 parser failures. Tests/generated dist were not included in this lint command. |
| Python syntax | 163 maintained backend Python files parsed; generated seed output excluded. |

Backend selections overlap and must not be summed into unique coverage. Source-proven races and API inventory findings are labelled separately from exercised HTTP/database counterexamples. No live UI/browser exploratory pass, external dependency vulnerability scan, or new production latency benchmark is claimed.

## Remaining delivery work, separate from confirmed bugs

- Production gateway collection, payout execution and provider reconciliation still require implementation/deployment proof; disabled simulated payouts are a deliberate safeguard.
- New business-rule escrow, fee, collateral, treasury and journal code already exists. The former blanket recommendation to build all of it from scratch is obsolete. Legacy agreement accounting and the precise residual findings above still need correction.
- Hardware/provider telemetry and physical handoff verification remain deployment/product work. Assignment-bound browser GPS is implemented, but it does not independently prove billable movement.
- Preserve applied migration history; deploy pending forward migrations through the existing release process. This audit applied no migration to a shared or remote project.
