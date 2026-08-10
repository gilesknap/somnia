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

from .config import Config
from .db import connect

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

# How much further on than the playback it reports a report may stand and still
# be believed to have been played through. Because the playback appears on both
# sides of the comparison, this is exactly the size of the largest jump that can
# be laundered as listening, so it is also the number to argue about. It has to
# cover the 400ms of rendered silence a chapter swap steps over, the quarter of
# a second between the last timeupdate and a pause, the second datetime('now')
# truncates away at each end, and a render clock that can legitimately run a
# frame past the container's. What it must stay well below is thirty seconds,
# which is the smallest forward jump the page has a button for.
HEARD_SLACK_MS = 5_000

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
# It costs a stamp up to two seconds in the future, which is read in exactly one
# place — the ceiling on how much playback the *next* report may claim, in
# :meth:`Player.report`. There it makes the first report after an open measure
# against a slightly shorter interval, which can only stop the mark rising, and
# the report after that one has already put the clock back where it belongs.
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
    heard_to_ms: int
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
    heard_to_ms: int | None = None
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
        as they left it. ``heard_to_ms`` stays because nothing has been heard.
        And ``position_seq`` stays because that number counts agent moves and
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

    def manifest(self, gid: int) -> Manifest | None:
        """The whole timeline of one book, or None if there is no such book."""
        with self._lock:
            book = self._conn.execute(
                "SELECT gid, title, authors, status, total_ms, chapters_total,"
                " position_ms, position_seq, heard_to_ms FROM books WHERE gid = ?",
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
            heard_to_ms=book["heard_to_ms"],
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

    def report(self, gid: int, position_ms: int, seq: int, played_ms: int) -> Report:
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
        is, and its honest answer is playback that really came out of the
        speaker. One press of the skip button is thirty seconds, an agent move
        is hours, and both arrive here as a report from further on than the last
        one. Believing those handed the whole spoiler guard away for a single
        nudge, and MAX() meant it never came back.

        Only the page can tell the two apart, so the page is asked. Every report
        says how much of the book has really played since the last one taken,
        counted off the media clock: a stretch they listened to moves that by as
        much as it moves the position, and a jump moves the position alone. The
        mark rises to the reported position when the two agree — when the report
        stands no further past the mark than the playback it brought with it,
        give or take :data:`HEARD_SLACK_MS`. Since the playback is on both sides
        of that comparison, the slack *is* the largest jump that can be
        laundered, whatever else the night did.

        It follows that the wall clock is no longer consulted for the answer,
        only as a ceiling: no report may claim more playback than has had time
        to happen since the last one taken. Elapsed time was the answer once and
        was too generous by exactly the shape of a night — a phone spends eight
        hours asleep with the sound off, reports nothing while it does, and the
        first thing it says on waking is five hours further on, which the clock
        would have covered in full. The ceiling and the claim measure the same
        interval by construction: ``position_at`` moves only on an accepted
        report, and so does the page's idea of what it has already been credited
        with. That is what makes it safe, and it is also what catches the one
        report that legitimately claims twice — an acknowledgement lost on the
        tailnet leaves the page owing that playback again. It does assume the
        book plays at the speed it was written: a playback-rate control, which
        somnia deliberately does not have, would have to scale this or a
        listener going faster than the clock would be refused for it.

        None of this consults ``reason``, and no report is disbelieved for
        saying the sound is off. A pause is the strongest evidence in the whole
        protocol that they listened right up to where it happened, and throwing
        it away left the mark a heartbeat behind the position with no way back —
        every report afterwards stood further on than the mark by more than it
        had playback to show for, so an ordinary pause stopped the guard for the
        rest of the book. A guard that has stopped rising is not a fix.

        One cost is real and is the one worth paying: after a forward skip the
        mark stops, because everything reported afterwards stands past a stretch
        with no playback behind it. Searches stay bounded at the last place they
        truly listened until they go back over it, and the agent offers to go on
        ahead rather than quoting what lies past it. One number cannot say "I
        heard this stretch but not that one" — that wants a set of intervals —
        and failing this way costs them a question at 2am, where failing the
        other way costs them the book.
        """
        with self._lock, self._conn:
            row = self._conn.execute(
                "UPDATE books SET position_ms = ?, position_at = datetime('now'),"
                # Every expression in a SET reads the row as it was before the
                # update, so the position_at inside this one is the previous
                # report's and not the one being written beside it. A book that
                # has never been reported on has no interval to have played
                # anything in, which is why a missing timestamp counts as no
                # time rather than as no limit. MAX(x, 0) is a no-op on a column
                # that is NOT NULL DEFAULT 0, so a report that cannot be
                # credited needs no second statement.
                " heard_to_ms = MAX(heard_to_ms, CASE WHEN ? - heard_to_ms <= MIN(?,"
                " (strftime('%s', 'now')"
                " - COALESCE(strftime('%s', position_at), strftime('%s', 'now')))"
                " * 1000) + ?"
                " THEN ? ELSE 0 END)"
                " WHERE gid = ? AND position_seq = ?"
                " RETURNING position_seq, heard_to_ms",
                (
                    position_ms,
                    position_ms,
                    played_ms,
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
        """The book's own words at ``ms``, never any further on than they got.

        For the "you are here" row on the list of places. Every other row on
        that screen carries its words down with the answer that named it; this
        one names no passage at all — it is a rule drawn at wherever the book
        has got to tonight, which normally falls between two of the places and
        inside none — so its words are the one thing on that screen the page has
        to come back and ask for.

        The guard is in the statement rather than in a branch above it, and that
        is the whole of why this route is safe to exist. ``start_ms <
        heard_to_ms`` is the spoiler guard's own predicate — it is exactly what
        :class:`somnia.tools.Candidate` calls not being ``ahead``, written the
        other way round — and it is applied to the row, not to the argument: a
        caller who asks about a point an hour past where anybody has listened is
        answered with the last passage that really was spoken, not refused and
        not obliged. So there is no number to guess and no error to read a
        frontier off. The furthest this can ever hand back is the furthest the
        sound has ever reached.

        ``heard_to_ms`` and not ``position_ms``, for the reason the column
        exists: being taken backwards must not shrink what may be shown, and the
        page asks about where they are now, which is at or behind it either way.

        None when there is nothing to say: no such book, a book whose text was
        never indexed, or a book nobody has played a second of — the last of
        those falls out of the same comparison, since no passage begins before
        zero. The row simply offers no reveal then, which is what it did before
        this existed.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT chunks.text FROM chunks JOIN books ON books.gid ="
                " chunks.book_gid WHERE chunks.book_gid = ? AND chunks.start_ms"
                " <= ? AND chunks.start_ms < books.heard_to_ms"
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

        Containment is checked after resolving, because the row is not beyond
        suspicion either: a symlink in the library, or a database carried over
        from a machine whose SOMNIA_LIBRARY_DIR was somewhere else, can both
        point outside. That case is logged rather than silently dropped — a
        library that has moved should be explicable from the journal, not
        guessed at.
        """
        path = Path(audio_file).resolve()
        # expanduser as well as resolve: Config's default library_dir is the
        # literal "~/library/audiobooks", and only load_config expands it.
        library = self._cfg.library_dir.expanduser().resolve()
        if not path.is_relative_to(library):
            logger.warning("%s lies outside %s: %s", what, library, path)
            return None
        # A chapter that has been deleted, or has not finished rendering, is an
        # absence rather than a traceback.
        return path if path.is_file() else None
