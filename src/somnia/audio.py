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
        """Encode accumulated audio to AAC in an m4a container via ffmpeg."""
        audio = (
            np.concatenate(self._parts)
            if self._parts
            else np.zeros(0, dtype=np.float32)
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
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
                    str(out_path),
                ],
                check=True,
            )
