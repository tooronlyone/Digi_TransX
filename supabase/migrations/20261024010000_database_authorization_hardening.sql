-- Forward-only remediation of the database authorization audit findings.
-- Prerequisite: the October portal migrations through 20261023203500.
-- Apply the complete file in one transaction. No existing identity is relinked.

DO $$
DECLARE relation_name text;
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'users','driver_profiles','marketplace_orders','shop_products',
        'shop_sales','shop_sale_items','contact_messages','fuel_station_pumps',
        'fuel_station_dispenses','driver_incidents','driver_reviews',
        'driver_trip_assignments','driver_gps_pings','driver_fuel_logs']
    LOOP
        IF to_regclass(format('public.%I',relation_name)) IS NULL THEN
            RAISE EXCEPTION 'Required public.% is missing; apply earlier feature migrations first',relation_name;
        END IF;
    END LOOP;
END $$;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS credentials_version bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS password_change_pending boolean NOT NULL DEFAULT false;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid='public.users'::regclass
                     AND conname='users_credentials_version_nonnegative') THEN
        ALTER TABLE public.users ADD CONSTRAINT users_credentials_version_nonnegative
            CHECK(credentials_version>=0);
    END IF;
END $$;

-- Auth user_metadata is caller-owned. Even an Admin API caller's metadata
-- cannot create privileged public authority. The trusted admin script/API
-- explicitly promotes the freshly created profile using its backend SQL role.
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog AS $$
DECLARE
    requested text := lower(trim(coalesce(NEW.raw_user_meta_data->>'legacy_role',
                                           NEW.raw_user_meta_data->>'role','everyday_user')));
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
    VALUES(NEW.id,NEW.email,coalesce(NEW.raw_user_meta_data->>'full_name',''),
           coalesce(NEW.raw_user_meta_data->>'phone',''),
           coalesce(nullif(NEW.raw_user_meta_data->>'cnic',''),'PENDING-'||NEW.id::text),
           safe_role,safe_legacy);
    -- A duplicate public email is a conflict, never an account-linking proof.
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.handle_new_auth_user() FROM PUBLIC,anon,authenticated;

-- Flask owns mutations and revalidates session/role/amount/state together.
-- Preserve participant reads; eliminate the parallel direct-write surface.
DO $$
DECLARE relation_name text; columns_sql text;
BEGIN
    FOREACH relation_name IN ARRAY ARRAY['users','service_seeker_profiles','everyday_user_profiles','transporter_profiles','fuel_station_profiles','shopkeeper_profiles','drivers','vehicles','shipments','shipment_bids','shipment_trips','shipment_status_history','documents','payments','wallets','wallet_transactions','wallet_withdrawal_requests','shipment_no_show_tracking','shipment_cancellations','shipment_notifications','shipment_disputes','shipment_trip_reviews','chat_threads','chat_messages','agreement_posts','agreement_post_trucks','agreement_bids','agreement_bid_trucks','agreements','agreement_trucks','agreement_trips','agreement_monthly_payments','agreement_payment_penalties','terms_acknowledgements','user_action_logs','marketplace_parts','marketplace_orders','marketplace_order_items','part_rfqs','part_rfq_bids']
    LOOP
        EXECUTE format('REVOKE INSERT,UPDATE,DELETE ON public.%I FROM PUBLIC,anon,authenticated',relation_name);
        SELECT string_agg(quote_ident(attname),',' ORDER BY attnum) INTO columns_sql
        FROM pg_attribute WHERE attrelid=to_regclass(format('public.%I',relation_name))
          AND attnum>0 AND NOT attisdropped;
        EXECUTE format('REVOKE INSERT(%s),UPDATE(%s) ON public.%I FROM PUBLIC,anon,authenticated',
                       columns_sql,columns_sql,relation_name);
    END LOOP;
END $$;
DROP POLICY IF EXISTS users_update_own ON public.users;
DROP POLICY IF EXISTS action_logs_own_insert ON public.user_action_logs;

-- Replace broad owner FOR ALL policies as defense in depth against an
-- accidental future table-level write grant.
DO $$
DECLARE target record;
BEGIN
    FOR target IN SELECT * FROM (VALUES
        ('transporter_profiles','transporter_profile_own','user_id'),
        ('fuel_station_profiles','fuel_station_profile_own','user_id'),
        ('shopkeeper_profiles','shopkeeper_profile_own','user_id'),
        ('drivers','drivers_owner_all','owner_user_id'),
        ('vehicles','vehicles_owner_all','owner_user_id'),
        ('shipments','shipments_client_own','client_user_id'),
        ('shipment_bids','bids_transporter_own','transporter_user_id'),
        ('shipment_trips','trips_transporter_own','transporter_user_id'),
        ('documents','documents_owner_all','owner_user_id'),
        ('wallet_withdrawal_requests','withdrawals_own','user_id'),
        ('agreement_posts','agr_posts_client_own','client_user_id'),
        ('agreement_bids','agr_bids_transporter_own','transporter_user_id'),
        ('agreement_trips','agr_trips_transporter_own','transporter_user_id'),
        ('marketplace_parts','parts_shop_manage','shop_user_id')
    ) AS policies(table_name,policy_name,owner_column)
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I',target.policy_name,target.table_name);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated '
                       'USING(%I=public.current_app_user_id())',
                       target.policy_name,target.table_name,target.owner_column);
    END LOOP;
