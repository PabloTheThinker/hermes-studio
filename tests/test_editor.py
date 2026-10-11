"""Edit page store: create, trim, split, undo, redo. The op log is the writer."""

from __future__ import annotations

import subprocess
import json

import opentimelineio as otio
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


def test_canvas_phone_undo_and_reject(home):
    """Desktop is the default now, so the undo check goes the other way: set Phone, undo back to Desktop."""
    E.create("demo")
    assert E.open_project("demo")["size"] == [1920, 1080]
    desk = E.set_canvas("demo", 1080, 1920)
    assert desk["size"] == [1080, 1920]
    back = E.undo("demo")
    assert back["size"] == [1920, 1080]
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


def test_transcript_is_empty_before_any_words(home):
    assert E.transcript("cut2") == [] if (E._dir("cut2") / "base.json").exists() else True
    folder = E._dir("cut2")
    folder.mkdir(parents=True, exist_ok=True)
    d = T.new_timeline("cut2")
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    assert E.transcript("cut2") == []


def test_transcript_keeps_only_words_inside_the_cut(home):
    folder = E._dir("cut3")
    folder.mkdir(parents=True, exist_ok=True)
    d = T.new_timeline("cut3")
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    run = folder / "run"
    (run / "work").mkdir(parents=True, exist_ok=True)
    (run / "work" / "transcript.json").write_text(
        json.dumps(
            {
                "words": [
                    {"text": "before", "start": 0.0, "end": 1.0},
                    {"text": "inside", "start": 1.5, "end": 2.0},
                    {"text": "after", "start": 9.0, "end": 10.0},
                ]
            }
        )
    )
    E._copy_transcript(run, folder / "transcript.json", [{"start": 0.0, "end": 3.0}])
    got = E.transcript("cut3")
    assert [w["text"] for w in got] == ["before", "inside"]


def test_transcript_stacks_words_across_clips(home):
    folder = E._dir("cut4")
    folder.mkdir(parents=True, exist_ok=True)
    d = T.new_timeline("cut4")
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    run = folder / "run"
    (run / "work").mkdir(parents=True, exist_ok=True)
    (run / "work" / "transcript.json").write_text(
        json.dumps({"words": [{"text": "one", "start": 0.5, "end": 1.0}, {"text": "two", "start": 4.0, "end": 5.0}]})
    )
    E._copy_transcript(run, folder / "transcript.json", [{"start": 0.0, "end": 2.0}, {"start": 4.0, "end": 6.0}])
    got = E.transcript("cut4")
    # clip 1 keeps source 0-2s ("one" at 0.5); clip 2 is source 4-6s ("two" at 4.0 -> 0.0 in clip)
    assert [w["text"] for w in got] == ["one", "two"]
    assert got[0]["start"] == pytest.approx(0.5, abs=0.01)
    assert got[1]["start"] == pytest.approx(2.0, abs=0.01)
    assert got[1]["end"] == pytest.approx(3.0, abs=0.01)


def test_transcript_refuses_a_project_that_is_not_there(home):
    with pytest.raises(E.EditorError):
        E.transcript("nope")


def test_an_imported_cut_has_a_real_history(home, monkeypatch):
    """An imported film must be undoable from the first edit, not only after one happens."""
    from hermes_studio import oplog as O

    folder = E._dir("imp1")
    (folder / "media").mkdir(parents=True, exist_ok=True)
    d = T.new_timeline("imp1")
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/c01.mp4", "dur": 4 * T.TICK_RATE, "fps": [30, 1]}}
    by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 4 * T.TICK_RATE], "at": 0, "fade_in": 0, "fade_out": 0}]
    d, _ = T.stamp_hash(d)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "base.json").write_text(json.dumps(d))
    E._dir("imp1")
    log = O.Oplog(d, path=folder / "oplog.jsonl")
    (folder / "oplog.jsonl").touch(exist_ok=True)
    E._save_current(folder, log.doc)

    assert (folder / "oplog.jsonl").is_file()
    split = E.split("imp1", "c1", 2.0)
    assert split["version"] == 1
    back = E.undo("imp1")
    assert back["version"] == 2
    assert len(E._log(folder).history_list()) == 2


def _two_clips(home, pid="tc"):
    """A project with two adjacent clips on the main track, for transition tests."""
    import json as _json

    from hermes_studio import oplog as _O

    folder = E._dir(pid)
    folder.mkdir(parents=True, exist_ok=True)
    d = T.new_timeline(pid)
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/talk.mp4", "dur": 60 * T.TICK_RATE, "fps": [30, 1]}}
    by["V1"]["items"] = [
        {"id": "aa", "type": "clip", "media": "m1", "src": [0, 8 * T.TICK_RATE], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "bb", "type": "clip", "media": "m1", "src": [0, 8 * T.TICK_RATE], "at": 8 * T.TICK_RATE, "fade_in": 0, "fade_out": 0},
    ]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(_json.dumps(d))
    log = _O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)
    return pid


def _main(v):
    return [t for t in v["tracks"] if t["role"] == "main"][0]["items"]


def _tr_of(pid):
    """The transition item on a project's main track (the engine stores ticks)."""
    return next(i for t in E._log(E._dir(pid)).doc["tracks"] for i in t["items"] if i["type"] == "transition")


def test_transition_overlaps_clips_and_undo_restores(home):
    pid = _two_clips(home)
    v = E.set_transition(pid, "aa", "bb", 1.0)
    rows = _main(v)
    bb = next(i for i in rows if i["id"] == "bb")
    # a 1s dissolve pulls bb back to 7s so the two overlap by exactly 1s
    assert bb["at"] == pytest.approx(7.0, abs=0.02)
    assert any(i["type"] == "transition" for i in rows)
    tr = next(i for i in rows if i["type"] == "transition")
    assert tr["between"] == ["aa", "bb"] and tr["dur"] == pytest.approx(1.0, abs=0.02)
    back = E.undo(pid)
    bb = next(i for i in _main(back) if i["id"] == "bb")
    assert bb["at"] == pytest.approx(8.0, abs=0.02)
    assert not any(i["type"] == "transition" for i in _main(back))


def test_transition_zero_is_a_hard_cut(home):
    pid = _two_clips(home)
    E.set_transition(pid, "aa", "bb", 1.0)
    v = E.set_transition(pid, "aa", "bb", 0.0)
    rows = _main(v)
    bb = next(i for i in rows if i["id"] == "bb")
    assert bb["at"] == pytest.approx(8.0, abs=0.02)
    assert not any(i["type"] == "transition" for i in rows)


def test_transition_rejects_too_long_or_wrong_order(home):
    pid = _two_clips(home)
    with pytest.raises(E.EditorError):
        E.set_transition(pid, "aa", "bb", 99.0)  # longer than the clips
    with pytest.raises(E.EditorError):
        E.set_transition(pid, "bb", "aa", 1.0)   # wrong order
    with pytest.raises(E.EditorError):
        E.set_transition(pid, "aa", "aa", 1.0)   # same clip twice


def test_render_applies_a_dissolve_not_a_hard_cut(home):
    """A cross-dissolve must actually blend: the mid-seam frame mixes both clips."""
    import subprocess

    from hermes_studio import render_timeline as R

    folder = E._dir("xd")
    (folder / "media").mkdir(parents=True, exist_ok=True)
    for col, name, freq in (("red", "ra", 440), ("blue", "bl", 660)):
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={col}:s=320x180:d=4:r=30",
             "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=4",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
             str(folder / "media" / f"{name}.mp4")],
            check=True, capture_output=True,
        )
    s = T.TICK_RATE
    d = T.new_timeline("xd")
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/ra.mp4", "dur": 4 * s, "fps": [30, 1]},
                  "m2": {"path": "media/bl.mp4", "dur": 4 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [
        {"id": "aa", "type": "clip", "media": "m1", "src": [0, 4 * s], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "bb", "type": "clip", "media": "m2", "src": [0, 4 * s], "at": 4 * s, "fade_in": 0, "fade_out": 0},
    ]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as _O

    log = _O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)
    E.set_transition("xd", "aa", "bb", 1.0)

    out = R.render_project("xd")
    # 4 + 4 - 1 (the overlap) = 7s
    assert out["duration"] == pytest.approx(7.0, abs=0.1)

    def avg_rgb(at: float):  # noqa: D401
        jpg = folder / f"_probe_{at}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", out["path"],
                        "-frames:v", "1", str(jpg)], check=True, capture_output=True)
        from PIL import Image

        im = Image.open(jpg).convert("RGB").resize((8, 8))
        px = list(im.getdata())
        n = len(px)
        return tuple(sum(p[c] for p in px) // n for c in range(3))

    early, mid, late = avg_rgb(1.0), avg_rgb(3.5), avg_rgb(5.0)
    # early is red-dominant, late is blue-dominant
    assert early[0] > early[2]
    assert late[2] > late[0]
    # mid-blend carries BOTH red and blue: that is the dissolve, not a hard cut
    assert mid[0] > 40 and mid[2] > 40


def test_render_honors_clip_speed(home):
    """props.speed must change how long a clip occupies on the timeline."""
    import subprocess

    from hermes_studio import render_timeline as R

    s = T.TICK_RATE

    def build(speed_pair, pid):
        folder = E._dir(pid)
        _make_source(folder / "media" / "talk.mp4")
        d = T.new_timeline(pid)
        by = {t["id"]: t for t in d["tracks"]}
        d["media"] = {"m1": {"path": "media/talk.mp4", "dur": 6 * s, "fps": [30, 1]}}
        props = {} if speed_pair is None else {"speed": speed_pair}
        by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 6 * s], "at": 0, "fade_in": 0, "fade_out": 0, "props": props}]
        d, _ = T.stamp_hash(d)
        (folder / "base.json").write_text(json.dumps(d))
        from hermes_studio import oplog as _O

        log = _O.Oplog(d, path=folder / "oplog.jsonl")
        E._save_current(folder, log.doc)
        return folder

    def file_dur(out):
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=nb_read_frames,duration", "-of", "default=nw=1", out["path"]],
            capture_output=True, text=True,
        )
        vals = dict(l.split("=", 1) for l in p.stdout.strip().split("\n") if "=" in l)
        return float(vals["duration"])

    # A 6s source at 1x, 2x, 4x should occupy 6, 3, 1.5 seconds on the timeline.
    for pair, expect in ((None, 6.0), ([2, 1], 3.0), ([4, 1], 1.5)):
        pid = f"sp{expect:.1f}".replace(".", "_")
        build(pair, pid)
        out = R.render_project(pid)
        assert out["duration"] == pytest.approx(expect, abs=0.05)
        assert file_dur(out) == pytest.approx(expect, abs=0.15)


