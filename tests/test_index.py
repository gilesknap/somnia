"""What happens to the index when a chapter is rendered a second time.

Rendering a chapter twice is not an exotic case: it is what restarting a render
that died has always done, because a render that died starts again at chapter
one. Every one of those restarts used to add a second copy of every passage of
every chapter it had already done, so a search came back with the same words
twice under two different ids, and a list of places to jump to could offer the
listener the same moment four times over.

So ``add_chunks`` now owns a chapter outright: after it returns, that chapter's
chunks are exactly the windows it was handed and nothing else. These tests are
that promise, including the awkward corner of it — a chapter that parses to no
windows at all still has its old ones taken away.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from fakes import FakeEmbedder
from somnia.db import connect
from somnia.embed import Embedder
from somnia.index import add_chunks, find_passage
from somnia.segment import Window

GID = 271


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "somnia.db")
    try:
        with conn:
            conn.execute(
                "INSERT INTO books (gid, title, voice) VALUES (?, 'Black Beauty',"
                " 'af_heart')",
                (GID,),
            )
        yield conn
    finally:
        conn.close()


@pytest.fixture
def embedder() -> Embedder:
    """One instance for the whole test: FakeEmbedder gives an axis per string,
    so a query only ever finds a passage the same instance indexed."""
    return cast(Embedder, FakeEmbedder())


def chapter(*texts: str, start_ms: int = 0) -> list[Window]:
    """A chapter's worth of windows, ten seconds apart so ids are not the clock."""
    return [
        Window(
            text=text,
            start_ms=start_ms + i * 10_000,
            end_ms=start_ms + (i + 1) * 10_000,
        )
        for i, text in enumerate(texts)
    ]


def counted(conn: sqlite3.Connection, chapter_idx: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM chunks WHERE book_gid = ? AND chapter_idx = ?",
        (GID, chapter_idx),
    ).fetchone()
    return int(row["n"])


def test_indexing_a_chapter_twice_leaves_one_copy_of_it(
    conn: sqlite3.Connection, embedder: Embedder
) -> None:
    windows = chapter("the meadow with the pond", "the long grass by the gate")
    add_chunks(conn, embedder, GID, 0, windows)
    add_chunks(conn, embedder, GID, 0, windows)

    assert counted(conn, 0) == 2
    texts = [
        r["text"]
        for r in conn.execute(
            "SELECT text FROM chunks WHERE book_gid = ? ORDER BY id", (GID,)
        )
    ]
    assert texts == [w.text for w in windows]


def test_the_vectors_are_taken_away_with_the_rows_they_belong_to(
    conn: sqlite3.Connection, embedder: Embedder
) -> None:
    """A vector left behind still matches a search, and points at nothing.

    ``chunks.id`` and ``vec_chunks.rowid`` are the same number by construction,
    which is the whole of the join. Deleting one side without the other leaves a
    vector that a search will happily return and that then joins to no row —
    invisible until a passage the listener asked for cannot be found.
    """
    add_chunks(conn, embedder, GID, 0, chapter("the meadow", "the pond", "the gate"))
    add_chunks(conn, embedder, GID, 0, chapter("the meadow again"))

    chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    vectors = conn.execute("SELECT COUNT(*) AS n FROM vec_chunks").fetchone()["n"]
    assert (chunks, vectors) == (1, 1)


def test_re_indexing_one_chapter_leaves_the_rest_of_the_book_alone(
    conn: sqlite3.Connection, embedder: Embedder
) -> None:
    """The unit is a chapter, because a chapter is what a render redoes."""
    add_chunks(conn, embedder, GID, 0, chapter("the meadow with the pond"))
    add_chunks(conn, embedder, GID, 1, chapter("the hunt", "Rob Roy was shot"))
    add_chunks(conn, embedder, GID, 0, chapter("the meadow, rendered again"))

    assert (counted(conn, 0), counted(conn, 1)) == (1, 2)


def test_a_chapter_that_now_parses_to_nothing_loses_what_it_had(
    conn: sqlite3.Connection, embedder: Embedder
) -> None:
    """The early-out is after the delete, not before it.

    Windowing can legitimately come back empty — a chapter that is a single
    illustration, or one whose text the parser now reads differently. If the
    delete sat behind the early-out, that chapter would keep yesterday's
    passages for ever while its audio said something else.
    """
    add_chunks(conn, embedder, GID, 0, chapter("the meadow with the pond"))
    add_chunks(conn, embedder, GID, 0, [])

    assert counted(conn, 0) == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM vec_chunks").fetchone()["n"] == 0


def test_a_search_after_a_re_render_offers_each_passage_once(
    conn: sqlite3.Connection, embedder: Embedder
) -> None:
    """The failure this whole change is about, seen from where it hurt.

    Duplicates were never visible in the database; they were visible as a list
    of four places to jump to in which the same moment appeared twice, which
    asks somebody half asleep to choose between two identical rows.
    """
    windows = chapter("the meadow with the pond", "the long grass by the gate")
    add_chunks(conn, embedder, GID, 0, windows)
    add_chunks(conn, embedder, GID, 0, windows)

    found = find_passage(conn, embedder, GID, "the meadow with the pond", k=5)
    assert [p.text for p in found].count("the meadow with the pond") == 1
