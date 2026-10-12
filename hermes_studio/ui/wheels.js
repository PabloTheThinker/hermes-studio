/* Hermes Studio colour wheels: the maths between a wheel's puck + master and the grade.
 *
 * A grade (grade.py) is per-channel lift / gamma / gain plus saturation. A wheel shows each
 * of the three as a master level (the luma-weighted average of r, g, b) and a colour balance:
 * the puck. The puck sits in the same (Cb, Cr) plane the vectorscope draws -- red up-left,
 * blue right -- so pushing a puck toward a colour pushes the picture's trace the same way.
 *
 *   balance (zero-luma RGB offset) from the puck (px, py) in the unit disc:
 *     Cb = px / 2, Cr = py / 2;  R = 1.5748 Cr;  B = 1.8556 Cb;  G = -(0.2126 R + 0.0722 B) / 0.7152
 *   lift_c  = master + K.lift  * off_c                (an offset of the black point)
 *   gamma_c = master * (1 + K.gamma * off_c)          (multipliers, so the master scales them)
 *   gain_c  = master * (1 + K.gain  * off_c)
 *
 * Because the offset has zero luma, the master is exactly the luma-weighted mean of the three
 * channel values, so fromGrade() recovers the same puck and master the page set: the wheels
 * survive a reload and an undo. curve / table / satMatrix mirror grade.py (a test pins them
 * equal) so a drag can grade the preview live, before the op lands.
 */