def test_set_speed_drops_a_transition_that_would_break(home):
    """Retiming a clip resets any dissolve on its seam, because the overlap can't survive
    a length change. The dissolve is dropped to a hard cut, not left to fail validation."""
    pid = _two_clips(home, "spd_xf")
    E.set_transition(pid, "aa", "bb", 1.0)
    v = E.open_project(pid)
    main = [t for t in v["tracks"] if t["role"] == "main"][0]["items"]
    assert any(i["type"] == "transition" for i in main)

    v = E.set_speed(pid, "aa", 2.0)
    main = [t for t in v["tracks"] if t["role"] == "main"][0]["items"]
    aa = next(i for i in main if i["id"] == "aa")
    # aa's 8s source at 2x now occupies 4s, and the dissolve is gone (hard cut).
    assert aa["dur"] == pytest.approx(4.0, abs=0.02)
    assert not any(i["type"] == "transition" for i in main)


def test_set_speed_refuses_out_of_range_and_undoes(home):
    pid = _two_clips(home, "spd_range")
    for bad in (0.05, 50.0):
        with pytest.raises(E.EditorError):
            E.set_speed(pid, "aa", bad)
    # 2x is legal and undoable; aa's 8s source now occupies 4s.
    v = E.set_speed(pid, "aa", 2.0)
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["dur"] == pytest.approx(4.0, abs=0.02)
    back = E.undo(pid)
    aa = next(i for i in [t for t in back["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["dur"] == pytest.approx(8.0, abs=0.02)


def test_render_applies_crop_and_look(home):
    """props.crop and props.look are in the schema; the render must honour both."""
    import subprocess

    from hermes_studio import render_timeline as R

    def make(props, pid):
        folder = E._dir(pid)
        _make_source(folder / "media" / "talk.mp4")
        s = T.TICK_RATE
        d = T.new_timeline(pid)
        by = {t["id"]: t for t in d["tracks"]}
        d["media"] = {"m1": {"path": "media/talk.mp4", "dur": 6 * s, "fps": [30, 1]}}
        by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 6 * s], "at": 0, "fade_in": 0, "fade_out": 0, "props": props}]
        d, _ = T.stamp_hash(d)
        (folder / "base.json").write_text(json.dumps(d))
        from hermes_studio import oplog as _O

        log = _O.Oplog(d, path=folder / "oplog.jsonl")
        E._save_current(folder, log.doc)

    def rgb(out, at=1.5):
        from pathlib import Path

        jpg = Path(str(out["path"]) + f"_p{at}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", out["path"], "-frames:v", "1", str(jpg)], check=True, capture_output=True)
        from PIL import Image

        im = Image.open(jpg).convert("RGB").resize((8, 8))
        px = list(im.getdata())
        n = len(px)
        return tuple(sum(p[c] for p in px) // n for c in range(3))

    # Crop is a [num, den] pair per the schema. Left half vs right half must differ.
    make({"crop": {"x": [0, 1], "y": [0, 1], "w": [1, 2], "h": [1, 1]}}, "cropL")
    make({"crop": {"x": [1, 2], "y": [0, 1], "w": [1, 2], "h": [1, 1]}}, "cropR")
    left, right = rgb(R.render_project("cropL")), rgb(R.render_project("cropR"))
    assert left != right
    # A cropped clip also fills the frame from its crop, so the graph carries a crop=
    # filter; an ungraded clip carries none.
    make({}, "plain2")
    for pid, expect_crop in (("cropL", True), ("plain2", False)):
        plan = R._build_plan(E._log(E._dir(pid)).doc, E._dir(pid))
        plan["cache"] = str(E._dir(pid) / "cache")
        graph, _ = R._build_graph(plan, None)
        assert ("crop=" in graph) is expect_crop

    # mono is a real grade: a legacy props.look renders as its grade.LOOKS preset, whose
    # saturation 0 is a colorchannelmixer (the old eq chains are gone).
    make({"look": "mono"}, "mono2")
    mplan = R._build_plan(E._log(E._dir("mono2")).doc, E._dir("mono2"))
    mplan["cache"] = str(E._dir("mono2") / "cache")
    mgraph, _ = R._build_graph(mplan, None)
    assert "colorchannelmixer=" in mgraph and "eq=" not in mgraph


def test_render_fades_video_to_and_from_black(home):
    """fade_in/fade_out must affect the picture, not just the audio. A white source with
    1s fades opens and closes near black and is full white in the middle."""
    import subprocess

    from hermes_studio import render_timeline as R

    folder = E._dir("vfade")
    (folder / "media").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=4:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
         str(folder / "media" / "v.mp4")],
        check=True, capture_output=True,
    )
    s = T.TICK_RATE
    d = T.new_timeline("vfade")
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/v.mp4", "dur": 4 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 4 * s], "at": 0, "fade_in": 1 * s, "fade_out": 1 * s}]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as _O

    log = _O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)

    out = R.render_project("vfade")

    def luma(at):
        from pathlib import Path

        from PIL import Image

        jpg = Path(str(out["path"]) + f"_f{at}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", out["path"], "-frames:v", "1", str(jpg)], check=True, capture_output=True)
        im = Image.open(jpg).convert("L").resize((8, 8))
        px = list(im.getdata())
        return sum(px) // len(px)

    assert luma(2.0) > 220          # full white in the middle
    assert luma(0.1) < 80           # near black at the start (fading in)
    assert luma(3.9) < 80           # near black at the end (fading out)


