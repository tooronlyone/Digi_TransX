# Authentication audit — current findings

Final reconciliation completed **28 October 2026 (Asia/Karachi)**; test execution and source evidence below were captured on 27 October.

Revalidated **27 October 2026 (Asia/Karachi)** against the local working tree. This replaces the earlier auth snapshot, which described password revocation, bootstrap and guard behavior that has since changed. [AUTH_SYSTEM_FULL_MAP.md](AUTH_SYSTEM_FULL_MAP.md) describes current ownership; [PROJECT_AUDIT_REPORT.md](PROJECT_AUDIT_REPORT.md) owns the active finding IDs.

## Remaining auth-related findings

| Finding | Current evidence | Tracking |
|---|---|---|
| Reset issuance/login admission controls | Six successive mocked reset requests were accepted; no resend limiter before email/OTP I/O. Existing/nonexistent accounts receive different responses. | [AUTH-05](PROJECT_AUDIT_REPORT.md#auth-05) |
| JSON validation gaps | Signup array/numeric-name probes still raise; login and reset scalar validation are corrected. Profile/contact and wallet topup retain object-shape assumptions. | [AUTH-06, including FIN-19 residual](PROJECT_AUDIT_REPORT.md#auth-06) |
| Random driver-code collisions | One five-digit random code attempt; unique_driver_id collision is not retried. | [DB-15](PROJECT_AUDIT_REPORT.md#db-15) |
| Public signup terms test allowlist | Static security test omits the intentionally public role-terms endpoint. This is a test contract issue, not a demonstrated data exposure. | [TEST-03](PROJECT_AUDIT_REPORT.md#test-03) |

The new profile-save data-loss issue is [REVIEW-001](PROJECT_AUDIT_REPORT.md#review-001), not a session-authentication failure.

## Verified current behavior

- Protected API requests reread durable session/device/user authority. The former worker-local authorization cache is gone. Access-lock persistence remains inside its database context. Source: `backend/auth/helpers.py:376`.
- Reset/change calls the credential-change service. It locks the owner, advances credential generation, closes the pending gate, revokes all active sessions/devices and commits before provider I/O. Unknown provider outcomes require reconciliation and do not resurrect old sessions. Source: `backend/auth/credential_changes.py:47` and `backend/auth/credential_changes.py:117`.
- Logout failure returns 503 and retains a visible retry path; it no longer claims successful revocation after a transaction failure. The frontend waits for confirmed success. Source: `backend/auth/routes.py:930` and `frontend-react/src/auth/logout.js`.
- Admin sign-in uses `await cacheUser(json)` before navigation, refreshing shared authority. The current component regression passes. Source: `frontend-react/src/pages/admin/AdminLogin.jsx:26`.
- HTML bootstrap contains checked auth status, limited user data, security references and freshness deadlines. AccessLockProvider consumes it; role guards consume shared AuthVerificationContext rather than each making an independent `/auth/me` call. Source: `backend/app.py:112`, `frontend-react/src/components/security/AccessLockProvider.jsx:26`, `frontend-react/src/hooks/useClientAuth.js`.
- `/unlock` is owned by App's `UnlockRoute` and the shared access-lock UI. The unused old `pages/auth/Unlock.jsx` stub does not define the live route. Source: `frontend-react/src/App.jsx:153`.
- Signup includes server-versioned role terms and acceptance persistence. `GET /auth/signup-terms` is intentionally available before login; acceptance is validated in signup. Source: `backend/auth/signup_terms.py`, `frontend-react/src/pages/auth/SignupTerms.jsx` and the 27 October forward migration.

## Contracts that are not bugs

- A valid durable session with a locked access proof is different from being logged out. `/auth/me` intentionally allows locked access to return the minimum presentation/unlock contract.
- Missing MPIN configuration or a database/service outage returns an unavailable state; configuration absence is not itself a discovered authentication bypass.
- Presentation state is not backend authorization. Browser freshness avoids repeated UI checks, but protected server handlers still verify durable authority.
- Compatibility auth aliases and the intentional 403 reservation endpoints must not be removed or weakened merely to make an inventory appear uniform.

## Verification and limits

Auth, session/device, password generation/revocation and frontend authority tests are included in the current local suite. Exact counts, any failures and overlap limits are recorded in [the revalidation receipt](docs/audit-evidence/2026-10-27/README.md). The reset-admission and malformed-signup demonstrations are local probes; no real password-reset mail or provider account mutation occurred. Current remote Supabase config, deployment secrets and edge controls were not inspected.
