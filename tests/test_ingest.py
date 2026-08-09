from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from fakes import FakeEmbedder
from somnia import ingest
from somnia.abs import AbsClient
from somnia.audio import ChapterAudio
from somnia.catalog import update_catalog
from somnia.config import Config
from somnia.db import connect
from somnia.embed import Embedder
from somnia.gutenberg import Book, Chapter
from somnia.ingest import RenderStopped, ingest_book, publish_chapters
from somnia.tts import TTSEngine

REL_PATH = "Sewell, Anna/Black Beauty"


class FakeAbs:
    """An ABS whose scan lags: the item only reaches full duration after N polls."""

    def __init__(self, duration_ms: int, polls_until_ready: int = 0) -> None:
        self._duration_ms = duration_ms
        self._polls_until_ready = polls_until_ready
        self.pushed: list[dict[str, Any]] | None = None
        self.finds = 0

    def find_item(self, library_id: str, rel_path: str) -> dict[str, Any] | None:
        self.finds += 1
        if rel_path != REL_PATH:
            return None
        seen = 0 if self.finds <= self._polls_until_ready else self._duration_ms
        return {"id": "item-1", "media": {"duration": seen / 1000}}

    def set_chapters(self, item_id: str, chapters: list[dict[str, Any]]) -> None:
        self.pushed = chapters


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[Any]:
    conn = connect(tmp_path / "somnia.db")
    try:
        yield _seeded(conn)
    finally:
        conn.close()


def _seeded(conn: Any) -> Any:
    conn.execute(
        "INSERT INTO books (gid, title, voice) VALUES (271, 'Black Beauty', 'af_heart')"
    )
    for idx, (title, start, end) in enumerate(
        [("01 My Early Home", 0, 231730), ("02 The Hunt", 231730, 549425)]
    ):
        conn.execute(
            "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms, audio_file)"
            " VALUES (271, ?, ?, ?, ?, '')",
            (idx, title, start, end),
        )
    conn.commit()
    return conn


def _cfg(tmp_path: Path) -> Config:
    cfg = Config(data_dir=tmp_path, library_dir=tmp_path / "library")
    cfg.abs_library_id = "lib-1"
    return cfg


def test_publish_chapters_states_every_boundary_in_seconds(
    conn: Any, tmp_path: Path
) -> None:
    abs_client = FakeAbs(duration_ms=549425)
    publish_chapters(
        _cfg(tmp_path), conn, cast(AbsClient, abs_client), 271, REL_PATH, 549425
    )
    assert abs_client.pushed == [
        {"id": 0, "start": 0.0, "end": 231.73, "title": "01 My Early Home"},
        {"id": 1, "start": 231.73, "end": 549.425, "title": "02 The Hunt"},
    ]


def test_publish_chapters_waits_for_the_scan_to_catch_up(
    conn: Any, tmp_path: Path
) -> None:
    abs_client = FakeAbs(duration_ms=549425, polls_until_ready=2)
    publish_chapters(
        _cfg(tmp_path),
        conn,
        cast(AbsClient, abs_client),
        271,
        REL_PATH,
        549425,
        timeout_s=10,
        # The waiting is not what is under test — the asking again is — and at
        # the real two seconds this one test spent four of them.
        poll_s=0,
    )
    assert abs_client.finds == 3
    assert abs_client.pushed is not None


