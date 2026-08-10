"""Command line interface for somnia."""

import logging
from argparse import ArgumentParser
from collections.abc import Sequence
from typing import TYPE_CHECKING

from . import __version__

if TYPE_CHECKING:
    # Only for the annotation on _queue_line. Every branch of main() imports
    # what it needs where it needs it, so that `somnia search` never pays for
    # the modules `somnia add` wants, and one type name is not a reason to
    # break that.
    from .queue import QueueRow

__all__ = ["main"]

_ORDINALS = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    """1st, 2nd, 3rd: how far down the line a book is, in English.

    A queue of three books deep does not need this, and somebody reading "place
    2" instead of "2nd in line" would understand it perfectly well. It is here
    because the line is a sentence about waiting and reads as one.
    """
    suffix = "th" if n % 100 in (11, 12, 13) else _ORDINALS.get(n % 10, "th")
    return f"{n}{suffix}"


def _queue_line(row: "QueueRow") -> str:
    """One job, on one line, for somebody at a terminal.

    The state comes first and in the same column every time, because the
    question being asked is "is anything actually happening", and that has to be
    answerable by looking down the left of the screen rather than by reading.

    Two of the words are not states at all. A render whose heartbeat has gone
    quiet says so, since 'rendering' would be a claim about a process that may
    have died with the box; and one that has been asked to stop says 'stopping',
    because it stays 'rendering' until the child gets to the end of its
    sentence, and printing that would look like the stop had been ignored.

    The chapter is the one being worked on rather than the count that is
    finished — the same number, and the same meaning, as the "rendering chapter
    3/34" line the renderer writes to the journal, so the two can be read side
    by side. It is held at the last chapter rather than allowed to say "50 of
    49" in the seconds between the final chapter landing and the job ending.
    """
    if row.state == "queued":
        where = f"{_ordinal(row.place)} in line"
    elif row.state != "rendering":
        where = row.state
    elif row.stopping:
        where = "stopping"
    elif not row.responding:
        where = "not responding"
    else:
        where = "rendering"

    name = row.title or f"book {row.gid}"
    if row.authors:
        name = f"{name} — {row.authors}"

    detail = ""
    if row.state == "rendering":
        detail = (
            f"chapter {min(row.chapters_done + 1, row.chapters_total)}"
            f" of {row.chapters_total}"
            if row.chapters_total
            else "fetching the text"
        )
    elif row.error:
        detail = row.error
    return f"{row.id:>4}  {where:<14}  {name}" + (f"  ({detail})" if detail else "")


