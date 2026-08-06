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
from typing import Any, cast

import pytest

from conftest import ToneBook
from fakes import BrokenAbs, RecordingAbs
from somnia.abs import AbsClient
from somnia.player import Player
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


# ------------------------------------------- the courtesy write to Audiobookshelf


def scanned_by_abs(tone_book: ToneBook, item_id: str = "abs-item-1") -> None:
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET abs_item_id = ? WHERE gid = ?", (item_id, GID)
        )


def with_abs(tone_book: ToneBook, fake: Any) -> Player:
    return Player(tone_book.cfg, cast(AbsClient, fake))


def test_audiobookshelf_is_told_where_they_stopped(tone_book: ToneBook) -> None:
    """So the book is in the right place if they ever open ABS somewhere else."""
    scanned_by_abs(tone_book)
    abs_client = RecordingAbs()
    player = with_abs(tone_book, abs_client)
    try:
        player.tell_abs(GID, 12_500)
    finally:
        player.close()
    assert abs_client.moves == [("abs-item-1", 12.5)]


def test_an_audiobookshelf_that_is_down_does_not_break_the_night(
    tone_book: ToneBook,
) -> None:
    """It is a courtesy, off the critical path, and the reply has already gone.

    The whole point of the pivot is that nothing playing depends on ABS being
    there, so a write that fails must cost exactly nothing.
    """
    scanned_by_abs(tone_book)
    player = with_abs(tone_book, BrokenAbs())
    try:
        player.tell_abs(GID, 12_500)  # says nothing, raises nothing
    finally:
        player.close()


def test_a_book_audiobookshelf_has_never_seen_is_simply_not_told(
    tone_book: ToneBook,
) -> None:
    """somnia renders books ABS may never scan, and they must still play."""
    abs_client = RecordingAbs()
    player = with_abs(tone_book, abs_client)
    try:
        player.tell_abs(GID, 12_500)
    finally:
        player.close()
    assert abs_client.moves == []
