-- Pre-merge security correction: one-time OTP/reset authorization claims.
-- Existing reset authorizations are invalidated because their legacy verifier
-- and read-before-consume behavior cannot safely participate in the new state.

begin;

lock table public.reset_tokens in access exclusive mode;

create or replace function pg_temp.reset_authorization_exact_state()
returns boolean language sql stable as $exact$
    select
        (select count(*) from pg_attribute
          where attrelid='public.reset_tokens'::regclass
            and attnum>0 and not attisdropped) = 11
    and exists(select 1 from information_schema.columns where table_schema='public'
          and table_name='reset_tokens' and column_name='claim_state'
          and data_type='text' and is_nullable='NO' and column_default like '%available%')
    and exists(select 1 from information_schema.columns where table_schema='public'
          and table_name='reset_tokens' and column_name='claim_digest'
          and data_type='bytea' and is_nullable='YES')
    and exists(select 1 from information_schema.columns where table_schema='public'
          and table_name='reset_tokens' and column_name='claimed_at'
          and data_type='timestamp with time zone' and is_nullable='YES')
    and exists(select 1 from information_schema.columns where table_schema='public'
          and table_name='reset_tokens' and column_name='completed_at'
          and data_type='timestamp with time zone' and is_nullable='YES')
    and exists(select 1 from pg_constraint where conrelid='public.reset_tokens'::regclass
          and conname='reset_tokens_token_hash_unique' and contype='u')
    and exists(select 1 from pg_constraint where conrelid='public.reset_tokens'::regclass
          and conname='reset_tokens_claim_state' and contype='c'
          and pg_get_constraintdef(oid) like '%reconciliation_required%')
    and exists(select 1 from pg_indexes where schemaname='public'
          and tablename='reset_tokens'
          and indexname='reset_tokens_claim_digest_unique'
          and indexdef like '%WHERE (claim_digest IS NOT NULL)%')
    and (select relrowsecurity from pg_class where oid='public.reset_tokens'::regclass)
    and (select count(*) from pg_policies where schemaname='public'
          and tablename='reset_tokens'
          and policyname='reset_tokens_service_role_all'
          and roles='{service_role}' and cmd='ALL') = 1
    and not exists(select 1 from pg_policies where schemaname='public'
          and tablename='reset_tokens' and policyname<>'reset_tokens_service_role_all')
    and not exists(select 1 from information_schema.role_table_grants
          where table_schema='public' and table_name='reset_tokens'
            and grantee in ('PUBLIC','anon','authenticated'))
    and (select array_agg(privilege_type::text order by privilege_type)
          from information_schema.role_table_grants
          where table_schema='public' and table_name='reset_tokens'
            and grantee='service_role')
        = array['INSERT','SELECT','UPDATE']::text[]
    and not exists(
        select 1
          from pg_class c
          cross join lateral aclexplode(c.relacl) acl
          left join pg_roles r on r.oid=acl.grantee
         where c.oid='public.reset_tokens_id_seq'::regclass
           and (acl.grantee=0 or r.rolname in ('anon','authenticated'))
    )
    and (select array_agg(acl.privilege_type::text order by acl.privilege_type)
          from pg_class c
          cross join lateral aclexplode(c.relacl) acl
          join pg_roles r on r.oid=acl.grantee
         where c.oid='public.reset_tokens_id_seq'::regclass
           and r.rolname='service_role')
        = array['SELECT','USAGE']::text[];
$exact$;

do $gate$
declare
    new_columns integer;
begin
    select count(*) into new_columns
      from information_schema.columns
     where table_schema='public' and table_name='reset_tokens'
       and column_name in ('claim_state','claim_digest','claimed_at','completed_at');

    if new_columns = 4 then
        if not pg_temp.reset_authorization_exact_state() then
            raise exception using errcode='55000',
                message='reset authorization post-state is partial or incompatible';
        end if;
        return;
    end if;

    if new_columns <> 0
       or (select count(*) from pg_attribute
             where attrelid='public.reset_tokens'::regclass
               and attnum>0 and not attisdropped) <> 7
       or (select count(*) from pg_constraint
             where conrelid='public.reset_tokens'::regclass) <> 2
       or (select count(*) from pg_indexes
             where schemaname='public' and tablename='reset_tokens') <> 2
       or not exists(select 1 from information_schema.columns
             where table_schema='public' and table_name='reset_tokens'
               and column_name='used' and data_type='integer'
               and is_nullable='NO' and column_default like '%0%') then
        raise exception using errcode='55000',
            message='reset authorization pre-state is partial or incompatible';
    end if;
end
$gate$;

do $migrate$
begin
    if not exists(select 1 from information_schema.columns
          where table_schema='public' and table_name='reset_tokens'
            and column_name='claim_state') then
        alter table public.reset_tokens
            add column claim_state text not null default 'available',
            add column claim_digest bytea,
            add column claimed_at timestamptz,
            add column completed_at timestamptz;

        update public.reset_tokens
           set used=1, claim_state='invalidated', claim_digest=null,
               claimed_at=null, completed_at=null;

        alter table public.reset_tokens
            add constraint reset_tokens_token_hash_unique unique(token_hash),
            add constraint reset_tokens_claim_state check(
                used in (0,1)
                and claim_state in (
                    'available','claimed','completed',
                    'reconciliation_required','invalidated'
                )
                and (
                    (claim_state='available' and used=0 and claim_digest is null
                        and claimed_at is null and completed_at is null
                        and token_hash ~ '^[0-9a-f]{64}$')
                    or (claim_state='claimed' and used=1
                        and octet_length(claim_digest)=32
                        and claimed_at is not null and completed_at is null
                        and token_hash ~ '^[0-9a-f]{64}$')
                    or (claim_state='completed' and used=1
                        and octet_length(claim_digest)=32
                        and claimed_at is not null and completed_at>=claimed_at
                        and token_hash ~ '^[0-9a-f]{64}$')
                    or (claim_state='reconciliation_required' and used=1
                        and octet_length(claim_digest)=32
                        and claimed_at is not null and completed_at is null
                        and token_hash ~ '^[0-9a-f]{64}$')
                    or (claim_state='invalidated' and used=1
                        and claim_digest is null and claimed_at is null
                        and completed_at is null)
                ));

        create unique index reset_tokens_claim_digest_unique
            on public.reset_tokens(claim_digest) where claim_digest is not null;

        drop policy admin_all_reset_tokens on public.reset_tokens;
        create policy reset_tokens_service_role_all on public.reset_tokens
            for all to service_role using(true) with check(true);
        revoke all privileges on table public.reset_tokens
            from public, anon, authenticated, service_role;
        grant select, insert, update on table public.reset_tokens to service_role;
        revoke all privileges on sequence public.reset_tokens_id_seq
            from public, anon, authenticated, service_role;
        grant usage, select on sequence public.reset_tokens_id_seq to service_role;
    end if;
end
$migrate$;

do $verify$
begin
    if not pg_temp.reset_authorization_exact_state() then
        raise exception using errcode='55000',
            message='reset authorization migration verification failed';
    end if;
end
$verify$;

commit;
