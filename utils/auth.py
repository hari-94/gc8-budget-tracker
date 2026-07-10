import streamlit as st
from utils.db import get_client


def login_form():
    st.title("💰 GC8 Budget Tracker")
    st.caption("Sign in to continue")

    tab_login, tab_signup = st.tabs(["Log in", "Request access"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            client = get_client()
            try:
                result = client.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state["session"] = result.session
                st.session_state["user"] = result.user
                _load_profile()
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab_signup:
        with st.form("signup_form"):
            email = st.text_input("Email", key="su_email")
            password = st.text_input("Password (min 6 characters)", type="password", key="su_pw")
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            client = get_client()
            try:
                client.auth.sign_up({"email": email, "password": password})
                st.success("Account created! New accounts start as 'viewer' — ask an admin to upgrade your role. You can log in now.")
            except Exception as e:
                st.error(f"Sign up failed: {e}")


def _load_profile():
    client = get_client()
    user = st.session_state["user"]
    res = client.table("profiles").select("*").eq("id", user.id).execute()
    if res.data:
        st.session_state["profile"] = res.data[0]
    else:
        st.session_state["profile"] = {"role": "viewer", "email": user.email}


def require_login():
    if "user" not in st.session_state or st.session_state["user"] is None:
        login_form()
        st.stop()
    if "profile" not in st.session_state:
        _load_profile()


def current_role() -> str:
    return st.session_state.get("profile", {}).get("role", "viewer")


def can_edit() -> bool:
    return current_role() in ("admin", "editor")


def is_admin() -> bool:
    return current_role() == "admin"


def logout_button():
    with st.sidebar:
        profile = st.session_state.get("profile", {})
        st.markdown(f"**{profile.get('email','')}**  \nRole: `{profile.get('role','viewer')}`")
        if st.button("Log out", use_container_width=True):
            get_client().auth.sign_out()
            for k in ("session", "user", "profile"):
                st.session_state.pop(k, None)
            st.rerun()
