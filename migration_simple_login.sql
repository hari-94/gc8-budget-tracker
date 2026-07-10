-- ============================================================================
-- MIGRATION: switch from Supabase Auth (email/password + confirmation emails)
-- to a simple username/password table, like the scheduler app.
-- Run this AFTER supabase_schema.sql has already been run once.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. New login table
-- ---------------------------------------------------------------------------
create table if not exists public.app_users (
  username      text primary key,
  password_hash text not null,
  full_name     text,
  role          text not null default 'viewer' check (role in ('admin','editor','viewer')),
  created_at    timestamptz not null default now()
);

alter table public.app_users enable row level security;
-- No one queries this table directly from the app except via verify_login() below,
-- so lock it down completely from the client.
create policy "app_users_no_direct_access" on public.app_users for all using (false);

-- ---------------------------------------------------------------------------
-- 2. Login-check function (password hashing/verification happens in Postgres,
--    so the plain password never gets compared client-side)
-- ---------------------------------------------------------------------------
create or replace function public.verify_login(p_username text, p_password text)
returns table(username text, full_name text, role text) as $$
  select username, full_name, role
  from public.app_users
  where username = p_username
    and password_hash = crypt(p_password, password_hash);
$$ language sql security definer;

grant execute on function public.verify_login(text, text) to anon, authenticated;

-- Helper used by the admin script/SQL below to create/update a user with a hashed password
create or replace function public.upsert_app_user(p_username text, p_password text, p_full_name text, p_role text)
returns void as $$
  insert into public.app_users (username, password_hash, full_name, role)
  values (p_username, crypt(p_password, gen_salt('bf')), p_full_name, p_role)
  on conflict (username) do update
    set password_hash = crypt(p_password, gen_salt('bf')),
        full_name = excluded.full_name,
        role = excluded.role;
$$ language sql security definer;

grant execute on function public.upsert_app_user(text, text, text, text) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Point created_by / updated_by / changed_by at usernames (text) instead
--    of Supabase Auth user ids (uuid)
-- ---------------------------------------------------------------------------
alter table public.expenses drop constraint if exists expenses_created_by_fkey;
alter table public.expenses drop constraint if exists expenses_updated_by_fkey;
alter table public.expenses alter column created_by type text using created_by::text;
alter table public.expenses alter column updated_by type text using updated_by::text;

alter table public.budget_allocations drop constraint if exists budget_allocations_updated_by_fkey;
alter table public.budget_allocations alter column updated_by type text using updated_by::text;

alter table public.expense_notes drop constraint if exists expense_notes_created_by_fkey;
alter table public.expense_notes alter column created_by type text using created_by::text;

alter table public.expense_audit_log drop constraint if exists expense_audit_log_changed_by_fkey;
alter table public.expense_audit_log alter column changed_by type text using changed_by::text;

-- The audit trigger function referenced new.created_by / old.updated_by directly, which
-- still works fine as text - no change needed there.

-- ---------------------------------------------------------------------------
-- 4. Simplify RLS: since we're no longer using Supabase Auth sessions, there's
--    no auth.uid() to check role against. Access control now happens in the
--    Streamlit app's login screen instead. Open these tables up to the anon key.
-- ---------------------------------------------------------------------------
drop policy if exists "categories_write_admin" on public.categories;
create policy "categories_write_open" on public.categories for all using (true) with check (true);

drop policy if exists "budget_write_editor" on public.budget_allocations;
create policy "budget_write_open" on public.budget_allocations for all using (true) with check (true);

drop policy if exists "vendors_write_editor" on public.vendors;
create policy "vendors_write_open" on public.vendors for all using (true) with check (true);

drop policy if exists "expenses_insert_editor" on public.expenses;
drop policy if exists "expenses_update_editor" on public.expenses;
drop policy if exists "expenses_delete_admin" on public.expenses;
create policy "expenses_write_open" on public.expenses for all using (true) with check (true);

drop policy if exists "notes_insert_editor" on public.expense_notes;
drop policy if exists "notes_delete_admin" on public.expense_notes;
create policy "notes_write_open" on public.expense_notes for all using (true) with check (true);

-- profiles/auth.users are no longer used for login, but leaving the old table alone is harmless.

-- ---------------------------------------------------------------------------
-- 5. Seed your team's logins (change these passwords after first login!)
-- ---------------------------------------------------------------------------
select public.upsert_app_user('hari',    'Har@123', 'Hari',         'admin');
select public.upsert_app_user('jazmin',  'Jaz@123', 'Jazmin',       'editor');
select public.upsert_app_user('liz',     'Liz@123', 'Liz Salazar',  'editor');
select public.upsert_app_user('rigo',    'Rig@123', 'Rigo Garcia',  'editor');

-- ============================================================================
-- To add/change a user later, just re-run:
--   select public.upsert_app_user('username', 'newpassword', 'Full Name', 'editor');
-- ============================================================================
