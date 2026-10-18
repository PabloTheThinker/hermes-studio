"""mask.js matte matches mask.py (preview = export formula)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_studio import mask as M

MASK_JS = Path(__file__).resolve().parent.parent / "hermes_studio" / "ui" / "mask.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def _run(body: str):
    src = f"const M = require({json.dumps(str(MASK_JS))});\n" + body
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize(
    "shape,mx,my,w,h,feather,invert,lx,ly",
    [
        ("rect", 0, 0, 0.5, 1, 0.08, False, 0.25, 0.5),
        ("rect", 0, 0, 0.5, 1, 0.08, False, 0.75, 0.5),
        ("rect", 0, 0, 0.5, 1, 0.08, False, 0.5, 0.5),
        ("rect", 0, 0, 0.5, 1, 0.08, False, 0.48, 0.5),
        ("rect", 0, 0, 0.5, 1, 0.08, False, 0.52, 0.5),
        ("ellipse", 0.1, -0.05, 0.4, 0.6, 0.06, True, 0.6, 0.4),
    ],
)
def test_matte_at_matches_mask_py(shape, mx, my, w, h, feather, invert, lx, ly):
    w_px, h_px = 320, 180
    py_v = M.matte_at(shape, mx, my, w, h, feather, invert, w_px, h_px, lx, ly)
    js = _run(
        f"console.log(JSON.stringify(M.matteAt({json.dumps(shape)}, {mx}, {my}, {w}, {h}, {feather}, {json.dumps(invert)}, {w_px}, {h_px}, {lx}, {ly})));"
    )
    assert abs(js - py_v) < 1e-5, (js, py_v)
