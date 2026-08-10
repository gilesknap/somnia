"""The tool layer: everything the agent can do, as a plain Python library.

Deliberately free of any Anthropic dependency — :mod:`somnia.agent` wraps these
for the tool runner, and the PWA will call them directly. Each function returns
structured data; turning that into prose is the caller's job.

The spoiler guard lives here rather than in the agent's prompt: a question about
a book is answered from the part the listener could have heard, because finding
out how it ends is the one thing a bedtime reader must never do by accident.
That is truer since the agent was allowed to answer out of what it already
knows about a book (ADR 6) rather than only out of passages a tool returned:
the retrieval is no longer the whole of the bound, so the number this layer
computes is handed to the model in words as well as being used to cut the
search.
"""

import sqlite3
from dataclasses import dataclass

from .catalog import CatalogSearch, search_catalog
from .config import Config
from .embed import Embedder
from .format import format_timestamp, shorten
from .index import Passage, find_passage
from .queue import QueueRow, submit, view

__all__ = [
    "Book",
    "Candidate",
    "Library",
    "Moved",
    "Offer",
    "Position",
    "Recall",
    "Refused",
]

# How many places may go on one screen. Four is what somebody half awake can
# compare without scrolling back up and starting again, and a list they have to
# re-read is worse than the conversation it replaced. The model ranks; if it
# names more than this, the ones it thought least likely are the ones dropped.
CANDIDATE_MAX = 4

# How much of a passage goes on a row. Enough to recognise a moment by, not
# enough to read a page of the book off a list of places you might go — and the
# rows have to stay short enough that four of them plus "you are here" fit on a
# phone held above a face in the dark.
CANDIDATE_TEXT_CHARS = 240


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
    """Places to be taken to, and the line that decides what may be said of them.

    Every hit, from anywhere in the book. There is no bound on the search since
    ADR 11 and nothing held back from this list, because a place is not a
    spoiler — a time on the clock says nothing about what happens at it.

    ``here_ms`` is where the book is, carried beside the hits rather than looked
    up again by whoever formats them, so the whole of one search is judged
    against one number. :meth:`ahead` is the judgement, and it is the same
    predicate :class:`Candidate` uses, out of the same function: a hit it is
    true of reaches the model as an id and a time with no words attached.
    """

    hits: list[Passage]
    here_ms: int

    def ahead(self, passage: Passage) -> bool:
        """Is this one they have not reached yet, and so may not be told?"""
        return ahead_of(passage.start_ms, self.here_ms)


@dataclass
class Recall:
    """Passages to answer a question from, and how far the answer may go.

    Deliberately not a :class:`Search`, and the two have grown further apart
    rather than closer. A search is looking for somewhere to be taken, so it
    reads the whole book and holds back the words of anywhere they have not
    reached; this is looking for something to say, so it never reads past the
    line at all. Nothing downstream is given a chunk id or a ``position_ms``
    either, because the answer to a question is a sentence and not a place.

    ``searched_to_ms`` is how far the passages were allowed to come from, or
    None on a book they have finished, where there is nothing left to hold back.
    It is not only a fact about the retrieval. It is the line the answer itself
    may not cross, which is a wider job than it used to be: since ADR 6 what the
    agent says is no longer confined to passages a tool handed it, so this
    number is the whole of what stands between its own knowledge of the book and
    the part of it nobody has heard.
    """

    passages: list[Passage]
    searched_to_ms: int | None


def ahead_of(start_ms: int, here_ms: int) -> bool:
    """Does a passage beginning here lie in front of the listener?

    One expression, in one place, because two ends of somnia read it and a
    boundary they disagreed about would be a boundary the guard has a hole at.
    :class:`Candidate` uses it to decide whether a row keeps its chapter title;
    :meth:`Search.ahead` uses it to decide whether the model is handed a
    passage's words at all.

    ``>=`` and not ``>``. A passage that begins exactly where the book has got
    to is the sentence they have not heard yet — and on a book nobody has
    started, where the line is zero, ``>`` would call the opening words already
    heard and print them in the clear.
    """
    return start_ms >= here_ms