def main(args: Sequence[str] | None = None) -> None:
    parser = ArgumentParser(prog="somnia")
    parser.add_argument("-v", "--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("catalog-update", help="download the Gutenberg catalog for browsing")

    p_search = sub.add_parser("search", help="search the local Gutenberg catalog")
    p_search.add_argument("query")
    p_search.add_argument("--language", default="en")

    p_add = sub.add_parser("add", help="render + index a book")
    p_add.add_argument("gid", type=int, help="Gutenberg book id")
    p_add.add_argument("--voice", default=None)

    p_worker = sub.add_parser("worker", help="render whatever is in the queue")
    p_worker.add_argument(
        "--once", action="store_true", help="render one book and exit"
    )

    p_queue = sub.add_parser("queue", help="the ingest queue: ask, watch, stop")
    queue_sub = p_queue.add_subparsers(dest="queue_command")
    queue_sub.add_parser("list", help="what is in the queue (the default)")
    p_queue_add = queue_sub.add_parser("add", help="ask for a book to be rendered")
    p_queue_add.add_argument("gid", type=int, help="Gutenberg book id")
    p_queue_stop = queue_sub.add_parser(
        "stop", help="take a book out of the line, or stop the render"
    )
    p_queue_stop.add_argument("job_id", type=int, metavar="ID", help="the queue row id")

    p_remove = sub.add_parser("remove", help="take a book out of the library for good")
    p_remove.add_argument("gid", type=int, help="Gutenberg book id")

    p_find = sub.add_parser("find", help="semantic search within an ingested book")
    p_find.add_argument("gid", type=int)
    p_find.add_argument("query")

    p_ask = sub.add_parser("ask", help="ask the agent about a book (2am surface)")
    p_ask.add_argument("question", nargs="?", help="omit for an interactive session")

    p_serve = sub.add_parser("serve", help="serve the chat page (tailnet only)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8721)

    ns = parser.parse_args(args)
    if ns.command is None:
        parser.print_help()
        return

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    from .config import load_config  # noqa: PLC0415
    from .db import connect  # noqa: PLC0415

    cfg = load_config()
    conn = connect(cfg.db_path, cross_thread=ns.command == "serve")

    if ns.command == "catalog-update":
        from .catalog import update_catalog  # noqa: PLC0415

        counts = update_catalog(conn)
        print(
            f"catalog updated: {counts.total} books"
            f" ({counts.gutenberg} from Project Gutenberg,"
            f" {counts.australia} from Project Gutenberg Australia)"
        )
    elif ns.command == "search":
        from .catalog import search_catalog  # noqa: PLC0415

        # The library is named only when it is the unexpected one. Every line
        # saying "Project Gutenberg" would be a column of noise; the whole
        # reason to print it at all is that an Australian book is somewhere
        # else, under an id that looks nothing like the others.
        for entry in search_catalog(conn, ns.query, language=ns.language):
            where = "  [PG Australia]" if entry.source == "australia" else ""
            print(f"{entry.gid:>10}  {entry.title} — {entry.authors}{where}")
    elif ns.command == "add":
        from .queue import submit  # noqa: PLC0415
        from .worker import asked_to_stop, render_one  # noqa: PLC0415

        # On the row rather than on this process's configuration. Setting
        # cfg.voice here only worked when this process went on to win the claim
        # a line later, and it does not have to: the worker unit is running and
        # may take the book first, in which case `--voice bm_george` rendered
        # six hours in af_heart and said nothing about it. Written down where
        # the render will look for it, whichever process does the rendering.
        # Not checked against the roster: a terminal is allowed any name Kokoro
        # knows, and a wrong one fails in the model's loader with the real list.
        # Submit, then render under the same claim every other renderer takes.
        # This used to go straight at ingest_book, which made it a second
        # renderer with no lease and nothing to stop two of them running at
        # once — and two Kokoro processes on two cores render slower than
        # somebody listens. There is now exactly one function in somnia that
        # renders a book, and it always holds a lease.
        asked = submit(conn, ns.gid, ns.voice or "")
        print(asked.said)
        if not asked.ok:
            # Somnia already has it, or it is already coming. Draining the line
            # by hand is `somnia worker --once`; this command was asked about
            # one book and has no business starting six hours of another.
            return
        with asked_to_stop() as stopping:
            rendered = render_one(cfg, conn, stopping=stopping)
        if rendered is None:
            print(
                "Something else is being rendered, so this one waits its"
                " turn. Run `somnia queue` to see the line."
            )
            return
        # Which book that was, because it is not always the one this command was
        # asked about. `render_one` claims the head of the line and the book
        # just submitted goes on the end of it, so anything already queued is
        # rendered first — and every sentence below used to be printed about
        # whichever book that turned out to be, under the id the person typed.
        # Six hours of the wrong book, reported as theirs.
        this_one = rendered.gid == ns.gid
        book = "the book" if this_one else f"book {rendered.gid}, which was ahead of it"
        if rendered.state == "queued":
            # Ctrl-C, or systemd stopping the session out from under it. Said
            # rather than logged because the person who pressed it is watching
            # a terminal and wants to know what it cost them.
            print(
                f"Stopped at the end of a chapter of {book}. Everything already"
                " rendered is still there, and it is back in the queue."
            )
        elif rendered.state == "done":
            print(f"Rendered {book}.")
        elif rendered.state == "failed":
            # The sentence itself is on the row; `somnia queue` prints it. What
            # belongs here is that it stopped and did not finish, which was said
            # nowhere at all before — a failed render simply ended the command.
            print(f"Could not render {book}. Run `somnia queue` for the reason.")
        elif rendered.state == "cancelled":
            print(f"Somebody stopped {book}.")
        if not this_one:
            print(f"Book {ns.gid} is still in the line. Run `somnia queue` to see it.")
    elif ns.command == "worker":
        from .worker import asked_to_stop, render_one, supervise  # noqa: PLC0415

        with asked_to_stop() as stopping:
            if ns.once:
                render_one(cfg, conn, stopping=stopping)
            else:
                supervise(cfg, conn, stopping=stopping)
    elif ns.command == "queue":
        from .queue import stop, submit, view  # noqa: PLC0415

        if ns.queue_command == "add":
            # No network and no render: this writes a row and says where in the
            # line it landed. Whether Gutenberg has the book at all is found out
            # when something comes to render it, and said in a sentence then.
            print(submit(conn, ns.gid).said)
        elif ns.queue_command == "stop":
            print(stop(conn, ns.job_id).said)
        else:
            rows = view(conn)
            if not rows:
                print("Nothing in the queue.")
            for row in rows:
                print(_queue_line(row))
    elif ns.command == "remove":
        from .library import remove_book  # noqa: PLC0415

        # No confirmation prompt. Typing a Gutenberg id is already a deliberate
        # act — nothing offers this command a gid to press — and a terminal
        # that stops to ask cannot be run from a script or over ssh from a
        # phone, which is where this actually gets used. The asking belongs on
        # the page, where a delete is one tap away from everything else.
        print(remove_book(cfg, conn, ns.gid).said)
    elif ns.command == "find":
        from .embed import Embedder  # noqa: PLC0415
        from .index import find_passage  # noqa: PLC0415

        embedder = Embedder(cfg.embed_model)
        for p in find_passage(conn, embedder, ns.gid, ns.query):
            mins = p.start_ms // 60000
            print(
                f"[{mins // 60}:{mins % 60:02d}h  d={p.distance:.3f}] {p.chapter_title}"
            )
            print(f"    {p.text}\n")
    elif ns.command == "ask":
        from .agent import Conversation, open_library  # noqa: PLC0415

        # The agent's own logging would drown its one-line answers.
        logging.getLogger().setLevel(logging.WARNING)
        conversation = Conversation(cfg, open_library(cfg, conn))
        while True:
            question = ns.question or input("> ").strip()
            if not question:
                break
            print(conversation.ask(question).reply)
            if ns.question:
                break
    elif ns.command == "serve":
        from .server import serve  # noqa: PLC0415

        serve(cfg, conn, ns.host, ns.port)


if __name__ == "__main__":
    main()
