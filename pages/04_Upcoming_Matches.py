from __future__ import annotations

import streamlit as st

from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.services.betting_service import BET_OUTCOME_OPTIONS
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.services.special_service import (
    SPECIAL_DONT_UNDERESTIMATE,
    SPECIAL_DOUBLER,
    SPECIAL_DOUBLE_OR_NOTHING,
    SPECIAL_KING_FIXER,
    SPECIAL_KING_OF_THE_HILL,
    SPECIAL_MATCH_FIXER,
    SPECIAL_WINNER_TAKES_ALL,
    SPECIAL_WHEEL,
)
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import OUTCOME_BADGE, format_datetime, render_match_card, render_stat_tiles

st.set_page_config(page_title="Upcoming Events", page_icon="📅", layout="wide")

services = get_runtime_services()
user = require_login(services, current_page="pages/04_Upcoming_Matches.py")
render_sidebar(user, current_page="pages/04_Upcoming_Matches.py")

render_page_intro(
    "Upcoming Events",
    "Check the next fixtures and multi-competitor games, play specials on your own matches, and place small bets before kickoff.",
)

if user.role == "participant":
    services.special_service.sync_current_special_state()
    participant_specials = services.special_service.get_participant_specials(user.id)
    available_specials = [
        special_key
        for special_key in (
            SPECIAL_DOUBLER,
            SPECIAL_DOUBLE_OR_NOTHING,
            SPECIAL_KING_OF_THE_HILL,
            SPECIAL_WINNER_TAKES_ALL,
            SPECIAL_WHEEL,
            SPECIAL_MATCH_FIXER,
            SPECIAL_KING_FIXER,
            SPECIAL_DONT_UNDERESTIMATE,
        )
        if participant_specials.get(special_key)
        and participant_specials[special_key].is_available
        and not participant_specials[special_key].is_active
    ]
    active_specials = [
        special_key
        for special_key in (
            SPECIAL_DOUBLER,
            SPECIAL_DOUBLE_OR_NOTHING,
            SPECIAL_KING_OF_THE_HILL,
            SPECIAL_WINNER_TAKES_ALL,
            SPECIAL_WHEEL,
            SPECIAL_MATCH_FIXER,
            SPECIAL_KING_FIXER,
            SPECIAL_DONT_UNDERESTIMATE,
        )
        if participant_specials.get(special_key) and participant_specials[special_key].is_active
    ]
    render_stat_tiles(
        [
            ("Free bet balance", f"{services.betting_service.get_available_balance(user.id):.1f}"),
            ("Open bets", str(len(services.repo.list_match_bets(participant_user_id=user.id, include_settled=False)))),
            ("Available specials", str(len(available_specials))),
            ("Active specials", str(len(active_specials))),
        ]
    )

all_cards = services.match_service.list_matches_for_view(statuses=["live", "upcoming"])
live_cards = [card for card in all_cards if card.status == "live"]
upcoming_cards = [card for card in all_cards if card.status == "upcoming"]
ranked_games = services.ranked_event_service.list_events(statuses=["live", "upcoming"])
live_ranked_games = [event for event in ranked_games if event.status == "live"]
upcoming_ranked_games = [event for event in ranked_games if event.status == "upcoming"]
ranked_event_ids = [event.id for event in ranked_games]
ranked_competitor_rows = (
    services.ranked_event_service.get_event_competitor_rows(ranked_event_ids)
    if ranked_event_ids
    else []
)
ranked_competitors_by_event: dict[int, list[str]] = {}
for row in ranked_competitor_rows:
    event_id = int(row.get("event_id", row.get("ranked_event_id")))
    ranked_competitors_by_event.setdefault(event_id, []).append(
        str(
            row.get("display_name")
            or row.get("username")
            or row.get("email")
            or f"User {row.get('participant_user_id')}"
        )
    )
all_match_ids = [card.match_id for card in all_cards]
open_bets = services.repo.list_match_bets(match_ids=all_match_ids, include_settled=False)
profile_rows_by_user_id = services.repo.get_profiles_by_user_ids(
    [bet.participant_user_id for bet in open_bets]
)
bets_by_match_id: dict[int, list[object]] = {}
for bet in open_bets:
    bets_by_match_id.setdefault(bet.match_id, []).append(bet)


def _user_is_in_match(match_card) -> bool:
    for side in match_card.sides.values():
        participants = side.get("participants")
        if isinstance(participants, list):
            for participant in participants:
                if getattr(participant, "user_id", None) == user.id:
                    return True
    return False


