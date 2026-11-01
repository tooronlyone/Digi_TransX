-- ============================================================================
-- Migration: one-time order payment foundation
-- Date: 2026-07-21
-- ============================================================================
-- Phase 1 backend/database foundation for one-time order payments:
--   1. Extends the existing payments table (no duplicate invoice table) with
--      wallet/card funding-split audit columns, processing-fee snapshot,
--      dummy-provider references, idempotency key and held/released/refunded
--      lifecycle timestamps.
--   2. Adds saved_payment_methods (tokenized dummy cards: token, brand, last
--      four, expiry only — never full numbers or CVC) and
--      user_payment_preferences (default method + automatic shortfall
--      charging).
--   3. Partial unique indexes: at most one active (processing/held/released)
--      payment per shipment, and a unique checkout idempotency key so
--      repeated requests can never double-charge or create duplicate trips.
--   4. Data migration: service-seeker/client wallets lose the artificial
--      minimum-balance reserve (minimum_required -> 0). Client wallets never
--      carried a locked minimum deposit (only transporter wallets lock the
--      security deposit), so no lock release is needed and transporter
--      wallet rules are untouched. No wallet rows or transactions are
--      deleted.
--
-- Safe to run once on the existing database; idempotent guards included.
-- Apply with the Supabase CLI (`supabase db push`) or the SQL editor as a
-- single transaction (psql: run with -1).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Extend payments for the one-time checkout audit trail
-- ---------------------------------------------------------------------------
alter table public.payments
    add column if not exists wallet_funded_amount   numeric(12,2) not null default 0
        check (wallet_funded_amount >= 0),
    add column if not exists card_funded_amount     numeric(12,2) not null default 0
        check (card_funded_amount >= 0),
    add column if not exists processing_fee_percent numeric(5,2)
        check (processing_fee_percent is null or processing_fee_percent >= 0),
    add column if not exists processing_fee_amount  numeric(12,2) not null default 0
        check (processing_fee_amount >= 0),
    -- numeric(14,2): card-funded amount can reach the maximum accepted bid and
    -- the processing fee is added on top, exceeding the funded columns' range.
    add column if not exists total_card_charge      numeric(14,2)
        check (total_card_charge is null or total_card_charge >= 0),
    add column if not exists funding_source         text
        check (funding_source is null or funding_source in ('wallet', 'card', 'wallet_card')),
    add column if not exists provider_name          text,
    add column if not exists provider_reference     text,
    add column if not exists idempotency_key        text,
    add column if not exists terms_version_id       bigint references public.terms_versions (id),
    add column if not exists held_at                timestamptz,
    add column if not exists released_at            timestamptz,
    add column if not exists refunded_at            timestamptz;

-- Lifecycle statuses for held-escrow payments ('paid' kept for historical
-- rows created by the previous immediate-payout flow).
alter table public.payments drop constraint if exists payments_status_check;
alter table public.payments add constraint payments_status_check
    check (status in ('processing', 'held', 'released', 'disputed', 'refunded', 'failed', 'paid'));

-- At most ONE active payment per one-time shipment. Disputed payments still
-- hold funds, so they count as active.
create unique index if not exists uniq_payments_active_per_shipment
    on public.payments (shipment_id)
    where shipment_id is not null and status in ('processing', 'held', 'disputed', 'released');

-- Repeated checkout requests may never create a second charge.
create unique index if not exists uniq_payments_idempotency_key
    on public.payments (idempotency_key)
    where idempotency_key is not null;

create index if not exists idx_payments_shipment_status
    on public.payments (shipment_id, status);

-- ---------------------------------------------------------------------------
-- 1b. Wallet top-up idempotency (reuse wallet_transactions, no new table)
-- ---------------------------------------------------------------------------
alter table public.wallet_transactions
    add column if not exists provider_name      text,
    add column if not exists provider_reference text;

-- A user + idempotency key identifies exactly one top-up.
create unique index if not exists uniq_wallet_topup_idempotency
    on public.wallet_transactions (user_id, reference_id)
    where type = 'topup' and reference_id is not null;

-- ---------------------------------------------------------------------------
-- 2. Saved payment methods (tokenized dummy cards)
-- ---------------------------------------------------------------------------
-- Only non-sensitive data is ever stored: provider token, brand, last four
-- digits and expiry. Full card numbers and CVC codes are never persisted.
create table if not exists public.saved_payment_methods (
    id              bigint generated by default as identity primary key,
    user_id         bigint not null references public.users (id) on delete cascade,
    provider_name   text not null default 'dummycard',
    provider_token  text not null unique,
    card_brand      text not null default 'card',
    card_last_four  text not null check (card_last_four ~ '^[0-9]{4}$'),
    expiry_month    integer not null check (expiry_month between 1 and 12),
    expiry_year     integer not null check (expiry_year between 2000 and 2200),
    is_default      boolean not null default false,
    status          text not null default 'active'
                    check (status in ('active', 'removed')),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    -- Composite key target so user_payment_preferences can prove (at the
    -- database level) that a default method belongs to the same user.
    constraint saved_payment_methods_user_row_unique unique (user_id, id)
);

