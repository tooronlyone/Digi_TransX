# Digi_TransX Rules 1–4 implementation and verification

> **27 October 2026 status note:** this is the dated implementation receipt, not a statement that every legacy agreement/UI workflow is correct. Current agreement accrual, penalties, billing periods and other residual defects are listed in [the reconciled audit](../PROJECT_AUDIT_REPORT.md). The latest local test result is in [the verification receipt](audit-evidence/2026-10-27/README.md); remote deployment was not reverified.

Implementation date: 25 October 2026, Asia/Karachi. This report concerns local source changes. No commit, push, deployment, remote migration, real payment, SMS, or physical fuel dispense was performed.

**Local implementation and scoped verification are complete. This is not a production-readiness declaration.** The final receipts and exact working-tree inventory are recorded alongside this report. Earlier security-remediation work was already present in a substantially dirty working tree and has been preserved.

## 1. Scope and status

| Area | Local implementation | Verification / limits |
|---|---|---|
| Rule 1 market mean and bid corridor | Implemented using existing bids, completed trips and verified reviews | Real PostgreSQL arithmetic, first-bid, rating-boundary, withdrawal, historical and concurrent-submission tests |
| Freight fees | New bookings snapshot 20%, itemized 10/5/3/2; Client commission zero | Exact fee and settlement tests; historical snapshots retain their amounts |
| Marketplace fees | New wallet-funded sales snapshot 10%, itemized 6/2/2; approved partial/full reversals | Real PostgreSQL duplicate/concurrent settlement and reversal tests; merchandise is the fee base, delivery excluded |
| Fuel fees | Station receives the complete verified amount, commission zero | Exact station wallet credit and duplicate-callback tests |
| One-time escrow and delivery | Full available-wallet funding, single-use Client-authorized OTP, two settlement tranches | Real PostgreSQL concurrent acceptance, OTP, dispute and release tests |
| Reserves | Initial Transporter30,000 / temporary Driver10,000; separate tracked collateral and immutable entries | No progressive default percentage, inferred fleet bracket, automatic surplus release or allegation forfeiture |
| Fuel protocol and credit | Reserved wallet plus aggregate rating-limited credit backed by a segregated verified treasury; station redemption/finalization; future earnings recovery | Internal funding and ledger reconciliation tested; actual bank liquidity and physical dispense evidence require independent verification |
| Owner-operators / safety | Credential-verified self-assignment, existing exclusive allocation and source tracking, incidents and authorized decisions, Transporter cancellation requests | No Driver cancellation permission, invented penalty or automatic confiscation |
| Everyday checkout | Safely blocked | Existing application deliberately excludes Everyday wallets. An approved wallet-onboarding/migration policy is required; card fallback would violate mandatory upfront wallet escrow |
| New variable-fare agreements | Safely blocked at finalization | Existing agreements calculate variable distance/monthly fares after work. A fixed upfront authorization/escrow and cancellation policy is required. Historical contracts retain their original snapshots/workflows |
| New marketplace COD | Safely blocked | No approved collection mechanism funds the seller's platform fee; a fabricated deduction or receivable was not introduced |
| Production rollout | Not performed | Remote migration, gateway, liquidity, security and production reconciliation remain required |

## 2. Repository inspection and conflicts

Inspection covered existing migrations and canonical schema, order/bid lifecycle, shared payment provider/checkout/refund services, wallet locks and withdrawal protection, marketplace escrow, driver consent/exclusive allocation, fuel stock/POS, durable sessions, CSRF and action-bound MPIN, RLS hardening, and the 24/25 October security-remediation reports.

The old one-time checkout supported wallet/card fallback; new accepted bookings require the entire fare from the Client's available wallet. The old Client confirmation released the complete payout; new versioned bookings require the delivery OTP and tranche service. The old fuel portal recorded cash/card sales without wallet settlement; the new voucher flow is an additional authenticated path and cash receipts retain their existing meaning. Old marketplace wallet sales paid the entire sale to the Shopkeeper; new sales carry immutable10% fee snapshots. Existing adjustable commission administration could contradict the approved20%; new non20 publication is rejected while historical policy rows remain unchanged.

All these changes are forward-only. New freight payments use `business_rules_version=rules-1-4-v1`; existing NULL-version rows retain their saved amounts and original delivery/refund rules. Marketplace uses its explicit fee-version marker. Existing migrations were not rewritten; four new ordered migrations extend the canonical schema.

The existing monthly agreements and Everyday no-wallet model are real contradictions with mandatory fixed upfront wallet escrow. Their affected new operations are blocked explicitly. No real-world financial action was performed while resolving these contradictions.

