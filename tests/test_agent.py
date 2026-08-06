import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic import Anthropic

from black_beauty import CHAPTERS, PASSAGES, build_black_beauty
from fakes import FakeAbs, FakeEmbedder
from somnia.abs import AbsClient
from somnia.agent import OFFER_SENTENCE, SYSTEM_PROMPT, Conversation, build_tools
from somnia.config import Config
from somnia.db import connect
from somnia.embed import Embedder
from somnia.queue import claim
from somnia.tools import Library, Moved, Offer


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


def client_that_acts_each(
    *rounds: tuple[list[Any], list[tuple[str, dict[str, Any]]]],
) -> Anthropic:
    """A client that does something different on each question it is asked.

    What is remembered between turns, and what is thrown away at the start of
    one, can only be told apart by asking twice — the passages a search found
    outlive the question that found them, and the list it offered does not.
    """
    remaining = iter(rounds)

    def tool_runner(**kwargs: Any) -> FakeRunner:
        turns, calls = next(remaining)
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
    assert conversation.ask("what have I got?").reply == "Black Beauty."
    assert conversation.ask("how far?").reply == "Two hours in."
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
    assert conversation.ask("take me back").reply == "Taking you there."


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
    assert conversation.ask("go").reply == "Moved to 1:00:00, and it plays from there."


def test_a_turn_that_moved_twice_reports_where_it_left_them(
    library_with_book: Library,
) -> None:
    """A turn can search, move, think better of it, and move again.

    The page has to end up somewhere, and the last place it was sent is the only
    one that matches what was said about it.
    """
    conversation = Conversation(
        Config(),
        library_with_book,
        client_that_acts(
            [SimpleNamespace(content=[text("You're at the fair.")])],
            calls=[
                ("move_to", {"gid": 271, "position_ms": 60_000}),
                ("move_to", {"gid": 271, "position_ms": 3_600_000}),
            ],
        ),
    )
    turn = conversation.ask("take me to the fair")

    assert turn.move is not None
    assert (turn.move.gid, turn.move.position_ms) == (271, 3_600_000)
    # The count the page is handed has to be the one the second move wrote, or
    # its next report is refused and it is dragged back to the first.
    assert turn.move.seq == 2


def test_a_turn_that_moved_nothing_carries_no_move(library_with_book: Library) -> None:
    """The page reads the move's presence, so an idle turn must not invent one."""
    conversation = Conversation(
        Config(),
        library_with_book,
        client_returning(
            FakeRunner([SimpleNamespace(content=[text("Two hours in.")])])
        ),
    )
    assert conversation.ask("how far am I?").move is None


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
    assert conversation.ask("where is the hunt?").reply == ""


# ------------------------------------------- the places they might have meant


@dataclass
class Searchable:
    """A book with real passages in it, and the row underneath."""

    library: Library
    conn: sqlite3.Connection


@dataclass
class Wired:
    """The tools as the runner sees them, with all three callbacks tapped.

    Built directly rather than through a conversation because what is under
    test here is what one tool does to the next: the refusals are the only
    thing standing between a listener and a book that moved while they were
    reading a list, and a refusal is a string the model is handed.
    """

    tools: dict[str, Any]
    # The factories are the parametrised aliases rather than bare `list`,
    # which builds the same empty list but keeps the element type. Bare
    # `list` infers as `list[Unknown]` under the strict pyright the lint job
    # runs, and these three lists are handed straight to `build_tools` as its
    # callbacks — so an unknown element type there is the one place a wrong
    # tool payload would stop being a type error and become a silent pass.
    notes: list[str] = field(default_factory=list[str])
    moves: list[Moved] = field(default_factory=list[Moved])
    offers: list[Offer] = field(default_factory=list[Offer])

    def call(self, name: str, **arguments: Any) -> str:
        return str(self.tools[name].call(arguments))


