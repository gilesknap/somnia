"""The semantic seek index: store chunk embeddings, search them."""

import sqlite3
from dataclasses import dataclass

from .embed import Embedder, Vectors
from .segment import Window

__all__ = ["Passage", "add_chunks", "find_passage"]


@dataclass
class Passage:
    chunk_id: int
    chapter_idx: int
    chapter_title: str
    start_ms: int
    end_ms: int
    text: str
    distance: float


def add_chunks(
    conn: sqlite3.Connection,
    embedder: Embedder,
    book_gid: int,
    chapter_idx: int,
    chunk_windows: list[Window],
) -> None:
    """Index one chapter's windows: text rows plus their embeddings.

    This owns the chapter: when it returns, that chapter's chunks are exactly
    the windows it was handed. It used only to insert, which was fine while a
    chapter was rendered once and never again — but restarting a render that
    died begins at chapter one, so every restart added a second copy of every
    passage it had already indexed. A search then came back with the same words
    twice under two ids, and a list of places to jump to could offer the same
    moment four times, which is an impossible question to put to somebody half
    asleep. So each chapter is cleared before it is written.

    Both deletes, in that order, and in the same transaction as the inserts.
    ``chunks.id`` and ``vec_chunks.rowid`` are the same number by construction —
    that identity is the whole of the join — so dropping one side alone leaves
    either a vector that still matches a search and joins to nothing, or a row
    no search can ever reach. The vectors go first because the rows are what
    say which vectors they were.

    An empty window list is a clearing rather than a no-op. Windowing can
    legitimately come back with nothing — a chapter that is one illustration, a
    parse that now reads the text differently — and leaving yesterday's passages
    in place under today's audio is exactly the sort of quiet wrongness the
    spoiler guard cannot survive. Which is why the encode, the one slow step,
    is what gets skipped instead: the write always happens.

    The encode stays outside the transaction. It is the embedding model, which
    is torch, which is the slowest thing in this process by an order of
    magnitude; holding sqlite's single write lock across it would put the page's
    own writes behind a neural network at 2am.
    """
    texts = [w.text for w in chunk_windows]
    vectors: Vectors | None = embedder.encode_passages(texts) if texts else None
    with conn:
        conn.execute(
            "DELETE FROM vec_chunks WHERE rowid IN"
            " (SELECT id FROM chunks WHERE book_gid = ? AND chapter_idx = ?)",
            (book_gid, chapter_idx),
        )
        conn.execute(
            "DELETE FROM chunks WHERE book_gid = ? AND chapter_idx = ?",
            (book_gid, chapter_idx),
        )
        if vectors is None:
            return
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


def find_passage(
    conn: sqlite3.Connection,
    embedder: Embedder,
    book_gid: int,
    query: str,
    k: int = 5,
    before_ms: int | None = None,
) -> list[Passage]:
    """Semantic search within one book.

    ``before_ms`` restricts the search to passages that start before that point
    in the book — the spoiler guard. Answering "who is Ginger?" from a chapter
    the listener has not reached yet would ruin the thing we are here to
    protect, so questions are answered from what they could have heard.

    Overlapping windows are collapsed to one, best first. :func:`segment.windows`
    cuts three sentences at a stride of two, so consecutive windows *share a
    sentence* by construction — and the sentence they share is exactly the one a
    good query matches hardest. "Where the hare dies" found both windows either
    side of the death in Black Beauty: twelve seconds apart, overlapping by
    thirteen, and the shared sentence was the answer.

    Two rows for one moment is not merely untidy. It is a choice with nothing in
    it, put to somebody half asleep — and worse, it is the arithmetic in
    :meth:`Library.offer_positions` reading two places where the book has one,
    so a goto that should have been a move, made there and then, becomes a list
    and a press. That is the cost ADR 12 exists to have deleted, coming back in
    through the search.

    The best-scoring window of an overlapping run is the one that survives, so
    the place they are taken to is the one the embedder actually chose. It is
    the ordering that does the work: the rows arrive by distance, and a window
    is kept only if it touches nothing already kept.
    """
    qvec = embedder.encode_query(query)
    # sqlite-vec applies its k limit before our filters, so over-fetch: the
    # book filter (and the spoiler cutoff, which can exclude most of a book)
    # both cut into the candidate set.
    fetch_k = k * (16 if before_ms is not None else 4)
    sql = """
        SELECT c.id, c.chapter_idx, c.start_ms, c.end_ms, c.text, v.distance
        FROM vec_chunks v
        JOIN chunks c ON c.id = v.rowid
        WHERE v.embedding MATCH ? AND v.k = ? AND c.book_gid = ?
    """
    params: list[object] = [qvec.tobytes(), fetch_k, book_gid]
    if before_ms is not None:
        sql += " AND c.start_ms <= ?"
        params.append(before_ms)
    # Every candidate, not the first k: the cut has to come after the collapse
    # or a query whose two best hits are one moment answers with k-1 places, and
    # the ones it drops to make room for a duplicate are real ones further down.
    rows = conn.execute(sql + " ORDER BY v.distance", params).fetchall()

    passages: list[Passage] = []
    for r in rows:
        if len(passages) == k:
            break
        # Two windows that share a sentence share the clock as well, which is
        # what makes this exact rather than a threshold somebody has to tune: no
        # milliseconds of grace, no "close enough", just whether the two spans
        # touch. Compared against every passage kept and not only the last,
        # because a long window can swallow two shorter ones after it.
        if any(
            r["start_ms"] < kept.end_ms and kept.start_ms < r["end_ms"]
            for kept in passages
        ):
            continue
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
                distance=r["distance"],
            )
        )
    return passages
