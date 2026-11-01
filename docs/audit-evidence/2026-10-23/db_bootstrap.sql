\set ON_ERROR_STOP on
CREATE ROLE anon;
CREATE ROLE authenticated;
CREATE ROLE service_role BYPASSRLS;
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
