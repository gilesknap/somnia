"""Looking after a book once it has been rendered, and taking one away.

Ingest brings a book in; this is the only place in somnia that takes one back
out. The two are not mirror images of each other. A render can be asked for
again — that is what the queue is for — and a delete cannot, so everything here
is arranged around being sure before anything is unlinked.

A book is spread across six places, and half a delete is worse than none of
one: a ``books`` row with no chapters is a shelf entry that cannot be opened,
and audio with no rows is disk that nothing will ever mention again. So all six
go together, or the whole thing is refused with a sentence saying why.

The refusals are the part worth reading. A render holding the book is not raced
— it is asked about first and the delete stands aside, because a worker
half-way through chapter nineteen is about to write files back into a folder
this was in the middle of emptying. And a chapter row whose path lies outside
``library_dir`` stops the whole delete rather than being skipped: the rows hold
absolute paths, and a path that is not where the library is means somnia has
been carried between machines or somebody has been editing rows by hand.
Neither is a state to start unlinking files in.
"""

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .queue import LIVE, book_name
from .stream import forget_streams

__all__ = [
    "Finished",
    "Removed",
    "finish_book",
    "forget_the_chapters",
    "inside_library",
    "remove_book",
]

logger = logging.getLogger(__name__)


@dataclass
class Removed:
    """What happened to a request to take a book out of the library.

    ``found`` is separate from ``ok`` because the two failures are different
    facts and a caller wants to tell them apart: a book that is not here is a
    page holding an id from a database that has moved on, and a book that was
    refused is here and stayed. It is the same split
    :class:`somnia.queue.Stopped` makes with its ``state``.

    ``said`` is always a whole sentence for a person, whichever of the three it
    is, so the terminal and the page cannot disagree about what just happened.
    """

    ok: bool
    found: bool
    said: str


@dataclass
class Finished:
    """What happened to a request to mark a book finished, or unfinish it.

    The same three fields as :class:`Removed`, and deliberately so: these are
    the verbs of the daytime screen, they are answered by one route each, and a
    page that has to read a different shape for every one of them will read the
    wrong one eventually. There is nothing here that can be refused, so ``ok``
    and ``found`` only ever differ from each other on a gid that is not here —
    which is worth saying in the shape rather than leaving a caller to infer a
    404 from a sentence.
    """

    ok: bool
    found: bool
    said: str


def finish_book(conn: sqlite3.Connection, gid: int, finished: bool = True) -> Finished:
    """Say the reader is done with this book, or that they are not after all.

    One column and nothing else. A finished book is not a deleted one and not a
    hidden one: it keeps its position, its audio and its rows, it still plays
    if it is opened, and the only thing that changes is that the night shelf
    stops offering it — which is the whole point, because a shelf that is
    mostly books already read is a shelf somebody has to go through at 2am to
    find the one they are on.

    Undoable, and that is why it is one function taking a boolean rather than
    two. Marking the wrong book finished is an ordinary mistake to make on a
    list, and the cost of making it has to be one press back; a verb with no
    way back would need asking twice, and asking twice about something this
    small is how a screen becomes tiring to use.

    ``datetime('now')`` is written here, in UTC, the way every other stamp in
    this database is — the column has no default because sqlite will not take a
    non-constant one on a column added to a table that already exists.
    """
    book = conn.execute("SELECT title FROM books WHERE gid = ?", (gid,)).fetchone()
    if book is None:
        return Finished(False, False, f"There is no book {gid} here.")
    name = book_name(str(book["title"]), gid)
    with conn:
        if finished:
            conn.execute(
                "UPDATE books SET finished_at = datetime('now') WHERE gid = ?",
                (gid,),
            )
        else:
            conn.execute("UPDATE books SET finished_at = NULL WHERE gid = ?", (gid,))
    said = f"{name} is finished." if finished else f"{name} is back on the shelf."
    logger.info("book %s (%s) finished=%s", gid, name, finished)
    return Finished(True, True, said)


def inside_library(cfg: Config, audio_file: str, what: str) -> Path | None:
    """A row's path, resolved, if it really is inside the library.

    Containment is checked after resolving, because the row is not beyond
    suspicion either: a symlink in the library, or a database carried over from
    a machine whose SOMNIA_LIBRARY_DIR was somewhere else, can both point
    outside. That case is logged rather than silently dropped — a library that
    has moved should be explicable from the journal, not guessed at.

    One rule with two callers whose stakes point opposite ways. The audio route
    will not *serve* a file from outside the library, and a delete will not
    *unlink* one. Getting it wrong in the first direction hands somebody a file
    they were never offered; in the second it takes away a file that was never
    somnia's. One place to be right about is the whole reason this is a
    function rather than two lines in each of them.
    """
    path = Path(audio_file).resolve()
    # expanduser as well as resolve: Config's default library_dir is the
    # literal "~/library/audiobooks", and only load_config expands it.
    library = cfg.library_dir.expanduser().resolve()
    if not path.is_relative_to(library):
        logger.warning("%s lies outside %s: %s", what, library, path)
        return None
    return path


