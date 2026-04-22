from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.session import render_sidebar, require_admin

st.set_page_config(page_title="Results Moved", page_icon="✅", layout="wide")

services = get_runtime_services()
admin_user = require_admin(services, current_page="pages/10_Admin_Results.py")
render_sidebar(admin_user)

render_page_intro(
    "Results Moved",
    "Head-to-head and multi-competitor results now live inside Manage Schedule, each under their own Results tab.",
    eyebrow="Admin",
)

st.info("Open Manage Schedule to create, edit, enter results, remove results, or delete both competition types from one place.")
if st.button("Open Manage Schedule", width="stretch", type="primary"):
    st.switch_page("pages/09_Admin_Schedule.py")

render_bottom_decoration()
