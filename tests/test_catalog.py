import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from somnia.catalog import search_catalog, text_url, update_catalog
from somnia.db import connect

CSV = """\
Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves
271,Text,2006-01-25,Black Beauty,en,"Sewell, Anna, 1820-1878",Horses -- Fiction,PZ,Best Books Ever Listings
2554,Text,2006-01-12,Crime and Punishment,en,"Dostoyevsky, Fyodor, 1821-1881",Psychological fiction,PG,Best Books Ever Listings
84,Sound,2021-01-01,Frankenstein (audio),en,"Shelley, Mary",Horror,PR,
996,Text,2004-04-27,Don Quijote,es,"Cervantes Saavedra, Miguel de",Spain -- Fiction,PQ,
"""

INDEX = """\
Feb 2002 Nineteen eighty-four, by George Orwell            [010002xx.xxx] 0002A
http://gutenberg.net.au/ebooks01/0100021h.html
Aug 2001 Animal Farm, by George Orwell                     [010001xx.xxx] 0001A
http://gutenberg.net.au/ebooks01/0100011h.html
"""

ORWELL_GID = 910100021


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = connect(tmp_path / "test.db")
    try:
        update_catalog(c, csv_text=CSV, index_text=INDEX)
        yield c
    finally:
        c.close()


def test_import_skips_non_text_entries(conn: sqlite3.Connection):
    count = conn.execute("SELECT count(*) AS n FROM catalog").fetchone()["n"]
    assert count == 5  # 3 Gutenberg (the Sound entry is excluded) + 2 Australian


def test_the_update_says_what_each_library_gave(tmp_path: Path):
    c = connect(tmp_path / "counts.db")
    try:
        counts = update_catalog(c, csv_text=CSV, index_text=INDEX)
    finally:
        c.close()
    assert (counts.gutenberg, counts.australia, counts.total) == (3, 2, 5)


def test_both_libraries_answer_one_search(conn: sqlite3.Connection):
    """The question is "what can I listen to", and it has one answer."""
    assert [r.gid for r in search_catalog(conn, "nineteen eighty-four")] == [ORWELL_GID]
    assert search_catalog(conn, "black beauty")[0].gid == 271


def test_a_result_says_which_library_it_came_from(conn: sqlite3.Connection):
    assert search_catalog(conn, "animal farm")[0].source == "australia"
    assert search_catalog(conn, "black beauty")[0].source == "gutenberg"


def test_an_australian_book_remembers_its_address(conn: sqlite3.Connection):
    """Because nothing can compute it: that is the whole reason for the table."""
    assert text_url(conn, ORWELL_GID) == (
        "http://gutenberg.net.au/ebooks01/0100021h.html"
    )


def test_a_gutenberg_book_has_no_address_to_remember(conn: sqlite3.Connection):
    """None is the ordinary answer, not a failure — fetch_book works it out."""
    assert text_url(conn, 271) is None


def test_the_library_name_is_not_searchable_text(conn: sqlite3.Connection):
    """Otherwise every one of its four thousand books answers "australia"."""
    assert search_catalog(conn, "australia") == []


def test_an_update_replaces_the_addresses_it_replaced_the_books_with(
    conn: sqlite3.Connection,
):
    """A stale address outlives its catalog row otherwise, and points at a book
    that is no longer offered."""
    update_catalog(conn, csv_text=CSV, index_text="")
    assert text_url(conn, ORWELL_GID) is None


def test_search_by_title(conn: sqlite3.Connection):
    results = search_catalog(conn, "black beauty")
    assert len(results) == 1
    assert results[0].gid == 271
    assert "Sewell" in results[0].authors


def test_search_by_subject(conn: sqlite3.Connection):
    results = search_catalog(conn, "horses")
    assert [r.gid for r in results] == [271]


def test_search_filters_language(conn: sqlite3.Connection):
    assert search_catalog(conn, "quijote") == []
    results = search_catalog(conn, "quijote", language="es")
    assert [r.gid for r in results] == [996]


def test_search_survives_punctuation(conn: sqlite3.Connection):
    assert search_catalog(conn, 'dostoyevsky\'s "crime"!')[0].gid == 2554


def test_search_empty_query(conn: sqlite3.Connection):
    assert search_catalog(conn, "...") == []
