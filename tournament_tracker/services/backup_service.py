from __future__ import annotations

import re
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
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
BACKUP_STATUS_LAST_RESTORE_AT_KEY = "backup_offsite_last_restore_at"
BACKUP_STATUS_LAST_RESTORE_OBJECT_KEY = "backup_offsite_last_restore_object_key"
BACKUP_SETTINGS_AUTO_INTERVAL_MINUTES_KEY = "backup_offsite_auto_interval_minutes"
BACKUP_SETTINGS_MANUAL_PREFIX_KEY = "backup_offsite_manual_prefix"
DEFAULT_AUTO_BACKUP_INTERVAL_MINUTES = 60
DEFAULT_MANUAL_BACKUP_PREFIX = "manual-backup"


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
    last_restore_at: Optional[str]
    last_restore_object_key: Optional[str]
    status_label: str
    detail_message: str


@dataclass(frozen=True, slots=True)
class OffsiteBackupResult:
    success: bool
    attempted: bool
    object_key: Optional[str]
    message: str


@dataclass(frozen=True, slots=True)
class OffsiteRestoreResult:
    restored: bool
    blocking_failure: bool
    object_key: Optional[str]
    message: str


@dataclass(frozen=True, slots=True)
class BackupSettings:
    auto_interval_minutes: int
    manual_prefix: str


@dataclass(frozen=True, slots=True)
class OffsiteBackupTargets:
    automatic_prefix: str
    automatic_object_key: str
    manual_prefix_root: str
    manual_object_key: str


@dataclass(frozen=True, slots=True)
class OffsiteBackupObject:
    object_key: str
    category: str
    size_bytes: int
    last_modified_at: Optional[str]