@pytest.fixture
def searchable(tmp_path: Path) -> Iterator[Searchable]:
    """A library the search and the list can both actually work on.

    The embedder has to be the one that indexed the book — a fake hands out an
    axis per string it has seen — so the library and the fixture share one.
    """
    conn: sqlite3.Connection = connect(tmp_path / "somnia.db")
    embedder = cast(Embedder, FakeEmbedder())
    try:
        build_black_beauty(conn, embedder)
        yield Searchable(
            library=Library(
                Config(data_dir=tmp_path),
                conn,
                cast(AbsClient, FakeAbs(0.0)),
                embedder,
            ),
            conn=conn,
        )
    finally:
        conn.close()


def wired(searchable: Searchable) -> Wired:
    """One turn's worth of tools, with somewhere for each callback to land."""
    ready = Wired(tools={})
    ready.tools = {
        tool.name: tool
        for tool in build_tools(
            searchable.library,
            ready.notes.append,
            ready.moves.append,
            ready.offers.append,
        )
    }
    return ready


def place(searchable: Searchable, start_ms: int) -> int:
    """The id of the passage that begins there, as a search would name it."""
    row = searchable.conn.execute(
        "SELECT id FROM chunks WHERE book_gid = 271 AND start_ms = ?", (start_ms,)
    ).fetchone()
    assert row is not None, f"no passage at {start_ms}"
    return int(row["id"])


def seq(searchable: Searchable) -> int:
    """How many times the book has been moved — zero if nothing wrote a thing."""
    row = searchable.conn.execute(
        "SELECT position_seq FROM books WHERE gid = 271"
    ).fetchone()
    return int(row["position_seq"])


