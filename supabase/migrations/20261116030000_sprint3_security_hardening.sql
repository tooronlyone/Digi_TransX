-- Sprint 3 Security Remediation (V1-SEC-012)
-- Harden active PostgreSQL SECURITY DEFINER and trigger function search paths,
-- schema-qualify object references, and restrict direct EXECUTE privileges.

BEGIN;

create or replace function public.enforce_single_client_profile()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
declare
    v_legacy text;
    other_table text := case tg_table_name
        when 'service_seeker_profiles' then 'everyday_user_profiles'
        else 'service_seeker_profiles' end;
    conflict boolean;
begin
    -- 1) Serialize on the user_id (released at commit/rollback). A concurrent
    --    opposite-table insert for the same user blocks here until we finish.
    perform pg_catalog.pg_advisory_xact_lock(new.user_id);

    -- 2) Read the owning user's app-logic role.
    select pg_catalog.lower(coalesce(legacy_role, '')) into v_legacy
    from public.users where id = new.user_id;
    if not found then
        raise exception 'user % does not exist; cannot create a client profile', new.user_id;
    end if;

    -- 3) Profile type must match the role:
    --    everyday_user_profiles  <-> legacy_role everyday_user
    --    service_seeker_profiles <-> legacy_role service_seeker/client
    --    any other role (transporter/admin/...) gets neither.
    if tg_table_name = 'everyday_user_profiles' then
        if v_legacy <> 'everyday_user' then
            raise exception 'everyday_user_profiles requires legacy_role everyday_user (user % is %)',
                new.user_id, coalesce(nullif(v_legacy, ''), '(none)');
        end if;
    else
        if v_legacy not in ('service_seeker', 'client') then
            raise exception 'service_seeker_profiles requires legacy_role service_seeker or client (user % is %)',
                new.user_id, coalesce(nullif(v_legacy, ''), '(none)');
        end if;
    end if;

    -- 4) Reject if the opposite profile already exists (checked under the lock).
    execute pg_catalog.format('select exists(select 1 from public.%I where user_id = $1)', other_table)
        into conflict using new.user_id;
    if conflict then
        raise exception 'user % already has a % row; a user cannot hold both client-profile types',
            new.user_id, other_table;
    end if;
    return new;
end;
$$;
revoke all on function public.enforce_single_client_profile() from public, anon, authenticated;

alter function public.prevent_version_mutation() set search_path = pg_catalog;
revoke all on function public.prevent_version_mutation() from public, anon, authenticated;

create or replace function public.current_app_user_id()
returns bigint
language sql stable security definer set search_path = pg_catalog
as $$
    select id from public.users where auth_id = auth.uid();
$$;
revoke all on function public.current_app_user_id() from public;

create or replace function public.current_app_role()
returns public.app_role
language sql stable security definer set search_path = pg_catalog
as $$
    select role from public.users where auth_id = auth.uid();
$$;
revoke all on function public.current_app_role() from public;

create or replace function public.is_admin()
returns boolean
language sql stable security definer set search_path = pg_catalog
as $$
    select coalesce(public.current_app_role() = 'admin'::public.app_role, false);
$$;
revoke all on function public.is_admin() from public;

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
            execute pg_catalog.format('grant execute on function public.current_app_user_id() to %I', client_role);
            execute pg_catalog.format('grant execute on function public.current_app_role() to %I', client_role);
            execute pg_catalog.format('grant execute on function public.is_admin() to %I', client_role);
        end if;
    end loop;
end
$$;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
    new.updated_at := pg_catalog.now();
    return new;
end;
$$;
revoke all on function public.set_updated_at() from public, anon, authenticated;

create or replace function public.log_shipment_status_change()
returns trigger language plpgsql security definer set search_path = pg_catalog as $$
begin
    if tg_op = 'INSERT' then
        insert into public.shipment_status_history (shipment_id, old_status, new_status, changed_by)
        values (new.id, null, new.status, public.current_app_user_id());
    elsif new.status is distinct from old.status then
        insert into public.shipment_status_history (shipment_id, old_status, new_status, changed_by)
        values (new.id, old.status, new.status, public.current_app_user_id());
    end if;
    return new;
end;
$$;
revoke all on function public.log_shipment_status_change() from public, anon, authenticated;

alter function public.preserve_bid_market_audit() set search_path = pg_catalog;
alter function public.protect_versioned_booking_terms() set search_path = pg_catalog;
alter function public.guard_payment_financial_invariants() set search_path = pg_catalog;
alter function public.protect_approved_reserve_reference() set search_path = pg_catalog;
alter function public.validate_settlement_resolution_integrity() set search_path = pg_catalog;
alter function public.protect_business_financial_history() set search_path = pg_catalog;
alter function public.guard_withdrawal_request_lifecycle() set search_path = pg_catalog;
alter function public.guard_security_reserve_balance() set search_path = pg_catalog;
alter function public.reconcile_security_reserve_backing() set search_path = pg_catalog;

COMMIT;
