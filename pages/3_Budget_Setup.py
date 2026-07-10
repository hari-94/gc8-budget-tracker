import streamlit as st
import pandas as pd

from utils.auth import require_login, logout_button, can_edit
from utils.db import get_categories, get_budget_vs_actual, upsert_budget_allocation

st.set_page_config(page_title="Budget Setup", page_icon="💰", layout="wide")
require_login()
logout_button()

st.title("💰 Budget Setup")
st.caption("Set or adjust the monthly budgeted amount for each category.")

fiscal_year = st.selectbox("Fiscal Year", options=[2026, 2025, 2027], index=0)
categories = get_categories()

if categories.empty:
    st.error("No categories found.")
    st.stop()

bva = get_budget_vs_actual(fiscal_year)
month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

expense_cats = categories[categories["type"] == "expense"].sort_values("name")
cat_label_map = dict(zip(expense_cats["name"] + "  (" + expense_cats["code"] + ")", expense_cats["code"]))

cat_label = st.selectbox("Category", options=list(cat_label_map.keys()))
code = cat_label_map[cat_label]

existing = bva[bva["code"] == code] if not bva.empty else pd.DataFrame()
month_amounts = {m: 0.0 for m in range(1, 13)}
for _, r in existing.iterrows():
    month_amounts[int(r["month"])] = float(r["budgeted_amount"])

st.subheader(f"{cat_label} — {fiscal_year}")

if not can_edit():
    st.info("You have view-only access.")
    df = pd.DataFrame({"Month": month_names, "Budgeted": [month_amounts[m] for m in range(1, 13)]})
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"Budgeted": st.column_config.NumberColumn(format="$%.2f")})
else:
    with st.form("budget_form"):
        cols = st.columns(4)
        new_values = {}
        for i, m in enumerate(range(1, 13)):
            with cols[i % 4]:
                new_values[m] = st.number_input(month_names[m-1], value=month_amounts[m],
                                                  min_value=0.0, step=100.0, key=f"m_{code}_{m}")
        total = sum(new_values.values())
        st.metric("Annual Total", f"${total:,.2f}")
        submitted = st.form_submit_button("Save Budget", type="primary", use_container_width=True)
        if submitted:
            for m, amt in new_values.items():
                upsert_budget_allocation(code, fiscal_year, m, amt, st.session_state["user"].id)
            st.cache_data.clear()
            st.success("Budget saved.")
            st.rerun()

st.divider()
st.subheader("All Categories — Annual Totals")
if not bva.empty:
    summary = bva.groupby(["code", "name"], as_index=False)["budgeted_amount"].sum() \
        .sort_values("budgeted_amount", ascending=False)
    st.dataframe(summary.rename(columns={"code": "Code", "name": "Category", "budgeted_amount": "Annual Budget"}),
                 hide_index=True, use_container_width=True,
                 column_config={"Annual Budget": st.column_config.NumberColumn(format="$%.2f")})
