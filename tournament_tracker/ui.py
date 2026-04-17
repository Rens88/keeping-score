from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st

from tournament_tracker.models import LeaderboardRow
from tournament_tracker.services.match_service import MatchCard, MatchCardParticipant


STATUS_BADGE = {
    "upcoming": "Upcoming",
    "live": "Live",
    "completed": "Completed",
}

OUTCOME_BADGE = {
    "side1_win": "Side 1 won",
    "side2_win": "Side 2 won",
    "draw": "Draw",
}


def format_datetime(value: Optional[str]) -> str:
    if not value:
        return "TBD"
    try:
        dt = datetime.fromisoformat(value.replace("Z", ""))
        return dt.strftime("%a %d %b %H:%M")
    except Exception:
        return value


def render_photo(photo_blob: Optional[bytes], caption: Optional[str] = None, width: int = 52) -> None:
    if photo_blob:
        st.image(photo_blob, width=width)
    else:
        st.markdown("`No photo`")
    if caption:
        st.caption(caption)


def participant_label(participant: MatchCardParticipant) -> str:
    label = participant.display_name
    if participant.has_doubler_on_match:
        label += " x2"
    return label


def render_match_card(card: MatchCard) -> None:
    with st.container(border=True):
        status_label = STATUS_BADGE.get(card.status, card.status)
        header = f"#{card.match_id} - {card.game_type}"
        st.subheader(header)
        st.caption(
            f"Status: {status_label} | Scheduled: {format_datetime(card.scheduled_at)} | Order: {card.scheduled_order or '-'}"
        )

        col1, col_mid, col2 = st.columns([1, 0.2, 1])
        with col1:
            side = card.sides.get(1, {"participants": []})
            side_name = side.get("side_name") or "Side 1"
            st.markdown(f"**{side_name}**")
            participants = side.get("participants")
            if isinstance(participants, list) and participants:
                for p in participants:
                    if isinstance(p, MatchCardParticipant):
                        st.write(participant_label(p))
            else:
                st.write("No players assigned")

        with col_mid:
            st.markdown("### VS")

        with col2:
            side = card.sides.get(2, {"participants": []})
            side_name = side.get("side_name") or "Side 2"
            st.markdown(f"**{side_name}**")
            participants = side.get("participants")
            if isinstance(participants, list) and participants:
                for p in participants:
                    if isinstance(p, MatchCardParticipant):
                        st.write(participant_label(p))
            else:
                st.write("No players assigned")

        if card.outcome:
            st.info(f"Result: {OUTCOME_BADGE.get(card.outcome, card.outcome)}")
        if card.result_notes:
            st.caption(f"Notes: {card.result_notes}")


def render_leaderboard(leaderboard: list[LeaderboardRow]) -> None:
    if not leaderboard:
        st.info("No completed matches yet. Leaderboard will appear once results are entered.")
        return

    for row in leaderboard:
        with st.container(border=True):
            rank_col, photo_col, main_col, score_col = st.columns([0.6, 1.2, 4, 1.2])
            with rank_col:
                st.markdown(f"### {row.rank}")
            with photo_col:
                render_photo(row.photo_blob, width=56)
            with main_col:
                st.markdown(f"**{row.display_name}**")
                st.caption(row.motto or "No motto")
                st.caption(
                    f"Played {row.matches_played} | W {row.wins} D {row.draws} L {row.losses} | Doubler used: {'Yes' if row.doubler_used else 'No'}"
                )
            with score_col:
                st.metric("Points", f"{row.total_points:.2f}")
