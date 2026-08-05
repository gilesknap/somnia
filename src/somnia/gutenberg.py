"""Fetch a Project Gutenberg book and parse it into chapters of paragraphs.

We use the HTML edition rather than plain text: it carries real structure
(headings for chapters, ``<p>`` for paragraphs) so no boilerplate heuristics
are needed beyond dropping the pg-header/pg-footer sections.
"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup, Tag

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


def fetch_book(gid: int) -> Book:
    """Download and parse a book by Gutenberg id."""
    last_error: Exception | None = None
    for pattern in _HTML_URLS:
        url = pattern.format(gid=gid)
        try:
            resp = httpx.get(url, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            return parse_book_html(gid, resp.text)
        except httpx.HTTPStatusError as e:
            last_error = e
    raise RuntimeError(f"could not fetch Gutenberg book {gid}") from last_error


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_book_html(gid: int, html: str) -> Book:
    soup = BeautifulSoup(html, "html.parser")

    for boiler_id in ("pg-header", "pg-footer"):
        section = soup.find(id=boiler_id)
        if isinstance(section, Tag):
            section.decompose()

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
