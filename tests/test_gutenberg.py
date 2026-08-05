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


def test_parse_headingless_document_is_one_chapter():
    html = "<html><body><p>One.</p><p>Two.</p></body></html>"
    book = parse_book_html(99, html)
    assert len(book.chapters) == 1
    assert book.chapters[0].paragraphs == ["One.", "Two."]