def test_render_honors_audio_volume(home):
    """props.volume sets a clip's audio level. Because loudnorm auto-levels to a target,
    it must stand aside once any volume is hand-set, or every render lands at the same level."""
    import subprocess

    from hermes_studio import render_timeline as R

    def make(vol_pair, pid):
        folder = E._dir(pid)
        (folder / "media").mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=2:r=30",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
             str(folder / "media" / "v.mp4")],
            check=True, capture_output=True,
        )
        s = T.TICK_RATE
        d = T.new_timeline(pid)
        by = {t["id"]: t for t in d["tracks"]}
        d["media"] = {"m1": {"path": "media/v.mp4", "dur": 2 * s, "fps": [30, 1]}}
        by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 2 * s], "at": 0, "fade_in": 0, "fade_out": 0}]
        props = {} if vol_pair is None else {"volume": vol_pair}
        by["A2"]["items"] = [{"id": "a1", "type": "clip", "media": "m1", "src": [0, 2 * s], "at": 0, "fade_in": 0, "fade_out": 0, "props": props}]
        d, _ = T.stamp_hash(d)
        (folder / "base.json").write_text(json.dumps(d))
        from hermes_studio import oplog as _O

        log = _O.Oplog(d, path=folder / "oplog.jsonl")
        E._save_current(folder, log.doc)

    def mean_db(out):
        r = subprocess.run(["ffmpeg", "-i", out["path"], "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        for line in r.stderr.split("\n"):
            if "mean_volume" in line:
                return float(line.split(":")[1].strip().replace(" dB", ""))
        raise AssertionError("no volume reported")

    make([1, 1], "vfull")
    make([1, 2], "vhalf")
    full, half = mean_db(R.render_project("vfull")), mean_db(R.render_project("vhalf"))
    # A halved volume must actually come out quieter (roughly -6 dB), which only holds if
    # loudnorm stood aside for the hand-set clip.
    assert half < full - 3.0


def test_look_and_volume_round_trip_and_validate(home):
    pid = _two_clips(home, "lookvol")
    # A named look applies and shows back in the view; an unknown one is refused.
    v = E.set_look(pid, "aa", "film")
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["look"] == "film"
    with pytest.raises(E.EditorError):
        E.set_look(pid, "aa", "vaporwave")
    # Clearing it works.
    v = E.set_look(pid, "aa", None)
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["look"] is None
    # Volume 0.5 stores and reads back as ~0.5; out of range is refused; undo restores.
    v = E.set_volume(pid, "aa", 0.5)
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["volume"] == pytest.approx(0.5, abs=0.01)
    with pytest.raises(E.EditorError):
        E.set_volume(pid, "aa", 9.0)
    back = E.undo(pid)
    aa = next(i for i in [t for t in back["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["volume"] == pytest.approx(1.0, abs=0.01)


def test_set_fade_round_trips(home):
    pid = _two_clips(home, "fadectl")
    v = E.set_fade(pid, "aa", fade_in=1.0, fade_out=0.5)
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["fade_in"] == pytest.approx(1.0, abs=0.02)
    assert aa["fade_out"] == pytest.approx(0.5, abs=0.02)
    back = E.undo(pid)
    aa = next(i for i in [t for t in back["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["fade_in"] == 0 and aa["fade_out"] == 0


def test_set_crop_round_trips_and_validates(home):
    pid = _two_clips(home, "cropctl")
    v = E.set_crop(pid, "aa", 0.0, 0.0, 0.5, 1.0)  # left half
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["crop"] == {"x": 0.0, "y": 0.0, "w": 0.5, "h": 1.0}
    # clearing it back to the full frame removes the crop
    v = E.set_crop(pid, "aa", 0, 0, 1, 1)
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["crop"] is None
    # an out-of-frame box is refused
    for bad in ((0.8, 0, 0.5, 1), (0, 0, 1.5, 1), (-0.1, 0, 1, 1)):
        with pytest.raises(E.EditorError):
            E.set_crop(pid, "aa", *bad)


def test_render_applies_transform(home):
    """props.transform repositions, scales, and rotates the picture. Identity must be a
    no-op (identical to no transform); zoom-out must letterbox with black; pan must move."""
    import subprocess

    from hermes_studio import render_timeline as R

    folder = E._dir("tfbase")
    (folder / "media").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "smptebars=s=320x180:d=3:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
         str(folder / "media" / "v.mp4")],
        check=True, capture_output=True,
    )
    s = T.TICK_RATE

    def build(tf, pid):
        d = T.new_timeline(pid, size=(320, 180))
        by = {t["id"]: t for t in d["tracks"]}
        d["media"] = {"m1": {"path": "media/v.mp4", "dur": 3 * s, "fps": [30, 1]}}
        props = {} if tf is None else {"transform": tf}
        by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 3 * s], "at": 0, "fade_in": 0, "fade_out": 0, "props": props}]
        d, _ = T.stamp_hash(d)
        f = E._dir(pid)
        (f / "media").mkdir(parents=True, exist_ok=True)
        import shutil as sh

        sh.copy(folder / "media" / "v.mp4", f / "media" / "v.mp4")
        (f / "base.json").write_text(json.dumps(d))
        from hermes_studio import oplog as _O

        log = _O.Oplog(d, path=f / "oplog.jsonl")
        E._save_current(f, log.doc)

    def frame(path, at=1.0):
        from pathlib import Path

        from PIL import Image

        jpg = Path(str(path) + f"_t{at}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", path, "-frames:v", "1", str(jpg)], check=True, capture_output=True)
        im = Image.open(jpg).convert("RGB")
        W, H = im.size
        return {"TL": im.getpixel((int(0.1 * W), int(0.1 * H))), "C": im.getpixel((W // 2, H // 2))}

    def pair(d):
        return {k: tuple(v) for k, v in d.items()}

    build(None, "tf_none")
    build({"x": [0, 1], "y": [0, 1], "scale": [1, 1], "rotate": [0, 1]}, "tf_id")
    none, ident = frame(R.render_project("tf_none")["path"]), frame(R.render_project("tf_id")["path"])
    assert pair(none) == pair(ident)  # identity is a true no-op

    # Zoom out to 0.5x: the corners go black (letterbox), the centre keeps picture.
    build({"x": [0, 1], "y": [0, 1], "scale": [1, 2], "rotate": [0, 1]}, "tf_out")
    zout = frame(R.render_project("tf_out")["path"])
    assert zout["TL"] == (0, 0, 0)
    assert sum(zout["C"]) > 60  # centre still has picture


def test_set_transform_round_trips_and_validates(home):
    pid = _two_clips(home, "tftest")
    v = E.set_transform(pid, "aa", scale=1.5, x=0.1, y=-0.2, rotate=45)
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["transform"]["scale"] == pytest.approx(1.5, abs=0.01)
    assert aa["transform"]["x"] == pytest.approx(0.1, abs=0.01)
    assert aa["transform"]["y"] == pytest.approx(-0.2, abs=0.01)
    assert aa["transform"]["rotate"] == pytest.approx(45, abs=0.01)
    # identity clears it
    v = E.set_transform(pid, "aa")
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["transform"] is None
    # out-of-range refusals
    for kw in ({"scale": 0}, {"scale": 500}, {"x": 10}, {"rotate": 9999}):
        with pytest.raises(E.EditorError):
            E.set_transform(pid, "aa", **kw)
    # undo restores
    E.set_transform(pid, "aa", scale=2.0)
    back = E.undo(pid)
    aa = next(i for i in [t for t in back["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["transform"] is None


def test_render_animates_keyframes(home):
    """A keyframe track must actually animate: frames early and late in a scale 1->2 push
    must differ from each other (and from the static source), proving the value moves over
    time rather than snapping to one value."""
    import subprocess

    from hermes_studio import render_timeline as R

    folder = E._dir("kfanim")
    (folder / "media").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "smptebars=s=640x360:d=4:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
         str(folder / "media" / "v.mp4")],
        check=True, capture_output=True,
    )
    s = T.TICK_RATE
    kfs = [
        {"at": 0, "x": [0, 1], "y": [0, 1], "scale": [1, 1], "rotate": [0, 1]},
        {"at": 4 * s, "x": [0, 1], "y": [0, 1], "scale": [2, 1], "rotate": [0, 1]},
    ]
    d = T.new_timeline("kfanim", size=(640, 360))
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/v.mp4", "dur": 4 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 4 * s], "at": 0, "fade_in": 0, "fade_out": 0, "props": {"keyframes": kfs}}]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as _O

    log = _O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)

    out = R.render_project("kfanim")
    assert "zoompan" in R._build_graph(R._build_plan(E._log(folder).doc, folder), None)[0]

    def topband(path, at):
        from pathlib import Path

        from PIL import Image

        jpg = Path(str(path) + f"_a{at}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", path, "-frames:v", "1", str(jpg)], check=True, capture_output=True)
        im = Image.open(jpg).convert("RGB")
        W, H = im.size
        return [im.getpixel((x, H // 4)) for x in range(0, W, 3)]

    early, late = topband(out["path"], 0.2), topband(out["path"], 3.6)
    # A real animation changes the pixels between early and late; a snapped/static value
    # (or a keyframe track the render ignored) would leave them identical.
    assert early != late


def test_set_keyframes_round_trips_and_validates(home):
    pid = _two_clips(home, "kfset")
    v = E.set_keyframes(pid, "aa", [
        {"at": 0.0, "x": 0, "y": 0, "scale": 1, "rotate": 0},
        {"at": 4.0, "x": 0, "y": 0, "scale": 2, "rotate": 0},
    ])
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    kfs = aa["keyframes"]
    assert len(kfs) == 2
    assert kfs[0]["at"] == pytest.approx(0.0, abs=0.01) and kfs[0]["scale"] == pytest.approx(1.0, abs=0.01)
    assert kfs[1]["at"] == pytest.approx(4.0, abs=0.01) and kfs[1]["scale"] == pytest.approx(2.0, abs=0.01)
    # a single keyframe (or none) clears the animation
    v = E.set_keyframes(pid, "aa", [{"at": 0.0, "x": 0, "y": 0, "scale": 1, "rotate": 0}])
    aa = next(i for i in [t for t in v["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["keyframes"] is None
    # out-of-order times and bad scale are refused
    with pytest.raises(E.EditorError):
        E.set_keyframes(pid, "aa", [{"at": 4.0, "scale": 1}, {"at": 1.0, "scale": 1}])
    with pytest.raises(E.EditorError):
        E.set_keyframes(pid, "aa", [{"at": 0.0, "scale": 1}, {"at": 2.0, "scale": 0}])
    # undo restores
    E.set_keyframes(pid, "aa", [{"at": 0.0, "scale": 1}, {"at": 2.0, "scale": 2}])
    back = E.undo(pid)
    aa = next(i for i in [t for t in back["tracks"] if t["role"] == "main"][0]["items"] if i["id"] == "aa")
    assert aa["keyframes"] is None


def test_waveform_reads_the_real_sound_and_caches_it(home):
    pid = _project(home, "wave")
    w = E.waveform(pid, "m1")
    assert w["rate"] == E.WAVE_RATE and w["silent"] is False
    assert abs(len(w["peaks"]) - 6 * E.WAVE_RATE) <= 3  # 6s source, 50 peaks a second
    mid = w["peaks"][25:-25]
    # ffmpeg's sine source plays at 1/8 full scale: a steady tone draws a steady ~125/1000.
    assert min(mid) > 80 and max(mid) < 200
    cache = E._dir(pid) / "waves" / "m1.json"
    assert cache.is_file()
    assert E.waveform(pid, "m1") == w  # second read comes from the cache, same peaks


def test_waveform_of_a_missing_file_is_silent_and_a_bad_id_refused(home):
    pid = _project(home, "wave2")
    (E._dir(pid) / "media" / "talk.mp4").unlink()
    assert E.waveform(pid, "m1") == {"media": "m1", "rate": E.WAVE_RATE, "peaks": [], "silent": True}
    with pytest.raises(E.EditorError):
        E.waveform(pid, "nope")
    with pytest.raises(E.EditorError):
        E.waveform("not-here", "m1")


def test_view_tells_the_page_which_media_a_clip_plays(home):
    pid = _project(home, "wave3")
    v = E.view(E._log(E._dir(pid)).doc)
    a1 = next(t for t in v["tracks"] if t["id"] == "A1")["items"][0]
    assert a1["media"] == "m1"


# ---------------------------------------------------------------- track mixer (mute / solo / gain)


def _mixer_cut(pid: str, *, extra_voice: bool = False) -> str:
    """V1 picture 0-4s. A1 voice: a 440 Hz tone over 0-2s. A2 music: the same tone over 2-4s.
    With extra_voice, the voice clip lives on a SECOND voice track (A3) instead, which the
    render used to drop because it only read the first track of each role."""
    import subprocess

    folder = E._dir(pid)
    (folder / "media").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=4:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
         str(folder / "media" / "v.mp4")],
        check=True, capture_output=True,
    )
    s = T.TICK_RATE
    d = T.new_timeline(pid)
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/v.mp4", "dur": 4 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 4 * s], "at": 0, "fade_in": 0, "fade_out": 0}]
    voice = [{"id": "a1", "type": "clip", "media": "m1", "src": [0, 2 * s], "at": 0, "fade_in": 0, "fade_out": 0}]
    if extra_voice:
        i = next(n for n, t in enumerate(d["tracks"]) if t["id"] == "A1")
        d["tracks"].insert(i + 1, {"id": "A3", "role": "voice", "items": voice})
    else:
        by["A1"]["items"] = voice
    by["A2"]["items"] = [{"id": "m2", "type": "clip", "media": "m1", "src": [2 * s, 4 * s], "at": 2 * s, "fade_in": 0, "fade_out": 0}]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as _O

    log = _O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)
    return pid


def _window_db(path: str, start: float, end: float) -> float:
    """Peak level (dB) of the rendered file's sound between start and end seconds."""
    import subprocess

    r = subprocess.run(
        ["ffmpeg", "-i", path, "-af", f"atrim={start}:{end},volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    for line in r.stderr.split("\n"):
        if "max_volume" in line:
            return float(line.split(":")[1].strip().replace(" dB", ""))
    raise AssertionError("no volume reported")


def test_set_track_mute_solo_gain_round_trip_and_undo(home):
    pid = _mixer_cut("mx")
    v = E.set_track(pid, "A1", mute=True, gain=0.5)
    a1 = next(t for t in v["tracks"] if t["id"] == "A1")
    assert a1["mute"] is True and a1["gain"] == 0.5 and a1["solo"] is False
    raw = next(t for t in E._log(E._dir(pid)).doc["tracks"] if t["id"] == "A1")
    assert raw["mute"] is True and raw["gain"] == [1, 2]
    # Back to unity: the field is removed, not stored as [1, 1], so the doc hashes as untouched.
    E.set_track(pid, "A1", mute=False, gain=1.0)
    raw = next(t for t in E._log(E._dir(pid)).doc["tracks"] if t["id"] == "A1")
    assert "mute" not in raw and "gain" not in raw
    E.undo(pid)
    raw = next(t for t in E._log(E._dir(pid)).doc["tracks"] if t["id"] == "A1")
    assert raw["mute"] is True and raw["gain"] == [1, 2]
    E.undo(pid)
    raw = next(t for t in E._log(E._dir(pid)).doc["tracks"] if t["id"] == "A1")
    assert "mute" not in raw and "gain" not in raw


def test_set_track_refuses_the_main_track_and_bad_gain(home):
    pid = _mixer_cut("mx2")
    for bad in (lambda: E.set_track(pid, "V1", mute=True), lambda: E.set_track(pid, "T1", solo=True),
                lambda: E.set_track(pid, "A1", gain=9.0), lambda: E.set_track(pid, "A1"),
                lambda: E.set_track(pid, "A9", mute=True)):
        with pytest.raises(E.EditorError):
            bad()


def test_render_honours_track_mute_and_solo(home):
    from hermes_studio import render_timeline as R

    pid = _mixer_cut("mx3")
    out = R.render_project(pid)["path"]
    assert _window_db(out, 0.2, 1.8) > -30 and _window_db(out, 2.2, 3.8) > -30  # voice, then music

    E.set_track(pid, "A1", mute=True)
    out = R.render_project(pid)["path"]
    assert _window_db(out, 0.2, 1.8) < -60  # voice muted: silence where it was
    assert _window_db(out, 2.2, 3.8) > -30  # music untouched
    E.undo(pid)

    E.set_track(pid, "A1", solo=True)
    out = R.render_project(pid)["path"]
    assert _window_db(out, 0.2, 1.8) > -30  # soloed voice plays
    assert _window_db(out, 2.2, 3.8) < -60  # everything not soloed is silent
    E.undo(pid)

    E.set_track(pid, "A1", mute=True)
    E.set_track(pid, "A2", mute=True)
    r = R.render_project(pid)
    assert _window_db(r["path"], 0.0, 4.0) < -60  # all muted: clean silence, not an error
    assert abs(r["duration"] - 4.0) < 0.1  # muting never changes how long the cut is


def test_render_track_gain_scales_the_level(home):
    from hermes_studio import render_timeline as R

    pid = _mixer_cut("mx4")
    E.set_track(pid, "A1", gain=0.5)
    half = _window_db(R.render_project(pid)["path"], 0.2, 1.8)
    E.set_track(pid, "A1", gain=0.25)
    quarter = _window_db(R.render_project(pid)["path"], 0.2, 1.8)
    assert 5.0 < half - quarter < 7.0  # halving the gain is -6 dB


def test_render_plays_a_second_voice_track(home):
    """It used to read only the first voice track; sound on A3 was dropped without a word."""
    from hermes_studio import render_timeline as R

    pid = _mixer_cut("mx5", extra_voice=True)
    out = R.render_project(pid)["path"]
    assert _window_db(out, 0.2, 1.8) > -30


@pytest.fixture()
def desk(home):
    import threading
    from http.server import ThreadingHTTPServer

    from hermes_studio.studio import StudioHandler

    srv = ThreadingHTTPServer(("127.0.0.1", 0), StudioHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def _post(port, path, body):
    import http.client

    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("POST", path, body=json.dumps(body).encode(),
              headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_desk_keeps_a_zero_volume_and_refuses_a_word(desk):
    """`float(body.get("volume") or 1)` turned a deliberate 0 into full volume."""
    pid = _mixer_cut("dz")
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "volume", "id": "a1", "volume": 0})
    assert st == 200
    a1 = next(i for t in res["project"]["tracks"] for i in t["items"] if i["id"] == "a1")
    assert a1["volume"] == 0.0
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "volume", "id": "a1", "volume": "loud"})
    assert st == 400 and "number" in res["error"]


def test_desk_track_op_sets_the_mixer_strip(desk):
    pid = _mixer_cut("dt")
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "track", "track": "A2", "solo": True, "gain": 0})
    assert st == 200
    a2 = next(t for t in res["project"]["tracks"] if t["id"] == "A2")
    assert a2["solo"] is True and a2["gain"] == 0.0  # gain 0 is silence, not "unset"
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "track", "track": "V1", "mute": True})
    assert st == 400


def test_splitting_a_clip_never_changes_how_loud_the_render_is(home):
    """The mix used to divide each stream's weight by the sum over ALL streams, so every split
    made the cut 6 dB quieter once a hand-set volume switched loudnorm off."""
    from hermes_studio import render_timeline as R

    pid = _mixer_cut("sp")
    E.set_volume(pid, "a1", 0.5)
    whole = _window_db(R.render_project(pid)["path"], 0.2, 1.8)
    E.split(pid, "a1", 0.7)
    two = [i["id"] for t in E.view(E._log(E._dir(pid)).doc)["tracks"] if t["id"] == "A1" for i in t["items"]]
    assert len(two) == 2
    E.split(pid, two[1], 1.4)
    after = _window_db(R.render_project(pid)["path"], 0.2, 1.8)
    assert abs(after - whole) < 0.5, (whole, after)


def test_desk_serves_sound_files_for_the_preview_mixer(desk):
    """Music tracks hold .mp3/.wav; the media route used to accept only video and label every
    file video/mp4 or video/webm, so the preview mixer could never fetch a music file."""
    import http.client
    import subprocess

    pid = _mixer_cut("snd")
    wav = E._dir(pid) / "media" / "bed.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", str(wav)],
                   check=True, capture_output=True)
    c = http.client.HTTPConnection("127.0.0.1", desk, timeout=20)
    c.request("GET", f"/api/editor/{pid}/media/bed.wav", headers={"Host": f"127.0.0.1:{desk}"})
    r = c.getresponse()
    body = r.read()
    assert r.status == 200 and r.getheader("Content-Type", "").startswith("audio/wav") and body[:4] == b"RIFF"
    c.request("GET", f"/api/editor/{pid}/media/v.mp4", headers={"Host": f"127.0.0.1:{desk}"})
    r = c.getresponse()
    r.read()
    assert r.status == 200 and r.getheader("Content-Type", "").startswith("video/mp4")
    for bad in ("x.exe", "../base.json", "..%2Fbase.json"):
        c.request("GET", f"/api/editor/{pid}/media/{bad}", headers={"Host": f"127.0.0.1:{desk}"})
        r = c.getresponse()
        r.read()
        assert r.status == 404, bad


def test_view_carries_the_exact_frame_rate_for_frame_steps_and_timecode(home):
    """The page steps one frame (arrows, K+J/L) and shows HH:MM:SS:FF from this. It stays a
    [num, den] pair so 30000/1001 doesn't drift the way a rounded float would."""
    pid = _mixer_cut("fps")
    assert E.view(E._log(E._dir(pid)).doc)["fps"] == [30, 1]
    d, _ = T.stamp_hash(T.new_timeline("ntsc", fps=(30000, 1001)))
    assert E.view(d)["fps"] == [30000, 1001]


def _probe(path: str) -> dict:
    import subprocess

    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames:format=duration", "-of", "json", path],
                       capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    return {"duration": float(d["format"]["duration"]), "frames": int(d["streams"][0]["nb_read_frames"])}


def test_render_an_in_out_range_is_that_stretch_of_the_full_render(home):
    """In/Out renders the marked range only. The trim runs after the mix and loudness, so the
    range sounds exactly like the same stretch of a full render. Voice (0-2s) and music (2-4s)
    sit ~9 dB apart, so a range that landed in the wrong place would read the wrong level."""
    from hermes_studio import render_timeline as R

    pid = _mixer_cut("rng")
    full = R.render_project(pid)["path"]
    voice_full, music_full = _window_db(full, 1.6, 1.9), _window_db(full, 2.2, 2.8)
    assert voice_full - music_full > 6  # the two are tellable apart

    import shutil

    shutil.copy(full, E._dir(pid) / "full.mp4")
    res = R.render_project(pid, start=1.5, end=3.0)
    assert res["range"] == [1.5, 3.0] and abs(res["duration"] - 1.5) < 1e-6
    p = _probe(res["path"])
    assert abs(p["duration"] - 1.5) < 0.05 and p["frames"] == 45  # 1.5 s at 30 fps, frame-exact
    assert abs(_window_db(res["path"], 0.1, 0.4) - voice_full) < 0.5  # 1.6-1.9 of the cut
    assert abs(_window_db(res["path"], 0.7, 1.3) - music_full) < 0.5  # 2.2-2.8 of the cut


def test_render_refuses_a_range_outside_the_cut(home):
    from hermes_studio import render_timeline as R

    pid = _mixer_cut("rng2")
    for start, end in ((-1, 2), (1, 9), (3, 2), (2, 2), (2, 2.01)):
        with pytest.raises(R.RenderError):
            R.render_project(pid, start=start, end=end)
    assert R.render_project(pid, start=3.0)["duration"] == 1.0  # In alone: to the end
    assert R.render_project(pid, end=0.5)["duration"] == 0.5  # Out alone: from the start


def test_desk_render_takes_the_in_and_out_marks(desk):
    pid = _mixer_cut("drng")
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "render", "in": 1, "out": 2.5})
    assert st == 200 and res["render"]["range"] == [1.0, 2.5]
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "render", "in": 3, "out": 1})
    assert st == 400 and "range" in res["error"]


