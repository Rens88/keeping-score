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
);

CREATE INDEX IF NOT EXISTS idx_competition_point_awards_source
ON competition_point_awards(source_type, source_key, participant_user_id);

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
    'registration_game',
    'registration_game',
    'Registration Game',
    NULL,
    u.registration_game_points,
    COALESCE(u.registration_game_completed_at, u.updated_at, u.created_at),
    NULL
FROM users u
WHERE u.role = 'participant'
  AND u.registration_game_points > 0;

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
    'competition_ranking',
    ma.game_slug,
    REPLACE(ma.game_slug, '_', ' '),
    ma.placement,
    ma.points_awarded,
    ma.awarded_at,
    ma.awarded_by_user_id
FROM minigame_awards ma;
