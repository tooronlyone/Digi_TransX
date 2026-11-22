-- Phase 1B-2C3B1: secure MPIN credentials and session-bound software access proof.
-- Legacy user MPIN verifiers are invalidated; no credential, session, or event
-- fixture is created.

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

create or replace function pg_temp.secure_mpin_exact_state()
returns boolean language sql stable as $exact$
select
    to_regclass('public.mpin_credentials') is not null
    and (select array_agg(a.attname||':'||format_type(a.atttypid,a.atttypmod)||':'||a.attnotnull order by a.attnum)
           from pg_attribute a where a.attrelid=to_regclass('public.mpin_credentials')
             and a.attnum>0 and not a.attisdropped) = array[
        'user_id:bigint:true','verifier:bytea:true','salt:bytea:true',
        'kdf_version:smallint:true','failed_attempts:smallint:true',
        'permanently_locked:boolean:true','locked_at:timestamp with time zone:false',
        'created_at:timestamp with time zone:true','updated_at:timestamp with time zone:true']
    and (select array_agg(c.conname order by c.conname) from pg_constraint c
          where c.conrelid=to_regclass('public.mpin_credentials')) = array[
        'mpin_credentials_attempts','mpin_credentials_kdf_version',
        'mpin_credentials_lock_state','mpin_credentials_pkey',
        'mpin_credentials_salt_shape','mpin_credentials_salt_unique',
        'mpin_credentials_timestamp_order','mpin_credentials_user_id_fkey',
        'mpin_credentials_verifier_shape']::name[]
    and (select count(*) from pg_constraint c where c.conrelid='public.user_sessions'::regclass) = 13
    and (select count(*) from pg_constraint c where c.conrelid='public.user_sessions'::regclass
          and c.conname in ('user_sessions_access_proof_digest_unique',
             'user_sessions_access_proof_shape','user_sessions_access_proof_state',
             'user_sessions_access_lock_state','user_sessions_password_verification_state')) = 5
    and (select count(*) from pg_attribute a where a.attrelid='public.user_sessions'::regclass
          and a.attnum>0 and not a.attisdropped) = 19
    and exists(select 1 from pg_attribute a where a.attrelid='public.user_sessions'::regclass
          and a.attname='access_proof_digest' and format_type(a.atttypid,a.atttypmod)='bytea' and not a.attnotnull)
    and exists(select 1 from pg_attribute a where a.attrelid='public.user_sessions'::regclass
          and a.attname='access_proof_expires_at' and format_type(a.atttypid,a.atttypmod)='timestamp with time zone' and not a.attnotnull)
    and exists(select 1 from pg_attribute a where a.attrelid='public.user_sessions'::regclass
          and a.attname='password_verified_at' and format_type(a.atttypid,a.atttypmod)='timestamp with time zone' and not a.attnotnull)
    and exists(select 1 from pg_constraint c where c.conrelid='public.user_sessions'::regclass
          and c.conname='user_sessions_access_proof_shape' and pg_get_constraintdef(c.oid) like '%octet_length(access_proof_digest) = 32%')
    and exists(select 1 from pg_constraint c where c.conrelid='public.user_sessions'::regclass
          and c.conname='user_sessions_access_lock_state' and pg_get_constraintdef(c.oid) like '%access_proof_digest IS NULL%')
    and (select relrowsecurity and not relforcerowsecurity from pg_class where oid=to_regclass('public.mpin_credentials'))
    and (select count(*) from pg_policies where schemaname='public' and tablename='mpin_credentials'
          and policyname='mpin_credentials_service_role_all' and roles='{service_role}' and cmd='ALL') = 1
    and not exists(select 1 from information_schema.role_table_grants where table_schema='public'
          and table_name='mpin_credentials' and grantee in ('PUBLIC','anon','authenticated'))
    and (select array_agg(privilege_type::text order by privilege_type) from information_schema.role_table_grants
          where table_schema='public' and table_name='mpin_credentials' and grantee='service_role')
        = array['DELETE','INSERT','SELECT','UPDATE']::text[]
    and not exists(select 1 from information_schema.views where table_schema='public'
          and view_definition ilike '%mpin_credentials%');
$exact$;

lock table public.users in share row exclusive mode;
lock table public.user_sessions in access exclusive mode;
lock table public.canonical_event_catalog_projection in access exclusive mode;
lock table public.security_events in access exclusive mode;
lock table public.business_audit_events in access exclusive mode;

do $gate$
declare
    signature text := pg_temp.canonical_event_semantic_signature();
    expected_pre constant text := '87c1377e1404933c69b1a90ac9962937';
    expected_post constant text := '8dcc0c1ecaf1df3fdad9d0be30f6be03';
    proof_columns integer;
