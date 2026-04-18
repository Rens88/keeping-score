from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.session import render_sidebar, require_admin
from tournament_tracker.ui import OUTCOME_BADGE

st.set_page_config(page_title="Enter or Edit Results", page_icon="✅", layout="wide")

services = get_services()
admin_user = require_admin(services)
render_sidebar(admin_user)

render_page_intro("Enter or Edit Results", "Record outcomes, add notes, or reset a match back to upcoming or live.", eyebrow="Admin")

cards = services.match_service.list_matches_for_view()
if not cards:
    st.info("No matches available.")
    st.stop()

label_to_match_id = {
    f"#{card.match_id} - {card.game_type} ({card.status})": card.match_id
    for card in cards
}
selected_label = st.selectbox("Select match", list(label_to_match_id.keys()))
selected_match_id = label_to_match_id[selected_label]
selected_card = next(card for card in cards if card.match_id == selected_match_id)

st.subheader(f"Match #{selected_card.match_id}: {selected_card.game_type}")
col1, col2 = st.columns(2)
with col1:
    side_name = selected_card.sides[1]["side_name"] or "Side 1"
    st.markdown(f"**{side_name}**")
    for p in selected_card.sides[1]["participants"]:
        if hasattr(p, "display_name"):
            st.write(f"- {p.display_name}{' x2' if p.has_doubler_on_match else ''}")
with col2:
    side_name = selected_card.sides[2]["side_name"] or "Side 2"
    st.markdown(f"**{side_name}**")
    for p in selected_card.sides[2]["participants"]:
        if hasattr(p, "display_name"):
            st.write(f"- {p.display_name}{' x2' if p.has_doubler_on_match else ''}")

outcome_options = ["side1_win", "draw", "side2_win"]
default_outcome_index = outcome_options.index(selected_card.outcome) if selected_card.outcome in outcome_options else 0

with st.form("result_form"):
    outcome = st.selectbox(
        "Result",
        outcome_options,
        index=default_outcome_index,
        format_func=lambda o: OUTCOME_BADGE.get(o, o),
    )
    notes = st.text_area("Notes", value=selected_card.result_notes or "")
    submit_result = st.form_submit_button("Save result", width="stretch")

if submit_result:
    try:
        services.match_service.set_match_result(
            match_id=selected_match_id,
            outcome=outcome,
            entered_by_user_id=admin_user.id,
            notes=notes,
            mark_completed=True,
        )
        st.success("Result saved.")
        st.rerun()
    except (ValidationError, NotFoundError) as exc:
        st.error(str(exc))

st.divider()
st.subheader("Reset result")
new_status = st.selectbox(
    "Status after clearing result",
    ["upcoming", "live"],
    index=0,
)
if st.button("Clear result for this match", width="stretch", type="secondary"):
    try:
        services.match_service.clear_match_result(match_id=selected_match_id, new_status=new_status)
        st.success("Result cleared.")
        st.rerun()
    except (ValidationError, NotFoundError) as exc:
        st.error(str(exc))

render_bottom_decoration()
