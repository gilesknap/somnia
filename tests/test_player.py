"""What the page is told about a book, and what it is allowed to tell back.

The manifest is the page's whole model of the timeline: get it wrong and every
seek is confidently wrong by a chapter, which sounds like a working player in a
screenshot and like the wrong book through a speaker.

The reports going the other way are somnia's only memory of the night, and the
one thing the tests below exist for is the asymmetry between them and an agent
move — a page saying where it has got to must never look like the agent having
sent it there.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import ToneBook
from somnia.player import Player
from somnia.tools import Library, Offer
from tone_book import CHAPTERS, GID, TOTAL_MS


@pytest.fixture
def player(tone_book: ToneBook) -> Iterator[Player]:
    player = Player(tone_book.cfg)
    try:
        yield player
    finally:
        player.close()


def moved_by_the_agent(tone_book: ToneBook, position_ms: int) -> None:
    """What Library.move_to does to the row, without the tool layer.

    The count is what a move is, as far as the page is concerned, so a test of
    the page's side of the protocol only needs this much of one.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET position_ms = ?, position_seq = position_seq + 1,"
            " position_at = datetime('now') WHERE gid = ?",
            (position_ms, GID),
        )


def test_the_manifest_names_every_chapter_and_where_it_starts(player: Player) -> None:
    manifest = player.manifest(GID)
    assert manifest is not None
    assert manifest.title == "Three Tones"
    assert manifest.total_ms == TOTAL_MS
    assert [(c.idx, c.title, c.start_ms) for c in manifest.chapters] == [
        (0, "The First Tone", 0),
        (1, "The Second Tone", 8_000),
        (2, "The Third Tone", 16_000),
    ]
    # A path on the VPS is not a URL, and saying where the library lives is not
    # the page's business either.
    assert [c.url for c in manifest.chapters] == [
        f"api/audio/{GID}/0",
        f"api/audio/{GID}/1",
        f"api/audio/{GID}/2",
    ]


def test_the_manifest_is_a_gapless_partition_of_the_book(player: Player) -> None:
    """A gap is a place a seek lands and hears nothing; an overlap repeats."""
    manifest = player.manifest(GID)
    assert manifest is not None
    chapters = manifest.chapters
    assert chapters[0].start_ms == 0
    assert chapters[-1].end_ms == manifest.total_ms
    assert all(
        a.end_ms == b.start_ms for a, b in zip(chapters, chapters[1:], strict=False)
    )


def test_a_book_never_started_has_no_position_rather_than_a_zero(
    player: Player,
) -> None:
    """The page has to tell "never opened" from "at the very beginning"."""
    manifest = player.manifest(GID)
    assert manifest is not None
    assert manifest.position_ms is None
    assert manifest.seq == 0


def test_a_manifest_is_asked_for_by_gid_and_a_wrong_one_is_not_an_error(
    player: Player,
) -> None:
    assert player.manifest(404_404) is None


def test_the_manifest_says_how_many_chapters_the_book_has(
    player: Player, tone_book: ToneBook
) -> None:
    """The denominator, so the page can tell two different ends apart.

    Running out of audio three chapters into thirty-nine is not the end of the
    book, it is the end of what has been read of it so far, and only a count of
    what the book *has* can tell those apart.

    Zero still means nobody wrote it down, and a page that finds one says
    nothing rather than "chapter 3 of 0" — but a *finished* book no longer sits
    at zero, because `connect` counts its chapters and writes the total the
    first time it is opened. This book is exactly that case: built before the
    column was filled in, done, three chapters on disk.
    """
    fresh = player.manifest(GID)
    assert fresh is not None
    assert fresh.chapters_total == 3

    # And the total is what the book HAS, which the chapters on disk only happen
    # to agree with here. A book whose rows are a fraction of it still says how
    # many it will have.
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET chapters_total = 39 WHERE gid = ?", (GID,)
        )
    counted = player.manifest(GID)
    assert counted is not None
    assert (counted.chapters_total, len(counted.chapters)) == (39, 3)


