"""The fast lane: the manifest, the audio, and where they are.

Everything here answers in milliseconds off disk, so it gets its own sqlite
connection and its own lock rather than sharing
:class:`somnia.server.Conversations`. A seek at 2am must never queue behind a
twenty-second model turn — a blank player while a question is being answered is
exactly the moment the phone gets put down.

The rows this reads are the ones ingest already writes: ``chapters`` has idx,
title, start_ms, end_ms and audio_file, so the player's manifest is one SELECT.
The only thing it may not hand to the page is ``audio_file`` itself, which is an
absolute path on the VPS. Chapters are addressed by index and resolved here.
"""

import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .db import connect

__all__ = ["BookEntry", "BookList", "Chapter", "Manifest", "Player"]

logger = logging.getLogger(__name__)


@dataclass
class BookEntry:
    """A book as the launcher needs it: enough to name it and to resume it."""

    gid: int
    title: str
    authors: str
    status: str
    total_ms: int
    chapters: int
    position_ms: int | None
    seq: int


@dataclass
class BookList:
    """Every book, most recently listened to first.

    ``last_gid`` is what a cold launch opens. It is None only when nothing has
    ever been played, which is the one time it is fair to ask which book they
    want.
    """

    last_gid: int | None
    books: list[BookEntry]


@dataclass
class Chapter:
    """One chapter of the timeline, and where its audio can be fetched.

    ``start_ms`` and ``end_ms`` are on the book's clock — the render clock,
    counted in PCM samples before encoding — which is the clock that search
    results, ABS chapter marks and the saved position all speak. The page must
    never derive them by summing what the decoder reports, which drifts by tens
    of milliseconds a chapter and is a second out by chapter forty.

    ``url`` is relative because the app may be mounted under a path, and it is
    built here so the page never has to think about encoding a file name like
    ``001 - The First Tone.m4a``.
    """

    idx: int
    title: str
    start_ms: int
    end_ms: int
    url: str


@dataclass
class Manifest:
    """One book, whole: the timeline, the position, and what has been heard.

    Deliberately one round trip. The page needs all of this before it can put a
    finger on the play button, and two fetches at 2am on a tailnet is two
    chances to be left with a player that shows nothing.
    """

    gid: int
    title: str
    authors: str
    status: str
    total_ms: int
    position_ms: int | None
    seq: int
    heard_to_ms: int
    chapters: list[Chapter]


class Player:
    """What the page asks for: which books there are, and the audio of one.

    Its own connection, opened cross-thread because the server's handlers run
    in a threadpool, and its own lock because sqlite connections are not
    thread-safe. Every statement is taken under it; nothing here waits on
    anything but the disk.
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = connect(cfg.db_path, cross_thread=True)

    def close(self) -> None:
        """Give the connection back, so shutdown is not a ResourceWarning."""
        with self._lock:
            self._conn.close()

    def books(self) -> BookList:
        """Every book somnia has, the one they were last listening to first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT b.gid, b.title, b.authors, b.status, b.total_ms,"
                " b.position_ms, b.position_seq, b.position_at,"
                " (SELECT COUNT(*) FROM chapters c WHERE c.book_gid = b.gid)"
                " AS chapters"
                " FROM books b"
                " ORDER BY b.position_at DESC NULLS LAST, b.created_at DESC"
            ).fetchall()
        books = [
            BookEntry(
                gid=row["gid"],
                title=row["title"],
                authors=row["authors"],
                status=row["status"],
                total_ms=row["total_ms"],
                chapters=row["chapters"],
                position_ms=row["position_ms"],
                seq=row["position_seq"],
            )
            for row in rows
        ]
        # Taken from the head of the same ordering rather than from a second
        # query, so the book the page opens can never disagree with the list it
        # is shown — datetime('now') only counts whole seconds, and two books
        # touched in the same second would otherwise be free to differ.
        last_gid = books[0].gid if rows and rows[0]["position_at"] else None
        return BookList(last_gid=last_gid, books=books)

    def manifest(self, gid: int) -> Manifest | None:
        """The whole timeline of one book, or None if there is no such book."""
        with self._lock:
            book = self._conn.execute(
                "SELECT gid, title, authors, status, total_ms, position_ms,"
                " position_seq, heard_to_ms FROM books WHERE gid = ?",
                (gid,),
            ).fetchone()
            if book is None:
                return None
            chapters = self._conn.execute(
                "SELECT idx, title, start_ms, end_ms FROM chapters"
                " WHERE book_gid = ? ORDER BY idx",
                (gid,),
            ).fetchall()
        return Manifest(
            gid=book["gid"],
            title=book["title"],
            authors=book["authors"],
            status=book["status"],
            total_ms=book["total_ms"],
            position_ms=book["position_ms"],
            seq=book["position_seq"],
            heard_to_ms=book["heard_to_ms"],
            chapters=[
                Chapter(
                    idx=row["idx"],
                    title=row["title"],
                    start_ms=row["start_ms"],
                    end_ms=row["end_ms"],
                    url=f"api/audio/{gid}/{row['idx']}",
                )
                for row in chapters
            ],
        )

    def chapter_file(self, gid: int, idx: int) -> Path | None:
        """The audio of one chapter, or None if it cannot honestly be served.

        The caller never names a file: it names a book and a chapter, and the
        path comes from the row. That is the whole of the traversal defence,
        and it has to be, because the server has no auth by design — anything
        that took a path from the request would be a read of the entire VPS.

        Containment is still checked after resolving, because the row is not
        beyond suspicion either: a symlink in the library, or a database
        carried over from a machine whose SOMNIA_LIBRARY_DIR was somewhere
        else, can both point outside. That case is logged rather than silently
        dropped — a library that has moved should be explicable from the
        journal, not guessed at.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT audio_file FROM chapters WHERE book_gid = ? AND idx = ?",
                (gid, idx),
            ).fetchone()
        if row is None:
            return None
        path = Path(row["audio_file"]).resolve()
        # expanduser as well as resolve: Config's default library_dir is the
        # literal "~/library/audiobooks", and only load_config expands it.
        library = self._cfg.library_dir.expanduser().resolve()
        if not path.is_relative_to(library):
            logger.warning("chapter %d/%d lies outside %s: %s", gid, idx, library, path)
            return None
        # A chapter that has been deleted, or has not finished rendering, is an
        # absence rather than a traceback.
        return path if path.is_file() else None
