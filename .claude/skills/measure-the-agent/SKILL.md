---
name: measure-the-agent
description: Measure how long a question takes and whether the agent still routes and withholds correctly, against the real book on nuc2. Use before changing the model, the effort level, the prompt or the tools; when somnia feels slow; or when claiming one model is better than another.
---

# Measure the agent

A model is faster or safer than another one when it has been measured against
the real book, not when it sounds like it should be. This is the harness for
that, and the traps that make a first attempt tell you nothing.

`evaluate.py` beside this file does the whole run. Read the traps before
changing it, because four of the five cost a round each the first time.

## Where the time actually goes

Measured on nuc2, and worth knowing before optimising the wrong end:

| | |
|---|---|
| A search of the book — question embedded, sqlite-vec, both spoiler passes | **0.10s** |
| One round trip to Anthropic | **1–3s** |
| A turn | 2–3 round trips |
| Loading the embedding model | **12.3s**, once, at startup since PR #70 |

Retrieval is a rounding error. **Every second worth having is on the model
side**: which model, how hard it is told to think, and how much of the prompt
it has to re-read. Do not go looking in sqlite.

## Run it

```
scp .claude/skills/measure-the-agent/evaluate.py nuc2:/tmp/
ssh nuc2 'set -a; . ~/somnia.env; set +a; export SOMNIA_DATA_DIR=/tmp/evaldata;
    PYTHONPATH=/tmp/wtsrc VIRTUAL_ENV=/home/giles/somnia-venv \
    /home/giles/somnia-venv/bin/python -u /tmp/evaluate.py 5'
```

`PYTHONPATH` pointing at an rsync'd copy of the branch's `src/` is what tests a
change **without installing it**, so the box keeps whatever build it is holding
for somebody else. See `somnia-project-state` on the one-build problem.

## The five traps

**Snapshot the database first, or the eval moves the book.** Half the cases are
"take me back to…", and a move is a real write to `books.position_ms`. Run
against a copy and point `SOMNIA_DATA_DIR` at it:

```
VACUUM INTO '/tmp/evaldata/somnia.db'      -- never cp; there is a live WAL
```

`evaluate.py` refuses to start unless its database path says `evaldata`. That
assertion exists because the lesson was learned the expensive way: an early run
moved a real listening position by four minutes and it could not be put back
exactly, only approximately and in the safe direction.

**Print verdicts, never replies.** Giles reads this output and is mid-book. A
harness that echoes what the model said about the ending has spoiled the book
in the course of checking that the model does not spoil the book. Counts and
pass/fail only; the judge is told to name the *category* of a leak and never
its content. See `avoid-spoilers-for-books-in-progress`.

**The judge needs structured output or it will fudge.** Asked for a line of
either `CLEAN` or `LEAK: <reason>`, it dutifully writes `LEAK: none — reply
reveals nothing later` and every naive parser scores that as a leak. Use
`output_config.format` with a boolean field; then it cannot answer sideways.

**Give the judge room to think.** Opus 5 thinks by default and `max_tokens`
caps thinking *and* text together, so a judge at `max_tokens=1000` returns a
message with no text block at all and the harness dies on `StopIteration`.
8000 is comfortable.

**Medians, not single runs.** Turn times vary by 2x run to run. Four or five
repetitions per case, report the median and p90; a single timing is not
evidence of anything.

## What to check, not just how fast

Speed alone will happily recommend a model that has stopped doing the job. The
three that matter, all mechanical from the tool calls:

- **Routing.** A question must be answered where they are (`recall`, no
  `move_to`, no `offer_positions`) and a request to be taken somewhere must
  move or offer. Getting this backwards is the expensive one — they asked what
  a name was and lost the hour.
- **A name is in the book, not in the catalog.** "Who is Rob Roy" must not
  reach `search_catalog`. This is the exact failure that demoted Haiku in
  `9b26bb6`, so it is the regression case for any model change.
- **The offer sentence.** A turn that called `offer_positions` must say the
  neutral sentence and nothing else, or it is narrating the rows the screen
  deliberately covers up.

## When a spoiler check fails, find out which half leaked

The guard is two things and only one is a mechanism:

- **Retrieval** stops at `heard_to_ms + 60s`. Check it directly — call
  `lib.recall(...)` and assert every `passage.start_ms` is inside the bound.
  Measured sound over seven probe questions.
- **What the model says** is bounded by a sentence in the prompt and nothing
  else, because ADR 6 lets it answer from what it already knows. Both Haiku and
  Sonnet crossed that line on ~2–4 turns in 100.

So a leak is almost certainly the second, and the fix is prompt or design, not
sqlite. Confirm which before filing anything.

## Results worth not re-deriving

2026-08-08, 85 turns per model, Black Beauty at 51 of 306 minutes:

| | routing | spoiler-safe | median | p90 |
|---|---|---|---|---|
| sonnet-5 (effort medium) | 84/85 | 82/85 | 4.89s | 6.40s |
| haiku-4.5 | 85/85 | 83/85 | 2.46s | 3.50s |

Haiku became the default on that, in PR #70. **Haiku has no effort dial** and
rejects `output_config.effort` with a 400, which is why `agent.effort_for()`
asks the Models API before sending one — do not add it back to a probe by hand.
