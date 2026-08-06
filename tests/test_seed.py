"""The one-shot that brings the real position across from Audiobookshelf.

Every book on the VPS has a NULL position, because the position only became
somnia's own at the pivot. Where they actually are is in ABS, and this is the
only thing left that reads it.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from somnia.abs import AbsClient
from somnia.config import Config
from somnia.db import connect
from somnia.player import Player
from somnia.seed import seed_positions

# Two books added on the same day, and the one they are really listening to is
# not the one added last: that ordering is the whole of the bug.
BEAUTY, CRIME = 271, 2554
LAST_NIGHT = 1_770_000_000_000  # epoch ms, and the later of the two
A_WEEK_AGO = 1_769_400_000_000


class SeedingAbs:
    """Audiobookshelf holding progress for the books it has been played in.

    Only ``progress`` is exercised. ``down_after`` makes it stop answering part
    way through the run, which is the case that has to leave the database
    exactly as it was.
    """

    def __init__(
        self, entries: dict[str, dict[str, Any]], down_after: int | None = None
    ) -> None:
        self._entries = entries
        self._down_after = down_after
        self.asked: list[str] = []

    def progress(self, item_id: str) -> dict[str, Any] | None:
        self.asked.append(item_id)
        if self._down_after is not None and len(self.asked) > self._down_after:
            raise httpx.ConnectError("connection refused")
        return self._entries.get(item_id)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "data" / "somnia.db")
    try:
        yield _seeded(conn)
    finally:
        conn.close()


def _seeded(conn: sqlite3.Connection) -> sqlite3.Connection:
    with conn:
        for gid, title, item_id in (
            (BEAUTY, "Black Beauty", "abs-beauty"),
            (CRIME, "Crime and Punishment", "abs-crime"),
        ):
            conn.execute(
                "INSERT INTO books (gid, title, voice, status, total_ms, abs_item_id)"
                " VALUES (?, ?, 'af_heart', 'done', 40000000, ?)",
                (gid, title, item_id),
            )
    return conn


def _abs(**kwargs: Any) -> AbsClient:
    return cast(AbsClient, SeedingAbs(**kwargs))


def both_books_played() -> dict[str, dict[str, Any]]:
    return {
        "abs-beauty": {"currentTime": 7_863.5, "lastUpdate": A_WEEK_AGO},
        "abs-crime": {"currentTime": 12_030.0, "lastUpdate": LAST_NIGHT},
    }


def row(conn: sqlite3.Connection, gid: int) -> Any:
    return conn.execute("SELECT * FROM books WHERE gid = ?", (gid,)).fetchone()


def test_the_seed_takes_the_position_and_the_mark_from_audiobookshelf(
    conn: sqlite3.Connection,
) -> None:
    """Seconds there, milliseconds here, on the same global timeline.

    The mark comes across with it because ABS's progress is real listening from
    before somnia held a position at all — which is exactly what the spoiler
    guard has no other way of knowing.
    """
    seeds = seed_positions(conn, _abs(entries=both_books_played()))

    assert row(conn, BEAUTY)["position_ms"] == 7_863_500
    assert row(conn, BEAUTY)["heard_to_ms"] == 7_863_500
    assert [s.changed for s in seeds] == [True, True]
    assert "seeded at 2:11:03" in seeds[0].sentence


def test_the_book_that_opens_is_the_one_they_were_last_listening_to(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """The failure this exists to fix, stated as the page would see it.

    A cold launch opens whatever ``position_at`` puts first. Stamping every
    seeded book with the time of the run would make them all equal to the
    second and hand the choice to ``created_at``, which is the book most
    recently added — night one, wrong book, 0:00.
    """
    seed_positions(conn, _abs(entries=both_books_played()))

    player = Player(Config(data_dir=tmp_path / "data"))
    try:
        listing = player.books()
    finally:
        player.close()
    assert listing.last_gid == CRIME
    assert [book.gid for book in listing.books] == [CRIME, BEAUTY]


def test_a_position_somnia_already_holds_is_never_overwritten(
    conn: sqlite3.Connection,
) -> None:
    """The page is the player, so the row is newer than anything ABS can say.

    Seeding over it would take them back to wherever the ABS app last synced,
    which on a book played entirely from the page is a whole night ago.
    """
    with conn:
        conn.execute(
            "UPDATE books SET position_ms = 9000000, position_at = '2026-08-05"
            " 23:40:00' WHERE gid = ?",
            (BEAUTY,),
        )
    seeds = seed_positions(conn, _abs(entries=both_books_played()))

    beauty = row(conn, BEAUTY)
    assert beauty["position_ms"] == 9_000_000
    assert beauty["position_at"] == "2026-08-05 23:40:00"
    # The mark still rises: ABS's number is listening that really happened, so
    # it can only ever be a floor under what they have heard.
    assert beauty["heard_to_ms"] == 7_863_500
    assert "left alone" in seeds[0].sentence


def test_the_seed_never_lowers_the_high_water_mark(conn: sqlite3.Connection) -> None:
    """A mark that could shrink is a book that can spoil itself twice over."""
    with conn:
        conn.execute("UPDATE books SET heard_to_ms = 20000000 WHERE gid = ?", (BEAUTY,))
    seed_positions(conn, _abs(entries=both_books_played()))
    assert row(conn, BEAUTY)["heard_to_ms"] == 20_000_000


def test_running_the_seed_twice_changes_nothing_the_second_time(
    conn: sqlite3.Connection,
) -> None:
    """It will be run again — by hand, at 2am, by someone unsure it worked."""
    seed_positions(conn, _abs(entries=both_books_played()))
    before = dict(row(conn, CRIME))

    again = seed_positions(conn, _abs(entries=both_books_played()))

    assert dict(row(conn, CRIME)) == before
    assert [s.changed for s in again] == [False, False]


def test_a_book_audiobookshelf_cannot_speak_for_is_left_as_it_was(
    conn: sqlite3.Connection,
) -> None:
    """Never scanned there, or scanned and never played: both are an absence.

    A ``currentTime`` of zero counts as never played rather than as the very
    beginning, because ABS writes a progress record the moment a book is
    opened — and a book opened once must not out-rank the one they are halfway
    through when the page asks which to open.
    """
    with conn:
        conn.execute("UPDATE books SET abs_item_id = '' WHERE gid = ?", (BEAUTY,))
    entries: dict[str, dict[str, Any]] = {
        "abs-crime": {"currentTime": 0, "lastUpdate": LAST_NIGHT}
    }

    seeds = seed_positions(conn, _abs(entries=entries))

    assert [s.changed for s in seeds] == [False, False]
    assert row(conn, BEAUTY)["position_ms"] is None
    assert row(conn, CRIME)["position_at"] is None
    assert seeds[0].sentence == "Audiobookshelf has never seen it"
    assert seeds[1].sentence == "never played in Audiobookshelf"


def test_an_audiobookshelf_that_drops_part_way_through_writes_nothing(
    conn: sqlite3.Connection,
) -> None:
    """Every read happens before the first write, so a half-run cannot exist.

    The alternative is a database that got one book and not the other, which
    nobody can tell from a database that got both.
    """
    abs_client = _abs(entries=both_books_played(), down_after=1)

    with pytest.raises(httpx.HTTPError):
        seed_positions(conn, abs_client)

    assert row(conn, BEAUTY)["position_ms"] is None
    assert row(conn, CRIME)["position_ms"] is None
