"""The colour wheels' maths (ui/wheels.js) under Node: the preview it builds for a live drag
equals grade.py's, the wheel state round-trips through a grade, and a puck pushes the colour
the way the vectorscope draws it."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_studio import grade as G

WHEELS_JS = Path(__file__).resolve().parent.parent / "hermes_studio" / "ui" / "wheels.js"
SCOPES_JS = WHEELS_JS.with_name("scopes.js")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def _run(body: str):
    src = f"const W = require({json.dumps(str(WHEELS_JS))}); const S = require({json.dumps(str(SCOPES_JS))});\n" + body
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


GRADES = [
    {"lift": [0.1, 0.0, -0.05], "gamma": [1.0, 1.3, 0.8], "gain": [1.1, 0.95, 1.0], "sat": 0.6},
    {"lift": [0, 0, 0], "gamma": [0.2, 5, 1], "gain": [1, 1, 1], "sat": 1.0},
    {"lift": [-0.2, 0.3, 0.0], "gamma": [1, 1, 1], "gain": [4, 0, 2], "sat": 2.5},
]


@pytest.mark.parametrize("g", GRADES)
def test_the_live_preview_pack_equals_grade_py(g):
    """A drag grades the preview from wheels.js before the op lands; when it does, the view's
    pack (grade.py) replaces it. They must be the same numbers or the picture would jump."""
    js = _run(f"console.log(JSON.stringify(W.preview({json.dumps(g)})))")
    py = G.preview(G.parse(G.store(**g)))
    assert js["matrix"] == py["matrix"]
    for ch in range(3):
        diffs = [abs(a - b) for a, b in zip(js["tables"][ch], py["tables"][ch])]
        assert max(diffs) <= 1e-5 + 1e-12, (ch, max(diffs))


def test_neutral_is_no_grade():
    r = _run("const st = W.neutral(); const g = W.toGrade(st); console.log(JSON.stringify({ st, g, neutral: W.isNeutral(g), prev: W.preview(g) }))")
    assert r["neutral"] and r["prev"] is None
    assert r["g"] == {"lift": [0, 0, 0], "gamma": [1, 1, 1], "gain": [1, 1, 1], "sat": 1, "curves": None, "temp": 0, "tint": 0}
    for k in ("lift", "gamma", "gain"):
        assert abs(r["st"][k]["x"]) < 1e-12 and abs(r["st"][k]["y"]) < 1e-12


def test_wheel_state_round_trips_through_a_grade():
    """Set pucks and masters, turn them into grade numbers (what the op stores), read them back:
    the same pucks and masters. So the wheels show what you left after a reload or an undo."""
    r = _run("""
const st = { lift: { m: 0.05, x: -0.4, y: 0.3 }, gamma: { m: 1.2, x: 0.6, y: -0.2 }, gain: { m: 0.9, x: 0.1, y: 0.7 }, sat: 1.3 };
const back = W.fromGrade(W.toGrade(st));
console.log(JSON.stringify({ st, back }));
""")
    for k in ("lift", "gamma", "gain"):
        for f in ("m", "x", "y"):
            assert abs(r["back"][k][f] - r["st"][k][f]) < 1e-9, (k, f)
    assert r["back"]["sat"] == pytest.approx(1.3)


def test_a_puck_moves_the_master_not_at_all():
    """The balance has zero luma: moving a puck tints without brightening (the master, the
    luma-weighted mean of the channels, stays put)."""
    r = _run("""
const out = [];
for (const [x, y] of [[1, 0], [0, 1], [-0.7, -0.7], [0.3, -0.9]]) {
  const o = W.offset(x, y); out.push(0.2126 * o[0] + 0.7152 * o[1] + 0.0722 * o[2]);
}
console.log(JSON.stringify(out));
""")
    assert all(abs(v) < 1e-12 for v in r)


def test_pushing_a_puck_toward_red_moves_the_vectorscope_toward_red():
    """Gain puck toward the red target on the wheel (where scopes.js draws red): a grey picture
    graded that way lands on the vectorscope in the same direction as pure red."""
    r = _run("""
const red = S.chroma(191, 0, 0), n = Math.hypot(red[0], red[1]);
const dir = [ (red[0] / 127.5) / (n / 127.5), (red[1] / 127.5) / (n / 127.5) ]; // unit vector on the scope
const st = W.neutral(); st.gain.x = 0.8 * dir[0]; st.gain.y = 0.8 * dir[1];
const g = W.toGrade(st);
const px = [0, 1, 2].map((ch) => Math.round(W.curve(g, ch, 128 / 255) * 255));
const c = S.chroma(px[0], px[1], px[2]);
console.log(JSON.stringify({ px, c, red }));
""")
    cb, cr = r["c"]
    rcb, rcr = r["red"]
    cos = (cb * rcb + cr * rcr) / ((cb ** 2 + cr ** 2) ** 0.5 * (rcb ** 2 + rcr ** 2) ** 0.5)
    assert cos > 0.99, r
    assert r["px"][0] > r["px"][1] and r["px"][0] > r["px"][2]


def test_values_are_clamped_to_the_grade_ranges():
    r = _run("""
