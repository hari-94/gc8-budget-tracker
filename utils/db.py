import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import date


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def get_authed_client() -> Client:
    """No Supabase Auth session in this app (simple username/password table instead) -
    just use the same anon client. Access control happens at the app's login screen."""
    return get_client()


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def get_categories(include_archived: bool = False) -> pd.DataFrame:
    client = get_client()
    q = client.table("categories").select("*").eq("is_active", True)
    res = q.order("code").execute()
    df = pd.DataFrame(res.data)
    if df.empty:
        return df
    # 'archived' column may not exist pre-migration; guard for it
    if "archived" in df.columns and not include_archived:
        df = df[df["archived"] != True]
    return df.reset_index(drop=True)


@st.cache_data(ttl=120)
def get_category_entry_counts() -> pd.DataFrame:
    client = get_client()
    try:
        res = client.rpc("category_entry_counts", {}).execute()
        return pd.DataFrame(res.data)
    except Exception:
        return pd.DataFrame(columns=["code", "entry_count", "total_amount"])


def set_category_archived(code: str, archived: bool):
    client = get_authed_client()
    client.rpc("set_category_archived", {"p_code": code, "p_archived": archived}).execute()
    st.cache_data.clear()


@st.cache_data(ttl=300)
def get_vendors() -> list:
    client = get_client()
    res = client.table("vendors").select("name").order("name").execute()
    return [r["name"] for r in res.data]


def add_vendor_if_new(name: str):
    if not name:
        return
    client = get_authed_client()
    client.table("vendors").upsert({"name": name.strip()}, on_conflict="name").execute()


def delete_vendor(name: str):
    """Remove a vendor from the picker list. Does not touch existing expenses."""
    client = get_authed_client()
    client.table("vendors").delete().eq("name", name).execute()
    st.cache_data.clear()


def vendor_usage_count(name: str) -> int:
    """How many active expenses reference this vendor (so we can warn before deleting)."""
    client = get_client()
    res = client.table("expenses").select("id", count="exact") \
        .eq("vendor", name).is_("deleted_at", "null").execute()
    return res.count or 0


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120)
def get_budget_vs_actual(fiscal_year: int, version: str = "Original") -> pd.DataFrame:
    client = get_client()
    q = client.table("v_budget_vs_actual").select("*").eq("fiscal_year", fiscal_year)
    # Only filter by version if the column exists (post-migration); fall back gracefully.
    try:
        res = q.eq("version", version).execute()
        df = pd.DataFrame(res.data)
        if df.empty and version != "Original":
            return df
        if df.empty:
            # maybe pre-migration data with no version column
            res2 = client.table("v_budget_vs_actual").select("*").eq("fiscal_year", fiscal_year).execute()
            return pd.DataFrame(res2.data)
        return df
    except Exception:
        res = q.execute()
        return pd.DataFrame(res.data)


@st.cache_data(ttl=120)
def get_dashboard_summary(fiscal_year: int) -> dict:
    client = get_client()
    res = client.table("v_dashboard_summary").select("*").eq("fiscal_year", fiscal_year).execute()
    if res.data:
        return res.data[0]
    return {"total_budget": 0, "total_spent": 0, "total_planned": 0, "total_remaining": 0}


def upsert_budget_allocation(category_code, fiscal_year, month, amount, user_id, version="Original"):
    client = get_authed_client()
    client.table("budget_allocations").upsert({
        "category_code": category_code,
        "fiscal_year": fiscal_year,
        "month": month,
        "budgeted_amount": amount,
        "version": version,
        "updated_by": user_id,
    }, on_conflict="category_code,fiscal_year,month,version").execute()
    st.cache_data.clear()


def copy_budget_year(from_year, to_year) -> int:
    """Seed a new fiscal year from an existing one. Returns rows copied."""
    client = get_authed_client()
    res = client.rpc("copy_budget_year", {"p_from_year": from_year, "p_to_year": to_year}).execute()
    st.cache_data.clear()
    return res.data if isinstance(res.data, int) else 0


@st.cache_data(ttl=120)
def get_budget_years() -> list:
    client = get_client()
    res = client.table("budget_allocations").select("fiscal_year").execute()
    years = sorted({r["fiscal_year"] for r in res.data}, reverse=True)
    return years


@st.cache_data(ttl=60)
def get_budget_versions(fiscal_year: int) -> list:
    client = get_client()
    try:
        res = client.rpc("budget_versions", {"p_year": fiscal_year}).execute()
        vers = [r["version"] for r in res.data] if res.data else []
        return vers or ["Original"]
    except Exception:
        return ["Original"]


def create_budget_revision(fiscal_year, source_version, new_version, from_month) -> int:
    client = get_authed_client()
    res = client.rpc("create_budget_revision", {
        "p_year": fiscal_year, "p_source_version": source_version,
        "p_new_version": new_version, "p_from_month": from_month,
    }).execute()
    st.cache_data.clear()
    return res.data if isinstance(res.data, int) else 0


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def get_expenses(status=None, category_code=None, date_from=None, date_to=None, limit=1000) -> pd.DataFrame:
    client = get_client()
    q = client.table("expenses").select("*").is_("deleted_at", "null")
    if status:
        q = q.eq("status", status)
    if category_code:
        q = q.eq("category_code", category_code)
    if date_from:
        q = q.gte("txn_date", str(date_from))
    if date_to:
        q = q.lte("txn_date", str(date_to))
    res = q.order("txn_date", desc=True).limit(limit).execute()
    return pd.DataFrame(res.data)


