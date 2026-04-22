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
from tournament_tracker.services.betting_service import BettingService
from tournament_tracker.services.invitation_service import InvitationService
from tournament_tracker.services.match_service import MatchService
from tournament_tracker.services.minigame_service import MiniGameService
from tournament_tracker.services.profile_service import ProfileService
from tournament_tracker.services.ranked_event_service import RankedEventService
from tournament_tracker.services.registration_service import RegistrationService
from tournament_tracker.services.ranking_service import RankingService
from tournament_tracker.services.special_service import SpecialService


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
    ranked_event_service: RankedEventService
    registration_service: RegistrationService
    minigame_service: MiniGameService
    special_service: SpecialService
    betting_service: BettingService


def _ranking_service_has_expected_capabilities(service: object) -> bool:
    return all(
        hasattr(service, attribute)
        for attribute in (
            "build_point_ledger_map",
            "list_point_activity_rows",
            "award_manual_adjustment",
            "compute_leaderboard",
        )
    )


def _services_have_expected_capabilities(services: object) -> bool:
    auth_service = getattr(services, "auth_service", None)
    ranking_service = getattr(services, "ranking_service", None)
    return bool(
        hasattr(getattr(services, "config", object()), "persistent_login_days")
        and hasattr(services, "minigame_service")
        and hasattr(services, "special_service")
        and hasattr(services, "betting_service")
        and hasattr(services, "ranked_event_service")
        and auth_service is not None
        and hasattr(auth_service, "create_persistent_session")
        and hasattr(auth_service, "restore_persistent_session")
        and ranking_service is not None
        and _ranking_service_has_expected_capabilities(ranking_service)
    )


def initialize_repository(config: AppConfig | None = None) -> tuple[AppConfig, SQLiteRepository]:
    cfg = config or get_config()
    repo = SQLiteRepository(cfg.db_path)
    repo.apply_migrations()
    auth_service = AuthService(repo, persistent_login_days=cfg.persistent_login_days)

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

    ranking_service = RankingService(repo)
    special_service = SpecialService(repo, ranking_service)
    betting_service = BettingService(repo, ranking_service, special_service)
    match_service = MatchService(repo, special_service=special_service)
    ranked_event_service = RankedEventService(repo)
    special_service.recalculate_match_competition_state()

    return AppServices(
        config=config,
        repo=repo,
        auth_service=AuthService(repo, persistent_login_days=config.persistent_login_days),
        backup_service=BackupService(repo),
        invitation_service=InvitationService(repo),
        match_service=match_service,
        ranking_service=ranking_service,
        profile_service=ProfileService(repo),
        ranked_event_service=ranked_event_service,
        registration_service=RegistrationService(repo, config),
        minigame_service=MiniGameService(repo),
        special_service=special_service,
        betting_service=betting_service,
    )


def _rebuild_services_from_existing(services: object) -> AppServices:
    config = getattr(services, "config")
    repo = getattr(services, "repo")
    persistent_login_days = getattr(config, "persistent_login_days", 30)
    existing_ranking_service = getattr(services, "ranking_service", None)
    ranking_service = (
        existing_ranking_service
        if existing_ranking_service is not None and _ranking_service_has_expected_capabilities(existing_ranking_service)
        else RankingService(repo)
    )
    existing_special_service = getattr(services, "special_service", None)
    if (
        existing_special_service is None
        or getattr(existing_special_service, "ranking_service", None) is not ranking_service
    ):
        special_service = SpecialService(repo, ranking_service)
    else:
        special_service = existing_special_service
    betting_service = BettingService(repo, ranking_service, special_service)
    auth_service = getattr(services, "auth_service", None)
    if (
        auth_service is None
        or not hasattr(auth_service, "create_persistent_session")
        or not hasattr(auth_service, "restore_persistent_session")
    ):
        auth_service = AuthService(repo, persistent_login_days=persistent_login_days)
    match_service = getattr(services, "match_service", MatchService(repo))
    if getattr(match_service, "special_service", None) is None:
        match_service = MatchService(repo, special_service=special_service)
    special_service.recalculate_match_competition_state()
    return AppServices(
        config=config,
        repo=repo,
        auth_service=auth_service,
        backup_service=getattr(services, "backup_service", BackupService(repo)),
        invitation_service=getattr(services, "invitation_service", InvitationService(repo)),
        match_service=match_service,
        ranking_service=ranking_service,
        profile_service=getattr(services, "profile_service", ProfileService(repo)),
        ranked_event_service=getattr(services, "ranked_event_service", RankedEventService(repo)),
        registration_service=getattr(services, "registration_service", RegistrationService(repo, config)),
        minigame_service=MiniGameService(repo),
        special_service=special_service,
        betting_service=betting_service,
    )


def get_runtime_services() -> AppServices:
    services = get_services()
    if _services_have_expected_capabilities(services):
        return services

    clear_cached = getattr(get_services, "clear", None)
    if callable(clear_cached):
        clear_cached()
        refreshed = get_services()
        if _services_have_expected_capabilities(refreshed):
            return refreshed

    return _rebuild_services_from_existing(services)
