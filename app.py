from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.session import enforce_registration_gate, get_current_user, render_sidebar

st.set_page_config(page_title="Weekend Tournament Tracker", page_icon="🏆", layout="wide")

services = get_services()
current_user = get_current_user(services)
if current_user:
    enforce_registration_gate(services, current_user, current_page="app.py")
render_sidebar(current_user)

render_page_intro(
    "Weekend Tournament Tracker",
    "Use the quick links below to move between leaderboard, matches, profiles, admin tools, and the new registration flow.",
)

if current_user:
    st.success("You are logged in.")
    st.write("Use the sidebar to navigate between leaderboard, matches, your weekend info, and the mini game.")

    if current_user.role == "admin":
        st.divider()
        st.subheader("Admin Quick Links")
        admin_col_1, admin_col_2 = st.columns(2)
        with admin_col_1:
            if st.button("Admin Dashboard", width="stretch", key="home_admin_dashboard"):
                st.switch_page("pages/07_Admin_Dashboard.py")
            if st.button("Participants & Registration", width="stretch", key="home_admin_participants"):
                st.switch_page("pages/08_Admin_Participants_Invitations.py")
            if st.button("Registration Game", width="stretch", key="home_admin_registration_game"):
                st.switch_page("pages/12_Admin_Registration_Game.py")
            if st.button("Mini Game", width="stretch", key="home_admin_minigame"):
                st.switch_page("pages/16_Admin_Mini_Game.py")
            if st.button("Manage Schedule", width="stretch", key="home_admin_schedule"):
                st.switch_page("pages/09_Admin_Schedule.py")
        with admin_col_2:
            if st.button("Enter/Edit Results", width="stretch", key="home_admin_results"):
                st.switch_page("pages/10_Admin_Results.py")
            if st.button("Backup & Restore", width="stretch", key="home_admin_backup"):
                st.switch_page("pages/11_Admin_Backup_Restore.py")
    else:
        st.divider()
        st.subheader("Weekend Quick Links")
        participant_col_1, participant_col_2 = st.columns(2)
        with participant_col_1:
            if st.button("Weekend Info", width="stretch", key="home_weekend_info"):
                st.switch_page("pages/14_Weekend_Info.py")
        with participant_col_2:
            if st.button("Mini Game", width="stretch", key="home_mini_game"):
                st.switch_page("pages/15_Mini_Game.py")
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
    "MVP: head-to-head matches, admin-managed registration, secure login, leaderboard, the registration game, Whack-a-mole, and the one-time doubler mechanic."
)
render_bottom_decoration()
