"""The ingest queue: one book rendered at a time, and everybody can see it.

Adding a book used to be a spawn and a shrug. ``Library.add_book`` started
``somnia add`` with all three of its stdio at /dev/null and threw the handle
away, so two requests a minute apart gave two Kokoro processes on two vCPUs —
and at that point the renderer no longer outruns somebody listening at 1x,
which is the assumption the whole of streaming ingest rests on. Nothing could
be seen either: no progress, no failure, no cancel, and a render that died left
its book claiming to be 'rendering' for ever.

This module is the state machine that replaces it. Pure functions over a
connection somebody else owns, in the shape of :mod:`somnia.index` and
:mod:`somnia.catalog`, so the server can call them on its own connection, the
worker on its, and the CLI on a third — which it must, because the whole point
is that the process watching a render is not the process doing it.

Three things are worth knowing before reading the SQL.

**The claim is one statement.** Whether anything is already rendering, and the
taking of the slot if not, happen inside a single guarded ``UPDATE ...
RETURNING``. sqlite has exactly one writer, so two claimants cannot both
observe an empty slot: the second waits for the write lock, and by the time it
has it the first has committed and its own ``WHERE`` no longer holds. An empty
result is the answer — the same idiom ``tools._write_position`` already uses.
Checking and then writing would be two statements with a race between them,
which on two vCPUs is a race that is lost the first time somebody double-taps.

**A lease is a uuid4, never a pid.** Pids come round again after a reboot, and
a lease that a stranger process can accidentally hold is not a lease. It is
carried on every write a renderer makes, and a write that does not match it
does nothing at all — so a worker that was superseded while it was thinking
cannot write over the one that replaced it.

**Liveness is a timestamp, read at read time.** A lock file answers "is
anything rendering" but a wedged process still holds one, so it reads healthy
for ever. ``beat_at`` is the only thing that tells a crashed renderer from a
slow one, and because staleness is computed when somebody looks rather than
written down by anybody, the queue says "not responding" honestly even when the
worker unit has been stopped and there is nobody left to write it.
"""

import sqlite3
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "MAX_ATTEMPTS",
    "STALE_S",
    "STEAL_S",
    "Beat",
    "Claim",
    "QueueRow",
    "Reconciled",
    "Stopped",
    "Submission",
    "beat",
    "claim",
    "finish",
    "note_chapter",
    "reconcile",
    "requeue",
    "stop",
    "submit",
    "view",
]

# How long a render may go without a heartbeat before the readout stops
# believing in it. Five minutes is longer than any single chapter's worth of
# beats and shorter than anybody's patience, and it is only a caption: nothing
# is taken away from a render for being quiet for five minutes.
STALE_S = 300

# How long before the slot itself is considered free. Twice the caption, because
# taking a book away from a process that turns out to be alive is the one
# mistake that produces two renderers, and being told "not responding" for five
# minutes before anything is done about it is the cheap half of that trade.
STEAL_S = 600

# How many times somnia will pick a book back up after an interruption. A render
# that is killed by a deploy or a reboot deserves to be resumed; a book that
# cannot be rendered at all would otherwise be retried all night, and a queue
# that spends the night failing the same book is worse than one that stops and
# says why.
MAX_ATTEMPTS = 3

# Waiting or running: exactly the rows the partial unique index constrains, and
# exactly the rows that hold a book's one live slot. A tuple of two strings
# renders as ('queued', 'rendering'), which is a SQL list, so it is interpolated
# into the statements below rather than restated in each of them — the one place
# a literal is safe to interpolate being a constant defined four lines above it.
LIVE = ("queued", "rendering")

# How a job can end. The renderer finished it, somebody stopped it, or it broke.
Terminal = Literal["done", "cancelled", "failed"]


@dataclass
class Submission:
    """What happened to a request to add a book.

    ``said`` is a sentence, always, because every caller is going to show it to
    somebody: the agent reads it out, the page prints it under the search
    results, and the CLI puts it on stdout. A refusal is not an error — it is an
    answer — so it comes back the same shape as an acceptance with ``ok`` false
    and ``id`` zero, and nothing anywhere has to catch anything.
    """

    ok: bool
    id: int
    said: str


