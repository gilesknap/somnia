"""Encoding a chapter, and what is left behind when it does not finish.

Real ffmpeg, because the thing under test is the file on disk: whether a
chapter that stopped part-way can be told from one that finished. A stub that
touched the path would agree with either implementation.

Everything else about `ChapterAudio` — the running clock, the silences — is
already exercised through `tests/test_ingest.py`.
"""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from somnia.audio import ChapterAudio


def one_second() -> ChapterAudio:
    audio = ChapterAudio(24000)
    audio.append(np.zeros(24000, dtype=np.float32))
    return audio


def test_a_chapter_that_encodes_is_there_and_plays(tmp_path: Path) -> None:
    out = tmp_path / "chapters" / "0001.m4a"

    one_second().encode(out)

    assert out.exists()
    assert out.stat().st_size > 0
    # And nothing beside it. The half-written file this writes through is the
    # implementation, and a caller that saw it would have two chapters.
    assert [p.name for p in out.parent.iterdir()] == ["0001.m4a"]


def test_an_encode_that_dies_leaves_no_chapter_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deploy, a reboot, an OOM kill, `systemctl stop` — all the same shape.

    ffmpeg used to be given the real path, so a kill part-way left a truncated
    .m4a where a finished one belongs. Nothing downstream re-checks that: the
    chapter row is written from the encode returning, and a resumed render
    skips chapters whose file is already there. The book kept a chapter that
    stops in the middle of a sentence and no later run repaired it.
    """
    out = tmp_path / "chapters" / "0001.m4a"

    def killed(command: list[str], **kwargs: object) -> object:
        # Whatever ffmpeg had written by then is on disk under whichever name
        # it was given, which is the point: the name it was given must not be
        # the chapter's. The command is typed rather than taken out of *args,
        # so that the shape this stands in for is stated instead of suppressed.
        for arg in command:
            if arg.endswith((".m4a", ".part")):
                Path(arg).write_bytes(b"\x00\x00\x00\x18ftypM4A ")
        raise subprocess.CalledProcessError(-9, "ffmpeg")

    monkeypatch.setattr(subprocess, "run", killed)

    with pytest.raises(subprocess.CalledProcessError):
        one_second().encode(out)

    assert not out.exists()
    # And no rubble either, so the next attempt starts from nothing.
    assert list(out.parent.iterdir()) == []


def test_a_second_attempt_writes_over_the_first(tmp_path: Path) -> None:
    """A render picked up again re-encodes a chapter it did not finish."""
    out = tmp_path / "chapters" / "0001.m4a"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"the last attempt, truncated")

    one_second().encode(out)

    assert out.read_bytes() != b"the last attempt, truncated"
    assert [p.name for p in out.parent.iterdir()] == ["0001.m4a"]
