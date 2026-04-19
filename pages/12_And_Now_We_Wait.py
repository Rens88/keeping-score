from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.session import render_sidebar, require_login

st.set_page_config(page_title="And Now We Wait", page_icon="⏳", layout="centered")

services = get_services()
user = require_login(
    services,
    current_page="pages/12_And_Now_We_Wait.py",
    allow_gate_page=True,
)
if not services.registration_service.participant_requires_registration_gate(user):
    st.switch_page("app.py")
    st.stop()

render_sidebar(user)

render_page_intro(
    "And now we wait...",
    "Your account is ready. The admin just has to unleash the registration game when the dramatic timing feels right.",
)

with st.container(border=True):
    st.subheader("What happens next?")
    st.write("Your login works. Your account exists. Your destiny is loading.")
    st.write(
        "As soon as the admin activates the registration game, this page will turn into your first teamweekend mission."
    )
    st.write("Until then, stay calm, hydrate responsibly, and keep your guessing brain loosely warmed up.")

with st.container(border=True):
    st.subheader("Current status")
    st.write("Registration game: not active yet")
    st.write("Your future reward: bragging rights, starting points, and one very specific location reveal.")

render_bottom_decoration()