begin
    select count(*) into proof_columns
      from information_schema.columns
     where table_schema='public' and table_name='user_sessions'
       and column_name in ('access_proof_digest','access_proof_expires_at','password_verified_at');

    if signature = expected_post
       and to_regclass('public.mpin_credentials') is not null
       and proof_columns = 3 then
        if exists(select 1 from public.users where mpin_hash is not null or mpin_enabled)
           or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 20
           or not pg_temp.secure_mpin_exact_state() then
            raise exception using errcode='55000', message='secure MPIN post-state is partial or incompatible';
        end if;
        return;
    end if;

    if signature is distinct from expected_pre
       or to_regclass('public.mpin_credentials') is not null
       or proof_columns <> 0
       or (select count(*) from pg_attribute where attrelid='public.user_sessions'::regclass and attnum>0 and not attisdropped) <> 16
       or (select count(*) from public.canonical_event_catalog_projection) <> 170
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 12
       or (select count(*) from public.canonical_event_catalog_projection
            where event_name in (
              'security.session.access_locked','security.mpin.enrolled','security.mpin.changed',
              'security.mpin.disabled','security.mpin.unlock_succeeded','security.mpin.unlock_failed',
              'security.mpin.locked','security.mpin.reset_completed'
            ) and not integrated and writable and lifecycle_status='planned') <> 8 then
        raise exception using errcode='55000', message='secure MPIN pre-state is partial or incompatible';
    end if;
end
$gate$;

do $migrate$
begin
    if to_regclass('public.mpin_credentials') is null then
        alter table public.user_sessions
            drop constraint user_sessions_access_lock_state,
            add column access_proof_digest bytea,
            add column access_proof_expires_at timestamptz,
            add column password_verified_at timestamptz,
            add constraint user_sessions_access_proof_digest_unique unique(access_proof_digest),
            add constraint user_sessions_access_proof_shape check(
                access_proof_digest is null or octet_length(access_proof_digest)=32),
            add constraint user_sessions_access_proof_state check(
                (access_proof_digest is null) = (access_proof_expires_at is null)
                and (not access_locked or access_proof_digest is null)
                and (access_proof_expires_at is null
                     or (access_proof_expires_at > authenticated_at
                         and access_proof_expires_at <= absolute_expires_at))),
            add constraint user_sessions_access_lock_state check(
                (access_locked and access_locked_at is not null
                    and access_proof_digest is null and access_proof_expires_at is null)
                or (not access_locked and access_locked_at is null)),
            add constraint user_sessions_password_verification_state check(
                password_verified_at is null
                or (password_verified_at >= authenticated_at
                    and password_verified_at <= updated_at));

        create table public.mpin_credentials (
            user_id bigint primary key references public.users(id),
            verifier bytea not null,
            salt bytea not null,
            kdf_version smallint not null,
            failed_attempts smallint not null default 0,
            permanently_locked boolean not null default false,
            locked_at timestamptz,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            constraint mpin_credentials_salt_unique unique(salt),
            constraint mpin_credentials_verifier_shape check(octet_length(verifier)=32),
            constraint mpin_credentials_salt_shape check(octet_length(salt)=32),
            constraint mpin_credentials_kdf_version check(kdf_version=1),
            constraint mpin_credentials_attempts check(failed_attempts between 0 and 5),
            constraint mpin_credentials_lock_state check(
                (permanently_locked and failed_attempts=5 and locked_at is not null)
                or (not permanently_locked and failed_attempts between 0 and 4 and locked_at is null)),
            constraint mpin_credentials_timestamp_order check(
                created_at <= updated_at and (locked_at is null or locked_at >= created_at))
        );

        alter table public.mpin_credentials enable row level security;
        create policy mpin_credentials_service_role_all on public.mpin_credentials
            for all to service_role using (true) with check (true);
        revoke all privileges on table public.mpin_credentials from public, anon, authenticated, service_role;
        grant select, insert, update, delete on table public.mpin_credentials to service_role;

        update public.users
           set mpin_hash=null, mpin_enabled=false
         where mpin_hash is not null or mpin_enabled;

        update public.canonical_event_catalog_projection
           set integrated=true
         where event_name in (
            'security.session.access_locked','security.mpin.enrolled','security.mpin.changed',
            'security.mpin.disabled','security.mpin.unlock_succeeded','security.mpin.unlock_failed',
            'security.mpin.locked','security.mpin.reset_completed'
         ) and writable and lifecycle_status='planned';
    end if;
end
$migrate$;

do $verify$
declare
    expected_integrated constant text[] := array[
        'security.login.failed','security.login.started','security.login.succeeded',
        'security.logout.completed','security.mpin.changed','security.mpin.disabled',
        'security.mpin.enrolled','security.mpin.locked','security.mpin.reset_completed',
        'security.mpin.unlock_failed','security.mpin.unlock_succeeded',
        'security.session.access_locked','security.session.issued','security.session.revoked',
        'security.signup.completed','security.signup.failed','security.signup.started',
        'security.trusted_device.added','security.trusted_device.removed','security.trusted_device.rotated'
    ];
begin
    if pg_temp.canonical_event_semantic_signature() is distinct from '8dcc0c1ecaf1df3fdad9d0be30f6be03'
       or (select count(*) from public.canonical_event_catalog_projection) <> 170
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='planned') <> 162
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='deferred') <> 8
       or (select count(*) from public.canonical_event_catalog_projection where writable) <> 156
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 20
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='planned' and not integrated) <> 142
       or (select count(*) from public.canonical_event_catalog_projection where writable and not integrated) <> 136
       or (select count(*) from public.canonical_event_catalog_projection where category='operations') <> 6
       or (select array_agg(event_name order by event_name) from public.canonical_event_catalog_projection where integrated) is distinct from expected_integrated
       or exists(select 1 from public.users where mpin_hash is not null or mpin_enabled)
       or not pg_temp.secure_mpin_exact_state() then
        raise exception using errcode='55000', message='secure MPIN final state is partial or incompatible';
    end if;
end
$verify$;

commit;
