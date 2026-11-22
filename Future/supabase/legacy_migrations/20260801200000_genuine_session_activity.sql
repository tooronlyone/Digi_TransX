-- Activate canonical evidence for bounded, trusted genuine-session activity.
-- No session, user, device, event, or migration-ledger fixture is created.

begin;

create or replace function pg_temp.canonical_event_semantic_signature()
returns text language plpgsql stable as $signature$
declare actual_signature text;
begin
    with signature_items as (
        select format('column|%s|%s|%s|%s|%s|%s|%s|%s', relation.relname, attribute.attnum, attribute.attname, pg_catalog.format_type(attribute.atttypid, attribute.atttypmod), attribute.attnotnull, coalesce(pg_get_expr(default_value.adbin, default_value.adrelid), ''), attribute.attidentity, attribute.attgenerated) as item from pg_class relation join pg_namespace namespace on namespace.oid=relation.relnamespace join pg_attribute attribute on attribute.attrelid=relation.oid left join pg_attrdef default_value on default_value.adrelid=relation.oid and default_value.adnum=attribute.attnum where namespace.nspname='public' and relation.relname in ('security_events','business_audit_events','canonical_event_catalog_projection') and attribute.attnum>0 and not attribute.attisdropped
        union all select format('constraint|%s|%s|%s|%s|%s|%s', relation.relname, constraint_value.conname, constraint_value.contype, constraint_value.condeferrable, constraint_value.condeferred, pg_get_constraintdef(constraint_value.oid,false)) from pg_constraint constraint_value join pg_class relation on relation.oid=constraint_value.conrelid join pg_namespace namespace on namespace.oid=relation.relnamespace where namespace.nspname='public' and relation.relname in ('security_events','business_audit_events','canonical_event_catalog_projection')
        union all select format('index|%s|%s|%s|%s|%s|%s', table_value.relname,index_value.relname,metadata.indisunique,metadata.indisprimary,metadata.indisvalid,pg_get_indexdef(index_value.oid)) from pg_index metadata join pg_class table_value on table_value.oid=metadata.indrelid join pg_class index_value on index_value.oid=metadata.indexrelid join pg_namespace namespace on namespace.oid=table_value.relnamespace where namespace.nspname='public' and table_value.relname in ('security_events','business_audit_events','canonical_event_catalog_projection')
        union all select format('trigger|%s|%s|%s|%s',relation.relname,trigger_value.tgname,trigger_value.tgenabled,pg_get_triggerdef(trigger_value.oid,false)) from pg_trigger trigger_value join pg_class relation on relation.oid=trigger_value.tgrelid join pg_namespace namespace on namespace.oid=relation.relnamespace where namespace.nspname='public' and relation.relname in ('security_events','business_audit_events','canonical_event_catalog_projection') and not trigger_value.tgisinternal
        union all select format('function|%s|%s|%s|%s|%s|%s|%s|%s|%s',function_value.proname,pg_get_function_identity_arguments(function_value.oid),pg_get_function_result(function_value.oid),language.lanname,function_value.provolatile,function_value.proisstrict,function_value.prosecdef,coalesce(array_to_string(function_value.proconfig,','),''),function_value.prosrc) from pg_proc function_value join pg_namespace namespace on namespace.oid=function_value.pronamespace join pg_language language on language.oid=function_value.prolang where namespace.nspname='public' and function_value.proname in ('is_bounded_event_json','prevent_canonical_event_update','enforce_canonical_event_contract')
        union all select format('rls|%s|%s|%s',relation.relname,relation.relrowsecurity,relation.relforcerowsecurity) from pg_class relation join pg_namespace namespace on namespace.oid=relation.relnamespace where namespace.nspname='public' and relation.relname in ('security_events','business_audit_events','canonical_event_catalog_projection')
        union all select format('policy|%s|%s|%s|%s|%s|%s',policy.tablename,policy.policyname,policy.permissive,array_to_string(policy.roles,','),policy.cmd,coalesce(policy.qual,'')||'|'||coalesce(policy.with_check,'')) from pg_policies policy where policy.schemaname='public' and policy.tablename in ('security_events','business_audit_events','canonical_event_catalog_projection')
        union all select format('table_privilege|%s|%s|%s|%s',relation.relname,coalesce(grantee.rolname,'PUBLIC'),privilege.privilege_type,privilege.is_grantable) from pg_class relation join pg_namespace namespace on namespace.oid=relation.relnamespace cross join lateral aclexplode(coalesce(relation.relacl,acldefault('r',relation.relowner))) privilege left join pg_roles grantee on grantee.oid=privilege.grantee where namespace.nspname='public' and relation.relname in ('security_events','business_audit_events','canonical_event_catalog_projection') and privilege.grantee<>relation.relowner
        union all select format('function_privilege|%s|%s|%s|%s',function_value.proname,coalesce(grantee.rolname,'PUBLIC'),privilege.privilege_type,privilege.is_grantable) from pg_proc function_value join pg_namespace namespace on namespace.oid=function_value.pronamespace cross join lateral aclexplode(coalesce(function_value.proacl,acldefault('f',function_value.proowner))) privilege left join pg_roles grantee on grantee.oid=privilege.grantee where namespace.nspname='public' and function_value.proname in ('is_bounded_event_json','prevent_canonical_event_update','enforce_canonical_event_contract') and privilege.grantee<>function_value.proowner
        union all select case when to_jsonb(catalog_value)?'event_contract' then format('catalog|%s|%s|%s|%s|%s|%s|%s|%s|%s',event_name,event_version,category,ownership_domain,retention_class,lifecycle_status,writable,integrated,(to_jsonb(catalog_value)->'event_contract')::text) else format('catalog|%s|%s|%s|%s|%s|%s|%s|%s',event_name,event_version,category,ownership_domain,retention_class,lifecycle_status,writable,integrated) end from public.canonical_event_catalog_projection catalog_value
    ) select md5(string_agg(item,E'\n' order by item)) into actual_signature from signature_items;
    return actual_signature;
