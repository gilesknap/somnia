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
    abs_item_id TEXT NOT NULL DEFAULT '',
    heard_to_ms INTEGER NOT NULL DEFAULT 0,
    position_ms INTEGER,
    position_seq INTEGER NOT NULL DEFAULT 0,
    position_at TEXT,
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


# Columns added after the first release. CREATE TABLE IF NOT EXISTS silently
# leaves an existing table alone, so new columns have to be added by hand.
_ADDED_COLUMNS = (
    ("books", "abs_item_id", "TEXT NOT NULL DEFAULT ''"),
    # The furthest point ever reached, which is not the same as where they are
    # now: the agent can move them backwards, and doing so must not shrink what
    # the spoiler guard is willing to search.
    ("books", "heard_to_ms", "INTEGER NOT NULL DEFAULT 0"),
    # Where they are now, as against how far they have ever got. Nullable on
    # purpose: "never started" and "at the very beginning" are different answers
    # to "where am I?", and only NULL can give the first one.
    ("books", "position_ms", "INTEGER"),
    # How many times the agent has moved this book. Not a write counter and not
    # a timestamp: the page's own saves leave it alone. That asymmetry is what
    # lets a refused save be applied unconditionally — a higher number can only
    # be a move the page has not seen — so a dropped reply costs nothing instead
    # of dragging the listener backwards fifteen seconds later.
    ("books", "position_seq", "INTEGER NOT NULL DEFAULT 0"),
    # Which book to open on a cold launch. Asking someone at 2am which book they
    # were listening to is the question this whole project exists to not ask.
    # It has a second job: it says when the last report was taken, which is the
    # ceiling on how much playback the next one may claim to have done since.
    # No default: sqlite refuses to add a column whose default is not constant,
    # so datetime('now') would fail on every database that already has books in
    # it. Every write that touches position_ms sets this explicitly instead.
    ("books", "position_at", "TEXT"),
    # How many chapters this book HAS, as against how many have been rendered —
    # which is the count of rows in `chapters`. Without it there is no honest
    # denominator anywhere: nothing could say "chapter 4 of 39", and the page
    # could not tell the end of the book from the end of what has been rendered
    # of it so far. Written the moment the parse finishes, because parsing is
    # minutes and rendering is hours, and the number is wanted for all of them.
    #
    # total_ms cannot stand in for it. While a book renders, total_ms means "how
    # much audio exists so far" and tools.get_position leans on it meaning
    # exactly that, so a book's length in milliseconds is simply not known until
    # the last chapter is encoded.
    #
    # 0 means nobody ever wrote it down, which is true of every book on the VPS
    # that was rendered before this column existed — not a book of no chapters,
    # which is not a thing. Anything reading it has to treat 0 as "don't know".
    ("books", "chapters_total", "INTEGER NOT NULL DEFAULT 0"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, decl in _ADDED_COLUMNS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def connect(db_path: Path, *, cross_thread: bool = False) -> sqlite3.Connection:
    """Open (creating if needed) the somnia database.

    ``cross_thread`` lifts sqlite's same-thread check for the server, whose
    request handlers run in a threadpool. The caller then owes it serialised
    access — :class:`somnia.server.Conversations` holds a lock for exactly this.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=not cross_thread)
    conn.row_factory = sqlite3.Row
    # Two connections now open this file — a turn's, and the player's fast lane
    # — and `somnia add` is a third process entirely. WAL so a reader never
    # blocks on the writer, and a timeout so a collision waits instead of
    # raising "database is locked" at 2am while a book renders. Order matters:
    # switching journal mode needs a brief exclusive lock, and the renderer may
    # be holding the file.
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript(_SCHEMA)
    conn.executescript(_VEC_SCHEMA)
    with conn:
        _migrate(conn)
    return conn
