from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from tournament_tracker.models import Match, utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.errors import NotFoundError, ValidationError

if TYPE_CHECKING:
    from tournament_tracker.services.special_service import SpecialService


DEFAULT_GAME_TYPES = ["Football", "Petanque", "Padel", "Lasergame", "Darts"]


@dataclass(slots=True)
class MatchCardParticipant:
    user_id: int
    display_name: str
    motto: Optional[str]
    photo_blob: Optional[bytes]
    photo_mime_type: Optional[str]
    side_number: int
    side_name: Optional[str]
    has_doubler_on_match: bool
    special_icons: tuple[str, ...] = ()


@dataclass(slots=True)
class MatchCard:
    match_id: int
    game_type: str
    scheduled_at: Optional[str]
    scheduled_order: Optional[int]
    status: str
    outcome: Optional[str]
    result_notes: Optional[str]
    sides: dict[int, dict[str, object]]


class MatchService:
    def __init__(self, repo: SQLiteRepository, special_service: Optional["SpecialService"] = None) -> None:
        self.repo = repo
        self.special_service = special_service

    def _validate_participant_ids(self, side1_ids: list[int], side2_ids: list[int]) -> None:
        if not side1_ids or not side2_ids:
            raise ValidationError("Each side must have at least one participant.")

        overlap = set(side1_ids) & set(side2_ids)
        if overlap:
            raise ValidationError("A participant cannot be on both sides.")

        unique_ids = set(side1_ids + side2_ids)
        count = self.repo.count_participant_users(unique_ids)
        if count != len(unique_ids):
            raise ValidationError("One or more selected users are not valid participants.")

    @staticmethod
    def normalize_scheduled_at(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.isoformat(timespec="minutes")
        return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes")

    def create_match(
        self,
        *,
        game_type: str,
        scheduled_at: Optional[datetime],
        scheduled_order: Optional[int],
        status: str,
        created_by_user_id: int,
        side1_name: Optional[str],
        side2_name: Optional[str],
        side1_participant_ids: list[int],
        side2_participant_ids: list[int],
    ) -> Match:
        clean_game_type = (game_type or "").strip()
        if not clean_game_type:
            raise ValidationError("Game type is required.")

        if status not in {"upcoming", "live", "completed"}:
            raise ValidationError("Invalid match status.")

        if scheduled_order is not None and scheduled_order < 1:
            raise ValidationError("Scheduled order must be positive.")

        self._validate_participant_ids(side1_participant_ids, side2_participant_ids)

        now_iso = utc_now_iso()
        match = self.repo.create_match(
            game_type=clean_game_type,
            scheduled_at=self.normalize_scheduled_at(scheduled_at),
            scheduled_order=scheduled_order,
            status=status,
            created_by_user_id=created_by_user_id,
            now_iso=now_iso,
            side1_name=(side1_name or "").strip() or None,
            side2_name=(side2_name or "").strip() or None,
            side1_participant_ids=side1_participant_ids,
            side2_participant_ids=side2_participant_ids,
        )
        self.repo.log_activity(
            event_type="match_created",
            message=f"Match scheduled: {clean_game_type} (#{match.id})",
            related_match_id=match.id,
            created_at=now_iso,
        )
        return match

    def update_match(
        self,
        *,
        match_id: int,
        game_type: str,
        scheduled_at: Optional[datetime],
        scheduled_order: Optional[int],
        status: str,
        side1_name: Optional[str],
        side2_name: Optional[str],
        side1_participant_ids: list[int],
        side2_participant_ids: list[int],
    ) -> Match:
        existing = self.repo.get_match(match_id)
        if not existing:
            raise NotFoundError("Match not found.")

        clean_game_type = (game_type or "").strip()
        if not clean_game_type:
            raise ValidationError("Game type is required.")

        if status not in {"upcoming", "live", "completed"}:
            raise ValidationError("Invalid match status.")

        if scheduled_order is not None and scheduled_order < 1:
            raise ValidationError("Scheduled order must be positive.")

        self._validate_participant_ids(side1_participant_ids, side2_participant_ids)

        updated = self.repo.update_match(
            match_id=match_id,
            game_type=clean_game_type,
            scheduled_at=self.normalize_scheduled_at(scheduled_at),
            scheduled_order=scheduled_order,
            status=status,
            updated_at=utc_now_iso(),
            side1_name=(side1_name or "").strip() or None,
            side2_name=(side2_name or "").strip() or None,
            side1_participant_ids=side1_participant_ids,
            side2_participant_ids=side2_participant_ids,
        )
        if not updated:
            raise NotFoundError("Match not found after update.")

        self.repo.log_activity(
            event_type="match_updated",
            message=f"Match updated: {clean_game_type} (#{match_id})",
            related_match_id=match_id,
            created_at=utc_now_iso(),
        )
        return updated

    def delete_match(self, match_id: int) -> None:
        existing = self.repo.get_match(match_id)
        if not existing:
            raise NotFoundError("Match not found.")
        self.repo.delete_match(match_id)
        if self.special_service is not None:
            self.special_service.recalculate_match_competition_state()
        self.repo.log_activity(
            event_type="match_deleted",
            message=f"Match deleted: {existing.game_type} (#{match_id})",
            related_match_id=None,
            created_at=utc_now_iso(),
        )

    def list_matches_for_view(
        self,
        *,
        statuses: Optional[list[str]] = None,
        participant_user_id: Optional[int] = None,
    ) -> list[MatchCard]:
        match_rows = self.repo.list_match_rows(statuses=statuses, participant_user_id=participant_user_id)
        match_ids = [int(row["match_id"]) for row in match_rows]

        participant_rows = self.repo.list_match_participant_rows(match_ids)
        include_current_catch_up = not statuses or any(status != "completed" for status in statuses)
        special_icons_by_match_and_user: dict[tuple[int, int], tuple[str, ...]] = {}
        if self.special_service is not None:
            special_icons_by_match_and_user = self.special_service.build_match_special_icon_map(
                match_ids=match_ids,
                include_current_catch_up=include_current_catch_up,
            )
        doubler_by_match_and_user = {
            key: any(icon.startswith("⚡") for icon in icons)
            for key, icons in special_icons_by_match_and_user.items()
        }

        participants_by_match: dict[int, list[MatchCardParticipant]] = {}
        for row in participant_rows:
            match_id = int(row["match_id"])
            user_id = int(row["user_id"])
            participant = MatchCardParticipant(
                user_id=user_id,
                display_name=(
                    row["display_name"]
                    or row["username"]
                    or row["email"]
                    or f"User {row['user_id']}"
                ),
                motto=row["motto"],
                photo_blob=row["photo_blob"],
                photo_mime_type=row["photo_mime_type"],
                side_number=int(row["side_number"]),
                side_name=row["side_name"],
                has_doubler_on_match=doubler_by_match_and_user.get((match_id, user_id), False),
                special_icons=special_icons_by_match_and_user.get((match_id, user_id), ()),
            )
            participants_by_match.setdefault(match_id, []).append(participant)

        cards: list[MatchCard] = []
        for row in match_rows:
            match_id = int(row["match_id"])
            sides: dict[int, dict[str, object]] = {
                1: {"side_name": None, "participants": []},
                2: {"side_name": None, "participants": []},
            }

            for participant in participants_by_match.get(match_id, []):
                side = sides[participant.side_number]
                if side["side_name"] is None and participant.side_name:
                    side["side_name"] = participant.side_name
                cast_list = side["participants"]
                if isinstance(cast_list, list):
                    cast_list.append(participant)

            cards.append(
                MatchCard(
                    match_id=match_id,
                    game_type=row["game_type"],
                    scheduled_at=row["scheduled_at"],
                    scheduled_order=row["scheduled_order"],
                    status=row["status"],
                    outcome=row["outcome"],
                    result_notes=row["result_notes"],
                    sides=sides,
                )
            )

        return cards

    def set_match_result(
        self,
        *,
        match_id: int,
        outcome: str,
        entered_by_user_id: int,
        notes: Optional[str],
        mark_completed: bool = True,
    ) -> None:
        if outcome not in {"side1_win", "draw", "side2_win"}:
            raise ValidationError("Invalid result outcome.")

        match = self.repo.get_match(match_id)
        if not match:
            raise NotFoundError("Match not found.")

        self.repo.upsert_match_result(
            match_id=match_id,
            outcome=outcome,
            entered_by_user_id=entered_by_user_id,
            entered_at=utc_now_iso(),
            notes=(notes or "").strip() or None,
            mark_completed=mark_completed,
        )

        self.repo.log_activity(
            event_type="match_result",
            message=f"Match result entered for {match.game_type} (#{match_id})",
            related_match_id=match_id,
            created_at=utc_now_iso(),
        )
        if self.special_service is not None:
            self.special_service.recalculate_match_competition_state()

    def clear_match_result(self, *, match_id: int, new_status: str = "upcoming") -> None:
        if new_status not in {"upcoming", "live"}:
            raise ValidationError("New status must be upcoming or live.")
        match = self.repo.get_match(match_id)
        if not match:
            raise NotFoundError("Match not found.")

        self.repo.delete_match_result(match_id=match_id, updated_at=utc_now_iso(), new_status=new_status)
        self.repo.log_activity(
            event_type="match_result_cleared",
            message=f"Match result cleared for {match.game_type} (#{match_id})",
            related_match_id=match_id,
            created_at=utc_now_iso(),
        )
        if self.special_service is not None:
            self.special_service.recalculate_match_competition_state()

    def activate_doubler(
        self,
        *,
        participant_user_id: int,
        match_id: int,
        actor_user_id: int,
        admin_override: bool = False,
    ) -> None:
        if self.special_service is None:
            raise ValidationError("Doubler activation is unavailable right now.")
        self.special_service.activate_match_special(
            participant_user_id=participant_user_id,
            special_key="doubler",
            match_id=match_id,
            actor_user_id=actor_user_id,
            admin_override=admin_override,
        )

    def clear_doubler(self, participant_user_id: int) -> None:
        existing = self.repo.get_doubler_activation(participant_user_id)
        if not existing:
            raise NotFoundError("No doubler activation found for that participant.")
        self.repo.delete_doubler_activation(participant_user_id)
        if self.special_service is not None:
            self.special_service.sync_current_special_state()

    def admin_force_reassign_doubler(
        self,
        *,
        participant_user_id: int,
        match_id: int,
        admin_user_id: int,
    ) -> None:
        match = self.repo.get_match(match_id)
        if not match:
            raise NotFoundError("Match not found.")

        if not self.repo.is_participant_in_match(
            participant_user_id=participant_user_id,
            match_id=match_id,
        ):
            raise ValidationError("Participant must be in the selected match.")

        result = self.repo.get_match_result(match_id)
        if result is not None:
            raise ValidationError("Cannot assign doubler to a match with known result.")

        if match.status != "upcoming":
            raise ValidationError("Doubler can only be assigned to upcoming matches.")

        self.repo.delete_doubler_activation(participant_user_id)
        self.activate_doubler(
            participant_user_id=participant_user_id,
            match_id=match_id,
            actor_user_id=admin_user_id,
            admin_override=True,
        )

    def list_doubler_status_rows(self) -> list[dict[str, object]]:
        participant_rows = self.repo.list_participants()
        activations = {
            row["participant_user_id"]: row
            for row in self.repo.list_doubler_rows()
        }

        rows: list[dict[str, object]] = []
        for participant in participant_rows:
            activation = activations.get(participant.user_id)
            rows.append(
                {
                    "user_id": participant.user_id,
                    "name": participant.display_name
                    or participant.username
                    or participant.email
                    or f"User {participant.user_id}",
                    "doubler_used": activation is not None,
                    "match_id": activation["match_id"] if activation else None,
                    "game_type": activation["game_type"] if activation else None,
                    "match_status": activation["status"] if activation else None,
                    "activated_at": activation["activated_at"] if activation else None,
                }
            )

        rows.sort(key=lambda r: str(r["name"]).lower())
        return rows

    def list_eligible_upcoming_matches_for_participant(self, participant_user_id: int) -> list[MatchCard]:
        if self.special_service is not None:
            self.special_service.sync_current_special_state()
            special = self.repo.get_participant_special(
                participant_user_id=participant_user_id,
                special_key="doubler",
            )
            if not special or not special.is_available:
                return []
        elif self.repo.get_doubler_activation(participant_user_id):
            return []

        all_upcoming = self.list_matches_for_view(statuses=["upcoming"], participant_user_id=participant_user_id)
        eligible: list[MatchCard] = []
        for card in all_upcoming:
            if self.repo.get_match_result(card.match_id) is None:
                eligible.append(card)
        return eligible

    def list_recent_activity(self, limit: Optional[int] = 10) -> list[dict[str, str]]:
        items = self.repo.list_recent_activity(limit=limit)
        return [{"timestamp": item.timestamp, "message": item.message} for item in items]
