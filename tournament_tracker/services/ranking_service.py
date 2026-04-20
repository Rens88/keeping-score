from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tournament_tracker.models import LeaderboardRow
from tournament_tracker.repository import (
    BETTING_SOURCE_TYPE,
    DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE,
    MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE,
    SQLiteRepository,
)

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
            }:
                stats.bonus_points += points_awarded

        for row in rows:
            user_id = int(row["participant_user_id"])
            match_id = int(row["match_id"])
            side_number = int(row["side_number"])
            player_outcome = self._outcome_for_side(row["outcome"], side_number)

            stats = stats_by_user.setdefault(user_id, ParticipantStats(user_id=user_id))
            stats.matches_played += 1

            if player_outcome == "win":
                stats.wins += 1
            elif player_outcome == "draw":
                stats.draws += 1
            else:
                stats.losses += 1

            base_points = POINTS[player_outcome]
            stats.total_points += base_points

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
