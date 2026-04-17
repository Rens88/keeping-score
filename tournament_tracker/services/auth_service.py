from __future__ import annotations

from typing import Optional

from tournament_tracker.models import User, utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.security import hash_password, verify_password
from tournament_tracker.services.errors import ValidationError


class AuthService:
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
