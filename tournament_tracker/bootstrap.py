from __future__ import annotations

from dataclasses import dataclass

try:
    import streamlit as st
except ModuleNotFoundError:
    class _NoStreamlit:
        @staticmethod
        def cache_resource(*_args: object, **_kwargs: object):
            def decorator(func):
                return func

            return decorator

    st = _NoStreamlit()  # type: ignore[assignment]

from tournament_tracker.config import AppConfig, get_config
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.auth_service import AuthService
from tournament_tracker.services.backup_service import BackupService
from tournament_tracker.services.invitation_service import InvitationService
from tournament_tracker.services.match_service import MatchService
from tournament_tracker.services.minigame_service import MiniGameService
from tournament_tracker.services.profile_service import ProfileService
from tournament_tracker.services.registration_service import RegistrationService
from tournament_tracker.services.ranking_service import RankingService


@dataclass(slots=True)
class AppServices:
    config: AppConfig
    repo: SQLiteRepository
    auth_service: AuthService
    backup_service: BackupService
    invitation_service: InvitationService
    match_service: MatchService
    ranking_service: RankingService
    profile_service: ProfileService
    registration_service: RegistrationService
    minigame_service: MiniGameService


def initialize_repository(config: AppConfig | None = None) -> tuple[AppConfig, SQLiteRepository]:
    cfg = config or get_config()
    repo = SQLiteRepository(cfg.db_path)
    repo.apply_migrations()
    auth_service = AuthService(repo)

    seed_values = (
        cfg.seed_admin_username,
        cfg.seed_admin_email,
        cfg.seed_admin_password,
    )
    has_any_seed_value = any(seed_values)
    has_all_seed_values = all(seed_values)

    if has_any_seed_value and not has_all_seed_values:
        raise RuntimeError(
            "Incomplete admin bootstrap configuration. "
            "Provide SEED_ADMIN_USERNAME, SEED_ADMIN_EMAIL, and SEED_ADMIN_PASSWORD together."
        )

    if has_all_seed_values:
        auth_service.ensure_seed_admin(
            username=cfg.seed_admin_username or "",
            email=cfg.seed_admin_email or "",
            password=cfg.seed_admin_password or "",
        )
    elif not repo.any_admin_exists():
        raise RuntimeError(
            "No admin account found. Configure SEED_ADMIN_USERNAME, SEED_ADMIN_EMAIL, "
            "and SEED_ADMIN_PASSWORD via environment variables or Streamlit secrets for first startup."
        )

    return cfg, repo


@st.cache_resource(show_spinner=False)
def get_services() -> AppServices:
    try:
        config, repo = initialize_repository()
    except RuntimeError as exc:
        if hasattr(st, "error") and hasattr(st, "stop"):
            st.error(str(exc))
            st.stop()
        raise

    return AppServices(
        config=config,
        repo=repo,
        auth_service=AuthService(repo),
        backup_service=BackupService(repo),
        invitation_service=InvitationService(repo),
        match_service=MatchService(repo),
        ranking_service=RankingService(repo),
        profile_service=ProfileService(repo),
        registration_service=RegistrationService(repo, config),
        minigame_service=MiniGameService(repo),
    )


def _rebuild_services_from_existing(services: object) -> AppServices:
    config = getattr(services, "config")
    repo = getattr(services, "repo")
    return AppServices(
        config=config,
        repo=repo,
        auth_service=getattr(services, "auth_service", AuthService(repo)),
        backup_service=getattr(services, "backup_service", BackupService(repo)),
        invitation_service=getattr(services, "invitation_service", InvitationService(repo)),
        match_service=getattr(services, "match_service", MatchService(repo)),
        ranking_service=getattr(services, "ranking_service", RankingService(repo)),
        profile_service=getattr(services, "profile_service", ProfileService(repo)),
        registration_service=getattr(services, "registration_service", RegistrationService(repo, config)),
        minigame_service=MiniGameService(repo),
    )


def get_runtime_services() -> AppServices:
    services = get_services()
    if hasattr(services, "minigame_service"):
        return services

    clear_cached = getattr(get_services, "clear", None)
    if callable(clear_cached):
        clear_cached()
        refreshed = get_services()
        if hasattr(refreshed, "minigame_service"):
            return refreshed

    return _rebuild_services_from_existing(services)
