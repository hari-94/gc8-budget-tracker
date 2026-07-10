-- ============================================================================
-- MIGRATION: admin user list/delete, role updates, restore-from-deleted support
-- Run this AFTER migration_simple_login.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Let the app list existing users (without exposing password hashes)
-- ---------------------------------------------------------------------------
create or replace function public.list_app_users()
returns table(username text, full_name text, role text, created_at timestamptz) as $$
  select username, full_name, role, created_at
  from public.app_users
  order by username;
$$ language sql security definer;

grant execute on function public.list_app_users() to anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. Let the app remove a user's login entirely
-- ---------------------------------------------------------------------------
create or replace function public.delete_app_user(p_username text)
returns void as $$
  delete from public.app_users where username = p_username;
$$ language sql security definer;

grant execute on function public.delete_app_user(text) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Role updates: Jazmin -> admin, Liz & Rigo stay editor
-- ---------------------------------------------------------------------------
update public.app_users set role = 'admin' where username = 'jazmin';
-- liz and rigo are already 'editor' from the previous migration, no change needed

-- ---------------------------------------------------------------------------
-- 4. Restore a soft-deleted expense
-- ---------------------------------------------------------------------------
create or replace function public.restore_expense(p_expense_id uuid)
returns void as $$
  update public.expenses set deleted_at = null where id = p_expense_id;
$$ language sql security definer;

grant execute on function public.restore_expense(uuid) to anon, authenticated;

-- ============================================================================

-- ---------------------------------------------------------------------------
-- 5. Update just a user's role, without touching their password
-- ---------------------------------------------------------------------------
create or replace function public.update_user_role(p_username text, p_role text)
returns void as $$
  update public.app_users set role = p_role where username = p_username;
$$ language sql security definer;

grant execute on function public.update_user_role(text, text) to anon, authenticated;
