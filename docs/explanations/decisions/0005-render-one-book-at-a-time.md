# 5. Render one book at a time, in its own unit, and let the page watch

## Status

Accepted. Two things below are out of date and both are about the screen rather
than the mechanism. This panel *does* open books now — `on the shelf`, added
2026-08-07 — and it is no longer one panel: it was cut in two on 2026-08-08,
`Books` at night and `Workshop` in daylight, with the catalog search, the queue
and the ended rows all on the daytime half. The paragraph headed **The page
watches, and adds, and never opens** is annotated where both matter.

Nothing about the queue itself, the worker unit, the lease or the heartbeat is
affected by either. What was added in the first was a list of books somnia has
already rendered and one write of `position_at`; the second moved elements
between two overlays and moved the poll with them. The argument for the first
reversal is in [ADR 3](0003-play-the-book-in-the-page.md)'s amendment.

## Context

Adding a book has no queue. `Library.add_book` spawned `somnia add` with
`start_new_session=True` and all three stdio at `/dev/null`, discarded the
handle, and returned a sentence promising chapter one in a few minutes. Two
requests a minute apart gave two Kokoro processes on two vCPUs, and the render
then no longer outruns 1× listening — which is the assumption the whole of
streaming ingest rests on. [design.md](../design.md) says so: at about 1.15×
realtime the renderer outruns a listener with a thin margin. Two renders halve
a thin margin, and the sentence about chapter one stops being true.