def expense_exists(category_code, txn_date, amount, vendor, invoice_number) -> bool:
    client = get_client()
    res = client.rpc("expense_exists", {
        "p_category": category_code, "p_date": str(txn_date), "p_amount": amount,
        "p_vendor": vendor or "", "p_invoice": invoice_number or "",
    }).execute()
    return bool(res.data)


def add_expense(category_code, vendor, invoice_number, txn_date, amount, status, notes,
                user_id, device=None):
    client = get_authed_client()
    try:
        client.table("expenses").insert({
            "category_code": category_code,
            "vendor": vendor,
            "invoice_number": invoice_number,
            "txn_date": str(txn_date),
            "amount": amount,
            "status": status,
            "notes": notes,
            "created_by": user_id,
            "updated_by": user_id,
            "created_device": device,
            "updated_device": device,
        }).execute()
    except Exception as e:
        msg = str(e).lower()
        if "uq_expenses_no_dupes" in msg or "duplicate key" in msg or "unique" in msg:
            raise ValueError("DUPLICATE") from e
        raise
    add_vendor_if_new(vendor)
    log_activity(user_id, "add_expense", device, f"{category_code} ${amount}")
    st.cache_data.clear()


def update_expense(expense_id, fields: dict, user_id, device=None):
    client = get_authed_client()
    fields["updated_by"] = user_id
    fields["updated_device"] = device
    client.table("expenses").update(fields).eq("id", expense_id).execute()
    log_activity(user_id, "edit_expense", device, str(expense_id))
    st.cache_data.clear()


def soft_delete_expense(expense_id, user_id, device=None):
    client = get_authed_client()
    client.table("expenses").update({
        "deleted_at": pd.Timestamp.utcnow().isoformat(),
        "updated_by": user_id,
        "updated_device": device,
    }).eq("id", expense_id).execute()
    log_activity(user_id, "delete_expense", device, str(expense_id))
    st.cache_data.clear()


def hard_delete_expense(expense_id):
    """Admin only - actually removes the row (RLS blocks non-admins)."""
    client = get_authed_client()
    client.table("expenses").delete().eq("id", expense_id).execute()
    st.cache_data.clear()


@st.cache_data(ttl=30)
def get_deleted_expenses(limit=200) -> pd.DataFrame:
    client = get_client()
    res = client.table("expenses").select("*").not_.is_("deleted_at", "null") \
        .order("deleted_at", desc=True).limit(limit).execute()
    return pd.DataFrame(res.data)


def restore_expense(expense_id):
    client = get_authed_client()
    client.rpc("restore_expense", {"p_expense_id": expense_id}).execute()
    st.cache_data.clear()


# ---------------------------------------------------------------------------
# User management (simple username/password table)
# ---------------------------------------------------------------------------

def list_app_users() -> pd.DataFrame:
    client = get_client()
    res = client.rpc("list_app_users", {}).execute()
    return pd.DataFrame(res.data)


def upsert_app_user(username, password, full_name, role):
    client = get_authed_client()
    client.rpc("upsert_app_user", {
        "p_username": username, "p_password": password,
        "p_full_name": full_name, "p_role": role,
    }).execute()


def update_user_role(username, role):
    client = get_authed_client()
    client.rpc("update_user_role", {"p_username": username, "p_role": role}).execute()


def delete_app_user(username):
    client = get_authed_client()
    client.rpc("delete_app_user", {"p_username": username}).execute()


# ---------------------------------------------------------------------------
# Activity / device tracking
# ---------------------------------------------------------------------------

def log_activity(username, action, device, detail=""):
    try:
        client = get_authed_client()
        client.rpc("log_activity", {
            "p_username": username, "p_action": action,
            "p_device": device or "", "p_detail": detail or "",
        }).execute()
    except Exception:
        pass  # never let logging break the main action


def get_recent_activity(limit=100) -> pd.DataFrame:
    client = get_client()
    res = client.rpc("recent_activity", {"p_limit": limit}).execute()
    return pd.DataFrame(res.data)


# ---------------------------------------------------------------------------
# Notes & history
# ---------------------------------------------------------------------------

def get_expense_notes(expense_id) -> pd.DataFrame:
    client = get_client()
    res = client.table("expense_notes").select("*") \
        .eq("expense_id", expense_id).order("created_at", desc=True).execute()
    return pd.DataFrame(res.data)


def add_expense_note(expense_id, note, user_id):
    client = get_authed_client()
    client.table("expense_notes").insert({
        "expense_id": expense_id,
        "note": note,
        "created_by": user_id,
    }).execute()


def get_expense_history(expense_id) -> pd.DataFrame:
    client = get_client()
    res = client.table("expense_audit_log").select("*") \
        .eq("expense_id", expense_id).order("changed_at", desc=True).execute()
    return pd.DataFrame(res.data)
