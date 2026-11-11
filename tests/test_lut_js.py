"""ui/lut.js matches lut.py (trilinear, same as ffmpeg lut3d interp=trilinear)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_studio import lut as L

LUT_JS = Path(__file__).resolve().parent.parent / "hermes_studio" / "ui" / "lut.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def _run(body: str):
    src = f"const H = require({json.dumps(str(LUT_JS))});\n" + body
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_js_sampler_matches_lut_py():
    text = L.make_test_cube(9)
    lut = L.parse(text)
    pack = L.preview_pack(lut)
    pts = [(0.12, 0.34, 0.56), (0.0, 0.0, 0.0), (1, 1, 1), (0.5, 0.2, 0.9), (0.88, 0.11, 0.44)]
    js = _run(f"""
const pack = H.pack({json.dumps(pack)});
const pts = {json.dumps(pts)};
const out = pts.map(([r,g,b]) => H.sample(pack, r, g, b));
console.log(JSON.stringify(out));
""")
    for (r, g, b), got in zip(pts, js, strict=True):
        want = L.sample_trilinear(lut, r, g, b)
        assert all(abs(a - b) < 1e-5 for a, b in zip(got, want)), (r, g, b, got, want)
