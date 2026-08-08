from somnia.gutenberg import parse_book_html

BOOK_HTML = """
<html><head><title>Black Beauty | Project Gutenberg</title></head><body>
<section id="pg-header"><p>The Project Gutenberg eBook of Black Beauty ***</p></section>
<h2>by Anna Sewell</h2>
<p class="toc">CONTENTS</p>
<p class="toc">Chapter I. My Early Home</p>
<h2>Chapter I. My Early Home</h2>
<p>The first place that I can well remember was a large pleasant meadow.</p>
<p>While I was young I lived upon my mother's milk.</p>
<h2>Chapter II. The Hunt</h2>
<p>Before I was two years old a circumstance happened.</p>
<section id="pg-footer"><p>*** END OF THE PROJECT GUTENBERG EBOOK ***</p></section>
</body></html>
"""


def test_parse_extracts_title_and_chapters():
    book = parse_book_html(271, BOOK_HTML)
    assert book.title == "Black Beauty"
    assert [c.title for c in book.chapters] == [
        "Chapter I. My Early Home",
        "Chapter II. The Hunt",
    ]
    assert book.chapters[0].paragraphs == [
        "The first place that I can well remember was a large pleasant meadow.",
        "While I was young I lived upon my mother's milk.",
    ]


def test_parse_drops_boilerplate_and_contents():
    book = parse_book_html(271, BOOK_HTML)
    all_text = " ".join(p for c in book.chapters for p in c.paragraphs)
    assert "Project Gutenberg" not in all_text
    assert "END OF" not in all_text


# Project Gutenberg Australia, whose books are marked up the same way and
# wrapped in something else entirely. Both fences are as they appear in the real
# files, including the footer's closing comment saying "header".
AUSTRALIAN_HTML = """
<html><head><title>Animal Farm</title></head><body>
<!--ebook header include-->
<table><tr><td><p>Project Gutenberg Australia, a treasure-trove of literature</p>
</td></tr></table>
<!--END ebook header include-->
<p style="text-align:center">Title: Animal Farm<br>Author: George Orwell</p>
<h2>Chapter I</h2>
<p>Mr. Jones, of the Manor Farm, had locked the hen-houses for the night.</p>
<h2>Chapter II</h2>
<p>Three nights later old Major died peacefully in his sleep.</p>
<hr>
<h2>THE END</h2>
<!--ebook footer include-->
<p style="text-align:center"><b>This site is full of FREE ebooks -
<a href="http://gutenberg.net.au">Project Gutenberg Australia</a></b></p>
<!--END ebook header include-->
</body></html>
"""


def test_parse_reads_an_australian_book_the_same_way():
    book = parse_book_html(910100011, AUSTRALIAN_HTML)
    assert book.title == "Animal Farm"
    assert [c.title for c in book.chapters] == ["Chapter I", "Chapter II"]


def test_parse_drops_the_australian_footer():
    """It sits after the last heading, so untouched it becomes a final chapter.

    A night that ends with a voice reading out "this site is full of free
    ebooks" is the exact opposite of what somnia is for.
    """
    book = parse_book_html(910100011, AUSTRALIAN_HTML)
    assert "THE END" not in [c.title for c in book.chapters]
    all_text = " ".join(p for c in book.chapters for p in c.paragraphs)
    assert "FREE ebooks" not in all_text


def test_parse_drops_the_australian_banner():
    """Which matters most for a book with no headings, where every paragraph in
    the body becomes part of the one chapter there is."""
    headingless = AUSTRALIAN_HTML.replace("<h2>", "<b>").replace("</h2>", "</b>")
    book = parse_book_html(910100011, headingless)
    all_text = " ".join(p for c in book.chapters for p in c.paragraphs)
    assert "treasure-trove" not in all_text
    assert "FREE ebooks" not in all_text
    assert "Mr. Jones" in all_text


def test_parse_accepts_bytes_so_the_document_declares_its_own_encoding():
    """Australia sends no charset in the header, so guessing is all that is
    left unless the bytes reach the parser undecoded."""
    book = parse_book_html(910100011, AUSTRALIAN_HTML.encode("utf-8"))
    assert [c.title for c in book.chapters] == ["Chapter I", "Chapter II"]


def test_parse_headingless_document_is_one_chapter():
    html = "<html><body><p>One.</p><p>Two.</p></body></html>"
    book = parse_book_html(99, html)
    assert len(book.chapters) == 1
    assert book.chapters[0].paragraphs == ["One.", "Two."]
