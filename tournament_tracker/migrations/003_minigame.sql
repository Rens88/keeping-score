CREATE TABLE IF NOT EXISTS minigame_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_slug TEXT NOT NULL,
    participant_user_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    duration_seconds INTEGER NOT NULL,
    played_at TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE
);

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
);

CREATE INDEX IF NOT EXISTS idx_minigame_runs_lookup
ON minigame_runs(game_slug, participant_user_id, score DESC, played_at ASC);

CREATE INDEX IF NOT EXISTS idx_minigame_awards_lookup
ON minigame_awards(game_slug, participant_user_id);

INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
VALUES ('whack_a_mole_enabled', 'false', datetime('now'));

INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
VALUES ('whack_a_mole_opens_at', '', datetime('now'));

INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
VALUES ('whack_a_mole_deadline_at', '', datetime('now'));

INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
VALUES ('whack_a_mole_award_scheme', '5,3,1', datetime('now'));

INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
VALUES ('whack_a_mole_awards_applied_at', '', datetime('now'));
