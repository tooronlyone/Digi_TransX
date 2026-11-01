# Order, card settings and list-query verification — 25 October 2026

## Implemented changes

- **BE-05:** Bid withdrawal locks the shipment before its bid, matching checkout's
  resource order, then updates only the authenticated transporter's pending bid
  with compare-and-set `RETURNING`. A closed shipment cannot withdraw a pending
  bid. A bid already accepted remains accepted after a racing withdrawal.
- **FIN-18:** `create_saved_method` synchronizes the preference whenever the first
  card or a newly selected default is saved. Existing auto-shortfall consent is
  preserved. This applies to checkout's direct helper call as well as the saved
  card API.
- Card/default/preference writes use **owner row (`FOR NO KEY UPDATE`) → per-user transaction advisory
  guard → domain rows**. Business checkout takes the guard before shipment, bid,
  truck and wallet locks. The saved-card update, removal and preference routes
  take it before modifying method rows. Repeated helper acquisition in the same
  transaction is safe. This also matches MPIN's existing owner lock and implicit
  user foreign-key key-share locks. This lock grade serializes competing settings
  writers without blocking a wallet writer's implicit owner `FOR KEY SHARE`.
- **PERF-01:** My Orders uses one grouped LEFT JOIN query and retains zero-bid
  orders, excludes withdrawn bids and filters by the authenticated owner.
- **DB-11:** POS sales list reads complete sale rows once and batches all line
  items with `sale_id = ANY(%s)`. It uses one query for an empty list and two
  otherwise. Date/limit validation returns 400 for malformed filters. Response
  fields, item order and ownership filtering are preserved.
- **FIN-08 / FIN-09:** Their previous production fixes remain intact. Admin
  approval locks both request and wallet; seller endpoints require shopkeeper.
  No new admin or marketplace production edit was necessary.

## Current focused results

```text
backend/tests/test_remaining_order_payment_performance.py
backend/tests/test_financial_marketplace_hardening.py::test_admin_approval_cannot_spend_marketplace_or_security_holds
backend/tests/test_financial_marketplace_hardening.py::test_two_admin_requests_cannot_overdraw_same_wallet

21 passed in 36.96s
```

The new module has 18 cases. The other three cases are existing admin reservation
and concurrent approval regressions, including two requests against the same
wallet and a replay of the same approval request.

The new tests use actual Flask authentication, CSRF and PostgreSQL transactions
against disposable loopback databases. Staged bid-withdrawal/checkout tests make
each side win the shipment lock in turn. The losing side never overwrites the
winning bid; payment/trip counts and wallet totals reconcile. List tests compare
0, 1 and 25 records and assert constant domain-query counts plus correct output
and foreign-owner exclusion. Four authenticated non-shopkeeper roles each
exercise all seven seller actions; every action returns 403 before domain SQL.

## Explicit foreign-key deadlock counterexample

The current staged test
`test_mpin_owner_locked_checkout_and_card_creation_have_no_fk_advisory_deadlock`
passes using a real checkout transaction holding the authentication owner and a
concurrent authenticated card-creation request.

An additional process replaced **only in memory** `lock_payment_settings` with
the earlier advisory-only implementation. The same test then failed with real
PostgreSQL `DeadlockDetected` (40P01): checkout held the user row and waited on
the card advisory lock; card creation held that advisory lock and waited on the
user foreign-key lock. This is an intentional counterexample, not a failure of
the current source. No application file was changed for it. The bounded
counterexample completed in 6.01 seconds and used no external provider.

## Owner lock grade versus a concurrent wallet credit

The final additional test,
`test_checkout_owner_guard_allows_existing_wallet_writer_fk_lock`, stages a real
`adjust_wallet_balance` credit holding its wallet before `perform_checkout`
acquires the owner's payment guard and attempts that wallet. The writer then
inserts its ordinary `wallet_transactions` row, which needs the user's foreign-key
`KEY SHARE` lock. With the final `FOR NO KEY UPDATE` owner guard, both transactions
commit: 1000 + 25 credit − 100 checkout = **925**, exactly two wallet transaction
rows, one payment and one trip.

A separate bounded process replaced only the guard in memory with owner
`FOR UPDATE` followed by the same advisory lock. The unchanged regression then
produced actual PostgreSQL `DeadlockDetected` (40P01) in **10.49 seconds**. That
intentional failure is recorded in
[`strong-owner-lock-counterexample.log`](strong-owner-lock-counterexample.log).
No production file or applied SQL migration was changed by the counterexample.
The final corrected 21-case run is in
[`order-payment-performance-final.log`](order-payment-performance-final.log).

This verifies the new payment guard's compatibility with the tested wallet/FK
schedule. It does not downgrade a stronger owner lock already acquired by an
earlier authentication/MPIN operation, and is not proof that every system-wide
authentication and domain lock combination is free of cycles.

## Existing payment and route checks

```text
backend/tests/test_payments.py backend/tests/test_commissions.py
157 passed in 36.18s
```

The lightweight payment-test fixture formerly created wallets and orders without
persisted users. A module-local integration fixture now seeds its four declared
actors (101, 102, 201, 202). Pure calculation tests still require no database.
The production owner guard was retained.

The existing route module initially produced **35 passed, one failed** in
44.49 seconds. Its sole failure was the direct-service concurrent checkout test,
which bypassed login and had never inserted its business owner. One existing
`_seed_user` helper call was added to that fixture; its unchanged concurrency
assertions then passed on current source: **1 passed in 7.22 seconds**. The whole
36-case route module was not repeated after this fixture-only correction.

## Isolation and scope

All commands set `SUPABASE_DB_URL` to the deliberately invalid local port 1 URL,
`DIGITRANSX_ENVIRONMENT=test`, and selected the loopback PostgreSQL 16 runner at
port 15477 with `TEST_SUPABASE_DB_URL`. Each canonical fixture created and removed
its own database. Legacy payment fixtures used uniquely named schemas. Card
providers were in-process simulators; no bank charge, SMTP or Supabase Auth API
operation occurred. Remote SQL rollout is recorded separately by the root task.

These results overlap and are not additive counts of unique coverage. The
legacy fixtures were corrected to satisfy a real owner invariant; no security
check, expected money total or concurrency assertion was weakened.
