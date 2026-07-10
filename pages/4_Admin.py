import streamlit as st
from utils.auth import require_login, logout_button, is_admin
from utils.db import get_authed_client

st.set_page_config(page_title="Admin", page_icon="👥", layout="wide")
require_login()
logout_button()

st.title("👥 Admin — User Management")

if not is_admin():
    st.warning("Admins only.")
    st.stop()

client = get_authed_client()
res = client.table("profiles").select("*").order("email").execute()

st.caption("Change a user's role. Roles: **admin** (full control incl. permanent delete), "
           "**editor** (can add/edit/soft-delete expenses & budget), **viewer** (read-only).")

for profile in res.data:
    c1, c2, c3 = st.columns([3, 2, 1])
    with c1:
        st.write(profile["email"])
    with c2:
        new_role = st.selectbox(
            "Role", options=["admin", "editor", "viewer"],
            index=["admin", "editor", "viewer"].index(profile["role"]),
            key=f"role_{profile['id']}", label_visibility="collapsed"
        )
    with c3:
        if st.button("Update", key=f"update_{profile['id']}"):
            client.table("profiles").update({"role": new_role}).eq("id", profile["id"]).execute()
            st.success(f"Updated {profile['email']} → {new_role}")
            st.rerun()
