-- Phase 4B-1 Security Remediation (DB-CRIT-001 & DB-HIGH-002)
-- 1. Create dedicated non-owner least-privilege runtime roles
-- 2. Lock down residual anon/authenticated privileges on sensitive/reference tables & views
-- 3. Grant strictly scoped table/column/sequence privileges & narrow RLS policies per role

BEGIN;

DO $$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY[
        'dtx_api_runtime',
        'dtx_scheduler_worker',
        'dtx_auditor_ro'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name
        ) THEN
            EXECUTE pg_catalog.format(
                'CREATE ROLE %I NOLOGIN NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION',
                role_name
            );
        END IF;
    END LOOP;
END
$$;

DO $$
BEGIN
    ALTER ROLE dtx_auditor_ro SET default_transaction_read_only = on;
EXCEPTION
    WHEN insufficient_privilege THEN NULL;
END
$$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC, anon, authenticated, dtx_api_runtime, dtx_scheduler_worker, dtx_auditor_ro;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role, dtx_api_runtime, dtx_scheduler_worker, dtx_auditor_ro;

-- Clear any default/prior grants on runtime roles before applying least-privilege grants.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM dtx_api_runtime, dtx_scheduler_worker, dtx_auditor_ro;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM dtx_api_runtime, dtx_scheduler_worker, dtx_auditor_ro;

-- ---------------------------------------------------------------------------
-- 1. Lock down residual anon / authenticated privileges (DB-HIGH-002)
--    All V1 UI requests go through Flask; direct PostgREST access to auth
--    secrets, login audit PII, commission/terms writes, and views is denied.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    relation_name text;
    sequence_name text;
    columns_sql text;
    existing_policy record;
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'password_reset_otps',
        'login_activity',
        'commission_policies',
        'terms_versions'
    ] LOOP
        EXECUTE pg_catalog.format(
            'REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated',
            relation_name
        );
        SELECT string_agg(quote_ident(attname), ',' ORDER BY attnum)
          INTO columns_sql
          FROM pg_catalog.pg_attribute
         WHERE attrelid = to_regclass(pg_catalog.format('public.%I', relation_name))
           AND attnum > 0
           AND NOT attisdropped;
        IF columns_sql IS NOT NULL THEN
            EXECUTE pg_catalog.format(
                'REVOKE SELECT(%s), INSERT(%s), UPDATE(%s), REFERENCES(%s) ON public.%I FROM PUBLIC, anon, authenticated',
                columns_sql, columns_sql, columns_sql, columns_sql, relation_name
            );
        END IF;
        sequence_name := pg_get_serial_sequence(pg_catalog.format('public.%I', relation_name), 'id');
        IF sequence_name IS NOT NULL THEN
            EXECUTE pg_catalog.format(
                'REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon, authenticated',
                sequence_name
            );
            EXECUTE pg_catalog.format(
                'GRANT USAGE, SELECT ON SEQUENCE %s TO service_role',
                sequence_name
            );
        END IF;
        FOR existing_policy IN
            SELECT policyname
              FROM pg_policies
             WHERE schemaname = 'public' AND tablename = relation_name
        LOOP
            EXECUTE pg_catalog.format('DROP POLICY %I ON public.%I', existing_policy.policyname, relation_name);
        END LOOP;
        EXECUTE pg_catalog.format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO service_role',
            relation_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY backend_only ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true)',
            relation_name
        );
    END LOOP;

    FOREACH relation_name IN ARRAY ARRAY[
        'saved_payment_methods_safe',
        'transporter_review_aggregates'
    ] LOOP
        EXECUTE pg_catalog.format(
            'REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated',
            relation_name
        );
        SELECT string_agg(quote_ident(attname), ',' ORDER BY attnum)
          INTO columns_sql
          FROM pg_catalog.pg_attribute
         WHERE attrelid = to_regclass(pg_catalog.format('public.%I', relation_name))
           AND attnum > 0
           AND NOT attisdropped;
        IF columns_sql IS NOT NULL THEN
            EXECUTE pg_catalog.format(
                'REVOKE SELECT(%s), INSERT(%s), UPDATE(%s), REFERENCES(%s) ON public.%I FROM PUBLIC, anon, authenticated',
                columns_sql, columns_sql, columns_sql, columns_sql, relation_name
            );
        END IF;
        EXECUTE pg_catalog.format(
            'GRANT SELECT ON public.%I TO service_role',
            relation_name
        );
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- 2. dtx_api_runtime (Flask API runtime — strictly scoped DML + narrow RLS)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    tbl text;
    seq text;
    api_read_only text[] := ARRAY[
        'security_reserve_brackets',
        'security_reserve_policy',
        'canonical_event_catalog_projection'
    ];
    api_append_only text[] := ARRAY[
        'financial_journal',
        'financial_journal_lines',
        'freight_settlement_resolutions',
        'security_reserve_entries',
        'delivery_incident_evidence',
        'wallet_transactions',
        'withdrawal_limit_upgrade_requests',
        'security_events',
        'business_audit_events',
        'shipment_status_history',
        'login_activity',
        'user_action_logs',
        'contact_messages',
        'documents',
        'shipment_cancellations',
        'shipment_trip_reviews',
        'terms_acknowledgements',
        'signup_terms_acceptances',
        'driver_incidents',
        'driver_reviews',
        'driver_gps_pings',
        'driver_fuel_logs',
        'trip_cancellation_requests',
        'commission_policies',
        'terms_versions'
    ];
    api_read_write_no_delete text[] := ARRAY[
        'admin_step_up_authorizations',
        'mpin_step_up_authorizations',
        'trusted_devices',
        'user_sessions',
        'password_reset_otps',
        'reset_tokens',
        'transporter_profiles',
        'driver_profiles',
        'driver_hire_contracts',
        'driver_trip_assignments',
        'drivers',
        'vehicles',
        'shipments',
        'shipment_bids',
        'shipment_trips',
        'shipment_no_show_tracking',
        'shipment_notifications',
        'shipment_disputes',
        'chat_threads',
        'chat_messages',
        'payments',
        'saved_payment_methods',
        'user_payment_preferences',
        'wallets',
        'wallet_withdrawal_requests',
        'delivery_otp_challenges',
        'freight_settlements',
        'security_reserves',
        'operational_incidents',
        'owner_operator_credentials'
    ];
    api_delete_narrow text[] := ARRAY[
        'http_rate_limits',
        'mpin_credentials',
        'everyday_user_profiles',
        'service_seeker_profiles',
        'users'
    ];
