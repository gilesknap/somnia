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

__all__ = [
    "Book",
    "Chapter",
    "fetch_book",
    "implausible_shape",
    "parse_book_html",
]

_HTML_URLS = (
    "https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.html",
    "https://www.gutenberg.org/cache/epub/{gid}/pg{gid}-images.html",
)

_SKIP_HEADINGS = re.compile(
    r"^(contents?|illustrations?|preface|index|footnotes?|transcriber)", re.IGNORECASE
)

# The heading levels a chapter boundary is ever written at, shallowest first.
_LEVELS = ("h2", "h3", "h4")

# What a split at the wrong level looks like. A book bound as volumes — three
# of them under one cover, which is how the 1818 Frankenstein is published —
# has its volume headings at the shallowest level that repeats, so the rule
# below picks those and every real chapter inside them disappears. The tell is
# the shape of what came out: a handful of sections, at least one of them far
# longer than any chapter anybody writes.
#
# Both numbers have to be met, and there has to be a deeper level that repeats,
# and descending has to produce more chapters than staying put. A book really
# in four parts, with nothing deeper marked up, is left exactly as it was.
_FEW_CHAPTERS = 5
_HUGE_PARAGRAPHS = 120

# Roughly what Kokoro reads at, used only to say a chapter's length in a unit
# somebody can judge. A chapter's length in paragraphs means nothing to anyone;
# "averaging 3.7 hours each" is the sentence that makes a bad parse obvious.
_WORDS_PER_MINUTE = 150

# How long an average chapter has to be before the parse is worth doubting.
# Generously long on purpose: this is not a style guide, it is a tripwire for
# markup nobody anticipated, and it must not cry wolf over a book of essays.
_LONG_CHAPTER_MINUTES = 90


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


def _split(body: Tag, level: str, volumes: str | None = None) -> list[Chapter]:
    """Cut the body into chapters at ``level``, in document order.

    With ``volumes``, a heading at that shallower level is not a chapter: it
    names the part the chapters after it belong to, and each of them is titled
    "Volume II — Chapter III" so the volume is carried rather than lost. That is
    the whole of what makes this parser volume-aware, and it is one walk rather
    than a walk per volume because these headings are siblings in the document
    — a volume has no subtree of its own to recurse into.

    Prose that arrives before the part's first chapter heading — a volume's
    epigraph, or the front matter a book opens with — becomes a chapter named
    after the part. Nothing in a book is dropped for being in an awkward place;
    the only text this loses is what a skipped heading owns, which is the table
    of contents and the transcriber's notes, and losing that is the point.
    """
    levels = [volumes, level] if volumes else [level]
    chapters: list[Chapter] = []
    current: Chapter | None = None
    part = ""
    # Two of them, because a skipped *part* has to outlast the headings inside
    # it. "Contents" or "Preface" at the volume level owns everything under it,
    # including its own subheadings — and one flag meant the first of those
    # subheadings cleared the skip and turned the rest of the front matter into
    # chapters. Which is exactly the text a listener must not be read at 2am.
    part_skipping = False
    skipping = False

    def close() -> None:
        nonlocal current
        # A chapter with no paragraphs in it is a heading, not a chapter: the
        # byline, a part-title page, a divider. It is never worth an audio file.
        if current and current.paragraphs:
            chapters.append(current)
        current = None

    for el in body.find_all([*levels, "p"]):
        if el.name == volumes:
            close()
            name = _clean(el.get_text())
            part_skipping = bool(_SKIP_HEADINGS.match(name))
            skipping = part_skipping
            part = "" if part_skipping else name
        elif el.name == level:
            close()
            title = _clean(el.get_text())
            skipping = part_skipping or bool(_SKIP_HEADINGS.match(title))
            if not skipping:
                current = Chapter(
                    title=f"{part} — {title}" if part else title, paragraphs=[]
                )
        else:
            text = _clean(el.get_text())
            if not text or skipping:
                continue
            if current is None:
                if not part:
                    # Before the first heading in the book, and outside any
                    # part. There is nothing to call this and nowhere to put it.
                    continue
                current = Chapter(title=part, paragraphs=[])
            current.paragraphs.append(text)
    close()
    return chapters


def _looks_like_volumes(chapters: list[Chapter]) -> bool:
    """Does this split look like volumes rather than chapters?

    Shape, not names. Matching the word "volume" would catch the English books
    that spell it that way and nothing else — "Part the First", "Buch I", a
    heading that is only a numeral — whereas a section a hundred and twenty
    paragraphs long is not a chapter in any language.
    """
    if not chapters or len(chapters) > _FEW_CHAPTERS:
        return False
    return max(len(c.paragraphs) for c in chapters) >= _HUGE_PARAGRAPHS


def implausible_shape(book: Book) -> str | None:
    """One short sentence about a parse that does not look like a book, or None.

    The heading rule is a heuristic over eighty thousand books' worth of
    hand-written HTML, so it will be wrong again in some shape nobody has seen.
    This is what makes it wrong *loudly*: parsing is minutes and rendering is
    hours, so a count that cannot be right is worth saying at the front of that,
    where somebody can stop it, rather than being discovered by a listener the
    next night with a four-hour audio file in front of them.

    It never stops a render. A book really is sometimes one long piece of prose,
    and refusing to read it would be a heuristic overruling a person.
    """
    if not book.chapters:
        return None
    words = sum(len(p.split()) for c in book.chapters for p in c.paragraphs)
    minutes = words / _WORDS_PER_MINUTE / len(book.chapters)
    if minutes < _LONG_CHAPTER_MINUTES:
        return None
    return (
        f"{len(book.chapters)} chapters, averaging {minutes / 60:.1f} hours each"
        " — the chapter headings may have been missed"
    )


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
    repeated = [level for level in _LEVELS if len(soup.find_all(level)) > 1]

    body = soup.body if soup.body else soup
    chapters = _split(body, repeated[0] if repeated else "h2")

    # And come back down a level if that produced volumes. The shallowest rule
    # above is right for the great majority of the corpus and wrong for every
    # book bound as parts, where it collects the part headings and the real
    # chapters inside them are neither boundaries nor text — they simply vanish,
    # taking a night's listening into three unnavigable blocks. Only accepted
    # if it actually finds more chapters, so a deeper level that repeats inside
    # one section and nowhere else cannot make things worse.
    if _looks_like_volumes(chapters):
        for deeper in repeated[1:]:
            inside = _split(body, deeper, volumes=repeated[0])
            if len(inside) > len(chapters):
                chapters = inside
                break

    if not chapters:
        # No usable headings: treat the whole body as one chapter.
        paragraphs = [_clean(p.get_text()) for p in body.find_all("p")]
        paragraphs = [p for p in paragraphs if p]
        chapters = [Chapter(title=doc_title, paragraphs=paragraphs)]

    return Book(gid=gid, title=doc_title, authors="", chapters=chapters)
