from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.session import render_sidebar, require_admin
from tournament_tracker.ui import render_stat_tiles

st.set_page_config(page_title="Admin Registration Game", page_icon="🧩", layout="wide")

services = get_services()
admin_user = require_admin(services, current_page="pages/12_Admin_Registration_Game.py")
render_sidebar(admin_user)

render_page_intro(
    "Registration Game",
    "Bepaal of nieuwe deelnemers nog wachten of meteen in de locatiegame terechtkomen.",
    eyebrow="Admin",
)

participants = services.profile_service.list_participant_profiles()
active = services.registration_service.is_registration_game_active()
waiting_count = sum(1 for participant in participants if not participant.registration_game_completed)
in_progress_count = sum(
    1
    for participant in participants
    if not participant.registration_game_completed and participant.registration_questions_answered > 0
)
completed_count = sum(1 for participant in participants if participant.registration_game_completed)

render_stat_tiles(
    [
        ("Game status", "Actief" if active else "Gepauzeerd"),
        ("Wachten / Pending", str(waiting_count)),
        ("Bezig", str(in_progress_count)),
        ("Klaar", str(completed_count)),
    ]
)

toggle_value = st.toggle(
    "Registration game actief",
    value=active,
    help="Uit: nieuwe deelnemers zien de wachtpagina. Aan: openstaande deelnemers zien de registration game.",
)
if toggle_value != active:
    services.registration_service.set_registration_game_active(
        admin_user_id=admin_user.id,
        active=toggle_value,
    )
    st.success(
        "Registration game geactiveerd."
        if toggle_value
        else "Registration game gepauzeerd. Openstaande deelnemers gaan terug naar de wachtpagina."
    )
    st.rerun()

st.divider()
st.subheader("Vragen en hints")
for idx, question in enumerate(services.registration_service.list_questions(), start=1):
    with st.expander(f"Vraag {idx}: {question['question']}"):
        st.write("Opties:")
        for option in question["options"]:
            prefix = "Juiste antwoord" if option["key"] == question["correctAnswer"] else "Optie"
            st.write(f"- {prefix} {option['key']}: {option['label']}")
        st.caption(question["hint"])

st.divider()
st.subheader("Voortgang deelnemers")
if not participants:
    st.info("Nog geen deelnemers.")
else:
    st.dataframe(
        [
            {
                "name": participant.display_name or participant.username or participant.email or participant.user_id,
                "status": (
                    "Finished"
                    if participant.registration_game_completed
                    else "In progress"
                    if participant.registration_questions_answered > 0
                    else "Game live"
                    if active
                    else "Waiting"
                ),
                "questions_answered": f"{participant.registration_questions_answered}/10",
                "incorrect_answers": participant.registration_game_incorrect_answers,
                "starting_points": f"{participant.registration_game_points:.0f}",
            }
            for participant in participants
        ],
        width="stretch",
        hide_index=True,
    )

render_bottom_decoration()
