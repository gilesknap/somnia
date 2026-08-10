# 4. Choose a place from a list, rather than talk about it

## Status

Accepted. Amended by the redesign pass, which changed how the list is drawn and
nothing about what it decides. The overlay is titled **Places you might be** and
carries a line saying how many places there are and what they span; the reveal
is the whole row and `goto` is a pill on its last line, ranged right, which
inverts the emphasis described below — the press that can be taken back is now
the big one; the "you are here" marker is a rule across the list rather than a
row in it; and the inert cancel is a `‹ controls` pill in the top left — the
same corner, the same word and the same gesture as the way out of the books
panel and as the player's own navigation pill, replacing a slab across the
bottom that said `close`. The list still replaces the
conversation rather than the seek, the guard is still decided once on the
server, and the way out still touches nothing.

**Amended 2026-08-08**: the smoke test owed below is owed on nuc2, not the VPS.
An 85-turn real-model run on nuc2 (design.md, *Agent surface*) covered routing
and the spoiler guard but not the narration-over-a-list case this record asks
about, which remains open.

Amended again by the handoff's second revision. Nothing on a row sits beside
anything else: the time, the chapter and the words are each a full-width line,
and `goto` is under them rather than next to them. At 360dp the old row could
not hold three things across — the chapter's name was truncated on the row it
names, and the passage was clipped mid-sentence in the narrow column beside the
pill. A half-shown passage is worse than none on a screen whose promise is that
the words are the book's own, because it can be recognised wrongly. Two things
were spent for it and are recorded here rather than discovered later: four rows
and the mark no longer fit 360x780, so the list scrolls from the moment it
opens; and a low reach for the words now lands on that row's own `goto`, where
before the reading was beside the pill and nothing was under it. The miss that
matters — onto the *next* row's `goto`, which moves the book somewhere nobody
asked for — is still held off by the row's padding.

Amended again, in two particulars, and both of them are about the reveal.

**The reveal toggles.** A second press on a row that has been opened puts its
words away again, and its chapter title with them, and the line under the words
says so — *tap to hide*. It was deliberately one-way before, on the grounds that
a control whose meaning depends on how many times it has been pressed is the
wrong thing to hand somebody who is not counting. What that missed is that the
row states which press it is about to be, so nobody has to count; and that a
screen which can only ever grow is the wrong shape for this one, because four
places with their passages open is the column of book at 2am that the list
exists to spare somebody. Until now the only way to fold one back was to close
the screen and open it again.

**The "you are here" marker is a place, not just a rule.** It keeps its own
line across the list — the listener's position falls between two search hits and
inside none, so it is not a row of the result set — but under that line it now
holds what every other row holds: its time, stated at the size the list states
times, and the words being spoken there, one press away. Amber marks it out, and
the pill under it still says `here` rather than `goto`. Its words are the one
thing on that screen no answer carries down, so the page fetches them, once, when
the list is drawn: `/api/passage/{gid}/{ms}`, which is bounded by `heard_to_ms`
in the same statement that finds the row and is addressed by a point on the clock
rather than by an id. That is not the oracle the rejected alternative below
argues against — there is no identifier to guess and no way of asking that
returns anything the sound has not already said out loud. If the request fails or
the book has nothing indexed, the row offers no press at all, which is what it
was before.

Amended once more by
[ADR 6](0006-answer-a-question-about-the-book.md), in one particular. The
rejected alternative below rests part of its case on `find_passage` being both
how the model seeks and how it answers — its docstring named "who Ginger is" as
a use — and that is no longer so: a question about the book is `recall`'s, and
`find_passage` finds places to be taken to. The conclusion is unchanged and
rather stronger for it. The *server* still cannot tell a question from a request
to be moved, so there is still no rule watching search results and raising a
list; what is new is that the model says which kind of turn it is by which tool
it calls, and the tools refuse a move or a list in a turn that answered.

