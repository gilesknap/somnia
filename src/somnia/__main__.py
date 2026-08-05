"""Command line interface for somnia."""

import logging
from argparse import ArgumentParser
from collections.abc import Sequence

from . import __version__

__all__ = ["main"]


def main(args: Sequence[str] | None = None) -> None:
    parser = ArgumentParser(prog="somnia")
    parser.add_argument("-v", "--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("catalog-update", help="download the Gutenberg catalog for browsing")

    p_search = sub.add_parser("search", help="search the local Gutenberg catalog")
    p_search.add_argument("query")
    p_search.add_argument("--language", default="en")

    p_add = sub.add_parser("add", help="render + index a book (streams into ABS)")
    p_add.add_argument("gid", type=int, help="Gutenberg book id")
    p_add.add_argument("--voice", default=None)

    p_find = sub.add_parser("find", help="semantic search within an ingested book")
    p_find.add_argument("gid", type=int)
    p_find.add_argument("query")

    p_ask = sub.add_parser("ask", help="ask the agent about a book (2am surface)")
    p_ask.add_argument("question", nargs="?", help="omit for an interactive session")

    sub.add_parser("libraries", help="list Audiobookshelf libraries (to get the id)")

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
    conn = connect(cfg.db_path)

    if ns.command == "catalog-update":
        from .catalog import update_catalog  # noqa: PLC0415

        n = update_catalog(conn)
        print(f"catalog updated: {n} books")
    elif ns.command == "search":
        from .catalog import search_catalog  # noqa: PLC0415

        for entry in search_catalog(conn, ns.query, language=ns.language):
            print(f"{entry.gid:>6}  {entry.title} — {entry.authors}")
    elif ns.command == "add":
        from .abs import AbsClient  # noqa: PLC0415
        from .embed import Embedder  # noqa: PLC0415
        from .ingest import ingest_book  # noqa: PLC0415
        from .tts import KokoroEngine  # noqa: PLC0415

        if ns.voice:
            cfg.voice = ns.voice
        engine = KokoroEngine(voice=cfg.voice)
        embedder = Embedder(cfg.embed_model)
        abs_client = AbsClient(cfg.abs_url, cfg.abs_token) if cfg.abs_token else None
        ingest_book(cfg, conn, engine, embedder, ns.gid, abs_client)
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
        from .agent import ask  # noqa: PLC0415

        # The agent's own logging would drown its one-line answers.
        logging.getLogger().setLevel(logging.WARNING)
        history: list[object] = []
        while True:
            question = ns.question or input("> ").strip()
            if not question:
                break
            reply, history = ask(cfg, conn, question, history)
            print(reply)
            if ns.question:
                break
    elif ns.command == "libraries":
        from .abs import AbsClient  # noqa: PLC0415

        abs_client = AbsClient(cfg.abs_url, cfg.abs_token)
        for lib in abs_client.libraries():
            print(f"{lib['id']}  {lib['name']}")


if __name__ == "__main__":
    main()
