# 9. Drop Audiobookshelf

Date: 2026-08-10

## Status

Accepted. This **supersedes** three things in
[ADR 3](0003-play-the-book-in-the-page.md): the position write-through, the
`somnia seed-positions` exception described at the end of *Consequences*, and
the sentence promising that the library is still on disk in ABS's own layout
and the ABS app still works on it. Everything else in that record stands. It is
318 lines of the argument for making the page the player, and this is that
argument reaching its end rather than contradicting itself: an app nothing
plays in is an app nothing needs to write to.

It also replaces the *reason* [ADR 7](0007-cross-a-chapter-without-letting-go.md)
gives for keeping the joined files out of the library. The placement does not
change.

## Context

The pivot in ADR 3 left three things behind that still spoke to Audiobookshelf:
a courtesy position write when the listener stopped, a rescan and a chapter-mark
push after each chapter of a render, and `somnia seed-positions`, run once by
hand to bring old positions across before the first night.

None of them runs. `~/somnia.env` on nuc2 has all three `SOMNIA_ABS_*` lines
commented out, and there is no ABS unit and no ABS container on the box. So
`cfg.abs_token` is empty, no client is ever constructed, `publish_chapters` has
not run for any recent render, and `tell_abs` returns on its first line every
time. The seed has been taken as well: five of the nine books carry an
`abs_item_id`, and Black Beauty carries the position and the high-water mark it
brought across. A one-shot that has been shot is not an outstanding feature.

The question is therefore not whether Audiobookshelf should go — it went, some
time ago, without anybody writing it down. It is whether a thousand lines that
do not execute should stay. They are not free: every one of them is a line
somebody reading this codebase has to follow far enough to find out that it
does nothing, and two of them are a live JWT sitting in a settings file that has
no use for it.

## Decision

**Audiobookshelf comes out of somnia altogether.** `abs.py`, `seed.py`, the
`libraries` and `seed-positions` subcommands, the three `SOMNIA_ABS_*` settings
and every call site go. `books.abs_item_id` is dropped from the schema after the
code is deployed, so that the gap between the two is a column nobody reads
rather than a migration. Nothing is kept for compatibility: there is one
instance, its ABS is already off, and the change in behaviour on it is nil.

**`SOMNIA_LIBRARY_DIR` stays, and so does the
`<Author>/<Title>/NNN - <chapter>.m4a` layout.** The obvious tidy-up is to fold
the library into the data directory now that nothing else reads the folder, and
it is refused. The two reasons have nothing to do with ABS:

- `chapters.audio_file` holds an absolute path for every chapter of every book
  on the box. Merging the directories means moving the files **and** rewriting
  the rows — a real migration, bought for no functional gain.
- The directory is independently justified. Audio is the large thing and
  belongs on whatever disk has room for it, and the server's refusal to serve a
  chapter that resolves outside `library_dir` is a containment rule worth
  keeping in a deployment with no auth anywhere. `somnia-doctor.sh` already
  checks both.

The layout it happens to be in was ABS's, and is now simply a shape that reads
well in a file manager. Nothing depends on it.

ADR 7 puts the joined files under `SOMNIA_DATA_DIR/streams` and **never** in the
library, on the grounds that a second copy of every book appearing among ABS's
own files would break ADR 3's promise in a scan nobody was watching. That
promise is what this record supersedes, so the reason is restated rather than
the decision: the library holds what a render produced, one file per chapter,
each with a row pointing at it; a join is a cache that can be deleted at any
time and rebuilt in a second or two of ffmpeg. Keeping the two apart is how
nothing has to tell them apart.

## Consequences

**Nothing changes on the live box.** That is the whole reason a one-shot
migration is safe and "no legacy path" is the right call. It is also the
uncomfortable part: a feature can stop working for months on the only
deployment there is, and the way it was found was reading the settings file for
another purpose.

**Offline listening has no fallback any more, and ADR 3 said it did.** That
record named offline downloads the largest loss of the pivot and softened it
with *if offline listening turns out to matter more than being moved to the
passage, the app is still there to do it*. It is not there. A night the tailnet
goes is a night without the book, and there is no second way to hear it.

**The asymmetry ADR 3 wrote down plainly has gone with the thing it was about.**
There is no longer anywhere else the book might be opened, so there is no longer
a night somnia does not learn about. `books.position_ms` is the record rather
than one of two records, and nothing can disagree with it.

**A capability was lost, and it was lost before this record.** ABS's web UI was
the only place a book could be deleted, a folder tidied, a bad render thrown
away. somnia has no delete anywhere — no route, no CLI command, no agent tool.
That went when the `SOMNIA_ABS_*` lines were commented out, not here, which is
why this does not wait on a replacement. Library management deserves its own
plan and its own argument, and `_forget_the_old_edition`'s reason for leaving
orphan m4a files behind — that deleting files somebody may be listening to
right now is the worse thing to be wrong about — is where that argument starts,
not where it ends. A re-render is not a delete.

**Something small is fixed by ceasing to be visible.** Three folders on nuc2
still read `The Project Gutenberg eBook of Dracula, by Bram Stoker.`, from
before the title repair in `db._repair`. That was ugly because it was a shelf
somebody looked at. It is now a path nobody reads: no rename, no migration, and
nothing to fix.

**One flat vocabulary where there were two.** The position report's `reason`
existed in two sets, because the five words that meant the sound had stopped
were the ones that triggered the write to ABS. With nothing to trigger, nothing
branches on the word at all; it is kept only so that a reason nobody wrote can
be noticed on the way in.
