"""One book as one file, so crossing a chapter need not touch the player.

The page is the player, and until now it fetched a chapter at a time: every
boundary assigned ``src``, which runs the media element load algorithm, empties
the element and takes Android's media notification down with it. Through the
phone's own speaker the rebuild is fast enough to be invisible. Over Bluetooth,
where audio focus has to be taken again and the A2DP route re-established, it is
slow enough to see and sometimes never finishes — and a book that goes quiet at
2am is not found out about until morning. That is issue 31.

So the chapters of a book are joined here into one file the element loads once.
``-c copy`` moves not a single audio byte: the joined ``mdat`` was measured, on
all forty-nine chapters of Black Beauty, to be the exact concatenation of the
chapters' own. The render clock the manifest speaks carries over as an identity,
so a position in the book stays a position in the file.

Two things about a stream's identity matter more than anything else here.

It lives under ``data_dir`` and never in ``library_dir``. The library is
Audiobookshelf's own layout, and ADR 3 promises the ABS app goes on working on
those files; a second copy of every book appearing among them would break that
promise quietly, in a scan nobody was watching.

And it is named by how many chapters it covers, so a book that grows while
somebody is listening gets a *new* file rather than a rewrite of the one their
phone has open. A version is written once and never touched again. The phone
holds a five-hour file open for the length of a night, and rewriting it under an
in-flight range request splices fresh bytes against a header the element parsed
twenty minutes ago — a corrupt read in the middle of a sentence.
"""

import logging
import os
import subprocess
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path

from .config import Config

__all__ = ["build_stream", "concat_list", "stream_path"]

logger = logging.getLogger(__name__)

# How far short of the chapters it joins a stream may fall, per chapter, before
# it is thrown away rather than served.
#
# There has to be a check at all because ffmpeg's concat demuxer does not treat
# an input it cannot read as a failure. It prints "Impossible to open", exits
# **zero**, and leaves a file covering however much it managed. Measured, not
# assumed: a three-chapter book with one unreadable chapter came out eight
# seconds long with a return code of nought. Served, that is a book that ends
# early — and reaching the end of a stream is precisely what removes the player
# from the platform's session and takes the lock screen down, which is the
# failure this whole module exists to prevent.
#
# So the build is judged against the clock the chapter rows keep rather than
# against the exit code. The allowance is one AAC frame at somnia's render rate
# — 1024 samples at 24 kHz, 42.667 ms — because that is the most a container can
# honestly fall short of the render clock at a join. A chapter that is missing
# is minutes, so nothing near this line is ever a real book.
FRAME_MS = 50

# One lock per book, for the life of the process, because the builds are keyed
# by book and there is one server. It is held across ffmpeg — a second or two on
# a five-hour book — so it lives in the threadpool the route hands it to and
# never on the event loop. The dictionary only grows by one small lock per book
# ever streamed, which over the life of a library is nothing worth reaping.
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def stream_path(cfg: Config, gid: int, n: int) -> Path:
    """Where the stream covering a book's first ``n`` chapters lives.

    Built out of two integers and nothing else, which is the whole of the
    traversal defence — the same argument
    :meth:`somnia.player.Player.chapter_file` makes, and it has to be made again
    here because the server has no auth by design.
    """
    return cfg.data_dir / "streams" / str(gid) / f"{n}.m4a"


def concat_list(files: Sequence[Path]) -> str:
    """The list file ffmpeg's concat demuxer reads, one line per chapter.

    Single quoted, with an apostrophe written as ``'\\''`` — close the quote,
    escape a literal one, open it again. ``_safe_name`` in ingest keeps
    apostrophes because chapter titles have them, so
    ``008 - 08 Ginger's Story Continued.m4a`` is a real path in the real
    library. Written without the escape the line ends at the apostrophe and
    ffmpeg goes looking for a file called ``008 - 08 Ginger`` — which, by the
    rule at the top of this module, it says and then exits zero over, leaving a
    Black Beauty that stops after chapter seven.
    """
    quoted = (str(f).replace("'", "'\\''") for f in files)
    return "".join(f"file '{path}'\n" for path in quoted)


def build_stream(
    cfg: Config, gid: int, files: Sequence[Path], span_ms: int
) -> Path | None:
    """Join a book's first chapters into one file, and say where it is.

    ``span_ms`` is how much book those chapters are meant to hold, on the render
    clock; it is what the finished file is judged against.

    None means the concatenation could not honestly be made, and the reason is
    in the journal. It is not the end of the night: the manifest keeps a url per
    chapter for exactly this, so a book whose build fails is one that blinks at
    every boundary, the way every book did before this — rather than one that
    will not open at all.
    """
    path = stream_path(cfg, gid, len(files))
    with _locks_guard:
        lock = _locks.setdefault(gid, threading.Lock())
    with lock:
        # Asked again while the first request was building it. The page's HEAD
        # and its first range arrive together, so this is the ordinary case at
        # boot rather than a race worth being clever about.
        if path.is_file():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        return _join(gid, path, files, span_ms)


def _join(gid: int, path: Path, files: Sequence[Path], span_ms: int) -> Path | None:
    """Write the concatenation to a temporary name, then rename it into place.

    Never straight to ``path``, because a half-written concatenation is
    indistinguishable by name from a finished one, and the phone that picks one
    up at 2am gets a book that will not open. ``os.replace`` is atomic within a
    directory, so the name the page asks for either does not exist yet or holds
    a whole book, and never the middle of one being written.
    """
    handle, name = tempfile.mkstemp(
        dir=path.parent, prefix=f"{path.stem}.", suffix=".part.m4a"
    )
    os.close(handle)
    temporary = Path(name)
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as listing:
            listing.write(concat_list(files))
            listing.flush()
            done = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "concat",
                    # The paths are absolute because that is what ingest wrote
                    # into the rows. Nothing in a request reaches this list.
                    "-safe",
                    "0",
                    "-i",
                    listing.name,
                    "-c",
                    "copy",
                    # The same flag ingest encodes each chapter with, and it
                    # matters more here: 1.7 MB of header for a five-hour book,
                    # and a phone that had to go back for the tail before the
                    # first note is a wait at the end of a press of play.
                    "-movflags",
                    "+faststart",
                    str(temporary),
                ],
                capture_output=True,
                text=True,
            )
        if done.returncode != 0:
            logger.error(
                "joining %d chapters of book %d failed (%d): %s",
                len(files),
                gid,
                done.returncode,
                done.stderr.strip(),
            )
            return None
        joined_ms = _duration_ms(temporary)
        if joined_ms is None or joined_ms < span_ms - FRAME_MS * len(files):
            logger.error(
                "joining %d chapters of book %d gave %s ms of a %d ms book: %s",
                len(files),
                gid,
                joined_ms,
                span_ms,
                done.stderr.strip() or "no complaint from ffmpeg",
            )
            return None
        os.replace(temporary, path)
        return path
    finally:
        # A build that failed leaves nothing behind. A part file that outlived
        # its build is the one thing in this directory that could be mistaken
        # for a version, and the mistake would be made by a phone.
        temporary.unlink(missing_ok=True)


def _duration_ms(path: Path) -> int | None:
    """How long the container says it is, or None if it will not say.

    ffprobe rather than reading the box, because it ships with the ffmpeg that
    just wrote the file and it is the same program's answer about its own work.
    """
    done = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        return None
    try:
        return round(float(done.stdout.strip()) * 1000)
    except ValueError:
        return None
