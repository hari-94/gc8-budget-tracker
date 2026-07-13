import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from utils.auth import require_login, logout_button, can_edit, current_username
from utils.theme import inject_theme, section_label, style_fig, INK, INK_FAINT, GREEN, AMBER, CLAY, SAND, LINE
from utils.db import (
    get_categories, get_budget_vs_actual, upsert_budget_allocation,
    get_budget_years, copy_budget_year,
)

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

section_label("Planning")
st.title("Budget Planner")
st.caption("Adjust a category by percentage or dollar amount, edit any month directly, and see the change before you save.")

categories = get_categories()
if categories.empty:
    st.error("No categories found.")
    st.stop()

# ---------------------------------------------------------------------------
# Year picker — defaults to CURRENT year
# ---------------------------------------------------------------------------
existing_years = get_budget_years()
this_year = date.today().year
future = list(range(this_year - 1, this_year + 6))
year_options = sorted(set(existing_years + future), reverse=True)
default_idx = year_options.index(this_year) if this_year in year_options else 0

fiscal_year = st.selectbox("Fiscal year", options=year_options, index=default_idx)
has_data = fiscal_year in existing_years

if not has_data and can_edit():
    st.info(f"No budget exists for {fiscal_year} yet.")
    prior_years = [y for y in existing_years if y < fiscal_year] or existing_years
    if prior_years:
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            source_year = st.selectbox("Start from", options=prior_years, index=0)
        with sc2:
            st.write("")
            if st.button("Create year", type="primary", use_container_width=True):
                n = copy_budget_year(source_year, fiscal_year)
                st.success(f"Created {fiscal_year} from {source_year} ({n} lines).")
                st.rerun()
    st.stop()

bva = get_budget_vs_actual(fiscal_year)

# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
expense_cats = categories[categories["type"] == "expense"].sort_values("name")
cat_label_map = dict(zip(expense_cats["name"] + "  (" + expense_cats["code"] + ")", expense_cats["code"]))
cat_label = st.selectbox("Category", options=list(cat_label_map.keys()))
code = cat_label_map[cat_label]

existing = bva[bva["code"] == code] if not bva.empty else pd.DataFrame()
saved_budget = {m: 0.0 for m in range(1, 13)}
month_spent = {m: 0.0 for m in range(1, 13)}
for _, r in existing.iterrows():
    saved_budget[int(r["month"])] = float(r["budgeted_amount"])
    month_spent[int(r["month"])] = float(r.get("spent_amount") or 0)

# ---------------------------------------------------------------------------
# Working copy — the "after" values live in session state, keyed by year+category,
# so switching category/year resets. "before" = saved_budget from the DB.
# ---------------------------------------------------------------------------
wk_key = f"work_{fiscal_year}_{code}"
if st.session_state.get("wk_active") != wk_key:
    st.session_state["wk_active"] = wk_key
    st.session_state["work"] = dict(saved_budget)

work = st.session_state["work"]

if not can_edit():
    st.info("You have view-only access.")
    df = pd.DataFrame({"Month": MONTHS,
                       "Budgeted": [saved_budget[m] for m in range(1, 13)],
                       "Actual": [month_spent[m] for m in range(1, 13)]})
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"Budgeted": st.column_config.NumberColumn(format="$%.2f"),
                                "Actual": st.column_config.NumberColumn(format="$%.2f")})
    st.stop()

# ---------------------------------------------------------------------------
# Bulk adjustment tool: % or fixed $ , applied to chosen months
# ---------------------------------------------------------------------------
st.subheader(f"{cat_label} — {fiscal_year}")

with st.container(border=True):
    st.markdown("**Bulk adjust**")
    a1, a2, a3, a4 = st.columns([1, 1.2, 1.4, 1])
    with a1:
        mode = st.radio("By", options=["Percent", "Dollar"], horizontal=False)
    with a2:
        if mode == "Percent":
            amt = st.number_input("Percentage", value=5.0, step=1.0, format="%.1f",
                                  help="Positive increases, negative decreases. e.g. 5 or -10")
        else:
            amt = st.number_input("Dollar amount", value=100.0, step=50.0, format="%.2f",
                                  help="Added to each selected month. Use a negative to reduce.")
    with a3:
        scope = st.selectbox("Apply to", options=["Remaining months", "Whole year"])
    with a4:
        st.write("")
        st.write("")
        apply_bulk = st.button("Apply to table", use_container_width=True)

    # Which months does the bulk change affect
    current_month = date.today().month
    if scope == "Remaining months" and fiscal_year == this_year:
        affected = list(range(current_month, 13))
    else:
        affected = list(range(1, 13))

    if apply_bulk:
        for m in affected:
            if mode == "Percent":
                work[m] = round(saved_budget[m] * (1 + amt / 100.0), 2)
            else:
                work[m] = round(saved_budget[m] + amt, 2)
        st.session_state["work"] = work
        st.rerun()

