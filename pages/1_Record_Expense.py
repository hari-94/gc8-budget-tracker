import streamlit as st
import time
from datetime import date

from utils.auth import require_login, logout_button, can_edit, current_username
from utils.theme import inject_theme, section_label, GREEN, INK_FAINT
from utils.helpers import get_device
from utils.db import (get_categories, get_vendors, add_expense, expense_exists,
                      delete_vendor, vendor_usage_count)

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


def success_animation(message):
    """Professional circular spinner that resolves into a green tick."""
    ph = st.empty()
    ph.markdown(f"""
    <style>
    @keyframes gc8spin {{ to {{ transform: rotate(360deg); }} }}
    @keyframes gc8pop {{ 0% {{ transform: scale(0.4); opacity:0; }}
                         60% {{ transform: scale(1.15); }} 100% {{ transform: scale(1); opacity:1; }} }}
    .gc8-ring {{ width:56px; height:56px; border-radius:50%;
      border:4px solid {GREEN}22; border-top-color:{GREEN};
      animation: gc8spin 0.7s linear infinite; margin:0 auto; }}
    .gc8-check {{ width:56px; height:56px; border-radius:50%; background:{GREEN};
      display:flex; align-items:center; justify-content:center; margin:0 auto;
      animation: gc8pop 0.35s ease-out; }}
    </style>
    <div style="text-align:center; padding:1rem 0;">
      <div class="gc8-ring"></div>
      <div style="color:{INK_FAINT}; font-size:0.9rem; margin-top:0.75rem;">Saving…</div>
    </div>
    """, unsafe_allow_html=True)
    time.sleep(0.9)
    ph.markdown(f"""
    <div style="text-align:center; padding:1rem 0;">
      <div class="gc8-check">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none">
          <path d="M5 13l4 4L19 7" stroke="white" stroke-width="2.5"
                stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div style="color:{GREEN}; font-weight:600; font-size:0.95rem; margin-top:0.75rem;">{message}</div>
    </div>
    """, unsafe_allow_html=True)
    time.sleep(1.1)
    ph.empty()


st.markdown(
    "Record money already spent, an invoice awaiting payment, or an upcoming cost "
    "you want to reserve budget for."
)
st.write("")

# Each successful save bumps this counter, which is appended to every input's
# key. New keys => Streamlit treats the inputs as brand-new empty widgets,
# reliably clearing the form.
if st.session_state.pop("clear_form", False):
    st.session_state["form_seq"] = st.session_state.get("form_seq", 0) + 1
    success_animation(st.session_state.pop("saved_msg", "Recorded"))

_seq = st.session_state.get("form_seq", 0)

col1, col2 = st.columns(2)
with col1:
    cat_label = st.selectbox("Category", options=list(cat_options.keys()),
                             index=None, placeholder="Choose a category", key=f"f_cat_{_seq}")
    add_new_vendor = st.toggle("Add a vendor that isn't in the list yet", key=f"f_newvendor_{_seq}")
    if add_new_vendor:
        vendor = st.text_input("New vendor name", placeholder="Type the vendor's name",
                               key=f"f_vendor_new_{_seq}")
    else:
        if vendors:
            vendor = st.selectbox("Vendor", options=vendors, index=None,
                                  placeholder="Choose a vendor", key=f"f_vendor_pick_{_seq}")
        else:
            vendor = None
            st.caption("No vendors on file yet — switch on the toggle above to add the first one.")
    invoice_number = st.text_input("Invoice number", placeholder="Leave blank for NA",
                                   key=f"f_invoice_{_seq}")
with col2:
    txn_date = st.date_input("Date", value=date.today(), key=f"f_date_{_seq}")
    amount = st.number_input("Amount", min_value=0.0, step=1.0, format="%.2f", key=f"f_amount_{_seq}")
    status = st.selectbox(
        "Status", options=["paid", "pending", "planned"],
        format_func=lambda s: {"paid": "Paid", "pending": "Pending payment",
                               "planned": "Planned / upcoming"}[s],
        key=f"f_status_{_seq}",
    )

notes = st.text_area("Notes", placeholder="Optional context — approval, dispute, reason for the cost",
                     key=f"f_notes_{_seq}")

# Normalize invoice to NA when blank
inv_clean = (invoice_number or "").strip() or "NA"

st.write("")
force = st.session_state.get("force_dup", False)
label = "Record anyway" if force else "Record expense"
if st.button(label, type="primary", use_container_width=True):
    code = cat_options.get(cat_label)
    if amount <= 0:
        st.error("Enter an amount greater than zero.")
    elif not cat_label:
        st.error("Choose a category.")
    elif not vendor:
        st.error("Choose an existing vendor, or switch on the toggle to add a new one.")
    else:
        # Duplicate guard
        dup = expense_exists(code, txn_date, amount, vendor, inv_clean)
        if dup and not force:
            st.session_state["force_dup"] = True
            st.warning(
                f"This looks like a duplicate — a **{cat_label}** expense of "
                f"**${amount:,.2f}** to **{vendor}** on **{txn_date}** "
                f"(invoice {inv_clean}) is already recorded. "
                "If it's genuinely a separate charge, press **Record anyway**."
            )
            st.stop()
        try:
            add_expense(
                category_code=code, vendor=vendor.strip(),
                invoice_number=inv_clean, txn_date=txn_date, amount=amount,
                status=status, notes=notes, user_id=current_username(), device=get_device(),
            )
        except ValueError:
            # Blocked by the database dedup guard
            st.session_state["force_dup"] = False
            st.error(
                "This exact expense is already recorded, so it wasn't added again. "
                "If it's genuinely a separate charge, change the invoice number to tell them apart."
            )
            st.stop()
        st.session_state["force_dup"] = False
        st.session_state["clear_form"] = True
        st.session_state["saved_msg"] = f"Recorded ${amount:,.2f}"
        st.rerun()

# ---------------------------------------------------------------------------
# Manage vendors — remove ones added by mistake or no longer used
# ---------------------------------------------------------------------------
st.divider()
with st.expander("Manage vendors"):
    st.caption("Remove a vendor from the picker. This does not change or delete any "
               "expenses already recorded against that vendor.")
    if not vendors:
        st.caption("No vendors on file yet.")
    else:
        vc1, vc2 = st.columns([3, 1])
        with vc1:
            to_remove = st.selectbox("Vendor to remove", options=vendors,
                                     index=None, placeholder="Choose a vendor",
                                     key="vendor_remove")
        with vc2:
            st.write("")
            st.write("")
            if st.button("Remove", use_container_width=True, disabled=not to_remove):
                used = vendor_usage_count(to_remove)
                if used > 0:
                    st.session_state["vendor_pending"] = to_remove
                    st.session_state["vendor_used"] = used
                else:
                    delete_vendor(to_remove)
                    st.success(f"Removed “{to_remove}”.")
                    st.rerun()

        # Confirmation when the vendor is still referenced by expenses
        pending = st.session_state.get("vendor_pending")
        if pending:
            st.warning(
                f"“{pending}” is used by {st.session_state.get('vendor_used', 0)} existing "
                f"expense(s). Removing it only takes it out of the picker — those expenses keep "
                f"their vendor name. Remove it anyway?"
            )
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("Yes, remove it", type="primary", use_container_width=True):
                    delete_vendor(pending)
                    st.session_state.pop("vendor_pending", None)
                    st.session_state.pop("vendor_used", None)
                    st.success(f"Removed “{pending}”.")
                    st.rerun()
            with cc2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.pop("vendor_pending", None)
                    st.session_state.pop("vendor_used", None)
                    st.rerun()