END $$;

DROP POLICY IF EXISTS chat_threads_participants ON public.chat_threads;
CREATE POLICY chat_threads_participants ON public.chat_threads
    FOR SELECT TO authenticated USING(
        public.current_app_user_id() IN(client_user_id,transporter_user_id,admin_user_id));
DROP POLICY IF EXISTS chat_messages_participants ON public.chat_messages;
DROP POLICY IF EXISTS chat_messages_member_read ON public.chat_messages;
DROP POLICY IF EXISTS chat_messages_member_insert ON public.chat_messages;
CREATE POLICY chat_messages_member_read ON public.chat_messages
    FOR SELECT TO authenticated USING(EXISTS(
        SELECT 1 FROM public.chat_threads t
        WHERE t.id=thread_id AND public.current_app_user_id() IN
            (t.client_user_id,t.transporter_user_id,t.admin_user_id)));
CREATE POLICY chat_messages_member_insert ON public.chat_messages
    FOR INSERT TO authenticated WITH CHECK(
        sender_user_id=public.current_app_user_id() AND EXISTS(
            SELECT 1 FROM public.chat_threads t
            WHERE t.id=thread_id AND public.current_app_user_id() IN
                (t.client_user_id,t.transporter_user_id,t.admin_user_id)));
-- INSERT remains revoked: the insert policy is a backstop, not a second API.

-- SECURITY DEFINER reads only a boolean for the caller's own identity and
-- never accepts a caller-supplied user/tenant ID.
CREATE OR REPLACE FUNCTION public.can_read_agreement(target_id bigint)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog AS $$
SELECT EXISTS(
    SELECT 1 FROM public.agreements a
    WHERE a.id=target_id
      AND (a.client_user_id=public.current_app_user_id()
           OR (public.current_app_role()='transporter'::public.app_role
               AND EXISTS(SELECT 1 FROM public.agreement_trucks t
                          WHERE t.agreement_id=a.id
                            AND t.transporter_user_id=public.current_app_user_id()))))
