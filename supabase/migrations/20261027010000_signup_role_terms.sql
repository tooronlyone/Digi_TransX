-- Account agreements belong to signup, not to individual booking reminders.
create table if not exists public.signup_terms_acceptances (
    user_id bigint not null references public.users(id) on delete cascade,
    terms_version text not null,
    role text not null check (role in ('service_seeker','everyday_user','logistics_provider','driver','fuel_station_manager','shopkeeper')),
    accepted_at timestamptz not null default now(),
    document_snapshot jsonb not null check (jsonb_typeof(document_snapshot) = 'object'),
    primary key (user_id, terms_version, role)
);
alter table public.signup_terms_acceptances enable row level security;
revoke all on public.signup_terms_acceptances from public, anon, authenticated;
comment on table public.signup_terms_acceptances is 'Server-recorded role agreement accepted during signup; reminder display never creates consent.';