def test_publish_chapters_does_not_wait_past_the_timeout_it_was_given(
    conn: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A poll interval longer than the timeout must not become the timeout.

    The sleep used to be `poll_s` flat, so the loop could wait a whole interval
    past the deadline it had already missed. Invisible at the shipped two
    seconds against thirty — and not invisible now that the interval is a
    parameter, because a caller can set one larger than the timeout. The wait is
    held by the render, between chapters, so what it costs is the book.
    """
    slept: list[float] = []
    monkeypatch.setattr(ingest.time, "sleep", slept.append)
    # A scan that never catches up. Not `polls_until_ready`, because the sleep
    # is stubbed out and the loop therefore spins through any number of polls
    # inside the timeout — it is the duration that has to stay short.
    abs_client = FakeAbs(duration_ms=0)

    publish_chapters(
        _cfg(tmp_path),
        conn,
        cast(AbsClient, abs_client),
        271,
        REL_PATH,
        549425,
        timeout_s=0.05,
        poll_s=30,
    )

    # Whatever it waited, none of it was the thirty seconds it was offered.
    assert all(nap <= 0.05 for nap in slept), slept
    assert abs_client.pushed is None


def test_publish_chapters_gives_up_quietly_when_the_item_never_appears(
    conn: Any, tmp_path: Path
) -> None:
    abs_client = FakeAbs(duration_ms=549425)
    publish_chapters(
        _cfg(tmp_path),
        conn,
        cast(AbsClient, abs_client),
        271,
        "not/this/book",
        549425,
        timeout_s=0,
    )
    assert abs_client.pushed is None


# ------------------------------------------------- rendering over a book we have


class SilentEngine:
    """Ten milliseconds of silence per character, so a chapter has a length.

    A render test cannot have Kokoro — it is in the ``[ml]`` extra and takes a
    minute to load a model — and does not need one. What ingest actually does
    with the samples is count them.

    It has a voice for the same reason the real engine does: ingest writes down
    what actually read the book, and it asks the engine rather than the
    configuration, because a request may have named a voice the renderer was
    not set to.
    """

    sample_rate = 1000
    voice = "af_heart"

    def render(self, text: str) -> Any:
        return np.zeros(10 * len(text), dtype=np.float32)


def _book(*titles: str) -> Book:
    """Black Beauty with as many chapters as the test needs, one line each.

    Three is the useful default: the ``conn`` fixture already has two chapters
    rendered, so a resume has exactly one chapter left to do and there is a
    boundary to check it started at.
    """
    return Book(
        gid=271,
        title="Black Beauty",
        authors="Sewell, Anna",
        chapters=[
            Chapter(title=title, paragraphs=[f"Something happened in {title}."])
            for title in titles
        ],
    )


BOOK = _book("01 My Early Home", "02 The Hunt", "03 My Breaking In")


@dataclass
class Fetched:
    """What Gutenberg is pretending to hold, so a test can change its mind.

    A book whose text changed between one render and the next is a real case
    and an ugly one — the chapter indices stop meaning the same thing — so a
    test has to be able to hand back a different book on the second fetch.
    """

    book: Book


@pytest.fixture
def unrendered(monkeypatch: pytest.MonkeyPatch) -> Fetched:
    """Write each chapter as an empty file rather than shelling out to ffmpeg.

    ffmpeg is a system package on the render host, and a test run should not
    need one — the tone book's audio is committed for the same reason. This
    stubs the single step that leaves the process; the rest of the pipeline,
    including every row it writes, is the real thing.
    """
    fetched = Fetched(book=BOOK)

    def encode(self: ChapterAudio, out_path: Path, bitrate: str = "64k") -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.touch()

    def fetch_book(gid: int, url: str | None = None) -> Book:
        return fetched.book

    monkeypatch.setattr(ChapterAudio, "encode", encode)
    monkeypatch.setattr(ingest, "fetch_book", fetch_book)
    return fetched


class RecordingEngine(SilentEngine):
    """A silent engine that keeps everything it was asked to say, in order."""

    def __init__(self) -> None:
        self.said: list[str] = []

    def render(self, text: str) -> Any:
        self.said.append(text)
        return super().render(text)


def _ingest(
    conn: Any,
    tmp_path: Path,
    *,
    engine: Any = None,
    should_stop: Callable[[], bool] | None = None,
    on_chapter: Callable[[int], None] | None = None,
) -> None:
    ingest_book(
        _cfg(tmp_path),
        conn,
        cast(TTSEngine, engine or SilentEngine()),
        cast(Embedder, FakeEmbedder()),
        271,
        should_stop=should_stop,
        on_chapter=on_chapter,
    )


def chapters(conn: Any) -> list[tuple[int, int, int]]:
    """Every chapter row, as (idx, start_ms, end_ms) — the book's timeline."""
    return [
        (r["idx"], r["start_ms"], r["end_ms"])
        for r in conn.execute(
            "SELECT idx, start_ms, end_ms FROM chapters WHERE book_gid = 271"
            " ORDER BY idx"
        )
    ]


def indexed_chapters(conn: Any) -> list[int]:
    """Which chapters have passages in the index, and how many each."""
    return [
        r["n"]
        for r in conn.execute(
            "SELECT chapter_idx, COUNT(*) AS n FROM chunks WHERE book_gid = 271"
            " GROUP BY chapter_idx ORDER BY chapter_idx"
        )
    ]


def rendered_files(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "library").rglob("*.m4a"))


def book_row(conn: Any) -> Any:
    return conn.execute("SELECT * FROM books WHERE gid = 271").fetchone()


