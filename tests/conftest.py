"""Fixtures shared across test modules."""

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from fakes import FakeEmbedder
from somnia.config import Config
from somnia.db import connect
from somnia.embed import Embedder
from tone_book import build_tone_book


@dataclass
class ToneBook:
    """A book with real audio on disk, and the seams a test needs to reach it."""

    cfg: Config
    conn: sqlite3.Connection
    embedder: Embedder
    book_dir: Path


@pytest.fixture
def tone_book(tmp_path: Path) -> Iterator[ToneBook]:
    """The three-tone book, freshly built under ``tmp_path``.

    The connection is opened cross-thread because the server runs its handlers
    in a threadpool, and a fixture that only worked for direct calls would send
    anyone testing the player back here to find out why.
    """
    cfg = Config(data_dir=tmp_path / "data", library_dir=tmp_path / "library")
    conn = connect(cfg.db_path, cross_thread=True)
    embedder = cast(Embedder, FakeEmbedder())
    try:
        yield ToneBook(
            cfg=cfg,
            conn=conn,
            embedder=embedder,
            book_dir=build_tone_book(conn, cfg.library_dir, embedder),
        )
    finally:
        # An unclosed connection surfaces as a ResourceWarning whenever the
        # garbage collector gets to it, which pytest raises as an error in
        # whichever test happened to be running at the time.
        conn.close()
