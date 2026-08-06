"""A three-chapter book that exists as real audio, for testing the player.

The rendered library lives on the VPS, so a development machine has no m4a
files at all. Anything that actually plays — the PWA, a browser driving it, a
person checking that a seek landed — needs something to point at, and this is
it: three chapters of pure tone. They are committed rather than generated,
because making them needs ffmpeg and a test run should not.

The tones are deliberately distinct, 440, 660 and 880 Hz, an octave apart end
to end. A seek that lands in the wrong chapter is then obvious in the first
instant. That matters more than it sounds: a player that puts them eight
seconds out looks exactly like a working one in a screenshot, and completely
different through a speaker.

Every chapter is exactly 8.000 seconds, so the boundaries are round numbers and
an off-by-one in a manifest has nowhere to hide.

To regenerate the audio, once per tone::

    ffmpeg -f lavfi -i "sine=frequency=440:sample_rate=24000:duration=8" \
        -c:a aac -b:a 64k -ac 1 "001 - The First Tone.m4a"
"""

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from somnia.embed import Embedder
from somnia.index import add_chunks
from somnia.segment import Window

__all__ = ["CHAPTERS", "GID", "TOTAL_MS", "ToneChapter", "build_tone_book"]

# Well outside Gutenberg's range, so a fixture book can never be mistaken for
# one somnia actually rendered.
GID = 900_001
TITLE = "Three Tones"
AUTHORS = "Somnia Test"
CHAPTER_MS = 8_000
TOTAL_MS = 24_000

AUDIO_DIR = Path(__file__).parent / "data" / "tone_book"


@dataclass
class ToneChapter:
    title: str
    file_name: str
    hz: int


# The file names carry spaces, a hyphen and a leading number because that is
# what ingest writes. A player that forgets to encode them fails here, rather
# than on the VPS at 2am.
CHAPTERS = [
    ToneChapter("The First Tone", "001 - The First Tone.m4a", 440),
    ToneChapter("The Second Tone", "002 - The Second Tone.m4a", 660),
    ToneChapter("The Third Tone", "003 - The Third Tone.m4a", 880),
]

# Two passages per chapter, so a seek can be wrong by less than a whole chapter
# and still be caught. The words describe the sound, which means a failing test
# reads as a place in the audio rather than as a row id.
PASSAGES = [
    (0, "the first tone begins, low and steady", 0),
    (0, "the low tone holds to the end of the first chapter", 4_000),
    (1, "the second tone, a fifth above the first", 8_000),
    (1, "the middle tone holds to the end of the second chapter", 12_000),
    (2, "the third tone, an octave above the first", 16_000),
    (2, "the high tone closes the book", 20_000),
]


def build_tone_book(
    conn: sqlite3.Connection,
    library_dir: Path,
    embedder: Embedder,
    *,
    heard_to_ms: int = TOTAL_MS,
) -> Path:
    """Seed the tone book into ``conn``, with its audio under ``library_dir``.

    The audio is copied rather than pointed at where it sits in the repo,
    because ``chapters.audio_file`` holds an absolute path — ingest writes
    ``str(out_path)`` — so those rows are only ever right for one location.
    Copying per test keeps the committed files pristine and lets a test that
    wants to delete a chapter do so without breaking the next one.

    The embedder is the caller's because :class:`fakes.FakeEmbedder` hands out
    an axis per string it has seen: a query only matches a passage if the same
    instance indexed it. Passing one in is what lets a search test find these
    passages at all.

    ``heard_to_ms`` defaults to the whole book: a player test should not have
    to think about the spoiler guard. A test of the guard itself should lower
    it, and chapter boundaries are the interesting values.
    """
    book_dir = library_dir / AUTHORS / TITLE
    book_dir.mkdir(parents=True, exist_ok=True)

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO books (gid, title, authors, voice, status,"
            " total_ms, heard_to_ms) VALUES (?, ?, ?, 'af_heart', 'done', ?, ?)",
            (GID, TITLE, AUTHORS, TOTAL_MS, heard_to_ms),
        )
        for idx, chapter in enumerate(CHAPTERS):
            audio_path = book_dir / chapter.file_name
            shutil.copyfile(AUDIO_DIR / chapter.file_name, audio_path)
            conn.execute(
                "INSERT OR REPLACE INTO chapters (book_gid, idx, title, start_ms,"
                " end_ms, audio_file) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    GID,
                    idx,
                    chapter.title,
                    idx * CHAPTER_MS,
                    (idx + 1) * CHAPTER_MS,
                    str(audio_path),
                ),
            )

    for idx, text, start_ms in PASSAGES:
        add_chunks(
            conn,
            embedder,
            GID,
            idx,
            [Window(text=text, start_ms=start_ms, end_ms=start_ms + 4_000)],
        )
    return book_dir