def stop_after(conn: Any, chapter_count: int) -> Callable[[], bool]:
    """A stop that asks to be let go once that many chapters are safely done.

    It reads the database rather than counting calls because that is what the
    worker's callback will do too — the answer has to come from outside this
    process, since the thing that will really be asked is a heartbeat.
    """

    def should_stop() -> bool:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM chapters WHERE book_gid = 271"
        ).fetchone()
        return int(row["n"]) >= chapter_count

    return should_stop


@pytest.mark.usefixtures("unrendered")
def test_re_rendering_a_book_keeps_where_they_had_got_to(
    conn: Any, tmp_path: Path
) -> None:
    """Restarting a render that died is the ordinary reason to run `somnia add`.

    The row used to be written with INSERT OR REPLACE, which is DELETE followed
    by INSERT: the position, the count of agent moves and the high-water mark
    all dropped back to their defaults. That was the one way the mark could
    shrink, and losing it was not even the worst of it — a page still open held
    a count the new row could never match, so every report it made for the rest
    of the night was refused and nothing more was ever written.

    The book here has two of its three chapters already, so this is now also
    the ordinary resume — the same four columns have to come through that
    untouched, and the chapter count arriving beside them must not disturb them
    either.
    """
    with conn:
        conn.execute(
            "UPDATE books SET position_ms = 300000, position_seq = 3,"
            " position_at = '2026-08-05 23:40:00', heard_to_ms = 250000,"
            " abs_item_id = 'abs-item-1' WHERE gid = 271"
        )

    _ingest(conn, tmp_path)

    row = conn.execute("SELECT * FROM books WHERE gid = 271").fetchone()
    assert (row["position_ms"], row["position_seq"]) == (300_000, 3)
    assert (row["position_at"], row["heard_to_ms"]) == ("2026-08-05 23:40:00", 250_000)
    assert row["abs_item_id"] == "abs-item-1"
    # And it still did its own job: what a render knows, it wrote.
    assert (row["title"], row["voice"], row["status"]) == (
        "Black Beauty",
        "af_heart",
        "done",
    )


@pytest.mark.usefixtures("unrendered")
def test_rendering_a_book_for_the_first_time_creates_its_row(tmp_path: Path) -> None:
    """The other half of the upsert, which nothing else in the suite reaches."""
    conn = connect(tmp_path / "fresh.db")
    try:
        _ingest(conn, tmp_path)
        row = conn.execute("SELECT * FROM books WHERE gid = 271").fetchone()
    finally:
        conn.close()
    assert (row["title"], row["status"]) == ("Black Beauty", "done")
    assert (row["position_ms"], row["heard_to_ms"]) == (None, 0)
    assert row["total_ms"] > 0
    # And how many chapters it has, which is the only honest denominator there
    # is: total_ms cannot serve, because while a book renders it means "how much
    # audio exists so far" and get_position leans on it meaning exactly that.
    assert row["chapters_total"] == 3


# ------------------------------------------------------- saying which chapter it is


@pytest.mark.usefixtures("unrendered")
def test_each_chapter_says_its_own_name_before_a_word_of_it(tmp_path: Path) -> None:
    """Until this, a chapter boundary was silent — see :mod:`somnia.announce`.

    The heading is rendered from the number and the name rather than verbatim,
    which is what turns Black Beauty's "01 My Early Home" into something a
    phonemiser reads as English.
    """
    conn = connect(tmp_path / "fresh.db")
    engine = RecordingEngine()
    try:
        _ingest(conn, tmp_path, engine=engine)
    finally:
        conn.close()
    assert engine.said[0] == "Chapter 1. My Early Home"
    assert "Chapter 2. The Hunt" in engine.said
    assert "Chapter 3. My Breaking In" in engine.said


@pytest.mark.usefixtures("unrendered")
def test_what_the_chapter_says_about_itself_is_not_in_the_index(
    tmp_path: Path,
) -> None:
    """The announcement is somnia's words, not the book's, and search is the book's.

    Indexed, it would put the same phrase at the top of every chapter into the
    semantic index — and hand the spoiler guard sentences no author wrote.
    """
    conn = connect(tmp_path / "fresh.db")
    try:
        _ingest(conn, tmp_path)
        rows = conn.execute("SELECT text FROM chunks WHERE book_gid = 271")
        texts = [r["text"] for r in rows]
    finally:
        conn.close()
    assert texts
    assert not any("Chapter 1." in t for t in texts)


