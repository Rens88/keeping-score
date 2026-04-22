from __future__ import annotations

from datetime import datetime

import streamlit as st

from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.services.minigame_service import (
    DEFAULT_AWARD_SCHEME,
    SIMON_SAYS_SLUG,
    WHACK_A_MOLE_SLUG,
)
from tournament_tracker.session import render_sidebar, require_admin
from tournament_tracker.ui import render_stat_tiles

st.set_page_config(page_title="Admin Mini Games", page_icon="🔨", layout="wide")

services = get_runtime_services()
admin_user = require_admin(services, current_page="pages/16_Admin_Mini_Game.py")
render_sidebar(admin_user)

render_page_intro(
    "Mini Games",
    "Plan both games, manage their open windows, and award weekend points once each deadline passes.",
    eyebrow="Admin",
)


def _render_admin_game_panel(game_slug: str, *, description: str) -> None:
    game_label = services.minigame_service.game_label(game_slug)
    game_config = services.minigame_service.get_game_config(game_slug)
    game_status = services.minigame_service.get_status(game_slug=game_slug)
    leaderboard = services.minigame_service.list_leaderboard(game_slug)
    total_attempts = sum(row.attempts for row in leaderboard)

    render_stat_tiles(
        [
            ("Game status", game_status.state.title()),
            ("Players on board", str(len(leaderboard))),
            ("Total attempts", str(total_attempts)),
            (
                "Awards applied",
                services.minigame_service.format_datetime(game_status.awards_applied_at)
                if game_status.awards_applied_at
                else "Not yet",
            ),
        ]
    )

    current_open = game_status.opens_at or services.minigame_service.default_open_at()
    current_deadline = game_status.deadline_at or services.minigame_service.default_deadline_at()
    current_scheme = ",".join(str(value) for value in (game_config.award_scheme or DEFAULT_AWARD_SCHEME))

    with st.container(border=True):
        st.subheader(game_label)
        st.write(description)

    with st.container(border=True):
        st.subheader("Instellingen")
        with st.form(f"admin_minigame_settings_{game_slug}"):
            render_form_field_label(
                f"{game_label} actief",
                "Uit: spelers zien alleen de status. Aan: de game volgt het open- en sluitmoment hieronder.",
            )
            enabled = st.toggle(
                f"{game_label} actief",
                value=game_config.enabled,
                label_visibility="collapsed",
            )
            col1, col2 = st.columns(2)
            with col1:
                render_form_field_label("Open op")
                open_date = st.date_input(
                    f"Open op {game_slug}",
                    value=current_open.date(),
                    label_visibility="collapsed",
                )
                render_form_field_label("Open om")
                open_time = st.time_input(
                    f"Open om {game_slug}",
                    value=current_open.time().replace(second=0, microsecond=0),
                    label_visibility="collapsed",
                )
            with col2:
                render_form_field_label("Deadline op")
                deadline_date = st.date_input(
                    f"Deadline op {game_slug}",
                    value=current_deadline.date(),
                    label_visibility="collapsed",
                )
                render_form_field_label("Deadline om")
                deadline_time = st.time_input(
                    f"Deadline om {game_slug}",
                    value=current_deadline.time().replace(second=0, microsecond=0),
                    label_visibility="collapsed",
                )

            render_form_field_label(
                "Puntenschema voor weekendleaderboard",
                "Komma-gescheiden punten per plek, bijvoorbeeld 5,3,1 of 5,4,3,2,1.",
            )
            award_scheme_input = st.text_input(
                f"Puntenschema voor weekendleaderboard {game_slug}",
                value=current_scheme,
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Instellingen opslaan", width="stretch", type="primary")

        if submitted:
            try:
                award_scheme = services.minigame_service.parse_award_scheme(award_scheme_input)
                opens_at = services.minigame_service.localize_naive(datetime.combine(open_date, open_time))
                deadline_at = services.minigame_service.localize_naive(datetime.combine(deadline_date, deadline_time))
                services.minigame_service.update_game_config(
                    admin_user_id=admin_user.id,
                    game_slug=game_slug,
                    enabled=enabled,
                    opens_at=opens_at,
                    deadline_at=deadline_at,
                    award_scheme=award_scheme,
                )
                st.success(f"{game_label} instellingen opgeslagen.")
                st.rerun()
            except ValidationError as exc:
                st.error(str(exc))

    with st.container(border=True):
        st.subheader("Status en toekenning")
        st.write(f"- Open vanaf: {services.minigame_service.format_datetime(game_status.opens_at)}")
        st.write(f"- Deadline: {services.minigame_service.format_datetime(game_status.deadline_at)}")
        st.write(f"- Puntenschema: {', '.join(str(value) for value in game_status.award_scheme)}")
        if game_status.state == "closed":
            st.success("De deadline is verstreken. Je kunt nu weekendpunten toekennen of verversen.")
            if st.button(
                f"Ken weekendpunten toe / ververs voor {game_label}",
                width="stretch",
                type="primary",
                key=f"award_minigame_{game_slug}",
            ):
                try:
                    services.minigame_service.apply_awards(
                        admin_user_id=admin_user.id,
                        game_slug=game_slug,
                    )
                    st.success(f"{game_label} weekendpunten zijn bijgewerkt.")
                    st.rerun()
                except ValidationError as exc:
                    st.error(str(exc))
        elif game_status.state == "scheduled":
            st.info("De game is ingepland maar nog niet open.")
        elif game_status.state == "live":
            st.info("De game is live. De stand hieronder verandert automatisch wanneer spelers nieuwe highscores zetten.")
        else:
            st.caption("Zodra de game actief is en een deadline heeft, kun je hier de weekendpunten afhandelen.")

    with st.container(border=True):
        st.subheader("Live stand")
        if not leaderboard:
            st.info("Nog geen gespeelde runs.")
        else:
            st.dataframe(
                [
                    {
                        "rank": row.rank,
                        "name": row.display_name,
                        "best_score": row.best_score,
                        "attempts": row.attempts,
                        "awarded_points": f"{row.awarded_points:.0f}",
                        "best_run_at": services.minigame_service.format_datetime(row.best_played_at),
                    }
                    for row in leaderboard
                ],
                width="stretch",
                hide_index=True,
            )

    with st.container(border=True):
        st.subheader("Preview weekendpunten")
        preview_rows = []
        for placement, points in enumerate(game_status.award_scheme, start=1):
            participant_name = leaderboard[placement - 1].display_name if placement <= len(leaderboard) else "Nog leeg"
            preview_rows.append(
                {
                    "place": placement,
                    "weekend_points": points,
                    "current_holder": participant_name,
                }
            )
        st.dataframe(preview_rows, width="stretch", hide_index=True)


whack_tab, simon_tab = st.tabs(["Whack-a-mole", "Simon Says"])

with whack_tab:
    _render_admin_game_panel(
        WHACK_A_MOLE_SLUG,
        description="Whack-a-mole blijft de snelle reactietest met tijdsdruk en veel korte runs.",
    )

with simon_tab:
    _render_admin_game_panel(
        SIMON_SAYS_SLUG,
        description="Simon Says test geheugen in oplopende reeksen. Hogere rondes leveren direct betere scores op.",
    )

render_bottom_decoration()
