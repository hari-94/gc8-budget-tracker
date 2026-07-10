import streamlit as st
from utils.db import get_client
from utils.theme import inject_theme, GREEN, INK, INK_SOFT, INK_FAINT, PAPER, SAND, LINE


def login_form():
    inject_theme()
    st.markdown(f"""
    <style>
    section[data-testid="stSidebar"] {{ display: none; }}
    div[data-testid="stAppViewContainer"] > section > div.block-container {{
        max-width: 420px; padding-top: 5rem;
    }}
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="text-align:center; margin-bottom:2rem;">
      <div style="display:inline-flex; align-items:center; justify-content:center;
                  width:52px; height:52px; border-radius:14px; background:{GREEN};
                  color:#fff; font-family:'Fraunces',serif; font-size:1.5rem;
                  font-weight:600; margin-bottom:1rem;">◆</div>
      <h1 style="font-family:'Fraunces',serif; font-size:1.7rem; font-weight:600;
                 color:{INK}; margin:0;">GC8 Budget</h1>
      <p style="color:{INK_FAINT}; font-size:0.9rem; margin:0.35rem 0 0;">
        Grand Colorado on Peak 8 · Housekeeping Operations</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        st.markdown(f"<div style='font-size:0.8rem; font-weight:600; color:{INK_SOFT}; "
                    f"margin-bottom:-0.5rem;'>Username</div>", unsafe_allow_html=True)
        username = st.text_input("Username", label_visibility="collapsed",
                                 placeholder="e.g. hari")
        st.markdown(f"<div style='font-size:0.8rem; font-weight:600; color:{INK_SOFT}; "
                    f"margin-bottom:-0.5rem;'>Password</div>", unsafe_allow_html=True)
        password = st.text_input("Password", type="password", label_visibility="collapsed",
                                 placeholder="Enter your password")
        st.write("")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if submitted:
        client = get_client()
        try:
            result = client.rpc("verify_login", {"p_username": username, "p_password": password}).execute()
            if result.data:
                st.session_state["profile"] = result.data[0]
                from utils.db import log_activity
                from utils.helpers import get_device
                log_activity(result.data[0].get("username"), "login", get_device(), "")
                st.rerun()
            else:
                st.error("That username and password don't match. Try again.")
        except Exception as e:
            st.error(f"Couldn't sign in: {e}")

    st.markdown(
        f"<p style='text-align:center; color:{INK_FAINT}; font-size:0.8rem; "
        f"margin-top:1.5rem;'>Need access? Ask an administrator to set up your login.</p>",
        unsafe_allow_html=True,
    )


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
        name = profile.get("full_name") or profile.get("username", "")
        role = profile.get("role", "viewer")
        st.markdown(f"""
        <div style="padding:0.5rem 0 1rem; border-bottom:1px solid rgba(255,255,255,0.12);
                    margin-bottom:1rem;">
          <div style="font-family:'Fraunces',serif; font-size:1.15rem; font-weight:600;
                      color:#fff;">◆ GC8 Budget</div>
          <div style="font-size:0.8rem; color:rgba(255,255,255,0.55); margin-top:0.6rem;">
            Signed in as</div>
          <div style="font-size:0.92rem; color:#fff; font-weight:500;">{name}</div>
          <div style="display:inline-block; font-size:0.68rem; letter-spacing:0.05em;
                      text-transform:uppercase; color:rgba(255,255,255,0.7);
                      background:rgba(255,255,255,0.1); padding:2px 8px; border-radius:6px;
                      margin-top:0.4rem;">{role}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("profile", None)
            st.rerun()
