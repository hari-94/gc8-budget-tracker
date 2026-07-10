import streamlit as st
from utils.auth import require_login, logout_button, is_admin
from utils.db import list_app_users, upsert_app_user, update_user_role, delete_app_user

st.set_page_config(page_title="Admin", page_icon="👥", layout="wide")
require_login()
logout_button()

st.title("👥 Admin — User Management")

if not is_admin():
    st.warning("Admins only.")
    st.stop()

st.subheader("Existing users")
users = list_app_users()
if users.empty:
    st.caption("No users found.")
else:
    for _, u in users.iterrows():
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            st.write(f"**{u['full_name'] or u['username']}**  \n`{u['username']}`")
        with c2:
            new_role = st.selectbox(
                "Role", options=["admin", "editor", "viewer"],
                index=["admin", "editor", "viewer"].index(u["role"]),
                key=f"role_{u['username']}", label_visibility="collapsed"
            )
            if new_role != u["role"]:
                if st.button("Update role", key=f"update_{u['username']}"):
                    update_user_role(u["username"], new_role)
                    st.success(f"{u['username']} -> {new_role}")
                    st.rerun()
        with c3:
            if st.button("Delete", key=f"delete_{u['username']}"):
                delete_app_user(u["username"])
                st.success(f"Deleted {u['username']}")
                st.rerun()
        st.divider()

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
            upsert_app_user(username.strip().lower(), password, full_name, role)
            st.success(f"Saved {username} as {role}.")
            st.rerun()

st.caption(
    "Roles: **admin** (full control incl. permanent delete + user management), "
    "**editor** (can add/edit/soft-delete expenses & budget), **viewer** (read-only)."
)
