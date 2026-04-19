from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from tournament_tracker.models import MiniGameConfig, MiniGameLeaderboardRow, User, utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.errors import ValidationError


APP_TIMEZONE = ZoneInfo("Europe/Amsterdam")
WHACK_A_MOLE_SLUG = "whack_a_mole"
DEFAULT_AWARD_SCHEME = (5, 3, 1)
DEFAULT_OPEN_DELAY_HOURS = 1
DEFAULT_DEADLINE_DELAY_DAYS = 2
WHACK_A_MOLE_HOLES = 9
WHACK_A_MOLE_TOTAL_SLOTS = 24
WHACK_A_MOLE_SLOT_DURATION_SECONDS = 0.9
WHACK_A_MOLE_DURATION_SECONDS = int(WHACK_A_MOLE_TOTAL_SLOTS * WHACK_A_MOLE_SLOT_DURATION_SECONDS)


@dataclass(frozen=True, slots=True)
class MiniGameStatus:
    state: str
    enabled: bool
    opens_at: Optional[datetime]
    deadline_at: Optional[datetime]
    award_scheme: tuple[int, ...]
    awards_applied_at: Optional[datetime]


@dataclass(frozen=True, slots=True)
class MiniGameParticipantSummary:
    attempts: int
    best_score: int
    awarded_points: float


