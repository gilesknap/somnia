"""The stand-in for the one thing somnia cannot have in a test.

The embedder would load torch and a sentence-transformer model, and more than
one test module needs one.
"""

from typing import Any

import numpy as np

from somnia.db import EMBED_DIM


class FakeEmbedder:
    """Deterministic one-hot vectors, so "nearest" is exactly predictable."""

    def __init__(self) -> None:
        self.axis_of: dict[str, int] = {}
        # How many times a query was embedded, which is the cheap proxy for how
        # many searches were run: one per search, and a search that is thrown
        # away costs the same as one that is read.
        self.queries = 0

    def _vec(self, text: str) -> Any:
        axis = self.axis_of.setdefault(text, len(self.axis_of))
        v = np.zeros(EMBED_DIM, dtype=np.float32)
        v[axis] = 1.0
        return v

    def encode_passages(self, texts: list[str]) -> Any:
        return np.stack([self._vec(t) for t in texts])

    def encode_query(self, text: str) -> Any:
        self.queries += 1
        return self._vec(text)
