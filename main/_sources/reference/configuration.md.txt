# Configuration

Every setting is an environment variable. There is no configuration file and no
precedence to learn: a variable that is set wins over the default, and that is
the whole of it. One flag overrides a setting for a single run: `add --voice`,
which shadows `SOMNIA_VOICE` and is written on the queue row rather than on the
process, so it survives whichever renderer gets there. `serve --host/--port` has
no variable behind it at all — the defaults are `127.0.0.1` and `8721`, and they
live in the command.

`~/somnia.env` is the conventional place to keep them, and what the installer
writes and the how-to guides assume. Your shell reads it with `source`; a
systemd unit reads it with `EnvironmentFile=`. **systemd does no variable
expansion**, so write paths out in full: `/home/you/library` and not
`$HOME/library` or `~/library`.

## Read from the environment

| Variable | Default | What it is |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | The agent's model calls. Required by `ask` and `serve`, and by nothing else |
| `SOMNIA_DATA_DIR` | `$XDG_DATA_HOME/somnia`, else `~/.local/share/somnia` | Holds `somnia.db`, and `streams/<gid>/<n>.m4a` — a book's chapters joined into the one file the page plays, `n` being how many chapters it covers. A rebuildable cache and the largest thing in here: about the library again, more if a book opened mid-render left shorter joins behind, since none are reaped. Created on startup if it is not there |
| `SOMNIA_LIBRARY_DIR` | `~/library/audiobooks` | Where rendered chapters are written, and the boundary outside which the server refuses to serve one |
| `SOMNIA_VOICE` | `af_heart` | The Kokoro voice a render uses **when the request did not name one**. See [the voices](#the-voices) below |
| `SOMNIA_AGENT_MODEL` | `claude-haiku-4-5` | The model behind the conversation. `claude-sonnet-5` is the alternative — twice the wait, five times the cost, and no better on any case that has been measured |
| `SOMNIA_AGENT_EFFORT` | `medium` | How hard that model may think before answering: `low`, `medium`, `high`, `xhigh` or `max`. **Only for models that have the dial** — Haiku has not, so on the default this is not sent and changes nothing. Anything else is ignored with a warning in the journal |
| `SOMNIA_EMBED_MODEL` | `intfloat/e5-small-v2` | The sentence embedding model. Must be 384-dimensional |
| `SOMNIA_ABS_URL` | `http://127.0.0.1:13378` | Audiobookshelf. A trailing slash is stripped for you |
| `SOMNIA_ABS_TOKEN` | — | Unset means no ABS client is built at all, and nothing is written there |
| `SOMNIA_ABS_LIBRARY_ID` | — | Which ABS library to rescan. From `somnia libraries` |

`ANTHROPIC_API_KEY` is the Anthropic SDK's own variable rather than one of ours,
so a key already exported for other tools is picked up without being named
twice.

`~` is expanded in the two path settings, so `~/library/audiobooks` works when a
shell sets it. Under systemd nothing expands it, which is the trap: see above.

(config-fail-quietly)=
### The two that fail quietly

**`SOMNIA_LIBRARY_DIR`** is load-bearing since the page became the player. Get
it wrong and everything starts, the agent answers questions, and every chapter
404s. Chapters are never served by path — the request names a book and a chapter
number and the file comes from the database row — but a row resolving outside
this directory is refused all the same, because a database carried from another
machine can point anywhere. What reaches the phone is *that chapter didn't
arrive*; the reason is a warning in the journal. `somnia-doctor.sh` checks it
directly.

**`SOMNIA_EMBED_MODEL`** cannot be changed once anything is indexed. The vector
table is created as `float[384]`, so a model of another width fails outright —
better than the alternative, which is what happens with a *different*
384-dimensional model: it loads, it indexes, and every distance it produces is
measured against embeddings from the old model. Searching then quietly returns
the wrong passages. Changing it means re-rendering every book.

(the-voices)=
## The voices

A book is read in one voice and cannot be re-read in another — every timestamp
somnia holds was measured against the audio that was actually produced. So the
voice is chosen **per book, when the book is asked for**, and written on the
queue row: the page offers a picker on the add press, `somnia add --voice` names
one, and `SOMNIA_VOICE` is what a request that named nothing falls back to. The
agent never names one, because nobody chooses a narrator out loud at 2am.

Six are on offer, and the page will accept no others:

| Voice | Sounds like |
|---|---|
| `af_heart` | American, warm and unhurried — the default, and Kokoro's own highest-graded voice |
| `af_bella` | American, lower and slower |
| `am_michael` | American, a man, even and plain |
| `am_puck` | American, a man, brighter and quicker |
| `bf_emma` | British, measured |
| `bm_george` | British, a man, low |

`SOMNIA_VOICE` and `--voice` will take **any** name Kokoro knows, not only these
six — a terminal is a deliberate act and trying `af_nicole` for a night should
not need a release. A name Kokoro does not know fails when the model loads, with
Kokoro's own list in the message.

The language is derived from the first letter of the name and must not be set
beside it: `b` is British English and `a` is American, and they select different
phonemisers. Until this was fixed every voice was read with an American
phonemiser, which made the two British ones sound like an American impression of
them.

Samples of each live in `src/somnia/web/voice/` and are what the picker plays.
They are committed rather than generated at runtime, because the box that serves
the page has no Kokoro on it; `scripts/somnia-voices.py`, run on the render
host, is what makes them.

## Not settable from the environment

These are fields of `Config` with no variable behind them. They are code-only
on purpose: each one changes what a render or an index *means*, so a book
rendered under one value and searched under another is not comparable with
itself, and that is not a thing to leave to a stray line in a unit file.

| Setting | Value | What it decides |
|---|---|---|
| `sentence_silence_ms` | 120 | The gap joined between sentences |
| `paragraph_silence_ms` | 500 | The gap between paragraphs |
| `window_sentences` | 3 | How many sentences make up one indexed passage |
| `window_stride` | 2 | How far the window moves between passages |
| `aac_bitrate` | `64k` | The encode |
| `agent_max_tokens` | 4096 | The ceiling on one model reply |

The first four are the ones that would silently invalidate an index: change the
window shape and new passages no longer line up with the old ones, though both
sit in the same table answering the same questions.

## What each command needs

Everything opens the database, so `SOMNIA_DATA_DIR` matters everywhere. Beyond
that, `ask` and `serve` need the key; `add` needs `SOMNIA_LIBRARY_DIR` and
`SOMNIA_VOICE`; `libraries` and `seed-positions` need `SOMNIA_ABS_TOKEN`; and
`serve` needs `SOMNIA_LIBRARY_DIR` to be the same one `add` used. The per-command
detail is in the [command line reference](cli.md).

## Checking what is actually set

`somnia-doctor.sh` loads `~/somnia.env` the way a systemd unit would and reports
what somnia's own configuration loader then sees — which is the question worth
asking, since a variable exported in the shell you are typing in is not
necessarily one the service has.
