"""The thing that empties the queue: a supervisor, and the child it waits on.

Renders used to happen wherever somebody happened to start one — a terminal, a
systemd template unit, or ``Library.add_book`` spawning a detached process and
throwing the handle away. They now happen in exactly one place, under a second
systemd user unit, and this module is both halves of it.

**The supervisor has no torch in it.** It reads one cheap row, spawns a child,
and waits. That is the whole of it, and it is why restarting ``somnia serve``
— which is what a deploy is — costs a render nothing, and why Kokoro and the
embedder never enter the process that answers the page. An OOM kills one book
rather than the night.

**The child holds a lease and asks between sentences.** It claims one job,
builds the expensive things only once it has won, and hands ``ingest_book`` a
callback that beats every ten seconds. That one statement — see
:func:`somnia.queue.beat` — proves the lease is still ours, renews it, and
carries the cancel flag back, so cancellation needs no signal, no pipe and
nothing to reconnect after a restart. Progress, liveness and stopping all come
down that one wire, and there is no other.

**Nothing here catches a signal by itself.** Installing a handler is a
process-wide act and a library function has no business doing it behind the
caller's back — worse, a test that called one would leave the handler installed
in the test runner. :func:`asked_to_stop` is a context manager the command line
wraps around a real render, and everything else is handed a plain callable.
"""

import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from types import FrameType
from typing import TYPE_CHECKING
from uuid import uuid4

from .config import Config
from .queue import (
    Claim,
    beat,
    claim,
    finish,
    note_chapter,
    note_warning,
    reconcile,
    requeue,
)

if TYPE_CHECKING:
    # Names for the two things a render is given, and nothing at runtime: both
    # of these modules pull in numpy on the way past, and one of them is the
    # door to torch. The supervisor imports this file and must carry none of it.
    from .embed import Embedder
    from .tts import TTSEngine

__all__ = ["Child", "Rendered", "asked_to_stop", "render_one", "supervise"]

logger = logging.getLogger(__name__)

# How long the supervisor waits between rounds. Ten seconds is nothing against
# a book that takes hours, and having it there unconditionally — after a child
# as well as instead of one — is what makes a spawn loop impossible: whatever
# else is going on, this process starts at most one child every ten seconds.
IDLE_S = 10.0

# How often the child says it is alive. The callback is asked at the top of
# every sentence, which is once or twice a second, and writing to sqlite that
# often would put the renderer in the way of the page for no reason at all.
# It is also the larger half of what a cancel costs: one interval, plus the
# sentence in flight.
BEAT_EVERY_S = 10.0

# How much of an unexpected exception goes in the queue row. The row is read on
# a phone in the dark, and the whole of it is in the journal anyway.
ERROR_CHARS = 200


@dataclass
class Child:
    """A render child that has already exited: which process, and how it went.

    ``code`` is :meth:`subprocess.Popen.wait`'s, so a negative one is a signal.
    ``pid`` is the interesting half: it is what the row this child claimed
    carries, and therefore the only handle the supervisor has on a job whose
    renderer died without saying anything.
    """

    pid: int
    code: int


@dataclass
class Rendered:
    """What one child did with the one book it claimed.

    ``state`` is the queue's own vocabulary where the job ended in one —
    'done', 'cancelled', 'failed' — plus two words for the endings that leave
    the row alone: 'queued' for a shutdown that put the book back, and 'lost'
    for a lease that belongs to somebody else now.
    """

    id: int
    gid: int
    state: str


def _never() -> bool:
    """Nobody has asked this process to stop, and nobody ever will."""
    return False


