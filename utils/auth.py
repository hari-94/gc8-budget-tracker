import streamlit as st
from utils.db import get_client


def login_form():
    st.title("💰 GC8 Budget Tracker")
    st.caption("Sign in to continue")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True)

    if submitted:
        client = get_client()
        try:
            result = client.rpc("verify_login", {"p_username": username, "p_password": password}).execute()
            if result.data:
                profile = result.data[0]
                st.session_state["profile"] = profile
                st.rerun()
            else:
                st.error("Incorrect username or password.")
        except Exception as e:
            st.error(f"Login failed: {e}")

    st.caption("Don't have a login? Ask an admin to create one for you.")


def require_login():
    if "profile" not in st.session_state or st.session_state["profile"] is None:
        login_form()
        st.stop()


def current_username() -> str:
    return st.session_state.get("profile", {}).get("username", "")


def current_role() -> str:
    return st.session_state.get("profile", {}).get("role", "viewer")


def can_edit() -> bool:
    return current_role() in ("admin", "editor")


def is_admin() -> bool:
    return current_role() == "admin"


def logout_button():
    with st.sidebar:
        profile = st.session_state.get("profile", {})
        st.markdown(f"**{profile.get('full_name') or profile.get('username','')}**  \nRole: `{profile.get('role','viewer')}`")
        if st.button("Log out", use_container_width=True):
            st.session_state.pop("profile", None)
            st.rerun()
