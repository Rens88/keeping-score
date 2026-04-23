from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any, Optional

DEFAULT_PUBLIC_APP_BASE_URL = "https://keeping-score-teamweekend-2025-2026.streamlit.app/"
IGNORED_APP_BASE_URL_PLACEHOLDERS = frozenset(
    {
        "https://your-app-name.streamlit.app",
        "https://your-app-name.streamlit.app/",
        "your-app-name.streamlit.app",
    }
)


def _read_streamlit_secret(key: str) -> Optional[str]:
    """Read a key from Streamlit secrets when running inside Streamlit."""
    try:
        import streamlit as st

        if key in st.secrets:
            value: Any = st.secrets[key]
            if value is None:
                return None
            return str(value)
    except Exception:
        return None
    return None


def _get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    env_value = os.getenv(key)
    if env_value is not None and env_value != "":
        return env_value

    secret_value = _read_streamlit_secret(key)
    if secret_value is not None and secret_value != "":
        return secret_value

    return default


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    db_path: Path
    app_base_url: str
    app_base_url_is_fallback: bool
    persistent_login_days: int
    default_invite_expiry_hours: int
    photo_storage_mode: str
    photo_upload_path: Optional[Path]

    seed_admin_username: Optional[str]
    seed_admin_email: Optional[str]
    seed_admin_password: Optional[str]
    backup_s3_endpoint: Optional[str]
    backup_s3_bucket: Optional[str]
    backup_s3_region: Optional[str]
    backup_s3_access_key_id: Optional[str]
    backup_s3_secret_access_key: Optional[str]
    backup_s3_prefix: str


def _normalize_app_env(value: Optional[str]) -> str:
    env = (value or "local").strip().lower()
    if env not in {"local", "cloud"}:
        return "local"
    return env


def _default_db_path_for_env(app_env: str) -> str:
    if app_env == "cloud":
        return "data/tournament_cloud.sqlite3"
    return "demo_state/weekend_tracker_requested_demo_state.sqlite3"


def _safe_int(value: Optional[str], fallback: int) -> int:
    try:
        return int(value or str(fallback))
    except Exception:
        return fallback


def _sanitize_app_base_url(value: Optional[str]) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""
    if candidate.lower() in IGNORED_APP_BASE_URL_PLACEHOLDERS:
        return ""
    return candidate.rstrip("/")


def get_config() -> AppConfig:
    app_env = _normalize_app_env(_get_setting("APP_ENV", "local"))
    db_path_raw = _get_setting("DB_PATH", _default_db_path_for_env(app_env))
    default_invite_expiry = _safe_int(_get_setting("DEFAULT_INVITE_EXPIRY_HOURS", "72"), 72)
    persistent_login_days = max(1, _safe_int(_get_setting("PERSISTENT_LOGIN_DAYS", "30"), 30))

    photo_storage_mode = (_get_setting("PHOTO_STORAGE_MODE", "db_blob") or "db_blob").strip().lower()
    if photo_storage_mode not in {"db_blob", "filesystem"}:
        photo_storage_mode = "db_blob"
    default_photo_upload_path = "data/uploads" if photo_storage_mode == "filesystem" else ""
    photo_upload_path_raw = (_get_setting("PHOTO_UPLOAD_PATH", default_photo_upload_path) or "").strip()

    seed_admin_username = (_get_setting("SEED_ADMIN_USERNAME", None) or "").strip() or None
    seed_admin_email = (_get_setting("SEED_ADMIN_EMAIL", None) or "").strip().lower() or None
    seed_admin_password = (_get_setting("SEED_ADMIN_PASSWORD", None) or "").strip() or None
    backup_s3_endpoint = (_get_setting("BACKUP_S3_ENDPOINT", None) or "").strip() or None
    backup_s3_bucket = (_get_setting("BACKUP_S3_BUCKET", None) or "").strip() or None
    backup_s3_region = (_get_setting("BACKUP_S3_REGION", None) or "").strip() or None
    backup_s3_access_key_id = (_get_setting("BACKUP_S3_ACCESS_KEY_ID", None) or "").strip() or None
    backup_s3_secret_access_key = (_get_setting("BACKUP_S3_SECRET_ACCESS_KEY", None) or "").strip() or None
    backup_s3_prefix = (_get_setting("BACKUP_S3_PREFIX", "keeping-score") or "keeping-score").strip().strip("/")
    configured_app_base_url = _sanitize_app_base_url(_get_setting("APP_BASE_URL", None))
    app_base_url_is_fallback = not bool(configured_app_base_url)
    app_base_url = (configured_app_base_url or DEFAULT_PUBLIC_APP_BASE_URL).rstrip("/")

    return AppConfig(
        app_env=app_env,
        db_path=Path(db_path_raw or _default_db_path_for_env(app_env)),
        app_base_url=app_base_url,
        app_base_url_is_fallback=app_base_url_is_fallback,
        persistent_login_days=persistent_login_days,
        default_invite_expiry_hours=default_invite_expiry,
        photo_storage_mode=photo_storage_mode,
        photo_upload_path=Path(photo_upload_path_raw) if photo_upload_path_raw else None,
        seed_admin_username=seed_admin_username,
        seed_admin_email=seed_admin_email,
        seed_admin_password=seed_admin_password,
        backup_s3_endpoint=backup_s3_endpoint,
        backup_s3_bucket=backup_s3_bucket,
        backup_s3_region=backup_s3_region,
        backup_s3_access_key_id=backup_s3_access_key_id,
        backup_s3_secret_access_key=backup_s3_secret_access_key,
        backup_s3_prefix=backup_s3_prefix,
    )
