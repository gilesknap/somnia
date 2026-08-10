# 3. Play the book in the page, not in Audiobookshelf

## Status

**Superseded in part on 2026-08-10 by [ADR 9](0009-drop-audiobookshelf.md)**, which drops Audiobookshelf entirely: the write-through, the seeding, and the promise that the ABS app goes on working on the library files.

Accepted. **Amended on 2026-08-07**: the sentence below saying "changing books
is done by asking" no longer holds, and the paragraph headed *Choosing a book is
a press now* at the end of this file says what replaced it and why. **Amended
again on 2026-08-08**, and this one is a retraction rather than a refinement:
the handset check recorded at the end of *Consequences* was written up as though
it had settled two things, and it had settled one. The paragraph headed *The
notification did not survive a boundary* says which half failed and how the
check came to pass anyway. Everything else here stands — the page is still the
player, the position is still somnia's own, and there is still no library to
browse for something you do not have.

## Context

somnia was built on the assumption that Audiobookshelf is the player, and
[design.md](../design.md) argued for it at length. The ABS Android app already
had screen-off playback, Bluetooth controls, a sleep timer with
shake-to-extend, fade-out and smart rewind; writing any of that again looked
like a great deal of work with nothing at the end of it that did not already
exist. "Take me to where the horse dies" was therefore implemented as a write —
`PATCH /api/me/progress/:id` — so that the next tap on play starts in the right
place.

The next tap on play is the problem. ABS has no transport API: nothing in it
can make a client play, pause or seek. The Android app has no deep link either,
so nothing outside the app can reach the button. The two gaps together mean
somnia could move the book and then had to ask the listener to finish the job.

A worse thing follows from the same gap. While a client holds an open playback
session it syncs its own `currentTime` back every few seconds, so a position
written underneath it is silently undone. `move_to` had grown a session hunt, a
settle wait and three attempts at outlasting a player that would not give up —
and even when it won, the audio already in flight kept playing, because there
was no way to tell the app it had been moved.

So the night went: pause by hand, ask, press play by hand. Two of those three
are someone half awake operating a phone in the dark, which is the exact thing
this project exists to remove. Bookmarks were rejected on those grounds
already: a bookmark is a signpost, and finding the new one among all the
others, in a menu, in the dark, is most of the work the agent was supposed to
remove. "Now press play again" is the same rejection wearing different clothes.

## The alternatives we rejected

Every one of these is a way to press play on the phone from somewhere else, so
that ABS could stay the player.

**Tasker or MacroDroid on the phone, driven from the VPS.** Both can hold an
HTTP listener and dispatch a media key, so `move_to` could write the position
and then ring the phone. It requires the VPS to open a connection into the
tailnet, and the ACL never lists `tag:vps` as a source. That is not an oversight
to patch: the VPS runs experiments, is treated as untrusted-ish, and the
one-way rule is the whole reason it is safe to keep somnia on it. An ACL
exception for a play button inverts the security model of the deployment to buy
back one gesture.

**The same, driven from the page over loopback.** The page is already on the
phone, so it could talk to a listener on `127.0.0.1` and the VPS would initiate
nothing. Three separate browser mechanisms stand in the way. The page is served
over HTTPS and the listener speaks HTTP, which is mixed content and blocked
outright. The request is cross-origin, so the listener has to satisfy a
preflight it was never designed to answer. And reaching a local address from a
public page needs Local Network Access permission, which Chrome has enforced
since version 142 and which prompts — a permission dialog at 2am, in the dark,
standing between them and the book, is worse than pressing play was. Each of
the three is also one Chrome release away from moving again.

**Home Assistant's companion app.** `notify.mobile_app_*` with `command_media`
does precisely this, properly, over a channel built for it, and if Home
Assistant were already running here it would be a few lines and this ADR would
read differently. It is not running. Standing up HA — its server, its updates,
its supervision, for the rest of the project's life — in order to press play in
an app that is already playing is the largest dependency on the list bought for
the smallest feature on it.

