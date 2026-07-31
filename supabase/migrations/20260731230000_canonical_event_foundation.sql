-- Phase 1B-1: canonical event foundation only.
-- No runtime route is connected, no historical row is copied, and no outbox
-- is created because there is no current asynchronous event consumer.

do $$
declare
    existing_count integer;
    target_table text;
    column_count integer;
begin
    select count(*) into existing_count
    from information_schema.tables as catalog_tables
    where catalog_tables.table_schema = 'public'
      and catalog_tables.table_name in ('security_events', 'business_audit_events')
      and catalog_tables.table_type = 'BASE TABLE';

    if existing_count not in (0, 2) then
        raise exception
            'canonical event foundation is partial: expected zero or both event tables, found %',
            existing_count;
    end if;

    if existing_count = 2 then
        foreach target_table in array array['security_events', 'business_audit_events'] loop
            select count(*) into column_count
            from information_schema.columns as catalog_columns
            where catalog_columns.table_schema = 'public'
              and catalog_columns.table_name = target_table;
            if column_count <> 43 then
                raise exception
                    'canonical event table public.% has unexpected column count %',
                    target_table, column_count;
            end if;
        end loop;
    end if;
end
$$;

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
        and (actor_type not in ('user', 'admin') or actor_id is not null)
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
        and (actor_type not in ('user', 'admin') or actor_id is not null)
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

drop trigger if exists trg_business_audit_events_no_update on public.business_audit_events;
create trigger trg_business_audit_events_no_update
    before update on public.business_audit_events
    for each row execute function public.prevent_canonical_event_update();

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

drop policy if exists security_events_service_role_all on public.security_events;
create policy security_events_service_role_all on public.security_events
    for all to service_role using (true) with check (true);
drop policy if exists business_audit_events_service_role_all on public.business_audit_events;
create policy business_audit_events_service_role_all on public.business_audit_events
    for all to service_role using (true) with check (true);

revoke all on table public.security_events from public;
revoke all on table public.business_audit_events from public;
revoke all on function public.is_bounded_event_json(jsonb, text) from public;
revoke all on function public.prevent_canonical_event_update() from public;

do $$
declare
    client_role text;
begin
    foreach client_role in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = client_role) then
            execute format('revoke all on table public.security_events from %I', client_role);
            execute format('revoke all on table public.business_audit_events from %I', client_role);
            execute format(
                'revoke all on function public.is_bounded_event_json(jsonb, text) from %I',
                client_role
            );
            execute format(
                'revoke all on function public.prevent_canonical_event_update() from %I',
                client_role
            );
        end if;
    end loop;

    if exists (select 1 from pg_roles where rolname = 'service_role') then
        grant select, insert, delete on public.security_events to service_role;
        grant select, insert, delete on public.business_audit_events to service_role;
        grant execute on function public.is_bounded_event_json(jsonb, text) to service_role;
    end if;
end
$$;
