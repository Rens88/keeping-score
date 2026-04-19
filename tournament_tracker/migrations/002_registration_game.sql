ALTER TABLE users ADD COLUMN account_origin TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE users ADD COLUMN registration_questions_answered INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN registration_game_guesses_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN registration_game_completed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN registration_game_incorrect_answers INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN registration_game_points REAL NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN registration_game_completed_at TEXT;

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at)
VALUES ('registration_game_active', 'false', datetime('now'));

UPDATE users
SET
    registration_game_completed = 1,
    registration_game_points = 0,
    account_origin = 'legacy'
WHERE role = 'participant'
  AND account_origin = 'legacy';

CREATE INDEX IF NOT EXISTS idx_users_registration_completed
ON users(registration_game_completed);