# ---------------------------------------------------------------- volume envelope (rubber band)


def test_render_follows_a_volume_envelope(home):
    """Hold full level to 1.0s, ramp to 0.25 (-12 dB) by 1.2s, hold. The render must drop
    12 dB right there; without the envelope the two halves match."""
    from hermes_studio import render_timeline as R

    pid = _mixer_cut("gk")
    # The reference is a flat envelope (one key at 1.0): any envelope is a hand-set level, so it
    # takes the same no-loudnorm path, and the two renders compare like for like.
    E.set_gain_keys(pid, "a1", [{"at": 0, "gain": 1}])
    flat = R.render_project(pid)["path"]
    a, b = _window_db(flat, 0.2, 0.9), _window_db(flat, 1.4, 1.9)
    assert abs(a - b) < 1.0
    E.set_gain_keys(pid, "a1", [{"at": 0, "gain": 1}, {"at": 1.0, "gain": 1}, {"at": 1.2, "gain": 0.25}])
    out = R.render_project(pid)["path"]
    before, after = _window_db(out, 0.2, 0.9), _window_db(out, 1.4, 1.9)
    assert 11.0 < before - after < 13.0, (before, after)
    assert abs(before - a) < 1.0  # the envelope at 1.0 leaves the start untouched


def test_gain_keys_round_trip_validate_and_undo(home):
    pid = _mixer_cut("gk2")
    v = E.set_gain_keys(pid, "a1", [{"at": 0.5, "gain": 1}, {"at": 1.5, "gain": 0.5}])
    a1 = next(i for t in v["tracks"] for i in t["items"] if i["id"] == "a1")
    assert a1["gain_keys"] == [{"at": 0.5, "gain": 1.0}, {"at": 1.5, "gain": 0.5}]
    for bad in ([{"at": 1, "gain": 1}, {"at": 0.5, "gain": 1}],  # out of order
                [{"at": 1, "gain": 9}],  # too loud
                [{"at": 1}],  # no gain
                []):
        with pytest.raises(E.EditorError):
            E.set_gain_keys(pid, "a1", bad)
    E.undo(pid)
    a1 = next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "a1")
    assert a1["gain_keys"] is None
    E.set_gain_keys(pid, "a1", [{"at": 0, "gain": 0.5}])
    E.set_gain_keys(pid, "a1", None)
    a1 = next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "a1")
    assert a1["gain_keys"] is None


