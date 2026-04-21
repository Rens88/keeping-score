from __future__ import annotations

from datetime import datetime, time

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.services.match_service import DEFAULT_GAME_TYPES
from tournament_tracker.session import render_sidebar, require_admin

st.set_page_config(page_title="Manage Schedule", page_icon="🗓️", layout="wide")

services = get_runtime_services()
admin_user = require_admin(services, current_page="pages/09_Admin_Schedule.py")
render_sidebar(admin_user)

render_page_intro("Manage Schedule", "Create, edit, and remove matches with clear pairings and timing.", eyebrow="Admin")

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


def _render_schedule_inputs(
    *,
    mode_key: str,
    existing_dt: datetime | None = None,
    default_with_time: bool = True,
) -> datetime | None:
    render_form_field_label(
        "Kickoff date and time",
        "Used for the match overview and for locking pre-match actions like betting and specials.",
    )
    schedule_options = ["Set date and time now", "Leave date and time empty for now"]
    default_index = 0 if (existing_dt is not None or default_with_time) else 1
    schedule_mode = st.selectbox(
        "Kickoff date and time",
        schedule_options,
        index=default_index,
        key=f"{mode_key}_schedule_mode",
        label_visibility="collapsed",
    )
    if schedule_mode != schedule_options[0]:
        return None

    default_date = existing_dt.date() if existing_dt else datetime.now().date()
    default_time = (
        existing_dt.time().replace(second=0, microsecond=0)
        if existing_dt
        else time(hour=12, minute=0)
    )
    col_date, col_time = st.columns(2)
    with col_date:
        render_form_field_label("Date")
        dt_date = st.date_input("Date", value=default_date, key=f"{mode_key}_date", label_visibility="collapsed")
    with col_time:
        render_form_field_label("Time")
        dt_time = st.time_input("Time", value=default_time, key=f"{mode_key}_time", label_visibility="collapsed")
    return datetime.combine(dt_date, dt_time)


st.caption("Create new matches in the first tab. Use the other tabs to update or remove an existing match.")

create_tab, edit_tab, delete_tab = st.tabs(["Create Match", "Edit Match", "Delete Match"])