BEGIN
    FOREACH tbl IN ARRAY api_read_only LOOP
        EXECUTE pg_catalog.format('GRANT SELECT ON TABLE public.%I TO dtx_api_runtime', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_select ON public.%I', tbl);
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_select ON public.%I FOR SELECT TO dtx_api_runtime USING (true)',
            tbl
        );
    END LOOP;

    FOREACH tbl IN ARRAY ARRAY['saved_payment_methods_safe', 'transporter_review_aggregates'] LOOP
        EXECUTE pg_catalog.format('GRANT SELECT ON public.%I TO dtx_api_runtime', tbl);
    END LOOP;

    FOREACH tbl IN ARRAY api_append_only LOOP
        EXECUTE pg_catalog.format('GRANT SELECT, INSERT ON TABLE public.%I TO dtx_api_runtime', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_select ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_insert ON public.%I', tbl);
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_select ON public.%I FOR SELECT TO dtx_api_runtime USING (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_insert ON public.%I FOR INSERT TO dtx_api_runtime WITH CHECK (true)',
            tbl
        );
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute
            WHERE attrelid = to_regclass(pg_catalog.format('public.%I', tbl))
              AND attname = 'id' AND NOT attisdropped
        ) THEN
            seq := pg_get_serial_sequence(pg_catalog.format('public.%I', tbl), 'id');
            IF seq IS NOT NULL THEN
                EXECUTE pg_catalog.format('GRANT USAGE, SELECT ON SEQUENCE %s TO dtx_api_runtime', seq);
            END IF;
        END IF;
    END LOOP;

    FOREACH tbl IN ARRAY api_read_write_no_delete LOOP
        EXECUTE pg_catalog.format('GRANT SELECT, INSERT, UPDATE ON TABLE public.%I TO dtx_api_runtime', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_select ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_insert ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_update ON public.%I', tbl);
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_select ON public.%I FOR SELECT TO dtx_api_runtime USING (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_insert ON public.%I FOR INSERT TO dtx_api_runtime WITH CHECK (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_update ON public.%I FOR UPDATE TO dtx_api_runtime USING (true) WITH CHECK (true)',
            tbl
        );
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute
            WHERE attrelid = to_regclass(pg_catalog.format('public.%I', tbl))
              AND attname = 'id' AND NOT attisdropped
        ) THEN
            seq := pg_get_serial_sequence(pg_catalog.format('public.%I', tbl), 'id');
            IF seq IS NOT NULL THEN
                EXECUTE pg_catalog.format('GRANT USAGE, SELECT ON SEQUENCE %s TO dtx_api_runtime', seq);
            END IF;
        END IF;
    END LOOP;

    FOREACH tbl IN ARRAY api_delete_narrow LOOP
        EXECUTE pg_catalog.format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO dtx_api_runtime', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_select ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_insert ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_update ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS api_runtime_delete ON public.%I', tbl);
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_select ON public.%I FOR SELECT TO dtx_api_runtime USING (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_insert ON public.%I FOR INSERT TO dtx_api_runtime WITH CHECK (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY api_runtime_update ON public.%I FOR UPDATE TO dtx_api_runtime USING (true) WITH CHECK (true)',
            tbl
        );
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute
            WHERE attrelid = to_regclass(pg_catalog.format('public.%I', tbl))
              AND attname = 'id' AND NOT attisdropped
        ) THEN
            seq := pg_get_serial_sequence(pg_catalog.format('public.%I', tbl), 'id');
            IF seq IS NOT NULL THEN
                EXECUTE pg_catalog.format('GRANT USAGE, SELECT ON SEQUENCE %s TO dtx_api_runtime', seq);
            END IF;
        END IF;
    END LOOP;
