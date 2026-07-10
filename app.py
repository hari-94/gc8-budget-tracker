import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from utils.auth import require_login, logout_button, current_role
from utils.db import get_dashboard_summary, get_budget_vs_actual, get_expenses, get_categories

st.set_page_config(page_title="GC8 Budget Tracker", page_icon="💰", layout="wide")

require_login()
logout_button()

st.title("💰 Budget Dashboard")

# ---------------------------------------------------------------------------
# Fiscal year selector
# ---------------------------------------------------------------------------
col_fy, _ = st.columns([1, 5])
with col_fy:
    fiscal_year = st.selectbox("Fiscal Year", options=[2026, 2025, 2027], index=0)

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
c1.metric("Total Budget", f"${total_budget:,.0f}")
c2.metric("Spent So Far", f"${total_spent:,.0f}", f"{pct_spent:.1f}% of budget")
c3.metric("Upcoming / Planned", f"${total_planned:,.0f}")
c4.metric("Remaining", f"${total_remaining:,.0f}",
          delta_color="inverse" if total_remaining < 0 else "normal")

# Progress bar
st.progress(min(pct_spent / 100, 1.0), text=f"{pct_spent:.1f}% of annual budget spent")
if total_remaining < 0:
    st.error(f"⚠️ Over budget by ${abs(total_remaining):,.0f} for {fiscal_year}")

st.divider()

# ---------------------------------------------------------------------------
# Spend by category (current fiscal year)
# ---------------------------------------------------------------------------
bva = get_budget_vs_actual(fiscal_year)

left, right = st.columns([3, 2])

with left:
    st.subheader("Budget vs Actual by Category")
    if not bva.empty:
        agg = bva[bva["type"] == "expense"].groupby(["code", "name"], as_index=False).agg(
            budgeted=("budgeted_amount", "sum"),
            spent=("spent_amount", "sum"),
        ).sort_values("budgeted", ascending=False).head(15)

        fig = go.Figure()
        fig.add_bar(name="Budgeted", x=agg["name"], y=agg["budgeted"], marker_color="#c7d2fe")
        fig.add_bar(name="Spent", x=agg["name"], y=agg["spent"], marker_color="#4f46e5")
        fig.update_layout(barmode="overlay", height=420, xaxis_tickangle=-40,
                           legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No budget data yet for this fiscal year.")

with right:
    st.subheader("Spend by Group")
    if not bva.empty:
        grp = bva[bva["type"] == "expense"].groupby("group_name", as_index=False)["spent_amount"].sum()
        grp = grp[grp["spent_amount"] > 0]
        if not grp.empty:
            fig2 = go.Figure(data=[go.Pie(
                labels=grp["group_name"], values=grp["spent_amount"], hole=0.55
            )])
            fig2.update_layout(height=420, showlegend=True)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No spend recorded yet.")

st.divider()

# ---------------------------------------------------------------------------
# Monthly trend
# ---------------------------------------------------------------------------
st.subheader("Monthly Spend Trend")
if not bva.empty:
    month_agg = bva[bva["type"] == "expense"].groupby("month", as_index=False).agg(
        budgeted=("budgeted_amount", "sum"),
        spent=("spent_amount", "sum"),
    ).sort_values("month")
    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    month_agg["month_name"] = month_agg["month"].apply(lambda m: month_names[m-1])
    fig3 = go.Figure()
    fig3.add_scatter(x=month_agg["month_name"], y=month_agg["budgeted"], name="Budgeted",
                      mode="lines+markers", line=dict(color="#c7d2fe", width=3, dash="dot"))
    fig3.add_scatter(x=month_agg["month_name"], y=month_agg["spent"], name="Spent",
                      mode="lines+markers", line=dict(color="#4f46e5", width=3))
    fig3.update_layout(height=350, legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------
st.subheader("Recent Transactions")
recent = get_expenses(limit=10)
if not recent.empty:
    categories = get_categories()
    cat_map = dict(zip(categories["code"], categories["name"])) if not categories.empty else {}
    recent["category"] = recent["category_code"].map(cat_map).fillna(recent["category_code"])
    display_cols = ["txn_date", "category", "vendor", "amount", "status", "notes"]
    st.dataframe(
        recent[display_cols].rename(columns={
            "txn_date": "Date", "category": "Category", "vendor": "Vendor",
            "amount": "Amount", "status": "Status", "notes": "Notes"
        }),
        use_container_width=True, hide_index=True,
        column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")}
    )
else:
    st.info("No transactions yet — add one from the **Add Expense** page.")

st.caption("Use the sidebar to add expenses, browse the full log, edit the budget, or manage users.")
