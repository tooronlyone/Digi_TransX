# Local Auth Refresh Tracing

This guide prepares disposable local data for browser refresh tracing. It is for evidence gathering only and must not be used with remote Supabase.

## Files

- `backend/scripts/local_auth_refresh_setup.py` seeds three local auth states and writes browser cookie values to JSON.
- `tools/auth_refresh_trace.mjs` uses Playwright to open `/transporter/dashboard` with those cookies and records the request timeline.

## Safety Rules In The Seeder

The setup script refuses to run unless all of these are true:

- The database URL host is `localhost`, `127.0.0.1`, or `::1`.
- The database name starts with `dtx_trace_`, `dtx_auth_trace_`, `dtx_phase1b2c0_`, or `dtx_local_`.
- `DIGITRANSX_ENVIRONMENT` is `local` or `test`.
- `DIGITRANSX_MPIN_PEPPER` exists and decodes to exactly 32 bytes.
- The provided local tracing DB URL is not equal to `SUPABASE_DB_URL`.

The Playwright trace script also refuses non-loopback app URLs.

## PowerShell Commands

Start disposable Postgres:

```powershell
docker run --name dtx-auth-trace-pg --rm -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=dtx_auth_trace_refresh -p 55432:5432 postgres:16
```

In a new PowerShell window, set local-only environment variables:

```powershell
$env:LOCAL_AUTH_TRACE_DB_URL = "postgresql://postgres:postgres@127.0.0.1:55432/dtx_auth_trace_refresh"
$env:DIGITRANSX_ENVIRONMENT = "local"
$env:DIGITRANSX_MPIN_PEPPER = [Convert]::ToBase64String(([byte[]](1..32)))
$env:FLASK_SECRET_KEY = "local-refresh-tracing-only-secret-change-me"
```

Prove the DB target is local before seeding:

```powershell
py -c "from urllib.parse import urlparse; import os; u=urlparse(os.environ['LOCAL_AUTH_TRACE_DB_URL']); print(u.hostname, u.path.lstrip('/'))"
```

Seed schema and test states:

```powershell
py backend/scripts/local_auth_refresh_setup.py --db-url $env:LOCAL_AUTH_TRACE_DB_URL --reset-schema --schema-mode full --output backend/scripts/seed_output/local_auth_refresh_trace.json
```

If the full Supabase schema cannot load into plain Postgres, retry the minimum auth/session schema:

```powershell
py backend/scripts/local_auth_refresh_setup.py --db-url $env:LOCAL_AUTH_TRACE_DB_URL --reset-schema --schema-mode minimal --output backend/scripts/seed_output/local_auth_refresh_trace.json
```

For backend runtime, explicitly point the app at the same local database in that shell:

```powershell
$env:SUPABASE_DB_URL = $env:LOCAL_AUTH_TRACE_DB_URL
$env:DIGITRANSX_ENVIRONMENT = "local"
$env:DIGITRANSX_MPIN_PEPPER = [Convert]::ToBase64String(([byte[]](1..32)))
$env:FLASK_SECRET_KEY = "local-refresh-tracing-only-secret-change-me"
py backend/app.py
```

For frontend runtime:

```powershell
cd frontend-react
npm run dev
```

Run a browser trace after backend and frontend are running:

```powershell
node tools/auth_refresh_trace.mjs --cookies backend/scripts/seed_output/local_auth_refresh_trace.json --state A --base-url http://127.0.0.1:5173 --out traces/auth-refresh-A.json
node tools/auth_refresh_trace.mjs --cookies backend/scripts/seed_output/local_auth_refresh_trace.json --state B --base-url http://127.0.0.1:5173 --out traces/auth-refresh-B.json
node tools/auth_refresh_trace.mjs --cookies backend/scripts/seed_output/local_auth_refresh_trace.json --state C --base-url http://127.0.0.1:5173 --out traces/auth-refresh-C.json
```

If Playwright is not installed in the workspace, install it only for local tracing under the existing frontend package:

```powershell
cd frontend-react
npm install --no-save playwright
cd ..
```

## Seeded Test States

- `A_valid_session_valid_access_proof_mpin`: transporter session, trusted device, valid access proof cookie, MPIN set.
- `B_valid_session_missing_access_proof_mpin`: transporter session and trusted device, access proof exists in DB but no browser proof cookie, MPIN set.
- `C_valid_session_missing_access_proof_no_mpin`: transporter session and trusted device, access proof exists in DB but no browser proof cookie, no MPIN credential.

The JSON output contains local disposable cookie values for `dtx_device_token`, `dtx_session_token`, and, for state A only, `dtx_access_proof`.

## Minimal Schema Coverage

The full schema mode is preferred because it lets non-auth startup requests hit the same tables they use in the app. Minimal mode exists only as a fallback for auth refresh tracing. In minimal mode, unrelated startup endpoints may fail because their application tables are intentionally absent.

## Checklist Before Runtime Tracing

- `LOCAL_AUTH_TRACE_DB_URL` host prints as `127.0.0.1`, `localhost`, or `::1`.
- DB name starts with a disposable prefix such as `dtx_auth_trace_`.
- `SUPABASE_DB_URL` is either unset or explicitly equal to the local tracing DB only in the backend shell.
- Root `.env` has not been edited and is not used by the seeding script.
- `DIGITRANSX_ENVIRONMENT` is `local` or `test`.
- `DIGITRANSX_MPIN_PEPPER` is set to a dummy 32-byte base64 value.
- Docker container name and port are local to this tracing run.
- The browser trace base URL is loopback.
