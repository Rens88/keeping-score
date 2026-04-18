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
    db_path: Path
    app_base_url: str
    default_invite_expiry_hours: int

    seed_admin_username: str
    seed_admin_email: str
    seed_admin_password: str



def get_config() -> AppConfig:
    db_path_raw = _get_setting("DB_PATH", "demo_state/weekend_tracker_requested_demo_state.sqlite3")
    default_invite_expiry = int(_get_setting("DEFAULT_INVITE_EXPIRY_HOURS", "72") or "72")

    return AppConfig(
        db_path=Path(db_path_raw or "demo_state/weekend_tracker_requested_demo_state.sqlite3"),
        app_base_url=(_get_setting("APP_BASE_URL", "") or "").rstrip("/"),
        default_invite_expiry_hours=default_invite_expiry,
        seed_admin_username=_get_setting("SEED_ADMIN_USERNAME", "admin") or "admin",
        seed_admin_email=_get_setting("SEED_ADMIN_EMAIL", "admin@example.com") or "admin@example.com",
        seed_admin_password=_get_setting("SEED_ADMIN_PASSWORD", "change-me-now") or "change-me-now",
    )