@dataclass
class Stopped:
    """What happened to a request to stop a render.

    ``state`` is what the row says afterwards, which is the interesting part: a
    job that was only waiting is 'cancelled' by the time this returns, while one
    that is rendering is still 'rendering' — nothing here reaches into that
    process, it only raises a flag the process will notice between sentences.
    An empty ``state`` means there is no such job at all, which is the one case a
    caller may want to answer differently from "too late".
    """

    ok: bool
    state: str
    said: str


@dataclass
class Claim:
    """The one job this process may now render, the book it is, and its voice.

    ``voice`` is empty for a job that named none, and the renderer reads that as
    "use whatever I am configured with" rather than substituting a default here.
    The two are the same string today; they are not the same statement, and the
    one place entitled to decide what an unspecified voice means is the process
    that holds the configuration.
    """

    id: int
    gid: int
    voice: str = ""


@dataclass
class Beat:
    """The answer to a heartbeat: keep going, or stop.

    That there is an answer at all is what makes cancellation free. The renderer
    has to say it is alive anyway, and the same statement that records it can
    carry the one bit back — so there is no signal to deliver, no pipe to keep
    open, and nothing to reconnect after a restart.
    """

    cancel: bool


@dataclass
class Reconciled:
    """What a tidy-up found, for the line it writes to the journal."""

    requeued: int
    failed: int
    freed: int


@dataclass
class QueueRow:
    """One row of the readout, with everything a caption needs and nothing else.

    ``chapters_done`` is counted from the ``chapters`` table rather than kept as
    a number somewhere, because a chapters row exists only once its m4a does:
    counting is the only form of the answer that cannot claim a chapter is
    listenable before it is. ``chapters_total`` is 0 for every book rendered
    before that column existed, and 0 means "nobody wrote it down" — so anything
    drawing "chapter 4 of 39" has to check it first.

    ``responding`` is about the renderer and not about the book: a job nobody has
    claimed is responding, because there is nobody to be silent. ``place`` is
    the rank among the books that are waiting, and 0 for anything that is not
    waiting — the one being rendered has left the line rather than being at the
    head of it.

    ``voice`` is here so that a choice made in one screen can be checked from
    another before it costs six hours. It is empty for a row that named none,
    and the readout says nothing at all in that case rather than guessing at the
    renderer's configuration, which this process cannot see.
    """

    id: int
    gid: int
    title: str
    authors: str
    voice: str
    state: str
    place: int
    chapters_done: int
    chapters_total: int
    rendered_ms: int
    stopping: bool
    responding: bool
    error: str
    submitted_at: str
    started_at: str


def _name(title: str, gid: int) -> str:
    """What to call a book in a sentence when it may not have a name yet.

    A submitted book has been through nothing but the local catalog, and the
    catalog can be missing, stale, or simply not have the book. "book 1342" is
    then the whole of the truth, and it is a good deal better than an empty pair
    of quotes in the middle of a sentence somebody reads at 2am.
    """
    return title or f"book {gid}"


