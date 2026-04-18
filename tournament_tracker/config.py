from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any, Optional


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
    default_invite_expiry_hours: int
    photo_storage_mode: str
    photo_upload_path: Optional[Path]

    seed_admin_username: Optional[str]
    seed_admin_email: Optional[str]
    seed_admin_password: Optional[str]


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


def get_config() -> AppConfig:
    app_env = _normalize_app_env(_get_setting("APP_ENV", "local"))
    db_path_raw = _get_setting("DB_PATH", _default_db_path_for_env(app_env))
    default_invite_expiry = _safe_int(_get_setting("DEFAULT_INVITE_EXPIRY_HOURS", "72"), 72)

    photo_storage_mode = (_get_setting("PHOTO_STORAGE_MODE", "db_blob") or "db_blob").strip().lower()
    if photo_storage_mode not in {"db_blob", "filesystem"}:
        photo_storage_mode = "db_blob"
    default_photo_upload_path = "data/uploads" if photo_storage_mode == "filesystem" else ""
    photo_upload_path_raw = (_get_setting("PHOTO_UPLOAD_PATH", default_photo_upload_path) or "").strip()

    seed_admin_username = (_get_setting("SEED_ADMIN_USERNAME", None) or "").strip() or None
    seed_admin_email = (_get_setting("SEED_ADMIN_EMAIL", None) or "").strip().lower() or None
    seed_admin_password = (_get_setting("SEED_ADMIN_PASSWORD", None) or "").strip() or None

    return AppConfig(
        app_env=app_env,
        db_path=Path(db_path_raw or _default_db_path_for_env(app_env)),
        app_base_url=(_get_setting("APP_BASE_URL", "") or "").rstrip("/"),
        default_invite_expiry_hours=default_invite_expiry,
        photo_storage_mode=photo_storage_mode,
        photo_upload_path=Path(photo_upload_path_raw) if photo_upload_path_raw else None,
        seed_admin_username=seed_admin_username,
        seed_admin_email=seed_admin_email,
        seed_admin_password=seed_admin_password,
    )
