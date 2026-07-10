import streamlit as st

from utils.theme import inject_theme
from utils.auth import require_login, logout_button, is_admin

st.set_page_config(page_title="GC8 Budget", page_icon="◆", layout="wide")
inject_theme()

# Gate everything behind login first
require_login()
logout_button()

# Define the navigation with clean, explicit labels
pages = [
    st.Page("pages/0_Dashboard.py", title="Dashboard", default=True),
    st.Page("pages/1_Record_Expense.py", title="Record expense"),
    st.Page("pages/2_Transactions.py", title="Transactions"),
    st.Page("pages/3_Budget_Planner.py", title="Budget planner"),
]
if is_admin():
    pages.append(st.Page("pages/4_Team_and_Access.py", title="Team and access"))

nav = st.navigation(pages)
nav.run()