def submit(conn: sqlite3.Connection, gid: int, voice: str = "") -> Submission:
    """Ask for a book to be rendered, and say where it lands in the line.

    ``voice`` is written down here, on the request, because this is the only
    moment anybody chooses it. Hours may pass before a worker picks the book up,
    and that worker is a different process with its own environment: a voice
    that lived in the renderer's configuration was therefore not a choice about
    a book at all, it was a choice about whatever happened to be rendering at
    the time. Empty means "the renderer's own", which is what the agent submits
    — nobody is picking a voice out loud at 2am — and what every row written
    before the column existed holds.

    Nothing here checks the name. The roster in :mod:`somnia.voices` is the
    page's constraint and is enforced where the press lands; a terminal is
    allowed the whole of Kokoro's list, and a name that is in neither fails in
    the model's own loader with the real list in the message.

    No network. Whether Gutenberg has this book, and whether it has it as HTML,
    costs a round trip and a parse, and a control that sits there for three
    seconds before answering reads as broken — so an unknown gid is accepted
    here and fails minutes later in the worker with a sentence saying which of
    the two it was.

    Two refusals. A book with a live queue row is already coming, and asking
    twice must not put it in the line twice. A book somnia already has, all of
    it, is done: re-rendering it would spend hours to produce the same audio and
    would take the listener nowhere.

    Everything else is accepted, and the interesting case is a books row on
    'pending' — a render that was interrupted, cancelled, or killed by a deploy.
    ``add_book`` used to refuse a book in *any* status, which meant a render
    that died at chapter three could never be asked for again by voice; that
    guard was the only thing standing between the agent and a second copy of
    every passage in the index, and it has been replaced by the fix rather than
    kept. A books row stuck on 'rendering' is accepted for the same reason: on
    the VPS that is what every render an agent ever started looks like, because
    the next deploy shot it dead.
    """
    live = conn.execute(
        f"SELECT title, state FROM queue WHERE gid = ? AND state IN {LIVE}", (gid,)
    ).fetchone()
    if live is not None:
        name = _name(str(live["title"]), gid)
        return Submission(
            False,
            0,
            f"{name} is being rendered now."
            if str(live["state"]) == "rendering"
            else f"{name} is already in the queue.",
        )
    book = conn.execute(
        "SELECT title, status FROM books WHERE gid = ?", (gid,)
    ).fetchone()
    if book is not None and str(book["status"]) == "done":
        return Submission(
            False, 0, f"{_name(str(book['title']), gid)} is already here, all of it."
        )

    # str(gid), and it matters. The catalog is an FTS5 table, so its gid column
    # holds the text '271'; handed the integer 271 sqlite compares an integer
    # against a string, decides they differ by type, and answers nothing at all
    # — no error, just a book with no name and no author, which is also how a
    # render ends up in a folder called 'Unknown Author'.
    entry = conn.execute(
        "SELECT title, authors FROM catalog WHERE gid = ?", (str(gid),)
    ).fetchone()
    title = str(entry["title"]) if entry is not None else ""
    authors = str(entry["authors"]) if entry is not None else ""

    try:
        with conn:
            row = conn.execute(
                "INSERT INTO queue (gid, title, authors, voice)"
                " VALUES (?, ?, ?, ?) RETURNING id",
                (gid, title, authors, voice),
            ).fetchone()
    except sqlite3.IntegrityError:
        # The partial unique index, catching what the read above could not: two
        # presses close enough together that both saw an empty queue. Losing
        # that race is the same answer as being refused by the check above, and
        # is said in the shape that is true of both live states — whoever won it
        # a millisecond ago may already have been claimed.
        return Submission(False, 0, f"{_name(title, gid)} is already in the queue.")

    job_id = int(row["id"])
    ahead = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM queue WHERE state = 'queued' AND id < ?",
            (job_id,),
        ).fetchone()["n"]
    )
    name = _name(title, gid)
    if ahead == 0:
        # Not "starts now", which would be a promise about a worker this process
        # cannot see. Next is true whether or not anything is running, and
        # whether or not anybody remembered to start the worker at all.
        said = f"{name} is next to be rendered."
    elif ahead == 1:
        said = f"{name} is in the queue, behind one other book."
    else:
        said = f"{name} is in the queue, behind {ahead} other books."
    return Submission(True, job_id, said)


# What to say about a job that has already ended, in the middle of the sentence
# explaining why it cannot be stopped.
_ALREADY = {
    "done": "has already been rendered",
    "cancelled": "was stopped already",
    "failed": "has already failed",
}


