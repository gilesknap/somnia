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

import logging
import sqlite3
import threading
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .abs import AbsClient
from .agent import Conversation, Turn, open_library
from .catalog import search_catalog
from .config import Config
from .db import connect
from .player import Player
from .queue import LIVE, QueueRow, Stopped, Submission, stop, submit, view
from .tools import Library

__all__ = ["Conversations", "Found", "Queue", "create_app", "serve"]

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"

# One listener, one phone — but a reloaded page mints a fresh token, so a few
# nights of tabs can accumulate. Old ones are dropped, not remembered.
MAX_CONVERSATIONS = 8

# Why the page is telling us where it is. The five below mean they have stopped
# — "switch" is the book left behind when the agent moves them to another one,
# which for that book is as much of a stop as putting the phone down — and so
# are the moments Audiobookshelf is worth telling: it is right whenever someone
# might next open it, at the cost of a handful of writes a night rather than one
# every fifteen seconds.
STOPPED = frozenset({"pause", "hidden", "unload", "ended", "switch"})
REASONS = STOPPED | frozenset({"load", "play", "tick", "seek", "chapter"})

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

    def ask(self, token: str, question: str, gid: int | None = None) -> Turn:
        with self._lock:
            conversation = self._by_token.pop(token, None)
            if conversation is None:
                conversation = Conversation(self._cfg, self._library)
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
    """

    gid: int
    title: str
    authors: str
    have: str | None


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
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = connect(cfg.db_path, cross_thread=True)

    def close(self) -> None:
        """Give the connection back, so shutdown is not a ResourceWarning."""
        with self._lock:
            self._conn.close()

    def view(self) -> list[QueueRow]:
        with self._lock:
            return view(self._conn)

    def submit(self, gid: int) -> Submission:
        with self._lock:
            return submit(self._conn, gid)

    def stop(self, job_id: int) -> Stopped:
        with self._lock:
            return stop(self._conn, job_id)

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
    # The player gets its own client rather than the library's. The point of
    # the fast lane is that nothing on it waits on the lane a model turn is
    # using, and that goes for the socket as much as for the connection.
    abs_client = AbsClient(cfg.abs_url, cfg.abs_token) if cfg.abs_token else None
    player = Player(cfg, abs_client)
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
        told = report.accepted and reason in STOPPED
        return JSONResponse(
            body,
            # After the reply is on the wire, never before it. Audiobookshelf is
            # a courtesy and the page is waiting.
            background=BackgroundTask(player.tell_abs, gid, position_ms)
            if told
            else None,
        )

    async def catalog(request: Request) -> Response:
        """Which books there are to add, from the copy of the catalog on disk.

        An FTS5 query and nothing else: no Gutenberg round trip, because this is
        asked while somebody is standing there with a keyboard up and the answer
        has to arrive in the time a tap takes. Punctuation is the caller's own
        and is dealt with in :func:`somnia.catalog.search_catalog`, so a
        possessive apostrophe is a search rather than a syntax error.
        """
        query = request.query_params.get("q", "")
        # The language is the page's to say, but there is only ever one voice
        # installed, so in practice this is English and the parameter exists to
        # keep the route honest rather than because anything varies it.
        language = request.query_params.get("language", "en")
        entries = await run_in_threadpool(renders.search, query, language)
        return JSONResponse(
            {"query": query, "entries": [asdict(entry) for entry in entries]}
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
        """
        payload = await _payload(request)
        gid = _number(payload.get("gid"))
        if gid < 1:
            # The one 400 here, matching /api/ask: there is nothing to submit,
            # so there is nothing to say 200 about. A gid is a positive integer,
            # which makes 0 as garbled as a word is.
            return JSONResponse({"error": "gid is required"}, 400)
        result = await run_in_threadpool(renders.submit, gid)
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
        """Hand the connections back when the server stops.

        Nothing is started here. No thread, no child process, no renderer: the
        queue is drained by the ``somnia-worker`` unit, so this app is the same
        cheap thing to start and stop that it was before the queue existed.
        """
        yield
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
            Route("/api/book/{gid:int}/open", open_book, methods=["POST"]),
            Route("/api/audio/{gid:int}/{idx:int}", audio),
            Route("/api/sentence/{gid:int}/{ms:int}", sentence),
            Route("/api/position", position, methods=["POST"]),
            Route("/api/catalog", catalog),
            # One path, two methods, two handlers. Starlette scans the whole
            # table for a full match before it settles for a partial one, so the
            # GET route's 405 for a POST never wins over the POST route below
            # it — reading the queue and adding to it stay separate functions
            # rather than one with a branch at the top.
            Route("/api/queue", queue_view),
            Route("/api/queue", queue_add, methods=["POST"]),
            Route("/api/queue/{id:int}/stop", queue_stop, methods=["POST"]),
            Mount("/", StaticFiles(directory=WEB_DIR, html=True)),
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
    except (TypeError, ValueError):
        return -1


def serve(cfg: Config, conn: sqlite3.Connection, host: str, port: int) -> None:
    """Run the chat page until interrupted."""
    import uvicorn  # noqa: PLC0415

    uvicorn.run(create_app(cfg, conn), host=host, port=port)
