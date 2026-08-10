# 10. Draw the spoiler line where they are

Date: 2026-08-10

## Status

Accepted. Takes away the high-water mark that
[ADR 4](0004-choose-a-place-from-a-list.md) and
[ADR 6](0006-answer-a-question-about-the-book.md) both rest part of their
argument on. Neither conclusion changes: a list is still how ambiguity is
answered, a question is still answered where they are and moves nothing. What
changes is the number both of them are measured against, and the amount of
machinery it took to keep that number honest.

## Context

The guard was drawn at `books.heard_to_ms`: the furthest point the sound had
really reached, as against `position_ms`, where the book is now. The reasoning
was symmetrical and, on paper, right. The agent can move the position anywhere.
Backwards, where being taken to chapter two must not un-hear chapters three to
twenty. Forwards, where treating where they were put as what they have heard
would unlock a whole book for one move.

Keeping a number that means *heard* rather than *reached* is expensive, because
only the page can tell the two apart — a skip and a stretch of listening both
arrive at the server as a position further on than the last one. So every
report carried a count of playback taken off the media clock, the mark rose to
the reported position only when the report stood no further past the mark than
that playback accounted for, the wall clock capped the claim, and five seconds
of slack covered the rounding. On the page that meant three module-scope
variables and a rule at every seek, every source load, every accepted reply and
every book switch about which of them to give up and when.

**It did not work, and the way it failed was silent.** A report standing further
past the mark than it had playback behind it cannot be credited — and after a
forward skip, *every* report is such a report. The gap the skip opened sits in
front of the mark permanently, and each honest heartbeat afterwards stands past
it by more, not less. So one press of `+30` stopped the mark for the rest of the
book. So did a chapter skip, a scrub, and an agent move the listener had asked
for.

Nothing announced this. The book played on, the position advanced, and the guard
went on answering questions against a place they had listened straight through
an hour ago. The visible symptom was the agent: asked about something a few
minutes behind them, it would say the passage lay further on than they had got
and offer to take them there — over and over, correctly, from its point of view.
It reads as a model being precious. It was a stuck column.

The cost was written down in `Player.report` at the time — *"after a forward
skip the mark stops … failing this way costs them a question at 2am"* — and the
estimate was wrong by the shape of a night. It is not one question. It is every
question after the first skip.

## The alternatives we rejected

**Fix the crediting rule so a skip does not stop the mark.** This is where the
first attempt went, and it cannot be reached from here. One number cannot say "I
heard this stretch but not that one" — that is a set of intervals, a second
table, and a merge on every report, all so that a search can be bounded a little
more tightly than the play head. Nothing on the phone gets better for it.

**Raise the mark to `max(heard_to_ms, position_ms)` on every write.** Strictly
more permissive than what shipped, and it does fix the skip. It was rejected
because it keeps two numbers in the schema to express what one of them now
decides, and because the number it keeps is invisible: a listener cannot see a
high-water mark, and cannot predict what the agent will and will not talk about.
The position is on the scrubber. Being able to look at the line is worth more at
2am than being able to argue it is optimal.

**Keeping the mark and accepting the skip bug as rare.** It is not rare. `+30`
is a button on the player, and the whole point of the agent is moving the book
around.

## Decision

**`books.position_ms` is the spoiler line, and there is no second number.** A
search is bounded at it, `Candidate.ahead` is `start_ms >= position_ms`, and
`/api/passage/{gid}/{ms}` answers out of a statement whose own `WHERE` carries
`start_ms < position_ms`. A book with no position at all is bounded at its
start, which is the state every book is in until it is played.

`heard_to_ms` is no longer read or written. The column is left on existing
databases rather than dropped — a column nobody selects costs a few bytes a row,
where `DROP COLUMN` costs a rewrite of the one table somnia cannot lose.

`played_ms` leaves the report body. A page still sending one is taken at its
word about the position anyway: a phone holds the app it last loaded for as long
as it likes, and a version-skewed page that silently stopped recording where it
got to is a worse failure than the field being ignored.

## Consequences

**A rewind narrows what may be said, and playing on widens it again.** Taken
back to chapter two, the stretch above goes quiet until it is played over. This
is the half of the old argument that was real, and it is now paid rather than
avoided. What makes it payable is that it heals at the speed the book plays,
one report at a time — where the mark, once a skip had stopped it, never healed
at all.

**A skip forward unlocks what it stepped over.** Somebody who skips is somebody
who decided to, and a listener who has read the book elsewhere is the ordinary
case rather than the strange one. The accidental version — a sleeping thumb
landing on the scrubber — really does open the book behind where it lands, with
no way back short of a rewind. That is the one place this is weaker than what it
replaced, and it is written down here rather than discovered later.

**Reaching the end of a book stops holding anything back.** There is no
"finished but skipped" state any more, because there is no record of what was
skipped.

**The page loses its playback clock.** `playedMs`, `playedFrom` and
`playedTaken` are gone, with the rules at every seek and source load about which
of them to give up. A report is a position, a sequence number and a reason.

**The server loses the hardest statement in the codebase.** `Player.report` is
now one `UPDATE` guarded on `position_seq`. `HEARD_SLACK_MS` and the wall-clock
ceiling go with it, and `OPENED_AHEAD_S` stops having a second job.

**The guard is now a number somebody can point at.** Everything that draws or
withholds is measured against the same figure the scrubber shows, so "why did it
say that?" has an answer that can be checked without opening the database.