def test_the_book_list_says_which_one_was_playing_last(
    player: Player, tone_book: ToneBook
) -> None:
    """A cold launch at 2am must not begin by asking which book they meant."""
    listing = player.books()
    assert listing.last_gid is None
    assert [(b.gid, b.title, b.chapters) for b in listing.books] == [
        (GID, "Three Tones", len(CHAPTERS))
    ]

    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET position_ms = 12500, position_seq = 7,"
            " position_at = datetime('now') WHERE gid = ?",
            (GID,),
        )
    listing = player.books()
    assert listing.last_gid == GID
    assert (listing.books[0].position_ms, listing.books[0].seq) == (12_500, 7)


def test_a_listed_book_says_how_many_chapters_it_has_and_when_it_came_in(
    player: Player, tone_book: ToneBook
) -> None:
    """The two columns the Workshop reads, off the row they were always on.

    ``chapters`` is what has been rendered and ``chapters_total`` is what the
    book has, so a coverage line can say `all 3 chapters` here and `read to 3
    of 39` the moment the book turns out to be longer than what is on disk.
    ``created_at`` is when somnia was first asked for the book, which is the
    only date on a shelf row that has nothing to do with where anybody has got
    to — and the one an ordering by how new a book is has to be built on.
    """
    entry = player.books().books[0]
    assert (entry.chapters, entry.chapters_total) == (len(CHAPTERS), len(CHAPTERS))
    assert entry.created_at

    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET chapters_total = 39,"
            " created_at = '2000-01-01 00:00:00' WHERE gid = ?",
            (GID,),
        )
    behind = player.books().books[0]
    assert (behind.chapters, behind.chapters_total) == (len(CHAPTERS), 39)
    assert behind.created_at == "2000-01-01 00:00:00"


# ------------------------------------------------ choosing which book to open


def another_book(tone_book: ToneBook, gid: int, *, rendered: bool = True) -> None:
    """A second book on the shelf, with or without a chapter of audio behind it.

    A row in ``books`` and a row in ``chapters`` are two different facts, and
    the gap between them is a book still waiting on its first chapter — which
    is the one shape opening has to refuse.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "INSERT INTO books (gid, title, voice, status, total_ms)"
            " VALUES (?, 'The Other Book', 'af_heart', 'done', 8000)",
            (gid,),
        )
        if rendered:
            tone_book.conn.execute(
                "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
                " audio_file) VALUES (?, 0, 'Its Only Chapter', 0, 8000, '')",
                (gid,),
            )


def added_first(tone_book: ToneBook, gid: int) -> None:
    """Make this the oldest book on the shelf, whatever order the test added them.

    ``created_at`` is the tie-break under ``position_at`` and is written by
    ``datetime('now')`` too, so two books a test inserts a microsecond apart
    normally carry the same one — and which of two rows equal on every sort key
    comes back first is the sorter's business, not something to assert against.
    Saying which is older aims the tie-break deliberately, so a test about the
    lead ``open_book`` writes cannot be answered by anything else.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET created_at = '2000-01-01 00:00:00' WHERE gid = ?",
            (gid,),
        )


def listening_to(tone_book: ToneBook, gid: int, position_ms: int = 5_000) -> None:
    """What an accepted report leaves behind: a position and a moment."""
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET position_ms = ?, position_at = datetime('now')"
            " WHERE gid = ?",
            (position_ms, gid),
        )


def test_opening_a_book_is_what_makes_it_the_one_a_cold_launch_opens(
    player: Player, tone_book: ToneBook
) -> None:
    """The entire mechanism of switching books, and it writes one column.

    Positions were always per book and ``last_gid`` was always the newest
    ``position_at``, so choosing a book needs no new state at all — only a way
    to say that this is the one they are on now.
    """
    another_book(tone_book, GID + 1)
    listening_to(tone_book, GID)
    assert player.books().last_gid == GID

    opened = player.open_book(GID + 1)
    assert opened is not None
    assert (opened.gid, opened.position_ms, opened.seq) == (GID + 1, None, 0)
    assert player.books().last_gid == GID + 1

    # And back again, because the whole point of per-book positions is that
    # changing your mind costs nothing.
    assert player.open_book(GID) is not None
    assert player.books().last_gid == GID


