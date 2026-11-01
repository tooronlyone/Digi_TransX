# Audit reconciliation evidence — 27 October 2026

Final reconciliation completed **28 October 2026 (Asia/Karachi)**; test execution and source evidence below were captured on 27 October.

Scope: current local working tree, HEAD `47c8adba44185626fa45e993709560e5c40cc126`, with pre-existing modified/untracked user code preserved. Main reports now show open issues rather than the historical pre-fix list. No application source fix, remote rollout, real email, card payment or payout was performed.

## Results

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

## Removed from active reports after verification

The following **57 original IDs** have local fixes. Removal means the original defect has a current source correction supported by the relevant local tests; it is not a statement that all production deployments have received it.

| IDs | Current correction and verification owner |
|---|---|
| DB-01, DB-02, DB-03, DB-04, DB-05, DB-06, DB-07, DB-08, DB-12, DB-13 | Canonical schema and forward migrations now include signup role/identity protection, browser ACL/RLS hardening, thread membership, nonrecursive agreements, hire tables, private operational reads and legacy-log insert restrictions. `test_database_authorization_hardening.py`, schema/migration/RLS suites. |
| AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-07 | No worker-local authority cache; checked-out transaction owns access-lock writes; credential generation/pending gates and session/device revocation precede password provider I/O; logout failure returns retryable 503. Auth/inventory, credential-race, session/device/logout suites. |
| BE-01, BE-02, BE-03, BE-04, BE-05 | Transporter-only fleet writes, consent-based assignment, finite validators, certified tanker volume, locked bid withdrawal. Fleet/driver, numeric/location and order/payment race suites. |
| BE-08 | Monthly payment now locks and rereads the source, treats paid replay idempotently, locks wallets and rolls back failed credit. Concurrent monthly settlement/recovery tests in `test_business_legacy_earnings_recovery.py`. BE-06/09/10 remain separate open agreement defects. |
| FIN-01, FIN-02, FIN-03, FIN-04, FIN-05, FIN-06, FIN-07, FIN-08, FIN-09, FIN-14, FIN-15, FIN-16, FIN-17, FIN-20, FIN-22 | Provider environment gates, private delivery challenges, atomic checked settlement, resource-owned reserves, wallet/withdrawal locks, production payout refusal, seller roles, stored pump rate/stock locking, exact POS line rounding/merged products, guarded marketplace states and conflict-safe wallet creation. Financial marketplace, fuel, payment and business-rule suites. |
| FIN-10, FIN-11, FIN-12, FIN-13 | Review provenance, owned-trip dispatch, assignment-bound GPS and exclusive consented allocations. Driver workflow/fleet/database suites. |
| FIN-18, DB-11 | Default-card/preference convergence and constant-query sales lists. Remaining order/payment/performance suite; `PERF-01` retains unbounded available-order matching only. |
| FE-001, FE-002, FE-003, FE-004, FE-005, FE-006, FE-007, FE-008, FE-009, FE-010, FE-013, FE-014, FE-016 | Receipt escaping, CSRF/idempotent marketplace transport, authoritative logout/admin sign-in, chat/location race guards, calendar dates, exact login password, GPS cancellation, exact POS money, account-bound cart/AI state and static-asset allowlist. Node/component suites and clean production build. The two current frontend suite failures concern different contracts and remain open above. |
| TEST-01, TEST-02 | Former application-DB test modules now use disposable remediation fixtures/fake SMTP; SMS migration test no longer hardcodes the newest migration. Source inspection and current suite execution. |

Machine-readable original disposition: [disposition.json](disposition.json). Source SHA-256 manifest: [source-sha256.json](source-sha256.json). Eighteen original IDs retain work; FIN-19 is merged into AUTH-06. Corrected portions of AUTH-06, BE-11, DB-09/10 and PERF-01 were removed while their residuals remain.

## Commands and artifacts

Run from the repository root unless stated otherwise. The evidence directory uses the user's audit date, Asia/Karachi.

```powershell
# Existing frontend tests, from frontend-react/
node --test tests/*.test.mjs
npm.cmd run test:components -- --reporter=verbose
npm.cmd run build
.\node_modules\.bin\eslint.cmd src build vite.config.js vitest.config.js eslint.config.js --format json

# PostgreSQL suite, after starting an EMPTY local cluster on 127.0.0.1:15479
py docs/audit-evidence/2026-10-27/run_backend.py backend/tests -q --tb=short
py docs/audit-evidence/2026-10-27/run_backend.py docs/audit-evidence/2026-10-27/test_reaudit_probes.py -q
```

- [Backend integration output](backend-postgres.txt), [JUnit](backend-postgres.xml), [no-DB output](backend-no-db.txt).
- [Frontend Node output](frontend-node.txt), [component output](frontend-components.txt), [build output](frontend-build.txt), [lint JSON](frontend-lint.json).
- [Backend counterexamples](test_reaudit_probes.py), [results](audit-probes.txt), [JUnit](audit-probes.xml). Eight passing probes mean the defects were reproduced; three use authenticated HTTP/real PostgreSQL (profile, contact and repeated penalties), the others use local functions or deliberately mocked provider/SMTP boundaries.
- [Rendered counterexamples](frontend-probes.test.jsx), [results](frontend-probes.txt). Copy the evidence JSX to `frontend-react/tests/auditReview20261027.test.jsx`, run only that file with Vitest, then remove the temporary copy. The copy was removed after this audit.
- [Current Flask route inventory](routes.json): 205 blueprint rules registered without importing the global app, so no application DB connection/startup worker ran. The duplicate `/api/auth` alias and static/SPA app rules are omitted; this does not affect the missing business endpoint checks.

The first fuel-panel probe used an incorrect label; it was corrected to the actual rendered label and the final three-probe run passed. The initial probe-helper mistake is not a product finding. The audit backend probe run overlapped the broad suite, so its printed two remaining databases belonged to that still-running suite, not abandoned probe data.

The runner permits only the task-owned loopback PostgreSQL port, supplies an invalid application DB URL and disables shared harness opt-in. Each integration fixture owns disposable child data. Local test durability settings were relaxed for speed; these tests do not establish crash durability. The broad run reported zero remaining task databases after teardown. On the 28 October completion check the task process was already gone and loopback port 15479 had no listener; the stopped local data directory was retained. No unrelated PostgreSQL service was stopped.

No live browser walkthrough, deployed Supabase inspection, dependency vulnerability scan or real gateway/physical-device test was performed. Dated 24/25 October rollout receipts remain past records and are not reasserted as fresh remote verification.

The frontend Node/component/build/lint checks were repeated after two existing frontend files changed during the session (StepShell and AgreementBids). The final outputs above reflect that repeat; findings and failure counts were unchanged. All files in the source manifest and the inventoried source-file set were unchanged at final reconciliation.