Worse, nothing could be seen. An agent-started render wrote one line to the
server's log saying it had begun and then nothing at all; a `database is
locked` after the five-second busy timeout raised into a process whose stderr
was `/dev/null`, and the render simply vanished, leaving `status = 'rendering'`
for ever. Nothing recorded how many chapters a book *has*, so no honest
fraction existed. Nothing distinguished a render that had died from one that
was merely slow — the only evidence either way was whether the chapter count
was still moving, and the only thing that knew when it last moved was the mtime
of an m4a. There was no cancel: you killed it by hand and the row stayed as it
was. And there was no resume, so restarting a dead render started at chapter
one and added a second copy of every passage to the index
([#11](https://github.com/gilesknap/somnia/issues/11)), which is why
[keep-renders-running.md](../../how-to/keep-renders-running.md) said, in bold,
*do not add `Restart=`*.

The deploy makes it sharper than it looks. `somnia-serve.service` carries
`Restart=always`, and deploying is pull main and restart the unit.
`start_new_session=True` escapes the session and the process group but not the
cgroup, and the unit uses the default `KillMode=control-group` — so every
render the agent has ever started was already shot dead on every deploy,
silently, leaving a row claiming work that nobody was doing. Every book on the
VPS stuck on `rendering` is one of those.

## The alternatives we rejected

**A render thread inside `somnia serve`.** The obvious one, and it fails on the
sentence the feature exists to defend. Kokoro and the embedder resident in the
process that answers the page means a restart costs twenty seconds rather than
one, an OOM takes the page down with the book, and the renderer competes for
both cores with the thing serving a 206 — which contradicts the fast lane's own
premise, written in `server.py`, that a seek is never stuck behind a model
turn. It can be nice'd, but a renderer nice'd below 1× realtime fails the
streaming premise outright, and "one at a time, slowed down" is a worse remedy
than "one at a time". A separate unit gets the page the same protection with
`Nice=` and `CPUWeight=` without gambling on the margin.

**A lock file instead of a heartbeat.** `flock` answers "is anything rendering"
in one syscall and needs no schema at all. It cannot answer the question that
matters: a wedged process still holds its lock, so the queue reads healthy for
ever, and a page showing "rendering" for six hours of nothing is worse than one
that says the renderer has gone quiet. `beat_at` is the only thing that tells a
crashed renderer from a slow one, and because staleness is computed when
somebody looks rather than written down by anybody, the answer stays honest
even when the worker unit has been stopped and there is nobody left to write.

**A new `books.status` value for "stopped".** Rejected because `pending` is the
schema's own default and grep says nothing has ever written it, so it already
means exactly "not growing and not finished" — no migration, and four published
documents stay true verbatim. The published enum stays `pending, rendering,
done`.

**Cancelling with a signal.** Instant, rather than the twenty seconds a
heartbeat costs, and it can land anywhere: including the two lines between a
chapter's passages being indexed and its `chapters` row being written, which
leaves the index holding words the player's manifest cannot see — so a place
the listener chose would send them past the end of their own timeline. Between
sentences is the only safe place to stop, and asking is the only way to stop
there.

**Automatic retry of anything that failed.** A queue that spends the night
failing the same book is worse than one that stops and says why. Interruptions
are picked up again, because a deploy and a reboot are somnia's business and
not the listener's; a child that ran and then died is not.

## Decision

**Renders leave `somnia serve` altogether** and run under a second systemd user
unit, `somnia-worker`: a thin supervisor with no torch in it that spawns one
child per book and waits for it. Restarting `somnia serve` — which is what a
deploy is — now costs a render nothing. Kokoro and the embedder never enter the
process that answers the page, so a restart stays a second rather than twenty,
an OOM kills one book instead of the night, and the fast lane keeps its promise
against CPU as well as against the connection. The child exits between books
and takes every megabyte of the model with it.

**One at a time is a guarantee, not a convention.** The claim is one guarded
`UPDATE ... RETURNING` over a new `queue` table whose `WHERE` refuses while any
row has a heartbeat newer than ten minutes. sqlite has one writer, so two
claimants cannot both see an empty slot: the second takes the write lock only
after the first has committed, and re-evaluates its own condition. That is the
same idiom `tools._write_position` already uses, where an empty result set is
the answer. `somnia add` by hand takes the same claim, so there is exactly one
function in the codebase that renders a book and it always holds a lease.

**The heartbeat does three jobs in one statement** — `UPDATE queue SET beat_at
= datetime('now') WHERE id = ? AND lease = ? RETURNING cancel`. It proves the
lease is still ours, renews it, and carries the cancel flag back. So
cancellation needs no signal, no pipe and no IPC: the child asks for it,
between sentences, on a database three writers already share. A stop between
sentences writes nothing at all, because `_render_chapter` encodes the whole
chapter on its last line — no partial m4a, no chunks, no chapters row. The
lease is a uuid4 and never a pid, because pids are reused after a reboot and a
lease must not be resurrectable.

**A crashed renderer is told from a slow one by `beat_at` alone**, computed at
read time and stored nowhere, so the queue says "not responding" honestly even
when the worker unit is stopped. `books.chapters_total` is written with the
existing upsert the moment `fetch_book` returns, which is the denominator that
makes "chapter 4 of 39" possible at all. A resume starts at the first missing
chapter and continues the global timeline, which is safe only because
`add_chunks` now deletes before inserting: that closes #11 and is what earns
`Restart=` on a unit for the first time.

**The page watches, and adds, and never opens.** One `library` control in the
top-left corner of the header — as far from the thumb as the geometry allows,
and the only thing in that corner on the screen the book is on — and one overlay
behind it, a sibling of `#candidates` and last in the document, which polls only
while it is open and the page is visible. It searches the catalog, submits,
shows what is rendering and what is waiting, and stops one. It never switches
what is playing, so [ADR 3](0003-play-the-book-in-the-page.md)'s "the page opens
the book they were last listening to; changing books is done by asking" stays
literally true: a catalog search for *adding* is not a library browser.
(**Amended 2026-08-07**: the panel does open books now, from a shelf of the ones
somnia already has, and ADR 3's clause was withdrawn to allow it. What that
amendment kept is the distinction this paragraph turns on — the catalog search
is still *adding*, and still a different act from picking up a book you have.)
(**Amended 2026-08-08**: that distinction is two screens now. The panel had
grown to eight blocks and could not be read in the dark, and what fixed it was
cutting on *when* each block is used: `Books` is the night half — the book
playing and the shelf — at the player's own type size, and `Workshop` is the
daytime half — the catalog search, the queue, the ended rows and the server
note — smaller and denser than anything else in the app, behind a quiet row at
the foot of `Books`. The two settings that were filed one to each screen are on
a third, `Settings`, reached from the player's own top-right corner: both are
set in the dark with the book playing, which is a fact about when they are used
and not about what they are. The poll went with the queue, so
the five-second wake is now on a screen two presses from the player that nobody
opens at 3am. The header pill says `books` and the panel says `Books` back.)
The way out is a `‹ controls` pill in the top left — the same corner and word as
the way out of `#candidates`, and the same shape as the `books` pill that opened
this; `Workshop`'s says `‹ books`, because that is where it goes — and it is
inert in the full sense
[ADR 4](0004-choose-a-place-from-a-list.md) gave that word; the destructive
control is `stop reading this`, two presses, quiet and dashed and nowhere near
the transport.

