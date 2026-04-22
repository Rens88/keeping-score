from __future__ import annotations

from datetime import datetime, timedelta

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

render_page_intro(
    "Manage Schedule",
    "Create, edit, and remove head-to-head matches, and manage ranked multi-competitor events.",
    eyebrow="Admin",
)

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
    del default_with_time
    render_form_field_label(
        "Kickoff date and time",
        "Used for the match overview and for locking pre-match actions like betting and specials.",
    )

    default_seed = (
        existing_dt.replace(second=0, microsecond=0)
        if existing_dt
        else (datetime.now().replace(second=0, microsecond=0) + timedelta(hours=2))
    )
    default_date = default_seed.date()
    default_time = (
        existing_dt.time().replace(second=0, microsecond=0)
        if existing_dt
        else default_seed.time()
    )
    col_date, col_time = st.columns(2)
    with col_date:
        render_form_field_label("Date")
        dt_date = st.date_input("Date", value=default_date, key=f"{mode_key}_date", label_visibility="collapsed")
    with col_time:
        render_form_field_label("Time")
        dt_time = st.time_input("Time", value=default_time, key=f"{mode_key}_time", label_visibility="collapsed")
    return datetime.combine(dt_date, dt_time)


def _match_side_text(side: dict[str, object], fallback: str) -> str:
    participants = side.get("participants")
    participant_names = [
        getattr(participant, "display_name", "")
        for participant in participants
        if hasattr(participant, "display_name")
    ] if isinstance(participants, list) else []
    side_name = str(side.get("side_name") or "").strip()
    participant_text = " + ".join(name for name in participant_names if name)
    return side_name or participant_text or fallback


def _format_chat_schedule(value: str | None) -> str:
    parsed = _parse_iso_to_datetime(value)
    if not parsed:
        return "TBD"
    return parsed.strftime("%A %d %B at %H:%M")


def _store_betting_chat_preview(match_id: int) -> None:
    cards = services.match_service.list_matches_for_view()
    match_card = next((card for card in cards if card.match_id == match_id), None)
    if match_card is None or match_card.status != "upcoming":
        st.session_state.pop("schedule_chat_preview_title", None)
        st.session_state.pop("schedule_chat_preview_message", None)
        return

    side1_text = _match_side_text(match_card.sides[1], "Side 1")
    side2_text = _match_side_text(match_card.sides[2], "Side 2")
    app_link = services.config.app_base_url.rstrip("/")
    upcoming_matches_link = f"{app_link}/upcoming_matches"
    message = (
        f"Betting is now open for match #{match_card.match_id}: {match_card.game_type}.\n\n"
        f"Fixture: {side1_text} vs {side2_text}\n"
        f"Kickoff: {_format_chat_schedule(match_card.scheduled_at)}\n\n"
        f"Open the betting page here: {upcoming_matches_link}\n"
        f"Then open match #{match_card.match_id} to place your bet."
    )
    st.session_state["schedule_chat_preview_title"] = f"Chat message for match #{match_card.match_id}"
    st.session_state["schedule_chat_preview_message"] = message


def _ranked_event_label(event) -> str:
    schedule_text = event.scheduled_at or "no time set"
    return f"#{event.id} - {event.title} ({event.status}, {schedule_text})"


def _ranked_event_competitor_label(row: dict[str, object]) -> str:
    return str(
        row.get("display_name")
        or row.get("username")
        or row.get("email")
        or f"User {row.get('participant_user_id')}"
    )


CREATE_MATCH_ORDER_KEY = "create_match_scheduled_order"
CREATE_EVENT_ORDER_KEY = "create_ranked_event_scheduled_order"


def _next_scheduled_order_default() -> int:
    scheduled_orders = [
        int(match.scheduled_order)
        for match in services.repo.list_matches()
        if match.scheduled_order is not None
    ]
    scheduled_orders.extend(
        int(event.scheduled_order)
        for event in services.ranked_event_service.list_events()
        if event.scheduled_order is not None
    )
    return max(scheduled_orders, default=0) + 1


