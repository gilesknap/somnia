"""The semantic seek index: store chunk embeddings, search them."""

import sqlite3
from dataclasses import dataclass

from .embed import Embedder
from .segment import Window

__all__ = ["Passage", "add_chunks", "find_passage", "indexed_frontier"]


@dataclass
class Passage:
    chunk_id: int
    chapter_idx: int
    chapter_title: str
    start_ms: int
    end_ms: int
    text: str
    context: str
    distance: float


def add_chunks(
    conn: sqlite3.Connection,
    embedder: Embedder,
    book_gid: int,
    chapter_idx: int,
    chunk_windows: list[Window],
) -> None:
    """Index one chapter's windows: text rows plus their embeddings."""
    if not chunk_windows:
        return
    vectors = embedder.encode_passages([w.text for w in chunk_windows])
    with conn:
        for window, vec in zip(chunk_windows, vectors, strict=True):
            cur = conn.execute(
                "INSERT INTO chunks (book_gid, chapter_idx, start_ms, end_ms, text)"
                " VALUES (?, ?, ?, ?, ?)",
                (book_gid, chapter_idx, window.start_ms, window.end_ms, window.text),
            )
            conn.execute(
                "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                (cur.lastrowid, vec.tobytes()),
            )


def indexed_frontier(conn: sqlite3.Connection, book_gid: int) -> int | None:
    """Highest chapter index rendered so far, or None if nothing yet."""
    row = conn.execute(
        "SELECT MAX(chapter_idx) AS m FROM chunks WHERE book_gid = ?", (book_gid,)
    ).fetchone()
    return row["m"] if row and row["m"] is not None else None


def find_passage(
    conn: sqlite3.Connection,
    embedder: Embedder,
    book_gid: int,
    query: str,
    k: int = 5,
) -> list[Passage]:
    """Semantic search within one book; candidates carry surrounding context."""
    qvec = embedder.encode_query(query)
    rows = conn.execute(
        """
        SELECT c.id, c.chapter_idx, c.start_ms, c.end_ms, c.text, v.distance
        FROM vec_chunks v
        JOIN chunks c ON c.id = v.rowid
        WHERE v.embedding MATCH ? AND v.k = ? AND c.book_gid = ?
        ORDER BY v.distance
        """,
        (qvec.tobytes(), k * 4, book_gid),
    ).fetchmany(k)

    passages: list[Passage] = []
    for r in rows:
        neighbours = conn.execute(
            "SELECT text FROM chunks WHERE book_gid = ? AND id IN (?, ?) ORDER BY id",
            (book_gid, r["id"] - 1, r["id"] + 1),
        ).fetchall()
        context = " […] ".join(n["text"] for n in neighbours)
        chap = conn.execute(
            "SELECT title FROM chapters WHERE book_gid = ? AND idx = ?",
            (book_gid, r["chapter_idx"]),
        ).fetchone()
        passages.append(
            Passage(
                chunk_id=r["id"],
                chapter_idx=r["chapter_idx"],
                chapter_title=chap["title"] if chap else "",
                start_ms=r["start_ms"],
                end_ms=r["end_ms"],
                text=r["text"],
                context=context,
                distance=r["distance"],
            )
        )
    return passages
