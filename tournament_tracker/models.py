from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


Role = str
MatchStatus = str
MatchOutcome = str


@dataclass(slots=True)
class User:
    id: int
    username: Optional[str]
    email: Optional[str]
    password_hash: str
    role: Role
    is_active: bool
    created_at: str
    updated_at: str
    account_origin: str = "legacy"
    registration_questions_answered: int = 0
    registration_game_guesses_used: int = 0
    registration_game_completed: bool = False
    registration_game_incorrect_answers: int = 0
    registration_game_points: float = 0.0
    registration_game_completed_at: Optional[str] = None


@dataclass(slots=True)
class ParticipantProfile:
    user_id: int
    display_name: str
    motto: str
    photo_blob: Optional[bytes]
    photo_mime_type: Optional[str]
    created_at: str
    updated_at: str


@dataclass(slots=True)
class Invitation:
    id: int
    token_hash: str
    created_by_user_id: int
    created_at: str
    expires_at: str
    used_at: Optional[str]
    used_by_user_id: Optional[int]
    note: Optional[str]


@dataclass(slots=True)
class Match:
    id: int
    game_type: str
    scheduled_at: Optional[str]
    scheduled_order: Optional[int]
    status: MatchStatus
    created_by_user_id: int
    created_at: str
    updated_at: str


@dataclass(slots=True)
class MatchSide:
    id: int
    match_id: int
    side_number: int
    side_name: Optional[str]


@dataclass(slots=True)
class MatchParticipant:
    id: int
    match_side_id: int
    participant_user_id: int


@dataclass(slots=True)
class MatchResult:
    id: int
    match_id: int
    outcome: MatchOutcome
    entered_by_user_id: int
    entered_at: str
    notes: Optional[str]


@dataclass(slots=True)
class DoublerActivation:
    id: int
    participant_user_id: int
    match_id: int
    activated_at: str
    activated_by_user_id: int


@dataclass(slots=True)
class MatchParticipantView:
    user_id: int
    display_name: str
    motto: str
    photo_blob: Optional[bytes]
    photo_mime_type: Optional[str]
    side_number: int
    has_doubler_on_match: bool


@dataclass(slots=True)
class MatchView:
    match_id: int
    game_type: str
    scheduled_at: Optional[str]
    scheduled_order: Optional[int]
    status: MatchStatus
    outcome: Optional[MatchOutcome]
    result_notes: Optional[str]


@dataclass(slots=True)
class LeaderboardRow:
    rank: int
    user_id: int
    display_name: str
    motto: str
    photo_blob: Optional[bytes]
    photo_mime_type: Optional[str]
    bonus_points: float
    total_points: float
    matches_played: int
    wins: int
    draws: int
    losses: int
    doubler_used: bool


@dataclass(slots=True)
class UserWithProfile:
    user_id: int
    username: Optional[str]
    email: Optional[str]
    role: str
    is_active: bool
    display_name: Optional[str]
    motto: Optional[str]
    photo_blob: Optional[bytes]
    photo_mime_type: Optional[str]
    account_origin: str = "legacy"
    registration_questions_answered: int = 0
    registration_game_guesses_used: int = 0
    registration_game_completed: bool = False
    registration_game_incorrect_answers: int = 0
    registration_game_points: float = 0.0
    registration_game_completed_at: Optional[str] = None


@dataclass(slots=True)
class InvitationDisplay:
    id: int
    created_at: str
    expires_at: str
    used_at: Optional[str]
    note: Optional[str]
    created_by_name: Optional[str]


@dataclass(slots=True)
class ActivityItem:
    timestamp: str
    message: str


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
