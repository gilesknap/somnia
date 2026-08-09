# Architecture

What the pieces are and how a night flows through them. This is the map;
[design.md](design.md) is the argument for why the map looks like this, and the
[ADRs](decisions.md) record the turns that were taken.

## The shape of it

somnia renders public-domain books to audio itself, and that one decision pays
for everything else. Because the renderer placed every sentence, it knows
exactly which span of audio each sentence occupies — so the text/audio index is
free, and a question at 2am can be answered with a timestamp rather than a
guess.

Three things run. The two on the box share one sqlite file and the audio on
disk; the third is on the phone and reaches both over HTTP:

- **the renderer** (`somnia worker`) — a supervisor that takes one book at a
  time off the queue and spawns a child to turn a Gutenberg id into per-chapter
  m4a files plus a semantic index, streaming chapter by chapter
- **the server** (`somnia serve`) — serves the page, the audio, the catalog,
  the queue and the agent
- **the page** (the installed PWA) — plays the book, picks the next one, and
  carries the conversation

The renderer is a separate unit from the server on purpose, and
[ADR 5](decisions/0005-render-one-book-at-a-time.md) has the argument:
restarting the page's process, which is what a deploy is, must not kill a
render, and Kokoro must never compete with a seek for two cores.

```mermaid
flowchart TB
  subgraph Phone["Phone — installed PWA"]
    ms["Media Session<br>lock screen, Bluetooth"] --- page["app.js<br>one audio element,<br>one global-ms timeline"]
  end

  ts["tailscale serve<br>TLS, and the only way in"]

  subgraph VPS["VPS — nothing public"]
    serve["somnia serve"]
    player["Player<br>fast lane"]
    agent["Conversation<br>agent lane"]
    worker["somnia worker<br>supervisor, no torch"]
    ingest["somnia worker --once<br>renderer, one book"]
    db[("somnia.db")]
    files[/"library dir<br>.m4a per chapter"/]
    joins[/"data dir<br>chapters joined,<br>one .m4a per book"/]
  end

  api["Anthropic API"]
  gut["Project Gutenberg"]
  abs["Audiobookshelf"]

  page <--> ts
  ts --> serve
  serve --> player & agent
  agent --> api
  agent -.->|"queues a book"| db
  worker -->|"claims one, spawns"| ingest
  worker --> db
  gut -->|"book HTML"| ingest
  player --> db & files
  files -->|"joined on the first ask,<br>-c copy"| joins
  player --> joins
  agent --> db
  ingest --> db & files
  player -.->|"only when they stop"| abs
  ingest -.->|"rescan, chapter marks"| abs
```

The dotted edges are the ones the page never waits on. Audiobookshelf is
**written to and, while a night is running, never read** — it is somewhere else
the book might be opened, not the record of anything, and a write that fails is
logged and forgotten. The single exception is `somnia seed-positions`, which
reads it once by hand before the first night and never again. Asking for a
book — from the panel or by voice — writes a queue row and nothing else, so the
answer comes back at once and the render happens in the other unit entirely,
minutes or hours later. That is how a book gets added at 2am without anything
waiting for it — and how two books asked for a minute apart cannot both be
rendering, because the worker claims one at a time and the claim is a single
guarded UPDATE.

There is no login anywhere. Reachability *is* the authentication: the server
binds to localhost, and only `tailscale serve` can reach the port. The box it
runs on joins the tailnet **tagged**, and the ACL never lists that tag as a
source, so it can be reached by personal devices and can never initiate a
connection into the tailnet.

## One clock

Every timestamp in somnia — index hit, chapter mark, saved position, what the
page shows, what ABS is told — is **global milliseconds from the start of the
book**. It is the render clock, counted in PCM samples before encoding, and
never what a decoder reports: summing durations off the files drifts tens of
milliseconds a chapter and is a second out by chapter forty.

The page converts between that clock and the clock of whatever the audio element
is actually holding, in four small functions, and that is the only place the
split exists. When the element holds the whole book joined into one file — the
ordinary case, and the reason a chapter boundary no longer takes the lock screen
down ([ADR 7](decisions/0007-cross-a-chapter-without-letting-go.md)) — the
conversion is the identity, measured on the real forty-nine chapter book rather
than assumed. When it holds a single chapter, which is the fallback, the
conversion is `(chapter index, seconds into this file)`. Either way "back a bit"
from the start of chapter five lands in chapter four, the way a listener means
it.

## Making a book

Asking for a book writes a row into `queue` and returns.

Two things ask. The agent, in a sentence, when somebody says a title out loud;
and the page's own panel, which searches the catalog on disk, offers a voice,
and posts a gid. Both end in the same `queue.submit` and both get the same
sentence back, so the page and the voice cannot disagree about what just
happened.

