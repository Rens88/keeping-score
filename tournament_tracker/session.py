from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

import streamlit as st

from tournament_tracker.branding import CANGEROES_LOGO_URL, render_cangeroes_header
from tournament_tracker.models import User

if TYPE_CHECKING:
    from tournament_tracker.bootstrap import AppServices

SESSION_USER_ID_KEY = "auth_user_id"
SESSION_AUTH_TOKEN_KEY = "auth_session_token"
AUTH_COOKIE_COMMAND_KEY = "auth_cookie_command"
AUTH_COOKIE_NAME = "weekend_tracker_session"
HOME_PAGE = "app.py"
PROFILE_PAGE = "pages/06_My_Profile.py"
REGISTRATION_WAIT_PAGE = "pages/12_And_Now_We_Wait.py"
REGISTRATION_GAME_PAGE = "pages/13_Registration_Game.py"


def _queue_set_auth_cookie(*, token: str, max_age_seconds: int) -> None:
    st.session_state[AUTH_COOKIE_COMMAND_KEY] = {
        "action": "set",
        "token": token,
        "max_age_seconds": int(max_age_seconds),
    }


def _queue_clear_auth_cookie() -> None:
    st.session_state[AUTH_COOKIE_COMMAND_KEY] = {"action": "clear"}


def _apply_pending_auth_cookie_command() -> bool:
    command = st.session_state.pop(AUTH_COOKIE_COMMAND_KEY, None)
    if not isinstance(command, dict):
        return False

    action = str(command.get("action") or "").strip().lower()
    cookie_name_json = json.dumps(AUTH_COOKIE_NAME)
    if action == "set":
        token_json = json.dumps(str(command.get("token") or ""))
        max_age_seconds = max(1, int(command.get("max_age_seconds") or 0))
        st.html(
            f"""
<script>
(() => {{
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  const name = {cookie_name_json};
  const token = {token_json};
  document.cookie = `${{name}}=${{token}}; Max-Age={max_age_seconds}; Path=/; SameSite=Lax${{secure}}`;
}})();
</script>
            """,
            unsafe_allow_javascript=True,
            width="content",
        )
        return False

    if action == "clear":
        st.html(
            f"""
<script>
(() => {{
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  const name = {cookie_name_json};
  document.cookie = `${{name}}=; Max-Age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/; SameSite=Lax${{secure}}`;
}})();
</script>
            """,
            unsafe_allow_javascript=True,
            width="content",
        )
        return True

    return False


def _clear_local_login_state() -> Optional[str]:
    raw_token = st.session_state.pop(SESSION_AUTH_TOKEN_KEY, None)
    st.session_state.pop(SESSION_USER_ID_KEY, None)
    return str(raw_token) if raw_token else None


def set_logged_in_user(
    user: User,
    *,
    services: Optional["AppServices"] = None,
    persist_login: bool = True,
) -> None:
    old_token = _clear_local_login_state()
    if services and old_token:
        services.auth_service.revoke_persistent_session(old_token)

    st.session_state[SESSION_USER_ID_KEY] = user.id
    if services and persist_login:
        session_token, max_age_seconds = services.auth_service.create_persistent_session(user.id)
        st.session_state[SESSION_AUTH_TOKEN_KEY] = session_token
        _queue_set_auth_cookie(token=session_token, max_age_seconds=max_age_seconds)
    elif old_token:
        _queue_clear_auth_cookie()


def logout_user(services: Optional["AppServices"] = None) -> None:
    token = _clear_local_login_state()
    if services and token:
        services.auth_service.revoke_persistent_session(token)
    _queue_clear_auth_cookie()


def get_current_user(services: AppServices) -> Optional[User]:
    skip_cookie_restore = _apply_pending_auth_cookie_command()
    user_id = st.session_state.get(SESSION_USER_ID_KEY)
    if not user_id:
        if not skip_cookie_restore:
            cookie_token = str(st.context.cookies.get(AUTH_COOKIE_NAME, "") or "").strip()
            if cookie_token:
                user = services.auth_service.restore_persistent_session(cookie_token)
                if user:
                    st.session_state[SESSION_USER_ID_KEY] = user.id
                    st.session_state[SESSION_AUTH_TOKEN_KEY] = cookie_token
                    return user
                _queue_clear_auth_cookie()
                _apply_pending_auth_cookie_command()
        return None

    user = services.repo.get_user_by_id(int(user_id))
    if not user or not user.is_active:
        token = _clear_local_login_state()
        if token:
            services.auth_service.revoke_persistent_session(token)
            _queue_clear_auth_cookie()
            _apply_pending_auth_cookie_command()
        return None
    return user


