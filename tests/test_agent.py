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
from somnia.config import Config, load_config
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


def client_recording_system(
    systems: list[str], blocks: list[list[dict[str, Any]]] | None = None
) -> Anthropic:
    """A client that keeps the system prompt it was handed, per turn.

    Recorded twice, because the prompt is two things at once. ``systems`` gets
    the whole of what the model reads, joined back into one string — that is
    what every test about *wording* wants, and none of them should have to know
    the prompt is split for the cache. ``blocks`` gets the split itself, for the
    one test that is about exactly that.
    """

    def tool_runner(**kwargs: Any) -> FakeRunner:
        system = kwargs["system"]
        systems.append("".join(block["text"] for block in system))
        if blocks is not None:
            blocks.append(system)
        return FakeRunner([SimpleNamespace(content=[text("Right you are.")])])

    fake = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner))
    )
    return cast(Anthropic, fake)


def client_recording_calls(calls: list[dict[str, Any]]) -> Anthropic:
    """A client that keeps every argument the runner was built with."""

    def tool_runner(**kwargs: Any) -> FakeRunner:
        calls.append(kwargs)
        return FakeRunner([SimpleNamespace(content=[text("Right you are.")])])

    fake = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner))
    )
    return cast(Anthropic, fake)


def test_the_open_book_is_named_to_the_model_on_every_turn(
    library_with_book: Library,
) -> None:
    """The bug this exists for: three books on the shelf and nothing saying
    which one is making the sound, so the prompt's "ask one short question"
    rule fired every turn and the answer to anything was "which book?".

    On the end of the system prompt and not in the messages, because it is a
    fact about now. A page that opens another book between two questions must
    not leave a sentence in the history that was true of the first one.
    """
    systems: list[str] = []
    conversation = Conversation(
        Config(), library_with_book, client_recording_system(systems)
    )

    conversation.ask("where was I?", 271)
    assert systems[-1].startswith(SYSTEM_PROMPT)
    assert "gid 271: Black Beauty" in systems[-1]

    # Said again on the next turn rather than remembered from the last one.
    conversation.ask("and now?", 271)
    assert "gid 271: Black Beauty" in systems[-1]
    # ...and nowhere in the conversation itself, which is what stops a stale
    # copy of it outliving the book it was about.
    assert all("gid 271" not in str(m.get("content")) for m in conversation.messages)


def test_how_hard_to_think_is_settable_and_reaches_the_model(
    library_with_book: Library,
) -> None:
    """The setting that decides how long a question waits.

    Sonnet thinks before it answers and, left alone, thinks as hard as it can:
    that is where most of a turn goes, and it is the one part of the wait that
    is a dial rather than a fact. It has to arrive with the request to be worth
    anything, so this checks that it does.
    """
    calls: list[dict[str, Any]] = []
    cfg = Config()
    cfg.agent_effort = "low"
    Conversation(cfg, library_with_book, client_recording_calls(calls)).ask("hi", 271)

    assert calls[-1]["output_config"] == {"effort": "low"}