def test_a_turn_that_offered_hands_the_page_the_list_and_says_one_sentence(
    searchable: Searchable,
) -> None:
    """Offering is a whole answer, and it is the page that gives it.

    The model has nothing left to say once the list is up — the screen holds
    the times and the words — so the turn ends with the one neutral sentence
    and the places travel beside it.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts(
            [SimpleNamespace(content=[])],
            calls=[
                (
                    "find_passage",
                    {"gid": 271, "description": "the meadow with the pond"},
                ),
                (
                    "offer_positions",
                    {
                        "gid": 271,
                        "chunk_ids": [
                            place(searchable, 10_000),
                            place(searchable, 300_000),
                        ],
                    },
                ),
            ],
        ),
    )
    turn = conversation.ask("the bit by the pond")

    assert turn.reply == OFFER_SENTENCE
    assert turn.candidates is not None
    assert [p.start_ms for p in turn.candidates.places] == [10_000, 300_000]
    # Nothing moved. The question is on the screen and the answer is theirs.
    assert turn.move is None
    assert seq(searchable) == 0


def test_the_sentence_beside_a_list_says_nothing_about_what_is_on_it(
    searchable: Searchable,
) -> None:
    """It names no place, no chapter, no character and no time.

    A sentence that summarised the list would leak exactly what the "show me
    what's there" control exists to withhold, and it would do it in the one
    part of the reply that is read aloud. The prompt quotes the same constant,
    so the words the model is told to say and the words said on its behalf
    cannot drift apart.
    """
    assert OFFER_SENTENCE == "There are a few places that could be it."
    assert not re.search(r"\d", OFFER_SENTENCE)
    for _, text, _ in PASSAGES:
        assert text not in OFFER_SENTENCE
    for title, _, _ in CHAPTERS:
        assert title not in OFFER_SENTENCE
    assert OFFER_SENTENCE in SYSTEM_PROMPT


def test_what_the_model_is_told_after_a_list_holds_no_time_and_no_words(
    searchable: Searchable,
) -> None:
    """A tool result is the one place a withheld passage could come back.

    So this one is counts and an instruction: how many places, how many of them
    lie further on, and the sentence to say. No timestamp, no chapter, no
    passage and no position_ms — the model is handed a sentence it already has
    rather than the materials to write its own.
    """
    ready = wired(searchable)
    ready.call(
        "find_passage",
        gid=271,
        description="a later scene the listener has not reached",
    )
    result = ready.call(
        "offer_positions",
        gid=271,
        chunk_ids=[place(searchable, 700_000), place(searchable, 10_000)],
    )

    assert OFFER_SENTENCE in result
    assert not re.search(r"\d+:\d\d:\d\d", result)
    assert "position_ms" not in result
    for _, text, start_ms in PASSAGES:
        assert text not in result
        assert str(start_ms) not in result
    for title, _, _ in CHAPTERS:
        assert title not in result
    assert "one of them is further on than they have listened" in result
    assert len(ready.offers) == 1


def test_a_search_names_a_passage_it_can_offer_without_giving_the_ahead_one_away(
    searchable: Searchable,
) -> None:
    """The id is the whole of the new handle, and the only one that ahead one gets.

    A list may only name passages a search really returned, and an id is how
    the model says which. For the passage past the mark that is all it is ever
    told beside the time — not the words, not the chapter, not the position —
    because offering it is the one thing that can be done with a passage nobody
    has heard, and offering it needs nothing more.
    """
    ahead = searchable.library.find_passage(
        271, "a later scene the listener has not reached"
    ).better_ahead
    assert ahead is not None

    result = wired(searchable).call(
        "find_passage",
        gid=271,
        description="a later scene the listener has not reached",
    )

    assert f"id={place(searchable, 10_000)}, position_ms=10000" in result
    assert f"(id={ahead.chunk_id})" in result
    assert "a later scene the listener has not reached" not in result
    assert "47 Hard Times" not in result
    assert "700000" not in result


def test_a_turn_that_offered_a_list_will_not_also_move_the_book(
    searchable: Searchable,
) -> None:
    """Refused at the tool, because there is nowhere later to refuse it.

    The row is written before the call returns, so stopping the move when the
    turn is assembled, or when the reply is serialised, would leave the
    position and its count in the database — and the page would meet them
    fifteen seconds later as the refusal of its next report and be dragged off,
    mid-list, to a place nobody chose.
    """
    ready = wired(searchable)
    ready.call("find_passage", gid=271, description="the meadow with the pond")
    ready.call(
        "offer_positions",
        gid=271,
        chunk_ids=[place(searchable, 10_000), place(searchable, 300_000)],
    )

    said = ready.call("move_to", gid=271, position_ms=10_000)

    assert "not yours to move" in said
    assert ready.moves == []
    assert ready.notes == []
    assert seq(searchable) == 0


def test_a_turn_that_moved_the_book_has_no_list_left_to_offer(
    searchable: Searchable,
) -> None:
    """The other way round, and refused just as flatly.

    A list drawn over a book that has already jumped is a question about where
    they are standing, asked after they were moved there.
    """
    ready = wired(searchable)
    ready.call("find_passage", gid=271, description="the meadow with the pond")
    ready.call("move_to", gid=271, position_ms=10_000)

    said = ready.call(
        "offer_positions",
        gid=271,
        chunk_ids=[place(searchable, 10_000), place(searchable, 300_000)],
    )

    assert "already moved them" in said
    assert ready.offers == []


def test_a_passage_it_did_not_find_here_is_not_a_place_it_can_offer(
    searchable: Searchable,
) -> None:
    """A real id, and still refused: it did not come from a search in this turn.

    An id read off the wrong part of a result line, or carried in from
    somewhere else entirely, resolves to words that are not the passage that
    matched — and a list whose rows are not the search results is worse than no
    list, because nothing on it says so.
    """
    ready = wired(searchable)

    said = ready.call(
        "offer_positions",
        gid=271,
        chunk_ids=[place(searchable, 10_000), place(searchable, 300_000)],
    )

    assert "did not come from a search in this conversation" in said
    assert ready.offers == []


def test_a_refused_offer_leaves_the_turn_free_to_move_them_instead(
    searchable: Searchable,
) -> None:
    """Every refusal emits nothing, and that includes not spending the turn.

    Told "move them there instead", the model has to be able to do it. A
    refusal that also locked the move would answer a question with silence.
    """
    ready = wired(searchable)
    ready.call("find_passage", gid=271, description="the meadow with the pond")

    said = ready.call("offer_positions", gid=271, chunk_ids=[place(searchable, 10_000)])
    assert said == "That is one place they have already heard. Move them there instead."
    assert ready.offers == []

    assert ready.call("move_to", gid=271, position_ms=10_000).startswith("Moved to")
    assert [m.seq for m in ready.moves] == [1]


def test_a_move_that_landed_nowhere_leaves_the_turn_free_to_offer(
    searchable: Searchable,
) -> None:
    """A move at a book that is not here is not a move.

    Nothing was written and nobody was taken anywhere, so there is nothing for
    a list to contradict — and the model has just been told the gid was wrong,
    which is exactly when it should be trying something else.
    """
    ready = wired(searchable)
    ready.call("find_passage", gid=271, description="the meadow with the pond")
    assert "no book 999" in ready.call("move_to", gid=999, position_ms=10_000)

    ready.call(
        "offer_positions",
        gid=271,
        chunk_ids=[place(searchable, 10_000), place(searchable, 300_000)],
    )
    assert len(ready.offers) == 1


def test_a_passage_found_answering_one_question_can_be_offered_in_the_next(
    searchable: Searchable,
) -> None:
    """What a search found outlives the question that asked for it.

    They say "no, the other one" a minute later, and the passages are the same
    passages. Clearing the record between turns would make the model search
    again to be allowed to name what it already had.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts_each(
            (
                [SimpleNamespace(content=[text("There's one about the pond.")])],
                [
                    (
                        "find_passage",
                        {"gid": 271, "description": "the meadow with the pond"},
                    )
                ],
            ),
            (
                [SimpleNamespace(content=[])],
                [
                    (
                        "offer_positions",
                        {
                            "gid": 271,
                            "chunk_ids": [
                                place(searchable, 10_000),
                                place(searchable, 300_000),
                            ],
                        },
                    )
                ],
            ),
        ),
    )
    assert conversation.ask("where's the pond bit?").candidates is None
    assert conversation.ask("no, show me where they all are").candidates is not None


