-- ============================================================================
-- Migration: vehicle-level operating location (truck -> pickup eligibility)
-- Date: 2026-07-22
-- ============================================================================
-- Adds where a specific truck currently sits, so order visibility can be
-- filtered by distance from the truck to the shipment PICKUP instead of the
-- too-broad province list. Province-level operating_provinces is left in place
-- (unused by eligibility) and nothing is dropped.
--
-- New columns on public.vehicles:
--   current_city       text                  -- coarse city label (safe to show)
--   current_lat        double precision      -- exact pre-trip latitude
--   current_lng        double precision      -- exact pre-trip longitude
--   service_radius_km  numeric(6,2)          -- how far it will travel to a pickup
--
-- Constraints:
--   * latitude in [-90, 90], longitude in [-180, 180]
--   * coordinates are both-null or both-present (never half a point)
--   * service radius strictly > 0 and at most 150 km (default 100)
--
-- Additive and idempotent: no column is dropped, no row is deleted or mutated,
-- existing rows simply get service_radius_km = 100 and null coordinates.
-- Safe to run once on the existing database. Apply with the Supabase CLI
-- (`supabase db push`) or the SQL editor.
-- ============================================================================

alter table public.vehicles
    add column if not exists current_city      text,
    add column if not exists current_lat       double precision,
    add column if not exists current_lng       double precision,
    add column if not exists service_radius_km numeric(6,2) not null default 100;

-- Latitude / longitude within valid ranges (null allowed).
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'vehicles_current_lat_range'
    ) then
        alter table public.vehicles
            add constraint vehicles_current_lat_range
            check (current_lat is null or (current_lat >= -90 and current_lat <= 90));
    end if;

    if not exists (
        select 1 from pg_constraint where conname = 'vehicles_current_lng_range'
    ) then
        alter table public.vehicles
            add constraint vehicles_current_lng_range
            check (current_lng is null or (current_lng >= -180 and current_lng <= 180));
    end if;

    -- Coordinates must be given as a complete pair (both null or both present).
    if not exists (
        select 1 from pg_constraint where conname = 'vehicles_current_coords_pair'
    ) then
        alter table public.vehicles
            add constraint vehicles_current_coords_pair
            check (
                (current_lat is null and current_lng is null)
                or (current_lat is not null and current_lng is not null)
            );
    end if;

    -- Service radius: strictly positive and capped at the 150 km hard maximum.
    if not exists (
        select 1 from pg_constraint where conname = 'vehicles_service_radius_km_bounds'
    ) then
        alter table public.vehicles
            add constraint vehicles_service_radius_km_bounds
            check (service_radius_km > 0 and service_radius_km <= 150);
    end if;
end $$;
