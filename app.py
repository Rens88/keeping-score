from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.session import enforce_registration_gate, get_current_user, render_sidebar

st.set_page_config(page_title="Weekend Tournament Tracker", page_icon="🏆", layout="wide")

services = get_runtime_services()
current_user = get_current_user(services)
if current_user:
    enforce_registration_gate(services, current_user, current_page="app.py")
render_sidebar(current_user, current_page="app.py")

render_page_intro(
    "Weekend Tournament Tracker",
    "Of course we needed this app. We can reveal the accommodation location, track rankings, view matches, use specials, play mini-games, and earn points by predicting outcomes.",
)

if current_user:
    st.success("You are logged in.")
    st.write("Use the icons above or the sidebar to jump between leaderboard, matches, specials, and admin tools.")

    if current_user.role == "admin":
        st.divider()
        st.subheader("Admin Quick Links")
        admin_col_1, admin_col_2 = st.columns(2)
        with admin_col_1:
            if st.button("Admin Dashboard", width="stretch", key="home_admin_dashboard"):
                st.switch_page("pages/07_Admin_Dashboard.py")
            if st.button("Specials", width="stretch", key="home_admin_specials"):
                st.switch_page("pages/17_Specials.py")
            if st.button("Participants & Registration", width="stretch", key="home_admin_participants"):
                st.switch_page("pages/08_Admin_Participants_Invitations.py")
            if st.button("Registration Game", width="stretch", key="home_admin_registration_game"):
                st.switch_page("pages/12_Admin_Registration_Game.py")
            if st.button("Mini Game", width="stretch", key="home_admin_minigame"):
                st.switch_page("pages/16_Admin_Mini_Game.py")
        with admin_col_2:
            if st.button("Manage Schedule", width="stretch", key="home_admin_schedule"):
                st.switch_page("pages/09_Admin_Schedule.py")
            if st.button("Results in Schedule", width="stretch", key="home_admin_results"):
                st.switch_page("pages/09_Admin_Schedule.py")
            if st.button("Backup & Restore", width="stretch", key="home_admin_backup"):
                st.switch_page("pages/11_Admin_Backup_Restore.py")
else:
    with st.container(border=True):
        st.subheader("Welcome")
        st.write("Log in to access the tournament pages.")
        btn_col_1, btn_col_2 = st.columns(2)
        with btn_col_1:
            if st.button("Go to Login", type="primary", width="stretch", key="home_login_btn"):
                st.switch_page("pages/01_Login.py")
        with btn_col_2:
            if st.button("Registration Help", width="stretch", key="home_invite_btn"):
                st.switch_page("pages/02_Accept_Invitation.py")

st.divider()
st.caption(
    "Of course we needed this app. We can reveal the accommodation location, track rankings, view matches, use specials, play mini-games, and earn points by predicting outcomes."
)
render_bottom_decoration()
