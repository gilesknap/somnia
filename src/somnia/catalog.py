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
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import httpx

from .pgau import PgauEntry, fetch_index, parse_index, source_of

__all__ = [
    "CATALOG_CSV_URL",
    "CatalogEntry",
    "CatalogSearch",
    "CatalogUpdate",
    "search_catalog",
    "update_catalog",
]

CATALOG_CSV_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"

# How alike two words have to be before one is offered as what the other meant.
# difflib's ratio, which is stdlib and needs nothing installed: "shelly" against
# "shelley" is 0.92, and 0.8 is about where a plausible typo stops and a
# different word starts. Too low and a search for a book somnia does not have
# answers with a book it does, confidently, which is worse than saying no.
_CLOSE_ENOUGH = 0.8

# How much longer or shorter a candidate may be than the word typed. Two covers
# a doubled letter, a dropped one, and both at once; going wider costs a larger
# scan for spellings nobody produces by accident.
_LENGTH_SLACK = 2


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
class CatalogSearch:
    """What a search found, and what it had to do to the query to find it.

    A list of books on its own could not be honest. A search that quietly
    ignored a word the person typed, or looked for a different one, has answered
    a question they did not ask — and "here are four editions of Frankenstein"
    is only true if it also says that nobody in the catalog is called Shelly.
    So the two things that were done to the query travel with the answer, and
    :attr:`said` is them in a clause anybody can read.

    Both are empty for almost every search, which is the point: they are empty
    for every query that worked before any of this existed.
    """

    entries: list[CatalogEntry]
    # Words the catalog has never indexed, and which nothing could be found for.
    # Left out of the search rather than allowed to veto it.
    ignored: list[str] = field(default_factory=list[str])
    # What was typed, against the catalog's own word that was searched instead.
    corrected: dict[str, str] = field(default_factory=dict[str, str])

    @property
    def said(self) -> str:
        """One clause about what was not searched for, or "" if nothing was.

        Written for somebody reading it in the dark rather than for a parser,
        and empty far more often than not — so anything drawing it has to be
        happy to draw nothing.
        """
        parts = [
            f'nothing in the catalog says "{was}", so this is "{instead}"'
            for was, instead in self.corrected.items()
        ]
        if self.ignored:
            words = " and ".join(f'"{w}"' for w in self.ignored)
            parts.append(f"nothing in the catalog says {words}, so it was left out")
        return "; ".join(parts)


@dataclass
class CatalogUpdate:
    """How many books each library contributed, so the CLI can say both."""

    gutenberg: int
    australia: int

    @property
    def total(self) -> int:
        return self.gutenberg + self.australia


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


def _match(
    conn: sqlite3.Connection, terms: list[str], language: str, limit: int
) -> list[CatalogEntry]:
    """The search itself, exactly as it has always been.

    FTS5 has its own query syntax, so each term is quoted: user punctuation —
    apostrophes, hyphens — cannot then produce a syntax error.
    """
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
            source=source_of(int(r["gid"])),
        )
        for r in rows
    ]


def _in_the_catalog(conn: sqlite3.Connection, term: str) -> bool:
    """Does any book in the library contain this word at all?

    One indexed lookup in ``catalog_vocab``, which is FTS5's own view of its
    index — so this is asking the search engine what it knows rather than
    running a search and counting the answer.
    """
    row = conn.execute(
        "SELECT doc FROM catalog_vocab WHERE term = ?", (term.lower(),)
    ).fetchone()
    return row is not None


