from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from typing import Optional

import streamlit as st

from tournament_tracker.branding import render_html_block
from tournament_tracker.models import LeaderboardRow, MatchBet
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
    icons = list(participant.special_icons)
    if participant.has_doubler_on_match and not any(icon.startswith("⚡") for icon in icons):
        icons.append("⚡x2")
    if icons:
        label += " " + " ".join(icons)
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
def render_match_card(card: MatchCard) -> None:
    with st.container(border=True):
        status_label = STATUS_BADGE.get(card.status, card.status)
        header = f"#{card.match_id} - {card.game_type}"
        st.subheader(header)
        st.caption(
            f"Status: {status_label} | Scheduled: {format_datetime(card.scheduled_at)} | Order: {card.scheduled_order or '-'}"
        )
        st.markdown(f"**{_who_vs_who_text(card)}**")

        for side_number in (1, 2):
            side = card.sides.get(side_number, {"participants": []})
            side_name = side.get("side_name") or f"Side {side_number}"
            participants = side.get("participants")
            names = " | ".join(
                participant_label(p)
                for p in participants
                if isinstance(p, MatchCardParticipant)
            ) if isinstance(participants, list) else ""
            st.write(f"{side_name}: {names or 'No players assigned'}")

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
    side1_names = " + ".join(participant_label(p) for p in _participants_for_side(card, 1)) or "Side 1"
    side2_names = " + ".join(participant_label(p) for p in _participants_for_side(card, 2)) or "Side 2"
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


def _points_gained_for_viewer(
    card: MatchCard,
    viewer_user_id: int,
    personal_outcome: str,
    points_by_match_and_user: Optional[dict[tuple[int, int], float]] = None,
) -> float:
    if points_by_match_and_user is not None:
        mapped_points = points_by_match_and_user.get((card.match_id, viewer_user_id))
        if mapped_points is not None:
            return mapped_points
    base_points = POINTS[personal_outcome]
    participants = _participants_for_side(card, 1) + _participants_for_side(card, 2)
    viewer = next((p for p in participants if p.user_id == viewer_user_id), None)
    if viewer and viewer.has_doubler_on_match:
        return base_points * 2
    return base_points


def _past_match_side_label(card: MatchCard, side_number: int) -> str:
    side = card.sides.get(side_number, {"participants": []})
    side_name = side.get("side_name")
    if isinstance(side_name, str) and side_name.strip():
        return side_name.strip()
    participant_names = " + ".join(p.display_name for p in _participants_for_side(card, side_number))
    return participant_names or f"Side {side_number}"


def _bet_prediction_label(card: MatchCard, predicted_outcome: str) -> str:
    if predicted_outcome == "side1_win":
        return f"{_past_match_side_label(card, 1)} to win"
    if predicted_outcome == "side2_win":
        return f"{_past_match_side_label(card, 2)} to win"
    return "Draw"


def _user_row_name(user_id: int, user_rows_by_user_id: Optional[dict[int, dict[str, object]]]) -> str:
    if not user_rows_by_user_id:
        return f"User {user_id}"
    row = user_rows_by_user_id.get(user_id, {})
    return str(
        row.get("display_name")
        or row.get("username")
        or row.get("email")
        or f"User {user_id}"
    )


def _past_match_table_html(title: str, rows: list[dict[str, object]], empty_text: str) -> str:
    if not rows:
        return (
            f'<div class="uc-past-section">'
            f'<div class="uc-past-section-title">{escape(title)}</div>'
            f'<div class="uc-past-empty">{escape(empty_text)}</div>'
            f"</div>"
        )

    table_rows: list[str] = []
    for row in rows:
        table_rows.append(
            f"""
<tr class="{escape(str(row['state']))}">
    <td class="uc-past-person-cell">
        <div class="uc-past-name">{escape(str(row['name']))}</div>
        <div class="uc-past-meta">{escape(str(row['detail']))}</div>
    </td>
    <td class="uc-past-num">{escape(str(row['outcome_points_text']))}</td>
    <td class="uc-past-num">{escape(str(row['special_points_text']))}</td>
    <td class="uc-past-num">{escape(str(row['betting_points_text']))}</td>
    <td class="uc-past-num">{escape(str(row['total_points_text']))}</td>
</tr>
            """
        )

    return (
        f"""
<div class="uc-past-section">
    <div class="uc-past-section-title">{escape(title)}</div>
    <div class="uc-past-table-wrap">
        <table class="uc-past-table">
            <thead>
                <tr>
                    <th>Person</th>
                    <th>Outcome</th>
                    <th>Special</th>
                    <th>Betting</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
    </div>
</div>
        """
    )


