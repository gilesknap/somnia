# 7. Cross a chapter without letting go of the player

## Status

**[ADR 9](0009-drop-audiobookshelf.md), 2026-08-10, replaces the reason given below for keeping the joined files out of the library.** The placement is unchanged.

Accepted, on a handset check that was made **over Bluetooth** — the route the
teardown was reported on, and the one ADR 3's check was never run on. The end of
*Consequences* says exactly what was observed and what is still untested, and it
should be read before anything here is quoted.

This refines [ADR 3](0003-play-the-book-in-the-page.md) rather than reversing
it. The page is still the player, the position is still somnia's own, and every
consequence that record lists is still the bill. What is new is that ADR 3
assumed crossing a chapter was free, said so on the strength of one night's
check, and was wrong; its amendment of 2026-08-08 withdraws the claim, and this
record is what the mechanism became instead.

## Context

The page held one `<audio>` element and stitched the per-chapter files into one
timeline. Crossing a chapter therefore meant assigning `player.src`, and that
assignment is not the small thing it reads as: it runs the media element load
algorithm, which **empties the element**, and an element holding no media has
nothing for Chrome to hang a platform media session on. The lock screen card
comes down, and is rebuilt on the far side out of whatever the page says next.

Over Bluetooth — audio focus taken again, the A2DP route re-established — that
rebuild is slow enough to see, and on some nights it did not finish at all. What
that leaves at 2am is a locked phone with no transport on it and a book that has
stopped, and the only person who could do anything about it is asleep. On the
phone's own speaker it has not been seen, which issue 31 is careful to say "may
only mean it is rarer there"; the obvious reading is that the rebuild is over
before it can be noticed on the forgiving route, but that is an inference from
one absence and nobody has watched for it.

There is a second failure riding on the same line, and it is the one the handset
actually reported. A boundary was not merely an element event; it was a *fetch*,
forty-nine times a book, over a tailnet, at three in the morning. The two
sentences that came back from the handset were "the book stopped arriving" and
"still trying to reach the book" — both from the network retry ladder, neither
from the autoplay path. So the boundary was also the page's most frequent
opportunity to need the network at the worst hour to need it. A mechanism that
crosses a chapter without asking for anything removes that opportunity
altogether, which is a larger win than the card staying up.

## The alternatives we rejected

**Two elements, ping-ponged.** Load the next chapter into a second element while
the first still plays, so the count of players in the tab goes 1 → 2 → 1 and
never touches zero, and Chrome never has cause to drop the session. It is a
cheap change and it might well work. It is rejected because nothing here can
ever say whether it does: the fake media session the web tests are written
against has no player set and no audio focus, so a page that blinks and a page
that does not are byte-identical to it — the single claim the route rests on is
outside the reach of the suite that would have to defend it, and a Chrome
release can revoke it silently. It also invents a failure the current design
cannot have. If the incoming element's `playing` never arrives, two chapters
play at once at full volume in a dark room, and the guard against that is a
`setTimeout` in a page the phone throttles to roughly one wake a minute. And it
makes the fade a per-element question for the first time: a boundary landing
inside the twenty seconds of a sleep fade would return the book to full volume,
which is the loudest thing that can happen at 2am and would happen silently.

**Media Source Extensions.** The only route that fixes the boundary *and* the
render frontier by construction, and the most honest of the three about what it
costs. It lost on cost per unit of proof. It cannot ship against the library as
it stands, because ingest writes plain `+faststart` MP4 and MSE cannot append
that, so it needs a second encoding of everything before it can play a note. It
cannot land incrementally. Its riskiest component — a windowed, byte-ranged,
quota-aware append-and-evict queue running unattended for eight hours with
throttled wakes — has no analogue anywhere in this codebase. And a fake
`SourceBuffer` accepts any bytes you hand it, so the one question worth
answering, *do these fragments append on that phone*, is structurally outside
the harness that would be written to answer it. It also converts a per-chapter
fault into a session fault, and its recovery from one is a new blob URL, a `src`
assignment and a gestureless `play()` — precisely the sequence the route exists
to prevent. It is not dead: it is where to go if the handset ever says no to
what is written below.

**Accept the blink, and fix only "never comes back".** Rejected as the answer,
kept as the floor. The per-chapter path is still in the page and is still what
runs when there is no join to be had, so a night that cannot have the good
mechanism has the old one rather than nothing. What made it wrong as *the*
answer is that it treats a nightly teardown of the only control surface the
listener has as weather.

