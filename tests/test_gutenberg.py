from somnia.gutenberg import Book, Chapter, implausible_shape, parse_book_html

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


# ------------------------------------------------------- books bound as volumes
#
# The 1818 Frankenstein (gid 41445) is three volumes under one cover, and its
# volume headings are the shallowest level that repeats — so the shallowest-wins
# rule used to collect *those*, and every real chapter inside them was neither a
# boundary nor a paragraph and simply disappeared. What came out was four
# chapters, each hours long, from a book that has twenty-seven.

ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII")


def volume_book(inner: str, volumes: int = 3, chapters: int = 4) -> str:
    """A book bound as volumes, with its chapters marked up one level deeper.

    Every chapter is long enough that the volumes clear the "far longer than any
    chapter anybody writes" bar — which is what the descent is triggered by, so
    a fixture of three-paragraph chapters would prove nothing.
    """
    parts = ["<html><head><title>Frankenstein</title></head><body>"]
    parts.append("<h2>by Mary Shelley</h2>")
    for v in range(volumes):
        parts.append(f"<h2>VOLUME {ROMANS[v]}</h2>")
        for c in range(chapters):
            parts.append(f"<{inner}>CHAPTER {ROMANS[c]}</{inner}>")
            parts.extend(
                f"<p>Volume {v + 1} chapter {c + 1} paragraph {i + 1}.</p>"
                for i in range(40)
            )
    parts.append("</body></html>")
    return "".join(parts)


def test_parse_splits_a_volume_bound_book_at_its_real_chapters():
    book = parse_book_html(41445, volume_book("h3"))
    assert len(book.chapters) == 12
    assert book.chapters[0].paragraphs[0] == "Volume 1 chapter 1 paragraph 1."


def test_parse_keeps_the_volume_in_the_chapter_title():
    """So "which chapter am I in" has an answer, and chapter I of volume III is
    not confusable with chapter I of volume I."""
    book = parse_book_html(41445, volume_book("h3"))
    assert book.chapters[0].title == "VOLUME I — CHAPTER I"
    assert book.chapters[-1].title == "VOLUME III — CHAPTER IV"


def test_parse_descends_to_h4_when_that_is_where_the_chapters_are():
    book = parse_book_html(41445, volume_book("h4"))
    assert len(book.chapters) == 12
    assert book.chapters[0].title == "VOLUME I — CHAPTER I"


def test_parse_leaves_a_book_of_a_few_real_chapters_alone():
    """The shape test is the whole guard. Four ordinary chapters marked up at h2
    with subheadings inside them must not be re-split into subheadings."""
    parts = ["<html><head><title>Short</title></head><body>"]
    for c in range(4):
        parts.append(f"<h2>Chapter {ROMANS[c]}</h2>")
        parts.append("<p>A paragraph.</p>")
        parts.append("<h3>A subheading</h3>")
        parts.append("<p>Another paragraph.</p>")
    parts.append("</body></html>")
    book = parse_book_html(99, "".join(parts))
    assert [c.title for c in book.chapters] == [
        "Chapter I",
        "Chapter II",
        "Chapter III",
        "Chapter IV",
    ]


def test_parse_keeps_prose_that_sits_before_a_volumes_first_chapter():
    """A volume's epigraph belongs to something rather than to nothing."""
    html = volume_book("h3").replace(
        "<h2>VOLUME I</h2>", "<h2>VOLUME I</h2><p>An epigraph.</p>", 1
    )
    book = parse_book_html(41445, html)
    assert book.chapters[0].title == "VOLUME I"
    assert book.chapters[0].paragraphs == ["An epigraph."]
    assert book.chapters[1].title == "VOLUME I — CHAPTER I"


# ------------------------------------------------- noticing a parse gone wrong


def long_book(chapters: int, words_each: int) -> Book:
    return Book(
        gid=1,
        title="Something",
        authors="",
        chapters=[
            Chapter(title=f"{i}", paragraphs=["word " * words_each])
            for i in range(chapters)
        ],
    )


def test_implausible_shape_says_nothing_about_an_ordinary_book():
    assert implausible_shape(long_book(39, 4_000)) is None


def test_implausible_shape_flags_chapters_that_are_hours_long():
    said = implausible_shape(long_book(3, 40_000))
    assert said is not None
    assert "3 chapters" in said
    assert "4.4 hours" in said


def test_implausible_shape_survives_a_book_with_no_chapters():
    assert implausible_shape(Book(gid=1, title="", authors="", chapters=[])) is None