@pytest.mark.usefixtures("unrendered")
def test_the_chapter_mark_lands_on_the_announcement_rather_than_after_it(
    tmp_path: Path,
) -> None:
    """A press for chapter two should arrive at the words "chapter two".

    The mark is where the chapter's audio begins, and the announcement is the
    first thing in it — so the first *indexed* passage necessarily starts later
    than the mark, by the length of the announcement and its silence. This is
    the assertion that the announcement went in before the clock was read, and
    therefore that every timestamp in the book is still exact.
    """
    conn = connect(tmp_path / "fresh.db")
    try:
        _ingest(conn, tmp_path)
        marks = {
            r["idx"]: r["start_ms"]
            for r in conn.execute(
                "SELECT idx, start_ms FROM chapters WHERE book_gid = 271"
            )
        }
        first = {
            r["chapter_idx"]: r["start"]
            for r in conn.execute(
                "SELECT chapter_idx, MIN(start_ms) AS start FROM chunks"
                " WHERE book_gid = 271 GROUP BY chapter_idx"
            )
        }
    finally:
        conn.close()
    assert set(marks) == set(first)
    assert all(first[idx] > marks[idx] for idx in marks)


# ------------------------------------------------------- counting, stopping, resuming


@pytest.mark.usefixtures("unrendered")
def test_the_chapter_count_is_written_down_before_a_word_is_rendered(
    tmp_path: Path,
) -> None:
    """The denominator has to exist while it is still worth having.

    "Chapter 4 of 39" is only sayable if 39 was written down, and it is wanted
    most in the hours before the render finishes. Parsing the book already
    knows the number, and parsing is the fast part, so it is written with the
    books row rather than at the end — a stop before the first sentence still
    leaves the count behind.
    """
    conn = connect(tmp_path / "fresh.db")
    try:
        with pytest.raises(RenderStopped):
            _ingest(conn, tmp_path, should_stop=lambda: True)
        row = book_row(conn)
        assert row["chapters_total"] == 3
        assert chapters(conn) == []
    finally:
        conn.close()


@pytest.mark.usefixtures("unrendered")
def test_rendering_the_whole_book_twice_leaves_one_copy_of_it(tmp_path: Path) -> None:
    """Issue #11, at the level a listener would have met it.

    The second run re-renders nothing, because every chapter is already there —
    but even where it does render again, the chapter's passages replace
    themselves rather than doubling.
    """
    conn = connect(tmp_path / "fresh.db")
    try:
        _ingest(conn, tmp_path)
        first = (chapters(conn), indexed_chapters(conn), book_row(conn)["total_ms"])
        _ingest(conn, tmp_path)
        assert (chapters(conn), indexed_chapters(conn), book_row(conn)["total_ms"]) == (
            first
        )
    finally:
        conn.close()


@pytest.mark.usefixtures("unrendered")
def test_a_render_picks_up_at_the_chapter_after_the_last_finished_one(
    conn: Any, tmp_path: Path
) -> None:
    """Two chapters are already done, so only the third is rendered.

    And it starts where chapter two ended: the timestamps are global across the
    whole book, so a resume that began the clock again at zero would put every
    later chapter on top of an earlier one and break every saved position.
    """
    done: list[int] = []
    _ingest(conn, tmp_path, on_chapter=done.append)

    assert done == [2]
    assert rendered_files(tmp_path) == ["003 - 03 My Breaking In.m4a"]
    timeline = chapters(conn)
    assert [idx for idx, _, _ in timeline] == [0, 1, 2]
    assert timeline[2][1] == timeline[1][2] == 549_425
    assert book_row(conn)["total_ms"] == timeline[2][2]


@pytest.mark.usefixtures("unrendered")
def test_a_hole_in_the_middle_is_filled_rather_than_stepped_over(
    conn: Any, tmp_path: Path
) -> None:
    """The resume point is the first chapter missing, not the highest present.

    A book can have a hole in it — one chapter whose write was interrupted
    between its audio and its row — and resuming from the highest index would
    leave that hole there for good, silent and unsearchable.
    """
    with conn:
        conn.execute("DELETE FROM chapters WHERE book_gid = 271 AND idx = 0")

    done: list[int] = []
    _ingest(conn, tmp_path, on_chapter=done.append)

    assert done == [0, 1, 2]
    assert [idx for idx, _, _ in chapters(conn)] == [0, 1, 2]


