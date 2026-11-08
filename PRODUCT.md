# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are registered commercial drivers working from an assigned vehicle or awaiting dispatch. They use the portal to review trip requests, run an active trip with GPS updates, track fuel records, monitor wallet activity and reputation, and maintain their driver profile.

## Product Purpose

Digi_TransX connects freight clients, transport operators, and drivers in one logistics workflow. The driver portal gives an individual driver a focused workspace for accepting work, completing assigned trips, recording operational evidence, and understanding earnings and trust status.

## Positioning

The driver experience is not a generic fleet dashboard: it is the operational handoff between a transporter's dispatch decision and a driver's verified delivery, with trip, GPS, fuel, wallet, and reputation context kept together.

## Operating Context

Drivers may use the portal from a phone while on the road and from a laptop or desktop while reviewing records. Important states include no assignment, pending trip request, accepted/active trip, completed trip, GPS permission or update failure, empty transaction or fuel history, and profile verification status.

## Capabilities and Constraints

- Existing React routes, API contracts, data fields, actions, and security guards must remain functional.
- Driver routes cover dashboard, active trip and GPS, trip requests, fuel and diesel logs, wallet, reputation, and profile.
- Pakistani Rupees and local transport terminology remain the product language.
- Role-based access must continue to restrict the portal to driver accounts.
- Inferred from the requested redesign: desktop and mobile layouts are both first-class delivery targets.

## Brand Commitments

- Product name: Digi_TransX.
- Preserve the light visual family already established on the login experience.
- Do not convert the driver portal to a dark theme.
- Light transport imagery may support the interface where it does not reduce task clarity.

## Evidence on Hand

- Existing login visual system: `frontend-react/src/styles/pages/auth.css`.
- Existing driver workflows: `frontend-react/src/pages/driver/`.
- Existing driver-oriented image: `frontend-react/src/assets/backgrounds/truck-driver-highway-mono.png`.
- Existing brand marks: `frontend-react/src/assets/brand/`.
- No customer testimonials or external performance claims are available; future UI must not fabricate them.

## Product Principles

- Put the driver's next operational action ahead of decorative content.
- Make live, pending, completed, and blocked states immediately distinguishable.
- Keep money, distance, date, and status data easy to scan under time pressure.
- Preserve trust through explicit feedback, recovery guidance, and secure role boundaries.
- Let the brand feel refined without slowing routine work.

## Accessibility & Inclusion

All driver workflows must remain keyboard accessible, preserve visible focus, maintain readable contrast, support reduced motion, and adapt to narrow mobile viewports without hiding primary actions.
