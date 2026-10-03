"""``timeline_outline``: the timeline in seconds and plain words, over MCP and REST."""

from __future__ import annotations

import pytest
from s3_app import App
from test_oplog import S, base

from hermes_studio import oplog as O
from hermes_studio.outline import outline


def test_outline_of_the_fixture():
    o = outline(O.Oplog(base()).doc)
    assert o["length_s"] == 14.0 and o["fps"] == 30.0 and o["size"] == [1080, 1920]
    v1 = next(t for t in o["tracks"] if t["id"] == "V1")
    assert [(r["id"], r["start_s"], r["end_s"], r["src_s"]) for r in v1["items"]] == [
        ("c1", 0.0, 4.0, [0.0, 4.0]),
        ("c2", 4.0, 8.0, [10.0, 14.0]),
        ("c3", 10.0, 14.0, [20.0, 24.0]),
    ]
    assert v1["gaps_s"] == [[8.0, 10.0]]
    x1 = next(t for t in o["tracks"] if t["id"] == "T1")["items"][0]
    assert x1 == {"id": "x1", "type": "text", "start_s": 5.0, "end_s": 6.0, "text": "Hi", "style": "pop", "rides_on": "c2"}
    assert o["markers"] == [{"id": "k1", "at_s": 2.0, "label": "here"}]
    assert o["text"].splitlines() == [
        "p1 v0: 1080x1920 at 30 fps, 14.00 s long, 2 media",
        "  media m1: talk.mp4, 600.00 s",
        "  media m2: song.mp3, 300.00 s",
        "T1 (text):",
        '  x1 5.00-6.00 "Hi" (pop) on c2',
        "V1 (main):",
        "  c1 0.00-4.00 m1[0.00-4.00]",
        "  c2 4.00-8.00 m1[10.00-14.00]",
        "  c3 10.00-14.00 m1[20.00-24.00]",
        "  gap 8.00-10.00",
        "A2 (music):",
        "  mu1 0.00-6.00 m2[0.00-6.00] on c1",
        'markers: k1 2.00 "here"',
    ]


def test_outline_shows_speed_volume_fades_and_crossfades():
    log = O.Oplog(base())
    ses = O.Session(O.Actor("human", "u"))
    ops = [
        {"op": "move_clip", "id": "c2", "at": 4 * S - S // 2},
        {"op": "add_transition", "between": ["c1", "c2"], "dur": S // 2, "id": "t1"},
        {"op": "set_props", "id": "c3", "props": {"speed": [2, 1], "volume": [1, 2]}},
        {"op": "set_fade", "id": "c1", "fade_in": S // 4},
    ]
    log.call(ses, "timeline_apply", {"base_version": 0, "ops": ops, "summary": "s", "client_op_id": "k"})
    o = outline(log.doc)
    v1 = {r["id"]: r for r in next(t for t in o["tracks"] if t["id"] == "V1")["items"]}
    assert v1["t1"] == {"id": "t1", "type": "crossfade", "start_s": 3.5, "end_s": 4.0, "between": ["c1", "c2"]}
    assert v1["c3"]["speed"] == 2.0 and v1["c3"]["volume"] == 0.5 and v1["c3"]["end_s"] == 12.0
    assert v1["c1"]["fade_in_s"] == 0.25 and "fade_out_s" not in v1["c1"]
    assert "  crossfade c1>c2 3.50-4.00" in o["text"].splitlines()
    assert "  c3 10.00-12.00 m1[20.00-24.00] speed 2 volume 0.5" in o["text"].splitlines()


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base())
    yield a
    a.close()


def test_outline_over_mcp_and_rest(app):
    ok, o = app.mcp("timeline_outline", {"project_id": "p1"})
    assert ok and o == outline(app.proj.log.doc) and o["hash"] == app.head()["hash"]
    st, _, r = app.req("GET", "/api/projects/p1/outline", token=app.agent)
    assert st == 200 and r == o
