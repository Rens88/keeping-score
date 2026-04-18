from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_page_intro
from tournament_tracker.bootstrap import get_services
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.session import get_current_user, render_sidebar, set_logged_in_user

st.set_page_config(page_title="Accept Invitation", page_icon="✉️", layout="centered")

services = get_services()
current_user = get_current_user(services)
render_sidebar(current_user)

render_page_intro("Accept Invitation", "Create your participant account using your invitation token.")

if current_user:
    st.info("You are already logged in.")
    if st.button("Go to Leaderboard", width="stretch", key="accept_invite_go_leaderboard"):
        st.switch_page("pages/03_Leaderboard.py")
    st.stop()

query_token = st.query_params.get("token", "")
if isinstance(query_token, list):
    query_token = query_token[0] if query_token else ""

token_default = (query_token or "").strip()
with st.container(border=True):
    st.caption("Paste the token from your invite link, or open the invite link directly on this page.")
    token = st.text_input("Invitation token", value=token_default)
    if token:
        validation = services.invitation_service.validate_invitation_token(token)
        if validation.valid:
            st.success("Invitation token is valid.")
        else:
            st.error(validation.message)

with st.container(border=True):
    with st.form("invitation_signup"):
        st.subheader("Profile and Login")
        display_name = st.text_input("Name")
        motto = st.text_input("Weekend motto")
        username = st.text_input("Username (optional if email is provided)")
        email = st.text_input("Email (optional if username is provided)")
        password = st.text_input("Password", type="password")
        photo = st.file_uploader(
            "Profile photo",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=False,
        )
        submitted = st.form_submit_button("Create account", width="stretch")

if submitted:
    photo_bytes = photo.getvalue() if photo else None
    photo_type = photo.type if photo else None

    try:
        user = services.invitation_service.accept_invitation(
            token=token,
            username=username,
            email=email,
            password=password,
            display_name=display_name,
            motto=motto,
            photo_blob=photo_bytes,
            photo_mime_type=photo_type,
        )
        set_logged_in_user(user)
        st.success("Account created. Welcome.")
        st.rerun()
    except ValidationError as exc:
        st.error(str(exc))
    except NotFoundError as exc:
        st.error(str(exc))
    except Exception:
        st.error("Could not create your account. Please check the invitation link and try again.")

st.divider()
if st.button("Already have an account? Login", width="stretch", key="accept_invite_go_login"):
    st.switch_page("pages/01_Login.py")
render_bottom_decoration()
