from __future__ import annotations

from typing import Optional

from tournament_tracker.models import User, utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.security import hash_password, verify_password
from tournament_tracker.services.errors import ValidationError


class AuthService:
    MIN_PASSWORD_LENGTH = 4

    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def authenticate(self, login_identifier: str, password: str) -> Optional[User]:
        login = login_identifier.strip()
        if not login or not password:
            return None

        user = self.repo.get_user_by_login(login)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def ensure_seed_admin(self, username: str, email: str, password: str) -> User:
        if len(password) < 8:
            raise ValidationError("Seed admin password must be at least 8 characters.")

        return self.repo.ensure_admin_exists(
            username=username.strip() or "admin",
            email=email.strip().lower(),
            password_hash=hash_password(password),
            now_iso=utc_now_iso(),
        )

    def _validate_new_password(self, password: str) -> None:
        if len(password) < self.MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password must be at least {self.MIN_PASSWORD_LENGTH} characters."
            )

    def change_password(
        self,
        *,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> None:
        user = self.repo.get_user_by_id(user_id)
        if not user or not user.is_active:
            raise ValidationError("User account not found.")
        if not verify_password(current_password, user.password_hash):
            raise ValidationError("Current password is incorrect.")

        self._validate_new_password(new_password)
        if verify_password(new_password, user.password_hash):
            raise ValidationError("New password must be different from the current password.")

        now_iso = utc_now_iso()
        updated = self.repo.update_user_password(
            user_id=user_id,
            password_hash=hash_password(new_password),
            updated_at=now_iso,
        )
        if not updated:
            raise ValidationError("Password update failed.")

        self.repo.log_activity(
            event_type="password_changed",
            message=f"Password changed for user {user_id}",
            created_at=now_iso,
            related_user_id=user_id,
        )

    def admin_reset_password(
        self,
        *,
        admin_user_id: int,
        target_user_id: int,
        new_password: str,
    ) -> None:
        admin_user = self.repo.get_user_by_id(admin_user_id)
        if not admin_user or admin_user.role != "admin":
            raise ValidationError("Only admins can reset passwords.")

        target_user = self.repo.get_user_by_id(target_user_id)
        if not target_user:
            raise ValidationError("Target user not found.")

        self._validate_new_password(new_password)

        now_iso = utc_now_iso()
        updated = self.repo.update_user_password(
            user_id=target_user_id,
            password_hash=hash_password(new_password),
            updated_at=now_iso,
        )
        if not updated:
            raise ValidationError("Password reset failed.")

        self.repo.log_activity(
            event_type="password_reset_admin",
            message=f"Admin reset password for user {target_user_id}",
            created_at=now_iso,
            related_user_id=target_user_id,
        )
