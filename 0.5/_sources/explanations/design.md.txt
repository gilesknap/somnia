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
different engine/voice: durations change and every timestamp — every index
entry, every chapter mark, and the position they went to sleep at — would be
invalidated.

## Streaming ingest: pick a book and go

The pipeline emits **one m4a file per chapter** into the Audiobookshelf
library folder as each chapter finishes, then triggers a library rescan.
Multi-file books are ABS's native format with a single global timeline, so:

- listening can start when chapter one is rendered (minutes after picking)
- the semantic index grows chapter by chapter, so a book can be asked about
  while it is still being read — but it is not what keeps the ending back. A
  book is indexed whole on the evening it renders and listened to over the
  fortnight after, so from the second night on, the only thing between a
  question and the last page is the spoiler guard below
- per-chapter files are simultaneously the streaming unit, the ABS-native
  unit, the re-render unit and — since the page became the player — the unit
  the phone fetches over HTTP (a single M4B would defeat all four)

All timestamps everywhere are **global milliseconds from book start** —
`chapters` rows carry each chapter's global start, so index hits, the saved
position, what the player has on screen and what ABS is told all speak the same
clock. It is the render clock, counted in samples before encoding, and never
what a decoder reports: summing durations off the files drifts by tens of
milliseconds a chapter and is a second out by chapter forty.

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

## Playback: the page is the player, and the position is somnia's own

This reverses the original design, which made the Audiobookshelf Android app
the player and a move a write to `PATCH /api/me/progress/:id`. It worked, and
it ended every move with "now press play again", because ABS has no transport
API and the app has no deep link. The argument, and the four ways of pressing
that button remotely that we turned down, are in
[ADR 3](decisions/0003-play-the-book-in-the-page.md); the losses are there too,
offline downloads chief among them.

**The page plays the book.** somnia rendered the audio, so serving it is one
route per chapter (`/api/audio/{gid}/{idx}`) resolved from the `chapters` row,
never from a path in the request; Range, `If-Range` and 416 — and therefore
seeking — are Starlette's own. The page holds one `<audio>` element for its
whole life and stitches the per-chapter files into a single timeline counted in
**global milliseconds**, the clock the index, the chapter marks and the agent
already speak. Which file a position falls in is an implementation detail of
three conversion functions, so "back a bit" from the start of chapter five
lands in chapter four, the way a listener means it.

**Most of the transport is not on the page.** With the screen off the book is
driven from the lock screen, the notification shade and whatever is paired over
Bluetooth, all of which arrive through the Media Session API. The scrubber
published there is chapter-scale on purpose: a whole-book scrubber on a
twelve-hour novel gives three minutes to the pixel, and one sleepy thumb would
fling them past the spoiler guard into the ending.

**Stopping the book is as much of the job as starting it.** The two things the
ABS app did that a bedtime player cannot do without: a sleep timer — fifteen,
thirty, forty-five or sixty minutes, or the end of the chapter — counted in
listening time rather than clock time, so pausing to ask a question does not
spend it, and ending in a twenty-second fade that reaches silence at the moment
it named rather than beginning there. And a rewind sized by how long the sound
was off, since a pause is three unlike things wearing one name: a moment taken
to hear something in the room, a question asked and answered, and falling
asleep with the phone in a hand. Only the last of those means the last thing
they took in was well before where the sound stopped, so only the longest rung
of the ladder goes back half a minute, and only that one lands on the start of
the sentence — which somnia can do and ABS could not, because ABS does not know
where sentences are. Shake-to-extend is the one thing from the app not
reimplemented: it wants a motion permission and a threshold nobody can guess at
from a desk.

**The position lives in sqlite, and nothing fights over it.** `position_ms` is
where they are, `position_seq` counts agent moves and nothing else, and
`position_at` is how a cold launch knows which book to open. The asymmetry is
the whole protocol: the page's own reports — every fifteen seconds while it
plays, at every jump and every chapter boundary, and whenever the sound starts
or stops — leave the count alone, so a report carrying a stale count can only
mean the agent moved the book, and the refusal that comes back is also the
instruction to jump. That is why a refusal is a 200 with a body and not a 409:
the last report of the night is a beacon, and a beacon can read nothing else.

A book being left behind gets a report of its own, sent while the page is still
on it, because it is the last thing that page will ever say about that book:
the pause a chapter swap fires is swallowed as spurious — quite rightly, or the
notification would be torn down at every boundary — so without it a book they
were moved out of would keep whatever position its last heartbeat happened to
catch, and the spoiler guard's mark would be left behind that position with no
way of ever catching up.

Nothing else in somnia may write those four columns. Ingest upserts the `books`
row rather than replacing it, and updates only what a render knows — title,
authors, voice, and that it is running. It used to be `INSERT OR REPLACE`,
which is `DELETE` then `INSERT`, so restarting a render that died wiped the
position and the mark, and left the count below the one a still-open page was
holding: every report that page made for the rest of the night was refused, and
nothing was written again until it was reloaded.

