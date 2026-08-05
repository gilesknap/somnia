import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic import Anthropic

from somnia.agent import Conversation
from somnia.config import Config
from somnia.db import connect
from somnia.tools import Library


def text(body: str) -> Any:
    return SimpleNamespace(type="text", text=body)


def tool_use() -> Any:
    return SimpleNamespace(type="tool_use", name="list_books", input={})


class FakeRunner:
    """The SDK tool runner, minus the model.

    ``dies_after`` reproduces a turn that gets part-way — a tool call made,
    its answer never returned — which is exactly the state that must not be
    kept.
    """

    def __init__(self, turns: list[Any], dies_after: int | None = None) -> None:
        self._turns = turns
        self._dies_after = dies_after
        self._sent = 0

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


@pytest.fixture
def library(tmp_path: Path) -> Iterator[Library]:
    conn: sqlite3.Connection = connect(tmp_path / "somnia.db")
    try:
        yield Library(Config(data_dir=tmp_path), conn)
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
