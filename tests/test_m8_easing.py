"""M8: eased transform keyframes and opacity keys match the render (real frames)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from hermes_studio import easing as EZ
from hermes_studio import editor as E
from hermes_studio import render_timeline as R
from hermes_studio import timeline as T

S = T.TICK_RATE


def _eval(expr: str, tvar: str, t: float) -> float:
    py = expr.replace("if(", "_if(").replace("lt(", "_lt(").replace("clip(", "_clip(")
    env = {
        "_if": lambda c, a, b: a if c else b,
        "_lt": lambda x, y: 1 if x < y else 0,
        "_clip": lambda x, lo, hi: max(lo, min(hi, x)),
        tvar: t,
    }
    return float(eval(py, {"__builtins__": {}}, env))  # noqa: S307


def _ffmpeg(*args: str):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True, capture_output=True)


def _frame(path: Path, t: float) -> Image.Image:
    jpg = path.with_suffix(f".f{t:.3f}.jpg")
    _ffmpeg("-ss", f"{t:.6f}", "-i", str(path), "-frames:v", "1", str(jpg))
    return Image.open(jpg).convert("RGB")


def _pair(v: float) -> list[int]:
    f = Fraction(v).limit_denominator(1000)
    return [f.numerator, f.denominator]


def _build_project(home: Path, pid: str, ticks: list[dict]) -> Path:
    folder = home / pid
    (folder / "media").mkdir(parents=True, exist_ok=True)
    dest = folder / "media" / "half.mp4"
    if not dest.exists():
        _ffmpeg(
            "-f", "lavfi", "-i", "color=c=white:s=640x360:d=4:r=30",
            "-f", "lavfi", "-i", "color=c=black:s=320x360:d=4:r=30",
            "-filter_complex", "[0:v][1:v]overlay=320:0[v]", "-map", "[v]",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-t", "4",
            str(dest),
        )
    d = T.new_timeline(pid, size=(640, 360))
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/half.mp4", "dur": 4 * S, "fps": [30, 1]}}
    by["V1"]["items"] = [{
        "id": "c1", "type": "clip", "media": "m1", "src": [0, 4 * S], "at": 0,
        "fade_in": 0, "fade_out": 0, "props": {"keyframes": ticks},
    }]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as _O

    log = _O.Oplog(d, path=folder / "oplog.jsonl")
    E._save_current(folder, log.doc)
    out = R.render_project(pid)
    return Path(out["path"])


@pytest.fixture
def home(monkeypatch):
    td = tempfile.mkdtemp(prefix="hs-m8-")
    monkeypatch.setenv("HERMES_STUDIO_EDITOR", td)
    yield Path(td)


def test_eased_zoom_expr_matches_python():
    """zoompan scale expression (eased) equals easing.interp_scalar on every output frame."""
    fps = 30.0
    plain = [{"at": 0.0, "scale": 1.0}, {"at": 4.0, "scale": 2.0, "ease": "ease-in-out"}]
    frame_kfs = [{**k, "at": k["at"] * fps} for k in plain]
    expr = R._interp_expr_eased(frame_kfs, "scale", "on")
    errs = []
    for n in range(0, 121):
        got = _eval(expr, "on", float(n))
        want = EZ.interp_scalar(plain, "scale", n / fps)
        errs.append(abs(got - want))
    assert max(errs) < 1e-4, max(errs)


def test_opacity_geq_expr_matches_python():
    """Opacity geq expression (clip clock T) equals easing.interp_scalar."""
    plain = [{"at": 0.0, "opacity": 1.0}, {"at": 2.0, "opacity": 0.0, "ease": "ease-in"}]
    expr = R._interp_expr_eased(plain, "opacity", "T")
    errs = []
    for i in range(0, 61):
        t = i / 30.0
        errs.append(abs(_eval(expr, "T", t) - EZ.interp_scalar(plain, "opacity", t)))
    assert max(errs) < 1e-4, max(errs)


def test_eased_push_in_differs_from_linear_on_disk(home):
    """A real eased Ken Burns push is not the same picture as a linear push mid-clip."""
    base = [
        {"at": T.seconds_to_ticks(0), "x": [0, 1], "y": [0, 1], "scale": [1, 1], "rotate": [0, 1]},
        {"at": T.seconds_to_ticks(4), "x": [0, 1], "y": [0, 1], "scale": [2, 1], "rotate": [0, 1]},
    ]
    eased = [dict(base[0], ease="ease-in-out"), base[1]]
    lin = _build_project(home, "m8lin", base)
    eas = _build_project(home, "m8eas", eased)
    a = _frame(lin, 1.0)
    b = _frame(eas, 1.0)
    w, h = a.size
    diffs = [abs(a.getpixel((x, h // 2))[0] - b.getpixel((x, h // 2))[0]) for x in range(0, w, 4)]
    assert max(diffs) > 8


def test_opacity_fade_on_white_region(home):
    """Opacity keys dim the picture on a white field (center of the white half)."""
    ticks = [
        {"at": T.seconds_to_ticks(0), "x": [0, 1], "y": [0, 1], "scale": [1, 1], "rotate": [0, 1], "opacity": [1, 1]},
        {"at": T.seconds_to_ticks(2), "x": [0, 1], "y": [0, 1], "scale": [1, 1], "rotate": [0, 1],
         "opacity": [0, 1], "ease": "ease-in"},
    ]
    vid = _build_project(home, "m8op", ticks)
    errs = []
    for i in range(3, 60, 3):
        t = i / 30.0
        im = _frame(vid, t)
        r = im.getpixel((80, im.size[1] // 2))[0] / 255.0
        want = EZ.interp_scalar(
            [{"at": 0, "opacity": 1.0}, {"at": 2.0, "opacity": 0.0, "ease": "ease-in"}],
            "opacity",
            t,
        )
        errs.append(abs(r - want))
    assert max(errs) <= 0.1, f"max opacity error {max(errs):.4f}"