def test_undo_and_redo_walk_the_stack_like_every_editor(home):
    """Three edits; undo, undo, redo, redo must land back on the last edit. Redo used to undo
    its own redo (0.5 -> 0.25 -> 0.5), and an undo after a redo skipped the redone step."""
    pid = _mixer_cut("stack")

    def vol():
        return next(i["volume"] for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "a1")

    for v in (0.5, 0.25, 0.125):
        E.set_volume(pid, "a1", v)
    seen = []
    for step in ("undo", "undo", "redo", "redo"):
        getattr(E, step)(pid)
        seen.append(vol())
    assert seen == [0.25, 0.5, 0.25, 0.125]
    with pytest.raises(E.EditorError, match="nothing to redo"):
        E.redo(pid)
    # Undo after a redo takes back the redone step, not an older edit; then redo again.
    E.undo(pid)
    assert vol() == 0.25
    E.undo(pid)
    assert vol() == 0.5
    E.redo(pid)
    assert vol() == 0.25
    # A fresh edit after an undo clears the redo stack...
    E.undo(pid)
    E.set_volume(pid, "a1", 0.75)
    with pytest.raises(E.EditorError, match="nothing to redo"):
        E.redo(pid)
    # ...and undo still walks all the way back to the start.
    seen = []
    for _ in range(2):
        E.undo(pid)
        seen.append(vol())
    assert seen == [0.5, 1]
    with pytest.raises(E.EditorError, match="nothing to undo"):
        E.undo(pid)


# ---------------------------------------------------------------- markers


def _markers(pid):
    return E.view(E._log(E._dir(pid)).doc)["markers"]


def test_view_returns_markers_in_time_order_not_storage_order(home):
    """The op log only appends, so a marker dropped at 1.5s is stored before one at 0.5s.
    view() sorts them, which is the order the ruler and marker jumping need."""
    pid = _mixer_cut("mk3")
    E.add_marker(pid, 1.5, "late")
    E.add_marker(pid, 0.5, "early")
    by_label = {m["label"]: m["id"] for m in E.view(E._log(E._dir(pid)).doc)["markers"]}
    E.set_marker(pid, by_label["late"], at=3.25)
    assert [(m["at"], m["label"]) for m in _markers(pid)] == [(0.5, "early"), (3.25, "late")]
    # ...while the op log still holds them in insertion order.
    assert [m["at"] for m in E._log(E._dir(pid)).doc["markers"]] == [2293200000, 352800000]


def test_markers_add_move_rename_recolour_remove_and_undo(home):
    pid = _mixer_cut("mk")
    E.add_marker(pid, 1.5, "  Hook  ")
    E.add_marker(pid, 0.5, "", "red")
    m = _markers(pid)
    assert [(x["at"], x["label"], x["color"]) for x in m] == [(0.5, "", "red"), (1.5, "Hook", "blue")]
    hook = m[1]["id"]
    E.set_marker(pid, hook, at=3.0)
    E.set_marker(pid, hook, label="Payoff")
    E.set_marker(pid, hook, color="green")
    assert [(x["at"], x["label"], x["color"]) for x in _markers(pid)][-1] == (3.0, "Payoff", "green")
    # Blue is the default: setting it removes the field, so the doc is as if never coloured.
    E.set_marker(pid, hook, color="blue")
    raw = next(x for x in E._log(E._dir(pid)).doc["markers"] if x["id"] == hook)
    assert "color" not in raw
    for _ in range(4):
        E.undo(pid)
    assert [(x["at"], x["label"], x["color"]) for x in _markers(pid)][-1] == (1.5, "Hook", "blue")
    E.remove_marker(pid, hook)
    assert len(_markers(pid)) == 1
    E.undo(pid)
    assert len(_markers(pid)) == 2


