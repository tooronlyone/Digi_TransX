-- Phase 1B-2C0: project the authoritative catalog's device/session/MPIN contracts.
-- No runtime emitter, event-row backfill, business DML, or integration activation.

begin;

create or replace function pg_temp.canonical_event_semantic_signature()
returns text
language plpgsql
stable
as $signature$
declare actual_signature text;
begin
    with signature_items as (
        select format('column|%s|%s|%s|%s|%s|%s|%s|%s', relation.relname, attribute.attnum, attribute.attname, pg_catalog.format_type(attribute.atttypid, attribute.atttypmod), attribute.attnotnull, coalesce(pg_get_expr(default_value.adbin, default_value.adrelid), ''), attribute.attidentity, attribute.attgenerated) as item
        from pg_class as relation join pg_namespace as namespace on namespace.oid = relation.relnamespace join pg_attribute as attribute on attribute.attrelid = relation.oid left join pg_attrdef as default_value on default_value.adrelid = relation.oid and default_value.adnum = attribute.attnum
        where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection') and attribute.attnum > 0 and not attribute.attisdropped
        union all select format('constraint|%s|%s|%s|%s|%s|%s', relation.relname, constraint_value.conname, constraint_value.contype, constraint_value.condeferrable, constraint_value.condeferred, pg_get_constraintdef(constraint_value.oid, false)) from pg_constraint as constraint_value join pg_class as relation on relation.oid = constraint_value.conrelid join pg_namespace as namespace on namespace.oid = relation.relnamespace where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection')
        union all select format('index|%s|%s|%s|%s|%s|%s', table_value.relname, index_value.relname, metadata.indisunique, metadata.indisprimary, metadata.indisvalid, pg_get_indexdef(index_value.oid)) from pg_index as metadata join pg_class as table_value on table_value.oid = metadata.indrelid join pg_class as index_value on index_value.oid = metadata.indexrelid join pg_namespace as namespace on namespace.oid = table_value.relnamespace where namespace.nspname = 'public' and table_value.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection')
        union all select format('trigger|%s|%s|%s|%s', relation.relname, trigger_value.tgname, trigger_value.tgenabled, pg_get_triggerdef(trigger_value.oid, false)) from pg_trigger as trigger_value join pg_class as relation on relation.oid = trigger_value.tgrelid join pg_namespace as namespace on namespace.oid = relation.relnamespace where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection') and not trigger_value.tgisinternal
        union all select format('function|%s|%s|%s|%s|%s|%s|%s|%s|%s', function_value.proname, pg_get_function_identity_arguments(function_value.oid), pg_get_function_result(function_value.oid), language.lanname, function_value.provolatile, function_value.proisstrict, function_value.prosecdef, coalesce(array_to_string(function_value.proconfig, ','), ''), function_value.prosrc) from pg_proc as function_value join pg_namespace as namespace on namespace.oid = function_value.pronamespace join pg_language as language on language.oid = function_value.prolang where namespace.nspname = 'public' and function_value.proname in ('is_bounded_event_json', 'prevent_canonical_event_update', 'enforce_canonical_event_contract')
        union all select format('rls|%s|%s|%s', relation.relname, relation.relrowsecurity, relation.relforcerowsecurity) from pg_class as relation join pg_namespace as namespace on namespace.oid = relation.relnamespace where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection')
        union all select format('policy|%s|%s|%s|%s|%s|%s', policy.tablename, policy.policyname, policy.permissive, array_to_string(policy.roles, ','), policy.cmd, coalesce(policy.qual, '') || '|' || coalesce(policy.with_check, '')) from pg_policies as policy where policy.schemaname = 'public' and policy.tablename in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection')
        union all select format('table_privilege|%s|%s|%s|%s', relation.relname, coalesce(grantee.rolname, 'PUBLIC'), privilege.privilege_type, privilege.is_grantable) from pg_class as relation join pg_namespace as namespace on namespace.oid = relation.relnamespace cross join lateral aclexplode(coalesce(relation.relacl, acldefault('r', relation.relowner))) as privilege left join pg_roles as grantee on grantee.oid = privilege.grantee where namespace.nspname = 'public' and relation.relname in ('security_events', 'business_audit_events', 'canonical_event_catalog_projection') and privilege.grantee <> relation.relowner
        union all select format('function_privilege|%s|%s|%s|%s', function_value.proname, coalesce(grantee.rolname, 'PUBLIC'), privilege.privilege_type, privilege.is_grantable) from pg_proc as function_value join pg_namespace as namespace on namespace.oid = function_value.pronamespace cross join lateral aclexplode(coalesce(function_value.proacl, acldefault('f', function_value.proowner))) as privilege left join pg_roles as grantee on grantee.oid = privilege.grantee where namespace.nspname = 'public' and function_value.proname in ('is_bounded_event_json', 'prevent_canonical_event_update', 'enforce_canonical_event_contract') and privilege.grantee <> function_value.proowner
        union all select case when to_jsonb(catalog_value) ? 'event_contract' then format('catalog|%s|%s|%s|%s|%s|%s|%s|%s|%s', event_name, event_version, category, ownership_domain, retention_class, lifecycle_status, writable, integrated, (to_jsonb(catalog_value) -> 'event_contract')::text) else format('catalog|%s|%s|%s|%s|%s|%s|%s|%s', event_name, event_version, category, ownership_domain, retention_class, lifecycle_status, writable, integrated) end from public.canonical_event_catalog_projection as catalog_value
    ) select md5(string_agg(item, E'\n' order by item)) into actual_signature from signature_items;
    return actual_signature;
