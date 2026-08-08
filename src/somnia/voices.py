"""The voices a book can be read in, and what the letters in front of one mean.

A module of its own, and the reason is the same one that keeps Kokoro out of the
supervisor: the server has to be able to say "no such voice" to a press on the
page, and :mod:`somnia.tts` imports numpy on the way to importing torch. The
roster is a tuple of strings, so the process answering the page can hold all of
it and still be the cheap one.

Kokoro's voice names carry their language in the first letter — ``a`` for
American English, ``b`` for British — and the pipeline needs telling that letter
separately, which is what :func:`lang_code_for` is for. Getting that wrong is
silent: the model happily reads a British voice with American phonemes and only
a listener notices.

The roster is short on purpose. Kokoro ships around thirty voices and most of
them are graded D by the people who trained them — fine for a sentence in a
demo, and audibly synthetic somewhere in the second hour of a novel. These six
are the ones worth a night, and they are spread rather than ranked: two American
women, two American men, one of each from Britain, so the choice on the page is
between voices that actually sound different from one another.
"""

from dataclasses import dataclass

__all__ = [
    "DEFAULT_VOICE",
    "SAMPLE_TEXT",
    "VOICES",
    "Voice",
    "known",
    "lang_code_for",
]


@dataclass(frozen=True)
class Voice:
    """One voice a book can be read in.

    ``id`` is Kokoro's name and the only form of it that ever reaches the model
    or the database. ``name`` is what the page says, because ``af_heart`` is a
    filename and the picker is read by somebody choosing how a book will sound.
    ``says`` is one line for anybody who cannot play the sample — a phone on
    silent, a screen reader, a network that dropped the clip — and it is written
    to be usable on its own rather than as a caption to audio.
    """

    id: str
    name: str
    says: str


# What every render used before there was a choice, and still what a submission
# that names no voice gets. It is also the best of them: Kokoro's own scorecard
# grades af_heart alone at A.
DEFAULT_VOICE = "af_heart"

VOICES = (
    Voice("af_heart", "heart", "American, warm and unhurried"),
    Voice("af_bella", "bella", "American, lower and slower"),
    Voice("am_michael", "michael", "American, a man, even and plain"),
    Voice("am_puck", "puck", "American, a man, brighter and quicker"),
    Voice("bf_emma", "emma", "British, measured"),
    Voice("bm_george", "george", "British, a man, low"),
)

# The sentence the samples are rendered from — Black Beauty's first line, which
# somnia can and does render in full, so what you hear in the picker is the
# thing itself rather than a demo phrase chosen to flatter a model. Long enough
# to hear a rhythm: a voice can be judged on three words about as well as a room
# can be judged from the doorway.
SAMPLE_TEXT = (
    "The first place that I can well remember was a large pleasant meadow"
    " with a pond of clear water in it."
)

# The languages Kokoro names in the first letter of a voice. Only the two
# English ones are in the roster above — the rest need a G2P backend that is not
# installed here (misaki's Japanese and Chinese extras), so a voice from one of
# them fails when the pipeline is built rather than reading anything wrong.
_LANG_CODES = frozenset("abefhijpz")


def known(voice: str) -> bool:
    """Is this one of the voices the page is allowed to ask for?

    Only the page is held to the roster. ``SOMNIA_VOICE`` and ``somnia add
    --voice`` will take any name Kokoro knows, because those are hands on a
    terminal doing something deliberate — trying af_nicole for a night is not a
    thing to need a release for. A press on a phone is different: it can only
    send what it was drawn with, so anything else arriving there is a stale page
    or somebody poking the API, and both want telling.
    """
    return any(v.id == voice for v in VOICES)


def lang_code_for(voice: str) -> str:
    """Which language Kokoro should phonemise in, given a voice name.

    This exists because getting it wrong is inaudible in the logs and obvious in
    the audio. ``KPipeline`` takes the language and the voice separately: the
    language picks the G2P — espeak-ng's ``en-us`` against its ``en-gb`` — and
    the voice only supplies the timbre. Pinned to ``a``, as it was, asking for
    ``bm_george`` got a British-sounding man reading American vowels, saying
    "clerk" to rhyme with "work" and rolling the r's at the ends of words. The
    pipeline logs a mismatch and carries on, which is the worst of both.

    Falls back to American for a name whose first letter means nothing here,
    which is exactly what the hardcoded value did — an unknown voice is going to
    fail in the model's own loader a moment later, and it should fail there,
    with Kokoro's list of real names in the message, rather than here.
    """
    first = voice[:1]
    return first if first in _LANG_CODES else "a"