The worker claims the oldest waiting row — while nothing else holds a live
lease — and spawns a child that streams it: each chapter is written into the
library folder and indexed the moment it finishes, so listening can start
minutes after picking a book while the rest arrives overnight.

```mermaid
flowchart TD
  Q[("queue row<br>claimed under a lease")] --> A
  A["fetch_book — Gutenberg HTML edition"] --> B["parse_book_html<br>chapters of paragraphs"]
  B --> T["books.chapters_total written<br>the only honest denominator"]
  T --> R{"chapters already on disk?"}
  R -->|"yes"| S["resume at the first missing one,<br>carrying the global clock on"]
  R -->|"no"| C
  S --> C

  subgraph loop["for each chapter"]
    C["sentences — pysbd"] --> P{"beat: still ours,<br>and not cancelled?"}
    P -->|"no"| X["stop here — this chapter<br>leaves no trace at all"]
    P -->|"yes"| D["engine.render — Kokoro-82M<br>one sentence at a time"]
    D --> E["ChapterAudio<br>+120ms between sentences<br>+500ms between paragraphs<br>clock counted in samples"]
    E --> F["ffmpeg → 'NNN - Title.m4a'<br>AAC 64k, faststart"]
    E --> G["TimedSentence[]<br>exact global start and end"]
    G --> H["windows — 3 sentences, stride 2"]
    H --> I["Embedder — e5-small-v2, 384-dim"]
  end

  I --> J[("chunks + vec_chunks")]
  F --> K[("chapters row<br>idx, start_ms, end_ms, audio_file")]
  K --> L["books.total_ms bumped<br>status stays 'rendering'"]
  F --> M["ABS rescan, then set_chapters"]
  L --> N["listenable now — the page re-asks<br>for the manifest while status is 'rendering'"]
```

Rendering per **sentence** rather than per chunk or per paragraph is what makes
the timestamps exact by construction, and it is why the engine is swappable:
anything that can render one sentence satisfies the `TTSEngine` protocol. It is
also where a stop is allowed to happen, and nowhere else: a chapter is encoded
on the last line of rendering it, so a render stopped between sentences leaves
no m4a, no chunks and no chapters row for the chapter it was in — which is what
makes the window between indexing a chapter and writing its row unreachable,
and therefore what makes cancelling and resuming safe at all.

Never re-render a book with a different engine or voice. Durations change, and
every timestamp — every index entry, every chapter mark, and the position they
went to sleep at — is invalidated. Which voice a book gets is therefore settled
once, on the queue row, at the moment somebody asks for it; the renderer prefers
that, then the voice already on the book, then its own configuration, so neither
a deploy nor a resume can change a narrator half way through.

Each chapter opens by saying what it is — *Chapter 12. The Invisible Man* — and
that line is built from the heading rather than being the heading: roman
numerals are converted, capitals are taken out, and a heading with no number in
it is spoken without one, because somnia's chapter *index* counts what the
parser found and is not what the book calls the chapter. It is rendered before
the first sentence's clock is read, so it costs the timestamps nothing, and it
is deliberately not indexed — it is not the book's text.

## What is stored

One sqlite file holds all of it: the catalog for browsing, the books and their
chapter timelines, the indexed text windows, and the vectors.

```mermaid
erDiagram
  catalog {
    text gid "FTS5, ~80k rows"
    text title
    text authors
  }
  catalog_urls {
    int gid PK "only where the address is not computable"
    text url "Project Gutenberg Australia"
  }
  books {
    int gid PK
    text title "the catalog's name; the scrape only if it has none"
    text status "pending, rendering, done"
    int total_ms "grows while rendering"
    int chapters_total "how many it HAS; 0 = unknown"
    int heard_to_ms "high-water mark"
    int position_ms "nullable: never started"
    int position_seq "agent moves only"
    text position_at "last report taken, or opened; newest is last_gid"
    text abs_item_id
  }
  queue {
    int id PK
    int gid "one live row per book"
    text state "queued, rendering, done, cancelled, failed"
    int cancel "asked to stop"
    text lease "uuid4 of the renderer, never a pid"
    int pid "which process claimed it"
    text beat_at "liveness, read at read time"
    text chapter_at "a second clock: long chapter vs dead process"
    int attempts "bounded at three"
    text error "one plain sentence"
  }
  chapters {
    int book_gid PK, FK
    int idx PK
    text title
    int start_ms "global"
    int end_ms "global"
    text audio_file "never sent to the page"
  }
  chunks {
    int id PK
    int book_gid FK
    int chapter_idx
    int start_ms "global"
    int end_ms "global"
    text text "3-sentence window"
  }
  vec_chunks {
    int rowid PK "= chunks.id"
    blob embedding "float[384], sqlite-vec"
  }

  books ||--o{ chapters : "timeline"
  books ||--o{ chunks : "index"
  chunks ||--|| vec_chunks : "rowid"
  books ||--o{ queue : "every time it was asked for"
```

