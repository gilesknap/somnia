"""Sentence embeddings for semantic seek.

e5 models are asymmetric: conversational queries ("where the horse dies") and
narrative passages get different prefixes, which measurably improves matching.
"""

from typing import Any

import numpy as np
import numpy.typing as npt

from .db import EMBED_DIM

__all__ = ["Embedder"]

Vectors = npt.NDArray[np.float32]


class Embedder:
    def __init__(self, model_name: str = "intfloat/e5-small-v2") -> None:
        import sentence_transformers  # noqa: PLC0415

        st: Any = sentence_transformers
        self._model: Any = st.SentenceTransformer(model_name)
        dim: Any = self._model.get_sentence_embedding_dimension()
        if dim != EMBED_DIM:
            raise ValueError(f"model {model_name} has dim {dim}, expected {EMBED_DIM}")

    def encode_passages(self, texts: list[str]) -> Vectors:
        prefixed = [f"passage: {t}" for t in texts]
        return np.asarray(
            self._model.encode(prefixed, normalize_embeddings=True), dtype=np.float32
        )

    def encode_query(self, text: str) -> Vectors:
        return np.asarray(
            self._model.encode([f"query: {text}"], normalize_embeddings=True),
            dtype=np.float32,
        )[0]
