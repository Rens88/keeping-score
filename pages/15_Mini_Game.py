from __future__ import annotations

import random
import time

import streamlit as st

from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.services.minigame_service import (
    SIMON_SAYS_SLUG,
    WHACK_A_MOLE_DURATION_SECONDS,
    WHACK_A_MOLE_HOLES,
    WHACK_A_MOLE_SLUG,
    WHACK_A_MOLE_SLOT_DURATION_SECONDS,
    WHACK_A_MOLE_TOTAL_SLOTS,
)
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import render_stat_tiles

st.set_page_config(page_title="Mini Games", page_icon="🔨", layout="wide")

services = get_runtime_services()
user = require_login(services, current_page="pages/15_Mini_Game.py")
render_sidebar(user)

if user.role != "participant":
    render_page_intro(
        "Mini Games",
        "Admins beheren de games via de adminpagina.",
        eyebrow="Mini Games",
    )
    if st.button("Open admin mini games", width="stretch", type="primary"):
        st.switch_page("pages/16_Admin_Mini_Game.py")
    render_bottom_decoration()
    st.stop()

render_page_intro(
    "Mini Games",
    "Kies een game, set a high score, and grab weekend points once the deadline closes.",
    eyebrow="Mini Games",
)

WHACK_GAME_STATE_KEY = "whack_a_mole_game_state"
WHACK_LAST_RESULT_KEY = "whack_a_mole_last_result"
WHACK_FEEDBACK_KEY = "whack_a_mole_feedback"
SIMON_GAME_STATE_KEY = "simon_says_game_state"
SIMON_LAST_RESULT_KEY = "simon_says_last_result"

SIMON_SEQUENCE_LENGTH = 20
SIMON_FIRST_SHOW_COLOR_SECONDS = 1.65
SIMON_SHOW_COLOR_SECONDS = 0.95
SIMON_SHOW_GAP_SECONDS = 0.35
SIMON_SHOW_SPEEDUP_EVERY_ROUNDS = 4
SIMON_SHOW_SPEEDUP_FACTOR = 0.8
SIMON_MIN_SHOW_COLOR_SECONDS = 0.2
SIMON_BASE_COLOR_COUNT = 4
SIMON_ADD_COLOR_EVERY_ROUNDS = 4
SIMON_MOVE_LAYOUT_EVERY_ROUNDS = 8
SIMON_WORD_MODE_START_ROUND = 13
SIMON_STROOP_MODE_START_ROUND = 17
SIMON_COLOR_POOL = (
    {"name": "Green", "ink": "#22c55e"},
    {"name": "Red", "ink": "#ef4444"},
    {"name": "Blue", "ink": "#3b82f6"},
    {"name": "Yellow", "ink": "#facc15"},
    {"name": "Purple", "ink": "#a855f7"},
    {"name": "Orange", "ink": "#fb923c"},
    {"name": "Pink", "ink": "#ec4899"},
    {"name": "Teal", "ink": "#14b8a6"},
)

current_user_profile = services.repo.get_user_with_profile(user.id)
current_player_name = str(
    getattr(current_user_profile, "display_name", None)
    or getattr(current_user_profile, "username", None)
    or getattr(current_user_profile, "email", None)
    or user.username
    or user.email
    or ""
)
SIMON_GAME_LABEL = "Siemen Says" if "siemen" in current_player_name.lower() else "Simon Says"


def _status_label(state: str) -> str:
    return {
        "disabled": "Nog niet vrijgegeven",
        "scheduled": "Ingepland",
        "live": "Live",
        "closed": "Gesloten",
    }.get(state, state.title())


