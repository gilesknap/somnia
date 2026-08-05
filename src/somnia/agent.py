"""The 2am conversation: an Anthropic tool runner over :mod:`somnia.tools`.

The model's job is disambiguation and phrasing, not retrieval — the tools do the
work, and every answer is grounded in a passage that was actually rendered. The
default model is Haiku, which costs cents per conversation and is more than
enough to turn "the bit where the horse dies" into a bookmark.
"""

import logging
import sqlite3
from typing import Any

from anthropic import Anthropic, beta_tool

from .abs import AbsClient
from .config import Config
from .tools import Library, format_timestamp

__all__ = ["SYSTEM_PROMPT", "ask", "build_tools"]

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You help someone find their place in an audiobook they are falling asleep to.
It is the middle of the night and they are half awake, often speaking rather
than typing, so their words may be garbled or vague. Work with what they give
you.

Answer in one or two sentences. No preamble, no lists, no markdown — this is
read on a phone in the dark, or heard.

Use the tools rather than your own memory of the book. You may well know these
books, but only what somnia has rendered actually exists as audio, and only a
passage the tools return can be bookmarked.

A search always returns its closest matches, however poor they are, so read the
passages and judge for yourself whether any is really the moment they meant. If
none is, say you couldn't find it rather than bookmarking the least bad one.

When they describe a moment they want to get back to, find it and plant a
bookmark, then tell them the name you gave it and roughly where it falls. They
jump to bookmarks from the app; you never play anything yourself.

Searches are limited to how far they have listened, so you cannot spoil the
book. If they ask about something further on, say it is further on than they
have got, and offer to answer anyway.

If it is ambiguous which book or which of several passages they mean, ask one
short question. Otherwise just act.\
"""


def build_tools(library: Library) -> list[Any]:
    """Wrap the tool layer for the runner, as text the model can read."""

    @beta_tool
    def list_books() -> str:
        """List the audiobooks somnia has, with how much is rendered so far.

        Use this to work out which book someone means, or when they ask what
        they can listen to.
        """
        books = library.books()
        if not books:
            return "No books yet."
        return "\n".join(
            f"gid {b.gid}: {b.title} by {b.authors or 'unknown'}"
            f" — {b.status}, {b.chapters} chapters, {format_timestamp(b.total_ms)} long"
            for b in books
        )

    @beta_tool
    def search_catalog(query: str) -> str:
        """Search Project Gutenberg for a book that could be added.

        Args:
            query: Title, author, or subject words to search for.
        """
        entries = library.search_catalog(query)
        if not entries:
            return f"Nothing in the Gutenberg catalog matches {query!r}."
        return "\n".join(
            f"gid {e.gid}: {e.title} — {e.authors}" for e in entries[:10]
        )

    @beta_tool
    def add_book(gid: int) -> str:
        """Start rendering a Gutenberg book to audio. Takes hours to finish.

        Args:
            gid: The Gutenberg id, from search_catalog.
        """
        return library.add_book(gid)

    @beta_tool
    def get_position(gid: int) -> str:
        """Where the listener currently is in a book, and the text there.

        Use this when they ask where they are, what they missed, or when they
        last fell asleep.

        Args:
            gid: The Gutenberg id of the book.
        """
        try:
            position = library.get_position(gid)
        except LookupError as exc:
            return str(exc)
        if position is None:
            return "They have not started this book."
        return (
            f"{format_timestamp(position.position_ms)} into"
            f" {position.book.title}, in {position.chapter_title!r}."
            f" The text there: {position.text}"
        )

    @beta_tool
    def find_passage(gid: int, description: str, allow_spoilers: bool = False) -> str:
        """Find passages in a book matching a description of what happens.

        Works on concrete events, characters, and places ("the horse dies",
        "who Ginger is"), not on atmosphere ("the strange bit").

        Args:
            gid: The Gutenberg id of the book.
            description: What happens in the passage they want.
            allow_spoilers: Search the whole book rather than only the part
                they have heard. Only set this if they have said they don't
                mind being spoiled.
        """
        passages = library.find_passage(
            gid, description, spoiler_free=not allow_spoilers
        )
        if not passages:
            return "No matching passage in what they have heard so far."
        return "\n\n".join(
            f"[{format_timestamp(p.start_ms)} in {p.chapter_title!r},"
            f" position_ms={p.start_ms}] {p.text}"
            for p in passages
        )

    @beta_tool
    def plant_bookmark(gid: int, position_ms: int, title: str) -> str:
        """Bookmark a moment so they can jump to it from the app.

        Args:
            gid: The Gutenberg id of the book.
            position_ms: Milliseconds from the start of the book, as returned
                by find_passage.
            title: A short name for the bookmark, in their words.
        """
        try:
            return library.plant_bookmark(gid, position_ms, title)
        except LookupError as exc:
            return str(exc)

    return [
        list_books,
        search_catalog,
        add_book,
        get_position,
        find_passage,
        plant_bookmark,
    ]


def ask(
    cfg: Config,
    conn: sqlite3.Connection,
    question: str,
    history: list[Any] | None = None,
) -> tuple[str, list[Any]]:
    """Run one turn of the conversation. Returns (reply, updated history)."""
    abs_client = AbsClient(cfg.abs_url, cfg.abs_token) if cfg.abs_token else None
    library = Library(cfg, conn, abs_client)
    client = Anthropic(api_key=cfg.anthropic_api_key or None)

    messages: list[Any] = [*(history or []), {"role": "user", "content": question}]
    runner = client.beta.messages.tool_runner(
        model=cfg.agent_model,
        max_tokens=cfg.agent_max_tokens,
        system=SYSTEM_PROMPT,
        tools=build_tools(library),
        messages=messages,
    )

    reply = ""
    for message in runner:
        messages.append({"role": "assistant", "content": message.content})
        tool_response = runner.generate_tool_call_response()
        if tool_response is not None:
            messages.append(tool_response)
        reply = "".join(b.text for b in message.content if b.type == "text")
    return reply, messages