def get_registration_gate_page(services: AppServices, user: User) -> Optional[str]:
    if not services.registration_service.participant_requires_registration_gate(user):
        return None
    if services.registration_service.is_registration_game_active():
        return REGISTRATION_GAME_PAGE
    return REGISTRATION_WAIT_PAGE


def get_initial_page_for_user(services: AppServices, user: User) -> str:
    return get_registration_gate_page(services, user) or HOME_PAGE


def enforce_registration_gate(
    services: AppServices,
    user: User,
    *,
    current_page: str,
    allow_gate_page: bool = False,
) -> None:
    destination = get_registration_gate_page(services, user)
    if not destination:
        return
    if allow_gate_page and current_page == destination:
        return
    if current_page == PROFILE_PAGE:
        return
    st.switch_page(destination)


def require_login(
    services: AppServices,
    *,
    current_page: Optional[str] = None,
    allow_gate_page: bool = False,
) -> User:
    user = get_current_user(services)
    if user:
        if current_page:
            enforce_registration_gate(
                services,
                user,
                current_page=current_page,
                allow_gate_page=allow_gate_page,
            )
        return user

    st.warning("Please log in first.")
    if st.button("Go to Login", width="stretch", key="require_login_go_login"):
        st.switch_page("pages/01_Login.py")
    st.stop()


def require_admin(services: AppServices, *, current_page: Optional[str] = None) -> User:
    user = require_login(services, current_page=current_page)
    if user.role == "admin":
        return user

    st.error("You do not have permission to view this page.")
    if st.button("Go to Leaderboard", width="stretch", key="require_admin_go_leaderboard"):
        st.switch_page("pages/03_Leaderboard.py")
    st.stop()


def _render_navigation_rows(
    buttons: list[tuple[str, str, str, str]],
    *,
    row_size: int = 3,
    icon_only: bool = False,
) -> None:
    if icon_only:
        with st.container(horizontal=True, horizontal_alignment="left", gap="small"):
            for icon, label, page, key in buttons:
                if st.button(icon, width="content", key=key, help=label):
                    st.switch_page(page)
        return

    for start in range(0, len(buttons), row_size):
        row_buttons = buttons[start:start + row_size]
        row_cols = st.columns(len(row_buttons))
        for col, (icon, label, page, key) in zip(row_cols, row_buttons):
            button_label = f"{icon} {label}"
            if col.button(button_label, width="stretch", key=key):
                st.switch_page(page)


def render_main_navigation(user: Optional[User], *, current_page: Optional[str] = None) -> None:
    if not user:
        return

    gate_destination: Optional[str] = None
    try:
        from tournament_tracker.bootstrap import get_runtime_services

        gate_destination = get_registration_gate_page(get_runtime_services(), user)
    except Exception:
        gate_destination = None

    text_mode = current_page == HOME_PAGE
    if gate_destination:
        label = "Registration Game" if gate_destination == REGISTRATION_GAME_PAGE else "And Now We Wait"
        icon = "🧩" if gate_destination == REGISTRATION_GAME_PAGE else "⏳"
        _render_navigation_rows(
            [
                (icon, label, gate_destination, "top_nav_registration_gate"),
                ("👤", "My Profile", PROFILE_PAGE, "top_nav_gated_profile"),
            ],
            row_size=2,
            icon_only=not text_mode,
        )
        st.divider()
        return

    st.markdown("**Quick Navigation**")
    st.caption("Click on the icons to navigate to the other pages, use sidepanel for more details.")
    _render_navigation_rows(
        [
            ("🏠", "Home", "app.py", "top_nav_home"),
            ("🏆", "Leaderboard", "pages/03_Leaderboard.py", "top_nav_leaderboard"),
            ("📅", "Upcoming", "pages/04_Upcoming_Matches.py", "top_nav_upcoming"),
            ("📜", "Past", "pages/05_Past_Matches.py", "top_nav_past"),
            ("👤", "My Profile", PROFILE_PAGE, "top_nav_profile"),
        ],
        row_size=5,
        icon_only=not text_mode,
    )

    if user.role == "participant":
        _render_navigation_rows(
            [
                ("✨", "Specials", "pages/17_Specials.py", "top_nav_specials"),
                ("🏡", "Weekend Info", "pages/14_Weekend_Info.py", "top_nav_weekend_info"),
                ("🔨", "Mini Games", "pages/15_Mini_Game.py", "top_nav_mini_game"),
            ],
            row_size=3,
            icon_only=not text_mode,
        )

    if user.role == "admin":
        _render_navigation_rows(
            [
                ("🛡️", "Admin Home", "pages/07_Admin_Dashboard.py", "top_nav_admin_home"),
                ("✨", "Specials", "pages/17_Specials.py", "top_nav_admin_specials"),
                ("👥", "Participants", "pages/08_Admin_Participants_Invitations.py", "top_nav_admin_participants"),
                ("🧩", "Registration Game", "pages/12_Admin_Registration_Game.py", "top_nav_admin_registration_game"),
                ("🔨", "Mini Games", "pages/16_Admin_Mini_Game.py", "top_nav_admin_mini_game"),
                ("🗓️", "Schedule", "pages/09_Admin_Schedule.py", "top_nav_admin_schedule"),
                ("✅", "Results", "pages/09_Admin_Schedule.py", "top_nav_admin_results"),
                ("💾", "Backup", "pages/11_Admin_Backup_Restore.py", "top_nav_admin_backup"),
            ],
            icon_only=not text_mode,
        )

    st.divider()


