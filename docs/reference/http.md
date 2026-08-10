# HTTP surface

What `somnia serve` answers. The page is the only client this was written for,
but nothing about it is private to the page.

**There is no authentication on any of it.** Anything that can reach the port
can list your books, read the agent, spend your API credit, move your position,
change which book you are on, and start or stop hours of rendering.
Reachability is the authentication, which is why the server binds to localhost
and the only path in is `tailscale serve`.

Everything the page fetches lives under `/api/`, and that prefix does work: the
service worker knows never to cache it — the Cache API throws when asked to
store the 206 a seek produces — and it keeps these routes ahead of the static
mount, which would otherwise swallow them. `/` serves the PWA itself, and
everything outside `/api/` goes out with `Cache-Control: no-cache` — which
means *ask before you use it*, not *do not store it*: unchanged, the ETag
answers 304; changed, the new file arrives at the next launch. Without it the
browser invents a freshness policy (Chrome's is a tenth of the file's age), and
what that looks like is a deploy that did not happen — new bytes on disk, every
request answered, last week's page on the phone.

All times are milliseconds on the **book clock**: the render clock, counted in
samples before encoding, and the same clock chapter marks, search results and
saved positions all speak. It is not per-chapter, and it is not what a decoder
would tell you.

| Route | Method | Answers |
|---|---|---|
| `/api/health` | GET | `{"ok": true}` |
| `/api/books` | GET | Every book, most recently listened to first |
| `/api/book/{gid}` | GET | One book, whole — or 404 |
| `/api/audio/{gid}/{idx}` | GET | The chapter's audio — or 404 |
| `/api/stream/{gid}/{n}` | GET | The first `n` chapters as one file — or 404 |
| `/api/sentence/{gid}/{ms}` | GET | Where the sentence being spoken at `ms` began |
| `/api/passage/{gid}/{ms}` | GET | The book's own words at `ms`, never further on than they have heard |
| `/api/catalog?q=…` | GET | Books to add, from the local catalog (both libraries) |
| `/api/voices` | GET | The voices a book may be asked for in |
| `/api/queue` | GET | What is rendering, what is waiting, what went wrong |
| `/api/book/{gid}` | DELETE | Take a book away — rows, audio and all |
| `/api/book/{gid}/open` | POST | Make this the book a cold launch opens — or 404 |
| `/api/book/{gid}/finished` | POST | Say the reader is done with a book, or that they are not |
| `/api/book/{gid}/name` | POST | Say what a book is called here, and who wrote it |
| `/api/ask` | POST | The agent's reply, and a move if it made one |
| `/api/forget` | POST | Drops one conversation |
| `/api/position` | POST | What became of a report — always 200 |
| `/api/queue` | POST | Ask for a book — always 200 |
| `/api/queue/{id}/stop` | POST | Stop a render, or take a book out of the line |

## `GET /api/books`

```json
{
  "last_gid": 271,
  "books": [
    {
      "gid": 271, "title": "Black Beauty", "authors": "Sewell, Anna",
      "status": "done", "total_ms": 22320000, "chapters": 49,
      "chapters_total": 49, "position_ms": 11560000, "seq": 3,
      "finished_at": null, "created_at": "2026-03-11 21:40:02"
    }
  ]
}
```

`last_gid` is what a cold launch opens. It is `null` only when nothing has ever
been played — the one moment it is fair to ask which book they want.
`position_ms` is `null` for a book never started, which is a different answer
from `0`.

`chapters` is how many of the book's chapters can be played *now*, counted from
rows that really exist, and `0` means there is nothing to open yet: a render
that has not produced its first chapter, or one that died before it. The books
panel draws its shelf from this list, and that is the field that decides whether
a row offers a press at all.

`chapters_total` is how many chapters the book *has*, which is a different
number from `chapters` on every book whose render has not finished — and the
one number the player, the `reading now` line, the shelf row and the book page
all read, so that they cannot disagree about how long a book is. `0` means
nobody wrote it down, which is true of anything rendered before the column
existed, and anything drawing it says nothing at all rather than "of 0".

`created_at` is when somnia was first asked for the book. It is the only date on
this row that is about the reader rather than the render, it is what the
Workshop means by *brought in*, and it is what sorting the library by how new a
book is is built on.

