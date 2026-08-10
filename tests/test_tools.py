import sqlite3
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from black_beauty import CHAPTERS, build_black_beauty
from fakes import FakeEmbedder
from somnia.config import Config
from somnia.db import connect
from somnia.embed import Embedder
from somnia.index import add_chunks
from somnia.segment import Window
from somnia.tools import (
    CANDIDATE_MAX,
    CANDIDATE_TEXT_CHARS,
    Library,
    Offer,
    Refused,
    format_timestamp,
)


@dataclass
class Fixture:
    """The library under test, plus the seams the tests need to poke."""

    library: Library
    conn: sqlite3.Connection
    # The one that indexed the book, because only it can find those passages
    # again — and because a test that wants a fourth or a fifth place to offer
    # has to index it with the same instance.
    embedder: Embedder


@pytest.fixture
def fixture(tmp_path: Path) -> Iterator[Fixture]:
    conn = connect(tmp_path / "somnia.db")
    try:
        yield _seeded(conn, tmp_path)
    finally:
        conn.close()


def _seeded(conn: sqlite3.Connection, tmp_path: Path) -> Fixture:
    embedder = cast(Embedder, FakeEmbedder())
    build_black_beauty(conn, embedder)
    cfg = Config(data_dir=tmp_path)
    return Fixture(
        library=Library(cfg, conn, embedder),
        conn=conn,
        embedder=embedder,
    )


def test_books_reports_rendered_chapter_count(fixture: Fixture) -> None:
    (book,) = fixture.library.books()
    assert book.title == "Black Beauty"
    assert book.chapters == len(CHAPTERS)


def test_get_position_names_the_chapter_and_the_text_there(fixture: Fixture) -> None:
    position = fixture.library.get_position(271)
    assert position is not None
    assert position.position_ms == 300_000
    assert position.chapter_title == "02 The Hunt"
    assert position.text == "Rob Roy was shot after the hunt"


def test_get_position_is_none_before_they_start(fixture: Fixture) -> None:
    """Nobody is at 0:00:00 — they have not begun, which is a different answer.

    Only a null position can tell the two apart, which is why the column is
    nullable rather than defaulting to zero like everything beside it.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = NULL WHERE gid = 271")
    assert fixture.library.get_position(271) is None


def test_a_book_still_rendering_is_not_called_finished_at_the_frontier(
    fixture: Fixture,
) -> None:
    """total_ms covers only what exists, so catching up is not the ending.

    find_passage switches the spoiler guard off for a finished book. Calling a
    book finished the moment they reach the end of what has been rendered would
    turn the guard off on the one book most able to spoil itself.
    """
    with fixture.conn:
        fixture.conn.execute(
            "UPDATE books SET status = 'rendering', position_ms = 900000"
            " WHERE gid = 271"
        )
    growing = fixture.library.get_position(271)
    assert growing is not None
    assert not growing.finished

    with fixture.conn:
        fixture.conn.execute("UPDATE books SET status = 'done' WHERE gid = 271")
    done = fixture.library.get_position(271)
    assert done is not None
    assert done.finished


def test_find_passage_will_not_search_past_where_they_are(fixture: Fixture) -> None:
    """The late passage is at 700_000ms; the listener is at 300_000ms.

    Nearest-neighbour search has no relevance floor, so the guarantee is not
    "no results" — it is that the unheard passage is never among them.
    """
    query = "a later scene the listener has not reached"
    heard = fixture.library.find_passage(271, query)
    assert 700_000 not in [p.start_ms for p in heard.hits]
    assert heard.searched_to_ms == 360_000

    spoiled = fixture.library.find_passage(271, query, spoiler_free=False)
    assert spoiled.hits[0].start_ms == 700_000
    assert spoiled.searched_to_ms is None


def test_a_book_nobody_has_listened_to_yet_is_bounded_at_its_start(
    fixture: Fixture,
) -> None:
    """No position at all is nothing heard, which is the opposite of no limit.

    A book somnia has rendered and nobody has played has no position, and
    reading that as "search the whole thing" would turn the guard off on
    exactly the books that have never been opened.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = NULL WHERE gid = 271")
    search = fixture.library.find_passage(
        271, "a later scene the listener has not reached"
    )
    assert search.searched_to_ms == 60_000
    assert 700_000 not in [p.start_ms for p in search.hits]
    # And the answer is not silence: what lies ahead is reported, so the agent
    # can offer to take them there instead of saying the book does not have it.
    assert search.better_ahead is not None
    assert search.better_ahead.start_ms == 700_000


