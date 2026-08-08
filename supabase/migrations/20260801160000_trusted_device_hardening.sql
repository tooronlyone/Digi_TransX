-- Phase 1B-2C2: hash trusted-device credentials and add bounded lifecycle state.
-- Exact legacy rows retain their stable id/user ownership and are converted in-place.

begin;

lock table public.trusted_devices in access exclusive mode;
lock table public.user_sessions in share row exclusive mode;
lock table public.canonical_event_catalog_projection in access exclusive mode;

do $gate$
declare
    columns text[];
    is_final boolean;
begin
    select array_agg(a.attname || ':' || pg_catalog.format_type(a.atttypid,a.atttypmod) || ':' || a.attnotnull order by a.attname)
      into columns
      from pg_attribute a
     where a.attrelid='public.trusted_devices'::regclass and a.attnum>0 and not a.attisdropped;

    is_final := columns = array[
        'created_at:timestamp with time zone:true','expires_at:timestamp with time zone:true',
        'id:bigint:true','last_used_at:timestamp with time zone:true',
        'previous_token_digest:bytea:false','revoked_at:timestamp with time zone:false','rotated_at:timestamp with time zone:false',
        'token_digest:bytea:true','user_id:bigint:true'
    ];
    if is_final then
        if (select count(*) from pg_constraint where conrelid='public.trusted_devices'::regclass
              and conname in ('trusted_devices_pkey','trusted_devices_token_digest_unique',
                 'trusted_devices_token_digest_shape','trusted_devices_previous_digest_shape',
                 'trusted_devices_user_id_fkey','trusted_devices_session_owner_unique',
                 'trusted_devices_timestamp_order')) <> 7
           or exists(select 1 from public.trusted_devices where octet_length(token_digest)<>32)
           or (select count(*) from public.canonical_event_catalog_projection
                where event_name in ('security.trusted_device.added','security.trusted_device.removed','security.trusted_device.rotated')
                  and integrated and writable and lifecycle_status='planned') <> 3 then
            raise exception using errcode='55000', message='trusted-device hardened post-state is partial or incompatible';
        end if;
        return;
    end if;

    if columns is distinct from array[
        'created_at:timestamp with time zone:true','device_token:text:true','id:bigint:true',
        'last_seen_at:timestamp with time zone:true','user_id:bigint:true'
    ]
       or (select count(*) from pg_constraint where conrelid='public.trusted_devices'::regclass
             and conname in ('trusted_devices_pkey','trusted_devices_device_token_key',
                'trusted_devices_user_id_fkey','trusted_devices_session_owner_unique')) <> 4
       or (select count(*) from public.canonical_event_catalog_projection
            where event_name in ('security.trusted_device.added','security.trusted_device.removed','security.trusted_device.rotated')
              and not integrated and writable and lifecycle_status='planned') <> 3 then
        raise exception using errcode='55000', message='trusted-device legacy pre-state is partial or incompatible';
    end if;
    if to_regprocedure('digest(bytea,text)') is null
       or pg_get_function_result(to_regprocedure('digest(bytea,text)')) <> 'bytea' then
        raise exception using errcode='55000', message='required SHA-256 digest(bytea,text) function is unavailable';
    end if;
    if exists(select 1 from public.trusted_devices where device_token is null
       or device_token !~ '^[A-Za-z0-9_-]{43}$')
       or (select count(*) from public.trusted_devices) <> (select count(distinct device_token) from public.trusted_devices) then
        raise exception using errcode='55000', message='legacy trusted-device tokens are null, duplicate, or not eligible high-entropy values';
    end if;
end
$gate$;

do $migrate$
begin
    if exists(select 1 from information_schema.columns where table_schema='public'
              and table_name='trusted_devices' and column_name='device_token') then
        alter table public.trusted_devices add column token_digest bytea;
        alter table public.trusted_devices add column previous_token_digest bytea;
        update public.trusted_devices
           set token_digest=digest(convert_to(device_token,'UTF8'),'sha256');
        alter table public.trusted_devices alter column token_digest set not null;
        alter table public.trusted_devices
            add column expires_at timestamptz,
            add column revoked_at timestamptz,
            add column rotated_at timestamptz;
        update public.trusted_devices
           set expires_at=created_at + interval '30 days';
        alter table public.trusted_devices alter column expires_at set not null;
        alter table public.trusted_devices rename column last_seen_at to last_used_at;
        alter table public.trusted_devices drop constraint trusted_devices_device_token_key;
        alter table public.trusted_devices drop column device_token;
        alter table public.trusted_devices
            add constraint trusted_devices_token_digest_unique unique(token_digest),
            add constraint trusted_devices_token_digest_shape check(octet_length(token_digest)=32),
            add constraint trusted_devices_previous_digest_shape check(
                previous_token_digest is null or octet_length(previous_token_digest)=32),
            add constraint trusted_devices_timestamp_order check(
                created_at <= last_used_at and created_at < expires_at
                and (revoked_at is null or revoked_at >= created_at)
                and (rotated_at is null or rotated_at >= created_at));
    end if;
end
$migrate$;

drop policy if exists trusted_devices_own on public.trusted_devices;
drop policy if exists admin_all_trusted_devices on public.trusted_devices;
drop policy if exists trusted_devices_service_role_all on public.trusted_devices;
create policy trusted_devices_service_role_all on public.trusted_devices
    for all to service_role using (true) with check (true);
revoke all privileges on table public.trusted_devices from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.trusted_devices to service_role;
revoke all privileges on sequence public.trusted_devices_id_seq from public, anon, authenticated, service_role;
grant usage, select on sequence public.trusted_devices_id_seq to service_role;

update public.canonical_event_catalog_projection
   set integrated=true
 where event_name in ('security.trusted_device.added','security.trusted_device.removed','security.trusted_device.rotated')
   and writable and lifecycle_status='planned';

do $verify$
begin
    if exists(select 1 from information_schema.columns where table_schema='public'
              and table_name='trusted_devices' and column_name='device_token')
       or exists(select 1 from public.trusted_devices where octet_length(token_digest)<>32)
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 10 then
        raise exception using errcode='55000', message='trusted-device hardening final verification failed';
    end if;
end
$verify$;

commit;
