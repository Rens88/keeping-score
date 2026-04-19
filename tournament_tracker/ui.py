from __future__ import annotations

import base64
from datetime import datetime
from html import escape
import json
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

from tournament_tracker.branding import render_html_block
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


def render_stat_tiles(items: list[tuple[str, str]]) -> None:
    if not items:
        return

    tile_html = ['<div class="uc-stat-grid">']
    for label, value in items:
        tile_html.append(
            f"""
<div class="uc-stat-tile">
    <div class="uc-stat-label">{escape(label)}</div>
    <div class="uc-stat-value">{escape(value)}</div>
</div>
            """
        )
    tile_html.append("</div>")

    render_html_block(
        """
<style>
    .uc-stat-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 0.75rem;
        margin: 0.2rem 0 0.35rem 0;
    }

    .uc-stat-tile {
        background: linear-gradient(180deg, var(--uc-surface-strong) 0%, var(--uc-surface-muted) 100%);
        border: 1px solid rgba(139, 115, 85, 0.18);
        border-left: 6px solid var(--uc-orange);
        border-radius: 18px;
        padding: 0.85rem 0.95rem;
        box-shadow: var(--uc-shadow-soft);
    }

    .uc-stat-label {
        color: var(--uc-text-soft) !important;
        font-size: 0.84rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        line-height: 1.15;
        text-transform: uppercase;
    }

    .uc-stat-value {
        color: var(--uc-text) !important;
        font-size: 2rem;
        font-weight: 900;
        line-height: 1;
        margin-top: 0.42rem;
    }

    @media (max-width: 640px) {
        .uc-stat-grid {
            grid-template-columns: 1fr;
        }

        .uc-stat-value {
            font-size: 2.2rem;
        }
    }
</style>
        """
    )
    render_html_block("".join(tile_html))