def render_past_matches_compact(
    cards: list[MatchCard],
    viewer_user_id: int,
    points_by_match_and_user: Optional[dict[tuple[int, int], float]] = None,
    match_bets: Optional[list[MatchBet]] = None,
    user_rows_by_user_id: Optional[dict[int, dict[str, object]]] = None,
) -> None:
    render_html_block(
        """
<style>
    .uc-past-summary {
        color: var(--uc-text);
        font-weight: 800;
        margin-bottom: 0.25rem;
    }

    .uc-past-meta-line {
        color: var(--uc-muted);
        font-size: 0.82rem;
        font-weight: 600;
        margin-bottom: 0.65rem;
    }

    .uc-past-section {
        margin-top: 0.9rem;
    }

    .uc-past-section-title {
        color: var(--uc-muted);
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.38rem;
    }

    .uc-past-table-wrap {
        overflow-x: auto;
        border: 1px solid rgba(139, 115, 85, 0.18);
        border-radius: 14px;
        box-shadow: var(--uc-shadow-soft);
    }

    .uc-past-table {
        width: 100%;
        min-width: 620px;
        border-collapse: separate;
        border-spacing: 0;
    }

    .uc-past-table th {
        background: var(--uc-surface-muted);
        color: var(--uc-muted);
        font-size: 0.74rem;
        font-weight: 800;
        letter-spacing: 0.07em;
        padding: 0.68rem 0.72rem;
        text-align: right;
        text-transform: uppercase;
    }

    .uc-past-table th:first-child {
        text-align: left;
    }

    .uc-past-table td {
        background: var(--uc-surface-strong);
        border-top: 1px solid rgba(139, 115, 85, 0.12);
        color: var(--uc-text);
        padding: 0.72rem;
        vertical-align: top;
    }

    .uc-past-table tbody tr.win td {
        background: var(--uc-success-bg);
    }

    .uc-past-table tbody tr.draw td {
        background: var(--uc-info-bg);
    }

    .uc-past-table tbody tr.loss td {
        background: var(--uc-danger-bg);
    }

    .uc-past-table tbody tr.neutral td {
        background: var(--uc-neutral-bg);
    }

    .uc-past-table tbody tr.win td:first-child {
        border-left: 6px solid var(--uc-success);
    }

    .uc-past-table tbody tr.draw td:first-child {
        border-left: 6px solid var(--uc-info);
    }

    .uc-past-table tbody tr.loss td:first-child {
        border-left: 6px solid var(--uc-danger);
    }

    .uc-past-table tbody tr.neutral td:first-child {
        border-left: 6px solid var(--uc-neutral);
    }

    .uc-past-person-cell {
        min-width: 220px;
    }

    .uc-past-name {
        color: var(--uc-text);
        font-size: 0.92rem;
        font-weight: 900;
        line-height: 1.15;
        overflow-wrap: anywhere;
    }

    .uc-past-meta {
        color: var(--uc-muted);
        font-size: 0.76rem;
        font-weight: 600;
        line-height: 1.3;
        margin-top: 0.2rem;
        overflow-wrap: anywhere;
    }

    .uc-past-num {
        font-weight: 900;
        text-align: right;
        white-space: nowrap;
    }

    .uc-past-empty {
        background: var(--uc-surface-strong);
        border: 1px solid rgba(139, 115, 85, 0.16);
        border-radius: 14px;
        color: var(--uc-text-soft);
        padding: 0.8rem 0.9rem;
    }
</style>
        """
    )
    del viewer_user_id  # The full match breakdown is no longer viewer-specific.

    bets_by_match: dict[int, list[MatchBet]] = {}
    betting_points_by_match_and_user: dict[tuple[int, int], float] = {}
    for bet in match_bets or []:
        bets_by_match.setdefault(bet.match_id, []).append(bet)
        if bet.net_points is not None:
            betting_points_by_match_and_user[(bet.match_id, bet.participant_user_id)] = float(bet.net_points)

    row_order = {"win": 0, "draw": 1, "loss": 2, "neutral": 3}

    for card in cards:
        result_label = OUTCOME_BADGE.get(card.outcome or "", card.outcome or "Result pending")
        expander_label = f"#{card.match_id} {card.game_type} | {result_label} | {format_datetime(card.scheduled_at)}"
        with st.expander(expander_label, expanded=False):
            st.markdown(f'<div class="uc-past-summary">{escape(_who_vs_who_text(card))}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="uc-past-meta-line">Order {card.scheduled_order or "-"}'
                + (f" | Notes: {escape(card.result_notes)}" if card.result_notes else "")
                + "</div>",
                unsafe_allow_html=True,
            )

            competitor_rows: list[dict[str, object]] = []
            for side_number in (1, 2):
                side_label = _past_match_side_label(card, side_number)
                for participant in _participants_for_side(card, side_number):
                    personal_outcome = _personal_outcome(card, participant.user_id) or "neutral"
                    outcome_points = POINTS.get(personal_outcome, 0.0)
                    performance_total = (
                        points_by_match_and_user.get((card.match_id, participant.user_id), outcome_points)
                        if points_by_match_and_user is not None
                        else outcome_points
                    )
                    special_points = round(float(performance_total) - float(outcome_points), 4)
                    betting_points = round(
                        betting_points_by_match_and_user.get((card.match_id, participant.user_id), 0.0),
                        4,
                    )
                    total_points = round(float(performance_total) + betting_points, 4)
                    competitor_rows.append(
                        {
                            "state": personal_outcome,
                            "name": participant_label(participant),
                            "detail": f"{side_label} | {PERSONAL_OUTCOME_LABEL.get(personal_outcome, 'Played')}",
                            "outcome_points_text": f"{outcome_points:.1f}",
                            "special_points_text": f"{special_points:+.1f}" if abs(special_points) > 1e-9 else "0.0",
                            "betting_points_text": f"{betting_points:+.1f}" if abs(betting_points) > 1e-9 else "0.0",
                            "total_points_text": f"{total_points:.1f}",
                        }
                    )

            competitor_rows.sort(
                key=lambda row: (row_order.get(str(row["state"]), 3), str(row["name"]).lower())
            )

            bettor_rows: list[dict[str, object]] = []
            for bet in sorted(
                bets_by_match.get(card.match_id, []),
                key=lambda current: (current.updated_at, current.participant_user_id),
                reverse=True,
            ):
                betting_points = (
                    float(bet.net_points)
                    if bet.net_points is not None
                    else float(bet.stake_points if bet.predicted_outcome == card.outcome else -bet.stake_points)
                )
                bet_state = "win" if betting_points > 0 else "loss" if betting_points < 0 else "draw"
                bettor_rows.append(
                    {
                        "state": bet_state,
                        "name": _user_row_name(bet.participant_user_id, user_rows_by_user_id),
                        "detail": f"{_bet_prediction_label(card, bet.predicted_outcome)} | stake {bet.stake_points:.0f}",
                        "outcome_points_text": "0.0",
                        "special_points_text": "0.0",
                        "betting_points_text": f"{betting_points:+.1f}" if abs(betting_points) > 1e-9 else "0.0",
                        "total_points_text": f"{betting_points:.1f}",
                    }
                )

            bettor_rows.sort(
                key=lambda row: (row_order.get(str(row["state"]), 3), str(row["name"]).lower())
            )

            render_html_block(
                _past_match_table_html(
                    "Competitors",
                    competitor_rows,
                    "No competitors were recorded for this match.",
                )
                + _past_match_table_html(
                    "Bets on this match",
                    bettor_rows,
                    "No bets were placed on this match.",
                )
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


def render_leaderboard(
    leaderboard: list[LeaderboardRow],
    point_ledger_by_user_id: Optional[dict[int, list[dict[str, object]]]] = None,
) -> None:
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

    .uc-board-ledger-wrap {
        margin-top: 0.75rem;
        padding-top: 0.75rem;
        border-top: 1px solid rgba(139, 115, 85, 0.18);
    }

    .uc-board-ledger-title {
        color: var(--uc-muted);
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.45rem;
    }

    .uc-board-ledger {
        display: grid;
        gap: 0.45rem;
        max-height: 14rem;
        overflow-y: auto;
        padding-right: 0.2rem;
    }

    .uc-board-ledger-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 0.55rem;
        align-items: start;
        background: rgba(0, 0, 0, 0.05);
        border: 1px solid rgba(139, 115, 85, 0.14);
        border-radius: 12px;
        padding: 0.55rem 0.7rem;
    }

    .uc-board-ledger-summary {
        color: var(--uc-text);
        font-size: 0.86rem;
        font-weight: 700;
        line-height: 1.25;
        overflow-wrap: anywhere;
    }

    .uc-board-ledger-time {
        color: var(--uc-muted);
        font-size: 0.74rem;
        font-weight: 600;
        margin-top: 0.18rem;
    }

    .uc-board-ledger-points {
        color: var(--uc-text);
        font-size: 0.9rem;
        font-weight: 900;
        white-space: nowrap;
    }

    .uc-board-ledger-points.positive {
        color: var(--uc-success);
    }

    .uc-board-ledger-points.negative {
        color: var(--uc-danger);
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
        ledger_rows = point_ledger_by_user_id.get(row.user_id, []) if point_ledger_by_user_id else []
        ledger_html_parts = [
            """
        <div class="uc-board-ledger-wrap">
            <div class="uc-board-ledger-title">Point Log</div>
            <div class="uc-board-ledger">
            """
        ]
        if not ledger_rows:
            ledger_html_parts.append(
                """
                <div class="uc-board-ledger-row">
                    <div class="uc-board-ledger-summary">No point history yet.</div>
                    <div class="uc-board-ledger-points">0.0</div>
                </div>
                """
            )
        else:
            for ledger_row in ledger_rows:
                points_value = float(ledger_row["points"])
                points_class = "positive" if points_value >= 0 else "negative"
                ledger_html_parts.append(
                    f"""
                <div class="uc-board-ledger-row">
                    <div>
                        <div class="uc-board-ledger-summary">{escape(str(ledger_row["summary"]))}</div>
                        <div class="uc-board-ledger-time">{escape(format_datetime(str(ledger_row["timestamp"])))}</div>
                    </div>
                    <div class="uc-board-ledger-points {points_class}">{points_value:+.1f}</div>
                </div>
                    """
                )
        ledger_html_parts.append(
            """
            </div>
        </div>
            """
        )
        ledger_html = "".join(ledger_html_parts)
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
        {ledger_html}
    </div>
</div>
            """
        )
    row_html.append("</div>")

    render_html_block("".join(row_html))
