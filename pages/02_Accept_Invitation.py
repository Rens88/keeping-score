from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.session import get_current_user, get_initial_page_for_user, render_sidebar

st.set_page_config(page_title="Registration Help", page_icon="✉️", layout="centered")

services = get_runtime_services()
current_user = get_current_user(services)
render_sidebar(current_user)

if current_user:
    st.switch_page(get_initial_page_for_user(services, current_user))
    st.stop()

render_page_intro(
    "Registration Help",
    "The admin now creates your account details for you. No invite token acrobatics required.",
)

with st.container(border=True):
    st.subheader("How it works")
    st.write("1. The admin creates your registration account and chooses your temporary password.")
    st.write("2. You receive a message with the app link, username, and password.")
    st.write("3. You log in with those details and the app guides you to the next step automatically.")

with st.container(border=True):
    st.subheader("What you need")
    st.write("Ask the admin for:")
    st.write("- The web link")
    st.write("- Your username")
    st.write("- Your password")
    st.write("Once you have those, head to the login page and the app will take it from there.")

st.divider()
if st.button("Go to Login", width="stretch", type="primary", key="registration_help_go_login"):
    st.switch_page("pages/01_Login.py")

render_bottom_decoration()