`queue` has no foreign key to `books`, and that is not an oversight: a book is
asked for before it exists, and its `books` row is not written until the parse
finishes. A partial unique index on `gid` over the waiting and rendering states
is what keeps one live job per book — enforced by the database rather than by a
check that two presses a millisecond apart would both pass.

A book is a few thousand windows, so brute-force exact nearest-neighbour search
is milliseconds. No database server, no shared infrastructure. The file is in
WAL mode because several writers exist — an agent turn, the player, the queue
panel, the worker, and a render running in another process entirely — and a
reader must never block on any of them. That the render is in another process
is also why the queue lives in this file rather than in a lock file or a
socket: sqlite is the one thing every process in somnia already shares, so a
render's progress and the request to stop it need no channel of their own.

`chunks` earns a second job it was not designed for: because its rows are
overlapping windows taken every second sentence, a window start is always a
sentence start. That is how the page's long rewind lands on the beginning of a
sentence rather than the middle of a clause.

## A night

Serving audio and answering questions are separate lanes. A model turn blocks
for tens of seconds on the API and on the embedder, and a seek must never queue
behind it — a dead player while a question is being answered is exactly the
moment the phone gets put down. So `Player` has its own sqlite connection, its
own lock and its own ABS client, and shares nothing with a conversation but the
file on disk.

The queue panel is a third lane in the same shape, and it is the same argument a
second time: a submit button that sits there for twenty seconds because somebody
happened to ask a question is exactly the dead control this arrangement exists
to refuse.

```mermaid
sequenceDiagram
  autonumber
  participant P as Page
  participant PL as Player
  participant AG as Agent
  participant DB as somnia.db
  participant AN as Anthropic

  Note over P: cold launch
  P->>PL: GET /api/books
  PL-->>P: last_gid
  P->>PL: GET /api/book/{gid}
  PL-->>P: timeline, position, heard_to_ms
  P->>PL: GET /api/audio/{gid}/{idx}, Range

  loop every 15s, and at every jump and stop
    P->>PL: position_ms, seq, played_ms
    PL->>DB: UPDATE ... WHERE position_seq = ?
    PL-->>P: accepted, heard_to_ms
  end

  Note over P,AN: "where does the horse die?"
  P->>AG: POST /api/ask
  AG->>AN: tool runner turn
  AN->>AG: find_passage
  AG->>DB: search, bounded at heard_to_ms
  AN->>AG: move_to
  AG->>DB: position_seq + 1
  AG-->>P: reply, and where to go
  P->>P: jump there and play

  alt that reply never arrives
    P->>PL: next report, stale seq
    PL-->>P: 200 refused — go here instead
    P->>P: jump anyway
  end
```

The asymmetry in step 7 is the whole protocol. `position_seq` counts **agent
moves and nothing else**; the page's own reports leave it alone. So a report
carrying a stale count can only mean the agent moved the book, and the refusal
that comes back is also where to go instead. That is why a refusal is a 200
with a body rather than a 409: the last report of the night is a `sendBeacon`,
and a beacon can read nothing else.

Only the player and an agent move may write those four columns; what ingest may
touch, and the one-off `somnia seed-positions` that never lowers a position, are
in [design.md](design.md).

## How far a question may see

The spoiler guard is bounded by the **furthest point ever played through**, not
by where they are now, because the agent can move the position anywhere. Only
the page can tell a skip from a stretch of listening, so every report says how
much audio really came out of the speaker since the last one taken.

```mermaid
flowchart TD
  R["a report arrives: position_ms, and the playback behind it"] --> C{"is it backed by playback that really happened?"}
  C -- yes --> U["the mark rises to position_ms"]
  C -- no --> K["the mark stands — a skip is not listening"]
  U --> S["a search is bounded at the mark + 60 seconds"]
  K --> S
  S --> Q{"does a closer match lie past the bound?"}
  Q -- yes --> O["say it is ahead of them and offer to go —<br>never what happens there"]
  Q -- no --> A["answer from what they could have heard"]
```

The comparison allows five seconds of slack, and takes the smaller of the
playback claimed and the wall clock since the last accepted report. The clock is
a ceiling on the claim, not the answer to it: a phone asleep in a pocket for
eight hours banks eight hours of clock and no listening at all. Because the
playback appears on both sides of the comparison, the slack *is* the largest
jump that can be laundered as listening — which is why it sits well below
thirty seconds, the smallest forward jump the page has a button for. Two costs
are accepted, and [design.md](design.md) argues both.

