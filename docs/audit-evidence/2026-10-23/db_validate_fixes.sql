\set ON_ERROR_STOP on
CREATE SCHEMA auth;
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
CREATE TABLE auth.users (id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb NOT NULL DEFAULT '{}'::jsonb);
CREATE SCHEMA storage;
CREATE TABLE storage.buckets (id text PRIMARY KEY, name text, public boolean);
CREATE TABLE storage.objects (id uuid DEFAULT gen_random_uuid() PRIMARY KEY, bucket_id text);
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
GRANT USAGE ON SCHEMA public, auth, storage TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO anon, authenticated, service_role;
\i supabase/schema.sql
SELECT 'fresh_schema_missing_october_tables' AS proof, to_regclass('public.driver_profiles') AS driver_profiles, to_regclass('public.shop_products') AS shop_products;
\i supabase/migrations/20261021200000_truck_parts_marketplace.sql
\i supabase/migrations/20261022100000_shop_inventory_products.sql
\i supabase/migrations/20261022110000_shop_sales_pos.sql
\i supabase/migrations/20261022160000_contact_messages.sql
\i supabase/migrations/20261022170000_fuel_station_portal.sql
\i supabase/migrations/20261022180000_driver_role_and_tracking.sql
\i supabase/migrations/20261023190000_driver_fuel_logs.sql
\i supabase/migrations/20261023203500_unrated_new_drivers.sql

\echo validating_DB_01
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog AS $$
DECLARE
    requested text := lower(trim(coalesce(
        NEW.raw_user_meta_data->>'legacy_role',
        NEW.raw_user_meta_data->>'role', 'everyday_user')));
    safe_legacy text;
    safe_role public.app_role;
BEGIN
    safe_legacy := CASE requested
        WHEN 'service_seeker' THEN 'service_seeker'
        WHEN 'client' THEN 'client'
        WHEN 'everyday_user' THEN 'everyday_user'
        WHEN 'logistics_provider' THEN 'logistics_provider'
        WHEN 'transporter' THEN 'transporter'
        WHEN 'fuel_station_manager' THEN 'fuel_station_manager'
        WHEN 'shopkeeper' THEN 'shopkeeper'
        WHEN 'driver' THEN 'driver'
        ELSE 'everyday_user' END;
    safe_role := CASE safe_legacy
        WHEN 'logistics_provider' THEN 'transporter'::public.app_role
        WHEN 'transporter' THEN 'transporter'::public.app_role
        WHEN 'fuel_station_manager' THEN 'fuel_station_manager'::public.app_role
        WHEN 'shopkeeper' THEN 'shopkeeper'::public.app_role
        ELSE 'customer'::public.app_role END;
    INSERT INTO public.users(auth_id,email,full_name,phone,cnic,role,legacy_role)
    VALUES (NEW.id, NEW.email,
        coalesce(NEW.raw_user_meta_data->>'full_name',''),
        coalesce(NEW.raw_user_meta_data->>'phone',''),
        coalesce(nullif(NEW.raw_user_meta_data->>'cnic',''),
                 'PENDING-' || NEW.id::text),
        safe_role,safe_legacy);
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.handle_new_auth_user() FROM PUBLIC, anon, authenticated;


\echo validating_DB_02
REVOKE UPDATE ON public.users FROM PUBLIC, anon, authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.transporter_profiles,
    public.fuel_station_profiles, public.shopkeeper_profiles
    FROM PUBLIC, anon, authenticated;
DROP POLICY IF EXISTS users_update_own ON public.users;
DROP POLICY IF EXISTS transporter_profile_own ON public.transporter_profiles;
DROP POLICY IF EXISTS fuel_station_profile_own ON public.fuel_station_profiles;
DROP POLICY IF EXISTS shopkeeper_profile_own ON public.shopkeeper_profiles;
CREATE POLICY transporter_profile_read_own ON public.transporter_profiles
    FOR SELECT TO authenticated USING (user_id=public.current_app_user_id());
CREATE POLICY fuel_station_profile_read_own ON public.fuel_station_profiles
    FOR SELECT TO authenticated USING (user_id=public.current_app_user_id());
CREATE POLICY shopkeeper_profile_read_own ON public.shopkeeper_profiles
    FOR SELECT TO authenticated USING (user_id=public.current_app_user_id());


\echo validating_DB_03
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'contact_messages','fuel_station_pumps','fuel_station_dispenses',
        'driver_profiles','driver_incidents','driver_reviews',
        'driver_trip_assignments','driver_gps_pings','driver_fuel_logs']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated',table_name);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO service_role',table_name);
    END LOOP;
END $$;


\echo validating_DB_04
REVOKE INSERT, UPDATE, DELETE ON public.drivers, public.vehicles,
    public.shipments, public.shipment_bids, public.shipment_trips,
    public.documents, public.wallet_withdrawal_requests,
    public.chat_threads, public.chat_messages,
    public.agreement_posts, public.agreement_post_trucks,
    public.agreement_bids, public.agreement_bid_trucks,
    public.agreements, public.agreement_trucks, public.agreement_trips,
    public.marketplace_parts, public.marketplace_orders,
    public.marketplace_order_items, public.part_rfqs, public.part_rfq_bids
    FROM PUBLIC, anon, authenticated;


