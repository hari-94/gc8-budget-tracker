import streamlit as st
from datetime import date

from utils.auth import require_login, logout_button, can_edit
from utils.db import get_categories, get_vendors, add_expense

st.set_page_config(page_title="Add Expense", page_icon="📝", layout="wide")
require_login()
logout_button()

st.title("📝 Add an Expense")

if not can_edit():
    st.warning("Your account is a **viewer** — ask an admin to upgrade your role to add expenses.")
    st.stop()

categories = get_categories()
if categories.empty:
    st.error("No categories found. Ask an admin to seed the chart of accounts.")
    st.stop()

expense_cats = categories[categories["type"] == "expense"]
cat_options = dict(zip(
    expense_cats["name"] + "  (" + expense_cats["code"] + ")",
    expense_cats["code"]
))

vendors = get_vendors()

st.caption("Use **Paid** for money already spent, **Pending** for an invoice received but not yet paid, "
           "and **Planned** for an upcoming expense you want to budget for ahead of time.")

with st.form("add_expense_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        cat_label = st.selectbox("Category", options=list(cat_options.keys()))
        vendor = st.selectbox("Vendor", options=["(new vendor)"] + vendors)
        if vendor == "(new vendor)":
            vendor = st.text_input("New vendor name")
        invoice_number = st.text_input("Invoice # (optional)")
    with col2:
        txn_date = st.date_input("Date", value=date.today())
        amount = st.number_input("Amount ($)", min_value=0.0, step=1.0, format="%.2f")
        status = st.selectbox("Status", options=["paid", "pending", "planned"],
                               format_func=lambda s: s.capitalize())
        building = st.selectbox("Building (optional)", options=["", "B1", "B2", "B3"])

    notes = st.text_area("Notes (optional)")

    submitted = st.form_submit_button("Add Expense", type="primary", use_container_width=True)

    if submitted:
        if amount <= 0:
            st.error("Amount must be greater than 0.")
        elif not cat_label:
            st.error("Please choose a category.")
        else:
            add_expense(
                category_code=cat_options[cat_label],
                vendor=vendor,
                invoice_number=invoice_number,
                txn_date=txn_date,
                amount=amount,
                status=status,
                notes=notes,
                building=building or None,
                user_id=st.session_state["user"].id,
            )
            st.success(f"Added ${amount:,.2f} — {cat_label} on {txn_date}")
            st.balloons()
