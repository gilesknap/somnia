"""The 2am surface: a tiny web server behind the PWA chat page.

The agent loop runs here rather than in the browser, so the Anthropic key never
leaves the VPS and the phone needs no login. There is no auth of any kind: the
server binds to localhost and is published on the tailnet by ``tailscale
serve``, which is the whole security model — see the network section of
docs/explanations/design.md.

Conversations live in memory, keyed by a token the page mints on load. That is
enough for one listener with one phone, and it means a night's chat leaves
nothing behind on disk.

The audio somnia rendered is served from here too, because the page is the
player now. That work is deliberately kept away from the agent: it goes through
:class:`somnia.player.Player`, which has its own connection, so a seek is never
stuck behind a model turn.

Nothing here renders a book. Submitting one writes a row into the queue and
that is all: the renderer lives in its own systemd unit, so restarting this one
— which is what a deploy is — costs a render nothing, and Kokoro and torch
never enter the process that answers the page. See ADR 5.
"""

import asyncio
import logging
import sqlite3
import threading
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .agent import Conversation, Turn, effort_for, open_library
from .catalog import search_catalog
from .config import Config
from .db import connect
from .format import shorten
from .library import Removed, remove_book
from .player import Player
from .queue import LIVE, QueueRow, Stopped, Submission, stop, submit, view
from .stream import build_stream, stream_path
from .tools import CANDIDATE_TEXT_CHARS, Library
from .voices import VOICES, known

__all__ = ["Conversations", "Found", "Queue", "create_app", "serve"]

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"


class Shell(StaticFiles):
    """The page, served so that a deploy is on the phone at the next launch.

    Starlette sends the shell with an ETag and a Last-Modified and no
    ``Cache-Control`` at all, and a response with no cache policy is not a
    response nobody caches — it is one the browser makes a policy up for.
    Chrome's heuristic is a tenth of the age of the file, so an ``app.js`` that
    had been sitting there a day was considered good for another two hours, and
    the page never so much as asked. What that looks like from the sofa is a
    deploy that did not happen: the units restarted, the bytes on disk are new,
    every request in the log is answered, and the phone goes on running last
    week's page. It cost an hour to find, twice, and the second time it looked
    exactly like the bug that had just been fixed.

    ``no-cache`` does not mean "do not store it". It means "ask before you use
    it", which is what the ETag was already there for: unchanged, the answer is
    a 304 of a few hundred bytes; changed, the new file arrives on the next
    launch. This is a shell of a few kilobytes on a tailnet, and the round trip
    it costs is not the slow part of anything — the service worker's own comment
    makes the same argument about the same files.

    It is also what makes that service worker's network-first policy mean
    anything. The worker asks the network first on purpose, but its ``fetch()``
    goes through the same HTTP cache as everybody else's, so a heuristically
    fresh copy was answered from inside the browser with no network trip at all
    and no way for the worker to know.

    ``/api/`` is not covered by this and must not be: the audio is served
    ranged, from another route, and the one thing here that really is immutable
    is the one file this class never sees.
    """

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-cache"
        return response


# One listener, one phone — but a reloaded page mints a fresh token, so a few
# nights of tabs can accumulate. Old ones are dropped, not remembered.
MAX_CONVERSATIONS = 8

# Every reason the page has for telling us where it is. Nothing branches on
# which one it is any more, so this is a vocabulary rather than a decision: it
# is here so a word nobody wrote can be noticed on the way in.
REASONS = frozenset(
    {
        "pause",
        "hidden",
        "unload",
        "ended",
        "switch",
        "load",
        "play",
        "tick",
        "seek",
        "chapter",
    }
)

# How many books a catalog search offers. Eight is what fits on a phone above a
# raised keyboard, and a list that has to be scrolled to be read is a second
# screen wearing a hat. Somebody who cannot see the book they meant should type
# more of its name, which costs one round trip on a tailnet and no scrolling in
# the dark.
CATALOG_LIMIT = 8


