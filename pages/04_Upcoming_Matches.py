from __future__ import annotations

import streamlit as st

from tournament_tracker.bootstrap import get_services
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import render_match_card

st.set_page_config(page_title="Upcoming Matches", page_icon="📅", layout="wide")

services = get_services()
user = require_login(services)
render_sidebar(user)

st.title("Upcoming Matches")

if user.role == "participant":
    st.subheader("My Doubler")
    activation = services.repo.get_doubler_activation(user.id)

    if activation:
        match = services.repo.get_match(activation.match_id)
        if match:
            st.success(
                f"You already used your doubler on match #{match.id} ({match.game_type})."
            )
        else:
            st.success("You already used your doubler.")
    else:
        eligible = services.match_service.list_eligible_upcoming_matches_for_participant(user.id)
        if not eligible:
            st.info("No eligible upcoming matches for your doubler right now.")
        else:
            options = {
                f"#{m.match_id} - {m.game_type} (order {m.scheduled_order or '-'})": m.match_id
                for m in eligible
            }
            selected_label = st.selectbox("Choose a match to activate your doubler", list(options.keys()))
            if st.button("Activate doubler", use_container_width=True):
                try:
                    services.match_service.activate_doubler(
                        participant_user_id=user.id,
                        match_id=options[selected_label],
                        actor_user_id=user.id,
                    )
                    st.success("Doubler activated.")
                    st.rerun()
                except ValidationError as exc:
                    st.error(str(exc))

    st.divider()

all_cards = services.match_service.list_matches_for_view(statuses=["live", "upcoming"])
live_cards = [card for card in all_cards if card.status == "live"]
upcoming_cards = [card for card in all_cards if card.status == "upcoming"]

if live_cards:
    st.subheader("Live")
    for card in live_cards:
        render_match_card(card)

st.subheader("Upcoming")
if not upcoming_cards:
    st.info("No upcoming matches scheduled yet.")
else:
    for card in upcoming_cards:
        render_match_card(card)
