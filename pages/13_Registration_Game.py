from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import render_stat_tiles
from tournament_tracker.weekend_info import ACCOMMODATION_LINK, REWARD_IMAGE_PATH

TOTAL_QUESTIONS = 10

st.set_page_config(page_title="Registration Game", page_icon="🧩", layout="centered")

services = get_runtime_services()
user = require_login(
    services,
    current_page="pages/13_Registration_Game.py",
    allow_gate_page=True,
)
if not services.registration_service.participant_requires_registration_gate(user):
    celebration_user_id = st.session_state.get("registration_game_celebration_user_id")
    if celebration_user_id != user.id:
        st.switch_page("app.py")
        st.stop()
render_sidebar(user, current_page="pages/13_Registration_Game.py")

if not services.registration_service.is_registration_game_active() and not user.registration_game_completed:
    st.switch_page("pages/12_And_Now_We_Wait.py")
    st.stop()

render_page_intro(
    "Registration Game",
    "Beantwoord een vraag, lees de hint en probeer na elke vraag de bestemming te raden.",
)

question_feedback = st.session_state.pop("registration_game_question_feedback", None)
guess_feedback = st.session_state.pop("registration_game_guess_feedback", None)

user = services.repo.get_user_by_id(user.id) or user
questions = services.registration_service.list_questions()
unlocked_hints = services.registration_service.get_unlocked_hints(user)
current_score = services.registration_service.calculate_points_so_far(
    user.registration_questions_answered,
    user.registration_game_incorrect_answers,
)

render_stat_tiles(
    [
        ("Beantwoorde vragen", f"{user.registration_questions_answered}/{TOTAL_QUESTIONS}"),
        ("Fouten", str(user.registration_game_incorrect_answers)),
        ("Punten tot nu", f"{current_score:.1f}"),
    ]
)

if user.registration_game_completed:
    points_awarded = float(user.registration_game_points)
    st.session_state["registration_game_celebration_user_id"] = user.id
    with st.container(border=True):
        st.subheader("Gefeliciteerd!")
        if REWARD_IMAGE_PATH.exists():
            st.image(str(REWARD_IMAGE_PATH), use_container_width=True)
        st.success("Je hebt de bestemming correct geraden.")
        st.write(f"Je hebt **{points_awarded:.1f} punten** verdiend.")
        st.write("De bestemming was `Erp`.")
        st.link_button("Open de accommodatie", ACCOMMODATION_LINK, width="stretch")
        if st.button("Open weekend info", width="stretch"):
            st.switch_page("pages/14_Weekend_Info.py")
        if st.button("Ga naar de homepagina", width="stretch", type="primary"):
            st.switch_page("app.py")
    render_bottom_decoration()
    st.stop()

with st.container(border=True):
    st.subheader("Hoe werkt het?")
    st.write(
        "Het doel is om zo snel mogelijk de **bestemming** te raden. Na elke multiple choice vraag krijg je een hint en "
        "een kans om je gok in te vullen."
    )
    st.write(
        "Elke goed beantwoorde vraag levert **1.0 punt** op. Zodra je `Erp` goed raadt, tellen alle resterende vragen meteen mee "
        "als goed voor **1.5 punt per stuk**."
    )
    st.write(
        "Speel dus slim, raad op tijd, en hou de locatie graag nog even voor jezelf zodat je de anderen geen gratis voordeel geeft."
    )

if isinstance(question_feedback, dict):
    with st.container(border=True):
        if question_feedback.get("is_correct"):
            st.success("Goed!")
        else:
            st.error("Fout!")
            st.write(
                "Juiste antwoord: "
                f"**{question_feedback.get('correct_option_key', '')}. "
                f"{question_feedback.get('correct_option_label', '')}**"
            )
        st.write(f"Hint: {question_feedback.get('hint', '')}")

if isinstance(guess_feedback, dict):
    if guess_feedback.get("is_correct"):
        st.success("Bestemming correct geraden.")
    else:
        st.warning(
            f"'{guess_feedback.get('guess', '')}' is niet correct. Door naar de volgende vraag."
        )

if services.registration_service.can_submit_guess(user):
    with st.container(border=True):
        st.subheader("Raad de bestemming")
        st.caption("Na elke beantwoorde vraag krijg je precies één gok. Hoofdletters en spaties maken niet uit.")
        with st.form("registration_guess_form", clear_on_submit=True):
            render_form_field_label("Bestemming")
            location_guess = st.text_input("Bestemming", label_visibility="collapsed")
            submitted_guess = st.form_submit_button("Raad de bestemming", width="stretch")

        if submitted_guess:
            try:
                result = services.registration_service.submit_location_guess(
                    user_id=user.id,
                    guess=location_guess,
                )
                st.session_state["registration_game_guess_feedback"] = {
                    "is_correct": result.is_correct,
                    "guess": location_guess.strip(),
                }
                if result.is_correct:
                    st.session_state["registration_game_celebration_user_id"] = user.id
                st.rerun()
            except ValidationError as exc:
                st.error(str(exc))

with st.container(border=True):
    st.subheader("Hints tot nu toe")
    if unlocked_hints:
        for hint_index, hint in enumerate(unlocked_hints, start=1):
            st.write(f"{hint_index}. {hint}")
    else:
        st.write("Nog geen hints vrijgespeeld.")

if user.registration_questions_answered < len(questions) and services.registration_service.can_answer_next_question(user):
    question_index = user.registration_questions_answered
    question = questions[question_index]
    option_rows = (
        question["options"][:2],
        question["options"][2:],
    )

    with st.container(border=True):
        st.subheader(f"Vraag {question_index + 1}")
        st.write(question["question"])
        st.caption("Kies één antwoord.")

        for row_index, option_row in enumerate(option_rows, start=1):
            cols = st.columns(2)
            for col, option in zip(cols, option_row):
                option_label = f"{option['key']}. {option['label']}"
                if col.button(
                    option_label,
                    width="stretch",
                    key=f"registration_answer_{question_index}_{row_index}_{option['key']}",
                ):
                    try:
                        result = services.registration_service.answer_next_question(
                            user_id=user.id,
                            selected_option_key=option["key"],
                        )
                        st.session_state["registration_game_question_feedback"] = {
                            "is_correct": result.is_correct,
                            "correct_option_key": result.correct_option_key,
                            "correct_option_label": result.correct_option_label,
                            "hint": result.hint,
                        }
                        st.rerun()
                    except ValidationError as exc:
                        st.error(str(exc))
elif user.registration_questions_answered >= len(questions):
    st.info("Alle vragen zijn geweest. Gebruik de laatste hint en raad de bestemming.")
else:
    st.info("Raad eerst de bestemming voordat je verdergaat naar de volgende vraag.")

render_bottom_decoration()
