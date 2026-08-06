# Command line

Nine commands. `somnia` on its own prints the help and stops, and `somnia
--version` prints the version and nothing else.

Results go to **stdout** and progress to **stderr**, so `somnia search bee >
books.txt` captures the books and leaves the logging in the terminal. Every
command loads the settings, creates `SOMNIA_DATA_DIR` if it is not there, opens
`somnia.db` and runs the migrations before it does anything else — including the
commands that then turn out to have nothing to do. A first run on a clean box
therefore leaves a database behind whatever else happens.

| Command | What it does | Needs |
|---|---|---|
| [`catalog-update`](#cli-catalog-update) | Download the Gutenberg catalog | the network |
| [`search`](#cli-search) | Find a book id in that catalog | a catalog |
| [`add`](#cli-add) | Render and index a book | `[ml]`, ffmpeg, espeak-ng |
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

Downloads the official Gutenberg CSV dump (~20MB) and replaces the local
catalog table with it. Only rows of type `Text` with a title are kept.

```console
$ somnia catalog-update
catalog updated: 76421 books
```

It **replaces**, rather than merges: the table is emptied first, so a run that
fails part way leaves you with what you started with, and a book that Gutenberg
has withdrawn disappears from your catalog too. Nothing else needs the network,
so after this the browsing is entirely offline.

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
```

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

Fetches the book from Gutenberg, renders every chapter with Kokoro, and indexes
each one the moment it is finished. This is the command that takes hours, and
the only one that needs the `[ml]` extra, ffmpeg and espeak-ng.

```console
$ somnia add 271
2026-08-06 21:04:11 INFO rendering chapter 1/49: 01. My Early Home
2026-08-06 21:09:38 INFO rendering chapter 2/49: 02. The Hunt
...
2026-08-07 02:31:55 INFO finished Black Beauty: 49 chapters, 6.2 hours
```

Audio lands in `SOMNIA_LIBRARY_DIR/<author>/<title>/NNN - <chapter>.m4a`, and
the database row is what everything else reads: chapters are never served by
path. The book is marked `rendering` at the start and `done` at the end, which
is how the page knows the difference between a book that is still growing and a
render that died.

`--voice` overrides `SOMNIA_VOICE` for this render only. **Never re-render a
book with a different voice.** Every timestamp somnia holds — chapter marks,
index entries, the place you fell asleep — belongs to the audio that was
actually produced.

Two things to know before re-running it on a book it has already rendered:

- It starts again at chapter one. There is no resume; each chapter is rendered
  and its file overwritten, so a render that died at chapter 40 costs you those
  40 chapters again.
- The index gains a **second copy** of every passage, because chapters are
  replaced but chunks are only ever inserted. Searches still work; they just
  return the same passage more than once. Both are
  [#11](https://github.com/gilesknap/somnia/issues/11).

What it does not touch is where you have got to. A re-render writes the title,
the authors, the voice and the status, and nothing about your position or how
far you have heard.

If `SOMNIA_ABS_TOKEN` and `SOMNIA_ABS_LIBRARY_ID` are both set, Audiobookshelf
is rescanned and given chapter marks after each chapter. A failure there is
logged and the render carries on.

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