def test_marker_values_are_checked(home):
    pid = _mixer_cut("mk2")
    v = E.add_marker(pid, 1.0, "x")
    mid = v["markers"][0]["id"]
    for bad in (lambda: E.add_marker(pid, -1), lambda: E.add_marker(pid, float("inf")),
                lambda: E.add_marker(pid, float("nan")), lambda: E.add_marker(pid, 1, "x", "teal"),
                lambda: E.add_marker(pid, 1, "x" * 201), lambda: E.set_marker(pid, mid),
                lambda: E.set_marker(pid, "nope", label="a"), lambda: E.set_marker(pid, mid, color="black")):
        with pytest.raises(E.EditorError):
            bad()
    assert len(_markers(pid)) == 1


def test_an_uncoloured_marker_keeps_the_old_hash_and_colour_survives_otio(home, tmp_path):
    from hermes_studio import timeline as T

    d = T.new_timeline("h")
    d["markers"] = [{"id": "k1", "at": 0, "label": "a"}]
    before = T.stamp_hash(d)[1]
    d2 = json.loads(json.dumps(d))
    d2["markers"][0]["color"] = "red"
    assert T.stamp_hash(d2)[1] != before
    assert T.validate(d2) == []
    d2["markers"][0]["color"] = "blue"  # the default is never stored
    assert any(p["rule"] == "out_of_range" for p in T.validate(d2))
    d2["markers"] = [{"id": "k1", "at": 0, "label": "a", "color": "purple"}, {"id": "k2", "at": 5, "label": "b"}]
    path = T.write_otio(T.stamp_hash(d2)[0], str(tmp_path / "m.otio"))
    back = T.from_otio(otio.adapters.read_from_file(path))
    assert [(m["id"], m.get("color")) for m in back["markers"]] == [("k1", "purple"), ("k2", None)]


def test_desk_marker_ops(desk):
    pid = _mixer_cut("dmk")
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "marker", "at": 2, "label": "Beat", "color": "yellow"})
    assert st == 200 and res["project"]["markers"][0]["color"] == "yellow"
    mid = res["project"]["markers"][0]["id"]
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "marker_set", "id": mid, "at": 2.5, "label": "Beat 2"})
    assert st == 200 and res["project"]["markers"][0]["at"] == 2.5
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "marker_set", "id": mid, "color": "teal"})
    assert st == 400
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "marker_del", "id": mid})
    assert st == 200 and res["project"]["markers"] == []


# ---------------------------------------------------------------- multi-clip selection


def _ids(pid):
    return [i["id"] for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"]]


def _spans(pid):
    return {i["id"]: [i["at"], i["at"] + i["dur"]] for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"]}


def test_move_items_moves_a_group_together_and_undoes_as_one_step(home):
    """_mixer_cut: V1=c1 (0-4s), A1=a1 (0-2s), A2=m2 (2-4s). Moving a1 and m2 together keeps
    their lengths and each one's offset, and costs a single undo step."""
    pid = _mixer_cut("grp")
    before = _spans(pid)
    E.move_items(pid, ["a1", "m2"], 1.0)
    after = _spans(pid)
    for i in ("a1", "m2"):
        # view() reports `at` in seconds, so a 1.0 s move shifts it by exactly 1.0 s
        assert abs(after[i][0] - before[i][0] - 1.0) < 1e-9
        assert after[i][1] - after[i][0] == before[i][1] - before[i][0]
    assert _log_versions(pid) == 1  # one entry for the whole group
    E.undo(pid)
    assert _spans(pid) == before


def _log_versions(pid):
    return E._log(E._dir(pid)).version


def test_move_items_rejects_bad_groups(home):
    pid = _mixer_cut("grp2")
    for bad in ([], "a1", [1, 2], ["a1", "a1"], ["a1", "nope"]):
        with pytest.raises(E.EditorError):
            E.move_items(pid, bad, 1.0)
    # an anchored text item cannot move on its own timeline (ids/tracks/clip validation)
    # Use a missing item so the group op still rejects.
    with pytest.raises(E.EditorError):
        E.move_items(pid, ["does-not-exist"], 1.0)


def test_delete_items_lifts_or_ripples_a_group_as_one_step(home):
    pid = _mixer_cut("grp3")
    before = _spans(pid)
    E.delete_items(pid, ["a1", "c1"])
    assert _log_versions(pid) == 1
    after = _spans(pid)
    assert "a1" not in after and "c1" not in after
    # a lift leaves the hole: the music clip on A2 stays where it was
    assert after["m2"][0] == before["m2"][0]
    E.undo(pid)
    assert _spans(pid) == before
    # ripple closes holes on the SAME track only. a1 is on A1 and c1 on V1, so nothing on
    # either track follows them; m2 is on A2 and never moves either way. To see ripple actually
    # pull a neighbour, delete c1 (0-4s on V1): V1 has no later item, so put one there first.
    E.split(pid, "c1", 2.0)
    pieces = [i["id"] for i in E.view(E._log(E._dir(pid)).doc)["tracks"][1]["items"]]
    E.delete_items(pid, [pieces[0]], ripple=True)  # lift the first 2s of V1
    after = _spans(pid)
    assert pieces[1] in after and abs(after[pieces[1]][0] - 0.0) < 1e-9  # the second half slid to 0
    E.undo(pid)
    assert abs(_spans(pid)[pieces[1]][0] - 2.0) < 1e-9  # and back to 2s


def test_delete_items_takes_transitions_that_touch_a_deleted_clip(home):
    pid = _mixer_cut("grp4")
    E.split(pid, "c1", 2.0)  # c1 -> two pieces, adjacent at 2s
    pieces = [i["id"] for i in E.view(E._log(E._dir(pid)).doc)["tracks"][1]["items"]]
    # Clips may only overlap where a transition justifies it, so the pull-back and the
    # cross-dissolve have to land in ONE apply (the validator checks the whole result).
    half = T.seconds_to_ticks(0.5)
    E.apply(pid, [{"op": "move_items", "ids": [pieces[1]], "by": -half},
                  {"op": "add_transition", "between": pieces, "dur": half}], "dissolve")
    tr = [t for t in E._log(E._dir(pid)).doc["tracks"] if t["id"] == "V1"][0]
    assert any(i["type"] == "transition" for i in tr["items"])
    E.delete_items(pid, [pieces[0]])
    tr = [t for t in E._log(E._dir(pid)).doc["tracks"] if t["id"] == "V1"][0]
    assert pieces[0] not in [i["id"] for i in tr["items"]]
    assert not any(i["type"] == "transition" for i in tr["items"])  # the seam went with it


def test_desk_group_ops(desk):
    pid = _mixer_cut("dgrp")
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "move_items", "ids": ["a1", "m2"], "by": 0.5})
    assert st == 200
    moved = {i["id"]: i["at"] for t in res["project"]["tracks"] for i in t["items"] if i["id"] in ("a1", "m2")}
    assert abs(moved["a1"] - 0.5) < 1e-9 and abs(moved["m2"] - 2.5) < 1e-9
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "delete_items", "ids": ["a1"], "ripple": True})
    assert st == 200 and "a1" not in [i["id"] for t in res["project"]["tracks"] for i in t["items"]]
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "move_items", "ids": [], "by": 1})
    assert st == 400 and "non-empty" in res["error"]


# ---------------------------------------------------------------- slip


def _raw(pid, iid):
    return next(i for t in E._log(E._dir(pid)).doc["tracks"] for i in t["items"] if i["id"] == iid)


def test_slip_moves_the_source_window_not_the_clip(home):
    """_mixer_cut: a1 plays media 0-2s at 0-2s on A1. Slipping +1 s plays media 1-3 s in the
    same place: the clip's at and length don't change, one undo step brings it back."""
    pid = _mixer_cut("slip")
    s = T.TICK_RATE
    before = _spans(pid)
    E.slip(pid, "a1", 1.0)
    it = _raw(pid, "a1")
    assert it["src"] == [1 * s, 3 * s]
    assert _spans(pid) == before  # nothing moved on the timeline, a1 included
    assert _log_versions(pid) == 1
    E.undo(pid)
    assert _raw(pid, "a1")["src"] == [0, 2 * s]


def test_slip_clamps_to_the_media_and_refuses_a_slip_that_cannot_move(home):
    pid = _mixer_cut("slip2")
    s = T.TICK_RATE
    E.slip(pid, "a1", 99.0)  # far past the end: stops with the window at the media's end
    assert _raw(pid, "a1")["src"] == [2 * s, 4 * s]
    with pytest.raises(E.EditorError, match="end of its media"):
        E.slip(pid, "a1", 1.0)  # already at the end
    E.slip(pid, "a1", -99.0)  # and back to the start
    assert _raw(pid, "a1")["src"] == [0, 2 * s]
    with pytest.raises(E.EditorError, match="end of its media"):
        E.slip(pid, "a1", -0.5)


def test_slip_scales_by_the_clip_speed(home):
    """At 2x a clip's 1 s of timeline holds 2 s of media, so a 0.5 s slip moves the source
    window by 1 s. The clip still stays put."""
    pid = _mixer_cut("slip3")
    s = T.TICK_RATE
    E.apply(pid, [{"op": "set_props", "id": "c1", "props": {"speed": [2, 1]}}], "2x")
    src0 = _raw(pid, "c1")["src"]
    # c1 now plays 4 s of media in 2 s; trim it to 2 s of media so it has room to slip
    E.apply(pid, [{"op": "trim_clip", "id": "c1", "src_out": src0[0] + 2 * s, "ripple": True}], "trim")
    at0 = _raw(pid, "c1")["at"]
    E.slip(pid, "c1", 0.5)
    it = _raw(pid, "c1")
    assert it["src"] == [1 * s, 3 * s] and it["at"] == at0


