from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.security import hash_password

OUTPUT_PATH = PROJECT_ROOT / "demo_state" / "weekend_tracker_requested_demo_state.sqlite3"
DEMO_PASSWORD = "1234"

PLAYERS = [
    ("Thijs", "Altijd rustig, altijd punten."),
    ("Rens", "Eerst koffie, dan winst."),
    ("Casper", "Geen stress, wel focus."),
    ("Jasper", "Ik ben er zo... echt."),
    ("Siemen", "Vandaag pak ik de dub."),
    ("Sebas", "Spelen alsof het finale is."),
    ("Rob", "Winnen met stijl."),
    ("Joost", "Eerst verdedigen, dan knallen."),
    ("Quinten", "Elke ronde telt."),
]


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    repo = SQLiteRepository(OUTPUT_PATH)
    repo.apply_migrations()

    now = datetime.now(timezone.utc)

    admin_created_at = utc_iso(now - timedelta(days=6))
    admin = repo.create_user(
        username="admin",
        email="admin@demo.local",
        password_hash=hash_password(DEMO_PASSWORD),
        role="admin",
        created_at=admin_created_at,
    )

    user_ids: dict[str, int] = {}

    for idx, (name, motto) in enumerate(PLAYERS):
        created_at = utc_iso(now - timedelta(days=5, hours=idx))
        user = repo.create_user(
            username=name,
            email=f"{name.lower()}@demo.local",
            password_hash=hash_password(DEMO_PASSWORD),
            role="participant",
            created_at=created_at,
        )
        repo.upsert_participant_profile(
            user_id=user.id,
            display_name=name,
            motto=motto,
            photo_blob=None,
            photo_mime_type=None,
            now_iso=created_at,
        )
        user_ids[name] = user.id

        # Create and directly consume invitation records for realistic state.
        token_hash = hashlib.sha256(f"invite-{name}".encode("utf-8")).hexdigest()
        invitation = repo.create_invitation(
            token_hash=token_hash,
            created_by_user_id=admin.id,
            expires_at=utc_iso(now + timedelta(days=14)),
            now_iso=utc_iso(now - timedelta(days=5, hours=idx)),
            note=f"Invite for {name}",
        )
        repo.mark_invitation_used(
            invitation_id=invitation.id,
            user_id=user.id,
            used_at=utc_iso(now - timedelta(days=5, hours=idx - 1)),
        )

    def create_match(
        *,
        order: int,
        days_ago: int,
        game_type: str,
        status: str,
        side1: list[str],
        side2: list[str],
        outcome: str | None = None,
        notes: str | None = None,
    ) -> int:
        scheduled = utc_iso(now - timedelta(days=days_ago, hours=12 - order))
        created_at = utc_iso(now - timedelta(days=days_ago, hours=13 - order))
        match = repo.create_match(
            game_type=game_type,
            scheduled_at=scheduled,
            scheduled_order=order,
            status=status,
            created_by_user_id=admin.id,
            now_iso=created_at,
            side1_name="Team A",
            side2_name="Team B",
            side1_participant_ids=[user_ids[n] for n in side1],
            side2_participant_ids=[user_ids[n] for n in side2],
        )

        if outcome:
            repo.upsert_match_result(
                match_id=match.id,
                outcome=outcome,
                entered_by_user_id=admin.id,
                entered_at=utc_iso(now - timedelta(days=days_ago, hours=11 - order)),
                notes=notes,
                mark_completed=True,
            )
        return match.id

    # 4 fake past rounds (8 completed matches), Jasper plays none because he is late.
    m1 = create_match(
        order=1,
        days_ago=4,
        game_type="Football",
        status="upcoming",
        side1=["Thijs", "Rens"],
        side2=["Casper", "Siemen"],
        outcome="side1_win",
        notes="Round 1 opener",
    )
    m2 = create_match(
        order=2,
        days_ago=4,
        game_type="Darts",
        status="upcoming",
        side1=["Rob"],
        side2=["Joost"],
        outcome="draw",
        notes="Round 1 quick duel",
    )
    m3 = create_match(
        order=3,
        days_ago=3,
        game_type="Padel",
        status="upcoming",
        side1=["Thijs", "Sebas"],
        side2=["Rob", "Quinten"],
        outcome="side2_win",
        notes="Round 2 doubles",
    )
    m4 = create_match(
        order=4,
        days_ago=3,
        game_type="Petanque",
        status="upcoming",
        side1=["Rens"],
        side2=["Casper"],
        outcome="side1_win",
        notes="Round 2 singles",
    )
    m5 = create_match(
        order=5,
        days_ago=2,
        game_type="Lasergame",
        status="upcoming",
        side1=["Siemen", "Sebas"],
        side2=["Joost", "Quinten"],
        outcome="draw",
        notes="Round 3 team battle",
    )
    m6 = create_match(
        order=6,
        days_ago=2,
        game_type="Football",
        status="upcoming",
        side1=["Thijs"],
        side2=["Rob"],
        outcome="side2_win",
        notes="Round 3 extra match",
    )
    m7 = create_match(
        order=7,
        days_ago=1,
        game_type="Darts",
        status="upcoming",
        side1=["Rens", "Quinten"],
        side2=["Casper", "Rob"],
        outcome="side2_win",
        notes="Round 4 doubles",
    )
    m8 = create_match(
        order=8,
        days_ago=1,
        game_type="Padel",
        status="upcoming",
        side1=["Thijs"],
        side2=["Siemen"],
        outcome="draw",
        notes="Round 4 close finish",
    )

    # Upcoming and live matches for testing views.
    m9 = create_match(
        order=9,
        days_ago=-1,
        game_type="Padel",
        status="upcoming",
        side1=["Rob", "Joost"],
        side2=["Casper", "Sebas"],
    )
    m10 = create_match(
        order=10,
        days_ago=-1,
        game_type="Darts",
        status="upcoming",
        side1=["Rens"],
        side2=["Siemen"],
    )
    create_match(
        order=11,
        days_ago=0,
        game_type="Football",
        status="live",
        side1=["Thijs", "Quinten"],
        side2=["Rob", "Sebas"],
    )

    # Used specials (doublers)
    repo.create_doubler_activation(
        participant_user_id=user_ids["Thijs"],
        match_id=m1,
        now_iso=utc_iso(now - timedelta(days=4, hours=13)),
        activated_by_user_id=user_ids["Thijs"],
    )
    repo.create_doubler_activation(
        participant_user_id=user_ids["Quinten"],
        match_id=m5,
        now_iso=utc_iso(now - timedelta(days=2, hours=13)),
        activated_by_user_id=user_ids["Quinten"],
    )
    repo.create_doubler_activation(
        participant_user_id=user_ids["Rob"],
        match_id=m9,
        now_iso=utc_iso(now - timedelta(hours=1)),
        activated_by_user_id=user_ids["Rob"],
    )

    for message in [
        "Demo state generated",
        "4 completed rounds loaded",
        "Upcoming schedule prepared",
        "Doublers seeded for test",
    ]:
        repo.log_activity(
            event_type="demo_seed",
            message=message,
            created_at=utc_iso(now),
            related_user_id=admin.id,
        )

    print(f"Wrote demo exported state: {OUTPUT_PATH}")
    print("Logins/password for participants: username is literal name, password is 1234")
    print("Admin login: username admin, password 1234")


if __name__ == "__main__":
    main()
