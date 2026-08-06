from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from fakes import FakeEmbedder
from somnia import ingest
from somnia.abs import AbsClient
from somnia.audio import ChapterAudio
from somnia.config import Config
from somnia.db import connect
from somnia.embed import Embedder
from somnia.gutenberg import Book, Chapter
from somnia.ingest import ingest_book, publish_chapters
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
    )
    assert abs_client.finds == 3
    assert abs_client.pushed is not None


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
    """

    sample_rate = 1000

    def render(self, text: str) -> Any:
        return np.zeros(10 * len(text), dtype=np.float32)


BOOK = Book(
    gid=271,
    title="Black Beauty",
    authors="Sewell, Anna",
    chapters=[Chapter(title="01 My Early Home", paragraphs=["The first place."])],
)


@pytest.fixture
def unrendered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write each chapter as an empty file rather than shelling out to ffmpeg.

    ffmpeg is a system package on the render host, and a test run should not
    need one — the tone book's audio is committed for the same reason. This
    stubs the single step that leaves the process; the rest of the pipeline,
    including every row it writes, is the real thing.
    """

    def encode(self: ChapterAudio, out_path: Path, bitrate: str = "64k") -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.touch()

    def fetch_book(gid: int) -> Book:
        return BOOK

    monkeypatch.setattr(ChapterAudio, "encode", encode)
    monkeypatch.setattr(ingest, "fetch_book", fetch_book)


def _ingest(conn: Any, tmp_path: Path) -> None:
    ingest_book(
        _cfg(tmp_path),
        conn,
        cast(TTSEngine, SilentEngine()),
        cast(Embedder, FakeEmbedder()),
        271,
    )


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
