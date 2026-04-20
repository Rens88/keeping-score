from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from tournament_tracker.models import utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.errors import ValidationError


class BackupService:
    DEMO_HALFWAY_PATH = Path(__file__).resolve().parents[2] / "demo_state" / "weekend_tracker_requested_demo_state.sqlite3"

    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def export_snapshot(self) -> tuple[str, bytes]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"weekend_tracker_full_backup_{timestamp}.sqlite3"
        data = self.repo.export_database_bytes()
        return filename, data

    def import_snapshot(self, backup_bytes: bytes) -> None:
        if not backup_bytes:
            raise ValidationError("Upload a non-empty backup file.")

        if len(backup_bytes) > 100 * 1024 * 1024:
            raise ValidationError("Backup file is too large (max 100MB).")

        try:
            self.repo.import_database_bytes(backup_bytes)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def get_demo_halfway_snapshot_path(self) -> Path:
        return self.DEMO_HALFWAY_PATH

    def load_demo_halfway_state(self) -> None:
        snapshot_path = self.get_demo_halfway_snapshot_path()
        if not snapshot_path.exists():
            raise ValidationError("The demo half-way snapshot could not be found.")
        self.import_snapshot(snapshot_path.read_bytes())

    def reset_to_fresh_state(self, *, preserve_admin_user_id: int) -> None:
        admin_user = self.repo.get_user_by_id(preserve_admin_user_id)
        if not admin_user or admin_user.role != "admin":
            raise ValidationError("A valid admin account is required for a fresh reset.")

        with tempfile.TemporaryDirectory(prefix="weekend_tracker_reset_") as temp_dir:
            temp_db_path = Path(temp_dir) / "fresh_state.sqlite3"
            fresh_repo = SQLiteRepository(temp_db_path)
            fresh_repo.apply_migrations()
            fresh_repo.ensure_admin_exists(
                username=admin_user.username or "admin",
                email=admin_user.email or "admin@reset.local",
                password_hash=admin_user.password_hash,
                now_iso=utc_now_iso(),
            )
            self.import_snapshot(temp_db_path.read_bytes())
