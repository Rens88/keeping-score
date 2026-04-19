from __future__ import annotations

import random
import time

import streamlit as st

from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.services.minigame_service import (
    WHACK_A_MOLE_DURATION_SECONDS,
    WHACK_A_MOLE_HOLES,
    WHACK_A_MOLE_SLOT_DURATION_SECONDS,
    WHACK_A_MOLE_TOTAL_SLOTS,
)
from tournament_tracker.session import render_sidebar, require_login
from tournament_tracker.ui import render_stat_tiles

st.set_page_config(page_title="Whack-a-mole", page_icon="🔨", layout="wide")

services = get_runtime_services()
user = require_login(services, current_page="pages/15_Mini_Game.py")
render_sidebar(user)

if user.role != "participant":
    render_page_intro(
        "Whack-a-mole",
        "Admins beheren de game via de adminpagina.",
        eyebrow="Mini Game",
    )
    if st.button("Open admin minigamebeheer", width="stretch", type="primary"):
        st.switch_page("pages/16_Admin_Mini_Game.py")
    render_bottom_decoration()
    st.stop()

render_page_intro(
    "Whack-a-mole",
    "Raak de mol zo vaak mogelijk voordat hij weer verdwijnt. Je beste score telt voor de minigame-stand.",
    eyebrow="Mini Game",
)

GAME_STATE_KEY = "whack_a_mole_game_state"
GAME_LAST_RESULT_KEY = "whack_a_mole_last_result"
GAME_FEEDBACK_KEY = "whack_a_mole_feedback"

game_status = services.minigame_service.get_status()
player_summary = services.minigame_service.get_participant_summary(user.id)
leaderboard = services.minigame_service.list_leaderboard()


def _status_label(state: str) -> str:
    return {
        "disabled": "Nog niet vrijgegeven",
        "scheduled": "Ingepland",
        "live": "Live",
        "closed": "Gesloten",
    }.get(state, state.title())


def _clear_game_state() -> None:
    st.session_state.pop(GAME_STATE_KEY, None)
    st.session_state.pop(GAME_FEEDBACK_KEY, None)


def _start_new_game() -> None:
    sequence = [random.randrange(WHACK_A_MOLE_HOLES) for _ in range(WHACK_A_MOLE_TOTAL_SLOTS)]
    st.session_state[GAME_STATE_KEY] = {
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
    st.session_state.pop(GAME_LAST_RESULT_KEY, None)
    st.session_state.pop(GAME_FEEDBACK_KEY, None)


game_state = st.session_state.get(GAME_STATE_KEY)
if isinstance(game_state, dict) and game_state.get("user_id") != user.id:
    _clear_game_state()
    game_state = None

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
    st.write(
        "Elke run duurt ongeveer "
        f"**{WHACK_A_MOLE_DURATION_SECONDS} seconden** met **{WHACK_A_MOLE_TOTAL_SLOTS}** sprongen."
    )
    if game_status.opens_at is not None:
        st.caption(f"Open vanaf: {services.minigame_service.format_datetime(game_status.opens_at)}")
    if game_status.deadline_at is not None:
        st.caption(f"Deadline: {services.minigame_service.format_datetime(game_status.deadline_at)}")

    if game_status.state == "disabled":
        st.info("Whack-a-mole is nog niet vrijgegeven door de admin.")
    elif game_status.state == "scheduled":
        st.info(
            "Whack-a-mole opent op "
            f"{services.minigame_service.format_datetime(game_status.opens_at)}."
        )
    elif game_status.state == "closed":
        st.info("Whack-a-mole is gesloten. Je kunt hieronder nog wel de eindstand bekijken.")
    elif not isinstance(game_state, dict):
        if st.button("Start een nieuwe run", width="stretch", type="primary"):
            _start_new_game()
            st.rerun()


@st.fragment(run_every=0.25)
def render_live_game() -> None:
    state = st.session_state.get(GAME_STATE_KEY)
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
                st.session_state[GAME_LAST_RESULT_KEY] = {
                    "score": score,
                    "misses": total_slots - score,
                }
            except ValidationError as exc:
                st.session_state[GAME_LAST_RESULT_KEY] = {
                    "error": str(exc),
                }
            state["saved"] = True
            st.session_state[GAME_STATE_KEY] = state
            _clear_game_state()
            st.rerun()
        return

    current_slot = min(int(elapsed // slot_duration), total_slots - 1)
    active_hole = sequence[current_slot]
    attempted_current_slot = current_slot in attempted_slots
    score = len(hit_slots)
    remaining_seconds = max(0.0, total_duration - elapsed)
    feedback = st.session_state.get(GAME_FEEDBACK_KEY)

    st.progress(min(1.0, elapsed / total_duration), text=f"Nog {remaining_seconds:0.1f} seconden")
    st.write(f"Score: **{score}**")
    st.caption(f"Sprong {current_slot + 1} van {total_slots}")

    for row_start in range(0, WHACK_A_MOLE_HOLES, 3):
        cols = st.columns(3)
        for col_index, col in enumerate(cols):
            hole_index = row_start + col_index
            label = "🐹" if hole_index == active_hole else "🕳️"
            if col.button(label, width="stretch", key=f"whack_hole_{current_slot}_{hole_index}"):
                latest_state = st.session_state.get(GAME_STATE_KEY)
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
                    st.session_state[GAME_STATE_KEY] = latest_state
                    st.session_state[GAME_FEEDBACK_KEY] = {
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


if isinstance(game_state, dict):
    with st.container(border=True):
        st.subheader("Live run")
        render_live_game()

last_result = st.session_state.get(GAME_LAST_RESULT_KEY)
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
        if game_status.state == "live" and st.button("Nog een keer spelen", width="stretch"):
            _start_new_game()
            st.rerun()

with st.container(border=True):
    st.subheader("Minigame-stand")
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
    st.subheader("Hoe werkt het?")
    st.write("- Je beste score telt voor de Whack-a-mole-stand.")
    st.write("- De admin kent weekendpunten toe zodra de deadline is verstreken.")
    st.write("- Je kunt meerdere pogingen doen zolang de game live staat.")

render_bottom_decoration()
