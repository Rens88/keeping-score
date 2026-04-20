from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Iterable, Iterator, Optional

from tournament_tracker.models import (
    ActivityItem,
    CompetitionPointAward,
    DoublerActivation,
    Invitation,
    InvitationDisplay,
    Match,
    MatchBet,
    MatchResult,
    MatchSpecialActivation,
    MiniGameAward,
    MiniGameRun,
    ParticipantProfile,
    ParticipantSpecial,
    User,
    UserWithProfile,
)

REGISTRATION_GAME_SOURCE_TYPE = "registration_game"
REGISTRATION_GAME_SOURCE_KEY = "registration_game"
COMPETITION_RANKING_SOURCE_TYPE = "competition_ranking"
MATCH_PERFORMANCE_ADJUSTMENT_SOURCE_TYPE = "match_performance_adjustment"
BETTING_SOURCE_TYPE = "betting"
DOUBLE_OR_NOTHING_BONUS_SOURCE_TYPE = "double_or_nothing_bonus"


class SQLiteRepository:
    REQUIRED_BACKUP_TABLES = {
        "users",
        "participant_profiles",
        "invitations",
        "matches",
        "match_sides",
        "match_participants",
        "match_results",
        "doubler_activations",
        "activity_log",
    }

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._table_columns_cache: dict[str, set[str]] = {}

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def apply_migrations(self) -> None:
        migrations_dir = Path(__file__).parent / "migrations"
        migration_files = sorted(migrations_dir.glob("*.sql"))

        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )

            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }

            for migration_file in migration_files:
                version = migration_file.name
                if version in applied:
                    continue
                sql = migration_file.read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)",
                    (version,),
                )

            self._ensure_registration_schema(conn)

        self._table_columns_cache.clear()

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_registration_schema(self, conn: sqlite3.Connection) -> None:
        user_columns = self._table_columns(conn, "users")
        registration_user_columns = (
            ("account_origin", "TEXT NOT NULL DEFAULT 'legacy'"),
            ("registration_questions_answered", "INTEGER NOT NULL DEFAULT 0"),
            ("registration_game_guesses_used", "INTEGER NOT NULL DEFAULT 0"),
            ("registration_game_completed", "INTEGER NOT NULL DEFAULT 0"),
            ("registration_game_incorrect_answers", "INTEGER NOT NULL DEFAULT 0"),
            ("registration_game_points", "REAL NOT NULL DEFAULT 0"),
            ("registration_game_completed_at", "TEXT"),
        )

        for column_name, definition in registration_user_columns:
            if column_name not in user_columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column_name} {definition}")
                user_columns.add(column_name)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
            VALUES ('registration_game_active', 'false', datetime('now'))
            """
        )
        minigame_setting_defaults = (
            ("whack_a_mole_enabled", "false"),
            ("whack_a_mole_opens_at", ""),
            ("whack_a_mole_deadline_at", ""),
            ("whack_a_mole_award_scheme", "5,3,1"),
            ("whack_a_mole_awards_applied_at", ""),
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (?, ?, datetime('now'))
            """,
            minigame_setting_defaults,
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS minigame_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_slug TEXT NOT NULL,
                participant_user_id INTEGER NOT NULL,
                score INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL,
                played_at TEXT NOT NULL,
                metadata_json TEXT,
                FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS minigame_awards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_slug TEXT NOT NULL,
                participant_user_id INTEGER NOT NULL,
                placement INTEGER NOT NULL,
                points_awarded REAL NOT NULL,
                awarded_at TEXT NOT NULL,
                awarded_by_user_id INTEGER NOT NULL,
                FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (awarded_by_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS competition_point_awards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_user_id INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                source_key TEXT NOT NULL,
                source_label TEXT NOT NULL,
                placement INTEGER,
                points_awarded REAL NOT NULL,
                awarded_at TEXT NOT NULL,
                awarded_by_user_id INTEGER,
                UNIQUE(source_type, source_key, participant_user_id),
                FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (awarded_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS match_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                participant_user_id INTEGER NOT NULL,
                predicted_outcome TEXT NOT NULL CHECK (predicted_outcome IN ('side1_win', 'draw', 'side2_win')),
                stake_points REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                settled_at TEXT,
                net_points REAL,
                UNIQUE(match_id, participant_user_id),
                FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
                FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS participant_specials (
                participant_user_id INTEGER NOT NULL,
                special_key TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 0,
                granted_at TEXT,
                activated_at TEXT,
                resolved_at TEXT,
                payload_json TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (participant_user_id, special_key),
                FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS match_special_activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_user_id INTEGER NOT NULL,
                special_key TEXT NOT NULL,
                match_id INTEGER NOT NULL,
                activated_at TEXT NOT NULL,
                activated_by_user_id INTEGER NOT NULL,
                payload_json TEXT,
                FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
                FOREIGN KEY (activated_by_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            UPDATE users
            SET registration_game_completed = 1,
                registration_game_points = 0,
                account_origin = 'legacy'
            WHERE role = 'participant'
              AND account_origin = 'legacy'
              AND registration_game_completed = 0
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_registration_completed
            ON users(registration_game_completed)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_minigame_runs_lookup
            ON minigame_runs(game_slug, participant_user_id, score DESC, played_at ASC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_minigame_awards_lookup
            ON minigame_awards(game_slug, participant_user_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_competition_point_awards_source
            ON competition_point_awards(source_type, source_key, participant_user_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_match_bets_match
            ON match_bets(match_id, participant_user_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_match_bets_participant
            ON match_bets(participant_user_id, settled_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_participant_specials_key
            ON participant_specials(special_key, is_available, is_active)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_match_special_activations_lookup
            ON match_special_activations(match_id, special_key, participant_user_id)
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
            VALUES ('catch_up_points_gap_threshold', '15', datetime('now'))
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO participant_specials (
                participant_user_id,
                special_key,
                is_available,
                is_active,
                granted_at,
                activated_at,
                resolved_at,
                payload_json,
                updated_at
            )
            SELECT
                u.id,
                'doubler',
                1,
                0,
                u.created_at,
                NULL,
                NULL,
                NULL,
                COALESCE(u.updated_at, u.created_at, datetime('now'))
            FROM users u
            WHERE u.role = 'participant'
            """
        )
        conn.execute(
            """
            INSERT INTO match_special_activations (
                participant_user_id,
                special_key,
                match_id,
                activated_at,
                activated_by_user_id,
                payload_json
            )
            SELECT
                da.participant_user_id,
                'doubler',
                da.match_id,
                da.activated_at,
                da.activated_by_user_id,
                NULL
            FROM doubler_activations da
            WHERE NOT EXISTS (
                SELECT 1
                FROM match_special_activations msa
                WHERE msa.participant_user_id = da.participant_user_id
                  AND msa.special_key = 'doubler'
                  AND msa.match_id = da.match_id
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO competition_point_awards (
                participant_user_id,
                source_type,
                source_key,
                source_label,
                placement,
                points_awarded,
                awarded_at,
                awarded_by_user_id
            )
            SELECT
                u.id,
                ?,
                ?,
                'Registration Game',
                NULL,
                u.registration_game_points,
                COALESCE(u.registration_game_completed_at, u.updated_at, u.created_at),
                NULL
            FROM users u
            WHERE u.role = 'participant'
              AND u.registration_game_points > 0
            """,
            (REGISTRATION_GAME_SOURCE_TYPE, REGISTRATION_GAME_SOURCE_KEY),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO competition_point_awards (
                participant_user_id,
                source_type,
                source_key,
                source_label,
                placement,
                points_awarded,
                awarded_at,
                awarded_by_user_id
            )
            SELECT
                ma.participant_user_id,
                ?,
                ma.game_slug,
                REPLACE(ma.game_slug, '_', ' '),
                ma.placement,
                ma.points_awarded,
                ma.awarded_at,
                ma.awarded_by_user_id
            FROM minigame_awards ma
            """,
            (COMPETITION_RANKING_SOURCE_TYPE,),
        )

    def _get_table_columns_cached(self, table_name: str) -> set[str]:
        if table_name not in self._table_columns_cache:
            with self.connection() as conn:
                self._table_columns_cache[table_name] = self._table_columns(conn, table_name)
        return self._table_columns_cache[table_name]

    def _user_registration_projection(self, alias: str = "u") -> str:
        user_columns = self._get_table_columns_cached("users")
        default_completed = "1"
        projection_map = {
            "account_origin": f"{alias}.account_origin" if "account_origin" in user_columns else "'legacy'",
            "registration_questions_answered": (
                f"{alias}.registration_questions_answered"
                if "registration_questions_answered" in user_columns
                else "0"
            ),
            "registration_game_guesses_used": (
                f"{alias}.registration_game_guesses_used"
                if "registration_game_guesses_used" in user_columns
                else "0"
            ),
            "registration_game_completed": (
                f"{alias}.registration_game_completed"
                if "registration_game_completed" in user_columns
                else default_completed
            ),
            "registration_game_incorrect_answers": (
                f"{alias}.registration_game_incorrect_answers"
                if "registration_game_incorrect_answers" in user_columns
                else "0"
            ),
            "registration_game_points": (
                f"{alias}.registration_game_points"
                if "registration_game_points" in user_columns
                else "0"
            ),
            "registration_game_completed_at": (
                f"{alias}.registration_game_completed_at"
                if "registration_game_completed_at" in user_columns
                else "NULL"
            ),
        }
        return ",\n                    ".join(
            f"{expression} AS {column_name}"
            for column_name, expression in projection_map.items()
        )

    def export_database_bytes(self) -> bytes:
        if not self.db_path.exists():
            self.apply_migrations()
        return self.db_path.read_bytes()

    def _validate_backup_file(self, candidate_path: Path) -> None:
        conn = sqlite3.connect(candidate_path)
        try:
            quick_check = conn.execute("PRAGMA quick_check").fetchone()
            if not quick_check or quick_check[0] != "ok":
                raise ValueError("Uploaded backup failed SQLite integrity check.")

            table_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            table_names = {str(row[0]) for row in table_rows}
            missing = self.REQUIRED_BACKUP_TABLES - table_names
            if missing:
                missing_list = ", ".join(sorted(missing))
                raise ValueError(f"Backup is missing required tables: {missing_list}")
        finally:
            conn.close()

    def import_database_bytes(self, backup_bytes: bytes) -> None:
        if not backup_bytes:
            raise ValueError("Backup file is empty.")

        fd, temp_name = tempfile.mkstemp(
            prefix="tournament_import_",
            suffix=".sqlite3",
            dir=str(self.db_path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)

        try:
            temp_path.write_bytes(backup_bytes)
            self._validate_backup_file(temp_path)

            if self.db_path.exists():
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                rollback_path = self.db_path.with_suffix(f"{self.db_path.suffix}.pre_import_{timestamp}.bak")
                shutil.copy2(self.db_path, rollback_path)

            temp_path.replace(self.db_path)
            self.apply_migrations()
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            account_origin=row["account_origin"] if "account_origin" in row.keys() else "legacy",
            registration_questions_answered=(
                int(row["registration_questions_answered"])
                if "registration_questions_answered" in row.keys()
                else 0
            ),
            registration_game_guesses_used=(
                int(row["registration_game_guesses_used"])
                if "registration_game_guesses_used" in row.keys()
                else 0
            ),
            registration_game_completed=(
                bool(row["registration_game_completed"])
                if "registration_game_completed" in row.keys()
                else False
            ),
            registration_game_incorrect_answers=(
                int(row["registration_game_incorrect_answers"])
                if "registration_game_incorrect_answers" in row.keys()
                else 0
            ),
            registration_game_points=(
                float(row["registration_game_points"])
                if "registration_game_points" in row.keys()
                else 0.0
            ),
            registration_game_completed_at=(
                row["registration_game_completed_at"]
                if "registration_game_completed_at" in row.keys()
                else None
            ),
        )

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> ParticipantProfile:
        return ParticipantProfile(
            user_id=row["user_id"],
            display_name=row["display_name"],
            motto=row["motto"],
            photo_blob=row["photo_blob"],
            photo_mime_type=row["photo_mime_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_invitation(row: sqlite3.Row) -> Invitation:
        return Invitation(
            id=row["id"],
            token_hash=row["token_hash"],
            created_by_user_id=row["created_by_user_id"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            used_at=row["used_at"],
            used_by_user_id=row["used_by_user_id"],
            note=row["note"],
        )

    @staticmethod
    def _row_to_match(row: sqlite3.Row) -> Match:
        return Match(
            id=row["id"],
            game_type=row["game_type"],
            scheduled_at=row["scheduled_at"],
            scheduled_order=row["scheduled_order"],
            status=row["status"],
            created_by_user_id=row["created_by_user_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_match_result(row: sqlite3.Row) -> MatchResult:
        return MatchResult(
            id=row["id"],
            match_id=row["match_id"],
            outcome=row["outcome"],
            entered_by_user_id=row["entered_by_user_id"],
            entered_at=row["entered_at"],
            notes=row["notes"],
        )

    @staticmethod
    def _row_to_doubler_activation(row: sqlite3.Row) -> DoublerActivation:
        return DoublerActivation(
            id=row["id"],
            participant_user_id=row["participant_user_id"],
            match_id=row["match_id"],
            activated_at=row["activated_at"],
            activated_by_user_id=row["activated_by_user_id"],
        )

    @staticmethod
    def _row_to_minigame_run(row: sqlite3.Row) -> MiniGameRun:
        return MiniGameRun(
            id=row["id"],
            game_slug=row["game_slug"],
            participant_user_id=row["participant_user_id"],
            score=int(row["score"]),
            duration_seconds=int(row["duration_seconds"]),
            played_at=row["played_at"],
            metadata_json=row["metadata_json"],
        )

    @staticmethod
    def _row_to_minigame_award(row: sqlite3.Row) -> MiniGameAward:
        return MiniGameAward(
            id=row["id"],
            game_slug=row["game_slug"],
            participant_user_id=row["participant_user_id"],
            placement=int(row["placement"]),
            points_awarded=float(row["points_awarded"]),
            awarded_at=row["awarded_at"],
            awarded_by_user_id=int(row["awarded_by_user_id"]),
        )

    @staticmethod
    def _row_to_competition_point_award(row: sqlite3.Row) -> CompetitionPointAward:
        return CompetitionPointAward(
            id=int(row["id"]),
            participant_user_id=int(row["participant_user_id"]),
            source_type=str(row["source_type"]),
            source_key=str(row["source_key"]),
            source_label=str(row["source_label"]),
            placement=int(row["placement"]) if row["placement"] is not None else None,
            points_awarded=float(row["points_awarded"]),
            awarded_at=str(row["awarded_at"]),
            awarded_by_user_id=(
                int(row["awarded_by_user_id"])
                if row["awarded_by_user_id"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_match_bet(row: sqlite3.Row) -> MatchBet:
        return MatchBet(
            id=int(row["id"]),
            match_id=int(row["match_id"]),
            participant_user_id=int(row["participant_user_id"]),
            predicted_outcome=str(row["predicted_outcome"]),
            stake_points=float(row["stake_points"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            settled_at=str(row["settled_at"]) if row["settled_at"] is not None else None,
            net_points=float(row["net_points"]) if row["net_points"] is not None else None,
        )

    @staticmethod
    def _row_to_participant_special(row: sqlite3.Row) -> ParticipantSpecial:
        return ParticipantSpecial(
            participant_user_id=int(row["participant_user_id"]),
            special_key=str(row["special_key"]),
            is_available=bool(row["is_available"]),
            is_active=bool(row["is_active"]),
            granted_at=str(row["granted_at"]) if row["granted_at"] is not None else None,
            activated_at=str(row["activated_at"]) if row["activated_at"] is not None else None,
            resolved_at=str(row["resolved_at"]) if row["resolved_at"] is not None else None,
            payload_json=str(row["payload_json"]) if row["payload_json"] is not None else None,
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_match_special_activation(row: sqlite3.Row) -> MatchSpecialActivation:
        return MatchSpecialActivation(
            id=int(row["id"]),
            participant_user_id=int(row["participant_user_id"]),
            special_key=str(row["special_key"]),
            match_id=int(row["match_id"]),
            activated_at=str(row["activated_at"]),
            activated_by_user_id=int(row["activated_by_user_id"]),
            payload_json=str(row["payload_json"]) if row["payload_json"] is not None else None,
        )

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_login(self, login_identifier: str) -> Optional[User]:
        login = login_identifier.strip().lower()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM users
                WHERE lower(coalesce(username, '')) = ?
                   OR lower(coalesce(email, '')) = ?
                LIMIT 1
                """,
                (login, login),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[User]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE lower(username) = lower(?)",
                (username,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE lower(email) = lower(?)",
                (email,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def create_user(
        self,
        *,
        username: Optional[str],
        email: Optional[str],
        password_hash: str,
        role: str,
        created_at: str,
    ) -> User:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (username, email, password_hash, role, created_at, created_at),
            )
            user_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise RuntimeError("User creation failed")
        return self._row_to_user(row)

    def upsert_participant_profile(
        self,
        *,
        user_id: int,
        display_name: str,
        motto: str,
        photo_blob: Optional[bytes],
        photo_mime_type: Optional[str],
        now_iso: str,
    ) -> ParticipantProfile:
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT user_id FROM participant_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE participant_profiles
                    SET display_name = ?,
                        motto = ?,
                        photo_blob = ?,
                        photo_mime_type = ?,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (display_name, motto, photo_blob, photo_mime_type, now_iso, user_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO participant_profiles
                        (user_id, display_name, motto, photo_blob, photo_mime_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        display_name,
                        motto,
                        photo_blob,
                        photo_mime_type,
                        now_iso,
                        now_iso,
                    ),
                )

            row = conn.execute(
                "SELECT * FROM participant_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if not row:
            raise RuntimeError("Profile upsert failed")
        return self._row_to_profile(row)

    def get_participant_profile(self, user_id: int) -> Optional[ParticipantProfile]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM participant_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def get_user_with_profile(self, user_id: int) -> Optional[UserWithProfile]:
        registration_projection = self._user_registration_projection("u")
        with self.connection() as conn:
            row = conn.execute(
                f"""
                SELECT
                    u.id AS user_id,
                    u.username,
                    u.email,
                    u.role,
                    u.is_active,
                    {registration_projection},
                    pp.display_name,
                    pp.motto,
                    pp.photo_blob,
                    pp.photo_mime_type
                FROM users u
                LEFT JOIN participant_profiles pp ON pp.user_id = u.id
                WHERE u.id = ?
                """,
                (user_id,),
            ).fetchone()

        if not row:
            return None

        return UserWithProfile(
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            display_name=row["display_name"],
            motto=row["motto"],
            photo_blob=row["photo_blob"],
            photo_mime_type=row["photo_mime_type"],
            account_origin=row["account_origin"],
            registration_questions_answered=int(row["registration_questions_answered"]),
            registration_game_guesses_used=int(row["registration_game_guesses_used"]),
            registration_game_completed=bool(row["registration_game_completed"]),
            registration_game_incorrect_answers=int(row["registration_game_incorrect_answers"]),
            registration_game_points=float(row["registration_game_points"]),
            registration_game_completed_at=row["registration_game_completed_at"],
        )

    def list_participants(self) -> list[UserWithProfile]:
        registration_projection = self._user_registration_projection("u")
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    u.id AS user_id,
                    u.username,
                    u.email,
                    u.role,
                    u.is_active,
                    {registration_projection},
                    pp.display_name,
                    pp.motto,
                    pp.photo_blob,
                    pp.photo_mime_type
                FROM users u
                LEFT JOIN participant_profiles pp ON pp.user_id = u.id
                WHERE u.role = 'participant'
                ORDER BY lower(coalesce(pp.display_name, u.username, u.email, cast(u.id as text)))
                """
            ).fetchall()

        return [
            UserWithProfile(
                user_id=row["user_id"],
                username=row["username"],
                email=row["email"],
                role=row["role"],
                is_active=bool(row["is_active"]),
                display_name=row["display_name"],
                motto=row["motto"],
                photo_blob=row["photo_blob"],
                photo_mime_type=row["photo_mime_type"],
                account_origin=row["account_origin"],
                registration_questions_answered=int(row["registration_questions_answered"]),
                registration_game_guesses_used=int(row["registration_game_guesses_used"]),
                registration_game_completed=bool(row["registration_game_completed"]),
                registration_game_incorrect_answers=int(row["registration_game_incorrect_answers"]),
                registration_game_points=float(row["registration_game_points"]),
                registration_game_completed_at=row["registration_game_completed_at"],
            )
            for row in rows
        ]

    def create_admin_managed_participant(
        self,
        *,
        username: str,
        email: Optional[str],
        password_hash: str,
        display_name: str,
        motto: str,
        created_by_admin_user_id: int,
        now_iso: str,
    ) -> User:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (
                    username,
                    email,
                    password_hash,
                    role,
                    is_active,
                    created_at,
                    updated_at,
                    account_origin,
                    registration_questions_answered,
                    registration_game_guesses_used,
                    registration_game_completed,
                    registration_game_incorrect_answers,
                    registration_game_points,
                    registration_game_completed_at
                )
                VALUES (?, ?, ?, 'participant', 1, ?, ?, 'admin_created', 0, 0, 0, 0, 0, NULL)
                """,
                (username, email, password_hash, now_iso, now_iso),
            )
            user_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO participant_profiles
                    (user_id, display_name, motto, photo_blob, photo_mime_type, created_at, updated_at)
                VALUES (?, ?, ?, NULL, NULL, ?, ?)
                """,
                (user_id, display_name, motto, now_iso, now_iso),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        if not row:
            raise RuntimeError("Admin-managed participant creation failed")
        return self._row_to_user(row)

    def count_participant_users(self, user_ids: Iterable[int]) -> int:
        user_ids = list(user_ids)
        if not user_ids:
            return 0
        placeholders = ",".join(["?"] * len(user_ids))
        sql = f"SELECT COUNT(*) AS c FROM users WHERE role = 'participant' AND id IN ({placeholders})"
        with self.connection() as conn:
            row = conn.execute(sql, tuple(user_ids)).fetchone()
        return int(row["c"] if row else 0)

    def create_invitation(
        self,
        *,
        token_hash: str,
        created_by_user_id: int,
        expires_at: str,
        now_iso: str,
        note: Optional[str],
    ) -> Invitation:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO invitations (token_hash, created_by_user_id, created_at, expires_at, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_hash, created_by_user_id, now_iso, expires_at, note),
            )
            invitation_id = int(cursor.lastrowid)
            row = conn.execute(
                "SELECT * FROM invitations WHERE id = ?",
                (invitation_id,),
            ).fetchone()

        if not row:
            raise RuntimeError("Invitation creation failed")
        return self._row_to_invitation(row)

    def get_invitation_by_token_hash(self, token_hash: str) -> Optional[Invitation]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM invitations WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        return self._row_to_invitation(row) if row else None

    def mark_invitation_used(
        self,
        *,
        invitation_id: int,
        user_id: int,
        used_at: str,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE invitations
                SET used_at = ?, used_by_user_id = ?
                WHERE id = ?
                """,
                (used_at, user_id, invitation_id),
            )

    def list_invitations(self, limit: int = 50) -> list[InvitationDisplay]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    i.id,
                    i.created_at,
                    i.expires_at,
                    i.used_at,
                    i.note,
                    coalesce(pp.display_name, u.username, u.email) AS created_by_name
                FROM invitations i
                LEFT JOIN users u ON u.id = i.created_by_user_id
                LEFT JOIN participant_profiles pp ON pp.user_id = i.created_by_user_id
                ORDER BY i.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            InvitationDisplay(
                id=row["id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                used_at=row["used_at"],
                note=row["note"],
                created_by_name=row["created_by_name"],
            )
            for row in rows
        ]

    def accept_invitation_create_participant(
        self,
        *,
        invitation_id: int,
        username: Optional[str],
        email: Optional[str],
        password_hash: str,
        display_name: str,
        motto: str,
        photo_blob: Optional[bytes],
        photo_mime_type: Optional[str],
        now_iso: str,
    ) -> User:
        with self.connection() as conn:
            invitation_row = conn.execute(
                "SELECT * FROM invitations WHERE id = ?",
                (invitation_id,),
            ).fetchone()
            if not invitation_row:
                raise ValueError("Invitation not found")
            if invitation_row["used_at"] is not None:
                raise ValueError("Invitation already used")

            cursor = conn.execute(
                """
                INSERT INTO users (
                    username,
                    email,
                    password_hash,
                    role,
                    is_active,
                    created_at,
                    updated_at,
                    account_origin,
                    registration_questions_answered,
                    registration_game_guesses_used,
                    registration_game_completed,
                    registration_game_incorrect_answers,
                    registration_game_points,
                    registration_game_completed_at
                )
                VALUES (?, ?, ?, 'participant', 1, ?, ?, 'invitation', 0, 0, 0, 0, 0, NULL)
                """,
                (username, email, password_hash, now_iso, now_iso),
            )
            user_id = int(cursor.lastrowid)

            conn.execute(
                """
                INSERT INTO participant_profiles
                    (user_id, display_name, motto, photo_blob, photo_mime_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    display_name,
                    motto,
                    photo_blob,
                    photo_mime_type,
                    now_iso,
                    now_iso,
                ),
            )

            conn.execute(
                """
                UPDATE invitations
                SET used_at = ?, used_by_user_id = ?
                WHERE id = ?
                """,
                (now_iso, user_id, invitation_id),
            )

            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        if not row:
            raise RuntimeError("Failed to create invited participant")
        return self._row_to_user(row)

    def create_match(
        self,
        *,
        game_type: str,
        scheduled_at: Optional[str],
        scheduled_order: Optional[int],
        status: str,
        created_by_user_id: int,
        now_iso: str,
        side1_name: Optional[str],
        side2_name: Optional[str],
        side1_participant_ids: list[int],
        side2_participant_ids: list[int],
    ) -> Match:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO matches (game_type, scheduled_at, scheduled_order, status, created_by_user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_type,
                    scheduled_at,
                    scheduled_order,
                    status,
                    created_by_user_id,
                    now_iso,
                    now_iso,
                ),
            )
            match_id = int(cursor.lastrowid)

            side1_id = int(
                conn.execute(
                    "INSERT INTO match_sides (match_id, side_number, side_name) VALUES (?, 1, ?)",
                    (match_id, side1_name),
                ).lastrowid
            )
            side2_id = int(
                conn.execute(
                    "INSERT INTO match_sides (match_id, side_number, side_name) VALUES (?, 2, ?)",
                    (match_id, side2_name),
                ).lastrowid
            )

            for participant_id in side1_participant_ids:
                conn.execute(
                    "INSERT INTO match_participants (match_side_id, participant_user_id) VALUES (?, ?)",
                    (side1_id, participant_id),
                )

            for participant_id in side2_participant_ids:
                conn.execute(
                    "INSERT INTO match_participants (match_side_id, participant_user_id) VALUES (?, ?)",
                    (side2_id, participant_id),
                )

            row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()

        if not row:
            raise RuntimeError("Match creation failed")
        return self._row_to_match(row)

    def update_match(
        self,
        *,
        match_id: int,
        game_type: str,
        scheduled_at: Optional[str],
        scheduled_order: Optional[int],
        status: str,
        updated_at: str,
        side1_name: Optional[str],
        side2_name: Optional[str],
        side1_participant_ids: list[int],
        side2_participant_ids: list[int],
    ) -> Optional[Match]:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE matches
                SET game_type = ?,
                    scheduled_at = ?,
                    scheduled_order = ?,
                    status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (game_type, scheduled_at, scheduled_order, status, updated_at, match_id),
            )

            side_rows = conn.execute(
                "SELECT id, side_number FROM match_sides WHERE match_id = ?",
                (match_id,),
            ).fetchall()
            side_ids = {row["side_number"]: row["id"] for row in side_rows}

            if 1 not in side_ids:
                side_ids[1] = int(
                    conn.execute(
                        "INSERT INTO match_sides (match_id, side_number, side_name) VALUES (?, 1, ?)",
                        (match_id, side1_name),
                    ).lastrowid
                )
            if 2 not in side_ids:
                side_ids[2] = int(
                    conn.execute(
                        "INSERT INTO match_sides (match_id, side_number, side_name) VALUES (?, 2, ?)",
                        (match_id, side2_name),
                    ).lastrowid
                )

            conn.execute(
                "UPDATE match_sides SET side_name = ? WHERE id = ?",
                (side1_name, side_ids[1]),
            )
            conn.execute(
                "UPDATE match_sides SET side_name = ? WHERE id = ?",
                (side2_name, side_ids[2]),
            )

            conn.execute("DELETE FROM match_participants WHERE match_side_id = ?", (side_ids[1],))
            conn.execute("DELETE FROM match_participants WHERE match_side_id = ?", (side_ids[2],))

            for participant_id in side1_participant_ids:
                conn.execute(
                    "INSERT INTO match_participants (match_side_id, participant_user_id) VALUES (?, ?)",
                    (side_ids[1], participant_id),
                )
            for participant_id in side2_participant_ids:
                conn.execute(
                    "INSERT INTO match_participants (match_side_id, participant_user_id) VALUES (?, ?)",
                    (side_ids[2], participant_id),
                )

            row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()

        return self._row_to_match(row) if row else None

    def delete_match(self, match_id: int) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM matches WHERE id = ?", (match_id,))

    def get_match(self, match_id: int) -> Optional[Match]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        return self._row_to_match(row) if row else None

    def list_matches(self, statuses: Optional[list[str]] = None) -> list[Match]:
        where_clause = ""
        params: list[Any] = []

        if statuses:
            placeholders = ",".join(["?"] * len(statuses))
            where_clause = f"WHERE status IN ({placeholders})"
            params.extend(statuses)

        sql = f"""
            SELECT *
            FROM matches
            {where_clause}
            ORDER BY
                CASE WHEN scheduled_order IS NULL THEN 1 ELSE 0 END,
                scheduled_order,
                CASE WHEN scheduled_at IS NULL THEN 1 ELSE 0 END,
                scheduled_at,
                id DESC
        """

        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        return [self._row_to_match(row) for row in rows]

    def list_match_rows(
        self,
        *,
        statuses: Optional[list[str]] = None,
        participant_user_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        where_parts: list[str] = []
        params: list[Any] = []

        if statuses:
            placeholders = ",".join(["?"] * len(statuses))
            where_parts.append(f"m.status IN ({placeholders})")
            params.extend(statuses)

        if participant_user_id is not None:
            where_parts.append(
                """
                EXISTS (
                    SELECT 1
                    FROM match_sides ms
                    JOIN match_participants mp ON mp.match_side_id = ms.id
                    WHERE ms.match_id = m.id
                      AND mp.participant_user_id = ?
                )
                """
            )
            params.append(participant_user_id)

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        sql = f"""
            SELECT
                m.id AS match_id,
                m.game_type,
                m.scheduled_at,
                m.scheduled_order,
                m.status,
                mr.outcome,
                mr.notes AS result_notes
            FROM matches m
            LEFT JOIN match_results mr ON mr.match_id = m.id
            {where_sql}
            ORDER BY
                CASE WHEN m.status = 'live' THEN 0 WHEN m.status = 'upcoming' THEN 1 ELSE 2 END,
                CASE WHEN m.scheduled_order IS NULL THEN 1 ELSE 0 END,
                m.scheduled_order,
                CASE WHEN m.scheduled_at IS NULL THEN 1 ELSE 0 END,
                m.scheduled_at,
                m.id DESC
        """

        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def list_match_participant_rows(self, match_ids: list[int]) -> list[dict[str, Any]]:
        if not match_ids:
            return []

        placeholders = ",".join(["?"] * len(match_ids))
        sql = f"""
            SELECT
                ms.match_id,
                ms.side_number,
                ms.side_name,
                u.id AS user_id,
                pp.display_name,
                pp.motto,
                pp.photo_blob,
                pp.photo_mime_type,
                u.username,
                u.email
            FROM match_sides ms
            JOIN match_participants mp ON mp.match_side_id = ms.id
            JOIN users u ON u.id = mp.participant_user_id
            LEFT JOIN participant_profiles pp ON pp.user_id = u.id
            WHERE ms.match_id IN ({placeholders})
            ORDER BY
                ms.match_id,
                ms.side_number,
                lower(coalesce(pp.display_name, u.username, u.email, cast(u.id as text)))
        """

        with self.connection() as conn:
            rows = conn.execute(sql, tuple(match_ids)).fetchall()
        return [dict(row) for row in rows]

    def list_doubler_rows_for_matches(self, match_ids: list[int]) -> list[dict[str, Any]]:
        if not match_ids:
            return []
        placeholders = ",".join(["?"] * len(match_ids))
        sql = f"""
            SELECT participant_user_id, match_id, activated_at
            FROM match_special_activations
            WHERE special_key = 'doubler'
              AND match_id IN ({placeholders})
        """
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(match_ids)).fetchall()
        return [dict(row) for row in rows]

    def list_completed_match_rows_for_scoring(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    m.id AS match_id,
                    m.game_type,
                    m.scheduled_at,
                    m.scheduled_order,
                    m.status,
                    mr.outcome,
                    mr.entered_at,
                    mr.notes AS result_notes
                FROM matches m
                JOIN match_results mr ON mr.match_id = m.id
                WHERE m.status = 'completed'
                ORDER BY mr.entered_at ASC, m.id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_match_result(
        self,
        *,
        match_id: int,
        outcome: str,
        entered_by_user_id: int,
        entered_at: str,
        notes: Optional[str],
        mark_completed: bool,
    ) -> MatchResult:
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT * FROM match_results WHERE match_id = ?",
                (match_id,),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE match_results
                    SET outcome = ?, entered_by_user_id = ?, entered_at = ?, notes = ?
                    WHERE match_id = ?
                    """,
                    (outcome, entered_by_user_id, entered_at, notes, match_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO match_results (match_id, outcome, entered_by_user_id, entered_at, notes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (match_id, outcome, entered_by_user_id, entered_at, notes),
                )

            if mark_completed:
                conn.execute(
                    "UPDATE matches SET status = 'completed', updated_at = ? WHERE id = ?",
                    (entered_at, match_id),
                )

            row = conn.execute(
                "SELECT * FROM match_results WHERE match_id = ?",
                (match_id,),
            ).fetchone()

        if not row:
            raise RuntimeError("Failed to upsert match result")
        return self._row_to_match_result(row)

    def delete_match_result(self, *, match_id: int, updated_at: str, new_status: str) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM match_results WHERE match_id = ?", (match_id,))
            conn.execute(
                "UPDATE matches SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, updated_at, match_id),
            )

    def get_match_result(self, match_id: int) -> Optional[MatchResult]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM match_results WHERE match_id = ?",
                (match_id,),
            ).fetchone()
        return self._row_to_match_result(row) if row else None

    def get_match_side_ids(self, match_id: int) -> dict[int, int]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, side_number FROM match_sides WHERE match_id = ?",
                (match_id,),
            ).fetchall()
        return {int(row["side_number"]): int(row["id"]) for row in rows}

    def is_participant_in_match(self, *, participant_user_id: int, match_id: int) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM match_sides ms
                JOIN match_participants mp ON mp.match_side_id = ms.id
                WHERE ms.match_id = ? AND mp.participant_user_id = ?
                LIMIT 1
                """,
                (match_id, participant_user_id),
            ).fetchone()
        return row is not None

    def create_doubler_activation(
        self,
        *,
        participant_user_id: int,
        match_id: int,
        activated_by_user_id: int,
        now_iso: str,
    ) -> DoublerActivation:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO match_special_activations (
                    participant_user_id,
                    special_key,
                    match_id,
                    activated_at,
                    activated_by_user_id,
                    payload_json
                )
                VALUES (?, 'doubler', ?, ?, ?, NULL)
                """,
                (participant_user_id, match_id, now_iso, activated_by_user_id),
            )
            activation_id = int(cursor.lastrowid)
            row = conn.execute(
                "SELECT * FROM match_special_activations WHERE id = ?",
                (activation_id,),
            ).fetchone()

        if not row:
            raise RuntimeError("Failed to create doubler activation")
        return DoublerActivation(
            id=int(row["id"]),
            participant_user_id=int(row["participant_user_id"]),
            match_id=int(row["match_id"]),
            activated_at=str(row["activated_at"]),
            activated_by_user_id=int(row["activated_by_user_id"]),
        )

    def get_doubler_activation(self, participant_user_id: int) -> Optional[DoublerActivation]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM match_special_activations
                WHERE participant_user_id = ?
                  AND special_key = 'doubler'
                ORDER BY activated_at DESC, id DESC
                LIMIT 1
                """,
                (participant_user_id,),
            ).fetchone()
        if not row:
            return None
        return DoublerActivation(
            id=int(row["id"]),
            participant_user_id=int(row["participant_user_id"]),
            match_id=int(row["match_id"]),
            activated_at=str(row["activated_at"]),
            activated_by_user_id=int(row["activated_by_user_id"]),
        )

    def delete_doubler_activation(self, participant_user_id: int) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                DELETE FROM match_special_activations
                WHERE participant_user_id = ?
                  AND special_key = 'doubler'
                """,
                (participant_user_id,),
            )

    def list_doubler_rows(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    da.participant_user_id,
                    da.match_id,
                    da.activated_at,
                    pp.display_name,
                    m.game_type,
                    m.status,
                    m.scheduled_order
                FROM match_special_activations da
                LEFT JOIN participant_profiles pp ON pp.user_id = da.participant_user_id
                LEFT JOIN matches m ON m.id = da.match_id
                WHERE da.special_key = 'doubler'
                ORDER BY da.activated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_completed_match_player_rows(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    mr.match_id,
                    mr.outcome,
                    ms.side_number,
                    mp.participant_user_id
                FROM match_results mr
                JOIN match_sides ms ON ms.match_id = mr.match_id
                JOIN match_participants mp ON mp.match_side_id = ms.id
                JOIN matches m ON m.id = mr.match_id
                WHERE m.status = 'completed'
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_profiles_by_user_ids(self, user_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not user_ids:
            return {}
        placeholders = ",".join(["?"] * len(user_ids))
        registration_projection = self._user_registration_projection("u")
        sql = f"""
            SELECT
                u.id AS user_id,
                u.username,
                u.email,
                {registration_projection},
                pp.display_name,
                pp.motto,
                pp.photo_blob,
                pp.photo_mime_type
            FROM users u
            LEFT JOIN participant_profiles pp ON pp.user_id = u.id
            WHERE u.id IN ({placeholders})
        """
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(user_ids)).fetchall()
        return {int(row["user_id"]): dict(row) for row in rows}

    def list_participant_match_rows(self, participant_user_id: int) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    m.id AS match_id,
                    m.game_type,
                    m.scheduled_at,
                    m.scheduled_order,
                    m.status,
                    mr.outcome,
                    ms.side_number
                FROM matches m
                JOIN match_sides ms ON ms.match_id = m.id
                JOIN match_participants mp ON mp.match_side_id = ms.id
                LEFT JOIN match_results mr ON mr.match_id = m.id
                WHERE mp.participant_user_id = ?
                ORDER BY
                    CASE WHEN m.status = 'completed' THEN 1 ELSE 0 END,
                    CASE WHEN m.scheduled_order IS NULL THEN 1 ELSE 0 END,
                    m.scheduled_order,
                    m.id DESC
                """,
                (participant_user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def log_activity(
        self,
        *,
        event_type: str,
        message: str,
        created_at: str,
        related_match_id: Optional[int] = None,
        related_user_id: Optional[int] = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO activity_log (event_type, message, related_match_id, related_user_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_type, message, related_match_id, related_user_id, created_at),
            )

    def list_recent_activity(self, limit: int = 10) -> list[ActivityItem]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT created_at, message
                FROM activity_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [ActivityItem(timestamp=row["created_at"], message=row["message"]) for row in rows]

    def create_minigame_run(
        self,
        *,
        game_slug: str,
        participant_user_id: int,
        score: int,
        duration_seconds: int,
        played_at: str,
        metadata_json: Optional[str],
    ) -> MiniGameRun:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO minigame_runs (
                    game_slug,
                    participant_user_id,
                    score,
                    duration_seconds,
                    played_at,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    game_slug,
                    participant_user_id,
                    score,
                    duration_seconds,
                    played_at,
                    metadata_json,
                ),
            )
            run_id = int(cursor.lastrowid)
            row = conn.execute(
                "SELECT * FROM minigame_runs WHERE id = ?",
                (run_id,),
            ).fetchone()

        if not row:
            raise RuntimeError("Failed to create minigame run")
        return self._row_to_minigame_run(row)

    def list_minigame_runs(self, game_slug: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    mr.id,
                    mr.game_slug,
                    mr.participant_user_id,
                    mr.score,
                    mr.duration_seconds,
                    mr.played_at,
                    mr.metadata_json,
                    pp.display_name,
                    pp.motto,
                    pp.photo_blob,
                    pp.photo_mime_type,
                    u.username,
                    u.email
                FROM minigame_runs mr
                JOIN users u ON u.id = mr.participant_user_id
                LEFT JOIN participant_profiles pp ON pp.user_id = mr.participant_user_id
                WHERE mr.game_slug = ?
                ORDER BY mr.score DESC, mr.played_at ASC, mr.id ASC
                """,
                (game_slug,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_competition_point_award(
        self,
        *,
        participant_user_id: int,
        source_type: str,
        source_key: str,
        source_label: str,
        placement: Optional[int],
        points_awarded: float,
        awarded_at: str,
        awarded_by_user_id: Optional[int],
    ) -> CompetitionPointAward:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO competition_point_awards (
                    participant_user_id,
                    source_type,
                    source_key,
                    source_label,
                    placement,
                    points_awarded,
                    awarded_at,
                    awarded_by_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    participant_user_id,
                    source_type,
                    source_key,
                    source_label,
                    placement,
                    points_awarded,
                    awarded_at,
                    awarded_by_user_id,
                ),
            )
            row = conn.execute(
                """
                SELECT *
                FROM competition_point_awards
                WHERE participant_user_id = ?
                  AND source_type = ?
                  AND source_key = ?
                """,
                (participant_user_id, source_type, source_key),
            ).fetchone()

        if not row:
            raise RuntimeError("Failed to upsert competition point award")
        return self._row_to_competition_point_award(row)

    def replace_competition_point_awards(
        self,
        *,
        source_type: str,
        source_key: str,
        source_label: str,
        awards: list[tuple[int, Optional[int], float, str, Optional[int]]],
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                DELETE FROM competition_point_awards
                WHERE source_type = ? AND source_key = ?
                """,
                (source_type, source_key),
            )
            conn.executemany(
                """
                INSERT INTO competition_point_awards (
                    participant_user_id,
                    source_type,
                    source_key,
                    source_label,
                    placement,
                    points_awarded,
                    awarded_at,
                    awarded_by_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        participant_user_id,
                        source_type,
                        source_key,
                        source_label,
                        placement,
                        points_awarded,
                        awarded_at,
                        awarded_by_user_id,
                    )
                    for participant_user_id, placement, points_awarded, awarded_at, awarded_by_user_id in awards
                ],
            )

    def list_competition_point_awards(
        self,
        *,
        source_type: Optional[str] = None,
        source_key: Optional[str] = None,
    ) -> list[CompetitionPointAward]:
        where_parts: list[str] = []
        params: list[Any] = []
        if source_type:
            where_parts.append("source_type = ?")
            params.append(source_type)
        if source_key:
            where_parts.append("source_key = ?")
            params.append(source_key)

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM competition_point_awards
                {where_sql}
                ORDER BY source_type, source_key, placement, awarded_at, id
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_competition_point_award(row) for row in rows]

    def list_competition_point_award_rows(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    participant_user_id,
                    source_type,
                    source_key,
                    source_label,
                    placement,
                    points_awarded,
                    awarded_at,
                    awarded_by_user_id
                FROM competition_point_awards
                ORDER BY awarded_at ASC, id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_competition_point_award(
        self,
        *,
        participant_user_id: int,
        source_type: str,
        source_key: str,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                DELETE FROM competition_point_awards
                WHERE participant_user_id = ?
                  AND source_type = ?
                  AND source_key = ?
                """,
                (participant_user_id, source_type, source_key),
            )

    def delete_competition_point_awards_by_source_types(self, source_types: list[str]) -> None:
        if not source_types:
            return
        placeholders = ",".join(["?"] * len(source_types))
        with self.connection() as conn:
            conn.execute(
                f"DELETE FROM competition_point_awards WHERE source_type IN ({placeholders})",
                tuple(source_types),
            )

    def upsert_match_bet(
        self,
        *,
        match_id: int,
        participant_user_id: int,
        predicted_outcome: str,
        stake_points: float,
        now_iso: str,
    ) -> MatchBet:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO match_bets (
                    match_id,
                    participant_user_id,
                    predicted_outcome,
                    stake_points,
                    created_at,
                    updated_at,
                    settled_at,
                    net_points
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
                ON CONFLICT(match_id, participant_user_id)
                DO UPDATE SET
                    predicted_outcome = excluded.predicted_outcome,
                    stake_points = excluded.stake_points,
                    updated_at = excluded.updated_at
                """,
                (
                    match_id,
                    participant_user_id,
                    predicted_outcome,
                    stake_points,
                    now_iso,
                    now_iso,
                ),
            )
            row = conn.execute(
                """
                SELECT *
                FROM match_bets
                WHERE match_id = ? AND participant_user_id = ?
                """,
                (match_id, participant_user_id),
            ).fetchone()

        if not row:
            raise RuntimeError("Failed to upsert match bet")
        return self._row_to_match_bet(row)

    def get_match_bet(self, *, match_id: int, participant_user_id: int) -> Optional[MatchBet]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM match_bets
                WHERE match_id = ? AND participant_user_id = ?
                """,
                (match_id, participant_user_id),
            ).fetchone()
        return self._row_to_match_bet(row) if row else None

    def list_match_bets(
        self,
        *,
        match_ids: Optional[list[int]] = None,
        participant_user_id: Optional[int] = None,
        include_settled: bool = True,
    ) -> list[MatchBet]:
        where_parts: list[str] = []
        params: list[Any] = []

        if match_ids:
            placeholders = ",".join(["?"] * len(match_ids))
            where_parts.append(f"match_id IN ({placeholders})")
            params.extend(match_ids)
        if participant_user_id is not None:
            where_parts.append("participant_user_id = ?")
            params.append(participant_user_id)
        if not include_settled:
            where_parts.append("settled_at IS NULL")

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM match_bets
                {where_sql}
                ORDER BY created_at DESC, id DESC
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_match_bet(row) for row in rows]

    def settle_match_bet(
        self,
        *,
        bet_id: int,
        settled_at: Optional[str],
        net_points: Optional[float],
    ) -> Optional[MatchBet]:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE match_bets
                SET settled_at = ?, net_points = ?
                WHERE id = ?
                """,
                (settled_at, net_points, bet_id),
            )
            row = conn.execute("SELECT * FROM match_bets WHERE id = ?", (bet_id,)).fetchone()
        return self._row_to_match_bet(row) if row else None

    def sum_open_bet_stakes(self, participant_user_id: int) -> float:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(stake_points), 0) AS total
                FROM match_bets
                WHERE participant_user_id = ?
                  AND settled_at IS NULL
                """,
                (participant_user_id,),
            ).fetchone()
        return float(row["total"] if row else 0.0)

    def upsert_participant_special(
        self,
        *,
        participant_user_id: int,
        special_key: str,
        is_available: bool,
        is_active: bool,
        granted_at: Optional[str],
        activated_at: Optional[str],
        resolved_at: Optional[str],
        payload_json: Optional[str],
        updated_at: str,
    ) -> ParticipantSpecial:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO participant_specials (
                    participant_user_id,
                    special_key,
                    is_available,
                    is_active,
                    granted_at,
                    activated_at,
                    resolved_at,
                    payload_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(participant_user_id, special_key)
                DO UPDATE SET
                    is_available = excluded.is_available,
                    is_active = excluded.is_active,
                    granted_at = excluded.granted_at,
                    activated_at = excluded.activated_at,
                    resolved_at = excluded.resolved_at,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    participant_user_id,
                    special_key,
                    1 if is_available else 0,
                    1 if is_active else 0,
                    granted_at,
                    activated_at,
                    resolved_at,
                    payload_json,
                    updated_at,
                ),
            )
            row = conn.execute(
                """
                SELECT *
                FROM participant_specials
                WHERE participant_user_id = ? AND special_key = ?
                """,
                (participant_user_id, special_key),
            ).fetchone()

        if not row:
            raise RuntimeError("Failed to upsert participant special")
        return self._row_to_participant_special(row)

    def get_participant_special(self, *, participant_user_id: int, special_key: str) -> Optional[ParticipantSpecial]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM participant_specials
                WHERE participant_user_id = ? AND special_key = ?
                """,
                (participant_user_id, special_key),
            ).fetchone()
        return self._row_to_participant_special(row) if row else None

    def list_participant_specials(
        self,
        *,
        participant_user_id: Optional[int] = None,
        special_key: Optional[str] = None,
    ) -> list[ParticipantSpecial]:
        where_parts: list[str] = []
        params: list[Any] = []
        if participant_user_id is not None:
            where_parts.append("participant_user_id = ?")
            params.append(participant_user_id)
        if special_key is not None:
            where_parts.append("special_key = ?")
            params.append(special_key)

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM participant_specials
                {where_sql}
                ORDER BY participant_user_id, special_key
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_participant_special(row) for row in rows]

    def create_match_special_activation(
        self,
        *,
        participant_user_id: int,
        special_key: str,
        match_id: int,
        activated_at: str,
        activated_by_user_id: int,
        payload_json: Optional[str],
    ) -> MatchSpecialActivation:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO match_special_activations (
                    participant_user_id,
                    special_key,
                    match_id,
                    activated_at,
                    activated_by_user_id,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    participant_user_id,
                    special_key,
                    match_id,
                    activated_at,
                    activated_by_user_id,
                    payload_json,
                ),
            )
            activation_id = int(cursor.lastrowid)
            row = conn.execute(
                "SELECT * FROM match_special_activations WHERE id = ?",
                (activation_id,),
            ).fetchone()

        if not row:
            raise RuntimeError("Failed to create match special activation")
        return self._row_to_match_special_activation(row)

    def list_match_special_activations(
        self,
        *,
        match_ids: Optional[list[int]] = None,
        participant_user_id: Optional[int] = None,
        special_key: Optional[str] = None,
    ) -> list[MatchSpecialActivation]:
        where_parts: list[str] = []
        params: list[Any] = []
        if match_ids:
            placeholders = ",".join(["?"] * len(match_ids))
            where_parts.append(f"match_id IN ({placeholders})")
            params.extend(match_ids)
        if participant_user_id is not None:
            where_parts.append("participant_user_id = ?")
            params.append(participant_user_id)
        if special_key is not None:
            where_parts.append("special_key = ?")
            params.append(special_key)

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM match_special_activations
                {where_sql}
                ORDER BY activated_at DESC, id DESC
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_match_special_activation(row) for row in rows]

    def delete_match_special_activation(self, activation_id: int) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM match_special_activations WHERE id = ?", (activation_id,))

    def replace_minigame_awards(
        self,
        *,
        game_slug: str,
        awards: list[tuple[int, int, float, str, int]],
    ) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM minigame_awards WHERE game_slug = ?", (game_slug,))
            conn.executemany(
                """
                INSERT INTO minigame_awards (
                    game_slug,
                    participant_user_id,
                    placement,
                    points_awarded,
                    awarded_at,
                    awarded_by_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        game_slug,
                        participant_user_id,
                        placement,
                        points_awarded,
                        awarded_at,
                        awarded_by_user_id,
                    )
                    for participant_user_id, placement, points_awarded, awarded_at, awarded_by_user_id in awards
                ],
            )
        self.replace_competition_point_awards(
            source_type=COMPETITION_RANKING_SOURCE_TYPE,
            source_key=game_slug,
            source_label=game_slug.replace("_", " ").title(),
            awards=[
                (
                    participant_user_id,
                    placement,
                    points_awarded,
                    awarded_at,
                    awarded_by_user_id,
                )
                for participant_user_id, placement, points_awarded, awarded_at, awarded_by_user_id in awards
            ],
        )

    def list_minigame_awards(self, game_slug: Optional[str] = None) -> list[MiniGameAward]:
        awards = self.list_competition_point_awards(
            source_type=COMPETITION_RANKING_SOURCE_TYPE,
            source_key=game_slug,
        )
        return [
            MiniGameAward(
                id=award.id,
                game_slug=award.source_key,
                participant_user_id=award.participant_user_id,
                placement=int(award.placement or 0),
                points_awarded=award.points_awarded,
                awarded_at=award.awarded_at,
                awarded_by_user_id=int(award.awarded_by_user_id or 0),
            )
            for award in awards
        ]

    def list_minigame_award_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "participant_user_id": award.participant_user_id,
                "game_slug": award.source_key,
                "placement": award.placement,
                "points_awarded": award.points_awarded,
                "awarded_at": award.awarded_at,
            }
            for award in self.list_competition_point_awards(source_type=COMPETITION_RANKING_SOURCE_TYPE)
        ]

    def get_first_admin(self) -> Optional[User]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_app_setting(self, key: str) -> Optional[str]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?",
                (key,),
            ).fetchone()
        return str(row["setting_value"]) if row else None

    def list_app_settings(self, prefix: Optional[str] = None) -> dict[str, str]:
        sql = "SELECT setting_key, setting_value FROM app_settings"
        params: tuple[Any, ...] = ()
        if prefix is not None:
            sql += " WHERE setting_key LIKE ?"
            params = (f"{prefix}%",)
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {str(row["setting_key"]): str(row["setting_value"]) for row in rows}

    def set_app_setting(self, *, key: str, value: str, updated_at: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key)
                DO UPDATE SET setting_value = excluded.setting_value, updated_at = excluded.updated_at
                """,
                (key, value, updated_at),
            )

    def delete_app_setting(self, key: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM app_settings WHERE setting_key = ?",
                (key,),
            )

    def any_admin_exists(self) -> bool:
        return self.get_first_admin() is not None

    def ensure_admin_exists(
        self,
        *,
        username: str,
        email: str,
        password_hash: str,
        now_iso: str,
    ) -> User:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
            ).fetchone()
            if row:
                return self._row_to_user(row)

            cursor = conn.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 'admin', 1, ?, ?)
                """,
                (username, email, password_hash, now_iso, now_iso),
            )
            admin_id = int(cursor.lastrowid)
            created = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()

        if not created:
            raise RuntimeError("Failed to seed admin user")
        return self._row_to_user(created)

    def update_user_password(
        self,
        *,
        user_id: int,
        password_hash: str,
        updated_at: str,
    ) -> Optional[User]:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = ?
                WHERE id = ?
                """,
                (password_hash, updated_at, user_id),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_user(row) if row else None

    def update_registration_game_progress(
        self,
        *,
        user_id: int,
        questions_answered: int,
        guesses_used: int,
        incorrect_answers: int,
        completed: bool,
        points: float,
        completed_at: Optional[str],
        updated_at: str,
    ) -> Optional[User]:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET registration_questions_answered = ?,
                    registration_game_guesses_used = ?,
                    registration_game_incorrect_answers = ?,
                    registration_game_completed = ?,
                    registration_game_points = ?,
                    registration_game_completed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    questions_answered,
                    guesses_used,
                    incorrect_answers,
                    1 if completed else 0,
                    points,
                    completed_at,
                    updated_at,
                    user_id,
                ),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_user(row) if row else None
