"""The ingest queue: what may be submitted, who gets to render, and what died.

Nothing here renders anything. The whole point of the queue is that the state
machine can be reasoned about without Kokoro in the room, so every test is a few
UPDATEs against a real sqlite file and the clock is moved by writing timestamps
rather than by sleeping.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from somnia.catalog import update_catalog
from somnia.db import connect
from somnia.queue import (
    MAX_ATTEMPTS,
    Beat,
    beat,
    claim,
    finish,
    note_chapter,
    reconcile,
    requeue,
    stop,
    submit,
    view,
)

CSV = """\
Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves
271,Text,2006-01-25,Black Beauty,en,"Sewell, Anna, 1820-1878",Horses,PZ,
120,Text,2006-01-25,Treasure Island,en,"Stevenson, Robert Louis",Pirates,PZ,
2701,Text,2001-07-01,Moby Dick,en,"Melville, Herman",Whaling,PZ,
"""


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = connect(tmp_path / "queue.db")
    try:
        update_catalog(c, csv_text=CSV)
        yield c
    finally:
        c.close()


def add_book_row(conn: sqlite3.Connection, gid: int, status: str) -> None:
    """A books row of the shape a render leaves behind."""
    with conn:
        conn.execute(
            "INSERT INTO books (gid, title, voice, status)"
            " VALUES (?, ?, 'af_heart', ?)",
            (gid, f"Book {gid}", status),
        )


def age_beat(conn: sqlite3.Connection, job_id: int, seconds: int) -> None:
    """Move a job's heartbeat into the past, which is how time passes here."""
    with conn:
        conn.execute(
            "UPDATE queue SET beat_at = datetime('now', ?) WHERE id = ?",
            (f"-{seconds} seconds", job_id),
        )


def state_of(conn: sqlite3.Connection, job_id: int) -> str:
    row = conn.execute("SELECT state FROM queue WHERE id = ?", (job_id,)).fetchone()
    return str(row["state"])


def finish_it(conn: sqlite3.Connection, job_id: int) -> None:
    """End a job the way a renderer would, without there being a renderer."""
    lease = "test-lease"
    with conn:
        conn.execute("UPDATE queue SET lease = ? WHERE id = ?", (lease, job_id))
    finish(conn, job_id, lease=lease, state="done")


# ------------------------------------------------------------------- submitting


def test_submit_takes_the_name_from_the_catalog(conn: sqlite3.Connection) -> None:
    """So a queued row reads as a book rather than as a number.

    This is also the guard on the string cast. The catalog is an FTS5 table, so
    its gid column holds the text '271'; asked for the integer 271 sqlite
    compares an integer against a string, finds them unequal by type, and
    silently answers nothing. That is the same near-miss that renders a book
    into a folder called 'Unknown Author', and it has no symptom until somebody
    reads the queue at 2am and sees three numbers.
    """
    result = submit(conn, 271)
    assert result.ok
    row = conn.execute("SELECT * FROM queue WHERE id = ?", (result.id,)).fetchone()
    assert row["title"] == "Black Beauty"
    assert "Sewell" in row["authors"]
    assert "Black Beauty" in result.said


def test_submit_of_a_book_the_catalog_has_never_heard_of_is_accepted(
    conn: sqlite3.Connection,
) -> None:
    """Because the only way to find out is to fetch it, and that is minutes away.

    A control that thinks for three seconds before answering reads as broken,
    so the submit is a database write and nothing else. A gid that does not
    exist fails later, in the worker, with a sentence.
    """
    result = submit(conn, 999999)
    assert result.ok
    row = conn.execute("SELECT * FROM queue WHERE id = ?", (result.id,)).fetchone()
    assert (row["title"], row["authors"]) == ("", "")
    # Nothing to call it by, so the sentence says the number out loud.
    assert "book 999999" in result.said


def test_a_second_submit_of_a_waiting_book_is_refused(conn: sqlite3.Connection) -> None:
    first = submit(conn, 271)
    second = submit(conn, 271)
    assert first.ok
    assert not second.ok
    assert "Black Beauty" in second.said
    assert conn.execute("SELECT COUNT(*) AS n FROM queue").fetchone()["n"] == 1


def test_the_database_itself_refuses_a_second_live_row(
    conn: sqlite3.Connection,
) -> None:
    """The check in submit is a courtesy; this is the guarantee.

    Two presses a millisecond apart would both read an empty queue and both
    decide to insert. The partial unique index means the loser of that race gets
    an IntegrityError instead of a second render.
    """
    submit(conn, 271)
    with pytest.raises(sqlite3.IntegrityError), conn:
        conn.execute("INSERT INTO queue (gid) VALUES (271)")


