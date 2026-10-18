/* Feathered rect/ellipse mask matte (mask.py). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.HSMask = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function smoothstep(edge0, edge1, x) {
    if (edge1 <= edge0) return x >= edge1 ? 1 : 0;
    const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
    return t * t * (3 - 2 * t);
  }

  function matteAt(shape, mx, my, w, h, feather, invert, wPx, hPx, lx, ly) {
    if (w <= 0 || h <= 0 || wPx <= 0 || hPx <= 0) return invert ? 1 : 0;
    const cx = 0.5 + mx;
    const cy = 0.5 + my;
    const px = lx * wPx;
    const py = ly * hPx;
    const cxPx = cx * wPx;
    const cyPx = cy * hPx;
    const hwPx = w * wPx * 0.5;
    const hhPx = h * hPx * 0.5;
    const fPx = Math.max(0, feather) * Math.min(wPx, hPx);
    let dPx;
    if (shape === "ellipse") {
      if (hwPx <= 1e-9 || hhPx <= 1e-9) dPx = 1e9;
      else {
        const rn = Math.sqrt(((px - cxPx) / hwPx) ** 2 + ((py - cyPx) / hhPx) ** 2);
        dPx = (rn - 1) * Math.min(hwPx, hhPx);
      }
    } else {
      dPx = Math.max(Math.abs(px - cxPx) - hwPx, Math.abs(py - cyPx) - hhPx);
    }
    let m;
    if (fPx <= 1e-9) m = dPx <= 0 ? 1 : 0;
    else m = smoothstep(0, 1, Math.max(0, Math.min(1, (-dPx) / fPx)));
    if (invert) m = 1 - m;
    return m;
  }

  function interpScalar(kfs, key, t, base) {
    if (!kfs || !kfs.length) return base;
    if (t <= kfs[0].at) return kfs[0][key];
    if (t >= kfs[kfs.length - 1].at) return kfs[kfs.length - 1][key];
    for (let i = 1; i < kfs.length; i++) {
      const a = kfs[i - 1];
      const b = kfs[i];
      if (t < b.at) {
        const u = (t - a.at) / (b.at - a.at);
        return a[key] + u * (b[key] - a[key]);
      }
    }
    return kfs[kfs.length - 1][key];
  }

  function resolveAt(mask, t) {
    const bx = mask.x || 0;
    const by = mask.y || 0;
    const bw = mask.w != null ? mask.w : 0.5;
    const bh = mask.h != null ? mask.h : 1;
    const keys = mask.keys;
    if (!keys || !keys.length) return { x: bx, y: by, w: bw, h: bh };
    const kfs = keys.map((k) => ({
      at: k.at,
      x: k.x != null ? k.x : bx,
      y: k.y != null ? k.y : by,
      w: k.w != null ? k.w : bw,
      h: k.h != null ? k.h : bh,
    })).sort((a, b) => a.at - b.at);
    return {
      x: interpScalar(kfs, "x", t, bx),
      y: interpScalar(kfs, "y", t, by),
      w: interpScalar(kfs, "w", t, bw),
      h: interpScalar(kfs, "h", t, bh),
    };
  }

  function applyMaskedGrade(data, w, h, mask, t, gradedData) {
    const shape = mask.shape || "rect";
    const feather = mask.feather || 0;
    const invert = !!mask.invert;
    const p = resolveAt(mask, t);
    for (let j = 0; j < h; j++) {
      for (let i = 0; i < w; i++) {
        const lx = (i + 0.5) / w;
        const ly = (j + 0.5) / h;
        const m = matteAt(shape, p.x, p.y, p.w, p.h, feather, invert, w, h, lx, ly);
        const o = (j * w + i) * 4;
        for (let c = 0; c < 3; c++) {
          data[o + c] = Math.round(data[o + c] * (1 - m) + gradedData[o + c] * m);
        }
      }
    }
  }

  return { matteAt, resolveAt, smoothstep, applyMaskedGrade };
});
