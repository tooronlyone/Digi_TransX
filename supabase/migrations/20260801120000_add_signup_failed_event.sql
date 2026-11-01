-- Phase 1B-2B catalog correction: define the generic terminal signup failure.
-- This changes projection metadata only.  It neither activates the definition
-- nor creates event, business, policy, trigger, writer, or guard state.

begin;

create or replace function pg_temp.canonical_event_semantic_signature()
returns text
language plpgsql
stable
as $signature$
declare
    actual_signature text;
begin
    with signature_items as (
        select format('column|%s|%s|%s|%s|%s|%s|%s|%s', relation.relname, attribute.attnum, attribute.attname, pg_catalog.format_type(attribute.atttypid, attribute.atttypmod), attribute.attnotnull, coalesce(pg_get_expr(default_value.adbin, default_value.adrelid), ''), attribute.attidentity, attribute.attgenerated) as item
        from pg_class as relation join pg_namespace as namespace on namespace.oid = relation.relnamespace join pg_attribute as attribute on attribute.attrelid = relation.oid left join pg_attrdef as default_value on default_value.adrelid = relation.oid and default_value.adnum = attribute.attnum
        where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection') and attribute.attnum > 0 and not attribute.attisdropped

        union all select format('constraint|%s|%s|%s|%s|%s|%s', relation.relname, constraint_value.conname, constraint_value.contype, constraint_value.condeferrable, constraint_value.condeferred, pg_get_constraintdef(constraint_value.oid, false))
        from pg_constraint as constraint_value join pg_class as relation on relation.oid = constraint_value.conrelid join pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection')

        union all select format('index|%s|%s|%s|%s|%s|%s', table_value.relname, index_value.relname, metadata.indisunique, metadata.indisprimary, metadata.indisvalid, pg_get_indexdef(index_value.oid))
        from pg_index as metadata join pg_class as table_value on table_value.oid = metadata.indrelid join pg_class as index_value on index_value.oid = metadata.indexrelid join pg_namespace as namespace on namespace.oid = table_value.relnamespace
        where namespace.nspname = 'public' and table_value.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection')

        union all select format('trigger|%s|%s|%s|%s', relation.relname, trigger_value.tgname, trigger_value.tgenabled, pg_get_triggerdef(trigger_value.oid, false))
        from pg_trigger as trigger_value join pg_class as relation on relation.oid = trigger_value.tgrelid join pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection') and not trigger_value.tgisinternal

        union all select format('function|%s|%s|%s|%s|%s|%s|%s|%s|%s', function_value.proname, pg_get_function_identity_arguments(function_value.oid), pg_get_function_result(function_value.oid), language.lanname, function_value.provolatile, function_value.proisstrict, function_value.prosecdef, coalesce(array_to_string(function_value.proconfig, ','), ''), function_value.prosrc)
        from pg_proc as function_value join pg_namespace as namespace on namespace.oid = function_value.pronamespace join pg_language as language on language.oid = function_value.prolang
        where namespace.nspname = 'public' and function_value.proname in ('is_bounded_event_json', 'prevent_canonical_event_update', 'enforce_canonical_event_contract')

        union all select format('rls|%s|%s|%s', relation.relname, relation.relrowsecurity, relation.relforcerowsecurity)
        from pg_class as relation join pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection')

        union all select format('policy|%s|%s|%s|%s|%s|%s', policy.tablename, policy.policyname, policy.permissive, array_to_string(policy.roles, ','), policy.cmd, coalesce(policy.qual, '') || '|' || coalesce(policy.with_check, '')) from pg_policies as policy
        where policy.schemaname = 'public' and policy.tablename in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection')

        union all select format('table_privilege|%s|%s|%s|%s', relation.relname, coalesce(grantee.rolname, 'PUBLIC'), privilege.privilege_type, privilege.is_grantable)
        from pg_class as relation join pg_namespace as namespace on namespace.oid = relation.relnamespace cross join lateral aclexplode(coalesce(relation.relacl, acldefault('r', relation.relowner))) as privilege left join pg_roles as grantee on grantee.oid = privilege.grantee
        where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection') and privilege.grantee <> relation.relowner

        union all select format('function_privilege|%s|%s|%s|%s', function_value.proname, coalesce(grantee.rolname, 'PUBLIC'), privilege.privilege_type, privilege.is_grantable)
        from pg_proc as function_value join pg_namespace as namespace on namespace.oid = function_value.pronamespace cross join lateral aclexplode(coalesce(function_value.proacl, acldefault('f', function_value.proowner))) as privilege left join pg_roles as grantee on grantee.oid = privilege.grantee
        where namespace.nspname = 'public' and function_value.proname in ('is_bounded_event_json', 'prevent_canonical_event_update', 'enforce_canonical_event_contract') and privilege.grantee <> function_value.proowner

        union all select format('catalog|%s|%s|%s|%s|%s|%s|%s|%s', event_name, event_version, category, ownership_domain, retention_class, lifecycle_status, writable, integrated) from public.canonical_event_catalog_projection
    ) select md5(string_agg(item, E'\n' order by item)) into actual_signature from signature_items;
    return actual_signature;
