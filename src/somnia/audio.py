"""Chapter audio assembly: accumulate rendered sentences, encode to m4a."""

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf  # type: ignore[import-untyped]

__all__ = ["ChapterAudio"]

Samples = npt.NDArray[np.float32]


class ChapterAudio:
    """Accumulates audio for one chapter and tracks the running clock."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._parts: list[Samples] = []
        self._samples = 0

    @property
    def position_ms(self) -> int:
        return round(self._samples * 1000 / self.sample_rate)

    def append(self, samples: Samples) -> None:
        self._parts.append(samples)
        self._samples += len(samples)

    def append_silence(self, ms: int) -> None:
        n = round(ms * self.sample_rate / 1000)
        self._parts.append(np.zeros(n, dtype=np.float32))
        self._samples += n

    def encode(self, out_path: Path, bitrate: str = "64k") -> None:
        """Encode accumulated audio to AAC in an m4a container via ffmpeg.

        Written beside the chapter and moved onto it, rather than into it.
        ffmpeg was given the real path, so anything that stopped it part-way —
        a deploy, a reboot, an OOM kill, `systemctl stop` while the last
        chapter of the night was encoding — left a truncated .m4a where a
        finished one belongs. Nothing downstream re-checks that: the chapter
        row is written from the encode returning, and a resumed render skips
        chapters whose file is already there, so the book keeps a chapter that
        stops in the middle of a sentence and no later run repairs it.

        The rename is on the same directory as the file it replaces, which is
        what makes it atomic: either the whole chapter is there or none of it
        is, and a half-written .part is ignored by everything and overwritten
        by the next attempt.
        """
        audio = (
            np.concatenate(self._parts)
            if self._parts
            else np.zeros(0, dtype=np.float32)
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = out_path.with_name(out_path.name + ".part")
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
                sf.write(tmp.name, audio, self.sample_rate)
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-loglevel",
                        "error",
                        "-i",
                        tmp.name,
                        "-c:a",
                        "aac",
                        "-b:a",
                        bitrate,
                        "-movflags",
                        "+faststart",
                        # Said out loud because the name below no longer ends
                        # in .m4a, and the extension is how ffmpeg was choosing
                        # a container: given `.part` it refuses to guess and
                        # writes nothing. `ipod` is the muxer `.m4a` was
                        # selecting all along — same muxer, same flags, and the
                        # first 32 bytes of the output compare equal either way.
                        "-f",
                        "ipod",
                        str(part_path),
                    ],
                    check=True,
                    # A chapter is minutes of audio and this is the last cheap
                    # step of rendering it, so an hour is far past anything
                    # honest work takes. What it is for is the other case: a
                    # wedged ffmpeg holds the one render slot in the whole of
                    # somnia, silently, and the queue behind it never moves.
                    timeout=3600,
                )
            part_path.replace(out_path)
        finally:
            part_path.unlink(missing_ok=True)
