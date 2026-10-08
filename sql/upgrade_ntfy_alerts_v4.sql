begin;

create extension if not exists pgcrypto;

create table if not exists public.tg_alert_settings (
  user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  provider text not null default 'ntfy'
    check (provider in ('ntfy','none')),
  ntfy_topic text not null default ('promo-' || replace(gen_random_uuid()::text,'-','')),
  ntfy_priority smallint not null default 5
    check (ntfy_priority between 1 and 5),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.tg_alert_settings(user_id)
select id from auth.users
on conflict (user_id) do nothing;

create or replace function public.tg_set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists tg_alert_settings_updated_at on public.tg_alert_settings;
create trigger tg_alert_settings_updated_at
before update on public.tg_alert_settings
for each row execute function public.tg_set_updated_at();

alter table public.tg_alert_settings enable row level security;

revoke all on public.tg_alert_settings from anon, authenticated;
grant select, insert, update on public.tg_alert_settings to authenticated;

drop policy if exists "alert_settings_select_own" on public.tg_alert_settings;
drop policy if exists "alert_settings_insert_own" on public.tg_alert_settings;
drop policy if exists "alert_settings_update_own" on public.tg_alert_settings;

create policy "alert_settings_select_own" on public.tg_alert_settings
for select to authenticated using (user_id=auth.uid());

create policy "alert_settings_insert_own" on public.tg_alert_settings
for insert to authenticated with check (user_id=auth.uid());

create policy "alert_settings_update_own" on public.tg_alert_settings
for update to authenticated
using (user_id=auth.uid())
with check (user_id=auth.uid());

commit;