end
$signature$;

do $migration$
declare
    actual_signature text;
    integrated_names text[];
    expected_pre_signature constant text := '7b8157021244549cfed79416b40ab662';
    expected_post_signature constant text := '993b1de965a1791a2a84ccff5fcfbdf9';
    expected_integrated_names constant text[] := array['security.login.failed', 'security.login.started', 'security.login.succeeded', 'security.logout.completed'];
begin
    lock table public.canonical_event_catalog_projection in access exclusive mode;
    lock table public.security_events in access exclusive mode;
    lock table public.business_audit_events in access exclusive mode;

    actual_signature := pg_temp.canonical_event_semantic_signature();
    select array_agg(event_name order by event_name) into integrated_names
      from public.canonical_event_catalog_projection where integrated;
    if integrated_names is distinct from expected_integrated_names then
        raise exception using errcode = '55000', message = 'signup failure catalog correction requires the exact four integrated definitions';
    end if;

    if actual_signature = expected_post_signature then
        if (select count(*) from public.canonical_event_catalog_projection) <> 158
           or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'planned') <> 150
           or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'deferred') <> 8
           or (select count(*) from public.canonical_event_catalog_projection where writable) <> 144
           or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 4 then
            raise exception using errcode = '55000', message = 'signup failure catalog correction post-state counts are incompatible';
        end if;
        return;
    end if;

    if actual_signature is distinct from expected_pre_signature
       or (select count(*) from public.canonical_event_catalog_projection) <> 157
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'planned') <> 149
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'deferred') <> 8
       or (select count(*) from public.canonical_event_catalog_projection where writable) <> 143
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 4
       or exists (select 1 from public.canonical_event_catalog_projection where event_name = 'security.signup.failed') then
        raise exception using errcode = '55000', message = 'signup failure catalog correction pre-state is partial or incompatible', detail = format('expected signature %s, found %s', expected_pre_signature, actual_signature);
    end if;

    if (select count(*) from pg_trigger as trigger_value join pg_class as relation on relation.oid = trigger_value.tgrelid join pg_namespace as namespace on namespace.oid = relation.relnamespace where namespace.nspname='public' and relation.relname in ('security_events', 'business_audit_events') and trigger_value.tgname in ('trg_security_events_contract', 'trg_business_audit_events_contract') and not trigger_value.tgisinternal) <> 2
       or to_regprocedure('public.enforce_canonical_event_contract()') is null
       or has_table_privilege('service_role', 'public.canonical_event_catalog_projection', 'select') then
        raise exception using errcode = '55000', message = 'signup failure catalog correction prerequisites are incomplete or unsafe';
    end if;

    insert into public.canonical_event_catalog_projection (
        event_name, event_version, category, ownership_domain, retention_class,
        lifecycle_status, writable, integrated
    ) values (
        'security.signup.failed', 1, 'security', 'security', 'security_12_months',
        'planned', true, false
    );

    if (select count(*) from public.canonical_event_catalog_projection where event_name = 'security.signup.failed') <> 1
       or (select count(*) from public.canonical_event_catalog_projection) <> 158
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'planned') <> 150
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'deferred') <> 8
       or (select count(*) from public.canonical_event_catalog_projection where writable) <> 144
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 4 then
        raise exception using errcode = '55000', message = 'signup failure catalog correction post-state is incompatible';
    end if;

    actual_signature := pg_temp.canonical_event_semantic_signature();
    if actual_signature is distinct from expected_post_signature then
        raise exception using errcode = '55000', message = 'signup failure catalog correction final semantic signature is incompatible', detail = format('expected signature %s, found %s', expected_post_signature, actual_signature);
    end if;
end
$migration$;

commit;
