"""Enough MP4 box walking to check a file, with no ffmpeg to hand.

ffmpeg makes the tone fixtures and joins the whole-book streams, but a plain
test run must not need it — see :mod:`tone_book`. So the handful of boxes it
takes to reach a duration, or to see where the header sits, are walked here
rather than shelled out for.

Both questions are about the shape of the container and neither is about the
audio, which is why this stays crude on purpose: top-level boxes only, sizes
read as 32-bit, no 64-bit ``largesize`` and no ``uuid``. Everything somnia
writes is a few hundred megabytes at most, so a size field that needs 64 bits
would itself be the news.
"""

import struct
from pathlib import Path

__all__ = ["boxes", "duration_ms", "payload"]


def boxes(path: Path) -> list[tuple[str, int, int]]:
    """The top-level boxes of an MP4, as ``(name, payload start, box end)``.

    In file order, because the order is the point: ingest writes
    ``-movflags +faststart``, which puts ``moov`` in front of ``mdat`` so a
    player has the sample tables before it has fetched the audio. A file with
    them the other way round plays fine from a disk and costs an extra round
    trip on a tailnet at 2am, which is exactly the difference this exposes.
    """
    data = path.read_bytes()
    found: list[tuple[str, int, int]] = []
    offset = 0
    while offset < len(data):
        (size,) = struct.unpack(">I", data[offset : offset + 4])
        if size < 8:
            raise AssertionError(f"box of size {size} at {offset} in {path}")
        found.append(
            (data[offset + 4 : offset + 8].decode(), offset + 8, offset + size)
        )
        offset += size
    return found


def payload(path: Path, name: str) -> bytes:
    """What is inside a named top-level box, concatenated if there are several.

    Wanted for ``mdat``, which is where every encoded sample lives and nothing
    else does. Comparing two files' ``mdat`` compares their audio and ignores
    everything a container rewrite touches.
    """
    data = path.read_bytes()
    return b"".join(data[start:end] for box, start, end in boxes(path) if box == name)


def duration_ms(path: Path) -> int:
    """How long the container says it is, from ``moov/mvhd``."""
    data = path.read_bytes()

    def find(box: bytes, start: int, end: int) -> tuple[int, int]:
        offset = start
        while offset < end:
            (size,) = struct.unpack(">I", data[offset : offset + 4])
            if data[offset + 4 : offset + 8] == box:
                return offset + 8, offset + size
            offset += size
        raise AssertionError(f"no {box.decode()} box in {path}")

    moov_start, moov_end = find(b"moov", 0, len(data))
    mvhd_start, _ = find(b"mvhd", moov_start, moov_end)
    # Version 0 mvhd: version+flags, created, modified, timescale, duration.
    timescale, duration = struct.unpack(">II", data[mvhd_start + 12 : mvhd_start + 20])
    return round(duration * 1000 / timescale)
