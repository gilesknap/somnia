# Serve the page that plays the book

`somnia serve` runs the 2am surface: a small chat page that talks to the agent,
with the Anthropic key held server-side. It is also the player — the page holds
the book somnia rendered and plays it, which is why asking to be taken
somewhere now ends in sound instead of in an instruction. Voice input uses the
browser's Web Speech API and the lock screen controls need a media session, so
the page must be reached over HTTPS (or localhost); `tailscale serve` provides
both the certificate and the only network path to it.

## Run it

```
$ somnia serve                       # 127.0.0.1:8721 by default
$ somnia serve --host 0.0.0.0 --port 9000
```

It needs the same environment as the rest of somnia, plus a key for the model.
Every setting is in [Configuration](../reference/configuration.md); these are
the ones a served night depends on:

| Variable | Why |
|---|---|
| `ANTHROPIC_API_KEY` | the agent's model calls, paid by you not the phone |
| `SOMNIA_LIBRARY_DIR` | where the rendered chapters are; the page streams them |
| `SOMNIA_DATA_DIR` | where `somnia.db` lives, and where the joined-up copy of each book the page plays is written; needs room, not just a path |
| `SOMNIA_ABS_URL`, `SOMNIA_ABS_TOKEN` | optional: keeping Audiobookshelf roughly in step, and the one-off below |
| `SOMNIA_AGENT_MODEL` | another model; the default is Sonnet 5 |

`SOMNIA_LIBRARY_DIR` is the one that has become load-bearing since the page
became the player, and it fails quietly if it is wrong. Chapters are never
served by path — the request names a book and a chapter number, and the file
comes from the database row — but a row pointing outside the library directory
is refused all the same, because a database carried over from another machine
can point anywhere. What you see on the phone is *that chapter didn't arrive*;
the real reason is a warning in the journal. It defaults to
`~/library/audiobooks`, which is right only if that is genuinely where `somnia
add` put things.

Audiobookshelf is now optional. somnia writes your position to it when you
stop, as a courtesy, so the ABS app finds roughly the right place if you open
it somewhere else — but nothing reads it while a night is running, and a write
that fails is logged and forgotten. Leave `SOMNIA_ABS_TOKEN` unset and no ABS
client is built at all.

Run `somnia seed-positions` once before the first night, if you have been
listening in Audiobookshelf. It is the one thing that reads ABS: it takes
where you had got to in each book, and how far you had heard, and puts them in
somnia's own database, so the page opens the book you were actually in rather
than the one added most recently, at the beginning. It says what it did for
every book, it never moves a position backwards, and running it again changes
nothing — so if you are unsure whether it worked, run it again.

`SOMNIA_AGENT_MODEL` overrides Sonnet 5. Haiku was the first choice, on cost,
and mostly held up; set `SOMNIA_AGENT_MODEL=claude-haiku-4-5` to go back to it.

**Keep `--host` as localhost.** The page has no login of any kind: anyone who
can reach it can drive the agent, spend your API credit, listen to your books,
and start or stop hours of rendering. Its only protection is that nothing but
`tailscale serve` can reach the port.

## Publish it on the tailnet

Audiobookshelf usually already holds port 443, so give the chat page its own:

```
$ tailscale serve --bg --https 8443 http://127.0.0.1:8721
$ tailscale serve status
```

The page is then at `https://<node>.<tailnet>.ts.net:8443/`, reachable from
your own devices and from nowhere else. The whole night goes over that path now
— the audio as well as the questions — so a phone that drops off the tailnet at
3am loses the book. Nothing is downloaded ahead of time.

## Install it on the phone

Open the page in Chrome and use *Add to home screen*. It installs as a
standalone app with its own icon, which is one tap in the dark instead of a
browser and a URL, and it is worth doing for more than the icon: an installed
app is the shape the media notification and the screen-off playback were built
for and tested in.

Nothing else is needed. The page keeps no login, and the conversation is
started fresh each time it is launched.

## Keep it running

As a systemd **user** service, alongside the rest of somnia:

```ini
# ~/.config/systemd/user/somnia-serve.service
[Unit]
Description=somnia chat page
After=network-online.target

[Service]
EnvironmentFile=%h/somnia.env
ExecStart=%h/.local/bin/somnia serve
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

The environment file must carry `SOMNIA_LIBRARY_DIR` if the library is not in
the default place. A unit that lacks it starts perfectly happily, answers
questions perfectly happily, and 404s every chapter.

```
$ loginctl enable-linger $USER          # survive logout
$ systemctl --user daemon-reload
$ systemctl --user enable --now somnia-serve
$ curl -s localhost:8721/api/health     # {"ok": true}
```

## Asking it things

Type, or hold the button and speak — it listens only while held, because a
bedroom is full of speech that was not meant for somnia. Answers are read, not
spoken back: the only thing the page makes a sound with is the book.

The button glows and pulses while it is listening, and the phone buzzes when it
starts and stops. Android's own speech recogniser plays a start and stop tone
that no web page can turn off; silencing it means muting system sounds on the
phone.

Ask to be taken somewhere and the book goes there and plays from there. If the
passage is in a book that was not even open, that book opens. Nothing has to be
pressed afterwards.

Ask it a *question* instead — who Rob Roy is, what became of Ginger, why they
went to London — and it answers in a sentence and leaves the book exactly where
it is. Nothing moves, no list goes up, and the book carries on playing
underneath. It is worth saying because it did not use to be true: every question
was read as *take me somewhere*, so asking who somebody was either put a list of
places on the screen or moved the book to one of them, and cost you the hour you
were in.

When more than one place could be what you meant, it does not ask — it puts
them on the screen. The screen is headed *Places you might be*, with a line
under it saying how many there are and what they span, and each row is a
time, a chapter and the book's own words — its own, never a description of
them, so you recognise the moment rather than take somnia's word for it, and
never the words of a place you have not reached yet, which is the paragraph
after this one. There is a *you are here* marker sitting
between them in book order so you can see which are behind you and which are
ahead. Press *goto* on a row and the book goes there and plays. Press
*‹ controls* in the top left — the same corner and the same word as the way out
of everything else — and nothing whatever happens: the book carries on exactly
as it was, in the same place, with the same sleep timer running. Nothing has
moved while the list is up, so there is nothing to undo. The book keeps playing
underneath it the whole time, which also means a sleep timer left to run out
under a list still ends the night — the list is not a reason to keep the book
going.

It will not answer about a part of the book you have not heard. An answer can
come out of somnia's own reading of the book rather than only out of the passage
it just looked up, and that line is the whole of what bounds it: somebody who
has not turned up yet gets *he hasn't come up yet in what you've heard*, and
nothing after that — not who he is, and not that he arrives later. The bound is
the furthest point the page has actually *played through*, not where you are
now — so being taken back to chapter two does not un-hear chapter twenty, and
being taken forward does not unlock what you were carried over. What you get
instead is that place as a row on the list, marked *ahead*, showing its time
and its chapter number and nothing else — no words, and not even the chapter's
name, since a chapter called *How Ginger Died* gives away as much as the
sentence under it. What it says instead is *tap to reveal · may spoil*: press
anywhere on the row's reading and it uncovers, and you decide having read it;
press *goto* and you go there without reading it at all. Two
things follow from measuring it that way. A book
somnia has never played is bounded at its opening minute, so if a book you have
been listening to for a fortnight puts everything on the list as *ahead*, the
listening happened in Audiobookshelf and somnia does not know about it — run
`somnia seed-positions`. And skipping forward while the sound is on stops the
mark where it was until you come back behind it, which is the price of one
press of *+30* not marking the rest of the book as heard.

Conversations are held in memory, keyed by a token the page mints when it
starts, and nothing is written to disk. *Start over* drops the history when the
agent has got the wrong end of a mumbled question; restarting the service drops
all of them.

## Playing the book

The page opens the book you last had open — the one you were listening to, or
the one you last pressed on the shelf — at the place you left it, or at its
beginning if you have not started it, and does not start it: opening the app at
2am to ask a question is not the same as asking for the book. Press play when
you want it.

To read something else, open *books* and press the book on the shelf — or ask,
which still works and is still the shortest way to say it. There is still no
library of things you do not have to browse: *Workshop*, behind the quiet row at
the foot of *Books*, is where a book is *added*, and its search goes to
Gutenberg's catalog rather than to your shelf.

Those two are one screen each on purpose. **Books** is the night screen — which
book, and how dark — and it is set at the same type size as the player, because
it is read in the same dark without glasses. **Workshop** is the daytime one —
find a book, have it read, watch it being made, and set how far a skip goes —
and it is smaller and denser than anything else in the app, because it is read
sitting up with the lights on.

On the page there are three buttons: back thirty seconds, play/pause, forward
thirty seconds — or fifteen, or sixty, if you have said so in *Workshop* under
*skip button size*; the labels say which. Most nights you will use none of them,
because the screen is off. With the phone locked the book is driven from the
notification, the lock
screen and whatever is paired over Bluetooth: play, pause, back and forward,
previous and next chapter, and a scrubber. The scrubber covers the chapter, not
the book — three minutes to the pixel across a whole novel is no use for the
nudge you actually want, and one sleepy thumb from the ending.

Pressing play again gives you back a little of what you missed, sized by how
long the sound was off: nothing under half a minute, then eight seconds, twenty
after a few minutes, and half a minute after an hour — and that longest one
lands on the start of the sentence you were in rather than in the middle of it.

**The sleep timer is the word *sleep* next to the clock.** Tapping it walks
fifteen, thirty, forty-five and sixty minutes, then the end of the chapter,
then off again, and it always says which it is on. It counts listening time, so
pausing to ask a question does not spend it. It ends in a twenty-second fade
that reaches silence at the time it named; tapping the control during that fade
brings the sound back, on the grounds that anyone reaching for it is awake
enough to have changed their mind. It is written down as it counts, so a reload
— or the phone throwing the app out of memory while it is in the background —
brings it back with the minutes it had left on it. A timer more than six hours
old is not brought back: opening the book the next evening is starting a night,
not finishing one.

If something else takes the sound — a call, an alarm — the book stops and stays
stopped, and the page says so. If the phone refuses to start audio without
being touched first, the page says *tap anywhere to carry on*, and anywhere
means anywhere.

A book that is still being rendered grows underneath you, and the page keeps
up with it: while the render is running it asks again for the chapter list —
when the audio runs out, and whenever you come back to the app — and carries
on into whatever has landed since. Open one that is three chapters in and it
will play those three, say *waiting for the next chapter to be read*, and go
on when chapter four arrives. A book with nothing rendered at all says *the
first chapter is still being read*, and the player appears when that chapter
lands — already playing if the agent took you to that book, waiting to be
pressed if you only opened the app. A book whose render is not running and has
no audio at all says *nothing yet — press books, then Workshop, to add one*,
which is also
what a somnia with no books in it says.

When a render stopped part way — you stopped it, or a reboot did — the audio
runs out mid-book, and the page says *the rest of this book hasn't been read
yet* rather than *that is the end of the book*. It knows the difference because
the parse writes down how many chapters the book has, so a book three chapters
into thirty-nine is tellable from one that is over. Nothing ends: the sleep
timer keeps counting and the page keeps wanting the sound. Queue the book
again — from *Workshop*, or by asking — and it picks up at the chapter after the
last finished one.

When the tailnet goes — wifi power save and a tailscale re-key both do it for a
few seconds — the page says *the book stopped arriving* and keeps trying,
waiting longer between attempts up to half a minute, and puts the chapter back
where you had got to rather than at the top of it. Opening the app while the
server is unreachable says *couldn't reach the book — trying again*, and does.
It stops the moment you pause — nothing reloads chapters under a book somebody
has put down — and waking the phone, or the wifi coming back, makes it try
again at once, so there is nothing to press.

## Choosing a book: *Books*

*books*, in the top left corner, opens a panel over the page. The book keeps
playing underneath it, and *‹ controls* puts it away having changed nothing at
all. What does change something is tapping a book — the one at the top, which
starts the book already open, or one on the shelf, which opens that one. No book
on this screen carries a button of its own: opening one is the same gesture
wherever it is in the list.

It is a night screen, and everything on it is set at the player's own type size
for that reason: it is read in the same dark, at the same arm's length, by
somebody who has taken their glasses off. It asks one question — *what shall I
listen to* — and nothing that is not part of that answer is on it. It asks the
server for one thing, once, when it opens: which books there are. It schedules
no wake and polls nothing, so a night spent looking at it is a night with no
radio traffic in it.

At the top, under *reading now*, is the book that is playing underneath the
panel — *The Moonstone* in amber, the only amber title in the app, and under it
*chapter 4 of 37 · picks up at 1:12:08* over a hairline showing how far through
it you are. The time is where a tap would land you; while the book is actually
sounding the heading reads *playing now* and the line ends *· playing*, because
then there is nothing to start. The hairline is not drawn at all while the book
is still being rendered, because until the render is over the book's length is
only how much of it exists so far. Tapping the block starts it and puts the
panel away — the same press as the play button, made from up here.

Under it, *on the shelf* is every other book somnia has, each with where you
left it — *0:27:42 in*, or *not started*. Tapping a row opens that book at that
place and takes the panel away with it. Changing your mind costs one press back:
nothing is written to the book you left, so it is still exactly where it was,
and so is the one you looked at. A book still being rendered says so and is not
a press at all until its first chapter exists, because until then there is
nothing to play. A book whose render stopped part way says *part rendered* and
can still be opened — what was read plays. If the box cannot be reached, the
shelf you last saw stays on screen with *couldn't reach somnia* under it: an
empty shelf and an unreachable server look identical and mean opposite things.

The rows say the title and nothing else — no author, no dates, no cover. At this
size the catalogue's *Title — Surname, Forename, dates* is three lines of a
phone, and it is metadata about a book you already own and chose. The title is
what you recognise a book you own by. Who wrote it appears in *Workshop*, where
you are choosing among seventy thousand you do not.

Under the shelf is *how dark*, which is the one setting that lives on a screen
rather than in a list, and it lives here because the layer it moves is over this
screen too: press *–* or *+* and the page you are looking at gets lighter or
darker as you watch. It goes from nothing to rather dark in ten presses, and it
cannot go dark enough to hide itself.

Last, above a hairline and deliberately quiet, is the row to *Workshop*. Nothing
behind it is a job for 2am.

## Adding a book, and watching it made: *Workshop*

*Workshop — add books, settings*, at the foot of *Books*, and reachable no other
way. *‹ books* comes back, and *Books* is exactly where you left it.

This is the daytime screen and it is denser than anything else in the app,
because it is read sitting up with the lights on — denser, and brighter. It is
drawn in its own ink rather than the night palette: fuller cream, stronger
hairlines, a lifted amber, and the sheet of black the rest of the app is read
through comes off entirely while it is up. Every alpha in the night scale was
chosen for a dark room, and in daylight those same values are not quiet, they
are gone. Nothing on it goes below 16dp. It asks one question too: *get me a new
book, and tell me it worked*. The order down it is that sentence.

At the top, under *project gutenberg*, is the search. Under the results is what
is happening, in a box headed *the server is working* — on the same screen and
directly beneath them on purpose, because somebody who has just pressed *add
this book* wants to see it being made, and splitting the press from its
consequence is how the same book gets added twice. The box holds the book being
rendered, with *narrating* in the corner of its line
and, under the name, which chapter it is on and how much of it can be played
now — *chapter 4 of 39 · 1h12m read so far* — over a hairline that fills as the
chapters land. Under it is whatever is waiting, marked *queued*, saying how far
down the line it is. One book renders at a time, always, so a queue of three is
three books' worth of waiting and not three renders fighting over two cores.

The word in the corner is the stage — *queued*, *narrating*, *ready*, *failed*,
*stopped* — and the line under the name is what is actually going on inside it.
A book whose text has not been parsed yet has no hairline at all rather than one
sitting at nothing: until the parse has run, nobody has written down how many
chapters there are, and the line says *fetching the text* instead of counting.
The box is not drawn at all when nothing is rendering.

A render that has not been heard from for five minutes says *not responding*
instead of pretending. That is a real answer: it means the worker died, or the
box did, or nobody ever started `somnia-worker`. Check
`journalctl --user -u somnia-worker`.

Under those are the renders that ended in the last day, and a failed one says
why in a sentence — *Gutenberg has book 4321 but no HTML edition, so somnia
cannot read it*. They go away by themselves after a day. There is nothing to
dismiss and no badge or count anywhere: a book finishing at 3am is
not news to somebody asleep, and it is on a screen nobody opens at 3am.

Searching is the top of this screen, and it is what you came here for: type part
of a title or an author and press *find*. That searches
the copy of the Gutenberg catalog on this machine, so it answers in the time a
tap takes and works with the internet down — run `somnia catalog-update` if a
book you know exists is not in it. A book somnia already has, or already has
coming, is marked and offers no button; a render that died is marked *part
rendered* and offers *finish this one*, which picks it up at the chapter after
the last finished one. One press queues it, and the sentence underneath is the
server's own — the same sentence the agent says when you ask it out loud.

*stop reading this* takes two presses, and the second one only asks. The render
stops at the end of the sentence it is reading, about twenty seconds later,
which is what keeps every chapter that was finished playable and stops the
index filling up with half a chapter. The row stays as the record of a render
somebody stopped.

At the foot is *skip button size* — fifteen, thirty or sixty seconds — which is
what the two buttons either side of play on the player mean, and what they say.
Set once, probably never again, which is exactly why it is here and not on a
screen read at night.

*Workshop* asks the server how things are going every five seconds while it is
open, and stops the moment it is closed or the phone goes in a pocket. Nothing
about the queue is polled otherwise — and since this is the only screen the
queue is on, and it is two presses from the player behind a row that says
*daytime*, no night has a five-second wake in it.

There is no settings screen and there is not going to be one. The two things
that wanted one are *how dark*, which is a night control and lives on *Books*
where it can be judged against the dark page it is changing, and *skip button
size*, which is configuration and lives here. Two controls that share nothing
but being adjustable are not a screen.

## Check screen-off playback before you trust a night to it

Everything above rests on an installed PWA being allowed to keep playing with
the screen off, and on its notification surviving a chapter boundary. The first
was confirmed on 2026-08-06 and is not an open question; it is the check to run
again on a new phone, after an Android update, or on the first night that goes
quiet. The second was confirmed on the same night on the phone's own speaker,
and that turned out not to settle it — over Bluetooth the notification is torn
down and rebuilt at every boundary, and some nights it does not come back. That
is issue #31, and it is why this page now asks a second question as well. Both
are properties of the handset rather than of this code, and neither can be
tested from a desk.

It is checked with a page of its own, which generates its own audio so it needs
no library, swaps chapters the way the player does, and writes every
media-session event to a log held in local storage — so the evidence survives
the page being discarded, which is one of the things being tested for.

It is served alongside the app, at:

```
https://<node>.<tailnet>.ts.net:8443/spike-background-audio.html
```

Open that on the phone. The line under the readout says whether it is running
as a browser tab or as an installed app; the installed case is the one
everything rests on, and it is the one Android treats more generously, so a tab
that keeps playing is good news for both while a tab that stops is not by itself
proof about the app.

In *Tone chapters*, press *Start* and confirm you can hear a tick once a second
— the tick is the cheapest stall detector there is, because you can hear time
passing with the screen off. Lock the phone, leave it two minutes, and wake it.
If **shortfall** is under a couple of seconds, nothing ever stopped it. Then
press every button you own — the lock screen, the pillow speaker, the headphones
— and check each one appears in the log, and use *Agent move* to confirm the
book can be moved and played again with no gesture at all, which is what the
agent does every time it takes you somewhere.

That mode is also a demonstration of the bug: it gives the element a new file at
every chapter, exactly as the player does, and **src writes** on the readout
counts the teardowns.

### Whether one file can carry a whole book

*Whole book* is the other question, and it is the one that decides whether the
player can stop letting go at a boundary. It loads a real book — the longest one
somnia has, or `?gid=<gid>` for a particular one — from a single URL,
`/api/stream/{gid}/{n}`, and never touches the element again: a chapter boundary
becomes arithmetic on the render clock, and the only thing that happens is that
the notification is renamed. `?book` on the URL starts the page in this mode, so
a home-screen shortcut can go straight to it in the dark.

It has to be run over Bluetooth with the screen locked, because that is the
route the last check got wrong. Watch **src writes** stay at 1 all night; watch
**chapter changes** climb without it moving. Then look at the notification
across a boundary — no log can see this, and it is the whole question: does the
panel keep the same session and simply change its title, or does it blink out
and come back?

Four other things are worth doing while it is up, all of them nightly in the
real player:

- *Seek to the middle*, which is the morning resume: the log says how long the
  seek took and how long until sound came back.
- Watch **holding** — the byte ranges Chrome has kept. If the first range goes
  on starting at 0 all night, the phone is holding the whole book.
- Turn the tailnet off for half a minute and back on. A stall shows as
  **shortfall**; whether the phone had to fetch the book again shows in
  **holding**, and the other half of that answer is in the server's own log —
  `journalctl -u somnia -f` shows a second `GET /api/stream/...` if Chrome
  threw the book away and asked for it again.
- Press the pillow speaker's skip and its scrubber. The panel is told the
  *chapter's* length and not the book's, so what those buttons move by is the
  question, and the log writes down what the panel was told each time.

It is a spike and it is meant to read like one. It is served rather than kept
out of the way because a diagnostic nobody can open from the handset is a
diagnostic nobody runs, and these are the two questions the whole pivot rests
on.

### Asking the same question of the real player

The player itself now loads the whole book from one URL, so the spike is no
longer the only place the question can be asked. To compare the two ways on the
same night, over the same speaker, open the app with `?chapters` on the address:

```
https://<node>.<tailnet>.ts.net:8443/?chapters
```

That plays the book a file at a time, the way it played before — a load at every
boundary, which is the bug — while the app opened normally plays it from one
file. Nothing else about the page differs, and nothing is remembered: it is a
property of the address, so closing the tab is the whole of undoing it.

Listen across a boundary each way, locked, over Bluetooth. The answer is what
the notification does, and there is nothing on any screen or in any log that can
stand in for it.
