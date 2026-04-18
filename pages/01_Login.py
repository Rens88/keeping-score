from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.session import get_current_user, render_sidebar, set_logged_in_user

st.set_page_config(page_title="Login", page_icon="🔐", layout="centered")

services = get_services()
current_user = get_current_user(services)
render_sidebar(current_user)

render_page_intro("Login", "Use your username or email and password.")

if current_user:
    st.success("You are already logged in.")
    if st.button("Go to Leaderboard", width="stretch", key="login_go_leaderboard"):
        st.switch_page("pages/03_Leaderboard.py")
    st.stop()

with st.container(border=True):
    st.caption("Participant and admin accounts both sign in here.")
    with st.form("login_form", clear_on_submit=False):
        login_identifier = st.text_input("Username or email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", width="stretch")

if submitted:
    user = services.auth_service.authenticate(login_identifier, password)
    if not user:
        st.error("Invalid credentials.")
    else:
        set_logged_in_user(user)
        st.success("Logged in successfully.")
        st.rerun()

st.divider()
if st.button("I have an invitation link", width="stretch", key="login_go_invite"):
    st.switch_page("pages/02_Accept_Invitation.py")
render_bottom_decoration()