def test_a_finished_render_can_be_left_out_of_the_index(
    conn: sqlite3.Connection,
) -> None:
    """A row that has ended is history, and history does not hold the slot."""
    result = submit(conn, 271)
    finish_it(conn, result.id)
    again = submit(conn, 271)
    assert again.ok


def test_submit_of_a_book_somnia_already_has_is_refused(
    conn: sqlite3.Connection,
) -> None:
    add_book_row(conn, 271, "done")
    result = submit(conn, 271)
    assert not result.ok
    assert conn.execute("SELECT COUNT(*) AS n FROM queue").fetchone()["n"] == 0


def test_submit_of_a_render_that_died_is_accepted(conn: sqlite3.Connection) -> None:
    """This is the retry that was impossible before the queue existed.

    'pending' is what a render that stopped, failed or was killed leaves behind.
    Refusing it — which is what add_book did, for every status there was — meant
    a book that died at chapter three could never be asked for again.
    """
    add_book_row(conn, 271, "pending")
    assert submit(conn, 271).ok


def test_a_book_stuck_on_rendering_can_still_be_asked_for(
    conn: sqlite3.Connection,
) -> None:
    """Every book on the VPS that was killed by a deploy looks like this."""
    add_book_row(conn, 271, "rendering")
    assert submit(conn, 271).ok


def test_place_is_the_rank_among_the_books_that_are_waiting(
    conn: sqlite3.Connection,
) -> None:
    submit(conn, 271)
    submit(conn, 120)
    submit(conn, 2701)
    assert [(row.gid, row.place) for row in view(conn)] == [
        (271, 1),
        (120, 2),
        (2701, 3),
    ]


def test_the_book_that_is_rendering_holds_no_place_in_the_line(
    conn: sqlite3.Connection,
) -> None:
    first = submit(conn, 271)
    submit(conn, 120)
    claim(conn, lease="a", pid=1)
    rows = {row.id: row for row in view(conn)}
    assert rows[first.id].state == "rendering"
    assert rows[first.id].place == 0
    # The one still waiting is next, not second: nothing is ahead of it in the
    # line, because the thing ahead of it has left the line.
    assert [row.place for row in view(conn) if row.state == "queued"] == [1]


# ---------------------------------------------------------------------- stopping


def test_stop_of_a_waiting_book_takes_it_out_at_once(conn: sqlite3.Connection) -> None:
    result = submit(conn, 271)
    stopped = stop(conn, result.id)
    assert stopped.ok
    assert stopped.state == "cancelled"
    assert state_of(conn, result.id) == "cancelled"


def test_stop_of_a_running_render_raises_the_flag_and_leaves_it_running(
    conn: sqlite3.Connection,
) -> None:
    """Nothing here reaches into the renderer; it asks, between sentences.

    So the state stays 'rendering' until the child says otherwise. Anything
    that wrote 'cancelled' here would be claiming a process had stopped on the
    strength of having asked it to.
    """
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    stopped = stop(conn, result.id)
    assert stopped.ok
    assert stopped.state == "rendering"
    row = conn.execute("SELECT * FROM queue WHERE id = ?", (result.id,)).fetchone()
    assert (row["state"], row["cancel"]) == ("rendering", 1)
    assert beat(conn, result.id, lease="a") is not None
    assert view(conn)[0].stopping


def test_stop_of_a_render_that_has_finished_is_refused(
    conn: sqlite3.Connection,
) -> None:
    result = submit(conn, 271)
    finish_it(conn, result.id)
    stopped = stop(conn, result.id)
    assert not stopped.ok
    assert stopped.state == "done"
    assert "Black Beauty" in stopped.said


def test_stop_of_a_job_that_was_never_there(conn: sqlite3.Connection) -> None:
    """An empty state is how the caller tells "no such job" from "too late"."""
    stopped = stop(conn, 42)
    assert (stopped.ok, stopped.state) == (False, "")
    assert "42" in stopped.said


# ---------------------------------------------------------- claiming and beating


def test_only_one_claimant_can_win(conn: sqlite3.Connection) -> None:
    submit(conn, 271)
    submit(conn, 120)
    first = claim(conn, lease="a", pid=1)
    second = claim(conn, lease="b", pid=2)
    assert first is not None
    assert first.gid == 271
    assert second is None


def test_a_claim_waits_while_a_render_is_still_beating(
    conn: sqlite3.Connection,
) -> None:
    submit(conn, 271)
    submit(conn, 120)
    claim(conn, lease="a", pid=1)
    beat(conn, 1, lease="a")
    assert claim(conn, lease="b", pid=2) is None


def test_a_claim_takes_over_from_a_render_that_stopped_beating(
    conn: sqlite3.Connection,
) -> None:
    """A lease is only as good as its last heartbeat.

    Without this a box that lost power mid-render would hold the one slot there
    is for ever, and every book submitted afterwards would sit in the queue
    behind a process that no longer exists.
    """
    submit(conn, 271)
    second = submit(conn, 120)
    claim(conn, lease="a", pid=1)
    age_beat(conn, 1, 700)
    taken = claim(conn, lease="b", pid=2)
    assert taken is not None
    assert taken.id == second.id