def forget_the_chapters(conn: sqlite3.Connection, gid: int) -> None:
    """Drop every row a render wrote about a book: chapters, chunks, vectors.

    ``vec_chunks`` first, and the order is the whole of it. It is a ``vec0``
    virtual table whose rowid *is* ``chunks.id``, so the vectors can only be
    found through the chunks that own them — delete the chunks first and the
    subquery matches nothing, the vectors are orphaned, and nothing anywhere
    says so. There is no foreign key to catch it and no error to read.

    No transaction is opened here, deliberately. Both callers have more to do
    in the same breath — a re-render is about to write the new edition, and a
    delete is about to take the ``books`` row with it — and a commit in the
    middle of either would leave a book that exists but has nothing in it.
    """
    conn.execute(
        "DELETE FROM vec_chunks WHERE rowid IN"
        " (SELECT id FROM chunks WHERE book_gid = ?)",
        (gid,),
    )
    conn.execute("DELETE FROM chunks WHERE book_gid = ?", (gid,))
    conn.execute("DELETE FROM chapters WHERE book_gid = ?", (gid,))


def _remove_empty_folders(folder: Path, library: Path) -> None:
    """Take away what a book leaves behind, and stop at the first thing that isn't.

    A book's chapters sit in ``library_dir/<author>/<title>``, so removing one
    can empty two folders and neither of them is somnia's to keep. ``rmdir``
    refuses a folder with anything in it, and that refusal is the guard: an
    author with a second book still on the shelf, or a stray cover somebody
    dropped in beside the audio, ends the walk rather than being cleared out of
    the way. The library itself is never a candidate — an empty library is
    still the library.
    """
    while folder != library and folder.is_relative_to(library):
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent


def remove_book(cfg: Config, conn: sqlite3.Connection, gid: int) -> Removed:
    """Take a book out of somnia altogether: its rows, its audio, its streams.

    The order matters twice. The rows go in one transaction and the files only
    afterwards, so the way this can be interrupted is m4a files nobody has a
    row for — recoverable, findable, and the same thing a re-render has always
    left behind. The other way round would be a shelf full of books that play
    silence.

    And the files are found by walking ``chapters.audio_file`` rather than by
    rebuilding ``library_dir/<author>/<title>`` from the row. The folder name
    is whatever the title was on the day it was rendered; the paths are what
    was actually written. Guessing would unlink a renamed book's neighbour, or
    more likely nothing at all, and report success either way.
    """
    live = conn.execute(
        f"SELECT id, title, state FROM queue WHERE gid = ? AND state IN {LIVE}",
        (gid,),
    ).fetchone()
    if live is not None:
        # The one refusal that is about timing rather than about the book. Said
        # with the job id in it because stopping is keyed on the job and not on
        # the gid, so the number needed next is not the one just typed.
        name = book_name(str(live["title"]), gid)
        job_id = int(live["id"])
        said = (
            f"{name} is being rendered, so stop it first: job {job_id}."
            if str(live["state"]) == "rendering"
            else f"{name} is waiting to be rendered, so take it out of the"
            f" line first: job {job_id}."
        )
        return Removed(False, True, said)

    book = conn.execute("SELECT title FROM books WHERE gid = ?", (gid,)).fetchone()
    if book is None:
        return Removed(False, False, f"There is no book {gid} here.")
    name = book_name(str(book["title"]), gid)

    chapters = conn.execute(
        "SELECT idx, audio_file FROM chapters WHERE book_gid = ? ORDER BY idx",
        (gid,),
    ).fetchall()
    files: list[Path] = []
    for row in chapters:
        path = inside_library(
            cfg, str(row["audio_file"]), f"chapter {int(row['idx']) + 1} of {name}"
        )
        if path is None:
            # Every path is checked before any of them is unlinked, so a book
            # with one bad row is left exactly as it was rather than half
            # taken away. Where it points is in the journal and not in this
            # sentence: it is an absolute path on the VPS, and the page that
            # will show this is on somebody's phone.
            return Removed(
                False,
                True,
                f"{name} has a chapter filed outside the library, so nothing"
                " has been removed. The journal says which.",
            )
        files.append(path)

    with conn:
        forget_the_chapters(conn, gid)
        # The whole history, not just a live row — and there is no live one, or
        # the refusal above would have answered. Every attempt that failed or
        # was stopped is a record of a book that no longer exists, and
        # `queue.view` never shows terminal rows, so leaving them would leave
        # something invisible to clean up later.
        conn.execute("DELETE FROM queue WHERE gid = ?", (gid,))
        conn.execute("DELETE FROM books WHERE gid = ?", (gid,))

    library = cfg.library_dir.expanduser().resolve()
    folders: list[Path] = []
    for path in files:
        # missing_ok, because a chapter that is already gone is nothing to
        # delete rather than a reason to stop half way with the rows already
        # committed. `somnia-doctor.sh` reports exactly this state.
        path.unlink(missing_ok=True)
        if path.parent not in folders:
            folders.append(path.parent)
    for folder in folders:
        _remove_empty_folders(folder, library)

    # The joined files under data_dir, which are the book as well — a whole
    # second copy of it, named by how many chapters it covered.
    forget_streams(cfg, gid)

    logger.info("removed book %s (%s), %d chapters", gid, name, len(files))
    return Removed(True, True, f"{name} is gone, with everything rendered of it.")
