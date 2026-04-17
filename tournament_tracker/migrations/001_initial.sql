CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'participant')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (username IS NOT NULL OR email IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS participant_profiles (
    user_id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    motto TEXT NOT NULL,
    photo_blob BLOB,
    photo_mime_type TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    used_by_user_id INTEGER,
    note TEXT,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (used_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_type TEXT NOT NULL,
    scheduled_at TEXT,
    scheduled_order INTEGER,
    status TEXT NOT NULL CHECK (status IN ('upcoming', 'live', 'completed')) DEFAULT 'upcoming',
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS match_sides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    side_number INTEGER NOT NULL CHECK (side_number IN (1, 2)),
    side_name TEXT,
    UNIQUE(match_id, side_number),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_side_id INTEGER NOT NULL,
    participant_user_id INTEGER NOT NULL,
    UNIQUE(match_side_id, participant_user_id),
    FOREIGN KEY (match_side_id) REFERENCES match_sides(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL UNIQUE,
    outcome TEXT NOT NULL CHECK (outcome IN ('side1_win', 'draw', 'side2_win')),
    entered_by_user_id INTEGER NOT NULL,
    entered_at TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (entered_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS doubler_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_user_id INTEGER NOT NULL UNIQUE,
    match_id INTEGER NOT NULL,
    activated_at TEXT NOT NULL,
    activated_by_user_id INTEGER NOT NULL,
    FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (activated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    related_match_id INTEGER,
    related_user_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (related_match_id) REFERENCES matches(id) ON DELETE SET NULL,
    FOREIGN KEY (related_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_match_sides_match ON match_sides(match_id);
CREATE INDEX IF NOT EXISTS idx_match_participants_side ON match_participants(match_side_id);
CREATE INDEX IF NOT EXISTS idx_match_results_match ON match_results(match_id);
CREATE INDEX IF NOT EXISTS idx_invitations_expires ON invitations(expires_at);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC);
