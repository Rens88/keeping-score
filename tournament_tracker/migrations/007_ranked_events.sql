CREATE TABLE IF NOT EXISTS ranked_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    scheduled_at TEXT,
    scheduled_order INTEGER,
    status TEXT NOT NULL CHECK (status IN ('upcoming', 'live', 'completed')),
    award_scheme TEXT NOT NULL DEFAULT '5,3,1',
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ranked_event_competitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ranked_event_id INTEGER NOT NULL,
    participant_user_id INTEGER NOT NULL,
    UNIQUE(ranked_event_id, participant_user_id),
    FOREIGN KEY (ranked_event_id) REFERENCES ranked_events(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ranked_event_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ranked_event_id INTEGER NOT NULL,
    participant_user_id INTEGER NOT NULL,
    placement INTEGER NOT NULL,
    entered_at TEXT NOT NULL,
    entered_by_user_id INTEGER,
    UNIQUE(ranked_event_id, participant_user_id),
    FOREIGN KEY (ranked_event_id) REFERENCES ranked_events(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (entered_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ranked_events_status_order
ON ranked_events(status, scheduled_order, scheduled_at, id);

CREATE INDEX IF NOT EXISTS idx_ranked_event_competitors_event
ON ranked_event_competitors(ranked_event_id, participant_user_id);

CREATE INDEX IF NOT EXISTS idx_ranked_event_results_event
ON ranked_event_results(ranked_event_id, placement, participant_user_id);
