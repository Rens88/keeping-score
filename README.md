# Weekend Tournament Tracker (Streamlit Multipage App)

## 1. Overview
Weekend Tournament Tracker is a single Streamlit multipage app for running a group weekend tournament.

It supports two roles:
- `admin`: manages participants, invitations, schedule, results, and doubler troubleshooting
- `participant`: logs in, views standings/matches/profile, and uses one personal doubler

The same codebase supports both:
- local hosting on one laptop for users on the same Wi-Fi network
- deployment on Streamlit Community Cloud

## 2. Features

### Admin features
- Role-protected admin pages and server-side authorization checks
- Invitation generation with token expiry and one-time use
- Participant management utilities (including password reset)
- Match create/edit/delete with:
  - game type
  - 2 sides
  - one or more participants per side
  - status (`upcoming`, `live`, `completed`)
- Result entry/edit/clear
- Doubler troubleshooting (inspect, clear, force reassign for eligible matches)
- Backup/export and import/restore (full SQLite snapshot)

### Participant features
- Login (username/email + password)
- Invitation-only signup (no public self-signup)
- Profile with name, motto, photo, role, and stats
- Leaderboard with:
  - rank, photo, name, motto
  - matches played, wins/draws/losses
  - bonus points, total points
  - doubler used
- Upcoming, live, and past match views
- Personal one-time doubler activation for eligible upcoming matches

### Scoring
- Win = `4`
- Draw = `2.5`
- Loss = `1`
- Team result awards points individually to each participant on that side
- Doubler affects only the player who activated it:
  - win `8`, draw `5`, loss `2`
- Players with no completed matches are excluded from leaderboard

## Architecture notes

The app is intentionally split so business logic stays out of page files:
- `app.py` and `pages/`: Streamlit UI/routes
- `tournament_tracker/services/`: domain logic
- `tournament_tracker/repository.py`: SQLite data access layer
- `tournament_tracker/migrations/`: schema migrations
- `tournament_tracker/models.py`: typed data models
- `tournament_tracker/config.py`: environment-aware configuration

V1 persistence is SQLite. The repository/service split keeps migration to Postgres straightforward later.

## 3. Local setup

### 3.1 Prerequisites
- Python 3.10+
- pip

### 3.2 Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.3 Initialize database and admin bootstrap

Two common options:

1. Use bundled demo-state database (default local mode):
- default DB path is `demo_state/weekend_tracker_requested_demo_state.sqlite3`
- includes demo users/matches for quick start

2. Start with a fresh database:
```bash
export APP_ENV=local
export DB_PATH=data/tournament.db
export SEED_ADMIN_USERNAME=admin
export SEED_ADMIN_EMAIL=admin@weekend.local
export SEED_ADMIN_PASSWORD='replace-with-strong-password'
```

Then run:
```bash
python scripts/smoke_test.py
```

Optional demo seeding on a fresh DB:
```bash
python scripts/seed_demo_data.py
```

### 3.4 Run locally
```bash
streamlit run app.py
```

## 4. Run on local Wi-Fi (LAN mode)

The host laptop runs the app; other participants connect from phones/laptops on the same Wi-Fi.

### 4.1 Start app listening on network interface
Using helper scripts:
```bash
# macOS/Linux/WSL/Git Bash
bash scripts/run_lan.sh
```

```powershell
# Windows PowerShell
.\scripts\run_lan.ps1
```

```bat
:: Windows Command Prompt (CMD)
scripts\run_lan.bat
```
The `.bat` launcher is verbose, always pauses before the window closes, and automatically tries the next free port if the default `8501` is already in use.

Or explicit command:
```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Note:
- `.streamlit/config.toml` already contains local-friendly defaults (`0.0.0.0:8501`, headless).
- CLI flags or environment variables override those defaults when needed.

### 4.2 Find host laptop local IP
- Windows: `ipconfig`
- macOS/Linux: `ifconfig` or `ip addr`
- In this setup, the expected LAN pattern has often been `192.168.2.x`
- Both laptop and phone should usually share the same first three octets (for example `192.168.2.*`)

### 4.3 Connect from other devices
Open in browser:
```text
http://<HOST_LOCAL_IP>:8501
```

Important:
- Use the laptop's real LAN IP address, not `0.0.0.0`
- Example: `http://192.168.2.6:8501`

