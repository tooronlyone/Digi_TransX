# Future — V2 Deferred Roles

This folder contains V2 reference code for the following deferred roles and features:

- Fuel Station Manager (`fuel_station_manager`)
- Shop Owner / Vendor (`shopkeeper`)
- Transporter truck parts marketplace and shop checkout
- Fuel station voucher authorization and redemption
- AI assistant and chat experience

## Version Status

These roles and features are **not part of Digi TransX V1**.

Their dedicated frontend and backend modules have been moved out of the active
V1 application. V1 imports, routes, signup choices, and visible entry points
were updated separately. Historical financial records and shared database
schema remain available so existing transactions can still be interpreted.

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

Until that V2 work begins, files under `Future/` should be treated as parked
reference code and should not be imported by the V1 application.
