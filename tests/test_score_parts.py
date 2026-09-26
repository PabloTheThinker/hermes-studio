"""Opus-style score breakdown: hook / flow / value, 0-99."""
from hermesclip.plan import score_parts
from hermesclip.transcribe import Word


def _w(text, t):
    return Word(text=text, start=t, end=t + 0.4)


def test_parts_in_range_and_keys():
    words = [_w(x, i * 0.5) for i, x in enumerate("Nobody tells you this secret about money. Here is why it works.".split())]
    p = score_parts(words, 12.0)
    assert set(p) == {"hook", "flow", "value"}
    assert all(0 <= v <= 99 for v in p.values())


def test_empty_words():
    assert score_parts([], 10.0) == {}
