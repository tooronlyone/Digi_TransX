-- Bounded MPIN step-up authorization foundation for six approved Category A targets.
-- This migration creates no user, credential, authorization, session, or event fixture.

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

create or replace function pg_temp.mpin_step_up_foundation_signature()
returns text language plpgsql stable as $foundation$
declare actual_signature text;
begin
    with signature_items as (
        select format('column|%s|%s|%s|%s|%s|%s',relation.relname,attribute.attnum,attribute.attname,pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),attribute.attnotnull,coalesce(pg_get_expr(default_value.adbin,default_value.adrelid),'')) item
          from pg_class relation join pg_namespace namespace on namespace.oid=relation.relnamespace join pg_attribute attribute on attribute.attrelid=relation.oid left join pg_attrdef default_value on default_value.adrelid=relation.oid and default_value.adnum=attribute.attnum
         where namespace.nspname='public' and relation.relname in ('user_sessions','mpin_credentials','mpin_step_up_authorizations','mpin_credential_generation_seq') and attribute.attnum>0 and not attribute.attisdropped
        union all select format('constraint|%s|%s|%s|%s',relation.relname,constraint_value.conname,constraint_value.contype,pg_get_constraintdef(constraint_value.oid,false)) from pg_constraint constraint_value join pg_class relation on relation.oid=constraint_value.conrelid join pg_namespace namespace on namespace.oid=relation.relnamespace where namespace.nspname='public' and relation.relname in ('user_sessions','mpin_credentials','mpin_step_up_authorizations')
        union all select format('index|%s|%s|%s|%s',table_value.relname,index_value.relname,metadata.indisunique,pg_get_indexdef(index_value.oid)) from pg_index metadata join pg_class table_value on table_value.oid=metadata.indrelid join pg_class index_value on index_value.oid=metadata.indexrelid join pg_namespace namespace on namespace.oid=table_value.relnamespace where namespace.nspname='public' and table_value.relname in ('user_sessions','mpin_credentials','mpin_step_up_authorizations')
        union all select format('rls|%s|%s|%s',relation.relname,relation.relrowsecurity,relation.relforcerowsecurity) from pg_class relation join pg_namespace namespace on namespace.oid=relation.relnamespace where namespace.nspname='public' and relation.relname in ('mpin_credentials','mpin_step_up_authorizations')
        union all select format('policy|%s|%s|%s|%s|%s|%s',policy.tablename,policy.policyname,policy.permissive,array_to_string(policy.roles,','),policy.cmd,coalesce(policy.qual,'')||'|'||coalesce(policy.with_check,'')) from pg_policies policy where policy.schemaname='public' and policy.tablename in ('mpin_credentials','mpin_step_up_authorizations')
        union all select format('privilege|%s|%s|%s|%s',relation.relname,coalesce(grantee.rolname,'PUBLIC'),privilege.privilege_type,privilege.is_grantable) from pg_class relation join pg_namespace namespace on namespace.oid=relation.relnamespace cross join lateral aclexplode(coalesce(relation.relacl,acldefault(case when relation.relkind='S' then 'S'::"char" else 'r'::"char" end,relation.relowner))) privilege left join pg_roles grantee on grantee.oid=privilege.grantee where namespace.nspname='public' and relation.relname in ('mpin_credentials','mpin_step_up_authorizations','mpin_credential_generation_seq') and privilege.grantee<>relation.relowner
    ) select md5(string_agg(item,E'\n' order by item)) into actual_signature from signature_items;
    return actual_signature;
end
$foundation$;

lock table public.canonical_event_catalog_projection in access exclusive mode;
lock table public.security_events in access exclusive mode;
lock table public.business_audit_events in access exclusive mode;
lock table public.user_sessions in share row exclusive mode;
lock table public.mpin_credentials in access exclusive mode;

do $guard$
declare
    actual_signature text := pg_temp.canonical_event_semantic_signature();
begin
    if actual_signature = '82bd918f68377090324c3a15da210769'
       and pg_temp.mpin_step_up_foundation_signature() in (
           '292d52b1f2d0e083555b161bba6a7ad3',
           'c0512954e08a1395c4fb0baf30b6cdc9'
       ) then
        return;
    end if;
    if actual_signature <> 'b57a59369062e678a7b269cd61d4e01e'
       or (select count(*) from public.canonical_event_catalog_projection) <> 170
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 21
       or to_regclass('public.mpin_step_up_authorizations') is not null
       or to_regclass('public.mpin_credential_generation_seq') is not null
       or exists(select 1 from information_schema.columns where table_schema='public'
                 and table_name='mpin_credentials' and column_name='credential_generation') then
        raise exception using errcode='55000', message='MPIN step-up foundation pre-state is partial or incompatible';
    end if;
end
$guard$;

