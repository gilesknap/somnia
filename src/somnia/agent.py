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

__all__ = ["SYSTEM_PROMPT", "Conversation", "build_tools", "open_library"]

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You help someone find their place in an audiobook they are falling asleep to.
It is the middle of the night and they are half awake, often speaking rather
than typing, so their words may be garbled or vague. Work with what they give
you.

Answer in one or two sentences. No preamble, no lists, no markdown — this is
read on a phone in the dark, or heard.

Everything you say about a book must come from a tool result in this
conversation. You know these books already, and that knowledge is the single
biggest risk here, not a resource: it is how you spoil a book without meaning
to. Never name a character, event, place or outcome that has not appeared in a
tool result — not to show you understood, not to offer them a choice, not even
to ask a clarifying question. If you want to ask which of two moments they
meant, describe only moments the tools actually returned.

Only what somnia has rendered exists as audio, and only a passage the tools
return can be bookmarked.

A search always returns its closest matches, however poor they are, so read the
passages and judge for yourself whether any is really the moment they meant. If
none is, say you couldn't find it rather than bookmarking the least bad one.

When they describe a moment they want to get back to, find it and plant a
bookmark, then tell them the name you gave it and roughly where it falls. They
jump to bookmarks from the app; you never play anything yourself.

Searches are limited to how far they have listened. When a search reports that
a closer match lies further on, say that it is ahead of where they have got and
offer to take them there or answer anyway — and say nothing about what happens
there until they accept.

Once they accept, search again with allow_spoilers so you can read those
passages and pick the right one. The timestamp alone is the top-ranked guess
and the ranking is often a near miss; bookmarking it unread lands them minutes
from the moment they asked for. Reading the passage does not oblige you to
describe it — bookmark it and name the bookmark in their words.

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
        return "\n".join(f"gid {e.gid}: {e.title} — {e.authors}" for e in entries[:10])

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
        search = library.find_passage(gid, description, spoiler_free=not allow_spoilers)
        lines: list[str] = []
        if search.searched_to_ms is not None:
            lines.append(
                f"Searched the first {format_timestamp(search.searched_to_ms)},"
                " which is as far as they have listened."
            )
        if search.hits:
            lines.append(
                "\n\n".join(
                    f"[{format_timestamp(p.start_ms)} in {p.chapter_title!r},"
                    f" position_ms={p.start_ms}] {p.text}"
                    for p in search.hits
                )
            )
        else:
            lines.append("Nothing in that stretch.")
        if search.better_ahead is not None:
            lines.append(
                "A closer match lies further on than they have listened, at"
                f" {format_timestamp(search.better_ahead.start_ms)}. Tell them it is"
                " ahead of where they are and offer to bookmark it or answer anyway."
                " Do not say what happens there unless they accept."
            )
        return "\n\n".join(lines)

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


def open_library(cfg: Config, conn: sqlite3.Connection) -> Library:
    """The tool layer, wired to Audiobookshelf if a token is configured."""
    abs_client = AbsClient(cfg.abs_url, cfg.abs_token) if cfg.abs_token else None
    return Library(cfg, conn, abs_client)


class Conversation:
    """One exchange with the agent, held open across turns.

    The library outlives the turn deliberately: its embedder loads torch and
    a sentence-transformer model, which takes seconds. Building it per question
    would put that wait between "where does the horse die" and the answer.
    """

    def __init__(
        self,
        cfg: Config,
        library: Library,
        client: Anthropic | None = None,
    ) -> None:
        self._cfg = cfg
        self._client = client or Anthropic(api_key=cfg.anthropic_api_key or None)
        self._tools = build_tools(library)
        self.messages: list[Any] = []

    def ask(self, question: str) -> str:
        """Run one turn: the tools do the work, the model does the talking.

        The turn is built on a copy and only kept if it finishes. A turn that
        dies part-way leaves an assistant tool call with no result behind it,
        and every later question in that conversation would be rejected —
        which, at 2am, looks like an app that has simply stopped working.
        """
        # The runner copies the list it is given, so mirroring its turns back
        # into ours is what carries the history to the next question.
        turn: list[Any] = [*self.messages, {"role": "user", "content": question}]
        runner = self._client.beta.messages.tool_runner(
            model=self._cfg.agent_model,
            max_tokens=self._cfg.agent_max_tokens,
            system=SYSTEM_PROMPT,
            tools=self._tools,
            messages=turn,
        )

        reply = ""
        for message in runner:
            turn.append({"role": "assistant", "content": message.content})
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                turn.append(tool_response)
            reply = "".join(b.text for b in message.content if b.type == "text")
        self.messages = turn
        return reply
