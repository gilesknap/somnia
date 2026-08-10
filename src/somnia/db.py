"""SQLite schema and connection handling.

One database file holds everything: the Gutenberg catalog (FTS5), per-book
metadata, indexed text chunks with their audio timestamps, the vector index
(sqlite-vec) used for semantic seek, and the ingest queue — which is here
rather than in a lock file or a socket because sqlite is the one thing every
process in somnia already shares, and a render's progress has to be readable
from a process that is not the one doing it.
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

-- Every word the catalog has ever been asked to index, with how many books it
-- appears in. FTS5 ships this: it is a read-only view over the index that is
-- already there, so it costs one statement, no rows of its own, and nothing at
-- import time — it cannot go stale because there is nothing in it to update.
--
-- It exists so that a search can tell "this word is not in the library" from
-- "these words are not in one book together". Without it, one misspelling in a
-- query vetoes the whole of it under FTS5's implicit AND, and searching for
-- "Mary Shelly's Frankenstein" answers that the catalog holds nothing — about
-- a library with four editions of it. See somnia.catalog.search_catalog.
CREATE VIRTUAL TABLE IF NOT EXISTS catalog_vocab USING fts5vocab(catalog, row);

-- Where to fetch a catalogued book's text, for the books whose address cannot
-- be worked out from their id. Project Gutenberg's own can: every one of them
-- is at cache/epub/<gid>/pg<gid>.html, which is why somnia has never needed
-- this table before. Project Gutenberg Australia's cannot — its files are named
-- after the month they were posted — so the address is written down at import.
--
-- A missing row therefore means Gutenberg proper, which is exactly what every
-- database that existed before this table did say, and no backfill is needed.
CREATE TABLE IF NOT EXISTS catalog_urls (
    gid INTEGER PRIMARY KEY,
    url TEXT NOT NULL
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
    -- Said here as well as in _ADDED_COLUMNS, which is how the five columns
    -- above it are handled and how this one was not. Nothing was broken by the
    -- omission — the rule below adds it to a table that already exists, and a
    -- table created by this statement is such a table by the time it runs — but
    -- it left a fresh database whose books table is only correct because a
    -- migration ran over it, and this file's own schema disagreeing with the
    -- one somnia actually opens.
    chapters_total INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    renamed_at TEXT
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

-- A whole table, not a column, so CREATE TABLE IF NOT EXISTS is the right tool
-- and this really does reach the live database on the VPS the next time
-- connect() runs. The _ADDED_COLUMNS rule below binds columns on tables that
-- already exist, where the same statement quietly does nothing.
--
-- Two indexes, and the second one is the feature. `queue_live` is partial, so
-- it constrains only rows that are waiting or running: one live job per book,
-- enforced by the database rather than by a check-then-insert that two presses
-- a millisecond apart would both pass. A book may appear here as many times as
-- it likes over its life — every render that failed or was stopped stays as the
-- record of itself — and only ever once at a time.
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gid INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    authors TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'queued',
    cancel INTEGER NOT NULL DEFAULT 0,
    lease TEXT NOT NULL DEFAULT '',
    pid INTEGER NOT NULL DEFAULT 0,
    beat_at TEXT,
    chapter_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    voice TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    ended_at TEXT
);
CREATE INDEX IF NOT EXISTS queue_state ON queue(state, id);
CREATE UNIQUE INDEX IF NOT EXISTS queue_live ON queue(gid)
    WHERE state IN ('queued', 'rendering');
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
    # When the reader said they were done with this book, which is a fact about
    # them and not about the render. `status` already holds the render's view —
    # pending, rendering, done — and overloading it was the obvious thing and
    # the wrong one: a book somebody has finished reading and a book that was
    # never made would become the same row, and the shelf could not tell a book
    # it should stop offering from one it never had anything to offer of.
    #
    # A date rather than a flag, because the only question anybody asks of it
    # after the first one is "when", and a column that already answers it costs
    # nothing over a 0/1 that would then need a second one beside it.
    #
    # NULL means still being read, which is every book somnia has ever had
    # until somebody says otherwise. No default, for the reason position_at
    # gives above: sqlite refuses a non-constant default on ADD COLUMN, so
    # whoever marks a book finished writes datetime('now') itself.
    ("books", "finished_at", "TEXT"),
    # When a person last said what this book is called, which is the one thing
    # that has to outrank the catalog. `title` and `authors` are written by
    # every render out of the catalog row, so a book renamed on the page and
    # then rendered again — the ordinary way to restart a render that died —
    # came back under the name somebody had just changed. The alternative was
    # to document the rename as lost, which is a screen offering an edit it
    # quietly takes away again.
    #
    # A date rather than a flag, for the reason finished_at is one: the second
    # question anybody asks of it is when, and the upsert only ever asks
    # whether it is NULL. It is not a copy of the name and nothing reads it
    # back — the name lives in `title`, where it always did.
    #
    # NULL means nobody has renamed this book, which is every book somnia has
    # rendered so far, so the upsert goes on doing exactly what it did until
    # somebody edits something. No default, as above: sqlite refuses a
    # non-constant one on ADD COLUMN.
    ("books", "renamed_at", "TEXT"),
    # Which voice this book was asked for in, held on the request rather than
    # taken from whatever the renderer's environment happened to say hours
    # later. The choice is made in front of the person making it and has to
    # survive the wait: the worker that eventually picks the book up is a
    # different process, started by systemd, that has never seen the page.
    #
    # Empty means "whatever the renderer is set to", which is every row
    # submitted before this column existed and every one the agent adds by
    # voice at 2am — not a real conversation to have half asleep.
    ("queue", "voice", "TEXT NOT NULL DEFAULT ''"),
    # Something worth saying about a render that is going perfectly well. The
    # only free text a live row had was `error`, which is read as "this book
    # failed" everywhere it is drawn, and a parse that came out looking wrong is
    # not a failure — the render can and does carry on.
    #
    # There is one thing in here so far: the sentence
    # :func:`somnia.gutenberg.implausible_shape` writes when a book parses into
    # a handful of chapters hours long. Parsing is minutes and rendering is
    # hours, so this is the difference between somebody seeing it while it is
    # still worth stopping and discovering it the next night with a four-hour
    # audio file in front of them.
    ("queue", "note", "TEXT NOT NULL DEFAULT ''"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, decl in _ADDED_COLUMNS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    # And then write down what the older books never got the chance to. A book
    # rendered before that column existed has a 0 in it, which everything
    # reading it correctly treats as "don't know" — so the player says
    # `chapter 4` where it should say `chapter 4 of 49`, and the one line on
    # that screen saying how much book is left says nothing at all. On the box
    # this runs on that was the book actually being listened to.
    #
    # Only for a book that has finished rendering. While one is still being
    # read the chapter rows are how many exist *so far*, so counting them would
    # write a total that is wrong and then stop looking wrong — a denominator
    # that quietly settles two chapters short is worse than the honest 0,
    # because nothing downstream would ever question it again.
    #
    # Idempotent, and it runs on every open: the guard is `chapters_total = 0`,
    # so a book that has a real total is never recounted and a book still
    # rendering is picked up by this the first time it is opened after it
    # finishes.
    conn.execute(
        "UPDATE books SET chapters_total = ("
        "  SELECT COUNT(*) FROM chapters WHERE chapters.book_gid = books.gid"
        ") WHERE status = 'done' AND chapters_total = 0"
        "  AND EXISTS (SELECT 1 FROM chapters WHERE chapters.book_gid = books.gid)"
    )

    _repair(conn)


# One-off repairs of data already written, as against the migrations above,
# which are idempotent by construction and cheap to re-check on every open.
# These are neither, so they are run once and recorded in sqlite's own
# `user_version` — a field made for exactly this, and cheaper than a table.
_REPAIRED_TO = 1


def _repair(conn: sqlite3.Connection) -> None:
    """Give back their real names the books that kept Gutenberg's header line.

    Ingest used to take the book's name from the HTML `<title>`, which for a
    good part of the corpus reads "The Project Gutenberg eBook of Dracula, by
    Bram Stoker." — so that is what the shelf said, wrapping to three lines on
    the one screen whose whole job is recognising a book you own in the dark.
    Ingest asks the catalog now, but a book already rendered keeps the name it
    was given, and only this puts it right.

    **Run once, not on every open.** The tempting version of this is guarded by
    `books.title <> catalog.title` and left to run forever, which is wrong in a
    way that only shows up at size: `catalog` is FTS5 with an UNINDEXED gid, so
    proving a title *matches* means scanning all 81,893 rows, once per book.
    Measured at 300ms for five books and 11.7 seconds for two hundred — on every
    CLI call and every server start, to do nothing.

    Nothing is written when the catalog is empty, and the version is not moved
    on either: a box that renders a book before it first runs `catalog-update`
    would otherwise have this marked done while the name it needed was still
    unknown, and nothing would ever come back for it.
    """
    if conn.execute("PRAGMA user_version").fetchone()[0] >= _REPAIRED_TO:
        return
    if conn.execute("SELECT 1 FROM catalog LIMIT 1").fetchone() is None:
        return

    # No CAST, though catalog.gid is text and books.gid is an INTEGER primary
    # key: comparing them applies the integer affinity of the column that has
    # one, so '45839' meets 45839. Checked rather than assumed — every spelling
    # of this join returns the same rows.
    #
    # `c.title <> ''` says the same thing as ingest's `if row and row["title"]`,
    # which is the point: the two ways a book can be named must not disagree
    # about what counts as a name. No row in either published list can reach
    # here empty — the CSV import drops a row with no Title and the Australian
    # index cannot produce one — so this defends against nothing today. It is
    # here because the alternative, if that ever stops being true, is a book
    # silently losing the name it had.
    conn.execute(
        "UPDATE books SET title = ("
        "  SELECT c.title FROM catalog c WHERE c.gid = books.gid AND c.title <> ''"
        ") WHERE EXISTS ("
        "  SELECT 1 FROM catalog c WHERE c.gid = books.gid AND c.title <> ''"
        "    AND c.title <> books.title"
        ")"
    )
    conn.execute(f"PRAGMA user_version = {_REPAIRED_TO}")


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