**A child that exits non-zero is a failure, not an interruption.** It records
its own ending for everything it survives, so a row still saying `rendering`
after the process has gone means it was killed outright — and the supervisor,
which is the one process that can prove nothing holds that row because it
waited for the pid itself, closes it as failed with the exit code in the
sentence. Interruptions go back in the line instead, bounded at three attempts.

## Consequences

**A second unit to install and keep running.** Deploying is now two restarts,
and if somebody forgets the worker, submissions pile up in a queue nobody
empties. The queue tells the truth about that — waiting rows sit there with a
place in line and nothing rendering — but nothing shouts.

**Cancel takes up to about twenty seconds:** one heartbeat interval plus the
sentence in flight. It could be instant with a signal, at the price of a kill
that lands between the chunk insert and the chapters row. Twenty seconds is
what that costs.

**A restart of the worker throws away the chapter in flight.** The signal
handler finishes the sentence and puts the book back in the line rather than
trying to finish the chapter, because a chapter can outlast systemd's stop
timeout and be SIGKILLed, which is the death that opens the orphan window.
Minutes of Kokoro per worker restart, and a render resumes at the chapter
boundary it reached.

**The old guard that `add_book` refuses a book somnia already has in any state
is gone.** It was the only thing standing between an agent and #11, and it is
replaced by the fix rather than reinstated — a `done` book is still refused, a
live queue row is still refused, and a dead render is now retryable, which it
never was.

**`somnia add` is no longer the renderer, and no longer starts at chapter
one.** It submits and then takes the same claim as everything else, so it
refuses while the worker is busy instead of becoming a second renderer, and
what it renders is the head of the line — which is the book you named unless
you had already asked for others. The template unit
`somnia-render@.service` is retired with it.

**A second overlay on a one-screen page.** ADR 4 argued the first one into
existence and this reuses its shape exactly, but two is the point at which
somebody will propose a third, and the argument for this one is weaker than for
the first: a list of places answers a question the listener just asked, whereas
this is a thing somebody goes looking for. Its defences are that it is opened
only on purpose from the far corner, that it holds no payload so nothing has to
close it, and that it never switches what is playing. (**Amended 2026-08-07**:
the third of those is gone — it switches what is playing when a book on its
shelf is pressed. The first two still hold, and the press replaced by it was a
sentence typed to an agent at 2am.)

**No percentage, no time remaining, no notification.** People will want all
three. Chapters differ in length by an order of magnitude, so a bar drawn from
4/39 moves in lurches that read as a stall; the only honest time denominator
does not exist until the last chapter is encoded; and a lit screen at 3am costs
more than the news is worth. There is one honest fraction available —
characters rendered over characters parsed, since Kokoro's cost is close to
linear in characters — and it is written down here as the thing to add when
somebody wants a bar that means something.

**The no-auth model now buys more.** There is still no login: reachability is
the authentication, and `reference/http.md`'s "anything that can reach the port
can list your books, read the agent, spend your API credit and move your
position" gains "and start or stop hours of rendering". A password is not the
honest response, because design.md already ruled it out — "adding a password
would mean typing one at 2am, in the dark, to ask where the horse dies". The
damage stays bounded by shape rather than by a token: the only submittable
thing is a Gutenberg id, into a serialised queue, on a box that is one tailnet
device.

Two claims here are properties of a machine and not of a test, so, in the form
[ADR 3](0003-play-the-book-in-the-page.md) set for its locked-screen check,
they are to be checked on the VPS and written into this file with the date:
that one render at a time really does outrun 1× listening at the measured rate,
and that `systemctl --user restart somnia-serve` really does now leave a render
running.
