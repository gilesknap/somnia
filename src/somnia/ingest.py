"""The streaming ingest pipeline.

Chapters become available to listen to as soon as they are rendered: each
finished chapter is written to the library folder and its chunks land in the
semantic index. Timestamps are global milliseconds across the whole book, so a
position means the same thing wherever it is read.
"""

import logging
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path

from .announce import announcement
from .audio import ChapterAudio
from .catalog import text_url
from .config import Config
from .embed import Embedder
from .gutenberg import Chapter, fetch_book
from .index import add_chunks
from .pgau import is_australian
from .segment import TimedSentence, sentences, windows
from .stream import forget_streams
from .tts import TTSEngine

__all__ = ["RenderStopped", "ingest_book"]

logger = logging.getLogger(__name__)


class RenderStopped(Exception):  # noqa: N818
    """Somebody asked for this render to stop, and it did.

    Not an error, which is why it has no Error on the end of it and why the
    naming rule is waived here. It is raised so the stack unwinds to whoever
    started the render and they can say so plainly — a render somebody stopped
    is a thing that worked. It always leaves the book on a chapter boundary,
    which is what makes it safe to raise at all.
    """


def _safe_name(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^\w \-,.']", "", text).strip()
    return cleaned or fallback


def _render_chapter(
    cfg: Config,
    engine: TTSEngine,
    chapter: Chapter,
    offset_ms: int,
    out_path: Path,
    should_stop: Callable[[], bool] | None = None,
    total: int = 0,
) -> tuple[int, list[TimedSentence]]:
    """Render one chapter to ``out_path``.

    Returns (duration_ms, timed sentences with global timestamps).

    The chapter says its own name first — see :mod:`somnia.announce` for what
    that sentence is made of and why it is not the heading verbatim. Three
    things about where it goes.

    It is rendered **before** the first sentence's ``start`` is taken, so every
    timestamp in the book still comes out of ``audio.position_ms`` and is exact
    by construction. Nothing needed adjusting for this; that is the property
    the per-sentence design was for.

    It becomes the first thing at ``chapters.start_ms``, which is what the
    agent moves somebody to. Landing on the words "Chapter twelve" is the
    correct answer to "take me to chapter twelve" — a mark that lands a beat
    *after* the announcement would be the odd one.

    It is deliberately **not** appended to ``timed``, so it never reaches the
    windows or the index. It is not the book's text: indexing it would put the
    same three words at the top of every chapter into a semantic search, and
    hand the spoiler guard sentences no author wrote.

    ``should_stop`` is asked between sentences and nowhere else. A sentence is
    the smallest thing Kokoro will render and takes a second or so, which is why
    a stop can take twenty: it is one interval of whatever the caller does in
    there, plus the sentence in flight. The alternative was a signal, and a
    signal can land anywhere — including the two lines between a chapter's
    passages being indexed and its row being written, which would leave the
    index holding words the player's manifest cannot see, so a place the
    listener chose would send them past the end of their own book.

    Every write this function does is on its last line: the encode. So a stop
    here leaves no m4a, no chunks and no chapters row — nothing at all, which is
    a state a resume already knows how to read.
    """
    audio = ChapterAudio(engine.sample_rate)
    timed: list[TimedSentence] = []
    said = announcement(chapter.title, total)
    if said:
        audio.append(engine.render(said))
        # A paragraph's worth of quiet after it, which is the longest silence
        # this book has anywhere else, so the announcement is heard as a thing
        # apart from the first sentence rather than as its opening clause.
        audio.append_silence(cfg.paragraph_silence_ms)
    for paragraph in chapter.paragraphs:
        for sent in sentences(paragraph):
            if should_stop is not None and should_stop():
                raise RenderStopped(f"stopped during {chapter.title}")
            start = offset_ms + audio.position_ms
            audio.append(engine.render(sent))
            end = offset_ms + audio.position_ms
            timed.append(TimedSentence(text=sent, start_ms=start, end_ms=end))
            audio.append_silence(cfg.sentence_silence_ms)
        audio.append_silence(cfg.paragraph_silence_ms - cfg.sentence_silence_ms)
    audio.encode(out_path, bitrate=cfg.aac_bitrate)
    return audio.position_ms, timed


def _forget_the_old_edition(conn: sqlite3.Connection, gid: int) -> None:
    """Take away everything a previous render of this book wrote to the database.

    Not the audio: the m4a files are numbered by chapter, so re-rendering
    overwrites them one for one, and the only ones left behind are the surplus
    from an edition that got shorter. They are orphans in the library folder
    rather than in the timeline — nothing points at them, and deleting files
    somebody may be listening to right now is a worse thing to be wrong about.
    """
    with conn:
        conn.execute(
            "DELETE FROM vec_chunks WHERE rowid IN"
            " (SELECT id FROM chunks WHERE book_gid = ?)",
            (gid,),
        )
        conn.execute("DELETE FROM chunks WHERE book_gid = ?", (gid,))
        conn.execute("DELETE FROM chapters WHERE book_gid = ?", (gid,))


def _resume_from(conn: sqlite3.Connection, gid: int) -> tuple[int, int]:
    """Where a render of this book should pick up: (chapter index, offset_ms).

    The first chapter with no row, not the one after the highest — a render can
    leave a hole in the middle, and stepping over it would leave that chapter
    silent and unsearchable for good. Everything from the hole onwards is
    rendered again, because the chapters after it sit at offsets computed from a
    duration that is about to change.
    """
    ends = {
        int(r["idx"]): int(r["end_ms"])
        for r in conn.execute(
            "SELECT idx, end_ms FROM chapters WHERE book_gid = ? ORDER BY idx", (gid,)
        )
    }
    start_at = 0
    while start_at in ends:
        start_at += 1
    return start_at, ends[start_at - 1] if start_at else 0


def ingest_book(
    cfg: Config,
    conn: sqlite3.Connection,
    engine: TTSEngine,
    embedder: Embedder,
    gid: int,
    *,
    should_stop: Callable[[], bool] | None = None,
    on_chapter: Callable[[int], None] | None = None,
) -> None:
    """Fetch, render, and index a book, streaming chapter by chapter.

    Rendering a book takes hours, so this can be interrupted and taken up again:
    it starts at the first chapter that has no row and carries the clock on from
    where that one ended. ``should_stop`` is asked between sentences and stops
    the render on the next chapter boundary by raising :class:`RenderStopped`;
    ``on_chapter`` is told each chapter index as its row is written, which is
    the only moment anything outside this process can know a chapter is real.
    Both are optional, and with neither of them this behaves as it always did.
    """
    # A Project Gutenberg Australia book keeps its address in the catalog rather
    # than in its id, so this lookup is what makes it fetchable at all. None is
    # the answer for every Gutenberg book and means "you already know where it
    # is"; if the id says Australia and the catalog has forgotten it, say so
    # here rather than fetching a URL nobody has.
    url = text_url(conn, gid)
    if url is None and is_australian(gid):
        raise RuntimeError(
            f"book {gid} is from Project Gutenberg Australia and the local"
            " catalog has no address for it — run `somnia catalog-update`"
        )
    book = fetch_book(gid, url)
    total = len(book.chapters)
    row = conn.execute(
        "SELECT title, authors FROM catalog WHERE gid = ?", (str(gid),)
    ).fetchone()
    authors: str = row["authors"] if row else ""

    # What the book is called is the catalog's to say, not the file's. The HTML
    # <title> is "The Project Gutenberg eBook of Dracula, by Bram Stoker." for a
    # good part of the corpus, and that is what the shelf used to wear. Stripping
    # that prefix would be a second guess at a string already held correctly one
    # table away — and the catalog's name is also the one that was on screen when
    # somebody pressed for the book, which is the name they are looking for at
    # 2am. The scrape stays as the fallback: it is the only source for anything
    # that did not come through the catalog, and `somnia add` will take a gid the
    # catalog has never heard of.
    #
    # Longer is allowed. 37431's catalog title is longer than its scraped one and
    # correct where the scrape was wrong — it really is Steele Mackaye's play and
    # not Austen's novel. This is about the name being right, not being short.
    title: str = str(row["title"]) if row and row["title"] else book.title

    # Read what we knew about this book before the upsert overwrites it. If the
    # chapter count has moved, Gutenberg has re-issued the text under us and
    # chapter four of one edition is not chapter four of the other: the indices
    # no longer mean the same thing, so splicing the two into one timeline would
    # leave every saved position pointing at the wrong words. Expensive, and the
    # only honest answer. A stored 0 is every book rendered before the column
    # existed, and says nothing either way, so it cannot condemn anything.
    known = conn.execute(
        "SELECT chapters_total FROM books WHERE gid = ?", (gid,)
    ).fetchone()
    stored_total = int(known["chapters_total"]) if known else 0
    if stored_total and stored_total != total:
        logger.warning(
            "book %d now has %d chapters, not %d: rendering it again from the start",
            gid,
            total,
            stored_total,
        )
        _forget_the_old_edition(conn, gid)

    # Upsert, not INSERT OR REPLACE. REPLACE is DELETE followed by INSERT, so
    # re-running a render — which is the normal way to restart one that died —
    # dropped position_ms, position_at, position_seq and heard_to_ms back to
    # their defaults. That was the one way the high-water mark could shrink, and
    # it wedged any page still open: it holds a count the reset row cannot
    # match, so every report it made for the rest of the night was refused.
    # A render knows the title, the authors, the voice, how many chapters the
    # book has and that it is running; it knows nothing about where anybody has
    # got to, so it writes nothing else.
    #
    # The voice comes off the engine and not out of the configuration, because
    # the request may have named one and the configuration is what a submission
    # that named none falls back to. This column is the record of what actually
    # read the book — the one thing a re-render must not disagree with, since
    # every timestamp somnia holds was measured in it.
    #
    # The chapter count goes in here, before a word is rendered, because parsing
    # is minutes and rendering is hours and the number is wanted for all of them:
    # it is the only denominator there is, and without it nothing can tell the
    # end of the book from the end of what has been rendered of it so far.
    with conn:
        conn.execute(
            "INSERT INTO books (gid, title, authors, voice, status, chapters_total)"
            " VALUES (?, ?, ?, ?, 'rendering', ?)"
            " ON CONFLICT(gid) DO UPDATE SET title = excluded.title,"
            " authors = excluded.authors, voice = excluded.voice,"
            " chapters_total = excluded.chapters_total, status = 'rendering'",
            (gid, title, authors, engine.voice, total),
        )

    # The joined files go before a chapter is written over. A stream is named by
    # how many chapters it holds and by nothing else, and `build_stream` serves
    # whatever it finds under that name without looking inside — so a book
    # rendered again in another voice kept playing the old narrator, out of a
    # file whose name had not changed, for as long as the chapter count did not.
    # Chapters are overwritten one for one from here on, so this is the last
    # moment the old joined file is still a truthful copy of anything.
    forget_streams(cfg, gid)

    book_dir = (
        cfg.library_dir
        / _safe_name(authors.split(";")[0], "Unknown Author")
        / _safe_name(title, f"gutenberg-{gid}")
    )

    try:
        start_at, offset_ms = _resume_from(conn, gid)
        if start_at:
            logger.info("resuming %s at chapter %d/%d", title, start_at + 1, total)
        for idx, chapter in enumerate(book.chapters):
            if idx < start_at:
                continue
            logger.info("rendering chapter %d/%d: %s", idx + 1, total, chapter.title)
            out_path = (
                book_dir / f"{idx + 1:03d} - {_safe_name(chapter.title, 'chapter')}.m4a"
            )
            duration_ms, timed = _render_chapter(
                cfg, engine, chapter, offset_ms, out_path, should_stop, total
            )

            chunk_windows = windows(
                timed, size=cfg.window_sentences, stride=cfg.window_stride
            )
            add_chunks(conn, embedder, gid, idx, chunk_windows)
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO chapters"
                    " (book_gid, idx, title, start_ms, end_ms, audio_file)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        gid,
                        idx,
                        chapter.title,
                        offset_ms,
                        offset_ms + duration_ms,
                        str(out_path),
                    ),
                )
                conn.execute(
                    "UPDATE books SET total_ms = ? WHERE gid = ?",
                    (offset_ms + duration_ms, gid),
                )
            offset_ms += duration_ms
            if on_chapter is not None:
                on_chapter(idx)
    except Exception:
        # Whatever went wrong — a stop that was asked for, a box that ran out of
        # memory, sqlite giving up after its five seconds — the one thing that
        # must not survive is a row still claiming a render is going on. Nothing
        # would ever put it right: that is how a book comes to sit on
        # 'rendering' for weeks. 'pending' is the schema's own default, which
        # grep says nothing has ever written, so it is free to mean what it
        # plainly says — not growing, and not finished. The exception goes on up
        # to whoever started the render, where its traceback belongs.
        with conn:
            conn.execute("UPDATE books SET status = 'pending' WHERE gid = ?", (gid,))
        raise

    with conn:
        conn.execute("UPDATE books SET status = 'done' WHERE gid = ?", (gid,))
    logger.info("finished %s: %d chapters, %.1f hours", title, total, offset_ms / 3.6e6)