def _refresh_create_order_defaults() -> None:
    next_order = _next_scheduled_order_default()
    st.session_state[CREATE_MATCH_ORDER_KEY] = next_order
    st.session_state[CREATE_EVENT_ORDER_KEY] = next_order


if CREATE_MATCH_ORDER_KEY not in st.session_state or CREATE_EVENT_ORDER_KEY not in st.session_state:
    _refresh_create_order_defaults()


st.caption("Choose the competition type first. Then use the second row to create, edit, enter results, or delete.")

head_to_head_tab, multi_competitor_tab = st.tabs(["Head-to-head", "Multi-competitor"])

with head_to_head_tab:
    st.caption("Head-to-head is for matches with two sides.")
    create_match_tab, edit_match_tab, results_match_tab, delete_match_tab = st.tabs(
        ["Create", "Edit", "Results", "Delete"]
    )

    with create_match_tab:
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
                step=1,
                key=CREATE_MATCH_ORDER_KEY,
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
                _store_betting_chat_preview(created_match.id)
                _refresh_create_order_defaults()
                st.success(f"Match #{created_match.id} created.")
            except ValidationError as exc:
                st.error(str(exc))

    with edit_match_tab:
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
                    _store_betting_chat_preview(updated_match.id)
                    st.success(f"Match #{updated_match.id} updated.")
                except (ValidationError, NotFoundError) as exc:
                    st.error(str(exc))

    with results_match_tab:
        cards = services.match_service.list_matches_for_view()
        if not cards:
            st.info("No matches available.")
        else:
            label_to_match_id = {
                f"#{card.match_id} - {card.game_type} ({card.status})": card.match_id
                for card in cards
            }
            render_form_field_label("Select game")
            selected_label = st.selectbox(
                "Select game",
                list(label_to_match_id.keys()),
                key="results_match_select",
                label_visibility="collapsed",
            )
            selected_match_id = label_to_match_id[selected_label]
            selected_card = next(card for card in cards if card.match_id == selected_match_id)

            def _side_heading(side_number: int) -> str:
                side_name = str(selected_card.sides[side_number]["side_name"] or "").strip()
                if side_name:
                    return f"Side {side_number}: {side_name}"
                return f"Side {side_number}"

            outcome_labels = {
                "side1_win": f"Side 1 won ({str(selected_card.sides[1]['side_name'] or 'Side 1').strip() or 'Side 1'})",
                "draw": "Draw",
                "side2_win": f"Side 2 won ({str(selected_card.sides[2]['side_name'] or 'Side 2').strip() or 'Side 2'})",
            }
            outcome_options = ["side1_win", "draw", "side2_win"]
            default_outcome_index = (
                outcome_options.index(selected_card.outcome)
                if selected_card.outcome in outcome_options
                else 0
            )

            st.subheader(f"Game #{selected_card.match_id}: {selected_card.game_type}")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**{_side_heading(1)}**")
                for participant in selected_card.sides[1]["participants"]:
                    if hasattr(participant, "display_name"):
                        suffix = ""
                        icons = list(getattr(participant, "special_icons", ()))
                        if icons:
                            suffix = " " + " ".join(icons)
                        elif participant.has_doubler_on_match:
                            suffix = " ⚡x2"
                        st.write(f"- {participant.display_name}{suffix}")
            with col2:
                st.markdown(f"**{_side_heading(2)}**")
                for participant in selected_card.sides[2]["participants"]:
                    if hasattr(participant, "display_name"):
                        suffix = ""
                        icons = list(getattr(participant, "special_icons", ()))
                        if icons:
                            suffix = " " + " ".join(icons)
                        elif participant.has_doubler_on_match:
                            suffix = " ⚡x2"
                        st.write(f"- {participant.display_name}{suffix}")

            with st.form("result_form"):
                render_form_field_label("Result")
                outcome = st.selectbox(
                    "Result",
                    outcome_options,
                    index=default_outcome_index,
                    format_func=lambda o: outcome_labels.get(o, o),
                    label_visibility="collapsed",
                )
                render_form_field_label("Notes")
                notes = st.text_area(
                    "Notes",
                    value=selected_card.result_notes or "",
                    label_visibility="collapsed",
                )
                submit_result = st.form_submit_button("Save result", width="stretch")

            if submit_result:
                try:
                    services.match_service.set_match_result(
                        match_id=selected_match_id,
                        outcome=outcome,
                        entered_by_user_id=admin_user.id,
                        notes=notes,
                        mark_completed=True,
                    )
                    st.success("Result saved. Status updated to completed.")
                    st.rerun()
                except (ValidationError, NotFoundError) as exc:
                    st.error(str(exc))

            st.divider()
            st.subheader("Remove result")
            render_form_field_label("Status after removing result")
            new_status = st.selectbox(
                "Status after removing result",
                ["upcoming", "live"],
                index=0,
                key="remove_match_result_status",
                label_visibility="collapsed",
            )
            if st.button("Remove result", width="stretch", type="secondary", key="remove_match_result_button"):
                try:
                    services.match_service.clear_match_result(match_id=selected_match_id, new_status=new_status)
                    st.success("Result removed.")
                    st.rerun()
                except (ValidationError, NotFoundError) as exc:
                    st.error(str(exc))

    with delete_match_tab:
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
                    _refresh_create_order_defaults()
                    st.success(f"Match #{selected_match_id} deleted.")
                except NotFoundError as exc:
                    st.error(str(exc))

