-- Phase 1B-2C3C2: exact six-operation high-risk MPIN step-up integration.
-- Adds only descriptor funding binding and activates consumption/reconciliation
-- evidence. It creates no user, session, credential, authorization, or event fixture.

begin;

lock table public.canonical_event_catalog_projection in access exclusive mode;
lock table public.security_events in access exclusive mode;
lock table public.mpin_step_up_authorizations in access exclusive mode;

do $guard$
declare
    funding_column_exists boolean;
    funding_constraint_exists boolean;
    integrated_count integer;
    writable_unintegrated_count integer;
    target_integrated_count integer;
begin
    select exists (
        select 1 from information_schema.columns
         where table_schema='public'
           and table_name='mpin_step_up_authorizations'
           and column_name='funding_source'
           and data_type='text'
    ) into funding_column_exists;
    select exists (
        select 1
          from pg_constraint constraint_value
          join pg_class relation on relation.oid=constraint_value.conrelid
          join pg_namespace namespace on namespace.oid=relation.relnamespace
         where namespace.nspname='public'
           and relation.relname='mpin_step_up_authorizations'
           and constraint_value.conname='mpin_step_up_descriptor_shape'
           and pg_get_constraintdef(constraint_value.oid,false) like '%funding_source%'
    ) into funding_constraint_exists;
    select count(*) into integrated_count
      from public.canonical_event_catalog_projection
     where integrated;
    select count(*) into writable_unintegrated_count
      from public.canonical_event_catalog_projection
     where writable and not integrated;
    select count(*) into target_integrated_count
      from public.canonical_event_catalog_projection
     where event_name in (
        'security.mpin.step_up_consumed',
        'security.mpin.step_up_reconciliation_required'
     ) and integrated;

    if to_regclass('public.mpin_step_up_authorizations') is null
       or (select count(*) from public.canonical_event_catalog_projection) <> 172
       or not exists (
           select 1 from public.canonical_event_catalog_projection
            where event_name='security.mpin.step_up_consumed'
              and writable and lifecycle_status='planned'
       )
       or not exists (
           select 1 from public.canonical_event_catalog_projection
            where event_name='security.mpin.step_up_reconciliation_required'
              and writable and lifecycle_status='planned'
       )
       or not (
           (
               not funding_column_exists
               and not funding_constraint_exists
               and integrated_count=23
               and writable_unintegrated_count=135
               and target_integrated_count=0
           )
           or (
               funding_column_exists
               and funding_constraint_exists
               and integrated_count=25
               and writable_unintegrated_count=133
               and target_integrated_count=2
           )
       ) then
        raise exception using errcode='55000',
            message='MPIN step-up integration pre-state is incompatible';
    end if;
end
$guard$;

alter table public.mpin_step_up_authorizations
    add column if not exists funding_source text;

alter table public.mpin_step_up_authorizations
    drop constraint if exists mpin_step_up_descriptor_shape;
alter table public.mpin_step_up_authorizations
    add constraint mpin_step_up_descriptor_shape check (
        credential_generation>0 and resource_id>0
        and action_key ~ '^[a-z][a-z0-9_.]{1,95}$'
        and resource_type ~ '^[a-z][a-z0-9_]{0,47}$'
        and (amount_minor is null or amount_minor>0)
        and ((amount_minor is null and currency is null)
          or (amount_minor is not null and currency ~ '^[A-Z]{3}$'))
        and (funding_source is null or funding_source='wallet')
    );

update public.canonical_event_catalog_projection
   set integrated=true
 where event_name in (
    'security.mpin.step_up_consumed',
    'security.mpin.step_up_reconciliation_required'
 );

do $post$
begin
    if (select count(*) from public.canonical_event_catalog_projection) <> 172
       or (select count(*) from public.canonical_event_catalog_projection where integrated) <> 25
       or (select count(*) from public.canonical_event_catalog_projection where lifecycle_status='planned' and not integrated) <> 139
       or (select count(*) from public.canonical_event_catalog_projection where writable and not integrated) <> 133
       or not exists (
           select 1 from information_schema.columns
            where table_schema='public'
              and table_name='mpin_step_up_authorizations'
              and column_name='funding_source'
              and data_type='text'
       )
       or exists (
           select 1 from public.canonical_event_catalog_projection
            where event_name in (
                'security.mpin.step_up_consumed',
                'security.mpin.step_up_reconciliation_required'
            ) and not integrated
       ) then
        raise exception using errcode='55000',
            message='MPIN step-up integration final state is incompatible';
    end if;
end
$post$;

commit;
