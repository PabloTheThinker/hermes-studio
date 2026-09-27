"""Namer tests: parsing, cleaning, offline fallback. No LLM call."""

from hermesclip import namer


def test_clean_strips_noise_and_title_cases():
    assert namer.clean('"why nobody talks about this 🔥."') == "Why Nobody Talks About This"


def test_parse_shapes():
    assert namer._parse('{"titles": ["a b", {"title": "c d"}]}', 2) == ["A B", "C D"]
    assert namer._parse('{"Clip 1": "one two", "Clip 2": "three four"}', 2) == ["One Two", "Three Four"]


def test_offline_title_prefers_strong_line():
    t = namer.offline_title("Okay so yeah. Why does nobody tell you the biggest mistake? It costs money.")
    assert t.endswith("?") and "Mistake" in t


def test_ai_titles_off_mode(monkeypatch):
    monkeypatch.setenv("HERMESCLIP_NAMER", "off")
    titles, src = namer.ai_titles(["I made ten thousand dollars in one week."])
    assert src == "offline" and titles[0]