def stop(conn: sqlite3.Connection, job_id: int) -> Stopped:
    """Take a book out of the line, or ask the render to stop.

    One statement does both, and it has to: read-then-write would leave a window
    in which a claim lands between the two, and the caller would be told the
    book had been taken out of the queue while a process was already rendering
    it. So the ``CASE`` decides inside the update — a waiting job ends here and
    now, a running one only gets the flag raised, and which of the two happened
    comes back in ``RETURNING``.

    The flag is all a running render gets. Nothing signals it, nothing kills it:
    it asks, between sentences, and stops on the next chapter boundary. That
    costs up to about twenty seconds and buys the guarantee that a stop never
    lands between a chapter's passages being indexed and its row being written,
    which would leave the index holding words the player's manifest cannot see.

    Keyed on the job id and not on the gid, because a book owns several rows
    over its life and stopping "Black Beauty" could otherwise reach into last
    week's attempt.
    """
    with conn:
        row = conn.execute(
            "UPDATE queue SET cancel = 1,"
            " state = CASE WHEN state = 'queued' THEN 'cancelled' ELSE state END,"
            " ended_at = CASE WHEN state = 'queued' THEN datetime('now')"
            "                 ELSE ended_at END"
            f" WHERE id = ? AND state IN {LIVE}"
            " RETURNING state, title, gid",
            (job_id,),
        ).fetchone()
    if row is not None:
        name = _name(str(row["title"]), int(row["gid"]))
        state = str(row["state"])
        said = (
            f"{name} has been taken out of the queue."
            if state == "cancelled"
            else f"{name} stops at the end of the sentence it is reading."
        )
        return Stopped(True, state, said)

    # Only now, on the path where nothing was changed, is it worth a second read
    # to find out why — and the two reasons want different answers from a
    # caller, so they are told apart rather than collapsed into one refusal.
    other = conn.execute(
        "SELECT state, title, gid FROM queue WHERE id = ?", (job_id,)
    ).fetchone()
    if other is None:
        return Stopped(False, "", f"There is no job {job_id} in the queue.")
    state = str(other["state"])
    name = _name(str(other["title"]), int(other["gid"]))
    return Stopped(
        False,
        state,
        f"{name} {_ALREADY.get(state, 'is not running')}, so there is nothing to stop.",
    )


def claim(
    conn: sqlite3.Connection, *, lease: str, pid: int, steal_s: int = STEAL_S
) -> Claim | None:
    """Take the next book in the line, if and only if nothing is rendering.

    The whole of one-at-a-time is in this statement's ``WHERE``. The subquery
    picks the oldest waiting job, and the ``NOT EXISTS`` refuses outright while
    any row is rendering with a heartbeat newer than ``steal_s``. Both are
    evaluated with the write lock held, which is what makes "nobody is
    rendering" a fact rather than a reading that may already be out of date.

    None is the ordinary answer, not an error: it means somebody else is
    rendering, or there is nothing to render. The caller exits and is started
    again in ten seconds by something that costs nothing to start.

    ``attempts`` counts up here, on the taking rather than on the failing,
    because the failures this bounds are the ones where nobody survives to
    record anything — a box that lost power does not get to increment a counter
    on its way down.
    """
    with conn:
        row = conn.execute(
            "UPDATE queue SET state = 'rendering', lease = :lease, pid = :pid,"
            " started_at = datetime('now'), beat_at = datetime('now'),"
            " attempts = attempts + 1"
            " WHERE id = (SELECT id FROM queue WHERE state = 'queued'"
            "             ORDER BY id LIMIT 1)"
            " AND NOT EXISTS (SELECT 1 FROM queue WHERE state = 'rendering'"
            "                 AND beat_at > datetime('now', :steal))"
            " RETURNING id, gid, voice",
            {"lease": lease, "pid": pid, "steal": f"-{steal_s} seconds"},
        ).fetchone()
    if row is None:
        return None
    return Claim(id=int(row["id"]), gid=int(row["gid"]), voice=str(row["voice"]))


def beat(conn: sqlite3.Connection, job_id: int, *, lease: str) -> Beat | None:
    """Say the render is alive, and find out whether it should stop.

    One statement proves the lease is still ours, renews it, and carries the
    cancel flag back. None means this process is not the renderer any more —
    somebody stole the lease after we went quiet for ten minutes, or the job was
    ended out from under us — and the only correct response is to stop writing
    anything at all, because whatever holds it now is entitled to the book.

    An empty lease is refused before it reaches the database. ``lease = ''`` is
    what a finished or requeued row holds, and it is a perfectly valid thing to
    ask sqlite for: a bug that let one through would beat every row nobody owns
    back into looking alive, and the slot would never come free again.
    """
    if not lease:
        return None
    with conn:
        row = conn.execute(
            "UPDATE queue SET beat_at = datetime('now')"
            " WHERE id = ? AND lease = ? RETURNING cancel",
            (job_id, lease),
        ).fetchone()
    return Beat(cancel=bool(row["cancel"])) if row is not None else None


