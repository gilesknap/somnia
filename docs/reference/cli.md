# Command line

Eleven commands. `somnia` on its own prints the help and stops, and `somnia
--version` prints the version and nothing else.

Results go to **stdout** and progress to **stderr**, so `somnia search bee >
books.txt` captures the books and leaves the logging in the terminal. Every
command loads the settings, creates `SOMNIA_DATA_DIR` if it is not there, opens
`somnia.db` and runs the migrations before it does anything else — including the
commands that then turn out to have nothing to do. A first run on a clean box
therefore leaves a database behind whatever else happens.

| Command | What it does | Needs |
|---|---|---|
| [`catalog-update`](#cli-catalog-update) | Download both Gutenberg catalogs | the network |
| [`search`](#cli-search) | Find a book id in those catalogs | a catalog |
| [`add`](#cli-add) | Ask for a book and render it here and now | `[ml]`, ffmpeg, espeak-ng |
| [`queue`](#cli-queue) | Ask for a book, see what is rendering, stop one | nothing |
| [`worker`](#cli-worker) | Empty the queue, one book at a time | `[ml]`, ffmpeg, espeak-ng |
| [`find`](#cli-find) | Semantic search inside one rendered book | `[ml]` |
| [`ask`](#cli-ask) | Put the agent in front of it | `ANTHROPIC_API_KEY` |
| [`serve`](#cli-serve) | The page that plays the book | `ANTHROPIC_API_KEY` |
| [`libraries`](#cli-libraries) | List Audiobookshelf library ids | `SOMNIA_ABS_TOKEN` |
| [`seed-positions`](#cli-seed-positions) | Take your place across from ABS, once | `SOMNIA_ABS_TOKEN` |

Settings come from the environment, and from nowhere else — there is no config
file and no flag that overrides one. They are listed in
[Configuration](configuration.md).

(cli-catalog-update)=
## `catalog-update`

```bash
somnia catalog-update
```

Downloads two lists and replaces the local catalog table with both of them:
the official Gutenberg CSV dump (~20MB, only rows of type `Text` with a title),
and [Project Gutenberg Australia](http://gutenberg.net.au)'s plain-text index
(~700KB, only books with an HTML edition).

```console
$ somnia catalog-update
catalog updated: 80494 books (76421 from Project Gutenberg, 4073 from Project Gutenberg Australia)
```

The second library is worth the extra request because it barely overlaps the
first: it clears books against Australian law rather than American, so about
four fifths of it is not in the Gutenberg catalog at all. Orwell's novels are
there, and Fitzgerald's uncollected stories, and several thousand pulp titles.
Its ids start at 900,000,000 so that they cannot collide with Gutenberg's own —
see [`search`](#cli-search) for what that looks like.

It **replaces**, rather than merges: the table is emptied first, so a run that
fails part way leaves you with what you started with, and a book that Gutenberg
has withdrawn disappears from your catalog too. Both downloads finish before
anything is written, so a library that is unreachable costs you the whole
update rather than half of one. Nothing else needs the network, so after this
the browsing is entirely offline.

:::{note}
Project Gutenberg Australia clears its books against **Australian** copyright
law, and says so: "it is possible that some eBooks which are public domain in
Australia are still under copyright protection in other countries." somnia does
not filter on that, and cannot — the index carries no author death dates. If
you are not in Australia, the check is yours to make.
:::

(cli-search)=
## `search`

```bash
somnia search QUERY [--language en]
```

Full-text search over titles, authors, subjects and bookshelves, returning **at
most ten** rows ordered by FTS rank. The `gid` in the first column is the only
handle the rest of somnia uses.

```console
$ somnia search "black beauty"
       271  Black Beauty — Sewell, Anna
$ somnia search "nineteen eighty-four"
 910100021  Nineteen eighty-four — George Orwell  [PG Australia]
```

Both libraries answer one search, because the question is "what can I listen to
tonight" and that has one answer. The library is named only when it is the
Australian one: every line saying "Project Gutenberg" would be a column of
noise, and a nine-digit id is the other tell.

Words are ANDed: every term has to appear somewhere in the row. Punctuation is
dropped rather than interpreted, so an apostrophe cannot produce a syntax error,
and single-character fragments — the `s` left by a possessive — are thrown away
instead of being required. `--language` is an exact match against the catalog's
language code, and it defaults to `en`; there is no way to ask for all
languages at once.

No results usually means no catalog: run [`catalog-update`](#cli-catalog-update).

(cli-add)=
## `add`

```bash
somnia add GID [--voice af_heart]
```

Puts the book in the [queue](#cli-queue) and then renders the head of the line
in this process: fetches from Gutenberg, renders every chapter with Kokoro, and
indexes each one the moment it is finished. This is the command that takes
hours, and one of the two that need the `[ml]` extra, ffmpeg and espeak-ng.

```console
$ somnia add 271
Black Beauty is next to be rendered.
2026-08-06 21:04:11 INFO claimed job 7: book 271
2026-08-06 21:04:11 INFO rendering chapter 1/49: 01. My Early Home
2026-08-06 21:09:38 INFO rendering chapter 2/49: 02. The Hunt
...
2026-08-07 02:31:55 INFO finished Black Beauty: 49 chapters, 6.2 hours
```

It takes the **same claim** the worker's child takes, so it is not a second
renderer: if something else is already rendering it says so in the first second
and stops, leaving the book in the line for the worker to reach.

```console
$ somnia add 120
Treasure Island is in the queue, behind one other book.
Something else is being rendered, so this one waits its turn. Run `somnia
queue` to see the line.
```

Two consequences of going through the queue. A book somnia already has in full
is refused, and nothing is rendered — this command was asked about one book and
has no business spending six hours on another; use
[`worker --once`](#cli-worker) to drain the line by hand. And what it renders
is the head of the line, which is the book you named unless you had already
asked for others, so read the `claimed job` line if you care which.

Ctrl-C stops it the way a `queue stop` does: at the end of the sentence it is
speaking, leaving every finished chapter playable, and the book goes back into
the queue rather than being cancelled — nobody stopped wanting it.

Audio lands in `SOMNIA_LIBRARY_DIR/<author>/<title>/NNN - <chapter>.m4a`, and
the database row is what everything else reads: chapters are never served by
path. The book is marked `rendering` at the start and `done` at the end, which
is how the page knows the difference between a book that is still growing and a
render that died.

`--voice` overrides `SOMNIA_VOICE` for this render only. **Never re-render a
book with a different voice.** Every timestamp somnia holds — chapter marks,
index entries, the place you fell asleep — belongs to the audio that was
actually produced.

Re-running it on a book it has already rendered is the ordinary way to finish
one that died, and it **resumes**: it starts at the first chapter that has no
row — the first missing one, not the one after the highest, so a hole in the
middle is filled rather than stepped over — and carries the global clock on
from where that chapter ended. Re-indexing a chapter replaces its passages
rather than adding a second copy of every one of them. Both of those were
[#11](https://github.com/gilesknap/somnia/issues/11), and both are fixed.

The one case that starts from zero is a book whose chapter *count* has changed
since it was last rendered, which means Gutenberg has re-issued the text.
Chapter four of one edition is not chapter four of another, so the old
chapters, chunks and vectors are dropped and the book is rendered again from
the start; it says so in a warning naming both counts.

What it does not touch is where you have got to. A re-render writes the title,
the authors, the voice and the status, and nothing about your position or how
far you have heard.

If `SOMNIA_ABS_TOKEN` and `SOMNIA_ABS_LIBRARY_ID` are both set, Audiobookshelf
is rescanned and given chapter marks after each chapter. A failure there is
logged and the render carries on.

(cli-queue)=
## `queue`

```bash
somnia queue [list]
somnia queue add GID
somnia queue stop ID
```

The ingest queue: what is being rendered, what is waiting behind it, and what
died overnight. `somnia queue` on its own prints it, and needs nothing but the
database — no key, no network, no `[ml]`.

```console
$ somnia queue
   1  rendering       Black Beauty — Sewell, Anna, 1820-1878  (chapter 4 of 49)
   2  1st in line     Treasure Island — Stevenson, Robert Louis
   3  cancelled       Moby Dick — Melville, Herman
```

The first column is the **job id**, and it is what `stop` takes. It is not the
Gutenberg id: a book can be queued, stopped and asked for again, and each of
those is a separate row, so stopping by book would be ambiguous about which
attempt you meant.

The second column is the whole state of the thing:

| Word | What it means |
|---|---|
| `rendering` | A renderer holds this book and said so within the last five minutes |
| `not responding` | It still holds it, but has not said anything for five minutes |
| `stopping` | It has been asked to stop and will, at the end of the sentence it is on |
| `Nth in line` | Waiting, with N−1 books ahead of it |
| `done` | Rendered, all of it |
| `cancelled` | Somebody stopped it |
| `failed` | It broke, and the reason is in brackets at the end of the line |

`not responding` is worked out when you look, from the last heartbeat, and is
stored nowhere — so it is honest even when the renderer has been stopped
altogether and there is nobody left to write anything down. The chapter number
in brackets is the one being worked on, which is the same number the renderer
logs as `rendering chapter 4/49`.

Rows that have ended drop off after **24 hours**. There is nothing to press to
make one go away: after a day a failure is history rather than news, and
history is in the journal.

`somnia queue add GID` asks for a book. It writes a row and returns at once —
there is no network in it — so an id Gutenberg has never heard of is accepted
here and fails later, with a sentence saying so, rather than making you wait
three seconds to be told no.

```console
$ somnia queue add 120
Treasure Island is in the queue, behind one other book.
```

The name comes from the **local catalog**, so a book queued before
[`catalog-update`](#cli-catalog-update) has ever run reads as `book 120` in the
list. That is cosmetic and nothing else depends on it. Two refusals: a book
that is already queued or already rendering, and a book somnia has rendered in
full. A render that died, was stopped, or was killed by a reboot is **not**
refused — asking again is how you retry one, and that was impossible before
this command existed.

`somnia queue stop ID` takes a book out of the line, or asks a running render
to stop.

```console
$ somnia queue stop 2
Treasure Island has been taken out of the queue.
```

A book that was only waiting goes immediately. A render that is running is only
*asked*: nothing signals it and nothing kills it, so it reads to the end of the
sentence it is on and stops on the next chapter boundary, which can take about
twenty seconds. Every chapter it had already finished stays exactly where it
is, and stays playable.

What empties the queue is [`worker`](#cli-worker), and if nothing is running it
nothing renders: rows sit there with their place in line and the readout says
so honestly. See [Keep a long render
running](../how-to/keep-renders-running.md) for the unit that runs it.

(cli-worker)=
## `worker`

```bash
somnia worker
somnia worker --once
```

Empties the queue, one book at a time, and is meant to be a systemd user unit
rather than something you type. It reconciles whatever the last crash left
behind, then loops: if a book is waiting it spawns a child — `somnia worker
--once` — and waits for it, and either way it sleeps ten seconds and looks
again.

The supervisor itself imports nothing expensive. Kokoro and the embedder live
in the child, which exits between books and takes every megabyte with it, and
the child's stdout and stderr are **inherited**, so its chapter lines and any
traceback land in the journal:

```console
$ journalctl --user -u somnia-worker -f
INFO worker watching /home/reader/.local/share/somnia/somnia.db: 1 requeued, 0 given up on, 1 books freed
INFO claimed job 7: book 271
INFO rendering chapter 1/49: 01. My Early Home
```

`--once` claims the next book, renders it and exits — which is also what
`somnia add` does after submitting, under the same claim. Use it to drain the
line by hand without asking for anything new. If something else is already
rendering it claims nothing and exits at once, saying so at INFO.

`SIGTERM` — which is what `systemctl --user stop` sends — stops the render at
the end of the sentence it is speaking, puts the book **back in the queue**
rather than cancelling it, and exits. Nobody stopped wanting the book, so the
next worker to start picks it up at the chapter after the last one that
finished. The chapter that was in flight is lost, deliberately: the child will
not gamble on finishing a chapter inside a stop timeout, because a chapter
killed part way through the encode is the one death that can leave the index
holding words the player cannot see.

A render that is interrupted this way is retried, bounded at **three**
attempts, after which the job is failed with a sentence saying it was
interrupted three times. A child that dies without recording anything — an OOM,
a SIGKILL, a segfault underneath — is failed straight away with its exit code
in the sentence, and never retried: a real error recurs, and a queue that
spends the night failing the same book is worse than one that stops and says
why.

(cli-find)=
## `find`

```bash
somnia find GID QUERY
```

Semantic search within one rendered book: the **five** nearest passages, closest
first.

```console
$ somnia find 271 "the horse is beaten in the street"
[2:47h  d=0.284] 32. A Horse Fair
    A poor old brown horse was there... he was being beaten about the head
    while the crowd looked on.
```

The bracket holds the position in the book and `d`, the embedding distance —
smaller is closer. Concrete events, characters and places search well;
atmosphere ("the bit that felt strange") does not, and that is a known
limitation rather than a bug.

`find` searches the **whole** book. It is the raw index, so it has no spoiler
guard: [`ask`](#cli-ask) is where that lives.

(cli-ask)=
## `ask`

```bash
somnia ask "which chapter is the one with the horse fair?"
somnia ask
```

Puts the agent in front of the index. With a question it answers and exits;
with none it prompts with `>` until you give it a blank line. Its own logging
is turned down to warnings so that it does not drown one-line answers.

Answers are bounded by the furthest point somnia has ever *played* — and from a
terminal it has played nothing, so the bound is the opening of the book. What
you get is that the passage lies further on than you have got, and an offer to
go there anyway. That is the spoiler guard working, not a fault. Say yes and it
searches the whole thing.

The key comes from `ANTHROPIC_API_KEY`, which is the Anthropic SDK's own
variable, so a key already exported for other tools is picked up here.

(cli-serve)=
## `serve`

```bash
somnia serve [--host 127.0.0.1] [--port 8721]
```

Serves the player, the agent behind it and the audio itself. It runs in the
foreground; `curl localhost:8721/api/health` answers `{"ok": true}`.

**Leave `--host` on localhost.** There is no login of any kind — reachability is
the authentication, and the only path in is meant to be `tailscale serve`. See
[Serve the page that plays the book](../how-to/serve-the-chat-page.md).

(cli-libraries)=
## `libraries`

```bash
somnia libraries
```

Prints the id and name of each Audiobookshelf library, which is where
`SOMNIA_ABS_LIBRARY_ID` comes from.

```console
$ somnia libraries
lib_8x2k1p9  Audiobooks
```

It needs `SOMNIA_ABS_TOKEN` and a reachable server; without them it fails rather
than returning nothing.

(cli-seed-positions)=
## `seed-positions`

```bash
somnia seed-positions
```

The one command that reads Audiobookshelf. Run it once, by hand, before the
first night, if you have been listening in ABS: it brings each book's position
and how far you had heard into somnia's own database.

```console
$ somnia seed-positions
   271  Black Beauty: seeded at 3:12:40 (2026-08-01 22:41:03); heard to 3:12:40
1 of 1 books changed.
```

It says what it did to every book, in a sentence, because the only person
running it is watching a terminal and deciding whether to trust the night to it.
Two rules make it safe to run again: a position somnia already holds is never
overwritten, and the heard-to mark only ever rises.

With no token it says there is nothing to read and stops. If Audiobookshelf
cannot be reached it says so and changes nothing — every read happens before the
first write, so an interrupted run really did leave the database alone.

## When something goes wrong

These are not polished-failure commands. Beyond the two cases
`seed-positions` handles by hand, a missing key, an unreachable server or a book
Gutenberg does not have will end in a traceback and a non-zero exit.

`somnia-doctor.sh` is the thing to run first: it checks the install, the
settings, the catalog, and that every rendered chapter is still on disk and
still inside `SOMNIA_LIBRARY_DIR` — the failure that otherwise reaches you at
2am as one chapter that didn't arrive.