create sequence if not exists public.mpin_credential_generation_seq;
alter table public.mpin_credentials
    add column if not exists credential_generation bigint not null
        default nextval('public.mpin_credential_generation_seq');
do $constraints$
begin
    if not exists(select 1 from pg_constraint where conrelid='public.mpin_credentials'::regclass and conname='mpin_credentials_generation_unique') then
        alter table public.mpin_credentials add constraint mpin_credentials_generation_unique unique(user_id,credential_generation);
    end if;
    if not exists(select 1 from pg_constraint where conrelid='public.mpin_credentials'::regclass and conname='mpin_credentials_generation_positive') then
        alter table public.mpin_credentials add constraint mpin_credentials_generation_positive check(credential_generation>0);
    end if;
    if not exists(select 1 from pg_constraint where conrelid='public.user_sessions'::regclass and conname='user_sessions_step_up_binding_unique') then
        alter table public.user_sessions add constraint user_sessions_step_up_binding_unique unique(session_id,user_id,trusted_device_id);
    end if;
end
$constraints$;

create table if not exists public.mpin_step_up_authorizations (
    authorization_id uuid primary key default gen_random_uuid(),
    user_id bigint not null references public.users (id),
    session_id uuid not null,
    trusted_device_id bigint not null,
    credential_generation bigint not null,
    proof_digest bytea not null,
    action_key text not null,
    resource_type text not null,
    resource_id bigint not null,
    amount_minor bigint,
    currency text,
    destination_digest bytea,
    request_fingerprint bytea not null,
    state text not null default 'available',
    claim_digest bytea,
    issued_at timestamptz not null default now(),
    claimed_at timestamptz,
    consumed_at timestamptz,
    expired_at timestamptz,
    reconciliation_required_at timestamptz,
    invalidated_at timestamptz,
    expires_at timestamptz not null default (now() + interval '3 minutes'),
    constraint mpin_step_up_session_binding_fk foreign key (session_id,user_id,trusted_device_id)
        references public.user_sessions (session_id,user_id,trusted_device_id),
    constraint mpin_step_up_device_binding_fk foreign key (trusted_device_id,user_id)
        references public.trusted_devices (id,user_id),
    constraint mpin_step_up_proof_unique unique (proof_digest),
    constraint mpin_step_up_claim_unique unique (claim_digest),
    constraint mpin_step_up_proof_shape check (octet_length(proof_digest)=32),
    constraint mpin_step_up_claim_shape check (claim_digest is null or octet_length(claim_digest)=32),
    constraint mpin_step_up_destination_shape check (destination_digest is null or octet_length(destination_digest)=32),
    constraint mpin_step_up_request_shape check (octet_length(request_fingerprint)=32),
    constraint mpin_step_up_descriptor_shape check (
        credential_generation>0 and resource_id>0
        and action_key ~ '^[a-z][a-z0-9_.]{1,95}$'
        and resource_type ~ '^[a-z][a-z0-9_]{0,47}$'
        and (amount_minor is null or amount_minor>0)
        and ((amount_minor is null and currency is null)
          or (amount_minor is not null and currency ~ '^[A-Z]{3}$'))),
    constraint mpin_step_up_exact_lifetime check (expires_at=issued_at+interval '3 minutes'),
    constraint mpin_step_up_state_shape check (
        (state='available' and claim_digest is null and claimed_at is null and consumed_at is null and expired_at is null and reconciliation_required_at is null and invalidated_at is null)
        or (state='claimed' and claim_digest is not null and claimed_at is not null and consumed_at is null and expired_at is null and reconciliation_required_at is null and invalidated_at is null)
        or (state='consumed' and consumed_at is not null and expired_at is null and reconciliation_required_at is null and invalidated_at is null and ((claim_digest is null and claimed_at is null) or (claim_digest is not null and claimed_at is not null)))
        or (state='expired' and expired_at is not null and consumed_at is null and reconciliation_required_at is null and invalidated_at is null and ((claim_digest is null and claimed_at is null) or (claim_digest is not null and claimed_at is not null)))
        or (state='reconciliation_required' and claim_digest is not null and claimed_at is not null and reconciliation_required_at is not null and consumed_at is null and expired_at is null and invalidated_at is null)
        or (state='invalidated' and invalidated_at is not null and consumed_at is null and expired_at is null and reconciliation_required_at is null)),
    constraint mpin_step_up_timestamp_order check (
        expires_at>issued_at and (claimed_at is null or claimed_at>=issued_at)
        and (consumed_at is null or consumed_at>=issued_at)
        and (expired_at is null or expired_at>=issued_at)
        and (reconciliation_required_at is null or reconciliation_required_at>=issued_at)
        and (invalidated_at is null or invalidated_at>=issued_at))
);
create unique index if not exists mpin_step_up_one_available_descriptor
    on public.mpin_step_up_authorizations
       (user_id,session_id,action_key,resource_type,resource_id,request_fingerprint)
    where state='available';
