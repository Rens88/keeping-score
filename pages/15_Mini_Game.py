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
    "Kies een game, zet een hoge score neer en pak weekendpunten zodra de deadline sluit.",
    eyebrow="Mini Games",
)

WHACK_GAME_STATE_KEY = "whack_a_mole_game_state"
WHACK_LAST_RESULT_KEY = "whack_a_mole_last_result"
WHACK_FEEDBACK_KEY = "whack_a_mole_feedback"
SIMON_GAME_STATE_KEY = "simon_says_game_state"
SIMON_LAST_RESULT_KEY = "simon_says_last_result"

SIMON_SEQUENCE_LENGTH = 20
SIMON_SHOW_COLOR_SECONDS = 1.0
SIMON_SHOW_GAP_SECONDS = 0.35
SIMON_STEP_SECONDS = SIMON_SHOW_COLOR_SECONDS + SIMON_SHOW_GAP_SECONDS
SIMON_COLOR_NAMES = ("Green", "Red", "Blue", "Yellow")
SIMON_COLOR_EMOJIS = ("🟢", "🔴", "🔵", "🟡")


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
    st.session_state[SIMON_GAME_STATE_KEY] = {
        "user_id": user.id,
        "started_at_epoch": time.time(),
        "started_at_iso": services.minigame_service.local_now().isoformat(),
        "sequence": [random.randrange(len(SIMON_COLOR_NAMES)) for _ in range(SIMON_SEQUENCE_LENGTH)],
        "round": 1,
        "input_index": 0,
        "phase": "show",
        "phase_started_at_epoch": time.time(),
        "saved": False,
        "message": "Kijk goed naar de eerste reeks.",
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


def _render_simon_pad(*, active_index: int | None, clickable: bool, button_prefix: str) -> None:
    for row_start in range(0, len(SIMON_COLOR_NAMES), 2):
        cols = st.columns(2)
        for col_offset, column in enumerate(cols):
            color_index = row_start + col_offset
            if color_index >= len(SIMON_COLOR_NAMES):
                continue
            is_active = active_index == color_index
            label = f"{SIMON_COLOR_EMOJIS[color_index]} {SIMON_COLOR_NAMES[color_index]}"
            if not clickable:
                active_style = (
                    "background: rgba(255, 122, 26, 0.22); "
                    "border-color: rgba(255, 122, 26, 0.95); "
                    "box-shadow: 0 0 0 2px rgba(255, 122, 26, 0.25); "
                    "transform: scale(1.02);"
                    if is_active
                    else
                    "background: rgba(255, 255, 255, 0.03); border-color: rgba(255, 255, 255, 0.12);"
                )
                column.markdown(
                    f"""
                    <div style="
                        border: 1px solid;
                        border-radius: 16px;
                        color: #f7efe5;
                        font-size: 1.05rem;
                        font-weight: 800;
                        min-height: 86px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        text-align: center;
                        padding: 0.9rem;
                        transition: all 120ms ease;
                        {active_style}
                    ">
                        {label}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                continue

            button_type = "primary" if is_active else "secondary"
            if column.button(
                label,
                width="stretch",
                type=button_type,
                key=f"{button_prefix}_{color_index}",
            ):
                state = st.session_state.get(SIMON_GAME_STATE_KEY)
                if not isinstance(state, dict) or state.get("phase") != "input":
                    st.rerun()

                sequence = [int(item) for item in state.get("sequence", [])]
                input_index = int(state.get("input_index", 0))
                current_round = int(state.get("round", 1))
                expected_color = sequence[input_index]
                if color_index != expected_color:
                    _finish_simon_says_run(
                        max(0, current_round - 1),
                        message="Net mis. Je score is opgeslagen.",
                    )
                    return

                if input_index + 1 >= current_round:
                    if current_round >= len(sequence):
                        _finish_simon_says_run(
                            current_round,
                            message="Perfect gespeeld. Je hebt de volledige reeks gehaald.",
                        )
                        return
                    state["round"] = current_round + 1
                    state["input_index"] = 0
                    state["phase"] = "show"
                    state["phase_started_at_epoch"] = time.time()
                    state["message"] = "Goed gedaan. Nieuwe reeks komt eraan."
                    st.session_state[SIMON_GAME_STATE_KEY] = state
                    st.rerun()

                state["input_index"] = input_index + 1
                state["message"] = "Goed. Ga door met de reeks."
                st.session_state[SIMON_GAME_STATE_KEY] = state
                st.rerun()


def _render_simon_reveal_header(*, active_color: int | None, current_step: int, total_steps: int) -> None:
    if active_color is None:
        st.info("Volgende kleur komt eraan...")
        return

    st.success(
        "Simon laat zien: "
        f"{SIMON_COLOR_EMOJIS[active_color]} {SIMON_COLOR_NAMES[active_color]} "
        f"(stap {current_step} van {total_steps})"
    )


@st.fragment(run_every=0.2)
def _render_live_simon_says() -> None:
    state = st.session_state.get(SIMON_GAME_STATE_KEY)
    if not isinstance(state, dict):
        return

    sequence = [int(item) for item in state.get("sequence", [])]
    current_round = int(state.get("round", 1))
    phase = str(state.get("phase", "show"))
    phase_started_at = float(state.get("phase_started_at_epoch", time.time()))
    message = str(state.get("message", ""))
    rounds_completed = max(0, current_round - 1)

    st.write(f"Score: **{rounds_completed}**")
    st.caption(f"Ronde {current_round} van {len(sequence)}")
    if message:
        st.caption(message)

    if phase == "show":
        elapsed = max(0.0, time.time() - phase_started_at)
        active_position = int(elapsed // SIMON_STEP_SECONDS)
        if active_position >= current_round:
            state["phase"] = "input"
            state["input_index"] = 0
            state["phase_started_at_epoch"] = time.time()
            state["message"] = "Jij bent. Klik de reeks na."
            st.session_state[SIMON_GAME_STATE_KEY] = state
            st.rerun()

        elapsed_within_step = elapsed - (active_position * SIMON_STEP_SECONDS)
        active_color = sequence[active_position] if elapsed_within_step < SIMON_SHOW_COLOR_SECONDS else None
        st.progress(min(1.0, elapsed / max(SIMON_STEP_SECONDS * current_round, 0.01)))
        st.caption("Simon zegt...")
        _render_simon_reveal_header(
            active_color=active_color,
            current_step=min(active_position + 1, current_round),
            total_steps=current_round,
        )
        _render_simon_pad(active_index=active_color, clickable=False, button_prefix=f"simon_show_{current_round}")
        return

    input_index = int(state.get("input_index", 0))
    st.progress(input_index / max(current_round, 1), text=f"Stap {input_index + 1} van {current_round}")
    _render_simon_pad(active_index=None, clickable=True, button_prefix=f"simon_input_{current_round}_{input_index}")


def _render_simon_says_tab() -> None:
    game_status, _player_summary = _render_game_status_box(SIMON_SAYS_SLUG, "Simon Says")
    game_state = st.session_state.get(SIMON_GAME_STATE_KEY)
    if isinstance(game_state, dict) and game_state.get("user_id") != user.id:
        _clear_state(SIMON_GAME_STATE_KEY, SIMON_LAST_RESULT_KEY)
        game_state = None

    with st.container(border=True):
        st.subheader("Simon Says")
        st.write(
            "Kijk naar de kleurreeks, onthoud hem en klik hem foutloos na. "
            "Je score is het aantal volledig voltooide rondes."
        )
        if game_status.state == "live" and not isinstance(game_state, dict):
            if st.button("Start Simon Says", width="stretch", type="primary"):
                _start_simon_says()
                st.rerun()

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
                    f"Je Simon Says score is **{int(last_result['score'])}**. {str(last_result['message'])}"
                )
            if game_status.state == "live" and st.button("Nog een keer spelen", width="stretch", key="simon_retry"):
                _start_simon_says()
                st.rerun()

    with st.container(border=True):
        st.subheader("Stand")
        _render_leaderboard_table(SIMON_SAYS_SLUG)

    with st.container(border=True):
        st.subheader("Hoe werkt het?")
        st.write("- Elke volledig gehaalde ronde telt als 1 punt.")
        st.write("- Zodra je een fout maakt, wordt je run opgeslagen.")
        st.write("- De admin kent weekendpunten toe zodra de deadline is verstreken.")


whack_tab, simon_tab = st.tabs(["Whack-a-mole", "Simon Says"])

with whack_tab:
    _render_whack_a_mole_tab()

with simon_tab:
    _render_simon_says_tab()

render_bottom_decoration()