class Conversations:
    """Live conversations, keyed by the page that owns them.

    Every turn runs under one lock. The listener is asleep, not load testing,
    and serialising means the shared sqlite connection and the embedder are
    only ever touched by one thread at a time.
    """

    def __init__(self, cfg: Config, library: Library) -> None:
        self._cfg = cfg
        self._library = library
        self._lock = threading.Lock()
        self._by_token: OrderedDict[str, Conversation] = OrderedDict()
        # One client for every conversation there will ever be, built once at
        # startup. Each conversation used to make its own, and a client is a
        # connection pool: the first question asked under a new token paid for
        # a TLS handshake to Anthropic before it could pay for anything else.
        # Starting over — which is one press, on the screen being typed into —
        # made a new token, so the cost landed exactly where somebody had just
        # said they were in a hurry.
        self._client = Anthropic(api_key=cfg.anthropic_api_key or None)

    def warm(self) -> None:
        """Get the slow lookups out of the way before anybody waits on them.

        Two of them. The small one first: whether this model takes an effort
        level is a question for the API, and asking it inside the first turn
        would put a round trip in front of the first answer of the night.

        The large one is the embedder. It is torch and a sentence-transformer,
        and it takes twelve seconds on
        nuc2. Loaded lazily, that wait lands on the first question of the night
        that searches anything — every time the unit restarts, which is every
        deploy — and it lands *inside* the turn, so what it looks like is the
        agent thinking for twenty seconds about "who is Ginger".

        Called off the event loop at startup, so the page is served and the
        book plays throughout: the only thing that waits on this is the first
        search, which is the thing it exists to stop waiting.

        Under the same lock every turn takes, because ``Library.embedder``
        builds on first read and two threads reading it at once would build it
        twice. A question that arrives mid-warm therefore waits for the load —
        which is exactly what it did before this existed, and the last time it
        will have to.
        """
        effort_for(self._client, self._cfg)
        with self._lock:
            _ = self._library.embedder

    def ask(self, token: str, question: str, gid: int | None = None) -> Turn:
        with self._lock:
            conversation = self._by_token.pop(token, None)
            if conversation is None:
                conversation = Conversation(self._cfg, self._library, self._client)
            self._by_token[token] = conversation
            while len(self._by_token) > MAX_CONVERSATIONS:
                self._by_token.popitem(last=False)
            # Passed per turn rather than held on the conversation: the page can
            # open another book between two questions, and a conversation that
            # remembered the first one would answer the second about the wrong
            # book without either end noticing.
            return conversation.ask(question, gid)

    def forget(self, token: str) -> None:
        """Start again — they have changed the subject, or the agent is lost."""
        with self._lock:
            self._by_token.pop(token, None)


@dataclass
class Found:
    """A book the local catalog knows about, as something to press.

    ``have`` is what somnia already thinks of this gid — 'done', 'rendering' or
    'pending' from ``books``, 'queued' or 'rendering' from a live queue row — and
    None when it has never heard of it. It travels with the row so a book that
    is already coming is *marked* rather than offered and then refused: a press
    that was never available cannot be a press that did nothing, and at 2am
    those two feel completely different.

    ``source`` is which library it came from — 'gutenberg' or 'australia'. It
    travels for the same reason ``have`` does: it changes what the row means
    before anybody presses it. The two libraries clear their books against
    different countries' law, and only one of those countries is the one the
    listener is sitting in.
    """

    gid: int
    title: str
    authors: str
    have: str | None
    source: str


