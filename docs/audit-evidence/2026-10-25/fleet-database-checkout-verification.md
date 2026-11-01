# Fleet, database and checkout verification — 25 October 2026

The final selected integration runs below use disposable loopback PostgreSQL 16
databases, real database constraints/row locks, actual Flask authentication and
CSRF, and fake external boundaries. They do not connect the application under
test to the shared Supabase project. The authorized remote migration operation
is recorded separately in [database-rollout.json](database-rollout.json).

Commands ran from `backend` with `py -3.10 -m pytest -q` and:

```powershell
$env:TEST_SUPABASE_DB_URL='postgresql://audit_local@127.0.0.1:15477/dtx_phase1b2c0_baseline_correction'
$env:SUPABASE_DB_URL='postgresql://audit:audit@127.0.0.1:1/invalid?connect_timeout=1'
$env:DIGITRANSX_ENVIRONMENT='test'
```

These credentials identify only the synthetic local runner. They are not
Supabase credentials. Its reduced durability configuration is suitable for
constraint/concurrency testing, not evidence of crash durability.

## Fleet, driver and schema selection

```text
tests/test_database_authorization_hardening.py
tests/test_driver_workflow_hardening.py
tests/test_fleet_consent_database.py

114 passed in 114.94s
```

The selection consists of 64 fresh/upgrade/replay authorization checks, 32 driver
workflow cases and 18 fleet/provenance/legacy-upgrade cases. The last group covers
five forbidden truck-creator roles, both transporter aliases, ignored forged
driver identity at creation, preserved consent-derived configuration identity,
direct SQL review/incident provenance, false completion without consent, legacy
reputation/link reconciliation, refusal of unproven legacy active consent, and
default-card convergence with consent preservation/replay.

The full final run has no failures or skips. Earlier failed setup attempts,
including a stopped runner, are not counted as successful checks. An existing
wallet-upgrade fixture was corrected to locate its specific immutable migration
by filename after this batch appended two migrations; no product invariant was
relaxed. [Raw final result](fleet-database-driver.log).

## Checkout account binding and retained route integrity

```text
tests/test_marketplace_checkout_identity.py
tests/test_coordinate_integrity.py
tests/test_premerge_route_security.py

81 passed in 32.58s
```

Nine account-header cases exercise the real authenticated boundary. A missing
or malformed `X-DTX-Expected-User-Id` returns 400, and an old account's ID paired
with a new account's authenticated cookies and valid CSRF returns 409. Rejections
occur before marketplace domain SQL. A matching account reaches a controlled
service replacement: that case proves the transport boundary, while separate
financial tests exercise stock/funds/settlement integrity.

The other 72 cases retain coordinate and premerge route protections. No skipped
case is counted as passed. [Raw final result](checkout-identity-compatibility.log).

## Scope of the evidence

These selections overlap other focused runs and cannot be added to their totals
as unique coverage. No second whole-backend suite run is claimed. No physical
delivery, device GPS hardware, real card charge, email delivery or production
load measurement was performed. See the separate payment and frontend receipts
and the [remediation record](../../SECURITY_REMEDIATION_2026-10-25.md).
