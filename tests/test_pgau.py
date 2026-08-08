import pytest

from somnia import pgau
from somnia.pgau import PGAU_GID_BASE, PgauEntry, is_australian, parse_index

# The real index, in miniature: a preamble of prose, then entries of one line
# plus however many URL lines the book has. Every oddity below was taken from
# the file itself rather than invented.
INDEX = """\

Project Gutenberg Australia

List of FREE ebooks available from this site

Check out the latest Additions to Roy Glashan's Library at
http://freeread.com.au/@RGLibrary/newbooks.html

*****

Sep 2024 Green Grey Homestead, Steele Rudd                 [240026xx.xxx] 4553A
http://gutenberg.net.au/ebooks24/2400261h.html
Jul 2024 The Umbrella Murder, Carolyn Wells                [240021xx.xxx] 4548A
http://gutenberg.net.au/ebooks24/2400211h.html
Jun 2024 Verse of Christopher Brennan, Christopher Brennan [240016xx.xxx] 4543A
http://gutenberg.net.au/ebooks24/2400161p.pdf
Oct 2023 Life of Patrick Sarsfield, Earl of Lucan,Todhunter[230115xx.xxx] 4521A
http://gutenberg.net.au/ebooks23/2301151h.html
Mar 2003 Apache Devil, by by Edgar Rice Burroughs          [030027xx.xxx] 0176A
http://gutenberg.net.au/ebooks03/0300271h.html
Feb 2002 Nineteen eighty-four, by George Orwell            [010002xx.xxx] 0002A
http://gutenberg.net.au/ebooks01/0100021.txt
http://gutenberg.net.au/ebooks01/0100021h.html
Jan 2002 Politics and the English Language, G Orwell       [020015xx.xxx] 0031A
http://gutenberg.net.au/ebooks02/0200151.txt
Jan 2001 Report on Agriculture and Trade                   [010009xx.xxx] 0009A
http://gutenberg.net.au/ebooks01/0100091h.html
"""

# Two books whose file stems are identical and whose directories are not. This
# pair is real: it is the reason a gid is built from both halves of the address.
COLLIDING = """\
Jan 2010 The Last Lemurian, George Firth Scott             [100062xx.xxx] 1000A
http://gutenberg.net.au/ebooks11/1000621h.html
Jan 2010 A Mummer's Throne, Fred Merrick White             [100062xx.xxx] 1001A
http://gutenberg.net.au/ebooks10/1000621h.html
"""

REPOSTED = """\
Jun 2006 The Mazaroff Rifle, Fred M White                  [060048xx.xxx] 0500A
http://gutenberg.net.au/ebooks06/0600481h.html
Jan 2006 The Mazaroff Rifle, Fred M White                  [060048xx.xxx] 0499A
http://gutenberg.net.au/ebooks06/0600481.txt
http://gutenberg.net.au/ebooks06/0600481h.html
"""


def entry(entries: list[PgauEntry], title: str) -> PgauEntry:
    return next(e for e in entries if e.title == title)


def test_an_entry_carries_its_title_author_and_address():
    book = entry(parse_index(INDEX), "Green Grey Homestead")
    assert book.authors == "Steele Rudd"
    assert book.url == "http://gutenberg.net.au/ebooks24/2400261h.html"


def test_ids_sit_clear_of_gutenbergs_own():
    """So one integer goes on meaning one book everywhere else in somnia."""
    entries = parse_index(INDEX)
    assert all(is_australian(e.gid) for e in entries)
    assert all(e.gid > PGAU_GID_BASE for e in entries)
    assert not is_australian(271)


def test_a_title_that_fills_the_column_is_still_read():
    """No space before the bracket, which quietly cost 217 books once."""
    book = entry(parse_index(INDEX), "Life of Patrick Sarsfield, Earl of Lucan")
    assert book.authors == "Todhunter"


def test_the_by_comes_off_the_author():
    assert entry(parse_index(INDEX), "Nineteen eighty-four").authors == "George Orwell"


def test_the_by_comes_off_twice_when_the_index_says_it_twice():
    assert entry(parse_index(INDEX), "Apache Devil").authors == "Edgar Rice Burroughs"


def test_an_entry_with_no_author_is_all_title():
    book = entry(parse_index(INDEX), "Report on Agriculture and Trade")
    assert book.authors == ""


def test_a_book_with_no_html_edition_is_passed_over():
    """somnia's parser wants the structure only the HTML edition has.

    Taking the .txt or the scanned PDF would put a book in the catalog that
    fails hours later at the front of the queue, which is the worst place to
    find out.
    """
    titles = [e.title for e in parse_index(INDEX)]
    assert "Politics and the English Language" not in titles
    assert "Verse of Christopher Brennan" not in titles


def test_a_book_listed_twice_over_is_one_book():
    """The .txt line comes first and must not cost the book its HTML edition."""
    entries = parse_index(INDEX)
    assert [e.title for e in entries].count("Nineteen eighty-four") == 1
    assert entry(entries, "Nineteen eighty-four").url.endswith("0100021h.html")


def test_two_books_sharing_a_stem_stay_two_books():
    entries = parse_index(COLLIDING)
    assert len(entries) == 2
    assert len({e.gid for e in entries}) == 2


def test_a_reposted_book_is_taken_once_and_from_the_newest_listing():
    entries = parse_index(REPOSTED)
    assert len(entries) == 1
    assert entries[0].url == "http://gutenberg.net.au/ebooks06/0600481h.html"


def test_the_preamble_is_not_a_book():
    """It has a URL under it, which is all an entry looks like from below."""
    assert not any("freeread" in e.url for e in parse_index(INDEX))


def test_an_empty_index_is_no_books_rather_than_an_error():
    assert parse_index("") == []


def test_the_index_is_read_as_the_windows_page_it_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It carries no charset, and the bytes in it are not UTF-8.

    A page written on Windows in the nineties: no HTTP charset, no meta tag, and
    single high bytes for the accents and dashes in its titles. httpx falls back
    to UTF-8 on a file that says nothing, so eleven entries arrived with U+FFFD
    where a character belonged — not a rendering blemish but a different string,
    which is a book the author's own name no longer finds.

    cp1252 and not latin-1: 0x96 is an undefined control code in latin-1 and is
    the en dash this file means by it.
    """
    body = (
        "Jan 2016 Le Compte de Janz\xe9, Anthony Trollope"
        "           [160001xx.xxx] 3000A\n"
        "http://gutenberg.net.au/ebooks16/1600011h.html\n"
    ).encode("cp1252")

    class Answered:
        content = body

        @staticmethod
        def raise_for_status() -> None:
            return None

    monkeypatch.setattr(pgau.httpx, "get", lambda *a, **k: Answered())

    text = pgau.fetch_index()

    assert "�" not in text
    assert "Janz\xe9" in text
    # And through the parser, which is what the catalog actually stores.
    assert parse_index(text)[0].title == "Le Compte de Janz\xe9"
