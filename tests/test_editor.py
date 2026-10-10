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

    def avg_rgb(at: float):
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
