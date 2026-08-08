"""What a chapter says its own name as, given what the compositor wrote."""

import pytest

from somnia.announce import announcement

# A book long enough that any number in these headings is believable. The
# bound only matters in the tests that are about the bound.
MANY = 40


@pytest.mark.parametrize(
    ("title", "said"),
    [
        # The numeral is converted rather than spelled out. "CHAPTER XVII" fed
        # to espeak is "chapter ex vee eye eye", which is the whole reason this
        # module exists.
        ("CHAPTER XVII", "Chapter 17."),
        ("Chapter IV", "Chapter 4."),
        # Real Gutenberg headings: the number and the name, separated by
        # whatever that edition happened to use.
        ("CHAPTER XVII.—THE INVISIBLE MAN", "Chapter 17. The Invisible Man"),
        ("CHAPTER I. My Early Home", "Chapter 1. My Early Home"),
        ("Chapter 9: The Bad Beginning", "Chapter 9. The Bad Beginning"),
        # Black Beauty's own spelling, which has no word "chapter" in it at all.
        ("01 My Early Home", "Chapter 1. My Early Home"),
        # A bare numeral is a chapter number and nothing else.
        ("XII", "Chapter 12."),
        ("7", "Chapter 7."),
        # Shouting is a typographic decision, not something the author said.
        ("CHAPTER II THE HUNT", "Chapter 2. The Hunt"),
        # ...and a heading that was set as written is passed through as written.
        (
            "Chapter 3. The Strange Man's Arrival",
            "Chapter 3. The Strange Man's Arrival",
        ),
    ],
)
def test_a_numbered_heading_is_said_as_a_number_and_a_name(
    title: str, said: str
) -> None:
    assert announcement(title, MANY) == said


def test_str_title_is_not_used_so_an_apostrophe_survives_the_shouting() -> None:
    """``"man's".title()`` is ``"Man'S"``, which espeak reads as two words."""
    assert announcement("CHAPTER IV THE STRANGE MAN'S ARRIVAL", MANY) == (
        "Chapter 4. The Strange Man's Arrival"
    )


@pytest.mark.parametrize(
    ("title", "said"),
    [
        # A book that calls its divisions something else is not corrected.
        ("PART II", "Part 2."),
        ("BOOK III — THE RETURN", "Book 3. The Return"),
        # An abbreviation on a page is a stumble in a voice.
        ("Chap. V", "Chapter 5."),
    ],
)
def test_the_books_own_word_for_a_division_is_kept(title: str, said: str) -> None:
    assert announcement(title, MANY) == said


@pytest.mark.parametrize(
    ("title", "said"),
    [
        # No number anywhere, so none is invented — see the module docstring on
        # why idx + 1 is the wrong answer rather than the easy one.
        ("MY EARLY HOME", "My Early Home."),
        ("Dedication", "Dedication."),
        # Already ends in a stop, so it does not get a second one.
        ("Who is Sylvia?", "Who is Sylvia?"),
    ],
)
def test_a_heading_with_no_number_is_spoken_as_it_stands(title: str, said: str) -> None:
    assert announcement(title, MANY) == said


@pytest.mark.parametrize("title", ["MIX", "DIM", "LID", "CIVIL"])
def test_a_word_made_of_roman_letters_is_a_word(title: str) -> None:
    """MIX is a valid roman numeral for 1009 and is obviously not one here.

    The guard is the book's own length: a heading in a forty-chapter book that
    reads as one thousand and nine is not a chapter number. Without it every
    heading spelled out of I, V, X, L, C, D and M becomes arithmetic.
    """
    assert announcement(title, MANY) == f"{title.capitalize()}."


def test_a_number_past_the_end_of_the_book_is_believed_if_the_book_said_chapter() -> (
    None
):
    """The bound is a guess about ambiguity, and an explicit word settles it.

    A parse that dropped some headings leaves ``total`` short of the highest
    real chapter number, and a book that has written the word CHAPTER is not
    being ambiguous about what follows it.
    """
    assert announcement("CHAPTER LXI", 40) == "Chapter 61."
    # ...where the same numeral alone, in the same book, is left as a title.
    assert announcement("LXI", 40) == "Lxi."


def test_a_book_of_one_chapter_says_nothing() -> None:
    """No headings were found, so the one "title" is the book's own name.

    "Chapter one. The Project Gutenberg eBook of Dracula" is worse than the
    silence it would replace.
    """
    assert announcement("The Project Gutenberg eBook of Dracula", 1) == ""


def test_a_heading_of_nothing_says_nothing() -> None:
    assert announcement("   ", MANY) == ""