`finished_at` is when the reader said they were done with the book, and `null`
while they have not — which is every book somnia has ever had until somebody
says otherwise. It is deliberately not `status`: that is the *render's* word,
and a book somebody has finished reading would otherwise be indistinguishable
from one that was never made. A finished book is still a book somnia has and
still plays; the night shelf stops offering it, and the Workshop is where it
goes.

The night shelf shows at most the twenty most recently touched books, and
finished books and the one playing underneath are not among them and do not
count towards the twenty. Everything is still in this answer — which books to
draw is the page's business, not the server's.

## `GET /api/book/{gid}`

One round trip on purpose: the page needs all of this before it can put a finger
on the play button, and two fetches at 2am on a tailnet is two chances to be
left with a player showing nothing.

```json
{
  "gid": 271, "title": "Black Beauty", "authors": "Sewell, Anna",
  "status": "done", "total_ms": 22320000, "chapters_total": 49,
  "position_ms": 11560000, "seq": 3, "heard_to_ms": 12040000,
  "chapters": [
    {"idx": 0, "title": "01. My Early Home", "start_ms": 0,
     "end_ms": 455000, "url": "api/audio/271/0"}
  ],
  "stream_url": "api/stream/271/49", "stream_ms": 22320000
}
```

`status` is `pending`, `rendering` or `done` — how the page tells a book still
growing from a render that died. `heard_to_ms` is the high-water mark the
spoiler guard uses, which is not `position_ms`: the agent can move someone
backwards, and doing so must not shrink what may be searched. Chapter `url` is
relative, because the app may be mounted under a path.

`stream_url` is the whole of what has been read of this book down one URL, and
`stream_ms` is how much book that is. The page loads it once and crosses every
chapter inside it without touching the media element — see `GET
/api/stream/{gid}/{n}`. It is `null` when there is nothing to join, which is a
book with no audio yet; the per-chapter `url`s are always there beside it, and a
page that finds no stream plays the book a file at a time.

`chapters_total` is how many chapters the book **has**, against `chapters`,
which is how many can be played. While a render is going those differ, and the
difference is the only way to tell running out of audio three chapters into
thirty-nine — which is not the end of the book — from reaching the end of one.
It is `0` for every book rendered before the column existed, and `0` means
nobody wrote it down, so say nothing rather than "3 of 0".

404 for a book that is not there.

## `DELETE /api/book/{gid}`

```json
{"ok": true, "found": true, "said": "Black Beauty is gone, with everything rendered of it."}
```

The only route in somnia that takes something away for good, and it takes all
of it: the `books` row, the chapters, the indexed chunks and their vectors,
every queue row the book ever had, the m4a files with the folders above them
once those are empty, and the joined streams under `data_dir`. Half of that
would be worse than none of it — a shelf entry that plays silence, or hours of
audio nothing will ever mention again.

DELETE, and it means it, which is the difference from `POST
/api/queue/{id}/stop`: that one is a POST because the row it names survives it.
Nothing survives this and nothing behind it is an undo, so the page asks twice
before it gets here.

**200 with `"ok": false`** for the two refusals, in the shape the queue's
routes already answer in — a refusal is an answer, and `said` is the sentence
to show for it. A book with a live queue row is refused because a render is
about to write chapters back into the folder this would be emptying, and the
sentence names the job to stop first; `queue.stop` is keyed on the job id, so
it is a different number from the one just deleted. And a book with a chapter
whose `audio_file` lies outside `SOMNIA_LIBRARY_DIR` is refused whole rather
than in part — the same containment rule `GET /api/audio/{gid}/{idx}` applies,
and a path outside the library means the database has been carried between
machines or edited by hand. Which chapter it was is in the journal, not in `said`: it is an absolute
path on the VPS and this is read on a phone.

**404** only for a gid that is not here at all, which is a page holding an id
from a database that has moved on. `found` is what tells the two apart, and the
body carries `said` either way.

A chapter whose file has already gone is not a refusal. There is nothing there
to delete, and stopping at the first gap would leave the rest of the book
orphaned for good.

## `POST /api/book/{gid}/open`

```json
{"gid": 271, "position_ms": 11560000, "seq": 3}
```

