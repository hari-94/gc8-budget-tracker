import streamlit as st
import pandas as pd
from datetime import date

from utils.auth import require_login, logout_button, can_edit, current_username
from utils.theme import inject_theme, section_label, INK_FAINT, GREEN, AMBER
from utils.db import (
    get_categories, get_budget_vs_actual, upsert_budget_allocation,
    get_budget_years, copy_budget_year, get_budget_versions, create_budget_revision,
)

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

section_label("Planning")
st.title("Budget Planner")
st.caption("Set the yearly budget, or create a mid-year revision based on how the year is tracking.")

categories = get_categories()
if categories.empty:
    st.error("No categories found.")
    st.stop()

# ---------------------------------------------------------------------------
# Year picker — defaults to the CURRENT year
# ---------------------------------------------------------------------------
existing_years = get_budget_years()
this_year = date.today().year
future = list(range(this_year - 1, this_year + 6))
year_options = sorted(set(existing_years + future), reverse=True)
default_idx = year_options.index(this_year) if this_year in year_options else 0

c_year, c_ver = st.columns([1, 1])
with c_year:
    fiscal_year = st.selectbox("Fiscal year", options=year_options, index=default_idx)

has_data = fiscal_year in existing_years
versions = get_budget_versions(fiscal_year) if has_data else ["Original"]

with c_ver:
    active_version = st.selectbox("Budget version", options=versions,
                                  help="'Original' is the plan set at the start of the year. "
                                       "Mid-year revisions appear here once created.")

# ---------------------------------------------------------------------------
# Seed a brand-new year from a previous one
# ---------------------------------------------------------------------------
if not has_data and can_edit():
    st.info(f"No budget exists for {fiscal_year} yet.")
    prior_years = [y for y in existing_years if y < fiscal_year] or existing_years
    if prior_years:
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            source_year = st.selectbox("Start from", options=prior_years, index=0,
                                       help="Copies that year's Original budget into the new year.")
        with sc2:
            st.write("")
            if st.button("Create year", type="primary", use_container_width=True):
                n = copy_budget_year(source_year, fiscal_year)
                st.success(f"Created {fiscal_year} from {source_year} ({n} lines).")
                st.rerun()
    st.stop()

bva = get_budget_vs_actual(fiscal_year, active_version)

# ---------------------------------------------------------------------------
# Mid-year rebudget — create a revision
# ---------------------------------------------------------------------------
if can_edit():
    with st.expander("Create a mid-year revision", expanded=False):
        st.markdown(
            "A revision keeps your **Original** budget intact for comparison and creates a new "
            "version alongside it. Months that have already passed are locked to **actual spend**; "
            "the remaining months are pre-filled from the version you revise, and you adjust from there."
        )
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            src = st.selectbox("Base it on", options=versions, key="rev_src")
        with rc2:
            default_name = f"Revised {MONTHS[date.today().month - 1]} {fiscal_year}" \
                if fiscal_year == this_year else f"Revised {fiscal_year}"
            new_name = st.text_input("Revision name", value=default_name)
        with rc3:
            # Default the "revise from" month to the current month (or July for a past/future year)
            default_from = date.today().month if fiscal_year == this_year else 7
            from_month = st.selectbox("Lock actuals through", options=list(range(1, 13)),
                                      index=default_from - 2 if default_from > 1 else 0,
                                      format_func=lambda m: MONTHS[m - 1],
                                      help="Months up to and including this are set to actual spend; "
                                           "later months stay adjustable.")
        st.caption(f"Months Jan–{MONTHS[from_month - 1]} will be locked to actuals; "
                   f"{MONTHS[from_month] if from_month < 12 else '—'}"
                   f"{'–Dec' if from_month < 12 else ''} stay editable.")
        if st.button("Create revision", type="primary"):
            if not new_name.strip():
                st.error("Give the revision a name.")
            elif new_name.strip() in versions:
                st.error("A version with that name already exists — pick another name.")
            else:
                # from_month is inclusive for locking; the RPC locks months < p_from_month,
                # so pass from_month + 1 to lock through the selected month.
                n = create_budget_revision(fiscal_year, src, new_name.strip(), from_month + 1)
                st.success(f"Created “{new_name.strip()}” ({n} lines). Select it above to review and adjust.")
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Category editor for the selected version
# ---------------------------------------------------------------------------
expense_cats = categories[categories["type"] == "expense"].sort_values("name")
cat_label_map = dict(zip(expense_cats["name"] + "  (" + expense_cats["code"] + ")", expense_cats["code"]))

cat_label = st.selectbox("Category", options=list(cat_label_map.keys()))
code = cat_label_map[cat_label]

existing = bva[bva["code"] == code] if not bva.empty else pd.DataFrame()
month_budget = {m: 0.0 for m in range(1, 13)}
month_spent = {m: 0.0 for m in range(1, 13)}
for _, r in existing.iterrows():
    month_budget[int(r["month"])] = float(r["budgeted_amount"])
    month_spent[int(r["month"])] = float(r.get("spent_amount") or 0)

st.subheader(f"{cat_label} — {fiscal_year} · {active_version}")

if not can_edit():
    st.info("You have view-only access.")
    df = pd.DataFrame({"Month": MONTHS,
                       "Budgeted": [month_budget[m] for m in range(1, 13)],
                       "Actual": [month_spent[m] for m in range(1, 13)]})
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"Budgeted": st.column_config.NumberColumn(format="$%.2f"),
                                "Actual": st.column_config.NumberColumn(format="$%.2f")})
else:
    with st.form("budget_form"):
        cols = st.columns(4)
        new_values = {}
        for i, m in enumerate(range(1, 13)):
            with cols[i % 4]:
                spent_hint = f"spent ${month_spent[m]:,.0f}" if month_spent[m] else ""
                new_values[m] = st.number_input(f"{MONTHS[m-1]}", value=month_budget[m],
                                                step=100.0, key=f"m_{fiscal_year}_{active_version}_{code}_{m}",
                                                help=spent_hint or None)
        total = sum(new_values.values())
        total_spent = sum(month_spent.values())
        mc1, mc2 = st.columns(2)
        mc1.metric("Annual budget", f"${total:,.2f}")
        mc2.metric("Actual so far", f"${total_spent:,.2f}")
        submitted = st.form_submit_button("Save budget", type="primary", use_container_width=True)
        if submitted:
            for m, amt in new_values.items():
                upsert_budget_allocation(code, fiscal_year, m, amt, current_username(),
                                         version=active_version)
            st.cache_data.clear()
            st.success("Saved.")
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# All categories — annual totals for the selected version
# ---------------------------------------------------------------------------
st.subheader(f"All categories — {active_version}")
if not bva.empty:
    summary = bva.groupby(["code", "name"], as_index=False).agg(
        budget=("budgeted_amount", "sum"), actual=("spent_amount", "sum"))
    summary["variance"] = summary["budget"] - summary["actual"]
    summary = summary.sort_values("budget", ascending=False)
    st.dataframe(
        summary.rename(columns={"code": "Code", "name": "Category",
                                "budget": "Budget", "actual": "Actual", "variance": "Variance"}),
        hide_index=True, use_container_width=True,
        column_config={
            "Budget": st.column_config.NumberColumn(format="$%.2f"),
            "Actual": st.column_config.NumberColumn(format="$%.2f"),
            "Variance": st.column_config.NumberColumn(format="$%.2f"),
        },
    )
else:
    st.caption("No budget lines for this version yet.")
