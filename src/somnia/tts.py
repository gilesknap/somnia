"""TTS engines. Rendering is per-sentence so timestamps are exact by construction."""

from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from .voices import DEFAULT_VOICE, lang_code_for

__all__ = ["KokoroEngine", "TTSEngine"]

Samples = npt.NDArray[np.float32]


class TTSEngine(Protocol):
    """A text-to-speech engine rendering one sentence at a time, in one voice.

    ``voice`` is on the protocol rather than only on the configuration because
    the ``books`` row has to record what actually read the book, and only the
    engine knows that. A request may name no voice, in which case the renderer
    supplies its own, and asking the configuration afterwards would write down
    the wrong answer for every book that did name one.
    """

    sample_rate: int
    voice: str

    def render(self, text: str) -> Samples:
        """Render text to mono float32 samples at ``sample_rate``."""
        ...


class KokoroEngine:
    """Kokoro-82M via the official pipeline. ~1.15x realtime on 2 CPU cores."""

    sample_rate = 24000

    def __init__(self, voice: str = DEFAULT_VOICE, lang_code: str = "") -> None:
        """Build the pipeline for one voice, in that voice's own language.

        ``lang_code`` used to default to ``"a"`` and nothing ever passed
        anything else, which quietly made the British voices unusable: the
        language chooses the phonemiser and the voice only chooses the timbre,
        so ``bm_george`` was a British-sounding man reading American vowels.
        It is derived from the voice now — see :func:`somnia.voices.lang_code_for`
        — and the argument stays only as an override for somebody who really
        does want that combination, which is a thing Kokoro allows.
        """
        from kokoro import KPipeline  # type: ignore[import-untyped]  # noqa: PLC0415

        self._pipeline: Any = KPipeline(
            lang_code=lang_code or lang_code_for(voice), repo_id="hexgrad/Kokoro-82M"
        )
        self.voice = voice

    def render(self, text: str) -> Samples:
        chunks: list[Samples] = []
        result: Any
        for result in self._pipeline(text, voice=self.voice):
            audio: Any = result.audio
            if audio is None:
                continue
            chunks.append(np.asarray(audio.numpy(), dtype=np.float32))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)
