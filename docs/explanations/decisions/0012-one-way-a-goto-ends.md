# 12. One way a goto ends

Date: 2026-08-10

## Status

Accepted. Amends [ADR 4](0004-choose-a-place-from-a-list.md) in one particular —
the model no longer decides between moving and offering — and amends
[ADR 6](0006-answer-a-question-about-the-book.md) by collapsing the two refusals
it describes into one. Both conclusions stand.

## Context

ADR 4 gave the model a choice: one plausible passage, move the book; two or
more, call `offer_positions` and let a thumb answer. That is a judgement, made
at 2am, on a mumbled sentence, by whichever model is configured — in practice
Haiku, chosen for speed.

It goes wrong in a way that is invisible from a desk and obvious in a bed. The
model would decline the judgement and hand it back as prose: *that's further on
than you've got — do you want me to take you there anyway?* Which is the
question ADR 4 exists to have deleted, arriving through the model's mouth
instead of through the tool it removed. Or it would offer a list of one place
they had already heard, get the tool's refusal — *"That is one place they have
already heard. Move them there instead."* — and argue with it, or re-offer, or
stop.

Both are the same failure. The decision is arithmetic on two facts the server
has and the model does not reliably use: how many places are plausible, and
whether the single one is behind them. The model is being asked for a
calculation, and what it gives back is a conversation.

There is a second cost. `move_to` and `offer_positions` are two tools with a
mutual exclusion between them, so the exclusion has to be written twice — once
in each — and the copy in `move_to` has to fire *before* `library.move_to`
writes, because the row reaches the page fifteen seconds later as the refusal of
its next report. A rule stated in two places is a rule with a seam.

## The alternatives we rejected

**Prompt wording: tell it harder not to ask.** The prompt already said, in
several places, not to ask which place and not to ask about spoilers. This
codebase has made this call before — `acted` exists because "never offer and
move in the same turn" was a prompt rule the tools now enforce. The wording was
not the problem; being asked for the judgement at all was.

**Keep both tools and make `move_to` refuse a place they have not heard.** Fixes
the spoiler half and leaves the move-or-offer judgement, the two-place
exclusion, and the bounce on a single heard place all where they were.

**Have `find_passage` draw the list itself, with no second call.** The furthest
version of this idea, and it takes away the one judgement the model is good at
and should keep: reading the passages it was given and saying "none of these is
really it". A screen of four wrong places is worse than being told it could not
find the moment.

## Decision

**Every goto ends in `offer_positions`, whatever becomes of it.** The model
names the passages that could really be the moment, best first. The tool
decides:

- more than one place → the list goes on the screen;
- one place at or past the position → the list goes on the screen, one row,
  covered — the press *is* the consent, which is what ADR 4 built it for;
- one place behind the position → `Library.move_to`, there and then, returning a
  `Moved` — unless a list is already on the screen, and then it is the second
  case instead: one row, and a press.

`move_to` comes off the model's tool list. `Library.move_to` stays and is what
the third case calls.

The single-heard-place `Refused` becomes that move. It was always the same rule;
it was just expressed as a bounce that cost a round trip and could be argued
with.

**The exclusions collapse into one place.** A turn that called `recall` refuses
the whole tool, so a question can no longer end in either a list or a jump, and
that is now one branch rather than two in two files. A turn that has already
taken somebody somewhere refuses a second go.

A turn that has already drawn a list is the one exclusion that is not a refusal.
It may draw another — that is a change of mind, the last offer wins, and nothing
has left the process yet — but it may not move, and the move cannot be caught
after the fact, because `Library.offer_positions` makes it before it returns and
a `Turn` is assembled long after that. So the fact that a list is up travels
down with the call, as `may_move`, and the place behind them comes back as a row
to press. Only the caller knows the screen is busy and only the library knows
what the arithmetic came to; the argument is where those two meet. It is
deliberately not a count of ids at the caller: the ids are deduplicated and the
ones resolving to nothing are dropped before any of this is decided, so two ids
are routinely one place.

## Consequences

**The model stops deciding whether to move.** It judges plausibility — which
passages could really be the moment — and nothing else. That is the judgement it
is good at, and the one that has a cheap failure: name too many and the cost is
an extra press, where deciding to move wrongly costs the hour they were in.

**"Are you sure?" has nowhere left to come from on a goto.** There is no consent
argument to solicit and no move-or-offer fork to hesitate at. The only pushback
left in the system is `recall` saying something has not come up yet, which is an
answer rather than a question.

**An explicit "take me to the end" costs one press.** The place is ahead, so it
goes up as a covered row. Given the alternative was a sentence asking for
consent and a second turn to give it, a thumb on a row is both faster and more
deliberate.

**A turn can no longer move the book twice.** It used to be able to move, think
better of it, and move again, with the last winning. Now the second call is
refused. A page dragged twice inside one answer arrives somewhere the sentence
does not describe.

**The prompt loses about a third of itself**, including all of the spoiler
apparatus that ADR 11 made unnecessary and the paragraphs that explained when to
move and when to offer. What is left is routing, plausibility and how to speak.

**The model can still name four bad places.** The tool cannot tell a plausible
passage from an implausible one — that is the judgement it deliberately keeps —
so a poor search still produces a poor list. The listener cancels it, which is
inert, and asks again.
