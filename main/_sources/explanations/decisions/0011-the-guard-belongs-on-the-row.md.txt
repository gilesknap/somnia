# 11. Put the guard on the row, not on the search

Date: 2026-08-10

## Status

Accepted. Builds on [ADR 10](0010-draw-the-line-where-they-are.md), which made
the position the line, and amends [ADR 4](0004-choose-a-place-from-a-list.md) in
one particular: the `better_ahead` passage that record calls "the crux of the
guard" no longer exists, because a search no longer has anything to hold back.
What ADR 4 decided about the *list* is unchanged and is stronger for it.

## Context

The guard was enforced at search time. `find_passage(spoiler_free=True)` cut the
results at the line, `allow_spoilers` was the way through it, and because a
bounded search that excludes the answer is indistinguishable from a book that
never contained it, the search also had to run a second time over the whole book
and report `better_ahead` — one passage past the line, named by id and time and
nothing else.

That is a lot of apparatus, and it bought two problems.

The first is cost. `better_ahead` is a second embedding of the query and a
second scan of the vectors, on the one screen where seconds are felt, spent to
find out something the answer then mostly declines to say.

The second is what it did to the conversation. `allow_spoilers` made "may I read
this?" a decision the model takes in the middle of a turn, on a mumbled sentence,
and the prompt then had to spend a paragraph explaining that reading past the
line does not license speaking past it — a distinction a small model holds
badly. Meanwhile the listener could not reach a passage further on except
through `better_ahead`, which reported at most one, chosen by whether it beat
everything in range. Ask for something in a book you have barely started and the
honest answer was one place, or none.

Underneath all of it is a category error. **A place is not a spoiler.** A time on
the clock says nothing about what happens at it. What spoils is the words, and
the words have their own guard: ADR 4 already keeps them off the screen behind a
press.

## The alternatives we rejected

**Keep the bound and widen `better_ahead` to several passages.** The obvious
incremental fix. It keeps the second search, keeps `allow_spoilers`, and keeps
the model deciding when to read — all to avoid returning times that were never
dangerous.

**Unbind the search and return everything whole.** The simple version, and the
one that quietly gives the guard away. Today the words of an unheard passage have
never been in the model's context; ADR 4 rests part of its case on exactly that,
observing that the worst a misbehaving model can narrate is a passage they have
already heard. Hand the search results back whole and that becomes a prompt rule
instead of a fact — on Haiku, which is the model this is run on.

## Decision

**`Library.find_passage` searches the whole book, with no bound and no consent
argument.** `spoiler_free`, `allow_spoilers` and `better_ahead` are gone, and
with them the second search.

**The guard moves one step later, into the shape of a result line.** A hit at or
past `position_ms` reaches the model as a time and an id:

```
[4:12:30, id=9411] further on than they have got — you have not been told what is there.
```

and a hit behind it reaches the model as it always did, with its chapter and its
words. The chapter title travels with the words, not with the time: *How Ginger
Died* gives away as much as the sentence under it.

`position_ms` comes off every line. Offers are made by id, so the number the
guard most wants to withhold is not printed anywhere.

**One predicate, `tools.ahead_of(start_ms, here_ms)`, decides both ends.** The
search reads it to choose a line format; `Candidate` reads it to decide whether a
row keeps its chapter title. A boundary they disagreed about would be a hole.

**`recall` stays bounded and gains nothing.** It is the tool that has no way to
hold anything back — an answer is prose, said out loud, with nobody's finger on
it — so the only safe bound is on what is read at all. There is still no
`allow_spoilers` there, and still no offer made off the back of one.

## Consequences

**The words of a passage they have not reached are never in the model's context
at any point in the turn.** That was true before by construction and is now true
by a rule one function wide. It is the guarantee this whole record exists to
keep, and it is why the prompt can stop arguing about spoilers.

**Every place in the book is reachable, and one press away.** "Take me to where
the horse dies" on a book they started tonight now puts up the real candidates,
covered, instead of one grudging `better_ahead` or nothing at all.

**A search costs one embedding instead of two.** Directly felt, on the screen
where waiting is felt.

**The model can no longer judge whether a passage ahead is really the one they
meant**, because it cannot read it. The search ranking chooses, the list shows
four at most, and the listener recognises the moment — which is what ADR 4 says
the list is for. For places behind them nothing changes: it still reads the
passages and still says "I couldn't find it" when none is right.

**A model that ignores the format can still say something silly about a time.**
It cannot say anything about what happens at one. That is the difference between
a cosmetic annoyance and a guard failure, and it is the line this record draws.
