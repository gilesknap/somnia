#!/usr/bin/env python3
"""Measure how fast this machine renders a book.

Rendering is the only slow thing somnia does — hours per book, where everything
else is seconds — so "is this box faster" means one number: how many seconds of
audio come out per second of wall clock. That is what this prints, as ``xRT``.
1.0x is a machine rendering a book in exactly the time it takes to listen to it.

It renders the same passage the same way ingest does — one sentence at a time,
through the same :class:`~somnia.tts.KokoroEngine` — so the figure is the one
that governs a real render and not a batched best case nothing will ever see.
The passage is fixed and carried in this file: comparing two machines means
giving them identical work, and a chapter fetched from Gutenberg is neither
identical between runs nor available on a box with no network.

Usage:

    somnia-bench.py                    # this machine, as somnia would run it
    somnia-bench.py --threads 4        # pin torch to 4 threads
    somnia-bench.py --device xpu       # try an Intel GPU
    somnia-bench.py --json             # for a script to read

The first few sentences of any run are slower than the rest — lazy imports,
weights arriving from disk, the allocator settling — so a warmup is rendered
and thrown away before the clock starts. ``--warmup 0`` includes it, which is
the honest figure for a render that only ever does one sentence, and the
misleading one for a render of a whole book.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from typing import Any

# Six sentences from Black Beauty (Sewell, 1877; public domain), which is book
# 271 and the one somnia's own tests read. Short lines, long lines and dialogue,
# in the proportion real prose has them — a passage of uniformly long sentences
# would flatter any machine by amortising the per-sentence overhead that a real
# chapter pays over and over.
PASSAGE = [
    "The first place that I can well remember was a large pleasant meadow"
    " with a pond of clear water in it.",
    "Some shady trees leaned over it, and rushes and water-lilies grew at"
    " the deep end.",
    "Over the hedge on one side we looked into a plowed field, and on the"
    " other we looked over a gate at our master's house, which stood by"
    " the roadside.",
    "While I was young I lived upon my mother's milk, as I could not eat grass.",
    "In the daytime I ran by her side, and at night I lay down close by her.",
    "When it was hot we used to stand by the pond in the shade of the trees,"
    " and when it was cold we had a nice warm shed near the grove.",
]


def _sentences(count: int) -> list[str]:
    """``count`` sentences, cycling the passage so every run does equal work."""
    return [PASSAGE[i % len(PASSAGE)] for i in range(count)]


def _machine() -> dict[str, Any]:
    """What this box is, in the terms that explain a rendering speed."""
    import torch  # noqa: PLC0415

    model = platform.processor() or platform.machine()
    try:  # /proc/cpuinfo names the chip; platform.processor() often does not.
        with open("/proc/cpuinfo") as handle:
            for line in handle:
                if line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    return {
        "host": platform.node(),
        "cpu": model,
        "cpu_count": __import__("os").cpu_count(),
        "torch": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "python": platform.python_version(),
    }


def _resolve_device(name: str) -> str:
    """Turn ``auto`` into whatever this box actually has, and check the rest.

    A device that is asked for and missing is a stop, not a fallback: the whole
    point of passing ``--device xpu`` is to find out whether the GPU is real,
    and a benchmark that quietly answers about the CPU instead would report a
    CPU number under a GPU heading and settle the question the wrong way.
    """
    import torch  # noqa: PLC0415

    available = {"cpu": True}
    available["cuda"] = torch.cuda.is_available()
    available["mps"] = getattr(torch.backends, "mps", None) is not None and (
        torch.backends.mps.is_available()
    )
    available["xpu"] = hasattr(torch, "xpu") and torch.xpu.is_available()

    if name == "auto":
        for candidate in ("cuda", "xpu", "mps", "cpu"):
            if available.get(candidate):
                return candidate
        return "cpu"
    if not available.get(name):
        have = ", ".join(sorted(k for k, v in available.items() if v))
        raise SystemExit(
            f"xx device {name!r} is not available here (this box has: {have})"
        )
    return name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--sentences", type=int, default=24, help="sentences to time (default 24)"
    )
    parser.add_argument(
        "--warmup", type=int, default=3, help="sentences to render untimed first"
    )
    parser.add_argument(
        "--threads", type=int, default=0, help="torch threads (0 leaves the default)"
    )
    parser.add_argument(
        "--device", default="auto", help="cpu, cuda, xpu, mps, or auto (default auto)"
    )
    parser.add_argument("--voice", default="af_heart", help="Kokoro voice")
    parser.add_argument(
        "--json", action="store_true", help="print JSON and nothing else"
    )
    args = parser.parse_args(argv)

    import torch  # noqa: PLC0415

    # Before the engine is built: KPipeline reads the thread count when it
    # constructs its modules, so setting it afterwards moves nothing.
    if args.threads:
        torch.set_num_threads(args.threads)

    device = _resolve_device(args.device)
    say = (lambda *a: None) if args.json else (lambda *a: print(*a, file=sys.stderr))

    say(f"==> loading Kokoro on {device}")
    load_start = time.perf_counter()
    from somnia.tts import KokoroEngine  # noqa: PLC0415

    engine = KokoroEngine(voice=args.voice)
    # somnia never passes a device, so KPipeline picked one on its own. Move the
    # model only when this run asked for something else, so the default path
    # stays exactly the code a real render takes.
    if device != "cpu" or args.device != "auto":
        engine._pipeline.model = engine._pipeline.model.to(device)  # noqa: SLF001
    load_s = time.perf_counter() - load_start
    say(f"    loaded in {load_s:.1f}s")

    for text in _sentences(args.warmup):
        engine.render(text)

    say(f"==> rendering {args.sentences} sentences")
    per_sentence: list[float] = []
    samples = 0
    wall_start = time.perf_counter()
    for text in _sentences(args.sentences):
        one = time.perf_counter()
        audio = engine.render(text)
        per_sentence.append(time.perf_counter() - one)
        samples += len(audio)
    wall_s = time.perf_counter() - wall_start

    audio_s = samples / engine.sample_rate
    xrt = audio_s / wall_s if wall_s else 0.0
    result = {
        **_machine(),
        "device": device,
        "voice": args.voice,
        "sentences": args.sentences,
        "load_s": round(load_s, 2),
        "audio_s": round(audio_s, 2),
        "wall_s": round(wall_s, 2),
        "xrt": round(xrt, 3),
        "per_sentence_mean_s": round(statistics.mean(per_sentence), 3),
        "per_sentence_median_s": round(statistics.median(per_sentence), 3),
        # What the number means to somebody waiting for a book, which is the
        # only form of it anybody acts on.
        "hours_for_a_5h_book": round(5 / xrt, 2) if xrt else None,
    }

    if args.json:
        print(json.dumps(result))
        return 0

    print(f"host          {result['host']}")
    print(f"cpu           {result['cpu']} ({result['cpu_count']} threads)")
    print(
        f"torch         {result['torch']} on {device},"
        f" {result['torch_threads']} threads"
    )
    print(f"model load    {result['load_s']}s")
    print(f"rendered      {result['audio_s']}s of audio in {result['wall_s']}s")
    print(
        f"per sentence  {result['per_sentence_mean_s']}s mean,"
        f" {result['per_sentence_median_s']}s median"
    )
    print()
    print(
        f"  {xrt:.2f}x realtime  —  a 5-hour book takes"
        f" {result['hours_for_a_5h_book']}h"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
