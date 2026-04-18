from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tournament_tracker.bootstrap import initialize_repository
from tournament_tracker.models import utc_now_iso
from tournament_tracker.security import hash_password
from tournament_tracker.services.match_service import MatchService

DEMO_PASSWORD = "demo-pass-123"

DEMO_PARTICIPANTS = [
    ("alex", "Alex", "No excuses, only rematches."),
    ("sam", "Sam", "Play fast, complain later."),
    ("jamie", "Jamie", "Weekend MVP in progress."),
    ("casey", "Casey", "Precision beats power."),
    ("riley", "Riley", "Pressure is a privilege."),
    ("jordan", "Jordan", "One more game."),
    ("morgan", "Morgan", "Calm hands, loud wins."),
    ("taylor", "Taylor", "No bad vibes, just points."),
    ("drew", "Drew", "Respect the scoreboard."),
    ("robin", "Robin", "Trust the process."),
    ("quinn", "Quinn", "Eyes on the finals."),
    ("sky", "Sky", "Every draw matters."),
    ("blake", "Blake", "Risk it for ranking."),
    ("devon", "Devon", "Still undefeated in my head."),
]


def pairwise(items: list[int]) -> Iterable[tuple[int, int]]:
    for i in range(0, len(items), 2):
        if i + 1 < len(items):
            yield items[i], items[i + 1]


def main() -> None:
    config, repo = initialize_repository()
    match_service = MatchService(repo)
    admin_user = repo.get_first_admin()
    if not admin_user:
        raise RuntimeError(
            "No admin account found. Configure SEED_ADMIN_USERNAME, SEED_ADMIN_EMAIL, "
            "and SEED_ADMIN_PASSWORD for first startup."
        )

    participant_ids: list[int] = []
    now = datetime.utcnow()

    for idx, (username, display_name, motto) in enumerate(DEMO_PARTICIPANTS, start=1):
        existing = repo.get_user_by_username(username)
        if existing:
            participant_ids.append(existing.id)
            continue

        user = repo.create_user(
            username=username,
            email=f"{username}@demo.local",
            password_hash=hash_password(DEMO_PASSWORD),
            role="participant",
            created_at=utc_now_iso(),
        )
        repo.upsert_participant_profile(
            user_id=user.id,
            display_name=display_name,
            motto=motto,
            photo_blob=None,
            photo_mime_type=None,
            now_iso=utc_now_iso(),
        )
        participant_ids.append(user.id)

    existing_matches = repo.list_matches()
    if not existing_matches:
        game_types = [
            "Football",
            "Padel",
            "Darts",
            "Petanque",
            "Lasergame",
            "Padel",
            "Football",
        ]

        matches_created = []
        for i, (a, b) in enumerate(pairwise(participant_ids), start=1):
            game_type = game_types[(i - 1) % len(game_types)]
            scheduled_dt = now + timedelta(hours=i)
            match = match_service.create_match(
                game_type=game_type,
                scheduled_at=scheduled_dt,
                scheduled_order=i,
                status="upcoming",
                created_by_user_id=admin_user.id,
                side1_name="Team A",
                side2_name="Team B",
                side1_participant_ids=[a],
                side2_participant_ids=[b],
            )
            matches_created.append(match)

        if matches_created:
            match_service.activate_doubler(
                participant_user_id=participant_ids[0],
                match_id=matches_created[0].id,
                actor_user_id=participant_ids[0],
            )

            outcomes = ["side1_win", "draw", "side2_win", "side1_win"]
            for match, outcome in zip(matches_created[:4], outcomes):
                match_service.set_match_result(
                    match_id=match.id,
                    outcome=outcome,
                    entered_by_user_id=admin_user.id,
                    notes="Demo result",
                )

    print("Demo data ready.")
    print(f"DB path: {config.db_path}")
    print(f"Demo participant password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