END
$$;

GRANT USAGE, SELECT ON SEQUENCE public.mpin_credential_generation_seq TO dtx_api_runtime;

CREATE POLICY api_runtime_delete ON public.http_rate_limits
    FOR DELETE TO dtx_api_runtime USING (expires_at < pg_catalog.now());
CREATE POLICY api_runtime_delete ON public.mpin_credentials
    FOR DELETE TO dtx_api_runtime USING (true);
CREATE POLICY api_runtime_delete ON public.everyday_user_profiles
    FOR DELETE TO dtx_api_runtime USING (true);
CREATE POLICY api_runtime_delete ON public.service_seeker_profiles
    FOR DELETE TO dtx_api_runtime USING (true);
CREATE POLICY api_runtime_delete ON public.users
    FOR DELETE TO dtx_api_runtime
    USING (role <> 'admin'::public.app_role AND is_blocked = false AND credentials_version = 0);

GRANT EXECUTE ON FUNCTION public.is_bounded_event_json(jsonb, text) TO dtx_api_runtime;

-- ---------------------------------------------------------------------------
-- 3. dtx_scheduler_worker (Overdue confirmations & due settlements ONLY)
-- ---------------------------------------------------------------------------
GRANT SELECT (id, role, legacy_role, is_blocked) ON TABLE public.users TO dtx_scheduler_worker;
DROP POLICY IF EXISTS scheduler_worker_select ON public.users;
CREATE POLICY scheduler_worker_select ON public.users
    FOR SELECT TO dtx_scheduler_worker USING (true);

GRANT SELECT ON TABLE public.security_reserves TO dtx_scheduler_worker;
DROP POLICY IF EXISTS scheduler_worker_select ON public.security_reserves;
CREATE POLICY scheduler_worker_select ON public.security_reserves
    FOR SELECT TO dtx_scheduler_worker USING (true);

DO $$
DECLARE
    tbl text;
    seq text;
    sched_update_only text[] := ARRAY[
        'shipments',
        'shipment_trips',
        'payments',
        'freight_settlements',
        'wallets'
    ];
    sched_insert_only text[] := ARRAY[
        'shipment_notifications',
        'wallet_transactions',
        'financial_journal',
        'financial_journal_lines'
    ];
    sched_insert_update text[] := ARRAY[
        'shipment_disputes',
        'chat_threads'
    ];
