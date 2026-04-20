from __future__ import annotations

from typing import Optional

from tournament_tracker.models import MatchBet, utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.services.ranking_service import RankingService
from tournament_tracker.services.special_service import SpecialService


BET_OUTCOME_OPTIONS = ("side1_win", "draw", "side2_win")


class BettingService:
    def __init__(
        self,
        repo: SQLiteRepository,
        ranking_service: RankingService,
        special_service: SpecialService,
    ) -> None:
        self.repo = repo
        self.ranking_service = ranking_service
        self.special_service = special_service

    def get_available_balance(self, participant_user_id: int) -> float:
        standing = self.ranking_service.get_participant_stats(participant_user_id)
        total_points = float(standing.total_points) if standing else 0.0
        reserved_points = self.repo.sum_open_bet_stakes(participant_user_id)
        return max(0.0, round(total_points - reserved_points, 4))

    def get_existing_bet(self, *, match_id: int, participant_user_id: int) -> Optional[MatchBet]:
        return self.repo.get_match_bet(match_id=match_id, participant_user_id=participant_user_id)

    def allowed_stakes_for_participant(self, participant_user_id: int) -> tuple[int, ...]:
        balance = self.get_available_balance(participant_user_id)
        stakes: list[int] = []
        if balance >= 1:
            stakes.append(1)
        if balance >= 2:
            stakes.append(2)
        return tuple(stakes)

    def place_bet(
        self,
        *,
        participant_user_id: int,
        match_id: int,
        predicted_outcome: str,
        stake_points: int,
    ) -> MatchBet:
        if predicted_outcome not in BET_OUTCOME_OPTIONS:
            raise ValidationError("Invalid bet outcome.")
        if stake_points not in {1, 2}:
            raise ValidationError("Stake must be 1 or 2 points.")

        match = self.repo.get_match(match_id)
        if not match:
            raise NotFoundError("Match not found.")
        if self.repo.get_match_result(match_id) is not None:
            raise ValidationError("Betting closes as soon as a result exists.")
        if not self.special_service.match_allows_pre_match_actions(match):
            raise ValidationError("Betting is closed for this match.")

        existing_bet = self.repo.get_match_bet(match_id=match_id, participant_user_id=participant_user_id)
        open_balance = self.get_available_balance(participant_user_id)
        if existing_bet and existing_bet.settled_at is None:
            open_balance += existing_bet.stake_points

        if open_balance < stake_points:
            raise ValidationError("You do not have enough free points to place that bet.")

        return self.repo.upsert_match_bet(
            match_id=match_id,
            participant_user_id=participant_user_id,
            predicted_outcome=predicted_outcome,
            stake_points=float(stake_points),
            now_iso=utc_now_iso(),
        )