with create_tab:
    with st.form("create_match_form"):
        render_form_field_label("Game type")
        game_type_choice = st.selectbox(
            "Game type",
            DEFAULT_GAME_TYPES + ["Other"],
            label_visibility="collapsed",
        )
        render_form_field_label("Custom game type")
        custom_game_type = st.text_input("Custom game type", value="", label_visibility="collapsed")
        render_form_field_label("Status")
        status = st.selectbox(
            "Status",
            ["upcoming", "live", "completed"],
            index=0,
            label_visibility="collapsed",
        )
        render_form_field_label("Scheduled order")
        scheduled_order = st.number_input(
            "Scheduled order",
            min_value=1,
            value=1,
            step=1,
            label_visibility="collapsed",
        )
        schedule_dt = _render_schedule_inputs(mode_key="create", default_with_time=True)

        render_form_field_label("Side 1 name")
        side1_name = st.text_input("Side 1 name", value="", label_visibility="collapsed")
        render_form_field_label("Side 2 name")
        side2_name = st.text_input("Side 2 name", value="", label_visibility="collapsed")

        all_labels = list(participant_label_to_id.keys())
        render_form_field_label("Side 1 participants")
        side1_labels = st.multiselect("Side 1 participants", options=all_labels, label_visibility="collapsed")
        render_form_field_label("Side 2 participants")
        side2_labels = st.multiselect("Side 2 participants", options=all_labels, label_visibility="collapsed")

        create_submit = st.form_submit_button("Create match", width="stretch")

    if create_submit:
        game_type = custom_game_type.strip() if game_type_choice == "Other" else game_type_choice
        try:
            created_match = services.match_service.create_match(
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
            st.success(f"Match #{created_match.id} created.")
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
        render_form_field_label("Select match to edit")
        selected_label = st.selectbox(
            "Select match to edit",
            list(label_to_match_id.keys()),
            label_visibility="collapsed",
        )
        selected_match_id = label_to_match_id[selected_label]
        selected_card = next(card for card in cards if card.match_id == selected_match_id)

        existing_dt = _parse_iso_to_datetime(selected_card.scheduled_at)

        side1_current_ids = [
            p.user_id for p in selected_card.sides[1]["participants"] if hasattr(p, "user_id")
        ]
        side2_current_ids = [
            p.user_id for p in selected_card.sides[2]["participants"] if hasattr(p, "user_id")
        ]

        with st.form("edit_match_form"):
            render_form_field_label("Game type")
            game_type_choice = st.selectbox(
                "Game type",
                DEFAULT_GAME_TYPES + ["Other"],
                index=(DEFAULT_GAME_TYPES.index(selected_card.game_type)
                       if selected_card.game_type in DEFAULT_GAME_TYPES
                       else len(DEFAULT_GAME_TYPES)),
                key="edit_game_type_choice",
                label_visibility="collapsed",
            )
            render_form_field_label("Custom game type")
            custom_game_type = st.text_input(
                "Custom game type",
                value=selected_card.game_type if selected_card.game_type not in DEFAULT_GAME_TYPES else "",
                key="edit_custom_game_type",
                label_visibility="collapsed",
            )
            render_form_field_label("Status")
            status = st.selectbox(
                "Status",
                ["upcoming", "live", "completed"],
                index=["upcoming", "live", "completed"].index(selected_card.status),
                key="edit_status",
                label_visibility="collapsed",
            )
            render_form_field_label("Scheduled order")
            scheduled_order = st.number_input(
                "Scheduled order",
                min_value=1,
                value=int(selected_card.scheduled_order or 1),
                step=1,
                key="edit_order",
                label_visibility="collapsed",
            )
            schedule_dt = _render_schedule_inputs(
                mode_key="edit",
                existing_dt=existing_dt,
                default_with_time=existing_dt is not None,
            )

            render_form_field_label("Side 1 name")
            side1_name = st.text_input(
                "Side 1 name",
                value=str(selected_card.sides[1]["side_name"] or ""),
                key="edit_side1_name",
                label_visibility="collapsed",
            )
            render_form_field_label("Side 2 name")
            side2_name = st.text_input(
                "Side 2 name",
                value=str(selected_card.sides[2]["side_name"] or ""),
                key="edit_side2_name",
                label_visibility="collapsed",
            )

            all_labels = list(participant_label_to_id.keys())
            side1_defaults = [participant_id_to_label[i] for i in side1_current_ids if i in participant_id_to_label]
            side2_defaults = [participant_id_to_label[i] for i in side2_current_ids if i in participant_id_to_label]

            render_form_field_label("Side 1 participants")
            side1_labels = st.multiselect(
                "Side 1 participants",
                options=all_labels,
                default=side1_defaults,
                key="edit_side1_players",
                label_visibility="collapsed",
            )
            render_form_field_label("Side 2 participants")
            side2_labels = st.multiselect(
                "Side 2 participants",
                options=all_labels,
                default=side2_defaults,
                key="edit_side2_players",
                label_visibility="collapsed",
            )

            update_submit = st.form_submit_button("Save changes", width="stretch")

        if update_submit:
            game_type = custom_game_type.strip() if game_type_choice == "Other" else game_type_choice
            try:
                updated_match = services.match_service.update_match(
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
                st.success(f"Match #{updated_match.id} updated.")
            except (ValidationError, NotFoundError) as exc:
                st.error(str(exc))

with delete_tab:
    cards = services.match_service.list_matches_for_view()
    if not cards:
        st.info("No matches yet.")
    else:
        label_to_match_id = {
            f"#{card.match_id} - {card.game_type} ({card.status})": card.match_id
            for card in cards
        }
        render_form_field_label("Select match to delete")
        selected_label = st.selectbox(
            "Select match to delete",
            list(label_to_match_id.keys()),
            key="delete_match_select",
            label_visibility="collapsed",
        )
        selected_match_id = label_to_match_id[selected_label]
        st.warning("Deleting a match permanently removes the match and its related data.")
        confirm_delete = st.checkbox(
            "I understand this will permanently delete the selected match.",
            key="delete_match_confirm",
        )
        if st.button("Delete selected match", type="secondary", width="stretch", disabled=not confirm_delete):
            try:
                services.match_service.delete_match(selected_match_id)
                st.success(f"Match #{selected_match_id} deleted.")
            except NotFoundError as exc:
                st.error(str(exc))

render_bottom_decoration()