def test_opening_a_book_leaves_everything_else_about_it_alone(
    player: Player, tone_book: ToneBook
) -> None:
    """Where it is, how much has been heard, and how often it has been moved.

    All three are the reasons this is safe to press in the dark. The position
    is what makes it resume where it was left; the mark is the spoiler guard,
    which nobody has heard any more of by pressing a button; and the count is
    agent moves and nothing else, so a page holding the old one is still in
    step and its next report is still accepted.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET position_ms = 11000, position_seq = 3,"
            " heard_to_ms = 9000 WHERE gid = ?",
            (GID,),
        )
    opened = player.open_book(GID)
    assert opened is not None
    assert (opened.position_ms, opened.seq) == (11_000, 3)

    manifest = player.manifest(GID)
    assert manifest is not None
    assert (manifest.position_ms, manifest.seq, manifest.heard_to_ms) == (
        11_000,
        3,
        9_000,
    )
    # The page opened this book holding seq 3 and has heard nothing since, so
    # the first thing it says has to be taken rather than refused. An open that
    # bumped the count would answer it with a jump to where the book already is.
    assert player.report(GID, 11_500, seq=3, played_ms=500).accepted is True


def test_the_book_left_behind_cannot_take_the_switch_back(
    player: Player, tone_book: ToneBook
) -> None:
    """The parting report is the write this has to beat, and it lands after it.

    Opening another book is the page leaving this one, and the last thing it
    says about the book it is leaving is where it got to — which stamps that
    book's ``position_at`` a millisecond or two after the open. Both are
    written by ``datetime('now')``, which counts whole seconds, so without a
    lead the two are the same second and the tie is broken by which book was
    added first: a reload would open the book they had just left.

    The destination is made the older of the two so that ``created_at`` points
    at the book being left. Without that this passes whether the lead is there
    or not, because both rows are added inside one second and the tie-break has
    nothing to say either.
    """
    another_book(tone_book, GID + 1)
    added_first(tone_book, GID + 1)
    listening_to(tone_book, GID)

    assert player.open_book(GID + 1) is not None
    parting = player.report(GID, 6_000, seq=0, played_ms=1_000)
    assert parting.accepted is True
    assert player.books().last_gid == GID + 1


def test_a_book_with_nothing_to_play_cannot_be_opened(
    player: Player, tone_book: ToneBook
) -> None:
    """A book waiting on its first chapter is not somewhere to be sent.

    It would be the book a cold launch opened, and the next launch would sit
    waiting on a render instead of on the book that was playing — with nothing
    on the screen to say which of the two had happened.
    """
    another_book(tone_book, GID + 1, rendered=False)
    listening_to(tone_book, GID)
    assert player.open_book(GID + 1) is None
    assert player.books().last_gid == GID


def test_opening_a_book_that_is_not_there_is_not_an_error(player: Player) -> None:
    """A page holding a gid from a database that has moved on."""
    assert player.open_book(404_404) is None


def test_a_chapter_is_found_by_its_index_not_by_a_path(
    player: Player, tone_book: ToneBook
) -> None:
    path = player.chapter_file(GID, 1)
    assert path == (tone_book.book_dir / CHAPTERS[1].file_name).resolve()
    assert player.chapter_file(GID, 99) is None
    assert player.chapter_file(404_404, 0) is None


def test_a_chapter_row_pointing_outside_the_library_is_refused(
    player: Player, tone_book: ToneBook, tmp_path: Path
) -> None:
    """The row is not beyond suspicion: a moved library or a symlink can lie."""
    outside = tmp_path / "not-in-the-library.m4a"
    outside.write_bytes(b"\x00")
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE chapters SET audio_file = ? WHERE book_gid = ? AND idx = 0",
            (str(outside), GID),
        )
    assert player.chapter_file(GID, 0) is None


def test_a_chapter_reached_through_a_dotted_path_is_still_refused(
    player: Player, tone_book: ToneBook, tmp_path: Path
) -> None:
    """Containment is checked after resolving, so .. cannot climb out."""
    outside = tmp_path / "climbed-out.m4a"
    outside.write_bytes(b"\x00")
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE chapters SET audio_file = ? WHERE book_gid = ? AND idx = 0",
            (str(tone_book.cfg.library_dir / ".." / outside.name), GID),
        )
    assert player.chapter_file(GID, 0) is None


def test_a_deleted_chapter_file_is_absent_rather_than_an_error(
    player: Player, tone_book: ToneBook
) -> None:
    """Half a book is normal here: the rest is still rendering."""
    (tone_book.book_dir / CHAPTERS[2].file_name).unlink()
    assert player.chapter_file(GID, 2) is None
    assert player.chapter_file(GID, 0) is not None


# -------------------------------------------------- where a sentence began


def test_the_sentence_being_spoken_is_where_a_long_pause_resumes(
    player: Player,
) -> None:
    """Landing mid-clause after an hour asleep is worse than the silence was."""
    assert player.sentence_start(GID, 5_000) == 4_000
    # On a boundary already: there is nothing to snap back to, and pretending
    # otherwise would cost a sentence they had not heard.
    assert player.sentence_start(GID, 4_000) == 4_000


def test_a_sentence_is_looked_for_across_the_book_not_within_one_chapter(
    player: Player,
) -> None:
    """A rewind out of the first seconds of a chapter lands in the one before.

    The page counts in the book's own milliseconds and so does this: which file
    a point falls in is not something either end has to agree about.
    """
    assert player.sentence_start(GID, 7_900) == 4_000
    assert player.sentence_start(GID, 8_100) == 8_000


def test_a_book_with_nothing_indexed_has_no_sentence_to_offer(
    player: Player,
) -> None:
    """The page asked whether it could do better, and the answer is no.

    A book still rendering, or one that is not here at all, both arrive here,
    and neither is a reason to refuse to resume.
    """
    assert player.sentence_start(GID + 1, 5_000) is None
    # Before the first word of the book there is nothing behind them either.
    assert player.sentence_start(GID, -1) is None


# ------------------------------------------- what is being said where they are


def test_the_words_at_a_point_are_the_ones_last_spoken_before_it(
    player: Player,
) -> None:
    """The "you are here" row's words, which no answer carries down for it."""
    assert player.passage_at(GID, 5_000) == (
        "the low tone holds to the end of the first chapter"
    )
    # On a boundary: the passage that starts there is the one being spoken.
    assert player.passage_at(GID, 4_000) == (
        "the low tone holds to the end of the first chapter"
    )