**Termux plus Shizuku.** A shell on the phone can dispatch a media key without
root, and it works well the day it is set up. It stops working at every reboot:
Shizuku has to be re-granted over ADB or by a re-pair, and a bedside audiobook
that needs a laptop after every restart is not a bedside audiobook.

What the four have in common is that they buy one gesture by adding a second
system on the phone which must keep working, silently, unattended, every night.
The gesture is not worth that.

## Decision

The PWA becomes the player.

somnia rendered the audio, so it can serve it. `chapters` already carries idx,
title, start_ms, end_ms and audio_file, so the manifest a player needs is one
SELECT and each chapter is one route; Range requests, and therefore seeking,
are Starlette's own. The page holds a single `<audio>` element and stitches the
per-chapter files into one timeline counted in global milliseconds — the same
clock the search index, the chapter marks and the agent already speak — so
which file a position lands in is an implementation detail of three functions.
The Media Session API puts the transport on the lock screen, in the
notification shade and on whatever is paired over Bluetooth, which for most of
the night is the only transport there is.

Pause, seek and play become local JavaScript. "Take me to where the horse dies"
now ends in sound rather than in an instruction.

The position becomes somnia's own record. `books.position_ms` holds it,
`position_seq` counts agent moves and nothing else, and `position_at` is how a
cold launch knows which book to open. The page says where it has got to every
fifteen seconds while it plays, at every jump and boundary, whenever the sound
starts or stops, and once more on the way out of a book it is leaving; a report
carrying a stale count is refused, and the refusal is also the instruction to
jump. Audiobookshelf is told afterwards, best effort, only when the listener
has stopped — and never read.

## Consequences

The move completes. Nobody presses play, and nothing has to be timed against a
client that might overwrite the position, so `move_to`'s three attempts, the
session hunt, `open_sessions`, `close_session` and `Config.move_settle_s` are
all deleted rather than repaired. There is nobody left to argue with about
where the book is. A seek is now a local assignment rather than a round trip
through another server, and the player reads sqlite on its own connection, so
it never queues behind a twenty-second model turn. The agent can also move a
book that was not even open, which was impossible before.

The bill is that the page now has to do everything the app did, and it does not
do all of it.

**Offline downloads are gone, and that is the largest loss.** The ABS app keeps
a book on the phone; the page streams every chapter from the VPS over the
tailnet, and the service worker cannot help — a ranged reply is a 206 and the
Cache API refuses to store one, so the audio is deliberately excluded from it.
The book therefore needs the tailnet all night. Wifi that drops at 3am takes
the book with it, where the app would have played on from a local file.

Everything that used to be somebody else's problem about a bad night is now
this page's. A media element that has taken a network error never fetches
again, so the page has to notice the silence and put the chapter back under
them, from where they had got to, waiting longer each time. A manifest is a
photograph of a book that is still rendering, so it has to be asked for again
or the night ends three chapters into forty-nine. And the page is discarded
whenever the phone wants the memory, so anything meant to outlive tonight has
to be written down rather than held in a variable. None of that is visible with
the phone locked — it all looks like a notification saying paused — which is
why each of them says what is happening where it can be read as well as doing
something about it. The other cost of the same move is that most of somnia's
behaviour now lives in JavaScript, so it is tested there too: Node's own test
runner over a fake media element, no browser and no npm install, because pytest
can see none of it.

The sleep timer is reimplemented and does not match. Fifteen, thirty, forty-five
or sixty minutes, or the end of the chapter, counted in listening time rather
than clock time, ending in a twenty-second fade. There is no shake-to-extend:
it needs a motion permission and a threshold nobody can guess at from a desk.
It is written to `localStorage` as it counts, because a timer kept only in a
variable was disarmed by every reload and by the phone discarding a
backgrounded tab, silently and with nothing on screen to say so, and the book
then played until morning — which is the failure the timer exists to prevent.
A timer more than six hours old is not restored: opening the book the next
evening is starting a night, not finishing one.

