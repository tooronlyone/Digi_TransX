-- Phase 1B-1: canonical event foundation only.
-- No runtime route is connected, no historical row is copied, and no outbox
-- is created because there is no current asynchronous event consumer.

do $$
declare
    owned_object_count integer;
    actual_signature text;
    expected_signature constant text := '772212260b85fd6b5cd4aa35ca9ffdfb';
begin
    -- A clean database has none of the migration-owned objects.  Any other
    -- pre-existing state must be the exact completed foundation.  The
    -- signature deliberately excludes OIDs and other generated metadata.
    select count(*) into owned_object_count
    from (
        select c.oid
        from pg_class as c
        join pg_namespace as n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relkind in ('r', 'p', 'v', 'm', 'S', 'i')
          and (
              c.relname in (
                  'security_events', 'business_audit_events',
                  'canonical_event_catalog_projection'
              )
              or c.relname like 'canonical_event_%'
              or c.relname like '%security_events%'
              or c.relname like '%business_audit_events%'
          )
        union all
        select p.oid
        from pg_proc as p
        join pg_namespace as n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and (
              p.proname in (
                  'is_bounded_event_json', 'prevent_canonical_event_update',
                  'enforce_canonical_event_contract'
              )
              or p.proname like '%canonical_event%'
              or p.proname like 'is_bounded_event_json%'
          )
    ) as owned_objects;

    if owned_object_count = 0 then
        return;
    end if;

    if owned_object_count <> 25
       or to_regclass('public.security_events') is null
       or to_regclass('public.business_audit_events') is null
       or to_regclass('public.canonical_event_catalog_projection') is null
       or to_regprocedure('public.is_bounded_event_json(jsonb,text)') is null
       or to_regprocedure('public.prevent_canonical_event_update()') is null
       or to_regprocedure('public.enforce_canonical_event_contract()') is null then
        raise exception using
            errcode = '55000',
            message = 'canonical event foundation is partial or incompatible; refusing to modify it';
    end if;

    with signature_items as (
        select format(
            'column|%s|%s|%s|%s|%s|%s|%s|%s',
            relation.relname, attribute.attnum, attribute.attname,
            pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
            attribute.attnotnull,
            coalesce(pg_get_expr(default_value.adbin, default_value.adrelid), ''),
            attribute.attidentity, attribute.attgenerated
        ) as item
        from pg_class as relation
        join pg_namespace as namespace on namespace.oid = relation.relnamespace
        join pg_attribute as attribute on attribute.attrelid = relation.oid
        left join pg_attrdef as default_value
          on default_value.adrelid = relation.oid
         and default_value.adnum = attribute.attnum
        where namespace.nspname = 'public'
          and relation.relname in (
              'security_events', 'business_audit_events',
              'canonical_event_catalog_projection'
          )
          and attribute.attnum > 0
          and not attribute.attisdropped

        union all
        select format(
            'constraint|%s|%s|%s|%s|%s|%s', relation.relname,
            constraint_value.conname, constraint_value.contype,
            constraint_value.condeferrable, constraint_value.condeferred,
            pg_get_constraintdef(constraint_value.oid, false)
        )
        from pg_constraint as constraint_value
        join pg_class as relation on relation.oid = constraint_value.conrelid
        join pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public'
          and relation.relname in (
              'security_events', 'business_audit_events',
              'canonical_event_catalog_projection'
          )

        union all
        select format(
            'index|%s|%s|%s|%s|%s|%s', table_value.relname,
            index_value.relname, metadata.indisunique, metadata.indisprimary,
            metadata.indisvalid, pg_get_indexdef(index_value.oid)
        )
        from pg_index as metadata
        join pg_class as table_value on table_value.oid = metadata.indrelid
        join pg_class as index_value on index_value.oid = metadata.indexrelid
        join pg_namespace as namespace on namespace.oid = table_value.relnamespace
        where namespace.nspname = 'public'
          and table_value.relname in (
              'security_events', 'business_audit_events',
              'canonical_event_catalog_projection'
          )

        union all
        select format(
            'trigger|%s|%s|%s|%s', relation.relname, trigger_value.tgname,
            trigger_value.tgenabled, pg_get_triggerdef(trigger_value.oid, false)
        )
        from pg_trigger as trigger_value
        join pg_class as relation on relation.oid = trigger_value.tgrelid
        join pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public'
          and relation.relname in (
              'security_events', 'business_audit_events',
              'canonical_event_catalog_projection'
          )
          and not trigger_value.tgisinternal

        union all
        select format(
            'function|%s|%s|%s|%s|%s|%s|%s|%s|%s', function_value.proname,
            pg_get_function_identity_arguments(function_value.oid),
            pg_get_function_result(function_value.oid), language.lanname,
            function_value.provolatile, function_value.proisstrict,
            function_value.prosecdef,
            coalesce(array_to_string(function_value.proconfig, ','), ''),
            function_value.prosrc
        )
        from pg_proc as function_value
        join pg_namespace as namespace on namespace.oid = function_value.pronamespace
        join pg_language as language on language.oid = function_value.prolang
        where namespace.nspname = 'public'
          and function_value.proname in (
              'is_bounded_event_json', 'prevent_canonical_event_update',
              'enforce_canonical_event_contract'
          )

        union all
        select format(
            'rls|%s|%s|%s', relation.relname, relation.relrowsecurity,
            relation.relforcerowsecurity
        )
        from pg_class as relation
        join pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public'
          and relation.relname in (
              'security_events', 'business_audit_events',
              'canonical_event_catalog_projection'
          )

        union all
        select format(
            'policy|%s|%s|%s|%s|%s|%s', policy.tablename,
            policy.policyname, policy.permissive, array_to_string(policy.roles, ','),
            policy.cmd, coalesce(policy.qual, '') || '|' || coalesce(policy.with_check, '')
        )
        from pg_policies as policy
        where policy.schemaname = 'public'
          and policy.tablename in (
              'security_events', 'business_audit_events',
              'canonical_event_catalog_projection'
          )

        union all
        select format(
            'table_privilege|%s|%s|%s|%s', relation.relname,
            coalesce(grantee.rolname, 'PUBLIC'),
            privilege.privilege_type, privilege.is_grantable
        )
        from pg_class as relation
        join pg_namespace as namespace on namespace.oid = relation.relnamespace
        cross join lateral aclexplode(coalesce(relation.relacl, acldefault('r', relation.relowner)))
            as privilege
        left join pg_roles as grantee on grantee.oid = privilege.grantee
        where namespace.nspname = 'public'
          and relation.relname in (
              'security_events', 'business_audit_events',
              'canonical_event_catalog_projection'
          )
          and privilege.grantee <> relation.relowner

        union all
        select format(
            'function_privilege|%s|%s|%s|%s', function_value.proname,
            coalesce(grantee.rolname, 'PUBLIC'), privilege.privilege_type,
            privilege.is_grantable
        )
        from pg_proc as function_value
        join pg_namespace as namespace on namespace.oid = function_value.pronamespace
        cross join lateral aclexplode(
            coalesce(function_value.proacl, acldefault('f', function_value.proowner))
        ) as privilege
        left join pg_roles as grantee on grantee.oid = privilege.grantee
        where namespace.nspname = 'public'
          and function_value.proname in (
              'is_bounded_event_json', 'prevent_canonical_event_update',
              'enforce_canonical_event_contract'
          )
          and privilege.grantee <> function_value.proowner

        union all
        select format(
            'catalog|%s|%s|%s|%s|%s|%s|%s|%s', event_name, event_version,
            category, ownership_domain, retention_class, lifecycle_status,
            writable, integrated
        )
        from public.canonical_event_catalog_projection
    )
    select md5(string_agg(item, E'\n' order by item)) into actual_signature
    from signature_items;

    if actual_signature is distinct from expected_signature then
        raise exception using
            errcode = '55000',
            message = 'canonical event foundation is partial or incompatible; refusing to modify it',
            detail = format('expected semantic signature %s, found %s', expected_signature, actual_signature);
    end if;
