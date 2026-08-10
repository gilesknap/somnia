"""Opening a database that was made by an older somnia.

There is exactly one database that matters and it is on the VPS, with books and
listening positions in it. Every column added after the first release has to
arrive by ALTER, because ``CREATE TABLE IF NOT EXISTS`` looks at an existing
table and does nothing at all — the failure mode being a column that exists on
every developer's machine and on nobody's real one.
"""

import sqlite3
from pathlib import Path

from somnia.catalog import update_catalog
from somnia.db import connect

# The books table as it stood before this feature, written out longhand rather
# than imported: the point of the test is that a database somnia is not looking
# at any more can still be opened, so it must not be built from today's schema.
_OLD_SCHEMA = """
CREATE TABLE books (
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
"""


def test_a_database_from_before_this_feature_gains_the_chapter_count(
    tmp_path: Path,
) -> None:
    """And the book in it is left exactly as it was found.

    A migration that disturbed a books row would be the same bug the upsert was
    written to fix, arriving by another door: the position, the count of moves
    and the high-water mark are what somebody's night is made of.
    """
    db_path = tmp_path / "old.db"
    old = sqlite3.connect(db_path)
    old.executescript(_OLD_SCHEMA)
    old.execute(
        "INSERT INTO books (gid, title, voice, status, total_ms, position_ms,"
        " position_seq, position_at, heard_to_ms) VALUES (271, 'Black Beauty',"
        " 'af_heart', 'done', 900000, 300000, 3, '2026-08-05 23:40:00', 250000)"
    )
    old.commit()
    old.close()

    conn = connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM books WHERE gid = 271").fetchone()
    finally:
        conn.close()

    # Nothing was written down about this book's chapters before now, and 0 is
    # how it says so — not a book of no chapters, which is not a thing.
    assert row["chapters_total"] == 0
    assert (row["position_ms"], row["position_seq"]) == (300_000, 3)
    assert (row["position_at"], row["heard_to_ms"]) == ("2026-08-05 23:40:00", 250_000)
    assert (row["status"], row["total_ms"]) == ("done", 900_000)


def test_a_database_from_before_this_feature_says_nothing_has_been_finished(
    tmp_path: Path,
) -> None:
    """Which is the truth about every book that predates the column.

    NULL and not a date, and not a 0 either: nobody has ever said they were
    done with these books, and a migration that guessed — from `status`, say,
    which is the render's word and not the reader's — would take a shelf of
    books somebody is half way through and file the lot of them as read.
    """
    db_path = tmp_path / "old.db"
    old = sqlite3.connect(db_path)
    old.executescript(_OLD_SCHEMA)
    old.execute(
        "INSERT INTO books (gid, title, voice, status, total_ms) VALUES"
        " (271, 'Black Beauty', 'af_heart', 'done', 900000)"
    )
    old.commit()
    old.close()

    conn = connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM books WHERE gid = 271").fetchone()
    finally:
        conn.close()

    assert row["finished_at"] is None


def test_a_finished_book_gets_its_chapter_count_written_from_its_chapters(
    tmp_path: Path,
) -> None:
    """The column arriving empty is only half a fix.

    Every book on the VPS that was rendered before it existed carries a 0, and
    0 correctly means "don't know" everywhere it is read — so the player says
    `chapter 4` and drops the only line on that screen saying how much book is
    left. On the box this runs on that was the book actually being listened to:
    Black Beauty, 49 chapters on disk, 0 written down.

    Counting them is safe for a book that has finished and only for one. While
    a book renders, its chapter rows are how many exist *so far*, so a total
    counted then would be wrong and would then stop looking wrong — a
    denominator that quietly settles two chapters short is worse than an honest
    0, because nothing downstream would question it again.
    """
    db_path = tmp_path / "somnia.db"
    old = sqlite3.connect(db_path)
    old.executescript(_OLD_SCHEMA)
    old.executescript(
        "CREATE TABLE chapters ("
        " book_gid INTEGER NOT NULL, idx INTEGER NOT NULL, title TEXT NOT NULL,"
        " start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,"
        " audio_file TEXT NOT NULL, PRIMARY KEY (book_gid, idx))"
    )
    old.execute(
        "INSERT INTO books (gid, title, voice, status, total_ms) VALUES"
        " (271, 'Black Beauty', 'af_heart', 'done', 900000)"
    )
    # Still being read: two chapters of it exist, and nobody knows how many it
    # will end up with.
    old.execute(
        "INSERT INTO books (gid, title, voice, status, total_ms) VALUES"
        " (999, 'Dracula', 'af_heart', 'rendering', 40000)"
    )
    for gid, count in ((271, 3), (999, 2)):
        for idx in range(count):
            old.execute(
                "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
                " audio_file) VALUES (?, ?, 'a chapter', 0, 1000, 'x.opus')",
                (gid, idx),
            )
    old.commit()
    old.close()

    conn = connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        totals = {
            r["gid"]: r["chapters_total"]
            for r in conn.execute("SELECT gid, chapters_total FROM books")
        }
    finally:
        conn.close()

    assert totals == {271: 3, 999: 0}


