# HTTP surface

What `somnia serve` answers. The page is the only client this was written for,
but nothing about it is private to the page.

**There is no authentication on any of it.** Anything that can reach the port
can list your books, read the agent, spend your API credit and move your
position. Reachability is the authentication, which is why the server binds to
localhost and the only path in is `tailscale serve`.

Everything the page fetches lives under `/api/`, and that prefix does work: the
service worker knows never to cache it — the Cache API throws when asked to
store the 206 a seek produces — and it keeps these routes ahead of the static
mount, which would otherwise swallow them. `/` serves the PWA itself.

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
| `/api/sentence/{gid}/{ms}` | GET | Where the sentence being spoken at `ms` began |
| `/api/ask` | POST | The agent's reply, and a move if it made one |
| `/api/forget` | POST | Drops one conversation |
| `/api/position` | POST | What became of a report — always 200 |

## `GET /api/books`

```json
{
  "last_gid": 271,
  "books": [
    {
      "gid": 271, "title": "Black Beauty", "authors": "Sewell, Anna",
      "status": "done", "total_ms": 22320000, "chapters": 49,
      "position_ms": 11560000, "seq": 3
    }
  ]
}
```

`last_gid` is what a cold launch opens. It is `null` only when nothing has ever
been played — the one moment it is fair to ask which book they want.
`position_ms` is `null` for a book never started, which is a different answer
from `0`.

## `GET /api/book/{gid}`

One round trip on purpose: the page needs all of this before it can put a finger
on the play button, and two fetches at 2am on a tailnet is two chances to be
left with a player showing nothing.

```json
{
  "gid": 271, "title": "Black Beauty", "authors": "Sewell, Anna",
  "status": "done", "total_ms": 22320000,
  "position_ms": 11560000, "seq": 3, "heard_to_ms": 12040000,
  "chapters": [
    {"idx": 0, "title": "01. My Early Home", "start_ms": 0,
     "end_ms": 455000, "url": "api/audio/271/0"}
  ]
}
```

`status` is `pending`, `rendering` or `done` — how the page tells a book still
growing from a render that died. `heard_to_ms` is the high-water mark the
spoiler guard uses, which is not `position_ms`: the agent can move someone
backwards, and doing so must not shrink what may be searched. Chapter `url` is
relative, because the app may be mounted under a path.

404 for a book that is not there.

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

## `GET /api/sentence/{gid}/{ms}`

```json
{"gid": 271, "ms": 11560000, "start_ms": 11554300}
```

Where the sentence being spoken at `ms` began. The page asks when someone
pauses, never when they press play: a resume has to be instant, and a phone
that has been face down for an hour is the least likely thing on the tailnet to
answer quickly.

## `POST /api/ask`

```json
{"token": "…", "question": "where does the horse get hurt?"}
```

`token` is minted by the page when it starts and keys a conversation held in
memory; nothing is written to disk. Both fields are required — 400 otherwise —
and a turn that fails is a 500 whose body says *Something went wrong down
here.*

```json
{"reply": "…", "move": {"gid": 271, "position_ms": 9930000, "seq": 4}}
```

`move` is present only when the book actually moved, so the page reads the key
rather than its contents. The sequence number travels with the position because
adopting one without the other would have the page's next report refused.

This is a head start, not the mechanism: if the reply never arrives, the same
move lands within fifteen seconds as the refusal of the page's next report.

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
journal. The five that mean the sound stopped — `pause`, `hidden`, `unload`,
`ended`, `switch` — also send the position to Audiobookshelf, as a background
task after the reply is on the wire.

**Always 200**, in one of two shapes:

```json
{"accepted": true, "gid": 271}
{"accepted": false, "gid": 271, "position_ms": 9930000, "seq": 4}
```

A refusal is not an error. It is how the page is told the agent moved the book
while it was not looking, and it carries where to go instead. A 409 would put a
red line in the console at 2am for something working exactly as designed, and
be unreadable to the `sendBeacon` sent as the page dies. Nulls are dropped
rather than sent: a report about a book that is gone has no position to talk
about, and `"position_ms": null` would read as one.

400 is reserved for a body with no `gid` or no `position_ms`.