def test_slip_refuses_text_and_unknown_items(home):
    pid = _mixer_cut("slip4")
    with pytest.raises(E.EditorError):
        E.slip(pid, "nope", 1.0)


def test_desk_slip(desk):
    pid = _mixer_cut("dslip")
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "slip", "item": "a1", "by": 0.5})
    assert st == 200
    row = next(i for t in res["project"]["tracks"] for i in t["items"] if i["id"] == "a1")
    assert row["at"] == 0 and abs(row["src_in"] - 0.5) < 1e-9 and abs(row["src_out"] - 2.5) < 1e-9
    assert "Slip a1" in res["project"]["summary"]


def test_nudges_snap_to_whole_frames_so_a_nudge_and_its_opposite_cancel(home):
    """The page sends seconds rounded to 3 decimals; 1/30 s as 0.033333 is not a whole frame of
    ticks. The engine snaps relative moves to the frame grid, so +1 frame then -1 frame lands
    exactly where it started (it used to drift a hair and collide with the neighbour)."""
    pid = _mixer_cut("nudge")
    s = T.TICK_RATE
    frame = s // 30
    E.move_items(pid, ["m2"], 0.033333)
    assert _raw(pid, "m2")["at"] == 2 * s + frame
    E.move_items(pid, ["m2"], -0.033333)
    assert _raw(pid, "m2")["at"] == 2 * s
    with pytest.raises(E.EditorError, match="less than a frame"):
        E.move_items(pid, ["m2"], 0.001)


def test_slip_snaps_to_whole_frames(home):
    pid = _mixer_cut("slipf")
    s = T.TICK_RATE
    E.slip(pid, "a1", 0.033333)
    assert _raw(pid, "a1")["src"] == [s // 30, 2 * s + s // 30]


# ---------------------------------------------------------------- roll


def _split_c1(pid):
    """Split V1's c1 (media 0-4 s at 0-4 s) at 2 s: two clips meeting at a hard cut."""
    E.split(pid, "c1", 2.0)
    return [i["id"] for i in E.view(E._log(E._dir(pid)).doc)["tracks"][1]["items"]]


def test_roll_moves_the_cut_and_nothing_else(home):
    pid = _mixer_cut("roll")
    s = T.TICK_RATE
    a, b = _split_c1(pid)
    before = _spans(pid)
    v0 = _log_versions(pid)
    E.roll(pid, a, 0.5)
    ra, rb = _raw(pid, a), _raw(pid, b)
    assert ra["src"] == [0, 2 * s + s // 2] and ra["at"] == 0
    assert rb["src"] == [2 * s + s // 2, 4 * s] and rb["at"] == 2 * s + s // 2
    after = _spans(pid)
    assert after[b][1] == before[b][1]  # the incoming clip still ends where it did
    assert {k: v for k, v in after.items() if k not in (a, b)} == {k: v for k, v in before.items() if k not in (a, b)}
    assert _log_versions(pid) == v0 + 1  # two trims, one step
    E.undo(pid)
    assert _spans(pid) == before


def test_roll_clamps_so_both_clips_keep_a_frame(home):
    pid = _mixer_cut("roll2")
    s = T.TICK_RATE
    f = s // 30
    a, b = _split_c1(pid)
    E.roll(pid, a, 99.0)
    assert _raw(pid, a)["src"] == [0, 4 * s - f] and _raw(pid, b)["src"] == [4 * s - f, 4 * s]
    with pytest.raises(E.EditorError, match="can't move that way"):
        E.roll(pid, a, 1.0)
    E.roll(pid, a, -99.0)
    assert _raw(pid, a)["src"] == [0, f] and _raw(pid, b)["at"] == f


def test_roll_keeps_a_crossfade_on_the_cut(home):
    pid = _mixer_cut("roll3")
    s = T.TICK_RATE
    a, b = _split_c1(pid)
    half = s // 2
    E.apply(pid, [{"op": "move_items", "ids": [b], "by": -half},
                  {"op": "add_transition", "between": [a, b], "dur": half}], "dissolve")
    end_b = _raw(pid, b)["at"] + T.item_duration(_raw(pid, b))
    E.roll(pid, a, 0.3)  # 9 frames at 30 fps (0.25 s would be 7.5 and round to 8)
    ra, rb = _raw(pid, a), _raw(pid, b)
    assert ra["src"][1] == s * 23 // 10 and rb["src"][0] == s * 23 // 10
    assert rb["at"] == ra["at"] + T.item_duration(ra) - half  # overlap is still the dissolve
    assert rb["at"] + T.item_duration(rb) == end_b


def test_roll_needs_a_touching_neighbour(home):
    pid = _mixer_cut("roll4")
    with pytest.raises(E.EditorError, match="no clip touches"):
        E.roll(pid, "a1", 0.5)  # a1 is alone on A1
    with pytest.raises(E.EditorError):
        E.roll(pid, "nope", 0.5)


def test_desk_roll(desk):
    pid = _mixer_cut("droll")
    a, b = _split_c1(pid)
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "roll", "item": a, "by": -0.5})
    assert st == 200 and f"Roll {a}|{b}" in res["project"]["summary"]
    rows = {i["id"]: i for t in res["project"]["tracks"] for i in t["items"]}
    assert abs(rows[a]["dur"] - 1.5) < 1e-9 and abs(rows[b]["at"] - 1.5) < 1e-9 and abs(rows[b]["dur"] - 2.5) < 1e-9


# ---------------------------------------------------------------- slide


def _three(pid):
    """V1's c1 (media 0-4 s) split at 1 s and 3 s: p0 0-1, p1 1-3, p2 3-4, hard cuts."""
    E.split(pid, "c1", 1.0)
    first = [i["id"] for i in E.view(E._log(E._dir(pid)).doc)["tracks"][1]["items"]]
    E.split(pid, first[1], 3.0)
    return [i["id"] for i in sorted(E.view(E._log(E._dir(pid)).doc)["tracks"][1]["items"], key=lambda i: i["at"])]


def test_slide_moves_the_clip_and_its_neighbours_absorb_it(home):
    pid = _mixer_cut("slide")
    s = T.TICK_RATE
    p0, p1, p2 = _three(pid)
    before = _spans(pid)
    v0 = _log_versions(pid)
    E.slide(pid, p1, 0.5)
    r0, r1, r2 = _raw(pid, p0), _raw(pid, p1), _raw(pid, p2)
    assert r1["src"] == [1 * s, 3 * s] and r1["at"] == s + s // 2          # its own media, later
    assert r0["src"] == [0, s + s // 2] and r0["at"] == 0                   # the one before grows
    assert r2["src"] == [3 * s + s // 2, 4 * s] and r2["at"] == 3 * s + s // 2  # the one after shrinks
    after = _spans(pid)
    assert after[p2][1] == before[p2][1]  # the total length is unchanged
    assert _log_versions(pid) == v0 + 1
    E.undo(pid)
    assert _spans(pid) == before


def test_slide_clamps_to_a_frame_on_each_side(home):
    pid = _mixer_cut("slide2")
    s = T.TICK_RATE
    f = s // 30
    p0, p1, p2 = _three(pid)
    E.slide(pid, p1, 99.0)
    assert _raw(pid, p2)["src"] == [4 * s - f, 4 * s] and _raw(pid, p1)["at"] == 2 * s - f
    with pytest.raises(E.EditorError, match="can't slide that way"):
        E.slide(pid, p1, 0.5)
    E.slide(pid, p1, -99.0)
    assert _raw(pid, p0)["src"] == [0, f] and _raw(pid, p1)["at"] == f


def test_slide_needs_a_clip_on_each_side(home):
    pid = _mixer_cut("slide3")
    p0, p1, p2 = _three(pid)
    with pytest.raises(E.EditorError, match="start of"):
        E.slide(pid, p0, 0.5)
    with pytest.raises(E.EditorError, match="end of"):
        E.slide(pid, p2, -0.5)


def test_desk_slide(desk):
    pid = _mixer_cut("dslide")
    p0, p1, p2 = _three(pid)
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "slide", "item": p1, "by": -0.5})
    assert st == 200 and f"Slide {p1}" in res["project"]["summary"]
    rows = {i["id"]: i for t in res["project"]["tracks"] for i in t["items"]}
    assert abs(rows[p0]["dur"] - 0.5) < 1e-9 and abs(rows[p1]["at"] - 0.5) < 1e-9
    assert abs(rows[p1]["src_in"] - 1.0) < 1e-9 and abs(rows[p2]["at"] - 2.5) < 1e-9 and abs(rows[p2]["dur"] - 1.5) < 1e-9


# ---------------------------------------------------------------- concurrency


def test_parallel_edits_to_one_project_never_corrupt_its_log(home):
    """The desk serves requests on threads. Three quick Look changes once raced: two requests
    both read version 1 and both appended version 2, and the log was refused on load ('out of
    sequence'), so the project would not open. Fire 24 edits from 8 threads at once: every one
    lands, in order, and the log reloads."""
    import threading

    from hermes_studio import oplog as O

    pid = _mixer_cut("race")
    errors: list[Exception] = []
    start = threading.Barrier(8)

    def worker(n):
        start.wait()
        for k in range(3):
            try:
                E.set_volume(pid, "a1", round(0.1 + 0.01 * (n * 3 + k), 3))
            except Exception as exc:  # noqa: BLE001 - collect, assert below
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors[:3]
    folder = E._dir(pid)
    base = json.loads((folder / "base.json").read_text())
    log = O.Oplog.load(base, folder / "oplog.jsonl")  # raised 'out of sequence' before the lock
    assert log.version == 24
    entries = [json.loads(line) for line in (folder / "oplog.jsonl").read_text().splitlines() if line.strip()]
    assert sorted(e["base_version"] for e in entries) == list(range(24))
    assert json.loads((folder / "timeline.json").read_text())["version"] == 24


def test_parallel_edits_from_separate_processes_are_serialised(home):
    """The CLI and the MCP server are other processes: the project's OS file lock (not just the
    desk's thread lock) has to keep their writes apart too. Four processes, five edits each."""
    import os
    import subprocess
    import sys

    from hermes_studio import oplog as O

    pid = _mixer_cut("xproc")
    code = (
        "import sys; from hermes_studio import editor as E\n"
        "for k in range(5): E.set_volume(sys.argv[1], 'a1', round(0.2 + 0.01 * (int(sys.argv[2]) * 5 + k), 3))\n"
    )
    env = {**os.environ, "HERMES_STUDIO_EDITOR": str(E.root())}
    procs = [subprocess.Popen([sys.executable, "-c", code, pid, str(n)], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) for n in range(4)]
    outs = [p.communicate(timeout=120) for p in procs]
    assert all(p.returncode == 0 for p in procs), [o[1].decode()[-400:] for o in outs]
    folder = E._dir(pid)
    log = O.Oplog.load(json.loads((folder / "base.json").read_text()), folder / "oplog.jsonl")
    assert log.version == 20


def test_reset_only_ever_rebuilds_the_demo(home, desk):
    """Reset deletes a project's folder. It used to run for any project, and the inspector
    showed "Reset demo" on real films: one click would have wiped one. Now a film is refused,
    by the editor and by the desk, and nothing in its folder is touched."""
    pid = _mixer_cut("film1")
    folder = E._dir(pid)
    before = sorted(p.name for p in folder.iterdir())
    with pytest.raises(E.EditorError, match="only rebuilds the demo"):
        E.reset(pid)
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "reset"})
    assert st == 400 and "only rebuilds the demo" in res["error"]
    assert sorted(p.name for p in folder.iterdir()) == before
    assert (folder / "media" / "v.mp4").is_file()
    # The demo itself still resets: a fresh project with no history.
    E.create("demo")
    E.split("demo", "c1", 2.0)
    assert len(E.history("demo")) == 1
    E.reset("demo")
    assert E.history("demo") == []


