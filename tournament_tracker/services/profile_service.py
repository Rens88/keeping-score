from __future__ import annotations

from typing import Optional

from tournament_tracker.models import UserWithProfile, utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.errors import NotFoundError, ValidationError


class ProfileService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def get_user_with_profile(self, user_id: int) -> UserWithProfile:
        user = self.repo.get_user_with_profile(user_id)
        if not user:
            raise NotFoundError("User not found")
        return user

    def update_profile(
        self,
        *,
        user_id: int,
        display_name: str,
        motto: str,
        photo_blob: Optional[bytes],
        photo_mime_type: Optional[str],
        delete_existing_photo: bool,
        allow_name_change: bool = True,
    ) -> UserWithProfile:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        existing_profile = self.repo.get_participant_profile(user_id)

        requested_name = (display_name or "").strip()
        if allow_name_change:
            clean_name = requested_name
        else:
            clean_name = (
                existing_profile.display_name
                if existing_profile and existing_profile.display_name
                else requested_name
            )
        clean_motto = (motto or "").strip()

        if len(clean_name) < 2 or len(clean_name) > 80:
            raise ValidationError("Name must be between 2 and 80 characters.")
        if len(clean_motto) < 1 or len(clean_motto) > 160:
            raise ValidationError("Motto must be between 1 and 160 characters.")

        if photo_blob:
            effective_photo_blob = photo_blob
            effective_photo_type = photo_mime_type
        elif delete_existing_photo:
            effective_photo_blob = None
            effective_photo_type = None
        elif existing_profile:
            effective_photo_blob = existing_profile.photo_blob
            effective_photo_type = existing_profile.photo_mime_type
        else:
            effective_photo_blob = None
            effective_photo_type = None

        self.repo.upsert_participant_profile(
            user_id=user_id,
            display_name=clean_name,
            motto=clean_motto,
            photo_blob=effective_photo_blob,
            photo_mime_type=effective_photo_type,
            now_iso=utc_now_iso(),
        )

        updated = self.repo.get_user_with_profile(user_id)
        if not updated:
            raise RuntimeError("Profile update failed")
        return updated

    def list_participant_profiles(self) -> list[UserWithProfile]:
        return self.repo.list_participants()

    def admin_update_participant_name(self, *, participant_user_id: int, new_display_name: str) -> UserWithProfile:
        user = self.repo.get_user_by_id(participant_user_id)
        if not user:
            raise NotFoundError("Participant user not found.")
        if user.role != "participant":
            raise ValidationError("Only participant names can be edited here.")

        profile = self.repo.get_participant_profile(participant_user_id)
        if not profile:
            raise NotFoundError("Participant profile not found.")

        clean_name = (new_display_name or "").strip()
        if len(clean_name) < 2 or len(clean_name) > 80:
            raise ValidationError("Name must be between 2 and 80 characters.")

        self.repo.upsert_participant_profile(
            user_id=participant_user_id,
            display_name=clean_name,
            motto=profile.motto,
            photo_blob=profile.photo_blob,
            photo_mime_type=profile.photo_mime_type,
            now_iso=utc_now_iso(),
        )
        updated = self.repo.get_user_with_profile(participant_user_id)
        if not updated:
            raise RuntimeError("Failed to update participant name.")
        return updated
