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
"""

import logging
import sqlite3
import threading
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict
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
from .config import Config
from .player import Player
from .tools import Library

__all__ = ["Conversations", "create_app", "serve"]

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

    def ask(self, token: str, question: str) -> Turn:
        with self._lock:
            conversation = self._by_token.pop(token, None)
            if conversation is None:
                conversation = Conversation(self._cfg, self._library)
            self._by_token[token] = conversation
            while len(self._by_token) > MAX_CONVERSATIONS:
                self._by_token.popitem(last=False)
            return conversation.ask(question)

    def forget(self, token: str) -> None:
        """Start again — they have changed the subject, or the agent is lost."""
        with self._lock:
            self._by_token.pop(token, None)


def create_app(cfg: Config, conn: sqlite3.Connection) -> Starlette:
    """The PWA, the agent behind it, and the book it plays."""
    conversations = Conversations(cfg, open_library(cfg, conn))
    # The player gets its own client rather than the library's. The point of
    # the fast lane is that nothing on it waits on the lane a model turn is
    # using, and that goes for the socket as much as for the connection.
    abs_client = AbsClient(cfg.abs_url, cfg.abs_token) if cfg.abs_token else None
    player = Player(cfg, abs_client)

    async def ask(request: Request) -> Response:
        payload = await _payload(request)
        token = str(payload.get("token") or "")
        question = str(payload.get("question") or "").strip()
        if not token or not question:
            return JSONResponse({"error": "token and question are required"}, 400)
        try:
            # A turn blocks for seconds on the model and on sqlite, so it runs
            # off the event loop.
            turn = await run_in_threadpool(conversations.ask, token, question)
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

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None, None]:
        """Hand the player's connection back when the server stops."""
        yield
        player.close()

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
            Route("/api/audio/{gid:int}/{idx:int}", audio),
            Route("/api/sentence/{gid:int}/{ms:int}", sentence),
            Route("/api/position", position, methods=["POST"]),
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
