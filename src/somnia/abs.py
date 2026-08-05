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

    def ping(self) -> bool:
        try:
            return self._client.get("/healthcheck").status_code == 200
        except httpx.HTTPError:
            return False