def note_chapter(conn: sqlite3.Connection, job_id: int, *, lease: str) -> None:
    """Record that a chapter has just landed.

    A second clock beside the heartbeat, and the reason for it is that the two
    disagree in a useful way: a fresh beat with an old ``chapter_at`` is a long
    chapter, which is normal and worth waiting for, while a stale beat is a
    process that is gone. One number cannot say both.

    Silently a no-op without the lease, like every other write here — the row
    belongs to whoever holds it, and this process finding out it does not is
    :func:`beat`'s job rather than this one's.
    """
    if not lease:
        return
    with conn:
        conn.execute(
            "UPDATE queue SET chapter_at = datetime('now'), beat_at = datetime('now')"
            " WHERE id = ? AND lease = ?",
            (job_id, lease),
        )


def finish(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    lease: str,
    state: Terminal,
    error: str = "",
) -> None:
    """End a job: rendered, stopped, or broken, and give the slot back.

    The lease is cleared with the same write, so the moment this returns the
    ``NOT EXISTS`` in :func:`claim` no longer sees this row and the next book can
    start. ``error`` is one plain sentence — it is printed to somebody in the
    dark, not parsed — and it is empty for the two endings that are not failures.

    The row stays. It is the record of a render that happened, which is what the
    readout shows for a day afterwards and what makes "it failed, and here is
    why" sayable at all.
    """
    if not lease:
        return
    with conn:
        conn.execute(
            "UPDATE queue SET state = ?, error = ?, ended_at = datetime('now'),"
            " lease = '', pid = 0 WHERE id = ? AND lease = ?",
            (state, error, job_id, lease),
        )


def requeue(conn: sqlite3.Connection, job_id: int, *, lease: str) -> None:
    """Put a book back in the line, because nobody stopped wanting it.

    This is what a worker being shut down does, and it is deliberately not
    'cancelled': a deploy, a reboot or a `systemctl stop` is somnia's business
    and not the listener's, so the book goes back to waiting and is picked up
    again by whatever starts next. It keeps its ``attempts``, which is the only
    thing that eventually stops a book that cannot be rendered from being tried
    all night.

    The heartbeat is cleared along with the lease. A queued row with a live
    heartbeat would keep :func:`claim` refusing on behalf of a process that has
    already exited, which is the queue wedging itself shut.
    """
    if not lease:
        return
    with conn:
        conn.execute(
            "UPDATE queue SET state = 'queued', lease = '', pid = 0, beat_at = NULL,"
            " chapter_at = NULL, started_at = NULL WHERE id = ? AND lease = ?",
            (job_id, lease),
        )


def reconcile(conn: sqlite3.Connection, *, steal_s: int = STEAL_S) -> Reconciled:
    """Put right whatever the last crash left behind. Run at worker startup.

    Three things, in this order, because each one changes what the next sees.

    A render that stopped beating has no process behind it. If the book has been
    picked up ``MAX_ATTEMPTS`` times without finishing it is failed with a
    sentence, and otherwise it goes back in the line — a box that lost power owes
    nobody an explanation, but the third power cut in a row is not a power cut.

    Then the books rows. A book on 'rendering' with nothing actually rendering it
    is a lie that nothing else will ever correct: ``ingest_book`` writes
    'pending' on its way out of every ending it survives, and the endings it does
    not survive are exactly the ones that leave this. Every render an agent ever
    started on the VPS is in this state, because ``start_new_session`` escapes
    the process group but not the cgroup, so each deploy killed them all.

    The sentence for a book that keeps dying is built in SQL so that it can name
    the real count, which is more honest than a constant if ``MAX_ATTEMPTS`` ever
    moves.
    """
    stale = f"-{steal_s} seconds"
    with conn:
        failed = conn.execute(
            "UPDATE queue SET state = 'failed', ended_at = datetime('now'),"
            " lease = '', pid = 0, error = 'Interrupted ' || attempts ||"
            " ' times without finishing, so somnia stopped trying.'"
            " WHERE state = 'rendering' AND attempts >= ?"
            " AND (beat_at IS NULL OR beat_at <= datetime('now', ?))"
            " RETURNING id",
            (MAX_ATTEMPTS, stale),
        ).fetchall()
        requeued = conn.execute(
            "UPDATE queue SET state = 'queued', lease = '', pid = 0, beat_at = NULL,"
            " chapter_at = NULL, started_at = NULL WHERE state = 'rendering'"
            " AND (beat_at IS NULL OR beat_at <= datetime('now', ?)) RETURNING id",
            (stale,),
        ).fetchall()
        freed = conn.execute(
            "UPDATE books SET status = 'pending' WHERE status = 'rendering'"
            " AND gid NOT IN (SELECT gid FROM queue WHERE state = 'rendering'"
            "                 AND beat_at > datetime('now', ?)) RETURNING gid",
            (stale,),
        ).fetchall()
    return Reconciled(requeued=len(requeued), failed=len(failed), freed=len(freed))


