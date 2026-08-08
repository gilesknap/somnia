"""The worker: one book at a time, and what happens when a render dies.

Nothing here loads Kokoro or torch, and neither is installed in this
environment at all — which is itself one of the assertions. ``render_one``
builds the expensive things only after it has won a claim, so a call that loses
one has to come back without an ImportError to its name.

Where the supervisor is under test the child is stood in for by a spawn hook.
A real child is a whole python process and a night of rendering; what the
supervisor is actually answerable for is the order books are taken in, that
only one is taken at a time, and what it does about a child that died without
saying anything — and all three of those are visible in the queue table.

The renders that do run here run in-process, over the same three-chapter Black
Beauty ``tests/test_ingest.py`` uses, with silence for audio and one-hot
vectors for embeddings.
"""

import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from fakes import FakeEmbedder
from somnia import ingest
from somnia.audio import ChapterAudio
from somnia.catalog import update_catalog
from somnia.config import Config
from somnia.db import connect
from somnia.embed import Embedder
from somnia.gutenberg import Book, Chapter
from somnia.queue import Claim, claim, finish, stop, submit
from somnia.tts import TTSEngine
from somnia.worker import Child, render_one, supervise
from test_ingest import BOOK, Fetched, SilentEngine

CSV = """\
Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves
271,Text,2006-01-25,Black Beauty,en,"Sewell, Anna, 1820-1878",Horses,PZ,
120,Text,2006-01-25,Treasure Island,en,"Stevenson, Robert Louis",Pirates,PZ,
2701,Text,2001-07-01,Moby Dick,en,"Melville, Herman",Whaling,PZ,
"""


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = connect(tmp_path / "somnia.db")
    try:
        update_catalog(c, csv_text=CSV)
        yield c
    finally:
        c.close()


@pytest.fixture
def gutenberg(monkeypatch: pytest.MonkeyPatch) -> Fetched:
    """Gutenberg and ffmpeg stubbed, exactly as tests/test_ingest.py stubs them.

    The six lines are written out again rather than shared, because a pytest
    fixture cannot be called by hand and importing one under its own name
    shadows it. What genuinely must not diverge is the book and the engine, and
    both of those do come from over there.
    """
    fetched = Fetched(book=BOOK)

    def encode(self: ChapterAudio, out_path: Path, bitrate: str = "64k") -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.touch()

    def fetch_book(gid: int, url: str | None = None) -> Any:
        return fetched.book

    monkeypatch.setattr(ChapterAudio, "encode", encode)
    monkeypatch.setattr(ingest, "fetch_book", fetch_book)
    return fetched


def cfg(tmp_path: Path) -> Config:
    return Config(data_dir=tmp_path, library_dir=tmp_path / "library")


def never() -> bool:
    """Nobody has asked this process to shut down.

    Passed everywhere on purpose. Left to itself ``render_one`` is handed a
    signal-backed one by the command line, and a test that let that happen
    would install a SIGTERM handler in the pytest process and leave it there.
    """
    return False


def row_of(conn: sqlite3.Connection, job_id: int) -> Any:
    return conn.execute("SELECT * FROM queue WHERE id = ?", (job_id,)).fetchone()


def book_row(conn: sqlite3.Connection) -> Any:
    return conn.execute("SELECT * FROM books WHERE gid = 271").fetchone()


def age_beat(conn: sqlite3.Connection, job_id: int, seconds: int) -> None:
    """Move a job's heartbeat into the past, which is how time passes here."""
    with conn:
        conn.execute(
            "UPDATE queue SET beat_at = datetime('now', ?) WHERE id = ?",
            (f"-{seconds} seconds", job_id),
        )


def chapters_done(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM chapters WHERE book_gid = 271"
        ).fetchone()["n"]
    )


# ------------------------------------------------------------ the supervisor

Work = Callable[[sqlite3.Connection, Claim, str, int], Child]


