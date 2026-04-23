from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ModuleNotFoundError:
    boto3 = None
    BotoConfig = None

from tournament_tracker.config import AppConfig
from tournament_tracker.models import utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.errors import ValidationError


BACKUP_STATUS_LAST_SUCCESS_AT_KEY = "backup_offsite_last_success_at"
BACKUP_STATUS_LAST_OBJECT_KEY = "backup_offsite_last_object_key"
BACKUP_STATUS_LAST_ERROR_AT_KEY = "backup_offsite_last_error_at"
BACKUP_STATUS_LAST_ERROR_MESSAGE_KEY = "backup_offsite_last_error_message"
BACKUP_STATUS_LAST_ATTEMPT_AT_KEY = "backup_offsite_last_attempt_at"


@dataclass(frozen=True, slots=True)
class OffsiteBackupStatus:
    configured: bool
    enabled: bool
    dependency_available: bool
    provider_label: str
    bucket: Optional[str]
    endpoint: Optional[str]
    region: Optional[str]
    prefix: str
    last_success_at: Optional[str]
    last_object_key: Optional[str]
    last_error_at: Optional[str]
    last_error_message: Optional[str]
    last_attempt_at: Optional[str]
    status_label: str
    detail_message: str


@dataclass(frozen=True, slots=True)
class OffsiteBackupResult:
    success: bool
    attempted: bool
    object_key: Optional[str]
    message: str


