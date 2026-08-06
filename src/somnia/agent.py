"""The 2am conversation: an Anthropic tool runner over :mod:`somnia.tools`.

The model's job is disambiguation and phrasing, not retrieval — the tools do the
work, and every answer is grounded in a passage that was actually rendered. The
default model is Haiku, which costs cents per conversation and is more than
enough to turn "the bit where the horse dies" into a place in the book.
"""

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic, beta_tool

from .abs import AbsClient
from .config import Config
from .tools import Library, Moved, format_timestamp

__all__ = ["SYSTEM_PROMPT", "Conversation", "Turn", "build_tools", "open_library"]

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

Only what somnia has rendered exists as audio, and you can only move them to a
passage the tools returned.

A name they say — a person, an animal, a place — is almost always something
inside the book they are listening to, and some of those names are also titles
of other books. Search the book before saying anything about what does or does
not exist. The catalog is for when they are plainly asking to add something new
to listen to, not for identifying a name they just said.

A search always returns its closest matches, however poor they are, so read the
passages and judge for yourself whether any is really the moment they meant. If
none is, say you couldn't find it rather than moving them to the least bad one.

When they describe a moment they want to get back to, find it and move the book
there, then tell them roughly where it now sits — "you're back at two hours in,
in the chapter about X". Moving takes them there: the page jumps to the new
place and plays from it. Never tell them to press play, and never say whether
anything is playing — you do not know.

Searches are limited to how far they have listened. When a search reports that
a closer match lies further on, say that it is ahead of where they have got and
offer to take them there or answer anyway — and say nothing about what happens
there until they accept.

Once they accept, search again with allow_spoilers so you can read those
passages and pick the right one. The timestamp alone is the top-ranked guess
and the ranking is often a near miss; moving them there unread lands them
minutes from the moment they asked for. Reading the passage does not oblige you
to describe it — move them there and tell them only that you have.

Moving them forward is a real jump: they will hear what is there. Never do it
past where they have listened unless they have just asked you to.

If it is ambiguous which book or which of several passages they mean, ask one
short question. Otherwise just act.

Never end your turn without saying something. Every action needs a sentence
after it, even when the answer is only "you're there now" — a silent reply is
indistinguishable from a broken app to someone half asleep in the dark. This
matters most just after they have told you to go ahead: say that you have
moved them and where to, and nothing about what happens there.\
"""


@dataclass
class Turn:
    """One exchange: what to say back, and where the book was put.

    ``move`` is None unless the agent moved the book, and the page reads the
    key's presence rather than its contents, so an empty one would be a move
    that never happened.

    Carrying it here is a shortcut, not the mechanism. The same move reaches the
    page anyway as the refusal of its next report — within fifteen seconds,
    whatever happens to this reply — and both routes end up in the same place.
    What the shortcut buys is those fifteen seconds, which is a long time to sit
    in the dark wondering whether anything happened.
    """

    reply: str
    move: Moved | None = None


def build_tools(
    library: Library,
    note: Callable[[str], None] = lambda _: None,
    record: Callable[[Moved], None] = lambda _: None,
) -> list[Any]:
    """Wrap the tool layer for the runner, as text the model can read.

    ``note`` is told about anything that changed the world — moving the book,
    starting a render. It is what the conversation falls back on when the model
    acts and then says nothing, and it deliberately never sees search results,
    which are full of the passages the spoiler guard exists to withhold.

    ``record`` hears about moves alone, and in numbers rather than prose,
    because the page has to act on one and cannot read a sentence.
    """

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
        started = library.add_book(gid)
        note(started)
        return started

    @beta_tool
    def get_position(gid: int) -> str:
        """Where the listener currently is in a book, and the text there.

        Use this when they ask where they are, what they missed, or when they
        last fell asleep.

        Args:
            gid: The Gutenberg id of the book.
        """
        position = library.get_position(gid)
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
                " ahead of where they are. Offer to take them there or to answer"
                " anyway, and do not say what happens there unless they accept."
            )
        return "\n\n".join(lines)

    @beta_tool
    def move_to(gid: int, position_ms: int) -> str:
        """Move the book to a moment, and play it from there.

        This is how they get taken to a passage: their position in the book
        becomes the point you name, and the book starts playing there.

        Args:
            gid: The Gutenberg id of the book.
            position_ms: Milliseconds from the start of the book, as returned
                by find_passage.
        """
        moved = library.move_to(gid, position_ms)
        note(moved.sentence)
        # A move that landed always counts up from zero, so a zero is the one
        # that did not — no such book, and nothing for the page to follow.
        if moved.seq:
            record(moved)
        return moved.sentence

    return [
        list_books,
        search_catalog,
        add_book,
        get_position,
        find_passage,
        move_to,
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
        self._actions: list[str] = []
        self._moves: list[Moved] = []
        self._tools = build_tools(library, self._actions.append, self._moves.append)
        self.messages: list[Any] = []

    def ask(self, question: str) -> Turn:
        """Run one turn: the tools do the work, the model does the talking.

        The turn is built on a copy and only kept if it finishes. A turn that
        dies part-way leaves an assistant tool call with no result behind it,
        and every later question in that conversation would be rejected —
        which, at 2am, looks like an app that has simply stopped working.
        """
        # The runner copies the list it is given, so mirroring its turns back
        # into ours is what carries the history to the next question.
        self._actions.clear()
        self._moves.clear()
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
            # Keep the last thing it actually said. A message that only calls a
            # tool has no text, and taking it as the answer would blank out a
            # sentence the model had already written.
            said = "".join(b.text for b in message.content if b.type == "text").strip()
            if said:
                reply = said

        if not reply:
            # It acted and then said nothing — most often after being told to go
            # ahead past the guard. What it did is better than a blank screen,
            # and the tools that report here are the ones that changed
            # something, never a search full of passages it was withholding.
            logger.warning("turn produced no text; answering with what it did")
            reply = self._actions[-1] if self._actions else ""
        self.messages = turn
        # The last move, on a turn that made more than one — a search, a move, a
        # second thought, a better move. The page has to end up somewhere, and
        # where it was told to go last is the only place that matches what was
        # said about it.
        return Turn(reply=reply, move=self._moves[-1] if self._moves else None)
