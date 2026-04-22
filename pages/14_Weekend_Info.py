from __future__ import annotations

import streamlit as st

from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.weekend_info import (
    ACCOMMODATION_LINK,
    ACCOMMODATION_ADDRESS,
    ACCOMMODATION_MAPS_LINK,
    PRACTICAL_INFO,
    REWARD_IMAGE_PATH,
    WIEBETAALTWAT_LINK,
)

st.set_page_config(page_title="Weekend Info", page_icon="🏡", layout="centered")

services = get_runtime_services()
user = require_login(services, current_page="pages/14_Weekend_Info.py")
render_sidebar(user)

render_page_intro(
    "Weekend Info",
    "Alles wat je nodig hebt nu de bestemming bekend is.",
)

if REWARD_IMAGE_PATH.exists():
    st.image(str(REWARD_IMAGE_PATH), use_container_width=True)

with st.container(border=True):
    st.subheader("Belangrijke links")
    st.link_button("Open de accommodatie", ACCOMMODATION_LINK, width="stretch")
    st.link_button("Open accommodatie in Maps", ACCOMMODATION_MAPS_LINK, width="stretch")
    st.link_button("Open WieBetaaltWat", WIEBETAALTWAT_LINK, width="stretch")

with st.container(border=True):
    st.subheader("Praktische info")
    st.write(f"- Address: {ACCOMMODATION_ADDRESS}")
    for item in PRACTICAL_INFO:
        if item == f"Accommodation address: {ACCOMMODATION_ADDRESS}":
            continue
        st.write(f"- {item}")

with st.container(border=True):
    st.subheader("Mini Games")
    game_summaries = []
    for game_slug in ("whack_a_mole", "simon_says"):
        game_label = services.minigame_service.game_label(game_slug)
        status = services.minigame_service.get_status(game_slug=game_slug)
        if status.state == "live":
            game_summaries.append(f"{game_label} is live")
        elif status.state == "scheduled":
            game_summaries.append(
                f"{game_label} opens op {services.minigame_service.format_datetime(status.opens_at)}"
            )
        elif status.state == "closed":
            game_summaries.append(f"{game_label} is gesloten, maar de eindstand is zichtbaar")
        else:
            game_summaries.append(f"{game_label} is nog niet vrijgegeven")

    for item in game_summaries:
        st.write(f"- {item}")
    if st.button("Open Mini Games", width="stretch", type="primary"):
        st.switch_page("pages/15_Mini_Game.py")

render_bottom_decoration()
