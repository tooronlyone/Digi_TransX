-- ============================================================================
-- Migration: harden the new client-profile tables
-- Date: 2026-07-23
-- ============================================================================
-- Corrective, forward-only follow-up to 20260723090000 (which is already
-- applied and must NOT be edited). This migration:
--
-- FIX 2 (RLS): Digi_TransX does not use a separate dispatcher role for client
--   profiles. Drop the dispatcher-read policies and narrow the owner policies
--   from FOR ALL to SELECT-own-row only. All profile mutations go through the
--   backend service role (which bypasses RLS), so a browser client can never
--   directly INSERT/UPDATE/DELETE a profile, change user_id, switch profile
--   type, or edit counters. Admin keeps full access via admin_all_* policies.
--
-- FIX 3 (integrity): replace the single shared trigger function with a
--   race-safe version — a transaction-scoped advisory lock on user_id
--   serializes concurrent inserts across BOTH tables, and the profile type
--   must match the owning user's role. Exactly one trigger function is kept;
--   the existing triggers reference it by name and are updated in place.
--
-- No table is created or dropped; customers stays gone and the area columns
-- stay gone. Idempotent. Apply with the Supabase CLI or the SQL editor.
-- ============================================================================

-- ---- FIX 2: drop dispatcher access, narrow owner policies to SELECT own ----
drop policy if exists service_seeker_profile_dispatcher_read on public.service_seeker_profiles;
drop policy if exists everyday_user_profile_dispatcher_read on public.everyday_user_profiles;

drop policy if exists service_seeker_profile_own on public.service_seeker_profiles;
drop policy if exists everyday_user_profile_own on public.everyday_user_profiles;
drop policy if exists service_seeker_profile_select_own on public.service_seeker_profiles;
drop policy if exists everyday_user_profile_select_own on public.everyday_user_profiles;

create policy service_seeker_profile_select_own on public.service_seeker_profiles
    for select using (user_id = public.current_app_user_id());
create policy everyday_user_profile_select_own on public.everyday_user_profiles
    for select using (user_id = public.current_app_user_id());

-- ---- FIX 3: race-safe, role-consistent shared trigger function -------------
create or replace function public.enforce_single_client_profile()
returns trigger language plpgsql as $$
declare
    v_legacy text;
    other_table text := case tg_table_name
        when 'service_seeker_profiles' then 'everyday_user_profiles'
        else 'service_seeker_profiles' end;
    conflict boolean;
begin
    -- 1) Serialize on the user_id (released at commit/rollback). A concurrent
    --    opposite-table insert for the same user blocks here until we finish.
    perform pg_advisory_xact_lock(new.user_id);

    -- 2) Read the owning user's app-logic role.
    select lower(coalesce(legacy_role, '')) into v_legacy
    from public.users where id = new.user_id;
    if not found then
        raise exception 'user % does not exist; cannot create a client profile', new.user_id;
    end if;

    -- 3) Profile type must match the role.
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
    execute format('select exists(select 1 from public.%I where user_id = $1)', other_table)
        into conflict using new.user_id;
    if conflict then
        raise exception 'user % already has a % row; a user cannot hold both client-profile types',
            new.user_id, other_table;
    end if;
    return new;
end;
$$;
