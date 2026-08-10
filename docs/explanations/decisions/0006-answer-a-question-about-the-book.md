# 6. Answer a question about the book, out of what you know, as far as they have listened

## Status

Amended by [ADR 11](0011-the-guard-belongs-on-the-row.md), which widens the gap
this record opened between the two tools rather than narrowing it: `find_passage`
now reads the whole book and holds back the *words* of anywhere they have not
reached, while `recall` still stops at the line when it reads. The argument
below against `recall` taking `allow_spoilers` is unchanged and is now the only
place that word appears in the reasoning — `find_passage` has no such argument
any more.

Amended by [ADR 10](0010-draw-the-line-where-they-are.md): the line a recall may
not cross is the position rather than a high-water mark. What this record says
about there being such a line, and about the answer being bounded by it rather
than by what a tool handed back, is unchanged.

Accepted. It reverses the strongest sentence in the system prompt — *Everything
you say about a book must come from a tool result in this conversation* — which
had been there since the agent was written, and replaces the bound it drew with
a different one that is drawn in the same place the spoiler guard is.

It amends [ADR 4](0004-choose-a-place-from-a-list.md) in one particular. That
record rests part of its argument on `find_passage` being both how the model
seeks and how it answers — "its own docstring names 'who Ginger is' as a use,
and questions about the book go through exactly the same call". They no longer
do. The conclusion ADR 4 drew from it stands and is if anything stronger: the
*server* still cannot tell a question from a request to be moved, so there is
still no rule that watches search results and raises a list. What has changed
is that the model now says which kind of turn it is by which tool it picks, and
the tools hold it to that.

## Context

Ask somnia "remind me who Rob Roy is" and it does not answer. It searches,
decides the passages that came back are places you might want to be, and either
puts them on the screen as a list — replying with the one sentence it is allowed
to say beside a list, "There are a few places that could be it." — or picks the
best one and moves the book there. Either way the question is never answered,
and in the second case asking it costs the listener their place in the night.

Every question was read as *take me somewhere*, because there was no *tell me
something*. The pressure ran one way and a question about a character rode it
the whole distance:

- **Nothing decided what kind of question had been asked**, because the prompt
  only ever described one kind. It said when to move, when to offer instead,
  what to do when the closest match lies past the mark, and what sentence to say
  beside a list. It never once said what to do with a question whose answer is a
  sentence, and it closed with "Otherwise just act" over a toolbox whose only
  acts were `move_to` and `offer_positions`.
- **The search was the same search.** `find_passage` was the only way into the
  book, and its own docstring offered "who Ginger is" as an example of what it
  was for. A character question and a place request produced the same call and
  the same result lines — passages carrying `id=` and `position_ms=`, which are
  precisely the two things the two locative tools consume.
- **A character name matches everywhere.** "Where the horse dies" has one true
  answer; "who is Rob Roy" matches every passage he appears in, which is exactly
  the condition the prompt names as the moment to offer a list. The more central
  the character, the more certainly the question became a list — and once it
  offers, it is gagged: the reply to a question about a character is a sentence
  that is not about the character.
- **If it did not offer, it moved.** One plausible passage and the prompt said
  find it and move the book there. That is the worst outcome available here, and
  it is the one a confident search produces.
- **`better_ahead` added a third push.** When the best match lies further on the
  tool result says "Offer it with `offer_positions`" — sound advice for "take me
  there", wrong for "who is he", where the answer should be that he has not come
  up yet in what they have heard.

The tool layer could not save it. It enforced exactly one exclusivity —
move-or-offer, never both — and both sides of that are locative. Nothing in the
code could tell that a turn should have produced neither.

Underneath all of it sat the grounding rule, and the rule was doing two jobs at
once. It was the spoiler guard's last line of defence, and it was also a
hallucination guard, and it enforced both by saying that only a passage returned
tonight may be spoken about. That is a tighter fence than the guard needs — a
book's first hour does not stop being safe to discuss because nothing searched
for it this turn — and it is the fence that made answering impossible.

## The alternatives we rejected

