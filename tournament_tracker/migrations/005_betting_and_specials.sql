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
);

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
);

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
);

CREATE INDEX IF NOT EXISTS idx_match_bets_match
ON match_bets(match_id, participant_user_id);

CREATE INDEX IF NOT EXISTS idx_match_bets_participant
ON match_bets(participant_user_id, settled_at);

CREATE INDEX IF NOT EXISTS idx_participant_specials_key
ON participant_specials(special_key, is_available, is_active);

CREATE INDEX IF NOT EXISTS idx_match_special_activations_lookup
ON match_special_activations(match_id, special_key, participant_user_id);

INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
VALUES ('catch_up_points_gap_threshold', '15', datetime('now'));

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
WHERE u.role = 'participant';

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
);
