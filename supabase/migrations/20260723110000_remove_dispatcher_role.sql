-- ============================================================================
-- Migration: remove the obsolete `dispatcher` role from Digi_TransX
-- Date: 2026-07-23
-- ============================================================================
-- Forward-only, corrective migration. Digi_TransX never shipped an operational
-- dispatcher: the role, its RLS/storage policies and its helper function are
-- obsolete and are removed here. Nothing replaces it — the Flask backend keeps
-- running through the service role (which bypasses RLS), and admin / customer /
-- transporter / fuel_station_manager / shopkeeper are untouched.
--
-- This migration:
--   1. ABORTS if any dispatcher user still exists (role or legacy_role). No such
--      user is converted or deleted automatically — a human must resolve it.
--   2. Drops every dispatcher RLS policy (drivers, vehicles, shipments,
--      shipment_bids, shipment_trips, shipment_status_history, documents) and
--      the shipment-documents storage policy, and rewrites users_select_own so
--      it no longer grants dispatcher read access.
--   3. Drops public.is_dispatcher().
--   4. Rebuilds public.app_role WITHOUT the dispatcher value. PostgreSQL cannot
--      DROP an enum value in place, so the type is rebuilt via rename → create →
--      column swap → drop-old. current_app_role() (which returns app_role) and
--      the two policies that reference it are recreated verbatim around the
--      swap; that recreation is the ONLY change to the non-dispatcher policy set.
--   5. Rewrites public.handle_new_auth_user() so signup metadata can no longer
--      map to dispatcher; unknown/invalid roles keep falling back to 'customer'
--      (never admin).
--
-- Must run as ONE transaction (the default for a single migration file): any
-- RAISE below aborts and rolls the whole thing back, leaving no partial state
-- and no temporary enum/function/policy behind. Idempotent: safe to re-apply —
-- the enum rebuild is guarded on the dispatcher value still being present, and
-- every other step uses IF EXISTS / CREATE OR REPLACE.
--
-- Old migrations are immutable and are NOT edited. This new file necessarily
-- names `dispatcher` because its whole job is to remove those objects.
-- ============================================================================

-- ---- 0. Safety guard: abort if a dispatcher user still exists ---------------
do $guard$
begin
    if exists (select 1 from public.users where role::text = 'dispatcher')
       or exists (select 1 from public.users
                  where lower(coalesce(legacy_role, '')) = 'dispatcher') then
        raise exception
            'Aborting dispatcher removal: dispatcher user(s) still exist. '
            'Resolve them manually (do not auto-convert or delete) and re-run.';
    end if;
end
$guard$;

-- ---- 1. Drop dispatcher RLS policies (public) -------------------------------
drop policy if exists drivers_dispatcher_all      on public.drivers;
drop policy if exists vehicles_dispatcher_all     on public.vehicles;
drop policy if exists shipments_dispatcher_all    on public.shipments;
drop policy if exists bids_dispatcher_all         on public.shipment_bids;
drop policy if exists trips_dispatcher_all         on public.shipment_trips;
drop policy if exists history_dispatcher_read     on public.shipment_status_history;
drop policy if exists documents_dispatcher_read   on public.documents;
-- Defensive: these two were already dropped by 20260723100000, but a re-run or
-- an older deployment may still have them. Harmless when absent.
drop policy if exists service_seeker_profile_dispatcher_read on public.service_seeker_profiles;
drop policy if exists everyday_user_profile_dispatcher_read  on public.everyday_user_profiles;

-- ---- 2. Drop dispatcher storage policy --------------------------------------
drop policy if exists "shipment_docs_dispatcher_read" on storage.objects;

-- ---- 3. Rewrite users_select_own without dispatcher read --------------------
-- Owners keep reading their own row; the dispatcher-wide read is gone.
drop policy if exists users_select_own on public.users;
create policy users_select_own on public.users
    for select using (auth_id = auth.uid());

-- ---- 4. Drop is_dispatcher() (now unreferenced) -----------------------------
drop function if exists public.is_dispatcher();