## 3. Database migrations

Apply in this order only after isolated verification and target-specific preflight:

1. `20261026000000_financial_journal.sql`: append-only journal headers/legs, unique idempotency keys, deferred balance checks, committed-journal append prohibition, immutable records, private RLS and backend ACLs.
2. `20261026010000_market_pricing_fees.sql`: immutable bid reference/rating/corridor snapshots, unique active bids, comparable-route index, forward marketplace fee version and immutable fee/reversal events.
3. `20261026020000_business_escrow_settlement.sql`: versioned payment/financial-terms snapshots, OTP challenges, settlement snapshots and authorized held-fund resolutions, separate reserves/policies/reference points, incident evidence, immutability and backend-only RLS.
4. `20261026030000_fuel_credit_owner_operator.sql`: narrow extension of the existing MPIN descriptor constraint for fuel authorization; segregated treasury binding; credit accounts/events; immutable voucher authorization/final slips; cancellation debt marking; owner-operator credentials and assignment mode; operational incidents and cancellation requests; role isolation and numeric checks.

The migration filename order is a release sequence, not a claim that anything has been applied remotely. `supabase/schema.sql` contains the same migration bodies below the Rules1–4 cutover marker. Fresh/upgrade/replay tests preserve legacy wallet/payment amounts and prevent browser access to private financial and OTP tables. Migrations create no treasury funding, fake credit liquidity, user credential, approved progressive percentage, or financial penalty.

## 4. Calculations and rounding

Money calculations in new financial services use `Decimal` and authoritative `NUMERIC` reads through `Db.execute_exact`. Existing API normalization remains available through `Db.execute` for compatibility. New frontend arithmetic uses integer minor units. Currency formatting is a presentation boundary.

**Market reference.** Normalize route cities/addresses and cargo characteristics, match exact cargo weight and vehicle category, then include each distinct eligible pending bid and each attributable completed-trip fare exactly once. Historical observations have the same arithmetic weight as active bids; no coefficients or weight bands are invented. Sparse markets bootstrap from the first eligible bid. Rejected, withdrawn, cancelled, explicitly ineligible, self-generated and duplicate contributions are excluded. A market advisory lock precedes shipment/bid locks for submissions/withdrawals. Validate before insertion, then publish the recalculated mean. Each bid stores its pre-insert reference, trusted rating, inclusive currency bounds and sample count.

For a pre-insert mean `M`, the minimum is `ceil_to_paisa(M×0.80)`. The maximum is `floor_to_paisa(M×1.20)` below4.5 or `floor_to_paisa(M×1.40)` at or above4.5. Display mean is rounded half-up to two decimals; exact reference and inclusive currency bounds are returned together. Ratings derive from reviews joined to the actual Client, Transporter and completed source trip, never the request or an unproven cached rating.

**Freight.** Fee total is half-up `gross×20%`; itemization reconciles exactly to that total with deterministic penny allocation. The four displayed components are:

| Component | Percent |
|---|---:|
| Digi_TransX Core Platform & Software Licensing Fee |10%|
| Live Satellite GPS Tracking & Fleet Security Services |5%|
| Digital Payment Gateway & Secure Wallet Processing |3%|
| Escrow Guarantee & Dispute Protection Fund |2%|
| Total Platform Deductions |20%|

Client platform commission is0%. For100,000 gross, commission20,000 and net80,000. With no authorized debt/reserve contribution,40,000 is available immediately and40,000 becomes release-eligible after120minutes. With15,000 authorized fuel debt, recover15,000 distinctly from the80,000 payable, then split the65,000 remaining into32,500/32,500. Debt never becomes an additional Client escrow charge. Odd-paisa halves use half-up for the first tranche and the exact remainder for the second.

**Marketplace.** Eligible merchandise amount×10%, displayed as Marketplace Listing & Tech Infrastructure6%, Digital Catalog & Search Visibility2%, Escrow Protection & Fraud Settlement2%. A10,000 eligible sale yields1,000 fee and9,000 seller proceeds before other approved adjustments. Delivery charges are excluded because their commission eligibility was not specified. Partial refunds use cumulative exact eligible-sale reversal totals and return the difference from prior reversals; this prevents repeated rounding drift or duplicate fee reversal. Historical settlements are not recalculated.

**Fuel.** Station fee is0%. For a25,000 cap and10,000 spendable Transporter wallet, reserve10,000 wallet plus15,000 eligible platform credit. At a verified25,000 dispense, station wallet receives25,000; utilized/outstanding credit becomes15,000. If actual charge is5,000, only5,000 wallet funds are consumed, unused wallet authorization is released, and all15,000 reserved credit is cancelled without becoming debt.

