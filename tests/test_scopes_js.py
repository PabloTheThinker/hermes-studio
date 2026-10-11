"""The scopes (ui/scopes.js), run under Node on synthetic pictures with known answers.

The browser check proves they draw from the graded preview; these prove the numbers: where a
level lands on the waveform and parade, where a colour lands on the vectorscope, and that the
luma weights are the same Rec.709 weights the grade's saturation uses (grade.LUMA).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_studio import grade as G

SCOPES_JS = Path(__file__).resolve().parent.parent / "hermes_studio" / "ui" / "scopes.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def _run(body: str):
    """Run ``body`` with S = scopes.js; it must print one JSON value."""
    src = f"const S = require({json.dumps(str(SCOPES_JS))});\n" + body
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


PIC = r"""
function pic(w, h, fn) {
  const a = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [r, g, b, al] = fn(x, y); const o = (y * w + x) * 4;
    a[o] = r; a[o + 1] = g; a[o + 2] = b; a[o + 3] = al === undefined ? 255 : al;
  }
  return a;
}
function where(hist, cols) { const out = []; for (let c = 0; c < cols; c++) { const lv = []; for (let l = 0; l < 256; l++) if (hist[c * 256 + l]) lv.push(l); out.push(lv); } return out; }
"""


def test_luma_weights_match_the_grade():
    w = _run("console.log(JSON.stringify([S.luma(1,0,0), S.luma(0,1,0), S.luma(0,0,1)]))")
    assert w == pytest.approx(list(G.LUMA))


def test_a_flat_colour_lands_on_one_level_per_trace():
    """R 200, G 60, B 30 everywhere: the parade shows 200 / 60 / 30 in every column, the
    waveform shows the Rec.709 luma, round(87.6) = 88."""
    r = _run(PIC + """
const a = S.analyze(pic(16, 8, () => [200, 60, 30]), 16, 8, 4);
console.log(JSON.stringify({ wave: where(a.wave, 4), r: where(a.parade[0], 4), g: where(a.parade[1], 4), b: where(a.parade[2], 4), stats: a.stats, n: a.n }));
""")
    assert r["n"] == 128
    assert r["wave"] == [[88]] * 4
    assert r["r"] == [[200]] * 4 and r["g"] == [[60]] * 4 and r["b"] == [[30]] * 4
    assert r["stats"] == {"r": [200, 200], "g": [60, 60], "b": [30, 30], "luma": [88, 88], "chroma": round(170 / 255, 3)}


def test_columns_follow_the_picture_left_to_right():
    """Left half black, right half white: the left waveform columns sit at 0, the right at 255."""
    r = _run(PIC + """
const a = S.analyze(pic(20, 4, (x) => x < 10 ? [0, 0, 0] : [255, 255, 255]), 20, 4, 4);
console.log(JSON.stringify(where(a.wave, 4)));
""")
    assert r == [[0], [0], [255], [255]]


def test_vectorscope_puts_75_percent_bars_in_their_target_boxes_and_grey_in_the_centre():
    r = _run(PIC + """
const V = S.VEC, out = {};
const cell = (rgb) => { const a = S.analyze(pic(2, 2, () => rgb), 2, 2); const i = a.vec.findIndex((v) => v > 0); return [i % V, Math.floor(i / V)]; };
const box = (t) => [Math.floor(((t.cb + 128) / 256) * V), Math.floor(((128 - t.cr) / 256) * V)];
for (const [k, rgb] of [["R", [191,0,0]], ["Yl", [191,191,0]], ["G", [0,191,0]], ["Cy", [0,191,191]], ["B", [0,0,191]], ["Mg", [191,0,191]]])
  out[k] = { got: cell(rgb), box: box(S.TARGETS.find((t) => t.name === k)) };
out.grey = cell([128, 128, 128]);
out.redUpLeft = S.chroma(191, 0, 0);
console.log(JSON.stringify(out));
""")
    for k in ("R", "Yl", "G", "Cy", "B", "Mg"):
        assert r[k]["got"] == r[k]["box"], k
    assert r["grey"] == [64, 64]  # zero chroma: the centre cell of a 128 grid
    cb, cr = r["redUpLeft"]
    assert cb < 0 and cr > 0  # red sits upper-left, as on every vectorscope


def test_transparent_pixels_are_not_picture():
    r = _run(PIC + """
const a = S.analyze(pic(4, 4, (x) => x < 2 ? [255, 0, 0, 0] : [10, 10, 10]), 4, 4);
console.log(JSON.stringify({ n: a.n, stats: a.stats }));
""")
    assert r["n"] == 8 and r["stats"]["r"] == [10, 10]


def test_draw_runs_on_a_canvas_shim_for_every_mode():
    """draw() only needs getContext('2d'): a recording shim proves each mode paints without
    throwing and writes pixels (the browser check proves what it looks like)."""
    r = _run(PIC + """
function canvas(W, H) {
  const data = new Uint8ClampedArray(W * H * 4);
  const ctx = { fillStyle: "", strokeStyle: "", font: "", lineWidth: 1, puts: 0,
    fillRect() {}, getImageData() { return { data }; }, putImageData() { this.puts++; },
    beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, arc() {}, strokeRect() {}, fillText() {} };
  return { width: W, height: H, getContext: () => ctx, data, ctx };
}
const a = S.analyze(pic(32, 18, (x, y) => [x * 8, y * 14, 128]), 32, 18, 32);
const out = {};
for (const m of ["wave", "parade", "vector"]) { const c = canvas(120, 80); S.draw(c, m, a); let lit = 0; for (let i = 3; i < c.data.length; i += 4) if (c.data[i]) lit++; out[m] = { puts: c.ctx.puts, lit }; }
console.log(JSON.stringify(out));
""")
    for m in ("wave", "parade", "vector"):
        assert r[m]["puts"] == 1 and r[m]["lit"] > 50, (m, r[m])


def test_chroma_reads_zero_for_grey_full_for_a_primary_and_75_for_75_percent_bars():
    r = _run(PIC + """
const c = (rgb) => S.analyze(pic(2, 2, () => rgb), 2, 2).stats.chroma;
console.log(JSON.stringify({ grey: c([128,128,128]), red: c([255,0,0]), red75: c([191,0,0]), blue: c([0,0,255]) }));
""")
    assert r["grey"] == 0 and r["red"] == 1.0
    assert abs(r["red75"] - 0.749) < 0.002  # 191 / 255
    assert r["blue"] == 1.0  # every full primary reads 100%, whatever its distance on the scope


def test_draw_scales_text_with_the_device_pixel_ratio():
    r = _run(PIC + """
const fonts = [];
function canvas(W, H) { const data = new Uint8ClampedArray(W * H * 4);
  const ctx = { set font(v) { fonts.push(v); }, get font() { return ""; }, fillRect() {}, getImageData() { return { data }; }, putImageData() {},
    beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, arc() {}, strokeRect() {}, fillText() {} };
  return { width: W, height: H, getContext: () => ctx }; }
const a = S.analyze(pic(8, 8, () => [100, 150, 200]), 8, 8);
S.draw(canvas(230, 132), "wave", a, 1); S.draw(canvas(460, 264), "wave", a, 2);
console.log(JSON.stringify(fonts));
""")
    assert r[0].startswith("9px") and r[-1].startswith("18px")
