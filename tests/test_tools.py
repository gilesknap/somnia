import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from somnia.abs import AbsClient
from somnia.config import Config
from somnia.db import EMBED_DIM, connect
from somnia.embed import Embedder
from somnia.index import add_chunks
from somnia.segment import Window
from somnia.tools import Library, format_timestamp

ITEM_ID = "abs-item-1"


class FakeEmbedder:
    """Deterministic one-hot vectors, so "nearest" is exactly predictable."""

    def __init__(self) -> None:
        self.axis_of: dict[str, int] = {}

    def _vec(self, text: str) -> Any:
        axis = self.axis_of.setdefault(text, len(self.axis_of))
        v = np.zeros(EMBED_DIM, dtype=np.float32)
        v[axis] = 1.0
        return v

    def encode_passages(self, texts: list[str]) -> Any:
        return np.stack([self._vec(t) for t in texts])

    def encode_query(self, text: str) -> Any:
        return self._vec(text)


class FakeAbs:
    def __init__(self, current_time: float | None = None) -> None:
        self._current_time = current_time
        self.bookmarks: list[tuple[str, float, str]] = []

    def progress(self, item_id: str) -> dict[str, Any] | None:
        if self._current_time is None:
            return None
        return {"libraryItemId": item_id, "currentTime": self._current_time}

    def create_bookmark(self, item_id: str, time_s: float, title: str) -> None:
        self.bookmarks.append((item_id, time_s, title))


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
    make_library: Callable[[FakeAbs], Library]


@pytest.fixture
def fixture(tmp_path: Path) -> Iterator[Fixture]:
    conn = connect(tmp_path / "somnia.db")
    embedder = FakeEmbedder()
    with conn:
        conn.execute(
            "INSERT INTO books (gid, title, authors, voice, status, total_ms,"
            " abs_item_id) VALUES (271, 'Black Beauty', 'Sewell, Anna',"
            " 'af_heart', 'done', 900000, ?)",
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

    def make_library(fake: FakeAbs) -> Library:
        return Library(cfg, conn, cast(AbsClient, fake), cast(Embedder, embedder))

    fake_abs = FakeAbs(300.0)
    try:
        yield Fixture(
            library=make_library(fake_abs),
            conn=conn,
            abs=fake_abs,
            make_library=make_library,
        )
    finally:
        conn.close()


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
    unplayed = fixture.make_library(FakeAbs(current_time=None))
    assert unplayed.get_position(271) is None


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


def test_plant_bookmark_uses_the_abs_item_and_seconds(fixture: Fixture) -> None:
    message = fixture.library.plant_bookmark(271, 300_500, "where Rob Roy dies")
    assert fixture.abs.bookmarks == [(ITEM_ID, 300.5, "where Rob Roy dies")]
    assert "0:05:00" in message


def test_plant_bookmark_explains_when_the_book_is_not_in_abs_yet(
    fixture: Fixture,
) -> None:
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET abs_item_id = '' WHERE gid = 271")
    with pytest.raises(LookupError):
        fixture.library.plant_bookmark(271, 1000, "nope")


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
