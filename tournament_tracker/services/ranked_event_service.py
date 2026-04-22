from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from tournament_tracker.models import RankedEvent, utc_now_iso
from tournament_tracker.repository import COMPETITION_RANKING_SOURCE_TYPE, SQLiteRepository
from tournament_tracker.services.errors import NotFoundError, ValidationError


DEFAULT_RANKED_EVENT_AWARD_SCHEME = (5, 3, 1)


class RankedEventService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    @staticmethod
    def normalize_scheduled_at(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.isoformat(timespec="minutes")
        return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes")

    @staticmethod
    def parse_award_scheme(raw_value: str | None) -> tuple[int, ...]:
        raw = (raw_value or "").strip()
        if not raw:
            return DEFAULT_RANKED_EVENT_AWARD_SCHEME

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
            return DEFAULT_RANKED_EVENT_AWARD_SCHEME
        return tuple(values)

    @staticmethod
    def serialize_award_scheme(values: tuple[int, ...]) -> str:
        if not values:
            values = DEFAULT_RANKED_EVENT_AWARD_SCHEME
        return ",".join(str(value) for value in values)

    def _validate_competitor_ids(self, competitor_user_ids: list[int]) -> None:
        unique_ids = list(dict.fromkeys(competitor_user_ids))
        if len(unique_ids) < 2:
            raise ValidationError("Choose at least two competitors for a ranked event.")
        if self.repo.count_participant_users(unique_ids) != len(unique_ids):
            raise ValidationError("One or more selected competitors are not valid participants.")

    def _validate_event_fields(
        self,
        *,
        title: str,
        scheduled_order: Optional[int],
        status: str,
        award_scheme: tuple[int, ...],
        competitor_user_ids: list[int],
    ) -> None:
        clean_title = (title or "").strip()
        if len(clean_title) < 2:
            raise ValidationError("Event title must be at least 2 characters.")
        if scheduled_order is not None and scheduled_order < 1:
            raise ValidationError("Scheduled order must be positive.")
        if status not in {"upcoming", "live", "completed"}:
            raise ValidationError("Invalid event status.")
        if not award_scheme:
            raise ValidationError("Add at least one award value.")
        self._validate_competitor_ids(competitor_user_ids)

    def create_event(
        self,
        *,
        title: str,
        scheduled_at: Optional[datetime],
        scheduled_order: Optional[int],
        status: str,
        award_scheme: tuple[int, ...],
        competitor_user_ids: list[int],
        created_by_user_id: int,
    ) -> RankedEvent:
        unique_ids = list(dict.fromkeys(competitor_user_ids))
        clean_title = (title or "").strip()
        self._validate_event_fields(
            title=clean_title,
            scheduled_order=scheduled_order,
            status=status,
            award_scheme=award_scheme,
            competitor_user_ids=unique_ids,
        )
        now_iso = utc_now_iso()
        event = self.repo.create_ranked_event(
            title=clean_title,
            scheduled_at=self.normalize_scheduled_at(scheduled_at),
            scheduled_order=scheduled_order,
            status=status,
            award_scheme=self.serialize_award_scheme(award_scheme),
            created_by_user_id=created_by_user_id,
            created_at=now_iso,
            competitor_user_ids=unique_ids,
        )
        self.repo.log_activity(
            event_type="ranked_event_created",
            message=f"Ranked event created: {clean_title} (#{event.id})",
            related_user_id=created_by_user_id,
            created_at=now_iso,
        )
        return event

    def update_event(
        self,
        *,
        event_id: int,
        title: str,
        scheduled_at: Optional[datetime],
        scheduled_order: Optional[int],
        status: str,
        award_scheme: tuple[int, ...],
        competitor_user_ids: list[int],
        updated_by_user_id: int,
    ) -> RankedEvent:
        unique_ids = list(dict.fromkeys(competitor_user_ids))
        clean_title = (title or "").strip()
        self._validate_event_fields(
            title=clean_title,
            scheduled_order=scheduled_order,
            status=status,
            award_scheme=award_scheme,
            competitor_user_ids=unique_ids,
        )
        updated = self.repo.update_ranked_event(
            event_id=event_id,
            title=clean_title,
            scheduled_at=self.normalize_scheduled_at(scheduled_at),
            scheduled_order=scheduled_order,
            status=status,
            award_scheme=self.serialize_award_scheme(award_scheme),
            updated_at=utc_now_iso(),
            competitor_user_ids=unique_ids,
        )
        if not updated:
            raise NotFoundError("Ranked event not found.")
        self.repo.log_activity(
            event_type="ranked_event_updated",
            message=f"Ranked event updated: {clean_title} (#{event_id})",
            related_user_id=updated_by_user_id,
            created_at=utc_now_iso(),
        )
        return updated

    def delete_event(self, event_id: int) -> None:
        existing = self.repo.get_ranked_event(event_id)
        if not existing:
            raise NotFoundError("Ranked event not found.")
        self.repo.delete_competition_point_awards_for_source(
            source_type=COMPETITION_RANKING_SOURCE_TYPE,
            source_key=f"ranked_event:{event_id}",
        )
        self.repo.delete_ranked_event(event_id)
        self.repo.log_activity(
            event_type="ranked_event_deleted",
            message=f"Ranked event deleted: {existing.title} (#{event_id})",
            created_at=utc_now_iso(),
        )

    def list_events(self, statuses: Optional[list[str]] = None) -> list[RankedEvent]:
        return self.repo.list_ranked_events(statuses=statuses)

    def get_event_competitor_rows(self, event_ids: list[int]) -> list[dict[str, object]]:
        return self.repo.list_ranked_event_competitor_rows(event_ids)

    def get_event_results_map(self, event_id: int) -> dict[int, int]:
        return {
            result.participant_user_id: result.placement
            for result in self.repo.list_ranked_event_results(event_id=event_id)
        }

    def save_results(
        self,
        *,
        event_id: int,
        placements_by_user_id: dict[int, int],
        entered_by_user_id: int,
    ) -> None:
        event = self.repo.get_ranked_event(event_id)
        if not event:
            raise NotFoundError("Ranked event not found.")

        competitor_rows = self.repo.list_ranked_event_competitor_rows([event_id])
        competitor_ids = {int(row["participant_user_id"]) for row in competitor_rows}
        if not competitor_ids:
            raise ValidationError("This ranked event has no competitors.")
        if set(placements_by_user_id.keys()) != competitor_ids:
            raise ValidationError("Every competitor needs a placement.")
        if any(placement < 1 for placement in placements_by_user_id.values()):
            raise ValidationError("Placements must be positive whole numbers.")

        award_scheme = self.parse_award_scheme(event.award_scheme)
        now_iso = utc_now_iso()
        self.repo.replace_ranked_event_results(
            event_id=event_id,
            results=[
                (participant_user_id, int(placement), now_iso, entered_by_user_id)
                for participant_user_id, placement in placements_by_user_id.items()
            ],
        )
        self.repo.update_ranked_event(
            event_id=event_id,
            title=event.title,
            scheduled_at=event.scheduled_at,
            scheduled_order=event.scheduled_order,
            status="completed",
            award_scheme=event.award_scheme,
            updated_at=now_iso,
            competitor_user_ids=sorted(competitor_ids),
        )
        self.repo.replace_competition_point_awards(
            source_type=COMPETITION_RANKING_SOURCE_TYPE,
            source_key=f"ranked_event:{event_id}",
            source_label=event.title,
            awards=[
                (
                    participant_user_id,
                    int(placement),
                    float(award_scheme[int(placement) - 1]),
                    now_iso,
                    entered_by_user_id,
                )
                for participant_user_id, placement in placements_by_user_id.items()
                if int(placement) <= len(award_scheme)
            ],
        )
        self.repo.log_activity(
            event_type="ranked_event_results_saved",
            message=f"Ranked event results saved: {event.title} (#{event_id})",
            related_user_id=entered_by_user_id,
            created_at=now_iso,
        )

    def clear_results(
        self,
        *,
        event_id: int,
        status_after_clear: str,
        cleared_by_user_id: int,
    ) -> RankedEvent:
        event = self.repo.get_ranked_event(event_id)
        if not event:
            raise NotFoundError("Ranked event not found.")
        if status_after_clear not in {"upcoming", "live", "completed"}:
            raise ValidationError("Invalid status after clearing results.")

        competitor_rows = self.repo.list_ranked_event_competitor_rows([event_id])
        competitor_ids = [int(row["participant_user_id"]) for row in competitor_rows]
        now_iso = utc_now_iso()
        self.repo.delete_ranked_event_results(event_id)
        self.repo.delete_competition_point_awards_for_source(
            source_type=COMPETITION_RANKING_SOURCE_TYPE,
            source_key=f"ranked_event:{event_id}",
        )
        updated = self.repo.update_ranked_event(
            event_id=event_id,
            title=event.title,
            scheduled_at=event.scheduled_at,
            scheduled_order=event.scheduled_order,
            status=status_after_clear,
            award_scheme=event.award_scheme,
            updated_at=now_iso,
            competitor_user_ids=competitor_ids,
        )
        if not updated:
            raise NotFoundError("Ranked event not found after clearing results.")
        self.repo.log_activity(
            event_type="ranked_event_results_cleared",
            message=f"Ranked event results cleared: {event.title} (#{event_id})",
            related_user_id=cleared_by_user_id,
            created_at=now_iso,
        )
        return updated
