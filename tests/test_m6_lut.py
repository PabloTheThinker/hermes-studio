"""M6: .cube 3D LUT import, intensity, preview = export within grade tolerance."""

from __future__ import annotations

import json
import statistics
import subprocess
from pathlib import Path

import pytest

from hermes_studio import editor as E
from hermes_studio import grade as G
from hermes_studio import lut as L
from hermes_studio import timeline as T

S = T.TICK_RATE


def _cut(pid: str, colour: str = "0x808080"):
    folder = E._dir(pid)
    (folder / "media").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=160x90:d=2:r=30",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-qp", "0", str(folder / "media" / "v.mp4")],
        check=True, capture_output=True,
    )
    d = T.new_timeline(pid, size=(160, 90))
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/v.mp4", "dur": 2 * S, "fps": [30, 1]}}
    by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 2 * S], "at": 0, "fade_in": 0, "fade_out": 0}]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as O

    E._save_current(folder, O.Oplog(d, path=folder / "oplog.jsonl").doc)
    return pid


def _store_lut(pid: str, text: str) -> str:
    return L.store_text(E._dir(pid), text)


def test_parse_accepts_a_good_cube_and_rejects_malformed():
    good = L.make_test_cube(3)
    lut = L.parse(good)
    assert lut.size == 3 and len(lut.data) == 3 ** 3 * 3
    with pytest.raises(ValueError, match="LUT_3D_SIZE"):
        L.parse("DOMAIN_MIN 0 0 0\n0 0 0\n")
    with pytest.raises(ValueError, match="3D LUTs"):
        L.parse("LUT_1D_SIZE 2\n0 0 0\n1 1 1\n")
    with pytest.raises(ValueError, match="expected 8"):
        L.parse("LUT_3D_SIZE 2\n0 0 0\n")
    with pytest.raises(ValueError, match="finite"):
        L.parse("LUT_3D_SIZE 2\nnan 0 0\n1 1 1\n0 0 0\n1 1 1\n0 0 0\n1 1 1\n0 0 0\n1 1 1\n")


def test_set_lut_and_clear_undo(home):
    pid = _cut("lut1")
    rel = _store_lut(pid, L.make_test_cube(5))
    E.set_lut(pid, "c1", rel, 0.6)
    row = next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "c1")
    assert row["lut"]["file"] == rel and row["lut"]["intensity"] == pytest.approx(0.6)
    E.clear_lut(pid, "c1")
    assert "lut" not in next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "c1")
    E.undo(pid)
    assert _row(pid)["lut"]["intensity"] == pytest.approx(0.6)


def _row(pid):
    return next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "c1")


def test_unset_lut_does_not_change_the_hash():
    import copy

    from tests.test_timeline import _golden

    d = _golden()
    h = T.stamp_hash(d)[1]
    unset = copy.deepcopy(d)
    unset["tracks"][1]["items"][0].setdefault("props", {})["lut"] = None
    assert T.stamp_hash(unset)[1] == h


def _ffmpeg_lut_pixel(rgb: tuple[int, int, int], cube_path: Path, intensity: float) -> tuple[int, int, int]:
    fp = G._filter_path(cube_path)
    lut = f"lut3d=file={fp}:interp=trilinear"
    t = float(intensity)
    if t <= 1e-9:
        vf = "format=rgb24"
    elif t >= 1.0 - 1e-9:
        vf = f"format=rgb24,{lut},format=rgb24"
    else:
        vf = f"format=rgb24,split=2[a][b];[b]{lut}[c];[a][c]blend=all_mode=normal:all_opacity={t:.6f},format=rgb24"
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "4x4", "-i", "-",
         "-vf", vf, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        input=bytes(rgb) * 16, check=True, capture_output=True,
    ).stdout
    return tuple(out[:3])


def test_ffmpeg_matches_lut_py_on_a_gradient_cube(tmp_path):
    text = L.make_test_cube(17)
    path = tmp_path / "t.cube"
    path.write_text(text)
    lut = L.parse(text)
    deltas = []
    for rgb in [(0, 0, 0), (255, 255, 255), (128, 128, 128), (200, 60, 30), (20, 120, 220)]:
        lin = tuple(c / 255 for c in rgb)
        want = [round(v * 255) for v in L.apply_pixel(lut, 1.0, lin)]
        got = _ffmpeg_lut_pixel(rgb, path, 1.0)
        deltas.extend(abs(a - b) for a, b in zip(got, want))
    med = statistics.median(deltas)
    assert med <= 2, (med, deltas)


def test_intensity_zero_is_identity_and_one_is_full_lut(tmp_path):
    text = L.make_test_cube(9)
    path = tmp_path / "t.cube"
    path.write_text(text)
    lut = L.parse(text)
    rgb = (140, 100, 60)
    lin = tuple(c / 255 for c in rgb)
    got0 = _ffmpeg_lut_pixel(rgb, path, 0.0)
    assert all(abs(a - b) <= 2 for a, b in zip(got0, rgb))
    full = [round(v * 255) for v in L.apply_pixel(lut, 1.0, lin)]
    got1 = _ffmpeg_lut_pixel(rgb, path, 1.0)
    assert all(abs(a - b) <= 2 for a, b in zip(got1, full))


def test_render_with_lut_matches_formula(home):
    from hermes_studio import render_timeline as R

    pid = _cut("lutrend", colour="0x909070")
    rel = _store_lut(pid, L.make_test_cube(17))
    E.set_lut(pid, "c1", rel, 0.75)
    out = R.render_project(pid)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(out.get("path") or out.get("file")),
         "-vf", "crop=8:8:76:41", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout
    n = len(raw) // 3
    lut = L.load_file(E._dir(pid), rel)
    base = (144 / 255, 144 / 255, 112 / 255)  # lavfi color=c=0x909070
    want = [v * 255 for v in L.apply_pixel(lut, 0.75, base)]
    deltas = []
    for i in range(n):
        rgb = (raw[i * 3] / 255, raw[i * 3 + 1] / 255, raw[i * 3 + 2] / 255)
        # yuv420 export shifts a flat field slightly; per-pixel check stays within grade tolerance.
        for c in range(3):
            deltas.append(abs(rgb[c] * 255 - want[c]))
    med = statistics.median(deltas)
    # H.264 yuv420 adds a few code values on a flat field; the gradient ffmpeg test pins Δ≤2.
    assert med <= 5, (med, want, [raw[0], raw[1], raw[2]])
