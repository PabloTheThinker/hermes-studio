"""get_transcript's window (from_s / to_s) and its text format, for agents reading long talks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from s3_app import App

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.tasks import fixture_doc, fixture_words  # noqa: E402
from hermes_studio import media as M  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(fixture_doc("p1"))
    M._write_json(M.cache_paths(a.proj.dir, "m1")["words"], {"words": fixture_words()})
    yield a
    a.close()


def test_window_keeps_the_words_said_in_it(app):
    ok, full = app.mcp("get_transcript", {"project_id": "p1"})
    assert ok and len(full["words"]) == 60  # 3 clips x 10 s, a word every 0.5 s
    ok, w = app.mcp("get_transcript", {"project_id": "p1", "from_s": 9, "to_s": 11})
    assert ok and [r["at_s"] for r in w["words"]] == [9.0, 9.5, 10.0, 10.5]
    assert all(r["at_s"] < 11 and r["end_s"] > 9 for r in w["words"])
    ok, tail = app.mcp("get_transcript", {"project_id": "p1", "from_s": 29})
    assert ok and [r["at_s"] for r in tail["words"]] == [29.0, 29.5]


def test_text_format_is_lines_with_start_times(app):
    ok, t = app.mcp("get_transcript", {"project_id": "p1", "format": "text", "to_s": 6})
    assert ok and t["count"] == 12 and "words" not in t
    lines = t["text"].splitlines()
    assert lines[0].startswith("[0.00] w0 w1") and len(lines[0].split()) == 13  # the stamp + 12 words
    assert len(lines) == 1 and lines[0].endswith("w11")
    ok, t = app.mcp("get_transcript", {"project_id": "p1", "format": "text", "to_s": 6.5})
    assert ok and t["count"] == 13 and t["text"].splitlines()[1] == "[6.00] w12"  # 12 words a line
    ok, full = app.mcp("get_transcript", {"project_id": "p1", "format": "text"})
    assert ok and len(full["text"]) < len(str(app.mcp("get_transcript", {"project_id": "p1"})[1]["words"])) / 5


def test_rest_and_refusals(app):
    st, _, r = app.req("GET", "/api/projects/p1/transcript?from_s=9&to_s=11&format=text", token=app.agent)
    assert st == 200 and r["count"] == 4 and r["text"].startswith("[9.00]")
    for args, want in [
        ({"from_s": -1}, ("bad_arg", "/from_s")),
        ({"to_s": "x"}, ("bad_arg", "/to_s")),
        ({"from_s": 5, "to_s": 5}, ("bad_arg", "/to_s")),
        ({"format": "srt"}, ("bad_arg", "/format")),
        ({"zz": 1}, ("unknown_arg", "/zz")),
    ]:
        ok, e = app.mcp("get_transcript", {"project_id": "p1", **args})
        assert not ok and (e["rule"], e["path"]) == want, (args, e)
