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
objects are intentionally removed by
`supabase/migrations/20261114010000_retire_agreements_v1.sql`. The complete
pre-removal schema is retained at
`Future/supabase/schema-with-agreements-v1.sql` as a restoration and redesign
reference.

## Agreemental V1 Archive

The parked Agreemental material is grouped as follows:

- `Future/backend/agreements/`: route, helper and commission-domain code.
- `Future/backend/tests/`: Agreemental-specific notification and commission tests.
- `Future/frontend-react/src/`: client, transporter and admin pages, shared map
  component and Agreemental styles.
- `Future/frontend-react/tests/agreementDatesAndCart.test.mjs`: the original
  mixed Agreemental/calendar test; active cart-only coverage was kept in V1.
- `Future/supabase/schema-with-agreements-v1.sql`: exact full schema snapshot
  from immediately before retirement.

These files are reference code, not a directly runnable package. Shared V1
integrations were deliberately removed from the active app, including route
registration, navigation, dashboard cards, chat links, driver assignments,
fuel vouchers, wallet earnings, scheduler jobs, commission policy publication
and database foreign-key columns.

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

Until that V2 work begins, files under `Future/` should be treated as parked
reference code and should not be imported by the V1 application.
