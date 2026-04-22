from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.session import (
    get_current_user,
    get_initial_page_for_user,
    render_sidebar,
    set_logged_in_user,
)

st.set_page_config(page_title="Login", page_icon="🔐", layout="centered")

services = get_runtime_services()
current_user = get_current_user(services)
render_sidebar(current_user)

render_page_intro("Login", "Use your username or email and password.")

if current_user:
    st.switch_page(get_initial_page_for_user(services, current_user))
    st.stop()

st.caption("Participant and admin accounts both sign in here.")
with st.form("login_form", clear_on_submit=False):
    render_form_field_label("Username or email")
    login_identifier = st.text_input("Username or email", label_visibility="collapsed")
    render_form_field_label("Password")
    password = st.text_input("Password", type="password", label_visibility="collapsed")
    render_form_field_label(
        "Stay logged in on this device",
        f"Recommended for phones and tablets. Keeps you signed in for about {services.config.persistent_login_days} days unless you log out.",
    )
    remember_me = st.checkbox("Stay logged in on this device", value=True, label_visibility="collapsed")
    submitted = st.form_submit_button("Log in", width="stretch")

if submitted:
    user = services.auth_service.authenticate(login_identifier, password)
    if not user:
        st.error("Invalid credentials.")
    else:
        set_logged_in_user(user, services=services, persist_login=remember_me)
        st.success("Logged in successfully.")
        st.switch_page(get_initial_page_for_user(services, user))

st.divider()
if st.button("How does registration work?", width="stretch", key="login_go_invite"):
    st.switch_page("pages/02_Accept_Invitation.py")
render_bottom_decoration()