class MiniGameService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    @staticmethod
    def local_now() -> datetime:
        return datetime.now(APP_TIMEZONE)

    @staticmethod
    def localize_naive(local_dt: datetime) -> datetime:
        if local_dt.tzinfo is not None:
            return local_dt.astimezone(APP_TIMEZONE)
        return local_dt.replace(tzinfo=APP_TIMEZONE)

    @staticmethod
    def default_open_at() -> datetime:
        return MiniGameService.local_now() + timedelta(hours=DEFAULT_OPEN_DELAY_HOURS)

    @staticmethod
    def default_deadline_at() -> datetime:
        return MiniGameService.local_now() + timedelta(days=DEFAULT_DEADLINE_DELAY_DAYS)

    @staticmethod
    def parse_award_scheme(raw_value: str | None) -> tuple[int, ...]:
        raw = (raw_value or "").strip()
        if not raw:
            return DEFAULT_AWARD_SCHEME

        values: list[int] = []
        for chunk in raw.split(","):
            piece = chunk.strip()
            if not piece:
                continue
            try:
                points = int(piece)
            except ValueError as exc:
                raise ValidationError("Award scheme must contain whole numbers separated by commas.") from exc
            if points <= 0:
                raise ValidationError("Award scheme values must be positive integers.")
            values.append(points)

        if not values:
            return DEFAULT_AWARD_SCHEME
        return tuple(values)

    @staticmethod
    def serialize_award_scheme(values: tuple[int, ...]) -> str:
        if not values:
            values = DEFAULT_AWARD_SCHEME
        return ",".join(str(value) for value in values)

    @staticmethod
    def parse_optional_datetime(raw_value: str | None) -> Optional[datetime]:
        value = (raw_value or "").strip()
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=APP_TIMEZONE)
        return parsed.astimezone(APP_TIMEZONE)

    @staticmethod
    def format_datetime(value: Optional[str | datetime]) -> str:
        if value is None:
            return "Not set"
        if isinstance(value, str):
            parsed = MiniGameService.parse_optional_datetime(value)
        else:
            parsed = value.astimezone(APP_TIMEZONE)
        if parsed is None:
            return "Not set"
        return parsed.strftime("%A %d %B %Y %H:%M")

    def get_game_config(self) -> MiniGameConfig:
        return MiniGameConfig(
            enabled=(self.repo.get_app_setting("whack_a_mole_enabled") or "").strip().lower() == "true",
            opens_at=(self.repo.get_app_setting("whack_a_mole_opens_at") or "").strip() or None,
            deadline_at=(self.repo.get_app_setting("whack_a_mole_deadline_at") or "").strip() or None,
            award_scheme=self.parse_award_scheme(self.repo.get_app_setting("whack_a_mole_award_scheme")),
            awards_applied_at=(self.repo.get_app_setting("whack_a_mole_awards_applied_at") or "").strip() or None,
        )

    def get_status(self, now: Optional[datetime] = None) -> MiniGameStatus:
        config = self.get_game_config()
        current_time = now.astimezone(APP_TIMEZONE) if now is not None else self.local_now()
        opens_at = self.parse_optional_datetime(config.opens_at)
        deadline_at = self.parse_optional_datetime(config.deadline_at)
        awards_applied_at = self.parse_optional_datetime(config.awards_applied_at)

        if not config.enabled:
            state = "disabled"
        elif opens_at and current_time < opens_at:
            state = "scheduled"
        elif deadline_at and current_time >= deadline_at:
            state = "closed"
        else:
            state = "live"

        return MiniGameStatus(
            state=state,
            enabled=config.enabled,
            opens_at=opens_at,
            deadline_at=deadline_at,
            award_scheme=config.award_scheme,
            awards_applied_at=awards_applied_at,
        )

    def update_game_config(
        self,
        *,
        admin_user_id: int,
        enabled: bool,
        opens_at: datetime,
        deadline_at: datetime,
        award_scheme: tuple[int, ...],
    ) -> None:
        local_open = self.localize_naive(opens_at)
        local_deadline = self.localize_naive(deadline_at)
        if local_deadline <= local_open:
            raise ValidationError("The deadline must be after the opening time.")

        now_iso = utc_now_iso()
        self.repo.set_app_setting(
            key="whack_a_mole_enabled",
            value="true" if enabled else "false",
            updated_at=now_iso,
        )
        self.repo.set_app_setting(
            key="whack_a_mole_opens_at",
            value=local_open.isoformat(),
            updated_at=now_iso,
        )
        self.repo.set_app_setting(
            key="whack_a_mole_deadline_at",
            value=local_deadline.isoformat(),
            updated_at=now_iso,
        )
        self.repo.set_app_setting(
            key="whack_a_mole_award_scheme",
            value=self.serialize_award_scheme(award_scheme),
            updated_at=now_iso,
        )
        self.repo.log_activity(
            event_type="minigame_config_updated",
            message=(
                "Admin updated the Whack-a-mole schedule "
                f"(enabled={enabled}, opens={local_open.isoformat()}, deadline={local_deadline.isoformat()})"
            ),
            created_at=now_iso,
            related_user_id=admin_user_id,
        )

    def list_leaderboard(self) -> list[MiniGameLeaderboardRow]:
        runs = self.repo.list_minigame_runs(WHACK_A_MOLE_SLUG)
        awards_by_user = {
            award.participant_user_id: float(award.points_awarded)
            for award in self.repo.list_minigame_awards(WHACK_A_MOLE_SLUG)
        }
        if not runs:
            return []

        attempts_by_user: dict[int, int] = defaultdict(int)
        best_by_user: dict[int, dict[str, object]] = {}

        for row in runs:
            user_id = int(row["participant_user_id"])
            attempts_by_user[user_id] += 1

            display_name = (
                row["display_name"]
                or row["username"]
                or row["email"]
                or f"User {user_id}"
            )
            candidate = {
                "user_id": user_id,
                "display_name": str(display_name),
                "motto": str(row["motto"] or ""),
                "photo_blob": row["photo_blob"],
                "photo_mime_type": row["photo_mime_type"],
                "best_score": int(row["score"]),
                "best_played_at": str(row["played_at"]),
            }

            current = best_by_user.get(user_id)
            if current is None:
                best_by_user[user_id] = candidate
                continue

            current_score = int(current["best_score"])
            current_played_at = str(current["best_played_at"])
            candidate_score = int(candidate["best_score"])
            candidate_played_at = str(candidate["best_played_at"])

            if candidate_score > current_score or (
                candidate_score == current_score and candidate_played_at < current_played_at
            ):
                best_by_user[user_id] = candidate

        ordered = sorted(
            best_by_user.values(),
            key=lambda row: (-int(row["best_score"]), str(row["best_played_at"]), int(row["user_id"])),
        )

        leaderboard: list[MiniGameLeaderboardRow] = []
        for rank, row in enumerate(ordered, start=1):
            user_id = int(row["user_id"])
            leaderboard.append(
                MiniGameLeaderboardRow(
                    rank=rank,
                    user_id=user_id,
                    display_name=str(row["display_name"]),
                    motto=str(row["motto"]),
                    photo_blob=row["photo_blob"],
                    photo_mime_type=row["photo_mime_type"],
                    best_score=int(row["best_score"]),
                    attempts=attempts_by_user[user_id],
                    best_played_at=str(row["best_played_at"]),
                    awarded_points=awards_by_user.get(user_id, 0.0),
                )
            )

        return leaderboard

    def get_participant_summary(self, participant_user_id: int) -> MiniGameParticipantSummary:
        attempts = 0
        best_score = 0
        awarded_points = 0.0

        for row in self.repo.list_minigame_runs(WHACK_A_MOLE_SLUG):
            if int(row["participant_user_id"]) != participant_user_id:
                continue
            attempts += 1
            best_score = max(best_score, int(row["score"]))

        for award in self.repo.list_minigame_awards(WHACK_A_MOLE_SLUG):
            if award.participant_user_id == participant_user_id:
                awarded_points += float(award.points_awarded)

        return MiniGameParticipantSummary(
            attempts=attempts,
            best_score=best_score,
            awarded_points=round(awarded_points, 2),
        )

    def record_run(
        self,
        *,
        user_id: int,
        score: int,
        duration_seconds: int,
        started_at: Optional[datetime] = None,
        metadata: Optional[dict[str, object]] = None,
    ) -> None:
        user = self._require_participant(user_id)
        if not user.registration_game_completed:
            raise ValidationError("Finish the registration game before playing the minigame.")

        status = self.get_status()
        if started_at is not None:
            started_at = started_at.astimezone(APP_TIMEZONE)
        started_before_deadline = bool(
            started_at is not None and status.deadline_at is not None and started_at < status.deadline_at
        )
        if status.state != "live" and not started_before_deadline:
            raise ValidationError("Whack-a-mole is not live right now.")
        if score < 0:
            raise ValidationError("Score cannot be negative.")

        metadata_json = json.dumps(metadata, separators=(",", ":"), sort_keys=True) if metadata else None
        now_iso = utc_now_iso()
        self.repo.create_minigame_run(
            game_slug=WHACK_A_MOLE_SLUG,
            participant_user_id=user_id,
            score=int(score),
            duration_seconds=int(duration_seconds),
            played_at=now_iso,
            metadata_json=metadata_json,
        )
        self.repo.log_activity(
            event_type="minigame_run_recorded",
            message=f"Participant {user_id} posted a Whack-a-mole score of {int(score)}",
            created_at=now_iso,
            related_user_id=user_id,
        )

    def apply_awards(self, *, admin_user_id: int) -> list[MiniGameLeaderboardRow]:
        status = self.get_status()
        if status.deadline_at is None:
            raise ValidationError("Set a deadline before awarding points.")
        if self.local_now() < status.deadline_at:
            raise ValidationError("You can only award points after the deadline has passed.")

        leaderboard = self.list_leaderboard()
        if not leaderboard:
            raise ValidationError("No Whack-a-mole scores have been posted yet.")

        now_iso = utc_now_iso()
        awards: list[tuple[int, int, float, str, int]] = []
        for placement, points in enumerate(status.award_scheme, start=1):
            if placement > len(leaderboard):
                break
            row = leaderboard[placement - 1]
            awards.append((row.user_id, placement, float(points), now_iso, admin_user_id))

        self.repo.replace_minigame_awards(
            game_slug=WHACK_A_MOLE_SLUG,
            awards=awards,
        )
        self.repo.set_app_setting(
            key="whack_a_mole_awards_applied_at",
            value=now_iso,
            updated_at=now_iso,
        )
        self.repo.log_activity(
            event_type="minigame_awards_applied",
            message=(
                "Admin awarded Whack-a-mole weekend points "
                f"using scheme {self.serialize_award_scheme(status.award_scheme)}"
            ),
            created_at=now_iso,
            related_user_id=admin_user_id,
        )
        return self.list_leaderboard()

    def _require_participant(self, user_id: int) -> User:
        user = self.repo.get_user_by_id(user_id)
        if not user or user.role != "participant":
            raise ValidationError("Participant account not found.")
        return user
