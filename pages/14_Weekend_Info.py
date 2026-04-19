from __future__ import annotations

import streamlit as st

from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.weekend_info import (
    ACCOMMODATION_LINK,
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
    st.link_button("Open WieBetaaltWat", WIEBETAALTWAT_LINK, width="stretch")

with st.container(border=True):
    st.subheader("Praktische info")
    for item in PRACTICAL_INFO:
        st.write(f"- {item}")

minigame_status = services.minigame_service.get_status()
with st.container(border=True):
    st.subheader("Mini Game")
    if minigame_status.state == "live":
        st.success("Whack-a-mole is live.")
        if st.button("Open Whack-a-mole", width="stretch", type="primary"):
            st.switch_page("pages/15_Mini_Game.py")
    elif minigame_status.state == "scheduled":
        st.info(
            "Whack-a-mole gaat open op "
            f"{services.minigame_service.format_datetime(minigame_status.opens_at)}."
        )
    elif minigame_status.state == "closed":
        st.info("Whack-a-mole is gesloten. Je kunt de eindstand nog bekijken op de minigame-pagina.")
        if st.button("Bekijk de minigame-stand", width="stretch"):
            st.switch_page("pages/15_Mini_Game.py")
    else:
        st.caption("Whack-a-mole is nog niet vrijgegeven.")

render_bottom_decoration()
