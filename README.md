# Digi_TransX 🚚

**Pakistan's Digital Transport & Logistics Marketplace**

Digi_TransX is a full-stack web platform that connects **clients (shippers)** who need goods transported with **transporters (truck owners / logistics providers)** across Pakistan. It covers the complete logistics lifecycle: posting a load, competitive bidding, smart truck matching, live GPS trip tracking, delivery verification, digital wallet payments, invoicing, and long-term transport agreements — all inside one application.

Digi_TransX is the first product of **D-HAG (Digital Human Harmony AI Grid)** — [d-hag.com](https://d-hag.com).

---

## Table of Contents

1. [What the Platform Does](#what-the-platform-does)
2. [User Roles](#user-roles)
3. [Core Features](#core-features)
4. [How a Shipment Works (Process Flow)](#how-a-shipment-works-process-flow)
5. [Technology Stack](#technology-stack)
6. [Project Structure](#project-structure)
7. [Backend Modules (API)](#backend-modules-api)
8. [Database](#database)
9. [Running the Project](#running-the-project)
10. [Configuration (Environment Variables)](#configuration-environment-variables)
11. [Tests](#tests)
12. [Future Features](#future-features)

---

## What the Platform Does

Traditional goods transport in Pakistan runs on phone calls, brokers, and guesswork. Digi_TransX digitizes the entire process:

- A client posts **what** they need moved (with a structured goods taxonomy — category, form, commodity, weight, volume, dimensions, temperature, special handling), **from where to where**, and **when**.
- The platform's **smart truck matching** suggests which truck types fit the load (refrigerated, flatbed, container, livestock, tanker, etc.).
- Verified transporters place **competitive bids** with their registered trucks.
- The client accepts a bid; payment is secured through the platform's **digital wallet** system.
- The trip runs with **GPS tracking** (Traccar integration), and delivery is confirmed through a **two-sided verification** process, with admin arbitration for disputes.
- On completion, the platform generates a **PDF invoice**, deducts its company fee, and credits the transporter's wallet. Transporters withdraw earnings through admin-approved withdrawal requests.
- For recurring needs, clients can post **long-term agreements** (monthly contracts with per-km rates and minimum monthly guarantees) instead of one-off orders.

## User Roles

| Role | Who they are | What they can do |
|---|---|---|
| **Client / Service Seeker** | Businesses & individuals who need goods moved | Post orders & agreements, review bids, pay via wallet, track shipments, chat, confirm delivery |
| **Transporter / Logistics Provider** | Truck owners & fleet operators | Register trucks (with documents), browse open orders, place bids, run trips, earn & withdraw |
| **Platform Admin** | D-HAG operations team | Manage users/trucks, approve withdrawals, resolve disputes, oversee payments & agreements |
| **Fuel Station Manager** *(onboarding exists)* | Petrol pump operators | Partner ecosystem role (future expansion) |
| **Shopkeeper** *(module exists)* | Small retailers | POS, inventory & sales analytics module (companion product area) |

Each role has its own registration flow, dashboard, and permissions.

## Core Features

### 🧾 Orders (Spot Marketplace)
- Structured order posting: pickup/dropoff city, area, exact location + map coordinates, date & time
- **Goods taxonomy** (state → commodity): category, form, commodity, weight (tons), volume (cbm/liters), dimensions (L×W×H), quantity, animal count, temperature requirement
- Special handling flags: refrigerated, hazardous, food-grade, fragile
- **Smart truck matching**: order requirements automatically matched against truck capabilities (payload range, bed dimensions, body style, refrigeration/hazmat support)
- Budget estimation, bid comparison, accept/reject flow
- Order cancellation with refund/penalty rules
- No-show tracking with automatic notifications and escalation

### 🚛 Truck / Fleet Management
- Truck registration with company, model, type (from a truck catalog), chassis number, capacity, bed dimensions, operating provinces
- Pricing setup: per-km rate, waiting charge per hour, loading charge
- Document uploads: truck photo, insurance, RC book
- Truck status lifecycle (inactive → active, with admin reason codes)
- Driver details (name, CNIC) per truck
- Live tracking via **Traccar** GPS device integration

### 📄 Agreements (Long-Term Contracts)
- Clients post agreement requirements (cargo type, service area, truck types & quantities)
- Transporters bid with specific trucks, per-km rates, and **minimum monthly guarantees**
- Auto-generated contract text; multi-truck, multi-transporter agreements
- Trip logging under agreements with GPS start/end points and distance calculation
- **Monthly billing engine** (scheduler): total km × rate vs. minimum guarantee, company fee deduction, payment due dates, and automatic **late-payment penalties**

### 💰 Wallet & Payments
- Per-user digital wallet with balance, locked (escrow) balance, and role-based minimum balance requirements
- Full transaction ledger (deposits, order payments, earnings, fees, refunds, penalties)
- Escrow model: client's payment locks on bid acceptance, releases to transporter after delivery verification
- Company fee automatically deducted on every completed trip
- Withdrawal requests with **tier-based limits** and admin approval
- Payout card details on profile
- **PDF invoice generation** for every completed order

### 📍 Tracking & Verification
- Live truck location via Traccar GPS devices
- Trip lifecycle: accepted → started → completed → delivery confirmed
- Two-sided delivery verification (transporter claims → client responds, twice) with **admin arbitration** for disputes
- Actual distance capture for billing

### 💬 Chat & Notifications
- Client ↔ transporter messaging per agreement post/bid
- Media sharing with request/approval flow
- **Group dispute chats** including an admin
- Read receipts, unread counts, order & trip notifications

### 🛡️ Admin Panel
- Dashboard with platform statistics
- User management (view, block/unblock with reason)
- Truck approval & management
- Withdrawal request processing
- Dispute resolution (trip verification decisions, km approval, penalty assignment)
- Agreement & payment oversight
- Login activity and user action audit logs

### 🔐 Authentication & Security
- Email/password signup with role-specific onboarding steps
- OTP-based password reset with attempt limits and cooldowns
- **MPIN quick-unlock** and trusted device management
- Session security (HttpOnly, SameSite cookies)
- Login activity logging (IP, user agent, failure reasons)

## How a Shipment Works (Process Flow)

```
CLIENT                        PLATFORM                      TRANSPORTER
------                        --------                      -----------
Post order with goods   →     Smart truck matching     →    Sees matching open orders
details & budget              (type/capacity/flags)
                                                      ←     Places bid (truck + price)
Reviews bids, accepts   →     Locks payment in wallet  →    Bid accepted → trip created
                              (escrow)
                                                      ←     Starts trip (GPS tracked)
Tracks shipment live          Traccar location feed   ←     Completes trip, claims delivery
Confirms delivery       →     Verification (2-step,
                              admin if disputed)
                              Releases payment:
                              company fee → platform
                              remainder → transporter wallet
                              PDF invoice generated
                                                      ←     Withdraws earnings (admin approved)
```

## Technology Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, Vite 8, React Router 7, Tailwind CSS 3, Recharts (charts), Leaflet (maps), Font Awesome |
| **Backend** | Python Flask (modular blueprints), background scheduler for monthly billing |
| **Database** | **Supabase PostgreSQL** (psycopg2 connection pool, Row Level Security) |
| **GPS Tracking** | GPS provider integration (Traccar-style, stub until provider credentials) |
| **Auth** | **Supabase Auth** (email/password) + Flask sessions, OTP reset flow, MPIN quick-unlock |
| **Files** | **Supabase Storage** — private `shipment-documents` bucket (truck docs, chat media) |

The production build serves the React app **from Flask** (single deployment): `frontend-react/dist` is served by `backend/app.py`.

## Project Structure

```
Digi_TransX/
├── backend/
│   ├── app.py                  # Flask entry point — registers all blueprints, serves React build
│   ├── scheduler.py            # Background jobs (monthly agreement billing, penalties)
│   ├── requirements.txt        # Python dependencies
│   ├── shared/db.py            # PostgreSQL access layer (psycopg2 pool -> Supabase)
│   ├── shared/supabase_client.py # Supabase Auth clients (service role + anon)
│   ├── shared/storage.py       # Supabase Storage helpers (shipment-documents bucket)
│   ├── auth/                   # Signup, login, OTP reset, MPIN, trusted devices
│   ├── admin/                  # Admin panel APIs (users, trucks, withdrawals, disputes)
│   ├── orders/                 # Spot orders, bids, trips, verification, invoices
│   │   └── goods_taxonomy.py   # Structured goods classification & truck matching rules
│   ├── agreements/             # Long-term contracts, bids, trips, monthly payments
│   ├── trucks/                 # Truck registration, catalog, documents, status
│   ├── wallet/                 # Balances, transactions, withdrawals, tier limits
│   ├── chat/                   # Messaging threads, media, dispute group chats
│   ├── tracking/               # Traccar GPS integration
│   ├── profile/                # User profile management
│   ├── settings/               # User settings
│   ├── tests/                  # Unit + PostgreSQL integration tests (commission policies)
│   └── scripts/
│       └── create_admin.py     # Bootstrap a platform admin account (Supabase Auth)
├── frontend-react/
│   └── src/pages/
│       ├── auth/               # Login, signup, role selection, role-detail steps, unlock
│       ├── client/             # Client dashboard, post order/agreement, bids, wallet, chat
│       ├── transporter/        # Transporter dashboard, trucks, bids, earnings, tracking
│       ├── admin/              # Admin dashboard, users, trucks, withdrawals, disputes
│       ├── shopkeeper/         # POS / inventory / sales analytics module
│       ├── org/                # Organization portal (admin / partner / departments)
│       └── shared/             # Shared components (AI chat, etc.)
├── .env.example                # Environment template (Supabase keys, SMTP, Flask)
└── supabase/
    ├── schema.sql              # Supabase PostgreSQL schema (tables, triggers, RLS, storage)
    └── migrations/             # Dated schema migrations for existing deployments
```

## Backend Modules (API)

All APIs are JSON over HTTP, organized as Flask blueprints:

| Module | Responsibility |
|---|---|
| `auth` | Registration (role-specific), login, logout, OTP password reset, MPIN unlock, trusted devices |
| `orders` | Order CRUD, goods taxonomy validation, truck matching, bids, trip lifecycle, delivery verification, no-show tracking, cancellations, notifications, invoices |
| `agreements` | Agreement posts, truck requirements, bids with per-truck rates, contract creation, trip logging, monthly payment generation, penalties |
| `trucks` | Truck registration/edit, catalog types & specs, document uploads, status management, Traccar device linking |
| `wallet` | Balance & ledger, deposits, escrow lock/release, withdrawal requests, tier limits |
| `chat` | Threads, messages, media requests, dispute group chats, read state |
| `tracking` | Live GPS positions from Traccar, trip distance |
| `admin` | Platform stats, user/truck management, withdrawal approval, dispute decisions |
| `profile` / `settings` | Profile data, payout card, preferences |

## Database

**Supabase PostgreSQL** — full schema in [supabase/schema.sql](supabase/schema.sql) (~35 tables, with Row Level Security, triggers, and the Storage bucket). The backend connects through a psycopg2 connection pool ([backend/shared/db.py](backend/shared/db.py)).

Main table groups:

- **Identity**: `users` (core identity only, linked to Supabase Auth) + per-role profile tables — `customers` (business = daily service seekers with history, individual = occasional everyday users), `transporter_profiles` (fleet, withdrawal tier, payout card), `fuel_station_profiles` & `shopkeeper_profiles` (future features, clean from day one) — plus `login_activity`, `password_reset_otps`, `reset_tokens`, `trusted_devices`, `user_action_logs`
- **Fleet**: `vehicles` (40+ columns: specs, pricing, documents, status, GPS), `drivers`
- **Marketplace**: `shipments`, `shipment_bids`, `shipment_trips`, `shipment_trip_verification`, `shipment_no_show_tracking`, `shipment_cancellations`, `shipment_notifications`, `shipment_status_history` (automatic audit trail), `payments`
- **Agreements**: `agreement_posts`, `agreement_post_trucks`, `agreement_bids`, `agreement_bid_trucks`, `agreements`, `agreement_trucks`, `agreement_trips`, `agreement_monthly_payments`, `agreement_payment_penalties`
- **Money**: `wallets`, `wallet_transactions`, `wallet_withdrawal_requests`
- **Communication**: `chat_threads`, `chat_messages`
- **Files**: `documents` (metadata for the private `shipment-documents` Storage bucket)

**Row Level Security roles:** admin (full access) · customer (own shipments only) · transporter (own fleet, bids, assigned trips). The Flask backend itself uses the service role.

Schema changes for existing deployments live as dated files in [supabase/migrations/](supabase/migrations) and are applied with `supabase db push` or the SQL Editor.

## Running the Project

### Prerequisites
- Python 3.10+
- Node.js 18+
- A Supabase project (free tier works)

### 1. Supabase setup (one time)

1. Create a project at [supabase.com](https://supabase.com) and enable **Email** auth
   (Authentication → Providers → Email; disable "Confirm email" since the backend creates confirmed users).
2. Open the SQL Editor and run the whole of [supabase/schema.sql](supabase/schema.sql) —
   it creates all tables, triggers, Row Level Security policies, and the `shipment-documents` Storage bucket.
3. Copy `.env.example` to `.env` in the project root and fill in `SUPABASE_URL`,
   `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_DB_URL`.

### 2. Backend (Flask)

```bash
cd backend
pip install -r requirements.txt
python app.py
# Runs at http://127.0.0.1:5000
```

Create an admin account:

```bash
python backend/scripts/create_admin.py --email admin@example.com --password YourPassword123
```

### Frontend (React, development)

```bash
cd frontend-react
npm install
npm run dev
# Vite dev server (proxies API calls to Flask — see vite.config.js)
```

### Production build

```bash
cd frontend-react
npm run build
# Flask automatically serves frontend-react/dist at http://127.0.0.1:5000
```

## Configuration (Environment Variables)

All configuration lives in `.env` (project root) — see [.env.example](.env.example) for the full template.

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Public API key (used only to verify passwords at login) |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side key — Auth admin operations + Storage (keep secret!) |
| `SUPABASE_DB_URL` | Postgres connection string used by the backend pool |
| `SUPABASE_STORAGE_BUCKET` | Storage bucket name (default `shipment-documents`) |
| `APP_TIMEZONE` | Timezone for app timestamps (default `Asia/Karachi`) |
| `FLASK_SECRET_KEY` | Session signing key — **must change in production** |
| `FLASK_HOST` / `FLASK_PORT` / `FLASK_DEBUG` / `FLASK_ENV` | Flask server settings |
| `DIGITRANSX_SMTP_*` | SMTP settings for OTP / password-reset emails |
| `TEST_SUPABASE_DB_URL` | **Tests only** — connection string of a dedicated PostgreSQL test database for the integration tests (never point this at the application database) |

## Tests

The backend test suite lives in [backend/tests/](backend/tests):

- **Unit tests** (calculation, validation, business rules) run with no database.
- **PostgreSQL integration tests** (commission policy versioning, Terms,
  acknowledgements, generated-key and conflict handling) run against a
  dedicated test database configured via `TEST_SUPABASE_DB_URL`. They create
  an isolated, uniquely named schema for the session and drop it afterwards.
  If `TEST_SUPABASE_DB_URL` is not set, these tests are skipped with a clear
  reason — they never fall back to `SUPABASE_DB_URL`.

```bash
cd backend
python -m pytest tests                          # unit tests (+ skips)
TEST_SUPABASE_DB_URL=postgresql://... python -m pytest tests   # full suite
```

## Future Features

Prepared in the codebase (`transporter/future_features/`):

- Fleet analytics & predictive insights
- Fuel management
- Maintenance scheduling
- Customer ratings
- Organization/department management
- Transporter leaderboard & service history

---

## About D-HAG

**D-HAG (Digital Human Harmony AI Grid)** builds technology that brings digital harmony to traditional industries. Digi_TransX is D-HAG's first product, targeting Pakistan's fragmented goods-transport market.

🌐 [d-hag.com](https://d-hag.com)

---

*© D-HAG. All rights reserved.*
