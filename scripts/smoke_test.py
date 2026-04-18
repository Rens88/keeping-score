from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tournament_tracker.bootstrap import initialize_repository


def main() -> None:
    config, repo = initialize_repository()
    with repo.connection() as conn:
        user_count = int(conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"])
        participant_count = int(
            conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'participant'").fetchone()["c"]
        )
        match_count = int(conn.execute("SELECT COUNT(*) AS c FROM matches").fetchone()["c"])

    print("Smoke test OK")
    print(f"APP_ENV={config.app_env}")
    print(f"DB_PATH={config.db_path}")
    print(f"users={user_count}, participants={participant_count}, matches={match_count}")


if __name__ == "__main__":
    main()
