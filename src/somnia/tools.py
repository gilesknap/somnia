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

from .abs import AbsClient, tell_abs
from .catalog import CatalogEntry, search_catalog
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
    """Search results, plus what the spoiler guard held back.

    ``better_ahead`` is the crux: without it, a spoiler-bounded search that
    excludes the answer is indistinguishable from a book that never contained
    it, and the only honest thing left to say is "not found". Knowing that a
    closer match lies ahead lets the answer be the true one instead: there is
    somewhere further on than you have got, and here is the time of it.

    That used to be asked as a question — "shall I take you there anyway?" —
    and is now a row on a list, offered by :meth:`Library.offer_positions`,
    with its words covered up until they ask to see them. The only thing that
    changed here is what is done with it; it is still one passage, still chosen
    only when it beats everything in range.
    """

    hits: list[Passage]
    searched_to_ms: int | None
    better_ahead: Passage | None


@dataclass
class Recall:
    """Passages to answer a question from, and how far the answer may go.

    Deliberately not a :class:`Search`, though it is built out of one. A search
    is looking for somewhere to be taken; this is looking for something to say,
    and the two want different things back. There is no ``better_ahead`` here at
    all — see :meth:`Library.recall` for why dropping it is the point rather
    than an omission — and nothing downstream is given a chunk id or a
    ``position_ms``, because the answer to a question is a sentence and not a
    place.

    ``searched_to_ms`` is the same number :class:`Search` carries and means the
    same thing: how far the passages were allowed to come from, or None on a
    book they have finished, where there is nothing left to hold back. It is not
    only a fact about the retrieval. It is the line the answer itself may not
    cross, which is a wider job than it used to be: since ADR 6 what the agent
    says is no longer confined to passages a tool handed it, so this number is
    the whole of what stands between its own knowledge of the book and the part
    of it nobody has heard.
    """

    passages: list[Passage]
    searched_to_ms: int | None


