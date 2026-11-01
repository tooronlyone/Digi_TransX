-- Phase 1B-1 forward-only correction: narrow additive Supabase default ACLs.
-- This migration changes no rows, policies, triggers, functions, catalog
-- definitions, default privileges, or historical migration state.

do $$
declare
    validation_phase integer;
    owned_object_count integer;
    event_row_count bigint;
    actual_signature text;
    expected_signature constant text := '772212260b85fd6b5cd4aa35ca9ffdfb';
    service_role_oid oid;
    relation_owner oid;
    all_table_privileges text[];
    narrow_privileges constant text[] := array['DELETE', 'INSERT', 'SELECT'];
    security_privileges text[];
    business_privileges text[];
    unexpected_acl_count integer;
    target_table text;
    client_role text;
    privilege_name text;
    effective_privileges text[];
begin
    select oid into service_role_oid from pg_roles where rolname = 'service_role';
    if service_role_oid is null then
        raise exception using
            errcode = '55000',
            message = 'canonical event ACL hardening requires role service_role';
    end if;

    for validation_phase in 0..1 loop
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

        if owned_object_count <> 25
           or to_regclass('public.security_events') is null
           or to_regclass('public.business_audit_events') is null
           or to_regclass('public.canonical_event_catalog_projection') is null
           or to_regprocedure('public.is_bounded_event_json(jsonb,text)') is null
           or to_regprocedure('public.prevent_canonical_event_update()') is null
           or to_regprocedure('public.enforce_canonical_event_contract()') is null then
            raise exception using
                errcode = '55000',
                message = 'canonical event foundation is partial or incompatible; refusing ACL mutation';
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
                message = 'canonical event ACL hardening requires both event tables to remain empty';
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

        if actual_signature is distinct from expected_signature then
            raise exception using
                errcode = '55000',
                message = 'canonical event foundation semantic contract is incompatible',
                detail = format('expected signature %s, found %s', expected_signature, actual_signature);
        end if;

        select relowner into relation_owner
        from pg_class
        where oid = 'public.security_events'::regclass;
        select array_agg(privilege_type order by privilege_type) into all_table_privileges
        from aclexplode(acldefault('r', relation_owner))
        where grantee = relation_owner;

        select array_agg(privilege.privilege_type order by privilege.privilege_type)
          into security_privileges
        from pg_class as relation
        cross join lateral aclexplode(
            coalesce(relation.relacl, acldefault('r', relation.relowner))
        ) as privilege
        where relation.oid = 'public.security_events'::regclass
          and privilege.grantee = service_role_oid;

        select array_agg(privilege.privilege_type order by privilege.privilege_type)
          into business_privileges
        from pg_class as relation
        cross join lateral aclexplode(
            coalesce(relation.relacl, acldefault('r', relation.relowner))
        ) as privilege
        where relation.oid = 'public.business_audit_events'::regclass
          and privilege.grantee = service_role_oid;

        select count(*) into unexpected_acl_count
        from pg_class as relation
        cross join lateral aclexplode(
            coalesce(relation.relacl, acldefault('r', relation.relowner))
        ) as privilege
        where relation.oid in (
            'public.security_events'::regclass,
            'public.business_audit_events'::regclass,
            'public.canonical_event_catalog_projection'::regclass
        )
          and privilege.grantee <> relation.relowner
          and not (
              relation.relname in ('security_events', 'business_audit_events')
              and privilege.grantee = service_role_oid
          );
        if unexpected_acl_count <> 0 then
            raise exception using
                errcode = '55000',
                message = 'canonical event tables contain an unexpected grantee';
        end if;

        if validation_phase = 0 then
            if not (
                (security_privileges = narrow_privileges
                 and business_privileges = narrow_privileges)
                or
                (security_privileges = all_table_privileges
                 and business_privileges = all_table_privileges)
            ) then
                raise exception using
                    errcode = '55000',
                    message = 'service_role ACL is neither the known additive-default state nor the exact narrow state';
            end if;

            execute 'REVOKE ALL PRIVILEGES ON TABLE public.security_events FROM service_role';
            execute 'REVOKE ALL PRIVILEGES ON TABLE public.business_audit_events FROM service_role';
            execute 'GRANT SELECT, INSERT, DELETE ON TABLE public.security_events TO service_role';
            execute 'GRANT SELECT, INSERT, DELETE ON TABLE public.business_audit_events TO service_role';
        else
            if security_privileges <> narrow_privileges
               or business_privileges <> narrow_privileges then
                raise exception using
                    errcode = '55000',
                    message = 'service_role ACL hardening did not produce the exact narrow state';
            end if;

            foreach target_table in array array[
                'security_events', 'business_audit_events',
                'canonical_event_catalog_projection'
            ] loop
                foreach client_role in array array['anon', 'authenticated'] loop
                    foreach privilege_name in array all_table_privileges loop
                        if has_table_privilege(
                            client_role,
                            format('public.%I', target_table),
                            privilege_name
                        ) then
                            raise exception using
                                errcode = '55000',
                                message = format(
                                    '%s retains unexpected %s privilege on public.%s',
                                    client_role, privilege_name, target_table
                                );
                        end if;
                    end loop;
                end loop;
            end loop;

            foreach privilege_name in array all_table_privileges loop
                if has_table_privilege(
                    'service_role',
                    'public.canonical_event_catalog_projection',
                    privilege_name
                ) then
                    raise exception using
                        errcode = '55000',
                        message = 'service_role retains access to the canonical event projection';
                end if;
            end loop;

            foreach target_table in array array[
                'security_events', 'business_audit_events'
            ] loop
                select array_agg(
                    privilege_names.privilege_name
                    order by privilege_names.privilege_name
                )
                  into effective_privileges
                from unnest(all_table_privileges)
                    as privilege_names(privilege_name)
                where has_table_privilege(
                    'service_role', format('public.%I', target_table),
                    privilege_names.privilege_name
                );
                if effective_privileges <> narrow_privileges then
                    raise exception using
                        errcode = '55000',
                        message = format(
                            'service_role effective privileges remain broader than intended on public.%s',
                            target_table
                        );
                end if;
            end loop;
        end if;
    end loop;
end
$$;