create index if not exists idx_saved_methods_user_status
    on public.saved_payment_methods (user_id, status);

-- A user can have at most one active default card.
create unique index if not exists uniq_saved_method_default_per_user
    on public.saved_payment_methods (user_id)
    where is_default and status = 'active';

-- ---------------------------------------------------------------------------
-- 3. User payment preferences
-- ---------------------------------------------------------------------------
create table if not exists public.user_payment_preferences (
    id              bigint generated by default as identity primary key,
    user_id         bigint not null unique references public.users (id) on delete cascade,
    default_payment_method_id bigint,
    auto_shortfall_charge_enabled boolean not null default false,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    -- The composite reference guarantees the default method belongs to the
    -- SAME user — a preference can never point at another user's card.
    constraint user_payment_preferences_method_owned_fk
        foreign key (user_id, default_payment_method_id)
        references public.saved_payment_methods (user_id, id)
        on delete set null (default_payment_method_id)
);

-- updated_at maintenance (same trigger function the other tables use)
drop trigger if exists trg_saved_payment_methods_updated_at on public.saved_payment_methods;
create trigger trg_saved_payment_methods_updated_at
    before update on public.saved_payment_methods
    for each row execute function public.set_updated_at();

drop trigger if exists trg_user_payment_preferences_updated_at on public.user_payment_preferences;
create trigger trg_user_payment_preferences_updated_at
    before update on public.user_payment_preferences
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 4. Row Level Security + token protection
--    (backend writes use the service role and bypass RLS; these rules govern
--    direct PostgREST/browser access, following the repository's patterns)
--
-- saved_payment_methods carries the provider token, which must NEVER be
-- readable from the browser:
--   - all table privileges are revoked from the browser roles, then SELECT is
--     re-granted on the non-sensitive columns only (provider_token and
--     user_id stay revoked, so selecting them fails at the privilege level)
--   - RLS restricts reads to the user's own rows
--   - browser roles get no INSERT/UPDATE/DELETE privilege at all — every
--     write goes through the backend API
--   - a security-invoker view exposes exactly the safe columns for direct
--     reads
-- ---------------------------------------------------------------------------
alter table public.saved_payment_methods    enable row level security;
alter table public.user_payment_preferences enable row level security;

drop policy if exists admin_all_saved_payment_methods on public.saved_payment_methods;
create policy admin_all_saved_payment_methods on public.saved_payment_methods
    for all using (public.is_admin()) with check (public.is_admin());

drop policy if exists admin_all_user_payment_preferences on public.user_payment_preferences;
create policy admin_all_user_payment_preferences on public.user_payment_preferences
    for all using (public.is_admin()) with check (public.is_admin());

-- Own rows: read-only, and never the token column (see grants below).
drop policy if exists saved_methods_own on public.saved_payment_methods;
drop policy if exists saved_methods_own_read on public.saved_payment_methods;
create policy saved_methods_own_read on public.saved_payment_methods
    for select using (user_id = public.current_app_user_id());

-- Preferences hold no secrets: own-row read-only; writes go through the API.
drop policy if exists payment_preferences_own on public.user_payment_preferences;
drop policy if exists payment_preferences_own_read on public.user_payment_preferences;
create policy payment_preferences_own_read on public.user_payment_preferences
    for select using (user_id = public.current_app_user_id());

-- Column-level privileges (browser roles exist on Supabase; guarded so the
-- migration also runs on plain PostgreSQL test databases).
do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.saved_payment_methods from %I', r);
            execute format('revoke all on table public.user_payment_preferences from %I', r);
        end if;
    end loop;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        execute 'grant select (id, card_brand, card_last_four, expiry_month, expiry_year, '
                'is_default, status, created_at) on public.saved_payment_methods to authenticated';
        execute 'grant select (id, user_id, default_payment_method_id, '
                'auto_shortfall_charge_enabled, created_at, updated_at) '
                'on public.user_payment_preferences to authenticated';
    end if;
end $$;

-- Safe direct-read surface: only non-sensitive columns, RLS of the invoker
-- applies (own rows only). provider_token is not part of this view.
create or replace view public.saved_payment_methods_safe
    with (security_invoker = true) as
select id, card_brand, card_last_four, expiry_month, expiry_year,
       is_default, status, created_at
from public.saved_payment_methods
where status = 'active';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        execute 'grant select on public.saved_payment_methods_safe to authenticated';
    end if;
end $$;

-- ---------------------------------------------------------------------------
-- 5. Data migration: drop the artificial client minimum-balance reserve
-- ---------------------------------------------------------------------------
-- Service seekers (wallet role 'client') can now hold any balance. Client
-- wallets never locked a minimum security deposit (that lock exists only on
-- transporter wallets), so only the minimum gate is cleared here; balances,
-- locked escrow amounts and the full transaction history stay untouched.
-- Transporter wallets keep their existing minimum/lock rules unchanged.
-- Wallet rows previously created for everyday users are intentionally kept
-- (nothing is deleted); the application simply no longer exposes them.
update public.wallets
set minimum_required = 0,
    is_minimum_met   = true
where role = 'client';