$$;
REVOKE ALL ON FUNCTION public.can_read_agreement(bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.can_read_agreement(bigint) TO authenticated;
DROP POLICY IF EXISTS agreements_parties ON public.agreements;
DROP POLICY IF EXISTS agr_trucks_parties ON public.agreement_trucks;
CREATE POLICY agreements_parties ON public.agreements
    FOR SELECT TO authenticated USING(public.can_read_agreement(id));
CREATE POLICY agr_trucks_parties ON public.agreement_trucks
    FOR SELECT TO authenticated USING(public.can_read_agreement(agreement_id));

-- Existing POS tables already use RLS; harden their ACL alongside the nine
-- omitted tables. The backend service policy works even without BYPASSRLS.
DO $$
DECLARE relation_name text; sequence_name text;
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'contact_messages','fuel_station_pumps','fuel_station_dispenses',
        'driver_profiles','driver_incidents','driver_reviews',
        'driver_trip_assignments','driver_gps_pings','driver_fuel_logs',
        'shop_products','shop_sales','shop_sale_items']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',relation_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC,anon,authenticated',relation_name);
        EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON public.%I TO service_role',relation_name);
        EXECUTE format('DROP POLICY IF EXISTS backend_service_access ON public.%I',relation_name);
        EXECUTE format('CREATE POLICY backend_service_access ON public.%I FOR ALL TO service_role '
                       'USING(true) WITH CHECK(true)',relation_name);
        sequence_name := NULL;
        IF EXISTS(SELECT 1 FROM pg_attribute
                  WHERE attrelid=to_regclass(format('public.%I',relation_name))
                    AND attname='id' AND NOT attisdropped) THEN
            sequence_name := pg_get_serial_sequence(format('public.%I',relation_name),'id');
        END IF;
        IF sequence_name IS NOT NULL THEN
            EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC,anon,authenticated',sequence_name);
            EXECUTE format('GRANT USAGE,SELECT ON SEQUENCE %s TO service_role',sequence_name);
        END IF;
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS public.driver_hire_contracts(
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    driver_user_id bigint NOT NULL REFERENCES public.driver_profiles(user_id) ON DELETE RESTRICT,
    transporter_user_id bigint NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    monthly_salary numeric(14,2) NOT NULL,
    contract_months integer NOT NULL DEFAULT 12,
    terms text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'offered',
    offered_at timestamptz DEFAULT now(),
    accepted_at timestamptz,
    terminated_at timestamptz,
    ended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- An older TEST installation created this table outside migrations with
-- offered_at/terminated_at but without the canonical audit timestamps. Keep
-- those legacy columns and derive the added timestamps from their evidence.
ALTER TABLE public.driver_hire_contracts
    ADD COLUMN IF NOT EXISTS offered_at timestamptz DEFAULT now(),
    ADD COLUMN IF NOT EXISTS terminated_at timestamptz,
    ADD COLUMN IF NOT EXISTS ended_at timestamptz,
    ADD COLUMN IF NOT EXISTS created_at timestamptz,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz;
UPDATE public.driver_hire_contracts
    SET created_at=coalesce(offered_at,now()) WHERE created_at IS NULL;
UPDATE public.driver_hire_contracts
    SET updated_at=created_at WHERE updated_at IS NULL;
UPDATE public.driver_hire_contracts
    SET ended_at=terminated_at WHERE ended_at IS NULL AND terminated_at IS NOT NULL;
-- Do not invent a missing salary/term/driver binding to make legacy rows fit.
-- Invalid rows make the complete migration roll back for explicit repair.
DO $$
BEGIN
    IF EXISTS(SELECT 1 FROM public.driver_hire_contracts
              WHERE monthly_salary IS NULL OR monthly_salary<=0
                 OR NOT(monthly_salary<'Infinity'::numeric)
                 OR monthly_salary<>round(monthly_salary,2)
                 OR monthly_salary>=1000000000000
                 OR contract_months IS NULL OR contract_months NOT BETWEEN 1 AND 60
                 OR terms IS NULL
                 OR status NOT IN('offered','active','declined','terminated','expired')
                 OR driver_user_id=transporter_user_id
                 OR (status='active' AND accepted_at IS NULL)) THEN
        RAISE EXCEPTION 'Existing driver hire contracts need explicit reconciliation';
    END IF;
END $$;
ALTER TABLE public.driver_hire_contracts
    ALTER COLUMN monthly_salary TYPE numeric(14,2) USING monthly_salary::numeric(14,2),
    ALTER COLUMN contract_months SET DEFAULT 12,
    ALTER COLUMN contract_months SET NOT NULL,
    ALTER COLUMN terms SET DEFAULT '',
    ALTER COLUMN terms SET NOT NULL,
    ALTER COLUMN status TYPE text USING status::text,
    ALTER COLUMN created_at SET DEFAULT now(),
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE public.driver_hire_contracts
    DROP CONSTRAINT IF EXISTS driver_hire_contracts_driver_user_id_fkey,
    DROP CONSTRAINT IF EXISTS driver_hire_contracts_transporter_user_id_fkey;
ALTER TABLE public.driver_hire_contracts
    ADD CONSTRAINT driver_hire_contracts_driver_user_id_fkey
        FOREIGN KEY(driver_user_id) REFERENCES public.driver_profiles(user_id) ON DELETE RESTRICT,
    ADD CONSTRAINT driver_hire_contracts_transporter_user_id_fkey
        FOREIGN KEY(transporter_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
DO $$
DECLARE item record;
BEGIN
    FOR item IN SELECT * FROM (VALUES
        ('driver_hire_salary_valid', 'monthly_salary>0 AND monthly_salary<''Infinity''::numeric'),
        ('driver_hire_duration_valid', 'contract_months BETWEEN 1 AND 60'),
        ('driver_hire_status_valid', 'status IN(''offered'',''active'',''declined'',''terminated'',''expired'')'),
        ('driver_hire_distinct_parties', 'driver_user_id<>transporter_user_id'),
        ('driver_hire_active_acceptance', 'status<>''active'' OR accepted_at IS NOT NULL')
    ) AS checks(name,expression)
    LOOP
        IF NOT EXISTS(SELECT 1 FROM pg_constraint
                      WHERE conrelid='public.driver_hire_contracts'::regclass AND conname=item.name) THEN
            EXECUTE format('ALTER TABLE public.driver_hire_contracts ADD CONSTRAINT %I CHECK(%s)',item.name,item.expression);
        END IF;
    END LOOP;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS driver_hire_one_active_per_driver
    ON public.driver_hire_contracts(driver_user_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS driver_hire_driver_created
    ON public.driver_hire_contracts(driver_user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS driver_hire_transporter_created
    ON public.driver_hire_contracts(transporter_user_id,created_at DESC);
ALTER TABLE public.driver_hire_contracts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.driver_hire_contracts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.driver_hire_contracts TO service_role;
REVOKE ALL ON SEQUENCE public.driver_hire_contracts_id_seq FROM PUBLIC,anon,authenticated;
GRANT USAGE,SELECT ON SEQUENCE public.driver_hire_contracts_id_seq TO service_role;
DROP POLICY IF EXISTS backend_service_access ON public.driver_hire_contracts;
CREATE POLICY backend_service_access ON public.driver_hire_contracts
    FOR ALL TO service_role USING(true) WITH CHECK(true);
DROP TRIGGER IF EXISTS trg_driver_hire_contracts_updated_at ON public.driver_hire_contracts;
CREATE TRIGGER trg_driver_hire_contracts_updated_at BEFORE UPDATE ON public.driver_hire_contracts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