**Amended 2026-08-10 (#66): the rule's time is frozen and its word is not.** The
marker read *you are here* on every showing of a list, including the showing
after a `goto`, where the book is somewhere else and the frozen time is what the
way back is for. The time stays exactly as it was — it is what `here` seeks to,
what the passage is fetched at and what the rows are sorted around, and
unfreezing it turns the one press that had to remember into an undo that undoes
nothing. What changed is one string: the page compares the stamp against the
live playhead on every showing and writes *you are here* only while they are
equal, *you were here* otherwise. On a list about another book the present tense
stays, because there the stamp is that book's stored position and nothing on
this page can move it.

Three alternatives were considered and are recorded so they are not re-argued.
*Two rows*, a live rule plus a frozen way back, gives one screen two clocks
among rows that are all a photograph of one moment, cannot be drawn for another
book at all, and adds a sixth row to a list that already scrolls from the moment
it opens. *A staleness threshold* — past tense only after N seconds — needs an N
nobody can justify from a desk, and this page has no thresholds. *A crossing
test* — past tense only once the playhead has passed one of the places — is the
tempting clever version and it misses the reported bug: a `goto` backwards that
lands between the same two rows leaves the mark's index unmoved, so the screen
would go on claiming they are somewhere they have just left. Exact equality has
no such hole, and pressing `here` lands the playhead on the stamp, so the way
back, taken, makes the sentence true again. The cost accepted is that a second
or two of sound under a cancelled list flips the word; that is under-claiming,
which is the direction this screen is allowed to be wrong in.

The caveat under the rule is deliberately unchanged. *Anything below this line
you may not have heard* can only ever over-warn — `heard_to_ms` never falls —
and that is the same trade already accepted for the never-refreshed `ahead`
flags. Loading a second clause onto the one sentence the screen is arranged
around buys nothing the tense above it has not already said.

What was **not** taken from that revision is the per-row `strong match` /
`possible match` / `faint match` line. It needs a distance threshold, which
"A confidence threshold to decide when to offer" below rejects for reasons that
have not changed, and `Candidate` carries no score. It is on issue #20.

## Context

"Take me to where the horse dies" has two endings that are not the good one,
and both of them were conversations.

The first is ambiguity. A search returns its five closest matches whether or
not any of them is right, and in a book with three dying horses several of them
genuinely are the moment, for different values of the moment. The prompt told
the model to ask one short question when it could not tell which passage was
meant, so the night went: "did you mean the one about an hour in, or the one at
four hours?" — read on a phone held above a face, by someone who is asleep
enough to have lost their place and awake enough to mind. Answering it means
composing a sentence. Composing a sentence means picking the microphone up
again, or finding the keyboard, and then hoping the answer parses. It is two
more turns of a conversation to express something a thumb could have expressed
in one press, and each of those turns is twenty seconds of a lit screen.

The second is the spoiler guard. Searches are bounded by `heard_to_ms`, and
when the closest match lies past that bound the search says so without saying
what it is — `Search.better_ahead`, which is the crux of the guard —
[design.md](../design.md) makes the same point — because without it a bounded
search that excludes the answer is indistinguishable from a book that never
contained it. The agent then had to turn that into speech: *that is
further on than you have got — shall I take you there anyway?* Which is a
reasonable sentence and a bad question at 2am. It arrives as prose, so it has
to be read; it needs a yes, so it needs another turn; and the yes it is asking
for is `allow_spoilers`, which is the single most consequential word in the
whole system, being solicited from somebody half asleep in the least
deliberate way available. Worse, `better_ahead` is set on very nearly every
search on a book somnia has not played much of, so on night one this was not an
edge case, it was the normal reply.

Both endings share a shape. The information that would settle it — a time, a
chapter, and the book's own words — is structured, and it was being flattened
into a sentence so that a second sentence could be composed to answer it. The
page is right there, it is already the player, and it can draw a list.

## The alternatives we rejected

**A server-side rule: when a search comes back ambiguous, show the list.** The
obvious version, and it cannot be built, because `find_passage` was not only how
the model seeks — its own docstring named "who Ginger is" as a use, and
questions about the book went through exactly the same call (which is what ADR 6
came back and undid). A rule that
intercepted close-together hits would put a list of places to jump to in front
of somebody who asked a question, and would blind the model on that turn so it
could neither answer nor say it could not find it, which the prompt explicitly
requires it to be able to say. Keying it on `better_ahead` is worse still: that
fires on almost every search on a barely-played book. The server cannot tell a
question from a request to be moved. Only the model can, and judging that is
the one thing it is here for. So the list is an explicit tool —
`offer_positions(gid, chunk_ids)` — and the model names which passages go on
it.

**Naming the places by `position_ms`.** The model is never told the ahead
passage's position; it gets a formatted `h:mm:ss` and nothing else, and
widening that to make a tool call easier would hand it the number the guard
exists to withhold — so a position argument could not name the one candidate
the spoiler case exists for. And a position is a point where a row is a
passage: the server would have to resolve "the chunk containing that
millisecond", so a rounded or invented number yields words that are not the
passage that matched, on a screen whose entire promise is that the words are
the book's own. A chunk id is exact, already unique, already on the search
result, and lets the tool *prove* that every offered passage came from a search
in this conversation. An id that did not is refused outright and never resolved
to the nearest chunk.

**Fetching an unheard candidate's words when the reveal is pressed.** This was
close, and it lost on three counts. A reveal endpoint is a permanent,
general-purpose `/api` route that returns unheard book text for any chunk id,
sitting there for the life of the deployment — a spoiler oracle one guessed
integer wide, which is strictly a larger thing to have built than shipping the
words inside the answer to a question that already searched for them. It is
also a round trip over the tailnet at 2am from a phone that has been face down
for an hour, on the one press where a spinner does the most damage: they
pressed reveal *because* they are unsure, a control that does nothing for three
seconds reads as broken, and the reflex is to press it again — which, with a
list on screen, is a press landing somewhere. This codebase has already made
that call once, in the owner's own comment about not putting the network in
front of a transport press, and the whole retry ladder exists because the link
genuinely goes away for seconds at a time. And the threat model is accident,
not adversary: the person holding the phone is the person the guard protects,
and opening devtools on your own handset is not an accident, it is the same
deliberate act as pressing reveal.

**Routing a chosen row through a server move.** Tempting, because that is what
the agent does, and wrong, because `position_seq` counts agent moves and
nothing else. A choice made on the page bumps nothing server-side, so calling
`follow()` with a fabricated count is either a silent no-op or leaves the page
holding a number the database does not have — after which every report for the
rest of the night is refused and the refusal drags them back. Waiting for a
real count instead puts a tailnet round trip in front of a transport press,
which is the one thing this page never does. The page is the player and owns
its position; a chosen row is a seek by a thumb, which is what the local path
already models, and it works with the link down. The server finds out at once
anyway, by the route every other seek already takes.

**A second screen.** Rejected on the strength of the comment at the top of
`index.html`, which says there is nowhere else to go and no state a wrong press
could leave them stranded in. A route or a second document would need a way
back, and a way back is a thing to get lost in.

**A confidence threshold to decide when to offer.** There is no distance
threshold anywhere in somnia and this is not the place to introduce the first
one. `Passage.distance`'s scale depends on the real e5 embedder, which no test
can exercise, and the fake embedder yields exactly two values — so a number
here could not be validated from a desk and would silently end up either
invisible or a nuisance. Plausibility stays a model judgement, which is what
the prompt has always called it, and the tool bounds the damage instead.

## Decision

**When more than one place could be the moment, the page draws them and a thumb
picks one.** The model calls `offer_positions` with the ids of the passages it
judges plausible; the server writes what each row says; `/api/ask` returns a
`candidates` object instead of a `move`; the page raises an overlay titled
**"Where do you mean?"** — which echoes the page's own opening line, *Where do
you want to be?*, because it is the same question asked from the other end.

A confident single hit is untouched. It still moves the book and plays, with no
list and no press. The list replaces the *conversation* about ambiguity, not
the seek.

Each row is a time, a chapter and the book's own words — never a description of
them, because a sentence the model wrote about a passage is a sentence about a
passage it may be wrong about, and the whole point of showing the list is that
they recognise the moment themselves. Between the rows, in book order, sits a
"you are here" marker, so which places are behind them and which are ahead is
something they see rather than something they are told. For the open book that
marker is the page's own position and not the server's, because the page is the
player and the server's copy is up to fifteen seconds stale.

**A place further on than they have listened shows its time and its chapter
number, and hides its words behind a second, separate press** labelled *show me
what's there*. Its chapter title is hidden with them: "How Ginger Died" is as
much of a spoiler as the sentence underneath it. Revealing is one deliberate
act and going there is a different one, and they are shaped differently — the
row is a raised, thumb-sized target, the reveal is a quiet dashed outline —
because they are different decisions and must not look like the same button.
That is what replaced "shall I take you there anyway?": the same question, but
asked by the screen, answerable by a thumb, and answerable in a third way the
sentence never offered, which is to look first.

**The list is an overlay, not a screen.** The book keeps playing underneath it,
the sleep timer keeps counting, the lock screen still works, and nothing has
moved. **Cancel is inert**: it hides the overlay, empties the list and drops
the payload, and touches nothing else at all — no move, no report, no count, no
position, no volume, no fade, no timer, no media session, no request of any
kind. It leaves the night exactly as it found it.

The words for a place they have not heard travel with the reply and are held in
one module-scope variable. They are never written into the DOM until the reveal
press, never put in storage, never logged, never passed to the transcript, and
dropped on any close.

**`goto` is the one press here that is not inert, so it carries a way back.**
Cancel changes nothing and reveal changes nothing; `goto` discards a position
nobody wrote down, and before this the only route back was another semantic
search — a model call and a question composed by somebody half asleep, which is
the expensive thing this whole feature exists to avoid. The toast that confirms
it names where it landed, *moved to 1:20:20*, and stands for six seconds rather
than the usual 2.8 with *undo* beside it.

The offer holds a position, not an intention, so it is withdrawn the moment
anything else moves the book — a thumb on *+30*, a chapter, the agent answering
the next question — and the sentence is left standing, because a receipt for
something that really happened reads no worse for the offer beside it having
gone. Pressed after that it would be a fourth move wearing the word *undo*.

It is a second way back and not the only one. The *you are here* row is the
first: it is frozen at the moment the question was asked, and says so — opening
the list again an hour later still offers the place the `goto` left, under a
rule that now reads *you were here*. The toast is for the
press that has just happened and the row is for the one somebody has had time to
regret, which is why both exist and why they say the same sentence.

Only for a `goto` inside the book that is playing. A row in another book
overwrites *that* book's stored position, which `openBook` reads and does not
keep, so undoing it would mean restoring a number the chooser was never handed.
Not built; the receipt is drawn without the offer.

## Consequences

**The spoiler guard is not weakened, and one hole in it is closed.** Whether a
row starts covered is decided on the server, in `Library.offer_positions`, as
`start_ms >= heard_to_ms`, read once for the whole offer. It is `>=` and not
`>`, which matters more than it looks: with `>`, a passage starting at
millisecond zero in a book nobody has played a second of would have printed its
opening words in the clear. There is no slack — the search bound is the mark
plus a minute, so the reveal guard is strictly tighter than the search guard,
and a passage inside that minute is findable and still covered up. There is no
exemption for a finished book. The page obeys the flag and computes nothing,
and `heard_to_ms` is deliberately not on the wire, so there is one number
decided in one place rather than two that can disagree about exactly the rows a
mistake matters most on.

Nothing about making, showing, revealing or cancelling an offer can raise the
mark. `offer_positions` issues SELECTs only, so an offering turn writes nothing
whatsoever; the reveal press sends no request and touches none of the counters
a report is built from; and the overlay never calls `seekGlobal`, so a page
that was only ever asked a question keeps its "never started" position rather
than turning it into 0:00:00. The mark still rises normally the moment the book
plays, which is asserted in both directions, because a guard that never rises
is not a fix.

**A list and a move can never arrive together**, and that is enforced twice
over. The `move_to` tool refuses to run at all once an offer exists in the
turn — refused *there*, before anything is written, because the row is written
before the call returns and suppressing it any later would leave the position
and its count in the database, to be met fifteen seconds afterwards as the
refusal of the page's next report, dragging somebody who was still reading the
list. And the server serialises `move` only in the `elif` branch of
`candidates`. Two independent things would both have to fail.

**The withheld words sit in the page's heap and in the network tab, and that is
a real widening.** It is bounded by discipline — truncated on the server, out
of the DOM until revealed, out of storage, out of the log, dropped on close —
and what that discipline buys back is the accident cases that actually happen:
a screen reader cannot read them out, a selection cannot catch them, a
screenshot cannot contain them, and a scroll cannot bring them into view. It is
written down here rather than left implicit because it is the one place this
feature made the guard's surface larger instead of smaller.

**The model can still not play along, and nothing here can make it.** It may
decline to call `offer_positions`, or call it and then narrate the places
anyway, and neither is testable against the real model from a desk. The damage
is bounded structurally rather than by the prompt: the only passages whose
words have ever been in its context are ones inside the spoiler bound, which
they have already heard, so the worst it can narrate is a cosmetic annoyance
and not a guard failure. The ahead passage's text has never been in the
process. The degraded behaviour is the old conversation, which still works.
This wants a real-model smoke test on the VPS before it is trusted, and if a
night proves the narration a nuisance the hardening is one line — overwrite the
reply with the neutral sentence whenever a list is going out — which is noted
in `server.py` next to the code so nobody has to rediscover it. It is not done
today because the model sometimes has something true and useful to add ("that
one's in the other book").

**Chunk ids are a new opaque handle for a small model**, printed on the same
tool-result line as a position, so it may well pass the wrong number. The tool
refuses an unknown id outright and the refusal says what a passage id looks
like, which is the best a desk can do about it.

**Some things the overlay deliberately does not undo.** A sleep fade running
underneath keeps running, and if it completes the book pauses and the page
writes "goodnight" onto a status line the overlay is covering. The countdown
has been spending itself the whole time the list was up, because the book was
playing and they were listening. A list left up long enough therefore ends the
night by itself. That is correct — a list is not a reason to keep the book
going — but it will read as a bug to whoever meets it first, so it is
commented where it happens. Cancel leaves the question and the neutral reply in
the transcript, which reads as an answer that never finished; acceptable at one
screen, and worth watching.

**A cross-book choice can be dropped.** Rows carry a book id and a place in
another book works — the page opens it and starts at the chosen place rather
than wherever that book was last left. But if that book has no rendered
chapters yet, opening it goes down the "the first chapter is still being read"
path and the chosen place is lost. Stated rather than engineered around:
threading a position through a wait that can be a quarter of an hour is a
promise the page cannot keep, and it would be a second place a position is
remembered.

**The page test harness had to grow up.** It could not express any of this: it
had no `createElement`, its `append` and `replaceChildren` were no-ops, and
`getElementById` could not find an element the page had built. That last one is
the subtle half — an element's id has to register it with the harness as it is
assigned, or a test asking for a row gets a different object than the one on
screen. The overlay's inertness is proved rather than asserted, by snapshotting
everything the page calls "the night" plus every request, beacon and source
write it has made, pressing cancel, and requiring all of it to be identical
afterwards and still identical a tick later.
