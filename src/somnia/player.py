"""The fast lane: the manifest, the audio, and where they are.

Everything here answers in milliseconds off disk, so it gets its own sqlite
connection and its own lock rather than sharing
:class:`somnia.server.Conversations`. A seek at 2am must never queue behind a
twenty-second model turn — a blank player while a question is being answered is
exactly the moment the phone gets put down.

The rows this reads are the ones ingest already writes: ``chapters`` has idx,
title, start_ms, end_ms and audio_file, so the player's manifest is one SELECT.
The only thing it may not hand to the page is ``audio_file`` itself, which is an
absolute path on the VPS. Chapters are addressed by index and resolved here.

It writes one thing: where they have got to. That is the pivot in a sentence —
the position is somnia's own record now, kept here rather than asked of
Audiobookshelf, which is told afterwards as a courtesy and never read.
"""

import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .abs import AbsClient
from .config import Config
from .db import connect

__all__ = ["BookEntry", "BookList", "Chapter", "Manifest", "Player", "Report"]

logger = logging.getLogger(__name__)


@dataclass
class BookEntry:
    """A book as the launcher needs it: enough to name it and to resume it."""

    gid: int
    title: str
    authors: str
    status: str
    total_ms: int
    chapters: int
    position_ms: int | None
    seq: int


@dataclass
class BookList:
    """Every book, most recently listened to first.

    ``last_gid`` is what a cold launch opens. It is None only when nothing has
    ever been played, which is the one time it is fair to ask which book they
    want.
    """

    last_gid: int | None
    books: list[BookEntry]


@dataclass
class Chapter:
    """One chapter of the timeline, and where its audio can be fetched.

    ``start_ms`` and ``end_ms`` are on the book's clock — the render clock,
    counted in PCM samples before encoding — which is the clock that search
    results, ABS chapter marks and the saved position all speak. The page must
    never derive them by summing what the decoder reports, which drifts by tens
    of milliseconds a chapter and is a second out by chapter forty.

    ``url`` is relative because the app may be mounted under a path, and it is
    built here so the page never has to think about encoding a file name like
    ``001 - The First Tone.m4a``.
    """

    idx: int
    title: str
    start_ms: int
    end_ms: int
    url: str


@dataclass
class Manifest:
    """One book, whole: the timeline, the position, and what has been heard.

    Deliberately one round trip. The page needs all of this before it can put a
    finger on the play button, and two fetches at 2am on a tailnet is two
    chances to be left with a player that shows nothing.
    """

    gid: int
    title: str
    authors: str
    status: str
    total_ms: int
    position_ms: int | None
    seq: int
    heard_to_ms: int
    chapters: list[Chapter]


@dataclass
class Report:
    """What became of a page's account of where it has got to.

    A refusal is not a failure — it is the protocol working, and it carries
    what the page missed. The only thing that can refuse a report is the agent
    having moved the book underneath it, so the refusal is also the instruction:
    go here instead. That is why it is answered 200 with a body rather than a
    409, which a beacon could not read at all.
    """

    accepted: bool
    gid: int
    position_ms: int | None = None
    seq: int | None = None
    heard_to_ms: int | None = None
    reason: str | None = None


