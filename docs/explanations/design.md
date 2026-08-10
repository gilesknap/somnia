# Design decisions

This records the load-bearing decisions made while designing somnia, and why.
It describes what actually got built; the scratch brief it grew out of has been
dropped, because a document nothing was checked against had started to read like
one that things were.

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

Benchmarks on the VPS somnia was first deployed to (2 vCPU AMD EPYC 9354P
slice):

| Engine | Speed | Verdict |
|---|---|---|
| Kokoro-82M (PyTorch) | ~1.1–1.26× realtime | chosen — preferred voice |
| Kokoro-82M (ONNX int8) | ~0.73× realtime | slower than PyTorch; dead end |
| Piper (en_GB-alan-medium) | ~18× realtime | fallback if speed ever matters more |

Kokoro sounds much better and the owner preferred it decisively. At ~1.15×
realtime on that 2 vCPU box the renderer still outruns 1× listening with a thin
margin — and that margin is the sentence the ingest queue exists to defend,
because two renders at once halve it and the whole of streaming ingest stops
working. **One book renders at a time**, in its own systemd unit, which is
[ADR 5](decisions/0005-render-one-book-at-a-time.md). If underruns bite in
practice: more vCPUs, or a render worker on a faster home machine pushing
chapters up — the lease a renderer holds is deliberately process-agnostic, so
another machine drops into the same slot without a second queue. Measured again
on 2026-08-07 with `scripts/somnia-bench.py` — the same sentence-at-a-time path
a render takes: 3.87× on nuc2 and 1.06× on the VPS
([ADR 7](decisions/0007-cross-a-chapter-without-letting-go.md)). Both outrun 1×
listening; only nuc2 has a cushion, which is why moving to a slower box reopens
ADR 7. Never re-render a book with a different engine/voice: durations change
and every timestamp — every index entry, every chapter mark, and the position
they went to sleep at — would be invalidated.

## Streaming ingest: pick a book and go

Asking for a book writes a row into a queue and answers at once. A separate
unit — `somnia worker` — takes the oldest waiting row while nothing else holds
a live lease, and spawns one child to render it. That is the whole of the
serialisation, and it is a property of the database rather than a convention:
the claim is a single guarded `UPDATE ... RETURNING`, so two books asked for a
millisecond apart cannot both start.

The pipeline emits **one m4a file per chapter** into the library folder as each
chapter finishes. A book is many files on one global timeline, so:

- listening can start when chapter one is rendered (minutes after picking)
- the semantic index grows chapter by chapter, so a book can be asked about
  while it is still being read — but it is not what keeps the ending back. A
  book is indexed whole on the evening it renders and listened to over the
  fortnight after, so from the second night on, the only thing between a
  question and the last page is the spoiler guard below
- per-chapter files are simultaneously the streaming unit, the re-render unit
  and — when there is no join to be had — the unit the phone fetches over HTTP
  (a single M4B would defeat all three)
- a chapter is also the unit a render can be **stopped and taken up again**
  at. The render asks between sentences and encodes a chapter on the last
  line, so a stop leaves no audio, no chunks and no row for the chapter it was
  in, and starting again picks up at the first chapter that has no row and
  carries the global clock on from where that one ended. Re-indexing a chapter
  replaces its passages rather than adding a second copy of every one of them,
  which is what makes any of that safe

All timestamps everywhere are **global milliseconds from book start**, on the
render clock — `chapters` rows carry each chapter's global start, so index hits,
the saved position and the player all speak it.
[Architecture](architecture.md) has the reason that is not what a decoder
reports.

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

A second library sits in the same FTS5 table — Project Gutenberg Australia,
which publishes no CSV and no API, only a text index meant for a person to
read, and whose ids are offset clear of Gutenberg's so that one integer goes on
meaning one book in the queue, the player and every saved position
([ADR 10](decisions/0008-a-second-library-under-the-same-ids.md)).

## Playback: the page is the player, and the position is somnia's own

This reverses the original design, which made the Audiobookshelf Android app
the player and a move a write to `PATCH /api/me/progress/:id`. It worked, and
it ended every move with "now press play again", because ABS has no transport
API and the app has no deep link. The argument, and the four ways of pressing
that button remotely that we turned down, are in
[ADR 3](decisions/0003-play-the-book-in-the-page.md); the losses are there too,
offline downloads chief among them.

**The page plays the book.** somnia rendered the audio, so serving it is a route
resolved from the `chapters` rows and never from a path in the request; Range,
`If-Range` and 416 — and therefore seeking — are Starlette's own. What holding
one clock costs the page is in [Architecture](architecture.md).

