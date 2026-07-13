import streamlit as st
import pandas as pd
from utils.auth import require_login, logout_button, is_admin
from utils.theme import inject_theme, section_label, INK_FAINT
from utils.helpers import fmt_mt
from utils.db import (
    list_app_users, upsert_app_user, update_user_role, delete_app_user,
    get_recent_activity, get_categories, get_category_entry_counts, set_category_archived,
)

section_label("Administration")
st.title("Team & Access")

if not is_admin():
    st.warning("Admins only.")
    st.stop()

tab_team, tab_activity, tab_cats = st.tabs(["Team", "Activity", "Categories"])

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

# ===========================================================================
# CATEGORIES — archive ones that aren't actively tracked
# ===========================================================================
with tab_cats:
    st.subheader("Category tracking")
    st.caption("Archive categories your team doesn't actively log (e.g. payroll or utilities "
               "handled elsewhere). Archived categories disappear from the expense picker, "
               "dashboard, and planner — but their budget data is kept and they can be restored anytime.")

    import pandas as pd
    all_cats = get_categories(include_archived=True)
    all_cats = all_cats[all_cats["type"] == "expense"] if not all_cats.empty else all_cats
    counts = get_category_entry_counts()
    count_map = dict(zip(counts["code"], counts["entry_count"])) if not counts.empty else {}

    if all_cats.empty:
        st.caption("No categories found.")
    else:
        show_which = st.radio("Show", options=["Active", "Archived", "All"], horizontal=True)

        rows = []
        for _, c in all_cats.iterrows():
            is_arch = bool(c.get("archived"))
            if show_which == "Active" and is_arch:
                continue
            if show_which == "Archived" and not is_arch:
                continue
            rows.append(c)

        if not rows:
            st.caption(f"No {show_which.lower()} categories.")
        for c in rows:
            code = c["code"]
            is_arch = bool(c.get("archived"))
            n = int(count_map.get(code, 0))
            cc1, cc2, cc3 = st.columns([4, 1.3, 1.2])
            with cc1:
                dim = "color:#8A887E;" if is_arch else ""
                badge = " · archived" if is_arch else ""
                st.markdown(f"<span style='{dim}'>**{c['name']}** &nbsp; "
                            f"<code>{code}</code>{badge}</span>", unsafe_allow_html=True)
            with cc2:
                tag = "no entries" if n == 0 else f"{n} entr{'y' if n==1 else 'ies'}"
                st.markdown(f"<span style='color:#8A887E; font-size:0.85rem;'>{tag}</span>",
                            unsafe_allow_html=True)
            with cc3:
                if is_arch:
                    if st.button("Restore", key=f"restore_cat_{code}", use_container_width=True):
                        set_category_archived(code, False)
                        st.rerun()
                else:
                    if st.button("Archive", key=f"arch_cat_{code}", use_container_width=True):
                        set_category_archived(code, True)
                        st.rerun()
            st.divider()

        # Quick bulk action: archive all zero-entry active categories
        if show_which in ("Active", "All"):
            zero_active = [c for c in rows if int(count_map.get(c["code"], 0)) == 0
                           and not bool(c.get("archived"))]
            if zero_active:
                st.markdown("###### Quick action")
                st.caption(f"{len(zero_active)} shown categor{'y has' if len(zero_active)==1 else 'ies have'} "
                           f"no entries at all.")
                if st.button(f"Archive all {len(zero_active)} zero-entry categories"):
                    for c in zero_active:
                        set_category_archived(c["code"], True)
                    st.success(f"Archived {len(zero_active)} categories.")
                    st.rerun()
