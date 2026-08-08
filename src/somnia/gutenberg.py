"""Fetch a Gutenberg book and parse it into chapters of paragraphs.

We use the HTML edition rather than plain text: it carries real structure
(headings for chapters, ``<p>`` for paragraphs) so no boilerplate heuristics
are needed beyond dropping each library's own wrapping.

Two libraries, one parser. Project Gutenberg Australia marks its books up the
same way — a heading per chapter, a ``<p>`` per paragraph — and everything below
worked on them unaltered the first time it was tried. What it wraps them in is
different, so that is what :func:`_strip_australian_chrome` is for, and it is
the only thing in this module that knows there are two libraries at all.
"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup, Comment, Tag

__all__ = ["Book", "Chapter", "fetch_book", "parse_book_html"]

_HTML_URLS = (
    "https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.html",
    "https://www.gutenberg.org/cache/epub/{gid}/pg{gid}-images.html",
)

_SKIP_HEADINGS = re.compile(
    r"^(contents?|illustrations?|preface|index|footnotes?|transcriber)", re.IGNORECASE
)


@dataclass
class Chapter:
    title: str
    paragraphs: list[str]


@dataclass
class Book:
    gid: int
    title: str
    authors: str
    chapters: list[Chapter]


def fetch_book(gid: int, url: str | None = None) -> Book:
    """Download and parse a book, by Gutenberg id or at a given address.

    ``url`` is for a book whose address cannot be computed from its id, which
    is every Project Gutenberg Australia book: the catalog remembers where each
    one lives and hands it over here. With no ``url`` this behaves as it always
    did and tries Gutenberg's own two spellings in turn.

    The bytes go to the parser undecoded on purpose. Australia sends
    ``Content-Type: text/html`` with no charset at all, so ``resp.text`` would
    fall back to a guess; BeautifulSoup reads the encoding the document declares
    about itself, which is the only place it is actually written down.
    """
    if url is not None:
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        return parse_book_html(gid, resp.content)

    last_error: Exception | None = None
    for pattern in _HTML_URLS:
        try:
            resp = httpx.get(pattern.format(gid=gid), timeout=60, follow_redirects=True)
            resp.raise_for_status()
            return parse_book_html(gid, resp.content)
        except httpx.HTTPStatusError as e:
            last_error = e
    raise RuntimeError(f"could not fetch Gutenberg book {gid}") from last_error


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_australian_chrome(soup: BeautifulSoup) -> None:
    """Take out the banner and the footer PG Australia wraps every book in.

    There is no ``id`` to find them by — this library predates that habit — but
    each block is fenced by an HTML comment naming itself, so the fence is what
    we cut on. Everything between the opening comment and its END is removed;
    the footer's own END comment says "header" (their typo, in four thousand
    files), so the footer is instead cut to the end of its parent, which is
    where it sits anyway.

    Worth doing rather than leaving to the heading rules, because the footer
    lands *after* the last heading in the book. Untouched it becomes a final
    chapter of its own, and a night that ends with a voice reading out "this
    site is full of free ebooks" is the exact opposite of what somnia is for.
    """
    fences = soup.find_all(
        string=lambda s: (
            isinstance(s, Comment)
            and s.strip().lower() in ("ebook header include", "ebook footer include")
        )
    )
    for fence in fences:
        closes = fence.strip().lower().startswith("ebook header")
        for sibling in list(fence.next_siblings):
            ends = isinstance(sibling, Comment) and sibling.strip().lower().startswith(
                "end ebook"
            )
            sibling.extract()
            if closes and ends:
                break
        fence.extract()


def parse_book_html(gid: int, html: str | bytes) -> Book:
    soup = BeautifulSoup(html, "html.parser")

    for boiler_id in ("pg-header", "pg-footer"):
        section = soup.find(id=boiler_id)
        if isinstance(section, Tag):
            section.decompose()

    _strip_australian_chrome(soup)

    # Gutenberg marks table-of-contents entries with class="toc". They sit under
    # a front-matter heading (often the byline), so heading-name matching alone
    # misses them and the whole contents list gets read aloud as chapter one.
    for entry in soup.find_all(class_="toc"):
        entry.decompose()

    title_tag = soup.find("title")
    doc_title = _clean(title_tag.get_text()) if title_tag else f"Gutenberg #{gid}"
    # Gutenberg <title> is usually "<book title> | Project Gutenberg".
    doc_title = doc_title.split("|")[0].strip()

    # Chapter boundaries are headings. Books vary in which level they use, so
    # pick the shallowest heading level that occurs more than once.
    heading_level = None
    for level in ("h2", "h3", "h4"):
        found = soup.find_all(level)
        if len(found) > 1:
            heading_level = level
            break
    if heading_level is None:
        heading_level = "h2"

    chapters: list[Chapter] = []
    current: Chapter | None = None
    body = soup.body if soup.body else soup
    for el in body.find_all([heading_level, "p"]):
        if el.name == heading_level:
            if current and current.paragraphs:
                chapters.append(current)
            title = _clean(el.get_text())
            current = (
                None
                if _SKIP_HEADINGS.match(title)
                else Chapter(title=title, paragraphs=[])
            )
        elif current is not None:
            text = _clean(el.get_text())
            if text:
                current.paragraphs.append(text)
    if current and current.paragraphs:
        chapters.append(current)

    if not chapters:
        # No usable headings: treat the whole body as one chapter.
        paragraphs = [_clean(p.get_text()) for p in body.find_all("p")]
        paragraphs = [p for p in paragraphs if p]
        chapters = [Chapter(title=doc_title, paragraphs=paragraphs)]

    return Book(gid=gid, title=doc_title, authors="", chapters=chapters)
