import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from somnia.catalog import search_catalog, update_catalog
from somnia.db import connect

CSV = """\
Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves
271,Text,2006-01-25,Black Beauty,en,"Sewell, Anna, 1820-1878",Horses -- Fiction,PZ,Best Books Ever Listings
2554,Text,2006-01-12,Crime and Punishment,en,"Dostoyevsky, Fyodor, 1821-1881",Psychological fiction,PG,Best Books Ever Listings
84,Sound,2021-01-01,Frankenstein (audio),en,"Shelley, Mary",Horror,PR,
996,Text,2004-04-27,Don Quijote,es,"Cervantes Saavedra, Miguel de",Spain -- Fiction,PQ,
"""


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = connect(tmp_path / "test.db")
    update_catalog(c, csv_text=CSV)
    try:
        yield c
    finally:
        c.close()


def test_import_skips_non_text_entries(conn: sqlite3.Connection):
    count = conn.execute("SELECT count(*) AS n FROM catalog").fetchone()["n"]
    assert count == 3  # the Sound entry is excluded


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