class FakeChildren:
    """The child process, minus the process.

    Each call claims exactly as the real one does — the claim is the thing
    being tested, so it has to be the real function — and then does whatever
    the test's ``work`` wants with the job it got, including nothing at all,
    which is what a box that lost power looks like from up here.
    """

    def __init__(self, conn: sqlite3.Connection, work: Work) -> None:
        self._conn = conn
        self._work = work
        self.taken: list[int] = []
        self.pid = 4000

    def __call__(self) -> Child:
        self.pid += 1
        lease = f"lease-{self.pid}"
        job = claim(self._conn, lease=lease, pid=self.pid)
        if job is None:
            return Child(pid=self.pid, code=0)
        self.taken.append(job.gid)
        return self._work(self._conn, job, lease, self.pid)


def renders(conn: sqlite3.Connection, job: Claim, lease: str, pid: int) -> Child:
    """A child that does its job, and proves it had the slot to itself."""
    # Asserted from inside the only window where one-at-a-time could go wrong:
    # while this child holds the claim, nothing else can take one.
    assert claim(conn, lease="interloper", pid=1) is None
    finish(conn, job.id, lease=lease, state="done")
    return Child(pid=pid, code=0)


def vanishes(conn: sqlite3.Connection, job: Claim, lease: str, pid: int) -> Child:
    """A box that lost power: the row is left exactly as the claim wrote it."""
    age_beat(conn, job.id, 700)
    return Child(pid=pid, code=0)


def crashes(conn: sqlite3.Connection, job: Claim, lease: str, pid: int) -> Child:
    """A child that died with the row still in its hands."""
    return Child(pid=pid, code=1)


def killed(conn: sqlite3.Connection, job: Claim, lease: str, pid: int) -> Child:
    """A child the kernel took: `wait` reports a negative code, not an exit."""
    return Child(pid=pid, code=-9)


class Rounds:
    """A ``stopping`` for a supervisor that must not run all night."""

    def __init__(self, n: int) -> None:
        self.left = n

    def __call__(self) -> bool:
        self.left -= 1
        return self.left < 0


