from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from typing import Optional

import streamlit as st

from tournament_tracker.models import LeaderboardRow
from tournament_tracker.services.match_service import MatchCard, MatchCardParticipant
from tournament_tracker.services.ranking_service import POINTS


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

PERSONAL_OUTCOME_LABEL = {
    "win": "Won",
    "draw": "Draw",
    "loss": "Lost",
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


def _participants_for_side(card: MatchCard, side_number: int) -> list[MatchCardParticipant]:
    side = card.sides.get(side_number, {"participants": []})
    participants = side.get("participants")
    if isinstance(participants, list):
        return [p for p in participants if isinstance(p, MatchCardParticipant)]
    return []


def _who_vs_who_text(card: MatchCard) -> str:
    side1_names = " + ".join(p.display_name for p in _participants_for_side(card, 1)) or "Side 1"
    side2_names = " + ".join(p.display_name for p in _participants_for_side(card, 2)) or "Side 2"
    return f"{side1_names} vs {side2_names}"


def _personal_outcome(card: MatchCard, viewer_user_id: int) -> Optional[str]:
    side_number: Optional[int] = None
    for participant in _participants_for_side(card, 1):
        if participant.user_id == viewer_user_id:
            side_number = 1
            break
    if side_number is None:
        for participant in _participants_for_side(card, 2):
            if participant.user_id == viewer_user_id:
                side_number = 2
                break

    if side_number is None or not card.outcome:
        return None
    if card.outcome == "draw":
        return "draw"
    if card.outcome == "side1_win":
        return "win" if side_number == 1 else "loss"
    if card.outcome == "side2_win":
        return "win" if side_number == 2 else "loss"
    return None


def _points_gained_for_viewer(card: MatchCard, viewer_user_id: int, personal_outcome: str) -> float:
    base_points = POINTS[personal_outcome]
    participants = _participants_for_side(card, 1) + _participants_for_side(card, 2)
    viewer = next((p for p in participants if p.user_id == viewer_user_id), None)
    if viewer and viewer.has_doubler_on_match:
        return base_points * 2
    return base_points


def render_past_matches_compact(cards: list[MatchCard], viewer_user_id: int) -> None:
    st.markdown(
        """
        <style>
            .uc-past-head {
                display: grid;
                grid-template-columns: minmax(220px, 1fr) 130px 130px;
                gap: 0.6rem;
                font-size: 0.78rem;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: #4b5563;
                font-weight: 700;
                margin-bottom: 0.35rem;
                padding: 0 0.5rem;
            }

            .uc-past-row {
                display: grid;
                grid-template-columns: minmax(220px, 1fr) 130px 130px;
                gap: 0.6rem;
                align-items: center;
                padding: 0.5rem 0.65rem;
                margin-bottom: 0.35rem;
                border-radius: 10px;
                border-left: 8px solid #9ca3af;
                background: #f8fafc;
                color: #111111;
                font-size: 0.92rem;
            }

            .uc-past-row.win {
                border-left-color: #16a34a;
                background: #ecfdf3;
            }

            .uc-past-row.draw {
                border-left-color: #2563eb;
                background: #eff6ff;
            }

            .uc-past-row.loss {
                border-left-color: #dc2626;
                background: #fef2f2;
            }

            .uc-past-row.neutral {
                border-left-color: #9ca3af;
                background: #f8fafc;
            }

            .uc-past-cell {
                overflow-wrap: anywhere;
            }

            .uc-past-points {
                font-weight: 800;
            }

            @media (max-width: 900px) {
                .uc-past-head {
                    display: none;
                }

                .uc-past-row {
                    grid-template-columns: 1fr;
                    gap: 0.2rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="uc-past-head">
            <div>Who Against Whom</div>
            <div>Result</div>
            <div>Points Gained</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for card in cards:
        personal_outcome = _personal_outcome(card, viewer_user_id)
        row_state = personal_outcome or "neutral"
        result_text = (
            PERSONAL_OUTCOME_LABEL[personal_outcome]
            if personal_outcome
            else OUTCOME_BADGE.get(card.outcome or "", "Result unknown")
        )
        points_text = "-"
        if personal_outcome:
            points_text = f"{_points_gained_for_viewer(card, viewer_user_id, personal_outcome):.2f}"

        who_vs_who = _who_vs_who_text(card)
        who_cell = f"#{card.match_id} {card.game_type}: {who_vs_who}"

        st.markdown(
            f"""
            <div class="uc-past-row {escape(row_state)}">
                <div class="uc-past-cell">{escape(who_cell)}</div>
                <div class="uc-past-cell">{escape(result_text)}</div>
                <div class="uc-past-cell uc-past-points">{escape(points_text)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_leaderboard(leaderboard: list[LeaderboardRow]) -> None:
    if not leaderboard:
        st.info("No completed matches yet. Leaderboard will appear once results are entered.")
        return

    rows: list[dict[str, object]] = []
    for row in leaderboard:
        photo_value: str | None = None
        if row.photo_blob:
            mime_type = row.photo_mime_type or "image/jpeg"
            photo_b64 = base64.b64encode(row.photo_blob).decode("ascii")
            photo_value = f"data:{mime_type};base64,{photo_b64}"

        specials_used = "⚡" if row.doubler_used else ""
        rows.append(
            {
                "Photo": photo_value,
                "Name": row.display_name,
                "Motto": row.motto,
                "Games Played": row.matches_played,
                "Won": row.wins,
                "Draw": row.draws,
                "Loss": row.losses,
                "Bonus Points": float(f"{row.bonus_points:.2f}"),
                "Total Points": float(f"{row.total_points:.2f}"),
                "Specials Used": specials_used,
            }
        )

    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_order=[
            "Photo",
            "Name",
            "Motto",
            "Games Played",
            "Won",
            "Draw",
            "Loss",
            "Bonus Points",
            "Total Points",
            "Specials Used",
        ],
        column_config={
            "Photo": st.column_config.ImageColumn("Photo", width="small"),
            "Name": st.column_config.TextColumn("Name", width="medium"),
            "Motto": st.column_config.TextColumn("Motto", width="medium"),
            "Games Played": st.column_config.NumberColumn("Games Played", width="small"),
            "Won": st.column_config.NumberColumn("Won", width="small"),
            "Draw": st.column_config.NumberColumn("Draw", width="small"),
            "Loss": st.column_config.NumberColumn("Loss", width="small"),
            "Bonus Points": st.column_config.NumberColumn("Bonus Points", format="%.2f", width="small"),
            "Total Points": st.column_config.NumberColumn("Total Points", format="%.2f", width="small"),
            "Specials Used": st.column_config.TextColumn("Specials Used", width="small"),
        },
    )
