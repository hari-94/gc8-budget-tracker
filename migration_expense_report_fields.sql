-- ============================================================================
-- MIGRATION: extra fields captured from Emburse expense-report imports
-- Run once in Supabase -> SQL Editor. Safe to re-run.
-- The app works without it; these fields are just left out until it's run.
-- ============================================================================

-- Who actually spent the money (the report's employee) - separate from created_by,
-- which is the app user who entered / imported the row.
alter table public.expenses add column if not exists spent_by text;

-- Where the purchase was made, e.g. "Frisco, CO".
alter table public.expenses add column if not exists location text;

-- Link to the receipts (and approval trail) for the expense, e.g. the Emburse
-- receipt report URL.
alter table public.expenses add column if not exists receipt_url text;

create index if not exists idx_expenses_spent_by on public.expenses(spent_by);

-- Make PostgREST pick up the new columns immediately.
notify pgrst, 'reload schema';