BEGIN
    FOREACH tbl IN ARRAY sched_update_only LOOP
        EXECUTE pg_catalog.format('GRANT SELECT, UPDATE ON TABLE public.%I TO dtx_scheduler_worker', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS scheduler_worker_select ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS scheduler_worker_update ON public.%I', tbl);
        EXECUTE pg_catalog.format(
            'CREATE POLICY scheduler_worker_select ON public.%I FOR SELECT TO dtx_scheduler_worker USING (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY scheduler_worker_update ON public.%I FOR UPDATE TO dtx_scheduler_worker USING (true) WITH CHECK (true)',
            tbl
        );
    END LOOP;

    FOREACH tbl IN ARRAY sched_insert_only LOOP
        EXECUTE pg_catalog.format('GRANT SELECT, INSERT ON TABLE public.%I TO dtx_scheduler_worker', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS scheduler_worker_select ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS scheduler_worker_insert ON public.%I', tbl);
        EXECUTE pg_catalog.format(
            'CREATE POLICY scheduler_worker_select ON public.%I FOR SELECT TO dtx_scheduler_worker USING (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY scheduler_worker_insert ON public.%I FOR INSERT TO dtx_scheduler_worker WITH CHECK (true)',
            tbl
        );
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute
            WHERE attrelid = to_regclass(pg_catalog.format('public.%I', tbl))
              AND attname = 'id' AND NOT attisdropped
        ) THEN
            seq := pg_get_serial_sequence(pg_catalog.format('public.%I', tbl), 'id');
            IF seq IS NOT NULL THEN
                EXECUTE pg_catalog.format('GRANT USAGE, SELECT ON SEQUENCE %s TO dtx_scheduler_worker', seq);
            END IF;
        END IF;
    END LOOP;

    FOREACH tbl IN ARRAY sched_insert_update LOOP
        EXECUTE pg_catalog.format('GRANT SELECT, INSERT, UPDATE ON TABLE public.%I TO dtx_scheduler_worker', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS scheduler_worker_select ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS scheduler_worker_insert ON public.%I', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS scheduler_worker_update ON public.%I', tbl);
        EXECUTE pg_catalog.format(
            'CREATE POLICY scheduler_worker_select ON public.%I FOR SELECT TO dtx_scheduler_worker USING (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY scheduler_worker_insert ON public.%I FOR INSERT TO dtx_scheduler_worker WITH CHECK (true)',
            tbl
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY scheduler_worker_update ON public.%I FOR UPDATE TO dtx_scheduler_worker USING (true) WITH CHECK (true)',
            tbl
        );
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute
            WHERE attrelid = to_regclass(pg_catalog.format('public.%I', tbl))
              AND attname = 'id' AND NOT attisdropped
        ) THEN
            seq := pg_get_serial_sequence(pg_catalog.format('public.%I', tbl), 'id');
            IF seq IS NOT NULL THEN
                EXECUTE pg_catalog.format('GRANT USAGE, SELECT ON SEQUENCE %s TO dtx_scheduler_worker', seq);
            END IF;
        END IF;
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- 4. dtx_auditor_ro (Read-only financial reconciliation & compliance export)
-- ---------------------------------------------------------------------------
GRANT SELECT (id, role, legacy_role, is_blocked, created_at) ON TABLE public.users TO dtx_auditor_ro;
DROP POLICY IF EXISTS auditor_ro_select ON public.users;
CREATE POLICY auditor_ro_select ON public.users
    FOR SELECT TO dtx_auditor_ro USING (true);

DO $$
DECLARE
    tbl text;
    auditor_tables text[] := ARRAY[
        'financial_journal',
        'financial_journal_lines',
        'freight_settlements',
        'freight_settlement_resolutions',
        'security_reserves',
        'security_reserve_entries',
        'security_reserve_policy',
        'security_reserve_brackets',
        'wallets',
        'wallet_transactions',
        'wallet_withdrawal_requests',
        'withdrawal_limit_upgrade_requests',
        'payments',
        'shipments',
        'shipment_bids',
        'shipment_trips',
        'shipment_disputes',
        'shipment_status_history',
        'commission_policies',
        'terms_versions',
        'terms_acknowledgements',
        'signup_terms_acceptances',
        'delivery_incident_evidence',
        'owner_operator_credentials',
        'operational_incidents',
        'trip_cancellation_requests',
        'security_events',
        'business_audit_events',
        'canonical_event_catalog_projection'
    ];
BEGIN
    FOREACH tbl IN ARRAY auditor_tables LOOP
        EXECUTE pg_catalog.format('GRANT SELECT ON TABLE public.%I TO dtx_auditor_ro', tbl);
        EXECUTE pg_catalog.format('DROP POLICY IF EXISTS auditor_ro_select ON public.%I', tbl);
        EXECUTE pg_catalog.format(
            'CREATE POLICY auditor_ro_select ON public.%I FOR SELECT TO dtx_auditor_ro USING (true)',
            tbl
        );
    END LOOP;
    GRANT SELECT ON public.transporter_review_aggregates TO dtx_auditor_ro;
END
$$;

-- RLS helper functions referenced by existing permissive TO PUBLIC policies
GRANT EXECUTE ON FUNCTION public.current_app_user_id() TO dtx_api_runtime, dtx_scheduler_worker, dtx_auditor_ro;
GRANT EXECUTE ON FUNCTION public.current_app_role() TO dtx_api_runtime, dtx_scheduler_worker, dtx_auditor_ro;
GRANT EXECUTE ON FUNCTION public.is_admin() TO dtx_api_runtime, dtx_scheduler_worker, dtx_auditor_ro;
GRANT EXECUTE ON FUNCTION public.is_transporter_assigned_to_shipment(bigint) TO dtx_api_runtime, dtx_scheduler_worker, dtx_auditor_ro;

COMMIT;
