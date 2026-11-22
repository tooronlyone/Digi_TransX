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

-- Replace triggers and SECURITY DEFINER functions that referenced retired
-- agreement_trip_id columns or agreement_trips triggers.
CREATE OR REPLACE FUNCTION public.validate_driver_reputation_provenance()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE allocation public.driver_trip_assignments%ROWTYPE; source_status text; reporter bigint;
    source_owner bigint; source_truck bigint; vehicle_owner bigint;
BEGIN
    IF NEW.assignment_id IS NULL THEN
        RAISE EXCEPTION 'A verified completed driver assignment is required' USING ERRCODE='23514';
    END IF;
    SELECT * INTO allocation FROM public.driver_trip_assignments WHERE id=NEW.assignment_id;
    IF NOT FOUND OR allocation.status<>'completed' OR allocation.accepted_at IS NULL THEN
        RAISE EXCEPTION 'A consented completed assignment is required' USING ERRCODE='23514';
    END IF;
        SELECT status,transporter_user_id,truck_id INTO source_status,source_owner,source_truck
            FROM public.shipment_trips WHERE id=allocation.trip_id;

    IF TG_TABLE_NAME='driver_reviews' THEN reporter := NEW.reviewer_user_id;
    ELSE reporter := NEW.reporter_user_id; END IF;
    SELECT owner_user_id INTO vehicle_owner FROM public.vehicles WHERE id=allocation.truck_id;
    IF source_status IS DISTINCT FROM 'completed'
       OR source_owner IS DISTINCT FROM allocation.transporter_user_id
       OR source_truck IS DISTINCT FROM allocation.truck_id
       OR vehicle_owner IS DISTINCT FROM allocation.transporter_user_id
       OR NEW.driver_user_id<>allocation.driver_user_id
       OR reporter<>allocation.transporter_user_id
       OR NEW.trip_id IS DISTINCT FROM allocation.trip_id THEN
        RAISE EXCEPTION 'Driver reputation provenance does not match the completed trip' USING ERRCODE='23514';
    END IF;
    IF TG_TABLE_NAME='driver_incidents' THEN
        IF TG_OP='INSERT' AND NEW.status IS DISTINCT FROM 'investigating' THEN
            RAISE EXCEPTION 'New incident reports require investigation' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.validate_driver_reputation_provenance() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS driver_review_provenance_guard ON public.driver_reviews;
CREATE TRIGGER driver_review_provenance_guard BEFORE INSERT OR UPDATE OF assignment_id,driver_user_id,reviewer_user_id,trip_id
    ON public.driver_reviews FOR EACH ROW EXECUTE FUNCTION public.validate_driver_reputation_provenance();
DROP TRIGGER IF EXISTS driver_incident_provenance_guard ON public.driver_incidents;
CREATE TRIGGER driver_incident_provenance_guard BEFORE INSERT OR UPDATE OF assignment_id,driver_user_id,reporter_user_id,trip_id
    ON public.driver_incidents FOR EACH ROW EXECUTE FUNCTION public.validate_driver_reputation_provenance();

