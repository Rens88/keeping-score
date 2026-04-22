from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.services.special_service import (
    MANUAL_MATCH_SPECIAL_KEYS,
    SPECIAL_CATCH_UP,
    SPECIAL_DONT_UNDERESTIMATE,
    SPECIAL_DOUBLER,
    SPECIAL_DOUBLE_OR_NOTHING,
    SPECIAL_KING_FIXER,
    SPECIAL_KING_OF_THE_HILL,
    SPECIAL_MATCH_FIXER,
    SPECIAL_WHEEL,
    SPECIAL_WINNER_TAKES_ALL,
)
from tournament_tracker.session import render_sidebar, require_admin

st.set_page_config(page_title="Participants and Registration", page_icon="👥", layout="wide")

services = get_runtime_services()
admin_user = require_admin(services, current_page="pages/08_Admin_Participants_Invitations.py")
render_sidebar(admin_user)

render_page_intro(
    "Participants and Registration",
    "Create registration accounts, generate invitation copy, manage names, and troubleshoot participant access.",
    eyebrow="Admin",
)

game_is_active = services.registration_service.is_registration_game_active()
if services.config.app_base_url_is_fallback:
    st.warning(
        "APP_BASE_URL is not configured yet, so invitation messages will use the fallback link "
        f"`{services.config.app_base_url}`. "
        "Set APP_BASE_URL when you want invitations to prefer your current local or custom deployment URL."
    )


def participant_name(participant: object) -> str:
    display_name = getattr(participant, "display_name", None)
    username = getattr(participant, "username", None)
    email = getattr(participant, "email", None)
    user_id = getattr(participant, "user_id", "?")
    return str(display_name or username or email or f"User {user_id}")


def participant_status(participant: object) -> str:
    if bool(getattr(participant, "registration_game_completed", False)):
        return "Finished"
    if int(getattr(participant, "registration_questions_answered", 0)) > 0:
        return "In progress"
    if game_is_active:
        return "Registration game live"
    return "Waiting"


def store_invitation_preview(*, title: str, message: str) -> None:
    st.session_state["registration_invitation_preview_title"] = title
    st.session_state["registration_invitation_preview_message"] = message


flash_message = st.session_state.pop("registration_invitation_flash_message", None)
if isinstance(flash_message, str) and flash_message:
    st.success(flash_message)

with st.container(border=True):
    st.subheader("Create registration account")
    st.caption("Admins create the account and password up front. New participants will land on the waiting page until the game is activated.")
    with st.form("create_registration_account_form", clear_on_submit=True):
        render_form_field_label("Display name")
        display_name = st.text_input("Display name", label_visibility="collapsed")
        render_form_field_label("Username")
        username = st.text_input("Username", label_visibility="collapsed")
        render_form_field_label("Email", "Optional.")
        email = st.text_input("Email (optional)", label_visibility="collapsed")
        render_form_field_label("Password", "Minimum 4 characters.")
        password = st.text_input("Password", type="password", label_visibility="collapsed")
        create_account = st.form_submit_button("Create account", width="stretch")

    if create_account:
        try:
            user = services.registration_service.create_admin_managed_participant(
                admin_user_id=admin_user.id,
                display_name=display_name,
                username=username,
                password=password,
                email=email,
            )
            invitation_message = services.registration_service.build_registration_invitation(
                display_name=display_name,
                username=username,
                password=password,
            )
            store_invitation_preview(
                title=f"Registration invitation for {display_name.strip() or username.strip()}",
                message=invitation_message,
            )
            st.success(f"Participant account created for {display_name.strip() or username.strip()} (user id {user.id}).")
        except ValidationError as exc:
            st.error(str(exc))

preview_message = st.session_state.get("registration_invitation_preview_message")
if isinstance(preview_message, str) and preview_message.strip():
    preview_title = str(st.session_state.get("registration_invitation_preview_title") or "Registration invitation")
    with st.container(border=True):
        st.subheader(preview_title)
        st.caption(
            "Copy this straight into WhatsApp, email, carrier pigeon, or your admin chat of choice. "
            "Use the copy icon on the message block below, or select the text manually."
        )
        st.code(preview_message)

st.divider()
st.subheader("Participants")
participants = services.profile_service.list_participant_profiles()
if not participants:
    st.info("No participants yet.")
