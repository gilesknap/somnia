"""Project Gutenberg Australia: a second library to search.

Australia clears a book against Australian law, which is not the law Project
Gutenberg proper works to, so the two collections barely overlap — of the 4,384
books listed here, around four fifths are not in the American catalog at all.
That is where Orwell's novels live, and Fitzgerald's uncollected stories, and a
very large amount of pulp.

Three things about this library are not true of the other one, and between them
they explain everything in this module:

* There is no CSV dump and no API. The whole catalog is one plain text file
  meant for a person to read, so it is parsed with a regular expression.
* A book's address cannot be computed from its id. Gutenberg's own files sit at
  a predictable URL, so somnia has never had to remember one; here the file is
  named after the month it was posted, sixty-nine of the four thousand break
  even the loose rule, and two different books share a stem. The address is
  written down instead — see ``catalog_urls`` in :mod:`somnia.db`.
* It is finished. The site stopped taking new books on 31 December 2024, so
  this import is a one-off in everything but name.

Ids are offset clear of Gutenberg's own so that one integer can go on meaning
one book everywhere else in somnia — the queue, the player, the audio routes and
every saved position keep the column they already have.
"""

import re
from dataclasses import dataclass

import httpx

__all__ = [
    "PGAU_GID_BASE",
    "PGAU_INDEX_URL",
    "PgauEntry",
    "fetch_index",
    "is_australian",
    "parse_index",
    "source_of",
]

PGAU_INDEX_URL = "http://gutenberg.net.au/gutindex_aus.txt"

# Far above anything Gutenberg will issue: it is at 78,000 after fifty years.
# The offset is what lets a PG Australia book be a `gid` like any other, so
# nothing downstream needs a second column or a composite key.
PGAU_GID_BASE = 900_000_000

# "Sep 2024 The Miserable Clerk, Steele Rudd    [240025xx.xxx] 4552A", and the
# next line is the URL. The gap before the bracket is \s* rather than \s+
# because a title long enough to fill the column runs straight into it, which
# quietly cost 217 books the first time this was written.
_ENTRY = re.compile(r"^\w{3} \d{4}\s+(?P<body>.+?)\s*\[[^\]]*\]")
_DATE = re.compile(r"^\w{3} \d{4}\s")
_URL = re.compile(r"^\s*(https?://\S+)\s*$")

# ebooks24/2400261h.html — two digits of directory, seven of file. Both are
# needed: stem 1000621 is The Last Lemurian under ebooks11 and A Mummer's
# Throne under ebooks10, so the stem alone would silently merge two books.
_ADDRESS = re.compile(r"/ebooks(?P<dir>\d{2})/(?P<stem>\d{7})h?\.html?$", re.IGNORECASE)


@dataclass
class PgauEntry:
    """One book in the Australian catalog, with the address of its text."""

    gid: int
    title: str
    authors: str
    url: str


def is_australian(gid: int) -> bool:
    """Whether this id belongs to Project Gutenberg Australia rather than PG."""
    return gid >= PGAU_GID_BASE


def source_of(gid: int) -> str:
    """Which of the two libraries a book came from, in the word the API uses.

    The catalog rows carry this word and so does every book on the shelf, and
    both of them mean the same comparison against the same offset. It lives
    here, beside the offset, so that a page asking where a book came from is
    reading an answer rather than repeating the arithmetic.
    """
    return "australia" if is_australian(gid) else "gutenberg"


def _gid(directory: str, stem: str) -> int:
    return PGAU_GID_BASE + int(directory) * 10_000_000 + int(stem)


def _title_and_authors(body: str) -> tuple[str, str]:
    """Split the index's one "Title, Author" string into its two halves.

    The last comma, because titles contain commas far more often than authors
    do and the author is always last. Roughly a quarter of the entries write
    "by Steele Rudd" where the rest write "Steele Rudd"; the page shows this
    string to somebody who is choosing a book, so the "by" comes off. Twice, if
    need be — two entries really do say "by by".

    A body with no comma at all is all title and no author, which is right for
    the ten official reports listed without one.
    """
    title, _, author = body.rpartition(",")
    if not title:
        return body.strip(), ""
    return title.strip(), re.sub(
        r"^(?:by\s+)+", "", author.strip(), flags=re.IGNORECASE
    )


def parse_index(text: str) -> list[PgauEntry]:
    """Every book in the index that somnia could actually read aloud.

    Which is not all of them. Around 300 entries are a .txt or a scanned PDF and
    nothing else, and somnia's parser wants the structure that only the HTML
    edition has — a heading per chapter, a ``<p>`` per paragraph — so a book
    with no HTML is passed over rather than added as something that would fail
    hours later at the front of the queue.

    Where the same book is listed twice, which happens when it was reposted, the
    first listing wins and the second is dropped: the index is newest first, so
    the first is the most recent thing said about it.
    """
    entries: list[PgauEntry] = []
    seen: set[int] = set()
    body: str | None = None
    for line in text.splitlines():
        if _DATE.match(line):
            entry = _ENTRY.match(line)
            # A dated line with no bracketed id is a heading or a note, and any
            # URLs under it belong to nothing.
            body = entry.group("body") if entry else None
            continue
        url = _URL.match(line)
        if url is None or body is None:
            continue
        address = _ADDRESS.search(url.group(1))
        if address is None:
            # A .txt, a .pdf, or one of the links out to Roy Glashan's Library.
            # Keep reading: the HTML edition may be the next line down.
            continue
        gid = _gid(address.group("dir"), address.group("stem"))
        # One book per entry either way. A few list two HTML files — a second
        # volume, or an older edition kept alongside — and taking both would put
        # one title in the catalog twice under ids that render the same words.
        if gid not in seen:
            seen.add(gid)
            title, authors = _title_and_authors(body)
            entries.append(
                PgauEntry(gid=gid, title=title, authors=authors, url=url.group(1))
            )
        body = None
    return entries


def fetch_index() -> str:
    """Download the catalog. Under a megabyte, and it never changes now.

    Decoded as cp1252 rather than left to ``.text``. The file carries no charset
    — no HTTP header and no meta tag — so httpx falls back to UTF-8, and the
    bytes are not UTF-8: it is a Windows-authored page from the nineties, and
    the accented names and dashes in it are single high bytes. Eleven entries
    came through with U+FFFD in them, which is not a rendering blemish but a
    different string — `Le Compte de Janz\xe9` was stored with a replacement
    character where the é belongs, so searching for the author by either
    spelling missed the book.

    cp1252 and not latin-1, which is the reflex: 0x91-0x97 are undefined control
    codes in latin-1 and are exactly what this file uses them for — curly quotes
    and the en and em dashes in its titles.
    """
    resp = httpx.get(PGAU_INDEX_URL, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    return resp.content.decode("cp1252")