What the `<audio>` element is given used to be a chapter at a time, swapped at
every boundary; it is now the whole book joined into one file, and a boundary is
arithmetic that never touches the element.
[ADR 7](decisions/0007-cross-a-chapter-without-letting-go.md) has the argument
and the bill. The per-chapter route is still there and is still what plays when
there is no join to be had.

**Most of the transport is not on the page.** With the screen off the book is
driven from the lock screen, the notification shade and whatever is paired over
Bluetooth, all of which arrive through the Media Session API. The scrubber
published there is chapter-scale on purpose ([Architecture](architecture.md)
says why). That used to be belt and braces — the loaded file was a chapter
long, so the platform's own idea of the duration agreed with what the page
published. Now the element holds the whole book and the page's
`setPositionState` is the only thing saying otherwise, so the chapter-scale
scrubber is one uncaught exception away from being the whole-book one this
paragraph refuses.

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
instruction to jump.

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
position, and left the count below the one a still-open page was
holding: every report that page made for the rest of the night was refused, and
nothing was written again until it was reloaded.

**Nothing outside somnia is told where the book is.** A courtesy write to
Audiobookshelf survived the pivot and has since been dropped: it bought a
position nobody read, and it had already stopped running on the live box —
the token was commented out and nothing noticed
([ADR 9](decisions/0009-drop-audiobookshelf.md)). The row is the record, and
there is nothing anywhere else for it to disagree with.

**The spoiler guard is bounded by where the book is**, and by nothing else
([ADR 10](decisions/0010-draw-the-line-where-they-are.md)). `books.position_ms`
is the line, a book with no position is bounded at its start rather than left
unbounded, and there is no second number anywhere to keep in step with it.

It was a high-water mark until then — the furthest point ever played *through*,
raised only as far as sound really came out of the speaker, which every report
had to prove by counting the media clock. The argument for it was the rewind:
being taken back to chapter two must not un-hear chapters three to twenty. The
argument against it was what it cost to be sure. A report standing further past
the mark than it had playback to show for could not be credited, and after any
forward skip every report stands past a stretch nothing was heard over — so one
press of +30 stopped the mark for the rest of the book, and the gap in front of
it only grew. Every question afterwards was answered against the place they
last listened straight through, which after an evening of skipping is nowhere
near where they are, and the agent spent the night saying that things behind
them lay ahead.

So the rewind is paid for instead, and it is the cheaper of the two: a move
backwards really does make the stretch above them unsayable, and playing on
puts it back a minute at a time. A skip forward is taken as meant — somebody
who skips is somebody who decided to — and what it steps over goes with it.

A bounded search does not simply come back empty. It also runs unbounded and
says whether a closer match lies past the line — never what it is — which is
what lets the agent offer rather than shrug, and `find_passage(allow_spoilers)`
is the way through, asked for by them and by nobody else.

**The line is also how far the agent may speak**, which used to be a different
rule entirely. The prompt's strongest line was that everything said about a book
had to come from a tool result in this conversation, and it was doing two jobs
at once — the guard, and a fence against the model's own knowledge — by drawing
one fence around the retrieval. [ADR
6](decisions/0006-answer-a-question-about-the-book.md) takes them apart. The
agent may now answer a question about a book out of what it already knows, and
the line it may not cross is that one: everything behind it may be talked about
freely, nothing in front of it may be said at all, and a character who has not
appeared yet gets "he hasn't come up yet in what you've heard" and nothing after
that sentence. What may be *read* and what may be *said* are two different
distances — `allow_spoilers` moves the first and never the second, which was
always true and is now the sentence the paragraph turns on. The tool that
answers, `recall`, is bounded exactly as a search is, hands back no `id=` and no
`position_ms`, drops `better_ahead` rather than reporting it, and marks the turn
so that `move_to` and `offer_positions` both refuse: asking who somebody is used
to drag the audio to a passage about them, and it is the tools that stop it
rather than a paragraph asking them not to. What the tools cannot hold is the
turn where nothing was called at all — the line is a number the model only
learns by asking for it, so an answer given without looking is bounded by
nothing, where under the old rule it was impossible. That one the prompt has to
carry, and it does: look before you speak, and hardest on the question you are
sure you already know the answer to.

**What it offers is a list of places, not a question**, and
[ADR 4](decisions/0004-choose-a-place-from-a-list.md) has the whole argument:
the row, the cover-up, and why an offering turn writes nothing at all.

