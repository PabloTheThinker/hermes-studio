/* Cubic easing — mirrors hermes_studio/easing.py (pinned equal by tests). */
(function () {
  "use strict";

  const DEFAULT_EASE = "linear";

  function easeProgress(u, kind) {
    u = Math.max(0, Math.min(1, u));
    const k = kind || DEFAULT_EASE;
    if (k === "ease-in") return u * u * u;
    if (k === "ease-out") {
      const v = 1 - u;
      return 1 - v * v * v;
    }
    if (k === "ease-in-out") {
      if (u < 0.5) return 4 * u * u * u;
      const v = -2 * u + 2;
      return 1 - (v * v * v) / 2;
    }
    return u;
  }

  function interpScalar(kfs, key, t, easeKey) {
    const ek = easeKey || "ease";
    if (!kfs.length) return 0;
    if (t <= kfs[0].at) return kfs[0][key];
    if (t >= kfs[kfs.length - 1].at) return kfs[kfs.length - 1][key];
    for (let i = 1; i < kfs.length; i++) {
      const a = kfs[i - 1], b = kfs[i];
      if (t < b.at) {
        if (b.at <= a.at) return a[key];
        const u = (t - a.at) / (b.at - a.at);
        const p = easeProgress(u, a[ek]);
        return a[key] + p * (b[key] - a[key]);
      }
    }
    return kfs[kfs.length - 1][key];
  }

  function sampleCurve(kfs, key, t0, t1, n) {
    const out = [];
    const steps = Math.max(2, n || 64);
    for (let i = 0; i <= steps; i++) {
      const t = t0 + ((t1 - t0) * i) / steps;
      out.push([t, interpScalar(kfs, key, t)]);
    }
    return out;
  }

  const api = { DEFAULT_EASE, easeProgress, interpScalar, sampleCurve };
  if (typeof window !== "undefined") window.HSEase = api;
  if (typeof module !== "undefined") module.exports = api;
})();
