"""Turning a chapter heading into a line somebody can be read.

Until this existed a chapter boundary was silent. The parser puts the heading in
``Chapter.title`` and only the ``<p>`` text into ``paragraphs``, so the words on
the page saying CHAPTER XVII were used for a filename and never spoken — one
chapter's audio simply stopped and the next one's first sentence began. Half
asleep that is indistinguishable from a skip.

Handing the heading straight to Kokoro does not work, and the reasons are the
whole of this module.

**Roman numerals.** ``CHAPTER XVII`` is phonemised letter by letter: "chapter
ex vee eye eye". Arabic digits are read as numbers, so the numeral is converted
rather than the text spelled out.

**Shouting.** Headings are very often set in capitals, and espeak-ng spells
some all-caps words out as initialisms. What is written is a typographic
decision made by a compositor in 1877 and is no part of what the sentence says.

**The number is the book's, not ours.** The obvious implementation announces
``idx + 1``, and it is wrong: the index is a position in what the parser found,
which includes a dedication or a frontispiece caption the book never counted.
Announcing "chapter two" over a heading that says CHAPTER I is worse than
announcing nothing, because it is a confident answer to the one question the
announcement exists to settle. So the number is read out of the heading, and a
heading with no number in it is spoken without one.
"""

import re

__all__ = ["announcement"]

# The words a book uses to introduce a numbered division of itself. Kept in the
# announcement rather than normalised to "chapter", because a book that calls
# its divisions Parts is not being approximate and the listener is holding the
# same vocabulary.
_SECTIONS = "chapter|chap|part|book|section|act|scene|canto|volume|letter"

# A heading that opens with a number, optionally introduced by one of those
# words. The separators after it are the ones real books use — a full stop, a
# colon, an em or en dash, or nothing at all — and everything after them is the
# descriptive half, which may be empty.
_NUMBERED = re.compile(
    rf"^\s*(?:(?P<word>{_SECTIONS})\b\.?\s*)?"
    r"(?P<number>[IVXLCDM]+|\d+)"
    r"\s*[.:,\-–—]*\s*(?P<rest>.*)$",
    # Headings arrive in every case a compositor ever used — CHAPTER, Chapter,
    # and the occasional chapter — and the roster of section words above is
    # written in one of them.
    re.IGNORECASE,
)

# Roman numerals as they are actually written, which is narrower than "letters
# from the roman set". Without this every heading that happens to be made of
# those letters — MIX, DIM, LID — parses as a number, and MIX would be
# announced as chapter one thousand and nine.
_ROMAN = re.compile(
    r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$", re.IGNORECASE
)

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman_to_int(text: str) -> int:
    """Read a roman numeral that has already been checked for shape."""
    total = 0
    previous = 0
    for char in reversed(text.lower()):
        value = _ROMAN_VALUES[char]
        total += -value if value < previous else value
        previous = max(previous, value)
    return total


def _unshout(text: str) -> str:
    """Take a heading out of capitals, and leave one alone that is not in them.

    Only when there is not a single lowercase letter in it, so a title that was
    set as written — *The Strange Man's Arrival* — is passed through exactly,
    and only THE STRANGE MAN'S ARRIVAL is touched. Capitalising word by word
    rather than with ``str.title``, which turns "man's" into "Man'S".
    """
    if not text or any(c.islower() for c in text):
        return text
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.lower().split())


def announcement(title: str, total: int) -> str:
    """What to say before a chapter, or an empty string to say nothing.

    Takes no chapter index, and that absence is the design: the only number
    this will ever speak is one it read in the heading. See the module
    docstring — a position in the parsed list is not what the book calls the
    chapter, and the two differ exactly when a book has front matter.

    ``total`` is how many chapters the parser found, and it does two jobs. A
    book of one chapter is one the parser found no headings in, so its single
    "title" is the book's own name off the ``<title>`` tag — announcing "chapter
    one, the project gutenberg ebook of Dracula" is worse than the silence it
    replaces, so nothing is said at all. And it bounds the numbers that are
    believable: a heading in a thirty-four chapter book that reads as numeral
    one thousand and nine is not a numeral, it is the word MIX.
    """
    title = title.strip()
    if total <= 1 or not title:
        return ""

    match = _NUMBERED.match(title)
    if match is not None:
        raw = match.group("number")
        # Three cases and the third is the one that matters: a token made of
        # roman letters that is not a roman numeral. DIM and CIVIL both reach
        # here, and neither is a number — 0 drops through to the title below.
        if raw.isdigit():
            number = int(raw)
        elif _ROMAN.fullmatch(raw):
            number = _roman_to_int(raw)
        else:
            number = 0
        word = match.group("word")
        rest = _unshout(match.group("rest").strip())
        # A number nobody could be looking at. Without the word in front of it
        # this is a heading made of roman letters that is not a numeral at all,
        # so it is left as the title it is. With the word in front of it the
        # book has said "chapter" and is believed, whatever the number.
        if number and (word or number <= total):
            said = (word or "chapter").capitalize()
            # 'Chap.' is an abbreviation on a page and a stumble in a voice.
            said = "Chapter" if said == "Chap" else said
            return f"{said} {number}. {rest}".strip()

    # No number in the heading, or one that could not be believed. The title is
    # the whole of what there is to say, and inventing a position for it would
    # be the confident wrong answer this module exists to avoid.
    said = _unshout(title)
    return said if said.endswith((".", "!", "?")) else f"{said}."