create index if not exists mpin_step_up_expiry_state_idx
    on public.mpin_step_up_authorizations(state,expires_at);
create index if not exists mpin_step_up_user_session_idx
    on public.mpin_step_up_authorizations(user_id,session_id,issued_at desc);

alter table public.mpin_step_up_authorizations enable row level security;
drop policy if exists mpin_step_up_authorizations_service_role_all
    on public.mpin_step_up_authorizations;
create policy mpin_step_up_authorizations_service_role_all
    on public.mpin_step_up_authorizations for all to service_role
    using (true) with check (true);
revoke all privileges on table public.mpin_step_up_authorizations
    from public, anon, authenticated, service_role;
grant select,insert,update on table public.mpin_step_up_authorizations to service_role;
revoke all privileges on sequence public.mpin_credential_generation_seq
    from public, anon, authenticated, service_role;
grant usage,select on sequence public.mpin_credential_generation_seq to service_role;

update public.canonical_event_catalog_projection
   set integrated=true,
       event_contract='{"actor_policy":"authenticated_self","allowed_metadata_keys":["action_key","authorization_ref","request_fingerprint_ref","resource_id","resource_type"],"allowed_result_codes":[]}'::jsonb
 where event_name='security.mpin.step_up_succeeded' and not integrated;

update public.canonical_event_catalog_projection
   set integrated=true,
       event_contract='{"actor_policy":"service_subject","allowed_metadata_keys":["action_key","request_fingerprint_ref","resource_id","resource_type","result_code"],"allowed_result_codes":["invalid_mpin","rate_limited"]}'::jsonb
 where event_name='security.mpin.step_up_failed' and not integrated;

insert into public.canonical_event_catalog_projection
    (event_name,event_version,category,ownership_domain,retention_class,
     lifecycle_status,writable,integrated,event_contract)
values
    ('security.mpin.step_up_consumed',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"authenticated_self","allowed_metadata_keys":["action_key","authorization_ref","request_fingerprint_ref","resource_id","resource_type"],"allowed_result_codes":[]}'::jsonb),
    ('security.mpin.step_up_reconciliation_required',1,'security','security','security_12_months','planned',true,false,'{"actor_policy":"service_subject","allowed_metadata_keys":["action_key","authorization_ref","request_fingerprint_ref","resource_id","resource_type","result_code"],"allowed_result_codes":["domain_outcome_uncertain"]}'::jsonb)
on conflict (event_name) do update set
    event_version=excluded.event_version,category=excluded.category,
    ownership_domain=excluded.ownership_domain,retention_class=excluded.retention_class,
    lifecycle_status=excluded.lifecycle_status,writable=excluded.writable,
    integrated=excluded.integrated,event_contract=excluded.event_contract;

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
            'provider_event_type', 'authorization_ref', 'action_key',
            'resource_type', 'request_fingerprint_ref'
        ];
        integer_keys := array[
            'policy_version', 'attempt_number', 'item_count', 'amount_minor',
            'resource_id'
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
               or item.member #>> '{}' !~ '^[a-z][a-z0-9_.:-]{0,127}$'
               or (item.key = 'authorization_ref'
                   and item.member #>> '{}' !~ '^authorization_[0-9a-f]{32}$')
               or (item.key = 'request_fingerprint_ref'
                   and item.member #>> '{}' !~ '^request_[0-9a-f]{64}$') then
                return false;
            end if;
        elsif item.key = any(integer_keys) then
            if item_type <> 'number'
               or item.member::text !~ '^(0|[1-9][0-9]*)$'
               or (item.key = 'resource_id' and item.member::text = '0') then
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

do $post$
declare actual_signature text := pg_temp.canonical_event_semantic_signature();
begin
    if actual_signature <> '82bd918f68377090324c3a15da210769'
       or (select count(*) from public.canonical_event_catalog_projection) <> 172
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='planned') <> 164
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='deferred') <> 8
       or (select count(*) from public.canonical_event_catalog_projection where writable) <> 158
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 23
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='planned' and not integrated) <> 141
       or (select count(*) from public.canonical_event_catalog_projection where writable and not integrated) <> 135
       or (select count(*) from public.canonical_event_catalog_projection where category='operations') <> 6
       or pg_temp.mpin_step_up_foundation_signature() not in (
           '292d52b1f2d0e083555b161bba6a7ad3',
           'c0512954e08a1395c4fb0baf30b6cdc9'
       ) then
        raise exception using errcode='55000', message='MPIN step-up foundation final state is incompatible', detail=format('event signature %s, foundation signature %s',actual_signature,pg_temp.mpin_step_up_foundation_signature());
    end if;
end
$post$;

commit;
