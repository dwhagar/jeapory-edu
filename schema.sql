-- Jeopardy game database schema

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0
);

-- round: 1 = Jeopardy, 2 = Double Jeopardy, 3 = Final Jeopardy
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    value INTEGER NOT NULL DEFAULT 100,
    position INTEGER NOT NULL DEFAULT 0,
    question_text TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT '',
    is_daily_double INTEGER NOT NULL DEFAULT 0,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS game_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_categories_round ON categories(round);
CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category_id);