def test_an_effort_level_that_is_not_one_is_ignored_rather_than_obeyed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A typo in a systemd unit must not become a 400 at 2am.

    The value goes straight to the API, which accepts five words and rejects
    everything else — and the rejection would land on the first question of the
    night, as a turn that failed for no visible reason. So it is checked on the
    way up instead, where the answer is a line in the journal and a working
    default.
    """
    monkey = pytest.MonkeyPatch()
    monkey.setenv("SOMNIA_AGENT_EFFORT", "meduim")
    try:
        cfg = load_config()
    finally:
        monkey.undo()

    assert cfg.agent_effort == Config().agent_effort
    assert "meduim" in caplog.text


def test_the_cached_half_of_the_prompt_is_the_half_that_never_changes(
    library_with_book: Library,
) -> None:
    """A prompt cache is a prefix match, so the order is the whole of it.

    The constant prompt goes first with the breakpoint on it, and the line
    naming the open book goes after. Swap them — or put a second breakpoint on
    the volatile line — and the prefix changes every time the book does, which
    is to say it is never read back and the cache silently costs money instead
    of saving it. Nothing about a turn would look wrong; it would just be slow
    again.
    """
    systems: list[str] = []
    blocks: list[list[dict[str, Any]]] = []
    conversation = Conversation(
        Config(), library_with_book, client_recording_system(systems, blocks)
    )

    conversation.ask("where was I?", 271)
    conversation.ask("and this one?", 999)

    for system in blocks:
        assert system[0]["text"] == SYSTEM_PROMPT
        assert system[0]["cache_control"] == {"type": "ephemeral"}
        # Nothing after the breakpoint may be cached: those are the bytes that
        # differ between two books, and a breakpoint there is a cache of one.
        assert all("cache_control" not in block for block in system[1:])

    # And the proof that the split was worth making: the cached block is
    # byte-identical across two turns about two different books.
    assert blocks[0][0]["text"] == blocks[1][0]["text"]
    assert blocks[0][1]["text"] != blocks[1][1]["text"]


def test_a_page_with_no_book_open_says_so_rather_than_leaving_it_out(
    library_with_book: Library,
) -> None:
    """Two different silences. A page that has opened nothing has a question
    worth answering — "what have I got?" — and the model has to be able to tell
    that from a turn where nobody mentioned the book.

    A gid the library has never heard of takes the same path: it is a page
    holding a book that was deleted underneath it, and an invented title would
    be worse than the ambiguity this whole line exists to remove.
    """
    systems: list[str] = []
    conversation = Conversation(
        Config(), library_with_book, client_recording_system(systems)
    )

    conversation.ask("what have I got?")
    assert systems[-1] == SYSTEM_PROMPT + "\n\nThey have no book open."

    conversation.ask("what about this one?", 999)
    assert systems[-1] == SYSTEM_PROMPT + "\n\nThey have no book open."
    assert "999" not in systems[-1]


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


# ----------------------------------------- questions that are not about a place


def test_what_a_recall_hands_back_holds_no_place_to_send_them_to(
    searchable: Searchable,
) -> None:
    """The book's words and the chapter they are in, and no handle at all.

    A chapter is something an answer can say out loud — "that was back in the
    hunt" — where an id and a position_ms are the two things offer_positions and
    move_to consume, and handing them over on a question's tool result is how
    "who is Rob Roy" turned into a jump. The one timestamp in it is the line the
    answer may not cross, not a place: it is there so the model knows how far it
    may speak.
    """
    result = wired(searchable).call(
        "recall", gid=271, question="Rob Roy was shot after the hunt"
    )

    assert "Rob Roy was shot after the hunt" in result
    assert "02 The Hunt" in result
    assert "id=" not in result
    assert "position_ms" not in result
    assert re.findall(r"\d+:\d\d:\d\d", result) == ["0:06:00"]
    assert "as far as they have listened" in result
    assert "300000" not in result


def test_a_recall_says_what_the_answer_is_when_nothing_it_found_is_about_it(
    searchable: Searchable,
) -> None:
    """Nearest-neighbour search has no relevance floor, so it always answers.

    The passages that come back are the closest ones in that stretch, which is
    not the same as passages about what was asked, and the difference is the
    whole of the spoiler case: a character who has not appeared yet has no
    passages, only near misses. So the sentence to say is handed over with them,
    the way the sentence beside a list is — and it stops at "not yet", because
    "he turns up in an hour" is the thing they have not heard.
    """
    result = wired(searchable).call(
        "recall", gid=271, question="somebody who has not appeared yet"
    )

    assert "has not come up yet in what they have heard" in result
    assert "not that it comes up later" in result


def test_a_book_they_have_finished_is_never_answered_with_not_yet(
    searchable: Searchable,
) -> None:
    """The one book where "it hasn't come up yet" is a false sentence.

    Nothing is held back from a recall on a book they have heard the end of, so
    a question it cannot find an answer to is a question the book does not
    answer — and telling somebody who finished Black Beauty last night that
    Ginger has not come up yet is the sort of wrongness they notice at 2am.
    """
    with searchable.conn:
        searchable.conn.execute("UPDATE books SET position_ms = 900000 WHERE gid = 271")

    result = wired(searchable).call("recall", gid=271, question="anybody at all")

    assert "nothing left to keep back" in result
    assert "say you couldn't find it" in result
    assert "not come up yet" not in result


def test_a_turn_that_answered_a_question_will_not_also_move_the_book(
    searchable: Searchable,
) -> None:
    """The refusal the whole split exists for, and the bug it closes.

    Every question used to arrive as a search, every search hands back
    positions, and a position is a thing to move to — so asking who a character
    was ended with the audio dragged to a passage about him and playing, which
    costs the listener the hour they were in. Held here rather than in the
    prompt because the pull is in the shape of the tools, and refused before
    library.move_to writes anything, because a written move reaches the page
    fifteen seconds later whatever the reply said.
    """
    ready = wired(searchable)
    ready.call("recall", gid=271, question="Rob Roy was shot after the hunt")

    said = ready.call("move_to", gid=271, position_ms=10_000)

    assert "not to be moved" in said
    assert ready.moves == []
    assert ready.notes == []
    assert seq(searchable) == 0


def test_a_turn_that_answered_a_question_puts_no_list_of_places_up_either(
    searchable: Searchable,
) -> None:
    """The other half of leaving the book alone, and the more insidious one.

    A character's name matches every passage he appears in, which is exactly
    the condition that used to make a question ambiguous enough to offer — and
    offering gags the reply, so the answer to "who is Rob Roy" became a sentence
    that is not about Rob Roy. A list is an answer to "where do you mean", and
    that is not what was asked.
    """
    ready = wired(searchable)
    ready.call("find_passage", gid=271, description="the meadow with the pond")
    ready.call("recall", gid=271, question="Rob Roy was shot after the hunt")

    said = ready.call(
        "offer_positions",
        gid=271,
        chunk_ids=[place(searchable, 10_000), place(searchable, 300_000)],
    )

    assert "not an answer" in said
    assert ready.offers == []


def test_a_question_about_a_book_that_is_not_here_is_still_a_question(
    searchable: Searchable,
) -> None:
    """The flag is set by the calling, not by what came back.

    A recall that found nothing is the case the refusal matters most in: "it
    hasn't come up yet in what you've heard" is precisely the answer that must
    not be followed by the book moving somewhere instead.
    """
    ready = wired(searchable)
    assert "Nothing in that stretch." in ready.call(
        "recall", gid=999, question="anybody at all"
    )

    assert "not to be moved" in ready.call("move_to", gid=271, position_ms=10_000)
    assert seq(searchable) == 0


def test_a_question_that_tugged_at_the_book_still_leaves_it_where_it_was(
    searchable: Searchable,
) -> None:
    """What the listener gets out of all this: a sentence, and their place.

    The reply survives the refusal — it is the answer, and refusing the move
    must not cost them that too — and the page is handed neither a move nor a
    list, so it draws a bare sentence, which is what it has always done with a
    turn that did neither.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts(
            [SimpleNamespace(content=[text("The horse shot after the hunt.")])],
            calls=[
                ("recall", {"gid": 271, "question": "Rob Roy was shot after the hunt"}),
                ("move_to", {"gid": 271, "position_ms": 300_000}),
            ],
        ),
    )
    turn = conversation.ask("remind me who Rob Roy is")

    assert turn.reply == "The horse shot after the hunt."
    assert turn.move is None
    assert turn.candidates is None
    assert seq(searchable) == 0