## Decision

**A book is one file, served from one URL, and the element is loaded once.**

The server joins a book's chapters with ffmpeg's concat demuxer and `-c copy`,
so not a byte of audio is re-encoded; the joined `mdat` was measured, on all
forty-nine chapters of Black Beauty, to be the exact concatenation of the
chapters' own, and the render clock the manifest speaks carries over as an
identity. A join lives at `SOMNIA_DATA_DIR/streams/{gid}/{n}.m4a` and **never**
in the library, because the library is Audiobookshelf's own layout and ADR 3
promises the ABS app goes on working on it. `n` is a version rather than a
length: it names how many chapters the file holds, so a book that grows while
somebody is listening is offered a *new* file and the one their phone has open
is never rewritten underneath an in-flight range request.

The manifest gains `stream_url` and `stream_ms`. `stream_url` is advertised on
the strength of the chapter rows and not of any file: the join is built by the
first request that wants it, so at manifest time there is nothing to look at, and
building one to find out would put a second or two of ffmpeg in front of every
poll of a book that is still being read. It is omitted only for a book with no
chapters at all. A join that then turns out to be impossible answers **404**, and
the url per chapter stays beside it in every manifest, because a book with no
join must be a book that blinks rather than a book that will not open. What turns
that 404 into a blinking night rather than a lost one is the page's own rule
below, and nothing on the server.

In the page, a chapter boundary becomes arithmetic. `enterChapter` sets which
chapter is current, hands the platform new metadata and redraws the screen, and
touches the element at nothing at all. There is no source to assign, no load
algorithm to run, nothing to empty, and therefore nothing for the platform to
take the session down with.

**The frontier is a pause, not an end.** A book being listened to while it
renders is a book whose element holds a join built before the chapters it is now
being asked for. The comparison is between what the element was given and what
the manifest says *now*, and never inside one manifest: the server writes
`stream_ms` as the last chapter's end and `total_ms` is bumped to the same number
as each chapter lands, so those two are equal in every manifest it can produce. A
page that watched for `stream_ms < total_ms` would watch for something that never
happens, run off the end of the join, and lose the card for the whole wait.

So the source is short of the book when either the manifest names audio this
source does not hold, or the render is still running and will make some. The
first of those is loaded through at once and the sound never stops. Only the
second is the pause: the element must not be allowed to reach `ended` — `ended`
removes the player from the session and destroys the card for the whole of a
render wait, which is the same loss by another road — so the page stops the sound
a fraction before the end of what it holds, asks the server for the rest of the
book from inside the same handler, and waits. A pause *suspends* a session rather
than ending it: the card stays up, with a play button on it, for as long as the
wait lasts, and the book resumes from where the sound stopped once the next
chapter has landed.

That first ask is immediate rather than on the ladder's first rung because with
the screen off nothing else refreshes the manifest — `visibilitychange` is the
only caller a night has, and a phone in a pocket never fires one — and because
the page has just made itself inaudible by pausing, after which its timers are
throttled to roughly one wake a minute.

**A join that is not there is abandoned, once, per book.** A url that has been
loaded even once is a file that exists, so every later failure of it is the wire
and the answer is to go on trying until morning. A url that has never yielded a
duration and goes on not yielding one is a join that is not coming, and the night
drops back to a file at a time — blinking, but playing — for the rest of that
book, because a concatenation that could not be made is a fact about the book it
was made from.

What decides "goes on" is the spacing and not the count, and the frontier is why.
The join asked for there is new by construction and has never loaded by
definition, so two failures two seconds apart — one tailscale re-key — would
condemn a file that was there the whole time and cost the night its card to fix a
network problem. So two failures count as two answers only when they are
`RETRY_MAX_MS` apart, which is the point at which the retry ladder itself stops
waiting any longer for a network it cannot see; and they are counted against the
url they were about, since what is known of the five-chapter join is not evidence
about the six-chapter one. A join that is really missing costs half a minute of
silence before the per-chapter path comes back under the listener, and no outage
shorter than that can cost a book its join.

## Consequences