end
$$;

create table if not exists public.canonical_event_catalog_projection (
    event_name text primary key,
    event_version smallint not null,
    category text not null,
    ownership_domain text not null,
    retention_class text not null,
    lifecycle_status text not null,
    writable boolean not null,
    integrated boolean not null,
    constraint canonical_event_catalog_projection_name_check check (
        event_name ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$'
        and length(event_name) <= 128
    ),
    constraint canonical_event_catalog_projection_version_check check (event_version > 0),
    constraint canonical_event_catalog_projection_category_check check (
        category in ('security', 'business_audit', 'operations')
    ),
    constraint canonical_event_catalog_projection_domain_check check (
        ownership_domain ~ '^[a-z][a-z0-9_]{0,63}$'
    ),
    constraint canonical_event_catalog_projection_retention_check check (
        retention_class in (
            'security_12_months', 'security_24_months', 'business_24_months',
            'financial_7_years', 'operations_90_days'
        )
    ),
    constraint canonical_event_catalog_projection_lifecycle_check check (
        lifecycle_status in ('planned', 'deferred')
    ),
    constraint canonical_event_catalog_projection_writable_check check (
        not writable
        or (lifecycle_status = 'planned' and category in ('security', 'business_audit'))
    ),
    constraint canonical_event_catalog_projection_integrated_check check (not integrated)
);