class BackupService:
    DEMO_HALFWAY_PATH = Path(__file__).resolve().parents[2] / "demo_state" / "weekend_tracker_requested_demo_state.sqlite3"

    def __init__(self, repo: SQLiteRepository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config
        self.repo.set_after_write_hook(self._sync_after_write)

    @staticmethod
    def _sanitize_object_part(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
        cleaned = cleaned.strip("-._")
        return cleaned or "backup"

    @staticmethod
    def _derive_region_from_endpoint(endpoint: Optional[str]) -> Optional[str]:
        if not endpoint:
            return None
        hostname = urlparse(endpoint).netloc or endpoint
        parts = hostname.split(".")
        if len(parts) >= 4 and parts[0] == "s3":
            return parts[1]
        return None

    def _is_offsite_configured(self) -> bool:
        return all(
            [
                self.config.backup_s3_endpoint,
                self.config.backup_s3_bucket,
                self.config.backup_s3_access_key_id,
                self.config.backup_s3_secret_access_key,
            ]
        )

    def _resolved_region(self) -> Optional[str]:
        return self.config.backup_s3_region or self._derive_region_from_endpoint(self.config.backup_s3_endpoint)

    def _write_backup_status_setting(self, key: str, value: str) -> None:
        self.repo.set_app_setting(
            key=key,
            value=value,
            updated_at=utc_now_iso(),
            trigger_backup=False,
        )

    def _update_last_attempt(self, attempted_at: str) -> None:
        self._write_backup_status_setting(BACKUP_STATUS_LAST_ATTEMPT_AT_KEY, attempted_at)

    def _record_sync_success(self, *, attempted_at: str, object_key: str) -> None:
        self._write_backup_status_setting(BACKUP_STATUS_LAST_SUCCESS_AT_KEY, attempted_at)
        self._write_backup_status_setting(BACKUP_STATUS_LAST_OBJECT_KEY, object_key)
        self._write_backup_status_setting(BACKUP_STATUS_LAST_ERROR_AT_KEY, "")
        self._write_backup_status_setting(BACKUP_STATUS_LAST_ERROR_MESSAGE_KEY, "")

    def _record_sync_failure(self, *, attempted_at: str, message: str) -> None:
        self._write_backup_status_setting(BACKUP_STATUS_LAST_ERROR_AT_KEY, attempted_at)
        self._write_backup_status_setting(BACKUP_STATUS_LAST_ERROR_MESSAGE_KEY, message)

    def _build_object_key(self, *, reason: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%Y%m%dT%H%M%SZ")
        db_name = self._sanitize_object_part(self.repo.db_path.stem)
        reason_part = self._sanitize_object_part(reason)
        prefix_parts = [part for part in self.config.backup_s3_prefix.split("/") if part]
        return "/".join(prefix_parts + ["automatic", timestamp, f"{db_name}_{reason_part}.sqlite3"])

    def _build_s3_client(self):
        if boto3 is None or BotoConfig is None:
            raise RuntimeError("Missing optional dependency `boto3`.")
        return boto3.client(
            "s3",
            endpoint_url=self.config.backup_s3_endpoint,
            region_name=self._resolved_region(),
            aws_access_key_id=self.config.backup_s3_access_key_id,
            aws_secret_access_key=self.config.backup_s3_secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    def _upload_offsite_snapshot(self, *, reason: str) -> OffsiteBackupResult:
        attempted_at = utc_now_iso()

        if not self._is_offsite_configured():
            return OffsiteBackupResult(
                success=False,
                attempted=False,
                object_key=None,
                message="Off-site backup is not configured yet.",
            )

        if boto3 is None or BotoConfig is None:
            message = "Off-site backup is configured, but the `boto3` dependency is missing."
            self._record_sync_failure(attempted_at=attempted_at, message=message)
            return OffsiteBackupResult(success=False, attempted=False, object_key=None, message=message)

        self._update_last_attempt(attempted_at)
        object_key = self._build_object_key(reason=reason)
        try:
            backup_bytes = self.repo.export_database_bytes()
            if not backup_bytes:
                raise RuntimeError("The local database file is empty.")

            client = self._build_s3_client()
            client.put_object(
                Bucket=str(self.config.backup_s3_bucket),
                Key=object_key,
                Body=backup_bytes,
                ContentType="application/x-sqlite3",
                Metadata={
                    "app": "keeping-score",
                    "source-db": self.repo.db_path.name,
                    "uploaded-at": attempted_at,
                },
            )
        except Exception as exc:
            message = str(exc) or "Unknown upload error."
            self._record_sync_failure(attempted_at=attempted_at, message=message)
            return OffsiteBackupResult(
                success=False,
                attempted=True,
                object_key=None,
                message=message,
            )

        self._record_sync_success(attempted_at=attempted_at, object_key=object_key)
        return OffsiteBackupResult(
            success=True,
            attempted=True,
            object_key=object_key,
            message=f"Off-site backup uploaded to {object_key}.",
        )

    def _sync_after_write(self) -> None:
        self._upload_offsite_snapshot(reason="auto")

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

        self._upload_offsite_snapshot(reason="manual-import")

    def run_offsite_backup_now(self) -> OffsiteBackupResult:
        return self._upload_offsite_snapshot(reason="manual")

    def get_offsite_backup_status(self) -> OffsiteBackupStatus:
        configured = self._is_offsite_configured()
        dependency_available = boto3 is not None and BotoConfig is not None
        enabled = configured and dependency_available
        last_success_at = self.repo.get_app_setting(BACKUP_STATUS_LAST_SUCCESS_AT_KEY) or None
        last_object_key = self.repo.get_app_setting(BACKUP_STATUS_LAST_OBJECT_KEY) or None
        last_error_at = self.repo.get_app_setting(BACKUP_STATUS_LAST_ERROR_AT_KEY) or None
        last_error_message = self.repo.get_app_setting(BACKUP_STATUS_LAST_ERROR_MESSAGE_KEY) or None
        last_attempt_at = self.repo.get_app_setting(BACKUP_STATUS_LAST_ATTEMPT_AT_KEY) or None

        if enabled:
            status_label = "Connected"
            detail_message = (
                "Automatic off-site backups are enabled. Every committed tournament-data write uploads "
                "a fresh SQLite snapshot to your configured S3-compatible bucket."
            )
        elif configured and not dependency_available:
            status_label = "Dependency missing"
            detail_message = "The backup credentials are present, but `boto3` is not installed yet."
        else:
            status_label = "Not configured"
            detail_message = (
                "Add the S3-compatible backup secrets in Streamlit Cloud to enable automatic off-site backups."
            )

        return OffsiteBackupStatus(
            configured=configured,
            enabled=enabled,
            dependency_available=dependency_available,
            provider_label="S3-compatible storage (Backblaze B2 works here)",
            bucket=self.config.backup_s3_bucket,
            endpoint=self.config.backup_s3_endpoint,
            region=self._resolved_region(),
            prefix=self.config.backup_s3_prefix,
            last_success_at=last_success_at,
            last_object_key=last_object_key,
            last_error_at=last_error_at,
            last_error_message=last_error_message,
            last_attempt_at=last_attempt_at,
            status_label=status_label,
            detail_message=detail_message,
        )

    def get_streamlit_secrets_template(self) -> str:
        return "\n".join(
            [
                'BACKUP_S3_ENDPOINT = "https://s3.<your-region>.backblazeb2.com"',
                'BACKUP_S3_BUCKET = "your-backup-bucket-name"',
                'BACKUP_S3_REGION = "<your-region>"',
                'BACKUP_S3_ACCESS_KEY_ID = "your-backblaze-key-id"',
                'BACKUP_S3_SECRET_ACCESS_KEY = "your-backblaze-application-key"',
                'BACKUP_S3_PREFIX = "keeping-score/live"',
            ]
        )

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
