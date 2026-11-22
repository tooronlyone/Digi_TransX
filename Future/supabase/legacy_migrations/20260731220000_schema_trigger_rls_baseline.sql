-- Baseline correction: converge migrated databases with the canonical
-- updated_at trigger set and remove the shipments <-> shipment_trips RLS
-- recursion without changing business rows or broadening access.

do $$
declare
    target record;
    existing record;
begin
    if to_regprocedure('public.set_updated_at()') is null then
        raise exception 'required trigger function public.set_updated_at() is missing';
    end if;

    for target in
        select *
        from (
            values
                ('transporter_profiles', 'trg_transporter_profiles_updated_at'),
                ('fuel_station_profiles', 'trg_fuel_station_profiles_updated_at'),
                ('shopkeeper_profiles', 'trg_shopkeeper_profiles_updated_at')
        ) as required(table_name, trigger_name)
    loop
        if to_regclass(format('public.%I', target.table_name)) is null then
            raise exception 'required table public.% is missing', target.table_name;
        end if;

        select trigger.tgfoid, trigger.tgtype
        into existing
        from pg_catalog.pg_trigger as trigger
        join pg_catalog.pg_class as relation
          on relation.oid = trigger.tgrelid
        join pg_catalog.pg_namespace as namespace
          on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public'
          and relation.relname = target.table_name
          and trigger.tgname = target.trigger_name
          and not trigger.tgisinternal;

        if found then
            if existing.tgfoid <> 'public.set_updated_at()'::regprocedure
               or existing.tgtype <> 19 then
                raise exception
                    'existing trigger public.%.% has an unexpected definition',
                    target.table_name,
                    target.trigger_name;
            end if;
        else
            execute format(
                'create trigger %I before update on public.%I '
                'for each row execute function public.set_updated_at()',
                target.trigger_name,
                target.table_name
            );
        end if;
    end loop;
end
$$;

create or replace function public.is_transporter_assigned_to_shipment(
    shipment_id bigint
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog
as $$
    select case
        when public.current_app_role()
             is distinct from 'transporter'::public.app_role
            then false
        else exists (
            select 1
            from public.shipment_trips as trip
            where trip.order_id = shipment_id
              and trip.transporter_user_id = public.current_app_user_id()
        )
    end;
$$;

revoke all
    on function public.is_transporter_assigned_to_shipment(bigint)
    from public;

do $$
declare
    client_role text;
begin
    foreach client_role in array array['anon', 'authenticated'] loop
        if exists (
            select 1
            from pg_catalog.pg_roles
            where rolname = client_role
        ) then
            execute format(
                'grant execute on function '
                'public.is_transporter_assigned_to_shipment(bigint) to %I',
                client_role
            );
        end if;
    end loop;
end
$$;

drop policy if exists shipments_transporter_read on public.shipments;
create policy shipments_transporter_read on public.shipments
    for select using (
        public.current_app_role() = 'transporter'
        and (
            status = 'open'
            or public.is_transporter_assigned_to_shipment(id)
        )
    );
