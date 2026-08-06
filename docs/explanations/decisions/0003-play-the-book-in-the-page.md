# 3. Play the book in the page, not in Audiobookshelf

## Status

Accepted

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
changing books is done by asking. ABS's listening sessions are gone as a data
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
that its media notification survives a chapter boundary. **Checked on 2026-08-06,
and both halves hold** — it played on with the phone locked, and it crossed a
chapter while locked. That is the ground the rest of this decision stands on, so
it is written here rather than left in a night's memory.

The spike page that answers it stays served, because the property belongs to the
handset and not to this code: a future Chrome, a battery-saver setting or a new
phone can take it away again, and the failure would arrive as a night that went
quiet rather than as anything in a log.
[how-to/serve-the-chat-page.md](../../how-to/serve-the-chat-page.md) says how to
run it.
