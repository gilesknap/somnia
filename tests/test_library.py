"""Taking a book away, which is the one thing in somnia that cannot be undone.

A render can be asked for again; nothing brings back the hours of audio this
unlinks. So these are mostly tests of the refusals and of the edges of the
delete rather than of the happy path — what gets left behind, and what does not
get taken away with it.

The tone book is the fixture for all of it because it is the only one that is
really on disk: three m4a files in `library_dir/<author>/<title>`, with rows in
every table that knows about a book. A delete tested against rows alone would
pass while leaving the audio exactly where it was.
"""

import sqlite3
from pathlib import Path

from conftest import ToneBook
from somnia.library import remove_book
from tone_book import CHAPTERS, GID


def queued(conn: sqlite3.Connection, state: str, gid: int = GID) -> int:
    """A queue row for the book, in whatever state the test is about."""
    with conn:
        row = conn.execute(
            "INSERT INTO queue (gid, title, state) VALUES (?, 'Three Tones', ?)"
            " RETURNING id",
            (gid, state),
        ).fetchone()
    return int(row["id"])


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    """How many rows each of the four tables holds about the tone book.

    All four in one dict so that a failure names the place that was missed
    rather than the first place that was missed.
    """
    return {
        "books": conn.execute(
            "SELECT COUNT(*) AS n FROM books WHERE gid = ?", (GID,)
        ).fetchone()["n"],
        "chapters": conn.execute(
            "SELECT COUNT(*) AS n FROM chapters WHERE book_gid = ?", (GID,)
        ).fetchone()["n"],
        "chunks": conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE book_gid = ?", (GID,)
        ).fetchone()["n"],
        "queue": conn.execute(
            "SELECT COUNT(*) AS n FROM queue WHERE gid = ?", (GID,)
        ).fetchone()["n"],
    }


def vectors(conn: sqlite3.Connection) -> int:
    """How many rows the vector index holds, whoever they belong to.

    Not filtered by book, because it cannot be: ``vec_chunks`` has no book
    column at all — its rowid is ``chunks.id`` and that is the only thing tying
    a vector to a book. Which is exactly why deleting the chunks first would
    orphan every one of them in silence, and why this counts the whole table.
    """
    return int(conn.execute("SELECT COUNT(*) AS n FROM vec_chunks").fetchone()["n"])


def test_a_book_being_rendered_is_not_deleted_but_is_told_how_to_stop_it(
    tone_book: ToneBook,
) -> None:
    """The refusal that is about timing rather than about the book.

    A worker half way through chapter nineteen is about to write files into the
    folder this would be emptying, so the answer is to stand aside and say
    which job to stop. The job id is in the sentence because stopping is keyed
    on the job and not on the book, so the number needed next is not the one
    that was just typed.
    """
    job_id = queued(tone_book.conn, "rendering")

    removed = remove_book(tone_book.cfg, tone_book.conn, GID)

    assert not removed.ok
    # Found, and therefore a refusal rather than a 404: the book is here and
    # is staying.
    assert removed.found
    assert "is being rendered" in removed.said
    assert f"job {job_id}" in removed.said
    assert counts(tone_book.conn)["books"] == 1
    assert (tone_book.book_dir / CHAPTERS[0].file_name).exists()


def test_a_book_waiting_in_the_line_is_refused_too_so_it_cannot_come_back(
    tone_book: ToneBook,
) -> None:
    """A queued row is a book that is about to be rendered again.

    Deleting the rows and leaving the row that asks for them would take the
    book away and then bring it back hours later, which is the one outcome
    nobody could have meant by pressing delete.
    """
    job_id = queued(tone_book.conn, "queued")

    removed = remove_book(tone_book.cfg, tone_book.conn, GID)

    assert not removed.ok
    assert "waiting to be rendered" in removed.said
    assert f"job {job_id}" in removed.said
    assert counts(tone_book.conn)["books"] == 1


def test_a_chapter_filed_outside_the_library_stops_the_whole_delete(
    tone_book: ToneBook, tmp_path: Path
) -> None:
    """One bad row leaves the book exactly as it was, not half taken away.

    A path outside `library_dir` means the database has been carried between
    machines, or somebody has been editing rows by hand, and neither is a state
    to start unlinking files in. Checked before anything at all is deleted, so
    the rows are still there to be looked at afterwards.
    """
    stranger = tmp_path / "not-the-library" / "someone elses.m4a"
    stranger.parent.mkdir()
    stranger.write_bytes(b"not ours")
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE chapters SET audio_file = ? WHERE book_gid = ? AND idx = 1",
            (str(stranger), GID),
        )

    removed = remove_book(tone_book.cfg, tone_book.conn, GID)

    assert not removed.ok
    assert removed.found
    assert "outside the library" in removed.said
    # The file that was never somnia's is the point of the whole rule.
    assert stranger.exists()
    still_here = {"books": 1, "chapters": 3, "chunks": 6, "queue": 0}
    assert counts(tone_book.conn) == still_here
    assert (tone_book.book_dir / CHAPTERS[0].file_name).exists()