def render_copy_to_clipboard_button(label: str, text: str, key: str) -> None:
    payload = json.dumps(text)
    button_id = f"copy-btn-{escape(key)}"
    status_id = f"copy-status-{escape(key)}"
    components.html(
        f"""
<div style="margin: 0.35rem 0 0.2rem 0;">
    <button
        id="{button_id}"
        onclick='navigator.clipboard.writeText({payload}).then(function() {{
            document.getElementById("{status_id}").innerText = "Copied to clipboard.";
        }}).catch(function() {{
            document.getElementById("{status_id}").innerText = "Copy failed. Select the text manually.";
        }});'
        style="
            width: 100%;
            border: none;
            border-radius: 12px;
            padding: 0.75rem 1rem;
            font-weight: 800;
            color: white;
            background: linear-gradient(180deg, #ea580c 0%, #c2410c 100%);
            cursor: pointer;
        "
    >
        {escape(label)}
    </button>
    <div id="{status_id}" style="padding-top: 0.45rem; font-size: 0.9rem; color: #625447;"></div>
</div>
        """,
        height=92,
    )


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
    render_html_block(
        """
<style>
    .uc-past-head {
        display: grid;
        grid-template-columns: minmax(220px, 1fr) 130px 130px;
        gap: 0.6rem;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--uc-muted);
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
        border-left: 8px solid var(--uc-neutral);
        background: var(--uc-neutral-bg);
        color: var(--uc-text);
        font-size: 0.92rem;
    }

    .uc-past-row.win {
        border-left-color: var(--uc-success);
        background: var(--uc-success-bg);
    }

    .uc-past-row.draw {
        border-left-color: var(--uc-info);
        background: var(--uc-info-bg);
    }

    .uc-past-row.loss {
        border-left-color: var(--uc-danger);
        background: var(--uc-danger-bg);
    }

    .uc-past-row.neutral {
        border-left-color: var(--uc-neutral);
        background: var(--uc-neutral-bg);
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
        """
    )

    render_html_block(
        """
<div class="uc-past-head">
    <div>Who Against Whom</div>
    <div>Result</div>
    <div>Points Gained</div>
</div>
        """
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

        render_html_block(
            f"""
<div class="uc-past-row {escape(row_state)}">
    <div class="uc-past-cell">{escape(who_cell)}</div>
    <div class="uc-past-cell">{escape(result_text)}</div>
    <div class="uc-past-cell uc-past-points">{escape(points_text)}</div>
</div>
            """
        )


def _leaderboard_avatar_html(row: LeaderboardRow) -> str:
    if row.photo_blob:
        mime_type = row.photo_mime_type or "image/jpeg"
        photo_b64 = base64.b64encode(row.photo_blob).decode("ascii")
        return (
            f'<img class="uc-board-avatar" src="data:{mime_type};base64,{photo_b64}" '
            f'alt="{escape(row.display_name)}">'
        )

    fallback = escape((row.display_name or "?")[:1].upper())
    return f'<div class="uc-board-avatar uc-board-avatar-fallback">{fallback}</div>'


def render_leaderboard(leaderboard: list[LeaderboardRow]) -> None:
    if not leaderboard:
        st.info("No completed matches yet. Leaderboard will appear once results are entered.")
        return

    render_html_block(
        """
<style>
    .uc-board-wrap {
        display: grid;
        gap: 0.75rem;
    }

    .uc-board-row {
        background: linear-gradient(180deg, var(--uc-surface-strong) 0%, var(--uc-surface-muted) 100%);
        border: 1px solid rgba(139, 115, 85, 0.18);
        border-left: 6px solid var(--uc-orange);
        border-radius: 18px;
        padding: 0.85rem 0.95rem;
        box-shadow: var(--uc-shadow-soft);
        position: relative;
    }

    .uc-board-top {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        gap: 0.75rem;
        align-items: center;
    }

    .uc-board-rank {
        min-width: 2.6rem;
        text-align: center;
        background: var(--uc-orange-soft);
        color: var(--uc-orange-ink);
        border: 1px solid rgba(234, 88, 12, 0.28);
        border-radius: 999px;
        padding: 0.3rem 0.55rem;
        font-size: 0.82rem;
        font-weight: 900;
        letter-spacing: 0.05em;
    }

    .uc-board-player {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        min-width: 0;
    }

    .uc-board-avatar {
        width: 2.9rem;
        height: 2.9rem;
        border-radius: 999px;
        object-fit: cover;
        border: 2px solid rgba(234, 88, 12, 0.28);
        flex-shrink: 0;
        display: block;
    }

    .uc-board-avatar-fallback {
        background: var(--uc-surface-muted);
        color: var(--uc-orange-ink);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 900;
        font-size: 1rem;
    }

    .uc-board-name-wrap {
        min-width: 0;
    }

    .uc-board-name-toggle {
        display: block;
        min-width: 0;
        cursor: pointer;
        text-decoration: none;
    }

    .uc-board-name {
        color: var(--uc-text);
        font-size: 1.02rem;
        font-weight: 900;
        line-height: 1.1;
        overflow-wrap: anywhere;
    }

    .uc-board-motto {
        color: var(--uc-text-soft);
        font-size: 0.84rem;
        font-weight: 600;
        line-height: 1.25;
        margin-top: 0.18rem;
        overflow-wrap: anywhere;
    }

    .uc-board-hint {
        color: var(--uc-muted);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        margin-top: 0.22rem;
        text-transform: uppercase;
    }

    .uc-board-total {
        text-align: right;
        min-width: 4.8rem;
    }

    .uc-board-total-label {
        color: var(--uc-muted);
        display: block;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.07em;
        text-transform: uppercase;
    }

    .uc-board-total-value {
        color: var(--uc-text);
        display: block;
        font-size: 1.26rem;
        font-weight: 900;
        line-height: 1.05;
    }

    .uc-board-stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
        gap: 0.45rem;
        margin-top: 0.75rem;
        padding-top: 0.75rem;
        border-top: 1px solid rgba(139, 115, 85, 0.18);
    }

    .uc-board-chip {
        background: rgba(0, 0, 0, 0.08);
        border: 1px solid rgba(139, 115, 85, 0.18);
        border-radius: 14px;
        color: var(--uc-text);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.55rem;
        padding: 0.5rem 0.75rem;
        font-size: 0.8rem;
        line-height: 1;
    }

    .uc-board-chip-label {
        color: var(--uc-muted);
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        white-space: nowrap;
    }

    .uc-board-chip-value {
        color: var(--uc-text);
        font-weight: 900;
        white-space: nowrap;
    }

    .uc-board-chip-value.is-ready {
        color: var(--uc-success);
    }

    .uc-board-chip-value.is-used {
        color: var(--uc-orange-dark);
    }

    .uc-board-toggle {
        position: absolute;
        inline-size: 1px;
        block-size: 1px;
        opacity: 0;
        pointer-events: none;
    }

    .uc-board-details {
        display: none;
    }

    .uc-board-toggle:checked ~ .uc-board-details {
        display: block;
    }

    .uc-board-toggle:checked ~ .uc-board-top .uc-board-name-toggle .uc-board-hint::before {
        content: "Hide details";
    }

    .uc-board-name-toggle .uc-board-hint::before {
        content: "Tap name for details";
    }

    @media (max-width: 640px) {
        .uc-board-row {
            padding: 0.8rem 0.85rem;
        }

        .uc-board-top {
            grid-template-columns: auto minmax(0, 1fr) auto;
        }

        .uc-board-total {
            min-width: auto;
            text-align: right;
        }

        .uc-board-total-value {
            font-size: 1.08rem;
        }

        .uc-board-stats {
            grid-template-columns: 1fr 1fr;
        }
    }
</style>
        """
    )

    row_html: list[str] = ['<div class="uc-board-wrap">']
    for row in leaderboard:
        doubler_status = "Used" if row.doubler_used else "Ready"
        doubler_class = "is-used" if row.doubler_used else "is-ready"
        toggle_id = f"uc-board-toggle-{row.user_id}"
        row_html.append(
            f"""
<div class="uc-board-row">
    <input class="uc-board-toggle" type="checkbox" id="{toggle_id}">
    <div class="uc-board-top">
        <div class="uc-board-rank">#{row.rank}</div>
        <div class="uc-board-player">
            {_leaderboard_avatar_html(row)}
            <div class="uc-board-name-wrap">
                <label class="uc-board-name-toggle" for="{toggle_id}">
                    <div class="uc-board-name">{escape(row.display_name)}</div>
                    <div class="uc-board-motto">{escape(row.motto or "No motto yet")}</div>
                    <div class="uc-board-hint"></div>
                </label>
            </div>
        </div>
        <div class="uc-board-total">
            <span class="uc-board-total-label">Total</span>
            <span class="uc-board-total-value">{row.total_points:.2f}</span>
        </div>
    </div>
    <div class="uc-board-details">
        <div class="uc-board-stats">
            <div class="uc-board-chip">
                <span class="uc-board-chip-label">Played</span>
                <span class="uc-board-chip-value">{row.matches_played}</span>
            </div>
            <div class="uc-board-chip">
                <span class="uc-board-chip-label">W-D-L</span>
                <span class="uc-board-chip-value">{row.wins}-{row.draws}-{row.losses}</span>
            </div>
            <div class="uc-board-chip">
                <span class="uc-board-chip-label">Bonus</span>
                <span class="uc-board-chip-value">{row.bonus_points:+.2f}</span>
            </div>
            <div class="uc-board-chip">
                <span class="uc-board-chip-label">Doubler</span>
                <span class="uc-board-chip-value {doubler_class}">{escape(doubler_status)}</span>
            </div>
        </div>
    </div>
</div>
            """
        )
    row_html.append("</div>")

    render_html_block("".join(row_html))
