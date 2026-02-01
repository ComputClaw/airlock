"""SQLite database layer for Airlock."""

import os
from pathlib import Path

import aiosqlite

DATA_DIR = Path(os.environ.get("AIRLOCK_DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "airlock.db"

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    encrypted_value BLOB,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    description TEXT DEFAULT '',
    locked INTEGER DEFAULT 0,
    expires_at TEXT,
    revoked INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS profile_credentials (
    profile_id TEXT NOT NULL REFERENCES profiles(id),
    credential_id TEXT NOT NULL REFERENCES credentials(id),
    PRIMARY KEY (profile_id, credential_id)
);

CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(id),
    script TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    error TEXT,
    llm_request TEXT,
    execution_time_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS admin (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


async def init_db() -> aiosqlite.Connection:
    """Initialize the database: create data dir, open connection, create tables."""
    global _db
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript(SCHEMA)
    await _db.commit()
    return _db


async def get_db() -> aiosqlite.Connection:
    """Return the active database connection."""
    if _db is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