def test_a_book_they_have_been_moved_through_is_bounded_where_they_landed(
    fixture: Fixture,
) -> None:
    """Where they were put is where they are, and the guard follows them there.

    This is the half of ADR 10 that gives something up. A move forward really
    does unlock what it skipped over, on the argument that a skip is a
    deliberate act — and the mark that used to hold the line here was paid for
    by stopping dead at the first press of the skip button, which cost every
    question for the rest of the night.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = 700000 WHERE gid = 271")
    search = fixture.library.find_passage(
        271, "a later scene the listener has not reached"
    )
    assert search.searched_to_ms == 760_000
    assert search.hits[0].start_ms == 700_000


def test_a_book_they_have_finished_is_searched_whole(fixture: Fixture) -> None:
    """There is nothing left to spoil once they have heard the end of it."""
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = 900000 WHERE gid = 271")
    search = fixture.library.find_passage(
        271, "a later scene the listener has not reached"
    )
    assert search.searched_to_ms is None
    assert search.hits[0].start_ms == 700_000


def test_find_passage_finds_what_they_have_already_heard(fixture: Fixture) -> None:
    search = fixture.library.find_passage(271, "Rob Roy was shot after the hunt")
    assert search.hits[0].start_ms == 300_000
    assert search.hits[0].chapter_title == "02 The Hunt"
    assert search.better_ahead is None


def test_moving_writes_the_position_the_page_will_read(fixture: Fixture) -> None:
    """Where the book resumes is somnia's own record, and this is what writes it."""
    moved = fixture.library.move_to(271, 300_500)
    row = fixture.conn.execute(
        "SELECT position_ms FROM books WHERE gid = 271"
    ).fetchone()
    assert row["position_ms"] == 300_500
    assert (moved.gid, moved.position_ms) == (271, 300_500)
    assert moved.sentence == "Moved to 0:05:00, and it plays from there."


def test_moving_counts_up_so_the_page_can_tell_it_happened(fixture: Fixture) -> None:
    """The count is how a page tells an agent move from its own heartbeat.

    Its own reports leave the count alone, so a number higher than the one it
    holds can only be a move it has not applied — and it can act on that
    without asking anything else.
    """

    def seq() -> int:
        row = fixture.conn.execute(
            "SELECT position_seq FROM books WHERE gid = 271"
        ).fetchone()
        return int(row["position_seq"])

    assert seq() == 0
    # Handed back as well as written: the page acts on the number it is given,
    # so the two disagreeing would refuse every report it made afterwards.
    assert fixture.library.move_to(271, 10_000).seq == 1
    assert seq() == 1
    assert fixture.library.move_to(271, 20_000).seq == 2
    assert seq() == 2


def test_moving_a_book_that_is_not_here_says_so_rather_than_raising(
    fixture: Fixture,
) -> None:
    """A sentence is more use than a traceback, and no move is no move.

    The count is how the page tells a move from nothing, and it counts up from
    zero on every one that lands — so zero says there is nothing to follow
    without needing a second field to say it.
    """
    moved = fixture.library.move_to(999, 60_000)
    assert moved.seq == 0
    assert "no book 999" in moved.sentence