\echo validating_DB_05
DROP POLICY IF EXISTS chat_messages_participants ON public.chat_messages;
CREATE POLICY chat_messages_member_read ON public.chat_messages
    FOR SELECT TO authenticated USING (
        EXISTS (SELECT 1 FROM public.chat_threads t
                WHERE t.id=thread_id
                  AND public.current_app_user_id() IN
                      (t.client_user_id,t.transporter_user_id,t.admin_user_id)));
CREATE POLICY chat_messages_member_insert ON public.chat_messages
    FOR INSERT TO authenticated WITH CHECK (
        sender_user_id=public.current_app_user_id()
        AND EXISTS (SELECT 1 FROM public.chat_threads t
                    WHERE t.id=thread_id
                      AND public.current_app_user_id() IN
                          (t.client_user_id,t.transporter_user_id,t.admin_user_id)));
REVOKE UPDATE, DELETE ON public.chat_messages FROM PUBLIC, anon, authenticated;


\echo validating_DB_06
CREATE OR REPLACE FUNCTION public.can_read_agreement(target_id bigint)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog AS $$
SELECT EXISTS (
    SELECT 1 FROM public.agreements a
    WHERE a.id=target_id
      AND (a.client_user_id=public.current_app_user_id()
           OR (public.current_app_role()='transporter'::public.app_role
               AND EXISTS (
                   SELECT 1 FROM public.agreement_trucks t
                   WHERE t.agreement_id=a.id
                     AND t.transporter_user_id=public.current_app_user_id()))))
$$;
REVOKE ALL ON FUNCTION public.can_read_agreement(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.can_read_agreement(bigint) TO authenticated;
DROP POLICY IF EXISTS agreements_parties ON public.agreements;
DROP POLICY IF EXISTS agr_trucks_parties ON public.agreement_trucks;
CREATE POLICY agreements_parties ON public.agreements
    FOR SELECT TO authenticated USING(public.can_read_agreement(id));
CREATE POLICY agr_trucks_parties ON public.agreement_trucks
    FOR SELECT TO authenticated USING(public.can_read_agreement(agreement_id));


\echo validating_DB_07
CREATE TABLE public.driver_hire_contracts (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    driver_user_id bigint NOT NULL REFERENCES public.driver_profiles(user_id) ON DELETE RESTRICT,
    transporter_user_id bigint NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    monthly_salary numeric(14,2) NOT NULL
        CHECK(monthly_salary>0 AND monthly_salary<'Infinity'::numeric),
    contract_months integer NOT NULL CHECK(contract_months BETWEEN 1 AND 60),
    terms text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'offered'
        CHECK(status IN('offered','active','declined','terminated','expired')),
    accepted_at timestamptz,
    ended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK(driver_user_id<>transporter_user_id),
    CHECK(status<>'active' OR accepted_at IS NOT NULL)
);
CREATE UNIQUE INDEX driver_hire_one_active_per_driver
    ON public.driver_hire_contracts(driver_user_id) WHERE status='active';
CREATE INDEX driver_hire_driver_created
    ON public.driver_hire_contracts(driver_user_id,created_at DESC);
CREATE INDEX driver_hire_transporter_created
    ON public.driver_hire_contracts(transporter_user_id,created_at DESC);
ALTER TABLE public.driver_hire_contracts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.driver_hire_contracts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.driver_hire_contracts TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.driver_hire_contracts_id_seq TO service_role;


\echo validating_DB_10
ALTER TABLE public.wallets ADD CONSTRAINT wallets_money_invariants
CHECK(balance>=0 AND balance<'Infinity'::numeric
      AND locked_balance>=0 AND locked_balance<'Infinity'::numeric
      AND locked_balance<=balance
      AND minimum_required>=0 AND minimum_required<'Infinity'::numeric)
NOT VALID;
ALTER TABLE public.wallets VALIDATE CONSTRAINT wallets_money_invariants;
ALTER TABLE public.marketplace_parts ADD CONSTRAINT marketplace_parts_finite_price
CHECK(price>=0 AND price<'Infinity'::numeric
      AND (discounted_price IS NULL OR
           (discounted_price>=0 AND discounted_price<=price))) NOT VALID;
ALTER TABLE public.marketplace_parts VALIDATE CONSTRAINT marketplace_parts_finite_price;


\echo validating_DB_12
DROP POLICY IF EXISTS action_logs_own_insert ON public.user_action_logs;
REVOKE INSERT,UPDATE,DELETE ON public.user_action_logs FROM PUBLIC,anon,authenticated;
REVOKE USAGE ON SEQUENCE public.user_action_logs_id_seq FROM PUBLIC,anon,authenticated;
GRANT INSERT,SELECT ON public.user_action_logs TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.user_action_logs_id_seq TO service_role;


\echo validating_DB_13
DROP POLICY IF EXISTS vehicles_active_read ON public.vehicles;
DROP POLICY IF EXISTS agr_post_trucks_read ON public.agreement_post_trucks;
DROP POLICY IF EXISTS agr_bid_trucks_read ON public.agreement_bid_trucks;
DROP POLICY IF EXISTS rfq_read ON public.part_rfqs;
REVOKE SELECT ON public.vehicles,public.agreement_post_trucks,
    public.agreement_bid_trucks,public.part_rfqs FROM PUBLIC,anon,authenticated;

SELECT 'all_selected_corrections_accepted' AS validation;
