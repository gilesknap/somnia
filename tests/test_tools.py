import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from fakes import BrokenAbs, FakeAbs, FakeEmbedder
from somnia.abs import AbsClient
from somnia.config import Config
from somnia.db import connect
from somnia.embed import Embedder
from somnia.index import add_chunks
from somnia.segment import Window
from somnia.tools import Library, format_timestamp

ITEM_ID = "abs-item-1"


CHAPTERS = [
    ("01 My Early Home", 0, 240_000),
    ("02 The Hunt", 240_000, 560_000),
    ("47 Hard Times", 560_000, 900_000),
]
PASSAGES = [
    ("the meadow with the pond", 10_000),
    ("Rob Roy was shot after the hunt", 300_000),
    # Invented, not a real passage: fixtures should not spoil the book for
    # anyone reading the tests. Only that it is late in the book matters.
    ("a later scene the listener has not reached", 700_000),
]


@dataclass
class Fixture:
    """The library under test, plus the seams the tests need to poke."""

    library: Library
    conn: sqlite3.Connection
    abs: FakeAbs
    # Any stand-in for Audiobookshelf, including one that only knows how to
    # fail: what a move does when ABS is down is now part of the contract.
    make_library: Callable[[object], Library]


@pytest.fixture
def fixture(tmp_path: Path) -> Iterator[Fixture]:
    conn = connect(tmp_path / "somnia.db")
    try:
        yield _seeded(conn, tmp_path)
    finally:
        conn.close()


def _seeded(conn: sqlite3.Connection, tmp_path: Path) -> Fixture:
    embedder = FakeEmbedder()
    with conn:
        # Five minutes in, and five minutes is the furthest they have got. Both
        # are seeded because the page writes them now — it reports where it has
        # reached every few seconds — so a library test starts from a listener
        # who has been listening rather than from one who has not.
        conn.execute(
            "INSERT INTO books (gid, title, authors, voice, status, total_ms,"
            " abs_item_id, position_ms, heard_to_ms) VALUES (271, 'Black Beauty',"
            " 'Sewell, Anna', 'af_heart', 'done', 900000, ?, 300000, 300000)",
            (ITEM_ID,),
        )
        for idx, (title, start, end) in enumerate(CHAPTERS):
            conn.execute(
                "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
                " audio_file) VALUES (271, ?, ?, ?, ?, '')",
                (idx, title, start, end),
            )
    for idx, (text, start) in enumerate(PASSAGES):
        add_chunks(
            conn,
            cast(Embedder, embedder),
            271,
            idx,
            [Window(text=text, start_ms=start, end_ms=start + 10_000)],
        )
    cfg = Config(data_dir=tmp_path)

    def make_library(fake: object) -> Library:
        return Library(cfg, conn, cast(AbsClient, fake), cast(Embedder, embedder))

    fake_abs = FakeAbs(300.0)
    return Fixture(
        library=make_library(fake_abs),
        conn=conn,
        abs=fake_abs,
        make_library=make_library,
    )


def test_books_reports_rendered_chapter_count(fixture: Fixture) -> None:
    (book,) = fixture.library.books()
    assert book.title == "Black Beauty"
    assert book.chapters == len(CHAPTERS)


def test_get_position_names_the_chapter_and_the_text_there(fixture: Fixture) -> None:
    position = fixture.library.get_position(271)
    assert position is not None
    assert position.position_ms == 300_000
    assert position.chapter_title == "02 The Hunt"
    assert position.text == "Rob Roy was shot after the hunt"


def test_get_position_is_none_before_they_start(fixture: Fixture) -> None:
    """Nobody is at 0:00:00 — they have not begun, which is a different answer.

    Only a null position can tell the two apart, which is why the column is
    nullable rather than defaulting to zero like everything beside it.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = NULL WHERE gid = 271")
    assert fixture.library.get_position(271) is None


def test_get_position_reads_somnias_own_record_not_audiobookshelf(
    fixture: Fixture,
) -> None:
    """The page is the player, so ABS only ever hears about a position later.

    Asking it where the book is would answer with whatever it was last told,
    which on a book played entirely from the page is a whole night out of date.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = 42000 WHERE gid = 271")
    stale = fixture.make_library(FakeAbs(current_time=888.0))

    position = stale.get_position(271)
    assert position is not None
    assert position.position_ms == 42_000


def test_a_book_still_rendering_is_not_called_finished_at_the_frontier(
    fixture: Fixture,
) -> None:
    """total_ms covers only what exists, so catching up is not the ending.

    find_passage switches the spoiler guard off for a finished book. Calling a
    book finished the moment they reach the end of what has been rendered would
    turn the guard off on the one book most able to spoil itself.
    """
    with fixture.conn:
        fixture.conn.execute(
            "UPDATE books SET status = 'rendering', position_ms = 900000"
            " WHERE gid = 271"
        )
    growing = fixture.library.get_position(271)
    assert growing is not None
    assert not growing.finished

    with fixture.conn:
        fixture.conn.execute("UPDATE books SET status = 'done' WHERE gid = 271")
    done = fixture.library.get_position(271)
    assert done is not None
    assert done.finished


