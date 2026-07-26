-- ============================================================================
-- One-time order and truck coordinate integrity
-- ============================================================================
-- Additive and idempotent. No coordinate is rounded, clamped or repaired.
-- The anomaly gate runs while both affected tables are locked and aborts with
-- category counts before any constraint is added.

lock table public.shipments, public.vehicles in share row exclusive mode;

do $$
declare
    shipment_pickup_pair_count bigint;
    shipment_pickup_lat_count bigint;
    shipment_pickup_lng_count bigint;
    shipment_dropoff_pair_count bigint;
    shipment_dropoff_lat_count bigint;
    shipment_dropoff_lng_count bigint;
    vehicle_current_pair_count bigint;
    vehicle_current_lat_count bigint;
    vehicle_current_lng_count bigint;
begin
    select
        count(*) filter (
            where (pickup_lat is null) <> (pickup_lng is null)
        ),
        count(*) filter (
            where pickup_lat is not null
              and not (
                  pickup_lat not in (
                      'NaN'::double precision,
                      'Infinity'::double precision,
                      '-Infinity'::double precision
                  )
                  and pickup_lat between -90::double precision
                                     and 90::double precision
              )
        ),
        count(*) filter (
            where pickup_lng is not null
              and not (
                  pickup_lng not in (
                      'NaN'::double precision,
                      'Infinity'::double precision,
                      '-Infinity'::double precision
                  )
                  and pickup_lng between -180::double precision
                                     and 180::double precision
              )
        ),
        count(*) filter (
            where (dropoff_lat is null) <> (dropoff_lng is null)
        ),
        count(*) filter (
            where dropoff_lat is not null
              and not (
                  dropoff_lat not in (
                      'NaN'::double precision,
                      'Infinity'::double precision,
                      '-Infinity'::double precision
                  )
                  and dropoff_lat between -90::double precision
                                      and 90::double precision
              )
        ),
        count(*) filter (
            where dropoff_lng is not null
              and not (
                  dropoff_lng not in (
                      'NaN'::double precision,
                      'Infinity'::double precision,
                      '-Infinity'::double precision
                  )
                  and dropoff_lng between -180::double precision
                                      and 180::double precision
              )
        )
    into
        shipment_pickup_pair_count,
        shipment_pickup_lat_count,
        shipment_pickup_lng_count,
        shipment_dropoff_pair_count,
        shipment_dropoff_lat_count,
        shipment_dropoff_lng_count
    from public.shipments;

    select
        count(*) filter (
            where (current_lat is null) <> (current_lng is null)
        ),
        count(*) filter (
            where current_lat is not null
              and not (
                  current_lat not in (
                      'NaN'::double precision,
                      'Infinity'::double precision,
                      '-Infinity'::double precision
                  )
                  and current_lat between -90::double precision
                                    and 90::double precision
              )
        ),
        count(*) filter (
            where current_lng is not null
              and not (
                  current_lng not in (
                      'NaN'::double precision,
                      'Infinity'::double precision,
                      '-Infinity'::double precision
                  )
                  and current_lng between -180::double precision
                                    and 180::double precision
              )
        )
    into
        vehicle_current_pair_count,
        vehicle_current_lat_count,
        vehicle_current_lng_count
    from public.vehicles;

    if shipment_pickup_pair_count
       + shipment_pickup_lat_count
       + shipment_pickup_lng_count
       + shipment_dropoff_pair_count
       + shipment_dropoff_lat_count
       + shipment_dropoff_lng_count
       + vehicle_current_pair_count
       + vehicle_current_lat_count
       + vehicle_current_lng_count > 0 then
        raise exception using
            errcode = '23514',
            message = format(
                'coordinate integrity precheck failed: '
                'shipments.pickup_pair=%s, shipments.pickup_lat=%s, '
                'shipments.pickup_lng=%s, shipments.dropoff_pair=%s, '
                'shipments.dropoff_lat=%s, shipments.dropoff_lng=%s, '
                'vehicles.current_pair=%s, vehicles.current_lat=%s, '
                'vehicles.current_lng=%s',
                shipment_pickup_pair_count,
                shipment_pickup_lat_count,
                shipment_pickup_lng_count,
                shipment_dropoff_pair_count,
                shipment_dropoff_lat_count,
                shipment_dropoff_lng_count,
                vehicle_current_pair_count,
                vehicle_current_lat_count,
                vehicle_current_lng_count
            );
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public'
          and t.relname = 'shipments'
          and c.conname = 'shipments_pickup_coords_pair'
    ) then
        alter table public.shipments
            add constraint shipments_pickup_coords_pair
            check (
                (pickup_lat is null and pickup_lng is null)
                or (pickup_lat is not null and pickup_lng is not null)
            );
    end if;

    if not exists (
        select 1 from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public' and t.relname = 'shipments'
          and c.conname = 'shipments_pickup_lat_finite_range'
    ) then
        alter table public.shipments
            add constraint shipments_pickup_lat_finite_range
            check (
                pickup_lat is null
                or (
                    pickup_lat not in (
                        'NaN'::double precision,
                        'Infinity'::double precision,
                        '-Infinity'::double precision
                    )
                    and pickup_lat between -90::double precision
                                       and 90::double precision
                )
            );
    end if;

    if not exists (
        select 1 from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public' and t.relname = 'shipments'
          and c.conname = 'shipments_pickup_lng_finite_range'
    ) then
        alter table public.shipments
            add constraint shipments_pickup_lng_finite_range
            check (
                pickup_lng is null
                or (
                    pickup_lng not in (
                        'NaN'::double precision,
                        'Infinity'::double precision,
                        '-Infinity'::double precision
                    )
                    and pickup_lng between -180::double precision
                                       and 180::double precision
                )
            );
    end if;

    if not exists (
        select 1 from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public' and t.relname = 'shipments'
          and c.conname = 'shipments_dropoff_coords_pair'
    ) then
        alter table public.shipments
            add constraint shipments_dropoff_coords_pair
            check (
                (dropoff_lat is null and dropoff_lng is null)
                or (dropoff_lat is not null and dropoff_lng is not null)
            );
    end if;

    if not exists (
        select 1 from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public' and t.relname = 'shipments'
          and c.conname = 'shipments_dropoff_lat_finite_range'
    ) then
        alter table public.shipments
            add constraint shipments_dropoff_lat_finite_range
            check (
                dropoff_lat is null
                or (
                    dropoff_lat not in (
                        'NaN'::double precision,
                        'Infinity'::double precision,
                        '-Infinity'::double precision
                    )
                    and dropoff_lat between -90::double precision
                                        and 90::double precision
                )
            );
    end if;

    if not exists (
        select 1 from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public' and t.relname = 'shipments'
          and c.conname = 'shipments_dropoff_lng_finite_range'
    ) then
        alter table public.shipments
            add constraint shipments_dropoff_lng_finite_range
            check (
                dropoff_lng is null
                or (
                    dropoff_lng not in (
                        'NaN'::double precision,
                        'Infinity'::double precision,
                        '-Infinity'::double precision
                    )
                    and dropoff_lng between -180::double precision
                                        and 180::double precision
                )
            );
    end if;

    if not exists (
        select 1 from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public' and t.relname = 'vehicles'
          and c.conname = 'vehicles_current_lat_finite_range'
    ) then
        alter table public.vehicles
            add constraint vehicles_current_lat_finite_range
            check (
                current_lat is null
                or (
                    current_lat not in (
                        'NaN'::double precision,
                        'Infinity'::double precision,
                        '-Infinity'::double precision
                    )
                    and current_lat between -90::double precision
                                      and 90::double precision
                )
            );
    end if;

    if not exists (
        select 1 from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public' and t.relname = 'vehicles'
          and c.conname = 'vehicles_current_lng_finite_range'
    ) then
        alter table public.vehicles
            add constraint vehicles_current_lng_finite_range
            check (
                current_lng is null
                or (
                    current_lng not in (
                        'NaN'::double precision,
                        'Infinity'::double precision,
                        '-Infinity'::double precision
                    )
                    and current_lng between -180::double precision
                                      and 180::double precision
                )
            );
    end if;
end $$;
