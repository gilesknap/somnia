"""Stand-ins for the two things somnia cannot have in a test.

The embedder would load torch and a sentence-transformer model; Audiobookshelf
would be a server. Both are shared by more than one test module.
"""

from typing import Any

import numpy as np

from somnia.db import EMBED_DIM


class FakeEmbedder:
    """Deterministic one-hot vectors, so "nearest" is exactly predictable."""

    def __init__(self) -> None:
        self.axis_of: dict[str, int] = {}

    def _vec(self, text: str) -> Any:
        axis = self.axis_of.setdefault(text, len(self.axis_of))
        v = np.zeros(EMBED_DIM, dtype=np.float32)
        v[axis] = 1.0
        return v

    def encode_passages(self, texts: list[str]) -> Any:
        return np.stack([self._vec(t) for t in texts])

    def encode_query(self, text: str) -> Any:
        return self._vec(text)


class RecordingAbs:
    """Audiobookshelf as the player now uses it: written to, never read."""

    def __init__(self) -> None:
        self.moves: list[tuple[str, float]] = []

    def set_position(self, item_id: str, time_s: float) -> None:
        self.moves.append((item_id, time_s))


class BrokenAbs:
    """An Audiobookshelf that is down, or behind a tailnet that just dropped."""

    def set_position(self, item_id: str, time_s: float) -> None:
        raise RuntimeError("connection refused")


class FakeAbs:
    """Audiobookshelf, remembering only what somnia asks of it.

    It used to model a player fighting somnia for the position — sessions to
    close, a position put back the moment it was written. Nothing plays the book
    there any more, so all that is left is a record of what it was told.
    """

    def __init__(self, current_time: float | None = None) -> None:
        self.current_time = current_time
        self.moves: list[tuple[str, float]] = []

    def progress(self, item_id: str) -> dict[str, Any] | None:
        if self.current_time is None:
            return None
        return {"libraryItemId": item_id, "currentTime": self.current_time}

    def set_position(self, item_id: str, time_s: float) -> None:
        self.moves.append((item_id, time_s))
        self.current_time = time_s
