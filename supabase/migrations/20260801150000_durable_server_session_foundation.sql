-- Phase 1B-2C1: durable server-session foundation only.
-- No runtime wiring, session rows, backfill, event activation, or legacy-row DML.

begin;

do $migration$
declare
    table_present boolean := to_regclass('public.user_sessions') is not null;
    owned_device_constraint boolean;
    exact_state boolean;
begin
    select exists (
        select 1 from pg_constraint c
        join pg_class r on r.oid = c.conrelid
        join pg_namespace n on n.oid = r.relnamespace
        where n.nspname = 'public' and r.relname = 'trusted_devices'
          and c.conname = 'trusted_devices_session_owner_unique'
    ) into owned_device_constraint;

    if not table_present then
        if owned_device_constraint then
            raise exception using errcode = '55000',
                message = 'durable session foundation is partial or incompatible';
        end if;
        if to_regclass('public.users') is null or to_regclass('public.trusted_devices') is null then
            raise exception using errcode = '55000',
                message = 'durable session foundation requires users and trusted_devices';
        end if;

        lock table public.users in share mode;
        lock table public.trusted_devices in share row exclusive mode;

        alter table public.trusted_devices
            add constraint trusted_devices_session_owner_unique unique (id, user_id);

        create table public.user_sessions (
            session_id uuid primary key default gen_random_uuid(),
            user_id bigint not null,
            token_digest bytea not null,
            trusted_device_id bigint,
            created_at timestamptz not null default now(),
            authenticated_at timestamptz not null default now(),
            last_genuine_activity_at timestamptz not null default now(),
            inactivity_expires_at timestamptz not null,
            absolute_expires_at timestamptz not null,
            access_locked boolean not null default false,
            access_locked_at timestamptz,
            revoked_at timestamptz,
            revocation_reason text,
            token_version integer not null default 1,
            token_rotated_at timestamptz,
            updated_at timestamptz not null default now(),
            constraint user_sessions_user_fk foreign key (user_id)
                references public.users (id),
            constraint user_sessions_trusted_device_owner_fk
                foreign key (trusted_device_id, user_id)
                references public.trusted_devices (id, user_id)
                on delete set null (trusted_device_id),
            constraint user_sessions_token_digest_unique unique (token_digest),
            constraint user_sessions_token_digest_shape check (octet_length(token_digest) = 32),
            constraint user_sessions_timestamp_order check (
                created_at <= authenticated_at
                and authenticated_at <= last_genuine_activity_at
                and inactivity_expires_at > last_genuine_activity_at
                and absolute_expires_at > authenticated_at
                and updated_at >= created_at
            ),
            constraint user_sessions_access_lock_state check (
                (access_locked and access_locked_at is not null)
                or (not access_locked and access_locked_at is null)
            ),
            constraint user_sessions_revocation_state check (
                (revoked_at is null and revocation_reason is null)
                or (
                    revoked_at is not null
                    and revoked_at >= authenticated_at
                    and revocation_reason in (
                        'logout', 'logout_all', 'password_changed', 'password_reset',
                        'account_blocked', 'device_removed', 'inactivity_expired',
                        'absolute_expiry', 'security_action', 'token_rotated',
                        'replay_detected'
                    )
                )
            ),
            constraint user_sessions_rotation_state check (
                token_version >= 1
                and (
                    (token_version = 1 and token_rotated_at is null)
                    or (token_version > 1 and token_rotated_at is not null
                        and token_rotated_at >= authenticated_at)
                )
            )
        );

        create index idx_user_sessions_active_token
            on public.user_sessions (token_digest) where revoked_at is null;
        create index idx_user_sessions_user_revocable
            on public.user_sessions (user_id, session_id) where revoked_at is null;

        alter table public.user_sessions enable row level security;
        create policy user_sessions_service_role_all on public.user_sessions
            for all to service_role using (true) with check (true);

        revoke all privileges on table public.user_sessions from public;
        revoke all privileges on table public.user_sessions from anon;
        revoke all privileges on table public.user_sessions from authenticated;
        revoke all privileges on table public.user_sessions from service_role;
        grant select, insert, update on table public.user_sessions to service_role;
    end if;

    select (
        (select count(*) = 16 from pg_attribute a
          where a.attrelid = 'public.user_sessions'::regclass
            and a.attnum > 0 and not a.attisdropped)
        and (select count(*) = 9 from pg_constraint c
             where c.conrelid = 'public.user_sessions'::regclass)
        and exists (select 1 from pg_constraint c where c.conrelid='public.trusted_devices'::regclass and c.conname='trusted_devices_session_owner_unique')
        and (select array_agg(c.conname order by c.conname) from pg_constraint c
             where c.conrelid='public.user_sessions'::regclass) = array[
                'user_sessions_access_lock_state', 'user_sessions_pkey',
                'user_sessions_revocation_state', 'user_sessions_rotation_state',
                'user_sessions_timestamp_order', 'user_sessions_token_digest_shape',
                'user_sessions_token_digest_unique',
                'user_sessions_trusted_device_owner_fk', 'user_sessions_user_fk'
             ]::name[]
        and not exists (
            select 1
            from (values
                ('session_id','uuid',true), ('user_id','bigint',true),
                ('token_digest','bytea',true), ('trusted_device_id','bigint',false),
                ('created_at','timestamp with time zone',true),
                ('authenticated_at','timestamp with time zone',true),
                ('last_genuine_activity_at','timestamp with time zone',true),
                ('inactivity_expires_at','timestamp with time zone',true),
                ('absolute_expires_at','timestamp with time zone',true),
                ('access_locked','boolean',true),
                ('access_locked_at','timestamp with time zone',false),
                ('revoked_at','timestamp with time zone',false),
                ('revocation_reason','text',false), ('token_version','integer',true),
                ('token_rotated_at','timestamp with time zone',false),
                ('updated_at','timestamp with time zone',true)
            ) expected(name, data_type, not_null)
            left join pg_attribute a on a.attrelid='public.user_sessions'::regclass
                and a.attname=expected.name and a.attnum > 0 and not a.attisdropped
            where a.attname is null
               or format_type(a.atttypid, a.atttypmod) <> expected.data_type
               or a.attnotnull <> expected.not_null
        )
        and (select count(*) = 7 from pg_attrdef d where d.adrelid='public.user_sessions'::regclass)
        and exists (select 1 from pg_attrdef d join pg_attribute a on a.attrelid=d.adrelid and a.attnum=d.adnum where d.adrelid='public.user_sessions'::regclass and a.attname='session_id' and pg_get_expr(d.adbin,d.adrelid)='gen_random_uuid()')
        and exists (select 1 from pg_attrdef d join pg_attribute a on a.attrelid=d.adrelid and a.attnum=d.adnum where d.adrelid='public.user_sessions'::regclass and a.attname='access_locked' and pg_get_expr(d.adbin,d.adrelid)='false')
        and exists (select 1 from pg_attrdef d join pg_attribute a on a.attrelid=d.adrelid and a.attnum=d.adnum where d.adrelid='public.user_sessions'::regclass and a.attname='token_version' and pg_get_expr(d.adbin,d.adrelid)='1')
        and (select count(*) = 4 from pg_attrdef d join pg_attribute a on a.attrelid=d.adrelid and a.attnum=d.adnum where d.adrelid='public.user_sessions'::regclass and a.attname in ('created_at','authenticated_at','last_genuine_activity_at','updated_at') and pg_get_expr(d.adbin,d.adrelid)='now()')
        and exists (select 1 from pg_constraint c where c.conrelid='public.user_sessions'::regclass and c.conname='user_sessions_token_digest_shape' and pg_get_constraintdef(c.oid) like '%octet_length(token_digest) = 32%')
        and exists (select 1 from pg_constraint c where c.conrelid='public.user_sessions'::regclass and c.conname='user_sessions_trusted_device_owner_fk' and pg_get_constraintdef(c.oid) like '%FOREIGN KEY (trusted_device_id, user_id)%trusted_devices(id, user_id)%')
        and exists (select 1 from pg_constraint c where c.conrelid='public.user_sessions'::regclass and c.conname='user_sessions_timestamp_order' and pg_get_constraintdef(c.oid) like '%created_at <= authenticated_at%' and pg_get_constraintdef(c.oid) like '%inactivity_expires_at > last_genuine_activity_at%' and pg_get_constraintdef(c.oid) like '%absolute_expires_at > authenticated_at%')
        and exists (select 1 from pg_constraint c where c.conrelid='public.user_sessions'::regclass and c.conname='user_sessions_access_lock_state' and pg_get_constraintdef(c.oid) like '%access_locked_at IS NOT NULL%' and pg_get_constraintdef(c.oid) like '%access_locked_at IS NULL%')
        and exists (select 1 from pg_constraint c where c.conrelid='public.user_sessions'::regclass and c.conname='user_sessions_revocation_state' and pg_get_constraintdef(c.oid) like '%replay_detected%' and pg_get_constraintdef(c.oid) like '%revocation_reason IS NULL%')
        and exists (select 1 from pg_constraint c where c.conrelid='public.user_sessions'::regclass and c.conname='user_sessions_rotation_state' and pg_get_constraintdef(c.oid) like '%token_version >= 1%' and pg_get_constraintdef(c.oid) like '%token_rotated_at IS NOT NULL%')
        and exists (select 1 from pg_indexes where schemaname='public' and tablename='user_sessions' and indexname='idx_user_sessions_active_token' and indexdef like '%WHERE (revoked_at IS NULL)%')
        and exists (select 1 from pg_indexes where schemaname='public' and tablename='user_sessions' and indexname='idx_user_sessions_user_revocable' and indexdef like '%WHERE (revoked_at IS NULL)%')
        and (select relrowsecurity and not relforcerowsecurity from pg_class where oid='public.user_sessions'::regclass)
        and (select count(*) = 1 from pg_policies where schemaname='public' and tablename='user_sessions' and policyname='user_sessions_service_role_all' and roles='{service_role}' and cmd='ALL')
        and not exists (select 1 from information_schema.role_table_grants where table_schema='public' and table_name='user_sessions' and grantee in ('PUBLIC','anon','authenticated'))
        and has_table_privilege('service_role', 'public.user_sessions', 'select')
        and has_table_privilege('service_role', 'public.user_sessions', 'insert')
        and has_table_privilege('service_role', 'public.user_sessions', 'update')
        and not has_table_privilege('service_role', 'public.user_sessions', 'delete')
        and not has_table_privilege('service_role', 'public.user_sessions', 'truncate')
        and not has_table_privilege('service_role', 'public.user_sessions', 'references')
        and not has_table_privilege('service_role', 'public.user_sessions', 'trigger')
    ) into exact_state;

    if not exact_state then
        raise exception using errcode = '55000',
            message = 'durable session foundation final state is partial or incompatible';
    end if;
end
$migration$;

commit;