@pytest.mark.usefixtures("unrendered")
def test_a_stop_lands_exactly_on_a_chapter_boundary(tmp_path: Path) -> None:
    """Nothing half-written anywhere: no stray m4a, no chunks without a chapter.

    The stop is asked for between sentences, and a chapter is encoded on the
    last line of rendering it, so the chapter being worked on when the answer
    comes back leaves no trace at all. That is what makes the window between
    indexing a chapter and writing its row unreachable — passages the player's
    manifest cannot see would send a chosen candidate past the end of its own
    timeline.
    """
    conn = connect(tmp_path / "fresh.db")
    try:
        with pytest.raises(RenderStopped):
            _ingest(conn, tmp_path, should_stop=stop_after(conn, 2))

        assert len(rendered_files(tmp_path)) == 2
        timeline = chapters(conn)
        assert [idx for idx, _, _ in timeline] == [0, 1]
        assert indexed_chapters(conn) == [1, 1]
        row = book_row(conn)
        assert row["total_ms"] == timeline[1][2]
        # Not 'rendering', which is a claim that work is going on, and not
        # 'done', which is a claim the book is all there. 'pending' is the
        # schema's own default and has never been written by anything, so it is
        # free to mean what it plainly says: not growing, and not finished.
        assert row["status"] == "pending"
    finally:
        conn.close()


@pytest.mark.usefixtures("unrendered")
def test_a_stop_and_a_resume_leave_the_listener_exactly_where_they_were(
    tmp_path: Path,
) -> None:
    """The high-water mark and the place they are in the book are not ours.

    A render knows the title, the authors, the voice and how far it has got. It
    knows nothing about where anybody is, so neither a stop nor the resume that
    follows may touch those four columns — and a page still open holds a count
    that a reset row could never match, so getting this wrong wedges the night
    rather than just losing a number.
    """
    conn = connect(tmp_path / "fresh.db")
    try:
        with pytest.raises(RenderStopped):
            _ingest(conn, tmp_path, should_stop=stop_after(conn, 1))
        with conn:
            conn.execute(
                "UPDATE books SET position_ms = 4000, position_seq = 3,"
                " position_at = '2026-08-05 23:40:00', heard_to_ms = 3500"
                " WHERE gid = 271"
            )
        night = dict(book_row(conn))

        with pytest.raises(RenderStopped):
            _ingest(conn, tmp_path, should_stop=stop_after(conn, 2))
        after_stop = dict(book_row(conn))

        _ingest(conn, tmp_path)
        after_resume = dict(book_row(conn))
    finally:
        conn.close()

    for row in (after_stop, after_resume):
        assert [row[c] for c in ("position_ms", "position_seq", "heard_to_ms")] == [
            4000,
            3,
            3500,
        ]
        assert row["position_at"] == night["position_at"]
    assert (after_stop["status"], after_resume["status"]) == ("pending", "done")


@pytest.mark.usefixtures("unrendered")
def test_a_failure_leaves_the_book_saying_it_is_not_being_rendered(
    tmp_path: Path,
) -> None:
    """A row stuck on 'rendering' for ever is the state this feature exists to end.

    The traceback still goes to whoever called — it belongs in the journal —
    but the database stops claiming that work is going on.
    """

    def explode() -> bool:
        raise RuntimeError("the box fell over")

    conn = connect(tmp_path / "fresh.db")
    try:
        with pytest.raises(RuntimeError, match="the box fell over"):
            _ingest(conn, tmp_path, should_stop=explode)
        assert book_row(conn)["status"] == "pending"
    finally:
        conn.close()


def test_a_book_whose_text_changed_underneath_us_is_rendered_again_from_zero(
    unrendered: Fetched, tmp_path: Path
) -> None:
    """Chapter four of one edition is not chapter four of another.

    Gutenberg does re-issue texts. If the chapter count has moved, the indices
    no longer mean the same thing, and splicing the two editions into one
    timeline would leave every saved position pointing at the wrong words. So
    the old rows go and the book is rendered from the start — expensive, and
    the only honest answer.
    """
    conn = connect(tmp_path / "fresh.db")
    try:
        _ingest(conn, tmp_path)
        unrendered.book = _book("01 My Early Home", "02 The Hunt")

        done: list[int] = []
        _ingest(conn, tmp_path, on_chapter=done.append)

        assert done == [0, 1]
        timeline = chapters(conn)
        assert [idx for idx, _, _ in timeline] == [0, 1]
        assert timeline[0][1] == 0
        assert indexed_chapters(conn) == [1, 1]
        row = book_row(conn)
        assert (row["chapters_total"], row["total_ms"]) == (2, timeline[1][2])
    finally:
        conn.close()