CREATE OR REPLACE FUNCTION public.sync_driver_allocation_with_trip()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE allocation_ids bigint[]; driver_ids bigint[]; truck_ids bigint[];
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status OR NEW.status NOT IN('in_progress','completed','cancelled','resolved_client') THEN
        RETURN NEW;
    END IF;
    SELECT array_agg(a.id),array_agg(DISTINCT a.driver_user_id),array_agg(DISTINCT a.truck_id)
      INTO allocation_ids,driver_ids,truck_ids FROM public.driver_trip_assignments a
     WHERE ((TG_TABLE_NAME='shipment_trips' AND a.trip_id=NEW.id))
       AND a.status IN('requested','accepted','in_progress');
    IF allocation_ids IS NULL THEN RETURN NEW; END IF;
    PERFORM v.id FROM public.vehicles v WHERE v.id=ANY(truck_ids) ORDER BY v.id FOR UPDATE;
    PERFORM p.user_id FROM public.driver_profiles p WHERE p.user_id=ANY(driver_ids) ORDER BY p.user_id FOR UPDATE;
    PERFORM a.id FROM public.driver_trip_assignments a WHERE a.id=ANY(allocation_ids) ORDER BY a.id FOR UPDATE;
    IF NEW.status='in_progress' THEN
        UPDATE public.driver_trip_assignments SET status='in_progress',started_at=coalesce(started_at,now()),updated_at=now()
         WHERE id=ANY(allocation_ids) AND status='accepted';
        RETURN NEW;
    END IF;
    UPDATE public.driver_trip_assignments
       SET status=CASE WHEN NEW.status='completed' AND status IN('accepted','in_progress') THEN 'completed' ELSE 'cancelled' END,
           completed_at=CASE WHEN NEW.status='completed' AND status IN('accepted','in_progress') THEN coalesce(completed_at,now()) ELSE completed_at END,
           updated_at=now()
     WHERE id=ANY(allocation_ids) AND status IN('requested','accepted','in_progress');
    UPDATE public.driver_profiles p SET current_truck_id=NULL,is_available=true,updated_at=now()
     WHERE p.user_id=ANY(driver_ids) AND NOT EXISTS(
        SELECT 1 FROM public.driver_trip_assignments a WHERE a.driver_user_id=p.user_id AND a.status IN('accepted','in_progress'));
    UPDATE public.vehicles v SET driver_name=NULL,driver_cnic=NULL,updated_at=now()
     WHERE v.id=ANY(truck_ids) AND NOT EXISTS(
        SELECT 1 FROM public.driver_trip_assignments a WHERE a.truck_id=v.id AND a.status IN('accepted','in_progress'));
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.sync_driver_allocation_with_trip() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS shipment_trip_driver_allocation_sync ON public.shipment_trips;
CREATE TRIGGER shipment_trip_driver_allocation_sync AFTER UPDATE OF status ON public.shipment_trips
    FOR EACH ROW EXECUTE FUNCTION public.sync_driver_allocation_with_trip();

CREATE OR REPLACE FUNCTION public.guard_final_fuel_voucher()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    IF TG_OP='DELETE' OR OLD.status IN('dispensed','cancelled','expired') THEN
        RAISE EXCEPTION 'Final fuel authorizations are immutable' USING ERRCODE='23514';
    END IF;
    IF (NEW.transporter_user_id,NEW.trip_id,NEW.truck_id,NEW.truck_plate,
        NEW.fuel_type,NEW.max_amount,NEW.max_liters,NEW.wallet_authorized,NEW.credit_authorized,
        NEW.restricted_station_id,NEW.otp_digest,NEW.idempotency_key,NEW.request_hash,NEW.expires_at)
       IS DISTINCT FROM
       (OLD.transporter_user_id,OLD.trip_id,OLD.truck_id,OLD.truck_plate,
        OLD.fuel_type,OLD.max_amount,OLD.max_liters,OLD.wallet_authorized,OLD.credit_authorized,
        OLD.restricted_station_id,OLD.otp_digest,OLD.idempotency_key,OLD.request_hash,OLD.expires_at) THEN
        RAISE EXCEPTION 'Fuel authorization identity is immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.guard_final_fuel_voucher() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS fuel_voucher_final_guard ON public.fuel_vouchers;
CREATE TRIGGER fuel_voucher_final_guard BEFORE UPDATE OR DELETE ON public.fuel_vouchers
    FOR EACH ROW EXECUTE FUNCTION public.guard_final_fuel_voucher();

CREATE OR REPLACE FUNCTION public.mark_cancelled_trip_fuel_debt()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    IF NEW.status IN('cancelled','resolved_client') AND NEW.status IS DISTINCT FROM OLD.status THEN
        UPDATE public.fuel_credit_accounts a SET cancellation_debt=true,updated_at=now()
        WHERE a.transporter_user_id=NEW.transporter_user_id AND a.outstanding_credit>0
          AND EXISTS(SELECT 1 FROM public.fuel_vouchers v WHERE v.transporter_user_id=a.transporter_user_id
             AND v.status='dispensed' AND v.credit_utilized>coalesce((SELECT sum(e.amount) FROM public.fuel_credit_events e
                  WHERE e.voucher_id=v.id AND e.event_type='recover_allocation'),0) AND
             v.trip_id=NEW.id);
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.mark_cancelled_trip_fuel_debt() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS shipment_fuel_debt_cancellation ON public.shipment_trips;
DROP TRIGGER IF EXISTS zz_shipment_fuel_debt_cancellation ON public.shipment_trips;
CREATE TRIGGER zz_shipment_fuel_debt_cancellation AFTER UPDATE OF status ON public.shipment_trips
    FOR EACH ROW EXECUTE FUNCTION public.mark_cancelled_trip_fuel_debt();

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
