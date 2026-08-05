"""What the page is told about a book, before a byte of audio is fetched.

The manifest is the page's whole model of the timeline: get it wrong and every
seek is confidently wrong by a chapter, which sounds like a working player in a
screenshot and like the wrong book through a speaker.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import ToneBook
from somnia.player import Player
from tone_book import CHAPTERS, GID, TOTAL_MS


@pytest.fixture
def player(tone_book: ToneBook) -> Iterator[Player]:
    player = Player(tone_book.cfg)
    try:
        yield player
    finally:
        player.close()


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
