# Rules 1–4 frontend implementation and verification — 25 October 2026

> **27 October 2026 status note:** this is the dated 25 October implementation receipt. Current signup captures role-specific terms; checkout no longer renders the prior insurance checkbox. The current audit also confirms the driver payout endpoint mismatch and fuel-voucher reload recovery gap. See [the current findings](../FINAL_REPORT.md) and [verification receipt](audit-evidence/2026-10-27/README.md) rather than treating this earlier scoped completion statement as a clean full-product audit.

The existing React portals now expose server-authoritative market references, itemized fees, full-wallet booking escrow, the Client-authorized delivery OTP handshake, settlement tranches, secure fuel vouchers, driver security notices, owner-operator assignment, safety reporting, and evidence-based Admin settlement resolution. Existing authentication, CSRF transports, account-lifetime guards, and MPIN step-up remain in use.

## Files changed in this task

New files:

- `frontend-react/src/components/business/BusinessRules.jsx`
- `frontend-react/src/components/business/DeliveryClientHandshake.jsx`
- `frontend-react/src/components/business/FuelVoucherPanel.jsx`
- `frontend-react/src/components/business/FuelVoucherRedemption.jsx`
- `frontend-react/src/components/business/OperationalInvestigations.jsx`
- `frontend-react/src/components/business/TripOperationalActions.jsx`
- `frontend-react/src/lib/exactMoney.js`
- `frontend-react/tests/businessRules.test.jsx`

Updated files (preserving pre-existing working-tree changes):

- `frontend-react/src/components/transporter/DriverAssignmentPanel.jsx`
- `frontend-react/src/components/wallet/WalletWorkspace.jsx`
- `frontend-react/src/pages/admin/AdminDisputes.jsx`
- `frontend-react/src/pages/client/AgreementBids.jsx`
- `frontend-react/src/pages/client/AgreementDetail.jsx`
- `frontend-react/src/pages/client/BidCheckout.jsx`
- `frontend-react/src/pages/client/ClientOrderDetail.jsx`
- `frontend-react/src/pages/client/PostOrder.jsx`
- `frontend-react/src/pages/driver/DriverActiveTrip.jsx`
- `frontend-react/src/pages/driver/DriverTrips.jsx`
- `frontend-react/src/pages/driver/DriverWallet.jsx`
- `frontend-react/src/pages/fuelstation/FuelDispensePOS.jsx`
- `frontend-react/src/pages/shopkeeper/ShopkeeperPartsOrders.jsx`
- `frontend-react/src/pages/transporter/AvailableBids.jsx`
- `frontend-react/src/pages/transporter/MyAgreements.jsx`
- `frontend-react/src/pages/transporter/OrderTracking.jsx`
- `frontend-react/src/pages/transporter/earning.jsx`
- `frontend-react/tests/remainingWorkflowSecurity.test.jsx`

## Financial behavior and contracts