def _render_special_actions(match_card) -> None:
    if user.role != "participant":
        return

    match = services.repo.get_match(match_card.match_id)
    if not match or not _user_is_in_match(match_card):
        return

    specials = services.special_service.get_participant_specials(user.id)
    if not services.special_service.match_allows_pre_match_actions(match):
        active_match_icons: list[str] = []
        for side in match_card.sides.values():
            participants = side.get("participants")
            if isinstance(participants, list):
                for participant in participants:
                    if getattr(participant, "user_id", None) == user.id:
                        active_match_icons = list(getattr(participant, "special_icons", ()))
        if active_match_icons:
            st.caption(f"Your played specials for this match: {' '.join(active_match_icons)}")
        return

    action_specs = [
        (SPECIAL_DOUBLER, "Play doubler"),
        (SPECIAL_DOUBLE_OR_NOTHING, "Play double-or-nothing"),
        (SPECIAL_KING_OF_THE_HILL, "Play King of the Hill"),
        (SPECIAL_WINNER_TAKES_ALL, "Play The winner takes it all"),
        (SPECIAL_WHEEL, "Spin Wheel of Fortune"),
        (SPECIAL_MATCH_FIXER, "Play Match Fixer"),
        (SPECIAL_KING_FIXER, "Play King Fixer"),
        (SPECIAL_DONT_UNDERESTIMATE, "Play Don't underestimate my power"),
    ]
    available_specs = [
        (special_key, label)
        for special_key, label in action_specs
        if specials.get(special_key) and specials[special_key].is_available and not specials[special_key].is_active
    ]
    if not available_specs:
        return

    st.caption("Your match specials")
    action_columns = st.columns(len(available_specs))
    for column, (special_key, label) in zip(action_columns, available_specs):
        if column.button(label, width="stretch", key=f"special_{special_key}_{match_card.match_id}"):
            try:
                services.special_service.activate_match_special(
                    participant_user_id=user.id,
                    special_key=special_key,
                    match_id=match_card.match_id,
                    actor_user_id=user.id,
                )
                st.success(f"{services.special_service.special_label(special_key)} activated.")
                st.rerun()
            except ValidationError as exc:
                st.error(str(exc))


def _participant_name(user_id: int) -> str:
    row = profile_rows_by_user_id.get(user_id, {})
    return str(
        row.get("display_name")
        or row.get("username")
        or row.get("email")
        or f"User {user_id}"
    )


def _match_side_label(match_card, side_number: int) -> str:
    side = match_card.sides.get(side_number, {})
    participants = side.get("participants")
    participant_names = [
        getattr(participant, "display_name", "")
        for participant in participants
        if hasattr(participant, "display_name")
    ] if isinstance(participants, list) else []
    side_name = str(side.get("side_name") or "").strip()
    return side_name or " + ".join(name for name in participant_names if name) or f"Side {side_number}"


def _bet_outcome_label(match_card, predicted_outcome: str) -> str:
    if predicted_outcome == "side1_win":
        return f"{_match_side_label(match_card, 1)} to win"
    if predicted_outcome == "side2_win":
        return f"{_match_side_label(match_card, 2)} to win"
    return "Draw"


def _render_public_bets(match_card) -> None:
    match_bets = bets_by_match_id.get(match_card.match_id, [])
    with st.container(border=True):
        st.markdown("**Current bets**")
        if not match_bets:
            st.caption("No open bets on this match yet.")
            return

        ordered_bets = sorted(match_bets, key=lambda bet: (bet.updated_at, bet.participant_user_id), reverse=True)
        if user.role == "admin":
            st.dataframe(
                [
                    {
                        "bettor": _participant_name(bet.participant_user_id),
                        "prediction": _bet_outcome_label(match_card, bet.predicted_outcome),
                        "stake": f"{int(bet.stake_points)} point" if int(bet.stake_points) == 1 else f"{int(bet.stake_points)} points",
                        "updated": format_datetime(bet.updated_at),
                    }
                    for bet in ordered_bets
                ],
                width="stretch",
                hide_index=True,
            )
            return

        total_stake = int(sum(bet.stake_points for bet in ordered_bets))
        unique_bettor_names: list[str] = []
        seen_user_ids: set[int] = set()
        for bet in ordered_bets:
            if bet.participant_user_id in seen_user_ids:
                continue
            seen_user_ids.add(bet.participant_user_id)
            unique_bettor_names.append(_participant_name(bet.participant_user_id))

        total_stake_text = f"{total_stake} point" if total_stake == 1 else f"{total_stake} points"
        st.caption(f"{len(unique_bettor_names)} participant(s) placed a bet. Total stake: {total_stake_text}.")
        st.dataframe(
            [{"bettor": name, "status": "Bet placed"} for name in unique_bettor_names],
            width="stretch",
            hide_index=True,
        )