def test_a_point_past_the_mark_is_answered_from_behind_it(
    player: Player, tone_book: ToneBook
) -> None:
    """The bound is on the row, not on the question — see Player.passage_at.

    This is the whole security argument for the route. Ask about a point an hour
    past anything anybody has listened to and the answer is still the last thing
    that was really spoken: there is no id to guess, and no refusal to read a
    frontier off either.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET heard_to_ms = 12000 WHERE gid = ?", (GID,)
        )
    spoken = "the second tone, a fifth above the first"
    assert player.passage_at(GID, TOTAL_MS) == spoken
    # And nothing from beyond it, however the question is put.
    assert player.passage_at(GID, 20_000) == "the second tone, a fifth above the first"


def test_a_passage_beginning_exactly_at_the_mark_has_not_been_spoken(
    player: Player, tone_book: ToneBook
) -> None:
    """`start_ms < heard_to_ms`, which is the guard's own predicate negated.

    A passage that begins where the sound stopped is a passage nobody has heard
    a word of — :class:`somnia.tools.Candidate` calls exactly that one `ahead` —
    and the two ends of somnia must not disagree about a boundary case on the
    one screen that shows both.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET heard_to_ms = 8000 WHERE gid = ?", (GID,)
        )
    assert player.passage_at(GID, 8_000) == (
        "the low tone holds to the end of the first chapter"
    )


def test_a_book_nobody_has_played_has_no_words_to_offer(
    player: Player, tone_book: ToneBook
) -> None:
    """No such book, nothing indexed, and nothing heard all answer the same.

    The row offers no reveal, which is what it did before the route existed.
    """
    assert player.passage_at(GID + 1, 5_000) is None
    assert player.passage_at(GID, -1) is None
    with tone_book.conn:
        tone_book.conn.execute("UPDATE books SET heard_to_ms = 0 WHERE gid = ?", (GID,))
    assert player.passage_at(GID, 5_000) is None


# ------------------------------------------------- what the page reports back


def set_heard(tone_book: ToneBook, heard_to_ms: int) -> None:
    """Wind the high-water mark back; the fixture starts at the whole book."""
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET heard_to_ms = ? WHERE gid = ?", (heard_to_ms, GID)
        )