insert into public.canonical_event_catalog_projection (
    event_name, event_version, category, ownership_domain, retention_class,
    lifecycle_status, writable, integrated
) values
    ('security.signup.started', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.signup.gps_result_recorded', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.signup.email_otp_sent', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.signup.email_otp_failed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.signup.completed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.login.started', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.login.failed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.login.gps_result_recorded', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.login.email_otp_sent', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.login.email_otp_failed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.login.succeeded', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.login.new_device_detected', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.login.suspicious_detected', 1, 'security', 'security', 'security_24_months', 'planned', true, false),
    ('security.session.refreshed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.session.expired_inactivity', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.session.revoked', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.logout.completed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.password.changed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.password_reset.requested', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.password_reset.completed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.trusted_device.added', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.trusted_device.removed', 1, 'security', 'security', 'security_12_months', 'planned', true, false),
    ('security.account.locked', 1, 'security', 'security', 'security_24_months', 'planned', true, false),
    ('security.account.unlocked', 1, 'security', 'security', 'security_24_months', 'planned', true, false),
    ('admin.security_action.performed', 1, 'security', 'admin', 'security_24_months', 'planned', true, false),
    ('one_time.order.created', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.order.updated', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.order.cancelled', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.order.expired', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.order.reopened', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.bid.submitted', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.bid.updated', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.bid.withdrawn', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.bid.accepted', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.bid.rejected', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.bid.expired', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.checkout.completed', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.checkout.cancelled', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.checkout.reversed', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.payment.held', 1, 'business_audit', 'one_time', 'financial_7_years', 'planned', true, false),
    ('one_time.payment.disputed', 1, 'business_audit', 'one_time', 'financial_7_years', 'planned', true, false),
    ('one_time.payment.released', 1, 'business_audit', 'one_time', 'financial_7_years', 'planned', true, false),
    ('one_time.payment.refunded', 1, 'business_audit', 'one_time', 'financial_7_years', 'planned', true, false),
    ('one_time.payment.reversal_recorded', 1, 'business_audit', 'one_time', 'financial_7_years', 'planned', true, false),
    ('one_time.payment.provider_webhook_applied', 1, 'business_audit', 'one_time', 'financial_7_years', 'planned', true, false),
    ('wallet.topup.completed', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.order_funding.debited', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.card_shortfall.credited', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.order_refund.credited', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.transporter_payout.credited', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.withdrawal.requested', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.withdrawal.approved', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.withdrawal.rejected', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.security_lock.enabled', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('wallet.security_lock.disabled', 1, 'business_audit', 'wallet', 'financial_7_years', 'planned', true, false),
    ('commission.policy.created', 1, 'business_audit', 'commission', 'financial_7_years', 'planned', true, false),
    ('commission.policy.scheduled', 1, 'business_audit', 'commission', 'financial_7_years', 'planned', true, false),
    ('commission.policy.activated', 1, 'business_audit', 'commission', 'financial_7_years', 'planned', true, false),
    ('commission.policy.deactivated', 1, 'business_audit', 'commission', 'financial_7_years', 'planned', true, false),
    ('commission.policy.activation_cancelled', 1, 'business_audit', 'commission', 'financial_7_years', 'planned', true, false),
    ('terms.version.created', 1, 'business_audit', 'terms', 'financial_7_years', 'planned', true, false),
    ('terms.version.published', 1, 'business_audit', 'terms', 'financial_7_years', 'planned', true, false),
    ('terms.version.retired', 1, 'business_audit', 'terms', 'financial_7_years', 'planned', true, false),
    ('terms.version.publication_cancelled', 1, 'business_audit', 'terms', 'financial_7_years', 'planned', true, false),
    ('terms.acknowledgement.recorded', 1, 'business_audit', 'terms', 'financial_7_years', 'planned', true, false),
    ('terms.acknowledgement.reconfirmed', 1, 'business_audit', 'terms', 'financial_7_years', 'planned', true, false),
    ('one_time.trip.created', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.trip.started', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.delivery.completion_requested', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.delivery.confirmed', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.delivery.rejected', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.delivery.confirmation_timed_out', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.trip.completed', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.trip.resolved_client', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.dispute.opened', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.dispute.transporter_statement_submitted', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.dispute.admin_reviewed', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.dispute.resolved_transporter_win', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.dispute.resolved_client_win', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.dispute.evidence_accessed', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.chat.thread_created', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.chat.message_sent', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.chat.message_read', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.chat.thread_closed', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.review.submitted', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.review.replay_detected', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('one_time.review.moderated', 1, 'business_audit', 'one_time', 'business_24_months', 'planned', true, false),
    ('transporter.profile.created', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.profile.updated', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.profile.status_changed', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.profile.verification_submitted', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.profile.verified', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.profile.verification_rejected', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.profile.payout_method_changed', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.truck.created', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.truck.updated', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.truck.activated', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.truck.deactivated', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.truck.location_updated', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.truck.document_linked', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.truck.archived', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.truck.verification_changed', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.driver.created', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.driver.updated', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.driver.activated', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.driver.deactivated', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.driver.assigned_to_truck', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.driver.unassigned_from_truck', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.driver.document_linked', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.driver.verification_changed', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.document.uploaded', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.document.replaced', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.document.verification_requested', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.document.verified', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.document.rejected', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.document.expired', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.document.archived', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('transporter.document.accessed', 1, 'business_audit', 'transporter', 'business_24_months', 'planned', true, false),
    ('matching.bid_eligibility_validated', 1, 'business_audit', 'matching', 'business_24_months', 'planned', true, false),
    ('matching.checkout_eligibility_revalidated', 1, 'business_audit', 'matching', 'business_24_months', 'planned', true, false),
    ('matching.bid_attempt_rejected', 1, 'business_audit', 'matching', 'business_24_months', 'planned', true, false),
    ('matching.policy_updated', 1, 'business_audit', 'matching', 'business_24_months', 'planned', true, false),
    ('notification.created', 1, 'business_audit', 'notification', 'business_24_months', 'planned', true, false),
    ('notification.delivery_attempted', 1, 'business_audit', 'notification', 'business_24_months', 'planned', true, false),
    ('notification.sent', 1, 'business_audit', 'notification', 'business_24_months', 'planned', true, false),
    ('notification.delivered', 1, 'business_audit', 'notification', 'business_24_months', 'planned', true, false),
    ('notification.failed', 1, 'business_audit', 'notification', 'business_24_months', 'planned', true, false),
    ('notification.retry_scheduled', 1, 'business_audit', 'notification', 'business_24_months', 'planned', true, false),
    ('notification.failed_final', 1, 'business_audit', 'notification', 'business_24_months', 'planned', true, false),
    ('notification.action_completed', 1, 'business_audit', 'notification', 'business_24_months', 'planned', true, false),
    ('business.profile.created', 1, 'business_audit', 'business', 'business_24_months', 'planned', true, false),
    ('business.profile.updated', 1, 'business_audit', 'business', 'business_24_months', 'planned', true, false),
    ('business.profile.status_changed', 1, 'business_audit', 'business', 'business_24_months', 'planned', true, false),
    ('business.payment_method.added', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_method.default_changed', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_method.deactivated', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_method.expired', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_method.provider_revoked', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_preference.created', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_preference.updated', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_preference.auto_shortfall_enabled', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_preference.auto_shortfall_disabled', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('business.payment_preference.default_method_changed', 1, 'business_audit', 'business', 'financial_7_years', 'planned', true, false),
    ('system.job.started', 1, 'operations', 'system', 'operations_90_days', 'planned', false, false),
    ('system.job.completed', 1, 'operations', 'system', 'operations_90_days', 'planned', false, false),
    ('system.job.failed', 1, 'operations', 'system', 'operations_90_days', 'planned', false, false),
    ('system.job.skipped', 1, 'operations', 'system', 'operations_90_days', 'planned', false, false),
    ('system.job.lock_not_acquired', 1, 'operations', 'system', 'operations_90_days', 'planned', false, false),
    ('system.job.manual_triggered', 1, 'operations', 'system', 'operations_90_days', 'planned', false, false),
    ('one_time.qr_payment.intent_created', 1, 'business_audit', 'one_time', 'business_24_months', 'deferred', false, false),
    ('one_time.qr_payment.confirmed', 1, 'business_audit', 'one_time', 'business_24_months', 'deferred', false, false),
    ('one_time.qr_payment.expired', 1, 'business_audit', 'one_time', 'business_24_months', 'deferred', false, false),
    ('one_time.qr_payment.cancelled', 1, 'business_audit', 'one_time', 'business_24_months', 'deferred', false, false),
    ('one_time.qr_payment.failed', 1, 'business_audit', 'one_time', 'business_24_months', 'deferred', false, false),
    ('one_time.qr_payment.amount_mismatch', 1, 'business_audit', 'one_time', 'business_24_months', 'deferred', false, false),
    ('one_time.qr_payment.refunded', 1, 'business_audit', 'one_time', 'business_24_months', 'deferred', false, false),
    ('one_time.qr_payment.webhook_applied', 1, 'business_audit', 'one_time', 'business_24_months', 'deferred', false, false)
on conflict (event_name) do nothing;

create or replace function public.is_bounded_event_json(event_value jsonb, value_kind text)
returns boolean
language plpgsql
immutable
set search_path = pg_catalog, public
as $$
declare
    string_keys text[];
    integer_keys text[];
    boolean_keys text[];
    max_bytes integer;
    item record;
    item_type text;
begin
    if event_value is null or jsonb_typeof(event_value) <> 'object' then
        return false;
    end if;

    if value_kind = 'state' then
        string_keys := array['status', 'currency', 'method', 'decision', 'delivery_status'];
        integer_keys := array['version', 'amount_minor'];
        boolean_keys := array['enabled', 'verified', 'active', 'is_default'];
        max_bytes := 1024;
    elsif value_kind = 'metadata' then
        string_keys := array[
            'result_code', 'currency', 'channel', 'delivery_method', 'risk_tier',
            'provider_event_type'
        ];
        integer_keys := array[
            'policy_version', 'attempt_number', 'item_count', 'amount_minor'
        ];
        boolean_keys := array['is_replay'];
        max_bytes := 2048;
    else
        return false;
    end if;

    if pg_column_size(event_value) > max_bytes
       or (select count(*) from jsonb_object_keys(event_value)) > 16 then
        return false;
    end if;

    for item in
        select json_member.key, json_member.value as member
        from jsonb_each(event_value) as json_member
    loop
        item_type := jsonb_typeof(item.member);
        if item.key = any(string_keys) then
            if item_type <> 'string'
               or length(item.member #>> '{}') > 128
               or item.member #>> '{}' !~ '^[a-z][a-z0-9_.:-]{0,127}$' then
                return false;
            end if;
        elsif item.key = any(integer_keys) then
            if item_type <> 'number'
               or item.member::text !~ '^(0|[1-9][0-9]*)$' then
                return false;
            end if;
        elsif item.key = any(boolean_keys) then
            if item_type <> 'boolean' then
                return false;
            end if;
        else
            return false;
        end if;
    end loop;
    return true;
end
$$;

create or replace function public.prevent_canonical_event_update()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    raise exception 'canonical event rows are append-only; UPDATE is forbidden';
end
$$;

create or replace function public.enforce_canonical_event_contract()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    definition record;
    expected_category text;
begin
    expected_category := case tg_table_name
        when 'security_events' then 'security'
        when 'business_audit_events' then 'business_audit'
        else null
    end;
    if expected_category is null then
        raise exception using
            errcode = '23514',
            message = 'canonical event contract trigger is attached to an unknown table';
    end if;

    select event_version, category, retention_class, writable
      into definition
      from public.canonical_event_catalog_projection
     where event_name = new.event_name;

    if not found
       or not definition.writable
       or definition.event_version <> new.event_version
       or definition.category <> new.category
       or definition.category <> expected_category
       or definition.retention_class <> new.retention_class then
        raise exception using
            errcode = '23514',
            message = 'event does not match a writable canonical catalog definition';
    end if;

    if new.actor_type in ('user', 'admin')
       and (new.actor_id is null or new.actor_role is null) then
        raise exception using
            errcode = '23514',
            message = 'user and admin canonical events require actor_id and actor_role';
    end if;

    return new;
end
$$;

create table if not exists public.security_events (
    event_id uuid primary key default gen_random_uuid(),
    event_name text not null,
    event_version smallint not null,
    category text not null,
    actor_type text not null,
    actor_id bigint,
    actor_role text,
    subject_user_id bigint,
    order_id bigint,
    bid_id bigint,
    trip_id bigint,
    payment_id bigint,
    wallet_id bigint,
    wallet_transaction_id bigint,
    withdrawal_id bigint,
    dispute_id bigint,
    chat_thread_id bigint,
    review_id bigint,
    policy_id bigint,
    terms_version_id bigint,
    notification_id bigint,
    transporter_profile_id bigint,
    truck_id bigint,
    driver_id bigint,
    document_id bigint,
    agreement_id bigint,
    request_id text not null,
    correlation_id text,
    session_ref text,
    device_ref text,
    source text not null,
    provider_mode text not null,
    environment text not null,
    before_state jsonb not null default '{}'::jsonb,
    after_state jsonb not null default '{}'::jsonb,
    reason_code text,
    metadata jsonb not null default '{}'::jsonb,
    retention_class text not null,
    consent_category text,
    occurred_at timestamptz not null default now(),
    idempotency_scope text,
    idempotency_key text,
    fingerprint text,
    constraint security_events_name_format check (
        event_name ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$'
        and length(event_name) <= 128
    ),
    constraint security_events_version_check check (event_version = 1),
    constraint security_events_category_check check (category = 'security'),
    constraint security_events_actor_check check (
        actor_type in ('user', 'admin', 'system', 'provider', 'anonymous')
        and (
            actor_type not in ('user', 'admin')
            or (actor_id is not null and actor_role is not null)
        )
    ),
    constraint security_events_actor_role_check check (
        actor_role is null or actor_role ~ '^[a-z][a-z0-9_:-]{0,63}$'
    ),
    constraint security_events_related_ids_check check (
        (order_id is null or order_id > 0)
        and (bid_id is null or bid_id > 0)
        and (trip_id is null or trip_id > 0)
        and (payment_id is null or payment_id > 0)
        and (wallet_id is null or wallet_id > 0)
        and (wallet_transaction_id is null or wallet_transaction_id > 0)
        and (withdrawal_id is null or withdrawal_id > 0)
        and (dispute_id is null or dispute_id > 0)
        and (chat_thread_id is null or chat_thread_id > 0)
        and (review_id is null or review_id > 0)
        and (policy_id is null or policy_id > 0)
        and (terms_version_id is null or terms_version_id > 0)
        and (notification_id is null or notification_id > 0)
        and (transporter_profile_id is null or transporter_profile_id > 0)
        and (truck_id is null or truck_id > 0)
        and (driver_id is null or driver_id > 0)
        and (document_id is null or document_id > 0)
        and (agreement_id is null or agreement_id > 0)
        and (actor_id is null or actor_id > 0)
        and (subject_user_id is null or subject_user_id > 0)
    ),
    constraint security_events_request_check check (
        request_id ~ '^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$'
        and (correlation_id is null
             or correlation_id ~ '^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$')
    ),
    constraint security_events_safe_refs_check check (
        (session_ref is null or session_ref ~ '^session_[0-9a-f]{32}$')
        and (device_ref is null or device_ref ~ '^device_[0-9a-f]{32}$')
    ),
    constraint security_events_source_check check (
        source in (
            'server_route', 'domain_service', 'admin_route', 'scheduler',
            'manual_worker', 'provider_webhook', 'test'
        )
    ),
    constraint security_events_provider_check check (provider_mode in ('none', 'dummy', 'real')),
    constraint security_events_environment_check check (
        environment in ('local', 'test', 'staging', 'production')
    ),
    constraint security_events_json_check check (
        public.is_bounded_event_json(before_state, 'state')
        and public.is_bounded_event_json(after_state, 'state')
        and public.is_bounded_event_json(metadata, 'metadata')
    ),
    constraint security_events_reason_check check (
        reason_code is null or reason_code in (
            'user_request', 'policy_decision', 'risk_rule', 'provider_confirmation',
            'provider_rejection', 'timeout', 'manual_review', 'scheduled_transition',
            'system_recovery', 'not_applicable'
        )
    ),
    constraint security_events_retention_check check (
        retention_class in ('security_12_months', 'security_24_months')
    ),
    constraint security_events_consent_check check (consent_category is null),
    constraint security_events_idempotency_check check (
        (idempotency_scope is null and idempotency_key is null and fingerprint is null)
        or (
            idempotency_scope ~ '^[a-z0-9][a-z0-9_.:-]{0,127}$'
            and idempotency_key ~ '^[a-z0-9][a-z0-9_.:-]{0,127}$'
            and fingerprint ~ '^[0-9a-f]{64}$'
        )
    )
);

create table if not exists public.business_audit_events (
    event_id uuid primary key default gen_random_uuid(),
    event_name text not null,
    event_version smallint not null,
    category text not null,
    actor_type text not null,
    actor_id bigint,
    actor_role text,
    subject_user_id bigint,
    order_id bigint,
    bid_id bigint,
    trip_id bigint,
    payment_id bigint,
    wallet_id bigint,
    wallet_transaction_id bigint,
    withdrawal_id bigint,
    dispute_id bigint,
    chat_thread_id bigint,
    review_id bigint,
    policy_id bigint,
    terms_version_id bigint,
    notification_id bigint,
    transporter_profile_id bigint,
    truck_id bigint,
    driver_id bigint,
    document_id bigint,
    agreement_id bigint,
    request_id text not null,
    correlation_id text,
    session_ref text,
    device_ref text,
    source text not null,
    provider_mode text not null,
    environment text not null,
    before_state jsonb not null default '{}'::jsonb,
    after_state jsonb not null default '{}'::jsonb,
    reason_code text,
    metadata jsonb not null default '{}'::jsonb,
    retention_class text not null,
    consent_category text,
    occurred_at timestamptz not null default now(),
    idempotency_scope text,
    idempotency_key text,
    fingerprint text,
    constraint business_audit_events_name_format check (
        event_name ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$'
        and length(event_name) <= 128
    ),
    constraint business_audit_events_version_check check (event_version = 1),
    constraint business_audit_events_category_check check (category = 'business_audit'),
    constraint business_audit_events_actor_check check (
        actor_type in ('user', 'admin', 'system', 'provider', 'anonymous')
        and (
            actor_type not in ('user', 'admin')
            or (actor_id is not null and actor_role is not null)
        )
    ),
    constraint business_audit_events_actor_role_check check (
        actor_role is null or actor_role ~ '^[a-z][a-z0-9_:-]{0,63}$'
    ),
    constraint business_audit_events_related_ids_check check (
        (order_id is null or order_id > 0)
        and (bid_id is null or bid_id > 0)
        and (trip_id is null or trip_id > 0)
        and (payment_id is null or payment_id > 0)
        and (wallet_id is null or wallet_id > 0)
        and (wallet_transaction_id is null or wallet_transaction_id > 0)
        and (withdrawal_id is null or withdrawal_id > 0)
        and (dispute_id is null or dispute_id > 0)
        and (chat_thread_id is null or chat_thread_id > 0)
        and (review_id is null or review_id > 0)
        and (policy_id is null or policy_id > 0)
        and (terms_version_id is null or terms_version_id > 0)
        and (notification_id is null or notification_id > 0)
        and (transporter_profile_id is null or transporter_profile_id > 0)
        and (truck_id is null or truck_id > 0)
        and (driver_id is null or driver_id > 0)
        and (document_id is null or document_id > 0)
        and (agreement_id is null or agreement_id > 0)
        and (actor_id is null or actor_id > 0)
        and (subject_user_id is null or subject_user_id > 0)
    ),
    constraint business_audit_events_request_check check (
        request_id ~ '^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$'
        and (correlation_id is null
             or correlation_id ~ '^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$')
    ),
    constraint business_audit_events_safe_refs_check check (
        (session_ref is null or session_ref ~ '^session_[0-9a-f]{32}$')
        and (device_ref is null or device_ref ~ '^device_[0-9a-f]{32}$')
    ),
    constraint business_audit_events_source_check check (
        source in (
            'server_route', 'domain_service', 'admin_route', 'scheduler',
            'manual_worker', 'provider_webhook', 'test'
        )
    ),
    constraint business_audit_events_provider_check check (provider_mode in ('none', 'dummy', 'real')),
    constraint business_audit_events_environment_check check (
        environment in ('local', 'test', 'staging', 'production')
    ),
    constraint business_audit_events_json_check check (
        public.is_bounded_event_json(before_state, 'state')
        and public.is_bounded_event_json(after_state, 'state')
        and public.is_bounded_event_json(metadata, 'metadata')
    ),
    constraint business_audit_events_reason_check check (
        reason_code is null or reason_code in (
            'user_request', 'policy_decision', 'risk_rule', 'provider_confirmation',
            'provider_rejection', 'timeout', 'manual_review', 'scheduled_transition',
            'system_recovery', 'not_applicable'
        )
    ),
    constraint business_audit_events_retention_check check (
        retention_class in ('business_24_months', 'financial_7_years')
    ),
    constraint business_audit_events_consent_check check (consent_category is null),
    constraint business_audit_events_idempotency_check check (
        (idempotency_scope is null and idempotency_key is null and fingerprint is null)
        or (
            idempotency_scope ~ '^[a-z0-9][a-z0-9_.:-]{0,127}$'
            and idempotency_key ~ '^[a-z0-9][a-z0-9_.:-]{0,127}$'
            and fingerprint ~ '^[0-9a-f]{64}$'
        )
    )
);

drop trigger if exists trg_security_events_no_update on public.security_events;
create trigger trg_security_events_no_update
    before update on public.security_events
    for each row execute function public.prevent_canonical_event_update();

drop trigger if exists trg_security_events_contract on public.security_events;
create trigger trg_security_events_contract
    before insert on public.security_events
    for each row execute function public.enforce_canonical_event_contract();

drop trigger if exists trg_business_audit_events_no_update on public.business_audit_events;
create trigger trg_business_audit_events_no_update
    before update on public.business_audit_events
    for each row execute function public.prevent_canonical_event_update();

drop trigger if exists trg_business_audit_events_contract on public.business_audit_events;
create trigger trg_business_audit_events_contract
    before insert on public.business_audit_events
    for each row execute function public.enforce_canonical_event_contract();

create unique index if not exists uniq_security_events_idempotency
    on public.security_events (idempotency_scope, idempotency_key)
    where idempotency_key is not null;
create index if not exists idx_security_events_occurred
    on public.security_events (occurred_at desc);
create index if not exists idx_security_events_name_occurred
    on public.security_events (event_name, occurred_at desc);
create index if not exists idx_security_events_actor_occurred
    on public.security_events (actor_id, occurred_at desc) where actor_id is not null;
create index if not exists idx_security_events_subject_occurred
    on public.security_events (subject_user_id, occurred_at desc) where subject_user_id is not null;

create unique index if not exists uniq_business_audit_events_idempotency
    on public.business_audit_events (idempotency_scope, idempotency_key)
    where idempotency_key is not null;
create index if not exists idx_business_audit_events_occurred
    on public.business_audit_events (occurred_at desc);
create index if not exists idx_business_audit_events_name_occurred
    on public.business_audit_events (event_name, occurred_at desc);
create index if not exists idx_business_audit_events_actor_occurred
    on public.business_audit_events (actor_id, occurred_at desc) where actor_id is not null;
create index if not exists idx_business_audit_events_subject_occurred
    on public.business_audit_events (subject_user_id, occurred_at desc) where subject_user_id is not null;
create index if not exists idx_business_audit_events_order_occurred
    on public.business_audit_events (order_id, occurred_at desc) where order_id is not null;
create index if not exists idx_business_audit_events_trip_occurred
    on public.business_audit_events (trip_id, occurred_at desc) where trip_id is not null;
create index if not exists idx_business_audit_events_payment_occurred
    on public.business_audit_events (payment_id, occurred_at desc) where payment_id is not null;
create index if not exists idx_business_audit_events_wallet_tx_occurred
    on public.business_audit_events (wallet_transaction_id, occurred_at desc)
    where wallet_transaction_id is not null;
create index if not exists idx_business_audit_events_dispute_occurred
    on public.business_audit_events (dispute_id, occurred_at desc) where dispute_id is not null;
create index if not exists idx_business_audit_events_notification_occurred
    on public.business_audit_events (notification_id, occurred_at desc)
    where notification_id is not null;

alter table public.security_events enable row level security;
alter table public.business_audit_events enable row level security;
alter table public.canonical_event_catalog_projection enable row level security;

drop policy if exists security_events_service_role_all on public.security_events;
create policy security_events_service_role_all on public.security_events
    for all to service_role using (true) with check (true);
drop policy if exists business_audit_events_service_role_all on public.business_audit_events;
create policy business_audit_events_service_role_all on public.business_audit_events
    for all to service_role using (true) with check (true);

revoke all on table public.security_events from public;
revoke all on table public.business_audit_events from public;
revoke all on table public.canonical_event_catalog_projection from public;
revoke all on function public.is_bounded_event_json(jsonb, text) from public;
revoke all on function public.prevent_canonical_event_update() from public;
revoke all on function public.enforce_canonical_event_contract() from public;

do $$
declare
    client_role text;
begin
    foreach client_role in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = client_role) then
            execute format('revoke all on table public.security_events from %I', client_role);
            execute format('revoke all on table public.business_audit_events from %I', client_role);
            execute format(
                'revoke all on table public.canonical_event_catalog_projection from %I',
                client_role
            );
            execute format(
                'revoke all on function public.is_bounded_event_json(jsonb, text) from %I',
                client_role
            );
            execute format(
                'revoke all on function public.prevent_canonical_event_update() from %I',
                client_role
            );
            execute format(
                'revoke all on function public.enforce_canonical_event_contract() from %I',
                client_role
            );
        end if;
    end loop;

    if exists (select 1 from pg_roles where rolname = 'service_role') then
        grant select, insert, delete on public.security_events to service_role;
        grant select, insert, delete on public.business_audit_events to service_role;
        grant execute on function public.is_bounded_event_json(jsonb, text) to service_role;
        revoke all on table public.canonical_event_catalog_projection from service_role;
        revoke all on function public.prevent_canonical_event_update() from service_role;
        revoke all on function public.enforce_canonical_event_contract() from service_role;
    end if;
end
$$;