def test_being_moved_back_narrows_the_guard_and_playing_on_widens_it(
    fixture: Fixture,
) -> None:
    """The price of one number, and the reason it is payable.

    Taking someone back to an earlier passage moves their position backwards,
    and since ADR 10 the position is the guard — so the stretch they had already
    listened to really does go quiet until they play over it again. What makes
    that bearable is the second half of this test: it heals by itself, as fast
    as the book plays. The high-water mark it replaced never healed at all once
    a skip had stopped it.
    """
    fixture.library.move_to(271, 10_000)
    narrowed = fixture.library.find_passage(271, "Rob Roy was shot after the hunt")
    assert narrowed.searched_to_ms == 70_000
    assert 300_000 not in [p.start_ms for p in narrowed.hits]

    fixture.library.move_to(271, 300_000)
    again = fixture.library.find_passage(271, "Rob Roy was shot after the hunt")
    assert again.searched_to_ms == 360_000
    assert again.hits[0].start_ms == 300_000


def test_format_timestamp_reads_as_a_listening_position() -> None:
    assert format_timestamp(0) == "0:00:00"
    assert format_timestamp(8_412_000) == "2:20:12"


def test_find_passage_says_when_the_answer_lies_ahead(fixture: Fixture) -> None:
    search = fixture.library.find_passage(
        271, "a later scene the listener has not reached"
    )
    assert search.better_ahead is not None
    assert search.better_ahead.start_ms == 700_000
    assert 700_000 not in [p.start_ms for p in search.hits]


# --------------------------------------------- answering rather than moving


def test_a_question_is_answered_from_what_they_have_already_heard(
    fixture: Fixture,
) -> None:
    """The same index and the same bound as a search, framed to be spoken.

    A question and a request to be taken somewhere really do look for the same
    passages — there is only one index — so what makes the two different is
    what comes back and what may follow it, not where it was looked up.
    """
    recalled = fixture.library.recall(271, "Rob Roy was shot after the hunt")

    assert [p.start_ms for p in recalled.passages][0] == 300_000
    assert recalled.searched_to_ms == 360_000


def test_a_question_is_never_told_that_a_closer_answer_lies_further_on(
    fixture: Fixture,
) -> None:
    """The nudge that is right for "take me there" and wrong for "who is he".

    A search reports the better match past the mark so it can be offered. There
    is nothing to offer here — they asked to be told something, not moved — and
    saying it lies further on would be a spoiler in its own right: "he hasn't
    come up yet in what you've heard" and "he comes up an hour and a half from
    here" are different sentences, and the second one gives away that he
    arrives at all. So the field is not ignored downstream, it is not there.
    """
    query = "a later scene the listener has not reached"
    assert fixture.library.find_passage(271, query).better_ahead is not None

    recalled = fixture.library.recall(271, query)

    assert 700_000 not in [p.start_ms for p in recalled.passages]
    assert not hasattr(recalled, "better_ahead")


def test_a_question_about_a_book_they_have_finished_may_be_answered_whole(
    fixture: Fixture,
) -> None:
    """There is nothing left to spoil, exactly as there is nothing left to hide.

    The one bound recall has is the search's own, so a book they have heard the
    end of unbounds this the same way it unbounds a search, and the None is how
    the agent is told there is nothing to keep back.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = 900000 WHERE gid = 271")
    recalled = fixture.library.recall(271, "a later scene the listener has not reached")

    assert recalled.searched_to_ms is None
    assert recalled.passages[0].start_ms == 700_000


def test_answering_a_question_changes_nothing_about_the_night(
    fixture: Fixture,
) -> None:
    """A question must cost them nothing at all, the position most of all.

    That is the whole complaint this tool exists to answer — asking who
    somebody was used to end with the book somewhere else — and since ADR 10 it
    is the spoiler guard as well, so a question that nudged the position would
    widen what the next question may be answered from.
    """
    before = night(fixture)
    fixture.library.recall(271, "Rob Roy was shot after the hunt")
    assert night(fixture) == before


# ------------------------------------------- the places they might have meant


def offered(result: Offer | Refused) -> Offer:
    """The offer, or a failure that shows what came back instead."""
    assert isinstance(result, Offer), result
    return result


def refused(result: Offer | Refused) -> str:
    """The refusal's own words, which are what the model is handed."""
    assert isinstance(result, Refused), result
    return result.reason


