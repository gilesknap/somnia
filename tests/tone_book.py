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
        -c:a aac -b:a 64k -ac 1 -movflags +faststart "001 - The First Tone.m4a"

``+faststart`` is not decoration. It is what ``somnia.audio.ChapterAudio.encode``
passes, so without it these files have their ``moov`` after their ``mdat`` and
are not the shape ingest writes. That made no difference while a chapter was
only ever fetched whole; it makes one now that chapters are joined into a
single stream, because where the header sits decides whether the phone can
start playing on the first response or has to go back for the tail.
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

    The book is seeded with no position at all, which is a book nobody has
    started — so the spoiler guard is shut, since ADR 10 made the position the
    whole of what it reads. A test that wants a listener inside the book puts
    one there, and chapter boundaries are the interesting values.
    """
    book_dir = library_dir / AUTHORS / TITLE
    book_dir.mkdir(parents=True, exist_ok=True)

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO books (gid, title, authors, voice, status,"
            " total_ms) VALUES (?, ?, ?, 'af_heart', 'done', ?)",
            (GID, TITLE, AUTHORS, TOTAL_MS),
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

    # A chapter's passages go in one call, because ``add_chunks`` owns the
    # chapter it is given: it clears what that chapter had before writing what
    # it was handed, which is how a re-render stops adding a second copy of
    # everything. Two calls for chapter one would leave only the second passage.
    for idx in range(len(CHAPTERS)):
        add_chunks(
            conn,
            embedder,
            GID,
            idx,
            [
                Window(text=text, start_ms=start_ms, end_ms=start_ms + 4_000)
                for chapter_idx, text, start_ms in PASSAGES
                if chapter_idx == idx
            ],
        )
    return book_dir
