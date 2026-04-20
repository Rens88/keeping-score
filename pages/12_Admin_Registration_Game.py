from __future__ import annotations

from datetime import datetime

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.session import render_sidebar, require_admin
from tournament_tracker.ui import render_stat_tiles

st.set_page_config(page_title="Admin Registration Game", page_icon="🧩", layout="wide")

services = get_runtime_services()
admin_user = require_admin(services, current_page="pages/12_Admin_Registration_Game.py")
render_sidebar(admin_user, current_page="pages/12_Admin_Registration_Game.py")

render_page_intro(
    "Registration Game",
    "Plan wanneer de locatiegame opent en bekijk hoe ver deelnemers al zijn.",
    eyebrow="Admin",
)

participants = services.profile_service.list_participant_profiles()
game_status = services.registration_service.get_game_status()
waiting_count = sum(1 for participant in participants if not participant.registration_game_completed)
in_progress_count = sum(
    1
    for participant in participants
    if not participant.registration_game_completed and participant.registration_questions_answered > 0
)
completed_count = sum(1 for participant in participants if participant.registration_game_completed)

status_label = {
    "disabled": "Uit",
    "scheduled": "Ingepland",
    "live": "Live",
}.get(game_status.state, game_status.state.title())

render_stat_tiles(
    [
        ("Game status", status_label),
        ("Open vanaf", services.registration_service.format_datetime(game_status.opens_at)),
        ("Wachten / Pending", str(waiting_count)),
        ("Klaar", str(completed_count)),
    ]
)

current_open = game_status.opens_at or services.registration_service.default_open_at()

with st.container(border=True):
    st.subheader("Instellingen")
    with st.form("admin_registration_game_settings"):
        render_form_field_label(
            "Registration game actief",
            "Uit: deelnemers blijven op de wachtpagina. Aan: de game opent automatisch op het moment hieronder.",
        )
        enabled = st.toggle(
            "Registration game actief",
            value=game_status.enabled,
            label_visibility="collapsed",
        )
        render_form_field_label("Open op")
        open_date = st.date_input(
            "Open op",
            value=current_open.date(),
            label_visibility="collapsed",
        )
        render_form_field_label("Open om")
        open_time = st.time_input(
            "Open om",
            value=current_open.time().replace(second=0, microsecond=0),
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Instellingen opslaan", width="stretch", type="primary")

    if submitted:
        try:
            opens_at = services.registration_service.localize_naive(datetime.combine(open_date, open_time))
            services.registration_service.update_game_config(
                admin_user_id=admin_user.id,
                enabled=enabled,
                opens_at=opens_at,
            )
            st.success("Registration game instellingen opgeslagen.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc))

with st.container(border=True):
    st.subheader("Status")
    if game_status.state == "live":
        st.success("De registration game is live. Nieuwe deelnemers landen direct in de vragenflow.")
    elif game_status.state == "scheduled":
        st.info(
            "De registration game staat ingepland en opent automatisch op "
            f"{services.registration_service.format_datetime(game_status.opens_at)}."
        )
    else:
        st.caption("De registration game is uitgeschakeld. Deelnemers blijven wachten tot jij hem activeert.")

with st.container(border=True):
    st.subheader("Vragen en hints")
    for idx, question in enumerate(services.registration_service.list_questions(), start=1):
        with st.expander(f"Vraag {idx}: {question['question']}"):
            st.write("Opties:")
            for option in question["options"]:
                prefix = "Juiste antwoord" if option["key"] == question["correctAnswer"] else "Optie"
                st.write(f"- {prefix} {option['key']}: {option['label']}")
            st.caption(question["hint"])

with st.container(border=True):
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
                        if game_status.state == "live"
                        else "Scheduled"
                        if game_status.state == "scheduled"
                        else "Waiting"
                    ),
                    "questions_answered": f"{participant.registration_questions_answered}/10",
                    "incorrect_answers": participant.registration_game_incorrect_answers,
                    "starting_points": f"{participant.registration_game_points:.1f}",
                }
                for participant in participants
            ],
            width="stretch",
            hide_index=True,
        )

render_bottom_decoration()