Verified ratings4–5 permit at most20,000 aggregate reserved+outstanding platform exposure;3–below4 permits10,000; below3 and unreviewed accounts permit0. A request reserves the actual shortfall and checks real segregated wallet availability plus independently attested treasury liquidity under locks. No treasury is seeded automatically. No interest, credit service fee or margin is charged.

## 5. Ledger and locking invariants

- Every new journal balances to zero within its database transaction. Journal headers, entries and committed amounts cannot be changed or appended later. Reversal means a new explicit record, never an edit.
- Full Client booking fare is atomically debited into the existing held-payment escrow. A shortfall leaves no partial hold, accepted bid or partial order allocation. The error reports the exact amount to top up.
- New settlement snapshots reconcile gross=commission+net and net=credit recovery+approved reserve contribution+tranche1+tranche2. Payment status/row locks and unique monetary references prevent duplicate commission or release.
- Booking source locks precede payment/settlement/wallet locks. Due-settlement workers skip a locked source, reread dispute state and release eligibility, and commit once. A worker never overrides a qualifying dispute.
- Checkout, legacy agreement payout and dispute resolution lock the Client/Transporter wallet pair in canonical `user_id` order, independent of wallet creation order. This removes the cross-flow lock inversion found in final review; the affected checkout, route, escrow and legacy-recovery suites passed198cases after the change.
- Fuel locks source trip→truck→Transporter wallet→credit account→treasury→treasury wallet→voucher→pump→station wallet. Transporter account locking serializes aggregate credit exposure. Finalized station receipts and credit events are immutable.
- Wallet fuel holds and platform fuel holds are separate from security collateral and Client escrow. Actual wallet spend plus actual utilized credit equals the station credit. Unused authorizations unlock their original backing.
- Treasury wallet identity cannot be rebound under pending authorizations. Cancellation/expiry can release original holds even if a truck later becomes ineligible. Redemption requires current source, ownership/authority, plate, pump, fuel and cap matches.
- Utilized cancelled-trip debt remains outstanding, blocks new platform credit until recovered and is allocated FIFO against future eligible earnings. It cannot debit collateral or Client escrow, or reverse a valid station payment.
- Security reserve balances remain in aggregate wallet collateral and `minimum_required`; normal fuel/withdrawal cannot spend them. Progressive accumulation has no unapproved default and cannot exceed the configured approved ceiling. No automatic surplus release or complaint-based confiscation exists.
- The journal covers versioned operations from this cutover. Existing historical wallet records remain authoritative history; this work does not invent bank-backed opening entries or assert a reconciled historical global double-entry ledger.

`python -m scripts.reconcile_business_rules` is read-only. It checks journal balance, freight snapshots, account/voucher credit totals and recovery allocations, and backing of reserve/fuel holds. A clean internal result does not establish actual bank funds, physical delivery, metering or historical opening reconciliation.

## 6. Security and lifecycle protections

Existing durable session/device binding, credential-generation invalidation, access locks, role guards, CSRF, RLS, withdrawal reservation checks and action-bound MPIN remain in place. New fuel authorization adds an amount/trip/request-bound one-use MPIN action and expected verified-account header. Its narrow database constraint extension preserves other action shapes. Account changes abort/rekey financial forms; secrets stay in component memory.

Delivery OTPs are generated from secure random nonces and a configured independent server secret; only keyed digests/nonces are persisted. Client reveal requires existing delivery MPIN step-up and verified ownership. Transporter submission checks source/actor/lifecycle, ten-minute expiry, five failed attempts and single use. Neither the transporter issue response nor unrelated user sessions receive the Client code. Missing secret blocks issuance safely.

The server completion timestamp starts the90-minute dispute window and120-minute release eligibility. Minutes90–120 are a buffer, not a second dispute filing window. The configured existing freight worker interval is ten minutes; eligibility at120minutes is not a promise of exact execution at that instant. Expired fuel holds are swept every minute in separate retry-safe transactions.

Operational and delivery complaints preserve evidence and notify authorized parties. Only an authorized documented decision may allocate the remaining applicable held funds; no allegation automatically changes public ratings or confiscates reserves. A qualifying accident creates an evidence-based record without an automatic cargo penalty. Liability, forfeiture and recovery beyond approved held amounts require an explicit policy and legal/contractual authority.