@contextmanager
def asked_to_stop() -> Generator[Callable[[], bool]]:
    """Catch SIGTERM and SIGINT, and answer "has somebody asked us to stop?".

    The handler sets a flag and does nothing else. It deliberately does not
    raise: a render has to be allowed to finish the sentence it is speaking and
    then unwind through the ordinary path, because that path is the one that
    puts the book back in the line. Raising from a handler would land the
    exception anywhere at all, including the two lines between a chapter's
    passages being indexed and its row being written.

    It does not try to finish the chapter either. A chapter can take longer
    than systemd's stop timeout, and being SIGKILLed part way through the
    encode is precisely the death that leaves indexed passages the player's
    manifest cannot see. Minutes of Kokoro are cheaper than that.

    The previous handlers go back on the way out, so a test can use this
    without leaving the runner deaf to Ctrl-C.
    """
    asked = False

    def catch(signum: int, frame: FrameType | None) -> None:
        nonlocal asked
        asked = True
        logger.info("signal %d: stopping at the end of this sentence", signum)

    previous = [(s, signal.signal(s, catch)) for s in (signal.SIGTERM, signal.SIGINT)]
    try:
        yield lambda: asked
    finally:
        for sig, handler in previous:
            signal.signal(sig, handler)


# ------------------------------------------------------------- the supervisor


def supervise(
    cfg: Config,
    conn: sqlite3.Connection,
    *,
    spawn: Callable[[], Child] | None = None,
    stopping: Callable[[], bool] = _never,
    idle_s: float = IDLE_S,
) -> None:
    """Empty the queue, one child at a time, for as long as this unit runs.

    A supervisor rather than a renderer, and the difference is the point: this
    process imports nothing expensive, so the memory it holds all night is a
    sqlite connection, and the child that does hold Kokoro exits between books
    and takes every megabyte of it with it.

    The child's stdout and stderr are **inherited**, which is the one line of
    this module a listener would notice. An agent-started render used to write
    to /dev/null, so "rendering chapter 3/34" and the traceback of a failure
    both went nowhere and the only evidence a render existed was that rows kept
    appearing. Both now land in ``journalctl --user -u somnia-worker``.

    ``reconcile`` runs every round and not only at startup. A rendering row
    whose process died with the box is only stale ten minutes later, so a
    tidy-up that ran once would leave the queue wedged behind it until somebody
    restarted the unit — which, since the whole point is that nobody is
    watching at 3am, means until morning.
    """
    spawn = spawn or _spawn_child
    counts = reconcile(conn)
    logger.info(
        "worker watching %s: %d requeued, %d given up on, %d books freed",
        cfg.db_path,
        counts.requeued,
        counts.failed,
        counts.freed,
    )
    while not stopping():
        if _anything_waiting(conn):
            child = spawn()
            if child.code != 0:
                _died_without_saying(conn, child)
        reconcile(conn)
        time.sleep(idle_s)
    logger.info("worker stopping")


def _spawn_child() -> Child:
    """Start one ``somnia worker --once`` and wait for it.

    stdin is closed because a render has nobody to ask anything of. stdout and
    stderr are left alone on purpose: inheriting them is what puts the child's
    chapter lines and its tracebacks in the journal.
    """
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "somnia", "worker", "--once"],
        stdin=subprocess.DEVNULL,
    )
    return Child(pid=proc.pid, code=proc.wait())


def _anything_waiting(conn: sqlite3.Connection) -> bool:
    """Is there a book in the line? One row, no join, once every ten seconds."""
    return (
        conn.execute("SELECT 1 FROM queue WHERE state = 'queued' LIMIT 1").fetchone()
        is not None
    )


def _died_without_saying(conn: sqlite3.Connection, child: Child) -> None:
    """Close a job whose renderer exited holding it.

    The child records its own ending for everything it survives — done,
    cancelled, failed, put back — so a row still saying 'rendering' after the
    process has gone means it was killed outright: an OOM, a SIGKILL past the
    stop timeout, a segfault in something underneath. Nobody else will ever
    correct that row, and until it is corrected it holds the only slot there
    is for ten minutes.

    This is the one write in somnia made by something that does not hold the
    lease, and the reason it is allowed to is stronger than a lease: the
    supervisor *waited for this pid to exit*, so it is the one process in the
    system that can prove nothing holds the row. It is keyed on that pid for
    the same reason — a hand-run ``somnia add`` may be rendering something else
    at this moment, and it is not ours to touch.

    Failed rather than requeued, deliberately. An interruption is somnia's
    business and comes back; a child that got as far as running and then died
    is a book that breaks something, and a queue that spends the night failing
    the same book is worse than one that stops and says why.

    Only ever called for a child that exited non-zero, and that matters: a
    child that exits **cleanly** while its row still says 'rendering' has had
    its lease taken away and stopped writing, which is exactly what it is
    supposed to do — the row belongs to whoever holds it now, and it is not
    ours to close either.
    """
    with conn:
        row = conn.execute(
            "UPDATE queue SET state = 'failed', error = ?, ended_at = datetime('now'),"
            " lease = '', pid = 0 WHERE state = 'rendering' AND pid = ?"
            " RETURNING id, gid",
            (_why_it_died(child.code), child.pid),
        ).fetchone()
    if row is not None:
        logger.error(
            "job %d (book %d): the renderer died holding it, exit code %d",
            row["id"],
            row["gid"],
            child.code,
        )


