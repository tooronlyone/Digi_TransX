# Current integration, notification and frontend audit

Final reconciliation completed **28 October 2026 (Asia/Karachi)**; test execution and source evidence below were captured on 27 October.

Revalidated **27 October 2026 (Asia/Karachi)**. Read with [PROJECT_AUDIT_REPORT.md](PROJECT_AUDIT_REPORT.md); this file is the supplemental UI/API integration register, not an additional copy of its 19 product findings.

**10 confirmed product findings remain here.** Three feature gaps and optional maintenance observations are listed separately. The prior 25-bug count incorrectly treated intentional denial endpoints, navigation choices and stylistic preferences as proven defects; that count and its Critical labels have been removed.

Evidence comes from current source, a newly registered Flask URL map ([routes.json](docs/audit-evidence/2026-10-27/routes.json)) and the [revalidation probes](docs/audit-evidence/2026-10-27/README.md). Missing-route matching does not exercise a live server or an external AI provider.

## Active findings

| ID | Severity | Current finding |
|---|---|---|
| [LEDGER-007](#ledger-007) | Medium | Driver signup notification cannot be dismissed |
| [LEDGER-012](#ledger-012) | Medium | Server-backed assistant endpoints are absent |
| [LEDGER-013](#ledger-013) | High | Driver payout screen calls two nonexistent wallet endpoints |
| [LEDGER-014](#ledger-014) | High | Shopkeeper Tables screens have no matching backend routes |
| [LEDGER-015](#ledger-015) | Low | About page requests five absent endpoints |
| [LEDGER-016](#ledger-016) | Low | Truck detail performs unsupported maintenance/fuel reads |
| [LEDGER-017](#ledger-017) | High | Admin and Driver layouts expose no notification inbox |
| [LEDGER-018](#ledger-018) | Medium | Withdrawal decisions do not notify the requester |
| [LEDGER-019](#ledger-019) | Medium | Agreement failures and late charges have no recipient notification |
| [LEDGER-023](#ledger-023) | Medium | Reloading a fuel voucher panel loses access to an outstanding authorization |

<a id="ledger-007"></a>
### LEDGER-007 — Driver signup notification cannot be dismissed

- **Severity:** Medium
- **Current source:** `frontend-react/src/pages/auth/roledetails/DriverDetails.jsx:66`; `frontend-react/src/components/common/Notification.jsx:3`
- **Verification:** DriverDetails still omits onClose. Notification uses it for both its close button and timeout.
- **Impact:** Signup feedback remains visible until navigation instead of responding to its dismissal control.
- **Required correction:** Pass a state-clearing callback and verify both manual and timed dismissal.

<a id="ledger-012"></a>
### LEDGER-012 — Server-backed assistant endpoints are absent

- **Severity:** Medium
- **Current source:** `frontend-react/src/lib/aiAssistant.js:1`; `frontend-react/src/components/ai/GlobalAiAssistant.jsx:320`
- **Verification:** Current Flask route inventory has no /api/ai-assistant routes. Mounted assistant components still call preferences/capabilities/interpret/confirm/cancel. Some callers contain unavailable-service handling, so the prior blanket Critical claim is removed.
- **Impact:** Server assistant features cannot complete against this backend; browser UI/fallback behavior does not supply those server actions.
- **Required correction:** Implement the intended authenticated service contract or hide/disable unsupported server features and stop absent-endpoint calls.

<a id="ledger-013"></a>
### LEDGER-013 — Driver payout screen calls two nonexistent wallet endpoints

- **Severity:** High
- **Current source:** `frontend-react/src/pages/driver/DriverWallet.jsx:24`; `frontend-react/src/pages/driver/DriverWallet.jsx:41`
- **Verification:** Fresh runtime route matching confirms GET /api/wallet/balance and POST /api/wallet/withdraw are absent. The page still calls both. Its shared funding workspace uses a different existing contract, so the entire wallet is not described as missing.
- **Impact:** Available payout balance and driver withdrawal submission cannot work. The existing transporter-only withdraw-locked route is not a valid drop-in replacement.
- **Required correction:** Define an authorized driver payout contract and connect this page to the canonical balance API; retain payout-provider/reserve safeguards.

<a id="ledger-014"></a>
### LEDGER-014 — Shopkeeper Tables screens have no matching backend routes

- **Severity:** High
- **Current source:** `frontend-react/src/pages/shopkeeper/ShopkeeperDashboard.jsx:18`; `frontend-react/src/pages/shopkeeper/CreateTable.jsx:71`; `frontend-react/src/pages/shopkeeper/TableView.jsx:40`
- **Verification:** Dashboard, table creation, row editing, analysis and export still call /api/shopkeeper/tables*. No such routes are registered; existing products/sales routes do not implement the table contract.
- **Impact:** The exposed table workflow cannot load or save data.
- **Required correction:** Implement the agreed table data model and authorization, or remove/disable these navigation paths with clear product copy.

<a id="ledger-015"></a>
### LEDGER-015 — About page requests five absent endpoints

- **Severity:** Low
- **Current source:** `frontend-react/src/pages/transporter/about.jsx:221`
- **Verification:** No /api/about route family is registered. The page makes five requests and falls back to hardcoded data.
- **Impact:** Every visit generates failed requests and can display placeholder information as current content.
- **Required correction:** Use maintained static content or implement the real content API; identify placeholder statistics clearly.

<a id="ledger-016"></a>
### LEDGER-016 — Truck detail performs unsupported maintenance/fuel reads

- **Severity:** Low
- **Current source:** `frontend-react/src/pages/transporter/truck_details.jsx:35`
- **Verification:** Runtime inventory confirms maintenance/fuel subroutes do not exist. Truck details still requests both and catches failures; their state variables are currently unused in the rendered page.
- **Impact:** Two unnecessary failures occur for each details load. This is not a broken financial transaction or proof of missing displayed records.
- **Required correction:** Remove unsupported reads or implement/render the intended history contract.

<a id="ledger-017"></a>
### LEDGER-017 — Admin and Driver layouts expose no notification inbox

- **Severity:** High
- **Current source:** `frontend-react/src/components/admin/AdminLayout.jsx:18`; `frontend-react/src/components/driver/DriverLayout.jsx:16`; `backend/shared/notifications.py:42`
- **Verification:** Neither portal layout renders NotificationBell or another notification center. The backend still emits administrator lifecycle notifications and driver operational notifications.
- **Impact:** Recipients lack the in-app surface for reviewing those messages. Severity is High, not the previous Critical label.
- **Required correction:** Expose an owner-scoped notification center and read/unread controls for both portals.

<a id="ledger-018"></a>
### LEDGER-018 — Withdrawal decisions do not notify the requester

- **Severity:** Medium
- **Current source:** `backend/admin/routes.py:365`; `backend/admin/routes.py:415`
- **Verification:** Approval/rejection handlers update the request and return to the admin without calling a user notification writer. Production payout is separately blocked until an executor exists.
- **Impact:** The requester has no in-app decision alert when an allowed decision completes.
- **Required correction:** Publish an idempotent requester notification alongside the authoritative decision.

<a id="ledger-019"></a>
### LEDGER-019 — Agreement failures and late charges have no recipient notification

- **Severity:** Medium
- **Current source:** `backend/agreements/helpers.py:423`; `backend/agreements/helpers.py:444`
- **Verification:** The payment/penalty workers still have no notification dispatch on failure or fee debit.
- **Impact:** Clients learn about an unpaid invoice or charge only by manually inspecting balances/history. The repeated-charge defect itself is tracked separately as BE-09.
- **Required correction:** Emit an idempotent notice linked to the invoice and actual assessment result.

<a id="ledger-023"></a>
### LEDGER-023 — Reloading a fuel voucher panel loses access to an outstanding authorization

- **Severity:** Medium
- **Current source:** `frontend-react/src/components/business/FuelVoucherPanel.jsx:13`; `backend/fuelstation/vouchers.py:116`
- **Verification:** Strengthened from the old unused-GET observation: a rendered probe created an authorized voucher, unmounted/remounted the panel and found no cancel control and no recovery GET. result and the idempotency ref are memory-only; the existing GET /api/fuel/vouchers is never used to restore outstanding authorization state.
- **Impact:** After reload or navigation, the owner cannot cancel the existing hold through this panel or recover a lost-response attempt there; creation becomes enabled again. This does not claim secrets should be redisplayed or all holds become permanent.
- **Required correction:** Load safe owner/trip voucher metadata on mount and offer cancel/recovery for outstanding authorizations, without persisting or replaying OTP secrets.

## Feature gaps requiring a product workflow

- **LEDGER-021 — Owner-operator credential verification:** No admin UI caller for POST /api/admin/owner-operator-credentials/<user_id>. The server prerequisite exists, but admin verification currently requires a trusted external/API workflow. Source: `backend/driver/business_rules.py:82`.
- **LEDGER-022 — Marketplace admin refunds:** The admin refund endpoint has no in-app caller. This is a missing management feature, not proof that the guarded refund service is broken. Source: `backend/marketplace/routes.py:260`.
- **LEDGER-024 — Saved payment method/preferences management:** The frontend reads saved methods but supplies no management UI for the remaining method/preference operations. Clarify intended product surface before treating an API without a caller as a defect. Source: `backend/payments/routes.py:165`.

These three rows are not included in the confirmed-bug count merely because an API has no frontend caller.

## Optional maintenance and rejected claims

- LEDGER-005/006/027: unimported future-feature pages, old Unlock/Balance/print/footer files and commented ServiceHistory routes remain maintenance candidates. Their existence alone is not an active user-facing defect. No source files were deleted by this audit.
- LEDGER-008/009/010/011: custom timed toasts and browser alerts are UI consistency improvements. Without an agreed dismissal/notification requirement they are not counted as independent functional bugs. LEDGER-007 remains a bug because its rendered close control is actually inert.
- LEDGER-001/002/003/004: intentional route aliases remain rejected suspicions.
- LEDGER-020: the overdue-delivery sweep is called by the scheduler; lack of an admin button alone does not prove a missing execution path.
- LEDGER-025: retired payment routes intentionally return 409 to reject removed flows. Do not reopen deprecated mutation paths to remove this response.
- LEDGER-026: generic wallet lock/unlock deliberately return 403; resource workflows own reservations. This closes FIN-04 and is not an implementation stub to bypass.
- LEDGER-028: external GPS provider integration remains deferred. Its actual financial consequence is already counted once as BE-07 in the main report.
- LEDGER-029: Available Bids remains reachable through My Bids/dashboard contextual navigation. A missing separate desktop-sidebar item is not proof of a broken route.

## Validation

The full source/config lint has 0 errors and 2 warnings; build passes. Existing frontend suites have one Node failure (REVIEW-002) and one component failure (TEST-04). Three additional rendered audit counterexamples pass by reproducing the documented defects. See the main report for exact counts and current backend results.