### 4.4 LAN caveats / troubleshooting
- Host laptop must stay on and connected to the same Wi-Fi
- Local firewall may block inbound traffic on chosen port
- Guest Wi-Fi sometimes isolates devices (client isolation)
- Ensure app listens on `0.0.0.0` (not only `127.0.0.1`)
- Port can be changed with `--server.port` or `STREAMLIT_SERVER_PORT`
- The Windows `.bat` launcher will automatically try a nearby free port when the default `8501` is already occupied
- Disable VPN on both laptop and phone while testing
- Turn off mobile data on the phone so requests stay on Wi-Fi
- If `localhost` works on the laptop but phone access fails, test with `python -m http.server 9999` to confirm whether the problem is app-specific
- If access works only when Windows Firewall is off, inspect inbound `Block` rules for Python first; they can override allow rules
- Prefer one clean Python allow rule scoped to the Private profile and local subnet instead of many overlapping rules

## 5. Deploy to Streamlit Community Cloud

### 5.1 Repository expectations
- `app.py` at repo root
- `pages/` for multipage navigation
- `requirements.txt` at repo root
- no separate app split required

### 5.2 Deployment steps
1. Push repo to GitHub
2. In Streamlit Community Cloud: **Create app**
3. Select repo/branch and set entrypoint to `app.py`
4. Add secrets in app settings (example below)
5. Deploy

### 5.3 Recommended Community Cloud secrets
```toml
APP_ENV = "cloud"
DB_PATH = "data/tournament_cloud.sqlite3"
APP_BASE_URL = "https://your-app-name.streamlit.app"
DEFAULT_INVITE_EXPIRY_HOURS = "72"

# Required on first deployment to create initial admin if DB has no admin yet
SEED_ADMIN_USERNAME = "admin"
SEED_ADMIN_EMAIL = "admin@your-domain.com"
SEED_ADMIN_PASSWORD = "replace-with-strong-password"
```

### 5.4 Cloud behavior notes
- SQLite/photo data are local to the running instance filesystem and may be ephemeral
- Use admin export regularly if event data matters
- Same app works in cloud mode, but durability is limited in V1

## 6. Configuration

Use environment variables locally and Streamlit secrets in cloud.

| Key | Default | Notes |
|---|---|---|
| `APP_ENV` | `local` | `local` or `cloud`; influences default DB path |
| `DB_PATH` | `demo_state/weekend_tracker_requested_demo_state.sqlite3` in `local`, `data/tournament_cloud.sqlite3` in `cloud` | SQLite file path |
| `APP_BASE_URL` | empty | Used for invitation links |
| `DEFAULT_INVITE_EXPIRY_HOURS` | `72` | Invitation validity duration |
| `PHOTO_STORAGE_MODE` | `db_blob` | V1 uses DB blob storage |
| `PHOTO_UPLOAD_PATH` | empty | Reserved for optional filesystem photo mode |
| `SEED_ADMIN_USERNAME` | none | Required with email/password on first startup if DB has no admin |
| `SEED_ADMIN_EMAIL` | none | Required with username/password on first startup if DB has no admin |
| `SEED_ADMIN_PASSWORD` | none | Required with username/email on first startup if DB has no admin |
| `STREAMLIT_SERVER_ADDRESS` | `0.0.0.0` (helper script) | LAN run helper input |
| `STREAMLIT_SERVER_PORT` | `8501` (helper script) | LAN run helper input |

Bootstrap rule:
- If DB already has an admin, seed values are optional.
- If DB has no admin, all three `SEED_ADMIN_*` values must be provided together.

## 7. Data/storage notes

- V1 database: SQLite (migrations in `tournament_tracker/migrations/`)
- Participant photos: stored as BLOBs in SQLite (simple, no extra service)
- Local mode: data persists while local DB file persists
- Community Cloud: local filesystem persistence is not guaranteed
- Backup/restore page is included for operational safety during the event

## 8. Future extensions

- Additional mechanics (betting/predictions, streak cards, extra powerups)
- Result approval workflow
- Richer match statistics per game
- Postgres repository implementation with same service layer
- Durable object storage if photo volume grows

## Included pages

- Login
- Accept invitation / create account
- Leaderboard
- Upcoming matches
- Past matches
- My profile
- Admin dashboard
- Admin participants / invitations
- Admin schedule management
- Admin result entry
- Admin backup & restore

## Smoke-test strategy

Run:
```bash
python scripts/smoke_test.py
```

This verifies:
- config loading
- repository initialization/migrations
- basic DB access through the current configured `DB_PATH`