def chunk_at(fixture: Fixture, start_ms: int) -> int:
    """The id of the passage that begins there — how a search names a place."""
    row = fixture.conn.execute(
        "SELECT id FROM chunks WHERE book_gid = 271 AND start_ms = ?", (start_ms,)
    ).fetchone()
    assert row is not None, f"no passage at {start_ms}"
    return int(row["id"])


def add_passage(fixture: Fixture, chapter_idx: int, text: str, start_ms: int) -> int:
    """Index one more passage into the book, and say what it is called.

    Deliberately not through :func:`somnia.index.add_chunks`, which owns the
    chapter it is handed and clears it first — the thing that stops a re-render
    adding a second copy of every passage. That is the right contract for a
    renderer, which always has a whole chapter's windows, and the wrong one for
    a test that wants a fourth place to offer alongside the three already
    there: it would take the other three away. So this appends, which is what
    it says, and the identity ``chunks.id == vec_chunks.rowid`` is honoured here
    exactly as the real thing honours it.
    """
    (vec,) = fixture.embedder.encode_passages([text])
    with fixture.conn:
        cur = fixture.conn.execute(
            "INSERT INTO chunks (book_gid, chapter_idx, start_ms, end_ms, text)"
            " VALUES (271, ?, ?, ?, ?)",
            (chapter_idx, start_ms, start_ms + 10_000, text),
        )
        fixture.conn.execute(
            "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
            (cur.lastrowid, vec.tobytes()),
        )
    return chunk_at(fixture, start_ms)


def passage_in_another_book(fixture: Fixture) -> int:
    """A second book with one passage in it, to try to smuggle into a list."""
    with fixture.conn:
        fixture.conn.execute(
            "INSERT INTO books (gid, title, voice, status, total_ms)"
            " VALUES (272, 'Another Book', 'af_heart', 'done', 600000)"
        )
    add_chunks(
        fixture.conn,
        fixture.embedder,
        272,
        0,
        [Window(text="a passage from somewhere else", start_ms=5_000, end_ms=15_000)],
    )
    row = fixture.conn.execute("SELECT id FROM chunks WHERE book_gid = 272").fetchone()
    return int(row["id"])


def night(fixture: Fixture) -> dict[str, Any]:
    """Everything about the book a listener could tell had changed."""
    row = fixture.conn.execute(
        "SELECT position_ms, position_seq, position_at FROM books WHERE gid = 271"
    ).fetchone()
    return dict(row)


def test_a_list_of_places_carries_the_books_own_words_for_each(
    fixture: Fixture,
) -> None:
    """A row is the passage that matched, never a description of it.

    A sentence the model wrote about a passage is a sentence about a passage it
    may have misread, and the whole point of showing the list is that they
    recognise the moment themselves. The model ranks; the server writes what
    each row says.
    """
    # A step past the first two passages, so both rows are behind them and this
    # test is about what a row says rather than about what it covers up.
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = 400000 WHERE gid = 271")
    offer = offered(
        fixture.library.offer_positions(
            271, [chunk_at(fixture, 300_000), chunk_at(fixture, 10_000)]
        )
    )

    assert (offer.gid, offer.title, offer.position_ms) == (271, "Black Beauty", 400_000)
    # Named in the model's order, drawn in the book's: a timeline out of order
    # cannot be read at a glance, and a glance is the only way it will be read.
    assert [p.start_ms for p in offer.places] == [10_000, 300_000]
    assert [p.chapter_idx for p in offer.places] == [0, 1]
    assert [p.chapter_title for p in offer.places] == [
        "01 My Early Home",
        "02 The Hunt",
    ]
    assert [p.text for p in offer.places] == [
        "the meadow with the pond",
        "Rob Roy was shot after the hunt",
    ]
    assert [p.ahead for p in offer.places] == [False, False]