def test_an_australian_book_is_fetched_from_the_address_the_catalog_kept(
    unrendered: Fetched, tmp_path: Path
) -> None:
    """Nothing can compute it, so the catalog hands it to fetch_book."""
    conn = connect(tmp_path / "au.db")
    asked: list[str | None] = []

    def fetch_book(gid: int, url: str | None = None) -> Book:
        asked.append(url)
        return unrendered.book

    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(ingest, "fetch_book", fetch_book)
            with conn:
                conn.execute(
                    "INSERT INTO catalog_urls (gid, url) VALUES (?, ?)",
                    (910100011, "http://gutenberg.net.au/ebooks01/0100011h.html"),
                )
            ingest_book(
                _cfg(tmp_path),
                conn,
                cast(TTSEngine, SilentEngine()),
                cast(Embedder, FakeEmbedder()),
                910100011,
            )
        assert asked == ["http://gutenberg.net.au/ebooks01/0100011h.html"]
    finally:
        conn.close()


def test_an_australian_book_with_no_address_says_so_before_fetching_anything(
    unrendered: Fetched, tmp_path: Path
) -> None:
    """A stale queue row outliving a catalog rebuild is the way this happens.

    The alternative is a request to a URL nobody has, which fails as a 404 and
    reads as "Gutenberg does not have this book" — the one wrong diagnosis.
    """
    conn = connect(tmp_path / "lost.db")
    try:
        with pytest.raises(RuntimeError, match="catalog-update"):
            ingest_book(
                _cfg(tmp_path),
                conn,
                cast(TTSEngine, SilentEngine()),
                cast(Embedder, FakeEmbedder()),
                910100011,
            )
    finally:
        conn.close()


CATALOG_CSV = """\
Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves
271,Text,2006-01-25,Black Beauty,en,"Sewell, Anna, 1820-1878",Horses,PZ,
"""


def _headline_book() -> Book:
    """What Gutenberg's own HTML calls Black Beauty, for a good part of the corpus."""
    return Book(
        gid=271,
        title="The Project Gutenberg eBook of Black Beauty, by Anna Sewell.",
        authors="",
        chapters=[Chapter(title="01 My Early Home", paragraphs=["A meadow."])],
    )


def test_a_book_is_called_what_the_catalog_calls_it(
    unrendered: Fetched, tmp_path: Path
) -> None:
    """And not what the file's own header line says.

    The catalog's name is also the one that was on screen when the book was
    pressed for, which is the name somebody is looking for at 2am.
    """
    conn = connect(tmp_path / "named.db")
    try:
        update_catalog(conn, csv_text=CATALOG_CSV, index_text="")
        unrendered.book = _headline_book()
        _ingest(conn, tmp_path)
        row = conn.execute("SELECT title FROM books WHERE gid = 271").fetchone()
        assert row["title"] == "Black Beauty"
    finally:
        conn.close()


def test_the_library_folder_takes_the_catalog_name_too(
    unrendered: Fetched, tmp_path: Path
) -> None:
    """One name for the book, not two — the folder is built from the same string."""
    conn = connect(tmp_path / "folder.db")
    try:
        update_catalog(conn, csv_text=CATALOG_CSV, index_text="")
        unrendered.book = _headline_book()
        _ingest(conn, tmp_path)
        made = [p.name for p in (tmp_path / "library").rglob("*") if p.is_dir()]
        assert "Black Beauty" in made
        assert not any(name.startswith("The Project Gutenberg") for name in made)
    finally:
        conn.close()


def test_a_book_the_catalog_never_heard_of_keeps_the_scraped_name(
    unrendered: Fetched, tmp_path: Path
) -> None:
    """`somnia add` takes any gid, so the scrape is still the only fallback."""
    conn = connect(tmp_path / "unknown.db")
    try:
        unrendered.book = Book(
            gid=271,
            title="Something Only The File Knows",
            authors="",
            chapters=[Chapter(title="One", paragraphs=["A line."])],
        )
        _ingest(conn, tmp_path)
        row = conn.execute("SELECT title FROM books WHERE gid = 271").fetchone()
        assert row["title"] == "Something Only The File Knows"
    finally:
        conn.close()
