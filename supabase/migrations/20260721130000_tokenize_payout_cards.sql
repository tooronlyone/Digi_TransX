-- ============================================================================
-- Migration: tokenize transporter payout cards
-- Date: 2026-07-21
-- ============================================================================
-- transporter_profiles previously stored the transporter's full payout card
-- number in plain text. From now on only non-sensitive display data is kept:
--   - a generated dummy/provider token
--   - card brand (derived) and last four digits
--   - the existing holder / expiry / bank labels (non-sensitive)
-- Existing raw numbers are converted to last-four/brand display data and the
-- raw column is dropped. Nothing else about transporter wallets changes.
--
-- Safe to run once on the existing database; idempotent guards included.
-- Apply with the Supabase CLI (`supabase db push`) or the SQL editor.
-- ============================================================================

alter table public.transporter_profiles
    add column if not exists payout_card_token     text,
    add column if not exists payout_card_brand     text,
    add column if not exists payout_card_last_four text;

-- Convert existing raw card numbers to safe display data, then drop the raw
-- column entirely. Guarded so a re-run (column already gone) is a no-op.
do $$
begin
    if exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'transporter_profiles'
          and column_name = 'payout_card_number'
    ) then
        update public.transporter_profiles
        set payout_card_last_four = right(regexp_replace(payout_card_number, '\D', '', 'g'), 4),
            payout_card_brand = coalesce(payout_card_brand, case
                when regexp_replace(payout_card_number, '\D', '', 'g') like '4%' then 'visa'
                when regexp_replace(payout_card_number, '\D', '', 'g') like '5%' then 'mastercard'
                when regexp_replace(payout_card_number, '\D', '', 'g') like '34%'
                  or regexp_replace(payout_card_number, '\D', '', 'g') like '37%' then 'amex'
                when regexp_replace(payout_card_number, '\D', '', 'g') like '6%' then 'discover'
                else 'card'
            end),
            payout_card_token = coalesce(
                payout_card_token,
                'dummytok_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24)
            )
        where payout_card_number is not null
          and length(regexp_replace(payout_card_number, '\D', '', 'g')) >= 4
          and payout_card_last_four is null;

        alter table public.transporter_profiles drop column payout_card_number;
    end if;
end $$;
