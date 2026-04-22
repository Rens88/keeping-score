from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from tournament_tracker.models import LeaderboardRow, utc_now_iso
from tournament_tracker.repository import (
    ADMIN_ADJUSTMENT_SOURCE_TYPE,
    BETTING_SOURCE_TYPE,
    COMPETITION_RANKING_SOURCE_TYPE,
    DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE,
    MATCH_SPECIAL_BONUS_SOURCE_TYPE,
    MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE,
    REGISTRATION_GAME_SOURCE_TYPE,
    SQLiteRepository,
)
from tournament_tracker.services.errors import ValidationError

POINTS = {
    "win": 4.0,
    "draw": 2.5,
    "loss": 1.0,
}


@dataclass(slots=True)
class ParticipantStats:
    user_id: int
    total_points: float = 0.0
    bonus_points: float = 0.0
    matches_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0


class RankingService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    @staticmethod
    def _outcome_for_side(match_outcome: str, side_number: int) -> str:
        if match_outcome == "draw":
            return "draw"
        if match_outcome == "side1_win":
            return "win" if side_number == 1 else "loss"
        if match_outcome == "side2_win":
            return "win" if side_number == 2 else "loss"
        raise ValueError(f"Unknown match outcome: {match_outcome}")

    @staticmethod
    def _display_name(row: object) -> str:
        display_name = getattr(row, "display_name", None)
        username = getattr(row, "username", None)
        email = getattr(row, "email", None)
        user_id = getattr(row, "user_id", "?")
        return str(display_name or username or email or f"User {user_id}")

    @staticmethod
    def _format_points(points: float) -> str:
        return f"{points:+.1f}"

    @staticmethod
    def _parse_match_id(source_key: str) -> Optional[int]:
        if not source_key.startswith("match:"):
            return None
        try:
            return int(source_key.split(":", 2)[1])
        except Exception:
            return None

    def compute_leaderboard(self) -> list[LeaderboardRow]:
        rows = self.repo.list_completed_match_player_rows()
        doubler_user_ids = {
            activation.participant_user_id
            for activation in self.repo.list_match_special_activations(special_key="doubler")
        }
        participants = self.repo.list_participants()
        competition_awards = self.repo.list_competition_point_award_rows()

        stats_by_user: dict[int, ParticipantStats] = {}

        for participant in participants:
            stats = stats_by_user.setdefault(participant.user_id, ParticipantStats(user_id=participant.user_id))
            stats.total_points = 0.0

        # Registration, ranking-based minigames, and future multi-competitor competitions
        # all flow through the same generic award layer before match points are added.
        for award_row in competition_awards:
            user_id = int(award_row["participant_user_id"])
            stats = stats_by_user.setdefault(user_id, ParticipantStats(user_id=user_id))
            points_awarded = float(award_row["points_awarded"])
            stats.total_points += points_awarded
            if award_row["source_type"] in {
                MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE,
                BETTING_SOURCE_TYPE,
                DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE,
                MATCH_SPECIAL_BONUS_SOURCE_TYPE,
            }:
                stats.bonus_points += points_awarded

        for row in rows:
            user_id = int(row["participant_user_id"])
            side_number = int(row["side_number"])
            player_outcome = self._outcome_for_side(str(row["outcome"]), side_number)

            stats = stats_by_user.setdefault(user_id, ParticipantStats(user_id=user_id))
            stats.matches_played += 1

            if player_outcome == "win":
                stats.wins += 1
            elif player_outcome == "draw":
                stats.draws += 1
            else:
                stats.losses += 1

            stats.total_points += POINTS[player_outcome]

        if not stats_by_user:
            return []

        profile_map = {participant.user_id: participant for participant in participants}

        ordered = sorted(
            stats_by_user.values(),
            key=lambda s: (-s.total_points, -s.wins, -s.draws, s.user_id),
        )

        leaderboard: list[LeaderboardRow] = []
        rank = 0
        previous_key: Optional[tuple[float, int, int]] = None

        for idx, item in enumerate(ordered, start=1):
            current_key = (round(item.total_points, 5), item.wins, item.draws)
            if previous_key != current_key:
                rank = idx
                previous_key = current_key

            profile = profile_map.get(item.user_id)
            display_name = (
                (profile.display_name if profile else None)
                or (profile.username if profile else None)
                or (profile.email if profile else None)
                or f"User {item.user_id}"
            )

            leaderboard.append(
                LeaderboardRow(
                    rank=rank,
                    user_id=item.user_id,
                    display_name=str(display_name),
                    motto=(profile.motto if profile and profile.motto else "") if profile else "",
                    photo_blob=profile.photo_blob if profile else None,
                    photo_mime_type=profile.photo_mime_type if profile else None,
                    bonus_points=round(item.bonus_points, 2),
                    total_points=round(item.total_points, 2),
                    matches_played=item.matches_played,
                    wins=item.wins,
                    draws=item.draws,
                    losses=item.losses,
                    doubler_used=item.user_id in doubler_user_ids,
                )
            )

        return leaderboard

    def get_participant_stats(self, participant_user_id: int) -> Optional[LeaderboardRow]:
        leaderboard = self.compute_leaderboard()
        for row in leaderboard:
            if row.user_id == participant_user_id:
                return row
        return None

    def _build_completed_match_context(
        self,
    ) -> tuple[
        dict[int, dict[str, object]],
        dict[int, dict[int, str]],
        dict[int, dict[int, list[str]]],
        dict[int, list[dict[str, object]]],
    ]:
        completed_match_rows = self.repo.list_completed_match_rows_for_scoring()
        match_rows_by_id = {int(row["match_id"]): row for row in completed_match_rows}
        participant_rows = self.repo.list_match_participant_rows(list(match_rows_by_id.keys()))

        side_labels_by_match: dict[int, dict[int, str]] = {}
        side_members_by_match: dict[int, dict[int, list[str]]] = {}
        participant_rows_by_match: dict[int, list[dict[str, object]]] = {}

        for row in participant_rows:
            match_id = int(row["match_id"])
            side_number = int(row["side_number"])
            side_label = str(row["side_name"] or f"Side {side_number}")
            participant_name = str(
                row["display_name"]
                or row["username"]
                or row["email"]
                or f"User {row['user_id']}"
            )
            side_labels_by_match.setdefault(match_id, {})[side_number] = side_label
            side_members_by_match.setdefault(match_id, {}).setdefault(side_number, []).append(participant_name)
            participant_rows_by_match.setdefault(match_id, []).append(dict(row))

        return match_rows_by_id, side_labels_by_match, side_members_by_match, participant_rows_by_match

    def _match_label(
        self,
        match_id: int,
        match_rows_by_id: dict[int, dict[str, object]],
    ) -> str:
        row = match_rows_by_id.get(match_id)
        if not row:
            return f"Match #{match_id}"
        return f"{row['game_type']} (#{match_id})"

    def _match_points_summary(
        self,
        *,
        match_id: int,
        game_type: str,
        player_outcome: str,
        side_number: int,
        side_labels_by_match: dict[int, dict[int, str]],
        side_members_by_match: dict[int, dict[int, list[str]]],
    ) -> str:
        outcome_label = {
            "win": "Won",
            "draw": "Drew",
            "loss": "Lost",
        }.get(player_outcome, player_outcome.title())
        opponent_side_number = 2 if side_number == 1 else 1
        side_label = side_labels_by_match.get(match_id, {}).get(side_number, f"Side {side_number}")
        opponent_members = side_members_by_match.get(match_id, {}).get(opponent_side_number, [])
        opponent_label = " + ".join(opponent_members) or side_labels_by_match.get(match_id, {}).get(
            opponent_side_number,
            f"Side {opponent_side_number}",
        )
        return f"{outcome_label} {game_type} as {side_label} vs {opponent_label}"

    def _award_summary(
        self,
        award_row: dict[str, object],
        match_rows_by_id: dict[int, dict[str, object]],
    ) -> str:
        source_type = str(award_row["source_type"])
        source_label = str(award_row["source_label"])
        source_key = str(award_row["source_key"])
        placement = award_row["placement"]
        match_id = self._parse_match_id(source_key)
        match_label = self._match_label(match_id, match_rows_by_id) if match_id is not None else None

        if source_type == BETTING_SOURCE_TYPE:
            return f"Bet settled on {match_label}" if match_label else "Bet settled"
        if source_type == MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE:
            return (
                f"Special-adjusted match points for {match_label}"
                if match_label
                else "Special-adjusted match points"
            )
        if source_type == MATCH_SPECIAL_BONUS_SOURCE_TYPE:
            return f"{source_label} on {match_label}" if match_label else source_label
        if source_type == DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE:
            return "Double-or-nothing bonus"
        if source_type == REGISTRATION_GAME_SOURCE_TYPE:
            return source_label
        if source_type == COMPETITION_RANKING_SOURCE_TYPE and placement is not None:
            return f"{source_label} (place {int(placement)})"
        return source_label

    def build_point_ledger_map(
        self,
        participant_user_ids: Optional[list[int]] = None,
    ) -> dict[int, list[dict[str, object]]]:
        filter_ids = set(participant_user_ids) if participant_user_ids else None
        ledger_map: dict[int, list[dict[str, object]]] = {}
        match_rows_by_id, side_labels_by_match, side_members_by_match, participant_rows_by_match = (
            self._build_completed_match_context()
        )

        for match_id, match_row in match_rows_by_id.items():
            outcome = str(match_row["outcome"])
            entered_at = str(match_row["entered_at"])
            game_type = str(match_row["game_type"])
            for participant_row in participant_rows_by_match.get(match_id, []):
                participant_user_id = int(participant_row["user_id"])
                if filter_ids is not None and participant_user_id not in filter_ids:
                    continue
                side_number = int(participant_row["side_number"])
                player_outcome = self._outcome_for_side(outcome, side_number)
                ledger_map.setdefault(participant_user_id, []).append(
                    {
                        "timestamp": entered_at,
                        "summary": self._match_points_summary(
                            match_id=match_id,
                            game_type=game_type,
                            player_outcome=player_outcome,
                            side_number=side_number,
                            side_labels_by_match=side_labels_by_match,
                            side_members_by_match=side_members_by_match,
                        ),
                        "points": POINTS[player_outcome],
                        "kind": "match",
                    }
                )

        for award_row in self.repo.list_competition_point_award_rows():
            participant_user_id = int(award_row["participant_user_id"])
            if filter_ids is not None and participant_user_id not in filter_ids:
                continue
            ledger_map.setdefault(participant_user_id, []).append(
                {
                    "timestamp": str(award_row["awarded_at"]),
                    "summary": self._award_summary(award_row, match_rows_by_id),
                    "points": float(award_row["points_awarded"]),
                    "kind": str(award_row["source_type"]),
                }
            )

        for rows in ledger_map.values():
            rows.sort(
                key=lambda row: (
                    str(row["timestamp"]),
                    float(row["points"]),
                    str(row["summary"]),
                ),
                reverse=True,
            )

        return ledger_map

    def list_point_ledger_rows(self, participant_user_id: int) -> list[dict[str, object]]:
        return self.build_point_ledger_map([participant_user_id]).get(participant_user_id, [])

    def list_point_activity_rows(self) -> list[dict[str, object]]:
        participants = self.repo.list_participants()
        participant_map = {
            participant.user_id: self._display_name(participant)
            for participant in participants
        }
        ledger_map = self.build_point_ledger_map(list(participant_map.keys()))

        rows: list[dict[str, object]] = []
        for participant_user_id, ledger_rows in ledger_map.items():
            participant_name = participant_map.get(participant_user_id, f"User {participant_user_id}")
            for ledger_row in ledger_rows:
                rows.append(
                    {
                        "timestamp": str(ledger_row["timestamp"]),
                        "category": "points",
                        "person": participant_name,
                        "points": float(ledger_row["points"]),
                        "summary": str(ledger_row["summary"]),
                    }
                )

        rows.sort(
            key=lambda row: (
                str(row["timestamp"]),
                float(row["points"]),
                str(row["summary"]),
            ),
            reverse=True,
        )
        return rows

    def award_manual_adjustment(
        self,
        *,
        participant_user_id: int,
        points: float,
        reason: str,
        admin_user_id: int,
    ) -> None:
        clean_reason = (reason or "").strip()
        if abs(points) < 1e-9:
            raise ValidationError("Adjustment must be greater than 0 points or less than 0 points.")
        if not clean_reason:
            raise ValidationError("Add a short reason so the point history stays readable.")

        participant = self.repo.get_user_with_profile(participant_user_id)
        if not participant or participant.role != "participant":
            raise ValidationError("Choose a valid participant for the point adjustment.")

        now_iso = utc_now_iso()
        source_key = (
            "adjustment:"
            f"{participant_user_id}:"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}:"
            f"{uuid4().hex}"
        )
        source_label = f"Admin adjustment: {clean_reason}"
        self.repo.upsert_competition_point_award(
            participant_user_id=participant_user_id,
            source_type=ADMIN_ADJUSTMENT_SOURCE_TYPE,
            source_key=source_key,
            source_label=source_label,
            placement=None,
            points_awarded=round(float(points), 4),
            awarded_at=now_iso,
            awarded_by_user_id=admin_user_id,
        )
        participant_name = self._display_name(participant)
        self.repo.log_activity(
            event_type="admin_points_adjusted",
            message=f"Admin adjusted {participant_name} by {self._format_points(float(points))} points ({clean_reason}).",
            created_at=now_iso,
            related_user_id=participant_user_id,
        )