@dataclass
class Candidate:
    """One place on the list of places they might have meant.

    ``text`` is the book's own words, taken from the chunk that matched, never
    a description of them: a sentence the model wrote about a passage is a
    sentence about a passage it may be wrong about, and the whole point of
    showing the list is that they recognise the moment themselves.

    ``ahead`` says the passage begins at or after the point the book has reached,
    and it is decided here, once, by the same code that owns the spoiler guard.
    The page obeys it and computes nothing: its own copy of the position goes
    stale over a night, so letting it judge would mean two numbers that can
    disagree about exactly the rows a mistake matters most on. When it is true
    the page keeps ``chapter_title`` off the screen — a Gutenberg chapter
    heading is as much of a spoiler as the sentence under it — while the words
    are behind a press on every row either way.
    """

    chunk_id: int
    start_ms: int
    chapter_idx: int
    chapter_title: str
    ahead: bool
    text: str


@dataclass
class Offer:
    """A list of places to choose between, and where they are now.

    This is the whole of what the page needs to draw the choice, because the
    alternative was a conversation — "did you mean the one an hour in or the one
    at four hours?" — read in the dark by someone half asleep. Nothing has moved
    when one of these is made: it is a question, and it is answered by a thumb.

    ``position_ms`` is None when they have never started the book, preserving
    the distinction :meth:`Library.get_position` keeps: nobody is at 0:00:00,
    and the page draws no "you are here" row at all rather than inventing one.
    """

    gid: int
    title: str
    position_ms: int | None
    places: list[Candidate]


