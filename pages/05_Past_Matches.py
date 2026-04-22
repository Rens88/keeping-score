from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.repository import COMPETITION_RANKING_SOURCE_TYPE
from tournament_tracker.ui import format_datetime, render_past_matches_compact

st.set_page_config(page_title="Past Events", page_icon="📜", layout="wide")

services = get_runtime_services()
user = require_login(services, current_page="pages/05_Past_Matches.py")
render_sidebar(user)

render_page_intro("Past Events", "Review completed head-to-head matches and multi-competitor games.")

show_only_mine = False
if user.role == "participant":
    render_form_field_label("Show only events I played")
    show_only_mine = st.toggle("Show only events I played", value=True, label_visibility="collapsed")

cards = services.match_service.list_matches_for_view(
    statuses=["completed"],
    participant_user_id=user.id if show_only_mine else None,
)
ranked_games = services.ranked_event_service.list_events(statuses=["completed"])
ranked_game_ids = [event.id for event in ranked_games]
ranked_competitor_rows = (
    services.ranked_event_service.get_event_competitor_rows(ranked_game_ids)
    if ranked_game_ids
    else []
)
competitor_ids_by_game: dict[int, list[int]] = {}
competitor_names_by_game_and_user: dict[tuple[int, int], str] = {}
for row in ranked_competitor_rows:
    game_id = int(row.get("event_id", row.get("ranked_event_id")))
    user_id = int(row["participant_user_id"])
    competitor_ids_by_game.setdefault(game_id, []).append(user_id)
    competitor_names_by_game_and_user[(game_id, user_id)] = str(
        row.get("display_name")
        or row.get("username")
        or row.get("email")
        or f"User {user_id}"
    )

if show_only_mine:
    ranked_games = [
        event
        for event in ranked_games
        if user.id in competitor_ids_by_game.get(event.id, [])
    ]

ranked_results = services.repo.list_ranked_event_results()
ranked_results_by_game: dict[int, list[object]] = {}
for result in ranked_results:
    ranked_results_by_game.setdefault(result.ranked_event_id, []).append(result)

ranked_points_by_game_and_user: dict[tuple[int, int], float] = {}
for award in services.repo.list_competition_point_award_rows():
    if (
        award["source_type"] == COMPETITION_RANKING_SOURCE_TYPE
        and str(award["source_key"]).startswith("ranked_event:")
    ):
        try:
            game_id = int(str(award["source_key"]).split(":", 1)[1])
        except Exception:
            continue
        ranked_points_by_game_and_user[(game_id, int(award["participant_user_id"]))] = float(award["points_awarded"])

if not cards and not ranked_games:
    st.info("No completed events yet.")
else:
    if cards:
        st.subheader("Head-to-head")
        completed_match_ids = [card.match_id for card in cards]
        points_by_match_and_user = (
            services.special_service.get_completed_match_point_map()
            if hasattr(services, "special_service")
            else None
        )
        match_bets = services.repo.list_match_bets(match_ids=completed_match_ids, include_settled=True)
        bettor_user_ids = sorted({bet.participant_user_id for bet in match_bets})
        user_rows_by_user_id = services.repo.get_profiles_by_user_ids(bettor_user_ids) if bettor_user_ids else {}
        render_past_matches_compact(
            cards,
            viewer_user_id=user.id,
            points_by_match_and_user=points_by_match_and_user,
            match_bets=match_bets,
            user_rows_by_user_id=user_rows_by_user_id,
        )

    if ranked_games:
        st.subheader("Multi-competitor")
        for event in ranked_games:
            expander_label = (
                f"#{event.id} {event.title} | Completed | {format_datetime(event.scheduled_at)}"
            )
            with st.expander(expander_label, expanded=False):
                st.caption(
                    f"Order: {event.scheduled_order or '-'} | "
                    "Weekend points: "
                    + ", ".join(
                        f"P{index}={points}"
                        for index, points in enumerate(
                            services.ranked_event_service.parse_award_scheme(event.award_scheme),
                            start=1,
                        )
                    )
                )
                rows = []
                for result in ranked_results_by_game.get(event.id, []):
                    competitor_name = competitor_names_by_game_and_user.get(
                        (event.id, result.participant_user_id),
                        f"User {result.participant_user_id}",
                    )
                    rows.append(
                        {
                            "placement": result.placement,
                            "competitor": competitor_name,
                            "weekend_points": f"{ranked_points_by_game_and_user.get((event.id, result.participant_user_id), 0.0):.1f}",
                        }
                    )
                if rows:
                    st.dataframe(rows, width="stretch", hide_index=True)
                else:
                    st.info("No result saved yet for this multi-competitor game.")

render_bottom_decoration()
