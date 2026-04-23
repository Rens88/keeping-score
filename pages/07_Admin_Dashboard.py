from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration, render_form_field_label, render_page_intro
from tournament_tracker.bootstrap import get_runtime_services
from tournament_tracker.services.errors import ValidationError
from tournament_tracker.services.special_service import (
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
from tournament_tracker.ui import render_stat_tiles

st.set_page_config(page_title="Admin Dashboard", page_icon="🛡️", layout="wide")

services = get_runtime_services()
admin_user = require_admin(services, current_page="pages/07_Admin_Dashboard.py")
render_sidebar(admin_user)

render_page_intro("Admin Dashboard", "A quick snapshot of participants, matches, specials, points, and activity.", eyebrow="Admin")

if all(
    [
        services.config.seed_admin_username,
        services.config.seed_admin_email,
        services.config.seed_admin_password,
    ]
) and services.config.seed_admin_password == "change-me-now":
    st.warning(
        "Seed admin password is set to `change-me-now`. Use a stronger value in env/secrets for real events."
    )

participants = services.profile_service.list_participant_profiles()
all_matches = services.repo.list_matches()
live_matches = [m for m in all_matches if m.status == "live"]
upcoming_matches = [m for m in all_matches if m.status == "upcoming"]
completed_matches = [m for m in all_matches if m.status == "completed"]
backup_status = services.backup_service.get_offsite_backup_status()

render_stat_tiles(
    [
        ("Participants", str(len(participants))),
        ("Upcoming", str(len(upcoming_matches))),
        ("Live", str(len(live_matches))),
        ("Completed", str(len(completed_matches))),
    ]
)

st.divider()
st.subheader("Backup Status")
with st.container(border=True):
    render_stat_tiles(
        [
            ("Off-site backup", backup_status.status_label),
            ("Last successful backup", backup_status.last_success_at or "Never"),
            ("Last auto-restore", backup_status.last_restore_at or "Never"),
            ("Backup target", backup_status.bucket or "Not configured"),
        ]
    )
    st.caption(backup_status.detail_message)
    if backup_status.endpoint:
        st.caption(f"Endpoint: {backup_status.endpoint}")
    if backup_status.last_object_key:
        st.caption(f"Latest uploaded object: {backup_status.last_object_key}")
    if backup_status.last_restore_object_key:
        st.caption(f"Latest restored object: {backup_status.last_restore_object_key}")
    if backup_status.last_error_message:
        st.warning(
            "Latest backup error"
            + (f" ({backup_status.last_error_at})" if backup_status.last_error_at else "")
            + f": {backup_status.last_error_message}"
        )

def _participant_name(participant: object) -> str:
    display_name = getattr(participant, "display_name", None)
    username = getattr(participant, "username", None)
    email = getattr(participant, "email", None)
    user_id = getattr(participant, "user_id", "?")
    return str(display_name or username or email or f"User {user_id}")


def _summarize_specials(row: dict[str, object], *, status_prefix: str) -> str:
    special_labels = {
        SPECIAL_DOUBLER: "Doubler",
        SPECIAL_DOUBLE_OR_NOTHING: "Double-or-nothing",
        SPECIAL_KING_OF_THE_HILL: "King of the Hill",
        SPECIAL_WINNER_TAKES_ALL: "Winner takes it all",
        SPECIAL_CATCH_UP: "Catch-up",
        SPECIAL_WHEEL: "Wheel of Fortune",
        SPECIAL_MATCH_FIXER: "Match Fixer",
        SPECIAL_KING_FIXER: "King Fixer",
        SPECIAL_DONT_UNDERESTIMATE: "Don't underestimate my power",
    }
    labels = [
        f"{label}: {row[key]}"
        for key, label in special_labels.items()
        if str(row[key]).startswith(status_prefix)
    ]
    return ", ".join(labels) if labels else "-"


participant_options = {
    f"{_participant_name(participant)} (id {participant.user_id})": participant.user_id
    for participant in participants
}

st.divider()
st.subheader("Quick Actions")
qa1, qa2, qa3, qa4, qa5, qa6, qa7 = st.columns(7)
if qa1.button("Participants & Registration", width="stretch", key="admin_dash_quick_participants"):
    st.switch_page("pages/08_Admin_Participants_Invitations.py")
if qa2.button("Registration Game", width="stretch", key="admin_dash_quick_registration_game"):
    st.switch_page("pages/12_Admin_Registration_Game.py")
if qa3.button("Mini Games", width="stretch", key="admin_dash_quick_minigame"):
    st.switch_page("pages/16_Admin_Mini_Game.py")
if qa4.button("Specials", width="stretch", key="admin_dash_quick_specials"):
    st.switch_page("pages/17_Specials.py")
if qa5.button("Manage Schedule", width="stretch", key="admin_dash_quick_schedule"):
    st.switch_page("pages/09_Admin_Schedule.py")
if qa6.button("Results in Schedule", width="stretch", key="admin_dash_quick_results"):
    st.switch_page("pages/09_Admin_Schedule.py")
if qa7.button("Backup & Restore", width="stretch", key="admin_dash_quick_backup"):
    st.switch_page("pages/11_Admin_Backup_Restore.py")

st.divider()
st.subheader("Points Tools")
with st.container(border=True):
    if not participant_options:
        st.info("No participants available for manual point adjustments yet.")
    else:
        with st.form("admin_manual_point_adjustment_form"):
            render_form_field_label("Participant")
            selected_participant_label = st.selectbox(
                "Participant",
                list(participant_options.keys()),
                label_visibility="collapsed",
            )
            render_form_field_label("Points to add or remove")
            adjustment_points = st.number_input(
                "Points to add or remove",
                value=1.0,
                step=0.5,
                format="%.1f",
                label_visibility="collapsed",
            )
            render_form_field_label(
                "Reason",
                "This appears in the point log and recent activity feed.",
            )
            adjustment_reason = st.text_input(
                "Reason",
                value="",
                label_visibility="collapsed",
            )
            submit_adjustment = st.form_submit_button("Apply point adjustment", width="stretch")

        if submit_adjustment:
            try:
                services.ranking_service.award_manual_adjustment(
                    participant_user_id=participant_options[selected_participant_label],
                    points=float(adjustment_points),
                    reason=adjustment_reason,
                    admin_user_id=admin_user.id,
                )
                st.success("Point adjustment saved.")
                st.rerun()
            except ValidationError as exc:
                st.error(str(exc))

        st.caption(
            "Use positive values to award points and negative values to remove them. "
            "Every change is added to the point log so you can explain leaderboard swings afterwards."
        )

st.divider()
st.subheader("Recent Activity")
activity_log_rows = services.repo.list_activity_log_rows(limit=None)
activity_user_ids = [
    int(row["related_user_id"])
    for row in activity_log_rows
    if row.get("related_user_id") is not None
]
activity_user_lookup = services.repo.get_profiles_by_user_ids(activity_user_ids) if activity_user_ids else {}
point_activity_rows = services.ranking_service.list_point_activity_rows()

combined_activity_rows: list[dict[str, object]] = []
for row in activity_log_rows:
    related_user_id = row.get("related_user_id")
    related_user = activity_user_lookup.get(int(related_user_id)) if related_user_id is not None else None
    person = (
        related_user.get("display_name")
        or related_user.get("username")
        or related_user.get("email")
        if related_user
        else ""
    )
    combined_activity_rows.append(
        {
            "time": str(row["created_at"]),
            "category": str(row["event_type"]).replace("_", " "),
            "person": str(person or ""),
            "points": "",
            "details": str(row["message"]),
        }
    )

for row in point_activity_rows:
    combined_activity_rows.append(
        {
            "time": str(row["timestamp"]),
            "category": "points",
            "person": str(row["person"]),
            "points": f"{float(row['points']):+.1f}",
            "details": str(row["summary"]),
        }
    )

combined_activity_rows.sort(
    key=lambda row: (
        str(row["time"]),
        str(row["category"]),
        str(row["person"]),
        str(row["details"]),
    ),
    reverse=True,
)

if not combined_activity_rows:
    st.info("No activity yet.")
else:
    st.dataframe(
        combined_activity_rows,
        width="stretch",
        hide_index=True,
        height=520,
    )

st.divider()
st.subheader("Specials Snapshot")
special_rows = services.special_service.list_special_status_rows()
if not special_rows:
    st.info("No participant rows yet.")
else:
    st.dataframe(
        [
            {
                "name": row["name"],
                "active_now": _summarize_specials(row, status_prefix="active"),
                "available_now": _summarize_specials(row, status_prefix="available"),
                "forced_overrides": ", ".join(
                    label
                    for key, label in (
                        (SPECIAL_DOUBLER, "Doubler"),
                        (SPECIAL_DOUBLE_OR_NOTHING, "Double-or-nothing"),
                        (SPECIAL_KING_OF_THE_HILL, "King of the Hill"),
                        (SPECIAL_WINNER_TAKES_ALL, "Winner takes it all"),
                        (SPECIAL_CATCH_UP, "Catch-up"),
                        (SPECIAL_WHEEL, "Wheel of Fortune"),
                        (SPECIAL_MATCH_FIXER, "Match Fixer"),
                        (SPECIAL_KING_FIXER, "King Fixer"),
                        (SPECIAL_DONT_UNDERESTIMATE, "Don't underestimate my power"),
                    )
                    if row.get(f"{key}_override") in {"on", "off"}
                ) or "-",
            }
            for row in special_rows
        ],
        width="stretch",
        hide_index=True,
        height=320,
    )

render_bottom_decoration()
