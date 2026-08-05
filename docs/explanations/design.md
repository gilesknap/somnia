# Design decisions

This records the load-bearing decisions made while designing somnia, and why.
The original scratch brief is in [original-brief.md](original-brief.md); this
document is what actually got built and supersedes it where they differ.

## The core insight

**Generate the audio yourself and text/audio alignment is free.** Because we
TTS the book, we know exactly which sentence produced which span of audio. The
(text → timestamp) index falls out of the render loop — no forced alignment,
no Whisper, no drift. Everything else follows from this.

## Rendering: per sentence, exact timestamps by construction

The brief agonised over "render per chunk (audible seams) vs render per
paragraph and interpolate (imprecise)". Both were rejected: we render **per
sentence** and join with short configurable silences (120ms between sentences,
500ms between paragraphs). Sentence boundaries are natural pause points, TTS
flatness suits sleep listening, and every sentence's start/end offset is known
exactly because we placed it there. This also makes the TTS engine swappable —
any engine that can render one sentence fits the `TTSEngine` protocol.

## Engine choice: Kokoro, benchmarked

Benchmarks on the target VPS (2 vCPU AMD EPYC 9354P slice):

| Engine | Speed | Verdict |
|---|---|---|
| Kokoro-82M (PyTorch) | ~1.1–1.26× realtime | chosen — preferred voice |
| Kokoro-82M (ONNX int8) | ~0.73× realtime | slower than PyTorch; dead end |
| Piper (en_GB-alan-medium) | ~18× realtime | fallback if speed ever matters more |

Kokoro sounds much better and the owner preferred it decisively. At ~1.15×
realtime the renderer still outruns 1× listening, so streaming works with a
thin margin. If underruns bite in practice: more vCPUs, or a render worker on
a faster home machine pushing chapters up. Never re-render a book with a
different engine/voice: durations change and every timestamp (and every
listener position in Audiobookshelf) would be invalidated.

## Streaming ingest: pick a book and go

The pipeline emits **one m4a file per chapter** into the Audiobookshelf
library folder as each chapter finishes, then triggers a library rescan.
Multi-file books are ABS's native format with a single global timeline, so:

- listening can start when chapter one is rendered (minutes after picking)
- the semantic index grows chapter by chapter; you can only ask about
  passages you could have heard
- per-chapter files are simultaneously the streaming unit, the ABS-native
  unit, and the re-render unit (a single M4B would defeat all three)

All timestamps everywhere are **global milliseconds from book start** —
`chapters` rows carry each chapter's global start so ABS positions, bookmark
targets, and index hits all speak the same clock.

## Semantic index

- ~3-sentence overlapping windows (size 3, stride 2) — small enough to seek
  usefully, big enough to be a searchable semantic unit.
- Embeddings: `intfloat/e5-small-v2` (384-dim). e5 is asymmetric —
  "query: "/"passage: " prefixes — which fits conversational 2am queries
  against narrative prose.
- Store: **sqlite-vec in a single sqlite file** alongside FTS5 for the
  catalog. A book is a few thousand windows; brute-force exact NN is
  milliseconds. No database server, no shared infrastructure.

Known limitation (accepted): concrete events ("the horse dies") search well;
atmosphere ("the bit that felt strange") doesn't. Chapter-summary embeddings
are a possible future hedge.

## Book discovery: local catalog, no API dependency

Project Gutenberg has no official JSON API. Instead of depending on the
community Gutendex instance, we import Gutenberg's **official catalog CSV
dump** (~20MB, all ~75k books) into sqlite FTS5. Browsing is fully offline
and deployment has no third-party API dependency. Refresh with
`somnia catalog-update`.

## Playback: Audiobookshelf is the player, bookmarks are the seek vector

We deliberately do **not** build an audio player. The ABS Android app already
has screen-off playback, Bluetooth controls, a sleep timer with
shake-to-extend, fade-out, and smart rewind after pauses. "Seek to where the
horse dies" is implemented as: create an ABS **bookmark** at the found
timestamp, named after the passage — two taps in the app instead of scrubbing.
ABS also records listening sessions, giving play/pause history (for inferring
sleep onset) for free.

## Agent surface

- Tool layer is a plain Python library: `search_catalog`, `add_book`,
  `find_passage`, `get_position` (reads ABS progress), `plant_bookmark`.
- 2am surface: a small **PWA chat page** served from the VPS. The server runs
  the agent loop (Anthropic Python SDK tool runner) with an API key held
  server-side — no OAuth. Voice input via the browser's Web Speech API
  (push-to-talk button); Android keyboard dictation as fallback.
- Model: **Haiku 4.5** default (cents per conversation), configurable up to
  Sonnet for harder disambiguation.
- MCP server (FastMCP wrapper over the tool layer) is a dev-time convenience,
  not the primary surface. claude.ai custom connectors were rejected for v1:
  they require a publicly reachable MCP endpoint plus OAuth, which conflicts
  with the network model below.

## Network model

The VPS is treated as untrusted-ish (it runs experiments). It joins the
owner's tailnet **tagged** (`tag:vps`), and the tailnet ACL never lists that
tag as a source — so the VPS is reachable from personal devices but can never
initiate connections into the tailnet. Nothing is exposed publicly.
`tailscale serve` fronts ABS (and later the PWA) with a real TLS certificate
on the node's `.ts.net` name.

## Deployment shape

- One installable package, subcommands per role (`somnia add`, `somnia serve`
  later, etc.). Heavy ML dependencies (torch, kokoro, sentence-transformers)
  live in the `[ml]` extra — install `somnia[ml]` on the rendering machine;
  CI and light installs skip them. On CPU-only machines install the CPU torch
  wheel (`--extra-index-url https://download.pytorch.org/whl/cpu`).
- Audiobookshelf runs as a rootless podman container (quadlet systemd unit)
  under a dedicated user, bound to localhost, fronted by tailscale serve.
- `ffmpeg` and `espeak-ng` are required system packages on the render host.

## Test books

*Black Beauty* (gid 271) and *Crime and Punishment* (gid 2554) — both public
domain, both contain a dying horse, which is the canonical semantic-seek
query ("there are three horses that die in this — which one?").
