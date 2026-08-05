"""Minimal Audiobookshelf API client (only what somnia needs)."""

from typing import Any

import httpx

__all__ = ["AbsClient"]


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

    def ping(self) -> bool:
        try:
            return self._client.get("/healthcheck").status_code == 200
        except httpx.HTTPError:
            return False
