"""The tone book has to be true, or everything built on it is quietly wrong.

A player test asks "did the seek land in chapter two?" and believes the answer
the database gives. If the rows and the audio ever disagree — a chapter
regenerated at a different length, a file that failed to copy — every one of
those tests still passes while the player is broken. So the fixture is checked
against the bytes on disk here, once, rather than trusted everywhere else.
"""

import struct
from pathlib import Path

from conftest import ToneBook
from tone_book import CHAPTER_MS, CHAPTERS, GID, TOTAL_MS


def mp4_duration_ms(path: Path) -> int:
    """Read an m4a's duration from its moov/mvhd box, with no ffmpeg to hand.

    ffmpeg makes the fixture but must not be needed to run the suite, so this
    walks the handful of MP4 boxes it takes to reach the one number wanted.
    """
    data = path.read_bytes()

    def find(box: bytes, start: int, end: int) -> tuple[int, int]:
        offset = start
        while offset < end:
            (size,) = struct.unpack(">I", data[offset : offset + 4])
            if data[offset + 4 : offset + 8] == box:
                return offset + 8, offset + size
            offset += size
        raise AssertionError(f"no {box.decode()} box in {path}")

    moov_start, moov_end = find(b"moov", 0, len(data))
    mvhd_start, _ = find(b"mvhd", moov_start, moov_end)
    # Version 0 mvhd: version+flags, created, modified, timescale, duration.
    timescale, duration = struct.unpack(">II", data[mvhd_start + 12 : mvhd_start + 20])
    return round(duration * 1000 / timescale)


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
        played = mp4_duration_ms(Path(row["audio_file"]))
        assert played == row["end_ms"] - row["start_ms"] == CHAPTER_MS


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