def test_find_passage_will_not_search_past_where_they_are(fixture: Fixture) -> None:
    """The late passage is at 700_000ms; the listener is at 300_000ms.

    Nearest-neighbour search has no relevance floor, so the guarantee is not
    "no results" — it is that the unheard passage is never among them.
    """
    query = "a later scene the listener has not reached"
    heard = fixture.library.find_passage(271, query)
    assert 700_000 not in [p.start_ms for p in heard.hits]
    assert heard.searched_to_ms == 360_000

    spoiled = fixture.library.find_passage(271, query, spoiler_free=False)
    assert spoiled.hits[0].start_ms == 700_000
    assert spoiled.searched_to_ms is None


def test_find_passage_finds_what_they_have_already_heard(fixture: Fixture) -> None:
    search = fixture.library.find_passage(271, "Rob Roy was shot after the hunt")
    assert search.hits[0].start_ms == 300_000
    assert search.hits[0].chapter_title == "02 The Hunt"
    assert search.better_ahead is None


def test_moving_writes_the_position_and_tells_audiobookshelf_too(
    fixture: Fixture,
) -> None:
    """Where the book resumes is somnia's own record now, not a remote one.

    ABS still hears the same number, in seconds and after the fact, so that a
    book opened there on some other evening starts somewhere near right.
    """
    moved = fixture.library.move_to(271, 300_500)
    row = fixture.conn.execute(
        "SELECT position_ms FROM books WHERE gid = 271"
    ).fetchone()
    assert row["position_ms"] == 300_500
    assert (moved.gid, moved.position_ms) == (271, 300_500)
    assert moved.sentence == "Moved to 0:05:00, and it plays from there."
    assert fixture.abs.moves == [(ITEM_ID, 300.5)]


def test_moving_counts_up_so_the_page_can_tell_it_happened(fixture: Fixture) -> None:
    """The count is how a page tells an agent move from its own heartbeat.

    Its own reports leave the count alone, so a number higher than the one it
    holds can only be a move it has not applied — and it can act on that
    without asking anything else.
    """

    def seq() -> int:
        row = fixture.conn.execute(
            "SELECT position_seq FROM books WHERE gid = 271"
        ).fetchone()
        return int(row["position_seq"])

    assert seq() == 0
    # Handed back as well as written: the page acts on the number it is given,
    # so the two disagreeing would refuse every report it made afterwards.
    assert fixture.library.move_to(271, 10_000).seq == 1
    assert seq() == 1
    assert fixture.library.move_to(271, 20_000).seq == 2
    assert seq() == 2


def test_a_book_audiobookshelf_has_never_seen_can_still_be_moved(
    fixture: Fixture,
) -> None:
    """somnia renders books ABS may not have scanned yet, and plays them anyway.

    Having nowhere to send the courtesy write used to raise, back when ABS held
    the position. The page holds it now, so this is an absence, not a failure.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET abs_item_id = '' WHERE gid = 271")

    moved = fixture.library.move_to(271, 60_000)
    assert moved.sentence == "Moved to 0:01:00, and it plays from there."
    assert moved.seq == 1
    assert fixture.abs.moves == []


def test_an_audiobookshelf_that_is_down_does_not_fail_a_move(
    fixture: Fixture,
) -> None:
    """The write that matters already happened before ABS was asked anything.

    Turning a move that worked into an error, because a server nothing is
    listening to could not be reached, is the wrong answer at 2am.
    """
    library = fixture.make_library(BrokenAbs())
    moved = library.move_to(271, 60_000)

    assert moved.sentence == "Moved to 0:01:00, and it plays from there."
    row = fixture.conn.execute(
        "SELECT position_ms FROM books WHERE gid = 271"
    ).fetchone()
    assert row["position_ms"] == 60_000


def test_moving_a_book_that_is_not_here_says_so_rather_than_raising(
    fixture: Fixture,
) -> None:
    """A sentence is more use than a traceback, and no move is no move.

    The count is how the page tells a move from nothing, and it counts up from
    zero on every one that lands — so zero says there is nothing to follow
    without needing a second field to say it.
    """
    moved = fixture.library.move_to(999, 60_000)
    assert moved.seq == 0
    assert "no book 999" in moved.sentence
    assert fixture.abs.moves == []


def test_being_moved_back_does_not_un_hear_the_rest(fixture: Fixture) -> None:
    """The guard bounds searches by the furthest point ever reached.

    Taking someone back to an earlier passage moves their position backwards.
    If that also moved the spoiler bound, the whole stretch they had already
    listened to would become unsearchable for the rest of the night.
    """
    fixture.library.find_passage(271, "anything")  # records 300s as heard
    fixture.library.move_to(271, 10_000)

    search = fixture.library.find_passage(271, "Rob Roy was shot after the hunt")
    assert search.searched_to_ms == 360_000
    assert search.hits[0].start_ms == 300_000


def test_format_timestamp_reads_as_a_listening_position() -> None:
    assert format_timestamp(0) == "0:00:00"
    assert format_timestamp(8_412_000) == "2:20:12"


def test_find_passage_says_when_the_answer_lies_ahead(fixture: Fixture) -> None:
    search = fixture.library.find_passage(
        271, "a later scene the listener has not reached"
    )
    assert search.better_ahead is not None
    assert search.better_ahead.start_ms == 700_000
    assert 700_000 not in [p.start_ms for p in search.hits]
