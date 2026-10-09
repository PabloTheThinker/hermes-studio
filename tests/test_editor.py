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


def test_canvas_desktop_undo_and_reject(home):
    E.create("demo")
    desk = E.set_canvas("demo", 1920, 1080)
    assert desk["size"] == [1920, 1080]
    back = E.undo("demo")
    assert back["size"] == [1080, 1920]
    with pytest.raises(E.EditorError):
        E.set_canvas("demo", 0, 1080)


def test_import_refuses_a_film_outside_the_library(home):
    with pytest.raises(E.EditorError):
        E.import_run("not-a-library-film")


def _make_source(dest, seconds: float = 6.0) -> None:
    """A real file with picture and sound, so the render has something true to read."""
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=320x180:rate=30:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )


def _project(home, pid: str = "cut", *, canvas=(1280, 720)):
    folder = E._dir(pid)
    _make_source(folder / "media" / "talk.mp4")
    s = T.TICK_RATE
    d = T.new_timeline(pid, size=canvas)
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/talk.mp4", "dur": 6 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [
        {"id": "c1", "type": "clip", "media": "m1", "src": [0, 2 * s], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "c2", "type": "clip", "media": "m1", "src": [3 * s, 6 * s], "at": 2 * s, "fade_in": 0, "fade_out": 0},
    ]
    by["A1"]["items"] = [{"id": "a1", "type": "clip", "media": "m1", "src": [0, 4 * s], "at": 0, "fade_in": 0, "fade_out": 0}]
    by["T1"]["items"] = [
        {"id": "x1", "type": "text", "dur": 2 * s, "text": "Hello Sir", "style": "pop", "fade_in": 0, "fade_out": 0, "at": 0}
    ]
    d, _ = T.stamp_hash(d)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as O

    log = O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)
    return pid


def test_render_writes_a_real_file_at_the_canvas_size(home):
    import subprocess

    from hermes_studio import render_timeline as R

    pid = _project(home)
    out = R.render_project(pid)
    assert out["ok"]
    path = home / pid / f"{pid}-render.mp4"
    assert path.is_file() and path.stat().st_size > 1024
    assert out["size"] == [1280, 720]
    # c1 runs 0-2, c2 runs 2-5, so the cut is 5s long (voice ends at 4s and must not shorten it)
    assert out["duration"] == pytest.approx(5, abs=0.05)
    assert out["captions"] is True
    # the file itself agrees, not just the report
    info = (
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            text=True,
        )
        .strip()
        .splitlines()[0]
    )
    w, h, dur = info.split(",")
    assert (int(w), int(h)) == (1280, 720)
    assert float(dur) == pytest.approx(5, abs=0.1)


def test_render_keeps_sound_where_the_timeline_puts_it(home):
    import subprocess

    from hermes_studio import render_timeline as R

    pid = _project(home)
    out = R.render_project(pid)
    assert out["ok"]
    frames = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            out["path"],
        ],
        text=True,
    ).strip()
    assert int(frames) > 100


def test_render_refuses_a_project_that_is_not_there(home):
    from hermes_studio import render_timeline as R

    with pytest.raises(E.EditorError):
        R.render_project("nope")


def test_render_refuses_an_empty_main_track(home):
    from hermes_studio import render_timeline as R

    folder = E._dir("empty")
    folder.mkdir(parents=True)
    d = T.new_timeline("empty")
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    with pytest.raises(R.RenderError):
        R.render_project("empty")


def test_render_rejects_a_bad_canvas(home):
    from hermes_studio import render_timeline as R

    pid = _project(home)
    plan = R._build_plan(E._log(E._dir(pid)).doc, E._dir(pid))
    plan["width"] = 0  # a canvas the op log would never have written, caught here anyway
    with pytest.raises(R.RenderError):
        R._build_graph(plan, None)