Owner-operators retain their Transporter role. Independently verified current driving credentials, an owned/controlled eligible truck and the existing exclusive driver/truck/trip allocation checks are mandatory. A narrowly scoped owner-operator GPS endpoint preserves the Driver portal role boundary. Drivers retain emergency reporting and cannot initiate the standard cancellation request.

## 7. API and frontend inventory

Added or extended APIs:

| Method / endpoint | Behavior |
|---|---|
|GET `/api/business-rules/fees`|Authoritative approved itemized schedule|
|GET `/api/orders/:order/market-reference`|Current comparable mean and trusted caller corridor; selected truck category supported|
|POST `/api/orders/:order/bids` and bid withdrawal|Serialize market mutations, validate pre-insert corridor and save immutable audit|
|Existing order checkout/quote|Full-wallet escrow, exact shortfall, insurance and immutable financial terms; read-only idempotent replays|
|Existing `complete-delivery`|Request Client delivery OTP for new-version bookings|
|GET/POST `/api/orders/:order/trips/:trip/delivery-otp`|Client availability / MPIN-protected reveal|
|POST `/api/orders/:order/trips/:trip/verify-delivery-otp`|Transporter verify and one-time completion/settlement|
|POST `/api/orders/:order/trips/:trip/disputes`|Timely authenticated evidence submission and applicable held-fund freeze|
|POST `/api/admin/freight-settlements/:settlement/resolve`|Evidence-based explicit allocation of remaining held tranche|
|Marketplace create/complete/cancel and Admin refund|Versioned10% fee, itemized settlement and approved cumulative reversals|
|POST `/api/marketplace/admin/orders/:order/refund`|Documented authorized refund/fee reversal with idempotency|
|GET/POST `/api/fuel/vouchers`|Owner-safe list / MPIN-protected capped authorization|
|POST `/api/fuel/vouchers/:voucher/cancel`|Owner release of undispensed authorization|
|POST `/api/fuelstation/vouchers/verify`|Station OTP consumption, pump/type/restriction checks and digital slip|
|POST `/api/fuelstation/vouchers/:voucher/dispense`|Atomic actual charge, inventory, station wallet credit and unused-hold release|
|POST `/api/transporter/drive-myself`|Credential-verified exclusive self-assignment|
|POST `/api/transporter/owner-operator/gps`|Tracking for the actor's current owner-operator assignment|
|POST `/api/admin/owner-operator-credentials/:user`|Documented independent driving-credential verification|
|POST `/api/operational-incidents`|Consented-assignment emergency/accident/abandonment/theft/negligence evidence|
|POST `/api/admin/operational-incidents/:incident/decision`|Authorized investigation result without an invented financial penalty|
|POST `/api/transporter/trips/:assignment/cancellation-request`|Transporter-only initiation; financial cancellation awaits approved policy|
|Existing wallet balance/topup/summary and truck mutations|Driver/Station wallets, exact funding arithmetic, reserve protection/review and tranche-aware reporting|

Frontend work updates Client order placement/detail/checkout, bid markets, Transporter order tracking and agreements, driver assignment/active trip/wallet, Fuel Station POS, Shopkeeper orders, Admin disputes, and shared wallet/security flows. Shared components present approved fee items, insurance, Client OTP inspection/reveal, tranche/dispute timing, capped voucher authorization and digital slips, safety reporting and authorized cancellation requests. The detailed frontend file inventory and evidence are in `BUSINESS_RULES_FRONTEND_2026-10-25.md`.

## 8. Tests and verification evidence

The final machine-readable receipt records exact counts and commands. Suites overlap and must not be added together as unique coverage.

- Current backend collection:1,396test IDs. The latest-receipt union covers all1,396: **1,393passed,0failed/errors,3skipped,0uncovered**. The skips are the deliberately opt-in shared-TEST logout-all, session/device and pending step-up probe matrices; a shared remote harness was not authorized or enabled.
- New Rules1–4 backend coverage: **150passed**:42pricing/fee,28escrow/OTP/settlement,41fuel/credit,15driver/owner-operator,2migration and22legacy future-earnings recovery cases.
- Final wallet-lock/source compatibility run after the last concurrency correction: **198passed** across escrow, legacy recovery, shared payments and order routes.
- Frontend: **91Vitest passed** and **103Node tests passed**. ESLint checked211files with **0errors and2retained Fast Refresh warnings**. Vite production build passed in15.77seconds; its existing Browserslist/large-chunk warnings remain deployment optimization items.
- The completed broad backend run captured1,365cases with1,293passed,69failed and3skipped. Those failures were investigated and superseded by later focused receipts against corrected source. The deduplicated union selects by test run start time. This report therefore does **not** claim a single clean whole-tree rerun; it claims complete current-ID coverage by retained latest receipts.
- The first broad run was interrupted at80% when the local Windows test cluster/session stopped and has no valid final count.
- Historical migration verification:40/40 baseline migrations unchanged. The four new migration bodies exactly match the canonical schema cutover tail. AST parsing passed for180backend Python files; `git diff --check` exited0 (Windows line-ending warnings only).
- The read-only internal Rules1–4 reconciliation passed against an isolated authorize→dispense→earnings-recovery fixture. This verifies internal journal/subledger equations only, not external bank or platform liquidity.
- Financial integration uses uniquely named disposable databases on explicit loopback PostgreSQL. Application DSN is deliberately invalid in test processes. No test falls back to repository database credentials or modifies production data.