end
$signature$;

do $migration$
declare
    actual_signature text;
    expected_pre_signature constant text := '371c7010a0553c7953708dea164ed0bc';
    expected_post_signature constant text := '3d9b730408336c82629c25342ddc7ea2';
    expected_integrated constant text[] := array['security.login.failed', 'security.login.started', 'security.login.succeeded', 'security.logout.completed', 'security.signup.completed', 'security.signup.failed', 'security.signup.started'];
begin
    lock table public.canonical_event_catalog_projection in access exclusive mode;
    lock table public.security_events in access exclusive mode;
    lock table public.business_audit_events in access exclusive mode;
    actual_signature := pg_temp.canonical_event_semantic_signature();

    if actual_signature = expected_post_signature then
        if (select count(*) from public.canonical_event_catalog_projection) <> 170
           or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'planned') <> 162
           or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'deferred') <> 8
           or (select count(*) from public.canonical_event_catalog_projection where writable) <> 156
           or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 7
           or (select array_agg(event_name order by event_name) from public.canonical_event_catalog_projection where integrated) is distinct from expected_integrated then
            raise exception using errcode = '55000', message = 'device/session/MPIN contract post-state is incompatible';
        end if;
        return;
    end if;

    if actual_signature is distinct from expected_pre_signature
       or (select count(*) from public.canonical_event_catalog_projection) <> 158
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'planned') <> 150
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'deferred') <> 8
       or (select count(*) from public.canonical_event_catalog_projection where writable) <> 144
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 7
       or (select array_agg(event_name order by event_name) from public.canonical_event_catalog_projection where integrated) is distinct from expected_integrated then
        raise exception using errcode = '55000', message = 'device/session/MPIN contract pre-state is partial or incompatible', detail = format('expected signature %s, found %s', expected_pre_signature, actual_signature);
    end if;

    alter table public.canonical_event_catalog_projection
        add column event_contract jsonb not null default '{"actor_policy":"generic","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb,
        add constraint canonical_event_catalog_projection_contract_check check (
            jsonb_typeof(event_contract) = 'object'
            and event_contract ? 'actor_policy'
            and event_contract ? 'allowed_metadata_keys'
            and event_contract ? 'allowed_result_codes'
            and event_contract ->> 'actor_policy' in ('generic', 'authenticated_self', 'service_subject', 'authenticated_self_or_service')
            and jsonb_typeof(event_contract -> 'allowed_metadata_keys') = 'array'
            and jsonb_typeof(event_contract -> 'allowed_result_codes') = 'array'
        );

    update public.canonical_event_catalog_projection set event_contract = case event_name
        when 'security.signup.failed' then '{"actor_policy":"generic","allowed_metadata_keys":["result_code"],"allowed_result_codes":["account_conflict","persistence_failed","provider_unavailable","reconciliation_required","validation_failed"]}'::jsonb
        when 'security.session.refreshed' then '{"actor_policy":"authenticated_self","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb
        when 'security.session.expired_inactivity' then '{"actor_policy":"service_subject","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb
        when 'security.session.revoked' then '{"actor_policy":"authenticated_self_or_service","allowed_metadata_keys":["result_code"],"allowed_result_codes":["absolute_expiry","account_blocked","device_removed","logout","logout_all","password_changed","password_reset","security_action"]}'::jsonb
        when 'security.trusted_device.added' then '{"actor_policy":"authenticated_self","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb
        when 'security.trusted_device.removed' then '{"actor_policy":"authenticated_self_or_service","allowed_metadata_keys":["result_code"],"allowed_result_codes":["account_blocked","attempt_limit","inactivity_expired","logout_all","password_changed","password_reset","security_action","user_removed"]}'::jsonb
        else '{"actor_policy":"generic","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb end;

    insert into public.canonical_event_catalog_projection (event_name,event_version,category,ownership_domain,retention_class,lifecycle_status,writable,integrated,event_contract) values
        ('security.session.issued',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb),
        ('security.session.access_locked',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"service_subject","allowed_metadata_keys":["result_code"],"allowed_result_codes":["app_launch","idle_lock","security_action"]}'::jsonb),
        ('security.trusted_device.rotated',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self_or_service","allowed_metadata_keys":["result_code"],"allowed_result_codes":["full_login","scheduled_rotation","security_action"]}'::jsonb),
        ('security.mpin.enrolled',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb),
        ('security.mpin.changed',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb),
        ('security.mpin.disabled',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb),
        ('security.mpin.unlock_succeeded',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb),
        ('security.mpin.unlock_failed',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"service_subject","allowed_metadata_keys":["result_code"],"allowed_result_codes":["invalid_mpin","rate_limited"]}'::jsonb),
        ('security.mpin.locked',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"service_subject","allowed_metadata_keys":["result_code"],"allowed_result_codes":["attempt_limit","security_action"]}'::jsonb),
        ('security.mpin.reset_completed',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self","allowed_metadata_keys":["result_code"],"allowed_result_codes":["security_recovery","user_reauthentication"]}'::jsonb),
        ('security.mpin.step_up_succeeded',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self","allowed_metadata_keys":[],"allowed_result_codes":[]}'::jsonb),
        ('security.mpin.step_up_failed',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"service_subject","allowed_metadata_keys":["result_code"],"allowed_result_codes":["challenge_expired","challenge_mismatch","invalid_mpin","rate_limited"]}'::jsonb);

    create or replace function public.enforce_canonical_event_contract()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $guard$
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

    select event_version, category, retention_class, writable, integrated,
           lifecycle_status, event_contract
      into definition
      from public.canonical_event_catalog_projection
     where event_name = new.event_name;

    if not found
       or not definition.writable
       or not definition.integrated
       or definition.lifecycle_status <> 'planned'
       or definition.event_version <> new.event_version
       or definition.category <> new.category
       or definition.category <> expected_category
       or definition.retention_class <> new.retention_class then
        raise exception using
            errcode = '23514',
            message = 'event does not match an integrated writable canonical catalog definition';
    end if;

    if new.actor_type in ('user', 'admin')
       and (new.actor_id is null or new.actor_role is null) then
        raise exception using
            errcode = '23514',
            message = 'user and admin canonical events require actor_id and actor_role';
    end if;

    if definition.event_contract ->> 'actor_policy' = 'authenticated_self'
       and not (
           new.actor_type in ('user', 'admin')
           and new.actor_id is not null
           and new.actor_id = new.subject_user_id
       ) then
        raise exception using errcode = '23514',
            message = 'event requires an authenticated actor and matching subject';
    elsif definition.event_contract ->> 'actor_policy' = 'service_subject'
       and not (
           new.actor_type = 'system'
           and new.actor_id is null
           and new.actor_role is null
           and new.subject_user_id is not null
       ) then
        raise exception using errcode = '23514',
            message = 'event requires the service actor and a derived subject';
    elsif definition.event_contract ->> 'actor_policy' = 'authenticated_self_or_service'
       and not (
           (new.actor_type in ('user', 'admin') and new.actor_id = new.subject_user_id)
           or (new.actor_type = 'system' and new.actor_id is null
               and new.actor_role is null and new.subject_user_id is not null)
       ) then
        raise exception using errcode = '23514',
            message = 'event requires an authenticated self actor or service subject';
    end if;

    if definition.event_contract ->> 'actor_policy' <> 'generic' then
        if (select count(*) from jsonb_object_keys(new.metadata)) <> jsonb_array_length(
               definition.event_contract -> 'allowed_metadata_keys'
           )
           or exists (
               select 1 from jsonb_object_keys(new.metadata) as key_value
                where not key_value = any (
                    array(select jsonb_array_elements_text(
                        definition.event_contract -> 'allowed_metadata_keys'
                    ))
                )
           )
           or (
               definition.event_contract -> 'allowed_result_codes' <> '[]'::jsonb
               and new.metadata ->> 'result_code' not in (
                   select jsonb_array_elements_text(
                       definition.event_contract -> 'allowed_result_codes'
                   )
               )
           ) then
            raise exception using errcode = '23514',
                message = 'event metadata does not match its canonical contract';
        end if;
    end if;

    return new;
end
$guard$;

    if (select count(*) from public.canonical_event_catalog_projection) <> 170
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'planned') <> 162
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'deferred') <> 8
       or (select count(*) from public.canonical_event_catalog_projection where writable) <> 156
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 7
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status = 'planned' and not integrated) <> 155
       or (select count(*) from public.canonical_event_catalog_projection where writable and not integrated) <> 149
       or (select count(*) from public.canonical_event_catalog_projection where category = 'operations') <> 6
       or (select array_agg(event_name order by event_name) from public.canonical_event_catalog_projection where integrated) is distinct from expected_integrated then
        raise exception using errcode = '55000', message = 'device/session/MPIN contract final catalog counts are incompatible';
    end if;
    actual_signature := pg_temp.canonical_event_semantic_signature();
    if actual_signature is distinct from expected_post_signature then
        raise exception using errcode = '55000', message = 'device/session/MPIN contract final semantic signature is incompatible', detail = format('expected signature %s, found %s', expected_post_signature, actual_signature);
    end if;
end
$migration$;

commit;
