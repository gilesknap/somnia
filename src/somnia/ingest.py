"""The streaming ingest pipeline.

Chapters become available to listen to as soon as they are rendered: each
finished chapter is written to the Audiobookshelf library folder, ABS is asked
to rescan, and the chapter's chunks land in the semantic index. Timestamps are
global milliseconds across the whole book (ABS presents multi-file books as a
single timeline), so the index and ABS agree about positions forever.
"""

import logging
import re
import sqlite3
from pathlib import Path

from .abs import AbsClient
from .audio import ChapterAudio
from .config import Config
from .embed import Embedder
from .gutenberg import Chapter, fetch_book
from .index import add_chunks
from .segment import TimedSentence, sentences, windows
from .tts import TTSEngine

__all__ = ["ingest_book"]

logger = logging.getLogger(__name__)


def _safe_name(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^\w \-,.']", "", text).strip()
    return cleaned or fallback


def _render_chapter(
    cfg: Config,
    engine: TTSEngine,
    chapter: Chapter,
    offset_ms: int,
    out_path: Path,
) -> tuple[int, list[TimedSentence]]:
    """Render one chapter to ``out_path``.

    Returns (duration_ms, timed sentences with global timestamps).
    """
    audio = ChapterAudio(engine.sample_rate)
    timed: list[TimedSentence] = []
    for paragraph in chapter.paragraphs:
        for sent in sentences(paragraph):
            start = offset_ms + audio.position_ms
            audio.append(engine.render(sent))
            end = offset_ms + audio.position_ms
            timed.append(TimedSentence(text=sent, start_ms=start, end_ms=end))
            audio.append_silence(cfg.sentence_silence_ms)
        audio.append_silence(cfg.paragraph_silence_ms - cfg.sentence_silence_ms)
    audio.encode(out_path, bitrate=cfg.aac_bitrate)
    return audio.position_ms, timed


def ingest_book(
    cfg: Config,
    conn: sqlite3.Connection,
    engine: TTSEngine,
    embedder: Embedder,
    gid: int,
    abs_client: AbsClient | None = None,
) -> None:
    """Fetch, render, and index a book, streaming chapter by chapter."""
    book = fetch_book(gid)
    row = conn.execute(
        "SELECT authors FROM catalog WHERE gid = ?", (str(gid),)
    ).fetchone()
    authors: str = row["authors"] if row else ""

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO books (gid, title, authors, voice, status)"
            " VALUES (?, ?, ?, ?, 'rendering')",
            (gid, book.title, authors, cfg.voice),
        )

    book_dir = (
        cfg.library_dir
        / _safe_name(authors.split(";")[0], "Unknown Author")
        / _safe_name(book.title, f"gutenberg-{gid}")
    )

    offset_ms = 0
    total = len(book.chapters)
    for idx, chapter in enumerate(book.chapters):
        logger.info("rendering chapter %d/%d: %s", idx + 1, total, chapter.title)
        out_path = (
            book_dir / f"{idx + 1:03d} - {_safe_name(chapter.title, 'chapter')}.m4a"
        )
        duration_ms, timed = _render_chapter(cfg, engine, chapter, offset_ms, out_path)

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

        if abs_client and cfg.abs_library_id:
            try:
                abs_client.scan_library(cfg.abs_library_id)
            except Exception:
                logger.warning("ABS scan trigger failed; continuing", exc_info=True)

    with conn:
        conn.execute("UPDATE books SET status = 'done' WHERE gid = ?", (gid,))
    logger.info(
        "finished %s: %d chapters, %.1f hours", book.title, total, offset_ms / 3.6e6
    )
