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
    DoublerActivation,
    Invitation,
    InvitationDisplay,
    Match,
    MatchResult,
    ParticipantProfile,
    User,
    UserWithProfile,
)


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
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.username,
                    u.email,
                    u.role,
                    u.is_active,
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
        )

    def list_participants(self) -> list[UserWithProfile]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.username,
                    u.email,
                    u.role,
                    u.is_active,
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
            )
            for row in rows
        ]

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
                INSERT INTO users (username, email, password_hash, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 'participant', 1, ?, ?)
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
            FROM doubler_activations
            WHERE match_id IN ({placeholders})
        """
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(match_ids)).fetchall()
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
                INSERT INTO doubler_activations (
                    participant_user_id,
                    match_id,
                    activated_at,
                    activated_by_user_id
                )
                VALUES (?, ?, ?, ?)
                """,
                (participant_user_id, match_id, now_iso, activated_by_user_id),
            )
            activation_id = int(cursor.lastrowid)
            row = conn.execute(
                "SELECT * FROM doubler_activations WHERE id = ?",
                (activation_id,),
            ).fetchone()

        if not row:
            raise RuntimeError("Failed to create doubler activation")
        return self._row_to_doubler_activation(row)

    def get_doubler_activation(self, participant_user_id: int) -> Optional[DoublerActivation]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM doubler_activations WHERE participant_user_id = ?",
                (participant_user_id,),
            ).fetchone()
        return self._row_to_doubler_activation(row) if row else None

    def delete_doubler_activation(self, participant_user_id: int) -> None:
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM doubler_activations WHERE participant_user_id = ?",
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
                FROM doubler_activations da
                LEFT JOIN participant_profiles pp ON pp.user_id = da.participant_user_id
                LEFT JOIN matches m ON m.id = da.match_id
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
        sql = f"""
            SELECT
                u.id AS user_id,
                u.username,
                u.email,
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

    def get_first_admin(self) -> Optional[User]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
            ).fetchone()
        return self._row_to_user(row) if row else None

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