def view(conn: sqlite3.Connection, *, stale_s: int = STALE_S) -> list[QueueRow]:
    """Everything worth showing: what is rendering, what is next, what went wrong.

    Terminal rows fall off after a day. After a day a failure is history rather
    than news, and history is in the journal — which is why there is no dismiss
    control anywhere in this feature: a list that empties itself needs nothing
    pressed to make it go away, and a press that only tidies a list is a press
    that can be made by mistake at 2am.

    The order is what is happening, then what is next, then what went wrong,
    because that is the order somebody reads it in. Within the line it is
    submission order, which is also the order it will be rendered in; within the
    dead it is newest first.

    One row per job, joined to the book it is about — which may not exist yet,
    since a book has no ``books`` row until its parse finishes, so every number
    that comes from there has to survive being absent.
    """
    rows = conn.execute(
        "SELECT q.id, q.gid, q.title, q.authors, q.voice, q.state, q.cancel, q.error,"
        " q.submitted_at, q.started_at,"
        " (SELECT COUNT(*) FROM chapters c WHERE c.book_gid = q.gid) AS chapters_done,"
        " COALESCE(b.chapters_total, 0) AS chapters_total,"
        " COALESCE(b.total_ms, 0) AS rendered_ms,"
        " (q.beat_at IS NOT NULL AND q.beat_at > datetime('now', :stale)) AS fresh"
        " FROM queue q LEFT JOIN books b ON b.gid = q.gid"
        f" WHERE q.state IN {LIVE}"
        "    OR (q.ended_at IS NOT NULL AND q.ended_at > datetime('now', '-24 hours'))"
        " ORDER BY CASE q.state WHEN 'rendering' THEN 0 WHEN 'queued' THEN 1"
        "                       ELSE 2 END,"
        f"         CASE WHEN q.state IN {LIVE} THEN q.id ELSE 0 END,"
        "          q.ended_at DESC, q.id",
        {"stale": f"-{stale_s} seconds"},
    ).fetchall()

    out: list[QueueRow] = []
    place = 0
    for r in rows:
        state = str(r["state"])
        if state == "queued":
            # Counted here rather than asked of the database, which is safe only
            # because the ordering above already puts the waiting rows in the
            # order they will be taken.
            place += 1
        out.append(
            QueueRow(
                id=int(r["id"]),
                gid=int(r["gid"]),
                title=str(r["title"]),
                authors=str(r["authors"]),
                voice=str(r["voice"]),
                state=state,
                place=place if state == "queued" else 0,
                chapters_done=int(r["chapters_done"]),
                chapters_total=int(r["chapters_total"]),
                rendered_ms=int(r["rendered_ms"]),
                stopping=state == "rendering" and bool(r["cancel"]),
                responding=state != "rendering" or bool(r["fresh"]),
                error=str(r["error"]),
                submitted_at=str(r["submitted_at"]),
                started_at=str(r["started_at"] or ""),
            )
        )
    return out
