"""A book with a timeline long enough to be spoiled, for testing the guard.

The other fixture book, :mod:`tone_book`, is three chapters of pure sound and
twenty-four seconds long — shorter than the minute of slack the spoiler guard
allows itself — so nothing about being ahead of the mark can be asserted on it
at all. This one has no audio and cannot be played, but it has fifteen minutes
of clock, three chapters, and a listener five minutes in, which is what "further
on than they have listened" needs in order to mean anything.

None of the passages are real passages from the book. A fixture that quoted one
would spoil it for whoever reads the test, which is the same failure the code
under test exists to prevent; only where each one sits matters.

The seed is shared because two suites need the same book and a second, subtly
different Black Beauty would be a place for them to disagree — the tool tests
and the agent tests must be arguing about one timeline.
"""

import sqlite3

from somnia.embed import Embedder
from somnia.index import add_chunks
from somnia.segment import Window

__all__ = [
    "ABS_ITEM_ID",
    "CHAPTERS",
    "GID",
    "PASSAGES",
    "TOTAL_MS",
    "build_black_beauty",
]

GID = 271
TITLE = "Black Beauty"
AUTHORS = "Sewell, Anna"
TOTAL_MS = 900_000
ABS_ITEM_ID = "abs-item-1"

CHAPTERS = [
    ("01 My Early Home", 0, 240_000),
    ("02 The Hunt", 240_000, 560_000),
    ("47 Hard Times", 560_000, 900_000),
]

# Chapter, words, where it starts. The last one is past the default mark, which
# is what makes it the passage every spoiler test is about.
PASSAGES = [
    (0, "the meadow with the pond", 10_000),
    (1, "Rob Roy was shot after the hunt", 300_000),
    (2, "a later scene the listener has not reached", 700_000),
]


def build_black_beauty(
    conn: sqlite3.Connection,
    embedder: Embedder,
    *,
    heard_to_ms: int = 300_000,
    position_ms: int | None = 300_000,
) -> None:
    """Seed the book into ``conn``, five minutes in and five minutes heard.

    Both numbers are seeded because the page writes both — it reports where it
    has reached every few seconds — so a test starts from a listener who has
    been listening rather than from one who has not. They are separate
    arguments because the whole of the guard lives in the gap between them:
    where they were put is not what they have heard.

    The embedder is the caller's because :class:`fakes.FakeEmbedder` hands out
    an axis per string it has seen, so a query only finds a passage if the same
    instance indexed it. Passing one in is what lets a search test find these
    passages at all.
    """
    with conn:
        conn.execute(
            "INSERT INTO books (gid, title, authors, voice, status, total_ms,"
            " abs_item_id, position_ms, heard_to_ms)"
            " VALUES (?, ?, ?, 'af_heart', 'done', ?, ?, ?, ?)",
            (GID, TITLE, AUTHORS, TOTAL_MS, ABS_ITEM_ID, position_ms, heard_to_ms),
        )
        for idx, (title, start_ms, end_ms) in enumerate(CHAPTERS):
            conn.execute(
                "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
                " audio_file) VALUES (?, ?, ?, ?, ?, '')",
                (GID, idx, title, start_ms, end_ms),
            )
    for chapter_idx, text, start_ms in PASSAGES:
        add_chunks(
            conn,
            embedder,
            GID,
            chapter_idx,
            [Window(text=text, start_ms=start_ms, end_ms=start_ms + 10_000)],
        )
