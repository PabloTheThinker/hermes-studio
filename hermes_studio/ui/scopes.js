/* Hermes Studio scopes: waveform, RGB parade and vectorscope from the graded preview.
 *
 * Pure analysis (analyze) is separate from drawing (draw) so the numbers can be checked
 * under Node, the way mix.js is. Everything works on the 8-bit encoded RGB the browser hands
 * back from getImageData, the same values ffmpeg grades and the render writes:
 *
 *   luma  Y' = 0.2126 R + 0.7152 G + 0.0722 B          (Rec.709, full range 0..255)
 *   Cb = (B - Y') / 1.8556,  Cr = (R - Y') / 1.5748     (each -127.5..127.5 at full chroma)
 *
 * A waveform column is a column of the picture (scaled to `cols`), its height the level; the
 * parade is the same for R, G and B side by side; the vectorscope plots (Cb, Cr) with the
 * Rec.709 75% colour-bar targets, as Resolve and Final Cut draw them.
 */
(function (root) {
  "use strict";
  const WR = 0.2126, WG = 0.7152, WB = 0.0722;
  const KB = 1.8556, KR = 1.5748;
  const VEC = 128; // vectorscope grid, VEC x VEC cells over Cb, Cr in -128..128

  function luma(r, g, b) { return WR * r + WG * g + WB * b; }
  function chroma(r, g, b) {
    const y = luma(r, g, b);
    return [(b - y) / KB, (r - y) / KR];
  }

  // The 75% bars a vectorscope's boxes mark: R, Yl, G, Cy, B, Mg at 75% (191) amplitude.
  const TARGETS = [["R", 191, 0, 0], ["Yl", 191, 191, 0], ["G", 0, 191, 0], ["Cy", 0, 191, 191], ["B", 0, 0, 191], ["Mg", 191, 0, 191]]
    .map(([name, r, g, b]) => { const [cb, cr] = chroma(r, g, b); return { name, cb, cr }; });

  // rgba: Uint8ClampedArray (or any indexable) of w*h*4. cols: waveform columns.
  function analyze(rgba, w, h, cols) {
    cols = Math.max(1, Math.min(cols || w, w));
    const wave = new Uint32Array(cols * 256);
    const par = [new Uint32Array(cols * 256), new Uint32Array(cols * 256), new Uint32Array(cols * 256)];
    const vec = new Uint32Array(VEC * VEC);
    const lo = [255, 255, 255, 255], hi = [0, 0, 0, 0]; // r, g, b, luma
    let n = 0, cmax = 0;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const o = (y * w + x) * 4;
        if (rgba[o + 3] === 0) continue; // fully transparent: not picture
        const r = rgba[o], g = rgba[o + 1], b = rgba[o + 2];
        const c = Math.min(cols - 1, Math.floor((x * cols) / w));
        const yl = luma(r, g, b);
        const yi = Math.min(255, Math.max(0, Math.round(yl)));
        wave[c * 256 + yi]++;
        par[0][c * 256 + r]++; par[1][c * 256 + g]++; par[2][c * 256 + b]++;
        const cb = (b - yl) / KB, cr = (r - yl) / KR;
        const vx = Math.min(VEC - 1, Math.max(0, Math.floor(((cb + 128) / 256) * VEC)));
        const vy = Math.min(VEC - 1, Math.max(0, Math.floor(((128 - cr) / 256) * VEC))); // +Cr up
        vec[vy * VEC + vx]++;
        // Chroma as colour science defines it: the spread of the channels, max - min. Every
        // full primary or secondary reads 100%, a 75% bar 75%, any grey 0. (Distance from the
        // vectorscope centre would not do: on Rec.709 green and magenta sit 16% farther out
        // than red, so a pure red would read 86%.)
        const cm = Math.max(r, g, b) - Math.min(r, g, b);
        if (cm > cmax) cmax = cm;
        const v4 = [r, g, b, yi];
        for (let k = 0; k < 4; k++) { if (v4[k] < lo[k]) lo[k] = v4[k]; if (v4[k] > hi[k]) hi[k] = v4[k]; }
        n++;
      }
    }
    return { cols, n, wave, parade: par, vec, vecSize: VEC,
      stats: n ? { r: [lo[0], hi[0]], g: [lo[1], hi[1]], b: [lo[2], hi[2]], luma: [lo[3], hi[3]],
        chroma: Math.round((cmax / 255) * 1000) / 1000 } : null };
  }

  // A level-column's brightness: log density so a few pixels still show (scopes read sparse
  // highlights), normalised to the busiest cell.
  function glow(count, peak) { return count ? Math.min(1, 0.18 + 0.82 * Math.log1p(count) / Math.log1p(peak)) : 0; }

  function graticule(ctx, x0, w, H, label, k) {
    ctx.strokeStyle = "rgba(242,239,232,.14)";
    ctx.fillStyle = "rgba(242,239,232,.45)";
    ctx.font = `${Math.round(9 * k)}px ui-monospace,monospace`;
    ctx.lineWidth = Math.max(1, Math.round(k));
    for (const p of [0, 25, 50, 75, 100]) {
      const y = Math.round((1 - p / 100) * (H - 1)) + 0.5;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
      if (label) ctx.fillText(String(p), x0 + 2 * k, Math.max(9 * k, y - 2 * k));
    }
  }

  function drawLevels(img, W, H, x0, w, hist, cols, rgb) {
    let peak = 1;
    for (let i = 0; i < hist.length; i++) if (hist[i] > peak) peak = hist[i];
    for (let c = 0; c < cols; c++) {
      const x = x0 + Math.floor((c * w) / cols);
      const x2 = x0 + Math.max(Math.floor(((c + 1) * w) / cols), Math.floor((c * w) / cols) + 1);
      for (let lv = 0; lv < 256; lv++) {
        const k = glow(hist[c * 256 + lv], peak);
        if (!k) continue;
        const y = Math.round((1 - lv / 255) * (H - 1));
        for (let xx = x; xx < x2 && xx < W; xx++) {
          const o = (y * W + xx) * 4;
          img.data[o] = Math.min(255, img.data[o] + rgb[0] * k);
          img.data[o + 1] = Math.min(255, img.data[o + 1] + rgb[1] * k);
          img.data[o + 2] = Math.min(255, img.data[o + 2] + rgb[2] * k);
          img.data[o + 3] = 255;
        }
      }
    }
  }

  // mode: "wave" | "parade" | "vector". a: analyze() result. Paints the whole canvas.
  // k: device pixels per CSS pixel (the canvas is sized to its box x devicePixelRatio), so
  // text and lines stay the same size on screen at any zoom or display density.
  function draw(canvas, mode, a, k) {
    k = k || 1;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.fillStyle = "#08090a";
    ctx.fillRect(0, 0, W, H);
    if (!a || !a.n) return;
    if (mode === "vector") {
      const S = Math.min(W, H), cx = W / 2, cy = H / 2, R = S / 2 - 4 * k;
      const img = ctx.getImageData(0, 0, W, H);
      let peak = 1;
      for (let i = 0; i < a.vec.length; i++) if (a.vec[i] > peak) peak = a.vec[i];
      const V = a.vecSize;
      for (let vy = 0; vy < V; vy++) for (let vx = 0; vx < V; vx++) {
        const k = glow(a.vec[vy * V + vx], peak);
        if (!k) continue;
        const px = Math.round(cx + ((vx + 0.5) / V - 0.5) * 2 * R), py = Math.round(cy + ((vy + 0.5) / V - 0.5) * 2 * R);
        const dot = Math.max(2, Math.round(2 * k));
        for (let dy = 0; dy < dot; dy++) for (let dx = 0; dx < dot; dx++) {
          const x = px + dx, y = py + dy;
          if (x < 0 || y < 0 || x >= W || y >= H) continue;
          const o = (y * W + x) * 4;
          img.data[o] = Math.min(255, img.data[o] + 230 * k); img.data[o + 1] = Math.min(255, img.data[o + 1] + 225 * k);
          img.data[o + 2] = Math.min(255, img.data[o + 2] + 210 * k); img.data[o + 3] = 255;
        }
      }
      ctx.putImageData(img, 0, 0);
      ctx.lineWidth = Math.max(1, Math.round(k));
      ctx.strokeStyle = "rgba(242,239,232,.18)";
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx - R, cy); ctx.lineTo(cx + R, cy); ctx.moveTo(cx, cy - R); ctx.lineTo(cx, cy + R); ctx.stroke();
      // Skin-tone line (about 123 degrees from +Cb, through the I axis), as on most scopes.
      ctx.strokeStyle = "rgba(255,200,61,.28)";
      const th = (123 * Math.PI) / 180;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(th) * R, cy - Math.sin(th) * R); ctx.stroke();
      ctx.strokeStyle = "rgba(242,239,232,.5)"; ctx.fillStyle = "rgba(242,239,232,.7)"; ctx.font = `${Math.round(9 * k)}px ui-monospace,monospace`;
      for (const t of TARGETS) {
        const x = cx + (t.cb / 128) * R, y = cy - (t.cr / 128) * R, b = 4 * k;
        ctx.strokeRect(x - b, y - b, 2 * b, 2 * b);
        ctx.fillText(t.name, x + 6 * k, y + 3 * k);
      }
      return;
    }
    const img = ctx.getImageData(0, 0, W, H);
    if (mode === "parade") {
      const gap = Math.round(4 * k), w = Math.floor((W - gap * 2) / 3);
      const tint = [[255, 70, 60], [70, 235, 90], [80, 130, 255]];
      for (let c = 0; c < 3; c++) drawLevels(img, W, H, c * (w + gap), w, a.parade[c], a.cols, tint[c]);
      ctx.putImageData(img, 0, 0);
      for (let c = 0; c < 3; c++) graticule(ctx, c * (w + gap), w, H, c === 0, k);
      return;
    }
    drawLevels(img, W, H, 0, W, a.wave, a.cols, [215, 225, 205]);
    ctx.putImageData(img, 0, 0);
    graticule(ctx, 0, W, H, true, k);
  }

  const api = { analyze, draw, luma, chroma, TARGETS, VEC };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HSScopes = api;
})(typeof window !== "undefined" ? window : globalThis);
