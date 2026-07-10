import streamlit as st
from utils.auth import require_login, logout_button, is_admin
from utils.db import get_client

st.set_page_config(page_title="Admin", page_icon="👥", layout="wide")
require_login()
logout_button()

st.title("👥 Admin — User Management")

if not is_admin():
    st.warning("Admins only.")
    st.stop()

client = get_client()

st.subheader("Add or update a user")
st.caption("If the username already exists, this resets their password and role.")
with st.form("user_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        username = st.text_input("Username (lowercase, no spaces)")
        full_name = st.text_input("Full name")
    with c2:
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", options=["admin", "editor", "viewer"])
    submitted = st.form_submit_button("Save user", type="primary", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
        else:
            client.rpc("upsert_app_user", {
                "p_username": username.strip().lower(),
                "p_password": password,
                "p_full_name": full_name,
                "p_role": role,
            }).execute()
            st.success(f"Saved {username} as {role}.")

st.divider()
st.caption(
    "Roles: **admin** (full control incl. permanent delete + user management), "
    "**editor** (can add/edit/soft-delete expenses & budget), **viewer** (read-only)."
)
st.info(
    "There's no list of existing users here since passwords are hashed and never stored in "
    "readable form. To check who exists, look at the `app_users` table in Supabase Table Editor "
    "(username, full_name, role are visible - passwords are not)."
)
