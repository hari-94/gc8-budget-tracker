-- ============================================================================
-- GC8 BUDGET TRACKER — SUPABASE SCHEMA
-- Run this in Supabase SQL Editor (Project → SQL Editor → New Query)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. EXTENSIONS
-- ---------------------------------------------------------------------------
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- 1. PROFILES  (extends Supabase auth.users with role info)
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text not null,
  full_name   text,
  role        text not null default 'viewer' check (role in ('admin','editor','viewer')),
  created_at  timestamptz not null default now()
);

-- Auto-create a profile row whenever a new auth user signs up
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, role)
  values (new.id, new.email, 'viewer');
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- 2. CATEGORIES  (chart of accounts — from "Category & Code" / "Budget_26")
-- ---------------------------------------------------------------------------
create table if not exists public.categories (
  code        text primary key,               -- e.g. '72500-570'
  name        text not null,                   -- e.g. 'Cleaning Supplies'
  group_name  text,                            -- e.g. 'Supplies','Laundry','Cleaning','Facilities & Maintenance','G&A','Income'
  type        text not null default 'expense' check (type in ('income','expense')),
  is_active   boolean not null default true,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 3. BUDGET ALLOCATIONS  (planned $ per category, per month, per fiscal year)
-- ---------------------------------------------------------------------------
create table if not exists public.budget_allocations (
  id                uuid primary key default gen_random_uuid(),
  category_code     text not null references public.categories(code) on delete cascade,
  fiscal_year       int  not null,
  month             int  not null check (month between 1 and 12),
  budgeted_amount   numeric(12,2) not null default 0,
  updated_by        uuid references public.profiles(id),
  updated_at        timestamptz not null default now(),
  unique (category_code, fiscal_year, month)
);

-- ---------------------------------------------------------------------------
-- 4. VENDORS  (lightweight lookup, built up as people type new ones)
-- ---------------------------------------------------------------------------
create table if not exists public.vendors (
  id          uuid primary key default gen_random_uuid(),
  name        text unique not null,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 5. EXPENSES  (actual + planned/upcoming line items)
-- ---------------------------------------------------------------------------
create table if not exists public.expenses (
  id                uuid primary key default gen_random_uuid(),
  category_code     text not null references public.categories(code),
  vendor            text,
  invoice_number    text,
  txn_date          date not null,
  amount            numeric(12,2) not null,
  status            text not null default 'paid' check (status in ('paid','pending','planned')),
  notes             text,                       -- quick single-line note (legacy/simple)
  building          text,                       -- optional: B1 / B2 / B3, if you want to tag by building
  created_by        uuid references public.profiles(id),
  created_at        timestamptz not null default now(),
  updated_by        uuid references public.profiles(id),
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz                 -- soft delete instead of hard delete
);

create index if not exists idx_expenses_category on public.expenses(category_code);
create index if not exists idx_expenses_date on public.expenses(txn_date);
create index if not exists idx_expenses_status on public.expenses(status);
create index if not exists idx_expenses_not_deleted on public.expenses(deleted_at) where deleted_at is null;

-- ---------------------------------------------------------------------------
-- 6. EXPENSE NOTES  (threaded notes/comments on a line item — many per expense)
-- ---------------------------------------------------------------------------
create table if not exists public.expense_notes (
  id            uuid primary key default gen_random_uuid(),
  expense_id    uuid not null references public.expenses(id) on delete cascade,
  note          text not null,
  created_by    uuid references public.profiles(id),
  created_at    timestamptz not null default now()
);

create index if not exists idx_expense_notes_expense on public.expense_notes(expense_id);

-- ---------------------------------------------------------------------------
-- 7. AUDIT LOG  (automatic history of every insert/update/delete on expenses)
-- ---------------------------------------------------------------------------
create table if not exists public.expense_audit_log (
  id            uuid primary key default gen_random_uuid(),
  expense_id    uuid not null,
  action        text not null check (action in ('insert','update','delete')),
  old_data      jsonb,
  new_data      jsonb,
  changed_by    uuid references public.profiles(id),
  changed_at    timestamptz not null default now()
);

create index if not exists idx_audit_expense on public.expense_audit_log(expense_id);

-- Trigger function: logs every change automatically, and bumps updated_at
create or replace function public.log_expense_change()
returns trigger as $$
begin
  if tg_op = 'INSERT' then
    insert into public.expense_audit_log(expense_id, action, new_data, changed_by)
    values (new.id, 'insert', to_jsonb(new), new.created_by);
    return new;
  elsif tg_op = 'UPDATE' then
    new.updated_at := now();
    insert into public.expense_audit_log(expense_id, action, old_data, new_data, changed_by)
    values (new.id, 'update', to_jsonb(old), to_jsonb(new), new.updated_by);
    return new;
  elsif tg_op = 'DELETE' then
    insert into public.expense_audit_log(expense_id, action, old_data, changed_by)
    values (old.id, 'delete', to_jsonb(old), old.updated_by);
    return old;
  end if;
  return null;
end;
$$ language plpgsql security definer;

drop trigger if exists trg_expense_audit on public.expenses;
create trigger trg_expense_audit
  before insert or update or delete on public.expenses
  for each row execute function public.log_expense_change();

-- ---------------------------------------------------------------------------
-- 8. HANDY VIEWS FOR THE DASHBOARD
-- ---------------------------------------------------------------------------

-- Total spent per category per month (actuals only, excludes soft-deleted & 'planned')
create or replace view public.v_actuals_by_category_month as
select
  category_code,
  extract(year from txn_date)::int  as fiscal_year,
  extract(month from txn_date)::int as month,
  sum(amount) filter (where status in ('paid','pending')) as spent_amount,
  sum(amount) filter (where status = 'planned')            as planned_amount,
  count(*)                                                  as txn_count
from public.expenses
where deleted_at is null
group by 1,2,3;

-- Budget vs Actual, joined
create or replace view public.v_budget_vs_actual as
select
  c.code,
  c.name,
  c.group_name,
  c.type,
  b.fiscal_year,
  b.month,
  b.budgeted_amount,
  coalesce(a.spent_amount, 0)   as spent_amount,
  coalesce(a.planned_amount, 0) as planned_amount,
  b.budgeted_amount - coalesce(a.spent_amount, 0) as remaining_amount
from public.categories c
join public.budget_allocations b on b.category_code = c.code
left join public.v_actuals_by_category_month a
  on a.category_code = c.code and a.fiscal_year = b.fiscal_year and a.month = b.month;

-- Dashboard headline numbers (current fiscal year, all expense categories)
create or replace view public.v_dashboard_summary as
select
  fiscal_year,
  sum(budgeted_amount) as total_budget,
  sum(spent_amount)    as total_spent,
  sum(planned_amount)  as total_planned,
  sum(budgeted_amount) - sum(spent_amount) as total_remaining
from public.v_budget_vs_actual
where type = 'expense'
group by fiscal_year;

-- ---------------------------------------------------------------------------
-- 9. ROW LEVEL SECURITY
-- ---------------------------------------------------------------------------
alter table public.profiles            enable row level security;
alter table public.categories          enable row level security;
alter table public.budget_allocations  enable row level security;
alter table public.vendors             enable row level security;
alter table public.expenses            enable row level security;
alter table public.expense_notes       enable row level security;
alter table public.expense_audit_log   enable row level security;

-- Helper: current user's role
create or replace function public.current_role()
returns text as $$
  select role from public.profiles where id = auth.uid();
$$ language sql stable security definer;

-- PROFILES: everyone can read all profiles (for name lookups); only admins edit roles
create policy "profiles_select_all" on public.profiles for select using (true);
create policy "profiles_update_admin" on public.profiles for update
  using (public.current_role() = 'admin');

-- CATEGORIES: everyone can read; only admins can write
create policy "categories_select_all" on public.categories for select using (true);
create policy "categories_write_admin" on public.categories for all
  using (public.current_role() = 'admin')
  with check (public.current_role() = 'admin');

-- BUDGET ALLOCATIONS: everyone can read; admin + editor can write
create policy "budget_select_all" on public.budget_allocations for select using (true);
create policy "budget_write_editor" on public.budget_allocations for all
  using (public.current_role() in ('admin','editor'))
  with check (public.current_role() in ('admin','editor'));

-- VENDORS: everyone can read; admin + editor can write
create policy "vendors_select_all" on public.vendors for select using (true);
create policy "vendors_write_editor" on public.vendors for all
  using (public.current_role() in ('admin','editor'))
  with check (public.current_role() in ('admin','editor'));

-- EXPENSES: everyone can read; admin + editor can insert/update; only admin can hard delete
-- (soft delete via UPDATE is how 'editor' removes a row — see app logic)
create policy "expenses_select_all" on public.expenses for select using (true);
create policy "expenses_insert_editor" on public.expenses for insert
  with check (public.current_role() in ('admin','editor'));
create policy "expenses_update_editor" on public.expenses for update
  using (public.current_role() in ('admin','editor'))
  with check (public.current_role() in ('admin','editor'));
create policy "expenses_delete_admin" on public.expenses for delete
  using (public.current_role() = 'admin');

-- EXPENSE NOTES: everyone can read; admin + editor can add; only admin can delete
create policy "notes_select_all" on public.expense_notes for select using (true);
create policy "notes_insert_editor" on public.expense_notes for insert
  with check (public.current_role() in ('admin','editor'));
create policy "notes_delete_admin" on public.expense_notes for delete
  using (public.current_role() = 'admin');

-- AUDIT LOG: read-only for everyone (admin + editor), no direct writes (trigger uses security definer)
create policy "audit_select_all" on public.expense_audit_log for select using (true);

-- ---------------------------------------------------------------------------
-- 10. SEED: chart of accounts pulled from your workbook's "Budget_26" / "Category & Code" tabs
-- ---------------------------------------------------------------------------
insert into public.categories (code, name, group_name, type) values
  ('53280-570','Weekly Clean Income','Income','income'),
  ('53300-570','Common Area Hskpg Income','Income','income'),
  ('53003-570','GC8OA Hskpg Income','Income','income'),
  ('56100-570','Misc. Income','Income','income'),
  ('56120-570','Admin Fee Income','Income','income'),
  ('71000-570','Wages - Salary','Wages','expense'),
  ('71010-570','Hourly Managers','Wages','expense'),
  ('71050-570','Hourly Inspector Wages','Wages','expense'),
  ('71150-570','Semi-Annual Employee Retention Bonus','Wages','expense'),
  ('71090-570','Temp Wages Unit','Wages','expense'),
  ('71095-570','Temp Wages Common','Wages','expense'),
  ('71070-570','Hourly Housekeeper Wages','Wages','expense'),
  ('71071-570','Hourly Houseperson Wages','Wages','expense'),
  ('71130-570','P/R Taxes','Wages','expense'),
  ('71600-570','Health Benefits: Hskp GC8','Wages','expense'),
  ('71620-570','401K Match: Hskp GC8','Wages','expense'),
  ('71640-570','Safety/WC: Hskp GC8','Wages','expense'),
  ('71700-570','Education & Training','G&A','expense'),
  ('71750-570','Uniforms','G&A','expense'),
  ('71800-570','Office Rent','G&A','expense'),
  ('72500-570','Cleaning Supplies','Supplies','expense'),
  ('72520-570','Common Area Cleaning Supplies','Supplies','expense'),
  ('72550-570','In Room Guest Amenities','Supplies','expense'),
  ('72560-570','Common Area Guest Amenities','Supplies','expense'),
  ('72600-570','Unit Laundry Expense','Laundry','expense'),
  ('72650-570','Common Laundry Expense','Laundry','expense'),
  ('72700-570','Linen Expense','Laundry','expense'),
  ('72800-570','Unit Inventory','Supplies','expense'),
  ('72900-570','Window Cleaning','Cleaning','expense'),
  ('72950-570','Carpet Cleaning Unit','Cleaning','expense'),
  ('72960-570','Carpet Cleaning Common','Cleaning','expense'),
  ('73100-570','Maintenance Expense','Facilities & Maintenance','expense'),
  ('73200-570','Vendor Services','Facilities & Maintenance','expense'),
  ('73300-570','Misc. Unit Furniture','Facilities & Maintenance','expense'),
  ('73400-570','Housekeeping Tools','Facilities & Maintenance','expense'),
  ('73600-570','Equipment Maintenance','Facilities & Maintenance','expense'),
  ('73610-570','Laundry Equipment Maintenance','Facilities & Maintenance','expense'),
  ('73700-570','Vehicle Maintenance','Facilities & Maintenance','expense'),
  ('73710-570','Gas & Oil','Facilities & Maintenance','expense'),
  ('73820-570','Owner/Guest Comp','G&A','expense'),
  ('73850-570','Licenses & Permits','G&A','expense'),
  ('74660-570','Utilities','G&A','expense'),
  ('74690-570','Telephone','G&A','expense'),
  ('74890-570','Equip/Furniture Rent','G&A','expense'),
  ('74910-570','Office Supplies','G&A','expense'),
  ('74920-570','COVID19 Protection','G&A','expense'),
  ('74950-570','Postage & Shipping','G&A','expense'),
  ('74970-570','Dues & Subscriptions','G&A','expense'),
  ('75000-570','Meals','G&A','expense'),
  ('75030-570','Entertainment Non-Deductible','G&A','expense'),
  ('75050-570','Employee Incentive','G&A','expense'),
  ('75060-570','ERA Expense','G&A','expense'),
  ('75100-570','Travel & Lodging','G&A','expense')
on conflict (code) do nothing;

-- ============================================================================
-- END OF SCRIPT
-- After running this, make your own account an admin with:
--   update public.profiles set role = 'admin' where email = 'you@example.com';
-- ============================================================================