def _why_it_died(code: int) -> str:
    """One sentence about a process that left nothing behind but a number."""
    if code < 0:
        return (
            f"The renderer was killed by signal {-code} before it could say why."
            " If this keeps happening the box is probably running out of memory."
        )
    return f"The renderer stopped with exit code {code} before it could say why."


# ------------------------------------------------------------------ one book


class _Watch:
    """The one wire between a render and everybody watching it.

    ``ingest_book`` asks :meth:`should_stop` at the top of every sentence and
    calls :meth:`on_chapter` as each chapter's row lands, and between them they
    are the whole of progress, liveness and cancellation. There is no channel
    besides this: no signal, no pipe, no socket to reconnect after a restart —
    only the database three processes already share.

    The beat is throttled because the question is asked once or twice a second
    and the answer only changes when somebody presses something. Ten seconds of
    sqlite writes is nothing; a write per sentence would put the renderer in
    front of the page for no reason at all.

    :meth:`on_warning` goes down the same wire and is not about stopping
    anything: it is the render saying the book it is about to spend six hours on
    parsed into a shape that cannot be right, minutes in, where somebody can
    still act on it.

    ``why`` is what the render was stopped *for*, which :class:`RenderStopped`
    itself does not say — and the three answers want three different things
    done about the row: put it back, leave it alone, or record that somebody
    stopped it.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        job: Claim,
        *,
        lease: str,
        stopping: Callable[[], bool],
        every_s: float,
    ) -> None:
        self._conn = conn
        self._job = job
        self._lease = lease
        self._stopping = stopping
        self._every_s = every_s
        self._last = time.monotonic()
        self.why: str = ""

    def should_stop(self) -> bool:
        if self._stopping():
            # Answered without a round trip, because this one is already known
            # here and the sentence in flight is the only thing worth waiting
            # for when systemd is counting down a stop timeout.
            self.why = "shutdown"
            return True
        now = time.monotonic()
        if now - self._last < self._every_s:
            return False
        self._last = now
        alive = beat(self._conn, self._job.id, lease=self._lease)
        if alive is None:
            self.why = "lost"
            return True
        if alive.cancel:
            self.why = "cancel"
            return True
        return False

    def beat_now(self) -> None:
        """Say the render is alive without being asked to stop.

        For the one stretch of a render that has no sentences in it: everything
        between the claim and the first one. :meth:`should_stop` is the only
        other thing that writes a beat and nothing calls it until ``ingest_book``
        is under way, so the model load and the fetch went by unannounced.
        """
        # Imported here for the reason the module docstring gives about every
        # other ingest import in this file: the supervisor imports this module,
        # and it must not pull numpy and torch in behind it.
        from .ingest import RenderStopped  # noqa: PLC0415

        self._last = time.monotonic()
        alive = beat(self._conn, self._job.id, lease=self._lease)
        # The answer matters as much as the beat. Loading the model is minutes,
        # and it is exactly the window in which another worker decides this
        # render is dead and takes the row — so the first thing this beat can
        # discover is that the job is not ours any more. Carrying on from here
        # would put two renderers on one book, which is the thing the lease
        # exists to make impossible; and a cancel pressed during the load is
        # heard here rather than at the end of the first chapter.
        if alive is None:
            self.why = "lost"
            raise RenderStopped("the job was taken away during start-up")
        if alive.cancel:
            self.why = "cancel"
            raise RenderStopped("stopped before the first sentence")

    def on_chapter(self, _idx: int) -> None:
        note_chapter(self._conn, self._job.id, lease=self._lease)

    def on_warning(self, said: str) -> None:
        note_warning(self._conn, self._job.id, lease=self._lease, note=said)


def render_one(
    cfg: Config,
    conn: sqlite3.Connection,
    *,
    engine: "TTSEngine | None" = None,
    embedder: "Embedder | None" = None,
    stopping: Callable[[], bool] = _never,
    beat_every_s: float = BEAT_EVERY_S,
) -> Rendered | None:
    """Claim the next book in the line and render it, or find out somebody else is.

    None is the ordinary answer and not an error: the line is empty, or another
    process holds the one slot. Nothing expensive has been built by then —
    Kokoro and the embedder are constructed *after* the claim, so a child that
    lost the race costs a python startup and nothing more, and ``somnia add``
    can refuse in the first second instead of importing torch to find out.

    ``engine`` and ``embedder`` are here for the tests, which have neither
    Kokoro nor sentence-transformers installed; left alone this builds the real
    ones. Their types are named under ``TYPE_CHECKING`` only, so annotating
    them costs the supervisor nothing at runtime.
    """
    lease = uuid4().hex
    job = claim(conn, lease=lease, pid=os.getpid())
    if job is None:
        logger.info("nothing to claim: the line is empty, or a render is already on")
        return None
    logger.info("claimed job %d: book %d", job.id, job.gid)

    # Imported here rather than at the top of the module because the supervisor
    # imports this file too, and it exists precisely so that the process
    # waiting on a render holds none of this.
    from .embed import Embedder as RealEmbedder  # noqa: PLC0415
    from .ingest import RenderStopped, ingest_book  # noqa: PLC0415
    from .tts import KokoroEngine  # noqa: PLC0415

    watch = _Watch(conn, job, lease=lease, stopping=stopping, every_s=beat_every_s)
    # In this order, and each step of it is a fix. The request's voice first:
    # the choice belongs to whoever asked for the book, hours before this
    # process existed, and reading it from this process's environment instead
    # made it a property of whichever renderer happened to wake up. Then the
    # voice already on the book, so a resume finishes in the narrator it
    # started in. The configuration last, for a book nobody has said anything
    # about — which is every book the agent adds.
    voice = job.voice or _voice_already(conn, job.gid) or cfg.voice
    logger.info("rendering book %d in %s", job.gid, voice)

    try:
        # Inside the try, which is the whole of this line's point. Loading
        # Kokoro and the embedder is minutes of work that reads model files off
        # disk, and it fails in all the ordinary ways: a half-downloaded
        # weight, a version that moved, a box out of memory. Built above the
        # try, any of those left the row saying 'rendering' with no process
        # behind it and nothing to say why — recovered only by `reconcile` at
        # the next worker start, after STEAL_S of a queue that looks busy.
        engine = engine or KokoroEngine(voice=voice)
        embedder = embedder or RealEmbedder(cfg.embed_model)
        # And a beat before the first sentence, because there is no other one
        # until then. `claim` stamps beat_at and `should_stop` does not write
        # again until ingest_book asks it to, so the gap between them is the
        # model load plus fetching and parsing the book — minutes, against a
        # STEAL_S that assumes a beat every ten seconds. Another worker starting
        # in that window reads a dead render and takes the book away from this
        # one while it is loading.
        watch.beat_now()
        ingest_book(
            cfg,
            conn,
            engine,
            embedder,
            job.gid,
            should_stop=watch.should_stop,
            on_chapter=watch.on_chapter,
            on_warning=watch.on_warning,
        )
    except RenderStopped:
        if watch.why == "shutdown":
            # Nobody stopped wanting the book. It keeps its attempt against it,
            # which is what eventually stops a book that cannot be rendered
            # from being picked up all night.
            requeue(conn, job.id, lease=lease)
            logger.info("job %d put back in the line", job.id)
            return Rendered(job.id, job.gid, "queued")
        if watch.why == "lost":
            # Somebody else holds this row now. Every write below is fenced on
            # the lease and would do nothing anyway, but saying nothing at all
            # is the honest version of that.
            logger.warning("job %d was taken away from this process", job.id)
            return Rendered(job.id, job.gid, "lost")
        finish(conn, job.id, lease=lease, state="cancelled")
        logger.info("job %d stopped, at the end of chapter", job.id)
        return Rendered(job.id, job.gid, "cancelled")
    except Exception as error:
        # A shutdown does not mean the book is broken, and it does not always
        # arrive as RenderStopped. `should_stop` is asked between sentences, so
        # it is only heard between sentences — and the longest thing a chapter
        # does happens after the last of them, in ffmpeg. Stop the worker while
        # a chapter is encoding and the child is killed under it, which comes
        # back here as CalledProcessError: the book was failed, kept its
        # sentence, and a deploy in the wrong second was recorded as a book that
        # cannot be read. Asked of `stopping` rather than of `watch.why`, which
        # is only written where RenderStopped is raised.
        if stopping():
            requeue(conn, job.id, lease=lease)
            logger.info("job %d put back in the line, mid-chapter", job.id)
            return Rendered(job.id, job.gid, "queued")
        # No re-raise. The traceback is already going to the journal, and
        # exiting non-zero would mean something else entirely to the
        # supervisor: it reads a non-zero child as one that died before it
        # could record anything, and this one has just recorded everything.
        sentence = _why_it_failed(conn, job.gid, error)
        logger.exception("job %d (book %d) failed: %s", job.id, job.gid, sentence)
        finish(conn, job.id, lease=lease, state="failed", error=sentence)
        return Rendered(job.id, job.gid, "failed")

    finish(conn, job.id, lease=lease, state="done")
    return Rendered(job.id, job.gid, "done")


def _voice_already(conn: sqlite3.Connection, gid: int) -> str:
    """Which voice has already read part of this book, if any has.

    Between the request and the configuration, and it belongs there. A render
    that died at chapter four comes back through this same path, and picking it
    up in whatever the renderer happens to be set to now would finish the book
    in a second voice — half of it read by one narrator and half by another,
    which is not something a listener would ever ask for and is exactly what a
    changed ``SOMNIA_VOICE`` would silently do.

    A request that *named* a voice still wins, and there is no guard against
    that: it can only come from a terminal, where somebody has typed the name
    of a voice next to the id of a book somnia already has some of, and that is
    a deliberate act rather than a thing to be protected from.
    """
    row = conn.execute("SELECT voice FROM books WHERE gid = ?", (gid,)).fetchone()
    return str(row["voice"]) if row is not None else ""


def _why_it_failed(conn: sqlite3.Connection, gid: int, error: Exception) -> str:
    """One plain sentence, for somebody holding a phone rather than a debugger.

    ``fetch_book`` raises the same RuntimeError whether Gutenberg has never
    heard of the id or has the book in every format except HTML, and those want
    different things done about them — one is a typo or a stale catalog, the
    other is a book somnia genuinely cannot read. The local catalog tells them
    apart without another round trip, and it is matched on the sentence
    gutenberg.py writes because that is the only handle there is; if that
    sentence ever changes, this falls back to the general answer rather than
    lying.
    """
    if isinstance(error, RuntimeError) and str(error).startswith(
        "could not fetch Gutenberg book"
    ):
        # str(gid), because the catalog is FTS5 and holds the id as text: asked
        # for an integer, sqlite decides the two differ by type and silently
        # finds nothing, which here would turn every missing HTML edition into
        # "there is no such book".
        known = conn.execute(
            "SELECT 1 FROM catalog WHERE gid = ?", (str(gid),)
        ).fetchone()
        if known is None:
            return (
                f"There is no Gutenberg book {gid} — or the local catalog is out"
                " of date, so try somnia catalog-update."
            )
        return (
            f"Gutenberg has book {gid} but no HTML edition, so somnia cannot read it."
        )
    return f"The render broke — {type(error).__name__}: {error}"[:ERROR_CHARS]
