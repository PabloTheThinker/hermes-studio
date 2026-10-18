"""easing.js mirrors easing.py (preview curves and keyframe sampling)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_studio import easing as E

EASING_JS = Path(__file__).resolve().parent.parent / "hermes_studio" / "ui" / "easing.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def _run(body: str):
    src = f"const E = require({json.dumps(str(EASING_JS))});\n" + body
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize("kind", ["linear", "ease-in", "ease-out", "ease-in-out"])
@pytest.mark.parametrize("u", [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1])
def test_ease_progress_matches_python(kind, u):
    js = _run(f"console.log(E.easeProgress({u}, {json.dumps(kind)}))")
    py = E.ease_progress(u, kind)
    assert abs(js - py) < 1e-12, (kind, u, js, py)


def test_interp_scalar_matches_python():
    kfs = [
        {"at": 0.0, "scale": 1.0, "ease": "ease-in-out"},
        {"at": 2.0, "scale": 2.0},
    ]
    pts = [i * 0.1 for i in range(21)]
    js = _run(
        "const kfs = " + json.dumps(kfs) + ";"
        f"console.log(JSON.stringify({json.dumps(pts)}.map((t) => E.interpScalar(kfs, 'scale', t))));"
    )
    for t, jv in zip(pts, js):
        pv = E.interp_scalar(kfs, "scale", t)
        assert abs(jv - pv) < 1e-9, (t, jv, pv)