def _nearest(conn: sqlite3.Connection, term: str) -> str | None:
    """The catalog's own word that this one was probably meant to be.

    Spelling correction *toward what the library can actually answer*, which is
    stronger than generic fuzziness: the candidates are the words the catalog
    holds, so this can never suggest a spelling that then finds nothing.

    The prefilter — same first letter, within two characters of the length — is
    what keeps this to thousands of rows rather than the whole vocabulary, and
    it is a range scan over an index that already exists. It gives up the typo
    that lands on the first letter, which is the rarer half of the mistakes
    somebody makes half asleep and not worth reading the whole word list for.

    Ties go to the commoner word. "shelly" is about equally close to "shelley"
    and to "shells", and the one that appears in a thousand books is the one
    somebody meant.
    """
    # Lowercased first, because that is the shape the index is in: unicode61
    # folds case as it tokenises, so every word in the vocabulary is lower case
    # and a range scan for "S" would step straight past "shelley".
    wanted = term.lower()
    first = wanted[0]
    rows = conn.execute(
        "SELECT term, doc FROM catalog_vocab"
        " WHERE term >= ? AND term < ? AND length(term) BETWEEN ? AND ?",
        (first, first + "￿", len(wanted) - _LENGTH_SLACK, len(wanted) + _LENGTH_SLACK),
    ).fetchall()
    best: str | None = None
    best_key = (_CLOSE_ENOUGH, 0)
    # One matcher, with the typed word as the cached side, and difflib's own two
    # upper bounds asked before the real comparison — which is what
    # `difflib.get_close_matches` does and the reason this stays inside the time
    # a tap takes on a vocabulary of a few hundred thousand words. Both are
    # ceilings on `ratio`, so a candidate they cannot lift above the best so far
    # is skipped without ever being aligned.
    matcher = SequenceMatcher()
    matcher.set_seq2(wanted)
    for row in rows:
        candidate = str(row["term"])
        matcher.set_seq1(candidate)
        if (
            matcher.real_quick_ratio() <= best_key[0]
            or matcher.quick_ratio() <= best_key[0]
        ):
            continue
        key = (matcher.ratio(), int(row["doc"]))
        if key > best_key:
            best, best_key = candidate, key
    return best


def search_catalog(
    conn: sqlite3.Connection, query: str, language: str = "en", limit: int = 10
) -> CatalogSearch:
    """Full-text search over titles, authors, subjects and bookshelves.

    **The exact search runs first and its answer is never touched.** A query
    that worked yesterday returns the same rows in the same order today; nothing
    below happens unless the search found nothing at all, and an exact term is
    never silently widened.

    What happens then is that one wrong word stops vetoing the whole query.
    FTS5's implicit AND makes every term a required exact match and ``unicode61``
    does no stemming and no spelling tolerance, so "Mary Shelly's Frankenstein"
    — the misspelling somebody makes at 2am, into the box built for exactly that
    person — matched nothing whatever, about a library holding four editions of
    the book. Two of the three words were right and counted for nothing.

    So the words that match nothing are found (one lookup each in the catalog's
    own vocabulary), corrected where a near enough word exists in the library,
    and dropped where none does. The corrected query is tried first because it
    is the more precise one; if it finds nothing, the query with the unknown
    words simply removed is tried, which is the answer that cannot be worse than
    silence. Either way the result says what it did, because "here are four
    Frankensteins" is only honest if it also says nobody in the catalog is
    called Shelly.

    Nothing widens a query whose every word the catalog knows. Terms that all
    exist but never appear in one book together is a real question with a real
    answer of "no", and dropping one of them would be guessing at which.
    """
    # Single-character fragments (e.g. the "s" from a possessive) would be
    # required matches under FTS5's implicit AND, so drop them.
    terms = [t for t in re.findall(r"\w+", query) if len(t) > 1]
    if not terms:
        return CatalogSearch([], [], {})

    found = _match(conn, terms, language, limit)
    if found:
        return CatalogSearch(found, [], {})

    unknown = [t for t in terms if not _in_the_catalog(conn, t)]
    if not unknown:
        return CatalogSearch([], [], {})

    corrected: dict[str, str] = {}
    for term in unknown:
        near = _nearest(conn, term)
        if near is not None:
            corrected[term] = near

    if corrected:
        # The corrected query first, because it is the more precise one: it puts
        # "shelley" back into the search rather than answering on "mary" and
        # "frankenstein" alone. Words that are unknown and have no near enough
        # neighbour are left out of it either way.
        instead = [
            corrected[t] if t in corrected else t
            for t in terms
            if t not in unknown or t in corrected
        ]
        found = _match(conn, instead, language, limit)
        if found:
            return CatalogSearch(
                found, [t for t in unknown if t not in corrected], corrected
            )

    kept = [t for t in terms if t not in unknown]
    if not kept:
        return CatalogSearch([], unknown, {})
    return CatalogSearch(_match(conn, kept, language, limit), unknown, {})
