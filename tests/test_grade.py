"""Primary grade: one formula (grade.py), checked against what ffmpeg actually renders and
against the table the page's preview interpolates."""
import json
import subprocess

import pytest

from hermes_studio import editor as E
from hermes_studio import grade as G
from hermes_studio import timeline as T

from tests.test_editor import _post, desk, home  # noqa: F401  (shared fixtures)


def _g(**kw):
    return G.parse(G.store(**kw))


# ---------------------------------------------------------------- the formula


def test_identity_is_no_grade():
    assert G.store() is None
    assert G.parse(None) is None
    assert G.store(lift=[0, 0, 0], gamma=[1, 1, 1], gain=[1, 1, 1], sat=1) is None
    assert G.ffmpeg_chain(None) == "" and G.preview(None) is None


def test_lift_sets_the_black_point_and_gain_the_white_point():
    g = _g(lift=[0.2, 0.2, 0.2], gain=[0.8, 0.8, 0.8])
    assert G.curve(g, 0, 0.0) == pytest.approx(0.2)
    assert G.curve(g, 0, 1.0) == pytest.approx(0.8)
    assert G.curve(g, 0, 0.5) == pytest.approx(0.5)


def test_gamma_bends_the_mids_and_keeps_the_ends():
    g = _g(gamma=[2, 2, 2])
    assert G.curve(g, 1, 0.0) == 0.0 and G.curve(g, 1, 1.0) == pytest.approx(1.0)
    assert G.curve(g, 1, 0.25) == pytest.approx(0.5)  # 0.25 ** (1/2)


def test_saturation_zero_is_rec709_mono():
    g = _g(sat=0)
    r, gg, b = G.apply_pixel(g, (1.0, 0.0, 0.0))
    assert r == pytest.approx(0.2126) and gg == pytest.approx(0.2126) and b == pytest.approx(0.2126)


def test_store_refuses_out_of_range_numbers():
    with pytest.raises(ValueError, match="gamma g"):
        G.store(gamma=[1, 0.1, 1])
    with pytest.raises(ValueError, match="lift r"):
        G.store(lift=[0.9, 0, 0])
    with pytest.raises(ValueError, match="saturation"):
        G.store(sat=9)
    with pytest.raises(ValueError, match="three numbers"):
        G.store(gain=[1, 1])


# ---------------------------------------------------------------- render == formula


COLOURS = [(0, 0, 0), (255, 255, 255), (128, 128, 128), (200, 60, 30), (20, 120, 220), (64, 192, 96)]
GRADES = [
    dict(lift=[0.1, 0.0, -0.05], gamma=[1.0, 1.3, 0.8], gain=[1.1, 0.95, 1.0]),
    dict(sat=0.0),
    dict(sat=1.6, gain=[0.9, 0.9, 0.9]),
    dict(lift=[0.05, 0.05, 0.05], gamma=[0.7, 0.7, 0.7], gain=[1, 1, 1], sat=0.5),
]


def _ffmpeg_pixel(rgb, chain):
    """Exact RGB bytes in on stdin (lavfi's color source goes through YUV and shifts the input
    by a few code values), the grade chain, RGB bytes out."""
    vf = "format=rgb24," + (chain + "," if chain else "") + "format=rgb24"
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "4x4", "-i", "-",
         "-vf", vf, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        input=bytes(rgb) * 16, check=True, capture_output=True,
    ).stdout
    return tuple(out[:3])


def test_the_pixel_probe_is_exact():
    assert _ffmpeg_pixel((200, 60, 30), "") == (200, 60, 30)


@pytest.mark.parametrize("kw", GRADES)
def test_ffmpeg_renders_the_formula(kw):
    """ffmpeg's lutrgb + colorchannelmixer give the reference formula's pixel, to 2 code
    values (one for lutrgb's integer table, one for the mixer's rounding)."""
    g = _g(**kw)
    chain = G.ffmpeg_chain(g)
    for rgb in COLOURS:
        want = [round(v * 255) for v in G.apply_pixel(g, tuple(c / 255 for c in rgb))]
        got = _ffmpeg_pixel(rgb, chain)
        assert all(abs(a - b) <= 2 for a, b in zip(got, want)), (kw, rgb, got, want)


@pytest.mark.parametrize("kw", GRADES[:1] + [dict(gamma=[0.2, 5, 1])])
def test_preview_table_is_within_a_code_value_of_the_curve(kw):
    """The page linearly interpolates the table (SVG feComponentTransfer type=table); across
    every 8-bit input the result stays within one code value of the exact curve, even at the
    steepest gamma allowed."""
    g = _g(**kw)
    tables = G.preview(g)["tables"]
    n = len(tables[0]) - 1
    for ch in range(3):
        t = tables[ch]
        for code in range(256):
            x = code / 255
            k = min(n - 1, int(x * n))
            u = x * n - k
            interp = t[k] + (t[k + 1] - t[k]) * u
            assert abs(interp - G.curve(g, ch, x)) * 255 <= 1.0, (ch, code)