**Audiobookshelf is written to and never read.** The write is best effort, off
the critical path, and only when they have stopped: it costs a handful of
requests a night and means the book is in roughly the right place if they open
ABS somewhere else. A failure is logged and ignored — the app is not the player
any more, so nothing tonight depends on it. Both routes to a position — an
agent move, and the page saying it has stopped — end in the same
`somnia.abs.tell_abs`, because they are one thing said twice.

There is exactly one read left, and it is not on a listening path.
`somnia seed-positions` runs once, by hand, and takes each book's
`currentTime` and `lastUpdate` out of ABS's progress records. Without it the
first night of the pivot opens the most recently *added* book at 0:00 and
bounds every search at the first minute, because the position they have really
reached lives on the other server and nothing here has ever heard of it. It
never lowers anything: a position somnia already holds is left alone (the page
is the player, so the row is the newer of the two) and the high-water mark only
rises. `position_at` comes from ABS's `lastUpdate` rather than from the moment
the seed ran — stamping every book with the same second would hand the choice
of which book to open back to `created_at`, which is the failure it is there
to fix.

**The spoiler guard is bounded by the furthest point ever played through**, not
by the current position, because the agent can move that position anywhere:
backwards, where being taken to chapter two must not un-hear chapters three to
twenty, and forwards, where treating where they were put as what they have
heard would unlock the whole book behind a single move. `books.heard_to_ms`
records the mark and only ever rises, and it rises only as far as sound really
came out of the speaker. Only the page can know that — a skip and a stretch of
listening both arrive at the server as a position further on than the last one
— so every report says how much of the book has actually played since the last
report the server took, counted off the media clock, and the mark rises to the
reported position only when the report stands no further past the mark than
that playback accounts for. The wall clock is a ceiling on the claim and not
the answer to it: a phone asleep in a pocket for eight hours banks eight hours
of clock and no listening at all, and reading the first report after it off the
clock handed over a five-hour agent move in full. A pause raises the mark like
anything else, because a pause is the best evidence in the protocol that they
listened right up to it; and playback the server never acknowledged stays owed
and is sent again, because a mark left even a heartbeat behind the position
refuses every report after it and never recovers — except across a jump, where
it is given up instead, since it was earned over the ground behind the jump and
would otherwise be spent on the distance by the report from the far side. Two costs, both chosen: after
a skip forward the mark stops until they go back over it, and a book nobody has
played is bounded at its start rather than left unbounded, so on night one the
agent has to say the passage is further on than they have got and offer to take
them there. Failing that way costs a question in the dark; failing the other
way costs them the book.

A bounded search does not simply come back empty. It also runs unbounded and
says whether a closer match lies past the mark — never what it is — which is
what lets the agent offer rather than shrug, and `find_passage(allow_spoilers)`
is the way through, asked for by them and by nobody else.

## Getting through the night is the page's job now

Three things the ABS app used to absorb, which nothing absorbs any more. All
three end the same way if they are not handled — silence, with a notification
that says paused — and none of them can be seen without unlocking the phone,
which is why each of them says what is happening on the status line as well as
doing something about it.

**The book grows while it is being played.** A manifest is a photograph of a
book that is still arriving: ingest writes each chapter row as it finishes and
bumps `total_ms` with it, so a book fetched once at boot is frozen at whatever
existed an instant after the page opened. Chapter three of forty-nine ended the
night with "that is the end of the book". The page asks again for as long as
the status says rendering — when the audio runs out, which is the ask the
listener is waiting on, and when the page comes back in front of them, which is
the ask that costs nothing — backing off from five seconds to a minute in
between, because Kokoro takes minutes over a chapter. Only the timeline is
adopted from the answer: `position_ms` and `seq` in it are the page's own last
report come back fifteen seconds late, and taking them would drag the listener
backwards every time the book grew.

**The tailnet goes, briefly, most nights.** Wifi power save, a DHCP renewal and
a tailscale re-key each take it away for a few seconds, and a media element
comes back from none of them by itself: once it has taken a network error it
never fetches again, and a buffer that ran dry with nothing behind it sits
there silently. So the page reloads the chapter — assigning `src` is the whole
of what makes an element try again — from where they had got to rather than
from the top of it, so five seconds off the network costs five seconds and not
the last ten minutes over again. It waits longer each time, two seconds to thirty,
because a VPS that is down is down and a phone that retried flat out until
morning is a phone with no battery in the morning. Every route to a reload goes
on that same ladder, including the one that never sees an error at all: a
server that accepts the connection and answers nothing — a proxy black hole, a
re-key caught mid-handshake — leaves the element stalling rather than failing,
and a stall that reloads on a fixed timer stalls again off the new source, for
ever, at exactly the fixed cadence the ladder exists to prevent. It stops
entirely when
they were the ones who stopped it, because a page reloading chapters under a
book somebody put down is spending the battery on nobody. The boot does the
same thing for the same reason: the service worker serves the shell when the
server cannot be reached, which is right, and what they land on otherwise is a
page that looks perfectly alive with no book in it.

