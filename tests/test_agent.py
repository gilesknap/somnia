import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic import Anthropic

from fakes import FakeAbs, FakeEmbedder
from somnia.abs import AbsClient
from somnia.agent import Conversation
from somnia.config import Config
from somnia.db import connect
from somnia.embed import Embedder
from somnia.tools import Library


def text(body: str) -> Any:
    return SimpleNamespace(type="text", text=body)


def tool_use() -> Any:
    return SimpleNamespace(type="tool_use", name="list_books", input={})


class FakeRunner:
    """The SDK tool runner, minus the model.

    ``dies_after`` reproduces a turn that gets part-way — a tool call made,
    its answer never returned — which is exactly the state that must not be
    kept. ``calls`` runs real tools, the way the runner would.
    """

    def __init__(
        self,
        turns: list[Any],
        dies_after: int | None = None,
        calls: list[tuple[str, dict[str, Any]]] | None = None,
        tools: list[Any] | None = None,
    ) -> None:
        self._turns = turns
        self._dies_after = dies_after
        self._sent = 0
        for name, arguments in calls or []:
            tool = next(t for t in tools or [] if t.name == name)
            tool.call(arguments)

    def __iter__(self) -> Iterator[Any]:
        for n, turn in enumerate(self._turns):
            if self._dies_after is not None and n == self._dies_after:
                raise RuntimeError("the API went away mid-turn")
            self._sent = n + 1
            yield turn

    def generate_tool_call_response(self) -> Any:
        turn = self._turns[self._sent - 1]
        if any(block.type == "tool_use" for block in turn.content):
            return {"role": "user", "content": [{"type": "tool_result"}]}
        return None


def client_returning(*runners: FakeRunner) -> Anthropic:
    """A stand-in Anthropic client that hands out the given runners in turn."""
    handed_out = iter(runners)

    def tool_runner(**kwargs: Any) -> FakeRunner:
        return next(handed_out)

    fake = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner))
    )
    return cast(Anthropic, fake)


def client_that_acts(
    turns: list[Any], calls: list[tuple[str, dict[str, Any]]]
) -> Anthropic:
    """A client whose runner calls real tools before yielding its turns."""

    def tool_runner(**kwargs: Any) -> FakeRunner:
        return FakeRunner(turns, calls=calls, tools=kwargs["tools"])

    fake = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner))
    )
    return cast(Anthropic, fake)


@pytest.fixture
def library(tmp_path: Path) -> Iterator[Library]:
    conn: sqlite3.Connection = connect(tmp_path / "somnia.db")
    try:
        yield Library(Config(data_dir=tmp_path), conn)
    finally:
        conn.close()


@pytest.fixture
def library_with_book(tmp_path: Path) -> Iterator[Library]:
    """A library the action tools can actually act on."""
    conn: sqlite3.Connection = connect(tmp_path / "somnia.db")
    try:
        with conn:
            conn.execute(
                "INSERT INTO books (gid, title, voice, status, total_ms,"
                " abs_item_id) VALUES (271, 'Black Beauty', 'af_heart', 'done',"
                " 7200000, 'abs-item-1')"
            )
        yield Library(
            Config(data_dir=tmp_path),
            conn,
            cast(AbsClient, FakeAbs(0.0)),
            cast(Embedder, FakeEmbedder()),
        )
    finally:
        conn.close()


def test_each_turn_is_remembered_for_the_next_question(library: Library) -> None:
    conversation = Conversation(
        Config(),
        library,
        client_returning(
            FakeRunner([SimpleNamespace(content=[text("Black Beauty.")])]),
            FakeRunner([SimpleNamespace(content=[text("Two hours in.")])]),
        ),
    )
    assert conversation.ask("what have I got?") == "Black Beauty."
    assert conversation.ask("how far?") == "Two hours in."
    # user, assistant, user, assistant — the second question was asked in the
    # context of the first.
    assert [m["role"] for m in conversation.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_a_turn_that_dies_leaves_the_conversation_as_it_was(library: Library) -> None:
    """A half-finished turn holds a tool call with no result behind it.

    Keeping that would make every later question in the conversation invalid,
    so a failed turn must leave no trace at all.
    """
    conversation = Conversation(
        Config(),
        library,
        client_returning(
            FakeRunner([SimpleNamespace(content=[text("Black Beauty.")])]),
            FakeRunner(
                [
                    SimpleNamespace(content=[tool_use()]),
                    SimpleNamespace(content=[text("never arrives")]),
                ],
                dies_after=1,
            ),
        ),
    )
    conversation.ask("what have I got?")
    good = list(conversation.messages)

    with pytest.raises(RuntimeError):
        conversation.ask("where does the horse die?")

    assert conversation.messages == good


def test_a_sentence_written_before_a_tool_call_is_not_lost(library: Library) -> None:
    """The last message of a turn is often a bare tool call with no text.

    Taking that as the answer would blank out what the model had already said.
    """
    conversation = Conversation(
        Config(),
        library,
        client_returning(
            FakeRunner(
                [
                    SimpleNamespace(content=[text("Taking you there.")]),
                    SimpleNamespace(content=[tool_use()]),
                ]
            )
        ),
    )
    assert conversation.ask("take me back") == "Taking you there."


def test_acting_without_speaking_answers_with_what_it_did(
    library_with_book: Library,
) -> None:
    """Silence after acting reads as a broken app to someone half asleep.

    It happens most after "go ahead" past the spoiler guard, where the prompt
    tells the model to say very little about what is there.
    """
    conversation = Conversation(
        Config(),
        library_with_book,
        client_that_acts(
            [SimpleNamespace(content=[])],
            calls=[("move_to", {"gid": 271, "position_ms": 3_600_000})],
        ),
    )
    assert conversation.ask("go") == "Moved to 1:00:00."


def test_a_search_is_never_used_as_the_answer(library_with_book: Library) -> None:
    """The fallback must not become a spoiler leak.

    Search results carry the passages the guard exists to withhold, so a turn
    that only searched and then said nothing says nothing.
    """
    conversation = Conversation(
        Config(),
        library_with_book,
        client_that_acts(
            [SimpleNamespace(content=[])],
            calls=[("find_passage", {"gid": 271, "description": "the hunt"})],
        ),
    )
    assert conversation.ask("where is the hunt?") == ""
