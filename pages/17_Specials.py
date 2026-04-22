from __future__ import annotations

from html import escape

import streamlit as st

from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.branding import (
    render_bottom_decoration,
    render_form_field_label,
    render_html_block,
    render_page_intro,
)
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.services.special_service import (
    SPECIAL_CATCH_UP,
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
from tournament_tracker.ui import render_stat_tiles

st.set_page_config(page_title="Specials", page_icon="✨", layout="wide")

services = get_runtime_services()
user = require_login(services, current_page="pages/17_Specials.py")
render_sidebar(user, current_page="pages/17_Specials.py")

render_page_intro(
    "Specials",
    "Open a special to see what it does, who has it active right now, how often it has been used, and how many bonus points it has produced.",
)

definitions = services.special_service.list_special_definitions()
participant_specials = (
    services.special_service.get_participant_specials(user.id)
    if user.role == "participant"
    else {}
)
catch_up_threshold = services.special_service.get_catch_up_threshold()
leaderboard = services.ranking_service.compute_leaderboard()
special_player_stats = services.special_service.build_special_player_stats()
first_place_names = [row.display_name for row in leaderboard if row.rank == 1]


def _render_special_status_table(rows: list[dict[str, object]]) -> None:
    if not rows:
        st.info("No participants yet.")
        return

    table_rows: list[str] = []
    for row in rows:
        bonus_points = float(row["bonus_points"])
        status = str(row["status"])
        if status.startswith("active"):
            activation_label = "Active now"
            activation_class = "active"
        elif status.startswith("available"):
            activation_label = "Available now"
            activation_class = "available"
        elif status.startswith("used"):
            activation_label = "Used already"
            activation_class = "used"
        else:
            activation_label = "Not available"
            activation_class = "inactive"
        bonus_class = (
            "positive" if bonus_points > 0 else "negative" if bonus_points < 0 else "neutral"
        )
        bonus_text = f"{bonus_points:+.1f}" if abs(bonus_points) > 1e-9 else "0.0"
        table_rows.append(
            f"""
<tr>
    <td class="uc-specials-player">
        <div class="uc-specials-player-name">{escape(str(row["name"]))}</div>
        <div class="uc-specials-player-meta">{escape(str(row["status"]))}</div>
    </td>
    <td>
        <span class="uc-specials-pill {activation_class}">{escape(activation_label)}</span>
    </td>
    <td class="uc-specials-num">{escape(str(row["times_used"]))}</td>
    <td class="uc-specials-num {bonus_class}">{escape(bonus_text)}</td>
</tr>
            """
        )

    render_html_block(
        f"""
<style>
    .uc-specials-table-wrap {{
        overflow-x: auto;
        border: 1px solid rgba(139, 115, 85, 0.18);
        border-radius: 14px;
        box-shadow: var(--uc-shadow-soft);
        margin-top: 0.65rem;
    }}

    .uc-specials-table {{
        width: 100%;
        min-width: 620px;
        border-collapse: separate;
        border-spacing: 0;
    }}

    .uc-specials-table th {{
        background: var(--uc-surface-muted);
        color: var(--uc-muted);
        font-size: 0.74rem;
        font-weight: 800;
        letter-spacing: 0.07em;
        padding: 0.72rem;
        text-align: left;
        text-transform: uppercase;
    }}

    .uc-specials-table td {{
        background: var(--uc-surface-strong);
        border-top: 1px solid rgba(139, 115, 85, 0.12);
        color: var(--uc-text);
        padding: 0.72rem;
        vertical-align: top;
    }}

    .uc-specials-player-name {{
        color: var(--uc-text);
        font-size: 0.92rem;
        font-weight: 900;
        line-height: 1.15;
        overflow-wrap: anywhere;
    }}

    .uc-specials-player-meta {{
        color: var(--uc-muted);
        font-size: 0.78rem;
        font-weight: 600;
        line-height: 1.3;
        margin-top: 0.18rem;
        overflow-wrap: anywhere;
    }}

    .uc-specials-pill {{
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 800;
        line-height: 1;
        padding: 0.42rem 0.68rem;
        white-space: nowrap;
    }}

    .uc-specials-pill.active {{
        background: var(--uc-success-bg);
        color: var(--uc-success);
    }}

    .uc-specials-pill.available {{
        background: var(--uc-orange-soft);
        color: var(--uc-orange-ink);
    }}

    .uc-specials-pill.used {{
        background: var(--uc-info-bg);
        color: var(--uc-info);
    }}

    .uc-specials-pill.inactive {{
        background: rgba(148, 163, 184, 0.18);
        color: #94a3b8;
    }}

    .uc-specials-num {{
        font-size: 0.92rem;
        font-weight: 900;
        text-align: right;
        white-space: nowrap;
    }}

    .uc-specials-num.positive {{
        color: var(--uc-success);
    }}

    .uc-specials-num.negative {{
        color: var(--uc-danger);
    }}

    .uc-specials-num.neutral {{
        color: var(--uc-text);
    }}
</style>
<div class="uc-specials-table-wrap">
    <table class="uc-specials-table">
        <thead>
            <tr>
                <th>Player</th>
                <th>Current state</th>
                <th>Times used</th>
                <th>Bonus points</th>
            </tr>
        </thead>
        <tbody>
            {''.join(table_rows)}
        </tbody>
    </table>
</div>
        """
    )


def _render_participant_special_status(special_key: str) -> None:
    special = participant_specials.get(special_key)
    if special and special.is_active:
        st.success("Your status: active right now.")
    elif special and special.is_available:
        st.success("Your status: available to use.")
    elif special and special.activated_at and special_key not in {SPECIAL_CATCH_UP, SPECIAL_KING_OF_THE_HILL}:
        st.info("Your status: already used.")
    elif special_key == SPECIAL_KING_OF_THE_HILL:
        st.info("Your status: this moves with the current leader unless it is already live in a match.")
    elif special_key == SPECIAL_CATCH_UP:
        st.info(
            "Your status: automatic. It turns on only while your gap to number 1 is above the current threshold."
        )
    else:
        st.info("Your status: not unlocked yet.")


def _render_special_context_note(special_key: str, rows: list[dict[str, object]]) -> None:
    available_names = [
        str(row["name"])
        for row in rows
        if str(row["status"]).startswith("available") or str(row["status"]).startswith("active")
    ]
    active_names = [
        str(row["name"])
        for row in rows
        if str(row["status"]).startswith("active")
    ]

    if special_key == SPECIAL_KING_OF_THE_HILL:
        if active_names:
            st.caption("Current holder: " + ", ".join(active_names))
        elif available_names:
            st.caption("Current holder: " + ", ".join(available_names))
        elif len(first_place_names) > 1:
            st.info(
                "Nobody currently holds King of the Hill because first place is shared by "
                + ", ".join(first_place_names)
                + ". It only appears when there is one clear leader."
            )
        else:
            st.info("Nobody currently holds King of the Hill right now.")
    elif special_key == SPECIAL_WINNER_TAKES_ALL and available_names:
        st.caption("Currently available to: " + ", ".join(available_names))

if user.role == "participant":
    available_count = sum(
        1 for special in participant_specials.values() if special.is_available and not special.is_active
    )
    active_count = sum(1 for special in participant_specials.values() if special.is_active)
    render_stat_tiles(
        [
            ("Available now", str(available_count)),
            ("Active now", str(active_count)),
            ("Catch-up threshold", f"{catch_up_threshold:.1f}"),
        ]
    )

for definition in definitions:
    with st.expander(f"{definition.icon} {definition.title}", expanded=False):
        st.write(definition.summary)
        st.caption(definition.unlock_rule)

        if user.role == "participant":
            _render_participant_special_status(definition.key)

        _render_special_context_note(definition.key, special_player_stats.get(definition.key, []))
        st.caption("All players")
        _render_special_status_table(special_player_stats.get(definition.key, []))

if user.role == "admin":
    catch_up_user_ids = services.special_service.get_current_catch_up_user_ids()
    current_holders = [
        row.display_name
        for row in leaderboard
        if row.user_id in catch_up_user_ids
    ]
    special_rows = services.special_service.list_special_status_rows()
    participant_options = {
        f"{row['name']} (id {row['user_id']})": int(row["user_id"])
        for row in special_rows
    }

    with st.container(border=True):
        st.subheader("Admin Settings")
        with st.form("catch_up_threshold_form"):
            render_form_field_label(
                "Catch-up threshold in points",
                "Players more than this many points behind number 1 get automatic catch-up mode.",
            )
            threshold_value = st.number_input(
                "Catch-up threshold in points",
                min_value=0.0,
                step=1.0,
                value=float(catch_up_threshold),
                label_visibility="collapsed",
            )
            save_threshold = st.form_submit_button("Save threshold", width="stretch")

        if save_threshold:
            try:
                services.special_service.set_catch_up_threshold(
                    admin_user_id=user.id,
                    threshold_points=float(threshold_value),
                )
                st.success("Catch-up threshold saved.")
                st.rerun()
            except ValidationError as exc:
                st.error(str(exc))

        if current_holders:
            st.caption("Currently in catch-up mode: " + ", ".join(current_holders))
        else:
            st.caption("Nobody is currently far enough behind to trigger catch-up mode.")

    with st.container(border=True):
        st.subheader("Special Overview")
        if not special_rows:
            st.info("No participants yet.")
        else:
            st.dataframe(
                [
                    {
                        "name": row["name"],
                        "doubler": row[SPECIAL_DOUBLER],
                        "double_or_nothing": row[SPECIAL_DOUBLE_OR_NOTHING],
                        "king_of_the_hill": row[SPECIAL_KING_OF_THE_HILL],
                        "winner_takes_it_all": row[SPECIAL_WINNER_TAKES_ALL],
                        "catch_up_mode": row[SPECIAL_CATCH_UP],
                        "wheel_of_fortune": row[SPECIAL_WHEEL],
                        "match_fixer": row[SPECIAL_MATCH_FIXER],
                        "king_fixer": row[SPECIAL_KING_FIXER],
                        "dont_underestimate_my_power": row[SPECIAL_DONT_UNDERESTIMATE],
                    }
                    for row in special_rows
                ],
                width="stretch",
                hide_index=True,
            )

    with st.container(border=True):
        st.subheader("Per-person override")
        if not participant_options:
            st.info("No participants available for special overrides.")
        else:
            render_form_field_label("Participant")
            selected_participant_label = st.selectbox(
                "Participant",
                list(participant_options.keys()),
                label_visibility="collapsed",
            )
            selected_participant_id = participant_options[selected_participant_label]
            selected_row = next(
                row for row in special_rows if int(row["user_id"]) == selected_participant_id
            )

            st.caption(
                "Current statuses: "
                f"Doubler={selected_row[SPECIAL_DOUBLER]}, "
                f"Double-or-nothing={selected_row[SPECIAL_DOUBLE_OR_NOTHING]}, "
                f"King of the Hill={selected_row[SPECIAL_KING_OF_THE_HILL]}, "
                f"The winner takes it all={selected_row[SPECIAL_WINNER_TAKES_ALL]}, "
                f"Catch-up={selected_row[SPECIAL_CATCH_UP]}, "
                f"Wheel={selected_row[SPECIAL_WHEEL]}, "
                f"Match Fixer={selected_row[SPECIAL_MATCH_FIXER]}, "
                f"King Fixer={selected_row[SPECIAL_KING_FIXER]}, "
                f"Don't underestimate my power={selected_row[SPECIAL_DONT_UNDERESTIMATE]}"
            )

            special_options = {
                "Doubler": SPECIAL_DOUBLER,
                "Double-or-nothing": SPECIAL_DOUBLE_OR_NOTHING,
                "King of the Hill": SPECIAL_KING_OF_THE_HILL,
                "The winner takes it all": SPECIAL_WINNER_TAKES_ALL,
                "Catch-up mode": SPECIAL_CATCH_UP,
                "Wheel of Fortune": SPECIAL_WHEEL,
                "Match Fixer": SPECIAL_MATCH_FIXER,
                "King Fixer": SPECIAL_KING_FIXER,
                "Don't underestimate my power": SPECIAL_DONT_UNDERESTIMATE,
            }
            render_form_field_label("Special")
            selected_special_label = st.selectbox(
                "Special",
                list(special_options.keys()),
                label_visibility="collapsed",
            )
            selected_special_key = special_options[selected_special_label]
            current_override = selected_row[f"{selected_special_key}_override"]

            override_options = {
                "Follow automatic rules": "auto",
                "Force on": "on",
                "Force off": "off",
            }
            render_form_field_label("Override mode")
            override_index = list(override_options.values()).index(current_override)
            selected_override_label = st.selectbox(
                "Override mode",
                list(override_options.keys()),
                index=override_index,
                label_visibility="collapsed",
            )
            if st.button("Save special override", width="stretch", type="primary"):
                try:
                    services.special_service.set_special_override_mode(
                        participant_user_id=selected_participant_id,
                        special_key=selected_special_key,
                        mode=override_options[selected_override_label],
                        updated_by_user_id=user.id,
                    )
                    st.success("Special override saved.")
                    st.rerun()
                except ValidationError as exc:
                    st.error(str(exc))

render_bottom_decoration()
