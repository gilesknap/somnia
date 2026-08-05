"""TTS engines. Rendering is per-sentence so timestamps are exact by construction."""

from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

__all__ = ["KokoroEngine", "TTSEngine"]

Samples = npt.NDArray[np.float32]


class TTSEngine(Protocol):
    """A text-to-speech engine rendering one sentence at a time."""

    sample_rate: int

    def render(self, text: str) -> Samples:
        """Render text to mono float32 samples at ``sample_rate``."""
        ...


class KokoroEngine:
    """Kokoro-82M via the official pipeline. ~1.15x realtime on 2 CPU cores."""

    sample_rate = 24000

    def __init__(self, voice: str = "af_heart", lang_code: str = "a") -> None:
        from kokoro import KPipeline  # type: ignore[import-untyped]  # noqa: PLC0415

        self._pipeline: Any = KPipeline(
            lang_code=lang_code, repo_id="hexgrad/Kokoro-82M"
        )
        self._voice = voice

    def render(self, text: str) -> Samples:
        chunks: list[Samples] = []
        result: Any
        for result in self._pipeline(text, voice=self._voice):
            audio: Any = result.audio
            if audio is None:
                continue
            chunks.append(np.asarray(audio.numpy(), dtype=np.float32))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)