def test_the_last_questions_list_does_not_reappear_under_this_answer(
    searchable: Searchable,
) -> None:
    """A list is about one question, and it is over when the next one arrives.

    Left behind, it would come back up over a book that has since been moved
    somewhere else entirely, with rows drawn against a position nobody is at.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts_each(
            (
                [SimpleNamespace(content=[])],
                [
                    (
                        "find_passage",
                        {"gid": 271, "description": "the meadow with the pond"},
                    ),
                    (
                        "offer_positions",
                        {
                            "gid": 271,
                            "chunk_ids": [
                                place(searchable, 10_000),
                                place(searchable, 300_000),
                            ],
                        },
                    ),
                ],
            ),
            ([SimpleNamespace(content=[text("Two hours in.")])], []),
        ),
    )
    assert conversation.ask("the bit by the pond").candidates is not None
    second = conversation.ask("how far am I?")
    assert second.candidates is None
    assert second.reply == "Two hours in."


def test_a_turn_that_offered_twice_shows_only_the_last_list(
    searchable: Searchable,
) -> None:
    """A second list in one turn is a change of mind, and nothing has left yet.

    The same rule as moves, for the same reason: the runner may call a tool
    several times inside one turn, and the page has to end up showing the one
    the sentence belongs to.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts(
            [SimpleNamespace(content=[])],
            calls=[
                (
                    "find_passage",
                    {
                        "gid": 271,
                        "description": "a later scene the listener has not reached",
                    },
                ),
                (
                    "offer_positions",
                    {
                        "gid": 271,
                        "chunk_ids": [
                            place(searchable, 10_000),
                            place(searchable, 300_000),
                        ],
                    },
                ),
                (
                    "offer_positions",
                    {
                        "gid": 271,
                        "chunk_ids": [
                            place(searchable, 10_000),
                            place(searchable, 700_000),
                        ],
                    },
                ),
            ],
        ),
    )
    turn = conversation.ask("where does that happen?")

    assert turn.candidates is not None
    assert [p.start_ms for p in turn.candidates.places] == [10_000, 700_000]