class BackupService:
    DEMO_HALFWAY_PATH = Path(__file__).resolve().parents[2] / "demo_state" / "weekend_tracker_requested_demo_state.sqlite3"

    def __init__(
        self,
        repo: SQLiteRepository,
        config: AppConfig,
        *,
        register_after_write_hook: bool = True,
    ) -> None:
        self.repo = repo
        self.config = config
        if register_after_write_hook:
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

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> Optional[datetime]:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    @staticmethod
    def _format_datetime(value: datetime | None) -> Optional[str]:
        if value is None:
            return None
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _automatic_backup_prefix(self) -> str:
        prefix_parts = [part for part in self.config.backup_s3_prefix.split("/") if part]
        return "/".join(prefix_parts + ["automatic"])

    def _manual_backup_prefix_root(self) -> str:
        prefix_parts = [part for part in self.config.backup_s3_prefix.split("/") if part]
        return "/".join(prefix_parts + ["manual"])

    def _default_automatic_object_key(self) -> str:
        db_name = self._sanitize_object_part(self.repo.db_path.stem)
        return "/".join([self._automatic_backup_prefix(), f"{db_name}_latest.sqlite3"])

    def _default_manual_object_key(self, manual_prefix: str) -> str:
        db_name = self._sanitize_object_part(self.repo.db_path.stem)
        manual_part = self._sanitize_object_part(manual_prefix)
        return "/".join([self._manual_backup_prefix_root(), f"{manual_part}_{db_name}.sqlite3"])

    def get_backup_settings(self) -> BackupSettings:
        raw_interval = (self.repo.get_app_setting(BACKUP_SETTINGS_AUTO_INTERVAL_MINUTES_KEY) or "").strip()
        try:
            auto_interval_minutes = int(raw_interval) if raw_interval else DEFAULT_AUTO_BACKUP_INTERVAL_MINUTES
        except ValueError:
            auto_interval_minutes = DEFAULT_AUTO_BACKUP_INTERVAL_MINUTES
        auto_interval_minutes = max(0, min(auto_interval_minutes, 7 * 24 * 60))

        manual_prefix = (self.repo.get_app_setting(BACKUP_SETTINGS_MANUAL_PREFIX_KEY) or "").strip()
        if not manual_prefix:
            manual_prefix = DEFAULT_MANUAL_BACKUP_PREFIX

        return BackupSettings(
            auto_interval_minutes=auto_interval_minutes,
            manual_prefix=manual_prefix,
        )

    def update_backup_settings(self, *, auto_interval_minutes: int, manual_prefix: str) -> BackupSettings:
        cleaned_manual_prefix = manual_prefix.strip()
        if auto_interval_minutes < 0:
            raise ValidationError("Automatic backup interval cannot be negative.")
        if auto_interval_minutes > 7 * 24 * 60:
            raise ValidationError("Automatic backup interval cannot exceed 10080 minutes (7 days).")
        if not cleaned_manual_prefix:
            raise ValidationError("Manual backup prefix cannot be empty.")
        if len(cleaned_manual_prefix) > 80:
            raise ValidationError("Manual backup prefix is too long (max 80 characters).")

        now_iso = utc_now_iso()
        self.repo.set_app_setting(
            key=BACKUP_SETTINGS_AUTO_INTERVAL_MINUTES_KEY,
            value=str(int(auto_interval_minutes)),
            updated_at=now_iso,
            trigger_backup=False,
        )
        self.repo.set_app_setting(
            key=BACKUP_SETTINGS_MANUAL_PREFIX_KEY,
            value=cleaned_manual_prefix,
            updated_at=now_iso,
            trigger_backup=False,
        )
        return BackupSettings(
            auto_interval_minutes=int(auto_interval_minutes),
            manual_prefix=cleaned_manual_prefix,
        )

    def _current_automatic_object_key(self) -> str:
        current_key = (self.repo.get_app_setting(BACKUP_STATUS_LAST_OBJECT_KEY) or "").strip()
        if current_key.startswith(self._automatic_backup_prefix()):
            return current_key
        return self._default_automatic_object_key()

    def get_offsite_backup_targets(self) -> OffsiteBackupTargets:
        settings = self.get_backup_settings()
        return OffsiteBackupTargets(
            automatic_prefix=self._automatic_backup_prefix(),
            automatic_object_key=self._current_automatic_object_key(),
            manual_prefix_root=self._manual_backup_prefix_root(),
            manual_object_key=self._default_manual_object_key(settings.manual_prefix),
        )

    def _local_database_needs_restore(self) -> tuple[bool, str]:
        db_path = self.repo.db_path
        if not db_path.exists():
            return True, "The local database file is missing."
        if db_path.stat().st_size <= 0:
            return True, "The local database file is empty."

        try:
            conn = sqlite3.connect(db_path)
            try:
                quick_check = conn.execute("PRAGMA quick_check").fetchone()
                if not quick_check or quick_check[0] != "ok":
                    return True, "The local database failed the SQLite integrity check."
                table_count_row = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                ).fetchone()
                table_count = int(table_count_row[0]) if table_count_row else 0
                if table_count <= 0:
                    return True, "The local database does not contain any tables."
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return True, "The local database could not be opened as a valid SQLite file."

        return False, "The local database is present and healthy."

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

    def _record_restore_success(self, *, attempted_at: str, object_key: str) -> None:
        self._write_backup_status_setting(BACKUP_STATUS_LAST_RESTORE_AT_KEY, attempted_at)
        self._write_backup_status_setting(BACKUP_STATUS_LAST_RESTORE_OBJECT_KEY, object_key)

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

    def _list_object_entries(self, client, *, prefix: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=str(self.config.backup_s3_bucket),
            Prefix=prefix,
        ):
            for item in page.get("Contents", []):
                object_key = str(item.get("Key") or "").strip()
                size_bytes = int(item.get("Size", 0) or 0)
                if not object_key or size_bytes <= 0:
                    continue
                entries.append(
                    {
                        "Key": object_key,
                        "Size": size_bytes,
                        "LastModified": item.get("LastModified"),
                    }
                )
        entries.sort(
            key=lambda item: (
                item.get("LastModified") is not None,
                item.get("LastModified") or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return entries

    def _delete_object_entries(self, client, *, entries: list[dict[str, Any]], keep_keys: set[str]) -> None:
        keys_to_delete = [
            {"Key": str(entry["Key"])}
            for entry in entries
            if str(entry["Key"]) not in keep_keys
        ]
        for start in range(0, len(keys_to_delete), 1000):
            batch = keys_to_delete[start : start + 1000]
            if not batch:
                continue
            response = client.delete_objects(
                Bucket=str(self.config.backup_s3_bucket),
                Delete={"Objects": batch, "Quiet": True},
            )
            errors = response.get("Errors", []) if isinstance(response, dict) else []
            if errors:
                first_error = errors[0]
                raise RuntimeError(
                    f"Could not delete old off-site backup `{first_error.get('Key', 'unknown')}`: "
                    f"{first_error.get('Message', 'Unknown error.')}"
                )

    def _find_latest_offsite_backup_object_key(self, client) -> Optional[str]:
        latest_key: Optional[str] = None
        latest_modified = None
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=str(self.config.backup_s3_bucket),
            Prefix=self._automatic_backup_prefix(),
        ):
            for item in page.get("Contents", []):
                object_key = item.get("Key")
                if not object_key or int(item.get("Size", 0) or 0) <= 0:
                    continue
                last_modified = item.get("LastModified")
                if latest_modified is None or (last_modified is not None and last_modified > latest_modified):
                    latest_modified = last_modified
                    latest_key = str(object_key)
        return latest_key

    def _should_run_automatic_backup(self, *, attempted_at: str, settings: BackupSettings) -> bool:
        if settings.auto_interval_minutes <= 0:
            return True
        last_success_at = self.repo.get_app_setting(BACKUP_STATUS_LAST_SUCCESS_AT_KEY)
        last_success_dt = self._parse_iso_datetime(last_success_at)
        attempted_dt = self._parse_iso_datetime(attempted_at)
        if last_success_dt is None or attempted_dt is None:
            return True
        return attempted_dt >= (last_success_dt + timedelta(minutes=settings.auto_interval_minutes))

    def _upload_backup_object(self, client, *, object_key: str, attempted_at: str, backup_bytes: bytes) -> None:
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

    def restore_latest_offsite_snapshot_if_needed(self) -> OffsiteRestoreResult:
        if not self.config.backup_auto_restore_on_startup:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=None,
                message="Automatic off-site restore on startup is disabled.",
            )

        needs_restore, reason = self._local_database_needs_restore()
        if not needs_restore:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=None,
                message=reason,
            )

        if not self._is_offsite_configured():
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=None,
                message=f"{reason} Off-site backup is not configured, so the app will start with a fresh local database.",
            )

        if boto3 is None or BotoConfig is None:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=True,
                object_key=None,
                message=(
                    f"{reason} Automatic off-site restore is configured, but the `boto3` dependency is missing, "
                    "so the latest backup cannot be downloaded."
                ),
            )

        try:
            client = self._build_s3_client()
            object_key = self._find_latest_offsite_backup_object_key(client)
        except Exception as exc:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=True,
                object_key=None,
                message=f"{reason} The app could not list off-site backups: {str(exc) or 'Unknown error.'}",
            )

        if not object_key:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=None,
                message=f"{reason} No off-site backup objects were found yet, so the app will start fresh.",
            )

        try:
            response = client.get_object(
                Bucket=str(self.config.backup_s3_bucket),
                Key=object_key,
            )
            backup_bytes = response["Body"].read()
            if not backup_bytes:
                raise RuntimeError("The downloaded off-site backup object was empty.")
            self.repo.import_database_bytes(backup_bytes)
            self._record_restore_success(
                attempted_at=utc_now_iso(),
                object_key=object_key,
            )
        except Exception as exc:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=True,
                object_key=object_key,
                message=(
                    f"{reason} The latest off-site backup `{object_key}` could not be restored: "
                    f"{str(exc) or 'Unknown error.'}"
                ),
            )

        return OffsiteRestoreResult(
            restored=True,
            blocking_failure=False,
            object_key=object_key,
            message=f"Local database restored automatically from off-site backup `{object_key}`.",
        )

    def restore_offsite_object(self, object_key: str) -> OffsiteRestoreResult:
        selected_key = object_key.strip()
        configured_prefix = self.config.backup_s3_prefix.strip("/")
        allowed_prefix = f"{configured_prefix}/" if configured_prefix else ""
        if not selected_key:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=None,
                message="Select an off-site backup file first.",
            )
        if allowed_prefix and not selected_key.startswith(allowed_prefix):
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=selected_key,
                message="The selected off-site object is outside the configured backup prefix.",
            )
        if not self._is_offsite_configured():
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=selected_key,
                message="Off-site backup is not configured yet.",
            )
        if boto3 is None or BotoConfig is None:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=selected_key,
                message="Off-site backup is configured, but the `boto3` dependency is missing.",
            )

        attempted_at = utc_now_iso()
        try:
            client = self._build_s3_client()
            response = client.get_object(
                Bucket=str(self.config.backup_s3_bucket),
                Key=selected_key,
            )
            backup_bytes = response["Body"].read()
            if not backup_bytes:
                raise RuntimeError("The selected off-site backup object was empty.")
            self.repo.import_database_bytes(backup_bytes)
            self._record_restore_success(attempted_at=attempted_at, object_key=selected_key)
        except Exception as exc:
            return OffsiteRestoreResult(
                restored=False,
                blocking_failure=False,
                object_key=selected_key,
                message=f"The selected off-site backup `{selected_key}` could not be restored: {str(exc) or 'Unknown error.'}",
            )

        return OffsiteRestoreResult(
            restored=True,
            blocking_failure=False,
            object_key=selected_key,
            message=f"Local database restored from off-site backup `{selected_key}`.",
        )

    def list_offsite_backup_objects(self) -> list[OffsiteBackupObject]:
        if not self._is_offsite_configured() or boto3 is None or BotoConfig is None:
            return []

        client = self._build_s3_client()
        automatic_prefix = self._automatic_backup_prefix()
        manual_prefix = self._manual_backup_prefix_root()
        configured_prefix = self.config.backup_s3_prefix.strip("/")
        list_prefix = f"{configured_prefix}/" if configured_prefix else ""
        objects: list[OffsiteBackupObject] = []
        for entry in self._list_object_entries(client, prefix=list_prefix):
            object_key = str(entry["Key"])
            if object_key.startswith(automatic_prefix):
                category = "automatic"
            elif object_key.startswith(manual_prefix):
                category = "manual"
            else:
                category = "other"
            objects.append(
                OffsiteBackupObject(
                    object_key=object_key,
                    category=category,
                    size_bytes=int(entry["Size"]),
                    last_modified_at=self._format_datetime(entry.get("LastModified")),
                )
            )
        return objects

    def _upload_offsite_snapshot(
        self,
        *,
        reason: str,
        include_manual_slot: bool = False,
        honor_interval: bool = False,
    ) -> OffsiteBackupResult:
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

        settings = self.get_backup_settings()
        automatic_target_key = self._current_automatic_object_key()
        manual_target_key = self._default_manual_object_key(settings.manual_prefix)
        if honor_interval and not self._should_run_automatic_backup(attempted_at=attempted_at, settings=settings):
            interval_label = (
                "every committed write"
                if settings.auto_interval_minutes <= 0
                else f"at most once every {settings.auto_interval_minutes} minute(s)"
            )
            return OffsiteBackupResult(
                success=True,
                attempted=False,
                object_key=automatic_target_key,
                message=f"Skipped automatic off-site backup because it is configured to run {interval_label}.",
            )

        self._update_last_attempt(attempted_at)
        automatic_uploaded = False
        try:
            backup_bytes = self.repo.export_database_bytes()
            if not backup_bytes:
                raise RuntimeError("The local database file is empty.")

            client = self._build_s3_client()
            automatic_entries = self._list_object_entries(client, prefix=self._automatic_backup_prefix())
            automatic_keys = {str(entry["Key"]) for entry in automatic_entries}
            if automatic_target_key not in automatic_keys and automatic_entries:
                automatic_target_key = str(automatic_entries[0]["Key"])
            self._delete_object_entries(client, entries=automatic_entries, keep_keys={automatic_target_key})
            self._upload_backup_object(
                client,
                object_key=automatic_target_key,
                attempted_at=attempted_at,
                backup_bytes=backup_bytes,
            )
            automatic_uploaded = True

            result_message = f"Off-site backup uploaded to automatic restore target {automatic_target_key}."
            if include_manual_slot:
                manual_entries = self._list_object_entries(client, prefix=self._manual_backup_prefix_root())
                manual_keys = {str(entry["Key"]) for entry in manual_entries}
                if manual_target_key in manual_keys:
                    self._delete_object_entries(client, entries=manual_entries, keep_keys={manual_target_key})
                else:
                    self._delete_object_entries(client, entries=manual_entries, keep_keys=set())
                self._upload_backup_object(
                    client,
                    object_key=manual_target_key,
                    attempted_at=attempted_at,
                    backup_bytes=backup_bytes,
                )
                result_message = (
                    "Off-site backup uploaded to automatic restore target "
                    f"{automatic_target_key} and manual target {manual_target_key}."
                )
        except Exception as exc:
            message = str(exc) or "Unknown upload error."
            if automatic_uploaded and include_manual_slot:
                message = (
                    f"Automatic restore target {automatic_target_key} was updated, "
                    f"but the manual backup target {manual_target_key} failed: {message}"
                )
            self._record_sync_failure(attempted_at=attempted_at, message=message)
            return OffsiteBackupResult(
                success=False,
                attempted=True,
                object_key=None,
                message=message,
            )

        self._record_sync_success(attempted_at=attempted_at, object_key=automatic_target_key)
        return OffsiteBackupResult(
            success=True,
            attempted=True,
            object_key=automatic_target_key,
            message=result_message,
        )

    def _sync_after_write(self) -> None:
        self._upload_offsite_snapshot(reason="auto", honor_interval=True)

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
        return self._upload_offsite_snapshot(reason="manual", include_manual_slot=True)

    def get_offsite_backup_status(self) -> OffsiteBackupStatus:
        configured = self._is_offsite_configured()
        dependency_available = boto3 is not None and BotoConfig is not None
        enabled = configured and dependency_available
        settings = self.get_backup_settings()
        last_success_at = self.repo.get_app_setting(BACKUP_STATUS_LAST_SUCCESS_AT_KEY) or None
        last_object_key = self.repo.get_app_setting(BACKUP_STATUS_LAST_OBJECT_KEY) or None
        last_error_at = self.repo.get_app_setting(BACKUP_STATUS_LAST_ERROR_AT_KEY) or None
        last_error_message = self.repo.get_app_setting(BACKUP_STATUS_LAST_ERROR_MESSAGE_KEY) or None
        last_attempt_at = self.repo.get_app_setting(BACKUP_STATUS_LAST_ATTEMPT_AT_KEY) or None
        last_restore_at = self.repo.get_app_setting(BACKUP_STATUS_LAST_RESTORE_AT_KEY) or None
        last_restore_object_key = self.repo.get_app_setting(BACKUP_STATUS_LAST_RESTORE_OBJECT_KEY) or None

        cadence_text = (
            "after every committed tournament-data write"
            if settings.auto_interval_minutes <= 0
            else f"at most once every {settings.auto_interval_minutes} minute(s) after committed tournament-data writes"
        )
        if enabled:
            status_label = "Connected"
            if self.config.backup_auto_restore_on_startup:
                detail_message = (
                    "Automatic off-site backups are enabled. The app refreshes one automatic snapshot "
                    f"{cadence_text}, and a manual backup refreshes both the automatic restore target and one "
                    "separate manual snapshot. If the local database is missing or broken on startup, the newest "
                    "automatic off-site snapshot is restored automatically before the app boots."
                )
            else:
                detail_message = (
                    "Automatic off-site backups are enabled. The app refreshes one automatic snapshot "
                    f"{cadence_text}, and a manual backup refreshes both the automatic restore target and one "
                    "separate manual snapshot. Startup auto-restore is currently disabled."
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
            last_restore_at=last_restore_at,
            last_restore_object_key=last_restore_object_key,
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
                'BACKUP_AUTO_RESTORE_ON_STARTUP = "true"',
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
