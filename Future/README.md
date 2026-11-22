# Future — V2 Deferred Roles

This folder contains V2 reference code for the following deferred roles and features:

- Fuel Station Manager (`fuel_station_manager`)
- Shop Owner / Vendor (`shopkeeper`)
- Transporter truck parts marketplace and shop checkout
- Fuel station voucher authorization and redemption
- AI assistant and chat experience
- Agreemental V1 long-term contracts, bidding, trips, payments and disputes

## Version Status

These roles and features are **not part of Digi TransX V1**.

Their dedicated frontend and backend modules have been moved out of the active
V1 application. V1 imports, routes, signup choices, and visible entry points
were updated separately.

Agreemental is different from the other parked modules: its active V1 database
objects were intentionally removed prior to V1 baseline consolidation by
the archived migration
`Future/supabase/legacy_migrations/20261114010000_retire_agreements_v1.sql`. The
complete pre-removal schema is retained at
`Future/supabase/schema-with-agreements-v1.sql` as a restoration and redesign
reference.

## Agreemental V1 Archive

The parked Agreemental material is grouped as follows:

- `Future/backend/agreements/`: route, helper, admin-route (`admin_routes.py`) and commission-domain code.
- `Future/backend/tests/`: Agreemental-specific notification and commission tests.
- `Future/frontend-react/src/`: client, transporter and admin (`AdminDisputeChat.jsx`, `AdminAgreements.jsx`, `AdminPayments.jsx`) pages, shared map component, future feature placeholders (`pages/future/`, `pages/transporter/future_features/`) and Agreemental styles.
- `Future/frontend-react/tests/`: parked V2 test suites and split assertions (`agreementDatesAndCart.test.mjs`, `assistantPrivacy.test.mjs`, `authShellBootstrapV2.test.mjs`, `shopkeeperReceiptAndPos.test.mjs`, `signupDraftDetailsV2.test.mjs`). Active V1 assertions stay in `frontend-react/tests/`.
- `Future/supabase/schema-with-agreements-v1.sql`: exact full schema snapshot
  from immediately before retirement.

Frontend V2 npm packages removed from active `frontend-react/package.json`:
- `recharts` and `jspdf` (used by Shopkeeper `AnalysisView.jsx`, `SalesAnalyticsPage.jsx`, and `receiptPrinting.js`; reinstall in `frontend-react/` when restoring Shopkeeper V2).

These files are reference code, not a directly runnable package. Shared V1
integrations were deliberately removed from the active app, including route
registration, navigation, dashboard cards, chat links, driver assignments,
fuel vouchers, wallet earnings, scheduler jobs, commission policy publication
and database foreign-key columns.

## Fuel V2 Archive (Pump Manager, Fuel Station, Fuel Credit & Vouchers)

Ordinary V1 Driver Fuel Reporting (`driver_fuel_logs`, `/api/driver/fuel-logs`,
`/api/driver/trips-for-fuel`, and read-only Transporter truck fuel history)
remains active in V1 as informational-only expense and consumption tracking
with **zero wallet, escrow, or credit side effects**.

The deferred V2 Fuel Station & Financing platform is parked in `Future/`:

- `Future/backend/fuelstation/`: Pump Manager dashboard, pump inventory, dispensing POS, and voucher redemption backend.
- `Future/backend/shared/fuel_credit.py`: Complete Fuel Credit & Fuel Voucher financing, authorization, treasury check, dispensing, expiry release, and earnings-recovery engine.
- `Future/backend/tests/`: Parked V2 fuel suites (`test_business_fuel_credit.py`, `test_business_legacy_earnings_recovery.py`, `test_fuel_station_portal.py`, `test_fuel_station_dispense_deferred.py`).
- `Future/frontend-react/src/pages/fuelstation/` & `Future/frontend-react/src/styles/pages/fuelstation.css`: Pump Manager UI and styling.
- `Future/supabase/fuel-v2-reference.sql`: V2-only schema objects (`fuel_station_profiles`, `fuel_station_pumps`, `fuel_station_dispenses`, `fuel_platform_treasury`, `fuel_credit_accounts`, `fuel_vouchers`, `fuel_credit_events`), immutability triggers, RLS/sequence grants, `'fuel_station_manager'` role enum/signup mappings, `freight_settlements.fuel_credit_recovered` column/constraint, and `mpin_step_up_authorizations` `fuel.voucher.authorize` descriptor rule.

To restore Fuel V2 cleanly:

