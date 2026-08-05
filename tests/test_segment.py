from somnia.segment import TimedSentence, sentences, windows


def test_sentences_handles_abbreviations():
    text = "Mr. Smith went to St. Ives. He met Dr. Jones there."
    assert sentences(text) == [
        "Mr. Smith went to St. Ives.",
        "He met Dr. Jones there.",
    ]


def test_sentences_handles_dialogue():
    text = '"Stop!" she cried. "The horse is dying." He did not stop.'
    result = sentences(text)
    assert len(result) == 3
    assert result[0] == '"Stop!" she cried.'


def _ts(i: int) -> TimedSentence:
    return TimedSentence(text=f"s{i}.", start_ms=i * 1000, end_ms=(i + 1) * 1000)


def test_windows_cover_all_sentences_with_overlap():
    sents = [_ts(i) for i in range(7)]
    result = windows(sents, size=3, stride=2)
    texts = [w.text for w in result]
    assert texts == ["s0. s1. s2.", "s2. s3. s4.", "s4. s5. s6."]
    assert result[0].start_ms == 0
    assert result[0].end_ms == 3000
    assert result[-1].end_ms == 7000


def test_windows_short_input():
    sents = [_ts(0), _ts(1)]
    result = windows(sents, size=3, stride=2)
    assert len(result) == 1
    assert result[0].text == "s0. s1."


def test_windows_empty():
    assert windows([]) == []
