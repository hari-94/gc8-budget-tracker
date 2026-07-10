-- ============================================================================
-- MIGRATION: backfill vendors from existing expenses + budget year carry-forward
-- Run this AFTER migration_admin_updates.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Populate the vendors table from every distinct vendor already in expenses
--    (the bulk import wrote straight to expenses and skipped this table)
-- ---------------------------------------------------------------------------
insert into public.vendors (name)
select distinct trim(vendor)
from public.expenses
where vendor is not null and trim(vendor) <> ''
on conflict (name) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Copy one fiscal year's budget into another (used to seed a new year
--    with last year's numbers, which you can then adjust)
-- ---------------------------------------------------------------------------
create or replace function public.copy_budget_year(p_from_year int, p_to_year int)
returns int as $$
declare
  rows_copied int;
begin
  insert into public.budget_allocations (category_code, fiscal_year, month, budgeted_amount)
  select category_code, p_to_year, month, budgeted_amount
  from public.budget_allocations
  where fiscal_year = p_from_year
  on conflict (category_code, fiscal_year, month) do nothing;
  get diagnostics rows_copied = row_count;
  return rows_copied;
end;
$$ language plpgsql security definer;

grant execute on function public.copy_budget_year(int, int) to anon, authenticated;

-- ============================================================================
