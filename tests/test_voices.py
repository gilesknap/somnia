"""The roster, and the letter at the front of a voice name.

Nothing here loads Kokoro. That is the point of the module being separate from
:mod:`somnia.tts`: the process that answers the page has to be able to say "no
such voice" without importing numpy, so the roster has to be testable without
it too.
"""

import pytest

from somnia.voices import DEFAULT_VOICE, VOICES, known, lang_code_for


def test_the_default_is_the_first_voice_on_offer() -> None:
    """The page reads the order, and the first of them is what it opens on.

    So the two have to agree: a roster whose first entry is not the renderer's
    default would draw one voice in amber and render the book in another, on a
    page that has never been pressed.
    """
    assert known(DEFAULT_VOICE)
    assert VOICES[0].id == DEFAULT_VOICE


def test_every_voice_is_named_once_and_says_something_about_itself() -> None:
    ids = [v.id for v in VOICES]
    names = [v.name for v in VOICES]
    assert len(set(ids)) == len(ids)
    # The short names are what the page draws, so two voices sharing one would
    # be two identical pills doing different things.
    assert len(set(names)) == len(names)
    assert all(v.says for v in VOICES)


@pytest.mark.parametrize(
    ("voice", "code"),
    [
        ("af_heart", "a"),
        ("am_michael", "a"),
        # The bug this was written for: pinned at "a", these read American
        # vowels in a British voice, and Kokoro logged a mismatch nobody saw.
        ("bf_emma", "b"),
        ("bm_george", "b"),
    ],
)
def test_the_language_comes_from_the_voice_that_carries_it(
    voice: str, code: str
) -> None:
    assert lang_code_for(voice) == code


def test_a_name_that_means_nothing_here_falls_back_to_american() -> None:
    """Exactly what the hardcoded value did, and the failure belongs downstream.

    Kokoro's own loader knows every real voice name and says so in the error;
    guessing here would only replace that message with a worse one.
    """
    assert lang_code_for("qq_nobody") == "a"
    assert lang_code_for("") == "a"


def test_the_roster_is_what_the_page_is_held_to_and_not_a_suggestion() -> None:
    assert known("af_heart")
    assert not known("af_nicole")
    assert not known("")
