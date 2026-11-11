/* 3D LUT preview (trilinear, matching lut.py and ffmpeg lut3d interp=trilinear). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.HSLut = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function pack(j) {
    return {
      size: j.size,
      domainMin: j.domain_min || [0, 0, 0],
      domainMax: j.domain_max || [1, 1, 1],
      data: j.data,
    };
  }

  function at(lut, ri, gi, bi) {
    const n = lut.size;
    const i = (bi * n * n + gi * n + ri) * 3;
    return [lut.data[i], lut.data[i + 1], lut.data[i + 2]];
  }

  function mapDomain(lut, r, g, b) {
    const out = [];
    const v = [r, g, b];
    for (let c = 0; c < 3; c++) {
      const lo = lut.domainMin[c];
      const hi = lut.domainMax[c];
      const x = hi === lo ? lo : (v[c] - lo) / (hi - lo);
      out.push(Math.max(0, Math.min(1, x)));
    }
    return out;
  }

  function mix(a, b, t) {
    return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])];
  }

  function sample(lut, r, g, b) {
    const m = mapDomain(lut, r, g, b);
    r = m[0]; g = m[1]; b = m[2];
    const n = lut.size;
    if (n === 1) return at(lut, 0, 0, 0);
    const scale = n - 1;
    const x = r * scale;
    const y = g * scale;
    const z = b * scale;
    const xi = Math.min(n - 2, Math.max(0, Math.floor(x)));
    const yi = Math.min(n - 2, Math.max(0, Math.floor(y)));
    const zi = Math.min(n - 2, Math.max(0, Math.floor(z)));
    const xf = x - xi;
    const yf = y - yi;
    const zf = z - zi;
    const c000 = at(lut, xi, yi, zi);
    const c100 = at(lut, xi + 1, yi, zi);
    const c010 = at(lut, xi, yi + 1, zi);
    const c110 = at(lut, xi + 1, yi + 1, zi);
    const c001 = at(lut, xi, yi, zi + 1);
    const c101 = at(lut, xi + 1, yi, zi + 1);
    const c011 = at(lut, xi, yi + 1, zi + 1);
    const c111 = at(lut, xi + 1, yi + 1, zi + 1);
    const c00 = mix(c000, c100, xf);
    const c01 = mix(c001, c101, xf);
    const c10 = mix(c010, c110, xf);
    const c11 = mix(c011, c111, xf);
    const c0 = mix(c00, c10, yf);
    const c1 = mix(c01, c11, yf);
    return mix(c0, c1, zf);
  }

  function applyPixel(lut, intensity, r, g, b) {
    const t = Math.max(0, Math.min(1, intensity));
    if (t <= 1e-12) return [r, g, b];
    const out = sample(lut, r, g, b);
    if (t >= 1 - 1e-12) return out;
    return [r + t * (out[0] - r), g + t * (out[1] - g), b + t * (out[2] - b)];
  }

  function applyImageData(lut, intensity, data, w, h) {
    const t = Math.max(0, Math.min(1, intensity));
    if (!lut || t <= 1e-12) return;
    for (let i = 0; i < w * h; i++) {
      const o = i * 4;
      const r = data[o] / 255;
      const g = data[o + 1] / 255;
      const b = data[o + 2] / 255;
      const px = applyPixel(lut, t, r, g, b);
      data[o] = Math.max(0, Math.min(255, Math.round(px[0] * 255)));
      data[o + 1] = Math.max(0, Math.min(255, Math.round(px[1] * 255)));
      data[o + 2] = Math.max(0, Math.min(255, Math.round(px[2] * 255)));
    }
  }

  return { pack, sample, applyPixel, applyImageData };
});