def test_the_line_is_drained_one_book_at_a_time_in_the_order_it_was_asked(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    for gid in (271, 120, 2701):
        submit(conn, gid)
    children = FakeChildren(conn, renders)

    supervise(cfg(tmp_path), conn, spawn=children, stopping=Rounds(4), idle_s=0)

    assert children.taken == [271, 120, 2701]
    assert [
        r["state"] for r in conn.execute("SELECT state FROM queue ORDER BY id")
    ] == [
        "done",
        "done",
        "done",
    ]


def test_a_child_that_died_without_saying_why_fails_the_job(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """And is not tried again, which is the whole of the retry policy.

    A render that was interrupted is picked up again — a deploy and a reboot
    are somnia's business, not the listener's — but a child that got as far as
    running and then died is a book that breaks something, and a queue that
    spends the night failing the same book is worse than one that stops and
    says why.
    """
    job = submit(conn, 271)
    children = FakeChildren(conn, crashes)

    supervise(cfg(tmp_path), conn, spawn=children, stopping=Rounds(3), idle_s=0)

    row = row_of(conn, job.id)
    assert row["state"] == "failed"
    assert "exit code 1" in row["error"]
    assert (row["lease"], row["pid"]) == ("", 0)
    assert children.taken == [271]


def test_a_book_that_keeps_being_interrupted_is_eventually_given_up_on(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Three power cuts in a row are not a power cut.

    Nobody survives to write anything down when the box goes, so this is the
    one thing standing between somnia and a book retried until morning.
    """
    job = submit(conn, 271)
    children = FakeChildren(conn, vanishes)

    supervise(cfg(tmp_path), conn, spawn=children, stopping=Rounds(6), idle_s=0)

    assert children.taken == [271, 271, 271]
    row = row_of(conn, job.id)
    assert row["state"] == "failed"
    assert str(row["error"]).startswith("Interrupted 3 times")


def test_a_book_left_claiming_it_was_rendering_is_freed_at_startup(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """The live VPS, exactly, on the first morning the worker is installed.

    Every render an agent ever started was shot dead by the next deploy, and
    until now nothing has ever put those rows right.
    """
    with conn:
        conn.execute(
            "INSERT INTO books (gid, title, voice, status)"
            " VALUES (271, 'Black Beauty', 'af_heart', 'rendering')"
        )

    supervise(
        cfg(tmp_path), conn, spawn=FakeChildren(conn, renders), stopping=Rounds(0)
    )

    assert book_row(conn)["status"] == "pending"


# ------------------------------------------------------------------ one book


def seed_a_night(conn: sqlite3.Connection) -> None:
    """A book somebody is part-way through, whose render died on them."""
    with conn:
        conn.execute(
            "INSERT INTO books (gid, title, voice, status, position_ms,"
            " position_seq, position_at, heard_to_ms)"
            " VALUES (271, 'Black Beauty', 'af_heart', 'pending', 4000, 3,"
            " '2026-08-05 23:40:00', 3500)"
        )


def night(conn: sqlite3.Connection) -> list[Any]:
    row = book_row(conn)
    return [
        row[c] for c in ("position_ms", "position_seq", "position_at", "heard_to_ms")
    ]


def a_book_with_room_to_stop() -> Book:
    """Black Beauty again, but two paragraphs a chapter rather than one.

    A stop is asked for between sentences, and the fixture book has exactly one
    sentence per chapter — so anything that presses a button while a sentence
    is rendering is only noticed after that chapter has already finished, and a
    stop could never land anywhere but a chapter boundary it was going to reach
    anyway. Two sentences give the press somewhere to land *inside* a chapter,
    which is the case worth asserting: that chapter leaves no m4a, no chunks
    and no row at all.
    """
    return Book(
        gid=271,
        title="Black Beauty",
        authors="Sewell, Anna",
        chapters=[
            Chapter(
                title=title,
                paragraphs=[f"Something happened in {title}.", "Then more."],
            )
            for title in ("01 My Early Home", "02 The Hunt", "03 My Breaking In")
        ],
    )


class PressesAButton(SilentEngine):
    """An engine that reaches out and presses something mid-render.

    Reading the chapters table rather than counting its own calls, because the
    thing being simulated arrives from outside this process — somebody on a
    phone, or systemd stopping the unit — and the only clock both ends agree
    about is the one in the database.
    """

    def __init__(
        self, conn: sqlite3.Connection, press: Callable[[], object], after: int
    ) -> None:
        self._conn = conn
        self._press = press
        self._after = after

    def render(self, text: str) -> Any:
        if chapters_done(self._conn) >= self._after:
            self._press()
        return super().render(text)


def render(
    conn: sqlite3.Connection,
    tmp_path: Path,
    *,
    engine: Any = None,
    stopping: Callable[[], bool] = never,
) -> Any:
    return render_one(
        cfg(tmp_path),
        conn,
        engine=cast(TTSEngine, engine or SilentEngine()),
        embedder=cast(Embedder, FakeEmbedder()),
        stopping=stopping,
        # Beat on every sentence. The real child asks the database once every
        # ten seconds, which over a book is often enough and here would be
        # never — a whole render is a few hundred microseconds of silence.
        beat_every_s=0,
    )


@pytest.mark.usefixtures("gutenberg")
def test_a_render_that_finishes_leaves_the_book_done_and_the_night_alone(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    seed_a_night(conn)
    job = submit(conn, 271)
    before = night(conn)

    rendered = render(conn, tmp_path)

    assert rendered is not None
    assert (rendered.id, rendered.gid, rendered.state) == (job.id, 271, "done")
    assert row_of(conn, job.id)["state"] == "done"
    assert book_row(conn)["status"] == "done"
    assert chapters_done(conn) == 3
    assert night(conn) == before


def test_a_cancel_stops_at_a_chapter_boundary_and_records_that_somebody_did_it(
    gutenberg: Fetched, conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Everything already rendered stays playable, and nothing is half written.

    Which is what makes the twenty seconds a cancel takes worth paying: a stop
    between sentences leaves no m4a, no chunks and no chapters row for the
    chapter it was in the middle of.
    """
    gutenberg.book = a_book_with_room_to_stop()
    job = submit(conn, 271)

    rendered = render(
        conn, tmp_path, engine=PressesAButton(conn, lambda: stop(conn, job.id), 2)
    )

    assert rendered is not None
    assert rendered.state == "cancelled"
    assert row_of(conn, job.id)["state"] == "cancelled"
    # Not 'rendering', which would be a claim that work is going on, and not
    # 'done', which would be a claim the book is all there.
    assert book_row(conn)["status"] == "pending"
    assert chapters_done(conn) == 2
    assert sorted(
        r["chapter_idx"]
        for r in conn.execute("SELECT DISTINCT chapter_idx FROM chunks")
    ) == [0, 1]
    assert len(list((tmp_path / "library").rglob("*.m4a"))) == 2


def test_a_shutdown_puts_the_book_back_in_the_line(
    gutenberg: Fetched, conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """A deploy is not somebody changing their mind about the book.

    So it goes back to waiting rather than to cancelled, keeping the attempt
    against it, and whatever starts next picks it up at the chapter after the
    last one that finished.
    """
    gutenberg.book = a_book_with_room_to_stop()
    job = submit(conn, 271)
    asked: list[bool] = []

    rendered = render(
        conn,
        tmp_path,
        engine=PressesAButton(conn, lambda: asked.append(True), 1),
        stopping=lambda: bool(asked),
    )

    assert rendered is not None
    assert rendered.state == "queued"
    row = row_of(conn, job.id)
    assert (row["state"], row["lease"], row["beat_at"]) == ("queued", "", None)
    assert row["attempts"] == 1
    assert book_row(conn)["status"] == "pending"
    assert chapters_done(conn) == 1


def test_a_render_whose_lease_was_taken_away_stops_writing_at_once(
    gutenberg: Fetched, conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """The row belongs to whoever holds it now, and this process is not it.

    A beat that answers nothing is the only way a child ever finds this out,
    and the only correct response is to stop — writing 'cancelled' over
    somebody else's render would be the one thing the lease exists to prevent.
    """
    gutenberg.book = a_book_with_room_to_stop()
    job = submit(conn, 271)

    def steal() -> None:
        with conn:
            conn.execute("UPDATE queue SET lease = 'b' WHERE id = ?", (job.id,))

    rendered = render(conn, tmp_path, engine=PressesAButton(conn, steal, 1))

    assert rendered is not None
    assert rendered.state == "lost"
    row = row_of(conn, job.id)
    assert (row["state"], row["lease"]) == ("rendering", "b")


def test_nothing_is_claimed_or_built_while_another_render_is_alive(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """The second half of that sentence is the assertion that costs nothing.

    No engine and no embedder are passed here, so building them would mean
    importing kokoro and sentence_transformers, neither of which is installed
    in this environment — the ImportError that never happens is the proof that
    the expensive things are built after the claim rather than before it.
    """
    submit(conn, 271)
    claim(conn, lease="held-by-somebody-else", pid=1)
    submit(conn, 120)

    assert render_one(cfg(tmp_path), conn, stopping=never) is None


def test_a_book_gutenberg_will_not_give_us_says_which_kind_of_no_it_was(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch_book raises the same RuntimeError for both, so the child asks.

    "There is no such book" and "there is a book but no HTML edition" want
    different things done about them, and the local catalog is what tells them
    apart without another round trip to Gutenberg.
    """

    def refuse(gid: int, url: str | None = None) -> Any:
        raise RuntimeError(f"could not fetch Gutenberg book {gid}")

    monkeypatch.setattr(ingest, "fetch_book", refuse)

    known = submit(conn, 271)
    assert render(conn, tmp_path).state == "failed"
    assert "no HTML edition" in row_of(conn, known.id)["error"]

    unknown = submit(conn, 999999)
    assert render(conn, tmp_path).state == "failed"
    error = str(row_of(conn, unknown.id)["error"])
    assert "There is no Gutenberg book 999999" in error
    assert "catalog-update" in error


@pytest.mark.usefixtures("gutenberg")
def test_a_render_that_breaks_says_so_in_one_sentence_and_keeps_the_traceback(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sentence is for a phone in the dark; the traceback is for the journal.

    The child does not re-raise, so a failure it recorded exits zero — which is
    what leaves a non-zero exit meaning only one thing: a child that died
    before it could say anything at all.
    """

    def explode(*args: object, **kwargs: object) -> Any:
        raise MemoryError("the box ran out")

    monkeypatch.setattr(ingest, "add_chunks", explode)
    job = submit(conn, 271)

    rendered = render(conn, tmp_path)

    assert rendered is not None
    assert rendered.state == "failed"
    error = str(row_of(conn, job.id)["error"])
    assert "MemoryError" in error
    assert "the box ran out" in error
    assert book_row(conn)["status"] == "pending"


# ------------------------------------------------------------ which voice reads it


class NamesItsVoice(SilentEngine):
    """Silence again, but built the way the real engine is: from a voice name."""

    def __init__(self, voice: str = "af_heart", lang_code: str = "") -> None:
        self.voice = voice


@pytest.mark.usefixtures("gutenberg")
def test_the_render_is_built_with_the_voice_the_request_asked_for(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one line the injected-engine tests cannot reach, and the whole point.

    ``render_one`` imports KokoroEngine inside the function — so that the
    supervisor holds none of torch — which is also what makes it substitutable
    here. Everything else in this module hands ``render_one`` an engine and so
    never exercises the choice of one.
    """
    from somnia import tts

    monkeypatch.setattr(tts, "KokoroEngine", NamesItsVoice)
    submit(conn, 271, "bm_george")

    rendered = render_one(
        cfg(tmp_path),
        conn,
        embedder=cast(Embedder, FakeEmbedder()),
        stopping=never,
        beat_every_s=0,
    )

    assert rendered is not None and rendered.state == "done"
    # And it is written down as what read the book, because every timestamp in
    # the row above was measured in this voice and a re-render in another one
    # would move all of them.
    voice = conn.execute("SELECT voice FROM books WHERE gid = 271").fetchone()["voice"]
    assert voice == "bm_george"


@pytest.mark.usefixtures("gutenberg")
def test_a_request_that_named_no_voice_gets_the_renderers_own(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what the agent submits: nobody picks a voice out loud at 2am."""
    from somnia import tts

    monkeypatch.setattr(tts, "KokoroEngine", NamesItsVoice)
    settings = cfg(tmp_path)
    settings.voice = "af_bella"
    submit(conn, 271)

    render_one(
        settings,
        conn,
        embedder=cast(Embedder, FakeEmbedder()),
        stopping=never,
        beat_every_s=0,
    )

    voice = conn.execute("SELECT voice FROM books WHERE gid = 271").fetchone()["voice"]
    assert voice == "af_bella"


def test_a_renderer_the_kernel_killed_says_which_signal_and_what_it_means(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Which on this box is the OOM killer, and is the likeliest way a render dies.

    A negative code from `wait` is a signal rather than an exit, and the
    supervisor has a sentence for exactly that — it names the signal and says
    what it usually means, because "the renderer was killed by signal 9" on its
    own tells somebody at 2am nothing they can act on. Nothing ran that branch.
    """
    job = submit(conn, 271)
    children = FakeChildren(conn, killed)

    supervise(cfg(tmp_path), conn, spawn=children, stopping=Rounds(2), idle_s=0)

    row = row_of(conn, job.id)
    assert row["state"] == "failed"
    error = str(row["error"])
    assert "signal 9" in error
    assert "running out of memory" in error