def _render_betting_box(match_card) -> None:
    if user.role != "participant":
        return

    match = services.repo.get_match(match_card.match_id)
    if not match:
        return

    existing_bet = services.betting_service.get_existing_bet(
        match_id=match_card.match_id,
        participant_user_id=user.id,
    )

    with st.container(border=True):
        st.markdown("**Betting**")
        if existing_bet:
            stake_text = f"{existing_bet.stake_points:.0f}"
            outcome_text = OUTCOME_BADGE.get(existing_bet.predicted_outcome, existing_bet.predicted_outcome)
            if existing_bet.settled_at:
                net_text = f"{existing_bet.net_points:+.1f}" if existing_bet.net_points is not None else "0.0"
                st.caption(f"Your settled bet: {stake_text} on {outcome_text} ({net_text}).")
            else:
                st.caption(f"Your current bet: {stake_text} on {outcome_text}.")

        if not services.special_service.match_allows_pre_match_actions(match):
            st.info("Betting is closed for this match.")
            return

        stake_options = set(services.betting_service.allowed_stakes_for_participant(user.id))
        if existing_bet and existing_bet.settled_at is None:
            stake_options.add(int(existing_bet.stake_points))
        ordered_stakes = [stake for stake in sorted(stake_options) if stake in {1, 2}]
        if not ordered_stakes:
            st.info("You need at least 1.0 free point before you can place a bet.")
            return

        default_outcome = existing_bet.predicted_outcome if existing_bet else BET_OUTCOME_OPTIONS[0]
        default_outcome_index = BET_OUTCOME_OPTIONS.index(default_outcome)
        default_stake = int(existing_bet.stake_points) if existing_bet else ordered_stakes[0]
        default_stake_index = ordered_stakes.index(default_stake) if default_stake in ordered_stakes else 0

        with st.form(f"bet_form_{match_card.match_id}"):
            render_form_field_label("Predicted outcome")
            predicted_outcome = st.selectbox(
                "Predicted outcome",
                BET_OUTCOME_OPTIONS,
                index=default_outcome_index,
                format_func=lambda value: OUTCOME_BADGE.get(value, value),
                label_visibility="collapsed",
            )
            render_form_field_label("Stake")
            stake_points = st.selectbox(
                "Stake",
                ordered_stakes,
                index=default_stake_index,
                format_func=lambda value: f"{value} point" if value == 1 else f"{value} points",
                label_visibility="collapsed",
            )
            submit_bet = st.form_submit_button("Save bet", width="stretch")

        if submit_bet:
            try:
                services.betting_service.place_bet(
                    participant_user_id=user.id,
                    match_id=match_card.match_id,
                    predicted_outcome=predicted_outcome,
                    stake_points=int(stake_points),
                )
                st.success("Bet saved.")
                st.rerun()
            except ValidationError as exc:
                st.error(str(exc))


def _render_ranked_game_card(event) -> None:
    with st.container(border=True):
        st.subheader(f"#{event.id} - {event.title}")
        st.caption(
            f"Status: {event.status.title()} | Scheduled: {format_datetime(event.scheduled_at)} | Order: {event.scheduled_order or '-'}"
        )
        competitors = ranked_competitors_by_event.get(event.id, [])
        if competitors:
            st.markdown("**Competitors**")
            for name in competitors:
                st.write(f"- {name}")
        award_scheme = services.ranked_event_service.parse_award_scheme(event.award_scheme)
        st.caption("Weekend points: " + ", ".join(f"P{index}={points}" for index, points in enumerate(award_scheme, start=1)))


if live_cards or live_ranked_games:
    st.subheader("Live")
    if live_cards:
        st.markdown("**Head-to-head**")
        for card in live_cards:
            render_match_card(card)
            _render_betting_box(card)
            _render_public_bets(card)
    if live_ranked_games:
        st.markdown("**Multi-competitor**")
        for event in live_ranked_games:
            _render_ranked_game_card(event)

st.subheader("Upcoming")
if not upcoming_cards and not upcoming_ranked_games:
    st.info("No upcoming events scheduled yet.")
else:
    if upcoming_cards:
        st.markdown("**Head-to-head**")
        for card in upcoming_cards:
            render_match_card(card)
            _render_special_actions(card)
            _render_betting_box(card)
            _render_public_bets(card)
    if upcoming_ranked_games:
        st.markdown("**Multi-competitor**")
        for event in upcoming_ranked_games:
            _render_ranked_game_card(event)

render_bottom_decoration()