The whole of switching books, and it writes one column: `position_at`. Since
`last_gid` is simply the book with the newest one, making a book the most recent
*is* choosing it — there is no new state, and no second place a position is
remembered.

Nothing else on the row is touched. `position_ms` stays where the last report
put it, which is what makes the book resume exactly where it was left;
`heard_to_ms` stays because pressing a button has not heard anything; and
`position_seq` stays because that counts agent moves and nothing else, so the
page's next report is accepted rather than refused and the listener is not
dragged anywhere. The two numbers in the answer are the book's own, from before
the press — they say where the page is about to resume, and the page then asks
for the manifest anyway.

The timestamp written is a couple of seconds ahead of every other book's rather
than simply `datetime('now')`. That column counts whole seconds and a tie is
broken by which book was added first, and the write this has to beat is the
page's parting report for the book it is leaving, which lands milliseconds
later — without the lead, a reload could open the book you had just left.

**404** for a book that is not there, and for a book with no audio yet — a
render still on its first chapter, or one that died before it. Both are the same
answer to a press: there is nothing to open. The guard is here and not only on
the page because a book nobody can play made the most recent one would leave the
next launch waiting on a render instead of on the book that was playing.

## `POST /api/book/{gid}/finished`

```json
{"finished": true}
```
```json
{"ok": true, "found": true, "said": "Black Beauty is finished."}
```

One column, `books.finished_at`, written as a UTC stamp or cleared. A body that
says nothing means `true`, which is the press that exists; `{"finished": false}`
is the undo, and it is the same route on purpose — an undo shaped like the doing
is what lets the day screen offer one control that toggles rather than two that
can disagree about a book.

Nothing else changes. The book keeps its position, its audio, its rows and its
`status`, and it still plays if it is opened. That is the whole distance between
this and the DELETE on the path above it, and it is why this one is not asked
about twice: marking the wrong row costs one press back.

POST rather than DELETE because nothing is deleted, and not on the agent at
all — a hold-to-talk request at 2am is the wrong way to say a book is over.

**404** for a gid that is not here, the same answer as the GET and the DELETE
on this path.

## `POST /api/book/{gid}/name`

```json
{"title": "Beauty, the horse", "authors": "Sewell, Anna"}
```
```json
{"ok": true, "found": true, "said": "It is called Beauty, the horse now.",
 "title": "Beauty, the horse", "authors": "Sewell, Anna"}
```

Two plain columns, `books.title` and `books.authors`, and a third that is the
point of the route: `books.renamed_at` records that a person has had an opinion
about this name, and `ingest_book`'s upsert reads it and leaves the pair alone
from then on. Without that, re-rendering a book — which is the ordinary way to
restart a render that died — put the catalog's name back hours later with
nobody watching.

Both columns in one request because a name and an author are one edit on the
screen that makes it, and two routes would let a phone that lost the tailnet
between them leave a book with half the change on it. A missing field means the
empty string rather than "leave it alone", which is what a form that has been
cleared actually says.

The stored strings come back, trimmed, so the page can draw what was saved
rather than what was typed.

**200 with `"ok": false`** for a book asked to have no title at all. Every
screen names a book by `title` and falls back to `book 1342` for a book the
catalog never named, so a blanked one would be indistinguishable from a book
that was never named — a rename that reads as a bug. An empty `authors` is
stored: plenty of books really do not have one.

The audio does not move. Chapters are found by the absolute path in their own
row, so a renamed book goes on playing out of a folder named after whatever it
was called on the day it was rendered.

**404** for a gid that is not here, the same answer as the GET, the DELETE and
the finished route on this path.

## `GET /api/audio/{gid}/{idx}`

The audio, as `audio/mp4`. Range, If-Range and 416 are handled, so seeking
works. No filename is offered — this is something to play, not to download.

404 if there is no such chapter, and also if the row points at a file that has
gone or resolved outside `SOMNIA_LIBRARY_DIR`. The second case is a warning in
the journal; on the phone both look like one chapter that didn't arrive.

The media type is pinned rather than guessed. Python does not know `.m4a` and
the container image has no mime table, so guessing yields
`application/octet-stream` and Safari refuses to play the book — a bug that
cannot reproduce on a development machine.

## `GET /api/stream/{gid}/{n}`