Every row's words travel with the answer that named them, which is why there is
no route anywhere that hands back the text of a chunk by id: that would be a
general way to read unheard book text, one guessed integer wide, sitting on the
server for the life of the deployment. `/api/passage/{gid}/{ms}` is the one
exception and proves the rule — addressed by a point on the book's clock rather
than by an identifier, and answering out of a statement whose own `WHERE`
carries `start_ms < position_ms`, so there is nothing to guess and no refusal to
read a frontier off.

## Getting through the night is the page's job now

Three things nothing absorbs on the page's behalf, and there is nothing else
left to absorb them. All three end the same way if they are not handled —
silence, with a notification that says paused — and none of them can be seen
without unlocking the phone, which is why each of them says what is happening
on the status line as well as doing something about it.

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
there silently. So the page reloads whatever it is holding — the joined book, or
a chapter in the fallback; assigning `src` is the whole of what makes an element
try again — from where they had got to rather than from the top of it, so five
seconds off the network costs five seconds and not the last ten minutes over
again. It waits longer each time, two seconds to
thirty, because a server that is down is down and a phone that retried flat out
until morning is a phone with no battery in the morning. Every route to a
reload goes on that same ladder, including the one that never sees an error at
all: a server that accepts the connection and answers nothing — a proxy black
hole, a re-key caught mid-handshake — leaves the element stalling rather than
failing, and a stall that reloads on a fixed timer stalls again off the new
source, for ever, at exactly the fixed cadence the ladder exists to prevent. It
stops entirely when they were the ones who stopped it, because a page reloading
audio under a book somebody put down is spending the battery on nobody. The
boot does the same thing for the same reason: the service worker serves the
shell when the server cannot be reached, which is right, and what they land on
otherwise is a page that looks perfectly alive with no book in it.

**The page itself dies.** A backgrounded tab is discarded whenever the phone
wants the memory back, and reloading is the first thing anyone does to a page
that looks stuck. The conversation is meant to die that way — it is keyed in
`sessionStorage` and starting fresh is the point — but an armed sleep timer is
an instruction about tonight that nobody has cancelled, so it is written to
`localStorage` as it counts down and restored with the minutes it had left.
Not a timer older than six hours: someone opening the book the next evening is
starting a night rather than finishing one, and a timer they could not remember
setting would end it early for no reason they could see.

**And the fade the timer ends on is written down for the same reason.** The
night ending by itself was the one fact about it nothing kept: the timer clears
itself on the way into the fade, and the fade then stops the book through the
ordinary path, which reports `pause` — the same word a thumb sends, and the only
word the server is ever told. So the page that opened in the morning could not
tell a book put down at eleven from one that faded out at 1:47, and it needed to
tell them apart twice over. Once for the rewind: how long the sound has been off
was held in a variable, in the tab the phone had discarded, so the longest rung
of that ladder — the one written for the night that ends with somebody asleep —
had never run in the case it was built for. And once for the morning itself,
which is a screen rather than a line over the player: the time the sound went at
the top of it, and under that the last places somnia found, the conversation,
and the position it would otherwise just keep. Twelve hours and no longer, on
the timer's argument said at a morning's distance instead of a night's.

How the lanes are kept apart, and why sqlite is in WAL with several writers, is
in [Architecture](architecture.md); that the renderer is a separate *unit* and
not merely a separate connection is
[ADR 5](decisions/0005-render-one-book-at-a-time.md).

## Agent surface