Smart rewind is reimplemented as a ladder on how long the sound was off —
nothing under half a minute, then eight seconds, twenty, and thirty at an hour —
and the longest rung snaps back to the start of the sentence, which ABS could
not do because it does not know where sentences are. The thresholds are no
longer configurable, because they are no longer settings.

Playback speed is simply not there: nothing changes the rate, and there is no
control for it. Nor is there a library browser, a chapter list, Android Auto,
or listening statistics. The page opens the book they were last listening to;
changing books is done by asking. **That last clause was amended on 2026-08-07
— see the end of this file.** ABS's listening sessions are gone as a data
source too, so the play/pause history the design hoped to infer sleep onset
from no longer exists — what is left is `position_at` and the reasons the page
gives when it reports. Nothing seeds the spoiler guard from ABS while a night
is running either, so a book somnia has never been played from stands at a
high-water mark of zero and is searched no further than its opening minute
until the page has played some of it.

The exception is `somnia seed-positions`, which is run once by hand and is the
only thing left that reads Audiobookshelf. Every book rendered before the pivot
has its position and its listening history there and nowhere else, so without
it the first night opens the book most recently added, at 0:00, and answers
questions about the rest from the first minute of it. It never lowers a mark
and never overwrites a position somnia already holds, so running it twice is
harmless — and after it, ABS is write-only again.

None of this is one-way. The library is still on disk in ABS's own layout, the
ABS app still works, and position write-through stays, so opening ABS somewhere
else finds roughly the right place. The asymmetry is worth stating plainly:
somnia writes to ABS and never reads it, so a night spent listening in the ABS
app is a night somnia does not learn about. If offline listening turns out to
matter more than being moved to the passage, the app is still there to do it.

Finally, this rested on an assumption that could only be checked on the handset:
that an installed PWA keeps playing with the screen off on Android Chrome, and
that its media notification survives a chapter boundary. It was checked on
2026-08-06 and written down here as *both halves hold* — it played on with the
phone locked, and it crossed a chapter while locked. **The second half was
withdrawn on 2026-08-08 and the sentence that claimed it is struck; see the end
of this file.** The first half stands and has stood every night since. That is
the ground the rest of this decision stands on, so it is written here rather
than left in a night's memory.

The spike page that answers it stays served, because the property belongs to the
handset and not to this code: a future Chrome, a battery-saver setting or a new
phone can take it away again, and the failure would arrive as a night that went
quiet rather than as anything in a log.
[how-to/serve-the-chat-page.md](../../how-to/serve-the-chat-page.md) says how to
run it.

## Amendment, 2026-08-07: choosing a book is a press now

**"Changing books is done by asking" is withdrawn.** The books panel lists the
books somnia already has, under `on the shelf`, and a press opens one where it
was left. Asking still works and is still the shortest way to say it out loud.

What made this reversible is that the sentence was never load-bearing on its
own. It was one line of a paragraph about what the pivot cost, listed beside the
chapter list and Android Auto, and what it was really refusing was **a library
browser**: a screen you go to in order to find something you do not have, which
is a second place to get lost in at 2am and a screen full of books you have
never heard of. That objection has not moved an inch. The page does have such a
search now — the Gutenberg catalog, seventy-five thousand books nobody owns —
and it is a separate act, which
[ADR 5](0005-render-one-book-at-a-time.md) argued into existence as *adding*.

**Further amended 2026-08-08**: it is a separate act on a separate *screen*
now. The panel was cut in two — `Books` at night, `Workshop` in daylight — and
the search went with the daytime half, behind a quiet `workshop ›` pill in the
night one's own header. That is the same argument this amendment makes, made twice: what a
2am screen must not be is a place to go looking for something you do not have,
and the surest way to keep it from being one is for the looking to be somewhere
else.

A shelf of three books you already have, each one a place you left, is not that
search wearing a hat. It is the cold launch's own question — which book — asked
at a moment other than a cold launch, and its answer is one tap on a book whose
name you recognise.