The book's first `n` chapters joined into one `audio/mp4`, with the same Range,
If-Range and 416 handling as a chapter, and the same pinned media type for the
same reason.

`n` is a version rather than a length: it names the chapters the file holds, so
a book that grew while somebody was listening is offered a *new* url and the
file their phone has open is never rewritten under an in-flight range request.
Versions are built on the first ask — a second or two of ffmpeg, `-c copy`, so
not a byte of audio is re-encoded — and kept under `SOMNIA_DATA_DIR/streams`,
never in the library. The library holds what a render produced, one file per
chapter, and every one of those paths is in the database; a join is a cache
that can be deleted at any time and rebuilt in a second or two, so it is kept
where nothing has to tell the two apart.

404 if the book has fewer than `n` chapters, if any of their audio has gone, or
if the join could not honestly be made. The reason is in the journal. The page
still has a url for every chapter, so a book with no stream is one that rebuilds
the lock screen at every boundary — a worse night, not a lost one.

## `GET /api/sentence/{gid}/{ms}`

```json
{"gid": 271, "ms": 11560000, "start_ms": 11554300}
```

Where the sentence being spoken at `ms` began. The page asks when someone
pauses, never when they press play: a resume has to be instant, and a phone
that has been face down for an hour is the least likely thing on the tailnet to
answer quickly.

## `GET /api/passage/{gid}/{ms}`

```json
{"gid": 271, "ms": 11560000, "text": "…"}
```

The only route that hands back the book's own words, for the *you are here* row
on the list of places — every other row on that screen carries its words down
with the answer that named it.

`text` is `null` when there is nothing to say: no such book, a book whose text
was never indexed, or a book nobody has played a second of. The row then offers
no reveal, which is what it did before this existed.

The bound is inside the statement: the row must satisfy
`start_ms < heard_to_ms`, applied to the row and not to the argument. Ask about
a point an hour past where anybody has listened and the answer is the last
passage that really was spoken — not a refusal, which is a frontier to read off.
The words are cut to 240 characters, the same limit as the places the row sits
among.

## `GET /api/catalog`

```json
{
  "query": "black beauty",
  "entries": [
    {"gid": 271, "title": "Black Beauty", "authors": "Sewell, Anna",
     "have": "done", "source": "gutenberg"}
  ]
}
```

An FTS5 search of the local catalog — the copy `somnia catalog-update` writes —
so there is no round trip to Gutenberg and no wait. `language` defaults to `en`.
Punctuation is the caller's own: terms are quoted before they reach FTS5, so an
apostrophe is a search rather than a syntax error.

At most **eight** entries. Eight is what fits on a phone above a raised
keyboard, and a list that has to be scrolled to be read is a second screen
wearing a hat; someone who cannot see the book they meant should type more of
its name.

`have` is what somnia already thinks of that gid — `done`, `rendering` or
`pending` from the book itself, `queued` or `rendering` from a live queue row —
and `null` if it has never heard of it. A live queue row wins, because a
`pending` book that has just been asked for again is coming. It travels with the
row so a book that is already on its way is *marked* rather than offered and
then refused.