@dataclass
class Candidate:
    """One place on the list of places they might have meant.

    ``text`` is the book's own words, taken from the chunk that matched, never
    a description of them: a sentence the model wrote about a passage is a
    sentence about a passage it may be wrong about, and the whole point of
    showing the list is that they recognise the moment themselves.

    ``ahead`` says the passage begins at or after the furthest point they have
    ever reached, and it is decided here, once, by the same code that owns the
    spoiler guard. The page obeys it and computes nothing: it has never read
    ``heard_to_ms`` and the copy it holds goes stale over a night, so letting it
    judge would mean two numbers that can disagree about exactly the rows a
    mistake matters most on. When it is true the page keeps both these words and
    ``chapter_title`` off the screen until they ask for them — a Gutenberg
    chapter heading is as much of a spoiler as the sentence under it.
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
        self,
        gid: int,
        query: str,
        k: int = 5,
        spoiler_free: bool = True,
        ahead: bool = True,
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
        # `ahead` is what stops this being paid for by callers that throw it
        # away. Working it out means a second search of the whole book — another
        # embedding of the query and another vector scan — and `recall` drops
        # the answer on the way out, deliberately and at length: see its
        # docstring for why a question must not be followed by a nudge towards
        # somewhere further on. So it was buying a spoiler it then refused to
        # tell anybody, twice a night, on the screen where seconds are felt.
        if before_ms is not None and ahead:
            whole_book = find_passage(self._conn, self.embedder, gid, query, k=k)
            ahead = [p for p in whole_book if p.start_ms > before_ms]
            floor = hits[0].distance if hits else float("inf")
            if ahead and ahead[0].distance < floor:
                better_ahead = ahead[0]
        return Search(hits=hits, searched_to_ms=before_ms, better_ahead=better_ahead)

    def recall(self, gid: int, question: str, k: int = 5) -> Recall:
        """Read the book back, to answer a question about it in words.

        The same search underneath — there is only one index, and a question and
        a request to be moved genuinely do look for the same passages — but what
        comes back is framed for saying rather than for going, and two things
        are taken away on the way out.

        ``better_ahead`` is dropped, and dropping it is the reason this method
        exists rather than the agent simply ignoring the field. It is a nudge
        towards offering a place further on, which is exactly right for "take me
        there" and exactly wrong for "who is he": the answer to a question about
        somebody who has not appeared yet is that they have not appeared yet,
        and it must not be followed by a list of places, because the reason they
        asked is that they wanted to carry on listening. It is also a spoiler in
        its own right. "He hasn't come up yet in what you've heard" and "he
        comes up an hour and a half from here" are different sentences, and the
        second one tells them the character arrives — which is a thing about the
        book they have not heard yet, and therefore not ours to say.

        There is no ``allow_spoilers`` either, and there will not be one. A move
        past the mark cannot be done spoiler-free — going there is hearing it —
        so consent is the only way to serve "take me to the end", and the tool
        takes it. An answer has no such necessity: whatever they are asking
        about, listening on tells them, and a yes given at 2am by somebody half
        asleep is the least deliberate consent in the whole system. So this one
        never widens, and a question about what has not happened yet is answered
        with the truth that it has not happened yet.
        """
        search = self.find_passage(gid, question, k=k, spoiler_free=True, ahead=False)
        return Recall(passages=search.hits, searched_to_ms=search.searched_to_ms)

    def offer_positions(self, gid: int, chunk_ids: list[int]) -> Offer | Refused:
        """Build the list of places to put on screen, from passages that matched.

        Reads and nothing else. An offer asks a question, so it must leave the
        night exactly as it found it: no position, no count, and above all no
        ``heard_to_ms``, which rises only from audio that really played. Showing
        somebody a list of places they have not been is not having been there.

        The ids are chunk ids, as :class:`somnia.index.Passage` carries them,
        and an id that resolves to nothing is dropped rather than rounded to the
        nearest chunk: a near miss would put words on the screen that are not
        the passage that matched, which is the one lie this list cannot tell. An
        id belonging to another book refuses the whole call, because a list is
        one book's timeline and half of another book's is not a timeline.

        A list of exactly one place they have already heard is refused too. That
        is not a question — it is a move with a press in front of it, and making
        them press it at 2am buys nothing. One place they have *not* heard is
        accepted, because there the press is the whole point: it is what replaced
        "shall I take you there anyway?".
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
        # judged against different marks if a report landed in between, and the
        # row that changed its mind would be the one furthest on.
        heard = self.heard_to_ms(gid)
        places = [
            Candidate(
                chunk_id=int(row["id"]),
                start_ms=int(row["start_ms"]),
                chapter_idx=int(row["chapter_idx"]),
                chapter_title=self._chapter_title(gid, int(row["chapter_idx"])),
                # Not `>`. A chunk that begins exactly at the mark is the
                # sentence they have not heard yet, and on a book nobody has
                # played a second of — heard_to_ms 0, which is every book until
                # it is played — `>` would print the opening words in the clear.
                # No slack either: the search bound is the mark plus a minute
                # (see find_passage), so a passage inside that minute is in
                # range to be found and still covered up here. That is the safe
                # direction, and it costs one press.
                ahead=int(row["start_ms"]) >= heard,
                text=shorten(str(row["text"]), CANDIDATE_TEXT_CHARS),
            )
            for row in rows[:CANDIDATE_MAX]
        ]
        # Sorted for the screen after the ranking has been spent on the cut: the
        # list is a timeline, and a timeline out of order cannot be read at a
        # glance, which is the only way it will be read.
        places.sort(key=lambda place: place.start_ms)
        if len(places) == 1 and not places[0].ahead:
            return Refused(
                "That is one place they have already heard. Move them there instead."
            )
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
        the book now, so there is nobody left to argue with. ABS is told
        afterwards, out of courtesy, and can fail without anyone noticing.
        """
        seq = self._write_position(gid, position_ms)
        if seq is None:
            # The model named a book that is not here. Saying so is worth more
            # at 2am than a traceback, and there is no move for the page to
            # follow — which a seq of zero is exactly how to say.
            return Moved(gid, position_ms, 0, f"There is no book {gid} here.")
        tell_abs(self._abs, self._abs_item_id(gid), position_ms)
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
