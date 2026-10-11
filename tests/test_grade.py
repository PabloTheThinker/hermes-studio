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
    E.clear_grade(pid, "c1")  # removes the whole grade
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


# ---------------------------------------------------------------- looks are grades


def test_every_look_is_a_valid_grade_and_reads_back_as_its_name():
    for name in G.LOOKS:
        stored = G.look(name)
        assert stored is not None and G.parse(stored) is not None
        assert G.look_name(stored) == name
    assert G.look(None) is None and G.look_name(None) is None
    assert G.look_name(G.store(sat=0.5)) is None  # a grade that is no look


def test_mono_desaturates_about_rec709_luma():
    g = G.parse(G.look("mono"))
    for rgb in ((1, 0, 0), (0, 1, 0), (0.2, 0.5, 0.9)):
        out = G.apply_pixel(g, rgb)
        assert max(out) - min(out) < 1e-9  # grey


def test_set_look_writes_the_grade_and_the_wheels_can_take_it_further(home):
    pid = _cut("look1")
    E.set_look(pid, "c1", "warm")
    row = _row(pid)
    assert row["look"] == "warm" and row["grade"] is not None and row["grade_preview"] is not None
    raw = next(i for t in E._log(E._dir(pid)).doc["tracks"] for i in t["items"] if i["id"] == "c1")
    assert raw["props"]["grade"] == G.look("warm") and raw["props"].get("look") is None
    # Move the grade off the look: it is a custom grade now, not "warm".
    g = row["grade"]
    E.set_grade(pid, "c1", lift=g["lift"], gamma=g["gamma"], gain=g["gain"], sat=g["sat"] + 0.2)
    assert _row(pid)["look"] is None and _row(pid)["grade"] is not None
    E.set_look(pid, "c1", None)
    assert _row(pid)["grade"] is None
    with pytest.raises(E.EditorError, match="unknown look"):
        E.set_look(pid, "c1", "vaporwave")