def _clear_state(*keys: str) -> None:
    for key in keys:
        st.session_state.pop(key, None)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    clean = hex_color.lstrip("#")
    if len(clean) != 6:
        return f"rgba(255, 255, 255, {alpha})"
    red = int(clean[0:2], 16)
    green = int(clean[2:4], 16)
    blue = int(clean[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _render_leaderboard_table(game_slug: str) -> None:
    leaderboard = services.minigame_service.list_leaderboard(game_slug)
    if not leaderboard:
        st.info("Nog geen gespeelde runs.")
        return

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


def _render_game_status_box(game_slug: str, live_label: str) -> tuple[object, object]:
    game_status = services.minigame_service.get_status(game_slug=game_slug)
    player_summary = services.minigame_service.get_participant_summary(user.id, game_slug=game_slug)
    render_stat_tiles(
        [
            ("Game status", _status_label(game_status.state)),
            ("Mijn beste score", str(player_summary.best_score)),
            ("Pogingen", str(player_summary.attempts)),
            ("Weekendpunten uit game", f"{player_summary.awarded_points:.0f}"),
        ]
    )

    with st.container(border=True):
        st.subheader("Speelvenster")
        if game_status.opens_at is not None:
            st.caption(f"Open vanaf: {services.minigame_service.format_datetime(game_status.opens_at)}")
        if game_status.deadline_at is not None:
            st.caption(f"Deadline: {services.minigame_service.format_datetime(game_status.deadline_at)}")

        if game_status.state == "disabled":
            st.info(f"{live_label} is nog niet vrijgegeven door de admin.")
        elif game_status.state == "scheduled":
            st.info(
                f"{live_label} opent op "
                f"{services.minigame_service.format_datetime(game_status.opens_at)}."
            )
        elif game_status.state == "closed":
            st.info(f"{live_label} is gesloten. Je kunt hieronder nog wel de eindstand bekijken.")

    return game_status, player_summary


def _start_whack_a_mole() -> None:
    sequence = [random.randrange(WHACK_A_MOLE_HOLES) for _ in range(WHACK_A_MOLE_TOTAL_SLOTS)]
    st.session_state[WHACK_GAME_STATE_KEY] = {
        "user_id": user.id,
        "started_at_epoch": time.time(),
        "started_at_iso": services.minigame_service.local_now().isoformat(),
        "sequence": sequence,
        "attempted_slots": [],
        "hit_slots": [],
        "total_slots": WHACK_A_MOLE_TOTAL_SLOTS,
        "slot_duration_seconds": WHACK_A_MOLE_SLOT_DURATION_SECONDS,
        "saved": False,
    }
    _clear_state(WHACK_LAST_RESULT_KEY, WHACK_FEEDBACK_KEY)


@st.fragment(run_every=0.25)
def _render_live_whack_a_mole() -> None:
    state = st.session_state.get(WHACK_GAME_STATE_KEY)
    if not isinstance(state, dict):
        return

    total_slots = int(state["total_slots"])
    slot_duration = float(state["slot_duration_seconds"])
    total_duration = total_slots * slot_duration
    elapsed = max(0.0, time.time() - float(state["started_at_epoch"]))
    attempted_slots = set(int(slot) for slot in state.get("attempted_slots", []))
    hit_slots = set(int(slot) for slot in state.get("hit_slots", []))
    sequence = [int(slot) for slot in state.get("sequence", [])]

    if elapsed >= total_duration:
        if not bool(state.get("saved")):
            score = len(hit_slots)
            try:
                services.minigame_service.record_run(
                    user_id=user.id,
                    game_slug=WHACK_A_MOLE_SLUG,
                    score=score,
                    duration_seconds=WHACK_A_MOLE_DURATION_SECONDS,
                    started_at=services.minigame_service.parse_optional_datetime(
                        str(state.get("started_at_iso", ""))
                    ),
                    metadata={
                        "slots_total": total_slots,
                        "hits": score,
                        "attempted_slots": len(attempted_slots),
                    },
                )
                st.session_state[WHACK_LAST_RESULT_KEY] = {
                    "score": score,
                    "misses": total_slots - score,
                }
            except ValidationError as exc:
                st.session_state[WHACK_LAST_RESULT_KEY] = {"error": str(exc)}
            state["saved"] = True
            st.session_state[WHACK_GAME_STATE_KEY] = state
            _clear_state(WHACK_GAME_STATE_KEY, WHACK_FEEDBACK_KEY)
            st.rerun()
        return

    current_slot = min(int(elapsed // slot_duration), total_slots - 1)
    active_hole = sequence[current_slot]
    attempted_current_slot = current_slot in attempted_slots
    score = len(hit_slots)
    remaining_seconds = max(0.0, total_duration - elapsed)
    feedback = st.session_state.get(WHACK_FEEDBACK_KEY)

    st.progress(min(1.0, elapsed / total_duration), text=f"Nog {remaining_seconds:0.1f} seconden")
    st.write(f"Score: **{score}**")
    st.caption(f"Sprong {current_slot + 1} van {total_slots}")

    for row_start in range(0, WHACK_A_MOLE_HOLES, 3):
        cols = st.columns(3)
        for col_index, col in enumerate(cols):
            hole_index = row_start + col_index
            label = "🐹" if hole_index == active_hole else "🕳️"
            if col.button(label, width="stretch", key=f"whack_hole_{current_slot}_{hole_index}"):
                latest_state = st.session_state.get(WHACK_GAME_STATE_KEY)
                if not isinstance(latest_state, dict):
                    st.rerun()
                latest_attempted = set(int(slot) for slot in latest_state.get("attempted_slots", []))
                latest_hits = set(int(slot) for slot in latest_state.get("hit_slots", []))
                if current_slot not in latest_attempted:
                    latest_attempted.add(current_slot)
                    is_hit = hole_index == active_hole
                    if is_hit:
                        latest_hits.add(current_slot)
                    latest_state["attempted_slots"] = sorted(latest_attempted)
                    latest_state["hit_slots"] = sorted(latest_hits)
                    st.session_state[WHACK_GAME_STATE_KEY] = latest_state
                    st.session_state[WHACK_FEEDBACK_KEY] = {
                        "slot": current_slot,
                        "is_hit": is_hit,
                    }
                st.rerun()

    if attempted_current_slot and isinstance(feedback, dict) and feedback.get("slot") == current_slot:
        if feedback.get("is_hit"):
            st.success("Raak!")
        else:
            st.warning("Mis. Wachten op de volgende sprong.")
    elif not attempted_current_slot:
        st.caption("Klik snel op de mol voordat hij weer verspringt.")
    else:
        st.caption("Volgende sprong komt eraan.")


def _render_whack_a_mole_tab() -> None:
    game_status, _player_summary = _render_game_status_box(WHACK_A_MOLE_SLUG, "Whack-a-mole")
    game_state = st.session_state.get(WHACK_GAME_STATE_KEY)
    if isinstance(game_state, dict) and game_state.get("user_id") != user.id:
        _clear_state(WHACK_GAME_STATE_KEY, WHACK_LAST_RESULT_KEY, WHACK_FEEDBACK_KEY)
        game_state = None

    with st.container(border=True):
        st.subheader("Whack-a-mole")
        st.write(
            "Elke run duurt ongeveer "
            f"**{WHACK_A_MOLE_DURATION_SECONDS} seconden** met **{WHACK_A_MOLE_TOTAL_SLOTS}** sprongen."
        )
        if game_status.state == "live" and not isinstance(game_state, dict):
            if st.button("Start een nieuwe Whack-a-mole run", width="stretch", type="primary"):
                _start_whack_a_mole()
                st.rerun()

    if isinstance(game_state, dict):
        with st.container(border=True):
            st.subheader("Live run")
            _render_live_whack_a_mole()

    last_result = st.session_state.get(WHACK_LAST_RESULT_KEY)
    if isinstance(last_result, dict):
        with st.container(border=True):
            st.subheader("Laatste run")
            if "error" in last_result:
                st.error(str(last_result["error"]))
            else:
                st.success(
                    f"Je run is opgeslagen met **{int(last_result['score'])}** punten "
                    f"en **{int(last_result['misses'])}** gemiste sprongen."
                )
            if game_status.state == "live" and st.button("Nog een keer spelen", width="stretch", key="whack_retry"):
                _start_whack_a_mole()
                st.rerun()

    with st.container(border=True):
        st.subheader("Stand")
        _render_leaderboard_table(WHACK_A_MOLE_SLUG)

    with st.container(border=True):
        st.subheader("Hoe werkt het?")
        st.write("- Je beste score telt voor de Whack-a-mole-stand.")
        st.write("- De admin kent weekendpunten toe zodra de deadline is verstreken.")
        st.write("- Je kunt meerdere pogingen doen zolang de game live staat.")


def _start_simon_says() -> None:
    initial_color_count = min(SIMON_BASE_COLOR_COUNT, len(SIMON_COLOR_POOL))
    st.session_state[SIMON_GAME_STATE_KEY] = {
        "user_id": user.id,
        "started_at_epoch": time.time(),
        "started_at_iso": services.minigame_service.local_now().isoformat(),
        "sequence": [random.randrange(initial_color_count)],
        "round": 1,
        "input_index": 0,
        "phase": "show",
        "layout_seed": random.randrange(10_000_000),
        "saved": False,
        "message": "Watch the color pattern carefully. If words appear later, ignore the words.",
    }
    _clear_state(SIMON_LAST_RESULT_KEY)


def _finish_simon_says_run(score: int, *, message: str) -> None:
    state = st.session_state.get(SIMON_GAME_STATE_KEY)
    if not isinstance(state, dict) or bool(state.get("saved")):
        return

    elapsed_total = max(1, int(round(time.time() - float(state["started_at_epoch"]))))
    try:
        services.minigame_service.record_run(
            user_id=user.id,
            game_slug=SIMON_SAYS_SLUG,
            score=max(0, int(score)),
            duration_seconds=elapsed_total,
            started_at=services.minigame_service.parse_optional_datetime(str(state.get("started_at_iso", ""))),
            metadata={
                "round_reached": int(state.get("round", 1)),
                "sequence_length": SIMON_SEQUENCE_LENGTH,
            },
        )
        st.session_state[SIMON_LAST_RESULT_KEY] = {
            "score": max(0, int(score)),
            "message": message,
        }
    except ValidationError as exc:
        st.session_state[SIMON_LAST_RESULT_KEY] = {"error": str(exc)}

    state["saved"] = True
    st.session_state[SIMON_GAME_STATE_KEY] = state
    _clear_state(SIMON_GAME_STATE_KEY)
    st.rerun()


def _simon_visible_color_ids(round_number: int) -> list[int]:
    extra_colors = max(0, round_number - 1) // SIMON_ADD_COLOR_EVERY_ROUNDS
    visible_count = min(SIMON_BASE_COLOR_COUNT + extra_colors, len(SIMON_COLOR_POOL))
    return list(range(visible_count))


def _simon_layout_for_round(round_number: int, *, layout_seed: int) -> list[int]:
    layout = _simon_visible_color_ids(round_number)
    layout_epoch = max(0, round_number - 1) // SIMON_MOVE_LAYOUT_EVERY_ROUNDS
    if layout_epoch <= 0:
        return layout

    shuffled = layout[:]
    random.Random(layout_seed + (layout_epoch * 977)).shuffle(shuffled)
    return shuffled


def _simon_display_name_for_color(actual_color_index: int, round_number: int) -> str:
    visible_ids = _simon_visible_color_ids(round_number)
    actual_name = str(SIMON_COLOR_POOL[actual_color_index]["name"])
    if round_number < SIMON_STROOP_MODE_START_ROUND or len(visible_ids) <= 1:
        return actual_name

    shift = 1 + ((round_number - SIMON_STROOP_MODE_START_ROUND) % (len(visible_ids) - 1))
    rotated = visible_ids[shift:] + visible_ids[:shift]
    mapped_word_index = rotated[visible_ids.index(actual_color_index)]
    return str(SIMON_COLOR_POOL[mapped_word_index]["name"])


def _simon_round_intro_message(round_number: int) -> str:
    if round_number >= SIMON_STROOP_MODE_START_ROUND:
        return "STROOP level! Follow the color of the letters, not the word."
    if round_number >= SIMON_WORD_MODE_START_ROUND:
        return "New twist: the buttons now show color words, but you still follow the colors."
    if round_number > 1 and (round_number - 1) % SIMON_MOVE_LAYOUT_EVERY_ROUNDS == 0:
        return "New twist: the colors moved to different positions."
    if round_number > 1 and (round_number - 1) % SIMON_ADD_COLOR_EVERY_ROUNDS == 0:
        return "New twist: an extra color has been added."
    return "Well done. A new color pattern is coming."


def _append_simon_color_for_round(state: dict[str, object], round_number: int) -> None:
    sequence = [int(item) for item in state.get("sequence", [])]
    if len(sequence) >= SIMON_SEQUENCE_LENGTH:
        state["sequence"] = sequence
        return
    visible_ids = _simon_visible_color_ids(round_number)
    if not visible_ids:
        visible_ids = [0]
    sequence.append(random.choice(visible_ids))
    state["sequence"] = sequence


def _simon_show_speed_factor(round_number: int) -> float:
    speedup_steps = max(0, round_number - 1) // SIMON_SHOW_SPEEDUP_EVERY_ROUNDS
    return SIMON_SHOW_SPEEDUP_FACTOR ** speedup_steps


def _simon_show_duration_for_position(position: int, round_number: int) -> float:
    base_duration = SIMON_FIRST_SHOW_COLOR_SECONDS if position == 1 else SIMON_SHOW_COLOR_SECONDS
    return max(SIMON_MIN_SHOW_COLOR_SECONDS, base_duration * _simon_show_speed_factor(round_number))


def _simon_total_show_duration(round_number: int) -> float:
    if round_number <= 0:
        return 0.01
    color_total = sum(
        _simon_show_duration_for_position(position, round_number)
        for position in range(1, round_number + 1)
    )
    gap_total = max(0, round_number - 1) * SIMON_SHOW_GAP_SECONDS
    return max(color_total + gap_total, 0.01)


def _render_simon_reveal_banner(*, actual_color_index: int, step_number: int, total_steps: int) -> str:
    color_name = str(SIMON_COLOR_POOL[actual_color_index]["name"])
    ink = str(SIMON_COLOR_POOL[actual_color_index]["ink"])
    glow = _hex_to_rgba(ink, 0.38)
    surface = _hex_to_rgba(ink, 0.24)
    return f"""
        <div style="
            margin-bottom: 0.9rem;
            padding: 1rem 1.1rem;
            border-radius: 20px;
            border: 1px solid {_hex_to_rgba(ink, 0.92)};
            background: linear-gradient(180deg, {surface} 0%, rgba(24, 19, 15, 0.96) 100%);
            box-shadow: 0 0 0 2px {glow}, 0 22px 40px rgba(0, 0, 0, 0.24);
            text-align: center;
        ">
            <div style="
                color: rgba(247, 239, 229, 0.88);
                font-size: 0.82rem;
                font-weight: 800;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                margin-bottom: 0.4rem;
            ">
                Watch this color
            </div>
            <div style="
                color: {ink};
                font-size: 2rem;
                font-weight: 900;
                line-height: 1.05;
                text-shadow: 0 0 20px {glow};
            ">
                {color_name}
            </div>
            <div style="
                color: rgba(247, 239, 229, 0.76);
                font-size: 0.88rem;
                font-weight: 700;
                margin-top: 0.45rem;
            ">
                Step {step_number} of {total_steps}
            </div>
        </div>
    """


def _render_simon_tile(
    *,
    actual_color_index: int,
    round_number: int,
    active: bool,
) -> str:
    ink = str(SIMON_COLOR_POOL[actual_color_index]["ink"])
    display_name = _simon_display_name_for_color(actual_color_index, round_number)
    color_surface = _hex_to_rgba(ink, 0.26 if active else 0.06)
    border_color = _hex_to_rgba(ink, 0.98 if active else 0.42)
    shadow = (
        f"box-shadow: 0 0 0 3px {_hex_to_rgba(ink, 0.34)}, 0 26px 44px rgba(0, 0, 0, 0.24); transform: scale(1.02);"
        if active
        else "box-shadow: 0 8px 18px rgba(0, 0, 0, 0.10);"
    )
    return f"""
        <div style="
            min-height: 126px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 0.25rem;
            padding: 0.9rem 0.8rem;
            border-radius: 18px;
            border: 1px solid {border_color};
            background: linear-gradient(180deg, {color_surface} 0%, rgba(24, 19, 15, 0.94) 100%);
            text-align: center;
            opacity: {1 if active else 0.42};
            transition: all 160ms ease;
            {shadow}
        ">
            <div style="
                color: {ink};
                font-size: 1.45rem;
                font-weight: 900;
                letter-spacing: 0.02em;
                line-height: 1.05;
            ">
                {display_name}
            </div>
        </div>
    """


def _render_simon_button_style(
    *,
    marker_id: str,
    actual_color_index: int,
    active: bool = False,
) -> str:
    ink = str(SIMON_COLOR_POOL[actual_color_index]["ink"])
    surface = _hex_to_rgba(ink, 0.18 if active else 0.12)
    border = _hex_to_rgba(ink, 0.96 if active else 0.60)
    glow = _hex_to_rgba(ink, 0.28 if active else 0.18)
    return f"""
        <div id="{marker_id}"></div>
        <style>
        #{marker_id} + div[data-testid="stButton"] > button {{
            min-height: 112px;
            border-radius: 18px;
            border: 1px solid {border};
            background: linear-gradient(180deg, {surface} 0%, rgba(24, 19, 15, 0.94) 100%);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.18);
            transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
        }}
        #{marker_id} + div[data-testid="stButton"] > button:hover {{
            border-color: {_hex_to_rgba(ink, 0.96)};
            box-shadow: 0 0 0 2px {glow}, 0 18px 32px rgba(0, 0, 0, 0.24);
            transform: translateY(-1px);
        }}
        #{marker_id} + div[data-testid="stButton"] > button p {{
            color: {ink};
            font-size: 1.35rem;
            font-weight: 900;
            line-height: 1.1;
            letter-spacing: 0.01em;
            text-shadow: 0 0 18px {glow};
        }}
        </style>
    """


def _render_simon_pad(
    *,
    round_number: int,
    layout_seed: int,
    active_index: int | None,
    clickable: bool,
    button_prefix: str,
) -> int | None:
    clicked_color_index: int | None = None
    layout = _simon_layout_for_round(round_number, layout_seed=layout_seed)

    for row_start in range(0, len(layout), 2):
        cols = st.columns(2)
        for col_offset, column in enumerate(cols):
            layout_position = row_start + col_offset
            if layout_position >= len(layout):
                continue
            color_index = layout[layout_position]
            is_active = active_index == color_index
            display_name = _simon_display_name_for_color(color_index, round_number)
            if not clickable:
                column.markdown(
                    _render_simon_tile(
                        actual_color_index=color_index,
                        round_number=round_number,
                        active=is_active,
                    ),
                    unsafe_allow_html=True,
                )
                continue

            column.markdown(
                _render_simon_button_style(
                    marker_id=f"simon_btn_{button_prefix}_{round_number}_{color_index}",
                    actual_color_index=color_index,
                    active=is_active,
                ),
                unsafe_allow_html=True,
            )
            if column.button(
                display_name,
                width="stretch",
                key=f"{button_prefix}_{color_index}",
            ):
                clicked_color_index = color_index

    return clicked_color_index


def _render_live_simon_says() -> None:
    state = st.session_state.get(SIMON_GAME_STATE_KEY)
    if not isinstance(state, dict):
        return

    sequence = [int(item) for item in state.get("sequence", [])]
    current_round = int(state.get("round", 1))
    phase = str(state.get("phase", "show"))
    layout_seed = int(state.get("layout_seed", 0))
    message = str(state.get("message", ""))
    rounds_completed = max(0, current_round - 1)

    st.write(f"Score: **{rounds_completed}**")
    st.caption(f"Ronde {current_round} van {SIMON_SEQUENCE_LENGTH}")
    if message:
        st.caption(message)
    if current_round >= SIMON_STROOP_MODE_START_ROUND:
        st.warning("STROOP level: follow the colors of the letters, not the words.")
    elif current_round >= SIMON_WORD_MODE_START_ROUND:
        st.info("The buttons now show words, but you must still follow the pattern of the colors.")
    else:
        st.info("Follow the pattern of the colors. If words appear, ignore the words.")

    if phase == "show":
        total_duration = _simon_total_show_duration(current_round)
        progress_placeholder = st.empty()
        status_placeholder = st.empty()
        pad_placeholder = st.empty()
        elapsed_before = 0.0
        for active_position, active_color in enumerate(sequence[:current_round], start=1):
            progress_placeholder.progress(
                min(1.0, elapsed_before / total_duration),
                text=f"Stap {active_position} van {current_round}",
            )
            status_placeholder.markdown(
                _render_simon_reveal_banner(
                    actual_color_index=active_color,
                    step_number=active_position,
                    total_steps=current_round,
                ),
                unsafe_allow_html=True,
            )
            with pad_placeholder.container():
                _render_simon_pad(
                    round_number=current_round,
                    layout_seed=layout_seed,
                    active_index=active_color,
                    clickable=False,
                    button_prefix="simon_show_static",
                )
            show_duration = _simon_show_duration_for_position(active_position, current_round)
            time.sleep(show_duration)
            elapsed_before += show_duration
            if active_position < current_round:
                progress_placeholder.progress(
                    min(1.0, elapsed_before / total_duration),
                    text=f"Stap {active_position} van {current_round}",
                )
                status_placeholder.info("Get ready for the next color...")
                with pad_placeholder.container():
                    _render_simon_pad(
                        round_number=current_round,
                        layout_seed=layout_seed,
                        active_index=None,
                        clickable=False,
                        button_prefix="simon_show_static",
                    )
                time.sleep(SIMON_SHOW_GAP_SECONDS)
                elapsed_before += SIMON_SHOW_GAP_SECONDS

        state["phase"] = "input"
        state["input_index"] = 0
        state["message"] = "Your turn. Repeat the color pattern in the same order. Ignore the words."
        st.session_state[SIMON_GAME_STATE_KEY] = state
        st.rerun()
        return

    input_index = int(state.get("input_index", 0))
    st.progress(input_index / max(current_round, 1), text=f"Stap {input_index + 1} van {current_round}")
    clicked_color = _render_simon_pad(
        round_number=current_round,
        layout_seed=layout_seed,
        active_index=None,
        clickable=True,
        button_prefix="simon_input",
    )
    if clicked_color is None:
        return

    latest_state = st.session_state.get(SIMON_GAME_STATE_KEY)
    if not isinstance(latest_state, dict) or latest_state.get("phase") != "input":
        st.rerun()

    sequence = [int(item) for item in latest_state.get("sequence", [])]
    current_round = int(latest_state.get("round", 1))
    input_index = int(latest_state.get("input_index", 0))
    expected_color = sequence[input_index]
    if clicked_color != expected_color:
        _finish_simon_says_run(
            max(0, current_round - 1),
            message="Net mis. Je score is opgeslagen.",
        )
        return

    if input_index + 1 >= current_round:
        if current_round >= SIMON_SEQUENCE_LENGTH:
            _finish_simon_says_run(
                current_round,
                message="Perfect gespeeld. Je hebt de volledige reeks gehaald.",
            )
            return
        latest_state["round"] = current_round + 1
        latest_state["input_index"] = 0
        latest_state["phase"] = "show"
        latest_state["message"] = _simon_round_intro_message(current_round + 1)
        _append_simon_color_for_round(latest_state, current_round + 1)
        st.session_state[SIMON_GAME_STATE_KEY] = latest_state
        st.rerun()

    latest_state["input_index"] = input_index + 1
    latest_state["message"] = "Correct. Keep following the colors in order."
    st.session_state[SIMON_GAME_STATE_KEY] = latest_state
    st.rerun()


def _render_simon_says_tab() -> None:
    game_status, _player_summary = _render_game_status_box(SIMON_SAYS_SLUG, SIMON_GAME_LABEL)
    game_state = st.session_state.get(SIMON_GAME_STATE_KEY)
    if isinstance(game_state, dict) and game_state.get("user_id") != user.id:
        _clear_state(SIMON_GAME_STATE_KEY, SIMON_LAST_RESULT_KEY)
        game_state = None

    with st.container(border=True):
        st.subheader(SIMON_GAME_LABEL)
        st.write(
            "Watch the color pattern, remember it, and repeat it without mistakes. "
            "If words appear, follow the colors, not the words. "
            "Your score is the number of fully completed rounds."
        )
        if game_status.state == "live" and not isinstance(game_state, dict):
            if st.button(f"Start {SIMON_GAME_LABEL}", width="stretch", type="primary"):
                _start_simon_says()
                game_state = st.session_state.get(SIMON_GAME_STATE_KEY)

    if isinstance(game_state, dict):
        with st.container(border=True):
            st.subheader("Live run")
            _render_live_simon_says()

    last_result = st.session_state.get(SIMON_LAST_RESULT_KEY)
    if isinstance(last_result, dict):
        with st.container(border=True):
            st.subheader("Laatste run")
            if "error" in last_result:
                st.error(str(last_result["error"]))
            else:
                st.success(
                    f"Je {SIMON_GAME_LABEL} score is **{int(last_result['score'])}**. {str(last_result['message'])}"
                )
            if game_status.state == "live" and st.button("Nog een keer spelen", width="stretch", key="simon_retry"):
                _start_simon_says()
                game_state = st.session_state.get(SIMON_GAME_STATE_KEY)

    with st.container(border=True):
        st.subheader("Stand")
        _render_leaderboard_table(SIMON_SAYS_SLUG)

    with st.container(border=True):
        st.subheader("Hoe werkt het?")
        st.write("- Elke volledig gehaalde ronde telt als 1 punt.")
        st.write("- Zodra je een fout maakt, wordt je run opgeslagen.")
        st.write("- Om de 4 rondes komt er een kleur bij en om de 8 rondes wisselen de kleuren van plek.")
        st.write("- Vanaf ronde 13 zie je kleurwoorden, maar je blijft de kleuren volgen.")
        st.write("- Vanaf ronde 17 begint het STROOP level: volg de kleur van de letters, niet het woord.")
        st.write("- De admin kent weekendpunten toe zodra de deadline is verstreken.")


whack_tab, simon_tab = st.tabs(["Whack-a-mole", SIMON_GAME_LABEL])

with whack_tab:
    _render_whack_a_mole_tab()

with simon_tab:
    _render_simon_says_tab()

render_bottom_decoration()
