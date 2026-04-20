from __future__ import annotations

from datetime import datetime

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import render_stat_tiles

st.set_page_config(page_title="And Now We Wait", page_icon="⏳", layout="centered")


def _format_countdown(target: datetime | None) -> str:
    if target is None:
        return "Nog niet gepland"
    delta = target - services.registration_service.local_now()
    total_seconds = max(0, int(delta.total_seconds()))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


services = get_runtime_services()
user = require_login(
    services,
    current_page="pages/12_And_Now_We_Wait.py",
    allow_gate_page=True,
)
if not services.registration_service.participant_requires_registration_gate(user):
    st.switch_page("app.py")
    st.stop()

if services.registration_service.is_registration_game_active():
    st.switch_page("pages/13_Registration_Game.py")
    st.stop()

render_sidebar(user, current_page="pages/12_And_Now_We_Wait.py")

game_status = services.registration_service.get_game_status()
countdown_label = _format_countdown(game_status.opens_at) if game_status.state == "scheduled" else "Nog niet bezig"

render_page_intro(
    "And now we wait...",
    "Je account is klaar. Terwijl je wacht kun je alvast je motto en profielfoto bijwerken zodat je straks stijlvol de game in gaat.",
)

render_stat_tiles(
    [
        ("Status", {"disabled": "Uit", "scheduled": "Ingepland", "live": "Live"}.get(game_status.state, game_status.state)),
        ("Open vanaf", services.registration_service.format_datetime(game_status.opens_at)),
        ("Countdown", countdown_label),
    ]
)

with st.container(border=True):
    st.subheader("What happens next?")
    st.write("Je login werkt. Je account bestaat. Je locatie-missie staat warm te draaien.")
    if game_status.state == "scheduled":
        st.write(
            "Zodra de timer afloopt opent de registration game automatisch en mag je beginnen met vragen beantwoorden, hints verzamelen en de bestemming raden."
        )
    else:
        st.write(
            "De admin heeft de registration game nog niet ingepland of geactiveerd. Zodra dat gebeurt, verandert deze pagina vanzelf in je eerste teamweekend missie."
        )
    st.write(
        "Gebruik de tussentijd slim: update je motto en profielfoto, zodat de rest van de groep meteen weet wie er straks punten komt jatten."
    )
    if st.button("Open my profile", width="stretch", type="primary"):
        st.switch_page("pages/06_My_Profile.py")

with st.container(border=True):
    st.subheader("Current status")
    if game_status.state == "scheduled":
        st.write(
            "Registration game opent op "
            f"**{services.registration_service.format_datetime(game_status.opens_at)}**."
        )
        st.write(f"Huidige countdown: **{countdown_label}**")
    elif game_status.state == "disabled":
        st.write("Registration game: nog niet actief of nog niet ingepland.")
    else:
        st.write("Registration game: live")
    st.write("Je toekomstige beloning: hints, startpunten en de reveal van een heel specifieke locatie.")

render_bottom_decoration()
