from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from tournament_tracker.models import Match, MatchSpecialActivation, ParticipantSpecial, utc_now_iso
from tournament_tracker.repository import (
    BETTING_SOURCE_TYPE,
    DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE,
    MATCH_SPECIAL_BONUS_SOURCE_TYPE,
    MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE,
    SQLiteRepository,
)
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.services.ranking_service import POINTS, RankingService


SPECIAL_DOUBLER = "doubler"
SPECIAL_DOUBLE_OR_NOTHING = "double_or_nothing"
SPECIAL_KING_OF_THE_HILL = "king_of_the_hill"
SPECIAL_WINNER_TAKES_ALL = "winner_takes_it_all"
SPECIAL_CATCH_UP = "catch_up_mode"
SPECIAL_WHEEL = "wheel_of_fortune"
SPECIAL_MATCH_FIXER = "match_fixer"
SPECIAL_KING_FIXER = "king_fixer"
SPECIAL_DONT_UNDERESTIMATE = "dont_underestimate_my_power"

SPECIAL_KEYS = (
    SPECIAL_DOUBLER,
    SPECIAL_DOUBLE_OR_NOTHING,
    SPECIAL_KING_OF_THE_HILL,
    SPECIAL_WINNER_TAKES_ALL,
    SPECIAL_CATCH_UP,
    SPECIAL_WHEEL,
    SPECIAL_MATCH_FIXER,
    SPECIAL_KING_FIXER,
    SPECIAL_DONT_UNDERESTIMATE,
)
MANUAL_MATCH_SPECIAL_KEYS = (
    SPECIAL_DOUBLER,
    SPECIAL_DOUBLE_OR_NOTHING,
    SPECIAL_KING_OF_THE_HILL,
    SPECIAL_WINNER_TAKES_ALL,
    SPECIAL_WHEEL,
    SPECIAL_MATCH_FIXER,
    SPECIAL_KING_FIXER,
    SPECIAL_DONT_UNDERESTIMATE,
)
MATCH_RELATED_AWARD_SOURCE_TYPES = (
    MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE,
    BETTING_SOURCE_TYPE,
    DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE,
    MATCH_SPECIAL_BONUS_SOURCE_TYPE,
)
SPECIAL_OVERRIDE_PREFIX = "special_override:"
WHEEL_MULTIPLIERS = (0.1, 0.5, 1.2, 1.5, 2.0, 3.0)
DEFAULT_CATCH_UP_THRESHOLD = 15.0
KING_OF_THE_HILL_WIN_BONUS = 2.0
WINNER_TAKES_ALL_WIN_POINTS = 5.0
WINNER_TAKES_ALL_LOSS_POINTS = 0.0


