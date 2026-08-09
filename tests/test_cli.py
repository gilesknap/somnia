import os
import subprocess
import sys
from pathlib import Path

from somnia import __version__
from somnia.db import connect
from somnia.queue import claim


def somnia(*args: str, env: dict[str, str]) -> str:
    """Run the real command line the way somebody at a terminal would.

    Out of process on purpose: the point of these is that the entry point wires
    itself up, opens a database and prints something, and none of that is
    exercised by calling the functions underneath it.
    """
    cmd = [sys.executable, "-m", "somnia", *args]
    return subprocess.check_output(cmd, env=env).decode()


def test_cli_version():
    cmd = [sys.executable, "-m", "somnia", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__


def test_queue_prints_an_empty_queue_and_then_a_filled_one(tmp_path: Path) -> None:
    """The whole of the queue from a terminal: nothing, add, look, stop.

    The catalog is empty here, which is the interesting half of it — a book with
    no name has to read as "book 120" rather than as a gap where the title
    should be, because a fresh box has no catalog until somebody runs
    `catalog-update` and the queue still has to be legible on it.
    """
    env = {**os.environ, "SOMNIA_DATA_DIR": str(tmp_path / "data")}

    assert "Nothing in the queue" in somnia("queue", env=env)

    added = somnia("queue", "add", "120", env=env)
    assert "book 120" in added
    assert "next to be rendered" in added

    listed = somnia("queue", env=env)
    assert "book 120" in listed
    assert "1st in line" in listed

    stopped = somnia("queue", "stop", "1", env=env)
    assert "taken out of the queue" in stopped

    # It does not vanish. A render somebody stopped is a thing that happened,
    # and the row is the record of it until the readout forgets it a day later.
    after = somnia("queue", env=env)
    assert "cancelled" in after
    assert "1st in line" not in after


def test_add_refuses_while_something_else_is_rendering(tmp_path: Path) -> None:
    """And refuses before importing anything, which is the real assertion.

    Neither kokoro nor sentence-transformers is installed in this environment,
    so an `add` that reached for its engine before finding out whether it had
    the slot would end in an ImportError and a non-zero exit — and this test
    would fail rather than pass. It answers from one guarded UPDATE instead,
    which is why the answer comes in the first second rather than after a
    minute of loading a model in order to say no.
    """
    env = {**os.environ, "SOMNIA_DATA_DIR": str(tmp_path / "data")}
    # Runs the migrations as a side effect, so there is a database to reach
    # into on the next line.
    somnia("queue", "add", "271", env=env)

    conn = connect(tmp_path / "data" / "somnia.db")
    try:
        claim(conn, lease="held-by-the-worker", pid=1)
    finally:
        conn.close()

    out = somnia("add", "120", env=env)

    # It did land in the line — this is one front door, so a book asked for
    # while the renderer is busy waits rather than being turned away — and the
    # sentence says where to go and look at it. "Next to be rendered" is true
    # of it and not a promise about when: the book ahead of it has left the
    # line to be rendered, so nothing is waiting in front of this one.
    assert "book 120 is next to be rendered" in out
    assert "waits its turn" in out
    assert "somnia queue" in out


def test_the_worker_command_runs_and_claims_nothing_from_an_empty_line(
    tmp_path: Path,
) -> None:
    """The argv the supervisor spawns its children with, actually executed.

    `supervise` builds a command line and hands it to Popen, and every test of
    the supervisor stands the child in with a hook — which is right, since a
    real child is a python process and a night of rendering. What none of them
    touch is whether that command line runs at all: a renamed flag, a module
    that no longer has a `__main__`, an import that moved, would all pass the
    suite and fail on the box, once, in the dark.

    Cheap because it stops early: `render_one` returns before the expensive
    imports when the claim finds nothing, so this loads neither kokoro nor
    torch — neither of which is installed here, which is itself the assertion.
    """
    env = {**os.environ, "SOMNIA_DATA_DIR": str(tmp_path / "data")}

    out = somnia("worker", "--once", env=env)

    # Nothing in the line, so nothing was taken and nothing was said about a
    # book. What matters is that it exited zero, which check_output asserts.
    assert "Traceback" not in out


def test_add_says_which_book_it_actually_rendered(tmp_path: Path) -> None:
    """`add` renders the head of the line, which is not always the book asked for.

    Everything the command printed afterwards was said about whatever
    `render_one` claimed, under the id the person typed. Ask for one book while
    another is already waiting and it rendered the other one for six hours and
    reported it as theirs.

    The render here does nothing at all — neither kokoro nor
    sentence-transformers is installed, so a real one could not run — which is
    why the book ahead fails rather than finishing. What is under test is whose
    name is on the sentence, and a failure carries one just as a success does.
    """
    env = {**os.environ, "SOMNIA_DATA_DIR": str(tmp_path / "data")}
    somnia("queue", "add", "271", env=env)

    out = somnia("add", "120", env=env)

    # 271 was ahead in the line, so 271 is what the renderer took.
    assert "book 271, which was ahead of it" in out
    # And the book actually asked for is still waiting, said plainly, because
    # somebody who typed 120 and read six hours of 271 has no other way to know.
    assert "Book 120 is still in the line" in out
