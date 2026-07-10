import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.auth import require_login, logout_button
from utils.theme import (
    inject_theme, style_fig, section_label,
    GREEN, GREEN_TINT, AMBER, CLAY, INK, INK_SOFT, INK_FAINT, LINE, SAND, SERIES,
)
from utils.db import get_dashboard_summary, get_budget_vs_actual, get_expenses, get_categories


MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
head_l, head_r = st.columns([3, 1])
with head_l:
    section_label("Grand Colorado on Peak 8 · Housekeeping")
    st.title("Budget Overview")
with head_r:
    fiscal_year = st.selectbox("Fiscal year", options=[2026, 2025, 2027], index=0,
                               label_visibility="collapsed")

summary = get_dashboard_summary(fiscal_year)
total_budget = float(summary.get("total_budget") or 0)
total_spent = float(summary.get("total_spent") or 0)
total_planned = float(summary.get("total_planned") or 0)
total_remaining = float(summary.get("total_remaining") or 0)
pct_spent = (total_spent / total_budget * 100) if total_budget else 0

# ---------------------------------------------------------------------------
# Headline metrics
# ---------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Annual budget", f"${total_budget:,.0f}")
c2.metric("Spent to date", f"${total_spent:,.0f}", f"{pct_spent:.0f}% of budget", delta_color="off")
c3.metric("Committed / upcoming", f"${total_planned:,.0f}")
c4.metric("Remaining", f"${total_remaining:,.0f}",
          delta_color="inverse" if total_remaining < 0 else "off")

# Slim utilization bar with marker
util = min(pct_spent, 100)
over = total_remaining < 0
bar_color = CLAY if over else GREEN
st.markdown(
    f"""
    <div style="margin:0.75rem 0 0.25rem;">
      <div style="display:flex; justify-content:space-between; font-size:0.8rem;
                  color:{INK_FAINT}; margin-bottom:6px;">
        <span>Budget utilization</span>
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
        f"Over budget by ${abs(total_remaining):,.0f} for {fiscal_year}.</div>",
        unsafe_allow_html=True,
    )

st.write("")
st.divider()

bva = get_budget_vs_actual(fiscal_year)
exp_bva = bva[bva["type"] == "expense"] if not bva.empty else pd.DataFrame()

# ---------------------------------------------------------------------------
# Monthly trend — budget line vs spend area
# ---------------------------------------------------------------------------
section_label("Spend pacing")
st.markdown("#### Monthly budget vs actual")
if not exp_bva.empty:
    m = exp_bva.groupby("month", as_index=False).agg(
        budgeted=("budgeted_amount", "sum"), spent=("spent_amount", "sum"))
    m = m.sort_values("month")
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
else:
    st.info("No budget data for this fiscal year yet.")

st.write("")

# ---------------------------------------------------------------------------
# Two-up: category bars + group composition
# ---------------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    section_label("By category")
    st.markdown("#### Largest spend lines")
    if not exp_bva.empty:
        agg = exp_bva.groupby(["code", "name"], as_index=False).agg(
            budgeted=("budgeted_amount", "sum"), spent=("spent_amount", "sum"))
        agg = agg.sort_values("spent", ascending=False).head(8).sort_values("spent")

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
        st.plotly_chart(style_fig(fig2, height=360), use_container_width=True,
                        config={"displayModeBar": False})

with right:
    section_label("Composition")
    st.markdown("#### Spend by group")
    if not exp_bva.empty:
        grp = exp_bva.groupby("group_name", as_index=False)["spent_amount"].sum()
        grp = grp[grp["spent_amount"] > 0].sort_values("spent_amount", ascending=False)
        if not grp.empty:
            fig3 = go.Figure(data=[go.Pie(
                labels=grp["group_name"], values=grp["spent_amount"],
                hole=0.62, sort=False,
                marker=dict(colors=SERIES, line=dict(color="#FFFFFF", width=2)),
                textposition="outside", textinfo="label",
                hovertemplate="%{label}: $%{value:,.0f} (%{percent})<extra></extra>",
            )])
            total_grp = grp["spent_amount"].sum()
            fig3.add_annotation(text=f"<b>${total_grp:,.0f}</b><br>total",
                                showarrow=False, font=dict(size=15, color=INK),
                                x=0.5, y=0.5)
            st.plotly_chart(style_fig(fig3, height=360, legend_top=False, showlegend=False),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No spend recorded yet.")

st.divider()

# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------
section_label("Latest")
st.markdown("#### Recent transactions")
recent = get_expenses(limit=8)
if not recent.empty:
    categories = get_categories()
    cat_map = dict(zip(categories["code"], categories["name"])) if not categories.empty else {}
    recent["Category"] = recent["category_code"].map(cat_map).fillna(recent["category_code"])
    show = recent.rename(columns={
        "txn_date": "Date", "vendor": "Vendor", "amount": "Amount",
        "status": "Status", "notes": "Notes"
    })[["Date", "Category", "Vendor", "Amount", "Status", "Notes"]]
    st.dataframe(
        show, use_container_width=True, hide_index=True,
        column_config={
            "Amount": st.column_config.NumberColumn(format="$%.2f"),
            "Status": st.column_config.TextColumn(width="small"),
        },
    )
else:
    st.info("No transactions yet. Record one from the Record Expense page.")
