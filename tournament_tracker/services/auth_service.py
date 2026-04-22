from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from tournament_tracker.models import User, utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.security import generate_session_token, hash_password, hash_token, verify_password
from tournament_tracker.services.errors import ValidationError


class AuthService:
    MIN_PASSWORD_LENGTH = 4

    def __init__(self, repo: SQLiteRepository, *, persistent_login_days: int = 30) -> None:
        self.repo = repo
        self.persistent_login_days = max(1, int(persistent_login_days))

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

    def create_persistent_session(self, user_id: int) -> tuple[str, int]:
        token = generate_session_token()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_iso = now.isoformat().replace("+00:00", "Z")
        expires_at = (now + timedelta(days=self.persistent_login_days)).isoformat().replace("+00:00", "Z")
        self.repo.create_auth_session(
            user_id=user_id,
            token_hash=hash_token(token),
            created_at=now_iso,
            expires_at=expires_at,
        )
        return token, self.persistent_login_days * 24 * 60 * 60

    def restore_persistent_session(self, token: str) -> Optional[User]:
        clean_token = (token or "").strip()
        if not clean_token:
            return None

        now_iso = utc_now_iso()
        session = self.repo.get_active_auth_session_by_token_hash(
            token_hash=hash_token(clean_token),
            now_iso=now_iso,
        )
        if not session:
            return None

        user = self.repo.get_user_by_id(session.user_id)
        if not user or not user.is_active:
            self.repo.revoke_auth_session_by_token_hash(
                token_hash=session.token_hash,
                revoked_at=now_iso,
            )
            return None

        self.repo.touch_auth_session(session_id=session.id, now_iso=now_iso)
        return user

    def revoke_persistent_session(self, token: str) -> None:
        clean_token = (token or "").strip()
        if not clean_token:
            return
        self.repo.revoke_auth_session_by_token_hash(
            token_hash=hash_token(clean_token),
            revoked_at=utc_now_iso(),
        )

    def revoke_all_persistent_sessions_for_user(self, user_id: int) -> None:
        self.repo.revoke_auth_sessions_for_user(user_id=user_id, revoked_at=utc_now_iso())

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

        self.repo.revoke_auth_sessions_for_user(user_id=user_id, revoked_at=now_iso)

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

        self.repo.revoke_auth_sessions_for_user(user_id=target_user_id, revoked_at=now_iso)

        self.repo.log_activity(
            event_type="password_reset_admin",
            message=f"Admin reset password for user {target_user_id}",
            created_at=now_iso,
            related_user_id=target_user_id,
        )
