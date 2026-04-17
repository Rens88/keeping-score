from __future__ import annotations

import base64
from datetime import datetime
import html
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

    rows_html: list[str] = []
    for row in leaderboard:
        if row.photo_blob:
            mime_type = row.photo_mime_type or "image/jpeg"
            photo_b64 = base64.b64encode(row.photo_blob).decode("ascii")
            photo_html = (
                f'<img src="data:{mime_type};base64,{photo_b64}" '
                f'alt="{html.escape(row.display_name)}" class="lb-photo" />'
            )
        else:
            photo_html = '<span class="lb-photo-placeholder"></span>'

        special_count = 1 if row.doubler_used else 0
        specials_html = "⚡" * special_count if special_count else "—"
        rows_html.append(
            f"""
            <tr>
                <td>{photo_html}</td>
                <td>{html.escape(row.display_name)}</td>
                <td>{row.matches_played}</td>
                <td>{row.wins}</td>
                <td>{row.draws}</td>
                <td>{row.losses}</td>
                <td class="lb-points">{row.total_points:.2f}</td>
                <td class="lb-specials">{specials_html}</td>
            </tr>
            """
        )

    st.markdown(
        f"""
        <style>
            .lb-wrap {{
                overflow-x: auto;
            }}

            .lb-table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.95rem;
                background: rgba(255, 255, 255, 0.85);
                border-radius: 8px;
                overflow: hidden;
                color: #111111 !important;
            }}

            .lb-table th, .lb-table td {{
                border-bottom: 1px solid rgba(0,0,0,0.08);
                text-align: left;
                padding: 0.35rem 0.45rem;
                white-space: nowrap;
                color: #111111 !important;
            }}

            .lb-table th {{
                font-weight: 700;
                background: rgba(215, 31, 38, 0.08);
            }}

            .lb-photo {{
                height: 1.05em;
                width: 1.05em;
                object-fit: cover;
                border-radius: 999px;
                display: inline-block;
                vertical-align: middle;
            }}

            .lb-photo-placeholder {{
                display: inline-block;
                height: 1.05em;
                width: 1.05em;
                border-radius: 999px;
                background: rgba(0,0,0,0.18);
                vertical-align: middle;
            }}

            .lb-points {{
                font-weight: 700;
                color: #0d0d0d !important;
            }}

            .lb-specials {{
                letter-spacing: 0.08em;
            }}
        </style>
        <div class="lb-wrap">
            <table class="lb-table">
                <thead>
                    <tr>
                        <th>Photo</th>
                        <th>Name</th>
                        <th>Games Played</th>
                        <th>Won</th>
                        <th>Draw</th>
                        <th>Loss</th>
                        <th>Points</th>
                        <th>Specials Used</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows_html)}
                </tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )
