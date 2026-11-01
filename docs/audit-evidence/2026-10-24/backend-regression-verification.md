# Backend regression verification — 24 October 2026

The broad local PostgreSQL run completed with **1,124 passed, 5 failed and 3 skipped** in **1,448.74 seconds**. Each of those five failures was investigated; the corresponding current tests then passed together: **5 passed in 22.30 seconds**. The initial result is retained without rewriting its failures as passes. A second complete 24-minute run was not performed after the focused corrections.

## Isolation and command

The application database URL was deliberately invalid (`127.0.0.1:1/invalid`), while `TEST_SUPABASE_DB_URL` selected the synthetic loopback PostgreSQL 16 runner at port 15477, database `dtx_phase1b2c0_baseline_correction`. Tests created disposable databases or uniquely named schemas and used real PostgreSQL constraints, transactions and row locks. Shared-project harness activation was disabled for this run. The disposable runner used reduced durability settings to accelerate repeated database creation; these tests do not constitute power-loss recovery testing.

```powershell
$env:TEST_SUPABASE_DB_URL='postgresql://audit_local@127.0.0.1:15477/dtx_phase1b2c0_baseline_correction'
$env:SUPABASE_DB_URL='postgresql://audit:audit@127.0.0.1:1/invalid?connect_timeout=1'
$env:DIGITRANSX_ENVIRONMENT='test'
$env:DTX_SHARED_TEST_HARNESS='0'
py -3.10 -m pytest backend/tests -q --tb=short -ra --junitxml=.codex-logs/security-remediation-backend.xml
```

The complete initial results are [backend-full-initial.log](backend-full-initial.log) and [backend-full-initial.junit.xml](backend-full-initial.junit.xml). The JUnit receipt contains 1,132 test cases, including the three skips.

## Exact failure disposition

| Initial failing test ID | Cause and correction | Current verification |
| --- | --- | --- |
| `backend/tests/test_audit_auth_inventory_fixes.py::test_new_otp_can_recover_a_failed_finalization_without_replaying_old_sessions` | This expectation permitted another provider update after an ambiguous/finalization failure. The hardened implementation deliberately keeps `password_change_pending` until explicit reconciliation, preventing a delayed provider write from racing a retry. The obsolete expectation was replaced by the explicit-reconciliation regression. | `test_failed_finalization_requires_explicit_reconciliation_without_replaying_old_sessions` passed. Exact-generation operator reconciliation and revocation behavior are also covered by the broader focused suite. |
| `backend/tests/test_auth_security_events.py::test_reset_finalization_failure_is_explicit_and_nonreplayable` | The assertion matched older English copy. It now verifies `password_change_reconciliation_required`, the persistent pending gate and the non-replayable reset claim. | Same test ID passed. |
| `backend/tests/test_canonical_event_foundation.py::test_only_the_bounded_auth_route_imports_or_emits_canonical_events` | The exact emitter inventory lacked the new credential-rotation service. Only `backend/auth/credential_changes.py` was added; it emits the existing integrated session/device revocation contracts. The narrow module inventory remains enforced. | Same test ID passed. |
| `backend/tests/test_premerge_route_security.py::test_password_change_otp_is_one_shot_and_provider_failure_is_sanitized` | The old fixture lacked the credential-rotation schema/helper wiring and expected an authenticated replay after cookies were cleared. The test now uses the canonical disposable harness and real authentication, verifies one provider call, consumed OTP, pending owner, revoked session, sanitized 503 and unauthorized replay. | Same test ID passed; all 12 tests in its module separately passed in 26.96 seconds. |
| `backend/tests/test_signup_security_events.py::test_validation_and_provider_conflict_are_anonymous_terminal_denials` | The test expected older public text. The existing route already used one sanitized `409` payload, `Already registered.`, for local and provider account conflicts. The strengthened assertion verifies identical payloads for provider, email-only and CNIC-only conflicts, anonymous `account_conflict` evidence, no provider exception/identifier leakage and no login authority. | Same test ID passed. |

The focused recheck was run together against the final backend code:

```text
backend/tests/test_audit_auth_inventory_fixes.py::test_failed_finalization_requires_explicit_reconciliation_without_replaying_old_sessions
backend/tests/test_auth_security_events.py::test_reset_finalization_failure_is_explicit_and_nonreplayable
backend/tests/test_canonical_event_foundation.py::test_only_the_bounded_auth_route_imports_or_emits_canonical_events
backend/tests/test_premerge_route_security.py::test_password_change_otp_is_one_shot_and_provider_failure_is_sanitized
backend/tests/test_signup_security_events.py::test_validation_and_provider_conflict_are_anonymous_terminal_denials
```

Its exact receipts are [backend-current-recheck.log](backend-current-recheck.log) and [backend-current-recheck.junit.xml](backend-current-recheck.junit.xml): **5 passed, 0 failures, 0 errors**.

## Intentional skips

| Test | Recorded reason |
| --- | --- |
| `backend/tests/test_shared_test_logout_all_harness.py::test_authorized_shared_test_logout_all_matrix` | `explicit shared-TEST opt-in is absent` |
| `backend/tests/test_shared_test_session_device_management_harness.py::test_authorized_shared_test_session_device_matrix` | `explicit shared-TEST opt-in is absent` |
| `backend/tests/test_shared_test_step_up_harness.py::test_authorized_shared_test_pending_probe_matrix` | `shared TEST harness is not explicitly enabled` |

These three shared-project probes were not executed by the broad local run and are not counted as passes. Separate database rollout evidence records the authorized Supabase test-project migration and role probes.

## Converted unsafe legacy fixtures

`backend/tests/test_fuel_station_portal.py` and `backend/tests/test_fixes_withdraw_history_contact.py` now use `tests.remediation_harness`: dynamically seeded UUID-linked accounts, canonical sessions, active CSRF checks, a full disposable schema and stubbed email delivery. They import no global application and contain no hardcoded application user IDs. The two modules passed **12/12** in **21.00 seconds**, covering role boundaries, pump stock/receipt/profile/log operations, persisted contact tickets, unauthenticated history and bid-withdrawal ownership/replay.

The evidence above combines the complete initial run with targeted current-code reruns. It does not claim that every remaining finding in the original project audit is resolved, or that live bank/card processing has been certified.
