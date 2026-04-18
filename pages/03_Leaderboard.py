from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import render_leaderboard

st.set_page_config(page_title="Leaderboard", page_icon="🏆", layout="wide")

services = get_services()
user = require_login(services)
render_sidebar(user)

render_page_intro("Leaderboard", "Current standings with bonus points, totals, and special-use status.")
leaderboard = services.ranking_service.compute_leaderboard()
render_leaderboard(leaderboard)
render_bottom_decoration()