def test_a_legacy_look_shows_and_renders_as_its_grade(home):
    """A doc from before looks were grades (props.look only): the view reports the look and
    sends its grade for the preview, and the render applies that same grade."""
    from hermes_studio import oplog as O
    from hermes_studio import render_timeline as R

    pid = _cut("legacy", colour="0x808080")
    folder = E._dir(pid)
    d = json.loads((folder / "base.json").read_text())
    d["tracks"][[t["id"] for t in d["tracks"]].index("V1")]["items"][0]["props"] = {"look": "punch"}
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    (folder / "oplog.jsonl").unlink(missing_ok=True)
    E._save_current(folder, O.Oplog(d, path=folder / "oplog.jsonl").doc)
    row = _row(pid)
    assert row["look"] == "punch" and row["grade_preview"] is not None
    out = R.render_project(pid)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1", "-i", str(out.get("path") or out.get("file")),
                          "-vf", "crop=8:8:76:41", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    got = [sum(raw[i::3]) / (len(raw) // 3) for i in range(3)]
    want = [v * 255 for v in G.apply_pixel(G.parse(G.look("punch")), (128 / 255,) * 3)]
    assert all(abs(a - b) <= 4 for a, b in zip(got, want)), (got, want)


# ---------------------------------------------------------------- custom curves


S_CURVE = {"m": [[0, 0], [0.25, 0.15], [0.75, 0.85], [1, 1]]}


def test_pchip_passes_through_its_points_and_never_overshoots():
    pts = ((0, 0), (0.2, 0.5), (0.4, 0.55), (0.7, 0.56), (1, 1))
    for x, y in pts:
        assert G.pchip(pts, x) == pytest.approx(y)
    xs = [i / 1000 for i in range(1001)]
    ys = [G.pchip(pts, x) for x in xs]
    assert all(b >= a - 1e-12 for a, b in zip(ys, ys[1:]))  # rising points: a rising curve
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):  # and each piece stays between its ends
        seg = [G.pchip(pts, x) for x in xs if x0 <= x <= x1]
        assert min(seg) >= min(y0, y1) - 1e-12 and max(seg) <= max(y0, y1) + 1e-12


def test_curves_compose_after_lift_gamma_gain_master_then_channel():
    g = G.parse(G.store(gain=[0.8, 0.8, 0.8], curves={**S_CURVE, "r": [[0, 0.1], [1, 1]]}))
    x = 0.6
    lgg = 0.8 * x
    m = G.pchip(((0, 0), (0.25, 0.15), (0.75, 0.85), (1, 1)), lgg)
    assert G.curve(g, 1, x) == pytest.approx(m)                     # green: master only
    assert G.curve(g, 0, x) == pytest.approx(0.1 + 0.9 * m)          # red: master then red


def test_curves_store_validate_and_straight_lines_are_dropped():
    assert G.store(curves={"m": [[0, 0], [1, 1]]}) is None  # a straight master is no grade
    st = G.store(curves={"g": [[1, 1], [0, 0], [0.5, 0.6]]})  # sorted on the way in
    assert [p[0] for p in G.parse(st)["curves"]["g"]] == [0, 0.5, 1]
    for bad, msg in [({"x": [[0, 0], [1, 1]]}, "unknown curve"), ({"m": [[0, 0]]}, "2 to"),
                     ({"m": [[0, 0], [0.5, 1.2], [1, 1]]}, "inside 0..1"),
                     ({"m": [[0.1, 0], [1, 1]]}, "input 0 to input 1"),
                     ({"m": [[0, 0], [0.5, 0.4], [0.5, 0.6], [1, 1]]}, "same input")]:
        with pytest.raises(ValueError, match=msg):
            G.store(curves=bad)


@pytest.mark.parametrize("curves", [S_CURVE, {"r": [[0, 0], [0.5, 0.7], [1, 1]], "b": [[0, 0.1], [0.6, 0.4], [1, 0.9]]}])
def test_ffmpeg_lut1d_renders_the_curves(tmp_path, curves):
    """With curves the render's per-channel stage is a LUT grade.py writes: ffmpeg's output must
    still be the reference formula, to 2 code values, on real pixels."""
    g = G.parse(G.store(lift=[0.05, 0, 0], sat=1.2, curves=curves))
    chain = G.ffmpeg_chain(g, tmp_path)
    assert "lut1d=" in chain and "lutrgb" not in chain
    assert len(list(tmp_path.glob("grade-*.cube"))) == 1
    G.ffmpeg_chain(g, tmp_path)  # same grade: same file, not a second one
    assert len(list(tmp_path.glob("grade-*.cube"))) == 1
    for rgb in COLOURS:
        want = [round(v * 255) for v in G.apply_pixel(g, tuple(c / 255 for c in rgb))]
        got = _ffmpeg_pixel(rgb, chain)
        assert all(abs(a - b) <= 2 for a, b in zip(got, want)), (rgb, got, want)


def test_a_lut_path_with_a_colon_and_a_quote_still_renders(tmp_path):
    odd = tmp_path / "it's a: [b],c;d"
    g = G.parse(G.store(curves=S_CURVE))
    chain = G.ffmpeg_chain(g, odd)
    want = [round(v * 255) for v in G.apply_pixel(g, (100 / 255,) * 3)]
    assert list(_ffmpeg_pixel((100, 100, 100), chain)) == pytest.approx(want, abs=2)


def test_wheels_keep_the_curves_and_the_curves_keep_the_wheels(home):
    pid = _cut("curves1")
    E.set_grade(pid, "c1", curves=S_CURVE)
    E.set_grade(pid, "c1", gain=[1.1, 1, 0.9])  # a wheel commit: no curves in it
    row = _row(pid)
    assert row["grade"]["curves"]["m"][1] == pytest.approx([0.25, 0.15])
    E.set_grade(pid, "c1", curves={"m": [[0, 0], [0.5, 0.6], [1, 1]]})  # a curve commit
    row = _row(pid)
    assert row["grade"]["gain"] == pytest.approx([1.1, 1, 0.9]) and len(row["grade"]["curves"]["m"]) == 3
    E.set_grade(pid, "c1", curves=None)  # clear just the curves
    assert _row(pid)["grade"]["curves"] is None and _row(pid)["grade"]["gain"] == pytest.approx([1.1, 1, 0.9])
    E.clear_grade(pid, "c1")
    assert _row(pid)["grade"] is None


def test_render_applies_the_curves(home):
    """A mid-grey clip under a master curve that lifts 0.5 to 0.7 renders at ~179."""
    from hermes_studio import render_timeline as R

    pid = _cut("curves2", colour="0x808080")
    E.set_grade(pid, "c1", curves={"m": [[0, 0], [0.5, 0.7], [1, 1]]})
    out = R.render_project(pid)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1", "-i", str(out.get("path") or out.get("file")),
                          "-vf", "crop=8:8:76:41", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    got = [sum(raw[i::3]) / (len(raw) // 3) for i in range(3)]
    want = G.apply_pixel(_row_grade(pid), (128 / 255,) * 3)[0] * 255
    assert all(abs(v - want) <= 4 for v in got), (got, want)
    assert list((E._dir(pid) / "cache" / "luts").glob("grade-*.cube"))


def _row_grade(pid):
    raw = next(i for t in E._log(E._dir(pid)).doc["tracks"] for i in t["items"] if i["id"] == "c1")
    return G.parse(raw["props"]["grade"])


def test_the_timeline_refuses_a_malformed_curve(home):
    pid = _cut("curves3")
    for bad in ({"m": [[[0, 1], [0, 1]]]}, {"m": [[[1, 2], [0, 1]], [[1, 1], [1, 1]]]}, {"z": []}):
        with pytest.raises(E.EditorError):
            E.apply(pid, [{"op": "set_props", "id": "c1", "props": {"grade": {"curves": bad}}}], "bad")