with multi_competitor_tab:
    st.caption(
        "Multi-competitor is for games with more than two competitors, where players finish in a placement order and earn points from a ranking scheme."
    )

    ranked_events = services.ranked_event_service.list_events()
    ranked_event_ids = [event.id for event in ranked_events]
    competitor_rows = (
        services.ranked_event_service.get_event_competitor_rows(ranked_event_ids)
        if ranked_event_ids
        else []
    )
    competitor_ids_by_event: dict[int, list[int]] = {}
    competitor_labels_by_event: dict[int, list[str]] = {}
    competitor_name_by_event_and_user: dict[tuple[int, int], str] = {}
    for row in competitor_rows:
        event_id = int(row.get("event_id", row.get("ranked_event_id")))
        user_id = int(row["participant_user_id"])
        label = participant_id_to_label.get(user_id) or _ranked_event_competitor_label(row)
        competitor_ids_by_event.setdefault(event_id, []).append(user_id)
        competitor_labels_by_event.setdefault(event_id, []).append(label)
        competitor_name_by_event_and_user[(event_id, user_id)] = label

    create_event_tab, edit_event_tab, results_event_tab, delete_event_tab = st.tabs(
        ["Create", "Edit", "Results", "Delete"]
    )

    with create_event_tab:
        with st.form("create_ranked_event_form"):
            render_form_field_label("Game type")
            event_title = st.text_input("Game type", value="", label_visibility="collapsed")
            render_form_field_label("Status")
            event_status = st.selectbox(
                "Status",
                ["upcoming", "live", "completed"],
                index=0,
                label_visibility="collapsed",
            )
            render_form_field_label("Scheduled order")
            event_order = st.number_input(
                "Scheduled order",
                min_value=1,
                step=1,
                key=CREATE_EVENT_ORDER_KEY,
                label_visibility="collapsed",
            )
            event_schedule_dt = _render_schedule_inputs(mode_key="ranked_create", default_with_time=True)
            render_form_field_label(
                "Award scheme",
                "Comma-separated weekend points per placement, for example 5,3,1.",
            )
            award_scheme_input = st.text_input(
                "Award scheme",
                value=services.ranked_event_service.serialize_award_scheme((5, 3, 1)),
                label_visibility="collapsed",
            )
            render_form_field_label("Competitors")
            competitor_labels = st.multiselect(
                "Competitors",
                options=list(participant_label_to_id.keys()),
                label_visibility="collapsed",
            )
            create_ranked_event_submit = st.form_submit_button("Create game", width="stretch")

        if create_ranked_event_submit:
            try:
                created_event = services.ranked_event_service.create_event(
                    title=event_title,
                    scheduled_at=event_schedule_dt,
                    scheduled_order=int(event_order),
                    status=event_status,
                    award_scheme=services.ranked_event_service.parse_award_scheme(award_scheme_input),
                    competitor_user_ids=[participant_label_to_id[label] for label in competitor_labels],
                    created_by_user_id=admin_user.id,
                )
                _refresh_create_order_defaults()
                st.success(f"Multi-competitor game #{created_event.id} created.")
            except ValidationError as exc:
                st.error(str(exc))

    with edit_event_tab:
        if not ranked_events:
            st.info("No multi-competitor games yet.")
        else:
            event_option_map = {_ranked_event_label(event): event.id for event in ranked_events}
            render_form_field_label("Select game to edit")
            selected_event_label = st.selectbox(
                "Select game to edit",
                list(event_option_map.keys()),
                key="edit_ranked_event_select",
                label_visibility="collapsed",
            )
            selected_event_id = event_option_map[selected_event_label]
            selected_event = next(event for event in ranked_events if event.id == selected_event_id)
            selected_event_dt = _parse_iso_to_datetime(selected_event.scheduled_at)
            selected_competitor_labels = competitor_labels_by_event.get(selected_event_id, [])

            with st.form("edit_ranked_event_form"):
                render_form_field_label("Game type")
                event_title = st.text_input(
                    "Game type",
                    value=selected_event.title,
                    key="edit_ranked_event_title",
                    label_visibility="collapsed",
                )
                render_form_field_label("Status")
                event_status = st.selectbox(
                    "Status",
                    ["upcoming", "live", "completed"],
                    index=["upcoming", "live", "completed"].index(selected_event.status),
                    key="edit_ranked_event_status",
                    label_visibility="collapsed",
                )
                render_form_field_label("Scheduled order")
                event_order = st.number_input(
                    "Scheduled order",
                    min_value=1,
                    value=int(selected_event.scheduled_order or 1),
                    step=1,
                    key="edit_ranked_event_order",
                    label_visibility="collapsed",
                )
                event_schedule_dt = _render_schedule_inputs(
                    mode_key="ranked_edit",
                    existing_dt=selected_event_dt,
                    default_with_time=selected_event_dt is not None,
                )
                render_form_field_label(
                    "Award scheme",
                    "Comma-separated weekend points per placement, for example 5,3,1.",
                )
                award_scheme_input = st.text_input(
                    "Award scheme",
                    value=selected_event.award_scheme,
                    key="edit_ranked_event_awards",
                    label_visibility="collapsed",
                )
                render_form_field_label("Competitors")
                competitor_labels = st.multiselect(
                    "Competitors",
                    options=list(participant_label_to_id.keys()),
                    default=selected_competitor_labels,
                    key="edit_ranked_event_competitors",
                    label_visibility="collapsed",
                )
                update_ranked_event_submit = st.form_submit_button("Save game changes", width="stretch")

            if update_ranked_event_submit:
                try:
                    updated_event = services.ranked_event_service.update_event(
                        event_id=selected_event_id,
                        title=event_title,
                        scheduled_at=event_schedule_dt,
                        scheduled_order=int(event_order),
                        status=event_status,
                        award_scheme=services.ranked_event_service.parse_award_scheme(award_scheme_input),
                        competitor_user_ids=[participant_label_to_id[label] for label in competitor_labels],
                        updated_by_user_id=admin_user.id,
                    )
                    st.success(f"Multi-competitor game #{updated_event.id} updated.")
                except (ValidationError, NotFoundError) as exc:
                    st.error(str(exc))

    with results_event_tab:
        if not ranked_events:
            st.info("No multi-competitor games yet.")
        else:
            event_option_map = {_ranked_event_label(event): event.id for event in ranked_events}
            render_form_field_label("Select game")
            selected_event_label = st.selectbox(
                "Select game",
                list(event_option_map.keys()),
                key="ranked_event_results_select",
                label_visibility="collapsed",
            )
            selected_event_id = event_option_map[selected_event_label]
            selected_event = next(event for event in ranked_events if event.id == selected_event_id)
            current_results = services.ranked_event_service.get_event_results_map(selected_event_id)
            competitor_ids = competitor_ids_by_event.get(selected_event_id, [])

            if not competitor_ids:
                st.info("This multi-competitor game has no competitors yet.")
            else:
                if current_results:
                    st.dataframe(
                        [
                            {
                                "placement": current_results[user_id],
                                "competitor": competitor_name_by_event_and_user.get(
                                    (selected_event_id, user_id),
                                    participant_id_to_label.get(user_id, f"User {user_id}"),
                                ),
                            }
                            for user_id in sorted(current_results, key=current_results.get)
                        ],
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.caption("No results saved yet for this event.")

                with st.form("ranked_event_results_form"):
                    placements_by_user_id: dict[int, int] = {}
                    for index, user_id in enumerate(competitor_ids, start=1):
                        label = competitor_name_by_event_and_user.get(
                            (selected_event_id, user_id),
                            participant_id_to_label.get(user_id, f"User {user_id}"),
                        )
                        render_form_field_label(label)
                        placements_by_user_id[user_id] = int(
                            st.number_input(
                                label,
                                min_value=1,
                                value=int(current_results.get(user_id, index)),
                                step=1,
                                key=f"ranked_event_place_{selected_event_id}_{user_id}",
                                label_visibility="collapsed",
                            )
                        )
                    save_ranked_results = st.form_submit_button("Save placements", width="stretch")

                if save_ranked_results:
                    try:
                        services.ranked_event_service.save_results(
                            event_id=selected_event_id,
                            placements_by_user_id=placements_by_user_id,
                            entered_by_user_id=admin_user.id,
                        )
                        st.success(f"Result saved for multi-competitor game #{selected_event_id}. Status updated to completed.")
                    except (ValidationError, NotFoundError) as exc:
                        st.error(str(exc))

                st.divider()
                st.subheader("Remove result")
                render_form_field_label("Status after removing result")
                clear_status = st.selectbox(
                    "Status after removing result",
                    ["upcoming", "live"],
                    index=["upcoming", "live"].index(
                        selected_event.status if selected_event.status in {"upcoming", "live"} else "upcoming"
                    ),
                    key=f"ranked_event_clear_status_{selected_event_id}",
                    label_visibility="collapsed",
                )
                if st.button("Remove result", width="stretch", key=f"ranked_event_clear_{selected_event_id}"):
                    try:
                        services.ranked_event_service.clear_results(
                            event_id=selected_event_id,
                            status_after_clear=clear_status,
                            cleared_by_user_id=admin_user.id,
                        )
                        st.success(f"Result removed for multi-competitor game #{selected_event_id}.")
                    except (ValidationError, NotFoundError) as exc:
                        st.error(str(exc))

    with delete_event_tab:
        if not ranked_events:
            st.info("No multi-competitor games yet.")
        else:
            event_option_map = {_ranked_event_label(event): event.id for event in ranked_events}
            render_form_field_label("Select game to delete")
            selected_event_label = st.selectbox(
                "Select game to delete",
                list(event_option_map.keys()),
                key="delete_ranked_event_select",
                label_visibility="collapsed",
            )
            selected_event_id = event_option_map[selected_event_label]
            st.warning("Deleting a multi-competitor game permanently removes its competitor list, placements, and awarded points.")
            confirm_delete = st.checkbox(
                "I understand this will permanently delete the selected game.",
                key="delete_ranked_event_confirm",
            )
            if st.button(
                "Delete selected game",
                type="secondary",
                width="stretch",
                disabled=not confirm_delete,
            ):
                try:
                    services.ranked_event_service.delete_event(selected_event_id)
                    _refresh_create_order_defaults()
                    st.success(f"Multi-competitor game #{selected_event_id} deleted.")
                except NotFoundError as exc:
                    st.error(str(exc))

preview_message = st.session_state.get("schedule_chat_preview_message")
if isinstance(preview_message, str) and preview_message.strip():
    preview_title = str(st.session_state.get("schedule_chat_preview_title") or "Chat message")
    with st.container(border=True):
        st.subheader(preview_title)
        st.caption("Copy this into your team chat so players know betting is live and where to find the match.")
        if services.config.app_base_url_is_fallback:
            st.info(
                "APP_BASE_URL is still using the fallback deployment URL. "
                "Set APP_BASE_URL when you want this message to prefer your live local or custom app link."
            )
        st.code(preview_message)

render_bottom_decoration()
