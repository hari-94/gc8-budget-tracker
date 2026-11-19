-- ============================================================================
-- MIGRATION: keep-alive heartbeat
-- Supabase's free plan pauses a project after 7 days without activity. A GitHub
-- Actions workflow (.github/workflows/keepalive.yml) calls public.keepalive()
-- every 2 days, which writes one row here. Nothing in the app reads this table,
-- so it never shows up in expenses, totals or the audit log.
-- Run once in Supabase -> SQL Editor. Safe to re-run.
-- ============================================================================

create table if not exists public.keepalive (
  id         int primary key default 1 check (id = 1),   -- always exactly one row
  pinged_at  timestamptz not null default now(),
  ping_count bigint not null default 1
);

-- No direct table access for app users; only the function below touches it.
alter table public.keepalive enable row level security;

create or replace function public.keepalive()
returns timestamptz as $$
  insert into public.keepalive (id, pinged_at, ping_count) values (1, now(), 1)
  on conflict (id) do update
    set pinged_at = now(), ping_count = public.keepalive.ping_count + 1
  returning pinged_at;
$$ language sql security definer set search_path = public;

grant execute on function public.keepalive() to anon, authenticated;

notify pgrst, 'reload schema';