def test_the_passage_the_guard_held_back_is_offered_and_marked_ahead(
    fixture: Fixture,
) -> None:
    """The one the list exists for: a closer match past where they have got.

    Its words come down with the list rather than being fetched when they ask
    to see them. A route that handed out the text of any chunk id would be a
    spoiler oracle one guessed integer wide, sitting there for the life of the
    deployment; and it would be asked at 2am, over a link that drops for
    seconds at a time, on the one press where a spinner does the most damage.
    So the words ride inside the answer to the question that already searched
    for them, and covering them up is the page's job.
    """
    search = fixture.library.find_passage(
        271, "a later scene the listener has not reached"
    )
    assert search.better_ahead is not None

    offer = offered(
        fixture.library.offer_positions(
            271, [search.better_ahead.chunk_id, chunk_at(fixture, 10_000)]
        )
    )
    assert [(p.start_ms, p.ahead) for p in offer.places] == [
        (10_000, False),
        (700_000, True),
    ]
    ahead = offer.places[1]
    assert ahead.text == "a later scene the listener has not reached"
    # The chapter heading travels too, and is withheld on the page exactly as
    # the words are: "47 Hard Times" is as much of a spoiler as the sentence
    # under it.
    assert ahead.chapter_title == "47 Hard Times"


def test_a_passage_that_begins_where_they_are_has_not_been_heard_yet(
    fixture: Fixture,
) -> None:
    """``>=`` and not ``>``: the sentence starting where they are is the next one.

    There is no slack either. The search bound is the position plus a minute,
    so a passage inside that minute can be found and is still covered up here —
    strictly tighter than the guard that let it through, which is the safe
    direction and costs one press.
    """
    assert fixture.library.position_ms(271) == 300_000
    offer = offered(
        fixture.library.offer_positions(
            271, [chunk_at(fixture, 10_000), chunk_at(fixture, 300_000)]
        )
    )
    assert [(p.start_ms, p.ahead) for p in offer.places] == [
        (10_000, False),
        (300_000, True),
    ]