@dataclass
class Refused:
    """Why an offer was not made, in words the model can act on.

    Handed back to it verbatim as the tool result, so it reads as an instruction
    rather than an error: told "search first" it searches, told "move them there
    instead" it moves them. Nothing reaches the page, which is the point — a
    refusal that still drew a screen would be a wrong screen.
    """

    reason: str


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
        embedder: Embedder | None = None,
    ) -> None:
        self._cfg = cfg
        self._conn = conn
        self._embedder = embedder

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder(self._cfg.embed_model)
        return self._embedder

    # ------------------------------------------------------------------ books

    def search_catalog(self, query: str, language: str = "en") -> CatalogSearch:
        """Search Project Gutenberg's catalog for a book to add.

        The whole result rather than the rows, because a search that had to
        correct or drop a word has answered a slightly different question and
        the agent is the one thing here that can say so out loud.
        """
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
        """Ask for a Gutenberg book to be rendered, and say where in the line it is.

        This starts nothing. It used to spawn ``somnia add`` detached, with all
        three of its stdio at /dev/null, and return a sentence promising
        chapter one in a few minutes — a promise it had no way of keeping,
        since a second question a minute later gave a second Kokoro process on
        two cores and both of them then rendered slower than somebody listens.
        Now it writes one row into the queue that the worker drains one book at
        a time, and the sentence can be honest about waiting.

        The refusals moved with it. A book somnia has all of is still refused,
        and so is one that is already coming; a render that died, was stopped
        or was killed by a deploy is not, which is the retry that was
        impossible before. :func:`somnia.queue.submit` has the argument.
        """
        return submit(self._conn, gid).said

    def queue(self) -> list[QueueRow]:
        """What is being rendered, what is waiting, and what died overnight.

        Here so that the voice and the page cannot disagree about what happened
        when somebody asked for a book: they read the same rows, through the
        same function. The agent uses the live ones to say "it is third in the
        line", which is the only true answer to "did that book get added?"
        between the asking and the first chapter.
        """
        return view(self._conn)

    # -------------------------------------------------------------- listening

    def get_position(self, gid: int) -> Position | None:
        """Where the listener left off, and the text at that point.

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

    def position_ms(self, gid: int) -> int:
        """Where the book is, as one number, with never-started counted as zero.

        The spoiler guard's whole input since ADR 10, and deliberately cheaper
        than :meth:`get_position` — the guard wants the line and not the chapter
        title or the words at it, and it is read on every search.

        A book nobody has started reads 0, which bounds everything at the
        beginning rather than leaving it unbounded. That distinction is kept
        where it means something, in ``get_position``, and collapsed here where
        it does not: "never started" and "at the very beginning" have exactly
        the same answer to the question this asks.
        """
        row = self._conn.execute(
            "SELECT position_ms FROM books WHERE gid = ?", (gid,)
        ).fetchone()
        return int(row["position_ms"] or 0) if row else 0

    def find_passage(self, gid: int, query: str, k: int = 5) -> Search:
        """Search the whole book for a passage — an event, a character, a moment.

        The whole book, with no spoiler bound at all, which is the change
        ADR 11 made and the thing to understand about this method. A search for
        somewhere to be taken is not a thing that can spoil anybody: what comes
        back is a list of times, and the guard is applied to what may be *said*
        and *shown* about each of them rather than to whether it may be found.

        That is what removed ``spoiler_free``, ``allow_spoilers`` and
        ``better_ahead`` together. A bounded search had to report separately
        that a closer match lay past the bound — otherwise a search that
        excluded the answer was indistinguishable from a book that never
        contained it — and that report cost a second embedding of the query and
        a second scan of the vectors, on the screen where seconds are felt. One
        unbounded search says the same thing by containing it.

        The guard did not go anywhere; it moved one step later and got stricter.
        Each hit past :meth:`position_ms` reaches the model as an id and a time
        and nothing else — see :func:`somnia.agent.build_tools` — and reaches
        the page as a row whose words are behind a press. The words of a passage
        nobody has heard are never in the model's context at any point, which is
        a stronger guarantee than the prompt could give and the reason this is
        safe on a small model.
        """
        return Search(
            hits=find_passage(self._conn, self.embedder, gid, query, k=k),
            here_ms=self.position_ms(gid),
        )

    def recall(self, gid: int, question: str, k: int = 5) -> Recall:
        """Read the book back, to answer a question about it in words.

        The same index underneath — a question and a request to be moved
        genuinely do look for the same passages — but this one stops at the
        line, and :meth:`find_passage` no longer does at all. That is the whole
        difference between them now, and it is the right way round.

        A search reads past the line because a place is not a spoiler: it comes
        back as a time to be offered, with its words held back until a thumb
        asks for them. An answer has no such shape. It is prose, said out loud,
        with nobody's finger on it — so there is nothing here to hold back
        *with*, and the only safe bound is on what is read in the first place.

        Nothing is offered off the back of one either. The answer to a question
        about somebody who has not appeared yet is that they have not appeared
        yet, and it must not be followed by a list of places, because the reason
        they asked is that they wanted to carry on listening. Saying where they
        would have to go is itself a spoiler: "he hasn't come up yet in what
        you've heard" and "he comes up an hour and a half from here" are
        different sentences, and the second tells them the character arrives.

        There is no ``allow_spoilers`` here and there will not be one. Somebody
        who wants to know what happens later can ask to be taken there, which is
        a deliberate act with a screen in front of it; a yes given at 2am by
        somebody half asleep is the least deliberate consent in the system, and
        this tool declines to collect one.
        """
        before_ms: int | None = None
        position = self.get_position(gid)
        if position is None or not position.finished:
            # Include the sentence being spoken, not just what precedes it.
            before_ms = self.position_ms(gid) + 60_000
        return Recall(
            passages=find_passage(
                self._conn, self.embedder, gid, question, k=k, before_ms=before_ms
            ),
            searched_to_ms=before_ms,
        )

    def offer_positions(
        self, gid: int, chunk_ids: list[int], may_move: bool = True
    ) -> Offer | Moved | Refused:
        """Put the places somewhere they can be answered — a screen, or the book.

        The one way a goto ends, since ADR 12. The model names the passages it
        judges plausible and this decides what becomes of them, because the
        decision is arithmetic and the model was bad at it: more than one place,
        or one place they have not reached, is a list; one place behind them is
        a move, made here, and the :class:`Moved` says so.

        That last case used to be a :class:`Refused` reading "move them there
        instead", which is the same rule expressed as a bounce — the model had
        to read it, agree, and call another tool, and on a small model it would
        sometimes argue with it instead. Doing the move is the same night with
        one fewer round trip in it and one fewer judgement asked of the model.

        An offer proper is reads and nothing else. It asks a question, so it
        must leave the night exactly as it found it: no position and no count.
        That matters more since the position became the guard's only input
        (ADR 10) — writing one would not merely record a place nobody went, it
        would move the line that decides what may be said, on the strength of a
        screen nobody has answered yet.

        The ids are chunk ids, as :class:`somnia.index.Passage` carries them,
        and an id that resolves to nothing is dropped rather than rounded to the
        nearest chunk: a near miss would put words on the screen that are not
        the passage that matched, which is the one lie this list cannot tell. An
        id belonging to another book refuses the whole call, because a list is
        one book's timeline and half of another book's is not a timeline.

        ``may_move`` is False on the second call of a turn that has already
        drawn a list, and it takes the move away rather than the call: the one
        place behind them comes back as a list of one, which is a move with a
        press in front of it and is the whole of what is left to safely do. A
        second list is a change of mind and stays allowed — nothing has left
        here yet, and the last offer wins — but a write under a live list
        reaches the page fifteen seconds later as the refusal of its next
        report, and drags a listener who is still reading it. Only the caller
        knows a list is up, and only this method knows a move is what the
        arithmetic came to, so the two facts have to meet somewhere: they meet
        here, on the argument, and not on a count of ids at the caller, which
        is not the same question. ``chunk_ids`` is deduplicated below and ids
        resolving to no row are dropped, so ``[7, 7]`` and ``[7, gone]`` are
        both one place and neither is one id.
        """
        book = self.book(gid)
        if book is None:
            return Refused(f"There is no book {gid} here.")

        # The model's own order, kept: it ranked them, and if it named more than
        # will fit, the ones it thought least likely are the ones that go.
        wanted: list[int] = []
        for chunk_id in chunk_ids:
            if chunk_id not in wanted:
                wanted.append(chunk_id)

        rows: list[sqlite3.Row] = []
        for chunk_id in wanted:
            row = self._conn.execute(
                "SELECT id, book_gid, chapter_idx, start_ms, text FROM chunks"
                " WHERE id = ?",
                (chunk_id,),
            ).fetchone()
            if row is None:
                continue
            if int(row["book_gid"]) != gid:
                return Refused(f"Passage {chunk_id} is not in book {gid}.")
            rows.append(row)
        if not rows:
            return Refused("None of those are passages from a search. Search first.")

        # Read once for the whole offer. Asking per row would let two rows be
        # judged against different lines if a report landed in between, and the
        # row that changed its mind would be the one furthest on.
        here = self.position_ms(gid)
        places = [
            Candidate(
                chunk_id=int(row["id"]),
                start_ms=int(row["start_ms"]),
                chapter_idx=int(row["chapter_idx"]),
                chapter_title=self._chapter_title(gid, int(row["chapter_idx"])),
                # The same call the search made about the same passage when it
                # decided whether to show the model its words. Two ends of one
                # rule, and they must agree: a row drawn as heard whose text the
                # model was never given reads as a bug, and a row drawn as ahead
                # whose text the model was given is the guard with a hole in it.
                ahead=ahead_of(int(row["start_ms"]), here),
                text=shorten(str(row["text"]), CANDIDATE_TEXT_CHARS),
            )
            for row in rows[:CANDIDATE_MAX]
        ]
        # Sorted for the screen after the ranking has been spent on the cut: the
        # list is a timeline, and a timeline out of order cannot be read at a
        # glance, which is the only way it will be read.
        places.sort(key=lambda place: place.start_ms)
        # One place, behind them, and no question left in it: they asked to be
        # taken somewhere and there is exactly one somewhere it could be. A list
        # of one is a move with a press in front of it, and making somebody
        # half asleep press it buys nothing.
        #
        # One place *ahead* of them is the opposite, and is the whole reason the
        # screen exists: there the press is what replaced "shall I take you
        # there anyway?", and it is answered by a thumb rather than by a
        # sentence composed in the dark.
        #
        # And where a list is already on the screen the press comes back to this
        # row too, for the length of that turn: buying somebody a press is worth
        # less than not moving the book under what they are reading.
        if may_move and len(places) == 1 and not places[0].ahead:
            return self.move_to(gid, places[0].start_ms)
        position = self.get_position(gid)
        return Offer(
            gid=gid,
            title=book.title,
            position_ms=position.position_ms if position is not None else None,
            places=places,
        )

    def _chapter_title(self, gid: int, chapter_idx: int) -> str:
        """What a chapter is called, or "" where there is no such row.

        An absence, not an error. A book whose chapters were never given names
        still has places worth offering, and the row simply reads "Ch 7".
        """
        row = self._conn.execute(
            "SELECT title FROM chapters WHERE book_gid = ? AND idx = ?",
            (gid, chapter_idx),
        ).fetchone()
        return str(row["title"]) if row is not None else ""

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
        the book now, so there is nobody left to argue with.
        """
        seq = self._write_position(gid, position_ms)
        if seq is None:
            # The model named a book that is not here. Saying so is worth more
            # at 2am than a traceback, and there is no move for the page to
            # follow — which a seq of zero is exactly how to say.
            return Moved(gid, position_ms, 0, f"There is no book {gid} here.")
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

        It moves the spoiler guard with it, which is what a move now means: the
        position is the line, so being taken back to chapter two makes chapters
        three to twenty unsayable again until they are played back over. That is
        the cost ADR 10 took on knowingly, against a mark that stopped rising at
        the first press of the skip button and stayed stopped.

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
