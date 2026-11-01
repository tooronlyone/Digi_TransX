-- Driver consent, exclusive allocation and attributable reputation.
-- Preserve legacy reports/reviews, but never treat unproven rows as authority.
ALTER TABLE public.driver_trip_assignments ADD COLUMN IF NOT EXISTS accepted_at timestamptz;
ALTER TABLE public.driver_reviews ADD COLUMN IF NOT EXISTS assignment_id bigint
    REFERENCES public.driver_trip_assignments(id) ON DELETE RESTRICT;
ALTER TABLE public.driver_incidents ADD COLUMN IF NOT EXISTS assignment_id bigint
    REFERENCES public.driver_trip_assignments(id) ON DELETE RESTRICT;

-- Never invent consent or pick a winner among existing double bookings.
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM public.driver_trip_assignments WHERE
        NOT ((trip_type='one_time' AND trip_id IS NOT NULL AND agreement_trip_id IS NULL)
          OR (trip_type='agreement' AND agreement_trip_id IS NOT NULL AND trip_id IS NULL))
        OR status NOT IN('requested','accepted','rejected','in_progress','completed','cancelled')
        OR (status IN('accepted','in_progress','completed') AND accepted_at IS NULL)) THEN
        RAISE EXCEPTION 'Legacy driver assignments require explicit provenance/consent reconciliation';
    END IF;
END $$;
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public.driver_trip_assignments'::regclass AND conname='driver_assignment_target_valid') THEN
        ALTER TABLE public.driver_trip_assignments ADD CONSTRAINT driver_assignment_target_valid CHECK(
            (trip_type='one_time' AND trip_id IS NOT NULL AND agreement_trip_id IS NULL)
            OR (trip_type='agreement' AND agreement_trip_id IS NOT NULL AND trip_id IS NULL));
    END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public.driver_trip_assignments'::regclass AND conname='driver_assignment_status_valid') THEN
        ALTER TABLE public.driver_trip_assignments ADD CONSTRAINT driver_assignment_status_valid CHECK(
            status IN('requested','accepted','rejected','in_progress','completed','cancelled'));
    END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public.driver_trip_assignments'::regclass AND conname='driver_assignment_consent_required') THEN
        ALTER TABLE public.driver_trip_assignments ADD CONSTRAINT driver_assignment_consent_required CHECK(
            status NOT IN('accepted','in_progress','completed') OR accepted_at IS NOT NULL);
    END IF;
END $$;
-- SET NULL would contradict the exclusive target constraint and lose provenance.
ALTER TABLE public.driver_trip_assignments
    DROP CONSTRAINT IF EXISTS driver_trip_assignments_trip_id_fkey,
    DROP CONSTRAINT IF EXISTS driver_trip_assignments_agreement_trip_id_fkey;