The other half of the argument is the mechanism, which is what makes a wrong
press cheap. Positions have been per book since this ADR was written:
`position_ms`, `position_seq`, `position_at` and `heard_to_ms` are columns on
each row, and `last_gid` is simply the book with the newest `position_at`. So
switching books is one write of one column, `POST /api/book/{gid}/open`, and it
touches nothing else — not the position, not the mark, and above all not
`position_seq`, because that counts agent moves and a page that came away
holding a stale count would have its next report refused and be dragged back.
Nothing is moved, nothing is heard, and the book being left keeps its own place
to the millisecond. **Changing your mind costs exactly one press back**, which
is the property a list of books has to have before a half-asleep thumb may land
on it, and it is the reason this is a smaller decision than the ADR it amends.

Two edges are written down because they cost something. A book with no audio yet
cannot be opened — the route answers 404 and the shelf offers no press — because
making it the most recent book would leave the *next* launch waiting on a render
rather than on the book that was playing, silently. And the timestamp the route
writes is a couple of seconds ahead of every other book's, because
`datetime('now')` counts whole seconds and the write it has to beat is the
page's parting report for the book it is leaving, which lands milliseconds
later; a tie there is broken by which book was added first, and a reload would
have opened the book they had just left.

What is still not here: a chapter list, Android Auto, listening statistics,
playback speed, and any way to reach a book somnia has not rendered except by
adding it. The page still opens the book you were last listening to. What
changed is that there is now a way to say which one that is without composing a
sentence.

## Amendment, 2026-08-08: the notification did not survive a boundary

**"Checked on 2026-08-06, and both halves hold" is withdrawn.** The first half
holds: an installed PWA does keep playing with the screen off on Android Chrome,
and it has done so every night since. The second half is false. The media
notification does *not* survive a chapter boundary, and the way it fails is the
way this project's failures always fail — the book goes quiet and nobody finds
out until morning.

What actually happens is that a boundary assigned `player.src`, which runs the
media element load algorithm, which empties the element; and an element holding
no media has nothing for Chrome to hang a platform media session on, so the
notification comes down and has to be built again on the far side. Over
Bluetooth, where audio focus has to be taken again and the A2DP route
re-established, it is slow enough to see — and sometimes it did not complete,
which at 2am means a locked phone with no transport on it and a book that has
stopped. That is [issue 31](https://github.com/gilesknap/somnia/issues/31), which
reports it as repeatedly seen on Bluetooth and not seen on the phone's own
speaker, while declining to conclude anything from the second half: "that may
only mean it is rarer there".

**How a check of a false property passed.** The spike page this ADR points at,
`spike-background-audio.html`, is what was run on 2026-08-06, and at that date
`loadChapter()` was `audio.src = …; audio.load()` — the one-element path, the
very thing that turned out to be the bug. So the check was not wrong about what
it saw; it saw a real page do a real boundary. What is not known is the audio
route it saw it on, because nobody wrote it down, and the check passing is the
only evidence there is about it. Either it was the phone's own speaker, where
this failure has never been seen and is presumably too quick to notice, or it was
Bluetooth on a night the failure did not land — issue 31 reports it as
intermittent even there. Both readings say the same thing, and it is the thing
this amendment exists for: the result was written up as a property of Android
Chrome when the most it could ever have been was a property of one route on one
evening. **A check made on one audio route is a check of one audio route**, and
a route nobody recorded is a route nobody knows.

**What this ADR got right, and it deserves saying.** Two paragraphs down from
the sentence being struck: *the failure would arrive as a night that went quiet
rather than as anything in a log*. That is exactly, and only, how it arrived —
there is no traceback anywhere for issue 31, and there never was going to be.
The same paragraph's reason for keeping the spike page served, that the property
belongs to the handset and not to this code, is what made the second check cheap
enough to run: the page was still there, still reachable, and a whole-book mode
was added to it in an evening.

**What replaced the mechanism**, and not the decision: the page is still the
player and everything else in this record stands. How a boundary is crossed is
now its own decision, with costs of its own, in
[ADR 7](0007-cross-a-chapter-without-letting-go.md).
