from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import render_leaderboard

st.set_page_config(page_title="Leaderboard", page_icon="🏆", layout="wide")

services = get_runtime_services()
user = require_login(services, current_page="pages/03_Leaderboard.py")
render_sidebar(user)

render_page_intro("Leaderboard", "Current standings with bonus points, totals, and special-use status.")
leaderboard = services.ranking_service.compute_leaderboard()
point_ledger_builder = getattr(services.ranking_service, "build_point_ledger_map", None)
point_ledger_map = point_ledger_builder([row.user_id for row in leaderboard]) if callable(point_ledger_builder) else {}
render_leaderboard(leaderboard, point_ledger_by_user_id=point_ledger_map)
render_bottom_decoration()
