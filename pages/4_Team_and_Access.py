import streamlit as st
import pandas as pd
from utils.auth import require_login, logout_button, is_admin
from utils.theme import inject_theme, section_label, INK_FAINT
from utils.helpers import fmt_mt
from utils.db import (
    list_app_users, upsert_app_user, update_user_role, delete_app_user,
    get_recent_activity,
)

section_label("Administration")
st.title("Team & Access")

if not is_admin():
    st.warning("Admins only.")
    st.stop()

tab_team, tab_activity = st.tabs(["Team", "Activity"])

# ===========================================================================
# TEAM
# ===========================================================================
with tab_team:
    st.subheader("Current team")
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

    st.subheader("Add or update a login")
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

# ===========================================================================
# ACTIVITY
# ===========================================================================
with tab_activity:
    st.subheader("Who's using the app")
    st.caption("Logins and actions across the team, in Mountain Time.")

    activity = get_recent_activity(limit=200)
    if activity.empty:
        st.caption("No activity recorded yet.")
    else:
        # Summary: last seen + device per user
        summary_rows = []
        for user, grp in activity.groupby("username"):
            last = grp.sort_values("created_at", ascending=False).iloc[0]
            logins = int((grp["action"] == "login").sum())
            summary_rows.append({
                "User": user,
                "Last active": fmt_mt(last["created_at"]),
                "Last device": last.get("device") or "—",
                "Logins": logins,
                "Total actions": len(grp),
            })
        summary = pd.DataFrame(summary_rows).sort_values("User")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.markdown("###### Recent events")
        recent = activity.head(60)
        action_label = {
            "login": "Signed in", "add_expense": "Added expense",
            "edit_expense": "Edited expense", "delete_expense": "Deleted expense",
        }
        for _, a in recent.iterrows():
            label = action_label.get(a["action"], a["action"])
            detail = f" · {a['detail']}" if a.get("detail") else ""
            st.markdown(
                f"<div style='padding:2px 0; font-size:0.88rem;'>"
                f"<b>{a['username']}</b> — {label}"
                f"<span style='color:{INK_FAINT};'>{detail} · {a.get('device') or 'unknown device'} · "
                f"{fmt_mt(a['created_at'])}</span></div>",
                unsafe_allow_html=True,
            )
