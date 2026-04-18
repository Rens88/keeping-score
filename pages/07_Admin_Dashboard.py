from __future__ import annotations

import streamlit as st

from tournament_tracker.branding import render_bottom_decoration
from tournament_tracker.bootstrap import get_services
from tournament_tracker.session import render_sidebar, require_admin

st.set_page_config(page_title="Admin Dashboard", page_icon="🛡️", layout="wide")

services = get_services()
admin_user = require_admin(services)
render_sidebar(admin_user)

st.title("Admin Dashboard")

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

col1, col2, col3, col4 = st.columns(4)
col1.metric("Participants", len(participants))
col2.metric("Upcoming", len(upcoming_matches))
col3.metric("Live", len(live_matches))
col4.metric("Completed", len(completed_matches))

st.divider()
st.subheader("Quick Actions")
qa1, qa2, qa3, qa4 = st.columns(4)
if qa1.button("Participants & Invitations", width="stretch", key="admin_dash_quick_participants"):
    st.switch_page("pages/08_Admin_Participants_Invitations.py")
if qa2.button("Manage Schedule", width="stretch", key="admin_dash_quick_schedule"):
    st.switch_page("pages/09_Admin_Schedule.py")
if qa3.button("Enter/Edit Results", width="stretch", key="admin_dash_quick_results"):
    st.switch_page("pages/10_Admin_Results.py")
if qa4.button("Backup & Restore", width="stretch", key="admin_dash_quick_backup"):
    st.switch_page("pages/11_Admin_Backup_Restore.py")

st.divider()
st.subheader("Recent Activity")
activity = services.match_service.list_recent_activity(limit=12)
if not activity:
    st.info("No activity yet.")
else:
    for item in activity:
        st.write(f"- {item['timestamp']}: {item['message']}")

st.divider()
st.subheader("Doubler Snapshot")
rows = services.match_service.list_doubler_status_rows()
if not rows:
    st.info("No participant rows yet.")
else:
    st.dataframe(
        [
            {
                "name": row["name"],
                "doubler_used": "yes" if row["doubler_used"] else "no",
                "match_id": row["match_id"],
                "game_type": row["game_type"],
                "match_status": row["match_status"],
                "activated_at": row["activated_at"],
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )

render_bottom_decoration()