# ------------------------------------------------------------- transition kinds


def _kind_cut(home, pid, kind, seconds=1.0, colour_a="red", colour_b="blue"):
    """Two solid colour clips with a transition of `kind` between them, rendered."""
    import json as _json
    import subprocess as _sp

    from hermes_studio import oplog as _O

    folder = E._dir(pid)
    (folder / "media").mkdir(parents=True, exist_ok=True)
    for col, name, freq in ((colour_a, "ra", 440), (colour_b, "bl", 660)):
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", f"-i", f"color=c={col}:s=320x180:d=4:r=30",
             "-f", "lavfi", f"-i", f"sine=frequency={freq}:duration=4", "-c:v", "libx264",
             "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(folder / "media" / f"{name}.mp4")],
            check=True, capture_output=True,
        )
    s = T.TICK_RATE
    d = T.new_timeline(pid)
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/ra.mp4", "dur": 4 * s, "fps": [30, 1]},
                  "m2": {"path": "media/bl.mp4", "dur": 4 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [
        {"id": "aa", "type": "clip", "media": "m1", "src": [0, 4 * s], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "bb", "type": "clip", "media": "m2", "src": [0, 4 * s], "at": 4 * s, "fade_in": 0, "fade_out": 0},
    ]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(_json.dumps(d))
    log = _O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)
    E.set_transition(pid, "aa", "bb", seconds, kind=kind)
    return folder


def _frame_halves(path, at, folder):
    """A frame at `at`: (mean rgb of the left half, of the right half), both 0..255."""
    from PIL import Image

    jpg = folder / f"_half_{at}.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", str(path),
                    "-frames:v", "1", str(jpg)], check=True, capture_output=True)
    im = Image.open(jpg).convert("RGB")
    w, h = im.size
    def mean(box):
        px = list(im.crop(box).resize((8, 8)).get_flattened_data()) if hasattr(im.crop(box), "get_flattened_data") else list(im.crop(box).resize((8, 8)).getdata())
        return tuple(sum(p[c] for p in px) // len(px) for c in range(3))
    return mean((0, 0, w // 2, h)), mean((w // 2, 0, w, h))


def test_transition_kinds_resolve_and_render(home):
    from hermes_studio import transitions as X
    from hermes_studio import render_timeline as R

    assert len(X.kinds()) > 20 and "fade" in X.kinds()
    assert X.resolve("Cross Fade") == "fade" and X.resolve("dip to black") == "fadeblack"
    assert X.resolve("Wipe Left") == "wipeleft" and X.resolve("nope") is None

    pid = "xk"
    _kind_cut(home, pid, "Wipe Right")
    folder = E._dir(pid)
    tr = _tr_of(pid)
    assert tr["kind"] == "wiperight" and tr["dur"] > 0
    out = R.render_project(pid)
    assert out["duration"] == pytest.approx(7.0, abs=0.1)
    # A wipe is not a dissolve: mid-way, one side of the frame has already gone and the other
    # hasn't, so the halves are strongly red- and blue-dominant in opposite directions. A
    # dissolve mixes both halves about equally -- that is the difference being asserted.
    l, r = _frame_halves(out["path"], 3.5, folder)
    reds, blues = sorted((l, r), key=lambda c: c[0] - c[2], reverse=True)
    assert reds[0] > reds[2] + 30 and reds[2] < 40, ("no red side", l, r)
    assert blues[2] > blues[0] + 30 and blues[0] < 40, ("no blue side", l, r)


def test_changing_a_kind_is_one_step_and_undo_restores_the_old_kind(home):
    from hermes_studio import transitions as X

    pid = _two_clips(home, "xkind")
    E.set_transition(pid, "aa", "bb", 1.0, kind="Wipe Left")
    E.set_transition(pid, "aa", "bb", 1.5, kind="Fade to Black")  # resize AND re-kind in one op
    # One step, not two: the kind and the length are the same op.
    assert [h["summary"] for h in E.history(pid)] == ["Wipe Left 1s", "Fade to Black 1.5s"]
    assert (_tr_of(pid)["kind"], _tr_of(pid)["dur"]) == ("fadeblack", T.seconds_to_ticks(1.5))
    E.undo(pid)
    assert (_tr_of(pid)["kind"], _tr_of(pid)["dur"]) == ("wipeleft", T.seconds_to_ticks(1.0))
    assert len(E.history(pid)) == 3  # two edits plus the undo itself
    with pytest.raises(E.EditorError, match="unknown transition kind"):
        E.set_transition(pid, "aa", "bb", 1.0, kind="no-such-thing")
    for said in ("cross fade", "Cross-Fade", "crossfade", "dip to black", "DIPBLACK", "dip"):
        assert X.resolve(said), said


def test_an_old_project_with_kind_xfade_still_loads(home):
    """Projects written before kinds stored kind 'xfade' (the filter name). They must keep
    opening, as a cross-dissolve."""
    import json as _json

    from hermes_studio import oplog as _O

    pid = "xlegacy"
    folder = E._dir(pid)
    folder.mkdir(parents=True, exist_ok=True)
    s = T.TICK_RATE
    d = T.new_timeline(pid)
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/talk.mp4", "dur": 60 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [
        {"id": "aa", "type": "clip", "media": "m1", "src": [0, 8 * s], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "bb", "type": "clip", "media": "m1", "src": [0, 8 * s], "at": 7 * s, "fade_in": 0, "fade_out": 0},
        {"id": "t1", "type": "transition", "kind": "xfade", "between": ["aa", "bb"], "dur": s},
    ]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(_json.dumps(d))
    log = _O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)
    assert _tr_of(pid)["kind"] == "fade"


def test_transitions_catalog_is_grouped_and_every_entry_renders(home):
    from hermes_studio import transitions as X
    from hermes_studio import render_timeline as R

    cat = X.catalog()
    groups = [g["group"] for g in cat]
    assert groups == ["Dissolve", "Wipe", "Slide", "Shape", "Other"]
    assert sum(len(g["kinds"]) for g in cat) == len(X.kinds())
    for k in X.kinds():
        assert X.resolve(X.label(k)) == k or X.resolve(k) == k, k
    # Spot-render one kind from each group, to prove the names ffmpeg lists really work.
    for kind in ("fade", "wipeleft", "slideup", "circlecrop", "pixelize"):
        pid = f"xc_{kind}"
        folder = _kind_cut(home, pid, kind)
        out = R.render_project(pid)
        assert out["duration"] == pytest.approx(7.0, abs=0.1), kind
    # And a dissolve, for contrast: it mixes both halves, so neither half is one colour.
    folder = _kind_cut(home, "xc_dissolve", "Cross Fade")
    out = R.render_project("xc_dissolve")
    l, r = _frame_halves(out["path"], 3.5, folder)
    for half in (l, r):
        assert half[0] > 40 and half[2] > 40, ("dissolve must mix", half)
