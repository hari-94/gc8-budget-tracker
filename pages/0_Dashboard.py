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
_MONTHS_FULL = ["January","February","March","April","May","June",
                "July","August","September","October","November","December"]

head_l, head_r1, head_r2 = st.columns([2.4, 0.9, 1.1])
with head_l:
    section_label("Grand Colorado on Peak 8 · Housekeeping")
    st.title("Budget Overview")
with head_r1:
    st.markdown("<div style='font-size:0.75rem;color:#8A887E;margin-bottom:2px;'>Year</div>",
                unsafe_allow_html=True)
    fiscal_year = st.selectbox("Fiscal year", options=_years, index=_default_idx,
                               label_visibility="collapsed")
with head_r2:
    st.markdown("<div style='font-size:0.75rem;color:#8A887E;margin-bottom:2px;'>Focus month</div>",
                unsafe_allow_html=True)
    _ALL = "All months"
    _month_opts = [_ALL] + _MONTHS_FULL
    # Default to current month if viewing the current year, else All months
    _def_label = _MONTHS_FULL[date.today().month - 1] if fiscal_year == _this_year else _ALL
    focus_month_name = st.selectbox("Focus month", options=_month_opts,
                                    index=_month_opts.index(_def_label),
                                    label_visibility="collapsed")
focus_all = (focus_month_name == _ALL)
focus_month = None if focus_all else (_MONTHS_FULL.index(focus_month_name) + 1)

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
# Headline metrics — scoped to the selected month (or the whole year if "All months")
# ---------------------------------------------------------------------------
if not focus_all:
    _cur_month = focus_month
    _cur_month_name = MONTHS[_cur_month - 1]
    month_df = df[df["month"] == _cur_month] if "month" in df.columns else df.iloc[0:0]
    prev_df = df[df["month"] == (_cur_month - 1)] if _cur_month > 1 and "month" in df.columns else df.iloc[0:0]
    # Headline figures follow the month
    scope_budget = month_df["budgeted_amount"].sum()
    scope_spent = month_df["spent_amount"].sum()
    spent_prev_month = prev_df["spent_amount"].sum()
    mom_delta = scope_spent - spent_prev_month
    scope_label = f"{_cur_month_name} budget"
    spent_label = f"Spent in {_cur_month_name}"
else:
    _cur_month = None
    _cur_month_name = "all months"
    month_df = df
    scope_budget = df["budgeted_amount"].sum()
    scope_spent = df["spent_amount"].sum()
    spent_prev_month = 0
    mom_delta = 0
    scope_label = "Annual budget"
    spent_label = "Spent to date"

scope_remaining = scope_budget - scope_spent
pct_spent = (scope_spent / scope_budget * 100) if scope_budget else 0

# keep these names for downstream sections (charts/key-metrics)
total_budget = scope_budget
total_spent = scope_spent
total_remaining = scope_remaining
spent_this_month = scope_spent
budget_this_month = scope_budget

c1, c2, c3, c4 = st.columns(4)
c1.metric(scope_label, f"${scope_budget:,.0f}")
c2.metric(spent_label, f"${scope_spent:,.0f}", f"{pct_spent:.0f}% of budget", delta_color="off")
if not focus_all:
    with c3:
        # Month-over-month: show last month's spend with the change indicator
        st.metric(f"{MONTHS[_cur_month-2] if _cur_month>1 else '—'} spend",
                  f"${spent_prev_month:,.0f}" if _cur_month > 1 else "—")
        if _cur_month > 1:
            down = mom_delta < 0
            d_color = "#1B7A4B" if down else ("#B44C3C" if mom_delta > 0 else "#8A887E")
            arrow = "▼" if down else ("▲" if mom_delta > 0 else "—")
            verb = "less than" if down else ("more than" if mom_delta > 0 else "same as")
            st.markdown(
                f"<div style='margin-top:-0.8rem; font-size:0.8rem; font-weight:600; "
                f"color:{d_color};'>{arrow} ${abs(mom_delta):,.0f} {verb} last mo.</div>",
                unsafe_allow_html=True,
            )
else:
    with c3:
        n_active = int((df.groupby('month')['spent_amount'].sum() > 0).sum()) if 'month' in df.columns else 0
        st.metric("Months with spend", f"{n_active} of 12")
c4.metric("Remaining", f"${scope_remaining:,.0f}",
          delta_color="inverse" if scope_remaining < 0 else "off")