# ---------------------------------------------------------------- the editor op


def _cut(pid, colour="black"):
    folder = E._dir(pid)
    (folder / "media").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=160x90:d=2:r=30",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-qp", "0", str(folder / "media" / "v.mp4")],
        check=True, capture_output=True,
    )
    s = T.TICK_RATE
    d = T.new_timeline(pid, size=(160, 90))
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/v.mp4", "dur": 2 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 2 * s], "at": 0, "fade_in": 0, "fade_out": 0}]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as O

    E._save_current(folder, O.Oplog(d, path=folder / "oplog.jsonl").doc)
    return pid


def _row(pid):
    return next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "c1")


def test_set_grade_stores_views_and_undoes(home):
    pid = _cut("grade1")
    E.set_grade(pid, "c1", lift=[0.1, 0, 0], sat=0.5)
    row = _row(pid)
    assert row["grade"]["lift"] == pytest.approx([0.1, 0, 0]) and row["grade"]["sat"] == pytest.approx(0.5)
    assert len(row["grade_preview"]["tables"]) == 3 and len(row["grade_preview"]["tables"][0]) == G.TABLE_POINTS
    E.set_grade(pid, "c1")  # identity clears it
    assert _row(pid)["grade"] is None
    E.undo(pid)
    assert _row(pid)["grade"]["sat"] == pytest.approx(0.5)
    with pytest.raises(E.EditorError, match="gain"):
        E.set_grade(pid, "c1", gain=[9, 1, 1])


def test_render_applies_the_grade_to_the_clip(home):
    """A black clip with lift 0.25 renders at code value ~64 on every channel; undo renders
    black again. Measured from the rendered mp4, not from the function's return value."""
    from hermes_studio import render_timeline as R

    pid = _cut("grade2")

    def centre():
        out = R.render_project(pid)
        mp4 = out.get("path") or out.get("file")
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(mp4), "-vf", "crop=8:8:76:41", "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
        n = len(raw) // 3
        return [sum(raw[i::3]) / n for i in range(3)]

    assert all(v < 6 for v in centre())
    E.set_grade(pid, "c1", lift=[0.25, 0.25, 0.25])
    assert all(abs(v - 64) <= 4 for v in centre()), centre()
    E.undo(pid)
    assert all(v < 6 for v in centre())


def test_desk_grade(desk):
    pid = _cut("dgrade")
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "grade", "id": "c1", "gamma": [1, 1.5, 1]})
    assert st == 200
    row = next(i for t in res["project"]["tracks"] for i in t["items"] if i["id"] == "c1")
    assert row["grade"]["gamma"] == pytest.approx([1, 1.5, 1]) and res["project"]["summary"] == "Grade c1"


def test_preview_frames_are_cached_per_media_not_just_per_time(home):
    """Two clips from different files at the same source second: each preview frame shows its
    own file. The cache used to key on time alone, so the second clip got the first's picture."""
    import io

    pid = "frames2"
    folder = E._dir(pid)
    (folder / "media").mkdir(parents=True, exist_ok=True)
    for name, colour in (("red.mp4", "red"), ("blue.mp4", "blue")):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=64x36:d=2:r=30",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(folder / "media" / name)],
                       check=True, capture_output=True)
    s = T.TICK_RATE
    d = T.new_timeline(pid, size=(64, 36))
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"mr": {"path": "media/red.mp4", "dur": 2 * s, "fps": [30, 1]},
                  "mb": {"path": "media/blue.mp4", "dur": 2 * s, "fps": [30, 1]}}
    by["V1"]["items"] = [
        {"id": "r", "type": "clip", "media": "mr", "src": [0, 2 * s], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "b", "type": "clip", "media": "mb", "src": [0, 2 * s], "at": 2 * s, "fade_in": 0, "fade_out": 0},
    ]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as O

    E._save_current(folder, O.Oplog(d, path=folder / "oplog.jsonl").doc)

    def mean_rgb(jpeg: bytes):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", "-", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             input=jpeg, capture_output=True, check=True).stdout
        n = len(raw) // 3
        return [sum(raw[i::3]) / n for i in range(3)]

    red = mean_rgb(E.frame_jpeg(pid, 1.0))   # clip r, source 1.0 s
    blue = mean_rgb(E.frame_jpeg(pid, 3.0))  # clip b, source 1.0 s too
    assert red[0] > 150 and red[2] < 80, red
    assert blue[2] > 150 and blue[0] < 80, blue