def test_a_book_that_is_not_here_is_said_to_be_missing_rather_than_removed(
    tone_book: ToneBook,
) -> None:
    """Not found is its own answer, and it is what the route turns into a 404.

    The tone book is still here afterwards, which is the half of this worth
    asserting: a delete asked about the wrong id must not be a delete of
    whatever it found instead.
    """
    removed = remove_book(tone_book.cfg, tone_book.conn, 424_242)

    assert not removed.ok
    assert not removed.found
    assert "424242" in removed.said
    assert counts(tone_book.conn)["books"] == 1


def test_a_delete_empties_all_six_places_a_book_lives_in(
    tone_book: ToneBook,
) -> None:
    """The whole of it, in one test, because half a delete is worse than none.

    The six are the books row, the chapters, the chunks, the vectors those
    chunks own, every queue row the book ever had, and the audio — with the
    joined streams under `data_dir`, which are a second whole copy of the book
    and would otherwise go on being served to a phone that already had one
    open.

    The queue rows here are terminal ones on purpose. `queue.view` never shows
    them, so a delete that left them behind would leave something nothing in
    somnia can see, for a book that no longer exists.
    """
    queued(tone_book.conn, "failed")
    queued(tone_book.conn, "cancelled")
    streams = tone_book.cfg.data_dir / "streams" / str(GID)
    streams.mkdir(parents=True)
    (streams / "3.m4a").write_bytes(b"the whole book, joined")

    removed = remove_book(tone_book.cfg, tone_book.conn, GID)

    assert removed.ok
    assert "Three Tones" in removed.said
    nothing = {"books": 0, "chapters": 0, "chunks": 0, "queue": 0}
    assert counts(tone_book.conn) == nothing
    assert vectors(tone_book.conn) == 0
    assert not tone_book.book_dir.exists()
    assert not streams.exists()


def test_the_folders_a_book_leaves_behind_go_with_it(tone_book: ToneBook) -> None:
    """Both of them: the book's folder and the author's, and not the library.

    A library with an empty folder for every book ever deleted is a library
    that has to be tidied by hand, and the folder names are the only thing
    anything walking the disk has to go on.
    """
    assert remove_book(tone_book.cfg, tone_book.conn, GID).ok

    assert not tone_book.book_dir.exists()
    assert not tone_book.book_dir.parent.exists()
    # An empty library is still the library, and something else writes there.
    assert tone_book.cfg.library_dir.is_dir()


def test_a_folder_with_anything_else_in_it_is_left_alone(
    tone_book: ToneBook,
) -> None:
    """The author has another book, and a cover somebody dropped in beside it.

    ``rmdir`` refusing a folder that is not empty is the guard rather than a
    thing to work around: neither of these is somnia's to throw away, and a
    delete that reached one folder further up would take the other book's audio
    with it.
    """
    other_book = tone_book.book_dir.parent / "Another Book"
    other_book.mkdir()
    (other_book / "001 - Chapter One.m4a").write_bytes(b"somebody elses chapter")
    cover = tone_book.book_dir / "cover.jpg"
    cover.write_bytes(b"a picture nobody asked somnia about")

    assert remove_book(tone_book.cfg, tone_book.conn, GID).ok

    # The chapters went; the picture stopped the folder going with them.
    assert cover.exists()
    assert not (tone_book.book_dir / CHAPTERS[0].file_name).exists()
    assert (other_book / "001 - Chapter One.m4a").exists()


def test_a_chapter_whose_file_is_already_gone_is_nothing_to_delete(
    tone_book: ToneBook,
) -> None:
    """A missing file is an absence, not a reason to stop half way.

    This is where a delete and the audio route part company. Serving treats a
    file that is not there as nothing to hand back; deleting has already
    committed the rows by the time it walks the disk, and stopping at the first
    gap would leave the two remaining chapters orphaned for good.
    """
    (tone_book.book_dir / CHAPTERS[1].file_name).unlink()

    removed = remove_book(tone_book.cfg, tone_book.conn, GID)

    assert removed.ok
    assert not tone_book.book_dir.exists()
