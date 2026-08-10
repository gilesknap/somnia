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
the position is somnia's own record, kept here, and there is nobody else to ask.
"""

import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .db import connect
from .library import Finished, Renamed, finish_book, inside_library, rename_book
from .pgau import source_of

__all__ = [
    "BookEntry",
    "BookList",
    "Chapter",
    "Manifest",
    "Opened",
    "Player",
    "Report",
    "StreamSource",
]

logger = logging.getLogger(__name__)

# How far ahead of everything else the book somebody just chose is stamped, in
# whole seconds. It is not a fudge factor, it is the resolution of the column:
# ``position_at`` is written by ``datetime('now')``, which counts whole seconds,
# and a tie between two books is broken by ``created_at`` — so a stamp that only
# equalled the newest would hand a reload back to the book they just left,
# depending on which of them happened to be added first.
#
# One second is not enough either, because the write it has to beat is the
# parting report of the book being left behind: the page sends that within
# milliseconds of asking for this one, and the two can land either side of a
# second boundary. Two whole seconds is the first value that is strictly greater
# than anything already in flight, whichever side of that boundary it lands. A
# parting report held up longer than that by the tailnet would still land last
# and still win, and that is left alone: the cost is a launch that opens the
# book they came from, which one more press puts right.
#
# It costs a stamp up to two seconds in the future, and nothing reads it for
# anything but the ordering above. It used to be read a second time, as the
# ceiling on how much playback the next report might claim — that ceiling went
# with the mark it protected (ADR 10), and with it the one place where a stamp in
# the future could do any harm.
OPENED_AHEAD_S = 2


@dataclass
class BookEntry:
    """A book as the launcher needs it: enough to name it and to resume it."""

    gid: int
    title: str
    authors: str
    status: str
    total_ms: int
    chapters: int
    # How many chapters the book has, against ``chapters`` above, which is how
    # many of them have been rendered. They are the same number on a book that
    # finished rendering and different on every book that did not, and the two
    # are the whole of what a coverage line says: all of it is here, or this
    # much of that much is. 0 means nobody wrote it down — true of anything
    # rendered before the column existed — and a page that has 0 has to say
    # nothing at all rather than "of 0", which the player already does.
    chapters_total: int
    position_ms: int | None
    seq: int
    # When the reader said they were done with it, or None while they are not.
    # A book that is finished is still a book somnia has — it plays, it holds
    # its position, and nothing about it is taken away — so this is one more
    # thing said about it rather than a reason to leave it out of the answer.
    # Which screens draw a finished book, and where, is the page's to decide.
    finished_at: str | None
    # When somnia was first asked for it, which is the only date a book has
    # that is about the reader rather than about the render: it is what "brought
    # in" means and what an ordering by how new a book is has to be built on.
    # It is already the tie-break under ``position_at`` in the ordering below,
    # so this is that same column said out loud rather than a new fact.
    created_at: str
    # Which of the two libraries the book came out of, in the same word a search
    # result carries it in. Nothing stores it: it is the gid read against the
    # Australian offset, which is arithmetic that belongs on this side of the
    # wire — a page that worked it out for itself would be holding a copy of a
    # constant it cannot see move.
    source: str


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
class Opened:
    """A book made the one a cold launch opens, and where it resumes.

    The position and the count are the book's own, untouched — they are here
    because the caller has just made this the current book and this is what
    that book was left at. Nothing here is new state: a page that took the
    manifest instead would read exactly the same two numbers.
    """

    gid: int
    position_ms: int | None
    seq: int


@dataclass
class Chapter:
    """One chapter of the timeline, and where its audio can be fetched.

    ``start_ms`` and ``end_ms`` are on the book's clock — the render clock,
    counted in PCM samples before encoding — which is the clock that search
    results and the saved position both speak. The page must never derive them
    by summing what the decoder reports, which drifts by tens of milliseconds a
    chapter and is a second out by chapter forty.

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

    ``chapters_total`` is how many chapters the book *has*, against the
    ``chapters`` list, which is how many of them can be played. While a render
    is going those two differ, and the difference is the only way the page can
    tell running out of audio three chapters into thirty-nine — which is not the
    end of the book — from reaching the end of one. It is 0 for every book
    rendered before that column existed, and 0 means nobody wrote it down, so a
    page that finds one has to say nothing rather than say "3 of 0".

    ``stream_url`` is the whole of what has been read of this book, down one
    URL, so that crossing a chapter need not touch the media element — see
    :mod:`somnia.stream` for why that matters at 2am. ``stream_ms`` is how much
    book it covers, on the render clock, which is the number that tells the end
    of the book from the end of what has been read of it so far. Both are per
    fetch: a book that grew has a longer stream at a different URL, and the one
    a phone already has open is never rewritten.

    None means play it a chapter at a time. That is not an error case to be
    swept up — it is a book with no audio yet, and it is every somnia serving a
    manifest older than this field. The per-chapter ``url`` on every
    :class:`Chapter` stays for exactly that, and costs nothing to keep.
    """

    gid: int
    title: str
    authors: str
    status: str
    total_ms: int
    chapters_total: int
    position_ms: int | None
    seq: int
    stream_url: str | None
    stream_ms: int
    chapters: list[Chapter]


@dataclass
class StreamSource:
    """The chapters one version of a book's stream is joined from.

    ``span_ms`` is how much book they hold, on the render clock. It travels with
    the files because it is what the finished join is judged against: ffmpeg
    will report an unreadable chapter and then exit zero with a short file, so
    the only thing that says a stream is the whole of what was asked for is the
    clock the rows already keep. See :mod:`somnia.stream`.
    """

    files: list[Path]
    span_ms: int


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
    reason: str | None = None


class Player:
    """What the page asks for: which books there are, and the audio of one.

    Its own connection, opened cross-thread because the server's handlers run
    in a threadpool, and its own lock because sqlite connections are not
    thread-safe. Every statement is taken under it; nothing here waits on
    anything but the disk.
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
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
                " b.chapters_total, b.created_at,"
                " b.position_ms, b.position_seq, b.position_at, b.finished_at,"
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
                chapters_total=row["chapters_total"],
                position_ms=row["position_ms"],
                seq=row["position_seq"],
                finished_at=row["finished_at"],
                created_at=row["created_at"],
                source=source_of(int(row["gid"])),
            )
            for row in rows
        ]
        # Taken from the head of the same ordering rather than from a second
        # query, so the book the page opens can never disagree with the list it
        # is shown — datetime('now') only counts whole seconds, and two books
        # touched in the same second would otherwise be free to differ.
        last_gid = books[0].gid if rows and rows[0]["position_at"] else None
        return BookList(last_gid=last_gid, books=books)

    def open_book(self, gid: int) -> Opened | None:
        """Make this the book a cold launch opens, and say where it resumes.

        The whole of switching books, and it writes one column. ``last_gid`` is
        simply the book with the newest ``position_at``, and positions have
        always been kept per book, so there is no new state here and no second
        place a position is remembered: the book they chose is resumed by being
        made the most recent one, at whatever it was left at.

        What it must not touch is everything else in that row. ``position_ms``
        stays where the last report put it, because opening a book is not
        listening to it and a book they change their mind about must be exactly
        as they left it — and since the position is now the whole of what the
        spoiler guard reads, leaving it alone is also what keeps opening a book
        from unlocking anything in it. And ``position_seq`` stays because that
        number counts agent moves and
        nothing else — bumping it here would refuse the page's next report and
        drag the listener back to wherever the server thought they were, which
        is the failure ADR 4 already refused for a chosen row.

        Refused for a book with no audio at all, which is a book still waiting
        on its first chapter or a render that died before one. That is the whole
        reason the check is here rather than only on the page: making a book
        nobody can play the one a cold launch opens would leave the next reload
        waiting on a render instead of on the book that was playing, and a
        listener who pressed something in the dark cannot see that happen.

        The timestamp is two seconds ahead of everything else; see
        :data:`OPENED_AHEAD_S` for why it is ahead at all.
        """
        with self._lock, self._conn:
            row = self._conn.execute(
                "UPDATE books SET position_at = datetime(MAX(datetime('now'),"
                # COALESCE inside MAX and not around it: sqlite's scalar MAX is
                # NULL if any argument is, so a database whose other books have
                # never been played would otherwise clear the column it is
                # setting. '' loses to any real timestamp, which is what makes
                # it the right stand-in for "nothing to beat".
                " COALESCE((SELECT MAX(position_at) FROM books WHERE gid <> ?),"
                " '')), ?)"
                # A book with no chapters row has nothing to play, and the page
                # would sit on "the first chapter is still being read" for as
                # long as it took somebody to notice.
                " WHERE gid = ? AND EXISTS"
                " (SELECT 1 FROM chapters c WHERE c.book_gid = books.gid)"
                " RETURNING position_ms, position_seq",
                (gid, f"+{OPENED_AHEAD_S} seconds", gid),
            ).fetchone()
        if row is None:
            return None
        return Opened(gid=gid, position_ms=row["position_ms"], seq=row["position_seq"])

    def finish(self, gid: int, finished: bool) -> Finished:
        """Mark a book finished, or put it back on the shelf.

        On this lane rather than the queue's, because it writes the ``books``
        row and every other write to that row — the position reports, the open
        — is taken under this lock. The delete is the exception and belongs
        where it is: the first thing it has to do is ask the queue.

        The work itself is :func:`somnia.library.finish_book`; this is the lock
        around it, the same way :meth:`open_book` is the lock around one UPDATE.
        """
        with self._lock:
            return finish_book(self._conn, gid, finished)

    def rename(self, gid: int, title: str, authors: str) -> Renamed:
        """Say what a book is called, under the lock the ``books`` row is kept.

        Beside :meth:`finish` and for the same reason: it writes that row, and
        every other write to it is taken here. The work is
        :func:`somnia.library.rename_book`.
        """
        with self._lock:
            return rename_book(self._conn, gid, title, authors)

    def manifest(self, gid: int) -> Manifest | None:
        """The whole timeline of one book, or None if there is no such book."""
        with self._lock:
            book = self._conn.execute(
                "SELECT gid, title, authors, status, total_ms, chapters_total,"
                " position_ms, position_seq FROM books WHERE gid = ?",
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
            chapters_total=book["chapters_total"],
            position_ms=book["position_ms"],
            seq=book["position_seq"],
            # Advertised on the strength of the rows and not of the file: the
            # join happens on the first ask, in the request that wants it, so
            # there is nothing here for a manifest to look at. A book with no
            # chapters has nothing to join and says so; a book whose join then
            # turns out to be impossible answers 404 to a page that still has a
            # url for every chapter to fall back on. Building it here to find
            # out would put a second or two of ffmpeg in front of every poll of
            # a book that is still being read, which is one every five seconds.
            stream_url=f"api/stream/{gid}/{len(chapters)}" if chapters else None,
            # What the stream holds, measured from the beginning of the book,
            # because that is what the page maps element seconds onto. It is
            # short of total_ms only while a render is running — the difference
            # is audio that exists in the manifest and not yet in any stream.
            stream_ms=chapters[-1]["end_ms"] if chapters else 0,
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

    def report(self, gid: int, position_ms: int, seq: int) -> Report:
        """Take the page's word for where the book is, unless it is out of date.

        Compare-and-swap on ``position_seq``, which counts agent moves and
        nothing else: a page saying where it has got to leaves the count alone.
        That asymmetry is the whole design. It means an empty result set has
        exactly one meaning — the agent has moved this book since the page last
        looked — so the page can apply the refusal unconditionally. Were a page
        report to bump the count too, every acknowledgement lost on a flaky
        tailnet would look like a move, and the listener would be yanked
        backwards fifteen seconds at random all night.

        One column, and it is the position. There was a second until ADR 10 — a
        mark of how far the sound had really reached, which the spoiler guard
        was drawn at rather than here, and which every report had to prove it
        had earned by counting its own playback off the media clock. It is gone,
        and with it the count on the report, the wall-clock ceiling over that
        count, and the slack that decided what was a listen and what was a jump.

        What it cost is worth writing down, because it is why this is now one
        statement. A report standing further past the mark than it had playback
        to show for could not be credited, and after a forward skip every report
        stands past a stretch nothing was heard over — so one press of the skip
        button stopped the mark for the rest of the book, and the gap only ever
        grew from there. The guard then bounded every question at the last place
        they listened straight through, which after an evening of skipping is
        nowhere near where they are, and the agent spent the night saying that
        things behind them lay ahead.
        """
        with self._lock, self._conn:
            row = self._conn.execute(
                "UPDATE books SET position_ms = ?, position_at = datetime('now')"
                " WHERE gid = ? AND position_seq = ?"
                " RETURNING position_seq",
                (position_ms, gid, seq),
            ).fetchone()
            if row is not None:
                # The seq handed back is the one that was sent. Saying so out
                # loud is what the page checks a lost reply against.
                return Report(
                    accepted=True,
                    gid=gid,
                    position_ms=position_ms,
                    seq=row["position_seq"],
                )
            current = self._conn.execute(
                "SELECT position_ms, position_seq FROM books WHERE gid = ?",
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
            reason="moved",
        )

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

    def passage_at(self, gid: int, ms: int) -> str | None:
        """The book's own words at ``ms``, never any further on than they are.

        For the "you are here" row on the list of places. Every other row on
        that screen carries its words down with the answer that named it; this
        one names no passage at all — it is a rule drawn at wherever the book
        has got to tonight, which normally falls between two of the places and
        inside none — so its words are the one thing on that screen the page has
        to come back and ask for.

        The guard is in the statement rather than in a branch above it, and that
        is the whole of why this route is safe to exist. ``start_ms <
        position_ms`` is the spoiler guard's own predicate — it is exactly what
        :class:`somnia.tools.Candidate` calls not being ``ahead``, written the
        other way round — and it is applied to the row, not to the argument: a
        caller who asks about a point an hour past where the book has got to is
        answered with the last passage behind them, not refused and not obliged.
        So there is no number to guess and no error to read a frontier off.

        None when there is nothing to say: no such book, a book whose text was
        never indexed, or a book nobody has started — the last of those falls
        out of the same comparison, since a NULL position matches no row at all,
        which is the answer "never started" deserves rather than the answer
        0:00:00 would get. The row simply offers no reveal then, which is what
        it did before this existed.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT chunks.text FROM chunks JOIN books ON books.gid ="
                " chunks.book_gid WHERE chunks.book_gid = ? AND chunks.start_ms"
                " <= ? AND chunks.start_ms < books.position_ms"
                " ORDER BY chunks.start_ms DESC LIMIT 1",
                (gid, ms),
            ).fetchone()
        return str(row["text"]) if row is not None else None

    def chapter_file(self, gid: int, idx: int) -> Path | None:
        """The audio of one chapter, or None if it cannot honestly be served.

        The caller never names a file: it names a book and a chapter, and the
        path comes from the row. That is the whole of the traversal defence,
        and it has to be, because the server has no auth by design — anything
        that took a path from the request would be a read of the entire VPS.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT audio_file FROM chapters WHERE book_gid = ? AND idx = ?",
                (gid, idx),
            ).fetchone()
        if row is None:
            return None
        return self._playable(row["audio_file"], f"chapter {gid}/{idx}")

    def stream_source(self, gid: int, n: int) -> StreamSource | None:
        """What a stream covering a book's first ``n`` chapters is made of.

        A version is a prefix of the book, named by how many chapters it holds,
        so this answers about a book as it was some number of chapters ago as
        readily as about the book as it is now. That is what lets a page that
        loaded version twelve at eleven o'clock keep playing it while the render
        runs on ahead — and it is why the file for a given ``n`` can always be
        made again from the same chapters, byte for byte, if it ever has to be.

        None means there is nothing honest to join: fewer chapters than were
        asked for, none at all, or one whose audio is missing or lies outside
        the library. A stream with a hole in it is not this book, and it would
        be one that stops in the night at the hole.
        """
        if n < 1:
            return None
        with self._lock:
            rows = self._conn.execute(
                "SELECT idx, start_ms, end_ms, audio_file FROM chapters"
                " WHERE book_gid = ? ORDER BY idx",
                (gid,),
            ).fetchall()
        if len(rows) < n:
            return None
        rows = rows[:n]
        files: list[Path] = []
        for row in rows:
            path = self._playable(row["audio_file"], f"chapter {gid}/{row['idx']}")
            if path is None:
                return None
            files.append(path)
        return StreamSource(
            files=files, span_ms=rows[-1]["end_ms"] - rows[0]["start_ms"]
        )

    def _playable(self, audio_file: str, what: str) -> Path | None:
        """A row's path, if it is inside the library and really there.

        The containment half is :func:`somnia.library.inside_library`, which is
        also what a delete asks before it unlinks anything. Two answers to
        "is this file the library's" would be one answer too many.

        The other half stays here, because it is only true of serving. A
        chapter that has been deleted, or has not finished rendering, is an
        absence rather than a traceback — but it is nothing to delete either,
        so a delete must not treat the same missing file as a refusal.
        """
        path = inside_library(self._cfg, audio_file, what)
        return path if path is not None and path.is_file() else None