# ---------------------------------------------------------------------------
# Editable full-year table  (before vs after)
# ---------------------------------------------------------------------------
st.markdown("**Edit any month directly**, then review the change below.")
editor_df = pd.DataFrame({
    "Month": MONTHS,
    "Current": [saved_budget[m] for m in range(1, 13)],
    "New": [work[m] for m in range(1, 13)],
    "Actual": [month_spent[m] for m in range(1, 13)],
})
edited = st.data_editor(
    editor_df, hide_index=True, use_container_width=True, key=f"editor_{wk_key}",
    height=460,  # fits all 12 month rows + header without an inner scrollbar
    disabled=["Month", "Current", "Actual"],
    column_config={
        "Current": st.column_config.NumberColumn(format="$%.2f", help="Currently saved budget"),
        "New": st.column_config.NumberColumn(format="$%.2f", help="Edit these values"),
        "Actual": st.column_config.NumberColumn(format="$%.2f", help="Actual spend so far"),
    },
)
# Capture manual edits back into the working copy
for i, m in enumerate(range(1, 13)):
    work[m] = float(edited.iloc[i]["New"])
st.session_state["work"] = work

# ---------------------------------------------------------------------------
# Change summary + before/after comparison chart
# ---------------------------------------------------------------------------
before_total = sum(saved_budget.values())
after_total = sum(work.values())
delta = after_total - before_total
pct_change = (delta / before_total * 100) if before_total else 0

st.divider()
section_label("Before vs after")

m1, m2, m3 = st.columns(3)
m1.metric("Current annual", f"${before_total:,.2f}")
arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
color = GREEN if delta > 0 else (CLAY if delta < 0 else INK_FAINT)
m2.metric("New annual", f"${after_total:,.2f}",
          f"{arrow} ${abs(delta):,.2f}  ({pct_change:+.1f}%)",
          delta_color="normal" if delta >= 0 else "inverse")
m3.metric("Net change", f"${delta:,.2f}", delta_color="off")

# Grouped bar: before vs after per month
labels = MONTHS
before_vals = [saved_budget[m] for m in range(1, 13)]
after_vals = [work[m] for m in range(1, 13)]

fig = go.Figure()
fig.add_bar(name="Current", x=labels, y=before_vals,
            marker=dict(color=SAND, line=dict(color=LINE, width=1)),
            hovertemplate="Current: $%{y:,.0f}<extra></extra>")
fig.add_bar(name="New", x=labels, y=after_vals, marker=dict(color=GREEN),
            hovertemplate="New: $%{y:,.0f}<extra></extra>")
# Arrow annotations where a month changed
for i, m in enumerate(range(1, 13)):
    d = work[m] - saved_budget[m]
    if abs(d) > 0.005:
        up = d > 0
        fig.add_annotation(
            x=labels[i], y=max(before_vals[i], after_vals[i]),
            text=("▲" if up else "▼"), showarrow=False, yshift=12,
            font=dict(size=13, color=GREEN if up else CLAY),
        )
fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
fig.update_yaxes(tickprefix="$", tickformat=",.0f")
st.plotly_chart(style_fig(fig, height=340), use_container_width=True,
                config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Save / reset
# ---------------------------------------------------------------------------
sc1, sc2 = st.columns([2, 1])
with sc1:
    if st.button("Save changes", type="primary", use_container_width=True, disabled=abs(delta) < 0.005 and after_vals == before_vals):
        for m in range(1, 13):
            if abs(work[m] - saved_budget[m]) > 0.005:
                upsert_budget_allocation(code, fiscal_year, m, round(work[m], 2), current_username())
        st.cache_data.clear()
        st.success(f"Saved. Annual budget for {cat_label} changed by ${delta:,.2f} ({pct_change:+.1f}%).")
        # refresh working copy from new saved state
        st.session_state.pop("wk_active", None)
        st.rerun()
with sc2:
    if st.button("Reset", use_container_width=True):
        st.session_state["work"] = dict(saved_budget)
        st.rerun()

st.caption("Saved changes flow straight to the Dashboard charts and the totals below.")

st.divider()

# ---------------------------------------------------------------------------
# All categories overview
# ---------------------------------------------------------------------------
st.subheader("All categories — annual totals")
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
    st.caption("No budget lines for this year yet.")
