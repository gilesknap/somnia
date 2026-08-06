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

from .abs import AbsClient, tell_abs
from .config import Config
from .db import connect

__all__ = ["BookEntry", "BookList", "Chapter", "Manifest", "Player", "Report"]

logger = logging.getLogger(__name__)

# How much further on than the clock a report may be and still be believed to
# have been played through. It covers the second datetime('now') truncates away
# at each end, the 400ms of rendered silence a chapter swap skips, and a render
# clock that can legitimately run a frame past the container's. What it must
# stay well below is thirty seconds, which is the smallest forward jump the page
# has a button for — anything bigger than this is a stretch nobody heard.
HEARD_SLACK_MS = 5_000


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

        How far they have *heard* is a different question from where the book
        is, and its honest answer is playback that really elapsed rather than a
        number that was reported. One press of the skip button is thirty
        seconds, an agent move is hours, and both arrive here as a report that
        says "playing" from further on than the last one. Believing those handed
        the whole spoiler guard away for a single nudge, and MAX() meant it
        never came back.

        So the mark rises only on a report that says the sound is on — a page
        sitting paused while a question is asked has heard nothing — and only as
        far as they could have reached by playing on from it: no further past
        the mark than the wall clock has moved since the last report that said
        the sound was on. That still believes the gaps that are real, a
        heartbeat lost on the tailnet or four minutes off the network with the
        book still playing, because elapsed time covers those honestly while a
        jump is thirty seconds of book in no seconds of clock. It is why
        ``reason`` is not consulted: a tick sent fifteen seconds after a skip is
        an honest tick, and still fifteen seconds of listening at a place they
        were never played to.

        ``playing_at`` is that clock. It is written on every report that says
        the sound is on whether or not the mark rose with it — left alone while
        the mark was stuck it would accrue until it covered the skip, and the
        mark would step over the stretch nobody heard a minute late — and
        cleared by anything that says the sound is off, so six hours face down
        on a bedside table cannot be spent by the skip that follows them. No
        clock means no time rather than no limit, which is why the page reports
        the moment the sound comes back on: that report begins the stretch and
        is believed because it has gone nowhere. Without it the first heartbeat
        after every pause would be fifteen seconds of book out of nowhere, and
        the guard would turn itself off on the first night rather than on the
        first skip.

        The cost is real and is the one worth paying: after a forward skip the
        mark stops for good, because everything reported afterwards is thirty
        seconds further on than it. Searches stay bounded at the last place they
        truly listened, and the agent offers to go on ahead rather than quoting
        what lies past it. One number cannot say "I heard this stretch but not
        that one" — that wants a set of intervals — and failing this way costs
        them a question at 2am, where failing the other way costs them the book.
        """
        with self._lock, self._conn:
            row = self._conn.execute(
                "UPDATE books SET position_ms = ?, position_at = datetime('now'),"
                " playing_at = CASE WHEN ? THEN datetime('now') END,"
                # Every expression in a SET reads the row as it was before the
                # update, so this is the previous report's playing_at and not
                # the one being written beside it. A missing clock counts as no
                # time at all rather than as no limit: the first report of a
                # stretch is believed only where it stands, never for ground in
                # front of it. MAX(x, 0) is a no-op on a column that is NOT NULL
                # DEFAULT 0, so a report that cannot be credited needs no second
                # statement.
                " heard_to_ms = MAX(heard_to_ms, CASE WHEN ? AND ? - heard_to_ms <="
                " (strftime('%s', 'now')"
                " - COALESCE(strftime('%s', playing_at), strftime('%s', 'now')))"
                " * 1000 + ?"
                " THEN ? ELSE 0 END)"
                " WHERE gid = ? AND position_seq = ?"
                " RETURNING position_seq, heard_to_ms",
                (
                    position_ms,
                    playing,
                    playing,
                    position_ms,
                    HEARD_SLACK_MS,
                    position_ms,
                    gid,
                    seq,
                ),
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
        """Look the item up, then hand the position to the courtesy write.

        Off the critical path: the reply has already gone out by the time this
        runs, and what it buys is that the position is right at the moment
        someone next opens ABS somewhere else — which is why it is only worth
        doing when they have stopped, and never on a tick.

        The lookup is here rather than inside :func:`somnia.abs.tell_abs`
        because this connection is shared with every audio request and is only
        safe under ``_lock``. The lock is given back before the write goes out:
        held across it, an ABS that hangs for its five seconds would stall the
        chapter swap this exists to stay out of the way of.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT abs_item_id FROM books WHERE gid = ?", (gid,)
            ).fetchone()
        tell_abs(self._abs, row["abs_item_id"] if row else "", position_ms)

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
