-- ============================================================================
-- MIGRATION: dedup safeguards, invoice/notes cleanup support, device tracking
-- Run this AFTER migration_vendors_and_years.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Columns to track WHO and from WHAT DEVICE a row was created/modified
--    (created_by / updated_by already exist as text usernames)
-- ---------------------------------------------------------------------------
alter table public.expenses add column if not exists created_device text;
alter table public.expenses add column if not exists updated_device text;

-- audit log: capture the device too
alter table public.expense_audit_log add column if not exists device text;

-- ---------------------------------------------------------------------------
-- 2. Activity log — every login, so the admin page can show who's actively
--    using the app and from which device
-- ---------------------------------------------------------------------------
create table if not exists public.activity_log (
  id          uuid primary key default gen_random_uuid(),
  username    text,
  action      text,                 -- 'login', 'add_expense', 'edit_expense', ...
  device      text,                 -- browser / OS string
  detail      text,
  created_at  timestamptz not null default now()
);
create index if not exists idx_activity_user on public.activity_log(username);
create index if not exists idx_activity_time on public.activity_log(created_at desc);

alter table public.activity_log enable row level security;
create policy "activity_all" on public.activity_log for all using (true) with check (true);

create or replace function public.log_activity(p_username text, p_action text, p_device text, p_detail text)
returns void as $$
  insert into public.activity_log (username, action, device, detail)
  values (p_username, p_action, p_device, p_detail);
$$ language sql security definer;
grant execute on function public.log_activity(text, text, text, text) to anon, authenticated;

create or replace function public.recent_activity(p_limit int default 100)
returns setof public.activity_log as $$
  select * from public.activity_log order by created_at desc limit p_limit;
$$ language sql security definer;
grant execute on function public.recent_activity(int) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Duplicate detection — a helper the app calls before inserting, plus a
--    partial unique index so identical (non-deleted) rows can't be saved twice.
--    "Identical" = same category, date, amount, vendor, invoice.
-- ---------------------------------------------------------------------------
create or replace function public.expense_exists(
  p_category text, p_date date, p_amount numeric, p_vendor text, p_invoice text)
returns boolean as $$
  select exists(
    select 1 from public.expenses
    where deleted_at is null
      and category_code = p_category
      and txn_date = p_date
      and amount = p_amount
      and coalesce(lower(trim(vendor)),'') = coalesce(lower(trim(p_vendor)),'')
      and coalesce(lower(trim(invoice_number)),'') = coalesce(lower(trim(p_invoice)),'')
  );
$$ language sql security definer;
grant execute on function public.expense_exists(text, date, numeric, text, text) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- 4. Timezone note: timestamps are stored in UTC (correct). The app converts
--    to America/Denver (Mountain Time) for display. No schema change needed;
--    handled in the application layer.
-- ---------------------------------------------------------------------------

-- ============================================================================