util = min(pct_spent, 100)
over = total_remaining < 0
bar_color = CLAY if over else GREEN
st.markdown(
    f"""
    <div style="margin:0.75rem 0 0.25rem;">
      <div style="display:flex; justify-content:space-between; font-size:0.8rem;
                  color:{INK_FAINT}; margin-bottom:6px;">
        <span>Budget utilization · {('all year' if focus_all else _cur_month_name)}{' · filtered' if active else ''}</span>
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

# ---------------------------------------------------------------------------
# Key metrics row — derived indicators
# ---------------------------------------------------------------------------
st.write("")
section_label("Key metrics")

# Per-category budget vs actual for the current scope (focus month or whole year)
cat_perf = (month_df.groupby(["code", "name"], as_index=False)
            .agg(budget=("budgeted_amount", "sum"), spent=("spent_amount", "sum")))
cat_perf["over"] = cat_perf["spent"] - cat_perf["budget"]

# Metric 1: how many categories are over budget (only those with a budget set)
budgeted = cat_perf[cat_perf["budget"] > 0]
n_over = int((budgeted["over"] > 0).sum())
n_budgeted = int(len(budgeted))

# Metric 2: the single biggest overspend (category furthest over its budget)
over_only = budgeted[budgeted["over"] > 0].sort_values("over", ascending=False)
if len(over_only):
    worst = over_only.iloc[0]
    worst_name, worst_over = worst["name"], worst["over"]
else:
    worst_name, worst_over = None, 0

# Budget adherence for the scope
month_pct = (spent_this_month / budget_this_month * 100) if budget_this_month else 0

# Top category by spend in the scope
top_cat_name, top_cat_amt = "—", 0
if not month_df.empty:
    tc = month_df.groupby("name")["spent_amount"].sum().sort_values(ascending=False)
    tc = tc[tc > 0]
    if len(tc):
        top_cat_name, top_cat_amt = tc.index[0], tc.iloc[0]

def _short(name, n=26):
    return name if not name or len(name) <= n else name[:n - 1].rstrip() + "…"

_scope_word = "year" if focus_all else MONTHS[_cur_month - 1]

def _subtitle(text, color="#8A887E"):
    st.markdown(f"<div style='margin-top:-0.8rem; font-size:0.78rem; font-weight:600; "
                f"color:{color}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>"
                f"{text}</div>", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Over budget",
              f"{n_over} of {n_budgeted}" if n_budgeted else "—",
              help="Number of budgeted categories whose actual spend exceeds their "
                   "budget for the selected scope.")
    if n_budgeted:
        if n_over:
            _subtitle(f"{n_over} need attention", "#B44C3C")
        else:
            _subtitle("all within budget", "#1B7A4B")
with k2:
    # Headline = the dollar amount over (always fits); subtitle = which category
    if worst_name:
        st.metric("Biggest overspend", f"${worst_over:,.0f}",
                  help="How much the most-over category exceeds its budget for the scope.")
        _subtitle(f"▲ {_short(worst_name)}", "#B44C3C")
    else:
        st.metric("Biggest overspend", "$0",
                  help="No category is over budget for the selected scope.")
        _subtitle("nothing over budget", "#1B7A4B")
with k3:
    st.metric(f"{_scope_word.capitalize()} vs budget",
              f"{month_pct:.0f}%" if budget_this_month else "—",
              help="Spend as a share of budget for the selected scope.")
with k4:
    # Headline = the dollar spent (always fits); subtitle = which category
    if top_cat_amt:
        st.metric(f"Top line · {_scope_word}", f"${top_cat_amt:,.0f}",
                  help="Highest-spend category for the selected scope.")
        _subtitle(_short(top_cat_name))
    else:
        st.metric(f"Top line · {_scope_word}", "—")

# Expandable breakdown of which categories are over budget
if n_over:
    with st.expander(f"See the {n_over} categor{'y' if n_over==1 else 'ies'} over budget", expanded=False):
        ob = over_only.copy()
        ob["pct_over"] = (ob["over"] / ob["budget"] * 100).round(0)
        ob_display = ob.rename(columns={
            "name": "Category", "budget": "Budget", "spent": "Actual",
            "over": "Over by", "pct_over": "% over",
        })[["Category", "Budget", "Actual", "Over by", "% over"]]
        st.dataframe(
            ob_display, hide_index=True, use_container_width=True,
            column_config={
                "Budget": st.column_config.NumberColumn(format="$%.0f"),
                "Actual": st.column_config.NumberColumn(format="$%.0f"),
                "Over by": st.column_config.NumberColumn(format="$%.0f"),
                "% over": st.column_config.NumberColumn(format="%.0f%%"),
            },
        )
        st.caption(f"Scope: {'full year' if focus_all else MONTHS[_cur_month-1]} {fiscal_year}"
                   f"{' · filtered' if active else ''}. "
                   "'Over by' is actual spend minus budget.")

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