`source` is which library the book came from — `gutenberg`, or `australia` for
[Project Gutenberg Australia](http://gutenberg.net.au), whose ids start at
900,000,000. The page names the second one on the row and says nothing for the
first. It travels for the same reason `have` does: the two libraries clear
their books against different countries' copyright law, and that is worth
knowing before the press rather than after it.

(http-voices)=
## `GET /api/voices`

```json
{
  "voices": [
    {"id": "af_heart", "name": "heart", "says": "American, warm and unhurried"},
    {"id": "bm_george", "name": "george", "says": "British, a man, low"}
  ]
}
```

The six voices a book may be asked for in, in the order the page draws them —
the first is the default, and the same one `SOMNIA_VOICE` starts at. Served
rather than written into `app.js` so that the list the page offers and the list
`POST /api/queue` will accept cannot come apart: a pill offering a voice the
route would refuse is a press that does nothing.

`id` is Kokoro's own name and the only form that reaches the model or the
database. `name` is what to draw. `says` is one line for anybody the sample
cannot reach — a phone on silent, a screen reader, a clip that did not arrive.

Cached for a day. It changes when somnia is deployed and not otherwise. The
samples themselves are static files under `/voice/{id}.m4a`, outside `/api/`,
and the service worker treats them like the rest of the shell.

## `GET /api/queue`

```json
{
  "items": [
    {"id": 7, "gid": 271, "title": "Black Beauty", "authors": "Sewell, Anna",
     "voice": "bm_george",
     "state": "rendering", "place": 0, "chapters_done": 4,
     "chapters_total": 49, "rendered_ms": 1840000, "stopping": false,
     "responding": true, "error": "",
     "submitted_at": "2026-08-05 22:14:03", "started_at": "2026-08-05 22:14:11"}
  ]
}
```

Everything worth showing, in one request: what is rendering, then what is
waiting in the order it will be taken, then what ended in the last 24 hours.
After a day a failure is history rather than news, and history is in
`journalctl --user -u somnia-worker` — which is why nothing here has to be
dismissed.

`state` is `queued`, `rendering`, `done`, `cancelled` or `failed`. That is the
queue's own vocabulary and is **not** `books.status`, which is still exactly
`pending`, `rendering`, `done`.

`place` is the rank among the books that are waiting, and `0` for anything that
is not waiting — the one being rendered has left the line rather than being at
the head of it. `chapters_done` is counted from chapters that really exist,
because a chapters row is written only once its audio does. `chapters_total` is
`0` until the parse finishes, and `0` means unknown. `stopping` is a render that
has been asked to stop and will, at the end of the sentence it is reading.

`responding` is worked out from the heartbeat when you ask, and is stored
nowhere: it is `false` for a render that has gone quiet for five minutes, which
is the only way a crashed renderer can be told from a slow one. It is honest
even when the worker unit has been stopped and there is nobody left to write
anything.

`voice` is what the request asked for, and `""` for one that asked for nothing —
which is what the agent submits, and what every row written before the column
existed holds. Empty means *the renderer's own*, and this process cannot see
what that is, so nothing here guesses at it.

## `POST /api/ask`

```json
{"token": "…", "question": "where does the horse get hurt?", "gid": 271}
```

`token` is minted by the page when it starts and keys a conversation held in
memory; nothing is written to disk. `token` and `question` are required — 400
otherwise — and a turn that fails is a 500 whose body says *Something went wrong
down here.*

`gid` is the book the page has open, and it is optional. It is named to the
model on the end of the system prompt, once per turn, so that a question over a
playing book is not answered with *which book do you mean?* — which is what
happened while it was missing, on every turn, because the model could list the
shelf and nothing told it which of them was making the sound. Anything that is
not a positive integer — absent, `null`, a string, a bool — is taken as "no book
open" rather than refused, so a page that has opened nothing can still ask, and
a cached older `app.js` keeps working.

It is sent per turn rather than fixed at the start of a conversation: the page
can open another book between two questions, and a conversation that remembered
the first one would answer the second about the wrong book.

```json
{"reply": "…", "move": {"gid": 271, "position_ms": 9930000, "seq": 4}}
```

`move` is present only when the book actually moved, so the page reads the key
rather than its contents. The sequence number travels with the position because
adopting one without the other would have the page's next report refused.

This is a head start, not the mechanism: if the reply never arrives, the same
move lands within fifteen seconds as the refusal of the page's next report.

```json
{"reply": "…", "candidates": {
  "gid": 271, "title": "Black Beauty", "position_ms": 11560000,
  "places": [{"chunk_id": 812, "start_ms": 9930000, "chapter_idx": 31,
              "chapter_title": "32. A Horse Fair", "ahead": false, "text": "…"}]}}
```

`candidates` and `move` never appear together — a list and a seek in one reply
would move the book under somebody still choosing. Read by presence, like
`move`. `position_ms` is `null` for a book never started, and the page draws no
*you are here* row rather than inventing one. `ahead` is decided on the server,
by the same code that owns the spoiler guard: a row with `ahead: true` is drawn
covered up — words and chapter title both — until they ask, and the page
computes nothing.

## `POST /api/forget`

`{"token": "…"}` → `{"ok": true}`. Drops that conversation, which is what
*Start over* does when the agent has the wrong end of a mumbled question.

## `POST /api/position`

The only position write the page makes.

```json
{"gid": 271, "position_ms": 11560000, "seq": 3,
 "played_ms": 15000, "reason": "tick"}
```

`played_ms` is sound that really came out of the speaker since the last report —
not time that passed — and it is what may raise the heard-to mark. A body
missing it claims no playback rather than an impossible amount of it.

`reason` is one of `load`, `play`, `tick`, `seek`, `chapter`, `pause`, `hidden`,
`unload`, `ended`, `switch`. An unknown one is taken as a tick and noted in the
journal. Nothing branches on which one it is: the list is a vocabulary rather
than a decision, kept so that a word nobody wrote can be noticed on the way in.

**Always 200**, in one of three:

```json
{"accepted": true,  "gid": 271, "position_ms": 11560000, "seq": 3, "heard_to_ms": 12040000}
{"accepted": false, "gid": 271, "position_ms": 9930000, "seq": 4, "heard_to_ms": 12040000, "reason": "moved"}
{"accepted": false, "gid": 271, "reason": "gone"}
```

A refusal is not an error. It is how the page is told the agent moved the book
while it was not looking, and it carries where to go instead. A 409 would put a
red line in the console at 2am for something working exactly as designed, invite
a throw in the fetch wrapper that skipped the one line that mattered, and be
unreadable to the `sendBeacon` sent as the page dies.

`reason` is what the page acts on. `moved` means the agent took the book
somewhere while the page was not looking, and the body says where. `gone` means
the row is not in this database any more — a page left open on a book that was
deleted — and there is nothing to go to. Nulls are dropped rather than sent: a
report about a book that is gone has no position to talk about, and
`"position_ms": null` would read as one.

400 is reserved for a body with no `gid` or no `position_ms`.

## `POST /api/queue`

```json
{"gid": 271, "voice": "bm_george"}
```

**Always 200**, in one of two shapes:

```json
{"ok": true,  "id": 7, "said": "Black Beauty is next to be rendered."}
{"ok": false, "id": 0, "said": "Black Beauty is already here, all of it."}
```

`said` is a sentence to show somebody — it is the *same string*
`Library.add_book` gives the agent, out of the same function, so the page and
the voice cannot disagree about what just happened. A refusal is an answer, not
an error, for the reason `/api/position` gives above; here the answer is the
sentence saying why.

Two things are refused: a book with a live queue row, which is already coming,
and a book somnia has all of. A render that died, was stopped, or was killed by
a deploy is **accepted** — that is the retry that used to be impossible.

Nothing is fetched here. Whether Gutenberg has this book, and has it as HTML,
costs a round trip and a parse, and a control that thinks for three seconds
reads as broken — so an unknown gid is taken and fails minutes later in the
worker with a sentence saying which of the two it was.

`voice` is optional and is held to [the roster](#http-voices) — the one thing
this route checks that the queue itself does not. Omitted, the render uses
whatever the renderer is configured with; named, it is written on the row and
survives the hours between the press and the render, whichever process gets
there. A name off the roster is **400**, because it can only be a page left open
across a release or somebody with curl, and a book is six hours — too long to
find out afterwards that a typo was quietly rendered in the default.

400 is otherwise reserved for a body with no positive integer `gid`. Nothing
starts a render in `somnia serve`: this writes one row, and the `somnia-worker`
unit drains it one book at a time — see
[ADR 5](../explanations/decisions/0005-render-one-book-at-a-time.md).

## `POST /api/queue/{id}/stop`

```json
{"ok": true, "state": "cancelled",
 "said": "Black Beauty has been taken out of the queue."}
```

Keyed on the queue row and not on the book: a gid owns several rows over its
life — every attempt that failed or was stopped stays as the record of itself —
so stopping by gid could reach into last week's.

A job that was only waiting is `cancelled` by the time this answers. A job that
is rendering is still `rendering`: nothing reaches into that process, it only
raises a flag the render notices between sentences, so it stops at the end of
the one it is reading, up to about twenty seconds later. Every chapter already
finished stays playable.

POST rather than DELETE, and the row does not go away — it becomes the record of
a render somebody stopped.

200 with `"ok": false` for a job that has already ended, which is a button
pressed a second too late. **404** only for a job that does not exist, which is a
page holding an id from a database that has moved on; its body carries `said`
too.
