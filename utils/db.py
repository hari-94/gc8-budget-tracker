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
def get_categories() -> pd.DataFrame:
    client = get_client()
    res = client.table("categories").select("*").eq("is_active", True).order("code").execute()
    return pd.DataFrame(res.data)


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


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120)
def get_budget_vs_actual(fiscal_year: int) -> pd.DataFrame:
    client = get_client()
    res = client.table("v_budget_vs_actual").select("*").eq("fiscal_year", fiscal_year).execute()
    return pd.DataFrame(res.data)


@st.cache_data(ttl=120)
def get_dashboard_summary(fiscal_year: int) -> dict:
    client = get_client()
    res = client.table("v_dashboard_summary").select("*").eq("fiscal_year", fiscal_year).execute()
    if res.data:
        return res.data[0]
    return {"total_budget": 0, "total_spent": 0, "total_planned": 0, "total_remaining": 0}


def upsert_budget_allocation(category_code, fiscal_year, month, amount, user_id):
    client = get_authed_client()
    client.table("budget_allocations").upsert({
        "category_code": category_code,
        "fiscal_year": fiscal_year,
        "month": month,
        "budgeted_amount": amount,
        "updated_by": user_id,
    }, on_conflict="category_code,fiscal_year,month").execute()


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


def add_expense(category_code, vendor, invoice_number, txn_date, amount, status, notes, building, user_id):
    client = get_authed_client()
    client.table("expenses").insert({
        "category_code": category_code,
        "vendor": vendor,
        "invoice_number": invoice_number,
        "txn_date": str(txn_date),
        "amount": amount,
        "status": status,
        "notes": notes,
        "building": building,
        "created_by": user_id,
        "updated_by": user_id,
    }).execute()
    add_vendor_if_new(vendor)
    st.cache_data.clear()


def update_expense(expense_id, fields: dict, user_id):
    client = get_authed_client()
    fields["updated_by"] = user_id
    client.table("expenses").update(fields).eq("id", expense_id).execute()
    st.cache_data.clear()


def soft_delete_expense(expense_id, user_id):
    client = get_authed_client()
    client.table("expenses").update({
        "deleted_at": pd.Timestamp.utcnow().isoformat(),
        "updated_by": user_id,
    }).eq("id", expense_id).execute()
    st.cache_data.clear()


def hard_delete_expense(expense_id):
    """Admin only - actually removes the row (RLS blocks non-admins)."""
    client = get_authed_client()
    client.table("expenses").delete().eq("id", expense_id).execute()
    st.cache_data.clear()


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