**The page itself dies.** A backgrounded tab is discarded whenever the phone
wants the memory back, and reloading is the first thing anyone does to a page
that looks stuck. The conversation is meant to die that way — it is keyed in
`sessionStorage` and starting fresh is the point — but an armed sleep timer is
an instruction about tonight that nobody has cancelled, so it is written to
`localStorage` as it counts down and restored with the minutes it had left.
Not a timer older than six hours: someone opening the book the next evening is
starting a night rather than finishing one, and a timer they could not remember
setting would end it early for no reason they could see.

## Serving the audio and answering the questions are separate lanes

A model turn blocks for tens of seconds on the API and on the embedder. A seek
must not queue behind it — a dead player while a question is being answered is
exactly the moment the phone gets put down — so `somnia.player.Player` has its
own sqlite connection, its own lock and its own ABS client, and shares nothing
with a conversation but the file on disk. sqlite is in WAL for the same reason:
three writers now exist (a turn, the player, and `somnia add` in another
process entirely) and a reader must never block on any of them.

## Agent surface

- Tool layer is a plain Python library: `list_books`, `search_catalog`,
  `add_book`, `find_passage` (bounded by the guard unless they say otherwise),
  `get_position` (reads somnia's own record of where they are), `move_to`
  (writes it, and counts the move so the page follows). The model is never told
  to tell them to press play, because there is nothing to press.
- 2am surface: a small **PWA chat page** served from the VPS. The server runs
  the agent loop (Anthropic Python SDK tool runner) with an API key held
  server-side — no OAuth. Voice input via the browser's Web Speech API
  (push-to-talk button); Android keyboard dictation as fallback.
- Model: **Sonnet 5** default, `SOMNIA_AGENT_MODEL` to change it. Haiku 4.5 was
  the original choice on cost, and mostly held up, but it read a character's
  name as the title of a book somnia does not have and said so — a spoken
  half-sentence at 2am is exactly the disambiguation this is here to do. The
  difference is a few cents a night.
- MCP server: designed for, never built, and nothing needs it. A FastMCP
  wrapper over the tool layer would be a dev-time convenience only — the 2am
  surface is the page, and the tools are a library any test can call directly.
  claude.ai custom connectors were rejected for v1 outright: they require a
  publicly reachable MCP endpoint plus OAuth, which conflicts with the network
  model below.

As built (`somnia serve`, Starlette + uvicorn): `POST /api/ask` and
`/api/forget` for the conversation, `/api/health`, and five routes the player
needs — `/api/books`, `/api/book/{gid}`, `/api/audio/{gid}/{idx}`,
`/api/sentence/{gid}/{ms}` and `POST /api/position` — with the page itself
mounted at `/`. Everything the page fetches sits under `/api/`, which is not
cosmetic: it is how the service worker knows what never to cache.

- **Conversation state lives on the server**, keyed by a token the page mints
  on load. The tool-runner history contains SDK content blocks, not JSON the
  page could hold; keeping it server-side also means the agent's whole library
  — including the loaded embedder — survives between questions instead of
  paying seconds of torch startup on every search.
- **Push-to-talk, not always-listening.** A bedroom is full of speech that was
  not meant for somnia, and holding a button is the one gesture that survives
  being half awake. Answers are read, never spoken back: the only thing the
  page makes a sound with is the book, and an answer read aloud over it would
  be somnia interrupting itself. A reply landing on a phone lying face down is
  also a reply nobody was listening for.
- **No login.** Reachability *is* the authentication: the server binds to
  localhost and only `tailscale serve` can reach it. Adding a password would
  mean typing one at 2am, in the dark, to ask where the horse dies.

## Network model

The VPS is treated as untrusted-ish (it runs experiments). It joins the
owner's tailnet **tagged** (`tag:vps`), and the tailnet ACL never lists that
tag as a source — so the VPS is reachable from personal devices but can never
initiate connections into the tailnet. Nothing is exposed publicly.
`tailscale serve` fronts ABS and the PWA on separate ports with a real TLS
certificate on the node's `.ts.net` name. That one-way rule is what ruled out
every remote-control route in
[ADR 3](decisions/0003-play-the-book-in-the-page.md), and the certificate is
not optional either: an installable PWA, the Web Speech API and a media session
all require a secure context.

The whole night now goes over that path — the audio as well as the questions —
which is the price of the pivot: nothing is downloaded, so a tailnet that drops
at 3am takes the book with it.

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