def test_a_book_that_already_knows_its_total_is_never_recounted(
    tmp_path: Path,
) -> None:
    """The backfill runs on every open, so it has to be idempotent in the one
    way that matters: a book whose real total is larger than the chapters on
    disk must keep it. That is every book between "the text was parsed" and
    "the last chapter was encoded", and overwriting it there would walk the
    denominator backwards while somebody watched.
    """
    db_path = tmp_path / "somnia.db"
    old = sqlite3.connect(db_path)
    old.executescript(_OLD_SCHEMA)
    old.executescript(
        "CREATE TABLE chapters ("
        " book_gid INTEGER NOT NULL, idx INTEGER NOT NULL, title TEXT NOT NULL,"
        " start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,"
        " audio_file TEXT NOT NULL, PRIMARY KEY (book_gid, idx))"
    )
    old.execute(
        "INSERT INTO books (gid, title, voice, status, total_ms) VALUES"
        " (271, 'Black Beauty', 'af_heart', 'done', 900000)"
    )
    old.execute(
        "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
        " audio_file) VALUES (271, 0, 'a chapter', 0, 1000, 'x.opus')"
    )
    old.commit()
    old.close()

    # First open fills it in from the one chapter on disk.
    connect(db_path).close()
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE books SET chapters_total = 49 WHERE gid = 271")
    conn.commit()
    conn.close()

    # Second open leaves the real total alone rather than counting again.
    conn = connect(db_path)
    try:
        total = conn.execute(
            "SELECT chapters_total FROM books WHERE gid = 271"
        ).fetchone()[0]
    finally:
        conn.close()
    assert total == 49


# --- the books that kept Gutenberg's header line ----------------------------

_CATALOG_CSV = """\
Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves
45839,Text,2021,Dracula,en,"Stoker, Bram",Horror,PR,
271,Text,2006,Black Beauty,en,"Sewell, Anna",Horses,PZ,
"""

_SCRAPED = "The Project Gutenberg eBook of Dracula, by Bram Stoker."


def _rendered(conn: sqlite3.Connection, gid: int, title: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO books (gid, title, voice) VALUES (?, ?, 'af_heart')",
            (gid, title),
        )


def _title(conn: sqlite3.Connection, gid: int) -> str:
    return str(
        conn.execute("SELECT title FROM books WHERE gid = ?", (gid,)).fetchone()[
            "title"
        ]
    )


def test_a_book_already_rendered_gets_its_real_name_back(tmp_path: Path) -> None:
    """The fix to ingest only helps books added after it; this is the rest."""
    path = tmp_path / "old.db"
    conn = connect(path)
    update_catalog(conn, csv_text=_CATALOG_CSV, index_text="")
    _rendered(conn, 45839, _SCRAPED)
    conn.close()

    conn = connect(path)
    try:
        assert _title(conn, 45839) == "Dracula"
    finally:
        conn.close()


def test_the_repair_runs_once_and_then_stops_looking(tmp_path: Path) -> None:
    """Proving a title *matches* means scanning every row of an FTS5 table with
    an UNINDEXED gid, once per book — 11.7 seconds at two hundred books, on
    every CLI call, to do nothing. So it is recorded and never repeated."""
    path = tmp_path / "once.db"
    conn = connect(path)
    update_catalog(conn, csv_text=_CATALOG_CSV, index_text="")
    _rendered(conn, 45839, _SCRAPED)
    conn.close()

    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 1
    # A name somebody chose after the repair ran is theirs to keep.
    with conn:
        conn.execute("UPDATE books SET title = 'Renamed' WHERE gid = 45839")
    conn.close()

    conn = connect(path)
    try:
        assert _title(conn, 45839) == "Renamed"
    finally:
        conn.close()


def test_a_book_the_catalog_does_not_have_is_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "unknown.db"
    conn = connect(path)
    update_catalog(conn, csv_text=_CATALOG_CSV, index_text="")
    _rendered(conn, 999999, "Only The File Knows")
    conn.close()

    conn = connect(path)
    try:
        assert _title(conn, 999999) == "Only The File Knows"
    finally:
        conn.close()


def test_an_empty_catalog_defers_the_repair_rather_than_spending_it(
    tmp_path: Path,
) -> None:
    """A box that renders a book before its first `catalog-update` would
    otherwise have this marked done while the name it needed was still unknown,
    and nothing would ever come back for it."""
    path = tmp_path / "nocatalog.db"
    conn = connect(path)
    _rendered(conn, 45839, _SCRAPED)
    conn.close()

    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert _title(conn, 45839) == _SCRAPED
    update_catalog(conn, csv_text=_CATALOG_CSV, index_text="")
    conn.close()

    conn = connect(path)
    try:
        assert _title(conn, 45839) == "Dracula"
    finally:
        conn.close()


def test_a_nameless_catalog_row_cannot_take_a_book_s_name_away(
    tmp_path: Path,
) -> None:
    """The same guard ingest keeps: an empty title is not a name.

    Neither published list can put an empty title in the catalog — the CSV
    import drops a row that has none, and the Australian index cannot produce
    one — so this is written straight into the table. It is pinned because the
    two places a book can be named must not disagree about what counts as one.
    """
    path = tmp_path / "nameless.db"
    conn = connect(path)
    update_catalog(conn, csv_text=_CATALOG_CSV, index_text="")
    _rendered(conn, 45839, _SCRAPED)
    with conn:
        conn.execute("UPDATE catalog SET title = '' WHERE gid = '45839'")
    conn.close()

    conn = connect(path)
    try:
        assert _title(conn, 45839) == _SCRAPED
    finally:
        conn.close()
