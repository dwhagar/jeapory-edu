#!/usr/bin/env python3
"""
Shared SQLite helpers for the Jeopardy game.

Both init_db.py (offline database setup / seeding) and server.py (the
running game server) need to open a database, apply schema.sql, create a
blank database with default teams, and read/write simple key-value game
settings. This module holds that logic in one place instead of duplicating
it across the two scripts.
"""
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"

# Database filenames may only use letters, numbers, spaces, - and _, so a
# sanitized name is always safe to use directly as a filesystem path (no
# path traversal, no characters that would need escaping).
DB_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{1,64}$")


def sanitize_db_name(name):
    """Normalize a user-supplied database name to a safe "<name>.db" filename.

    Appends the .db extension if missing and validates the stem against
    DB_NAME_RE. Raises ValueError if the name is empty or contains
    disallowed characters.
    """
    name = (name or "").strip()
    if not name.lower().endswith(".db"):
        name = f"{name}.db"
    stem = name[:-3]
    if not DB_NAME_RE.match(stem):
        raise ValueError(
            "Database names may only use letters, numbers, spaces, - and _ (1-64 characters)"
        )
    return name


def list_db_files(directory):
    """Return the sorted filenames of every .db file in `directory`."""
    return sorted(p.name for p in Path(directory).glob("*.db"))


def connect(path):
    """Open a sqlite3 connection to `path` configured the way the app
    expects everywhere: dict-like row access (sqlite3.Row) and foreign key
    enforcement (needed for the questions -> categories ON DELETE CASCADE)."""
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def build_schema(conn, schema_path=SCHEMA_PATH):
    """Create any missing tables/indexes by running schema.sql.

    Uses `CREATE TABLE IF NOT EXISTS`, so this is safe to call on a
    database that already has data.
    """
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.commit()


def wipe(conn):
    """Drop all game tables so the schema and data can be rebuilt from scratch."""
    conn.executescript("""
        DROP TABLE IF EXISTS questions;
        DROP TABLE IF EXISTS categories;
        DROP TABLE IF EXISTS teams;
        DROP TABLE IF EXISTS game_meta;
    """)
    conn.commit()


def is_empty(conn):
    """Return True if the categories table has no rows (a freshly created database)."""
    cur = conn.execute("SELECT COUNT(*) FROM categories")
    return cur.fetchone()[0] == 0


def insert_default_teams(conn):
    """Insert the standard 'Team 1' / 'Team 2' rows (score 0) used whenever
    a database's teams are reset to a blank starting state. Does not commit."""
    conn.execute("INSERT INTO teams (name, score, position) VALUES ('Team 1', 0, 0)")
    conn.execute("INSERT INTO teams (name, score, position) VALUES ('Team 2', 0, 1)")


def get_meta(conn, key, default=None):
    """Fetch a single key/value setting from the game_meta table (e.g.
    "current_round"), or `default` if it hasn't been set."""
    row = conn.execute("SELECT value FROM game_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    """Upsert a key/value setting into the game_meta table. Does not commit;
    the caller is responsible for committing the transaction."""
    conn.execute(
        "INSERT INTO game_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def row_to_dict(row):
    """Convert a sqlite3.Row into a plain dict with every column, unfiltered."""
    return {k: row[k] for k in row.keys()}


def ensure_db_at(path, schema_path=SCHEMA_PATH):
    """Create schema + default teams + current_round=1 at `path` if it
    doesn't already exist. No-op if the file is already there."""
    path = Path(path)
    if path.exists():
        return
    conn = connect(path)
    try:
        build_schema(conn, schema_path)
        set_meta(conn, "current_round", "1")
        insert_default_teams(conn)
        conn.commit()
    finally:
        conn.close()