def test_a_beat_from_a_lease_that_was_taken_away_answers_nothing(
    conn: sqlite3.Connection,
) -> None:
    """Which is the only way a child finds out it is no longer the renderer."""
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    with conn:
        conn.execute("UPDATE queue SET lease = 'b' WHERE id = ?", (result.id,))
    assert beat(conn, result.id, lease="a") is None


def test_a_beat_carries_the_cancel_flag_back(conn: sqlite3.Connection) -> None:
    """One statement proves the lease, renews it, and answers the question.

    This is the whole of the cancel channel: no signal, no pipe, nothing to
    connect to a process that may be on the other side of a reboot.
    """
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    assert beat(conn, result.id, lease="a") == Beat(cancel=False)
    stop(conn, result.id)
    assert beat(conn, result.id, lease="a") == Beat(cancel=True)


def test_a_beat_with_no_lease_at_all_touches_nothing(conn: sqlite3.Connection) -> None:
    """An empty lease is what a finished row holds, and it must match nothing.

    ``WHERE lease = ''`` is a perfectly good query that would beat every row
    nobody owns back into life.
    """
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    finish(conn, result.id, lease="a", state="done")
    assert beat(conn, result.id, lease="") is None
    assert state_of(conn, result.id) == "done"


def test_a_chapter_moves_its_own_clock(conn: sqlite3.Connection) -> None:
    """A second hand, so a long chapter cannot be mistaken for a dead process."""
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    assert (
        conn.execute(
            "SELECT chapter_at FROM queue WHERE id = ?", (result.id,)
        ).fetchone()["chapter_at"]
        is None
    )
    note_chapter(conn, result.id, lease="a")
    assert (
        conn.execute(
            "SELECT chapter_at FROM queue WHERE id = ?", (result.id,)
        ).fetchone()["chapter_at"]
        is not None
    )


def test_finish_records_why_and_gives_the_slot_back(conn: sqlite3.Connection) -> None:
    result = submit(conn, 271)
    submit(conn, 120)
    claim(conn, lease="a", pid=1)
    finish(conn, result.id, lease="a", state="failed", error="no HTML edition")
    row = conn.execute("SELECT * FROM queue WHERE id = ?", (result.id,)).fetchone()
    assert (row["state"], row["error"], row["lease"]) == (
        "failed",
        "no HTML edition",
        "",
    )
    assert row["ended_at"] is not None
    assert claim(conn, lease="b", pid=2) is not None


def test_requeue_puts_an_interrupted_book_back_at_its_own_place(
    conn: sqlite3.Connection,
) -> None:
    """A worker being restarted is not somebody changing their mind.

    Nobody stopped wanting the book, so it goes back to waiting rather than to
    cancelled — and it keeps the attempt against it, which is what eventually
    stops somnia trying a book that cannot be rendered.
    """
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    requeue(conn, result.id, lease="a")
    row = conn.execute("SELECT * FROM queue WHERE id = ?", (result.id,)).fetchone()
    assert (row["state"], row["lease"], row["beat_at"]) == ("queued", "", None)
    assert row["attempts"] == 1
    assert claim(conn, lease="b", pid=2) is not None


# ------------------------------------------------------------------ reconciling


def test_reconcile_puts_a_render_that_stopped_beating_back_in_the_queue(
    conn: sqlite3.Connection,
) -> None:
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    age_beat(conn, result.id, 700)
    counts = reconcile(conn)
    assert counts.requeued == 1
    assert state_of(conn, result.id) == "queued"


def test_reconcile_leaves_a_render_that_is_still_beating_alone(
    conn: sqlite3.Connection,
) -> None:
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    reconcile(conn)
    assert state_of(conn, result.id) == "rendering"


def test_reconcile_gives_up_on_a_book_that_keeps_dying(
    conn: sqlite3.Connection,
) -> None:
    """A queue that spends the night failing the same book is worse than one
    that stops and says why."""
    result = submit(conn, 271)
    for _ in range(MAX_ATTEMPTS):
        claim(conn, lease="a", pid=1)
        age_beat(conn, result.id, 700)
        reconcile(conn)
    row = conn.execute("SELECT * FROM queue WHERE id = ?", (result.id,)).fetchone()
    assert row["state"] == "failed"
    assert str(row["error"]).startswith(f"Interrupted {MAX_ATTEMPTS} times")
    assert row["ended_at"] is not None