**A second copy of every book on disk.** About 161 MB for a five-hour book;
somnia's library goes from 730 MB to roughly 1.46 GB against 859 G free on
nuc2, so the disk cost is real and currently irrelevant. It is deliberately in
`SOMNIA_DATA_DIR` and not in `SOMNIA_LIBRARY_DIR`: a second copy of every book
appearing among ABS's own files would break ADR 3's promise quietly, in a scan
nobody was watching. The joins are a cache and nothing else — deleting the
`streams` directory costs a second or two of ffmpeg per book the next time each
is opened, and costs no data at all — but **nothing reaps them yet**, and that
is deliberate too.

One book is not necessarily one copy, and the worst case is much worse than
161 MB. A version is named by how many chapters it holds, and a book listened to
while it renders reaches a new version every time the listener catches up with
the frontier, so on a box slow enough for that to happen at nearly every
boundary the disk ends up holding a join of the first chapter, of the first two,
of the first three, and so on. That is arithmetic rather than a measurement: for
a forty-nine chapter book it sums to about twenty-five times the book, some four
gigabytes for a five-hour Black Beauty, none of which is deleted by anything. In
practice it does not arise, because steady listening does not reach the frontier
at all — see the paragraph below, which is this one wearing the other hat. It
would take a render repeatedly stopped and restarted under a listener, which is
the same short list of ways the frontier is met in the first place.

**Nothing reaps any of that, and the omission is deliberate rather than
outstanding.** The safe half of a reaper is easy and buys nothing on a box with
859 G free. The dangerous half needs a fact the server does not have: which
version some phone still has open. A version deleted under a playing element is
a 404 in the middle of a sentence at 3am, which is the exact failure this record
exists to end — and the fallback does not save it, because a url that has played
is a url the page has proved and will go on retrying until morning rather than
abandoning. So the reaper waits for its own issue and its own rules: only a
version the manifest no longer names, only with no render in flight, and never
inside twenty-four hours.

**A book cannot be served from one URL while it is still being written.** The
join holds the chapters that existed when it was built, so a book added at
eleven and listened to at midnight will run out of file before it runs out of
book. That is what the frontier pause exists to survive, and the cost is
honest: the sound really does stop, and the listener really is waiting on a
render, with a card on the lock screen saying paused. What they get in exchange
is that the card is still there when the chapter lands.

**Per-chapter error isolation is given up in the ordinary case.** The page's
`ended` handler used to carry an explicit promise: a chapter whose encode was
truncated became a skip rather than a book that hangs at 2am. In one file there
is nothing to skip to, and the element's error is now about the book rather than
about a chapter. Two things keep this survivable and neither restores what was
lost. The build is judged against the clock the chapter rows keep rather than
against ffmpeg's exit code — the concat demuxer prints "Impossible to open",
exits **zero**, and hands back however much it managed, measured on a
three-chapter book that came out eight seconds long — so a join that came out
short is refused and answers 404 rather than being served as a book with chapters
missing out of the middle of it. The manifest advertises `stream_url` all the
same, on the strength of the rows, so the page finds out by loading it; and it is
the page's give-up rule that turns that into a night which blinks its way through
a book instead of ending early. That rule is the second thing keeping this
survivable: a join that never loads is abandoned after two failures half a minute
apart, which puts the per-chapter path and its skip back under the listener at
the cost of half a minute of silence. What is genuinely gone is granularity: one
unreadable chapter file now costs the whole book its join.

**A longer time to first sound, and nobody has measured what it costs.** The
whole `moov` is fetched before a single frame decodes — about 1.73 MB for a
five-hour book, extrapolating to something near 4.1 MB for twelve hours. The
bytes are not new (the joined header is about 2% smaller than the forty-nine
per-chapter headers it replaces) but they are all up front, at boot and again on
every reload, where they used to be spread over a night. This is the first thing
to look at if a press of play starts to feel slow.

**`publishPosition` is now the only thing keeping the lock screen scrubber
chapter-scale, and it used to have help.** It used to be the loaded file's own
duration that made the scrubber a chapter wide; the page's position state agreed
with it. Now the element is five hours long and the position state is the sole
source of the smaller number. `setPositionState` throws when the position
exceeds the duration it is given, and a page that supplies no position state at
all does not get nothing — it gets the platform's fallback, which is the
element's duration. So a throw that used to degrade to roughly the right size
now degrades to exactly the wrong one: five hours of scrubber where twelve
minutes belong. That is
[design.md](../design.md)'s own objection to a whole-book scrubber — *one sleepy
thumb would fling them past the spoiler guard into the ending* — arriving by a
route nobody chose, and arriving silently, since a page whose position state
threw looks exactly like a page whose position state did not. This is why
the web harness's fake `setPositionState` throws on a bad position rather than
quietly accepting it, and why the clamp inside `publishPosition` is now
load-bearing in a way it was not when it was written.

