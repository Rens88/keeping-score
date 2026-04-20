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
    MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE,
    SQLiteRepository,
)
from tournament_tracker.services.errors import NotFoundError, ValidationError
from tournament_tracker.services.ranking_service import POINTS, RankingService


SPECIAL_DOUBLER = "doubler"
SPECIAL_DOUBLE_OR_NOTHING = "double_or_nothing"
SPECIAL_CATCH_UP = "catch_up_mode"
SPECIAL_WHEEL = "wheel_of_fortune"

SPECIAL_KEYS = (
    SPECIAL_DOUBLER,
    SPECIAL_DOUBLE_OR_NOTHING,
    SPECIAL_CATCH_UP,
    SPECIAL_WHEEL,
)
MANUAL_MATCH_SPECIAL_KEYS = (
    SPECIAL_DOUBLER,
    SPECIAL_DOUBLE_OR_NOTHING,
    SPECIAL_WHEEL,
)
MATCH_RELATED_AWARD_SOURCE_TYPES = (
    MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE,
    BETTING_SOURCE_TYPE,
    DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE,
)
SPECIAL_OVERRIDE_PREFIX = "special_override:"
WHEEL_MULTIPLIERS = (0.1, 0.5, 1.2, 1.5, 2.0, 3.0)
DEFAULT_CATCH_UP_THRESHOLD = 15.0


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
        return "✨"

    @staticmethod
    def special_label(special_key: str) -> str:
        return {
            SPECIAL_DOUBLER: "Doubler",
            SPECIAL_DOUBLE_OR_NOTHING: "Double-or-nothing",
            SPECIAL_CATCH_UP: "Catch-up mode",
            SPECIAL_WHEEL: "Wheel of Fortune",
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

        participants_by_match: dict[int, list[dict[str, object]]] = {}
        for row in participant_rows:
            participants_by_match.setdefault(int(row["match_id"]), []).append(row)

        activations_by_match_and_user: dict[tuple[int, int], list[MatchSpecialActivation]] = {}
        activations_by_user: dict[int, list[MatchSpecialActivation]] = {}
        for activation in activations:
            key = (activation.match_id, activation.participant_user_id)
            activations_by_match_and_user.setdefault(key, []).append(activation)
            activations_by_user.setdefault(activation.participant_user_id, []).append(activation)

        for activation_list in activations_by_match_and_user.values():
            activation_list.sort(key=self._activation_sort_key)
        for activation_list in activations_by_user.values():
            activation_list.sort(key=self._activation_sort_key)

        point_map: dict[tuple[int, int], float] = {}
        completed_records_by_user: dict[int, list[dict[str, object]]] = {}
        resolved_don_activation_ids: set[int] = set()

        for match_row in completed_match_rows:
            match_id = int(match_row["match_id"])
            outcome = str(match_row["outcome"])

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
                base_points = POINTS[player_outcome]
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

                final_points = round(base_points * multiplier, 4)
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
        activations = self.repo.list_match_special_activations()
        any_activation_keys: dict[int, set[str]] = {}
        pending_activation_keys: dict[int, set[str]] = {}

        for activation in activations:
            any_activation_keys.setdefault(activation.participant_user_id, set()).add(activation.special_key)
            match = all_matches.get(activation.match_id)
            if match and match.status != "completed":
                pending_activation_keys.setdefault(activation.participant_user_id, set()).add(activation.special_key)

        last_place_user_ids = self.get_current_last_place_user_ids()
        catch_up_user_ids = self.get_current_catch_up_user_ids()

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
                elif special_key == SPECIAL_WHEEL:
                    is_available = is_pending or ((not has_been_used) and losses_by_user.get(user_id, 0) >= 2)
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
                    if special_key == SPECIAL_CATCH_UP:
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
                elif special and special.activated_at and special_key != SPECIAL_CATCH_UP:
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
        for row in participant_rows:
            participants_by_match.setdefault(int(row["match_id"]), []).append(row)

        activations_by_match_and_user: dict[tuple[int, int], list[MatchSpecialActivation]] = {}
        activations_by_user: dict[int, list[MatchSpecialActivation]] = {}
        for activation in activations:
            key = (activation.match_id, activation.participant_user_id)
            activations_by_match_and_user.setdefault(key, []).append(activation)
            activations_by_user.setdefault(activation.participant_user_id, []).append(activation)

        for activation_list in activations_by_match_and_user.values():
            activation_list.sort(key=self._activation_sort_key)
        for activation_list in activations_by_user.values():
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
                base_points = POINTS[player_outcome]
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

                final_points = round(base_points * multiplier, 4)
                adjustment = round(final_points - base_points, 4)
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
                totals[bet.participant_user_id] = totals.get(bet.participant_user_id, 0.0) + net_points

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
