"""The tool layer: everything the agent can do, as a plain Python library.

Deliberately free of any Anthropic dependency — :mod:`somnia.agent` wraps these
for the tool runner, and the PWA will call them directly. Each function returns
structured data; turning that into prose is the caller's job.

The spoiler guard lives here rather than in the agent's prompt: a question about
a book is answered from the part the listener could have heard, because finding
out how it ends is the one thing a bedtime reader must never do by accident.
"""

import logging
import sqlite3
import subprocess
import sys
from dataclasses import dataclass

from .abs import AbsClient
from .catalog import CatalogEntry, search_catalog
from .config import Config
from .embed import Embedder
from .index import Passage, find_passage

__all__ = ["Book", "Library", "Position"]

logger = logging.getLogger(__name__)


@dataclass
class Book:
    gid: int
    title: str
    authors: str
    status: str
    total_ms: int
    chapters: int


@dataclass
class Position:
    """Where the listener is, and what is happening there."""

    book: Book
    position_ms: int
    chapter_idx: int
    chapter_title: str
    text: str
    finished: bool


class Library:
    """The agent's view of somnia: what exists, what was heard, where to go.

    The embedder is loaded lazily — it pulls in torch, and answering "what am I
    part-way through?" should not pay for that.
    """

    def __init__(
        self,
        cfg: Config,
        conn: sqlite3.Connection,
        abs_client: AbsClient | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._cfg = cfg
        self._conn = conn
        self._abs = abs_client
        self._embedder = embedder

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder(self._cfg.embed_model)
        return self._embedder

    # ------------------------------------------------------------------ books

    def search_catalog(self, query: str, language: str = "en") -> list[CatalogEntry]:
        """Search Project Gutenberg's catalog for a book to add."""
        return search_catalog(self._conn, query, language=language)

    def books(self) -> list[Book]:
        """Every book somnia has rendered or is rendering."""
        rows = self._conn.execute(
            "SELECT b.gid, b.title, b.authors, b.status, b.total_ms,"
            " (SELECT COUNT(*) FROM chapters c WHERE c.book_gid = b.gid) AS chapters"
            " FROM books b ORDER BY b.created_at"
        ).fetchall()
        return [
            Book(
                gid=r["gid"],
                title=r["title"],
                authors=r["authors"],
                status=r["status"],
                total_ms=r["total_ms"],
                chapters=r["chapters"],
            )
            for r in rows
        ]

    def book(self, gid: int) -> Book | None:
        return next((b for b in self.books() if b.gid == gid), None)

    def add_book(self, gid: int) -> str:
        """Start rendering a Gutenberg book, in the background.

        A book takes hours to render, so this returns as soon as the work has
        started. Chapter one is listenable within a few minutes; the rest
        arrives while you sleep.
        """
        existing = self.book(gid)
        if existing is not None:
            return f"{existing.title} is already here ({existing.status})."
        subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "somnia", "add", str(gid)],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("started ingest of gid %d", gid)
        return f"Started rendering book {gid}. Chapter one plays in a few minutes."

    # -------------------------------------------------------------- listening

    def _abs_item_id(self, gid: int) -> str:
        row = self._conn.execute(
            "SELECT abs_item_id FROM books WHERE gid = ?", (gid,)
        ).fetchone()
        item_id: str = row["abs_item_id"] if row else ""
        if not item_id:
            raise LookupError(f"book {gid} is not in Audiobookshelf yet")
        return item_id

    def _require_abs(self) -> AbsClient:
        if self._abs is None:
            raise LookupError("Audiobookshelf is not configured")
        return self._abs

    def get_position(self, gid: int) -> Position | None:
        """Where the listener left off, and the text at that point."""
        book = self.book(gid)
        if book is None:
            return None
        progress = self._require_abs().progress(self._abs_item_id(gid))
        if progress is None:
            return None
        position_ms = int(float(progress.get("currentTime", 0.0)) * 1000)
        chapter = self._conn.execute(
            "SELECT idx, title FROM chapters WHERE book_gid = ? AND start_ms <= ?"
            " ORDER BY start_ms DESC LIMIT 1",
            (gid, position_ms),
        ).fetchone()
        chunk = self._conn.execute(
            "SELECT text FROM chunks WHERE book_gid = ? AND start_ms <= ?"
            " ORDER BY start_ms DESC LIMIT 1",
            (gid, position_ms),
        ).fetchone()
        return Position(
            book=book,
            position_ms=position_ms,
            chapter_idx=chapter["idx"] if chapter else 0,
            chapter_title=chapter["title"] if chapter else "",
            text=chunk["text"] if chunk else "",
            finished=bool(progress.get("isFinished")),
        )

    def find_passage(
        self, gid: int, query: str, k: int = 5, spoiler_free: bool = True
    ) -> list[Passage]:
        """Search a book for a passage — an event, a character, a moment.

        With ``spoiler_free`` (the default) the search stops at how far the
        listener has got. Pass False only when they have said they don't mind.
        """
        before_ms: int | None = None
        if spoiler_free:
            position = self.get_position(gid)
            if position is not None and not position.finished:
                # Include the sentence being spoken, not just what precedes it.
                before_ms = position.position_ms + 60_000
        return find_passage(
            self._conn, self.embedder, gid, query, k=k, before_ms=before_ms
        )

    def plant_bookmark(self, gid: int, position_ms: int, title: str) -> str:
        """Drop a named bookmark so the app is two taps from the passage."""
        self._require_abs().create_bookmark(
            self._abs_item_id(gid), position_ms / 1000, title
        )
        return f'Bookmarked "{title}" at {format_timestamp(position_ms)}.'


def format_timestamp(ms: int) -> str:
    """Global milliseconds as h:mm:ss — how a listener thinks about position."""
    seconds = ms // 1000
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