def heard(tone_book: ToneBook) -> int:
    row = tone_book.conn.execute(
        "SELECT heard_to_ms FROM books WHERE gid = ?", (GID,)
    ).fetchone()
    return int(row["heard_to_ms"])


def reported_since(tone_book: ToneBook, seconds_ago: int) -> None:
    """Say when the last report the server took came in.

    That is the ceiling on how much playback the next report may claim to have
    done since, and a test that runs in a millisecond has no time in it to have
    played anything at all. Writing it is how a night of listening fits inside
    a test.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET position_at = datetime('now', ?) WHERE gid = ?",
            (f"-{seconds_ago} seconds", GID),
        )


def test_a_position_report_is_taken_at_its_word(
    player: Player, tone_book: ToneBook
) -> None:
    report = player.report(GID, 5_000, seq=0, played_ms=0)
    assert (report.accepted, report.position_ms, report.reason) == (True, 5_000, None)

    manifest = player.manifest(GID)
    assert manifest is not None
    assert manifest.position_ms == 5_000


def test_a_book_played_through_raises_the_high_water_mark(
    player: Player, tone_book: ToneBook
) -> None:
    """Nine seconds of book with nine seconds of playback behind it."""
    set_heard(tone_book, 0)
    reported_since(tone_book, 9)
    report = player.report(GID, 9_000, seq=0, played_ms=9_000)
    assert report.heard_to_ms == 9_000
    assert heard(tone_book) == 9_000


def test_a_report_with_no_playback_behind_it_does_not_raise_the_mark(
    player: Player, tone_book: ToneBook
) -> None:
    """A page sitting paused while they ask a question has heard nothing.

    A minute of clock is left between the reports, so what is being tested is
    that time on its own buys nothing: no sound came out of it.
    """
    set_heard(tone_book, 4_000)
    reported_since(tone_book, 60)
    report = player.report(GID, 20_000, seq=0, played_ms=0)
    assert (report.accepted, report.position_ms) == (True, 20_000)
    assert report.heard_to_ms == 4_000
    assert heard(tone_book) == 4_000


def test_the_pause_at_the_end_of_a_stretch_carries_the_mark_with_it(
    player: Player, tone_book: ToneBook
) -> None:
    """A pause is the best evidence in the protocol that they listened to here.

    It is also where the mark would otherwise be left behind. A pause lands up
    to a heartbeat past the last report taken, and a mark a heartbeat behind
    the position refuses everything that comes after it — so reading a pause as
    "they have heard nothing" stopped the guard for the rest of the book on the
    first ordinary pause of the night, which most nights is within a minute.
    """
    set_heard(tone_book, 8_000)
    reported_since(tone_book, 7)
    paused = player.report(GID, 14_500, seq=0, played_ms=6_500)
    assert paused.heard_to_ms == 14_500

    # The press of play that follows stands exactly where the pause did, so it
    # has nothing to prove and claims nothing.
    resumed = player.report(GID, 14_500, seq=0, played_ms=0)
    assert resumed.heard_to_ms == 14_500

    # And the night carries on from there rather than from where it stuck.
    reported_since(tone_book, 9)
    on = player.report(GID, 23_500, seq=0, played_ms=9_000)
    assert on.heard_to_ms == 23_500


def test_a_skip_forward_while_playing_is_not_counted_as_heard(
    player: Player, tone_book: ToneBook
) -> None:
    """One press of +30 used to hand over the whole book.

    Four seconds into the tone book, one second of playback since the last
    report, and this report says twenty seconds: sixteen of them went past with
    no sound behind them, so nobody listened to them.
    """
    set_heard(tone_book, 4_000)
    reported_since(tone_book, 1)
    report = player.report(GID, 20_000, seq=0, played_ms=1_000)
    assert (report.accepted, report.position_ms) == (True, 20_000)
    assert report.heard_to_ms == 4_000
    assert heard(tone_book) == 4_000


def test_the_ticks_after_a_skip_do_not_carry_the_mark_over_it(
    player: Player, tone_book: ToneBook
) -> None:
    """The heartbeats that follow a skip are honest, and still prove nothing.

    Each is a second of listening at a place they were never played to, and the
    hole in front of them does not shrink for being reported across. The mark
    stays behind it rather than stepping over it a minute later. This is the
    whole of what the rule costs: after a skip forward the mark stops, and it
    stops until they go back to where they really were.
    """
    set_heard(tone_book, 4_000)
    reported_since(tone_book, 1)
    player.report(GID, 20_000, seq=0, played_ms=1_000)
    for position_ms in (21_000, 22_000, 23_000):
        reported_since(tone_book, 1)
        player.report(GID, position_ms, seq=0, played_ms=1_000)
    assert heard(tone_book) == 4_000


def test_a_move_the_page_followed_does_not_mark_the_book_between_as_heard(
    player: Player, tone_book: ToneBook
) -> None:
    """Every agent move seeks with the sound on, which is the same hole.

    Being taken to the passage they asked for says nothing about the hours in
    front of it, and the page reporting from there must not claim them.
    """
    set_heard(tone_book, 4_000)
    moved_by_the_agent(tone_book, 20_000)
    reported_since(tone_book, 1)
    report = player.report(GID, 20_000, seq=1, played_ms=1_000)
    assert (report.accepted, report.heard_to_ms) == (True, 4_000)


def test_a_stretch_played_through_off_the_network_still_counts(
    player: Player, tone_book: ToneBook
) -> None:
    """A gap between reports is not a gap in the listening.

    Reports die on a tailnet that is down, and the book plays on regardless.
    The one that gets through afterwards is twenty seconds further on with
    twenty seconds of playback behind it, which is exactly what listening looks
    like — so the mark catches up rather than freezing at the moment the signal
    went. The page owes that playback until a report carrying it is taken,
    which is what makes this possible after four minutes as well as after
    twenty seconds.
    """
    set_heard(tone_book, 0)
    reported_since(tone_book, 20)
    report = player.report(GID, 20_000, seq=0, played_ms=20_000)
    assert report.heard_to_ms == 20_000


def test_a_night_the_phone_slept_through_cannot_be_spent_as_listening(
    player: Player, tone_book: ToneBook
) -> None:
    """Eight hours of clock is not eight hours of listening.

    The last thing a page says before the phone is put down is that the sound
    is on, and then nothing arrives for hours — the tab is frozen, or
    discarded, or simply has nothing to say. Measured off the wall clock, the
    first report after that could cover a move of five hours in full: the guard
    turned itself off overnight with nobody touching it. Measured off playback
    there is nothing to spend, because nothing played.
    """
    set_heard(tone_book, 4_000)
    reported_since(tone_book, 8 * 60 * 60)
    report = player.report(GID, 20_000, seq=0, played_ms=0)
    assert report.heard_to_ms == 4_000
    assert heard(tone_book) == 4_000


def test_a_report_cannot_claim_more_playback_than_there_was_time_for(
    player: Player, tone_book: ToneBook
) -> None:
    """The clock is not the answer any more, but it is still the ceiling.

    A page whose acknowledgement was lost owes that playback again and sends it
    with the next report, which is right and is what stops the mark being left
    behind. Two pages open on the same book would owe each other's, which is
    not. Neither can produce more listening than the interval it happened in.
    """
    set_heard(tone_book, 0)
    reported_since(tone_book, 2)
    report = player.report(GID, 20_000, seq=0, played_ms=20_000)
    assert report.heard_to_ms == 0
    assert heard(tone_book) == 0


def test_a_position_report_never_lowers_the_high_water_mark(
    player: Player, tone_book: ToneBook
) -> None:
    """Being taken back to chapter one must not un-hear chapters two and three."""
    set_heard(tone_book, 20_000)
    reported_since(tone_book, 5)
    report = player.report(GID, 1_000, seq=0, played_ms=5_000)
    assert (report.accepted, report.heard_to_ms) == (True, 20_000)
    assert heard(tone_book) == 20_000


def test_two_reports_in_a_row_from_the_same_page_are_both_accepted(
    player: Player, tone_book: ToneBook
) -> None:
    """The lost-acknowledgement case, and the reason page writes leave seq alone.

    If a report bumped the count, a reply lost on the tailnet would leave the
    page holding a number the server had moved past, and its next heartbeat
    would come back as a refusal carrying its own position from fifteen seconds
    ago — a backwards yank per dropped packet, all night, each one looking
    exactly like the agent doing it.
    """
    first = player.report(GID, 1_000, seq=0, played_ms=0)
    second = player.report(GID, 2_000, seq=0, played_ms=0)
    assert (first.accepted, second.accepted) == (True, True)
    assert (first.seq, second.seq) == (0, 0)


def test_a_position_written_by_a_page_that_missed_a_move_is_refused(
    player: Player, tone_book: ToneBook
) -> None:
    moved_by_the_agent(tone_book, 16_500)
    report = player.report(GID, 3_000, seq=0, played_ms=0)
    assert (report.accepted, report.reason) == (False, "moved")

    manifest = player.manifest(GID)
    assert manifest is not None
    assert manifest.position_ms == 16_500


def test_a_refused_report_carries_the_move_it_missed(
    player: Player, tone_book: ToneBook
) -> None:
    """The refusal is also the instruction: this is where you should be.

    A page that were only told "no" would have to ask, and a page that never
    asked would keep being refused for the rest of the night.
    """
    moved_by_the_agent(tone_book, 16_500)
    report = player.report(GID, 3_000, seq=0, played_ms=0)
    assert (report.position_ms, report.seq) == (16_500, 1)


def test_a_refused_report_leaves_the_high_water_mark_alone(
    player: Player, tone_book: ToneBook
) -> None:
    set_heard(tone_book, 4_000)
    moved_by_the_agent(tone_book, 16_500)
    player.report(GID, 12_000, seq=0, played_ms=0)
    assert heard(tone_book) == 4_000


def test_a_page_that_has_seen_the_move_is_allowed_to_write_again(
    player: Player, tone_book: ToneBook
) -> None:
    """A refusal has to be recoverable, or the move ends the night's writes."""
    moved_by_the_agent(tone_book, 16_500)
    refused = player.report(GID, 3_000, seq=0, played_ms=0)
    assert refused.seq is not None

    caught_up = player.report(GID, 17_000, seq=refused.seq, played_ms=0)
    assert (caught_up.accepted, caught_up.position_ms) == (True, 17_000)


