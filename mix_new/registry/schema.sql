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

CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    links_json TEXT NOT NULL,
    natural_key TEXT NOT NULL,
    published_at TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    matched_keywords_json TEXT NOT NULL,
    amendment_type TEXT,
    level TEXT,
    stage TEXT,
    topic TEXT,
    industry TEXT,
    okved_codes_json TEXT,
    act_number TEXT,
    act_date TEXT,
    referenced_acts_json TEXT,
    credibility TEXT NOT NULL,
    credibility_reasons_json TEXT,
    record_status TEXT NOT NULL,
    manual_check_status TEXT NOT NULL DEFAULT 'не проверено',
    act_text_url TEXT,
    first_seen_date TEXT NOT NULL,
    related_act_id INTEGER REFERENCES acts(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(natural_key)
);

CREATE INDEX IF NOT EXISTS idx_news_credibility ON news_items(credibility);

-- Все прочитанные статьи (а не только отобранные регуляторные): по ним
-- считаются тренды. tags_json — темы и конкуренты из trends.yml,
-- tags_version — версия словаря, по которой статья размечена.
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link TEXT NOT NULL,
    title TEXT NOT NULL,
    text TEXT,
    published_date TEXT NOT NULL,
    source_name TEXT NOT NULL,
    tags_json TEXT,
    tags_version TEXT,
    title_tokens TEXT,
    tokens_version TEXT,
    first_seen TEXT NOT NULL,
    UNIQUE(link)
);

CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(published_date);

-- Карточки трендов (вкладка «Тренды» → «Карточки трендов»): группа
-- сигналов об одном изменении и его описание. Создаются автоматически
-- после каждого запуска (pipeline/trend_cards.py), origin = 'auto'.
CREATE TABLE IF NOT EXISTS trend_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    what_changes TEXT NOT NULL DEFAULT '',
    drivers TEXT NOT NULL DEFAULT '',
    barriers TEXT NOT NULL DEFAULT '',
    consequences TEXT NOT NULL DEFAULT '',
    steeple_json TEXT NOT NULL DEFAULT '[]',
    origin TEXT NOT NULL DEFAULT 'manual',
    auto_key TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    stats_json TEXT,
    weak_evidence INTEGER NOT NULL DEFAULT 0,
    signals_hash TEXT,
    ai_model TEXT,
    ai_generated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_trend_cards_auto ON trend_cards(auto_key);

CREATE TABLE IF NOT EXISTS trend_card_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES trend_cards(id) ON DELETE CASCADE,
    link TEXT NOT NULL,
    title TEXT NOT NULL,
    published_date TEXT,
    source TEXT,
    note TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL,
    UNIQUE(card_id, link)
);
