"""The whole-book stream: where it is written, and what the list file says.

The build itself is proved through the route, in :mod:`test_server`, because
that is the only place the phone ever meets it. What is here is the pair of
decisions the route cannot show: where a stream is allowed to live, and how a
chapter's name is written down for ffmpeg.
"""

from pathlib import Path

from somnia.config import Config
from somnia.stream import concat_list, forget_streams, stream_path


def test_a_stream_is_named_by_how_much_of_the_book_it_covers(tmp_path: Path) -> None:
    """Two promises in one path, and the second one is ADR 3's.

    A version is a chapter count, so a book that grew while somebody was
    listening gets a new file rather than a rewrite of the one their phone is
    reading — a version rewritten under a playing element is a corrupt read
    mid-sentence.

    And it lives under ``data_dir``. ``library_dir`` is Audiobookshelf's own
    layout, and a second copy of every book appearing in it would be somnia
    breaking the promise that the ABS app keeps working.
    """
    cfg = Config(data_dir=tmp_path / "data", library_dir=tmp_path / "library")
    path = stream_path(cfg, 900_001, 12)

    assert path == cfg.data_dir / "streams" / "900001" / "12.m4a"
    assert stream_path(cfg, 900_001, 13) != path
    assert not path.is_relative_to(cfg.library_dir)


def test_the_list_survives_an_apostrophe_in_a_chapter_title() -> None:
    """``_safe_name`` keeps apostrophes, and the concat list is single-quoted.

    ``008 - 08 Ginger's Story Continued.m4a`` is a real file from the real
    library, and it is where this was found. Written naively the line ends at
    the apostrophe, and ffmpeg looks for a file called ``008 - 08 Ginger``.

    What makes that worth a test of its own rather than a comment: ffmpeg does
    not fail. It prints "Impossible to open", exits 0, and writes a book that
    stops at the bad chapter.
    """
    line = concat_list([Path("/library/008 - 08 Ginger's Story Continued.m4a")])
    assert line == "file '/library/008 - 08 Ginger'\\''s Story Continued.m4a'\n"


def test_every_chapter_gets_a_line_in_the_order_it_is_played() -> None:
    """The list is the timeline: out of order is a book read out of order."""
    files = [Path("/library/001 - One.m4a"), Path("/library/002 - Two.m4a")]
    assert concat_list(files).splitlines() == [
        "file '/library/001 - One.m4a'",
        "file '/library/002 - Two.m4a'",
    ]


def test_a_book_rendered_again_does_not_keep_its_old_joined_file(
    tmp_path: Path,
) -> None:
    """The one thing a chapter count cannot tell you: which voice read it.

    A stream is named by how many chapters it holds and by nothing else, and
    `build_stream` serves whatever it finds under that name without looking
    inside. Render the same book again in another narrator — same chapters,
    same count — and the file the page actually plays is still the old voice,
    for as long as the chapter count does not change. Which is for ever.
    """
    cfg = Config(data_dir=tmp_path)
    old = stream_path(cfg, 271, 3)
    old.parent.mkdir(parents=True)
    old.write_bytes(b"three chapters, read by the old narrator")
    # A second book, to prove this takes away one book's streams and not the
    # whole directory: they share a parent.
    other = stream_path(cfg, 120, 2)
    other.parent.mkdir(parents=True)
    other.write_bytes(b"nothing to do with 271")

    forget_streams(cfg, 271)

    assert not old.exists()
    assert other.exists()


def test_forgetting_the_streams_of_a_book_that_has_none_is_quiet(
    tmp_path: Path,
) -> None:
    """It runs at the top of every render, including a book's first."""
    forget_streams(Config(data_dir=tmp_path), 271)
