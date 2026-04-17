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
    st.page_link("pages/01_Login.py", label="Go to Login")
    st.stop()


def require_admin(services: AppServices) -> User:
    user = require_login(services)
    if user.role == "admin":
        return user

    st.error("You do not have permission to view this page.")
    st.page_link("pages/03_Leaderboard.py", label="Go to Leaderboard")
    st.stop()


def render_main_navigation(user: Optional[User]) -> None:
    if not user:
        return

    st.markdown("**Quick Navigation**")
    core_cols = st.columns(5)
    core_cols[0].page_link("app.py", label="Home", icon="🏠")
    core_cols[1].page_link("pages/03_Leaderboard.py", label="Leaderboard", icon="🏆")
    core_cols[2].page_link("pages/04_Upcoming_Matches.py", label="Upcoming", icon="📅")
    core_cols[3].page_link("pages/05_Past_Matches.py", label="Past", icon="📜")
    core_cols[4].page_link("pages/06_My_Profile.py", label="My Profile", icon="👤")

    if user.role == "admin":
        admin_cols = st.columns(5)
        admin_cols[0].page_link("pages/07_Admin_Dashboard.py", label="Admin Home", icon="🛡️")
        admin_cols[1].page_link("pages/08_Admin_Participants_Invitations.py", label="Participants", icon="👥")
        admin_cols[2].page_link("pages/09_Admin_Schedule.py", label="Schedule", icon="🗓️")
        admin_cols[3].page_link("pages/10_Admin_Results.py", label="Results", icon="✅")
        admin_cols[4].page_link("pages/11_Admin_Backup_Restore.py", label="Backup", icon="💾")

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
        st.page_link("pages/03_Leaderboard.py", label="Leaderboard")
        st.page_link("pages/04_Upcoming_Matches.py", label="Upcoming")
        st.page_link("pages/05_Past_Matches.py", label="Past Matches")
        st.page_link("pages/06_My_Profile.py", label="My Profile")

        if user and user.role == "admin":
            st.divider()
            st.subheader("Admin")
            st.page_link("pages/07_Admin_Dashboard.py", label="Dashboard")
            st.page_link("pages/08_Admin_Participants_Invitations.py", label="Participants & Invites")
            st.page_link("pages/09_Admin_Schedule.py", label="Manage Schedule")
            st.page_link("pages/10_Admin_Results.py", label="Enter/Edit Results")
            st.page_link("pages/11_Admin_Backup_Restore.py", label="Backup & Restore")
