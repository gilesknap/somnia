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

__all__ = ["Book", "Library", "Moved", "Position"]

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
class Moved:
    """What a move did, for the three callers that each want a different part.

    The model reads ``sentence``, and so does the listener on the turns where
    the model acts and then says nothing. The page gets the numbers: ``gid`` and
    ``position_ms`` say where to go, and ``seq`` is what stops it being dragged
    straight back — a page that adopted the position without the count would
    have its next report refused, and the refusal would carry it back to the
    move target after it had already played on.

    ``seq`` counts up from zero on every move that lands, so a zero here means
    no move landed at all: there is no such book, and there is nothing for the
    page to follow.
    """

    gid: int
    position_ms: int
    seq: int
    sentence: str


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
        """What Audiobookshelf calls this book, or "" if it has never seen it.

        An absence, not an error. A book somnia rendered before ABS last scanned
        the library has no item there, and since the page is the player that no
        longer stops anything — it only means there is nowhere to send the
        courtesy write.
        """
        row = self._conn.execute(
            "SELECT abs_item_id FROM books WHERE gid = ?", (gid,)
        ).fetchone()
        item_id: str = row["abs_item_id"] if row else ""
        return item_id

    def get_position(self, gid: int) -> Position | None:
        """Where the listener left off, and the text at that point.

        Read from somnia's own record, not from Audiobookshelf. The page is the
        player now and reports here every few seconds while it plays; ABS only
        ever hears about a position afterwards, as a courtesy, so asking it
        would answer with whatever it was last told — seconds out at best, and
        a whole night out on a book played entirely from the page.

        A NULL position means they have never started this book. Nobody is at
        0:00:00, and collapsing the two would make "you haven't begun this one"
        unsayable.
        """
        book = self.book(gid)
        if book is None:
            return None
        row = self._conn.execute(
            "SELECT position_ms FROM books WHERE gid = ?", (gid,)
        ).fetchone()
        if row is None or row["position_ms"] is None:
            return None
        position_ms = int(row["position_ms"])
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
            # Not the naive `>= total_ms`. A book still rendering has a
            # total_ms that covers only what exists so far, so that form would
            # call it finished the moment they caught up with the renderer —
            # and find_passage switches the spoiler guard *off* for a finished
            # book, on precisely the book most able to spoil itself.
            finished=book.status == "done" and position_ms >= book.total_ms - 1000,
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

        The bound is the high-water mark and nothing else. Not the current
        position, because the agent can move them anywhere: backwards, where
        having been taken to chapter two must not un-hear chapters three to
        twenty, and forwards, where treating where they were put as what they
        have heard would unlock the whole book behind a single move. Not a
        status of done either — that says the rendering finished, not that
        anybody listened to it.

        A mark of zero therefore bounds the search at the beginning of the book
        rather than leaving it unbounded, which is what it used to do. Zero
        means nothing has been heard, and that is precisely when the whole book
        is ahead of them; reading it as "no limit" turned the guard off on every
        book the page has never played — since the position pivot, every book
        there is — and had the agent free to quote the ending of something they
        are three chapters into.

        What that costs is night one: until they have listened to some of a
        book, a search finds nothing in range and the agent has to say the match
        lies further on than they have got and offer to take them there. That is
        one question in the dark, and they can answer it. The other way round
        they cannot un-hear the answer.
        """
        before_ms: int | None = None
        if spoiler_free:
            position = self.get_position(gid)
            if position is None or not position.finished:
                # Include the sentence being spoken, not just what precedes it.
                before_ms = self.heard_to_ms(gid) + 60_000

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

    def move_to(self, gid: int, position_ms: int) -> Moved:
        """Take them to a point in the book, and play from there.

        This replaced planting a bookmark. A bookmark is only a signpost: it
        still has to be found in a list of every other bookmark, in the dark, by
        someone who is half asleep. Moving takes them there instead.

        One write does the whole job. The row is what the page reads on load and
        what its reports are refused against, so raising the count beside the
        position is the move as far as the page is concerned: the next thing it
        hears back tells it to jump, and it does.

        There used to be a fight here — sessions to close, a wait to settle, and
        three attempts at outlasting a running Audiobookshelf player that kept
        syncing its own position back over this one. Nothing but the page plays
        the book now, so there is nobody left to argue with. ABS is told
        afterwards, out of courtesy, and can fail without anyone noticing.
        """
        seq = self._write_position(gid, position_ms)
        if seq is None:
            # The model named a book that is not here. Saying so is worth more
            # at 2am than a traceback, and there is no move for the page to
            # follow — which a seq of zero is exactly how to say.
            return Moved(gid, position_ms, 0, f"There is no book {gid} here.")
        self._tell_abs(gid, position_ms)
        return Moved(
            gid=gid,
            position_ms=position_ms,
            seq=seq,
            # Read out verbatim when the model acts and then says nothing, so it
            # has to stand on its own. It does not say to press play, because
            # nobody has to any more.
            sentence=f"Moved to {format_timestamp(position_ms)},"
            " and it plays from there.",
        )

    def _write_position(self, gid: int, position_ms: int) -> int | None:
        """Record a move where the page will find it, and count it.

        The count is the only thing that tells an agent move apart from the
        page's own reports of where it has got to, which leave it alone. A
        number higher than the one the page holds can therefore only be a move
        it has not applied, which is what lets it act on one unconditionally.

        ``heard_to_ms`` is deliberately untouched. Being taken back to chapter
        two must not un-hear chapters three to twenty, or the whole stretch they
        had already listened to becomes unsearchable for the rest of the night.

        None if there is no such book: the guarded UPDATE returns no row at all,
        which is the cheapest way to ask and answer in one statement.
        """
        with self._conn:
            row = self._conn.execute(
                "UPDATE books SET position_ms = ?, position_seq = position_seq + 1,"
                " position_at = datetime('now') WHERE gid = ?"
                " RETURNING position_seq",
                (position_ms, gid),
            ).fetchone()
        return int(row["position_seq"]) if row is not None else None

    def _tell_abs(self, gid: int, position_ms: int) -> None:
        """Keep Audiobookshelf's idea of the position in step, if it has one.

        Best effort on purpose. The ABS app is not the player any more, so a
        write that fails costs nothing tonight, and a book somnia rendered
        before ABS ever scanned it has no item to write to at all. This must
        never turn a move that worked into an error at 2am.
        """
        item_id = self._abs_item_id(gid)
        if self._abs is None or not item_id:
            return
        try:
            self._abs.set_position(item_id, position_ms / 1000)
        except Exception:
            logger.warning("ABS position write failed; continuing", exc_info=True)


def format_timestamp(ms: int) -> str:
    """Global milliseconds as h:mm:ss — how a listener thinks about position."""
    seconds = ms // 1000
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
