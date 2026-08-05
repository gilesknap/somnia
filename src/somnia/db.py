"""SQLite schema and connection handling.

One database file holds everything: the Gutenberg catalog (FTS5), per-book
metadata, indexed text chunks with their audio timestamps, and the vector
index (sqlite-vec) used for semantic seek.
"""

import sqlite3
from pathlib import Path

import sqlite_vec  # type: ignore[import-untyped]

__all__ = ["EMBED_DIM", "connect"]

EMBED_DIM = 384

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS catalog USING fts5(
    gid UNINDEXED, title, authors, subjects, bookshelves, language UNINDEXED
);

CREATE TABLE IF NOT EXISTS books (
    gid INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '',
    voice TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    total_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    book_gid INTEGER NOT NULL REFERENCES books(gid),
    idx INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    audio_file TEXT NOT NULL,
    PRIMARY KEY (book_gid, idx)
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_gid INTEGER NOT NULL REFERENCES books(gid),
    chapter_idx INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_book ON chunks(book_gid, start_ms);
"""

_VEC_SCHEMA = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
    embedding float[{EMBED_DIM}]
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the somnia database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript(_SCHEMA)
    conn.executescript(_VEC_SCHEMA)
    return conn