def test_a_silent_turn_that_offered_answers_with_the_sentence_not_with_what_it_did(
    searchable: Searchable,
) -> None:
    """The fallback has two things to choose between, and the list wins.

    A turn can do something worth reporting and then offer — here a move at a
    book that is not there — and the note it left is true but is not what is on
    the screen. There is nothing useful to say beside a list that the list does
    not already say better, so the one sentence that belongs there is used.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts(
            [SimpleNamespace(content=[])],
            calls=[
                (
                    "find_passage",
                    {"gid": 271, "description": "the meadow with the pond"},
                ),
                ("move_to", {"gid": 999, "position_ms": 10_000}),
                (
                    "offer_positions",
                    {
                        "gid": 271,
                        "chunk_ids": [
                            place(searchable, 10_000),
                            place(searchable, 300_000),
                        ],
                    },
                ),
            ],
        ),
    )
    turn = conversation.ask("the bit by the pond")

    assert turn.reply == OFFER_SENTENCE
    assert turn.candidates is not None


def test_a_confident_single_hit_still_just_moves_the_book(
    searchable: Searchable,
) -> None:
    """The list is for ambiguity, and nothing else changed.

    When exactly one passage is plainly the moment they described, the book
    moves and plays and no screen goes up in front of it. Putting a list of one
    obvious answer between them and the book would be the conversation this
    replaced, wearing a different coat.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts(
            [SimpleNamespace(content=[text("You're back by the pond.")])],
            calls=[
                (
                    "find_passage",
                    {"gid": 271, "description": "the meadow with the pond"},
                ),
                ("move_to", {"gid": 271, "position_ms": 10_000}),
            ],
        ),
    )
    turn = conversation.ask("take me back to the pond")

    assert turn.candidates is None
    assert turn.move is not None
    assert (turn.move.position_ms, turn.move.seq) == (10_000, 1)
    assert turn.reply == "You're back by the pond."


def test_a_move_on_the_last_question_does_not_stop_a_list_on_this_one(
    searchable: Searchable,
) -> None:
    """What a turn has already done is about that turn and no other.

    Moving them and then offering a list is refused because the list would be a
    question about where they are now standing. A minute later, when they ask
    something else, it is an ordinary question again — and the flags that said
    otherwise belong to the question that set them.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts_each(
            (
                [SimpleNamespace(content=[text("You're back by the pond.")])],
                [
                    (
                        "find_passage",
                        {"gid": 271, "description": "the meadow with the pond"},
                    ),
                    ("move_to", {"gid": 271, "position_ms": 10_000}),
                ],
            ),
            (
                [SimpleNamespace(content=[])],
                [
                    (
                        "offer_positions",
                        {
                            "gid": 271,
                            "chunk_ids": [
                                place(searchable, 10_000),
                                place(searchable, 300_000),
                            ],
                        },
                    )
                ],
            ),
        ),
    )
    assert conversation.ask("take me back to the pond").move is not None

    second = conversation.ask("no, the other one")
    assert second.candidates is not None
    assert second.move is None


# ------------------------------------------------------------ asking for a book


def test_list_books_names_a_book_that_is_only_waiting_to_be_rendered(
    searchable: Searchable,
) -> None:
    """Otherwise the only true answer to "did that get added?" is "no such book".

    A book asked for tonight has no `books` row until its parse finishes, which
    is behind however many hours of rendering are in front of it. For the whole
    of that time the agent used to say the book was not there — while the queue
    said it was second in line, which is the sort of disagreement between the
    voice and the screen that ends with somebody asking for it twice.
    """
    ready = wired(searchable)

    ready.call("add_book", gid=120)
    listed = ready.call("list_books")

    assert "gid 271" in listed
    assert "waiting to be rendered, 1 in the line" in listed


def test_list_books_says_a_book_being_rendered_is_being_rendered(
    searchable: Searchable,
) -> None:
    """And says which part of it is happening, in the queue's own words.

    A claimed job whose book has no row yet is still fetching and parsing the
    text, which is minutes; the number of chapters it has is not known until
    that finishes, so there is nothing yet to count towards.
    """
    ready = wired(searchable)
    ready.call("add_book", gid=120)
    claim(searchable.conn, lease="somebody", pid=1)

    listed = ready.call("list_books")

    assert "still fetching the text" in listed