@dataclass(frozen=True, slots=True)
class SpecialDefinition:
    key: str
    title: str
    icon: str
    summary: str
    unlock_rule: str


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class SpecialService:
    def __init__(self, repo: SQLiteRepository, ranking_service: RankingService) -> None:
        self.repo = repo
        self.ranking_service = ranking_service

    @staticmethod
    def _participant_outcome(match_outcome: str, side_number: int) -> str:
        if match_outcome == "draw":
            return "draw"
        if match_outcome == "side1_win":
            return "win" if side_number == 1 else "loss"
        if match_outcome == "side2_win":
            return "win" if side_number == 2 else "loss"
        raise ValueError(f"Unknown match outcome: {match_outcome}")

    @staticmethod
    def _parse_match_time(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed

    @staticmethod
    def _now_local_naive() -> datetime:
        return datetime.now().astimezone().replace(tzinfo=None)

    @staticmethod
    def _activation_sort_key(activation: MatchSpecialActivation) -> tuple[str, int]:
        return (activation.activated_at, activation.id)

    @staticmethod
    def _override_setting_key(participant_user_id: int, special_key: str) -> str:
        return f"{SPECIAL_OVERRIDE_PREFIX}{participant_user_id}:{special_key}"

    @staticmethod
    def _record_is_in_activation_window(
        activation: MatchSpecialActivation,
        record: dict[str, object],
    ) -> bool:
        record_entered_at = str(record["entered_at"])
        record_match_id = int(record["match_id"])
        if record_entered_at > activation.activated_at:
            return True
        return record_entered_at == activation.activated_at and record_match_id >= activation.match_id

    @staticmethod
    def badge_for_special(special_key: str, payload_json: Optional[str] = None) -> str:
        if special_key == SPECIAL_DOUBLER:
            return "⚡x2"
        if special_key == SPECIAL_DOUBLE_OR_NOTHING:
            return "🎲2"
        if special_key == SPECIAL_KING_OF_THE_HILL:
            return "👑+2"
        if special_key == SPECIAL_WINNER_TAKES_ALL:
            return "👑5-0"
        if special_key == SPECIAL_CATCH_UP:
            return "🪂x2"
        if special_key == SPECIAL_WHEEL:
            multiplier = None
            if payload_json:
                try:
                    multiplier = float(json.loads(payload_json).get("multiplier"))
                except Exception:
                    multiplier = None
            if multiplier is not None:
                return f"🎡x{multiplier:g}"
            return "🎡"
        if special_key == SPECIAL_MATCH_FIXER:
            return "🛠️+"
        if special_key == SPECIAL_KING_FIXER:
            return "👑🛠️"
        if special_key == SPECIAL_DONT_UNDERESTIMATE:
            return "⚔️"
        return "✨"

    @staticmethod
    def special_label(special_key: str) -> str:
        return {
            SPECIAL_DOUBLER: "Doubler",
            SPECIAL_DOUBLE_OR_NOTHING: "Double-or-nothing",
            SPECIAL_KING_OF_THE_HILL: "King of the Hill",
            SPECIAL_WINNER_TAKES_ALL: "The winner takes it all",
            SPECIAL_CATCH_UP: "Catch-up mode",
            SPECIAL_WHEEL: "Wheel of Fortune",
            SPECIAL_MATCH_FIXER: "Match Fixer",
            SPECIAL_KING_FIXER: "King Fixer",
            SPECIAL_DONT_UNDERESTIMATE: "Don't underestimate my power",
        }.get(special_key, special_key.replace("_", " ").title())

    def get_special_override_mode(self, *, participant_user_id: int, special_key: str) -> str:
        raw_value = (
            self.repo.get_app_setting(self._override_setting_key(participant_user_id, special_key)) or ""
        ).strip().lower()
        if raw_value in {"on", "off"}:
            return raw_value
        return "auto"

    def list_special_override_modes(self) -> dict[tuple[int, str], str]:
        settings = self.repo.list_app_settings(prefix=SPECIAL_OVERRIDE_PREFIX)
        modes: dict[tuple[int, str], str] = {}
        for setting_key, setting_value in settings.items():
            suffix = setting_key.removeprefix(SPECIAL_OVERRIDE_PREFIX)
            participant_text, separator, special_key = suffix.partition(":")
            if not separator:
                continue
            try:
                participant_user_id = int(participant_text)
            except ValueError:
                continue
            mode = setting_value.strip().lower()
            if mode in {"on", "off"}:
                modes[(participant_user_id, special_key)] = mode
        return modes

    def set_special_override_mode(
        self,
        *,
        participant_user_id: int,
        special_key: str,
        mode: str,
        updated_by_user_id: int,
    ) -> None:
        clean_mode = (mode or "").strip().lower()
        if special_key not in SPECIAL_KEYS:
            raise ValidationError("Unknown special.")
        if clean_mode not in {"auto", "on", "off"}:
            raise ValidationError("Special override must be auto, on, or off.")

        participant = self.repo.get_user_with_profile(participant_user_id)
        if not participant or participant.role != "participant":
            raise ValidationError("Participant not found.")

        now_iso = utc_now_iso()
        setting_key = self._override_setting_key(participant_user_id, special_key)
        if clean_mode == "auto":
            self.repo.delete_app_setting(setting_key)
        else:
            self.repo.set_app_setting(key=setting_key, value=clean_mode, updated_at=now_iso)
            if special_key == SPECIAL_KING_OF_THE_HILL and clean_mode == "on":
                for (other_user_id, other_special_key), other_mode in self.list_special_override_modes().items():
                    if (
                        other_special_key == SPECIAL_KING_OF_THE_HILL
                        and other_user_id != participant_user_id
                        and other_mode == "on"
                    ):
                        self.repo.delete_app_setting(
                            self._override_setting_key(other_user_id, SPECIAL_KING_OF_THE_HILL)
                        )

        if clean_mode == "off":
            matches_by_id = {match.id: match for match in self.repo.list_matches()}
            for activation in self.repo.list_match_special_activations(
                participant_user_id=participant_user_id,
                special_key=special_key,
            ):
                match = matches_by_id.get(activation.match_id)
                if match and match.status != "completed":
                    self.repo.delete_match_special_activation(activation.id)

        self.sync_current_special_state(now_iso=now_iso)

        participant_name = (
            participant.display_name
            or participant.username
            or participant.email
            or f"User {participant.user_id}"
        )
        self.repo.log_activity(
            event_type="special_override_updated",
            message=(
                f"Admin set {self.special_label(special_key)} override for {participant_name} to {clean_mode}."
            ),
            related_user_id=participant_user_id,
            created_at=now_iso,
        )

    def list_special_definitions(self) -> list[SpecialDefinition]:
        return [
            SpecialDefinition(
                key=SPECIAL_DOUBLER,
                title="Doubler",
                icon=self.badge_for_special(SPECIAL_DOUBLER),
                summary="Counts your own match score twice on one selected upcoming match.",
                unlock_rule="Everyone starts with this special. It also reappears whenever you are last in the ranking.",
            ),
            SpecialDefinition(
                key=SPECIAL_DOUBLE_OR_NOTHING,
                title="Double-or-nothing",
                icon=self.badge_for_special(SPECIAL_DOUBLE_OR_NOTHING),
                summary="Links two of your matches together and doubles both scores if the second one is a win.",
                unlock_rule="Unlocked after your first win. You can only hold one copy and use it once.",
            ),
            SpecialDefinition(
                key=SPECIAL_KING_OF_THE_HILL,
                title="King of the Hill",
                icon=self.badge_for_special(SPECIAL_KING_OF_THE_HILL),
                summary="As long as you hold first place, you can tag one match so a win earns 2 extra performance points.",
                unlock_rule="Only the current leader can hold it, and it transfers when someone else takes over first place unless it is already active in a live match.",
            ),
            SpecialDefinition(
                key=SPECIAL_WINNER_TAKES_ALL,
                title="The winner takes it all",
                icon=self.badge_for_special(SPECIAL_WINNER_TAKES_ALL),
                summary="Turns a non-draw into a 5-0 scoring split: the winners get 5 points and the losers get 0.",
                unlock_rule="Unlocked the first time you reach first place. You can only hold one copy and use it once.",
            ),
            SpecialDefinition(
                key=SPECIAL_CATCH_UP,
                title="Catch-up mode",
                icon=self.badge_for_special(SPECIAL_CATCH_UP),
                summary="Automatically doubles performance and betting scores while you are far enough behind the leader.",
                unlock_rule="Turns on automatically when you are more than the admin-set threshold behind number 1.",
            ),
            SpecialDefinition(
                key=SPECIAL_WHEEL,
                title="Wheel of Fortune",
                icon=self.badge_for_special(SPECIAL_WHEEL),
                summary="Spins a random multiplier or penalty for one selected upcoming match.",
                unlock_rule="Unlocked after your second loss. You can only hold one copy and use it once.",
            ),
            SpecialDefinition(
                key=SPECIAL_MATCH_FIXER,
                title="Match Fixer",
                icon=self.badge_for_special(SPECIAL_MATCH_FIXER),
                summary=(
                    "On one of your own upcoming matches, gain 1 extra point for every bettor "
                    "who predicted the final outcome correctly."
                ),
                unlock_rule=(
                    "Unlocked once your positive betting winnings reach at least 1 point in total, "
                    "ignoring betting losses. You can only use it once."
                ),
            ),
            SpecialDefinition(
                key=SPECIAL_KING_FIXER,
                title="King Fixer",
                icon=self.badge_for_special(SPECIAL_KING_FIXER),
                summary=(
                    "On one of your own upcoming matches, gain 2 extra points for every bettor "
                    "who predicted the final outcome correctly."
                ),
                unlock_rule=(
                    "Unlocked once your positive betting winnings reach at least 10 points in total, "
                    "ignoring betting losses. You can only use it once."
                ),
            ),
            SpecialDefinition(
                key=SPECIAL_DONT_UNDERESTIMATE,
                title="Don't underestimate my power",
                icon=self.badge_for_special(SPECIAL_DONT_UNDERESTIMATE),
                summary=(
                    "On one of your own upcoming matches, gain back the total points lost by bettors "
                    "who predicted your side to lose and were wrong."
                ),
                unlock_rule=(
                    "Unlocked once your betting losses reach at least 5 points in total, "
                    "ignoring betting wins. You can only use it once."
                ),
            ),
        ]

    def get_catch_up_threshold(self) -> float:
        raw_value = (self.repo.get_app_setting("catch_up_points_gap_threshold") or "").strip()
        if not raw_value:
            return DEFAULT_CATCH_UP_THRESHOLD
        try:
            value = float(raw_value)
        except ValueError:
            return DEFAULT_CATCH_UP_THRESHOLD
        return max(0.0, value)

    def set_catch_up_threshold(self, *, admin_user_id: int, threshold_points: float) -> None:
        if threshold_points < 0:
            raise ValidationError("Catch-up threshold cannot be negative.")
        now_iso = utc_now_iso()
        self.repo.set_app_setting(
            key="catch_up_points_gap_threshold",
            value=f"{threshold_points:.1f}",
            updated_at=now_iso,
        )
        self.recalculate_match_competition_state()
        self.repo.log_activity(
            event_type="catch_up_threshold_updated",
            message=f"Catch-up threshold updated to {threshold_points:.1f} points.",
            related_user_id=admin_user_id,
            created_at=now_iso,
        )

    def match_allows_pre_match_actions(self, match: Match) -> bool:
        if match.status != "upcoming":
            return False
        scheduled_at = self._parse_match_time(match.scheduled_at)
        if scheduled_at is None:
            return True
        return self._now_local_naive() < scheduled_at

    def _current_totals(self) -> dict[int, float]:
        leaderboard_rows = self.ranking_service.compute_leaderboard()
        totals = {row.user_id: float(row.total_points) for row in leaderboard_rows}
        for participant in self.repo.list_participants():
            totals.setdefault(participant.user_id, 0.0)
        return totals

    def get_current_last_place_user_ids(self) -> set[int]:
        totals = self._current_totals()
        if not totals:
            return set()
        lowest_total = min(totals.values())
        return {user_id for user_id, total in totals.items() if abs(total - lowest_total) < 1e-9}

    def get_current_first_place_user_ids(self) -> set[int]:
        totals = self._current_totals()
        if not totals:
            return set()
        highest_total = max(totals.values())
        lowest_total = min(totals.values())
        if abs(highest_total - lowest_total) < 1e-9:
            return set()
        return {user_id for user_id, total in totals.items() if abs(total - highest_total) < 1e-9}

    def get_current_king_of_the_hill_holder_user_id(self) -> Optional[int]:
        leaderboard = self.ranking_service.compute_leaderboard()
        if not leaderboard:
            return None
        if len(leaderboard) > 1 and leaderboard[1].rank == leaderboard[0].rank:
            return None
        return leaderboard[0].user_id

    def get_current_catch_up_user_ids(self) -> set[int]:
        totals = self._current_totals()
        if not totals:
            return set()
        leader_total = max(totals.values())
        threshold = self.get_catch_up_threshold()
        return {
            user_id
            for user_id, total in totals.items()
            if (leader_total - total) > threshold
        }

    def build_match_special_icon_map(
        self,
        *,
        match_ids: list[int],
        include_current_catch_up: bool,
    ) -> dict[tuple[int, int], tuple[str, ...]]:
        icons: dict[tuple[int, int], list[str]] = {}
        for activation in self.repo.list_match_special_activations(match_ids=match_ids):
            badge = self.badge_for_special(activation.special_key, activation.payload_json)
            icons.setdefault((activation.match_id, activation.participant_user_id), []).append(badge)

        if include_current_catch_up:
            catch_up_users = self.get_current_catch_up_user_ids()
            for row in self.repo.list_match_participant_rows(match_ids):
                user_id = int(row["user_id"])
                match_id = int(row["match_id"])
                if user_id in catch_up_users:
                    icons.setdefault((match_id, user_id), []).append(self.badge_for_special(SPECIAL_CATCH_UP))

        return {key: tuple(values) for key, values in icons.items()}

    @staticmethod
    def _match_has_winner_takes_all_activation(
        *,
        match_activations: list[MatchSpecialActivation],
        outcome: str,
    ) -> bool:
        if outcome == "draw":
            return False
        return any(
            activation.special_key == SPECIAL_WINNER_TAKES_ALL
            for activation in match_activations
        )

    @staticmethod
    def _match_has_special_for_user(
        *,
        match_activations_for_user: list[MatchSpecialActivation],
        special_key: str,
    ) -> bool:
        return any(activation.special_key == special_key for activation in match_activations_for_user)

    @staticmethod
    def _base_points_for_match_outcome(
        *,
        player_outcome: str,
        king_of_the_hill_active: bool,
        winner_takes_all_active: bool,
    ) -> float:
        if winner_takes_all_active:
            if player_outcome == "win":
                points = WINNER_TAKES_ALL_WIN_POINTS
                if king_of_the_hill_active:
                    points += KING_OF_THE_HILL_WIN_BONUS
                return points
            if player_outcome == "loss":
                return WINNER_TAKES_ALL_LOSS_POINTS
        points = POINTS[player_outcome]
        if king_of_the_hill_active and player_outcome == "win":
            points += KING_OF_THE_HILL_WIN_BONUS
        return points

    def _bet_positive_and_negative_totals(self) -> tuple[dict[int, float], dict[int, float]]:
        positive_totals = {participant.user_id: 0.0 for participant in self.repo.list_participants()}
        negative_totals = {participant.user_id: 0.0 for participant in self.repo.list_participants()}

        for award in self.repo.list_competition_point_awards(source_type=BETTING_SOURCE_TYPE):
            user_id = int(award.participant_user_id)
            points = float(award.points_awarded)
            if points > 0:
                positive_totals[user_id] = positive_totals.get(user_id, 0.0) + points
            elif points < 0:
                negative_totals[user_id] = negative_totals.get(user_id, 0.0) + abs(points)

        return positive_totals, negative_totals

    @staticmethod
    def _special_bonus_match_and_key(source_key: str) -> Optional[tuple[int, str]]:
        if not source_key.startswith("match:"):
            return None
        parts = source_key.split(":")
        if len(parts) < 3:
            return None
        try:
            match_id = int(parts[1])
        except ValueError:
            return None
        special_key = ":".join(parts[2:])
        return match_id, special_key

    @staticmethod
    def _opposite_win_outcome_for_side(side_number: int) -> str:
        return "side2_win" if side_number == 1 else "side1_win"

    def _cleanup_king_of_the_hill_activations(
        self,
        *,
        matches_by_id: dict[int, Match],
        holder_user_id: Optional[int],
    ) -> None:
        for activation in self.repo.list_match_special_activations(special_key=SPECIAL_KING_OF_THE_HILL):
            match = matches_by_id.get(activation.match_id)
            if not match or match.status == "completed":
                continue
            if match.status == "live":
                continue
            if holder_user_id is not None and activation.participant_user_id == holder_user_id:
                continue
            self.repo.delete_match_special_activation(activation.id)

    def _get_king_of_the_hill_holder_user_id(
        self,
        *,
        matches_by_id: dict[int, Match],
        override_modes: dict[tuple[int, str], str],
    ) -> Optional[int]:
        live_holder_candidates: list[tuple[str, int, int]] = []
        for activation in self.repo.list_match_special_activations(special_key=SPECIAL_KING_OF_THE_HILL):
            match = matches_by_id.get(activation.match_id)
            if not match or match.status != "live":
                continue
            live_holder_candidates.append((activation.activated_at, activation.id, activation.participant_user_id))
        if live_holder_candidates:
            live_holder_candidates.sort()
            return int(live_holder_candidates[0][2])

        forced_holders = sorted(
            user_id
            for (user_id, special_key), mode in override_modes.items()
            if special_key == SPECIAL_KING_OF_THE_HILL and mode == "on"
        )
        if forced_holders:
            return int(forced_holders[0])

        return self.get_current_king_of_the_hill_holder_user_id()

    def get_completed_match_point_map(self) -> dict[tuple[int, int], float]:
        totals = {participant.user_id: 0.0 for participant in self.repo.list_participants()}
        for award in self.repo.list_competition_point_award_rows():
            if award["source_type"] in MATCH_RELATED_AWARD_SOURCE_TYPES:
                continue
            user_id = int(award["participant_user_id"])
            totals[user_id] = totals.get(user_id, 0.0) + float(award["points_awarded"])

        completed_match_rows = self.repo.list_completed_match_rows_for_scoring()
        completed_match_ids = [int(row["match_id"]) for row in completed_match_rows]
        participant_rows = self.repo.list_match_participant_rows(completed_match_ids)
        activations = self.repo.list_match_special_activations(match_ids=completed_match_ids)
        threshold = self.get_catch_up_threshold()
        special_bonus_points_by_match_and_user: dict[tuple[int, int], float] = {}
        for award in self.repo.list_competition_point_awards(source_type=MATCH_SPECIAL_BONUS_SOURCE_TYPE):
            parsed = self._special_bonus_match_and_key(award.source_key)
            if parsed is None:
                continue
            award_match_id, _special_key = parsed
            key = (award_match_id, int(award.participant_user_id))
            special_bonus_points_by_match_and_user[key] = round(
                special_bonus_points_by_match_and_user.get(key, 0.0) + float(award.points_awarded),
                4,
            )

        participants_by_match: dict[int, list[dict[str, object]]] = {}
        participant_side_by_match_and_user: dict[tuple[int, int], int] = {}
        for row in participant_rows:
            match_id = int(row["match_id"])
            user_id = int(row["user_id"])
            side_number = int(row["side_number"])
            participants_by_match.setdefault(match_id, []).append(row)
            participant_side_by_match_and_user[(match_id, user_id)] = side_number

        activations_by_match_and_user: dict[tuple[int, int], list[MatchSpecialActivation]] = {}
        activations_by_user: dict[int, list[MatchSpecialActivation]] = {}
        activations_by_match: dict[int, list[MatchSpecialActivation]] = {}
        for activation in activations:
            key = (activation.match_id, activation.participant_user_id)
            activations_by_match_and_user.setdefault(key, []).append(activation)
            activations_by_user.setdefault(activation.participant_user_id, []).append(activation)
            activations_by_match.setdefault(activation.match_id, []).append(activation)

        for activation_list in activations_by_match_and_user.values():
            activation_list.sort(key=self._activation_sort_key)
        for activation_list in activations_by_user.values():
            activation_list.sort(key=self._activation_sort_key)
        for activation_list in activations_by_match.values():
            activation_list.sort(key=self._activation_sort_key)

        point_map: dict[tuple[int, int], float] = {}
        completed_records_by_user: dict[int, list[dict[str, object]]] = {}
        resolved_don_activation_ids: set[int] = set()

        for match_row in completed_match_rows:
            match_id = int(match_row["match_id"])
            outcome = str(match_row["outcome"])
            winner_takes_all_active = self._match_has_winner_takes_all_activation(
                match_activations=activations_by_match.get(match_id, []),
                outcome=outcome,
            )

            leader_total = max(totals.values()) if totals else 0.0
            catch_up_users = {
                user_id
                for user_id, total in totals.items()
                if (leader_total - total) > threshold
            }

            for participant_row in participants_by_match.get(match_id, []):
                user_id = int(participant_row["user_id"])
                side_number = int(participant_row["side_number"])
                player_outcome = self._participant_outcome(outcome, side_number)
                king_of_the_hill_active = self._match_has_special_for_user(
                    match_activations_for_user=activations_by_match_and_user.get((match_id, user_id), []),
                    special_key=SPECIAL_KING_OF_THE_HILL,
                )
                performance_base_points = self._base_points_for_match_outcome(
                    player_outcome=player_outcome,
                    king_of_the_hill_active=king_of_the_hill_active,
                    winner_takes_all_active=winner_takes_all_active,
                )
                multiplier = 1.0

                for activation in activations_by_match_and_user.get((match_id, user_id), []):
                    if activation.special_key == SPECIAL_DOUBLER:
                        multiplier *= 2.0
                    elif activation.special_key == SPECIAL_WHEEL and activation.payload_json:
                        try:
                            multiplier *= float(json.loads(activation.payload_json).get("multiplier", 1.0))
                        except Exception:
                            multiplier *= 1.0

                if user_id in catch_up_users:
                    multiplier *= 2.0

                final_points = round(performance_base_points * multiplier, 4)
                point_map[(match_id, user_id)] = final_points
                totals[user_id] = totals.get(user_id, 0.0) + final_points
                completed_records_by_user.setdefault(user_id, []).append(
                    {
                        "match_id": match_id,
                        "entered_at": str(match_row["entered_at"]),
                        "player_outcome": player_outcome,
                        "points": final_points,
                    }
                )

            affected_user_ids = {
                int(row["user_id"])
                for row in participants_by_match.get(match_id, [])
            }
            for user_id in affected_user_ids:
                user_records = completed_records_by_user.get(user_id, [])
                for activation in activations_by_user.get(user_id, []):
                    if (
                        activation.special_key != SPECIAL_DOUBLE_OR_NOTHING
                        or activation.id in resolved_don_activation_ids
                    ):
                        continue
                    eligible_records = [
                        record for record in user_records
                        if self._record_is_in_activation_window(activation, record)
                    ]
                    if len(eligible_records) < 2:
                        continue
                    if eligible_records[1]["player_outcome"] == "win":
                        first_record = eligible_records[0]
                        second_record = eligible_records[1]
                        point_map[(int(first_record["match_id"]), user_id)] = round(
                            point_map.get((int(first_record["match_id"]), user_id), 0.0)
                            + float(first_record["points"]),
                            4,
                        )
                        point_map[(int(second_record["match_id"]), user_id)] = round(
                            point_map.get((int(second_record["match_id"]), user_id), 0.0)
                            + float(second_record["points"]),
                            4,
                        )
                        totals[user_id] = totals.get(user_id, 0.0) + float(first_record["points"]) + float(second_record["points"])
                    resolved_don_activation_ids.add(activation.id)

            for (bonus_match_id, user_id), bonus_points in special_bonus_points_by_match_and_user.items():
                if bonus_match_id != match_id or abs(bonus_points) <= 1e-9:
                    continue
                point_map[(match_id, user_id)] = round(
                    point_map.get((match_id, user_id), 0.0) + bonus_points,
                    4,
                )
                totals[user_id] = totals.get(user_id, 0.0) + bonus_points

        return point_map

    def sync_current_special_state(self, *, now_iso: Optional[str] = None) -> None:
        current_now_iso = now_iso or utc_now_iso()
        participants = self.repo.list_participants()
        override_modes = self.list_special_override_modes()
        participant_ids = [participant.user_id for participant in participants]
        wins_by_user = {user_id: 0 for user_id in participant_ids}
        losses_by_user = {user_id: 0 for user_id in participant_ids}

        for row in self.repo.list_completed_match_player_rows():
            user_id = int(row["participant_user_id"])
            outcome = self._participant_outcome(str(row["outcome"]), int(row["side_number"]))
            if outcome == "win":
                wins_by_user[user_id] = wins_by_user.get(user_id, 0) + 1
            elif outcome == "loss":
                losses_by_user[user_id] = losses_by_user.get(user_id, 0) + 1

        all_matches = {match.id: match for match in self.repo.list_matches()}
        king_of_the_hill_holder_user_id = self._get_king_of_the_hill_holder_user_id(
            matches_by_id=all_matches,
            override_modes=override_modes,
        )
        self._cleanup_king_of_the_hill_activations(
            matches_by_id=all_matches,
            holder_user_id=king_of_the_hill_holder_user_id,
        )
        activations = self.repo.list_match_special_activations()
        any_activation_keys: dict[int, set[str]] = {}
        pending_activation_keys: dict[int, set[str]] = {}

        for activation in activations:
            any_activation_keys.setdefault(activation.participant_user_id, set()).add(activation.special_key)
            match = all_matches.get(activation.match_id)
            if match and match.status != "completed":
                pending_activation_keys.setdefault(activation.participant_user_id, set()).add(activation.special_key)

        last_place_user_ids = self.get_current_last_place_user_ids()
        first_place_user_ids = self.get_current_first_place_user_ids()
        catch_up_user_ids = self.get_current_catch_up_user_ids()
        positive_betting_totals, negative_betting_totals = self._bet_positive_and_negative_totals()

        for participant in participants:
            user_id = participant.user_id
            existing_specials = {
                special.special_key: special
                for special in self.repo.list_participant_specials(participant_user_id=user_id)
            }
            activated_keys = any_activation_keys.get(user_id, set())
            pending_keys = pending_activation_keys.get(user_id, set())

            for special_key in SPECIAL_KEYS:
                existing = existing_specials.get(special_key)
                is_pending = special_key in pending_keys
                has_been_used = special_key in activated_keys

                if special_key == SPECIAL_DOUBLER:
                    is_available = is_pending or (not has_been_used) or (user_id in last_place_user_ids)
                    is_active = is_pending
                elif special_key == SPECIAL_DOUBLE_OR_NOTHING:
                    is_available = is_pending or ((not has_been_used) and wins_by_user.get(user_id, 0) >= 1)
                    is_active = is_pending
                elif special_key == SPECIAL_KING_OF_THE_HILL:
                    is_available = is_pending or (king_of_the_hill_holder_user_id == user_id)
                    is_active = is_pending
                elif special_key == SPECIAL_WINNER_TAKES_ALL:
                    has_unlocked_once = bool(existing and existing.granted_at)
                    is_available = is_pending or (
                        (not has_been_used) and (has_unlocked_once or user_id in first_place_user_ids)
                    )
                    is_active = is_pending
                elif special_key == SPECIAL_WHEEL:
                    is_available = is_pending or ((not has_been_used) and losses_by_user.get(user_id, 0) >= 2)
                    is_active = is_pending
                elif special_key == SPECIAL_MATCH_FIXER:
                    is_available = is_pending or (
                        (not has_been_used) and positive_betting_totals.get(user_id, 0.0) >= 1.0
                    )
                    is_active = is_pending
                elif special_key == SPECIAL_KING_FIXER:
                    is_available = is_pending or (
                        (not has_been_used) and positive_betting_totals.get(user_id, 0.0) >= 10.0
                    )
                    is_active = is_pending
                elif special_key == SPECIAL_DONT_UNDERESTIMATE:
                    is_available = is_pending or (
                        (not has_been_used) and negative_betting_totals.get(user_id, 0.0) >= 5.0
                    )
                    is_active = is_pending
                else:
                    is_available = user_id in catch_up_user_ids
                    is_active = is_available

                granted_at = existing.granted_at if existing and existing.granted_at else None
                if is_available and granted_at is None:
                    granted_at = current_now_iso

                activated_at = existing.activated_at if existing else None
                if is_active and activated_at is None:
                    activated_at = current_now_iso

                resolved_at = existing.resolved_at if existing else None
                if existing and existing.is_active and not is_active:
                    resolved_at = current_now_iso
                if is_active:
                    resolved_at = None

                payload_json = existing.payload_json if existing else None
                if special_key == SPECIAL_CATCH_UP and not is_active:
                    payload_json = None

                override_mode = override_modes.get((user_id, special_key), "auto")
                if override_mode == "on":
                    is_available = True
                    if special_key in {SPECIAL_CATCH_UP}:
                        is_active = True
                elif override_mode == "off":
                    is_available = False
                    is_active = False
                    payload_json = None

                self.repo.upsert_participant_special(
                    participant_user_id=user_id,
                    special_key=special_key,
                    is_available=is_available,
                    is_active=is_active,
                    granted_at=granted_at,
                    activated_at=activated_at,
                    resolved_at=resolved_at,
                    payload_json=payload_json,
                    updated_at=current_now_iso,
                )

    def get_participant_specials(self, participant_user_id: int) -> dict[str, ParticipantSpecial]:
        self.sync_current_special_state()
        return {
            special.special_key: special
            for special in self.repo.list_participant_specials(participant_user_id=participant_user_id)
        }

    def list_special_status_rows(self) -> list[dict[str, object]]:
        self.sync_current_special_state()
        participants = self.repo.list_participants()
        overrides = self.list_special_override_modes()
        matches_by_id = {match.id: match for match in self.repo.list_matches()}
        activation_lookup: dict[tuple[int, str], list[MatchSpecialActivation]] = {}
        for activation in self.repo.list_match_special_activations():
            activation_lookup.setdefault((activation.participant_user_id, activation.special_key), []).append(activation)

        rows: list[dict[str, object]] = []
        for participant in participants:
            special_map = self.get_participant_specials(participant.user_id)
            row: dict[str, object] = {
                "user_id": participant.user_id,
                "name": participant.display_name
                or participant.username
                or participant.email
                or f"User {participant.user_id}",
            }
            for special_key in SPECIAL_KEYS:
                override_mode = overrides.get((participant.user_id, special_key), "auto")
                status = "locked"
                special = special_map.get(special_key)
                pending_activation = None
                for activation in activation_lookup.get((participant.user_id, special_key), []):
                    match = matches_by_id.get(activation.match_id)
                    if match and match.status != "completed":
                        pending_activation = activation
                        break

                if pending_activation is not None:
                    status = f"active on #{pending_activation.match_id}"
                elif special and special.is_active:
                    status = "active"
                elif special and special.is_available:
                    status = "available"
                elif special and special.activated_at and special_key not in {SPECIAL_CATCH_UP, SPECIAL_KING_OF_THE_HILL}:
                    status = "used"

                if override_mode == "on":
                    status += " (forced on)"
                elif override_mode == "off":
                    status += " (forced off)"

                row[special_key] = status
                row[f"{special_key}_override"] = override_mode
            rows.append(row)

        rows.sort(key=lambda item: str(item["name"]).lower())
        return rows

    def _compute_special_bonus_totals_and_usage_counts(
        self,
    ) -> tuple[dict[tuple[int, str], float], dict[tuple[int, str], int]]:
        bonus_totals: dict[tuple[int, str], float] = {}
        usage_counts: dict[tuple[int, str], int] = {}

        all_activations = self.repo.list_match_special_activations()
        for activation in all_activations:
            key = (activation.participant_user_id, activation.special_key)
            usage_counts[key] = usage_counts.get(key, 0) + 1

        for award in self.repo.list_competition_point_awards(source_type=MATCH_SPECIAL_BONUS_SOURCE_TYPE):
            parsed = self._special_bonus_match_and_key(award.source_key)
            if parsed is None:
                continue
            _match_id, special_key = parsed
            key = (int(award.participant_user_id), special_key)
            bonus_totals[key] = round(
                bonus_totals.get(key, 0.0) + float(award.points_awarded),
                4,
            )

        totals = {participant.user_id: 0.0 for participant in self.repo.list_participants()}
        for award in self.repo.list_competition_point_award_rows():
            if award["source_type"] in MATCH_RELATED_AWARD_SOURCE_TYPES:
                continue
            user_id = int(award["participant_user_id"])
            totals[user_id] = totals.get(user_id, 0.0) + float(award["points_awarded"])

        completed_match_rows = self.repo.list_completed_match_rows_for_scoring()
        completed_match_ids = [int(row["match_id"]) for row in completed_match_rows]
        participant_rows = self.repo.list_match_participant_rows(completed_match_ids)
        activations = self.repo.list_match_special_activations(match_ids=completed_match_ids)
        bets = self.repo.list_match_bets(match_ids=completed_match_ids, include_settled=True)
        threshold = self.get_catch_up_threshold()
        special_bonus_points_by_match_and_user: dict[tuple[int, int], float] = {}
        for award in self.repo.list_competition_point_awards(source_type=MATCH_SPECIAL_BONUS_SOURCE_TYPE):
            parsed = self._special_bonus_match_and_key(award.source_key)
            if parsed is None:
                continue
            match_id, _special_key = parsed
            key = (match_id, int(award.participant_user_id))
            special_bonus_points_by_match_and_user[key] = round(
                special_bonus_points_by_match_and_user.get(key, 0.0) + float(award.points_awarded),
                4,
            )

        participants_by_match: dict[int, list[dict[str, object]]] = {}
        participant_side_by_match_and_user: dict[tuple[int, int], int] = {}
        for row in participant_rows:
            match_id = int(row["match_id"])
            user_id = int(row["user_id"])
            side_number = int(row["side_number"])
            participants_by_match.setdefault(match_id, []).append(row)
            participant_side_by_match_and_user[(match_id, user_id)] = side_number

        activations_by_match_and_user: dict[tuple[int, int], list[MatchSpecialActivation]] = {}
        activations_by_user: dict[int, list[MatchSpecialActivation]] = {}
        activations_by_match: dict[int, list[MatchSpecialActivation]] = {}
        for activation in activations:
            key = (activation.match_id, activation.participant_user_id)
            activations_by_match_and_user.setdefault(key, []).append(activation)
            activations_by_user.setdefault(activation.participant_user_id, []).append(activation)
            activations_by_match.setdefault(activation.match_id, []).append(activation)

        for activation_list in activations_by_match_and_user.values():
            activation_list.sort(key=self._activation_sort_key)
        for activation_list in activations_by_user.values():
            activation_list.sort(key=self._activation_sort_key)
        for activation_list in activations_by_match.values():
            activation_list.sort(key=self._activation_sort_key)

        bets_by_match: dict[int, list] = {}
        for bet in bets:
            bets_by_match.setdefault(bet.match_id, []).append(bet)

        completed_records_by_user: dict[int, list[dict[str, object]]] = {}
        resolved_don_activation_ids: set[int] = set()

        for match_row in completed_match_rows:
            match_id = int(match_row["match_id"])
            outcome = str(match_row["outcome"])
            entered_at = str(match_row["entered_at"])
            winner_takes_all_active = self._match_has_winner_takes_all_activation(
                match_activations=activations_by_match.get(match_id, []),
                outcome=outcome,
            )

            leader_total = max(totals.values()) if totals else 0.0
            catch_up_users = {
                user_id
                for user_id, total in totals.items()
                if (leader_total - total) > threshold
            }
            catch_up_usage_for_match: set[int] = set()

            for participant_row in participants_by_match.get(match_id, []):
                user_id = int(participant_row["user_id"])
                side_number = int(participant_row["side_number"])
                player_outcome = self._participant_outcome(outcome, side_number)
                standard_base_points = POINTS[player_outcome]
                match_user_activations = activations_by_match_and_user.get((match_id, user_id), [])
                king_of_the_hill_active = self._match_has_special_for_user(
                    match_activations_for_user=match_user_activations,
                    special_key=SPECIAL_KING_OF_THE_HILL,
                )
                performance_base_points = self._base_points_for_match_outcome(
                    player_outcome=player_outcome,
                    king_of_the_hill_active=king_of_the_hill_active,
                    winner_takes_all_active=winner_takes_all_active,
                )

                doubler_active = False
                wheel_multiplier = 1.0
                for activation in match_user_activations:
                    if activation.special_key == SPECIAL_DOUBLER:
                        doubler_active = True
                    elif activation.special_key == SPECIAL_WHEEL and activation.payload_json:
                        try:
                            wheel_multiplier *= float(json.loads(activation.payload_json).get("multiplier", 1.0))
                        except Exception:
                            wheel_multiplier *= 1.0

                doubler_factor = 2.0 if doubler_active else 1.0
                catch_up_factor = 2.0 if user_id in catch_up_users else 1.0
                final_points = round(
                    performance_base_points * doubler_factor * wheel_multiplier * catch_up_factor,
                    4,
                )

                if king_of_the_hill_active:
                    no_koth_base = self._base_points_for_match_outcome(
                        player_outcome=player_outcome,
                        king_of_the_hill_active=False,
                        winner_takes_all_active=winner_takes_all_active,
                    )
                    bonus = round(
                        final_points - (no_koth_base * doubler_factor * wheel_multiplier * catch_up_factor),
                        4,
                    )
                    bonus_totals[(user_id, SPECIAL_KING_OF_THE_HILL)] = round(
                        bonus_totals.get((user_id, SPECIAL_KING_OF_THE_HILL), 0.0) + bonus,
                        4,
                    )

                if winner_takes_all_active:
                    no_wta_base = self._base_points_for_match_outcome(
                        player_outcome=player_outcome,
                        king_of_the_hill_active=king_of_the_hill_active,
                        winner_takes_all_active=False,
                    )
                    bonus = round(
                        final_points - (no_wta_base * doubler_factor * wheel_multiplier * catch_up_factor),
                        4,
                    )
                    bonus_totals[(user_id, SPECIAL_WINNER_TAKES_ALL)] = round(
                        bonus_totals.get((user_id, SPECIAL_WINNER_TAKES_ALL), 0.0) + bonus,
                        4,
                    )

                if doubler_active:
                    bonus = round(
                        final_points - (performance_base_points * wheel_multiplier * catch_up_factor),
                        4,
                    )
                    bonus_totals[(user_id, SPECIAL_DOUBLER)] = round(
                        bonus_totals.get((user_id, SPECIAL_DOUBLER), 0.0) + bonus,
                        4,
                    )

                if abs(wheel_multiplier - 1.0) > 1e-9:
                    bonus = round(
                        final_points - (performance_base_points * doubler_factor * catch_up_factor),
                        4,
                    )
                    bonus_totals[(user_id, SPECIAL_WHEEL)] = round(
                        bonus_totals.get((user_id, SPECIAL_WHEEL), 0.0) + bonus,
                        4,
                    )

                if user_id in catch_up_users:
                    catch_up_usage_for_match.add(user_id)
                    bonus = round(
                        final_points - (performance_base_points * doubler_factor * wheel_multiplier),
                        4,
                    )
                    bonus_totals[(user_id, SPECIAL_CATCH_UP)] = round(
                        bonus_totals.get((user_id, SPECIAL_CATCH_UP), 0.0) + bonus,
                        4,
                    )

                totals[user_id] = totals.get(user_id, 0.0) + final_points
                completed_records_by_user.setdefault(user_id, []).append(
                    {
                        "match_id": match_id,
                        "entered_at": entered_at,
                        "player_outcome": player_outcome,
                        "final_points": final_points,
                    }
                )

            for bet in bets_by_match.get(match_id, []):
                base_net_points = float(bet.stake_points if bet.predicted_outcome == outcome else -bet.stake_points)
                if bet.participant_user_id in catch_up_users:
                    catch_up_usage_for_match.add(bet.participant_user_id)
                    bonus_totals[(bet.participant_user_id, SPECIAL_CATCH_UP)] = round(
                        bonus_totals.get((bet.participant_user_id, SPECIAL_CATCH_UP), 0.0) + base_net_points,
                        4,
                    )

            for user_id in catch_up_usage_for_match:
                usage_counts[(user_id, SPECIAL_CATCH_UP)] = usage_counts.get((user_id, SPECIAL_CATCH_UP), 0) + 1

            affected_user_ids = {
                int(row["user_id"])
                for row in participants_by_match.get(match_id, [])
            }
            for user_id in affected_user_ids:
                user_records = completed_records_by_user.get(user_id, [])
                for activation in activations_by_user.get(user_id, []):
                    if (
                        activation.special_key != SPECIAL_DOUBLE_OR_NOTHING
                        or activation.id in resolved_don_activation_ids
                    ):
                        continue
                    eligible_records = [
                        record for record in user_records
                        if self._record_is_in_activation_window(activation, record)
                    ]
                    if len(eligible_records) < 2:
                        continue
                    if eligible_records[1]["player_outcome"] == "win":
                        bonus_points = round(
                            float(eligible_records[0]["final_points"]) + float(eligible_records[1]["final_points"]),
                            4,
                        )
                        bonus_totals[(user_id, SPECIAL_DOUBLE_OR_NOTHING)] = round(
                            bonus_totals.get((user_id, SPECIAL_DOUBLE_OR_NOTHING), 0.0) + bonus_points,
                            4,
                        )
                        totals[user_id] = totals.get(user_id, 0.0) + bonus_points
                    resolved_don_activation_ids.add(activation.id)

            for (bonus_match_id, user_id), bonus_points in special_bonus_points_by_match_and_user.items():
                if bonus_match_id != match_id or abs(bonus_points) <= 1e-9:
                    continue
                totals[user_id] = totals.get(user_id, 0.0) + bonus_points

        return bonus_totals, usage_counts

    def build_special_player_stats(self) -> dict[str, list[dict[str, object]]]:
        def _status_priority(status: str) -> int:
            if status.startswith("active"):
                return 0
            if status.startswith("available"):
                return 1
            if status.startswith("used"):
                return 2
            return 3

        special_rows = self.list_special_status_rows()
        by_user_id = {
            int(row["user_id"]): row
            for row in special_rows
        }
        bonus_totals, usage_counts = self._compute_special_bonus_totals_and_usage_counts()

        grouped: dict[str, list[dict[str, object]]] = {special_key: [] for special_key in SPECIAL_KEYS}
        for row in special_rows:
            user_id = int(row["user_id"])
            for special_key in SPECIAL_KEYS:
                status = str(row[special_key])
                active_now = status.startswith("active")
                grouped[special_key].append(
                    {
                        "user_id": user_id,
                        "name": str(row["name"]),
                        "status": status,
                        "active_now": active_now,
                        "times_used": usage_counts.get((user_id, special_key), 0),
                        "bonus_points": round(float(bonus_totals.get((user_id, special_key), 0.0)), 1),
                        "override": str(by_user_id[user_id].get(f"{special_key}_override", "auto")),
                    }
                )

        for rows in grouped.values():
            rows.sort(
                key=lambda item: (
                    _status_priority(str(item["status"])),
                    -float(item["bonus_points"]),
                    -int(item["times_used"]),
                    str(item["name"]).lower(),
                )
            )
        return grouped

    def activate_match_special(
        self,
        *,
        participant_user_id: int,
        special_key: str,
        match_id: int,
        actor_user_id: int,
        admin_override: bool = False,
    ) -> None:
        if special_key not in MANUAL_MATCH_SPECIAL_KEYS:
            raise ValidationError("That special cannot be activated on a match.")

        match = self.repo.get_match(match_id)
        if not match:
            raise NotFoundError("Match not found.")
        if self.repo.get_match_result(match_id) is not None:
            raise ValidationError("Specials cannot be activated after the result is known.")
        if not admin_override and not self.match_allows_pre_match_actions(match):
            raise ValidationError("This match is already locked for pre-match actions.")
        if not self.repo.is_participant_in_match(participant_user_id=participant_user_id, match_id=match_id):
            raise ValidationError("Participant is not part of that match.")

        self.sync_current_special_state()
        special = self.repo.get_participant_special(
            participant_user_id=participant_user_id,
            special_key=special_key,
        )
        if not admin_override and (not special or not special.is_available):
            raise ValidationError(f"{self.special_label(special_key)} is not available right now.")
        if special is None:
            special = self.repo.upsert_participant_special(
                participant_user_id=participant_user_id,
                special_key=special_key,
                is_available=bool(admin_override),
                is_active=False,
                granted_at=utc_now_iso(),
                activated_at=None,
                resolved_at=None,
                payload_json=None,
                updated_at=utc_now_iso(),
            )

        existing_pending_activation = next(
            (
                activation
                for activation in self.repo.list_match_special_activations(
                    participant_user_id=participant_user_id,
                    special_key=special_key,
                )
                if (self.repo.get_match(activation.match_id) or match).status != "completed"
            ),
            None,
        )
        if existing_pending_activation is not None:
            if existing_pending_activation.match_id == match_id:
                raise ValidationError(f"{self.special_label(special_key)} is already active on this match.")
            raise ValidationError(
                f"{self.special_label(special_key)} is already active on match #{existing_pending_activation.match_id}."
            )

        now_iso = utc_now_iso()
        payload_json = None
        if special_key == SPECIAL_WHEEL:
            multiplier = random.choice(WHEEL_MULTIPLIERS)
            payload_json = json.dumps({"multiplier": multiplier}, separators=(",", ":"), sort_keys=True)

        self.repo.create_match_special_activation(
            participant_user_id=participant_user_id,
            special_key=special_key,
            match_id=match_id,
            activated_at=now_iso,
            activated_by_user_id=actor_user_id,
            payload_json=payload_json,
        )
        self.repo.upsert_participant_special(
            participant_user_id=participant_user_id,
            special_key=special_key,
            is_available=False,
            is_active=True,
            granted_at=special.granted_at or now_iso,
            activated_at=now_iso,
            resolved_at=None,
            payload_json=payload_json,
            updated_at=now_iso,
        )

        profile = self.repo.get_user_with_profile(participant_user_id)
        participant_name = (
            profile.display_name if profile and profile.display_name else f"Player {participant_user_id}"
        )
        match_label = f"{match.game_type} (#{match.id})"
        message = f"{participant_name} activated {self.special_label(special_key)} for {match_label}."
        if special_key == SPECIAL_WHEEL and payload_json:
            try:
                multiplier = float(json.loads(payload_json)["multiplier"])
                message = (
                    f"{participant_name} spun Wheel of Fortune for {match_label} and landed on x{multiplier:g}."
                )
            except Exception:
                pass
        self.repo.log_activity(
            event_type="special_activated",
            message=message,
            related_match_id=match_id,
            related_user_id=participant_user_id,
            created_at=now_iso,
        )

    def recalculate_match_competition_state(self) -> None:
        now_iso = utc_now_iso()
        self.repo.delete_competition_point_awards_by_source_types(list(MATCH_RELATED_AWARD_SOURCE_TYPES))

        participants = self.repo.list_participants()
        totals = {participant.user_id: 0.0 for participant in participants}
        for award in self.repo.list_competition_point_award_rows():
            if award["source_type"] in MATCH_RELATED_AWARD_SOURCE_TYPES:
                continue
            user_id = int(award["participant_user_id"])
            totals[user_id] = totals.get(user_id, 0.0) + float(award["points_awarded"])

        completed_match_rows = self.repo.list_completed_match_rows_for_scoring()
        completed_match_ids = [int(row["match_id"]) for row in completed_match_rows]
        participant_rows = self.repo.list_match_participant_rows(completed_match_ids)
        activations = self.repo.list_match_special_activations(match_ids=completed_match_ids)
        bets = self.repo.list_match_bets(include_settled=True)
        threshold = self.get_catch_up_threshold()

        participants_by_match: dict[int, list[dict[str, object]]] = {}
        participant_side_by_match_and_user: dict[tuple[int, int], int] = {}
        for row in participant_rows:
            match_id = int(row["match_id"])
            user_id = int(row["user_id"])
            side_number = int(row["side_number"])
            participants_by_match.setdefault(match_id, []).append(row)
            participant_side_by_match_and_user[(match_id, user_id)] = side_number

        activations_by_match_and_user: dict[tuple[int, int], list[MatchSpecialActivation]] = {}
        activations_by_user: dict[int, list[MatchSpecialActivation]] = {}
        activations_by_match: dict[int, list[MatchSpecialActivation]] = {}
        for activation in activations:
            key = (activation.match_id, activation.participant_user_id)
            activations_by_match_and_user.setdefault(key, []).append(activation)
            activations_by_user.setdefault(activation.participant_user_id, []).append(activation)
            activations_by_match.setdefault(activation.match_id, []).append(activation)

        for activation_list in activations_by_match_and_user.values():
            activation_list.sort(key=self._activation_sort_key)
        for activation_list in activations_by_user.values():
            activation_list.sort(key=self._activation_sort_key)
        for activation_list in activations_by_match.values():
            activation_list.sort(key=self._activation_sort_key)

        bets_by_match: dict[int, list] = {}
        for bet in bets:
            bets_by_match.setdefault(bet.match_id, []).append(bet)

        for bet in bets:
            if bet.match_id not in completed_match_ids:
                self.repo.settle_match_bet(bet_id=bet.id, settled_at=None, net_points=None)

        completed_records_by_user: dict[int, list[dict[str, object]]] = {}
        resolved_don_activation_ids: set[int] = set()

        for match_row in completed_match_rows:
            match_id = int(match_row["match_id"])
            outcome = str(match_row["outcome"])
            entered_at = str(match_row["entered_at"])
            winner_takes_all_active = self._match_has_winner_takes_all_activation(
                match_activations=activations_by_match.get(match_id, []),
                outcome=outcome,
            )

            leader_total = max(totals.values()) if totals else 0.0
            catch_up_users = {
                user_id
                for user_id, total in totals.items()
                if (leader_total - total) > threshold
            }

            for participant_row in participants_by_match.get(match_id, []):
                user_id = int(participant_row["user_id"])
                side_number = int(participant_row["side_number"])
                player_outcome = self._participant_outcome(outcome, side_number)
                standard_base_points = POINTS[player_outcome]
                king_of_the_hill_active = self._match_has_special_for_user(
                    match_activations_for_user=activations_by_match_and_user.get((match_id, user_id), []),
                    special_key=SPECIAL_KING_OF_THE_HILL,
                )
                performance_base_points = self._base_points_for_match_outcome(
                    player_outcome=player_outcome,
                    king_of_the_hill_active=king_of_the_hill_active,
                    winner_takes_all_active=winner_takes_all_active,
                )
                multiplier = 1.0

                for activation in activations_by_match_and_user.get((match_id, user_id), []):
                    if activation.special_key == SPECIAL_DOUBLER:
                        multiplier *= 2.0
                    elif activation.special_key == SPECIAL_WHEEL and activation.payload_json:
                        try:
                            multiplier *= float(json.loads(activation.payload_json).get("multiplier", 1.0))
                        except Exception:
                            multiplier *= 1.0

                if user_id in catch_up_users:
                    multiplier *= 2.0

                final_points = round(performance_base_points * multiplier, 4)
                adjustment = round(final_points - standard_base_points, 4)
                if abs(adjustment) > 1e-9:
                    self.repo.upsert_competition_point_award(
                        participant_user_id=user_id,
                        source_type=MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE,
                        source_key=f"match:{match_id}",
                        source_label=f"Match performance adjustment #{match_id}",
                        placement=None,
                        points_awarded=adjustment,
                        awarded_at=entered_at,
                        awarded_by_user_id=None,
                    )

                totals[user_id] = totals.get(user_id, 0.0) + final_points
                completed_records_by_user.setdefault(user_id, []).append(
                    {
                        "match_id": match_id,
                        "entered_at": entered_at,
                        "player_outcome": player_outcome,
                        "final_points": final_points,
                    }
                )

            settled_bets_for_match: list[tuple[object, float]] = []
            for bet in bets_by_match.get(match_id, []):
                net_points = bet.stake_points if bet.predicted_outcome == outcome else -bet.stake_points
                if bet.participant_user_id in catch_up_users:
                    net_points *= 2.0
                net_points = round(net_points, 4)
                self.repo.upsert_competition_point_award(
                    participant_user_id=bet.participant_user_id,
                    source_type=BETTING_SOURCE_TYPE,
                    source_key=f"match:{match_id}",
                    source_label=f"Betting #{match_id}",
                    placement=None,
                    points_awarded=net_points,
                    awarded_at=entered_at,
                    awarded_by_user_id=None,
                )
                self.repo.settle_match_bet(
                    bet_id=bet.id,
                    settled_at=entered_at,
                    net_points=net_points,
                )
                settled_bets_for_match.append((bet, net_points))
                totals[bet.participant_user_id] = totals.get(bet.participant_user_id, 0.0) + net_points

            correct_bettor_count = sum(
                1
                for bet, _net_points in settled_bets_for_match
                if bet.predicted_outcome == outcome
            )

            for participant_row in participants_by_match.get(match_id, []):
                user_id = int(participant_row["user_id"])
                side_number = participant_side_by_match_and_user.get((match_id, user_id))
                if side_number is None:
                    continue
                for activation in activations_by_match_and_user.get((match_id, user_id), []):
                    bonus_points = 0.0
                    if activation.special_key == SPECIAL_MATCH_FIXER:
                        bonus_points = float(correct_bettor_count)
                    elif activation.special_key == SPECIAL_KING_FIXER:
                        bonus_points = float(correct_bettor_count * 2)
                    elif activation.special_key == SPECIAL_DONT_UNDERESTIMATE:
                        opposite_prediction = self._opposite_win_outcome_for_side(side_number)
                        bonus_points = round(
                            sum(
                                abs(net_points)
                                for bet, net_points in settled_bets_for_match
                                if bet.predicted_outcome == opposite_prediction and net_points < 0
                            ),
                            4,
                        )

                    if abs(bonus_points) <= 1e-9:
                        continue

                    self.repo.upsert_competition_point_award(
                        participant_user_id=user_id,
                        source_type=MATCH_SPECIAL_BONUS_SOURCE_TYPE,
                        source_key=f"match:{match_id}:{activation.special_key}",
                        source_label=f"{self.special_label(activation.special_key)} bonus",
                        placement=None,
                        points_awarded=bonus_points,
                        awarded_at=entered_at,
                        awarded_by_user_id=None,
                    )
                    totals[user_id] = totals.get(user_id, 0.0) + bonus_points

            affected_user_ids = {
                int(row["user_id"])
                for row in participants_by_match.get(match_id, [])
            }
            for user_id in affected_user_ids:
                user_records = completed_records_by_user.get(user_id, [])
                for activation in activations_by_user.get(user_id, []):
                    if (
                        activation.special_key != SPECIAL_DOUBLE_OR_NOTHING
                        or activation.id in resolved_don_activation_ids
                    ):
                        continue
                    eligible_records = [
                        record for record in user_records
                        if self._record_is_in_activation_window(activation, record)
                    ]
                    if len(eligible_records) < 2:
                        continue
                    if eligible_records[1]["player_outcome"] == "win":
                        bonus_points = round(
                            float(eligible_records[0]["final_points"]) + float(eligible_records[1]["final_points"]),
                            4,
                        )
                        self.repo.upsert_competition_point_award(
                            participant_user_id=user_id,
                            source_type=DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE,
                            source_key=f"activation:{activation.id}",
                            source_label="Double-or-nothing bonus",
                            placement=None,
                            points_awarded=bonus_points,
                            awarded_at=str(eligible_records[1]["entered_at"]),
                            awarded_by_user_id=None,
                        )
                        totals[user_id] = totals.get(user_id, 0.0) + bonus_points
                    resolved_don_activation_ids.add(activation.id)

        self.sync_current_special_state(now_iso=now_iso)
