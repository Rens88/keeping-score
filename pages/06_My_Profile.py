from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration
from tournament_tracker.bootstrap import get_services
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.session import render_sidebar, require_login

st.set_page_config(page_title="My Profile", page_icon="👤", layout="wide")

services = get_services()
user = require_login(services)
render_sidebar(user)

st.title("My Profile")

profile = services.repo.get_user_with_profile(user.id)
if not profile:
    st.error("Profile not found.")
    st.stop()

col1, col2 = st.columns([1, 3])
with col1:
    if profile.photo_blob:
        st.image(profile.photo_blob, width=130)
    else:
        st.caption("No photo")
with col2:
    st.subheader(profile.display_name or profile.username or profile.email or f"User {profile.user_id}")
    st.write(profile.motto or "No motto yet")
    st.caption(f"Role: {profile.role}")

if user.role == "participant":
    stats = services.ranking_service.get_participant_stats(user.id)
    if stats:
        stat_cols = st.columns(5)
        stat_cols[0].metric("Points", f"{stats.total_points:.2f}")
        stat_cols[1].metric("Played", stats.matches_played)
        stat_cols[2].metric("Wins", stats.wins)
        stat_cols[3].metric("Draws", stats.draws)
        stat_cols[4].metric("Losses", stats.losses)
    else:
        st.info("No match stats yet.")

    st.divider()
    st.subheader("Edit profile")

    with st.form("edit_profile"):
        st.caption("Name changes are managed by admins.")
        st.text_input("Name", value=profile.display_name or "", disabled=True)
        motto = st.text_input("Motto", value=profile.motto or "")
        new_photo = st.file_uploader("Upload new photo", type=["png", "jpg", "jpeg", "webp"])
        keep_existing = st.checkbox("Keep existing photo if no new upload", value=True)
        save = st.form_submit_button("Save profile", width="stretch")

    if save:
        try:
            updated = services.profile_service.update_profile(
                user_id=user.id,
                display_name=profile.display_name or "",
                motto=motto,
                photo_blob=new_photo.getvalue() if new_photo else None,
                photo_mime_type=new_photo.type if new_photo else None,
                keep_existing_photo=keep_existing,
                allow_name_change=False,
            )
            st.success("Profile updated.")
            if updated.photo_blob:
                st.image(updated.photo_blob, width=120)
            st.rerun()
        except (ValidationError, NotFoundError) as exc:
            st.error(str(exc))

st.divider()
st.subheader("Change password")
with st.form("change_password_form"):
    current_password = st.text_input("Current password", type="password")
    new_password = st.text_input("New password", type="password")
    confirm_password = st.text_input("Confirm new password", type="password")
    password_save = st.form_submit_button("Update password", width="stretch")

if password_save:
    if new_password != confirm_password:
        st.error("New password and confirmation do not match.")
    else:
        try:
            services.auth_service.change_password(
                user_id=user.id,
                current_password=current_password,
                new_password=new_password,
            )
            st.success("Password updated.")
        except ValidationError as exc:
            st.error(str(exc))

st.divider()
st.subheader("Participant Directory")
participants = services.profile_service.list_participant_profiles()
if not participants:
    st.info("No participants yet.")
else:
    for participant in participants:
        name = (
            participant.display_name
            or participant.username
            or participant.email
            or f"User {participant.user_id}"
        )
        with st.container(border=True):
            col_a, col_b = st.columns([1, 4])
            with col_a:
                if participant.photo_blob:
                    st.image(participant.photo_blob, width=80)
                else:
                    st.caption("No photo")
            with col_b:
                st.markdown(f"**{name}**")
                st.caption(participant.motto or "No motto")

render_bottom_decoration()
