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
42324,Text,2013-03-21,"Frankenstein; Or, The Modern Prometheus",en,"Shelley, Mary Wollstonecraft, 1797-1851",Horror tales,PR,Gothic Fiction
41445,Text,2012-11-27,"Frankenstein; Or, The Modern Prometheus",en,"Shelley, Mary Wollstonecraft, 1797-1851",Horror tales,PR,Gothic Fiction
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
    assert count == 7  # 5 Gutenberg (the Sound entry is excluded) + 2 Australian


def test_the_update_says_what_each_library_gave(tmp_path: Path):
    c = connect(tmp_path / "counts.db")
    try:
        counts = update_catalog(c, csv_text=CSV, index_text=INDEX)
    finally:
        c.close()
    assert (counts.gutenberg, counts.australia, counts.total) == (5, 2, 7)


def test_both_libraries_answer_one_search(conn: sqlite3.Connection):
    """The question is "what can I listen to", and it has one answer."""
    assert [r.gid for r in search_catalog(conn, "nineteen eighty-four").entries] == [
        ORWELL_GID
    ]
    assert search_catalog(conn, "black beauty").entries[0].gid == 271


def test_a_result_says_which_library_it_came_from(conn: sqlite3.Connection):
    assert search_catalog(conn, "animal farm").entries[0].source == "australia"
    assert search_catalog(conn, "black beauty").entries[0].source == "gutenberg"


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
    assert search_catalog(conn, "australia").entries == []


def test_an_update_replaces_the_addresses_it_replaced_the_books_with(
    conn: sqlite3.Connection,
):
    """A stale address outlives its catalog row otherwise, and points at a book
    that is no longer offered."""
    update_catalog(conn, csv_text=CSV, index_text="")
    assert text_url(conn, ORWELL_GID) is None


def test_search_by_title(conn: sqlite3.Connection):
    results = search_catalog(conn, "black beauty").entries
    assert len(results) == 1
    assert results[0].gid == 271
    assert "Sewell" in results[0].authors


def test_search_by_subject(conn: sqlite3.Connection):
    results = search_catalog(conn, "horses").entries
    assert [r.gid for r in results] == [271]


def test_search_filters_language(conn: sqlite3.Connection):
    assert search_catalog(conn, "quijote").entries == []
    results = search_catalog(conn, "quijote", language="es").entries
    assert [r.gid for r in results] == [996]


def test_search_survives_punctuation(conn: sqlite3.Connection):
    assert search_catalog(conn, 'dostoyevsky\'s "crime"!').entries[0].gid == 2554


def test_search_empty_query(conn: sqlite3.Connection):
    assert search_catalog(conn, "...").entries == []


# --------------------------------------------------- a query with a typo in it
#
# FTS5's implicit AND makes every term a required exact match and unicode61 has
# no spelling tolerance, so one wrong word used to take a query that names two
# right ones to nothing at all. "Mary Shelly's Frankenstein" — the misspelling
# somebody makes at 2am, into the box built for that person — answered that the
# catalog held nothing, about a library with two editions of the book in it.


def test_a_misspelled_name_still_finds_the_book(conn: sqlite3.Connection):
    results = search_catalog(conn, "Mary Shelly's Frankenstein")
    assert sorted(e.gid for e in results.entries) == [41445, 42324]


def test_a_misspelling_is_corrected_towards_the_catalogs_own_word(
    conn: sqlite3.Connection,
):
    """Not generic fuzziness: the candidates are the words the library holds, so
    a correction can never suggest a spelling that then finds nothing."""
    results = search_catalog(conn, "Mary Shelly's Frankenstein")
    assert results.corrected == {"Shelly": "shelley"}
    assert results.ignored == []
    assert results.said == (
        'nothing in the catalog says "Shelly", so this is "shelley"'
    )


def test_a_word_nothing_is_near_is_dropped_rather_than_vetoing_the_query(
    conn: sqlite3.Connection,
):
    results = search_catalog(conn, "black beauty zzzqx")
    assert [e.gid for e in results.entries] == [271]
    assert results.ignored == ["zzzqx"]
    assert results.corrected == {}
    assert "left out" in results.said


def test_an_exact_search_is_untouched_by_any_of_it(conn: sqlite3.Connection):
    """The relaxation only ever runs after an exact search found nothing, so a
    query that worked yesterday returns the same rows and says nothing new."""
    results = search_catalog(conn, "black beauty")
    assert [e.gid for e in results.entries] == [271]
    assert (results.ignored, results.corrected, results.said) == ([], {}, "")


def test_words_the_catalog_knows_are_never_dropped_to_force_an_answer(
    conn: sqlite3.Connection,
):
    """Two real words that never appear in one book together is a real question
    with a real answer of "no". Dropping one of them would be guessing at which
    one was meant, and would answer a question nobody asked."""
    results = search_catalog(conn, "beauty punishment")
    assert results.entries == []
    assert (results.ignored, results.corrected, results.said) == ([], {}, "")


def test_a_correction_that_finds_nothing_falls_back_to_leaving_the_word_out(
    conn: sqlite3.Connection,
):
    """ "quijote" is in the catalog but not in English, so correcting "beuty" to
    "beauty" and keeping it gives nothing — and the answer that cannot be worse
    than silence is the query with the unknown word simply removed."""
    results = search_catalog(conn, "quijoteX horses")
    assert [e.gid for e in results.entries] == [271]
    assert results.ignored == ["quijoteX"]


def test_a_query_of_nothing_but_unknown_words_still_answers_honestly(
    conn: sqlite3.Connection,
):
    results = search_catalog(conn, "zzzqx wwwqx")
    assert results.entries == []
    assert results.ignored == ["zzzqx", "wwwqx"]


def test_the_vocabulary_is_the_catalog_as_it_is_now(conn: sqlite3.Connection):
    """It is a view over the FTS5 index rather than a table of its own, so a
    catalog rebuilt from a smaller list cannot leave stale words behind that
    would be offered as corrections for ever."""
    assert search_catalog(conn, "Mary Shelly's Frankenstein").entries != []
    update_catalog(conn, csv_text=CSV.replace("Shelley", "Sewell"), index_text=INDEX)
    assert search_catalog(conn, "Mary Shelly's Frankenstein").corrected == {}
