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
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .agent import Conversation, open_library
from .config import Config
from .player import Player
from .tools import Library

__all__ = ["Conversations", "create_app", "serve"]

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"

# One listener, one phone — but a reloaded page mints a fresh token, so a few
# nights of tabs can accumulate. Old ones are dropped, not remembered.
MAX_CONVERSATIONS = 8


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

    def ask(self, token: str, question: str) -> str:
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
    player = Player(cfg)

    async def ask(request: Request) -> Response:
        payload = await _payload(request)
        token = str(payload.get("token") or "")
        question = str(payload.get("question") or "").strip()
        if not token or not question:
            return JSONResponse({"error": "token and question are required"}, 400)
        try:
            # A turn blocks for seconds on the model and on sqlite, so it runs
            # off the event loop.
            reply = await run_in_threadpool(conversations.ask, token, question)
        except Exception:
            logger.exception("agent turn failed")
            return JSONResponse({"error": "Something went wrong down here."}, 500)
        return JSONResponse({"reply": reply})

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


def serve(cfg: Config, conn: sqlite3.Connection, host: str, port: int) -> None:
    """Run the chat page until interrupted."""
    import uvicorn  # noqa: PLC0415

    uvicorn.run(create_app(cfg, conn), host=host, port=port)