end
$signature$;

lock table public.canonical_event_catalog_projection in access exclusive mode;
lock table public.security_events in access exclusive mode;
lock table public.business_audit_events in access exclusive mode;

do $migration$
declare
    actual_signature text := pg_temp.canonical_event_semantic_signature();
    expected_pre constant text := '8dcc0c1ecaf1df3fdad9d0be30f6be03';
    expected_post constant text := 'b57a59369062e678a7b269cd61d4e01e';
begin
    if actual_signature = expected_post then
        if (select count(*) from public.canonical_event_catalog_projection) <> 170
           or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='planned') <> 162
           or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='deferred') <> 8
           or (select count(*) from public.canonical_event_catalog_projection where writable) <> 156
           or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 21
           or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='planned' and not integrated) <> 141
           or (select count(*) from public.canonical_event_catalog_projection where writable and not integrated) <> 135
           or (select count(*) from public.canonical_event_catalog_projection where category='operations') <> 6
           or not exists(select 1 from public.canonical_event_catalog_projection where event_name='security.session.refreshed' and integrated and writable and lifecycle_status='planned')
           or exists(select 1 from public.canonical_event_catalog_projection where event_name='security.session.expired_inactivity' and integrated) then
            raise exception using errcode='55000', message='genuine-session-activity post-state is partial or incompatible';
        end if;
        return;
    end if;

    if actual_signature is distinct from expected_pre
       or (select count(*) from public.canonical_event_catalog_projection) <> 170
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 20
       or not exists(select 1 from public.canonical_event_catalog_projection where event_name='security.session.refreshed' and not integrated and writable and lifecycle_status='planned')
       or exists(select 1 from public.canonical_event_catalog_projection where event_name='security.session.expired_inactivity' and integrated) then
        raise exception using errcode='55000', message='genuine-session-activity pre-state is partial or incompatible', detail=format('expected signature %s, found %s', expected_pre, actual_signature);
    end if;

    update public.canonical_event_catalog_projection
       set integrated=true
     where event_name='security.session.refreshed'
       and not integrated and writable and lifecycle_status='planned';
    if not found then
        raise exception using errcode='55000', message='genuine-session-activity activation lost its exact target';
    end if;

    if pg_temp.canonical_event_semantic_signature() is distinct from expected_post then
        raise exception using errcode='55000', message='genuine-session-activity final signature is incompatible';
    end if;
end
$migration$;

commit;
