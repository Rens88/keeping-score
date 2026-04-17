from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
from typing import Optional

from tournament_tracker.models import User
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.security import hash_password
from tournament_tracker.services.errors import NotFoundError, ValidationError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


@dataclass(slots=True)
class InvitationCreationResult:
    token: str
    invitation_id: int
    expires_at: str


@dataclass(slots=True)
class InvitationValidationResult:
    valid: bool
    message: str
    invitation_id: Optional[int] = None


class InvitationService:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_iso_timestamp(value: str) -> datetime:
        clean_value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def create_invitation(
        self,
        *,
        created_by_user_id: int,
        expiry_hours: int,
        note: Optional[str],
    ) -> InvitationCreationResult:
        if expiry_hours <= 0 or expiry_hours > 24 * 14:
            raise ValidationError("Expiry must be between 1 and 336 hours.")

        token = secrets.token_urlsafe(24)
        token_hash = self.hash_token(token)
        now = datetime.now(tz=timezone.utc)
        expires_at = (now + timedelta(hours=expiry_hours)).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )
        now_iso = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

        invitation = self.repo.create_invitation(
            token_hash=token_hash,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at,
            now_iso=now_iso,
            note=(note or "").strip() or None,
        )

        return InvitationCreationResult(
            token=token,
            invitation_id=invitation.id,
            expires_at=invitation.expires_at,
        )

    def validate_invitation_token(self, token: str) -> InvitationValidationResult:
        clean_token = (token or "").strip()
        if not clean_token:
            return InvitationValidationResult(valid=False, message="Invitation token is required.")

        invitation = self.repo.get_invitation_by_token_hash(self.hash_token(clean_token))
        if not invitation:
            return InvitationValidationResult(valid=False, message="Invitation link is invalid.")

        if invitation.used_at:
            return InvitationValidationResult(valid=False, message="Invitation link has already been used.")

        now = datetime.now(tz=timezone.utc)
        expires_at = self._parse_iso_timestamp(invitation.expires_at)
        if expires_at <= now:
            return InvitationValidationResult(valid=False, message="Invitation link has expired.")

        return InvitationValidationResult(
            valid=True,
            message="Invitation is valid.",
            invitation_id=invitation.id,
        )

    def accept_invitation(
        self,
        *,
        token: str,
        username: Optional[str],
        email: Optional[str],
        password: str,
        display_name: str,
        motto: str,
        photo_blob: Optional[bytes],
        photo_mime_type: Optional[str],
    ) -> User:
        token = (token or "").strip()
        username = (username or "").strip() or None
        email = (email or "").strip().lower() or None
        display_name = (display_name or "").strip()
        motto = (motto or "").strip()

        if not token:
            raise ValidationError("Invitation token is required.")

        if not username and not email:
            raise ValidationError("Provide at least a username or an email.")

        if username and not _USERNAME_RE.match(username):
            raise ValidationError(
                "Username must be 3-30 characters and only include letters, numbers, ., _, or -."
            )

        if email and not _EMAIL_RE.match(email):
            raise ValidationError("Please enter a valid email address.")

        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters.")

        if len(display_name) < 2 or len(display_name) > 80:
            raise ValidationError("Name must be between 2 and 80 characters.")

        if len(motto) < 1 or len(motto) > 160:
            raise ValidationError("Motto must be between 1 and 160 characters.")

        if not photo_blob:
            raise ValidationError("A profile photo is required.")

        if len(photo_blob) > 3 * 1024 * 1024:
            raise ValidationError("Photo is too large. Please upload an image under 3MB.")

        validation = self.validate_invitation_token(token)
        if not validation.valid:
            raise NotFoundError(validation.message)

        now_iso = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        if username and self.repo.get_user_by_username(username):
            raise ValidationError("That username is already in use.")
        if email and self.repo.get_user_by_email(email):
            raise ValidationError("That email address is already in use.")

        invitation_id = validation.invitation_id
        if invitation_id is None:
            raise NotFoundError("Invitation not found.")

        try:
            user = self.repo.accept_invitation_create_participant(
                invitation_id=invitation_id,
                username=username,
                email=email,
                password_hash=hash_password(password),
                display_name=display_name,
                motto=motto,
                photo_blob=photo_blob,
                photo_mime_type=photo_mime_type,
                now_iso=now_iso,
            )
            return user
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
