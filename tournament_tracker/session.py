from __future__ import annotations

from typing import Optional

import streamlit as st

from tournament_tracker.bootstrap import AppServices
from tournament_tracker.branding import CANGEROES_LOGO_URL, render_cangeroes_header
from tournament_tracker.models import User

SESSION_USER_ID_KEY = "auth_user_id"


def set_logged_in_user(user: User) -> None:
    st.session_state[SESSION_USER_ID_KEY] = user.id


def logout_user() -> None:
    st.session_state.pop(SESSION_USER_ID_KEY, None)


def get_current_user(services: AppServices) -> Optional[User]:
    user_id = st.session_state.get(SESSION_USER_ID_KEY)
    if not user_id:
        return None
    user = services.repo.get_user_by_id(int(user_id))
    if not user or not user.is_active:
        st.session_state.pop(SESSION_USER_ID_KEY, None)
        return None
    return user


def require_login(services: AppServices) -> User:
    user = get_current_user(services)
    if user:
        return user

    st.warning("Please log in first.")
    if st.button("Go to Login", width="stretch", key="require_login_go_login"):
        st.switch_page("pages/01_Login.py")
    st.stop()


def require_admin(services: AppServices) -> User:
    user = require_login(services)
    if user.role == "admin":
        return user

    st.error("You do not have permission to view this page.")
    if st.button("Go to Leaderboard", width="stretch", key="require_admin_go_leaderboard"):
        st.switch_page("pages/03_Leaderboard.py")
    st.stop()


def _render_navigation_rows(buttons: list[tuple[str, str, str]], row_size: int = 3) -> None:
    for start in range(0, len(buttons), row_size):
        row_buttons = buttons[start:start + row_size]
        row_cols = st.columns(len(row_buttons))
        for col, (label, page, key) in zip(row_cols, row_buttons):
            if col.button(label, width="stretch", key=key):
                st.switch_page(page)


def render_main_navigation(user: Optional[User]) -> None:
    if not user:
        return

    st.markdown("**Quick Navigation**")
    st.caption("Use the top row for fast page switches without opening the sidebar.")
    _render_navigation_rows(
        [
            ("🏠 Home", "app.py", "top_nav_home"),
            ("🏆 Leaderboard", "pages/03_Leaderboard.py", "top_nav_leaderboard"),
            ("📅 Upcoming", "pages/04_Upcoming_Matches.py", "top_nav_upcoming"),
            ("📜 Past", "pages/05_Past_Matches.py", "top_nav_past"),
            ("👤 My Profile", "pages/06_My_Profile.py", "top_nav_profile"),
        ]
    )

    if user.role == "admin":
        _render_navigation_rows(
            [
                ("🛡️ Admin Home", "pages/07_Admin_Dashboard.py", "top_nav_admin_home"),
                ("👥 Participants", "pages/08_Admin_Participants_Invitations.py", "top_nav_admin_participants"),
                ("🗓️ Schedule", "pages/09_Admin_Schedule.py", "top_nav_admin_schedule"),
                ("✅ Results", "pages/10_Admin_Results.py", "top_nav_admin_results"),
                ("💾 Backup", "pages/11_Admin_Backup_Restore.py", "top_nav_admin_backup"),
            ]
        )

    st.divider()


def render_sidebar(user: Optional[User]) -> None:
    render_cangeroes_header()
    render_main_navigation(user)

    with st.sidebar:
        st.image(
            CANGEROES_LOGO_URL,
            width=190,
        )
        st.title("Weekend Tracker")
        if user:
            st.caption(f"Logged in as `{user.username or user.email or user.id}` ({user.role})")
            if st.button("Log out", width="stretch"):
                logout_user()
                st.rerun()

        st.divider()
        st.subheader("Navigation")
        if st.button("Leaderboard", width="stretch", key="side_nav_leaderboard"):
            st.switch_page("pages/03_Leaderboard.py")
        if st.button("Upcoming", width="stretch", key="side_nav_upcoming"):
            st.switch_page("pages/04_Upcoming_Matches.py")
        if st.button("Past Matches", width="stretch", key="side_nav_past"):
            st.switch_page("pages/05_Past_Matches.py")
        if st.button("My Profile", width="stretch", key="side_nav_profile"):
            st.switch_page("pages/06_My_Profile.py")

        if user and user.role == "admin":
            st.divider()
            st.subheader("Admin")
            if st.button("Dashboard", width="stretch", key="side_nav_admin_dashboard"):
                st.switch_page("pages/07_Admin_Dashboard.py")
            if st.button("Participants & Invites", width="stretch", key="side_nav_admin_participants"):
                st.switch_page("pages/08_Admin_Participants_Invitations.py")
            if st.button("Manage Schedule", width="stretch", key="side_nav_admin_schedule"):
                st.switch_page("pages/09_Admin_Schedule.py")
            if st.button("Enter/Edit Results", width="stretch", key="side_nav_admin_results"):
                st.switch_page("pages/10_Admin_Results.py")
            if st.button("Backup & Restore", width="stretch", key="side_nav_admin_backup"):
                st.switch_page("pages/11_Admin_Backup_Restore.py")
