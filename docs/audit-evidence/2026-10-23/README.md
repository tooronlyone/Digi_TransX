# Digi_TransX audit evidence — 23–24 October 2026

These are synthetic local/offline audit artifacts supporting `PROJECT_AUDIT_REPORT.md`. They do not contain a dump of production data or production credentials. Application source was not repaired by this audit. The PostgreSQL cluster used for the audit was isolated on loopback port 15477 and is stopped after verification.

Run the following **from the repository root** with the existing Python 3.10 packages and frontend dependencies. They intentionally reproduce defects in the audited source and will need changes when those defects are fixed:

```powershell
py -3.10 docs/audit-evidence/2026-10-23/financial_probes.py
py -3.10 docs/audit-evidence/2026-10-23/root_probes.py
py -3.10 docs/audit-evidence/2026-10-23/db_python_proofs.py
node docs/audit-evidence/2026-10-23/frontend_proof.mjs
```

The Python probes force an unusable database URL or extract source functions into fake contexts; frontend probes use Node/JSDOM and fake storage. Expected Flask error logs in root_probes demonstrate handled service failures and an intentional malformed-request HTTP500. No SMTP/provider or configured Supabase connection is needed.

`db_bootstrap.sql` deliberately installs synthetic Auth/Storage stubs and broad representative client grants to test policy behavior. **Run it only against a brand-new disposable PostgreSQL cluster/database**, from the repository root with psql ON_ERROR_STOP. Roles are cluster-global; the bootstrap is not idempotent and is not a deployment migration. Apply db_proofs.sql only to that synthetic database. Logs show local outcomes; actual remote grants/public signup may differ. `db_validate_fixes.sql` is another disposable-copy validation script, not a production release script.

`ledger_design.sql` is the proposed complete ledger foundation from section 6. `ledger_probes.py` expects a new empty local database named audit_ledger_validation_final on 127.0.0.1:15477, user audit_local, and existing anon/authenticated roles. It creates tables and synthetic accounts; it is intentionally not safe to run in an application database and does not provision/restart PostgreSQL itself. The preserved output demonstrates balance/replay/overdraft/history checks, including rejection of appending to an already committed journal.

`targeted_tests.log` records the prefix-eligible run: 257 passed and 7 failed. `integration_failure.log` documents why the earlier generic database name was ineligible for several suites. The earlier broad run had 798 passed, 47 failed, 3 skipped and 129 setup errors; those failing/error totals are not a count of confirmed product defects. The independent no-database run produced 411 passed, 559 skipped and 7 failed. Unsafe application-database tests were excluded from all suite execution.

`frontend_lint.json` is the source/config-only ESLint output (69 errors, 24 warnings). `npm_advisories.json` reports zero known production npm advisories at query time. `report_manifest.json` records finding counts and validated primary source ranges; `source_hashes.json` records the audited authored Python/frontend/SQL source bytes. A passing dependency advisory query or parser is not a proof of application security.
