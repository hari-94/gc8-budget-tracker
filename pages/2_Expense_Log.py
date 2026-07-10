import streamlit as st
import pandas as pd
from datetime import date, datetime

from utils.auth import require_login, logout_button, can_edit, is_admin, current_username
from utils.db import (
    get_categories, get_expenses, update_expense, soft_delete_expense,
    hard_delete_expense, get_expense_notes, add_expense_note, get_expense_history
)

st.set_page_config(page_title="Expense Log", page_icon="📋", layout="wide")
require_login()
logout_button()

st.title("📋 Expense Log")

categories = get_categories()
cat_name_map = dict(zip(categories["code"], categories["name"])) if not categories.empty else {}

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
with st.expander("Filters", expanded=True):
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        status_filter = st.selectbox("Status", options=["All", "paid", "pending", "planned"])
    with f2:
        cat_filter_label = st.selectbox(
            "Category", options=["All"] + list((categories["name"] + "  (" + categories["code"] + ")") if not categories.empty else [])
        )
    with f3:
        date_from = st.date_input("From", value=None)
    with f4:
        date_to = st.date_input("To", value=None)

expenses = get_expenses(
    status=None if status_filter == "All" else status_filter,
    category_code=None if cat_filter_label == "All" else cat_filter_label.split("(")[-1].rstrip(")"),
    date_from=date_from if date_from else None,
    date_to=date_to if date_to else None,
    limit=2000,
)

if expenses.empty:
    st.info("No expenses match these filters.")
    st.stop()

expenses["category"] = expenses["category_code"].map(cat_name_map).fillna(expenses["category_code"])
st.caption(f"{len(expenses)} transactions · total ${expenses['amount'].sum():,.2f}")

st.dataframe(
    expenses[["txn_date", "category", "vendor", "invoice_number", "amount", "status", "notes"]].rename(columns={
        "txn_date": "Date", "category": "Category", "vendor": "Vendor",
        "invoice_number": "Invoice #", "amount": "Amount", "status": "Status", "notes": "Notes"
    }),
    use_container_width=True, hide_index=True, height=350,
    column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")}
)

st.divider()

# ---------------------------------------------------------------------------
# Select one transaction to inspect / edit / annotate
# ---------------------------------------------------------------------------
st.subheader("Line Item Detail")

expenses["label"] = (
    expenses["txn_date"].astype(str) + " · " + expenses["category"] + " · " +
    expenses["vendor"].fillna("") + " · $" + expenses["amount"].astype(str)
)
selected_label = st.selectbox("Select a transaction", options=expenses["label"])
row = expenses[expenses["label"] == selected_label].iloc[0]
expense_id = row["id"]

tab_edit, tab_notes, tab_history = st.tabs(["✏️ Edit", "💬 Notes", "🕒 History"])

with tab_edit:
    if not can_edit():
        st.info("You have view-only access.")
        st.write(row[["txn_date", "category", "vendor", "invoice_number", "amount", "status", "notes"]])
    else:
        with st.form(f"edit_form_{expense_id}"):
            c1, c2 = st.columns(2)
            with c1:
                new_amount = st.number_input("Amount", value=float(row["amount"]), min_value=0.0, format="%.2f")
                new_status = st.selectbox("Status", options=["paid", "pending", "planned"],
                                           index=["paid", "pending", "planned"].index(row["status"]))
                new_vendor = st.text_input("Vendor", value=row.get("vendor") or "")
            with c2:
                new_date = st.date_input("Date", value=pd.to_datetime(row["txn_date"]).date())
                new_invoice = st.text_input("Invoice #", value=row.get("invoice_number") or "")
            new_notes = st.text_area("Quick note (single field)", value=row.get("notes") or "")

            save_col, delete_col = st.columns([3, 1])
            with save_col:
                save = st.form_submit_button("Save Changes", type="primary", use_container_width=True)
            with delete_col:
                delete = st.form_submit_button("🗑 Delete", use_container_width=True)

            if save:
                update_expense(expense_id, {
                    "amount": new_amount, "status": new_status, "vendor": new_vendor,
                    "txn_date": str(new_date), "invoice_number": new_invoice, "notes": new_notes,
                }, current_username())
                st.success("Updated.")
                st.rerun()

            if delete:
                soft_delete_expense(expense_id, current_username())
                st.success("Deleted (recoverable by an admin via the audit log).")
                st.rerun()

with tab_notes:
    st.caption("Add running commentary on this line item — e.g. why an amount changed, dispute status, approval context.")
    existing_notes = get_expense_notes(expense_id)
    if can_edit():
        new_note = st.text_area("Add a note", key=f"note_{expense_id}")
        if st.button("Post Note", key=f"post_{expense_id}"):
            if new_note.strip():
                add_expense_note(expense_id, new_note.strip(), current_username())
                st.rerun()
    if not existing_notes.empty:
        for _, n in existing_notes.iterrows():
            author = n.get("created_by") or "Someone"
            when = pd.to_datetime(n["created_at"]).strftime("%b %d, %Y %I:%M %p")
            st.markdown(f"**{author}** · _{when}_")
            st.write(n["note"])
            st.divider()
    else:
        st.caption("No notes yet.")

with tab_history:
    st.caption("Automatic audit trail — every insert, edit, and delete on this line item.")
    hist = get_expense_history(expense_id)
    if not hist.empty:
        for _, h in hist.iterrows():
            when = pd.to_datetime(h["changed_at"]).strftime("%b %d, %Y %I:%M %p")
            st.markdown(f"**{h['action'].upper()}** · _{when}_")
            if h["action"] == "update":
                old, new = h.get("old_data") or {}, h.get("new_data") or {}
                changed = {k: (old.get(k), new.get(k)) for k in new if old.get(k) != new.get(k) and k != "updated_at"}
                for field, (before, after) in changed.items():
                    st.write(f"- **{field}**: `{before}` → `{after}`")
            st.divider()
    else:
        st.caption("No history yet.")

if is_admin():
    with st.expander("⚠️ Admin: permanently delete this record"):
        st.warning("This bypasses soft-delete and cannot be undone.")
        if st.button("Permanently delete", key=f"hard_delete_{expense_id}"):
            hard_delete_expense(expense_id)
            st.success("Permanently deleted.")
            st.rerun()