class Player:
    """What the page asks for: which books there are, and the audio of one.

    Its own connection, opened cross-thread because the server's handlers run
    in a threadpool, and its own lock because sqlite connections are not
    thread-safe. Every statement is taken under it; nothing here waits on
    anything but the disk.

    ``abs_client`` is only ever written to, never read, and only when the
    listener has stopped. Audiobookshelf is no longer the player and no longer
    the record — it is somewhere else they might one day open the book.
    """

    def __init__(self, cfg: Config, abs_client: AbsClient | None = None) -> None:
        self._cfg = cfg
        self._abs = abs_client
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = connect(cfg.db_path, cross_thread=True)

    def close(self) -> None:
        """Give the connection back, so shutdown is not a ResourceWarning."""
        with self._lock:
            self._conn.close()

    def books(self) -> BookList:
        """Every book somnia has, the one they were last listening to first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT b.gid, b.title, b.authors, b.status, b.total_ms,"
                " b.position_ms, b.position_seq, b.position_at,"
                " (SELECT COUNT(*) FROM chapters c WHERE c.book_gid = b.gid)"
                " AS chapters"
                " FROM books b"
                " ORDER BY b.position_at DESC NULLS LAST, b.created_at DESC"
            ).fetchall()
        books = [
            BookEntry(
                gid=row["gid"],
                title=row["title"],
                authors=row["authors"],
                status=row["status"],
                total_ms=row["total_ms"],
                chapters=row["chapters"],
                position_ms=row["position_ms"],
                seq=row["position_seq"],
            )
            for row in rows
        ]
        # Taken from the head of the same ordering rather than from a second
        # query, so the book the page opens can never disagree with the list it
        # is shown — datetime('now') only counts whole seconds, and two books
        # touched in the same second would otherwise be free to differ.
        last_gid = books[0].gid if rows and rows[0]["position_at"] else None
        return BookList(last_gid=last_gid, books=books)

    def manifest(self, gid: int) -> Manifest | None:
        """The whole timeline of one book, or None if there is no such book."""
        with self._lock:
            book = self._conn.execute(
                "SELECT gid, title, authors, status, total_ms, position_ms,"
                " position_seq, heard_to_ms FROM books WHERE gid = ?",
                (gid,),
            ).fetchone()
            if book is None:
                return None
            chapters = self._conn.execute(
                "SELECT idx, title, start_ms, end_ms FROM chapters"
                " WHERE book_gid = ? ORDER BY idx",
                (gid,),
            ).fetchall()
        return Manifest(
            gid=book["gid"],
            title=book["title"],
            authors=book["authors"],
            status=book["status"],
            total_ms=book["total_ms"],
            position_ms=book["position_ms"],
            seq=book["position_seq"],
            heard_to_ms=book["heard_to_ms"],
            chapters=[
                Chapter(
                    idx=row["idx"],
                    title=row["title"],
                    start_ms=row["start_ms"],
                    end_ms=row["end_ms"],
                    url=f"api/audio/{gid}/{row['idx']}",
                )
                for row in chapters
            ],
        )

    def report(self, gid: int, position_ms: int, seq: int, playing: bool) -> Report:
        """Take the page's word for where the book is, unless it is out of date.

        Compare-and-swap on ``position_seq``, which counts agent moves and
        nothing else: a page saying where it has got to leaves the count alone.
        That asymmetry is the whole design. It means an empty result set has
        exactly one meaning — the agent has moved this book since the page last
        looked — so the page can apply the refusal unconditionally. Were a page
        report to bump the count too, every acknowledgement lost on a flaky
        tailnet would look like a move, and the listener would be yanked
        backwards fifteen seconds at random all night.

        The high-water mark rises only when something was actually playing. A
        page sitting paused while a question is asked has heard nothing, and a
        forward seek followed immediately by a pause would otherwise mark the
        skipped stretch as heard and give the spoiler guard away.
        """
        # MAX(x, 0) is a no-op on a column that is NOT NULL DEFAULT 0, so the
        # paused case needs no second statement.
        heard_ms = position_ms if playing else 0
        with self._lock, self._conn:
            row = self._conn.execute(
                "UPDATE books SET position_ms = ?, position_at = datetime('now'),"
                " heard_to_ms = MAX(heard_to_ms, ?)"
                " WHERE gid = ? AND position_seq = ?"
                " RETURNING position_seq, heard_to_ms",
                (position_ms, heard_ms, gid, seq),
            ).fetchone()
            if row is not None:
                # The seq handed back is the one that was sent. Saying so out
                # loud is what the page checks a lost reply against.
                return Report(
                    accepted=True,
                    gid=gid,
                    position_ms=position_ms,
                    seq=row["position_seq"],
                    heard_to_ms=row["heard_to_ms"],
                )
            current = self._conn.execute(
                "SELECT position_ms, position_seq, heard_to_ms FROM books"
                " WHERE gid = ?",
                (gid,),
            ).fetchone()
        if current is None:
            # Deleted, or a page left open on a book from another database.
            # Telling it so is what stops it reporting about it all night.
            return Report(accepted=False, gid=gid, reason="gone")
        return Report(
            accepted=False,
            gid=gid,
            position_ms=current["position_ms"],
            seq=current["position_seq"],
            heard_to_ms=current["heard_to_ms"],
            reason="moved",
        )

    def tell_abs(self, gid: int, position_ms: int) -> None:
        """Keep Audiobookshelf's idea of the position in step, if it has one.

        Best effort, and off the critical path: the reply has already gone out
        by the time this runs. The ABS app is not the player any more, so a
        write that fails costs nothing tonight, and a book somnia rendered
        before ABS ever scanned it has no item to write to at all. What it buys
        is that the position is right at the moment someone next opens ABS
        somewhere else — which is why it is only worth doing when they have
        stopped, and never on a tick.
        """
        if self._abs is None:
            return
        with self._lock:
            row = self._conn.execute(
                "SELECT abs_item_id FROM books WHERE gid = ?", (gid,)
            ).fetchone()
        item_id: str = row["abs_item_id"] if row else ""
        if not item_id:
            return
        try:
            self._abs.set_position(item_id, position_ms / 1000)
        except Exception:
            logger.warning("ABS position write failed; continuing", exc_info=True)

    def sentence_start(self, gid: int, ms: int) -> int | None:
        """Where the sentence being spoken at ``ms`` began, if anything knows.

        For the page's smart rewind. Someone who paused for an hour was asleep
        long before the sound stopped, so coming back needs more than the last
        few seconds — and dropping them into the middle of a sentence gives them
        a clause with no beginning, which is worse than the silence was.

        The chunks table is the only record of where sentences fall. Its rows
        are overlapping three-sentence windows taken every second sentence, so a
        window start is always a sentence start, and the nearest one at or
        before a point is at most two sentences back. That is close enough to be
        the thing the page snaps to, and it is already indexed by
        ``chunks_book`` on (book_gid, start_ms).

        None when there is nothing to say: no such book, or a book whose text
        was never indexed. The page's question is only ever "is there a better
        place to land than the one I worked out?", and to that, "no" and "no
        such book" are the same answer.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT start_ms FROM chunks WHERE book_gid = ? AND start_ms <= ?"
                " ORDER BY start_ms DESC LIMIT 1",
                (gid, ms),
            ).fetchone()
        return int(row["start_ms"]) if row is not None else None

    def chapter_file(self, gid: int, idx: int) -> Path | None:
        """The audio of one chapter, or None if it cannot honestly be served.

        The caller never names a file: it names a book and a chapter, and the
        path comes from the row. That is the whole of the traversal defence,
        and it has to be, because the server has no auth by design — anything
        that took a path from the request would be a read of the entire VPS.

        Containment is still checked after resolving, because the row is not
        beyond suspicion either: a symlink in the library, or a database
        carried over from a machine whose SOMNIA_LIBRARY_DIR was somewhere
        else, can both point outside. That case is logged rather than silently
        dropped — a library that has moved should be explicable from the
        journal, not guessed at.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT audio_file FROM chapters WHERE book_gid = ? AND idx = ?",
                (gid, idx),
            ).fetchone()
        if row is None:
            return None
        path = Path(row["audio_file"]).resolve()
        # expanduser as well as resolve: Config's default library_dir is the
        # literal "~/library/audiobooks", and only load_config expands it.
        library = self._cfg.library_dir.expanduser().resolve()
        if not path.is_relative_to(library):
            logger.warning("chapter %d/%d lies outside %s: %s", gid, idx, library, path)
            return None
        # A chapter that has been deleted, or has not finished rendering, is an
        # absence rather than a traceback.
        return path if path.is_file() else None