**The frontier pause rests on an assumption about a throttled page.** It is
KNOWN that `ended` destroys the session and that a pause does not. It is ASSUMED
that `timeupdate` keeps firing at something near 4 Hz with the screen off, which
is what makes it possible to stop a fraction short of the end rather than at it.
The code says so where the check is made, and the `ended` handler is the
backstop: if the pause is missed the element ends, the card goes, and the book
still comes back when the chapter lands. That loses the panel and not the night.

**A night that starts with the tailnet down falls back and blinks.** The page
cannot tell a join that does not exist from a join it could not reach, because
in both cases nothing has been proved by nothing having been reached. Such a
night spends itself on the per-chapter path. It is the right way to be wrong —
falling back on a good join costs a blink at every boundary, and failing to fall
back on a missing one costs the whole night — but it is a real cost and it is
written here rather than discovered later.

**A listener does not normally reach the frontier at all, and this should be
said plainly because the machinery for it reads as though they would.** Measured
on 2026-08-07 with `scripts/somnia-bench.py`: nuc2 renders at 3.87× realtime and
the VPS at 1.06×. Both outrun 1× listening. A book is opened when its first
chapter exists, so the listener begins one whole chapter behind the frontier and
the gap only widens — on nuc2 quickly, on the VPS by six percent an hour, but in
neither case does it close. Steady listening never catches a running render.

What reaches the frontier is a render that is **not running**: one that was
stopped, or died, or that a deploy shot in the head, or — this being the
ordinary case rather than the exotic one — a book queued behind another, because
[ADR 5](0005-render-one-book-at-a-time.md) renders one book at a time and the
second book's frontier does not move until the first is finished. A listener
pressing through chapters faster than they play reaches it too.

So the frontier is an edge, not the path. The reason it is worth the machinery
anyway is what it costs when it is met: `ended` fires, the platform drops the
player, and the panel goes — leaving a locked phone with no transport on it and
somebody asleep in front of it. Stopping a fraction short turns that into a
paused card with a play button, which is a night that can be resumed.

**What the 1.06× measurement does mean** is that the VPS has no cushion. The
margin is the one chapter of head start plus six percent, so any interruption to
the render is recovered from slowly, and a frontier met on that box is met for
much longer. That is the second reason **moving to a slower box reopens this
decision**, and it is the condition this was accepted under.

**Finally, and in ADR 3's own words, this rests on an assumption that could only
be checked on the handset**: that Chrome, given one progressive `audio/mp4` of
about 161 MB and left playing with the screen locked for hours, keeps a single
platform media session up throughout, and that assigning
`navigator.mediaSession.metadata` on a *playing* element renames the card
without disturbing the session underneath it.

What is known is this. **On 2026-08-08 a chapter boundary was crossed on the
lock screen of the handset, over Bluetooth, and the card stayed up throughout.**

The route is the whole reason that sentence is worth writing. ADR 3's check was
run on 2026-08-06 and passed, and its route was never written down; the
teardown was then reported over Bluetooth and only over Bluetooth. So the
speaker is the forgiving route — it rebuilds the notification fast enough to
hide the fault — and a check run there could not have told this design apart
from the one it replaces. This one was run on the route that was failing, which
is what makes it evidence rather than a repetition of the mistake being amended.

It is still one boundary on one night, and three things it did not cover are
worth naming so that nobody reads more into it than it holds. It did not run
long enough to say whether Chrome keeps the session up across **hours** of a
161 MB progressive resource. It did not include a **frontier wait**, which
could not have been tested then because the machinery for it did not exist
until this record was written. And it says nothing about the **fallback to the
per-chapter path**, which by design is the blinking behaviour anyway.

So this holds a confirmation of the mechanism and not yet of the night. The
spike page stays served for the reason ADR 3 gave for keeping it — the property
belongs to the handset and not to this code — and that reason has earned itself
twice over: it is what made this mechanism cheap to try, and it is what will
make the remaining checks cheap to run.