The mark bounds what is *said* as well as what is searched, and those are two
different distances. The agent may answer a question about a book out of what it
already knows of it, as far as that line and no further
([ADR 6](decisions/0006-answer-a-question-about-the-book.md)); `allow_spoilers`
lets it read past the line to pick the right place to send somebody, and never
lets it describe what it read. The question tool, `recall`, is bounded by the
same code as a search and marks the turn so that `move_to` and
`offer_positions` refuse — a question must not cost the listener their place.

## What the page has to survive

Three things the Audiobookshelf app used to absorb, which nothing absorbs any
more. All three end the same way if unhandled — silence, under a notification
that says paused — and none can be seen without unlocking the phone, so each
also says what is happening on the status line.

| What happens | What the page does |
|---|---|
| The book grows while it is playing | Re-asks for the manifest while `status` is `rendering` — when the audio runs out, and when the app comes back in front of them — backing off from 5s to a minute. Only the timeline is adopted; the position in the answer is its own report come back late. |
| The tailnet drops for a few seconds | Reassigns `src` to reload whatever it is holding — the joined book, or a chapter in the fallback — *from where they had got to*, on a ladder from 2s to 30s. Every route to a reload uses that ladder, including a stall that never raises an error. It stops entirely when they were the ones who stopped it. |
| The page is discarded | The conversation is meant to die — it is keyed in `sessionStorage`. An armed sleep timer is not, so it is written to `localStorage` as it counts down and restored with the minutes it had left, unless it is more than six hours old. |

Most of the transport is not on the page at all. With the screen off the book
is driven from the lock screen, the notification shade and whatever is paired
over Bluetooth, all arriving through the Media Session API. The scrubber
published there is chapter-scale on purpose: a whole-book scrubber on a
twelve-hour novel gives three minutes to the pixel, and one sleepy thumb would
fling them past the spoiler guard into the ending.

## The modules

| Module | Job |
|---|---|
| `catalog` | Both libraries' published lists in one FTS5 table — browsing is offline, with no third-party API |
| `pgau` | Project Gutenberg Australia's plain-text index, and the offset ids that keep it out of Gutenberg's way |
| `gutenberg` | Fetch the HTML edition, parse it into chapters of paragraphs |
| `segment` | Sentences (pysbd), and the overlapping windows the index is built from |
| `announce` | The line a chapter opens with, built from the heading rather than being it |
| `tts` | The `TTSEngine` protocol, and Kokoro-82M behind it |
| `voices` | The six voices a book may be read in, kept out of `tts` so the process answering the page need not import torch |
| `audio` | Accumulate a chapter's samples, track the clock, encode via ffmpeg |
| `embed` | e5-small-v2, with the asymmetric `query:` / `passage:` prefixes |
| `index` | Store chunk embeddings; search one book, optionally bounded |
| `ingest` | The streaming pipeline that joins all of the above — resumable, stoppable |
| `queue` | The ingest queue as pure functions: submit, claim, beat, stop, reconcile |
| `worker` | The supervisor and the one-book child that holds the lease |
| `db` | The schema, the migrations, the one-off repairs, WAL, and loading sqlite-vec |
| `tools` | Everything the agent can do, as a plain library with no Anthropic import |
| `agent` | The system prompt and the tool-runner loop |
| `player` | The fast lane: manifest, audio files, position reports |
| `stream` | The chapters joined into one file per version, so a boundary touches nothing |
| `server` | Starlette routes, conversation storage, the mounted page |
| `abs` | The Audiobookshelf client — a courtesy write and one seed-time read |
| `config` | Where everything is and what it is set to, from the environment |
| `seed` | The one-off read of Audiobookshelf, before the first night |
| `web/` | The PWA: `index.html`, `app.js`, `sw.js`, the manifest and icons |

## The HTTP surface

Everything the page fetches sits under `/api/`, which is not cosmetic: it is
how the service worker knows what never to cache, and it keeps these routes
ahead of the static mount that would otherwise swallow them.

Which lane a route belongs to is the same split as everywhere else: `/api/ask`
and `/api/forget` are the agent's, the manifest, the audio and the position
reports are the player's, and the catalog, the voices and the queue are the
third's. What each one answers is in [the HTTP reference](../reference/http.md);
`/` is the page itself, served straight off the installed package.

A chapter or a stream is named by a book and a number, never by a path. A
chapter's file comes from its `chapters` row and is refused if it resolves
outside the library directory; a stream's name is two integers under the data
directory, and it is built only from chapters that passed that same check. That
is the whole traversal defence, and it has to be, because the server has no auth
by design.