class Queue:
    """The third lane: what is being rendered, and asking for one more book.

    Its own connection and its own lock, in the shape of :class:`Player`, and
    for the same reason twice over. Not the player's, because the whole point of
    the fast lane is that a seek waits on nothing at all. Not the agent's, which
    is held under the conversation lock for the entire length of a model turn —
    a submit button that sits there for twenty seconds because somebody happened
    to ask a question is exactly the dead control the design already refuses.

    So there are three connections into one sqlite file now, which is worth
    saying out loud: the agent's, the player's, and this. sqlite in WAL mode with
    a busy timeout is built for that, and every statement here is a handful of
    milliseconds against local disk.

    Nothing here renders anything. Submitting is one INSERT, stopping is one
    UPDATE, and the process that actually spends hours on Kokoro is another unit
    entirely — which is why a deploy's restart of this one costs a render
    nothing. The catalog search lives here too, rather than on the agent's
    library, because it is the same panel asking and it must not queue behind a
    turn either.
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = connect(cfg.db_path, cross_thread=True)

    def close(self) -> None:
        """Give the connection back, so shutdown is not a ResourceWarning."""
        with self._lock:
            self._conn.close()

    def view(self) -> list[QueueRow]:
        with self._lock:
            return view(self._conn)

    def submit(self, gid: int, voice: str = "") -> Submission:
        with self._lock:
            return submit(self._conn, gid, voice)

    def stop(self, job_id: int) -> Stopped:
        with self._lock:
            return stop(self._conn, job_id)

    def remove(self, gid: int) -> Removed:
        """Take a book out of the library altogether — rows, audio and streams.

        On this connection rather than the player's, because the first thing a
        delete does is ask the queue whether anything is rendering the book,
        and that is this lane's question. Under this lock for the same reason
        `stop` is: two presses on the same book a millisecond apart must not
        both walk the same folder.

        The player will not notice, and does not have to. It holds no rows in
        Python — every manifest is a fresh SELECT — so the next request simply
        finds the book gone, which is what it now is.
        """
        with self._lock:
            return remove_book(self._cfg, self._conn, gid)

    def search(self, query: str, language: str) -> list[Found]:
        """The local catalog, offline, with what somnia already has marked."""
        with self._lock:
            entries = search_catalog(self._conn, query, language, CATALOG_LIMIT)
            have = self._have([entry.gid for entry in entries])
        return [
            Found(
                gid=entry.gid,
                title=entry.title,
                authors=entry.authors,
                have=have.get(entry.gid),
                source=entry.source,
            )
            for entry in entries
        ]

    def _have(self, gids: list[int]) -> dict[int, str]:
        """What somnia already knows about these books, in one statement.

        Two places have to be asked and neither is sufficient. A book that is
        only in the line has no ``books`` row at all until its parse finishes
        minutes later, and a book that was rendered before the queue existed has
        no queue row and never will. So both are read, the queue first, and the
        first answer for a gid wins: a book on 'pending' with a fresh queue row
        is a retry that is already coming, and "queued" is the useful half of
        that. The ``rank`` column is what makes "first" mean the queue rather
        than whatever order the compound select happened to produce.

        The placeholders are built from the gids' own count, and the only thing
        interpolated is that many question marks — the values are always bound.
        """
        if not gids:
            return {}
        marks = ",".join("?" * len(gids))
        rows = self._conn.execute(
            "SELECT gid, have FROM ("
            f" SELECT gid, state AS have, 0 AS rank FROM queue WHERE state IN {LIVE}"
            " UNION ALL"
            " SELECT gid, status AS have, 1 AS rank FROM books"
            f") WHERE gid IN ({marks}) ORDER BY rank",
            tuple(gids),
        ).fetchall()
        out: dict[int, str] = {}
        for row in rows:
            out.setdefault(int(row["gid"]), str(row["have"]))
        return out


def create_app(cfg: Config, conn: sqlite3.Connection) -> Starlette:
    """The PWA, the agent behind it, and the book it plays."""
    conversations = Conversations(cfg, open_library(cfg, conn))
    player = Player(cfg)
    renders = Queue(cfg)

    async def ask(request: Request) -> Response:
        payload = await _payload(request)
        token = str(payload.get("token") or "")
        question = str(payload.get("question") or "").strip()
        if not token or not question:
            return JSONResponse({"error": "token and question are required"}, 400)
        # Which book the page has open, and optional on purpose: a page that has
        # opened nothing yet still has questions worth asking, and an older
        # cached app.js that does not send it must keep working rather than 400.
        # Anything that is not a positive integer is no book at all — a gid that
        # arrived as a string or a null is a page saying it does not know, and
        # guessing one would answer about a book nobody is listening to.
        raw = payload.get("gid")
        # `not isinstance(raw, bool)` is not paranoia: in Python `True` is an
        # int, so a page that sent `"gid": true` would otherwise open book 1.
        a_book = isinstance(raw, int) and not isinstance(raw, bool) and raw > 0
        gid = raw if a_book else None
        try:
            # A turn blocks for seconds on the model and on sqlite, so it runs
            # off the event loop.
            turn = await run_in_threadpool(conversations.ask, token, question, gid)
        except Exception:
            logger.exception("agent turn failed")
            return JSONResponse({"error": "Something went wrong down here."}, 500)
        body: dict[str, Any] = {"reply": turn.reply}
        if turn.candidates is not None:
            # The list of places they might have meant, drawn as an overlay over
            # the one screen. Read by presence, like "move", and shipped whole
            # from the dataclasses in tools.py so there is exactly one
            # definition of this shape — the words on each row are the book's
            # own, and whether a row starts covered up was decided there, beside
            # the spoiler guard, and is not recomputed here or on the page.
            #
            # If a night ever shows the model narrating the places beside the
            # list, the hardening is one line: replace turn.reply with
            # agent.OFFER_SENTENCE whenever this key is set. It is not done
            # today because the model sometimes has something true to add, and
            # the worst it can say is a sentence about a passage they have
            # already heard.
            body["candidates"] = asdict(turn.candidates)
        elif turn.move is not None:
            # Present only when the book actually moved: the page reads the key
            # rather than its contents. The count travels with the position
            # because adopting one without the other would have the page's next
            # report refused, and the refusal would drag it back here after it
            # had already played on.
            #
            # This is a head start, not the mechanism. If this reply never
            # arrives the same move lands within fifteen seconds as the refusal
            # of the page's next report, and both routes end in one function.
            #
            # An `elif` and not an `if`: a list and a seek in one reply would
            # move the book under somebody still choosing where to send it. The
            # tools already refuse the second of an offer and a move, so this is
            # the belt to that braces — two independent things would have to
            # fail before the page could be told both.
            body["move"] = {
                "gid": turn.move.gid,
                "position_ms": turn.move.position_ms,
                "seq": turn.move.seq,
            }
        return JSONResponse(body)

    async def forget(request: Request) -> Response:
        payload = await _payload(request)
        conversations.forget(str(payload.get("token") or ""))
        return JSONResponse({"ok": True})

    async def health(request: Request) -> Response:
        return JSONResponse({"ok": True})

    async def books(request: Request) -> Response:
        return JSONResponse(asdict(await run_in_threadpool(player.books)))

    async def book(request: Request) -> Response:
        gid = int(request.path_params["gid"])
        manifest = await run_in_threadpool(player.manifest, gid)
        if manifest is None:
            return JSONResponse({"error": "no such book"}, 404)
        return JSONResponse(asdict(manifest))

    async def remove_the_book(request: Request) -> Response:
        """Take a book out of somnia: its rows, its audio, its joined streams.

        DELETE, and it means it — unlike ``/api/queue/{id}/stop``, which is a
        POST precisely because the row it names survives it. There is nothing
        left of a book after this and no undo anywhere behind it, which is why
        the page will ask twice before it gets here.

        200 with ``"ok": false`` for a refusal: a book being rendered right now
        is a real book that is staying, and the sentence says how to stop the
        render first. **404** only for a gid that is not here at all, the same
        answer, for the same reason, as the GET on this path.
        """
        gid = int(request.path_params["gid"])
        removed = await run_in_threadpool(renders.remove, gid)
        return JSONResponse(asdict(removed), 200 if removed.found else 404)

    async def open_book(request: Request) -> Response:
        """Make this the book the page opens, which is the whole of switching.

        One column, on one row: the book with the newest ``position_at`` is what
        a cold launch opens, so making a book the most recent one *is* choosing
        it. Nothing about where it is, how far it has been heard, or how many
        times the agent has moved it is touched — see
        :meth:`somnia.player.Player.open_book`.

        Keyed on the book in the path rather than on a number in a body, the
        same shape as ``/api/queue/{id}/stop``: a request that names no book at
        all is a 404 from the router, so there is no 400 to write here.

        404 for a book that is not there and for one with no audio yet, which
        are the same answer to a press — there is nothing to open — and neither
        is a state the panel ever offers a press in.
        """
        gid = int(request.path_params["gid"])
        opened = await run_in_threadpool(player.open_book, gid)
        if opened is None:
            return JSONResponse({"error": "no book to open"}, 404)
        return JSONResponse(asdict(opened))

    async def sentence(request: Request) -> Response:
        """Where the sentence being spoken at a point began.

        Asked once, when they pause — never when they press play. A resume has
        to be instant, and a phone that has been face down for an hour is the
        least likely thing on the tailnet to answer quickly, so the page fetches
        this while the connection is still warm and holds it for later.
        """
        gid = int(request.path_params["gid"])
        ms = int(request.path_params["ms"])
        start_ms = await run_in_threadpool(player.sentence_start, gid, ms)
        return JSONResponse({"gid": gid, "ms": ms, "start_ms": start_ms})

    async def passage(request: Request) -> Response:
        """What is being said at a point, for the "you are here" row.

        The only route in somnia that hands back the book's own words, and it
        can only ever hand back words that have already been played out loud —
        see :meth:`Player.passage_at`, where that bound is part of the same
        statement that finds the row. A general "give me the text of chunk N"
        would be a spoiler oracle one guessed integer wide; this is bounded by
        the same number the search has always been bounded by.

        Cut to the length a row on that screen can hold, by the same rule and to
        the same limit as the places it sits among: the words are there to
        recognise a moment by, not to read the book off a list.
        """
        gid = int(request.path_params["gid"])
        ms = int(request.path_params["ms"])
        text = await run_in_threadpool(player.passage_at, gid, ms)
        return JSONResponse(
            {
                "gid": gid,
                "ms": ms,
                "text": shorten(text, CANDIDATE_TEXT_CHARS) if text else None,
            }
        )

    async def audio(request: Request) -> Response:
        gid = int(request.path_params["gid"])
        idx = int(request.path_params["idx"])
        path = await run_in_threadpool(player.chapter_file, gid, idx)
        if path is None:
            return JSONResponse({"error": "no such chapter"}, 404)
        # Pin the media type. Python's mimetypes does not know .m4a, and the
        # runtime image has no /etc/mime.types either, so letting it guess
        # gives application/octet-stream and Safari refuses to play the book —
        # a bug that cannot reproduce on a development machine. No filename=,
        # which would make it a download rather than something to play.
        # Range, If-Range and 416 are Starlette's own, and seeking depends on
        # them, so nothing here touches the request headers.
        return FileResponse(path, media_type="audio/mp4")

    async def stream(request: Request) -> Response:
        """The whole book as one file, so a chapter boundary touches nothing.

        ``n`` is how many chapters the stream covers, which makes it a version:
        a book that grew while somebody was listening is a different number and
        a different file, and the one their phone has open is never rewritten.
        See :mod:`somnia.stream`, which is where all of that is argued.

        Built on the first ask rather than at the end of a render, because most
        versions of a growing book are never played — measured on the real
        library, a night costs one build, or none. It costs a second or two of
        ffmpeg in front of the first byte, spent while the page is already
        saying it is opening the book.

        A build that cannot honestly be made is a 404, loudly in the journal
        rather than quietly here. The manifest still carries a url per chapter,
        so a book with no stream is one that blinks at every boundary the way
        every book did before — which is a worse night, not a lost one.

        Media type, Content-Disposition and the untouched request headers are
        all for the reasons ``audio`` above gives; nothing about them is
        different for being a whole book rather than a chapter.
        """
        gid = int(request.path_params["gid"])
        n = int(request.path_params["n"])
        path = stream_path(cfg, gid, n)
        if not path.is_file():
            source = await run_in_threadpool(player.stream_source, gid, n)
            if source is None:
                return JSONResponse({"error": "no such stream"}, 404)
            built = await run_in_threadpool(
                build_stream, cfg, gid, source.files, source.span_ms
            )
            if built is None:
                return JSONResponse({"error": "the book would not join"}, 404)
            path = built
        return FileResponse(path, media_type="audio/mp4")

    async def position(request: Request) -> Response:
        """Where the page has got to — the only position write it makes.

        Answered 200 whatever happens, in one of three shapes. A refusal is not
        an error: it is how the page is told the agent moved the book while it
        was not looking, and it carries where to go instead. A 409 would put a
        red line in the console at 2am for something working exactly as
        designed, invite a throw in the fetch wrapper that skipped the one line
        that mattered, and be unreadable to the beacon sent as the page dies.
        """
        payload = await _payload(request)
        gid = _number(payload.get("gid"))
        position_ms = _number(payload.get("position_ms"))
        if gid < 0 or position_ms < 0:
            return JSONResponse({"error": "gid and position_ms are required"}, 400)
        reason = str(payload.get("reason") or "tick")
        if reason not in REASONS:
            # Taken as a tick and carried on with. A garbled 2am request is not
            # news, but it should be findable in the journal afterwards.
            logger.info("position reported for an unknown reason %r", reason)
        report = await run_in_threadpool(
            player.report,
            gid,
            position_ms,
            _number(payload.get("seq")),
            # A page too old to know about this one, or a garbled body, claims
            # no playback rather than an impossible amount of it: the mark then
            # rises only where the report stands, which is what a report with
            # nothing behind it deserves.
            max(0, _number(payload.get("played_ms"))),
        )
        # Nulls dropped rather than sent: a report about a book that is gone
        # has no position to talk about, and saying "position_ms": null would
        # read as one.
        body = {k: v for k, v in asdict(report).items() if v is not None}
        return JSONResponse(body)

    async def catalog(request: Request) -> Response:
        """Which books there are to add, from the copy of the catalog on disk.

        An FTS5 query and nothing else: no Gutenberg round trip, because this is
        asked while somebody is standing there with a keyboard up and the answer
        has to arrive in the time a tap takes. Punctuation is the caller's own
        and is dealt with in :func:`somnia.catalog.search_catalog`, so a
        possessive apostrophe is a search rather than a syntax error.
        """
        query = request.query_params.get("q", "")
        # The language is the page's to say, but every voice somnia offers
        # reads English — the roster is American and British and nothing else,
        # because the other languages need a G2P backend that is not installed.
        # So in practice this is English and the parameter exists to keep the
        # route honest rather than because anything varies it.
        language = request.query_params.get("language", "en")
        entries = await run_in_threadpool(renders.search, query, language)
        return JSONResponse(
            {"query": query, "entries": [asdict(entry) for entry in entries]}
        )

    async def voices(request: Request) -> Response:
        """The voices a book may be asked for in, in the order they are drawn.

        Served rather than written into app.js, so that the list the page draws
        and the list this server will accept cannot come apart — a picker
        offering a voice the route refuses is a press that does nothing, which
        is the failure this page is arranged to make impossible. It also means
        the roster is one edit in one file when a voice is added or dropped.

        No database, nothing to lock: a tuple of strings, read once when the
        page opens Workshop.
        """
        return JSONResponse(
            {"voices": [asdict(voice) for voice in VOICES]},
            # `no-cache` means store it and ask before using it, which is what
            # this wants: a 304 of a few hundred bytes on a tailnet, against a
            # roster that can be a day out of date. A day was the wrong bargain
            # for the same reason the shell above is not allowed to make it —
            # somnia's roster changes when somnia is deployed, and the phone
            # that has the old one cannot be told. Workshop then offers a voice
            # the renderer has not got, or hides one it has, and the sample
            # plays nothing; the deploy is on the box and the page disagrees
            # with it until tomorrow.
            headers={"cache-control": "no-cache"},
        )

    async def queue_view(request: Request) -> Response:
        """The whole queue in one GET: what is rendering, what is next, what died.

        One request rather than one per row, because the panel polls this every
        few seconds while it is open and a fan of requests over a tailnet at 2am
        is a fan of chances to be shown half a list.
        """
        rows = await run_in_threadpool(renders.view)
        return JSONResponse({"items": [asdict(row) for row in rows]})

    async def queue_add(request: Request) -> Response:
        """Ask for a book, and be told in a sentence where it landed.

        Answered 200 whether or not it was taken, for exactly the reason
        ``/api/position`` gives: a 409 would put a red line in the console at 2am
        for something working exactly as designed, and invite a throw in the
        fetch wrapper that skipped the one line that mattered — which here is the
        sentence saying why. A refusal is an answer, and it is the answer
        somebody reads twice.

        The sentence comes from :func:`somnia.queue.submit`, which is also what
        ``Library.add_book`` returns, so the page and the voice cannot disagree
        about what just happened.

        ``voice`` is optional and is held to the roster, which is the one thing
        this route checks that the queue does not. The page can only send what
        it was drawn with, so a name that is not on the list is a page left open
        across a release or somebody with curl — and a book is six hours, which
        is too long to find out that a typo was quietly rendered in the default.
        Absent is not the same as wrong: no voice at all means the renderer's
        own, which is what the agent submits and what the CLI has always done.
        """
        payload = await _payload(request)
        gid = _number(payload.get("gid"))
        if gid < 1:
            # The one 400 here, matching /api/ask: there is nothing to submit,
            # so there is nothing to say 200 about. A gid is a positive integer,
            # which makes 0 as garbled as a word is.
            return JSONResponse({"error": "gid is required"}, 400)
        voice = str(payload.get("voice") or "")
        if voice and not known(voice):
            return JSONResponse({"error": f"no such voice: {voice}"}, 400)
        result = await run_in_threadpool(renders.submit, gid, voice)
        return JSONResponse(asdict(result))

    async def queue_stop(request: Request) -> Response:
        """Take a book out of the line, or ask the render to stop.

        Keyed on the queue row and not on the book: a gid owns several rows over
        its life — every attempt that failed or was stopped stays as the record
        of itself — so stopping by gid could reach into last week's.

        POST rather than DELETE, and the row does not go away. It becomes the
        record of a render somebody stopped, which is what the readout shows for
        a day afterwards.

        404 only for a job that does not exist, which is a page holding an id
        from a database that has moved on. A job that has already ended is 200
        with a sentence: that is a button pressed a second too late, and it is a
        different fact.
        """
        job_id = int(request.path_params["id"])
        stopped = await run_in_threadpool(renders.stop, job_id)
        return JSONResponse(asdict(stopped), 200 if stopped.state else 404)

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None, None]:
        """Warm the embedder on the way up, hand the connections back on the way down.

        Still no renderer and no child process — the queue is drained by the
        ``somnia-worker`` unit, and this app is the same cheap thing to start
        and stop that it was before the queue existed. The one thing it now
        starts is a thread that loads the embedding model, and it is a thread
        rather than an await so that starting is still instant: the page, the
        audio and the position reports are all being served while it loads, and
        the only caller that meets it is a search, which would have paid the
        whole cost itself.
        """
        warming = asyncio.create_task(run_in_threadpool(conversations.warm))
        yield
        # Cancelling rather than awaiting: a restart during those twelve
        # seconds is somebody deploying, and they should not have to wait for a
        # model to finish loading so that it can be thrown away.
        warming.cancel()
        player.close()
        renders.close()

    return Starlette(
        # Every route the page uses is under /api/, which is not cosmetic: the
        # service worker skips that prefix, and the Cache API throws if asked
        # to store the 206 that a seek produces. It also keeps them ahead of
        # the StaticFiles mount, which otherwise swallows everything.
        routes=[
            Route("/api/ask", ask, methods=["POST"]),
            Route("/api/forget", forget, methods=["POST"]),
            Route("/api/health", health),
            Route("/api/books", books),
            Route("/api/book/{gid:int}", book),
            # The same path, read and then taken away, in the shape the queue's
            # two routes are already in: one method each, one handler each.
            Route("/api/book/{gid:int}", remove_the_book, methods=["DELETE"]),
            Route("/api/book/{gid:int}/open", open_book, methods=["POST"]),
            Route("/api/audio/{gid:int}/{idx:int}", audio),
            Route("/api/stream/{gid:int}/{n:int}", stream),
            Route("/api/sentence/{gid:int}/{ms:int}", sentence),
            Route("/api/passage/{gid:int}/{ms:int}", passage),
            Route("/api/position", position, methods=["POST"]),
            Route("/api/catalog", catalog),
            Route("/api/voices", voices),
            # One path, two methods, two handlers. Starlette scans the whole
            # table for a full match before it settles for a partial one, so the
            # GET route's 405 for a POST never wins over the POST route below
            # it — reading the queue and adding to it stay separate functions
            # rather than one with a branch at the top.
            Route("/api/queue", queue_view),
            Route("/api/queue", queue_add, methods=["POST"]),
            Route("/api/queue/{id:int}/stop", queue_stop, methods=["POST"]),
            Mount("/", Shell(directory=WEB_DIR, html=True)),
        ],
        lifespan=lifespan,
    )


async def _payload(request: Request) -> dict[str, Any]:
    """The request body, or an empty one — a garbled 2am request is not news."""
    try:
        body: Any = await request.json()
    except ValueError:
        return {}
    return cast(dict[str, Any], body) if isinstance(body, dict) else {}


def _number(value: Any) -> int:
    """A whole number from the page, or -1 for anything that is not one.

    Every number the page sends is a count of milliseconds or of moves, so
    negative is already impossible and one sentinel does for missing, garbled
    and nonsensical alike.
    """
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        # OverflowError because JSON has Infinity and python's json accepts it:
        # `{"position_ms": Infinity}` reaches here as a float that int() will
        # not convert, and the two exceptions caught before this let it out of
        # the function and up through the route as a 500. Every other kind of
        # nonsense the page could send is already the sentinel, and a request
        # somnia cannot make sense of is a 400 by way of -1, not a traceback.
        return -1


def serve(cfg: Config, conn: sqlite3.Connection, host: str, port: int) -> None:
    """Run the chat page until interrupted."""
    import uvicorn  # noqa: PLC0415

    uvicorn.run(create_app(cfg, conn), host=host, port=port)
