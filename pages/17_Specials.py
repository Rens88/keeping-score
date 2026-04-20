from __future__ import annotations

import streamlit as st

from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.services.special_service import (
    SPECIAL_CATCH_UP,
    SPECIAL_DOUBLER,
    SPECIAL_DOUBLE_OR_NOTHING,
    SPECIAL_KING_OF_THE_HILL,
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
    "See what each special does, which ones you currently hold, and when catch-up mode kicks in.",
)

definitions = services.special_service.list_special_definitions()
participant_specials = (
    services.special_service.get_participant_specials(user.id)
    if user.role == "participant"
    else {}
)
catch_up_threshold = services.special_service.get_catch_up_threshold()

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
    with st.container(border=True):
        st.subheader(f"{definition.icon} {definition.title}")
        st.write(definition.summary)
        st.caption(definition.unlock_rule)

        if user.role == "participant":
            special = participant_specials.get(definition.key)
            if special and special.is_active:
                st.success("Status: active right now.")
            elif special and special.is_available:
                st.success("Status: available to use.")
            elif special and special.activated_at and definition.key not in {SPECIAL_CATCH_UP, SPECIAL_KING_OF_THE_HILL}:
                st.info("Status: already used.")
            elif definition.key == SPECIAL_KING_OF_THE_HILL:
                st.info("Status: this moves with the current leader unless it is already live in a match.")
            elif definition.key == SPECIAL_CATCH_UP:
                st.info(
                    "Status: automatic. It turns on only while your gap to number 1 is above the current threshold."
                )
            else:
                st.info("Status: not unlocked yet.")

if user.role == "admin":
    leaderboard = services.ranking_service.compute_leaderboard()
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
                f"Wheel={selected_row[SPECIAL_WHEEL]}"
            )

            special_options = {
                "Doubler": SPECIAL_DOUBLER,
                "Double-or-nothing": SPECIAL_DOUBLE_OR_NOTHING,
                "King of the Hill": SPECIAL_KING_OF_THE_HILL,
                "The winner takes it all": SPECIAL_WINNER_TAKES_ALL,
                "Catch-up mode": SPECIAL_CATCH_UP,
                "Wheel of Fortune": SPECIAL_WHEEL,
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
