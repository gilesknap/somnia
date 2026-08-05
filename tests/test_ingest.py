from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from somnia.abs import AbsClient
from somnia.config import Config
from somnia.db import connect
from somnia.ingest import publish_chapters

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
