from __future__ import annotations

import streamlit as st

from tournament_tracker.bootstrap import get_services
from tournament_tracker.session import get_current_user, render_sidebar

st.set_page_config(page_title="Weekend Tournament Tracker", page_icon="🏆", layout="wide")

services = get_services()
current_user = get_current_user(services)
render_sidebar(current_user)

st.title("Weekend Tournament Tracker")

if current_user:
    st.success("You are logged in.")
    st.write("Use the sidebar to navigate between leaderboard, matches, and your profile.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.page_link("pages/03_Leaderboard.py", label="Open Leaderboard")
    with col2:
        st.page_link("pages/04_Upcoming_Matches.py", label="Open Upcoming Matches")
    with col3:
        st.page_link("pages/06_My_Profile.py", label="Open My Profile")

    if current_user.role == "admin":
        st.divider()
        st.subheader("Admin Quick Links")
        st.page_link("pages/07_Admin_Dashboard.py", label="Admin Dashboard")
        st.page_link("pages/08_Admin_Participants_Invitations.py", label="Participants & Invitations")
        st.page_link("pages/09_Admin_Schedule.py", label="Manage Schedule")
        st.page_link("pages/10_Admin_Results.py", label="Enter/Edit Results")
        st.page_link("pages/11_Admin_Backup_Restore.py", label="Backup & Restore")
else:
    st.info("Log in to access the tournament pages.")
    st.page_link("pages/01_Login.py", label="Go to Login")
    st.page_link("pages/02_Accept_Invitation.py", label="Accept Invitation")

st.divider()
st.caption("MVP: head-to-head matches, invitations, secure login, leaderboard, and one-time doubler mechanic.")
