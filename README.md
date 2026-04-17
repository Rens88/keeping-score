# Weekend Tournament Tracker (Streamlit MVP)

Production-ready V1 Streamlit app for a weekend group tournament (14 participants) with:
- app-managed authentication (`admin` and `participant` roles)
- invitation-only participant onboarding
- schedule and result management for head-to-head matches
- leaderboard with per-player points and one-time individual doubler mechanic
- SQLite-backed storage with migration files for clean V1 deployment

## Tech choices
- **Framework:** Streamlit multipage app
- **Backend/Persistence:** SQLite (`data/tournament.db`)
- **Password hashing:** PBKDF2-HMAC-SHA256 (salted, high iteration count)
- **Photo storage (V1 choice):** participant photos are stored as **BLOBs in SQLite**
  - Why: no extra storage service required, deployment-friendly for MVP
  - Tradeoff: on Streamlit Community Cloud, local file storage (including SQLite files) is **not guaranteed to persist**
- **Branding:** Utrecht Cangeroes inspired visual theme, including logo and dynamic hero header media

## Features included

### Authentication and roles
- Login with username/email + password
- Role-based access:
  - participant pages require login
  - admin pages enforce server-side `require_admin()` checks
- Seeded first admin account via environment variables or Streamlit secrets

### Invitation onboarding
- Admins generate one-time invitation tokens
- Token validation checks:
  - invalid token
  - expired token
  - already used token
- Invitation signup requires:
  - name
  - motto
  - photo upload
  - username or email + password

### Admin capabilities
- Create, update, delete matches
- Set game type, side composition (multi-player sides supported), status
- Enter/edit/clear match results
- Export full app state (admin-only)
- Import full app state (admin-only, full overwrite)
- Doubler troubleshooting controls:
  - clear used doubler
  - force reassign doubler to an eligible upcoming match

### Participant capabilities
- View leaderboard
- View upcoming/live/completed matches
- View participant directory with photo + motto
- View own profile and stats
- Activate own one-time doubler on eligible upcoming matches

### Scoring and doubler
- Win: `4`
- Draw: `2.5`
- Loss: `1`
- Team result gives all teammates same base result points
- Doubler applies **only** to that player in that match:
  - win `8`, draw `5`, loss `2`
- Players with no completed matches are excluded from leaderboard

## Project structure

```text
.
├── app.py
├── pages/
│   ├── 01_Login.py
│   ├── 02_Accept_Invitation.py
│   ├── 03_Leaderboard.py
│   ├── 04_Upcoming_Matches.py
│   ├── 05_Past_Matches.py
│   ├── 06_My_Profile.py
│   ├── 07_Admin_Dashboard.py
│   ├── 08_Admin_Participants_Invitations.py
│   ├── 09_Admin_Schedule.py
│   ├── 10_Admin_Results.py
│   └── 11_Admin_Backup_Restore.py
├── assets/
│   └── deocration/
│       ├── your-image.jpg
│       └── your-video.mp4
├── tournament_tracker/
│   ├── bootstrap.py
│   ├── branding.py
│   ├── config.py
│   ├── models.py
│   ├── repository.py
│   ├── security.py
│   ├── session.py
│   ├── ui.py
│   ├── migrations/
│   │   └── 001_initial.sql
│   └── services/
├── scripts/
│   └── seed_demo_data.py
└── requirements.txt
```

## Configuration

Set via environment variables or Streamlit secrets:

- `DB_PATH` (default: `data/tournament.db`)
- `APP_BASE_URL` (optional, used to render invitation links)
- `DEFAULT_INVITE_EXPIRY_HOURS` (default: `72`)
- `SEED_ADMIN_USERNAME` (default: `admin`)
- `SEED_ADMIN_EMAIL` (default: `admin@example.com`)
- `SEED_ADMIN_PASSWORD` (default: `change-me-now`) **set this in real use**

Example `.streamlit/secrets.toml`:

```toml
SEED_ADMIN_USERNAME = "admin"
SEED_ADMIN_EMAIL = "admin@weekend.local"
SEED_ADMIN_PASSWORD = "replace-with-strong-password"
DB_PATH = "data/tournament.db"
APP_BASE_URL = "https://your-app-name.streamlit.app"
DEFAULT_INVITE_EXPIRY_HOURS = "72"
```

## Local run

1. Create virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run app from the repository root:

```bash
streamlit run app.py
```

3. Optional: seed demo participants and matches:

```bash
python scripts/seed_demo_data.py
```

Demo participant password from seed script: `demo-pass-123`

### Header media (image + mp4)

The app header can randomly show either an image or an mp4 video.

Put files in:
- `assets/deocration`

Supported header media formats:
- images: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`
- video: `.mp4`

If no local media is found, a remote Utrecht Cangeroes fallback image is shown.

## Streamlit Community Cloud deployment

1. Push this repo to GitHub.
2. In Streamlit Community Cloud, click **Create app** and select repo/branch with `app.py` as entrypoint.
3. Add secrets in app settings (same keys as above, especially `SEED_ADMIN_PASSWORD`).
4. Ensure `requirements.txt` is in repo root.
5. Deploy.

Important for V1 on Community Cloud:
- `data/tournament.db` is local file storage and may be deleted by the platform.
- Use this setup for weekend/MVP use only.
- For reliable long-term persistence, switch to Postgres (or another external DB) and object storage for photos.

Reference docs:
- Deploy overview: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app
- App dependencies: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- File organization: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization
- Secrets management: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- Local SQLite persistence note: https://docs.streamlit.io/develop/concepts/connections/connecting-to-data

## Admin export and import (full state)

Use `Admin -> Backup & Restore`:
- **Export** downloads a full database snapshot (`.sqlite3`) containing everything:
  - users, roles, password hashes
  - participant profiles and photos
  - invitations
  - matches, teams, participants
  - results and doubler activations
  - activity log
- **Import** replaces the entire current state with the uploaded snapshot.

Notes:
- Import is destructive (full overwrite).
- Keep backup files secure, because they contain sensitive authentication data (hashed passwords).
- After import, admins are logged out and must log in again.

## Migrations strategy (V1)

- SQL migrations are stored in `tournament_tracker/migrations/*.sql`.
- On startup, the app applies unapplied migrations in filename order.
- Applied files are tracked in `schema_migrations`.

This keeps V1 simple while making schema evolution explicit.

## Core schema

V1 tables:
- `users`
- `participant_profiles`
- `invitations`
- `matches`
- `match_sides`
- `match_participants`
- `match_results`
- `doubler_activations`
- `activity_log`

## Security notes

- Passwords are never stored in plaintext.
- Invitation tokens are stored hashed (SHA-256), not raw.
- Admin pages enforce role checks server-side.

## Future extensions

- Swap SQLite repository for Postgres-backed repository implementation
- Durable media storage (S3/GCS or object store)
- Additional mechanics (betting, extra power cards, streak bonuses)
- Match-specific score details (sets/goals/rounds)
- Public spectator view with read-only mode
