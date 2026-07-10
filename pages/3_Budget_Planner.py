import streamlit as st
import pandas as pd
from datetime import date

from utils.auth import require_login, logout_button, can_edit, current_username
from utils.theme import inject_theme, section_label, INK_FAINT
from utils.db import (
    get_categories, get_budget_vs_actual, upsert_budget_allocation,
    get_budget_years, copy_budget_year,
)


section_label("Planning")
st.title("Budget Planner")
st.caption("Set or adjust the monthly budgeted amount for each category.")

categories = get_categories()
if categories.empty:
    st.error("No categories found.")
    st.stop()

# ---------------------------------------------------------------------------
# Fiscal year picker — includes existing years plus the option to start a new one
# ---------------------------------------------------------------------------
existing_years = get_budget_years()
this_year = date.today().year
year_options = sorted(set(existing_years + [this_year, this_year + 1]), reverse=True)

top_l, top_r = st.columns([1, 2])
with top_l:
    fiscal_year = st.selectbox("Fiscal year", options=year_options, index=0)

has_data = fiscal_year in existing_years

# If the chosen year is empty, offer to seed it from a previous year
if not has_data and can_edit():
    with top_r:
        st.write("")
        prior_years = [y for y in existing_years if y < fiscal_year] or existing_years
        default_source = max(prior_years) if prior_years else None
        st.info(f"No budget exists for {fiscal_year} yet.")
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            source_year = st.selectbox("Start from", options=prior_years,
                                       index=0 if prior_years else None,
                                       key="seed_source",
                                       help="Copies that year's monthly budget into the new year so you can adjust it.")
        with sc2:
            st.write("")
            if st.button("Create year", type="primary", use_container_width=True):
                n = copy_budget_year(source_year, fiscal_year)
                st.success(f"Created {fiscal_year} from {source_year} ({n} lines). Adjust below as needed.")
                st.rerun()

bva = get_budget_vs_actual(fiscal_year)
month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

expense_cats = categories[categories["type"] == "expense"].sort_values("name")
cat_label_map = dict(zip(expense_cats["name"] + "  (" + expense_cats["code"] + ")", expense_cats["code"]))

st.divider()

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
                                                  step=100.0, key=f"m_{fiscal_year}_{code}_{m}")
        total = sum(new_values.values())
        st.metric("Annual total", f"${total:,.2f}")
        submitted = st.form_submit_button("Save budget", type="primary", use_container_width=True)
        if submitted:
            for m, amt in new_values.items():
                upsert_budget_allocation(code, fiscal_year, m, amt, current_username())
            st.cache_data.clear()
            st.success("Budget saved.")
            st.rerun()

st.divider()
st.subheader("All categories — annual totals")
if not bva.empty:
    summary = bva.groupby(["code", "name"], as_index=False)["budgeted_amount"].sum() \
        .sort_values("budgeted_amount", ascending=False)
    st.dataframe(summary.rename(columns={"code": "Code", "name": "Category", "budgeted_amount": "Annual budget"}),
                 hide_index=True, use_container_width=True,
                 column_config={"Annual budget": st.column_config.NumberColumn(format="$%.2f")})
else:
    st.caption("No budget lines for this year yet.")
