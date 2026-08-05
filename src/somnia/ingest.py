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
import time
from pathlib import Path

from .abs import AbsClient
from .audio import ChapterAudio
from .config import Config
from .embed import Embedder
from .gutenberg import Chapter, fetch_book
from .index import add_chunks
from .segment import TimedSentence, sentences, windows
from .tts import TTSEngine

__all__ = ["ingest_book", "publish_chapters"]

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


def publish_chapters(
    cfg: Config,
    conn: sqlite3.Connection,
    abs_client: AbsClient,
    gid: int,
    rel_path: str,
    expect_ms: int,
    timeout_s: float = 30.0,
) -> None:
    """Tell ABS where this book's chapters start, once its scan has caught up.

    The scan ABS runs is asynchronous, so we wait for the item's duration to
    reach the audio we have written before stating the marks — pushing early
    would describe chapters past the end of the file ABS knows about. Every
    push sends the whole list, so a push that times out is repaired by the
    next chapter's.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        item = abs_client.find_item(cfg.abs_library_id, rel_path)
        if item is not None and item["media"]["duration"] * 1000 >= expect_ms - 1000:
            with conn:
                conn.execute(
                    "UPDATE books SET abs_item_id = ? WHERE gid = ?",
                    (item["id"], gid),
                )
            rows = conn.execute(
                "SELECT idx, title, start_ms, end_ms FROM chapters"
                " WHERE book_gid = ? ORDER BY idx",
                (gid,),
            ).fetchall()
            abs_client.set_chapters(
                item["id"],
                [
                    {
                        "id": r["idx"],
                        "start": r["start_ms"] / 1000,
                        "end": r["end_ms"] / 1000,
                        "title": r["title"],
                    }
                    for r in rows
                ],
            )
            return
        if time.monotonic() >= deadline:
            logger.warning(
                "ABS scan did not catch up in %.0fs; marks deferred", timeout_s
            )
            return
        time.sleep(2)


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
                publish_chapters(
                    cfg,
                    conn,
                    abs_client,
                    gid,
                    str(book_dir.relative_to(cfg.library_dir)),
                    offset_ms,
                )
            except Exception:
                logger.warning("ABS update failed; continuing", exc_info=True)

    with conn:
        conn.execute("UPDATE books SET status = 'done' WHERE gid = ?", (gid,))
    logger.info(
        "finished %s: %d chapters, %.1f hours", book.title, total, offset_ms / 3.6e6
    )
