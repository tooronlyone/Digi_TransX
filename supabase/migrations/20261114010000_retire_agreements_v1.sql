-- Retire the V1 Agreemental system from the active schema.
--
-- This is intentionally destructive for Agreemental domain data. The full V1
-- schema remains archived at Future/supabase/schema-with-agreements-v1.sql for
-- the planned V2 redesign. Shared one-time shipment, wallet, chat and driver
-- records remain, but agreement-only links and rows are removed.

BEGIN;

-- Remove shared communication rows that belong exclusively to Agreemental.
-- Chat messages cascade with their retired thread; shipment/order chats remain.
DELETE FROM public.chat_threads
WHERE agreement_post_id IS NOT NULL OR agreement_bid_id IS NOT NULL;
DELETE FROM public.shipment_notifications
WHERE notification_type LIKE 'agreement\_%' ESCAPE '\';

-- Remove shared child records that point at agreement driver assignments or
-- agreement fuel authorizations before their discriminator columns disappear.
CREATE TEMP TABLE retired_agreement_assignments ON COMMIT DROP AS
SELECT id
FROM public.driver_trip_assignments
WHERE agreement_trip_id IS NOT NULL OR trip_id IS NULL;

DELETE FROM public.operational_incidents
WHERE assignment_id IN (SELECT id FROM retired_agreement_assignments);
DELETE FROM public.trip_cancellation_requests
WHERE assignment_id IN (SELECT id FROM retired_agreement_assignments);
DELETE FROM public.driver_fuel_logs
WHERE agreement_trip_id IS NOT NULL
   OR assignment_id IN (SELECT id FROM retired_agreement_assignments);
DELETE FROM public.driver_reviews
WHERE agreement_trip_id IS NOT NULL
   OR assignment_id IN (SELECT id FROM retired_agreement_assignments);
DELETE FROM public.driver_incidents
WHERE agreement_trip_id IS NOT NULL
   OR assignment_id IN (SELECT id FROM retired_agreement_assignments);
DELETE FROM public.driver_gps_pings WHERE agreement_trip_id IS NOT NULL;
DELETE FROM public.driver_trip_assignments
WHERE id IN (SELECT id FROM retired_agreement_assignments);

DELETE FROM public.fuel_credit_events
WHERE voucher_id IN (
    SELECT id FROM public.fuel_vouchers WHERE agreement_trip_id IS NOT NULL
);
DELETE FROM public.fuel_vouchers WHERE agreement_trip_id IS NOT NULL;

-- Shared tables become one-time-shipment-only.
ALTER TABLE public.chat_threads
    DROP COLUMN IF EXISTS agreement_bid_id CASCADE,
    DROP COLUMN IF EXISTS agreement_post_id CASCADE;

ALTER TABLE public.driver_trip_assignments
    DROP CONSTRAINT IF EXISTS driver_assignment_target_valid,
    DROP CONSTRAINT IF EXISTS driver_trip_assignments_agreement_trip_id_fkey,
    DROP COLUMN IF EXISTS agreement_trip_id CASCADE,
    DROP COLUMN IF EXISTS trip_type CASCADE,
    ALTER COLUMN trip_id SET NOT NULL;
ALTER TABLE public.driver_trip_assignments
    ADD CONSTRAINT driver_assignment_target_valid CHECK (trip_id IS NOT NULL);

ALTER TABLE public.driver_reviews DROP COLUMN IF EXISTS agreement_trip_id CASCADE;
ALTER TABLE public.driver_incidents DROP COLUMN IF EXISTS agreement_trip_id CASCADE;
ALTER TABLE public.driver_gps_pings DROP COLUMN IF EXISTS agreement_trip_id CASCADE;
ALTER TABLE public.driver_fuel_logs DROP COLUMN IF EXISTS agreement_trip_id CASCADE;

ALTER TABLE public.fuel_vouchers
    DROP COLUMN IF EXISTS agreement_trip_id CASCADE,
    ALTER COLUMN trip_id SET NOT NULL;

ALTER TABLE public.security_events DROP COLUMN IF EXISTS agreement_id;
ALTER TABLE public.business_audit_events DROP COLUMN IF EXISTS agreement_id;

-- Drop the Agreemental domain in dependency order.
DROP FUNCTION IF EXISTS public.can_read_agreement(bigint) CASCADE;
DROP TABLE IF EXISTS public.agreement_payment_penalties CASCADE;
DROP TABLE IF EXISTS public.agreement_monthly_payments CASCADE;
DROP TABLE IF EXISTS public.agreement_trips CASCADE;
DROP TABLE IF EXISTS public.agreement_trucks CASCADE;
DROP TABLE IF EXISTS public.agreements CASCADE;
DROP TABLE IF EXISTS public.agreement_bid_trucks CASCADE;
DROP TABLE IF EXISTS public.agreement_bids CASCADE;
DROP TABLE IF EXISTS public.agreement_post_trucks CASCADE;
DROP TABLE IF EXISTS public.agreement_posts CASCADE;

-- Terms and commission configuration now publish one-time order policy only.
ALTER TABLE public.terms_versions DROP COLUMN IF EXISTS agreement_policy_id;
DROP TRIGGER IF EXISTS trg_commission_policies_immutable ON public.commission_policies;
DELETE FROM public.commission_policies WHERE policy_type = 'agreement';
ALTER TABLE public.commission_policies
    DROP CONSTRAINT IF EXISTS commission_policies_policy_type_check;
ALTER TABLE public.commission_policies
    ADD CONSTRAINT commission_policies_policy_type_check
    CHECK (policy_type = 'one_time_order');
CREATE TRIGGER trg_commission_policies_immutable
    BEFORE UPDATE OR DELETE ON public.commission_policies
    FOR EACH ROW EXECUTE FUNCTION public.prevent_version_mutation();

COMMIT;
