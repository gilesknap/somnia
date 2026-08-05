"""Local Gutenberg catalog: import the official CSV dump, search it offline."""

import csv
import io
import re
import sqlite3
from dataclasses import dataclass

import httpx

__all__ = ["CATALOG_CSV_URL", "CatalogEntry", "search_catalog", "update_catalog"]

CATALOG_CSV_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"


@dataclass
class CatalogEntry:
    gid: int
    title: str
    authors: str
    subjects: str
    language: str


def update_catalog(conn: sqlite3.Connection, csv_text: str | None = None) -> int:
    """Replace the catalog table from the official Gutenberg CSV dump.

    Pass ``csv_text`` to import from a string (used in tests); otherwise the
    ~20MB dump is downloaded.
    """
    if csv_text is None:
        resp = httpx.get(CATALOG_CSV_URL, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        csv_text = resp.text
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = [
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
    with conn:
        conn.execute("DELETE FROM catalog")
        conn.executemany(
            "INSERT INTO catalog (gid, title, authors, subjects, bookshelves, language)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


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
        )
        for r in rows
    ]
