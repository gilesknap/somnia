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


class FakeAbs:
    """Audiobookshelf, remembering only what somnia asks of it."""

    def __init__(
        self,
        current_time: float | None = None,
        playing: list[str] | None = None,
        stubborn: int = 0,
    ) -> None:
        self.current_time = current_time
        self.moves: list[tuple[str, float]] = []
        self.sessions = list(playing or [])
        self.closed: list[str] = []
        # A player that re-opens a session and reports its own position back,
        # undoing this many moves before giving up.
        self.stubborn = stubborn

    def progress(self, item_id: str) -> dict[str, Any] | None:
        if self.current_time is None:
            return None
        return {"libraryItemId": item_id, "currentTime": self.current_time}

    def open_sessions(self, item_id: str) -> list[str]:
        return list(self.sessions)

    def close_session(self, session_id: str) -> None:
        self.closed.append(session_id)
        self.sessions.remove(session_id)

    def set_position(self, item_id: str, time_s: float) -> None:
        # A live session would overwrite this the moment it next syncs, so
        # record what the position becomes only once nothing is playing.
        if self.sessions:
            raise AssertionError("wrote a position underneath a live session")
        was = self.current_time
        self.moves.append((item_id, time_s))
        self.current_time = time_s
        if self.stubborn:
            # The player noticed its session close, opened another, and put
            # the book back where it thought it was.
            self.stubborn -= 1
            self.sessions.append(f"reopened-{self.stubborn}")
            self.current_time = was
