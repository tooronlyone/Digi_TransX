-- Close raw PostgREST reads that bypass Flask's participant-aware serializers.
-- Prerequisite: 20261024010000_database_authorization_hardening.sql.
-- Vehicle rows contain driver identity/tracker/document metadata; open RFQs
-- contain precise locations. Agreement truck rows contain private bid terms.
-- The current frontend calls Flask exclusively for all five tables below.
-- RFQ bids are included because their former RLS policy queried part_rfqs.
-- Apply this complete, replay-safe file in one transaction.

DO $$
DECLARE
    relation_name text;
    columns_sql text;
    sequence_name text;
    existing_policy record;
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'vehicles','agreement_post_trucks','agreement_bid_trucks',
        'part_rfqs','part_rfq_bids']
    LOOP
        IF to_regclass(format('public.%I',relation_name)) IS NULL THEN
            RAISE EXCEPTION 'Required public.% is missing; apply earlier feature migrations first',relation_name;
        END IF;
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',relation_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC,anon,authenticated',relation_name);
        -- Table REVOKE alone does not remove explicit column grants.
        SELECT string_agg(quote_ident(attname),',' ORDER BY attnum)
          INTO columns_sql
          FROM pg_attribute
         WHERE attrelid=to_regclass(format('public.%I',relation_name))
           AND attnum>0 AND NOT attisdropped;
        EXECUTE format('REVOKE SELECT(%s),INSERT(%s),UPDATE(%s),REFERENCES(%s) '
                       'ON public.%I FROM PUBLIC,anon,authenticated',
                       columns_sql,columns_sql,columns_sql,columns_sql,relation_name);
        -- A later mistaken grant must not reactivate a public/owner policy.
        FOR existing_policy IN SELECT policyname FROM pg_policies
                                WHERE schemaname='public' AND tablename=relation_name
        LOOP
            EXECUTE format('DROP POLICY %I ON public.%I',existing_policy.policyname,relation_name);
        END LOOP;
        GRANT USAGE ON SCHEMA public TO service_role;
        EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON public.%I TO service_role',relation_name);
        EXECUTE format('CREATE POLICY backend_service_access ON public.%I '
                       'FOR ALL TO service_role USING(true) WITH CHECK(true)',relation_name);
        sequence_name := pg_get_serial_sequence(format('public.%I',relation_name),'id');
        IF sequence_name IS NOT NULL THEN
            EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC,anon,authenticated',sequence_name);
            EXECUTE format('GRANT USAGE,SELECT ON SEQUENCE %s TO service_role',sequence_name);
        END IF;
    END LOOP;
END $$;
