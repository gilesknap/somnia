# Bedtime reader — scratch brief

Dumped from a phone conversation. Not a spec. Argue with it.

## Why

Tinnitus went ~3x louder in a week (unilateral, same side as a sore throat/ear —
GP Friday). Sleep is wrecked. Masking noise alone needs more level than I want
in a shared bed. Narrative distraction works at *much* lower volume because
speech grabs attention well below the energetic masking threshold.

Hardware: Avantree Slumber 2 under-pillow speaker, Bluetooth, arriving tomorrow.

The thing I actually want that doesn't exist:

> "Rewind to where the horse dies."

I fall asleep, lose my place, and can't find it again — the last ~5-10 min
before sleep onset never gets consolidated to memory, so scrubbing until
something "sounds familiar" is unreliable by construction. Semantic seek fixes
this. Also want: "where did I get to?" → answer in *prose*, not a timestamp.

Public domain only. Gutenberg. No DRM, no copyright problem.

## Key insight (the whole thing hinges on this)

**Generate the audio myself → text/audio alignment is free.**

If I TTS it, I know which sentence produced which audio segment. Exact
(text → timestamp) index falls out of the render loop. No forced alignment,
no Whisper, no drift.

(LibriVox human narration is the alternative but then it's WhisperX word-level
timestamps + align against Gutenberg text. Extra step, extra failure mode.
Skip for v1. Maybe never — TTS flatness is arguably *better* for sleep: no
dynamic range spikes, no dramatic emphasis, leaks less to Natasha at the same
intelligibility.)

## Pipeline

1. Fetch Gutenberg plain text. Strip the licence header/footer boilerplate.
2. Sentence split. Watch out for `Mr.` / `St.` / dialogue punctuation.
3. Chunk to ~3 sentences (tune — needs to be a searchable semantic unit but
   fine-grained enough to seek usefully).
4. Render each chunk with Kokoro. Accumulate duration →
   `(chunk_id, chapter, start_ms, end_ms, text)`.
5. Embed chunks → pgvector (already running, reuse it).
6. Concat to a single M4B with chapter markers.

Kokoro vs Piper: Kokoro sounds better, Piper is faster/lighter. Try Kokoro
first, it runs fine on the VPS. Batch overnight, it's not interactive.

Watch: chunk boundaries mid-sentence produce audible seams on concat. Render
with a little silence padding? Or render per-paragraph and index per-sentence
by interpolation — worse but simpler.

## MCP surface

Four tools is probably enough:

- `find_passage(query)` → semantic search. **Returns candidates with
  surrounding context**, not just the top hit — I need to disambiguate before
  seeking. ("There are three horses that die in this. Which one?")
- `seek_to(ms)`
- `get_position()` → returns ms **and the text at that point**. This is the one
  that closes the loop. Wake up, ask where I got to, get told in prose. Then
  "no, further back, before they reach the inn" is just another find_passage.
- `list_bookmarks()` / `add_bookmark(ms, note)`

Maybe later: `set_sleep_timer(min)`, `get_history()` (play/pause events so it
can infer where I dropped off from the *gap*, not from what I remember).

## The hard bit: playback control

My phone is the player. That's the whole problem.

Audiobookshelf's API syncs progress but won't push a seek to a client in real
time. Options:

- **Small PWA on the VPS holding a websocket.** Phone opens it, plays audio,
  listens for seek commands. Cleanest. Everything else is standard.
- Audiobookshelf + custom client — more work, more benefit long term.
- Local-only: skip remote control entirely, MCP just *tells* me a timestamp
  and I scrub manually. Ugly but works day one and de-risks everything else.

Probably build the last one first as a fallback path, then add the socket.

PWA needs: screen dim/off with audio continuing, Bluetooth media controls,
shake-to-extend sleep timer, smart rewind on resume (scaled to pause length),
fade-out rather than hard stop (abrupt endings wake me).

## Order of work

1. Ingest script — Gutenberg fetch → chunk → Kokoro → timestamp index →
   pgvector. Self-contained, testable before any MCP plumbing exists.
   **Start here.**
2. `find_passage` + `get_position` against a static index, output timestamps
   only. Prove the semantic search is actually good enough.
3. PWA player.
4. Websocket seek.
5. Sleep timer / bookmarks / history.

## Known limitations

- Semantic search is good on concrete events ("the horse dies"). Much weaker on
  "the bit with the odd atmosphere". Accept it.
- Chunk granularity vs search quality is a real tradeoff, will need tuning
  against actual 2am queries.
- TTS mispronunciation of archaic/proper nouns. Pronunciation dictionary if it
  gets annoying.

## Test books

Both public domain, both contain a dying horse, which is the canonical query:

- *Black Beauty*
- *Crime and Punishment*

## Open questions

- Chunk size? Start 3 sentences, tune.
- Store audio as one M4B + offsets, or per-chunk files? One file is better for
  the player, per-chunk is better for re-rendering. Probably one file + keep
  chunks for regeneration.
- Does the sleep-onset gap in the play/pause history actually predict where I
  stopped listening better than my memory does? Probably. Worth logging from
  day one even if unused.