def render_sidebar(user: Optional[User], *, current_page: Optional[str] = None) -> None:
    render_cangeroes_header()
    render_main_navigation(user, current_page=current_page)

    with st.sidebar:
        st.image(
            CANGEROES_LOGO_URL,
            width=190,
        )
        st.title("Weekend Tracker")
        if user:
            st.caption(f"Logged in as `{user.username or user.email or user.id}` ({user.role})")
            if st.button("Log out", width="stretch"):
                from tournament_tracker.bootstrap import get_runtime_services

                logout_user(get_runtime_services())
                st.rerun()

        st.divider()
        st.subheader("Navigation")
        gate_destination: Optional[str] = None
        if user:
            try:
                from tournament_tracker.bootstrap import get_runtime_services

                gate_destination = get_registration_gate_page(get_runtime_services(), user)
            except Exception:
                gate_destination = None

        if gate_destination:
            label = "Registration Game" if gate_destination == REGISTRATION_GAME_PAGE else "And Now We Wait"
            if st.button(label, width="stretch", key="side_nav_registration_gate"):
                st.switch_page(gate_destination)
            if st.button("My Profile", width="stretch", key="side_nav_gated_profile"):
                st.switch_page(PROFILE_PAGE)
        else:
            if st.button("Leaderboard", width="stretch", key="side_nav_leaderboard"):
                st.switch_page("pages/03_Leaderboard.py")
            if st.button("Upcoming", width="stretch", key="side_nav_upcoming"):
                st.switch_page("pages/04_Upcoming_Matches.py")
            if st.button("Past Events", width="stretch", key="side_nav_past"):
                st.switch_page("pages/05_Past_Matches.py")
            if st.button("My Profile", width="stretch", key="side_nav_profile"):
                st.switch_page(PROFILE_PAGE)
            if user and user.role == "participant":
                if st.button("Specials", width="stretch", key="side_nav_specials"):
                    st.switch_page("pages/17_Specials.py")
                if st.button("Weekend Info", width="stretch", key="side_nav_weekend_info"):
                    st.switch_page("pages/14_Weekend_Info.py")
                if st.button("Mini Games", width="stretch", key="side_nav_mini_game"):
                    st.switch_page("pages/15_Mini_Game.py")

        if user and user.role == "admin":
            st.divider()
            st.subheader("Admin")
            if st.button("Dashboard", width="stretch", key="side_nav_admin_dashboard"):
                st.switch_page("pages/07_Admin_Dashboard.py")
            if st.button("Participants & Registration", width="stretch", key="side_nav_admin_participants"):
                st.switch_page("pages/08_Admin_Participants_Invitations.py")
            if st.button("Registration Game", width="stretch", key="side_nav_admin_registration_game"):
                st.switch_page("pages/12_Admin_Registration_Game.py")
            if st.button("Mini Games", width="stretch", key="side_nav_admin_mini_game"):
                st.switch_page("pages/16_Admin_Mini_Game.py")
            if st.button("Specials", width="stretch", key="side_nav_admin_specials"):
                st.switch_page("pages/17_Specials.py")
            if st.button("Manage Schedule", width="stretch", key="side_nav_admin_schedule"):
                st.switch_page("pages/09_Admin_Schedule.py")
            if st.button("Results in Schedule", width="stretch", key="side_nav_admin_results"):
                st.switch_page("pages/09_Admin_Schedule.py")
            if st.button("Backup & Restore", width="stretch", key="side_nav_admin_backup"):
                st.switch_page("pages/11_Admin_Backup_Restore.py")