const st = W.neutral(); st.lift.m = 0.49; st.lift.x = 1; st.gain.m = 3.9; st.gain.y = 1; st.gamma.m = 0.21; st.gamma.x = -1; st.sat = 9;
console.log(JSON.stringify(W.toGrade(st)));
""")
    for k in ("lift", "gamma", "gain"):
        lo, hi = (float(x) for x in G.RANGES[k])
        assert all(lo <= v <= hi for v in r[k]), (k, r[k])
    assert r["sat"] == 4
    G.store(**r)  # and grade.py accepts every one of them


def test_the_ring_puts_red_where_the_vectorscope_does():
    r = _run("console.log(JSON.stringify(W.ringStops()))")
    assert r.startswith("#") and "deg" in r
    red_deg = float(r.split("#ff3b30 ")[1].split("deg")[0])
    assert 270 < red_deg < 360  # up-left of centre, clockwise from the top


CURVES = [
    {"m": [[0, 0], [0.25, 0.15], [0.75, 0.85], [1, 1]]},
    {"r": [[0, 0.1], [0.3, 0.2], [0.6, 0.65], [1, 0.95]], "b": [[0, 0], [0.5, 0.35], [1, 1]],
     "m": [[0, 0.05], [0.2, 0.5], [0.4, 0.55], [0.7, 0.56], [1, 1]]},
]


@pytest.mark.parametrize("cv", CURVES)
def test_the_live_preview_with_curves_equals_grade_py(cv):
    """A curve drag grades the preview from wheels.js; the same numbers must come back from
    grade.py when the op lands (pchip mirrored line for line)."""
    g = {"lift": [0.05, 0, -0.02], "gamma": [1, 1.2, 0.9], "gain": [1, 0.95, 1.1], "sat": 1.1, "curves": cv}
    js = _run(f"console.log(JSON.stringify(W.preview({json.dumps(g)})))")
    py = G.preview(G.parse(G.store(**g)))
    for ch in range(3):
        diffs = [abs(a - b) for a, b in zip(js["tables"][ch], py["tables"][ch])]
        assert max(diffs) <= 2e-5, (ch, max(diffs))  # store() rounds points to 1e-4; tables to 1e-5


def test_curves_ride_along_in_the_wheel_state():
    r = _run("""
const g = { lift: [0,0,0], gamma: [1,1,1], gain: [1,1,1], sat: 1, curves: { m: [[0,0],[0.5,0.7],[1,1]], g: [[0,0],[1,1]] } };
const st = W.fromGrade(g); const back = W.toGrade(st);
console.log(JSON.stringify({ st: st.curves, back: back.curves, neutralWithCurve: W.isNeutral(back),
  straightOnly: W.isNeutral(W.toGrade(W.fromGrade({ ...g, curves: { m: [[0,0],[1,1]] } }))) }));
""")
    assert r["st"] == {"m": [[0, 0], [0.5, 0.7], [1, 1]]}  # the straight green curve is no curve
    assert r["back"] == r["st"] and r["neutralWithCurve"] is False and r["straightOnly"] is True


def test_white_balance_and_eyedropper_mirror_grade_py():
    r = _run("""
const out = { wb: [[0,0],[100,0],[-60,30],[45,80]].map(([t,n]) => W.wb(t, n)),
  neu: [[0.55,0.5,0.4],[0.3,0.42,0.5],[0.2,0.25,0.18]].map((p) => W.neutralise(p)) };
console.log(JSON.stringify(out));
""")
    for (t, n), js in zip([(0, 0), (100, 0), (-60, 30), (45, 80)], r["wb"]):
        assert js == pytest.approx(list(G.wb(t, n)), abs=1e-12)
    for px, js in zip([(0.55, 0.5, 0.4), (0.3, 0.42, 0.5), (0.2, 0.25, 0.18)], r["neu"]):
        assert js == pytest.approx(list(G.neutralise(px)), abs=0.011)


def test_the_live_preview_with_white_balance_equals_grade_py():
    g = {"lift": [0.02, 0, 0], "gamma": [1, 1.1, 1], "gain": [1, 1, 0.95], "sat": 1.1, "temp": -35, "tint": 20,
         "curves": {"m": [[0, 0], [0.5, 0.6], [1, 1]]}}
    js = _run(f"console.log(JSON.stringify(W.preview({json.dumps(g)})))")
    py = G.preview(G.parse(G.store(**g)))
    for ch in range(3):
        assert max(abs(a - b) for a, b in zip(js["tables"][ch], py["tables"][ch])) <= 2e-5