def test_a_book_nobody_has_played_covers_up_even_its_opening_words(
    fixture: Fixture,
) -> None:
    """Every book stands at nothing until the page plays one.

    With ``>``, a passage beginning at 0:00:00 would be judged already heard on
    a book nobody has listened to a second of, and its opening words would be
    painted in the clear on the very screen built to cover them.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = NULL WHERE gid = 271")
        fixture.conn.execute(
            "UPDATE chunks SET start_ms = 0 WHERE book_gid = 271 AND start_ms = 10000"
        )
    offer = offered(
        fixture.library.offer_positions(
            271, [chunk_at(fixture, 0), chunk_at(fixture, 300_000)]
        )
    )
    assert [(p.start_ms, p.ahead) for p in offer.places] == [(0, True), (300_000, True)]


def test_one_place_they_have_already_heard_is_a_move_not_a_question(
    fixture: Fixture,
) -> None:
    """A list of one they know is a move with a press in front of it.

    Making somebody half asleep press a button to be taken to the only place on
    offer buys nothing, so the tool sends the model back to move them instead.
    """
    assert refused(
        fixture.library.offer_positions(271, [chunk_at(fixture, 10_000)])
    ) == ("That is one place they have already heard. Move them there instead.")


def test_one_place_they_have_not_heard_is_the_whole_reason_for_the_list(
    fixture: Fixture,
) -> None:
    """Here the press is the point: it is what replaced asking them.

    "Shall I take you there anyway?" was a question read in the dark and
    answered by composing a sentence. This is the same question as a row.
    """
    offer = offered(fixture.library.offer_positions(271, [chunk_at(fixture, 700_000)]))
    assert [(p.start_ms, p.ahead) for p in offer.places] == [(700_000, True)]


def test_a_place_in_another_book_refuses_the_whole_list(fixture: Fixture) -> None:
    """A list is one book's timeline, and half of another's is not a timeline.

    Every row is drawn against one "you are here", and the page seeks in one
    book. A stray row would be measured against the wrong clock entirely.
    """
    alien = passage_in_another_book(fixture)
    assert refused(
        fixture.library.offer_positions(271, [chunk_at(fixture, 10_000), alien])
    ) == (f"Passage {alien} is not in book 271.")


def test_a_place_in_another_book_is_refused_even_when_it_would_not_have_fitted(
    fixture: Fixture,
) -> None:
    """The books are checked over everything it named, before the four are cut.

    Otherwise whether a mixed-up list was caught would depend on where in the
    ranking the stray one landed, which is the sort of rule that holds for a
    year and then does not.
    """
    alien = passage_in_another_book(fixture)
    named = [
        chunk_at(fixture, 10_000),
        chunk_at(fixture, 300_000),
        add_passage(fixture, 0, "one more passage in the meadow", 20_000),
        add_passage(fixture, 0, "another passage in the meadow", 30_000),
        alien,
    ]
    assert refused(fixture.library.offer_positions(271, named)) == (
        f"Passage {alien} is not in book 271."
    )


def test_an_id_that_is_no_passage_at_all_is_refused_rather_than_guessed_at(
    fixture: Fixture,
) -> None:
    """Never resolved to whatever chunk is nearest.

    A near miss would put the book's words on the screen under a time they do
    not belong to, and nothing on the row would say so — which is the one lie
    this list cannot tell. Being sent back to search is recoverable.
    """
    nowhere = "None of those are passages from a search. Search first."
    assert refused(fixture.library.offer_positions(271, [999_999])) == nowhere
    assert refused(fixture.library.offer_positions(271, [])) == nowhere


def test_only_the_four_it_thought_likeliest_go_on_the_screen(
    fixture: Fixture,
) -> None:
    """Four is what somebody half awake can compare without scrolling back.

    Which four is the model's business — it ranked them, and the ones it named
    last are the ones that go. The order it named them in is spent on that cut
    and then thrown away, because the screen wants a timeline.
    """
    named = [
        chunk_at(fixture, 300_000),
        add_passage(fixture, 0, "one more passage in the meadow", 20_000),
        add_passage(fixture, 0, "another passage in the meadow", 21_000),
        add_passage(fixture, 0, "a third passage in the meadow", 22_000),
        add_passage(fixture, 0, "the passage it thought least likely", 23_000),
    ]
    offer = offered(fixture.library.offer_positions(271, named))

    assert len(offer.places) == CANDIDATE_MAX
    assert [p.start_ms for p in offer.places] == [20_000, 21_000, 22_000, 300_000]
    assert named[4] not in [p.chunk_id for p in offer.places]


def test_a_long_passage_is_cut_to_something_a_row_can_hold(fixture: Fixture) -> None:
    """Enough to recognise a moment by, not a page of the book on a menu.

    The ellipsis goes on only where something was really cut, so a row that
    ends in one is telling the truth about there being more, and never at the
    front: on a screen built around withholding things, a leading "…" would
    suggest the beginning had been taken away too.
    """
    whole = " ".join(["the meadow and the pond and the long grass"] * 12)
    long_one = add_passage(fixture, 0, whole, 20_000)
    short_one = chunk_at(fixture, 10_000)
    offer = offered(fixture.library.offer_positions(271, [long_one, short_one]))

    cut = next(p for p in offer.places if p.chunk_id == long_one).text
    assert len(cut) <= CANDIDATE_TEXT_CHARS + 1
    assert cut.endswith("…")
    assert not cut.startswith("…")
    # A whole word, and the book's own words up to that point rather than a
    # paraphrase of them.
    assert whole.startswith(cut[:-1])
    assert whole[len(cut) - 1] == " "
    # And a passage that fits is left exactly as the book has it, with nothing
    # to suggest anything was held back.
    assert next(p for p in offer.places if p.chunk_id == short_one).text == (
        "the meadow with the pond"
    )


def test_a_place_in_a_chapter_with_no_name_is_still_a_place(fixture: Fixture) -> None:
    """An absence, not an error: the row simply reads "Ch 10"."""
    nameless = add_passage(fixture, 9, "somewhere in a chapter with no row", 20_000)
    offer = offered(
        fixture.library.offer_positions(271, [nameless, chunk_at(fixture, 10_000)])
    )
    assert next(p for p in offer.places if p.chunk_id == nameless).chapter_title == ""


def test_the_same_place_named_twice_is_one_row(fixture: Fixture) -> None:
    """Two rows that go to the same second are a question with no answer.

    The two searches behind one of these use different limits and are each
    truncated, so a passage can genuinely come back from both of them.
    """
    here, later = chunk_at(fixture, 10_000), chunk_at(fixture, 300_000)
    offer = offered(fixture.library.offer_positions(271, [here, later, here]))
    assert [p.chunk_id for p in offer.places] == [here, later]


def test_offering_a_book_that_is_not_here_says_so_rather_than_raising(
    fixture: Fixture,
) -> None:
    """A sentence is more use than a traceback, here as everywhere else."""
    assert refused(
        fixture.library.offer_positions(999, [chunk_at(fixture, 10_000)])
    ) == ("There is no book 999 here.")


def test_a_book_they_have_never_started_draws_no_you_are_here(
    fixture: Fixture,
) -> None:
    """Nobody is at 0:00:00, so the row is left off rather than invented.

    The page draws no marker at all instead of putting them at the beginning of
    a book they have not begun, which would be a place they are not.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = NULL WHERE gid = 271")
    offer = offered(
        fixture.library.offer_positions(
            271, [chunk_at(fixture, 10_000), chunk_at(fixture, 300_000)]
        )
    )
    assert offer.position_ms is None


