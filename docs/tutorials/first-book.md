# Add a book and ask it something

Fifteen minutes, most of which is waiting for a chapter to be read aloud. By
the end you will have a book rendering, an index you can search, and a page on
your phone that plays it.

This assumes you have [installed somnia](installation.md) and that
`somnia search` finds things.

## Pick a book

somnia reads Project Gutenberg. Search the local catalog for a Gutenberg id —
the `gid` is the only handle anything else uses:

```
$ somnia search "black beauty"
   271  Black Beauty — Sewell, Anna
```

## Render it

```
$ somnia add 271
2026-08-06 21:04:11 INFO rendering chapter 1/49: 01. My Early Home
2026-08-06 21:09:38 INFO rendering chapter 2/49: 02. The Hunt
...
```

This takes hours — Kokoro runs at about 1.15× realtime, so a six-hour book is
roughly a five-hour render — but **you do not wait for it**. Each chapter is
written to the library folder and indexed the moment it finishes, so chapter
one is listenable within a few minutes and the rest arrives while you sleep.

Leave it running in a `tmux` session, or let the agent start it for you later
(`add_book` spawns exactly this command in the background).

One rule: never re-render a book with a different voice. Every timestamp in the
database — chapter marks, index entries, the place you fell asleep — is tied to
the audio that was actually produced.

## Search what has been rendered

```
$ somnia find 271 "the horse is beaten in the street"
[2:47h  d=0.284] 32. A Horse Fair
    A poor old brown horse was there... he was being beaten about the head
    while the crowd looked on.
```

`d` is the distance — smaller is closer. Concrete events, characters and places
search well; atmosphere ("the bit that felt strange") does not, and that is a
known limitation rather than a bug.

`somnia find` searches the whole book. The agent, in the next step, does not.

## Ask it in words

```
$ export ANTHROPIC_API_KEY=sk-ant-...
$ somnia ask "which chapter is the one with the horse fair?"
```

Give no question and you get an interactive prompt; a blank line ends it.

The first thing you will probably see is the agent telling you that the passage
is further on than you have got, and offering to take you there. That is the
spoiler guard working. It bounds every search at the furthest point somnia has
actually *played* — and from the command line, nothing has played anything, so
the bound is the first minute of the book. Say yes and it will search the whole
thing.

The guard is why the agent exists in this shape at all: a question at 2am must
never be answered with something you have not heard yet.

## Play it from your phone

```
$ somnia serve
```

That serves the page, the agent behind it, and the book itself, on
`127.0.0.1:8721`. **Leave it on localhost.** There is no login of any kind; the
only thing protecting it is that nothing but `tailscale serve` can reach the
port. Publish it, and install it on the phone, by following
[Serve the page that plays the book](../how-to/serve-the-chat-page.md).

Once it is on your phone, a night looks like this:

- The page opens the book you were last in, at the place you left it, and does
  **not** start it. Opening the app to ask a question is not the same as asking
  for the book.
- Press play, then lock the phone. From there the book is driven from the lock
  screen, the notification and anything paired over Bluetooth.
- Tap **sleep** to walk the timer through 15, 30, 45, 60 minutes and the end of
  the chapter. It counts listening time, so pausing to ask a question does not
  spend it, and it ends in a twenty-second fade.
- Half asleep, hold the talk button and say *"go back to where the horse gets
  hurt"*. The book goes there and plays from there. There is nothing to press
  afterwards.

## If you already listened in Audiobookshelf

Run this once, before the first night:

```
$ somnia seed-positions
   271  Black Beauty: seeded at 3:12:40 (2026-08-01 22:41:03); heard to 3:12:40
1 of 1 books changed.
```

It is the only thing that ever reads Audiobookshelf. Without it, somnia thinks
you have heard nothing, opens the wrong book, and bounds every search at the
first minute. It never moves a position backwards and running it twice changes
nothing.