def test_a_report_about_a_book_that_is_gone_says_so(player: Player) -> None:
    """Left open on a deleted book, a page should stop talking about it."""
    report = player.report(404_404, 1_000, seq=0, played_ms=0)
    assert (report.accepted, report.reason) == (False, "gone")
    assert report.position_ms is None


def test_a_list_of_places_neither_raises_the_mark_nor_stops_it_rising(
    player: Player, tone_book: ToneBook
) -> None:
    """Both directions, because only one of them is a fix.

    A list of places they might have meant is a question. Nothing has played
    and nobody has been anywhere, so the mark must not move by a millisecond —
    if it did, every list would widen the next search past what they have
    listened to and the guard would unwind itself one question at a time.

    And a mark that has stopped rising is not a guard, it is a book that can
    never be searched again. So the same night carries on either side of the
    question: nine seconds of listening before it, nine seconds after, and the
    mark steps to both. The two assertions belong in one test because a broken
    guard passes either of them alone.
    """
    library = Library(tone_book.cfg, tone_book.conn, embedder=tone_book.embedder)
    set_heard(tone_book, 0)
    reported_since(tone_book, 9)
    assert player.report(GID, 9_000, seq=0, played_ms=9_000).heard_to_ms == 9_000

    places = [
        int(row["id"])
        for row in tone_book.conn.execute(
            "SELECT id FROM chunks WHERE book_gid = ? AND start_ms IN (4000, 20000)"
            " ORDER BY start_ms",
            (GID,),
        )
    ]
    offer = library.offer_positions(GID, places)
    assert isinstance(offer, Offer), offer
    assert heard(tone_book) == 9_000
    # Nor did it move them, or count anything: the whole of an offer is reads.
    row = tone_book.conn.execute(
        "SELECT position_ms, position_seq FROM books WHERE gid = ?", (GID,)
    ).fetchone()
    assert (row["position_ms"], row["position_seq"]) == (9_000, 0)

    reported_since(tone_book, 9)
    assert player.report(GID, 18_000, seq=0, played_ms=9_000).heard_to_ms == 18_000
    assert heard(tone_book) == 18_000
