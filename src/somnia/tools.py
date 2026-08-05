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
import time
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
class Search:
    """Search results, plus what the spoiler guard held back.

    ``better_ahead`` is the crux: without it, a spoiler-bounded search that
    excludes the answer is indistinguishable from a book that never contained
    it, and the only honest thing left to say is "not found". Knowing that a
    closer match lies ahead lets the answer be "that is further on than you
    have got — shall I take you there anyway?", which is the true one.
    """

    hits: list[Passage]
    searched_to_ms: int | None
    better_ahead: Passage | None


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
        self._remember_heard(gid, position_ms)
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

    def _remember_heard(self, gid: int, position_ms: int) -> None:
        """Record the furthest point reached, never letting it go backwards."""
        with self._conn:
            self._conn.execute(
                "UPDATE books SET heard_to_ms = MAX(heard_to_ms, ?) WHERE gid = ?",
                (position_ms, gid),
            )

    def heard_to_ms(self, gid: int) -> int:
        row = self._conn.execute(
            "SELECT heard_to_ms FROM books WHERE gid = ?", (gid,)
        ).fetchone()
        return int(row["heard_to_ms"]) if row else 0

    def find_passage(
        self, gid: int, query: str, k: int = 5, spoiler_free: bool = True
    ) -> Search:
        """Search a book for a passage — an event, a character, a moment.

        With ``spoiler_free`` (the default) the search stops at the furthest
        point they have ever reached, and reports separately whether a closer
        match lies beyond it. Pass False once they have said they don't mind.

        The bound is the high-water mark rather than the current position
        because the agent can move them backwards: having been taken back to
        chapter two must not un-hear chapters three to twenty.
        """
        before_ms: int | None = None
        if spoiler_free:
            position = self.get_position(gid)  # also records the high-water mark
            heard = self.heard_to_ms(gid)
            if heard and not (position is not None and position.finished):
                # Include the sentence being spoken, not just what precedes it.
                before_ms = heard + 60_000

        hits = find_passage(
            self._conn, self.embedder, gid, query, k=k, before_ms=before_ms
        )
        better_ahead: Passage | None = None
        if before_ms is not None:
            whole_book = find_passage(self._conn, self.embedder, gid, query, k=k)
            ahead = [p for p in whole_book if p.start_ms > before_ms]
            floor = hits[0].distance if hits else float("inf")
            if ahead and ahead[0].distance < floor:
                better_ahead = ahead[0]
        return Search(hits=hits, searched_to_ms=before_ms, better_ahead=better_ahead)

    def move_to(self, gid: int, position_ms: int) -> str:
        """Move the book to a point, so pressing play resumes there.

        This replaced planting a bookmark. A bookmark is only a signpost: it
        still has to be found in a list of every other bookmark, in the dark,
        by someone who is half asleep. Moving the position means the next tap
        on play is already in the right place.

        Any player still holding an open session on this book is ended first.
        A session is the authority on where the book is while it lasts, so
        writing underneath a live one is silently undone a few seconds later.

        Then it checks. A player whose session is closed underneath it opens a
        new one and reports where *it* thinks the book is, which put the
        position back and made the first attempt of the night look like it did
        nothing at all. Losing that race once is normal; losing it three times
        means something is playing that will not be talked out of it, and
        saying so is more use at 2am than a confident lie.
        """
        abs_client = self._require_abs()
        item_id = self._abs_item_id(gid)
        target_s = position_ms / 1000
        interrupted = False

        for attempt in range(3):
            live = abs_client.open_sessions(item_id)
            interrupted = interrupted or bool(live)
            for session_id in live:
                abs_client.close_session(session_id)
            abs_client.set_position(item_id, target_s)

            # Nothing playing, nothing to argue with: don't make them wait for
            # a race that cannot happen. A player that was running gets a
            # couple of seconds to reopen a session and put the book back.
            if live:
                time.sleep(self._cfg.move_settle_s)
            if self._is_at(item_id, target_s):
                if attempt:
                    logger.info("move to %d took %d tries", position_ms, attempt + 1)
                break
            logger.warning("position was put back after moving to %d", position_ms)
        else:
            return (
                "Something is playing that keeps putting the book back where it"
                " was. Stop it and ask me again."
            )

        moved = f"Moved to {format_timestamp(position_ms)}."
        if interrupted:
            # They will not have heard it stop: the audio already in flight
            # keeps playing, and only the next press of play starts from here.
            return f"{moved} A player was running, so it was stopped first."
        return moved

    def _is_at(self, item_id: str, target_s: float) -> bool:
        """Did the move stick, or has a player already overwritten it?"""
        progress = self._require_abs().progress(item_id)
        if progress is None:
            return False
        return abs(float(progress.get("currentTime", 0.0)) - target_s) < 2.0


def format_timestamp(ms: int) -> str:
    """Global milliseconds as h:mm:ss — how a listener thinks about position."""
    seconds = ms // 1000
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
