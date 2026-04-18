from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.session import render_sidebar, require_admin

st.set_page_config(page_title="Participants and Invitations", page_icon="👥", layout="wide")

services = get_services()
admin_user = require_admin(services)
render_sidebar(admin_user)

render_page_intro(
    "Participants and Invitations",
    "Invite players, manage participant details, and troubleshoot doubler state.",
    eyebrow="Admin",
)

st.subheader("Generate invitation")
with st.form("create_invitation_form"):
    expiry_hours = st.number_input(
        "Expires in (hours)",
        min_value=1,
        max_value=336,
        value=services.config.default_invite_expiry_hours,
        step=1,
    )
    note = st.text_input("Note (optional)")
    create_invite = st.form_submit_button("Create invitation", width="stretch")

if create_invite:
    try:
        result = services.invitation_service.create_invitation(
            created_by_user_id=admin_user.id,
            expiry_hours=int(expiry_hours),
            note=note,
        )
        if services.config.app_base_url:
            invite_link = (
                f"{services.config.app_base_url}/Accept_Invitation"
                f"?token={result.token}"
            )
        else:
            invite_link = f"/Accept_Invitation?token={result.token}"

        st.success("Invitation created.")
        st.code(invite_link)
        st.caption("If APP_BASE_URL is not set, copy the token and append it to your app URL.")
    except ValidationError as exc:
        st.error(str(exc))

st.divider()
st.subheader("Recent invitations")
invitations = services.repo.list_invitations(limit=50)
if not invitations:
    st.info("No invitations created yet.")
else:
    st.dataframe(
        [
            {
                "id": invite.id,
                "created_at": invite.created_at,
                "expires_at": invite.expires_at,
                "used_at": invite.used_at or "-",
                "note": invite.note or "",
                "created_by": invite.created_by_name or "-",
            }
            for invite in invitations
        ],
        width="stretch",
        hide_index=True,
    )

st.divider()
st.subheader("Participants")
participants = services.profile_service.list_participant_profiles()
if not participants:
    st.info("No participants yet.")
else:
    participant_rows = []
    participant_options: dict[str, int] = {}
    for participant in participants:
        participant_name = (
            participant.display_name
            or participant.username
            or participant.email
            or f"User {participant.user_id}"
        )
        option_label = f"{participant_name} (id {participant.user_id})"
        participant_options[option_label] = participant.user_id
        participant_rows.append(
            {
                "user_id": participant.user_id,
                "name": participant_name,
                "username": participant.username or "",
                "email": participant.email or "",
                "motto": participant.motto or "",
            }
        )

    st.dataframe(participant_rows, width="stretch", hide_index=True)

    st.subheader("Reset participant password")
    if participant_options:
        pw_target_label = st.selectbox(
            "Participant for password reset",
            list(participant_options.keys()),
            key="participant_pw_reset_select",
        )
        pw_target_user_id = participant_options[pw_target_label]
        new_password = st.text_input(
            "New password",
            type="password",
            key="participant_pw_reset_new",
            help="Minimum 4 characters.",
        )
        if st.button("Reset password", width="stretch", key="participant_pw_reset_btn"):
            try:
                services.auth_service.admin_reset_password(
                    admin_user_id=admin_user.id,
                    target_user_id=pw_target_user_id,
                    new_password=new_password,
                )
                st.success("Participant password reset.")
            except ValidationError as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("Edit participant name")
    if participant_options:
        selected_participant_label = st.selectbox(
            "Participant to rename",
            list(participant_options.keys()),
            key="participant_rename_select",
        )
        selected_participant_id = participant_options[selected_participant_label]
        selected_participant = next(
            (p for p in participants if p.user_id == selected_participant_id),
            None,
        )
        current_name = (
            selected_participant.display_name
            if selected_participant and selected_participant.display_name
            else selected_participant.username
            if selected_participant and selected_participant.username
            else selected_participant.email
            if selected_participant and selected_participant.email
            else ""
        )
        new_name = st.text_input("New display name", value=current_name, key="participant_rename_input")
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
    st.subheader("Doubler troubleshooting")
    doubler_rows = services.match_service.list_doubler_status_rows()
    options = {
        f"{row['name']} (id {row['user_id']})": int(row["user_id"])
        for row in doubler_rows
    }
    selected_label = st.selectbox("Participant", list(options.keys())) if options else None

    if selected_label:
        selected_user_id = options[selected_label]
        selected_status = next(
            (row for row in doubler_rows if int(row["user_id"]) == selected_user_id),
            None,
        )
        if selected_status:
            st.write(
                f"Current status: {'used' if selected_status['doubler_used'] else 'not used'}"
                + (
                    f" (match #{selected_status['match_id']} - {selected_status['game_type']})"
                    if selected_status["doubler_used"]
                    else ""
                )
            )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Clear doubler", width="stretch"):
                try:
                    services.match_service.clear_doubler(selected_user_id)
                    st.success("Doubler cleared.")
                    st.rerun()
                except NotFoundError as exc:
                    st.error(str(exc))

        with col_b:
            participant_matches = services.match_service.list_matches_for_view(
                statuses=["upcoming"], participant_user_id=selected_user_id
            )
            if participant_matches:
                match_option_map = {
                    f"#{m.match_id} - {m.game_type} (order {m.scheduled_order or '-'})": m.match_id
                    for m in participant_matches
                }
                selected_match_label = st.selectbox(
                    "Reassign to upcoming match",
                    list(match_option_map.keys()),
                    key="reassign_match",
                )
                if st.button("Force reassign doubler", width="stretch"):
                    try:
                        services.match_service.admin_force_reassign_doubler(
                            participant_user_id=selected_user_id,
                            match_id=match_option_map[selected_match_label],
                            admin_user_id=admin_user.id,
                        )
                        st.success("Doubler reassigned.")
                        st.rerun()
                    except (ValidationError, NotFoundError) as exc:
                        st.error(str(exc))
            else:
                st.info("No upcoming matches for this participant.")

render_bottom_decoration()
