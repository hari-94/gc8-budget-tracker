import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.theme import (
    style_fig, section_label,
    GREEN, AMBER, CLAY, INK, INK_SOFT, INK_FAINT, LINE, SAND, SERIES,
)
from utils.db import get_budget_vs_actual, get_expenses, get_categories

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
from datetime import date
_this_year = date.today().year
_years = sorted({_this_year, _this_year - 1, _this_year + 1, 2025, 2026, 2027}, reverse=True)
_default_idx = _years.index(_this_year) if _this_year in _years else 0

head_l, head_r = st.columns([3, 1])
with head_l:
    section_label("Grand Colorado on Peak 8 · Housekeeping")
    st.title("Budget Overview")
with head_r:
    fiscal_year = st.selectbox("Fiscal year", options=_years, index=_default_idx,
                               label_visibility="collapsed")

# Budget version — lets you measure actuals against the Original plan or a mid-year revision
bva = get_budget_vs_actual(fiscal_year)
exp_bva_all = bva[bva["type"] == "expense"].copy() if not bva.empty else pd.DataFrame()

# Drop archived categories so the dashboard only reflects actively-tracked lines
if not exp_bva_all.empty:
    active_codes = set(get_categories()["code"].tolist())
    exp_bva_all = exp_bva_all[exp_bva_all["code"].isin(active_codes)]

if exp_bva_all.empty:
    st.info("No budget data for this fiscal year yet.")
    st.stop()

# ---------------------------------------------------------------------------
# Filter bar — group + category multi-select, driving everything below
# ---------------------------------------------------------------------------
all_groups = sorted(exp_bva_all["group_name"].dropna().unique().tolist())

with st.container():
    fc1, fc2, fc3 = st.columns([2, 3, 1])
    with fc1:
        sel_groups = st.multiselect("Groups", options=all_groups, default=[],
                                    placeholder="All groups")
    # Categories available depend on the chosen groups
    scope = exp_bva_all if not sel_groups else exp_bva_all[exp_bva_all["group_name"].isin(sel_groups)]
    cat_choices = (scope[["code", "name"]].drop_duplicates()
                   .assign(label=lambda d: d["name"] + "  (" + d["code"] + ")")
                   .sort_values("name"))
    label_to_code = dict(zip(cat_choices["label"], cat_choices["code"]))
    with fc2:
        sel_cat_labels = st.multiselect("Categories", options=list(label_to_code.keys()),
                                        default=[], placeholder="All categories in scope")
    with fc3:
        st.write("")
        st.write("")
        active = bool(sel_groups or sel_cat_labels)
        st.caption("Filtered" if active else "All data")

# Apply the filters
df = exp_bva_all
if sel_groups:
    df = df[df["group_name"].isin(sel_groups)]
if sel_cat_labels:
    sel_codes = [label_to_code[l] for l in sel_cat_labels]
    df = df[df["code"].isin(sel_codes)]

# ---------------------------------------------------------------------------
# Headline metrics (recomputed from the filtered set)
# ---------------------------------------------------------------------------
total_budget = df["budgeted_amount"].sum()
total_spent = df["spent_amount"].sum()
total_planned = df["planned_amount"].sum() if "planned_amount" in df else 0
total_remaining = total_budget - total_spent
pct_spent = (total_spent / total_budget * 100) if total_budget else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Budget", f"${total_budget:,.0f}")
c2.metric("Spent to date", f"${total_spent:,.0f}", f"{pct_spent:.0f}% of budget", delta_color="off")
c3.metric("Committed / upcoming", f"${total_planned:,.0f}")
c4.metric("Remaining", f"${total_remaining:,.0f}",
          delta_color="inverse" if total_remaining < 0 else "off")

