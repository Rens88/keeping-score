from __future__ import annotations

from datetime import datetime, timezone

from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.errors import ValidationError


class BackupService:
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