(function (root) {
  "use strict";
  const WR = 0.2126, WG = 0.7152, WB = 0.0722;
  const KB = 1.8556, KR = 1.5748;
  const K = { lift: 0.25, gamma: 0.5, gain: 0.5 }; // a puck at the rim: lift +-0.2, gamma/gain x(1 +- 0.4)
  const RANGE = { lift: [-0.5, 0.5], gamma: [0.2, 5], gain: [0, 4], sat: [0, 4], temp: [-100, 100], tint: [-100, 100] };
  const WB_STOPS = 0.5; // grade.WB_STOPS
  // White-balance multipliers (r, g, b): grade.wb, line for line.
  function wb(temp, tint) {
    const a = WB_STOPS / 100;
    const r = Math.pow(2, a * temp + 0.5 * a * tint), g = Math.pow(2, -a * tint), b = Math.pow(2, -a * temp + 0.5 * a * tint);
    const y = WR * r + WG * g + WB * b;
    return [r / y, g / y, b / y];
  }
  // The eyedropper: temp and tint that make an ungraded pixel (0..1) grey (grade.neutralise).
  function neutralise(rgb) {
    const [r, g, b] = rgb.map((v) => Math.max(v, 0));
    if (Math.min(r, g, b) <= 1e-6) return [0, 0];
    const a = WB_STOPS / 100;
    const temp = Math.log2(b / r) / (2 * a);
    const tint = (-Math.log2(r / g) - a * temp) / (1.5 * a);
    const c = (v) => Math.round(Math.min(100, Math.max(-100, v)) * 100) / 100;
    return [c(temp), c(tint)];
  }
  const NEUTRAL = { lift: 0, gamma: 1, gain: 1 };
  const TABLE_POINTS = 257;

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const luma = (r, g, b) => WR * r + WG * g + WB * b;

  // The zero-luma RGB offset a puck at (px, py) stands for.
  function offset(px, py) {
    const cb = px / 2, cr = py / 2;
    const r = KR * cr, b = KB * cb;
    return [r, -(WR * r + WB * b) / WG, b];
  }
  // And back: the puck for a zero-luma offset (inverse of offset()).
  function puck(off) {
    return [(off[2] / KB) * 2, (off[0] / KR) * 2];
  }

  // One wheel's three channel values from its master and puck.
  function channels(kind, m, px, py) {
    const off = offset(px, py), k = K[kind], [lo, hi] = RANGE[kind];
    return off.map((o) => clamp(kind === "lift" ? m + k * o : m * (1 + k * o), lo, hi));
  }

  // Curves: { m | r | g | b: [[x, y], ...] } with x rising from 0 to 1. A straight line
  // (two points, 0->0 and 1->1) is no curve.
  const straight = (pts) => pts.length === 2 && Math.abs(pts[0][1]) < 1e-9 && Math.abs(pts[1][1] - 1) < 1e-9;
  function cleanCurves(cv) {
    const out = {};
    for (const k of ["m", "r", "g", "b"]) if (cv && cv[k] && cv[k].length >= 2 && !straight(cv[k])) out[k] = cv[k].map((p) => [p[0], p[1]]);
    return Object.keys(out).length ? out : null;
  }

  // The page's wheel state -> grade numbers (what the "grade" op takes).
  function toGrade(st) {
    return {
      lift: channels("lift", st.lift.m, st.lift.x, st.lift.y),
      gamma: channels("gamma", st.gamma.m, st.gamma.x, st.gamma.y),
      gain: channels("gain", st.gain.m, st.gain.x, st.gain.y),
      sat: clamp(st.sat, RANGE.sat[0], RANGE.sat[1]),
      curves: cleanCurves(st.curves),
      temp: clamp(st.temp || 0, -100, 100),
      tint: clamp(st.tint || 0, -100, 100),
    };
  }

  // Grade numbers (view row .grade, or null) -> wheel state. Exact inverse of toGrade for
  // anything toGrade produced; for other grades it shows the nearest balance + master.
  function fromGrade(g) {
    const st = { sat: g && g.sat != null ? g.sat : 1, curves: cleanCurves(g && g.curves) || {},
      temp: g && g.temp ? g.temp : 0, tint: g && g.tint ? g.tint : 0 };
    for (const kind of ["lift", "gamma", "gain"]) {
      const v = g && g[kind] ? g[kind] : [NEUTRAL[kind], NEUTRAL[kind], NEUTRAL[kind]];
      const m = luma(v[0], v[1], v[2]);
      const k = K[kind];
      const off = kind === "lift" ? v.map((c) => (c - m) / k) : v.map((c) => (m ? (c / m - 1) / k : 0));
      let [x, y] = puck(off);
      const d = Math.hypot(x, y);
      if (d > 1) { x /= d; y /= d; }
      st[kind] = { m, x, y };
    }
    return st;
  }

  function neutral() { return fromGrade(null); }
  function isNeutral(g) {
    const e = 1e-6;
    return ["lift", "gamma", "gain"].every((k) => g[k].every((v) => Math.abs(v - NEUTRAL[k]) < e)) && Math.abs(g.sat - 1) < e && !cleanCurves(g.curves)
      && Math.abs(g.temp || 0) < e && Math.abs(g.tint || 0) < e;
  }

  // ---- the preview pack, computed here for a live drag (mirrors grade.py) ----------------
  // Monotone cubic (Fritsch-Carlson PCHIP): grade.pchip, line for line.
  function pchip(pts, x) {
    const n = pts.length;
    if (x <= pts[0][0]) return pts[0][1];
    if (x >= pts[n - 1][0]) return pts[n - 1][1];
    if (n === 2) { const [[x0, y0], [x1, y1]] = pts; return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0); }
    const h = [], d = [];
    for (let k = 0; k < n - 1; k++) { h.push(pts[k + 1][0] - pts[k][0]); d.push((pts[k + 1][1] - pts[k][1]) / h[k]); }
    const m = new Array(n).fill(0);
    m[0] = d[0]; m[n - 1] = d[n - 2];
    for (let k = 1; k < n - 1; k++) {
      if (d[k - 1] * d[k] <= 0) m[k] = 0;
      else { const w1 = 2 * h[k] + h[k - 1], w2 = h[k] + 2 * h[k - 1]; m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k]); }
    }
    for (const [e, dd] of [[0, d[0]], [n - 1, d[n - 2]]]) {
      if (m[e] * dd <= 0) m[e] = 0;
      else if (Math.abs(m[e]) > 3 * Math.abs(dd)) m[e] = 3 * dd;
    }
    let k = 0;
    while (k < n - 2 && x > pts[k + 1][0]) k++;
    const t = (x - pts[k][0]) / h[k], t2 = t * t, t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * pts[k][1] + (t3 - 2 * t2 + t) * h[k] * m[k] + (-2 * t3 + 3 * t2) * pts[k + 1][1] + (t3 - t2) * h[k] * m[k + 1];
  }
  function curve(g, ch, x) {
    const lo = g.lift[ch], hi = g.gain[ch], gm = g.gamma[ch];
    if (g.temp || g.tint) x = clamp(x * wb(g.temp || 0, g.tint || 0)[ch], 0, 1);
    let y = Math.pow(clamp(lo + x * (hi - lo), 0, 1), 1 / gm);
    const cv = g.curves;
    if (cv) {
      if (cv.m) y = pchip(cv.m, y);
      const ck = "rgb"[ch];
      if (cv[ck]) y = pchip(cv[ck], y);
      y = clamp(y, 0, 1);
    }
    return y;
  }
  function satMatrix(s) {
    const k = 1 - s;
    return [[k * WR + s, k * WG, k * WB], [k * WR, k * WG + s, k * WB], [k * WR, k * WG, k * WB + s]];
  }
  function preview(g) {
    if (!g || isNeutral(g)) return null;
    const n = TABLE_POINTS - 1;
    const r5 = (v) => Math.round(v * 1e5) / 1e5, r6 = (v) => Math.round(v * 1e6) / 1e6;
    return {
      tables: [0, 1, 2].map((ch) => Array.from({ length: TABLE_POINTS }, (_, i) => r5(curve(g, ch, i / n)))),
      matrix: satMatrix(g.sat).map((row) => row.map(r6)),
    };
  }

  // The hue ring's stops, placed where each colour sits on the vectorscope (CSS conic angles:
  // 0deg at the top, clockwise), so the wheel and the scope agree.
  function ringStops() {
    const cols = [["#ff3b30", 1, 0, 0], ["#ffd60a", 1, 1, 0], ["#34c759", 0, 1, 0], ["#32d5f0", 0, 1, 1], ["#2f6bff", 0, 0, 1], ["#d63bff", 1, 0, 1]];
    const stops = cols.map(([css, r, g, b]) => {
      const y = luma(r, g, b), cb = (b - y) / KB, cr = (r - y) / KR;
      let a = (Math.atan2(cb, cr) * 180) / Math.PI; // x right = Cb, y up = Cr; clockwise from up
      if (a < 0) a += 360;
      return [a, css];
    }).sort((p, q) => p[0] - q[0]);
    const first = stops[0], last = stops[stops.length - 1];
    // Wrap: the colour at 0deg is interpolated between the last and first stops.
    const span = 360 - last[0] + first[0];
    const t = (360 - last[0]) / span;
    const mix = (a, b) => { const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); const A = p(a), B = p(b);
      return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, "0")).join(""); };
    const edge = mix(last[1], first[1]);
    return `${edge} 0deg, ` + stops.map(([a, c]) => `${c} ${a.toFixed(1)}deg`).join(", ") + `, ${edge} 360deg`;
  }

  const api = { K, RANGE, offset, puck, channels, toGrade, fromGrade, neutral, isNeutral, curve, pchip, cleanCurves, wb, neutralise, satMatrix, preview, ringStops, TABLE_POINTS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HSWheels = api;
})(typeof window !== "undefined" ? window : globalThis);
