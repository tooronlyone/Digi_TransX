-- Phase 1B-2A: activate the bounded login/logout security event integration.
-- The two Phase 1B-1 migrations are already applied and must remain immutable.
-- This migration mutates only the catalog projection; it creates no event or business rows.

begin;

create or replace function pg_temp.canonical_event_semantic_signature()
returns text
language plpgsql
stable
as $signature$
declare
    validation_phase integer := 1;
    actual_signature text;
begin
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
            cross join lateral aclexplode(
                coalesce(relation.relacl, acldefault('r', relation.relowner))
            ) as privilege
            left join pg_roles as grantee on grantee.oid = privilege.grantee
            where namespace.nspname = 'public'
              and relation.relname in (
                  'security_events', 'business_audit_events',
                  'canonical_event_catalog_projection'
              )
              and privilege.grantee <> relation.relowner
              and (
                  validation_phase = 1
                  or relation.relname not in ('security_events', 'business_audit_events')
              )

            union all
            select format(
                'table_privilege|%s|service_role|%s|f',
                table_names.table_name, privilege_names.privilege_name
            )
            from unnest(array['security_events', 'business_audit_events'])
                as table_names(table_name)
            cross join unnest(array['DELETE', 'INSERT', 'SELECT'])
                as privilege_names(privilege_name)
            where validation_phase = 0

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
    return actual_signature;
end
$signature$;

do $migration$
declare
    prior_signature text;
    final_signature text;
    event_row_count bigint;
    selected_integrated integer;
    other_integrated integer;
    affected integer;
    expected_prior_signature constant text := '772212260b85fd6b5cd4aa35ca9ffdfb';
    expected_final_signature constant text := 'f5168975e0605fe0f7b84c1276a0082a';
    selected_names constant text[] := array[
        'security.login.started',
        'security.login.failed',
        'security.login.succeeded',
        'security.logout.completed'
    ];
begin
    lock table public.canonical_event_catalog_projection in access exclusive mode;
    lock table public.security_events in access exclusive mode;
    lock table public.business_audit_events in access exclusive mode;

    prior_signature := pg_temp.canonical_event_semantic_signature();

    select
        count(*) filter (where integrated and event_name = any(selected_names)),
        count(*) filter (where integrated and not (event_name = any(selected_names)))
      into selected_integrated, other_integrated
      from public.canonical_event_catalog_projection;

    if selected_integrated = 0 and other_integrated = 0 then
        if prior_signature is distinct from expected_prior_signature then
            raise exception using
                errcode = '55000',
                message = 'Phase 1B-2A requires the exact corrected Phase 1B-1 foundation',
                detail = format(
                    'expected signature %s, found %s',
                    expected_prior_signature, prior_signature
                );
        end if;

        select count(*) into event_row_count
        from (
            select event_id from public.security_events
            union all
            select event_id from public.business_audit_events
        ) as existing_events;
        if event_row_count <> 0 then
            raise exception using
                errcode = '55000',
                message = 'Phase 1B-2A first activation requires both event tables to be empty';
        end if;

        alter table public.canonical_event_catalog_projection
            drop constraint canonical_event_catalog_projection_integrated_check;
        alter table public.canonical_event_catalog_projection
            add constraint canonical_event_catalog_projection_integrated_check
            check (
                not integrated
                or (
                    lifecycle_status = 'planned'
                    and writable
                    and category in ('security', 'business_audit')
                )
            );

        update public.canonical_event_catalog_projection
        set integrated = true
        where event_name = any(selected_names)
          and event_version = 1
          and category = 'security'
          and ownership_domain = 'security'
          and retention_class = 'security_12_months'
          and lifecycle_status = 'planned'
          and writable
          and not integrated;
        get diagnostics affected = row_count;
        if affected <> 4 then
            raise exception using
                errcode = '55000',
                message = 'Phase 1B-2A activation did not update exactly four locked definitions';
        end if;
    elsif selected_integrated = 4 and other_integrated = 0 then
        if prior_signature is distinct from expected_final_signature then
            raise exception using
                errcode = '55000',
                message = 'Phase 1B-2A prior activation is partial or incompatible',
                detail = format(
                    'expected signature %s, found %s',
                    expected_final_signature, prior_signature
                );
        end if;
    else
        raise exception using
            errcode = '55000',
            message = 'Phase 1B-2A catalog activation is partial or unexpected';
    end if;

    if (select count(*) from public.canonical_event_catalog_projection) <> 157
       or (
           select count(*)
           from public.canonical_event_catalog_projection
           where integrated and event_name = any(selected_names)
       ) <> 4
       or (
           select count(*)
           from public.canonical_event_catalog_projection
           where integrated and not (event_name = any(selected_names))
       ) <> 0
       or (
           select count(*)
           from public.canonical_event_catalog_projection
           where lifecycle_status = 'planned' and not integrated
       ) <> 145
       or (
           select count(*)
           from public.canonical_event_catalog_projection
           where lifecycle_status = 'deferred' and integrated
       ) <> 0 then
        raise exception using
            errcode = '55000',
            message = 'Phase 1B-2A final catalog counts do not match the locked contract';
    end if;

    final_signature := pg_temp.canonical_event_semantic_signature();
    if final_signature is distinct from expected_final_signature then
        raise exception using
            errcode = '55000',
            message = 'Phase 1B-2A final semantic signature is incompatible',
            detail = format(
                'expected signature %s, found %s',
                expected_final_signature, final_signature
            );
    end if;
end
$migration$;

commit;
