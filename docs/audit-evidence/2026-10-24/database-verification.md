# Database remediation verification — 2026-10-24

The owner explicitly designated the configured Supabase project
`fysupkvuvhvtowbfgoev` as a testing database and authorized its use for this work.
No application credentials or database row contents are stored in this record.

## Applied forward migrations

1. `20261024010000_database_authorization_hardening.sql`
2. `20261024020000_marketplace_financial_controls.sql`
3. `20261024030000_private_operational_read_surfaces.sql`
4. `20261024040000_validate_wallet_money_invariants.sql`

Their SHA-256 hashes, application timestamps, row-count comparisons and role
probes are recorded in [database-hardening-rollout.json](database-hardening-rollout.json).
The canonical `supabase/schema.sql` mirrors these files for fresh installations.
All migration files were preserved byte-for-byte after their application.

## Local PostgreSQL regression

```text
py -3.10 -m pytest backend/tests/test_database_authorization_hardening.py -q --tb=short
64 passed in 37.01s
```

Tests used only a loopback PostgreSQL16 instance on port15477 and disposable
child databases. `SUPABASE_DB_URL` was deliberately pointed at an invalid local
address for the test process. Proofs cover fresh snapshot construction, upgrade
from the feature baseline, repeat application, preserved administrator identity,
safe handling of the manually-created hire-contract table, legacy column grants,
signup metadata, authorization-sensitive profile writes, all backend-only table
ACLs, accidental read regrants, chat-thread membership, agreement policy recursion,
wallet invariants, checkout idempotency and backend-only delivery secrets. A
legacy invalid-wallet fixture also proves validation aborts without rewriting
money, leaving the invalid historical row available for explicit reconciliation.

## Remote TEST verification

- Final catalogue inspection:68 public tables, all68 with RLS enabled,112 public
  RLS policies, and19 backend-only tables with browser SELECT/INSERT/UPDATE/DELETE
  denied and explicit `service_role` privileges preserved.
- The first pair of migrations preserved all67 pre-existing table row counts and
  user `id/auth_id/role/legacy_role` bindings. The new delivery-secret table raised
  the public table count to68. One previously exposed plaintext delivery OTP was
  invalidated; no identity was relinked or promoted.
- The third migration preserved all68 table row counts and the same identity
  bindings. Raw vehicle identity/tracker data, agreement truck terms, RFQ exact
  locations and dependent RFQ bids are backend-only.
- Direct `anon` and `authenticated` reads of private driver profiles and delivery
  secrets, and direct `legacy_role` updates, were denied with PostgreSQL42501.
- Direct `anon` and `authenticated` SELECTs on `vehicles`,
  `agreement_post_trucks`, `agreement_bid_trucks`, `part_rfqs` and `part_rfq_bids`
  were denied with42501. Explicit column reads were also revoked.
- `service_role` retains SELECT/INSERT/UPDATE/DELETE plus explicit RLS policies;
  the local service-role proofs do not depend on BYPASSRLS.
- Participant reads on `agreements` and `agreement_trucks` complete without RLS
  recursion. Their security-definer bridge has a fixed `pg_catalog` search path
  and is not callable by `anon`.

The wallet money-invariant constraint initially used `NOT VALID` to avoid silently
rewriting pre-existing balances. The fourth forward migration validated every
existing wallet after a fresh remote preflight found zero violating rows. The
constraint now has `convalidated=true`. Wallet row counts and a hash of all wallet
identities, balances, reserved amounts and minimum requirements were identical
before and after validation. No existing amount was changed.
