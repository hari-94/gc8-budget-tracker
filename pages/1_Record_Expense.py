import streamlit as st
from datetime import date

from utils.auth import require_login, logout_button, can_edit, current_username
from utils.theme import inject_theme, section_label, INK_FAINT
from utils.db import get_categories, get_vendors, add_expense


section_label("Entry")
st.title("Record an Expense")

if not can_edit():
    st.warning("Your account has view-only access. Ask an administrator to enable editing.")
    st.stop()

categories = get_categories()
if categories.empty:
    st.error("No categories found. Ask an administrator to set up the chart of accounts.")
    st.stop()

expense_cats = categories[categories["type"] == "expense"]
cat_options = dict(zip(
    expense_cats["name"] + "  (" + expense_cats["code"] + ")",
    expense_cats["code"]
))

vendors = sorted(get_vendors())

st.markdown(
    "Record money already spent, an invoice awaiting payment, or an upcoming cost "
    "you want to reserve budget for."
)
st.write("")

col1, col2 = st.columns(2)
with col1:
    cat_label = st.selectbox("Category", options=list(cat_options.keys()))

    # Vendor: pick from the existing list, or toggle on a field for a brand-new one
    add_new_vendor = st.toggle("Add a vendor that isn't in the list yet")
    if add_new_vendor:
        vendor = st.text_input("New vendor name", placeholder="Type the vendor's name")
    else:
        if vendors:
            vendor = st.selectbox("Vendor", options=vendors,
                                  index=None, placeholder="Choose a vendor")
        else:
            vendor = None
            st.caption("No vendors on file yet — switch on the toggle above to add the first one.")

    invoice_number = st.text_input("Invoice number", placeholder="Optional")
with col2:
    txn_date = st.date_input("Date", value=date.today())
    amount = st.number_input("Amount", min_value=0.0, step=1.0, format="%.2f")
    status = st.selectbox(
        "Status", options=["paid", "pending", "planned"],
        format_func=lambda s: {"paid": "Paid", "pending": "Pending payment",
                               "planned": "Planned / upcoming"}[s],
    )

notes = st.text_area("Notes", placeholder="Optional context — approval, dispute, reason for the cost")

st.write("")
if st.button("Record expense", type="primary", use_container_width=True):
    if amount <= 0:
        st.error("Enter an amount greater than zero.")
    elif not cat_label:
        st.error("Choose a category.")
    elif not vendor:
        st.error("Choose an existing vendor, or switch on the toggle to add a new one.")
    else:
        add_expense(
            category_code=cat_options[cat_label],
            vendor=vendor.strip(),
            invoice_number=invoice_number,
            txn_date=txn_date,
            amount=amount,
            status=status,
            notes=notes,
            user_id=current_username(),
        )
        st.success(f"Recorded ${amount:,.2f} for {cat_label} on {txn_date}.")
