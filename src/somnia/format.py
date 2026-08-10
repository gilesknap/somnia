"""How a position and a passage are written down for somebody to read.

Two functions, and they are here rather than in :mod:`somnia.tools` because of
what importing that costs. `tools` is the agent's library: it reaches the index,
which reaches the embedder, which is numpy and sentence-transformers — a second
or so of imports and a large chunk of memory. Anything whose whole business is
writing a clock down for somebody to read should not be paying that.

Nothing here touches the database, the model or the network. That is the whole
of the rule for what belongs in this file: if it can be tested with a number and
a string, it can live here and be imported by anything.
"""

__all__ = ["format_timestamp", "shorten"]


def shorten(text: str, limit: int) -> str:
    """A passage cut to a length a row can hold, on a word boundary.

    Public because the "you are here" row is cut by it too, from the other side
    of the app: its words come back from ``/api/passage`` rather than down with
    an offer, and a rule that only half the rows on one screen obeyed would show
    up as the one row that can be longer than the screen.

    The ellipsis goes on only when something was actually cut, so a row that
    ends in one is telling the truth about there being more. There is never a
    leading one: the words start where the passage starts, and a row that opened
    with "…" would read as though the beginning had been withheld, which on a
    screen built around withholding things is precisely the wrong suggestion.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip()
    # A single word longer than the whole limit has no boundary to cut on, and
    # an empty row says nothing at all — so fall back to cutting mid-word.
    return f"{cut or text[:limit].rstrip()}…"


def format_timestamp(ms: int) -> str:
    """Global milliseconds as h:mm:ss — how a listener thinks about position."""
    seconds = ms // 1000
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
