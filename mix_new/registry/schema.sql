CREATE TABLE IF NOT EXISTS acts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    act_kind TEXT NOT NULL,
    number TEXT,
    issuing_body TEXT NOT NULL,
    adoption_date TEXT,
    publication_date TEXT,
    title TEXT NOT NULL,
    source_url TEXT,
    status TEXT NOT NULL,
    amendment_type TEXT,
    summary_bullets_json TEXT,
    okved_codes_json TEXT,
    cross_cutting INTEGER NOT NULL DEFAULT 0,
    commodity_groups_json TEXT,
    page_count INTEGER,
    discovered_date TEXT NOT NULL,
    linkage_note TEXT,
    unconfirmed_reason TEXT,
    source_name TEXT NOT NULL,
    natural_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(natural_key)
);

CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    act_id INTEGER NOT NULL REFERENCES acts(id) ON DELETE CASCADE,
    date_text TEXT NOT NULL,
    what_changes TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    act_id INTEGER NOT NULL REFERENCES acts(id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS run_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    found_count INTEGER NOT NULL DEFAULT 0,
    discarded_count INTEGER NOT NULL DEFAULT 0,
    unconfirmed_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    unreachable INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_acts_status ON acts(status);
CREATE INDEX IF NOT EXISTS idx_journal_run ON run_journal(run_id);
