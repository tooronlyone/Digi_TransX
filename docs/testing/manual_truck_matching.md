# Manual truck-matching test guide

This guide verifies the production order/truck matching rules
(`backend/orders/helpers.py:truck_order_mismatch`) end-to-end, using the 50
seeded test transporters.

Matching controls two things the UI does **not** surface directly:

1. Which orders a transporter can see in **available orders**.
2. Whether a transporter's bid passes **bid validation**.

Because the seeker UI does not list matched transporters, use
`audit_order_matching.py` to see exactly who should match and why.

## Prerequisites

1. Seed the test fleet (see `backend/scripts/seed_matching_test_fleet.py`).
   Confirm 50 marked transporters each with one **active** primary vehicle.
2. Know a test **seeker** (customer) login for posting orders.
3. Have the test transporter password (`DIGITRANSX_MATCHING_TEST_PASSWORD`) to
   log in as any `dtx.matching.seed.NNN@example.test` transporter.

## Per-test procedure

For every case below:

1. **Post an order** as the seeker with the described goods.
2. **Note the order ID** shown after posting.
3. Run the audit for that order:
   ```
   python backend/scripts/audit_order_matching.py --order-id <ID>
   ```
   Read the matched list, the non-match reasons, and the totals by type.
4. **Log in as one reported matched transporter** and confirm the order
   appears in available orders.
5. **Place a test bid** with that transporter's active truck and confirm bid
   validation accepts it.
6. **Log in as a reported non-matched transporter** and confirm the order is
   hidden, or that a bid with its truck is rejected with the **same reason**
   the audit printed.

The audit reason and the app's behaviour must agree in every case — they run
the identical production function.

## Test cases

The matching checks, in order, are: (1) truck **type** in the order's required
types, (2) **weight** capacity, (3) **volume** capacity, (4) load **dimensions**
fit the cargo bed. Each case below targets one or more of these.

| # | Case | Goods / setup | Primarily exercises |
|---|------|---------------|---------------------|
| 1 | General cargo | Dry boxed goods, moderate weight, no special flags | Type (rigid/box/light trucks) |
| 2 | Machinery | Heavy machinery on a flatbed/low-bed; large dimensions | Type + dimensions |
| 3 | Frozen food | Requires refrigeration; reefer types only | Type (reefer), refrigeration |
| 4 | Pharmaceuticals | Temperature-controlled, fragile | Type (reefer/insulated), fragile |
| 5 | Milk / water | Food-grade liquid; volume-driven | Type (milk tanker), volume |
| 6 | Fuel | Hazardous liquid | Type (fuel/oil tanker), hazardous |
| 7 | Chemicals | Hazardous liquid | Type (chemical tanker), hazardous |
| 8 | Cement | Bulk powder | Type (bulk cement / powder bulker), weight |
| 9 | Sand / gravel | Construction bulk | Type (dump / tipper), weight/volume |
| 10 | Livestock | Live animals | Type (livestock carrier) |
| 11 | Weight boundary | Load weight set **just below** a truck's capacity, then **exactly above** it | Weight capacity boundary |
| 12 | Volume boundary | Load volume **just below** capacity, then **exactly above** it | Volume capacity boundary |
| 13 | Dimension boundary | Load length **shorter than**, **equal to**, then **longer than** the truck bed | Dimension fit |

### Boundary-case guidance

The seeded vehicles deliberately vary capacity/volume/bed values across the
lower bound, midpoint and upper bound of each catalog type, so boundary tests
have a truck to sit exactly on.

- **Weight (case 11):** pick a matched truck from case 1's audit, read its
  `cap=` value, then post one order at `capacity` tons (must match — the rule
  allows exact boundary) and one at `capacity + 0.1` tons (must reject with the
  "can carry up to … tons" message).
- **Volume (case 12):** same approach using the truck's `volume_max_cbm`. Equal
  volume matches; a slightly larger volume rejects with the "holds up to … cbm"
  message.
- **Dimensions (case 13):** read a matched truck's `bed_length_ft`, convert to
  cm (× 30.48). A load length below or equal to that matches; a longer load
  rejects with the "cargo bed length is only … ft" message. Repeat for width
  and height.

## Expected outcome

For each case, the set of transporters the audit reports as matched is exactly
the set that can see the order and pass bid validation; every reported
non-match is hidden or rejected with the identical printed reason. Any
divergence is a matching bug to investigate in
`backend/orders/helpers.py:truck_order_mismatch`.