def test_asking_which_place_they_meant_changes_nothing_at_all(
    fixture: Fixture,
) -> None:
    """An offer is a question. Nothing has moved and nothing has been heard.

    ``heard_to_ms`` above all: it rises only from audio that really came out of
    the speaker, and showing somebody a list of places they have not been is
    not having been there. If drawing the list raised it, every list would
    widen the next search past where they had listened, and the guard would
    unwind itself one question at a time — which is the one failure in this
    project that cannot be undone in the morning.
    """
    before = night(fixture)
    offered(
        fixture.library.offer_positions(
            271, [chunk_at(fixture, 10_000), chunk_at(fixture, 700_000)]
        )
    )
    assert night(fixture) == before

    # And a refused one is no different: it writes nothing either, and there is
    # nothing left behind for the next question to trip over.
    refused(fixture.library.offer_positions(271, [chunk_at(fixture, 10_000)]))
    assert night(fixture) == before


def test_a_passage_with_no_word_boundary_to_cut_on_is_still_cut(
    fixture: Fixture,
) -> None:
    """Chunk text comes out of a rendering pipeline, not out of a proof-reader.

    A run of characters longer than a whole row has no space to cut at, and
    handing the row an empty string would say nothing at all — so it is cut
    where it has to be. Something they can recognise the place by beats nothing
    they can read.
    """
    unbroken = "x" * (CANDIDATE_TEXT_CHARS * 2)
    long_one = add_passage(fixture, 0, unbroken, 20_000)
    offer = offered(
        fixture.library.offer_positions(271, [long_one, chunk_at(fixture, 10_000)])
    )

    cut = next(p for p in offer.places if p.chunk_id == long_one).text
    assert cut == "x" * CANDIDATE_TEXT_CHARS + "…"


def test_a_passage_inside_the_searches_own_slack_is_still_covered_up(
    fixture: Fixture,
) -> None:
    """The two guards are not the same number, and this one is the tighter.

    A search runs to the mark plus a minute, so that the sentence being spoken
    counts as heard. A row is covered up at the bare mark. So a passage in that
    minute can be found, offered, and still arrive with its words hidden — the
    safe direction, and it costs one press.
    """
    inside = add_passage(fixture, 1, "a passage inside the minute of slack", 340_000)
    search = fixture.library.find_passage(271, "a passage inside the minute of slack")
    assert inside in [p.chunk_id for p in search.hits]

    offer = offered(
        fixture.library.offer_positions(271, [chunk_at(fixture, 10_000), inside])
    )
    assert [(p.start_ms, p.ahead) for p in offer.places] == [
        (10_000, False),
        (340_000, True),
    ]