**Prompt wording alone: a paragraph saying "some questions want a sentence".**
The cheap version, and it will drift, because the pull described above is
structural and not tonal. Every tool the model can reach on a question turn
hands back positions, and a position is a thing to move to. This codebase has
made this call before: `acted` exists because "never offer and move in the same
turn" was a prompt rule that the tools now refuse rather than one the model has
to remember. A paragraph is also the version no test can hold, which is most of
the argument by itself.

**A required intent argument on `find_passage`** — `find_passage(gid, what,
intent="answer")`. Rejected because the result would then have to change shape
with the flag: a locative result must carry `id=` and `position_ms=` on every
line, and an answering result must carry neither, or the thing that turns a
question into a jump is still sitting in the model's context. A tool whose
result is two different shapes is two tools sharing a name, and the tool list is
the part of the prompt a small model reads hardest. Two names with two
docstrings say it where a boolean has to be remembered.

**Keeping the grounding rule and answering only out of returned passages.** This
was the open question in [#24](https://github.com/gilesknap/somnia/issues/24)
and it was decided the other way, deliberately. The passages come back as
three-sentence windows picked by nearest neighbour: good evidence for *where*
something is, thin evidence for *who* somebody is. "Rob Roy is the horse Beauty
knew, shot at the hunt" is not a sentence in any one window, so a strictly
grounded answer would very often have to be "I can't tell you from what I can
see" — which is the same non-answer this record exists to remove, wearing a
politer coat. The model has read these books. The thing that must never leak is
what happens *past where they have got to*, and that has never been the same
thing as what a tool happened to return.

**Letting `recall` take `allow_spoilers`, the way `find_passage` does.** A move
past the mark cannot be done spoiler-free — going there is hearing it — so
consent is the only way to serve "take me to the end", and `find_passage` takes
it. An answer has no equivalent necessity: whatever they are asking about,
listening on tells them. And a yes given at 2am by somebody half asleep is the
least deliberate consent in the system, which ADR 4 already says about this
exact word. So this tool has no way through, and a question about what has not
happened yet is answered with the truth that it has not happened yet.

**Reporting `better_ahead` on an answering search and letting the model ignore
it.** Rejected twice over. It is a nudge to put a list of places in front of
somebody whose whole reason for asking was that they wanted to keep listening;
and it is a spoiler in its own right, because "he hasn't come up yet in what
you've heard" and "he comes up an hour and a half from here" are different
sentences, and the second one gives away that he arrives at all.

## Decision

**A turn is either locative or a question, and the tools decide what may follow
each.**

`recall(gid, question)` is the tool for a question whose answer is a sentence.
It runs the same bounded search — there is one index, and a question and a
request to be moved genuinely do look for the same passages — and then takes two
things away on the way out. It carries no `better_ahead` at all, and its result
lines carry the chapter and the book's words but no `id=` and no `position_ms`:
a chapter is something an answer can say out loud ("that was back in the hunt"),
where an id and a position are handles for moving.

Calling it sets `acted["recalled"]`, which is `acted` doing the job it was built
for. `move_to` and `offer_positions` both refuse afterwards, in the same voice
as the refusals already there — *"They asked a question, not to be moved; the
book stays where it is."* Refused in the tool, before `library.move_to` writes
anything, because a written move reaches the page fifteen seconds later as the
refusal of its next report whatever the reply said, and there is nowhere further
down to stop it. The flag is set even when the recall found nothing and even on
a book that is not there, because calling it is the model saying what kind of
turn this is — and a question that found nothing is the case the refusal matters
most in.

**What may be said is bounded by how far they have listened, not by what a tool
returned tonight.** The prompt's grounding paragraph is replaced by one that
draws the line in the same place the guard draws it: everything behind it may be
talked about freely, whether it came back from a tool or the model simply knows
it; nothing in front of it may be said at all — not a name, not a death, not
that somebody turns up later, not that a question they are asking is one the
book answers. Someone who has not appeared yet gets "he hasn't come up yet in
what you've heard" and nothing after it.

**What may be read and what may be said are now two different distances**, and
saying so out loud is part of the decision rather than a side effect. It was
always true — `find_passage(allow_spoilers=True)` exists so the model can read
past the mark to pick the right place, and the prompt has always said that
reading a passage does not oblige it to describe one — but under the old rule it
was true by accident, since the fence was drawn around the tool result. It is
now the sentence the whole paragraph turns on.

**The tool layer carries what it can of that, so the prompt is not alone.** The
search is bounded exactly as before; `better_ahead` is gone rather than ignored;
and every recall result opens by naming the line in words the model can act on —
*"Answer from the first 0:06:00 of the book, which is as far as they have
listened, and say nothing that happens after it"* — and closes with the sentence
to say when nothing it found was about the question, which stops at "not yet"
and explicitly not at "it comes up later". That is the same pattern as the one
sentence handed back after a list goes up: where a sentence is the answer, the
tool gives it rather than leaving the model to compose one.

The page needs nothing. `/api/ask` already returns a bare `reply` when a turn
carries no move and no candidates, and the page draws it as a sentence.

## Consequences

**The model can now be wrong about the part of the book they have already
heard**, which is a failure the old rule made impossible, and it is accepted
with its eyes open. The worst case is a confidently wrong sentence about
something they listened to an hour ago — annoying, visible to them immediately,
because they heard it, and gone by morning. The old rule's failure was not
answering the question at all, or answering it by moving the book. The guard's
own failure mode is untouched: everything past the mark is still unsayable, and
that is the failure that cannot be undone.

**The guard is now only reached if the model looks first.** This is the sharper
edge of the same trade and it is worth stating on its own. The old rule enforced
itself: with nothing sayable that a tool had not returned, an answer nobody had
searched for was structurally impossible, so a spoiler needed a tool call to
carry it. The new bound is a number — the mark — and the model does not know
that number until a tool tells it, which means an answer given straight out of
the model's own knowledge, with no `recall` in the turn at all, is bounded by
nothing whatever. "How does it end" is the shape of question most likely to
arrive that way, and it is the worst one to get wrong. Nothing in the tool layer
can stop it, because the failure is a turn in which no tool was called, so the
prompt carries it: it says that the line is somewhere different every night,
that only `recall` or `find_passage` can say where it is, and that nothing about
what happens in a book may be said until one of them has — least of all on the
question the model is certain it already knows the answer to. That is prompt
work holding a guard, which this record otherwise argues against, and it is
here because there is nowhere else to put it. It belongs on the list of things
to try on a real book: ask a question about a book with nothing open, and one
whose answer is the ending.

**The routing itself cannot be tested from a desk.** `FakeRunner` scripts the
model's turns, so the suite can prove that the tools refuse a move after a
recall, that a recall hands out no place to send anybody to, and that the flag
is cleared for the next question — but nothing here proves the model picks
`recall` when it is asked who somebody is. That is the same limit ADR 4 records
about `offer_positions` and it is answered the same way: a handful of real
questions against a real book, checked for three things — the reply answers,
`move` is absent, `candidates` is absent.

**A compound question is served in halves.** "Who is Rob Roy, and take me to
where he's shot" recalls, answers, and then finds the move refused; they have to
ask again. That is the deliberate side of the trade — the tie is broken towards
answering, because an answer costs them nothing and a wrong move costs them the
hour — and it is the case to watch on the live box, since somebody half asleep
does ask compound questions.

**Asking about somebody and then asking where they are costs two searches.** A
recall adds nothing to the record of passages an offer may name, so the model
has to go and look with `find_passage` before it can put places on the screen.
That is right — the ids it never received cannot be smuggled in from a
conversation turn where nothing was offerable — and a second search is
milliseconds.

**Nothing about answering touches the night.** `recall` issues SELECTs only, by
way of `find_passage`, so `position_ms` and `position_seq` are exactly as they
were. Reading the book back to answer a question is not listening to it — and
since ADR 10 the first of those is the guard itself, so a question that nudged
it would widen what the next question may be answered from.