util = min(pct_spent, 100)
over = total_remaining < 0
bar_color = CLAY if over else GREEN
st.markdown(
    f"""
    <div style="margin:0.75rem 0 0.25rem;">
      <div style="display:flex; justify-content:space-between; font-size:0.8rem;
                  color:{INK_FAINT}; margin-bottom:6px;">
        <span>Budget utilization{' · filtered view' if active else ''}</span>
        <span style="color:{bar_color}; font-weight:600;">{pct_spent:.1f}%</span>
      </div>
      <div style="height:8px; background:{SAND}; border-radius:99px; overflow:hidden;">
        <div style="width:{util}%; height:100%; background:{bar_color}; border-radius:99px;"></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
if over:
    st.markdown(
        f"<div style='color:{CLAY}; font-size:0.85rem; margin-top:0.4rem;'>"
        f"Over budget by ${abs(total_remaining):,.0f}.</div>",
        unsafe_allow_html=True,
    )

st.write("")
st.divider()

# ---------------------------------------------------------------------------
# Monthly trend — budget line vs spend area (filtered)
# ---------------------------------------------------------------------------
section_label("Spend pacing")
st.markdown("#### Monthly budget vs actual")
m = df.groupby("month", as_index=False).agg(
    budgeted=("budgeted_amount", "sum"), spent=("spent_amount", "sum")).sort_values("month")
m["label"] = m["month"].apply(lambda x: MONTHS[int(x) - 1])

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=m["label"], y=m["budgeted"], name="Budgeted",
    mode="lines", line=dict(color=INK_FAINT, width=1.5, dash="dot"),
    hovertemplate="Budgeted: $%{y:,.0f}<extra></extra>",
))
fig.add_trace(go.Scatter(
    x=m["label"], y=m["spent"], name="Actual",
    mode="lines", line=dict(color=GREEN, width=2.5),
    fill="tozeroy", fillcolor="rgba(27,77,62,0.08)",
    hovertemplate="Actual: $%{y:,.0f}<extra></extra>",
))
fig.update_yaxes(tickprefix="$", tickformat=",.0f")
st.plotly_chart(style_fig(fig, height=300), use_container_width=True,
                config={"displayModeBar": False})

st.write("")

# ---------------------------------------------------------------------------
# Two-up: category bars + group composition (filtered)
# ---------------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    section_label("By category")
    st.markdown("#### Spend by line" + (" (top 10)" if df["code"].nunique() > 10 else ""))
    agg = df.groupby(["code", "name"], as_index=False).agg(
        budgeted=("budgeted_amount", "sum"), spent=("spent_amount", "sum"))
    agg = agg.sort_values("spent", ascending=False).head(10).sort_values("spent")

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        y=agg["name"], x=agg["budgeted"], name="Budgeted", orientation="h",
        marker=dict(color=SAND, line=dict(color=LINE, width=1)),
        hovertemplate="Budgeted: $%{x:,.0f}<extra></extra>",
    ))
    fig2.add_trace(go.Bar(
        y=agg["name"], x=agg["spent"], name="Actual", orientation="h",
        marker=dict(color=GREEN),
        hovertemplate="Actual: $%{x:,.0f}<extra></extra>",
    ))
    fig2.update_layout(barmode="overlay", bargap=0.35)
    fig2.update_xaxes(tickprefix="$", tickformat=",.0f")
    fig2.update_yaxes(showgrid=False)
    st.plotly_chart(style_fig(fig2, height=380), use_container_width=True,
                    config={"displayModeBar": False})

with right:
    section_label("Composition")
    # If a single group is in scope, break down by category; otherwise by group
    by_group = df["group_name"].nunique() > 1
    st.markdown("#### Spend by group" if by_group else "#### Spend by category")
    field = "group_name" if by_group else "name"
    comp = df.groupby(field, as_index=False)["spent_amount"].sum()
    comp = comp[comp["spent_amount"] > 0].sort_values("spent_amount", ascending=False)
    if not comp.empty:
        fig3 = go.Figure(data=[go.Pie(
            labels=comp[field], values=comp["spent_amount"],
            hole=0.62, sort=False,
            marker=dict(colors=SERIES, line=dict(color="#FFFFFF", width=2)),
            textposition="outside", textinfo="label",
            hovertemplate="%{label}: $%{value:,.0f} (%{percent})<extra></extra>",
        )])
        fig3.add_annotation(text=f"<b>${comp['spent_amount'].sum():,.0f}</b><br>spent",
                            showarrow=False, font=dict(size=15, color=INK), x=0.5, y=0.5)
        st.plotly_chart(style_fig(fig3, height=380, legend_top=False, showlegend=False),
                        use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No spend recorded in this selection.")

st.divider()

# ---------------------------------------------------------------------------
# Recent activity (filtered to the selected categories where possible)
# ---------------------------------------------------------------------------
section_label("Latest")
st.markdown("#### Recent transactions")
selected_codes = df["code"].unique().tolist()
recent = get_expenses(limit=500)
if not recent.empty:
    recent = recent[recent["category_code"].isin(selected_codes)].head(10)
if not recent.empty:
    categories = get_categories()
    cat_map = dict(zip(categories["code"], categories["name"])) if not categories.empty else {}
    recent["Category"] = recent["category_code"].map(cat_map).fillna(recent["category_code"])
    show = recent.rename(columns={
        "category_code": "Code", "txn_date": "Date", "vendor": "Vendor",
        "amount": "Amount", "status": "Status", "notes": "Notes"
    })[["Date", "Code", "Category", "Vendor", "Amount", "Status", "Notes"]]
    st.dataframe(
        show, use_container_width=True, hide_index=True,
        column_config={
            "Amount": st.column_config.NumberColumn(format="$%.2f"),
            "Code": st.column_config.TextColumn(width="small"),
            "Status": st.column_config.TextColumn(width="small"),
        },
    )
else:
    st.info("No transactions in this selection.")
