"""The local catalog: import the published lists, search them offline.

Two libraries feed it. Project Gutenberg publishes a CSV dump of everything it
has; Project Gutenberg Australia publishes a text file meant for a person to
read (:mod:`somnia.pgau`). They are kept in one table because the question the
page asks is "what can I listen to tonight", and that question has one answer,
not one per library.
"""

import csv
import io
import re
import sqlite3
from dataclasses import dataclass

import httpx

from .pgau import PgauEntry, fetch_index, is_australian, parse_index

__all__ = [
    "CATALOG_CSV_URL",
    "CatalogEntry",
    "CatalogUpdate",
    "search_catalog",
    "update_catalog",
]

CATALOG_CSV_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"


@dataclass
class CatalogEntry:
    gid: int
    title: str
    authors: str
    subjects: str
    language: str
    # Which library this book comes from: 'gutenberg' or 'australia'. Read off
    # the id rather than stored, because the id is what the offset in
    # :mod:`somnia.pgau` was for — there is one fact here, not two that could
    # drift apart.
    source: str


@dataclass
class CatalogUpdate:
    """How many books each library contributed, so the CLI can say both."""

    gutenberg: int
    australia: int

    @property
    def total(self) -> int:
        return self.gutenberg + self.australia


def _source(gid: int) -> str:
    return "australia" if is_australian(gid) else "gutenberg"


def _gutenberg_rows(csv_text: str) -> list[tuple[str, str, str, str, str, str]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return [
        (
            r["Text#"],
            r["Title"],
            r["Authors"],
            r["Subjects"],
            r["Bookshelves"],
            r["Language"],
        )
        for r in reader
        if r.get("Type") == "Text" and r.get("Title")
    ]


def _australia_rows(
    entries: list[PgauEntry],
) -> list[tuple[str, str, str, str, str, str]]:
    # No subjects and no bookshelves: the Australian index carries neither, and
    # writing the library's name into a searchable column would make every one
    # of its four thousand books answer a search for "australia".
    #
    # The language is asserted rather than known, for the same reason — there is
    # no such column to read. The collection is English, and a book that is not
    # would be invisible to a search rather than wrong in one.
    return [(str(e.gid), e.title, e.authors, "", "", "en") for e in entries]


def update_catalog(
    conn: sqlite3.Connection,
    csv_text: str | None = None,
    index_text: str | None = None,
) -> CatalogUpdate:
    """Replace the catalog from both libraries' published lists.

    With no arguments the ~20MB dump and the ~700KB index are both downloaded.
    Pass either text and nothing is downloaded at all: the update imports
    exactly what it was handed, and the library you left out contributes
    nothing. That is the test path, and it is all-or-nothing on purpose —
    supplying one list and silently fetching the other over the network is the
    kind of half-offline that makes a test suite depend on a website in Sydney.

    Both downloads happen before anything is written, so a library that is
    unreachable leaves the catalog exactly as it was rather than half of it.
    Rebuilt whole rather than merged, because that is what it has always been —
    a local copy of somebody else's list, and the cheapest way to be sure it
    says what theirs does is to write it again.
    """
    if csv_text is None and index_text is None:
        resp = httpx.get(CATALOG_CSV_URL, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        csv_text = resp.text
        index_text = fetch_index()

    gutenberg = _gutenberg_rows(csv_text or "")
    australian = parse_index(index_text or "")
    rows = gutenberg + _australia_rows(australian)

    with conn:
        conn.execute("DELETE FROM catalog")
        conn.executemany(
            "INSERT INTO catalog (gid, title, authors, subjects, bookshelves, language)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute("DELETE FROM catalog_urls")
        conn.executemany(
            "INSERT INTO catalog_urls (gid, url) VALUES (?, ?)",
            [(e.gid, e.url) for e in australian],
        )
    return CatalogUpdate(gutenberg=len(gutenberg), australia=len(australian))


def text_url(conn: sqlite3.Connection, gid: int) -> str | None:
    """Where this book's text lives, or None if its id already says.

    None is the answer for every Project Gutenberg book and is not a failure:
    :func:`somnia.gutenberg.fetch_book` computes those addresses itself.
    """
    row = conn.execute("SELECT url FROM catalog_urls WHERE gid = ?", (gid,)).fetchone()
    return str(row["url"]) if row else None


def search_catalog(
    conn: sqlite3.Connection, query: str, language: str = "en", limit: int = 10
) -> list[CatalogEntry]:
    """Full-text search over titles, authors, subjects and bookshelves."""
    # FTS5 has its own query syntax; quote each term so user punctuation
    # (apostrophes, hyphens) can't produce a syntax error.
    # Single-character fragments (e.g. the "s" from a possessive) would be
    # required matches under FTS5's implicit AND, so drop them.
    terms = [t for t in re.findall(r"\w+", query) if len(t) > 1]
    if not terms:
        return []
    match = " ".join(f'"{t}"' for t in terms)
    rows = conn.execute(
        "SELECT gid, title, authors, subjects, language FROM catalog"
        " WHERE catalog MATCH ? AND language = ? ORDER BY rank LIMIT ?",
        (match, language, limit),
    ).fetchall()
    return [
        CatalogEntry(
            gid=int(r["gid"]),
            title=r["title"],
            authors=r["authors"],
            subjects=r["subjects"],
            language=r["language"],
            source=_source(int(r["gid"])),
        )
        for r in rows
    ]
