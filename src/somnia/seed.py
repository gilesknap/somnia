"""The one-shot that brings the listener's real position across from ABS.

Everything else in somnia treats Audiobookshelf as write-only. This is the
exception, and it is meant to be run once: before the pivot the position lived
in ABS and nowhere else, so every book somnia has rendered so far has a NULL
``position_ms`` and a high-water mark of zero while the place they had actually
got to — halfway through a book they have been listening to for a fortnight —
sits in a progress record on the other server. Left alone, the first night with
the page as the player opens the most recently *added* book at 0:00, and the
spoiler guard bounds every search at the first minute of a book they are three
chapters into.

It is a module of its own rather than a branch of the ingest or the player
because it belongs to neither: it runs from the command line, by hand, at a
moment when nothing is playing.
"""

import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from .abs import AbsClient
from .format import format_timestamp

__all__ = ["Seed", "seed_positions"]


@dataclass
class Seed:
    """What the seed did to one book.

    ``sentence`` is the whole of it in English, because the only caller is a
    person watching a terminal wanting to know whether it did the right thing
    before they trust the night to it. The numbers are what the row says
    afterwards, not what ABS offered, so a book that was left alone reports the
    position it kept.
    """

    gid: int
    title: str
    position_ms: int | None
    heard_to_ms: int
    changed: bool
    sentence: str


def seed_positions(conn: sqlite3.Connection, abs_client: AbsClient) -> list[Seed]:
    """Take each book's position from Audiobookshelf, once, and never lower one.

    Safe to run twice, and safe to run a year later, because of two rules.
    A position somnia already has is never overwritten: the page is the player,
    so anything in the row is newer than anything ABS can say, and seeding over
    it would drag them back to wherever the ABS app last synced. And the
    high-water mark only ever rises — ``MAX`` — because what ABS knows is real
    listening, from before any of this existed, and can only ever be a floor
    under what they have heard.

    ``position_at`` is taken from the progress record's ``lastUpdate``, not
    from now. It is what orders the launcher, and stamping every book with the
    same second would collapse that ordering onto ``created_at`` — which opens
    the book most recently added rather than the one they were listening to,
    the exact failure this exists to fix.

    A ``currentTime`` of zero is read as never played rather than as the very
    beginning. ABS writes a progress record the moment a book is opened, and a
    book that was opened once and never listened to must not out-rank the one
    they are halfway through.

    Every read happens before any write, so an ABS that goes away part way
    through leaves nothing half done: the run either changes the database or
    fails having changed nothing, and either way running it again is safe. It
    costs one ``/api/me`` per book, which is a handful of requests on something
    that happens once.

    It deliberately does not touch ``position_seq``, so an open page will not
    follow it — and would overwrite it on its next heartbeat. This is run
    before anyone opens the page, not during a night.
    """
    books = conn.execute(
        "SELECT gid, title, abs_item_id, position_ms, heard_to_ms FROM books"
        " ORDER BY created_at"
    ).fetchall()
    progress: dict[int, dict[str, Any] | None] = {
        book["gid"]: abs_client.progress(book["abs_item_id"])
        for book in books
        if book["abs_item_id"]
    }

    seeds: list[Seed] = []
    for book in books:
        gid: int = book["gid"]
        entry = progress.get(gid)
        position_ms = round(float(entry.get("currentTime") or 0) * 1000) if entry else 0
        if entry is None or not position_ms:
            nothing = (
                "never played in Audiobookshelf"
                if book["abs_item_id"]
                else "Audiobookshelf has never seen it"
            )
            seeds.append(
                Seed(
                    gid=gid,
                    title=book["title"],
                    position_ms=book["position_ms"],
                    heard_to_ms=book["heard_to_ms"],
                    changed=False,
                    sentence=nothing,
                )
            )
            continue
        # lastUpdate is epoch milliseconds. It is always there on a record that
        # has a position; the fallback is only so that a stranger ABS cannot
        # turn the run into a traceback, and now is the least wrong guess.
        at_s = int(entry.get("lastUpdate") or time.time() * 1000) // 1000
        with conn:
            row = conn.execute(
                "UPDATE books SET position_ms = COALESCE(position_ms, ?),"
                " position_at = COALESCE(position_at, datetime(?, 'unixepoch')),"
                " heard_to_ms = MAX(heard_to_ms, ?) WHERE gid = ?"
                " RETURNING position_ms, position_at, heard_to_ms",
                (position_ms, at_s, position_ms, gid),
            ).fetchone()
        kept = book["position_ms"] is not None
        raised = row["heard_to_ms"] > book["heard_to_ms"]
        where = (
            f"already at {format_timestamp(row['position_ms'])}, left alone"
            if kept
            else f"seeded at {format_timestamp(row['position_ms'])}"
            f" ({row['position_at']})"
        )
        seeds.append(
            Seed(
                gid=gid,
                title=book["title"],
                position_ms=row["position_ms"],
                heard_to_ms=row["heard_to_ms"],
                changed=not kept or raised,
                sentence=where
                + (
                    f"; heard to {format_timestamp(row['heard_to_ms'])}"
                    if raised
                    else ""
                ),
            )
        )
    return seeds
