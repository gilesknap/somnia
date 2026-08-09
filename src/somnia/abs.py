"""Minimal Audiobookshelf API client (only what somnia needs)."""

import logging
from typing import Any

import httpx

__all__ = ["AbsClient", "tell_abs"]

logger = logging.getLogger(__name__)


class AbsClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

    def libraries(self) -> list[dict[str, Any]]:
        resp = self._client.get("/api/libraries")
        resp.raise_for_status()
        result: list[dict[str, Any]] = resp.json()["libraries"]
        return result

    def scan_library(self, library_id: str) -> None:
        """Ask ABS to rescan the library folder (picks up newly written chapters)."""
        resp = self._client.post(f"/api/libraries/{library_id}/scan")
        resp.raise_for_status()

    def find_item(self, library_id: str, rel_path: str) -> dict[str, Any] | None:
        """The library item at ``rel_path`` (relative to the library folder)."""
        resp = self._client.get(f"/api/libraries/{library_id}/items")
        resp.raise_for_status()
        items: list[dict[str, Any]] = resp.json()["results"]
        for item in items:
            if item.get("relPath") == rel_path:
                return item
        return None

    def set_chapters(self, item_id: str, chapters: list[dict[str, Any]]) -> None:
        """Replace an item's chapter marks.

        ABS derives chapter marks from the audio files the first time it scans
        an item and never rebuilds them afterwards — not even on a forced scan
        — so a book that grows file by file would keep the chapter list it had
        on day one. somnia knows the real boundaries, so it states them.
        """
        resp = self._client.post(
            f"/api/items/{item_id}/chapters", json={"chapters": chapters}
        )
        resp.raise_for_status()

    def progress(self, item_id: str) -> dict[str, Any] | None:
        """Where the listener is in this book, or None if never played.

        The only read somnia still makes of Audiobookshelf, and it exists for
        :func:`somnia.seed.seed_positions` and nothing else. The page is the
        player and the position is somnia's own, so anything on a listening
        path that asked ABS where the book is would get back whatever it was
        last told as a courtesy — seconds out at best, a whole night out on a
        book played from the page. What it is for is the one thing sqlite
        cannot know: where they had got to before any of this existed.

        ``currentTime`` is seconds on the same global timeline as somnia's
        stored millisecond offsets, because ABS presents a multi-file book as
        one continuous track. ``lastUpdate`` is epoch milliseconds, and is the
        only record of *which* book they were in most recently.
        """
        resp = self._client.get("/api/me")
        resp.raise_for_status()
        entries: list[dict[str, Any]] = resp.json().get("mediaProgress", [])
        for entry in entries:
            if entry.get("libraryItemId") == item_id:
                return entry
        return None

    def set_position(self, item_id: str, time_s: float) -> None:
        """Move the listener to a point in the book.

        This is the same progress record the app writes while you listen, so
        setting it is indistinguishable from having listened up to there: the
        app resumes from this point instead of where it left off. ABS
        recalculates the percentage itself from the item's duration.

        somnia and Audiobookshelf are free to disagree from here on, and
        deliberately so. The page is the player, its position is somnia's own,
        and this is written afterwards as a courtesy — so that a book opened in
        ABS on some other evening starts somewhere near right. A player running
        there will overwrite this within seconds and nothing tries to stop it.
        """
        # A short timeout of its own. This is a courtesy write now — the page is
        # the player, and nothing waits on ABS agreeing — so an ABS that is down
        # rather than absent must not hold a turn, or a reply to a question, for
        # the thirty seconds the client otherwise allows.
        resp = self._client.patch(
            f"/api/me/progress/{item_id}",
            json={"currentTime": round(time_s, 3)},
            timeout=5,
        )
        resp.raise_for_status()


def tell_abs(client: AbsClient | None, item_id: str, position_ms: int) -> None:
    """Say where the book has got to, if there is anywhere to say it.

    Both routes to a position end here — the agent moving the book, and the
    page reporting that it has stopped — because they are one thing: a courtesy
    write to a server nothing is listening to. It is best effort by design and
    never raises. A write that fails costs nothing tonight, and a book somnia
    rendered before ABS last scanned the library has no item to write to at
    all; an empty ``item_id`` is that absence, not an error.

    The caller passes the item id rather than a book id because the two callers
    reach the database differently, and one of them holds a lock it must not
    still be holding while this waits on the network.
    """
    if client is None or not item_id:
        return
    try:
        client.set_position(item_id, position_ms / 1000)
    except Exception:
        logger.warning("ABS position write failed; continuing", exc_info=True)