Relevant evidence directory: `docs/audit-evidence/2026-10-25/rules-1-4/`. `final-verification.json`, `regression-receipt-union.json`, `final-wallet-lock-regression.xml`, frontend logs, raw broad receipts and superseding focused receipts are retained there. The original frontend evidence names are retained under `docs/audit-evidence/2026-10-25/business-rules-*`.

## 9. Unresolved approvals and unverified integrations

Blocked pending business approval/configuration:

1. Progressive reserve percentage within2–5%, exact approved fleet configurations outside the five reference points, and surplus reserve release.
2. Everyday wallet onboarding and migration from the deliberately card-only role model.
3. Fixed upfront authorization, funding and cancellation/refund rules for variable-distance/monthly agreements.
4. Marketplace COD commission collection and any delivery-fee commission basis; line-level partial handoff/fulfillment policy beyond authorized amount reversals.
5. Trip cancellation financial/refund policy and any penalty, liability cap, rating sanction, pending-payout forfeiture or reserve recovery amount.
6. Independently documented platform treasury funding and current liquidity; migration does not grant credit against a fabricated balance.

Implemented but not fully verified against external systems: actual gateway/payout rails, bank/treasury attestation, SMS transport, license validity, GPS/device evidence, physical dispense quantity, real-world cargo inspection, production tenant/RLS rollout, operational load, and crash-durability behavior. The existing wallet preview uses its legacy default2.5% gateway fee; changing server gateway configuration can differ from that preview. No production-readiness claim is made.

Residual risks include operational collusion between separately valid identities, dishonest physical quantity/price/evidence entry, leakage through infrastructure-level request logging outside application code, unavailable/misconfigured secrets or workers, and pre-existing historical accounting/security work outside Rules1–4. These need deployment-specific controls and verification. Existing historical agreement penalties remain in the historical branch; this work does not create those policies for new blocked agreements.

## 10. Deployment and rollback considerations

No rollout has occurred. Before rollout: back up the approved target; inspect existing active bids for duplicate/unproven rows that cause a migration preflight to abort; verify existing security remediation; validate funding/identity/source snapshots; apply migrations in order in an isolated clone; compare legacy row counts and amount fingerprints; configure an independent OTP secret and approved treasury funding; run internal and external reconciliation; release frontend/backend contracts together; run exactly one owner of the existing legacy agreement jobs. New release/expiry operations are independently retry-safe but the historical agreement scheduler retains its documented single-owner restriction.

Do not roll an old application back over active new-version financial records: it would not understand held tranches, credit reservations or financial terms. Disable affected new writes, retain schema/ledgers, finish or explicitly resolve active authorizations and disputes, and use a reviewed forward corrective migration. Do not drop new ledgers, rewrite old settlements, release surplus reserves or refund a full already-partially-paid fare as an automatic rollback.

## 11. Files and exact Git status

The task-specific inventory and hashes are in `docs/audit-evidence/2026-10-25/rules-1-4/task-source-inventory.md` and `task-source-sha256.json`. They enumerate81source, test, migration, frontend and report paths attributable to this implementation. The exact final `git status --short`, exhaustive porcelain status, branch/HEAD/staging identity and final verification receipt are beside them. The initial observed status is retained in `docs/audit-evidence/2026-10-26-business-rules/initial-git-status.txt`.

The working tree was already substantially dirty. Unrelated pre-existing files—including the existing deletion of `frontend-react/src/pages/transporter/partner_with_us.jsx`, prior security remediation, portal/marketplace work and other untracked artifacts—were preserved and are visible in the exhaustive status; they are not all claimed as Rules1–4 changes.

No files were staged or committed automatically. No push, deployment, remote migration or production financial operation was performed.