1. Apply V2 Fuel schema additions from `Future/supabase/fuel-v2-reference.sql` via explicit forward migrations (never overwrite populated V1 tables), restore `'fuel_station_manager'` to `app_role`, `handle_new_auth_user()`, and `signup_terms_acceptances`.
2. Restore `Future/backend/shared/fuel_credit.py` into `backend/shared/fuel_credit.py` (NOTE: fix pre-existing `agreement_trip_id` vs `trip_id` variable cleanup around `voucher_details` before enabling) and re-register `fuelstation_blueprint` from `Future/backend/fuelstation/`.
3. Re-enable `FUEL_STATION_ROLES` and `'fuel_station_manager'` profile/wallet role mappings in `backend/shared/roles.py`, `backend/auth/helpers.py`, `backend/auth/signup_terms.py`, and `backend/wallet/helpers.py`.
4. Re-add `"fuel.voucher.authorize"` to `backend/auth/step_up_service.py` `ACTION_POLICIES` and matching `mpin_step_up_descriptor_shape` DB constraint clause.
5. Re-add `run_expire_fuel_vouchers` / `expire_fuel_vouchers_interval` job in `backend/scheduler.py`.
6. Re-connect Fuel Credit recovery hooks in `backend/orders/business_lifecycle.py` (`settle_verified_delivery`), `backend/shared/payments.py` (`release_one_time_payment`, `get_active_payment_for_shipment`), `backend/wallet/routes.py`, `backend/wallet/earnings.py`, and `backend/scripts/reconcile_business_rules.py`.
7. Reconcile `fuel_platform_treasury` liquidity and independent financial ledger checks before opening Fuel V2 to production traffic.

## V2 Plan

When the Digi TransX web application is upgraded for V2, the code in this
folder will be reviewed and gradually updated before being reintroduced into
the active application. The user-moved `AI/` directory is also parked here.

The V2 work should include:

1. Review each role's requirements and user flows.
2. Update the frontend pages, layouts, guards, and responsive experience.
3. Update the backend routes, validation, authorization, and database usage.
4. Reconnect shared authentication, marketplace, fuel credit, wallet, AI, and navigation code.
5. Restore and update the relevant tests.
6. Reintegrate each role incrementally after verification.

For Agreemental V2 specifically:

1. Design a new schema/migration from the archived snapshot; do not reverse the
   destructive retirement migration against a populated production database.
2. Reconnect shared domains explicitly (chat, driver, fuel, wallet, events,
   commissions and notifications) instead of copying old cross-domain columns.
3. Re-audit every object read/write for participant ownership and IDOR/BOLA,
   including nested post, bid, truck, trip, payment and dispute identifiers.
4. Add route-level authorization tests for owner, counterparty, unrelated user,
   admin and missing-object cases before exposing any V2 route.
5. Restore frontend routes/navigation only after the new backend and migration
   have passed those tests.
6. Update `Future/frontend-react/src/pages/transporter/MyAgreements.jsx` so
   `DriverAssignmentPanel` supports agreement-trip IDs (V1 `DriverAssignmentPanel`
   accepts `tripId` only).

## Shopkeeper / Marketplace V2 & Legacy Migration Archive

- `Future/supabase/shopkeeper-marketplace-v2-reference.sql`: Preserved V2-only Shopkeeper & Truck Parts Marketplace schema objects (`shopkeeper_profiles`, `marketplace_parts`, `marketplace_orders`, `marketplace_order_items`, `part_rfqs`, `part_rfq_bids`, `shop_products`, `shop_sales`, `shop_sale_items`), constraints (`marketplace_*`, `wallet_transactions_marketplace_leg`), triggers (`preserve_marketplace_fee_snapshot`, `prevent_marketplace_financial_mutation`), and `'shopkeeper'` role enum/signup mappings excluded from the active V1 baseline.
- `Future/backend/tests/test_shopkeeper_pos_deferred.py`: Parked V2 Shopkeeper POS tests extracted cleanly from active V1 tests.
- `Future/supabase/legacy_migrations/`: All 49 historical incremental migrations archived outside the active installation chain so `supabase/migrations/20261116000000_digitransx_v1_baseline.sql` serves as the single atomic fresh-install V1 baseline.
  - To restore Shopkeeper / Marketplace in V2: apply forward migrations derived from `Future/supabase/shopkeeper-marketplace-v2-reference.sql`, add `'shopkeeper'` back to `app_role`, `handle_new_auth_user()`, `signup_terms_acceptances`, `LEGACY_TO_APP_ROLE`, `SHOPKEEPER_ROLES`, and `FEE_COMPONENTS['marketplace']`, and restore the frontend Shopkeeper routes and packages (`recharts`, `jspdf`).

Until that V2 work begins, files under `Future/` should be treated as parked
reference code and should not be imported by the V1 application.
