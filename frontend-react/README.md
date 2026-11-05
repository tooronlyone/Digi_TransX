# Digi_TransX frontend

## Local development

Start the Flask backend from the repository root:

```powershell
py -3 -m backend.app
```

Then start the React development server from this directory:

```powershell
npm install
npm run dev
```

The development server uses the real Flask API by default and proxies `/auth`,
`/api`, uploads, truck, job, and AI routes to `http://localhost:5000`. A fresh
clone therefore works without setting `VITE_USE_MOCK_API`.

Mock mode is opt-in. Enable it only when intentionally developing without the
Flask API:

```powershell
$env:VITE_USE_MOCK_API='true'
npm run dev
```

Unset that environment variable before returning to normal development.