def test_a_recall_is_never_used_as_the_answer(searchable: Searchable) -> None:
    """The raw book is not an answer, however far inside the bound it is.

    A recall changes nothing, so it has nothing to report to the fallback, and
    a turn that only read the book and then said nothing says nothing — the
    same rule as a search, for the same reason.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts(
            [SimpleNamespace(content=[])],
            calls=[
                ("recall", {"gid": 271, "question": "Rob Roy was shot after the hunt"})
            ],
        ),
    )
    assert conversation.ask("who is Rob Roy?").reply == ""


def test_a_question_answered_now_does_not_stop_them_being_moved_next(
    searchable: Searchable,
) -> None:
    """Who is Rob Roy, and then: right, take me to where he's shot.

    The flag belongs to the question that set it, like the other two. A turn
    that answered has to leave the next one free to do the ordinary thing, or
    every question would cost the rest of the conversation its ability to move
    the book.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts_each(
            (
                [SimpleNamespace(content=[text("The horse shot after the hunt.")])],
                [
                    (
                        "recall",
                        {"gid": 271, "question": "Rob Roy was shot after the hunt"},
                    )
                ],
            ),
            (
                [SimpleNamespace(content=[text("You're back at the hunt.")])],
                [
                    (
                        "find_passage",
                        {"gid": 271, "description": "Rob Roy was shot after the hunt"},
                    ),
                    ("move_to", {"gid": 271, "position_ms": 300_000}),
                ],
            ),
        ),
    )
    assert conversation.ask("who is Rob Roy?").move is None

    second = conversation.ask("take me to where he's shot")
    assert second.move is not None
    assert second.move.position_ms == 300_000


def test_a_passage_only_a_recall_found_is_not_a_place_it_can_offer(
    searchable: Searchable,
) -> None:
    """Reading the book back hands out no offerable places, in this turn or any.

    A search remembers every passage it returned, so that a list can be proved
    to name real ones. A recall deliberately adds nothing to that record: it
    gave the model no ids, and an id it produced anyway did not come from a
    search. Asked afterwards where somebody turns up, it has to go and look.
    """
    conversation = Conversation(
        Config(),
        searchable.library,
        client_that_acts_each(
            (
                [SimpleNamespace(content=[text("The horse shot after the hunt.")])],
                [
                    (
                        "recall",
                        {"gid": 271, "question": "Rob Roy was shot after the hunt"},
                    )
                ],
            ),
            (
                [SimpleNamespace(content=[text("I couldn't find it.")])],
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
    conversation.ask("who is Rob Roy?")

    assert conversation.ask("show me where he turns up").candidates is None


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