- Bidding and Client shipment details load `GET /api/orders/:id/market-reference`; selected truck IDs are passed for the applicable market. The display never substitutes a locally computed average for the authoritative backend reference. First-bid bootstrap has no invented corridor.
- Fee schedules load `GET /api/business-rules/fees`. New settlement and marketplace invoice snapshots supply itemized amounts. UI rendering does not recalculate historical fees.
- New checkout quotes use `wallet_escrow_required`, `wallet_shortfall`, and `can_checkout`. A shortfall disables acceptance and shows the exact server shortfall. Unsupported Everyday wallets display a policy blocker. Existing booking history retains legacy payment data.
- The approved insurance notice is shown during placement, checkout acknowledgement, and shipment details. The accepted notice version is submitted for backend audit persistence. The notice expressly preserves mandatory obligations and verified-misconduct liability.
- New deliveries use `POST complete-delivery`, Client `POST delivery-otp` through `protectedFetch` and MPIN, and Transporter `POST verify-delivery-otp` with an eight-digit code. Codes stay in memory and are cleared with the verified account's component lifetime.
- Settlement rendering uses server amounts for net entitlement, credit recovery, reserve contribution, both tranches, the 90-minute dispute cutoff, and 120-minute release eligibility. The UI explains periodic worker processing and qualifying dispute freezes. Unapproved progressive reserve policy is visible without a guessed deduction.
- Legacy agreement and order views display the actual authorized fuel-credit recovery and wallet credit without changing the historical fare/fee snapshot. Client copy states that Transporter debt recovery is not an additional Client charge.
- Fuel authorization uses `POST /api/fuel/vouchers`, a stable retry idempotency key, MPIN `protectedFetch`, CSRF, and the expected verified-account header. Authorization caps and quantities are decimal strings. Tank Full requires a monetary cap. Owner state is keyed by account, truck, and source trip; pending requests are aborted on account change.
- If an authorization response is lost, retrying retains the original key. A safe replay never redisplays the secret. The Transporter can cancel their unused authorization through `POST /api/fuel/vouchers/:id/cancel`, confirm the funding release, and explicitly create a replacement voucher. Creation stays disabled while the displayed authorization is pending. Cancellation clears the code and observes account lifetime; it never automatically creates another authorization or reverses a finalized Fuel Station payment.
- Fuel authorization shows the server-returned wallet-funded and platform-credit reservations and explains that utilized credit survives cancellation for future-earnings recovery; it never suggests Client escrow or security reserve funding.
- Fuel Station verification uses the OTP plus pump ID. Finalization sends the bound truck, fuel type, pump, redemption token, and actual quantity. The server determines the money amount and verifies available funding. The digital slip shows caps before dispense and actual amounts afterwards; station commission is zero.
- Fuel Station and Client order page state is keyed by the verified account. Switching accounts unmounts previous forms, aborts pending reads/mutations, discards late results and redemption tokens, and prevents operations still awaiting CSRF from dispatching for the new account. The digital slip displays the backend's `redeemed_station_id`.
- Owner-operator assignment uses `POST /api/transporter/drive-myself`; verified credentials and conflicting allocation checks remain backend decisions. Owner-operator GPS uses the role-specific endpoint and assignment binding.
- Driver safety reports use `POST /api/operational-incidents`; only Transporters see the standard cancellation-request action. Requests remain subject to policy review, and allegation text states that reporting does not establish fault, cancel trips, or confiscate funds.
- Admin new-policy dispute resolution requires the selected case's loaded evidence, a verified investigation result, explicit refund amount, decision evidence references, and notes. The remaining held-tranche endpoint allocates only the applicable funds. Existing selection/request race guards are preserved. Historical agreement penalties remain within their original legacy branch.
- A separate Operational Investigations section in Admin Disputes lists investigating, confirmed, and dismissed reports. It loads actor-authorized incident detail before enabling a decision, displays evidence references as text without fetching external content, and requires explicit decision notes. An Admin can confirm or dismiss the selected incident; this action records a finding without automatic penalties, forfeiture, rating changes, or reserve deductions. Stale or mismatched incident evidence cannot enable a decision, and account changes cancel pending decisions.
- Driver wallets display available amounts and frozen funds separately. Withdrawal UI reloads authoritative amounts instead of subtracting a floating-point estimate. Funding tools reuse the shared wallet UI. Shared topups now send the previously missing idempotency header.
- Transporter earnings labels PKR 30,000 as the initial reserve requirement. Current minimum and aggregate locked funds come from the server; progressive reserves and other holds are not described as a fixed PKR 30,000 balance.
- Fuel POS estimated totals, wallet preview calculations, and shortfalls use integer minor-unit arithmetic. The existing legacy topup preview still assumes the existing 2.5% default; a different backend gateway-fee configuration can differ from that preview. This is separate from the server-authoritative freight/marketplace commission schedule.

## Verification

Final verification commands were run locally without accessing a remote database, SMS provider, payment provider, or actual device location:

| Check | Result | Evidence |
|---|---|---|
| `npm run test:components` | 91 passed, 0 failed, 0 skipped; includes 28 Rules 1–4 cases | `docs/audit-evidence/2026-10-25/rules-1-4/frontend-final-vitest.log` |
| `node --test tests/*.test.mjs` | 103 passed, 0 failed, 0 skipped | `docs/audit-evidence/2026-10-25/rules-1-4/frontend-final-node.log` |
| `npm run lint -- --format json ...` | 211 files, 0 errors, 2 existing Fast Refresh warnings | `docs/audit-evidence/2026-10-25/rules-1-4/frontend-final-eslint.json` |
| `npm run build` | passed; latest source run 15.77 seconds | `docs/audit-evidence/2026-10-25/rules-1-4/final-source-build.log` |
| `git diff --check -- frontend-react` | passed; Git emitted line-ending normalization notices only | local check |

The two retained ESLint warnings are `react-refresh/only-export-components` in `StepUpProvider.jsx` and `TransporterPlaceholderPage.jsx`. Vite retains the existing large-chunk and outdated Browserslist-data warnings.

The new component tests exercise first-bid display, trusted market corridor loading and stale-response protection, all four freight fee items, zero fuel commission, exact money previews, insurance consent, MPIN-protected OTP reveal, OTP account lifetime, server dispute-cutoff errors, voucher decimal caps and retry keys, explicit cancellation/reissue after a lost authorization response, funding-before-dispense flow, bound truck/pump/token finalization, account-switch cancellation before dispatch, Driver/Transporter cancellation differences, exact wallet shortfall with no card fallback, evidence-bound Admin held-fund allocation, and operational incident decisions that reject foreign or stale evidence.

The first 91-case full component run had 90 passes and one timing-dependent failure in the pre-existing chat polling test. Its test double captured Testing Library's wait-loop timers as well as application polling. The corrected fixture captures only 4,000 ms application polling and uses noncolliding fake timer IDs. The unchanged assertions still require exactly one slow initial read, no repeated aborts or duplicate reads, and eventual valid message rendering. The investigation and earlier focused rerun are recorded in `docs/audit-evidence/2026-10-25/rules-1-4/frontend-timer-fixture-review.md` and `frontend-chat-regression-rerun.log`.

This verification does not establish real SMS delivery, physical fuel meter accuracy, platform liquidity, remote RLS deployment, end-to-end payment settlement, device credential authenticity, or production readiness. The isolated financial/database integration evidence is reported separately by the backend implementation.

No commit, push, or deployment was performed.