def test_a_book_they_have_reached_the_end_of_holds_nothing_back(
    fixture: Fixture,
) -> None:
    """Standing at the end unlocks the book, and that is the deliberate half.

    There used to be a mark here saying otherwise — it rose only over audio
    that really played, so a book skipped to the end still had hours behind it
    that nobody had heard, and those stayed covered. ADR 10 gave that up on the
    grounds it was bought too dear: the same rule stopped the mark at the first
    press of the skip button and left every question for the rest of the night
    answered against a place they had long since passed. Somebody who skipped
    to the end of a book meant to be there.
    """
    with fixture.conn:
        fixture.conn.execute("UPDATE books SET position_ms = 900000 WHERE gid = 271")
    assert fixture.library.find_passage(271, "anything").searched_to_ms is None

    offer = offered(
        fixture.library.offer_positions(
            271, [chunk_at(fixture, 10_000), chunk_at(fixture, 700_000)]
        )
    )
    assert [(p.start_ms, p.ahead) for p in offer.places] == [
        (10_000, False),
        (700_000, False),
    ]


# ------------------------------------------------------------ asking for a book


def test_add_book_puts_it_in_the_queue_and_starts_no_process(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole of what changed: a row, and not a detached renderer.

    It used to spawn `somnia add` with all three of its stdio at /dev/null and
    throw the handle away, so two questions a minute apart gave two Kokoro
    processes on two cores — and the second one halved a margin the whole of
    streaming ingest rests on. There has never been a test of that path, in
    either shape, so the Popen that must not happen is booby-trapped rather
    than merely unasserted.
    """

    def spawns_nothing(*args: object, **kwargs: object) -> None:
        raise AssertionError("add_book must not start a process")

    monkeypatch.setattr(subprocess, "Popen", spawns_nothing)

    said = fixture.library.add_book(120)

    rows = fixture.conn.execute("SELECT gid, state FROM queue").fetchall()
    assert [(r["gid"], r["state"]) for r in rows] == [(120, "queued")]
    assert "next to be rendered" in said


def test_add_book_refuses_a_book_somnia_already_has_all_of(fixture: Fixture) -> None:
    """Black Beauty is rendered, so asking for it again would buy nothing."""
    said = fixture.library.add_book(271)
    assert "already here, all of it" in said
    assert fixture.conn.execute("SELECT COUNT(*) AS n FROM queue").fetchone()["n"] == 0


def test_add_book_refuses_a_book_that_is_already_coming(fixture: Fixture) -> None:
    """Asked twice at 2am, which is exactly how somebody half asleep asks."""
    fixture.library.add_book(120)
    said = fixture.library.add_book(120)
    assert "already in the queue" in said
    assert fixture.conn.execute("SELECT COUNT(*) AS n FROM queue").fetchone()["n"] == 1


def test_a_recall_does_not_pay_for_a_search_it_throws_away(
    fixture: Fixture,
) -> None:
    """`better_ahead` costs a second search of the whole book, and recall drops it.

    Not an optimisation for its own sake: recall drops the field deliberately
    and says why at length — a question must not be followed by a nudge towards
    somewhere further on, because that is a spoiler in itself. So the second
    search was buying something the method exists to refuse to say, on the
    screen where every second of the wait is felt.

    A search is one embedded query, which is what is counted here.
    """
    # The fixture holds it as the protocol, and the counter is the fake's own.
    counting = cast(FakeEmbedder, fixture.embedder)

    counting.queries = 0
    fixture.library.recall(271, "Rob Roy was shot after the hunt")
    assert counting.queries == 1

    # And a move still gets it, because "take me there" is the question the
    # nudge is right for.
    counting.queries = 0
    search = fixture.library.find_passage(271, "Rob Roy was shot after the hunt")
    assert counting.queries == 2
    assert search.searched_to_ms is not None