-- ---- 5. Rebuild app_role without the dispatcher value -----------------------
-- Guarded on the value still being present so re-application is a no-op.
do $enum$
begin
    if exists (
        select 1
        from pg_enum e
        join pg_type t on t.oid = e.enumtypid
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = 'public' and t.typname = 'app_role'
          and e.enumlabel = 'dispatcher'
    ) then
        -- The two policies that reference current_app_role() (and thus the enum
        -- type) must be dropped before the function/type can be rebuilt. They
        -- are recreated verbatim below.
        execute 'drop policy if exists shipments_transporter_read on public.shipments';
        execute 'drop policy if exists agr_posts_transporter_read on public.agreement_posts';

        -- users_update_own reads the role column in its WITH CHECK, so the
        -- column type swap is blocked until it is dropped. Recreated verbatim.
        execute 'drop policy if exists users_update_own on public.users';

        -- current_app_role() returns app_role, so it blocks the type rebuild.
        execute 'drop function if exists public.current_app_role()';

        -- Rebuild the enum: rename old → create new (no dispatcher) → swap the
        -- users.role column across → drop old. Legitimate values keep their
        -- original relative order.
        execute 'alter type public.app_role rename to app_role__predispatch_old';
        execute $ct$
            create type public.app_role as enum
                ('admin', 'customer', 'transporter',
                 'fuel_station_manager', 'shopkeeper')
        $ct$;

        execute 'alter table public.users alter column role drop default';
        execute 'alter table public.users alter column role type public.app_role '
              || 'using role::text::public.app_role';
        execute $sd$alter table public.users alter column role set default 'customer'$sd$;

        -- Recreate current_app_role() returning the rebuilt enum (behavior for
        -- admin / customer / transporter / fuel_station_manager / shopkeeper is
        -- unchanged).
        execute $fn$
            create function public.current_app_role()
            returns public.app_role
            language sql stable security definer set search_path = public
            as 'select role from public.users where auth_id = auth.uid()'
        $fn$;

        -- Recreate the two transporter-read policies exactly as they were.
        execute $p1$
            create policy shipments_transporter_read on public.shipments
                for select using (
                    public.current_app_role() = 'transporter'
                    and (
                        status = 'open'
                        or id in (select order_id from public.shipment_trips
                                  where transporter_user_id = public.current_app_user_id())
                    )
                )
        $p1$;
        execute $p2$
            create policy agr_posts_transporter_read on public.agreement_posts
                for select using (public.current_app_role() = 'transporter')
        $p2$;

        -- Recreate users_update_own exactly as it was (owner may update own row,
        -- but may not change their own role).
        execute $uu$
            create policy users_update_own on public.users
                for update using (auth_id = auth.uid())
                with check (
                    auth_id = auth.uid()
                    and role = (select u.role from public.users u
                                where u.auth_id = auth.uid())
                )
        $uu$;

        -- Nothing depends on the old type anymore.
        execute 'drop type public.app_role__predispatch_old';
    end if;
end
$enum$;

-- ---- 6. Rewrite the signup trigger so dispatcher cannot be created ----------
-- Same mapping as before minus the dispatcher branch. Unknown / invalid roles
-- keep falling through to 'customer' (never admin).
create or replace function public.handle_new_auth_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
    v_legacy text := coalesce(new.raw_user_meta_data ->> 'legacy_role',
                              new.raw_user_meta_data ->> 'role', '');
    v_role public.app_role;
begin
    v_role := case lower(v_legacy)
        when 'platform_admin' then 'admin'::public.app_role
        when 'logistics_provider' then 'transporter'::public.app_role
        when 'transporter' then 'transporter'::public.app_role
        when 'fuel_station_manager' then 'fuel_station_manager'::public.app_role
        when 'shopkeeper' then 'shopkeeper'::public.app_role
        else 'customer'::public.app_role
    end;
    insert into public.users (auth_id, email, full_name, phone, cnic, role, legacy_role)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data ->> 'full_name', ''),
        coalesce(new.raw_user_meta_data ->> 'phone', ''),
        coalesce(nullif(new.raw_user_meta_data ->> 'cnic', ''), 'PENDING-' || new.id::text),
        v_role,
        nullif(v_legacy, '')
    )
    on conflict (email) do update set auth_id = excluded.auth_id;
    return new;
end;
$$;

-- ---- 7. Post-conditions: fail loudly if any dispatcher artifact survived ----
do $verify$
begin
    if exists (
        select 1 from pg_enum e
        join pg_type t on t.oid = e.enumtypid
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = 'public' and t.typname = 'app_role'
          and e.enumlabel = 'dispatcher'
    ) then
        raise exception 'post-check failed: app_role still contains dispatcher';
    end if;
    if exists (
        select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = 'is_dispatcher'
    ) then
        raise exception 'post-check failed: public.is_dispatcher() still exists';
    end if;
    if exists (
        select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = 'public' and t.typname = 'app_role__predispatch_old'
    ) then
        raise exception 'post-check failed: temporary enum type was left behind';
    end if;
    if exists (
        select 1 from pg_policies
        where schemaname in ('public', 'storage')
          and (policyname ilike '%dispatcher%'
               or coalesce(qual, '')       ilike '%is_dispatcher%'
               or coalesce(with_check, '') ilike '%is_dispatcher%')
    ) then
        raise exception 'post-check failed: a dispatcher policy still remains';
    end if;
end
$verify$;