else:
    participant_rows = []
    participant_options: dict[str, int] = {}
    participants_by_id = {participant.user_id: participant for participant in participants}
    for participant in participants:
        option_label = f"{participant_name(participant)} (id {participant.user_id})"
        participant_options[option_label] = participant.user_id
        participant_rows.append(
            {
                "user_id": participant.user_id,
                "name": participant_name(participant),
                "username": participant.username or "",
                "email": participant.email or "",
                "status": participant_status(participant),
                "questions_answered": f"{participant.registration_questions_answered}/10",
                "incorrect_answers": participant.registration_game_incorrect_answers,
                "starting_points": f"{participant.registration_game_points:.1f}",
            }
        )

    st.dataframe(participant_rows, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Reset password and generate fresh invitation")
    render_form_field_label("Participant")
    pw_target_label = st.selectbox(
        "Participant for password reset",
        list(participant_options.keys()),
        key="participant_pw_reset_select",
        label_visibility="collapsed",
    )
    pw_target_user_id = participant_options[pw_target_label]
    pw_target = participants_by_id[pw_target_user_id]
    render_form_field_label("New password", "Minimum 4 characters.")
    new_password = st.text_input(
        "New password",
        type="password",
        key="participant_pw_reset_new",
        help="Minimum 4 characters.",
        label_visibility="collapsed",
    )
    if st.button("Reset password and refresh invitation", width="stretch", key="participant_pw_reset_btn"):
        try:
            services.auth_service.admin_reset_password(
                admin_user_id=admin_user.id,
                target_user_id=pw_target_user_id,
                new_password=new_password,
            )
            username_for_invite = (pw_target.username or "").strip()
            if not username_for_invite:
                st.success("Participant password reset.")
                st.info("This participant has no username stored, so no registration invitation message was generated.")
            else:
                invitation_message = services.registration_service.build_registration_invitation(
                    display_name=participant_name(pw_target),
                    username=username_for_invite,
                    password=new_password,
                )
                store_invitation_preview(
                    title=f"Fresh registration invitation for {participant_name(pw_target)}",
                    message=invitation_message,
                )
                st.session_state["registration_invitation_flash_message"] = (
                    "Participant password reset and invitation refreshed."
                )
                st.rerun()
        except ValidationError as exc:
            st.error(str(exc))

    st.divider()
    st.subheader("Edit participant name")
    render_form_field_label("Participant to rename")
    selected_participant_label = st.selectbox(
        "Participant to rename",
        list(participant_options.keys()),
        key="participant_rename_select",
        label_visibility="collapsed",
    )
    selected_participant_id = participant_options[selected_participant_label]
    selected_participant = participants_by_id[selected_participant_id]
    current_name = participant_name(selected_participant)
    render_form_field_label("New display name")
    new_name = st.text_input(
        "New display name",
        value=current_name,
        key="participant_rename_input",
        label_visibility="collapsed",
    )
    if st.button("Save participant name", width="stretch", key="participant_rename_save"):
        try:
            services.profile_service.admin_update_participant_name(
                participant_user_id=selected_participant_id,
                new_display_name=new_name,
            )
            st.success("Participant name updated.")
            st.rerun()
        except (ValidationError, NotFoundError) as exc:
            st.error(str(exc))

    st.divider()
    st.subheader("Specials troubleshooting")
    special_rows = services.special_service.list_special_status_rows()
    options = {
        f"{row['name']} (id {row['user_id']})": int(row["user_id"])
        for row in special_rows
    }
    if options:
        render_form_field_label("Participant")
        selected_label = st.selectbox("Participant", list(options.keys()), label_visibility="collapsed")
    else:
        selected_label = None

    if selected_label:
        selected_user_id = options[selected_label]
        selected_status = next(
            (row for row in special_rows if int(row["user_id"]) == selected_user_id),
            None,
        )
        if not selected_status:
            st.info("Could not load the special status for this participant.")
        else:
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
                key="special_troubleshooting_select",
                label_visibility="collapsed",
            )
            selected_special_key = special_options[selected_special_label]
            current_status = str(selected_status[selected_special_key])
            current_override = str(selected_status.get(f"{selected_special_key}_override", "auto"))
            st.write(f"Current status: {current_status}")

            status_is_available = current_status.startswith("available") or current_status.startswith("active")
            toggle_label = "Deactivate special" if status_is_available else "(re)-activate special"
            toggle_mode = "off" if status_is_available else "on"

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button(toggle_label, width="stretch", key="special_troubleshooting_toggle"):
                    try:
                        services.special_service.set_special_override_mode(
                            participant_user_id=selected_user_id,
                            special_key=selected_special_key,
                            mode=toggle_mode,
                            updated_by_user_id=admin_user.id,
                        )
                        st.success(f"{services.special_service.special_label(selected_special_key)} updated.")
                        st.rerun()
                    except ValidationError as exc:
                        st.error(str(exc))

            with col_b:
                if selected_special_key in MANUAL_MATCH_SPECIAL_KEYS:
                    participant_matches = services.match_service.list_matches_for_view(
                        statuses=["upcoming"], participant_user_id=selected_user_id
                    )
                    if participant_matches:
                        match_option_map = {
                            f"#{m.match_id} - {m.game_type} (order {m.scheduled_order or '-'})": m.match_id
                            for m in participant_matches
                        }
                        render_form_field_label("Assign to upcoming match")
                        selected_match_label = st.selectbox(
                            "Assign to upcoming match",
                            list(match_option_map.keys()),
                            key=f"special_assign_match_{selected_special_key}",
                            label_visibility="collapsed",
                        )
                        if st.button("Force assign special to match", width="stretch", key="special_force_assign_btn"):
                            try:
                                if current_status.startswith("active"):
                                    services.special_service.set_special_override_mode(
                                        participant_user_id=selected_user_id,
                                        special_key=selected_special_key,
                                        mode="off",
                                        updated_by_user_id=admin_user.id,
                                    )
                                if current_override != "auto" or current_status.startswith("active"):
                                    services.special_service.set_special_override_mode(
                                        participant_user_id=selected_user_id,
                                        special_key=selected_special_key,
                                        mode="auto",
                                        updated_by_user_id=admin_user.id,
                                    )
                                services.special_service.activate_match_special(
                                    participant_user_id=selected_user_id,
                                    special_key=selected_special_key,
                                    match_id=match_option_map[selected_match_label],
                                    actor_user_id=admin_user.id,
                                    admin_override=True,
                                )
                                st.success(f"{services.special_service.special_label(selected_special_key)} assigned.")
                                st.rerun()
                            except (ValidationError, NotFoundError) as exc:
                                st.error(str(exc))
                    else:
                        st.info("No upcoming matches for this participant.")
                else:
                    st.caption("This special is not assigned to a specific upcoming match.")

render_bottom_decoration()
