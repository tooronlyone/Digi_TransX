# Cleanup and test audit — current status

Final reconciliation completed **28 October 2026 (Asia/Karachi)**; test execution and source evidence below were captured on 27 October.

Revalidated **27 October 2026 (Asia/Karachi)**. Supersedes the old 20 October test counts and failure classification. Existing source files were not deleted or refactored. Current bugs are indexed in [AUDIT_LEDGER.md](../AUDIT_LEDGER.md).

## Maintained source inventory

| Area | Files |
|---|---:|
| Backend production Python | 84 |
| Backend maintained script Python | 9 |
| Backend test/helper Python | 70 |
| Frontend source JS/JSX | 189 |
| Frontend source CSS | 29 |
| Frontend existing test files | 22 |
| Forward SQL migrations | 45 |

Counts exclude dependencies, generated dist, seed output, Python bytecode, caches, traces and local PostgreSQL data. They include the owner's uncommitted first-party files. All 163 maintained backend Python files parse.

## Current verification and failures

Frontend source/config lint: **0 errors, 2 warnings** across 195 files. Production build passes; a large bundle warning remains. Node suites: **103 passed, 1 failed**. Rendered suites: **96 passed, 1 failed**. No-DB backend: **544 passed, 1 failed, 878 skipped**. Full PostgreSQL outcome is recorded in the [current evidence receipt](audit-evidence/2026-10-27/README.md); skipped/opt-in integration tests are not counted as passes.

- **REVIEW-002:** PostOrder lost its contextual mode/records navigation; the existing responsive contract test detects the removed component. Record the intended replacement if the UX change was deliberate.
- **TEST-03:** static security allowlist needs the intentionally public signup-terms endpoint. This is test drift, not an inferred data exposure.
- **TEST-04:** checkout shortfall test still clicks the removed insurance checkbox. Keep the shortfall/disabled-submit assertions and update the interaction.

The previous SMS migration-tail assertion (TEST-02) has been corrected. The old cleanup report's canonical-event/bootstrap test expectation is no longer listed as a current failure. The two application-DB-writing test modules now use disposable fixtures and fake SMTP (TEST-01 corrected).

## Maintenance candidates, not active product defects

Unimported future-feature pages, the unused old Unlock/Balance/print/footer files and commented ServiceHistory routes remain source-cleanup candidates. Static absence of imports alone does not establish that a module must be deleted. No deletion was performed. API aliases are deliberate compatibility contracts. Retired flow 409 responses and resource-reservation 403 responses are deliberate safeguards, not missing implementations to reopen.

Custom toasts/browser alerts are consistency work unless they fail an actual control contract; DriverDetails' missing Notification onClose is retained as LEDGER-007. The external GPS provider is deferred; the actual billing trust issue remains BE-07. A missing standalone sidebar entry is not a defect when the destination is intentionally available through contextual navigation.

Three new rendered audit probes and eight backend probes are retained as evidence outside the normal suites; they assert observed defects and are not proposed fixed-behavior regression tests. Raw logs and reproduction instructions are in [audit-evidence/2026-10-27](audit-evidence/2026-10-27/README.md).
