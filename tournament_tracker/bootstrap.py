from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from tournament_tracker.config import AppConfig, get_config
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.services.auth_service import AuthService
from tournament_tracker.services.backup_service import BackupService
from tournament_tracker.services.invitation_service import InvitationService
from tournament_tracker.services.match_service import MatchService
from tournament_tracker.services.profile_service import ProfileService
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


def initialize_repository(config: AppConfig | None = None) -> tuple[AppConfig, SQLiteRepository]:
    cfg = config or get_config()
    repo = SQLiteRepository(cfg.db_path)
    repo.apply_migrations()
    AuthService(repo).ensure_seed_admin(
        username=cfg.seed_admin_username,
        email=cfg.seed_admin_email,
        password=cfg.seed_admin_password,
    )
    return cfg, repo


@st.cache_resource(show_spinner=False)
def get_services() -> AppServices:
    config, repo = initialize_repository()
    return AppServices(
        config=config,
        repo=repo,
        auth_service=AuthService(repo),
        backup_service=BackupService(repo),
        invitation_service=InvitationService(repo),
        match_service=MatchService(repo),
        ranking_service=RankingService(repo),
        profile_service=ProfileService(repo),
    )
