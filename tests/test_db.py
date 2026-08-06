"""Opening a database that was made by an older somnia.

There is exactly one database that matters and it is on the VPS, with books and
listening positions in it. Every column added after the first release has to
arrive by ALTER, because ``CREATE TABLE IF NOT EXISTS`` looks at an existing
table and does nothing at all — the failure mode being a column that exists on
every developer's machine and on nobody's real one.
"""

import sqlite3
from pathlib import Path

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
