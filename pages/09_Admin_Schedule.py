from __future__ import annotations

from datetime import datetime, time

import streamlit as st

from tournament_tracker.bootstrap import get_services
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.services.match_service import DEFAULT_GAME_TYPES
from tournament_tracker.session import render_sidebar, require_admin

st.set_page_config(page_title="Manage Schedule", page_icon="🗓️", layout="wide")

services = get_services()
admin_user = require_admin(services)
render_sidebar(admin_user)

st.title("Manage Schedule")

participants = services.profile_service.list_participant_profiles()
participant_label_to_id: dict[str, int] = {}
participant_id_to_label: dict[int, str] = {}
for participant in participants:
    label = (
        participant.display_name
        or participant.username
        or participant.email
        or f"User {participant.user_id}"
    )
    label = f"{label} (id {participant.user_id})"
    participant_label_to_id[label] = participant.user_id
    participant_id_to_label[participant.user_id] = label

if len(participant_label_to_id) < 2:
    st.warning("Need at least two participants to schedule matches.")


def _parse_iso_to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        return None


create_tab, edit_tab = st.tabs(["Create Match", "Edit Existing Match"])

with create_tab:
    with st.form("create_match_form"):
        game_type_choice = st.selectbox("Game type", DEFAULT_GAME_TYPES + ["Other"])
        custom_game_type = st.text_input("Custom game type", value="")
        status = st.selectbox("Status", ["upcoming", "live", "completed"], index=0)
        scheduled_order = st.number_input("Scheduled order", min_value=1, value=1, step=1)
        has_schedule_time = st.checkbox("Set date/time", value=False)
        if has_schedule_time:
            col_date, col_time = st.columns(2)
            with col_date:
                dt_date = st.date_input("Date")
            with col_time:
                dt_time = st.time_input("Time", value=time(hour=12, minute=0))
            schedule_dt = datetime.combine(dt_date, dt_time)
        else:
            schedule_dt = None

        side1_name = st.text_input("Side 1 name", value="")
        side2_name = st.text_input("Side 2 name", value="")

        all_labels = list(participant_label_to_id.keys())
        side1_labels = st.multiselect("Side 1 participants", options=all_labels)
        side2_labels = st.multiselect("Side 2 participants", options=all_labels)

        create_submit = st.form_submit_button("Create match", use_container_width=True)

    if create_submit:
        game_type = custom_game_type.strip() if game_type_choice == "Other" else game_type_choice
        try:
            services.match_service.create_match(
                game_type=game_type,
                scheduled_at=schedule_dt,
                scheduled_order=int(scheduled_order),
                status=status,
                created_by_user_id=admin_user.id,
                side1_name=side1_name,
                side2_name=side2_name,
                side1_participant_ids=[participant_label_to_id[label] for label in side1_labels],
                side2_participant_ids=[participant_label_to_id[label] for label in side2_labels],
            )
            st.success("Match created.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc))

with edit_tab:
    cards = services.match_service.list_matches_for_view()
    if not cards:
        st.info("No matches yet.")
    else:
        label_to_match_id = {
            f"#{card.match_id} - {card.game_type} ({card.status})": card.match_id
            for card in cards
        }
        selected_label = st.selectbox("Select match", list(label_to_match_id.keys()))
        selected_match_id = label_to_match_id[selected_label]
        selected_card = next(card for card in cards if card.match_id == selected_match_id)

        existing_dt = _parse_iso_to_datetime(selected_card.scheduled_at)
        default_date = existing_dt.date() if existing_dt else datetime.utcnow().date()
        default_time = existing_dt.time() if existing_dt else time(hour=12, minute=0)

        side1_current_ids = [
            p.user_id for p in selected_card.sides[1]["participants"] if hasattr(p, "user_id")
        ]
        side2_current_ids = [
            p.user_id for p in selected_card.sides[2]["participants"] if hasattr(p, "user_id")
        ]

        with st.form("edit_match_form"):
            game_type_choice = st.selectbox(
                "Game type",
                DEFAULT_GAME_TYPES + ["Other"],
                index=(DEFAULT_GAME_TYPES.index(selected_card.game_type)
                       if selected_card.game_type in DEFAULT_GAME_TYPES
                       else len(DEFAULT_GAME_TYPES)),
                key="edit_game_type_choice",
            )
            custom_game_type = st.text_input(
                "Custom game type",
                value=selected_card.game_type if selected_card.game_type not in DEFAULT_GAME_TYPES else "",
                key="edit_custom_game_type",
            )
            status = st.selectbox(
                "Status",
                ["upcoming", "live", "completed"],
                index=["upcoming", "live", "completed"].index(selected_card.status),
                key="edit_status",
            )
            scheduled_order = st.number_input(
                "Scheduled order",
                min_value=1,
                value=int(selected_card.scheduled_order or 1),
                step=1,
                key="edit_order",
            )
            has_schedule_time = st.checkbox(
                "Set date/time",
                value=existing_dt is not None,
                key="edit_has_schedule",
            )
            if has_schedule_time:
                col_date, col_time = st.columns(2)
                with col_date:
                    dt_date = st.date_input("Date", value=default_date, key="edit_date")
                with col_time:
                    dt_time = st.time_input("Time", value=default_time, key="edit_time")
                schedule_dt = datetime.combine(dt_date, dt_time)
            else:
                schedule_dt = None

            side1_name = st.text_input(
                "Side 1 name",
                value=str(selected_card.sides[1]["side_name"] or ""),
                key="edit_side1_name",
            )
            side2_name = st.text_input(
                "Side 2 name",
                value=str(selected_card.sides[2]["side_name"] or ""),
                key="edit_side2_name",
            )

            all_labels = list(participant_label_to_id.keys())
            side1_defaults = [participant_id_to_label[i] for i in side1_current_ids if i in participant_id_to_label]
            side2_defaults = [participant_id_to_label[i] for i in side2_current_ids if i in participant_id_to_label]

            side1_labels = st.multiselect(
                "Side 1 participants",
                options=all_labels,
                default=side1_defaults,
                key="edit_side1_players",
            )
            side2_labels = st.multiselect(
                "Side 2 participants",
                options=all_labels,
                default=side2_defaults,
                key="edit_side2_players",
            )

            update_submit = st.form_submit_button("Save changes", use_container_width=True)

        if update_submit:
            game_type = custom_game_type.strip() if game_type_choice == "Other" else game_type_choice
            try:
                services.match_service.update_match(
                    match_id=selected_match_id,
                    game_type=game_type,
                    scheduled_at=schedule_dt,
                    scheduled_order=int(scheduled_order),
                    status=status,
                    side1_name=side1_name,
                    side2_name=side2_name,
                    side1_participant_ids=[participant_label_to_id[label] for label in side1_labels],
                    side2_participant_ids=[participant_label_to_id[label] for label in side2_labels],
                )
                st.success("Match updated.")
                st.rerun()
            except (ValidationError, NotFoundError) as exc:
                st.error(str(exc))

        st.divider()
        confirm_delete = st.checkbox("I understand this will permanently delete the selected match.")
        if st.button("Delete selected match", type="secondary", use_container_width=True, disabled=not confirm_delete):
            try:
                services.match_service.delete_match(selected_match_id)
                st.success("Match deleted.")
                st.rerun()
            except NotFoundError as exc:
                st.error(str(exc))
