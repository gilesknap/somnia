#!/usr/bin/env python3
"""Render one sample of each voice, for the picker on Workshop to play.

A list of voice names is not a choice. ``bm_george`` and ``af_bella`` mean
nothing until you have heard them, and the alternative to hearing them is
finding out five minutes into a six-hour render. So the picker plays a clip,
and this is what makes the clips.

Run on the render host — the samples are committed, because the box that serves
the page has no Kokoro on it and never will:

    scripts/somnia-voices.py                    # every voice in the roster
    scripts/somnia-voices.py --voice bm_george  # just the one, after a change
    scripts/somnia-voices.py --out /tmp/try     # somewhere other than the app

Every voice says the same sentence, which is Black Beauty's first line — a real
book somnia renders, so what you hear in the picker is the thing itself rather
than a phrase chosen to flatter a model. Identical text is also the only way to
compare two voices: two clips of different words are a comparison of the words.

The output is m4a at the same bitrate as a book, through the same encoder, for
the same reason — a sample that sounds better than the render it promises is
worse than no sample at all.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The page is served out of the package, so that is where the clips live: they
# are static assets of the app in the way the fonts and the icons are, and a
# deploy that carried the code without them would leave every press silent.
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "src" / "somnia" / "web" / "voice"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--voice",
        action="append",
        default=None,
        metavar="ID",
        help="one voice, repeatable (default: the whole roster)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"where to write the clips (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args(argv)

    from somnia.audio import ChapterAudio  # noqa: PLC0415
    from somnia.config import Config  # noqa: PLC0415
    from somnia.tts import KokoroEngine  # noqa: PLC0415
    from somnia.voices import SAMPLE_TEXT, VOICES, known  # noqa: PLC0415

    wanted = args.voice or [v.id for v in VOICES]
    unknown = [v for v in wanted if not known(v)]
    if unknown:
        # Refused rather than rendered. A clip for a voice the roster does not
        # have is one the page will never ask for and nobody will ever notice
        # is stale, and the name is far more likely to be a typo.
        print(f"xx not in the roster: {', '.join(unknown)}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    bitrate = Config().aac_bitrate
    for voice in wanted:
        print(f"==> {voice}", file=sys.stderr)
        # One engine per voice, because the voice is fixed when the pipeline is
        # built — and because the language is derived from the name, which is
        # the whole reason the British ones are worth listening to now.
        engine = KokoroEngine(voice=voice)
        audio = ChapterAudio(engine.sample_rate)
        audio.append(engine.render(SAMPLE_TEXT))
        out_path = args.out / f"{voice}.m4a"
        audio.encode(out_path, bitrate=bitrate)
        print(f"    {out_path} ({out_path.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
