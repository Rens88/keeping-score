from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import render_past_matches_compact

st.set_page_config(page_title="Past Matches", page_icon="📜", layout="wide")

services = get_services()
user = require_login(services)
render_sidebar(user)

render_page_intro("Past Matches", "Review completed matches and the points they produced.")

show_only_mine = False
if user.role == "participant":
    show_only_mine = st.toggle("Show only matches I played", value=True)

cards = services.match_service.list_matches_for_view(
    statuses=["completed"],
    participant_user_id=user.id if show_only_mine else None,
)

if not cards:
    st.info("No completed matches yet.")
else:
    render_past_matches_compact(cards, viewer_user_id=user.id)

render_bottom_decoration()
