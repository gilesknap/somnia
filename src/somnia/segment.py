"""Sentence splitting and windowing for the semantic index."""

from dataclasses import dataclass
from functools import cache
from typing import Any, cast

import pysbd  # type: ignore[import-untyped]

__all__ = ["TimedSentence", "Window", "sentences", "windows"]


@dataclass
class TimedSentence:
    text: str
    start_ms: int
    end_ms: int


@dataclass
class Window:
    text: str
    start_ms: int
    end_ms: int


@cache
def _segmenter() -> Any:
    return pysbd.Segmenter(language="en", clean=False)


def sentences(paragraph: str) -> list[str]:
    """Split a paragraph into sentences (handles Mr., St., dialogue, etc.)."""
    result = cast(list[str], _segmenter().segment(paragraph))
    return [s.strip() for s in result if s.strip()]


def windows(sents: list[TimedSentence], size: int = 3, stride: int = 2) -> list[Window]:
    """Overlapping sentence windows — the searchable unit of the index."""
    if not sents:
        return []
    out: list[Window] = []
    i = 0
    while True:
        group = sents[i : i + size]
        out.append(
            Window(
                text=" ".join(s.text for s in group),
                start_ms=group[0].start_ms,
                end_ms=group[-1].end_ms,
            )
        )
        if i + size >= len(sents):
            break
        i += stride
    return out
