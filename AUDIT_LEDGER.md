# Current audit ledger

Final reconciliation completed **28 October 2026 (Asia/Karachi)**; test execution and source evidence below were captured on 27 October.

Revalidated 27 October 2026 (Asia/Karachi). This is an index of current findings, not a historical claim that every original suspicion is still a bug. Fixed findings have been removed from the active list. Full proof and correction criteria live in the linked reports; [closure/disposition evidence](docs/audit-evidence/2026-10-27/README.md) retains the verification trail.

## Active product findings

| ID | Severity | Source | Current issue | Details |
|---|---|---|---|---|
| AUTH-05 | High | `backend/auth/routes.py:1055`; `backend/auth/routes.py:505` | Password-reset issuance still has no resend admission limit | [Evidence](PROJECT_AUDIT_REPORT.md#auth-05) |
| AUTH-06 | Medium | `backend/auth/helpers.py:748`; `backend/auth/routes.py:353`; `backend/profile/routes.py:36`; `backend/contact/routes.py:13`; `backend/wallet/routes.py:239` | Wrong JSON shapes still crash signup, profile, contact and wallet entry points | [Evidence](PROJECT_AUDIT_REPORT.md#auth-06) |
| BE-06 | High | `backend/agreements/routes.py:722` | Agreement trip completion still races monthly distance accrual | [Evidence](PROJECT_AUDIT_REPORT.md#be-06) |
| BE-07 | High | `backend/agreements/routes.py:662`; `backend/agreements/routes.py:722`; `backend/tracking/traccar.py:17` | Agreement billing still trusts transporter-supplied start/end coordinates | [Evidence](PROJECT_AUDIT_REPORT.md#be-07) |
| BE-09 | High | `backend/agreements/helpers.py:444` | Every repeated late-fee sweep can charge the same overdue invoice again | [Evidence](PROJECT_AUDIT_REPORT.md#be-09) |
| BE-10 | High | `backend/agreements/helpers.py:134`; `backend/agreements/routes.py:722` | Agreement due dates and service periods still exclude valid work | [Evidence](PROJECT_AUDIT_REPORT.md#be-10) |
| BE-11 | Medium | `backend/agreements/routes.py:291`; `backend/agreements/routes.py:662`; `supabase/schema.sql:1334`; `supabase/schema.sql:1336` | Agreement bids and active trips still use unprotected check-then-insert | [Evidence](PROJECT_AUDIT_REPORT.md#be-11) |
| DB-09 | Medium | `backend/shared/db.py:77`; `backend/shared/db.py:132` | Legacy database reads discard timestamp offsets | [Evidence](PROJECT_AUDIT_REPORT.md#db-09) |
| DB-10 | Medium | `backend/shared/db.py:77`; `backend/shared/db.py:132`; `backend/wallet/routes.py:281` | Legacy database reads still convert exact NUMERIC amounts to float | [Evidence](PROJECT_AUDIT_REPORT.md#db-10) |
| DB-14 | Medium | `backend/shared/db.py:57` | Concurrent first use can construct two database pools | [Evidence](PROJECT_AUDIT_REPORT.md#db-14) |
| DB-15 | Medium | `backend/auth/routes.py:279`; `supabase/schema.sql:3323` | Driver signup still fails on a random driver-code collision | [Evidence](PROJECT_AUDIT_REPORT.md#db-15) |
| FE-012 | High | `frontend-react/src/pages/shopkeeper/POSPage.jsx:75`; `backend/shopkeeper/routes.py:198` | POS retry can repeat an already committed sale after receipt loading fails | [Evidence](PROJECT_AUDIT_REPORT.md#fe-012) |
| FE-011 | Medium | `frontend-react/src/pages/shopkeeper/POSPage.jsx:49`; `frontend-react/src/pages/shopkeeper/POSPage.jsx:229` | POS quantity controls cannot safely choose fractional units | [Evidence](PROJECT_AUDIT_REPORT.md#fe-011) |
| FE-015 | Medium | `frontend-react/src/components/wallet/WalletWorkspace.jsx:51`; `frontend-react/src/pages/transporter/ac_history.jsx:69` | Wallet displays still misclassify signed debits and reservation movements | [Evidence](PROJECT_AUDIT_REPORT.md#fe-015) |
| FIN-21 | Medium | `backend/shared/payments.py:1684` | Legacy card refunds still omit the original provider charge reference | [Evidence](PROJECT_AUDIT_REPORT.md#fin-21) |
| PERF-01 | Medium | `backend/orders/routes.py:408` | Available-order matching still reads an unbounded candidate set | [Evidence](PROJECT_AUDIT_REPORT.md#perf-01) |
| BE-12 | Low | `backend/contact/routes.py:41` | Authenticated contact tickets still lose user attribution | [Evidence](PROJECT_AUDIT_REPORT.md#be-12) |
| REVIEW-001 | Medium | `frontend-react/src/pages/client/ClientAccount.jsx:73`; `backend/profile/routes.py:36` | Profile save truncates last names and ignores editable business fields | [Evidence](PROJECT_AUDIT_REPORT.md#review-001) |
| REVIEW-002 | Medium | `frontend-react/src/pages/client/PostOrder.jsx:216`; `frontend-react/src/components/client/ClientLayout.jsx:24`; `frontend-react/src/components/client/OrderWorkspaceNavigation.jsx:3`; `frontend-react/tests/responsiveInterface.test.mjs:73` | Post Order has lost the expected order-mode and records navigation | [Evidence](PROJECT_AUDIT_REPORT.md#review-002) |
| LEDGER-007 | Medium | `frontend-react/src/pages/auth/roledetails/DriverDetails.jsx:66`; `frontend-react/src/components/common/Notification.jsx:3` | Driver signup notification cannot be dismissed | [Evidence](FINAL_REPORT.md#ledger-007) |
| LEDGER-012 | Medium | `frontend-react/src/lib/aiAssistant.js:1`; `frontend-react/src/components/ai/GlobalAiAssistant.jsx:320` | Server-backed assistant endpoints are absent | [Evidence](FINAL_REPORT.md#ledger-012) |
| LEDGER-013 | High | `frontend-react/src/pages/driver/DriverWallet.jsx:24`; `frontend-react/src/pages/driver/DriverWallet.jsx:41` | Driver payout screen calls two nonexistent wallet endpoints | [Evidence](FINAL_REPORT.md#ledger-013) |
| LEDGER-014 | High | `frontend-react/src/pages/shopkeeper/ShopkeeperDashboard.jsx:18`; `frontend-react/src/pages/shopkeeper/CreateTable.jsx:71`; `frontend-react/src/pages/shopkeeper/TableView.jsx:40` | Shopkeeper Tables screens have no matching backend routes | [Evidence](FINAL_REPORT.md#ledger-014) |
| LEDGER-015 | Low | `frontend-react/src/pages/transporter/about.jsx:221` | About page requests five absent endpoints | [Evidence](FINAL_REPORT.md#ledger-015) |
| LEDGER-016 | Low | `frontend-react/src/pages/transporter/truck_details.jsx:35` | Truck detail performs unsupported maintenance/fuel reads | [Evidence](FINAL_REPORT.md#ledger-016) |
| LEDGER-017 | High | `frontend-react/src/components/admin/AdminLayout.jsx:18`; `frontend-react/src/components/driver/DriverLayout.jsx:16`; `backend/shared/notifications.py:42` | Admin and Driver layouts expose no notification inbox | [Evidence](FINAL_REPORT.md#ledger-017) |
| LEDGER-018 | Medium | `backend/admin/routes.py:365`; `backend/admin/routes.py:415` | Withdrawal decisions do not notify the requester | [Evidence](FINAL_REPORT.md#ledger-018) |
| LEDGER-019 | Medium | `backend/agreements/helpers.py:423`; `backend/agreements/helpers.py:444` | Agreement failures and late charges have no recipient notification | [Evidence](FINAL_REPORT.md#ledger-019) |
| LEDGER-023 | Medium | `frontend-react/src/components/business/FuelVoucherPanel.jsx:13`; `backend/fuelstation/vouchers.py:116` | Reloading a fuel voucher panel loses access to an outstanding authorization | [Evidence](FINAL_REPORT.md#ledger-023) |

## Test blockers

| ID | Severity | Current finding |
|---|---|---|
| [TEST-03](PROJECT_AUDIT_REPORT.md#test-03) | Low | Public signup terms endpoint is missing from the static security-test allowlist |
| [TEST-04](PROJECT_AUDIT_REPORT.md#test-04) | Low | Checkout component test still expects the removed insurance checkbox |

## Product gaps and maintenance

- **LEDGER-021 — Owner-operator credential verification:** No admin UI caller for POST /api/admin/owner-operator-credentials/<user_id>. The server prerequisite exists, but admin verification currently requires a trusted external/API workflow. Source: `backend/driver/business_rules.py:82`.
- **LEDGER-022 — Marketplace admin refunds:** The admin refund endpoint has no in-app caller. This is a missing management feature, not proof that the guarded refund service is broken. Source: `backend/marketplace/routes.py:260`.
- **LEDGER-024 — Saved payment method/preferences management:** The frontend reads saved methods but supplies no management UI for the remaining method/preference operations. Clarify intended product surface before treating an API without a caller as a defect. Source: `backend/payments/routes.py:165`.

Optional cleanup, intentional denial endpoints, route aliases and other rejected suspicions are explained in [FINAL_REPORT.md](FINAL_REPORT.md#optional-maintenance-and-rejected-claims). They do not inflate the 29-product-finding / 2-test-blocker count. FIN-19 residual JSON validation is merged into AUTH-06. The original 57 corrected IDs are recorded only in the verification receipt, not as active bugs.