def test_reconcile_frees_a_book_left_claiming_it_was_rendering(
    conn: sqlite3.Connection,
) -> None:
    """The live VPS, exactly: books stuck on 'rendering' with no queue at all.

    Every render an agent ever started was shot dead by the next deploy, and
    nothing has ever put those rows right.
    """
    add_book_row(conn, 271, "rendering")
    counts = reconcile(conn)
    assert counts.freed == 1
    status = conn.execute("SELECT status FROM books WHERE gid = 271").fetchone()
    assert status["status"] == "pending"


def test_reconcile_leaves_the_book_that_is_really_rendering_alone(
    conn: sqlite3.Connection,
) -> None:
    add_book_row(conn, 271, "rendering")
    submit(conn, 271)
    claim(conn, lease="a", pid=1)
    reconcile(conn)
    status = conn.execute("SELECT status FROM books WHERE gid = 271").fetchone()
    assert status["status"] == "rendering"


def test_reconcile_does_not_disturb_a_finished_book(conn: sqlite3.Connection) -> None:
    add_book_row(conn, 271, "done")
    reconcile(conn)
    status = conn.execute("SELECT status FROM books WHERE gid = 271").fetchone()
    assert status["status"] == "done"


# -------------------------------------------------------------------- the readout


def test_view_forgets_a_failure_after_a_day(conn: sqlite3.Connection) -> None:
    """After a day a failure is history, and history is in the journal.

    Which is why there is no dismiss control anywhere in this feature: the list
    empties itself, and nothing on it needs pressing to make it go away.
    """
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    finish(conn, result.id, lease="a", state="failed", error="no HTML edition")
    assert [row.state for row in view(conn)] == ["failed"]
    with conn:
        conn.execute(
            "UPDATE queue SET ended_at = datetime('now', '-25 hours') WHERE id = ?",
            (result.id,),
        )
    assert view(conn) == []


def test_view_says_when_a_render_has_gone_quiet(conn: sqlite3.Connection) -> None:
    """Read at read time and stored nowhere, so it is true even when the worker
    unit has been stopped and nothing is left to write it down."""
    result = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    assert view(conn)[0].responding
    age_beat(conn, result.id, 360)
    assert not view(conn)[0].responding


def test_a_book_waiting_its_turn_is_not_reported_as_unresponsive(
    conn: sqlite3.Connection,
) -> None:
    """Nothing has claimed it, so there is nobody to be silent."""
    submit(conn, 271)
    assert view(conn)[0].responding


def test_view_counts_the_chapters_that_exist(conn: sqlite3.Connection) -> None:
    """Never a stored counter: a chapters row exists only once its m4a does."""
    add_book_row(conn, 271, "rendering")
    with conn:
        conn.execute(
            "UPDATE books SET chapters_total = 49, total_ms = 4321 WHERE gid = 271"
        )
        for idx in range(3):
            conn.execute(
                "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
                " audio_file) VALUES (271, ?, 'ch', 0, 1, 'x.m4a')",
                (idx,),
            )
    submit(conn, 271)
    row = view(conn)[0]
    assert (row.chapters_done, row.chapters_total, row.rendered_ms) == (3, 49, 4321)


def test_view_puts_the_render_first_then_the_line_then_the_dead(
    conn: sqlite3.Connection,
) -> None:
    """The order down the page is what is happening, what is next, what went
    wrong — which is the order somebody reads it in."""
    dead = submit(conn, 2701)
    finish_it(conn, dead.id)
    running = submit(conn, 271)
    claim(conn, lease="a", pid=1)
    waiting = submit(conn, 120)
    assert [row.id for row in view(conn)] == [running.id, waiting.id, dead.id]


def test_the_voice_is_written_on_the_request_and_handed_to_whoever_renders_it(
    conn: sqlite3.Connection,
) -> None:
    """The choice is made in front of somebody; the render happens hours later.

    Between the two the book may be picked up by a worker in another process
    with another environment, which is precisely what `somnia add --voice` used
    to lose the race to. The row is the only thing both ends can see.
    """
    submit(conn, 271, "bm_george")
    taken = claim(conn, lease="a-lease", pid=1234)
    assert taken is not None
    assert taken.voice == "bm_george"


def test_a_request_that_names_no_voice_says_so_rather_than_guessing(
    conn: sqlite3.Connection,
) -> None:
    """Empty means "the renderer's own", which is what the agent submits.

    Not the default filled in here: this process cannot see the renderer's
    configuration, and writing af_heart down would make a book rendered on a
    box set to something else disagree with its own row for ever.
    """
    submit(conn, 271)
    taken = claim(conn, lease="a-lease", pid=1234)
    assert taken is not None
    assert taken.voice == ""


def test_the_readout_says_which_voice_a_book_is_being_read_in(
    conn: sqlite3.Connection,
) -> None:
    """So a wrong press is visible in the seconds after it, not six hours later."""
    submit(conn, 271, "bf_emma")
    assert view(conn)[0].voice == "bf_emma"
