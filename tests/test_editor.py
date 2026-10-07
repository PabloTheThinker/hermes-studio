"""Edit page store: create, trim, split, undo, redo. The op log is the writer."""

from __future__ import annotations

import json

import pytest

from hermes_studio import editor as E
from hermes_studio import timeline as T


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_STUDIO_EDITOR", str(tmp_path))
    return tmp_path


def test_create_draws_four_tracks(home):
    v = E.create("demo")
    assert v["id"] == "demo"
    assert [t["id"] for t in v["tracks"]] == ["T1", "V1", "A1", "A2"]
    assert len(v["tracks"][1]["items"]) == 3
    assert v["duration"] > 20


def test_trim_split_undo_redo(home):
    E.create("demo")
    v1 = E.open_project("demo")["version"]
    trimmed = E.trim("demo", "c1", src_out=6 * T.TICK_RATE)
    c1 = next(i for i in trimmed["tracks"][1]["items"] if i["id"] == "c1")
    assert c1["dur"] == pytest.approx(6, abs=0.01)
    assert trimmed["version"] == v1 + 1
    split = E.split("demo", "c2", 12)
    ids = [i["id"] for i in split["tracks"][1]["items"]]
    assert "c2" not in ids
    assert len(ids) == 4
    back = E.undo("demo")
    assert "c2" in [i["id"] for i in back["tracks"][1]["items"]]
    again = E.redo("demo")
    assert "c2" not in [i["id"] for i in again["tracks"][1]["items"]]


def test_lift_move_and_edge(home):
    E.create("demo")
    lifted = E.lift("demo", "c3")
    assert "c3" not in [i["id"] for i in lifted["tracks"][1]["items"]]
    moved = E.move("demo", "c2", 10)
    c2 = next(i for i in moved["tracks"][1]["items"] if i["id"] == "c2")
    assert c2["at"] == pytest.approx(10, abs=0.02)
    edged = E.set_edge("demo", "c1", "end", 5)
    c1 = next(i for i in edged["tracks"][1]["items"] if i["id"] == "c1")
    assert c1["dur"] == pytest.approx(5, abs=0.02)
    back = E.undo("demo")
    c1b = next(i for i in back["tracks"][1]["items"] if i["id"] == "c1")
    assert c1b["dur"] == pytest.approx(8, abs=0.02)
    E.create("demo")
    before = E.open_project("demo")["version"]
    with pytest.raises(E.EditorError):
        E.split("demo", "c1", 0)
    assert E.open_project("demo")["version"] == before


def test_media_path_cannot_leave_the_project(home):
    E.create("demo")
    with pytest.raises(E.EditorError):
        E.resolve_media(home / "demo", "../secret.mp4")
    assert E.resolve_media(home / "demo", "media/talk.mp4") == (home / "demo" / "media" / "talk.mp4").resolve()


def test_playhead_maps_into_the_source(home):
    E.create("demo")
    doc = json.loads((home / "demo" / "timeline.json").read_text())
    hit = E.source_time(doc, 4)
    assert hit is not None
    media, src = hit
    assert media == "m1"
    assert src == pytest.approx(4, abs=0.02)
    jumped = E.source_time(doc, 10)
    assert jumped is not None and jumped[1] == pytest.approx(22, abs=0.02)
    later = E.source_time(doc, 20)
    assert later is not None and later[1] == pytest.approx(50, abs=0.05)


def test_import_lays_clips_end_to_end(home):
    view = E.write_import("cut1", "A film", [("c01.mp4", 3.0, "Hook"), ("c02.mp4", 2.5, "Payoff")])
    main = next(t for t in view["tracks"] if t["role"] == "main")
    assert [i["at"] for i in main["items"]] == pytest.approx([0, 3], abs=0.02)
    assert main["items"][1]["dur"] == pytest.approx(2.5, abs=0.02)
    assert main["items"][0]["file"] == "c01.mp4"
    assert view["summary"].startswith("Opened")


def test_import_refuses_a_film_outside_the_library(home):
    with pytest.raises(E.EditorError):
        E.import_run("not-a-library-film")
