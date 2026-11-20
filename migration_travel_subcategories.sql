-- ============================================================================
-- Split Travel & Lodging (75100) into the lines Emburse offers:
--   75100-Travel & Lodging-Prop Mgmt  -> 75100-570      Travel & Lodging (existing)
--   75100-Lodging                     -> 75100-570-LDG  Lodging          (new)
--   75100-Mileage                     -> 75100-570-MIL  Mileage          (new)
-- All three still post to GL account 75100; the suffix only separates them in the app.
--
-- The dashboard lists a category only when it has budget rows for the year, so each
-- new line gets $0 rows for every fiscal year/version that already has a budget.
-- Set real amounts in Budget Planner if you want to budget them separately.
--
-- Safe to run more than once.
-- ============================================================================

insert into public.categories (code, name, group_name, type) values
  ('75100-570-LDG', 'Lodging', 'G&A', 'expense'),
  ('75100-570-MIL', 'Mileage', 'G&A', 'expense')
on conflict (code) do nothing;

-- Travel & Lodging had been archived (zero entries), which hid it from the dashboard
-- and the expense picker.
update public.categories set archived = false where code = '75100-570';

insert into public.budget_allocations (category_code, fiscal_year, month, budgeted_amount, version)
select c.code, y.fiscal_year, m.month, 0, y.version
from (values ('75100-570-LDG'), ('75100-570-MIL')) as c(code)
cross join (select distinct fiscal_year, version from public.budget_allocations) as y
cross join generate_series(1, 12) as m(month)
on conflict do nothing;
