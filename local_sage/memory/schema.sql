-- Schema for local-sage session memory database.
-- All tables use IF NOT EXISTS so this script is safe to run on an existing database.

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    repo_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    file_path TEXT NOT NULL,
    patch TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts_assumed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    symbol_id TEXT NOT NULL,
    contract_yaml TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    passed INTEGER NOT NULL,
    failures TEXT,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    description TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    description TEXT NOT NULL,
    rationale TEXT,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    written_at TEXT NOT NULL
);
