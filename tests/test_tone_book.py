"""The tone book has to be true, or everything built on it is quietly wrong.

A player test asks "did the seek land in chapter two?" and believes the answer
the database gives. If the rows and the audio ever disagree — a chapter
regenerated at a different length, a file that failed to copy — every one of
those tests still passes while the player is broken. So the fixture is checked
against the bytes on disk here, once, rather than trusted everywhere else.
"""

from pathlib import Path

from conftest import ToneBook
from mp4 import boxes, duration_ms
from tone_book import CHAPTER_MS, CHAPTERS, GID, TOTAL_MS


def test_every_chapter_row_points_at_audio_that_is_really_there(
    tone_book: ToneBook,
) -> None:
    rows = tone_book.conn.execute(
        "SELECT audio_file FROM chapters WHERE book_gid = ? ORDER BY idx", (GID,)
    ).fetchall()
    assert len(rows) == len(CHAPTERS)
    for row in rows:
        path = Path(row["audio_file"])
        assert path.is_file(), f"{path} is in the database but not on disk"
        assert path.stat().st_size > 0


def test_the_audio_is_as_long_as_the_database_says(tone_book: ToneBook) -> None:
    """The one thing a seek test cannot check for itself."""
    rows = tone_book.conn.execute(
        "SELECT start_ms, end_ms, audio_file FROM chapters WHERE book_gid = ?"
        " ORDER BY idx",
        (GID,),
    ).fetchall()
    for row in rows:
        played = duration_ms(Path(row["audio_file"]))
        assert played == row["end_ms"] - row["start_ms"] == CHAPTER_MS


def test_the_fixtures_have_their_header_where_ingest_puts_it(
    tone_book: ToneBook,
) -> None:
    """A fixture that is not the shape ingest writes tests the wrong file.

    ``somnia.audio.ChapterAudio.encode`` passes ``-movflags +faststart``, which
    moves ``moov`` in front of ``mdat``. Nothing cared while a chapter was only
    ever fetched whole, so the regeneration recipe in :mod:`tone_book` was
    written without it and the committed files came out the other way round.
    Joining chapters into one stream cares: the joined header is the thing the
    phone must have before the first note, and a fixture with it at the end
    would let a stream that costs an extra round trip at 2am look correct here.
    """
    for chapter in CHAPTERS:
        names = [name for name, _, _ in boxes(tone_book.book_dir / chapter.file_name)]
        assert names.index("moov") < names.index("mdat"), chapter.file_name


def test_the_chapters_tile_the_book_without_gaps(tone_book: ToneBook) -> None:
    """A gap between chapters is a place a seek can land and hear nothing."""
    rows = tone_book.conn.execute(
        "SELECT start_ms, end_ms FROM chapters WHERE book_gid = ? ORDER BY idx", (GID,)
    ).fetchall()
    boundaries = [(r["start_ms"], r["end_ms"]) for r in rows]
    assert boundaries[0][0] == 0
    assert boundaries[-1][1] == TOTAL_MS
    assert all(a[1] == b[0] for a, b in zip(boundaries, boundaries[1:], strict=False))

    (total_ms,) = tone_book.conn.execute(
        "SELECT total_ms FROM books WHERE gid = ?", (GID,)
    ).fetchone()
    assert total_ms == TOTAL_MS


def test_the_chapters_do_not_sound_alike(tone_book: ToneBook) -> None:
    """Distinct tones are how a person tells a wrong seek from a right one."""
    contents = {
        (tone_book.book_dir / chapter.file_name).read_bytes() for chapter in CHAPTERS
    }
    assert len(contents) == len(CHAPTERS)
    assert len({chapter.hz for chapter in CHAPTERS}) == len(CHAPTERS)


def test_the_passages_are_findable_by_the_chapter_they_are_in(
    tone_book: ToneBook,
) -> None:
    """Chunks exist for every chapter, so a search can reach the whole book."""
    rows = tone_book.conn.execute(
        "SELECT chapter_idx, COUNT(*) AS n FROM chunks WHERE book_gid = ?"
        " GROUP BY chapter_idx ORDER BY chapter_idx",
        (GID,),
    ).fetchall()
    assert [(r["chapter_idx"], r["n"]) for r in rows] == [(0, 2), (1, 2), (2, 2)]