ALTER TABLE public.driver_trip_assignments
    ADD CONSTRAINT driver_trip_assignments_trip_id_fkey FOREIGN KEY(trip_id)
        REFERENCES public.shipment_trips(id) ON DELETE RESTRICT,
    ADD CONSTRAINT driver_trip_assignments_agreement_trip_id_fkey FOREIGN KEY(agreement_trip_id)
        REFERENCES public.agreement_trips(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX IF NOT EXISTS driver_assignment_one_active_driver
    ON public.driver_trip_assignments(driver_user_id) WHERE status IN('accepted','in_progress');
CREATE UNIQUE INDEX IF NOT EXISTS driver_assignment_one_active_truck
    ON public.driver_trip_assignments(truck_id) WHERE status IN('accepted','in_progress');
CREATE UNIQUE INDEX IF NOT EXISTS driver_assignment_one_active_trip
    ON public.driver_trip_assignments(trip_id) WHERE trip_id IS NOT NULL AND status IN('accepted','in_progress');
CREATE UNIQUE INDEX IF NOT EXISTS driver_assignment_one_active_agreement_trip
    ON public.driver_trip_assignments(agreement_trip_id) WHERE agreement_trip_id IS NOT NULL AND status IN('accepted','in_progress');
CREATE UNIQUE INDEX IF NOT EXISTS driver_review_one_per_assignment
    ON public.driver_reviews(assignment_id) WHERE assignment_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS driver_review_one_per_trip
    ON public.driver_reviews(driver_user_id,trip_id) WHERE assignment_id IS NOT NULL AND trip_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS driver_review_one_per_agreement_trip
    ON public.driver_reviews(driver_user_id,agreement_trip_id) WHERE assignment_id IS NOT NULL AND agreement_trip_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS driver_assignment_trip_status
    ON public.driver_trip_assignments(trip_id,status) WHERE trip_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS driver_assignment_agreement_trip_status
    ON public.driver_trip_assignments(agreement_trip_id,status) WHERE agreement_trip_id IS NOT NULL;

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
    IF allocation.trip_id IS NOT NULL THEN
        SELECT status,transporter_user_id,truck_id INTO source_status,source_owner,source_truck
            FROM public.shipment_trips WHERE id=allocation.trip_id;
    ELSE
        SELECT status,transporter_user_id,truck_id INTO source_status,source_owner,source_truck
            FROM public.agreement_trips WHERE id=allocation.agreement_trip_id;
    END IF;
    IF TG_TABLE_NAME='driver_reviews' THEN reporter := NEW.reviewer_user_id;
    ELSE reporter := NEW.reporter_user_id; END IF;
    SELECT owner_user_id INTO vehicle_owner FROM public.vehicles WHERE id=allocation.truck_id;
    IF source_status IS DISTINCT FROM 'completed'
       OR source_owner IS DISTINCT FROM allocation.transporter_user_id
       OR source_truck IS DISTINCT FROM allocation.truck_id
       OR vehicle_owner IS DISTINCT FROM allocation.transporter_user_id
       OR NEW.driver_user_id<>allocation.driver_user_id
       OR reporter<>allocation.transporter_user_id
       OR NEW.trip_id IS DISTINCT FROM allocation.trip_id
       OR NEW.agreement_trip_id IS DISTINCT FROM allocation.agreement_trip_id THEN
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
CREATE TRIGGER driver_review_provenance_guard BEFORE INSERT OR UPDATE OF assignment_id,driver_user_id,reviewer_user_id,trip_id,agreement_trip_id
    ON public.driver_reviews FOR EACH ROW EXECUTE FUNCTION public.validate_driver_reputation_provenance();
DROP TRIGGER IF EXISTS driver_incident_provenance_guard ON public.driver_incidents;
CREATE TRIGGER driver_incident_provenance_guard BEFORE INSERT OR UPDATE OF assignment_id,driver_user_id,reporter_user_id,trip_id,agreement_trip_id
    ON public.driver_incidents FOR EACH ROW EXECUTE FUNCTION public.validate_driver_reputation_provenance();

-- Trip -> truck -> profile -> assignment is also the API allocation lock order.
-- Driver availability remains reserved through a pending delivery confirmation
-- or dispute; only a terminal authoritative trip releases the allocation.
CREATE OR REPLACE FUNCTION public.sync_driver_allocation_with_trip()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE allocation_ids bigint[]; driver_ids bigint[]; truck_ids bigint[];
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status OR NEW.status NOT IN('in_progress','completed','cancelled','resolved_client') THEN
        RETURN NEW;
    END IF;
    SELECT array_agg(a.id),array_agg(DISTINCT a.driver_user_id),array_agg(DISTINCT a.truck_id)
      INTO allocation_ids,driver_ids,truck_ids FROM public.driver_trip_assignments a
     WHERE ((TG_TABLE_NAME='shipment_trips' AND a.trip_id=NEW.id)
         OR (TG_TABLE_NAME='agreement_trips' AND a.agreement_trip_id=NEW.id))
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
DROP TRIGGER IF EXISTS agreement_trip_driver_allocation_sync ON public.agreement_trips;
CREATE TRIGGER agreement_trip_driver_allocation_sync AFTER UPDATE OF status ON public.agreement_trips
    FOR EACH ROW EXECUTE FUNCTION public.sync_driver_allocation_with_trip();

-- Legacy auto-links never established acceptance. Clear the authoritative link;
-- raw historical review/incident records remain for investigation, not public trust.
UPDATE public.driver_profiles p SET current_truck_id=NULL,is_available=true,updated_at=now()
 WHERE (current_truck_id IS NOT NULL OR is_available IS DISTINCT FROM true) AND NOT EXISTS(
    SELECT 1 FROM public.driver_trip_assignments a WHERE a.driver_user_id=p.user_id
      AND a.truck_id=p.current_truck_id AND a.status IN('accepted','in_progress') AND a.accepted_at IS NOT NULL);
WITH proven_reviews AS (
    SELECT r.driver_user_id,avg(r.rating) AS average_rating,count(*) AS review_count
      FROM public.driver_reviews r JOIN public.driver_trip_assignments a ON a.id=r.assignment_id
      LEFT JOIN public.shipment_trips s ON s.id=a.trip_id
      LEFT JOIN public.agreement_trips t ON t.id=a.agreement_trip_id
     WHERE a.status='completed' AND a.accepted_at IS NOT NULL
       AND r.driver_user_id=a.driver_user_id AND r.reviewer_user_id=a.transporter_user_id
       AND r.trip_id IS NOT DISTINCT FROM a.trip_id AND r.agreement_trip_id IS NOT DISTINCT FROM a.agreement_trip_id
       AND coalesce(s.transporter_user_id,t.transporter_user_id)=a.transporter_user_id
       AND coalesce(s.truck_id,t.truck_id)=a.truck_id
       AND coalesce(s.status,t.status)='completed' GROUP BY r.driver_user_id
), proven_incidents AS (
    SELECT i.driver_user_id,count(*) AS incident_count FROM public.driver_incidents i
      JOIN public.driver_trip_assignments a ON a.id=i.assignment_id
      LEFT JOIN public.shipment_trips s ON s.id=a.trip_id
      LEFT JOIN public.agreement_trips t ON t.id=a.agreement_trip_id
     WHERE i.status='confirmed' AND a.status='completed' AND a.accepted_at IS NOT NULL
       AND i.driver_user_id=a.driver_user_id AND i.reporter_user_id=a.transporter_user_id
       AND i.trip_id IS NOT DISTINCT FROM a.trip_id AND i.agreement_trip_id IS NOT DISTINCT FROM a.agreement_trip_id
       AND coalesce(s.status,t.status)='completed'
       AND coalesce(s.transporter_user_id,t.transporter_user_id)=a.transporter_user_id
       AND coalesce(s.truck_id,t.truck_id)=a.truck_id GROUP BY i.driver_user_id
)
UPDATE public.driver_profiles p SET rating=CASE WHEN r.review_count>0
    THEN greatest(1.00,r.average_rating-coalesce(i.incident_count,0)*0.50)::numeric(3,2) ELSE NULL END,
    rating_count=coalesce(r.review_count,0),updated_at=now()
 FROM (SELECT p2.user_id,r2.average_rating,r2.review_count FROM public.driver_profiles p2
       LEFT JOIN proven_reviews r2 ON r2.driver_user_id=p2.user_id) r
 LEFT JOIN proven_incidents i ON i.driver_user_id=r.user_id WHERE p.user_id=r.user_id;

CREATE INDEX IF NOT EXISTS shipments_client_created_id ON public.shipments(client_user_id,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS shop_sales_owner_created_id ON public.shop_sales(shop_user_id,created_at DESC,id DESC);