- Tool layer is a plain Python library: `list_books` (which names what is
  waiting to be rendered as well as what exists, since a book asked for
  tonight has no `books` row for hours), `search_catalog`, `add_book` (which
  writes a queue row and starts nothing, so what it can honestly say is where
  in the line the book landed), `find_passage` (places to be taken to, bounded
  by the guard unless they say otherwise), `recall` (the same search framed to
  be answered from, with no place in it and no way past the guard),
  `get_position` (reads somnia's own record of where they are), `move_to`
  (writes it, and counts the move so the page follows), and `offer_positions`
  (writes nothing, and puts several places on the screen for them to choose
  between). The model is never told to tell them to press play, because there is
  nothing to press. Which *book* they meant is still one short spoken question;
  which *passage* they meant never is; and whether they wanted moving or telling
  is the model's to judge, which it declares by which of the two searches it
  calls.
- 2am surface: the installed PWA, which is the player as well as the
  conversation, served over the tailnet. The server runs the agent loop
  (Anthropic Python SDK tool runner) with an API key held server-side — no
  OAuth. Voice input via the browser's Web Speech API (push-to-talk button);
  Android keyboard dictation as fallback.
- Model: **Haiku 4.5** default, `SOMNIA_AGENT_MODEL` to change it. It was the
  original choice on cost, lost the job for reading a character's name as the
  title of a book somnia does not have and saying so — a spoken half-sentence
  at 2am is exactly the disambiguation this is here to do — and Sonnet 5 held
  it for two months. **It has the job back, on measurement.** Over 85 turns per
  model on nuc2 (2026-08-08), against the real book and this prompt rather than
  the much softer one it was judged against then, Haiku routed 85/85 against
  Sonnet's 84/85, was judged spoiler-safe on 83/85 against Sonnet's 82/85, and
  answered in a median 2.46s against 4.89s — half the time, a fifth of the
  cost, on a screen where every second of the wait is felt. It did not
  reproduce the Rob Roy failure in five tries, which is not proof the failure
  is gone: if a name is ever read as a book title again, Sonnet is one
  environment variable away. See `somnia/config.py` for the table.
- **The spoiler guard is two things and only one of them is sound.** In that
  same run, retrieval never once crossed the line — checked mechanically, every
  passage handed to the model began before the line. What leaked, on both
  models, at two to four turns in a hundred, was the model's own knowledge of
  the book. That is precisely the surface ADR 6 opened when it let the agent
  answer out of what it already knows: everything behind the line is a prompt
  instruction, not a mechanism, and prompt instructions are followed most of
  the time. Worth knowing before trusting the guard absolutely, and not a
  reason to prefer either model.
- **How long a turn takes is almost entirely the model.** Retrieval is around a
  tenth of a second — the two searches, the sqlite-vec lookup and the embedding
  of the question all together — and the rest is round trips to Anthropic. So
  the levers are all on that side, in the order they are worth: the model
  itself (above), the constant half of the system prompt cached across hops,
  loading the embedding model at startup rather than inside whichever question
  needs it first, and `SOMNIA_AGENT_EFFORT` for the models that have such a
  dial. Haiku has not got one, so on the default that setting is not sent and
  changes nothing; on Sonnet it defaults to `medium` against the API's `high`
  and is worth about two seconds a turn. Turning thinking off altogether is
  faster again and is not done: a Sonnet 5 turn with no thinking can write its
  tool call into the reply as prose instead of calling the tool, which does not
  read as a failure — it reads as an answer.
- MCP server: designed for, never built, and nothing needs it. A FastMCP
  wrapper over the tool layer would be a dev-time convenience only — the 2am
  surface is the page, and the tools are a library any test can call directly.
  claude.ai custom connectors were rejected for v1 outright: they require a
  publicly reachable MCP endpoint plus OAuth, which conflicts with the network
  model below.

The whole HTTP surface is in [reference/http.md](../reference/http.md).
Everything the page fetches sits under `/api/`, which is not cosmetic: it is how
the service worker knows what never to cache, and it keeps those routes ahead of
the static mount at `/`.

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

Nothing is exposed publicly. The server binds to localhost (`--host` defaults to
`127.0.0.1`) and only `tailscale serve` can reach it, fronting the PWA with a
real TLS certificate on the node's `.ts.net` name. When
somnia ran on a shared experiment box, that box joined the tailnet **tagged**
(`tag:vps`) with the ACL never listing the tag as a source, so it could be
reached from personal devices and could never initiate a connection inward —
that one-way rule is what ruled out every remote-control route in
[ADR 3](decisions/0003-play-the-book-in-the-page.md). The certificate is not
optional either: an installable PWA, the Web Speech API and a media session all
require a secure context.

The whole night now goes over that path — the audio as well as the questions —
which is the price of the pivot: nothing is downloaded, so a tailnet that drops
at 3am takes the book with it.

## Deployment shape

- How it is installed and run is in
  [the installation tutorial](../tutorials/installation.md) — the package name,
  the `[ml]` extra and the CPU torch trap all live there. The one decision worth
  recording here is that the server and the renderer are **separate systemd user
  units**, `somnia-serve` and `somnia-worker`, so that restarting the process
  that serves the page cannot kill a render — which, before the worker existed,
  it silently did on every deploy
  ([ADR 5](decisions/0005-render-one-book-at-a-time.md)). Both units run on
  nuc2, a small home machine; the VPS this was first built on is stopped.
- Nothing else runs beside them. Audiobookshelf was a third unit — a rootless
  podman container under a dedicated user, with a `tailscale serve` of its own
  — until it was turned off on the box; the code caught up with that in
  [ADR 9](decisions/0009-drop-audiobookshelf.md).

## Test books

*Black Beauty* (gid 271) and *Crime and Punishment* (gid 2554) — both public
domain, both contain a dying horse, which is the canonical semantic-seek
query ("there are three horses that die in this — which one?").
