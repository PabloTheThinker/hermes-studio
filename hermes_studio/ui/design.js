/* Hermes Studio · Design editor (Canva-style). Fabric.js 7 (MIT) on a same-origin canvas.
   One document format with hermes_studio/design.py: pages -> layers in page pixels.
   Hermes Agent edits the same designs through MCP (design_*); the editor picks those edits up live. */
(function () {
  "use strict";
  const F = () => window.fabric;
  const FONTS = { archivo: "Archivo", playfair: "Playfair Italic", caveat: "Caveat (hand)", mono: "JetBrains Mono", opensans: "Open Sans" };
  const fam = (id) => "hs-" + (FONTS[id] ? id : "archivo");
  const SWATCH = ["#0b0b0c", "#f2efe8", "#ffffff", "#ffc83d", "#cd8032", "#f5e6c8", "#ff8fb4", "#111111", "#c9c5bd", "#2b2b2e"];
  const LOOKS = [["bw", "B&W"], ["noir", "Noir"], ["warm", "Warm"], ["cool", "Cool"], ["punch", "Punch"], ["fade", "Fade"]];
  const SIZE_ORDER = ["tiktok-carousel", "story", "square", "youtube-thumb", "x-post"];
  const SIZE_NAME = { "tiktok-carousel": "Carousel", story: "Story", square: "Square post", "youtube-thumb": "Thumbnail", "x-post": "X / LinkedIn" };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  async function call(path, body) {
    const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || res.statusText);
    return data;
  }
  const fileToDataURL = (file) => new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = bad; r.readAsDataURL(file); });

  let fontsReady = null;
  function loadFonts() {
    if (!fontsReady) {
      const want = [["archivo", "400 20px"], ["archivo", "800 20px"], ["playfair", "italic 500 20px"], ["caveat", "600 20px"], ["mono", "500 20px"], ["opensans", "400 20px"]];
      fontsReady = Promise.all(want.map(([id, spec]) => document.fonts.load(`${spec} "${fam(id)}"`).catch(() => null)));
    }
    return fontsReady;
  }

  /* ================================================================ home */
  let S = null; // editor session

  async function home(root) {
    leave();
    document.body.classList.remove("designing");
    root.innerHTML = `<p class="kicker">Design</p><h1>Make the post.<br>Not just the clip.</h1>
      <p class="lede">Carousels, covers, thumbnails and posts. Drag, type, remove backgrounds, export. Hermes Agent can build and edit the same designs for you.</p>
      <div id="dz-start"><p class="hint">Loading…</p></div>
      <div class="proj-h"><h2>Your designs</h2><span class="hint">Newest first</span></div>
      <div id="dz-list"></div>
      <div class="dz-agent"><p class="kicker">With Hermes Agent</p>
        <p>Ask your agent: <span class="mono">“Make a 5-slide TikTok carousel about my new release, my photo on the first slide.”</span>
        It uses the <span class="mono">design_new</span>, <span class="mono">design_edit</span>, <span class="mono">photo</span> and <span class="mono">design_render</span> tools, and the design shows up here for you to finish.</p></div>`;
    let info;
    try { info = await call("/api/designs"); } catch (e) { root.querySelector("#dz-start").innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    const pick = { size: localStorage.getItem("hs.size") || "tiktok-carousel", tpl: "carousel" };
    const start = root.querySelector("#dz-start");
    const drawStart = () => {
      start.innerHTML = `<label class="f">Size</label><div class="dz-sizes">${SIZE_ORDER.filter(k => info.sizes[k]).map(k => {
        const z = info.sizes[k], r = z.w / z.h;
        return `<button class="dz-size ${pick.size === k ? "on" : ""}" data-size="${k}"><span class="dz-shape" style="aspect-ratio:${r}"></span><b>${esc(SIZE_NAME[k] || z.label)}</b><span class="mono">${z.w}×${z.h}</span></button>`;
      }).join("")}</div>
      <label class="f" style="margin-top:1rem">Start from</label><div class="dz-tpls">${info.templates.map(t => `<button class="dz-tpl ${pick.tpl === t.id ? "on" : ""}" data-tpl="${t.id}"><b>${esc(t.label)}</b><span class="mono">${t.pages} page${t.pages > 1 ? "s" : ""}</span></button>`).join("")}</div>
      <div class="row" style="margin-top:1rem"><button class="btn primary" id="dz-create">Create design</button><span class="hint">${esc(info.sizes[pick.size].label)}</span></div>`;
      start.querySelectorAll("[data-size]").forEach(b => b.onclick = () => { pick.size = b.dataset.size; localStorage.setItem("hs.size", pick.size); drawStart(); });
      start.querySelectorAll("[data-tpl]").forEach(b => b.onclick = () => { pick.tpl = b.dataset.tpl; drawStart(); });
      start.querySelector("#dz-create").onclick = async (ev) => {
        ev.target.disabled = true;
        try { const r = await call("/api/design", { size: pick.size, template: pick.tpl }); location.hash = "#/design/" + r.design.id; }
        catch (e) { ev.target.disabled = false; alert(e.message); }
      };
    };
    drawStart();
    const list = root.querySelector("#dz-list");
    if (!info.designs.length) { list.innerHTML = `<div class="empty">No designs yet. Pick a size above.</div>`; return; }
    list.innerHTML = `<div class="dz-grid">${info.designs.map(d => `<div class="dz-card" data-id="${esc(d.id)}">
        <a class="dz-thumb" href="#/design/${esc(d.id)}" style="aspect-ratio:${d.w}/${d.h}">${d.thumb ? `<img src="/design/${esc(d.id)}/${esc(d.thumb)}?v=${encodeURIComponent(d.updated)}" alt="" loading="lazy">` : `<span class="mono">${d.w}×${d.h}</span>`}</a>
        <div class="dz-meta"><a href="#/design/${esc(d.id)}"><b>${esc(d.title)}</b></a><span class="mono">${d.pages} page${d.pages > 1 ? "s" : ""} · ${d.w}×${d.h}</span>
        <span class="dz-acts"><button class="btn sm" data-dup="${esc(d.id)}">Duplicate</button><button class="btn sm" data-del="${esc(d.id)}">Delete</button></span></div></div>`).join("")}</div>`;
    list.querySelectorAll("[data-dup]").forEach(b => b.onclick = async () => { await call(`/api/design/${b.dataset.dup}/duplicate`, {}); home(root); });
    list.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { if (confirm("Move this design to the trash?")) { await call(`/api/design/${b.dataset.del}/delete`, {}); home(root); } });
  }

  /* ================================================================ editor */
  async function open(root, id) {
    leave();
    document.body.classList.add("designing");
    root.innerHTML = `<div class="ed" id="ed">
      <header class="ed-top">
        <a class="btn sm" href="#/design" id="ed-back">← Designs</a>
        <input id="ed-title" class="ed-title" aria-label="Design title" />
        <span class="ed-sep"></span>
        <button class="btn sm" id="ed-undo" title="Undo (Ctrl+Z)">Undo</button>
        <button class="btn sm" id="ed-redo" title="Redo (Ctrl+Shift+Z)">Redo</button>
        <span class="ed-save mono" id="ed-save"></span>
        <span class="ed-grow"></span>
        <select id="ed-resize" class="sm" title="Copy into another size"><option value="">Resize…</option></select>
        <button class="btn sm" id="ed-agent" title="Let Hermes Agent work on this design">Agent</button>
        <button class="btn primary sm" id="ed-export">Export</button>
      </header>
      <nav class="ed-tabs" id="ed-tabs">
        ${[["templates", "Templates"], ["text", "Text"], ["photos", "Photos"], ["shapes", "Shapes"], ["brand", "Brand"]].map(([k, l]) => `<button data-tab="${k}">${l}</button>`).join("")}
      </nav>
      <section class="ed-panel" id="ed-panel"></section>
      <div class="ed-stage" id="ed-stage"><div class="ed-canvas-wrap" id="ed-wrap"><canvas id="ed-canvas"></canvas></div>
        <div class="ed-busy" id="ed-busy" hidden></div>
        <div class="ed-zoom mono"><button class="btn sm" id="ed-zout">−</button><span id="ed-zv"></span><button class="btn sm" id="ed-zin">+</button><button class="btn sm" id="ed-zfit">Fit</button></div></div>
      <aside class="ed-props" id="ed-props"></aside>
      <footer class="ed-pages" id="ed-pages"></footer>
      <input type="file" id="ed-file" accept="image/png,image/jpeg,image/webp" multiple hidden />
    </div>`;
    if (!F()) { root.innerHTML = `<p class="err">The design canvas did not load.</p>`; return; }
    await loadFonts();
    let doc;
    try { doc = (await call(`/api/design/${encodeURIComponent(id)}`)).design; } catch (e) { root.innerHTML = `<p class="err">${esc(e.message)}</p><p><a href="#/design">Back to designs</a></p>`; return; }
    const canvas = new (F().Canvas)(root.querySelector("#ed-canvas"), { preserveObjectStacking: true, backgroundColor: doc.pages[0].bg, selectionColor: "rgba(255,200,61,.08)", selectionBorderColor: "#ffc83d" });
    S = { root, id, doc, canvas, page: 0, hist: [], fut: [], loading: false, dirty: false, saveT: 0, pollT: 0, thumbs: [], tab: "templates", guides: { v: false, h: false }, clip: null, lastSaved: doc.updated, uploads: [] };
    F().InteractiveFabricObject.ownDefaults = Object.assign(F().InteractiveFabricObject.ownDefaults || {}, {
      cornerColor: "#ffc83d", cornerStrokeColor: "#110c00", borderColor: "#ffc83d", cornerSize: 11, transparentCorners: false, cornerStyle: "circle", borderScaleFactor: 1.5,
    });
    $("#ed-title").value = doc.title;
    $("#ed-title").onchange = () => { S.doc.title = $("#ed-title").value.trim() || "Untitled design"; commit(); };
    wireCanvas();
    wireTop();
    wireKeys();
    fit();
    await loadPage(0);
    S.hist = [JSON.stringify(S.doc)];
    drawTab("templates");
    drawProps();
    drawPages();
    window.addEventListener("resize", onResize);
    S.pollT = setInterval(pollAgent, 3000);
    renderThumbsLater();
  }
  const $ = (q) => S.root.querySelector(q);
  function onResize() { if (S) { fit(); } }

  function leave() {
    if (!S) return;
    clearInterval(S.pollT);
    window.removeEventListener("resize", onResize);
    document.removeEventListener("keydown", onKey);
    if (S.dirty) { syncPage(); saveNow(true); }
    try { saveThumb(); } catch { /* best effort */ }
    try { S.canvas.dispose(); } catch { /* already gone */ }
    S = null;
    document.body.classList.remove("designing");
  }

  /* ---------------------------------------------------------------- layer <-> fabric */
  const assetUrl = (src) => `/design/${encodeURIComponent(S.id)}/${src}`;

  function cover(img, w, h) {
    const el = img.getElement();
    const nw = el.naturalWidth || el.width, nh = el.naturalHeight || el.height;
    const s = Math.max(w / nw, h / nh), cw = w / s, ch = h / s;
    img.set({ cropX: (nw - cw) / 2, cropY: (nh - ch) / 2, width: cw, height: ch, scaleX: s, scaleY: s });
    const r = (img.hs && img.hs.radius) || 0;
    img.clipPath = r ? new (F().Rect)({ width: cw, height: ch, rx: r / s, ry: r / s, originX: "center", originY: "center" }) : undefined;
    img.dirty = true;
  }

  async function objFrom(L) {
    const f = F();
    const base = { originX: "left", originY: "top", opacity: L.opacity == null ? 1 : L.opacity };
    let o;
    if (L.type === "text") {
      o = new f.Textbox(L.upper ? String(L.text).toUpperCase() : String(L.text), Object.assign({}, base, {
        left: L.x, top: L.y, width: L.w, fontSize: L.size, fontFamily: fam(L.font), fontWeight: L.weight, fontStyle: L.italic ? "italic" : "normal",
        fill: L.color, textAlign: L.align, lineHeight: L.line, charSpacing: L.spacing, backgroundColor: L.bg || "", splitByGrapheme: false,
      }));
      o.hs = { type: "text", font: L.font, upper: !!L.upper };
    } else if (L.type === "rect") {
      o = new f.Rect(Object.assign({}, base, { left: L.x, top: L.y, width: L.w, height: L.h, fill: L.fill || "transparent", stroke: L.stroke || null, strokeWidth: L.stroke_w || 0, rx: L.radius || 0, ry: L.radius || 0, strokeUniform: true }));
      o.hs = { type: "rect" };
    } else if (L.type === "ellipse") {
      o = new f.Ellipse(Object.assign({}, base, { left: L.x, top: L.y, rx: L.w / 2, ry: L.h / 2, fill: L.fill || "transparent", stroke: L.stroke || null, strokeWidth: L.stroke_w || 0, strokeUniform: true }));
      o.hs = { type: "ellipse" };
    } else if (L.type === "line") {
      const t = L.stroke_w || 6;
      o = new f.Rect(Object.assign({}, base, { left: L.x, top: L.y - t / 2, width: L.w, height: t, fill: L.stroke || "#ffc83d" }));
      o.hs = { type: "line" };
      o.setControlsVisibility({ mt: false, mb: false });
    } else if (L.type === "image") {
      o = await f.FabricImage.fromURL(assetUrl(L.src));
      o.hs = { type: "image", src: L.src, radius: L.radius || 0, fit: L.fit || "cover" };
      o.set(Object.assign({}, base, { left: L.x, top: L.y, flipX: !!L.flip }));
      if (L.fit === "contain") {
        const el = o.getElement(), s = Math.min(L.w / (el.naturalWidth || el.width), L.h / (el.naturalHeight || el.height));
        o.set({ scaleX: s, scaleY: s, left: L.x + (L.w - o.width * s) / 2, top: L.y + (L.h - o.height * s) / 2 });
      } else cover(o, L.w, L.h);
    } else return null;
    if (L.name) o.hs.name = L.name;
    if (L.angle) o.rotate(L.angle);
    return o;
  }

  function layerFrom(o) {
    const c = o.getCenterPoint(), w = o.width * o.scaleX, h = o.height * o.scaleY;
    const L = { x: c.x - w / 2, y: c.y - h / 2, w, opacity: +o.opacity.toFixed(3), angle: +(o.angle || 0).toFixed(2) };
    const t = o.hs && o.hs.type;
    if (o.hs && o.hs.name) L.name = o.hs.name;
    if (t === "text") {
      Object.assign(L, { type: "text", text: o.text, size: +(o.fontSize * o.scaleY).toFixed(2), font: o.hs.font, weight: +o.fontWeight || 400, italic: o.fontStyle === "italic",
        color: o.fill, align: o.textAlign, line: o.lineHeight, spacing: o.charSpacing || 0, upper: !!o.hs.upper, bg: o.backgroundColor || "" });
    } else if (t === "rect" || t === "ellipse") {
      Object.assign(L, { type: t, h, fill: o.fill === "transparent" ? "" : o.fill, stroke: o.stroke || "", stroke_w: o.strokeWidth || 0, radius: t === "rect" ? (o.rx || 0) : 0 });
    } else if (t === "line") {
      Object.assign(L, { type: "line", y: c.y, h: 0, stroke: o.fill, stroke_w: h });
    } else if (t === "image") {
      Object.assign(L, { type: "image", src: o.hs.src, h, fit: o.hs.fit === "contain" ? "contain" : "cover", radius: o.hs.radius || 0, flip: !!o.flipX });
      if (L.fit === "contain") L.fit = "cover"; // contain is baked into the box on first edit
    } else return null;
    for (const k of ["x", "y", "w", "h"]) if (typeof L[k] === "number") L[k] = +L[k].toFixed(2);
    return L;
  }

  function bake(o) {
    const sx = o.scaleX, sy = o.scaleY, t = o.hs && o.hs.type;
    if (sx === 1 && sy === 1 && t !== "image") return;
    if (t === "text") o.set({ fontSize: o.fontSize * sy, width: o.width * sx, scaleX: 1, scaleY: 1 });
    else if (t === "rect") o.set({ width: o.width * sx, height: o.height * sy, scaleX: 1, scaleY: 1 });
    else if (t === "ellipse") o.set({ rx: o.rx * sx, ry: o.ry * sy, scaleX: 1, scaleY: 1 });
    else if (t === "line") o.set({ width: o.width * sx, scaleX: 1, scaleY: 1 });
    else if (t === "image") { o.hs.fit = "cover"; cover(o, o.width * sx, o.height * sy); }
    o.setCoords();
  }

  /* ---------------------------------------------------------------- pages + history */
  function syncPage() {
    if (!S || S.loading) return;
    const layers = S.canvas.getObjects().map(layerFrom).filter(Boolean);
    S.doc.pages[S.page] = { bg: S.canvas.backgroundColor || "#0b0b0c", layers };
  }

  // Page loads are async (images); run them one at a time so fast undo/redo can't interleave two loads.
  let _chain = Promise.resolve();
  function loadPage(i) {
    const run = () => _loadPage(i);
    _chain = _chain.then(run, run);
    return _chain;
  }
  async function _loadPage(i) {
    if (!S) return;
    S.loading = true;
    S.page = clamp(i, 0, S.doc.pages.length - 1);
    const p = S.doc.pages[S.page], objs = [];
    for (const L of p.layers) {
      try { const o = await objFrom(L); if (o) objs.push(o); } catch (e) { console.warn("layer skipped", e); }
    }
    if (!S) return;
    S.canvas.discardActiveObject();
    S.canvas.clear();
    S.canvas.backgroundColor = p.bg;
    objs.forEach(o => S.canvas.add(o));
    S.loading = false;
    S.canvas.requestRenderAll();
  }

  function commit() {
    if (!S || S.loading) return;
    syncPage();
    const snap = JSON.stringify(S.doc);
    if (snap === S.hist[S.hist.length - 1]) return;
    S.hist.push(snap); if (S.hist.length > 80) S.hist.shift();
    S.fut = [];
    S.dirty = true;
    setSave("Editing…");
    clearTimeout(S.saveT); S.saveT = setTimeout(() => saveNow(), 900);
    thumbNow();
  }

  async function restore(snap) {
    S.doc = JSON.parse(snap);
    $("#ed-title").value = S.doc.title;
    await loadPage(Math.min(S.page, S.doc.pages.length - 1));
    S.dirty = true; clearTimeout(S.saveT); S.saveT = setTimeout(() => saveNow(), 600);
    drawProps(); drawPages(); renderThumbsLater();
  }
  function flush() { if (_cs) { clearTimeout(_cs); _cs = 0; commit(); } }
  async function undo() { flush(); if (S.hist.length < 2) return; S.fut.push(S.hist.pop()); await restore(S.hist[S.hist.length - 1]); }
  async function redo() { flush(); if (!S.fut.length) return; const s = S.fut.pop(); S.hist.push(s); await restore(s); }

  function setSave(t) { const el = S && $("#ed-save"); if (el) el.textContent = t; }
  async function saveNow(sync) {
    if (!S) return;
    const id = S.id, body = { design: S.doc };
    if (sync) { // leaving the page: fire and forget
      fetch(`/api/design/${id}/save`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), keepalive: true });
      return;
    }
    try { const r = await call(`/api/design/${id}/save`, body); if (S && S.id === id) { S.dirty = false; S.lastSaved = r.design.updated; setSave("Saved"); } }
    catch (e) { setSave("Not saved: " + e.message); }
  }

  async function pollAgent() { // Hermes Agent edited this design: pick it up when we have nothing unsaved
    if (!S || S.dirty || S.loading || document.hidden) return;
    const a = S.canvas.getActiveObject(); if (a && a.isEditing) return;
    try {
      const r = await call(`/api/design/${encodeURIComponent(S.id)}`);
      if (S && r.design.updated && r.design.updated !== S.lastSaved && !S.dirty) {
        S.lastSaved = r.design.updated; S.doc = r.design; S.hist.push(JSON.stringify(S.doc));
        $("#ed-title").value = S.doc.title;
        await loadPage(Math.min(S.page, S.doc.pages.length - 1)); drawProps(); drawPages(); renderThumbsLater();
        setSave("Updated by Hermes");
      }
    } catch { /* desk offline: try again next tick */ }
  }

  /* ---------------------------------------------------------------- canvas wiring */
  function fit(z) {
    const st = $("#ed-stage"); if (!st) return;
    const W = S.doc.w, H = S.doc.h;
    const auto = Math.min((st.clientWidth - 64) / W, (st.clientHeight - 64) / H);
    S.zoom = clamp(z || auto, 0.05, 3);
    S.canvas.setDimensions({ width: Math.round(W * S.zoom), height: Math.round(H * S.zoom) });
    S.canvas.setZoom(S.zoom);
    $("#ed-zv").textContent = Math.round(S.zoom * 100) + "%";
    S.canvas.requestRenderAll();
  }

  function wireCanvas() {
    const c = S.canvas;
    c.on("object:modified", (e) => { if (e.target) { (e.target.type === "activeselection" ? e.target.getObjects() : [e.target]).forEach(bake); } c.requestRenderAll(); commit(); drawProps(); });
    c.on("text:editing:exited", () => commit());
    c.on("text:changed", () => { S.dirty = true; });
    ["selection:created", "selection:updated", "selection:cleared"].forEach(ev => c.on(ev, () => drawProps()));
    c.on("object:moving", (e) => {
      const o = e.target, ctr = o.getCenterPoint(), W = S.doc.w, H = S.doc.h, thr = 8 / S.zoom;
      let x = ctr.x, y = ctr.y;
      S.guides.v = Math.abs(x - W / 2) < thr; if (S.guides.v) x = W / 2;
      S.guides.h = Math.abs(y - H / 2) < thr; if (S.guides.h) y = H / 2;
      if (S.guides.v || S.guides.h) o.setPositionByOrigin(new (F().Point)(x, y), "center", "center");
    });
    c.on("mouse:up", () => { if (S.guides.v || S.guides.h) { S.guides.v = S.guides.h = false; c.requestRenderAll(); } });
    c.on("after:render", () => {
      if (!S || (!S.guides.v && !S.guides.h)) return;
      const ctx = c.getContext(), z = S.zoom; ctx.save(); ctx.strokeStyle = "#ff4fd8"; ctx.lineWidth = 1; ctx.setLineDash([5, 4]);
      if (S.guides.v) { ctx.beginPath(); ctx.moveTo(S.doc.w / 2 * z + .5, 0); ctx.lineTo(S.doc.w / 2 * z + .5, S.doc.h * z); ctx.stroke(); }
      if (S.guides.h) { ctx.beginPath(); ctx.moveTo(0, S.doc.h / 2 * z + .5); ctx.lineTo(S.doc.w * z, S.doc.h / 2 * z + .5); ctx.stroke(); }
      ctx.restore();
    });
    const st = $("#ed-stage");
    st.addEventListener("dragover", (e) => { e.preventDefault(); st.classList.add("drop"); });
    st.addEventListener("dragleave", () => st.classList.remove("drop"));
    st.addEventListener("drop", (e) => { e.preventDefault(); st.classList.remove("drop"); if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files); });
    $("#ed-file").onchange = (e) => { uploadFiles(e.target.files); e.target.value = ""; };
  }

  function wireTop() {
    $("#ed-undo").onclick = undo; $("#ed-redo").onclick = redo;
    $("#ed-zin").onclick = () => fit(S.zoom * 1.2); $("#ed-zout").onclick = () => fit(S.zoom / 1.2); $("#ed-zfit").onclick = () => fit();
    $("#ed-tabs").querySelectorAll("[data-tab]").forEach(b => b.onclick = () => drawTab(b.dataset.tab));
    $("#ed-export").onclick = exportAll;
    $("#ed-agent").onclick = agentInfo;
    call("/api/designs").then(info => {
      const sel = $("#ed-resize"); if (!sel) return;
      SIZE_ORDER.forEach(k => { const z = info.sizes[k]; if (z && !(z.w === S.doc.w && z.h === S.doc.h)) sel.insertAdjacentHTML("beforeend", `<option value="${k}">${esc(z.label)} · ${z.w}×${z.h}</option>`); });
      sel.onchange = async () => {
        const size = sel.value; sel.value = ""; if (!size) return;
        busy("Resizing…"); syncPage(); await saveNow();
        try { const r = await call(`/api/design/${S.id}/resize`, { size }); busy(); location.hash = "#/design/" + r.design.id; } catch (e) { busy(); alert(e.message); }
      };
    }).catch(() => {});
  }

  function onKey(e) {
    if (!S) return;
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (/INPUT|SELECT|TEXTAREA/.test(tag)) return;
    const o = S.canvas.getActiveObject();
    if (o && o.isEditing) return;
    const mod = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
    if (mod && k === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
    if (mod && k === "y") { e.preventDefault(); redo(); return; }
    if (mod && k === "d") { e.preventDefault(); duplicateSel(); return; }
    if (mod && k === "c" && o) { S.clip = selected().map(layerFrom); return; }
    if (mod && k === "v" && S.clip) { e.preventDefault(); pasteLayers(S.clip.map(L => Object.assign({}, L, { x: L.x + 24, y: L.y + 24 }))); return; }
    if ((k === "delete" || k === "backspace") && o) { e.preventDefault(); removeSel(); return; }
    if (k.startsWith("arrow") && o) {
      e.preventDefault(); const d = e.shiftKey ? 10 : 1;
      o.set({ left: o.left + (k === "arrowleft" ? -d : k === "arrowright" ? d : 0), top: o.top + (k === "arrowup" ? -d : k === "arrowdown" ? d : 0) }); o.setCoords(); S.canvas.requestRenderAll(); commitSoon(); return;
    }
    if (!mod && k === "t") { e.preventDefault(); addText("body"); }
  }
  function wireKeys() { document.addEventListener("keydown", onKey); }
  let _cs = 0; function commitSoon() { clearTimeout(_cs); _cs = setTimeout(() => { _cs = 0; commit(); }, 300); }

  /* ---------------------------------------------------------------- adding */
  async function addLayer(L, select = true) {
    const o = await objFrom(L); if (!o) return null;
    S.canvas.add(o); if (select) S.canvas.setActiveObject(o);
    S.canvas.requestRenderAll(); commit(); drawProps(); return o;
  }
  async function pasteLayers(list) {
    const objs = []; for (const L of list) { const o = await objFrom(L); if (o) { S.canvas.add(o); objs.push(o); } }
    if (objs.length === 1) S.canvas.setActiveObject(objs[0]);
    else if (objs.length) S.canvas.setActiveObject(new (F().ActiveSelection)(objs, { canvas: S.canvas }));
    S.canvas.requestRenderAll(); commit(); drawProps();
  }
  const TEXT_PRESETS = {
    heading: { text: "ADD A HEADING", size: .095, weight: 800, upper: true, line: 1.0 },
    sub: { text: "Add a subheading", size: .06, weight: 700, line: 1.08 },
    body: { text: "Add a little body text. Keep it short enough to read in three seconds.", size: .042, weight: 400, color: "#c9c5bd", line: 1.35 },
    serif: { text: "the line in italics", size: .07, font: "playfair", italic: true, weight: 500, color: "#f5e6c8" },
    hand: { text: "a handwritten note!", size: .065, font: "caveat", weight: 600, color: "#ff8fb4", angle: -6 },
    kicker: { text: "01 · KICKER", size: .034, font: "mono", weight: 500, color: "#ffc83d", spacing: 60 },
    banner: { text: "One line on a cream banner.", size: .045, weight: 700, color: "#111111", bg: "#f5e6c8", align: "center" },
    handle: { text: localStorage.getItem("hs.handle") || "@yourhandle", size: .036, font: "mono", weight: 500, color: "#f2efe8" },
  };
  function addText(kind) {
    const p = TEXT_PRESETS[kind] || TEXT_PRESETS.body, W = S.doc.w, H = S.doc.h, m = Math.round(W * .074);
    const size = Math.round(W * p.size);
    return addLayer({ type: "text", text: p.text, x: m, y: Math.round(H * .4), w: W - 2 * m, size, font: p.font || "archivo", weight: p.weight, italic: !!p.italic, color: p.color || "#f2efe8",
      align: p.align || "left", line: p.line || 1.15, spacing: p.spacing || 0, upper: !!p.upper, bg: p.bg || "", opacity: 1, angle: p.angle || 0 });
  }
  function addShape(kind) {
    const W = S.doc.w, H = S.doc.h, s = Math.round(Math.min(W, H) * .3);
    const c = { x: (W - s) / 2, y: (H - s) / 2 };
    const L = {
      rect: { type: "rect", ...c, w: s, h: s, fill: "#ffc83d", radius: 0 },
      round: { type: "rect", ...c, w: s, h: s, fill: "#ffc83d", radius: Math.round(s * .16) },
      circle: { type: "ellipse", ...c, w: s, h: s, fill: "#ffc83d" },
      ring: { type: "ellipse", ...c, w: s, h: s, fill: "", stroke: "#ffc83d", stroke_w: Math.max(4, Math.round(s * .04)) },
      line: { type: "line", x: W * .1, y: H / 2, w: W * .8, h: 0, stroke: "#ffc83d", stroke_w: Math.max(4, Math.round(W * .006)) },
      card: { type: "rect", x: W * .074, y: H * .45, w: W * .852, h: H * .3, fill: "#f5f1e8", radius: Math.round(W * .026) },
      pill: { type: "rect", x: W * .074, y: H * .8, w: W * .34, h: W * .1, fill: "#ffc83d", radius: Math.round(W * .05) },
      shade: { type: "rect", x: 0, y: H * .55, w: W, h: H * .45, fill: "#000000b3", radius: 0 },
    }[kind];
    return addLayer(Object.assign({ opacity: 1, angle: 0 }, L));
  }
  async function addImage(src, natural) {
    const W = S.doc.w, H = S.doc.h;
    let w = W * .8, h = H * .5;
    if (natural && natural.w && natural.h) { const s = Math.min(W * .8 / natural.w, H * .7 / natural.h); w = natural.w * s; h = natural.h * s; }
    return addLayer({ type: "image", src, x: (W - w) / 2, y: (H - h) / 2, w, h, fit: "cover", radius: 0, opacity: 1, angle: 0 });
  }
  function imgSize(url) { return new Promise((ok) => { const i = new Image(); i.onload = () => ok({ w: i.naturalWidth, h: i.naturalHeight }); i.onerror = () => ok(null); i.src = url; }); }
  async function uploadFiles(files) {
    for (const f of Array.from(files || [])) {
      if (!/^image\/(png|jpeg|webp)$/.test(f.type)) { alert(`${f.name}: PNG, JPEG or WebP only`); continue; }
      if (f.size > 22 * 1024 * 1024) { alert(`${f.name}: too large (22 MB max)`); continue; }
      busy("Uploading " + f.name + "…");
      try {
        const r = await call(`/api/design/${S.id}/asset`, { data: await fileToDataURL(f), name: f.name.replace(/\.[^.]+$/, "") });
        S.uploads.unshift(r.src); await addImage(r.src, await imgSize(assetUrl(r.src)));
      } catch (e) { alert(e.message); }
      busy();
    }
    if (S.tab === "photos") drawTab("photos");
  }

  /* ---------------------------------------------------------------- selection actions */
  const selected = () => { const a = S.canvas.getActiveObject(); return !a ? [] : a.type === "activeselection" ? a.getObjects() : [a]; };
  function removeSel() { const sel = selected(); if (!sel.length) return; S.canvas.discardActiveObject(); sel.forEach(o => S.canvas.remove(o)); S.canvas.requestRenderAll(); commit(); drawProps(); }
  function duplicateSel() { const sel = selected(); if (sel.length) pasteLayers(sel.map(layerFrom).filter(Boolean).map(L => Object.assign({}, L, { x: L.x + 24, y: L.y + 24 }))); }
  function arrange(how) {
    const o = S.canvas.getActiveObject(); if (!o) return; const c = S.canvas;
    ({ front: () => c.bringObjectToFront(o), back: () => c.sendObjectToBack(o), up: () => c.bringObjectForward(o), down: () => c.sendObjectBackwards(o) })[how]();
    c.requestRenderAll(); commit();
  }
  function align(how) {
    const o = S.canvas.getActiveObject(); if (!o) return;
    const r = o.getBoundingRect(), W = S.doc.w, H = S.doc.h, ctr = o.getCenterPoint();
    // getBoundingRect is in canvas pixels at the current zoom in Fabric 7 when absolute=false; normalise
    const z = 1, bw = r.width / z, bh = r.height / z;
    let x = ctr.x, y = ctr.y;
    if (how === "left") x = bw / 2; if (how === "center") x = W / 2; if (how === "right") x = W - bw / 2;
    if (how === "top") y = bh / 2; if (how === "middle") y = H / 2; if (how === "bottom") y = H - bh / 2;
    o.setPositionByOrigin(new (F().Point)(x, y), "center", "center"); o.setCoords(); S.canvas.requestRenderAll(); commit();
  }
  function setProp(o, key, val, live) {
    const t = o.hs.type;
    if (key === "font") { o.hs.font = val; o.set("fontFamily", fam(val)); }
    else if (key === "upper") { o.hs.upper = val; if (val) o.set("text", o.text.toUpperCase()); }
    else if (key === "italic") o.set("fontStyle", val ? "italic" : "normal");
    else if (key === "radius") { if (t === "image") { o.hs.radius = val; cover(o, o.width * o.scaleX, o.height * o.scaleY); } else o.set({ rx: val, ry: val }); }
    else if (key === "stroke_w") { if (t === "line") { const c = o.getCenterPoint(); o.set("height", val); o.setPositionByOrigin(c, "center", "center"); } else o.set("strokeWidth", val); }
    else if (key === "fill" && t === "line") o.set("fill", val);
    else o.set(key, val);
    if (t === "text") o.initDimensions && o.initDimensions();
    o.setCoords(); S.canvas.requestRenderAll();
    if (!live) commit();
  }

  async function photoOp(op, look) {
    const o = S.canvas.getActiveObject(); if (!o || o.hs.type !== "image") return;
    busy({ cutout: "Removing the background…", enhance: "Enhancing…", look: "Applying look…" }[op]);
    try {
      const r = await call(`/api/design/${S.id}/photo`, { src: o.hs.src, op, look });
      const L = layerFrom(o); L.src = r.src;
      const n = await objFrom(L); const idx = S.canvas.getObjects().indexOf(o);
      S.canvas.remove(o); S.canvas.insertAt(idx, n); S.canvas.setActiveObject(n); S.uploads.unshift(r.src);
      S.canvas.requestRenderAll(); commit(); drawProps();
    } catch (e) { alert(e.message); }
    busy();
  }
  function fillPage() {
    const o = S.canvas.getActiveObject(); if (!o || o.hs.type !== "image") return;
    o.set({ angle: 0, left: 0, top: 0 }); o.hs.fit = "cover"; cover(o, S.doc.w, S.doc.h); o.set({ left: 0, top: 0 }); o.setCoords();
    S.canvas.sendObjectToBack(o); S.canvas.requestRenderAll(); commit(); drawProps();
  }

  /* ---------------------------------------------------------------- left panel */
  async function drawTab(tab) {
    S.tab = tab;
    $("#ed-tabs").querySelectorAll("[data-tab]").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
    const P = $("#ed-panel");
    if (tab === "text") {
      P.innerHTML = `<p class="ed-h">Text</p><p class="hint">Click to add. Double-click on the page to type. Shortcut: T.</p>
        <button class="ed-add t-heading" data-text="heading">ADD A HEADING</button>
        <button class="ed-add t-sub" data-text="sub">Add a subheading</button>
        <button class="ed-add t-body" data-text="body">Add body text</button>
        <p class="ed-h">Styles that read on a phone</p>
        <button class="ed-add t-serif" data-text="serif">the line in italics</button>
        <button class="ed-add t-hand" data-text="hand">a handwritten note!</button>
        <button class="ed-add t-kicker" data-text="kicker">01 · KICKER</button>
        <button class="ed-add t-banner" data-text="banner">Cream banner</button>
        <button class="ed-add t-handle" data-text="handle">${esc(TEXT_PRESETS.handle.text)}</button>`;
      P.querySelectorAll("[data-text]").forEach(b => b.onclick = () => addText(b.dataset.text));
    } else if (tab === "shapes") {
      P.innerHTML = `<p class="ed-h">Shapes</p><div class="ed-shapes">${[["rect", "Square"], ["round", "Rounded"], ["circle", "Circle"], ["ring", "Ring"], ["line", "Line"], ["card", "Card"], ["pill", "Button"], ["shade", "Shade"]].map(([k, l]) => `<button class="ed-shape s-${k}" data-shape="${k}"><i></i><span>${l}</span></button>`).join("")}</div>
        <p class="hint">Card = a white panel for proof or a screenshot. Shade = a dark wash so text reads over a photo.</p>`;
      P.querySelectorAll("[data-shape]").forEach(b => b.onclick = () => addShape(b.dataset.shape));
    } else if (tab === "photos") {
      const used = [...new Set([...S.uploads, ...S.doc.pages.flatMap(p => p.layers.filter(l => l.type === "image").map(l => l.src))])];
      P.innerHTML = `<p class="ed-h">Photos</p><button class="btn primary" id="ed-up" style="width:100%">Upload images</button><p class="hint">Or drop files on the page. PNG, JPEG, WebP. They stay on this computer.</p>
        ${used.length ? `<p class="ed-h">In this design</p><div class="ed-imgs">${used.map(s => `<button data-src="${esc(s)}"><img src="${assetUrl(s)}" alt="" loading="lazy"></button>`).join("")}</div>` : ""}
        <p class="ed-h">From your clips</p><div class="ed-imgs" id="ed-clipimgs"><p class="hint">Loading…</p></div>`;
      $("#ed-up").onclick = () => $("#ed-file").click();
      P.querySelectorAll("[data-src]").forEach(b => b.onclick = async () => addImage(b.dataset.src, await imgSize(assetUrl(b.dataset.src))));
      try {
        const lib = await call("/api/library");
        const thumbs = (lib.runs || []).flatMap(r => (r.clips || []).filter(c => c.thumb).map(c => ({ job: r.id, file: c.thumb, title: c.title }))).slice(0, 24);
        const box = S && $("#ed-clipimgs"); if (!box) return;
        box.innerHTML = thumbs.length ? thumbs.map(t => `<button data-job="${esc(t.job)}" data-file="${esc(t.file)}" title="${esc(t.title)}"><img src="/media/${encodeURIComponent(t.job)}/${encodeURIComponent(t.file)}" alt="" loading="lazy"></button>`).join("") : `<p class="hint">Clip frames from your runs show up here.</p>`;
        box.querySelectorAll("[data-job]").forEach(b => b.onclick = async () => {
          busy("Adding frame…");
          try { const r = await call(`/api/design/${S.id}/from-clip`, { job: b.dataset.job, file: b.dataset.file }); await addImage(r.src, await imgSize(assetUrl(r.src))); } catch (e) { alert(e.message); }
          busy();
        });
      } catch { const box = S && $("#ed-clipimgs"); if (box) box.innerHTML = `<p class="hint">Library not available.</p>`; }
    } else if (tab === "brand") {
      const kit = brandKit();
      P.innerHTML = `<p class="ed-h">Brand kit</p><p class="hint">Saved on this computer. Click a colour to apply it to the selection, or to the page if nothing is selected.</p>
        <div class="ed-sw">${kit.colors.map(c => `<button data-color="${c}" style="background:${c}" title="${c}"></button>`).join("")}<label class="ed-sw-add" title="Add colour"><input type="color" id="ed-addc" value="#ffc83d">+</label></div>
        <label class="f">Your handle</label><input id="ed-handle" value="${esc(kit.handle)}" placeholder="@yourhandle" />
        <button class="btn" id="ed-addhandle" style="margin-top:.5rem">Add handle to page</button>
        <label class="f" style="margin-top:1rem">Fonts</label><p class="hint">Headline Archivo · Accent Playfair Italic · Notes Caveat · Labels JetBrains Mono</p>
        <button class="btn sm" id="ed-kitreset" style="margin-top:.6rem">Reset colours</button>`;
      P.querySelectorAll("[data-color]").forEach(b => b.onclick = () => applyColor(b.dataset.color));
      $("#ed-addc").onchange = (e) => { kit.colors.push(e.target.value); saveKit(kit); drawTab("brand"); };
      $("#ed-handle").onchange = (e) => { kit.handle = e.target.value.trim(); saveKit(kit); TEXT_PRESETS.handle.text = kit.handle || "@yourhandle"; };
      $("#ed-addhandle").onclick = () => addText("handle");
      $("#ed-kitreset").onclick = () => { kit.colors = SWATCH.slice(); saveKit(kit); drawTab("brand"); };
    } else {
      P.innerHTML = `<p class="ed-h">Templates</p><p class="hint">Adds the template's pages after this one. Your pages stay.</p><div id="ed-tpls"><p class="hint">Loading…</p></div>`;
      try {
        const info = await call("/api/designs");
        const box = S && $("#ed-tpls"); if (!box) return;
        box.innerHTML = info.templates.filter(t => t.id !== "blank").map(t => `<button class="ed-tpl" data-tpl="${t.id}"><b>${esc(t.label)}</b><span class="mono">${t.pages} page${t.pages > 1 ? "s" : ""}</span></button>`).join("");
        box.querySelectorAll("[data-tpl]").forEach(b => b.onclick = async () => {
          const r = await call(`/api/design-template/${b.dataset.tpl}?w=${S.doc.w}&h=${S.doc.h}`);
          syncPage();
          const cur = S.doc.pages[S.page], blank = !cur.layers.length;
          S.doc.pages.splice(blank ? S.page : S.page + 1, blank ? 1 : 0, ...r.pages);
          await loadPage(blank ? S.page : S.page + 1); S.hist.push("x"); commit(); drawPages(); renderThumbsLater();
        });
      } catch (e) { const box = S && $("#ed-tpls"); if (box) box.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
    }
  }
  function brandKit() { try { const k = JSON.parse(localStorage.getItem("hs.kit") || "null"); if (k && Array.isArray(k.colors)) return k; } catch { /* reset */ } return { colors: SWATCH.slice(), handle: localStorage.getItem("hs.handle") || "" }; }
  function saveKit(k) { localStorage.setItem("hs.kit", JSON.stringify(k)); localStorage.setItem("hs.handle", k.handle || ""); }
  function applyColor(c) {
    const sel = selected();
    if (!sel.length) { S.canvas.backgroundColor = c; S.canvas.requestRenderAll(); commit(); drawProps(); return; }
    sel.forEach(o => { const t = o.hs.type; if (t === "image") return; setProp(o, t === "ellipse" && !o.fill ? "stroke" : "fill", c, true); });
    commit(); drawProps();
  }

  /* ---------------------------------------------------------------- right panel */
  function colorRow(label, key, val, allowNone) {
    return `<label class="f">${label}</label><div class="ed-crow"><input type="color" data-k="${key}" value="${/^#[0-9a-f]{6}/i.test(val || "") ? val.slice(0, 7) : "#000000"}">
      <div class="ed-sw sm">${brandKit().colors.slice(0, 8).map(c => `<button data-k="${key}" data-v="${c}" style="background:${c}" title="${c}"></button>`).join("")}${allowNone ? `<button data-k="${key}" data-v="" class="none" title="None">∅</button>` : ""}</div></div>`;
  }
  const num = (label, key, val, min, max, step) => `<label class="f">${label} <span class="mono" data-show="${key}">${val}</span></label><input type="range" data-k="${key}" data-num="1" min="${min}" max="${max}" step="${step}" value="${val}">`;

  function drawProps() {
    if (!S) return;
    const P = $("#ed-props"), sel = selected(), o = sel.length === 1 ? sel[0] : null;
    if (!sel.length) {
      P.innerHTML = `<p class="ed-h">Page ${S.page + 1} of ${S.doc.pages.length}</p>${colorRow("Background", "bg", S.canvas.backgroundColor)}
        <p class="hint" style="margin-top:1rem">${S.doc.w}×${S.doc.h}. Use Resize at the top to copy this design into another size.</p>
        <p class="ed-h">Shortcuts</p><p class="hint mono">T text · Del delete · ⌘/Ctrl D duplicate · ⌘/Ctrl Z undo · arrows nudge (Shift ×10) · double-click to type</p>`;
    } else if (!o) {
      P.innerHTML = `<p class="ed-h">${sel.length} selected</p><div class="ed-btns"><button class="btn sm" data-act="dup">Duplicate</button><button class="btn sm" data-act="del">Delete</button></div>
        ${colorRow("Colour", "fill", "")}<p class="ed-h">Align to page</p>${alignBtns()}`;
    } else {
      const t = o.hs.type;
      let h = `<p class="ed-h">${{ text: "Text", rect: "Shape", ellipse: "Shape", line: "Line", image: "Photo" }[t]}</p>`;
      if (t === "text") {
        h += `<label class="f">Font</label><select data-k="font">${Object.entries(FONTS).map(([k, l]) => `<option value="${k}" ${o.hs.font === k ? "selected" : ""}>${l}</option>`).join("")}</select>
          <div class="ed-two"><div><label class="f">Size</label><input type="number" data-k="fontSize" data-num="1" min="6" max="600" value="${Math.round(o.fontSize)}"></div>
          <div><label class="f">Weight</label><select data-k="fontWeight" data-num="1">${[300, 400, 500, 600, 700, 800, 900].map(w => `<option ${+o.fontWeight === w ? "selected" : ""}>${w}</option>`).join("")}</select></div></div>
          <div class="ed-btns" style="margin-top:.6rem">${["left", "center", "right"].map(a => `<button class="btn sm ${o.textAlign === a ? "on" : ""}" data-k="textAlign" data-v="${a}">${a[0].toUpperCase() + a.slice(1)}</button>`).join("")}
          <button class="btn sm ${o.fontStyle === "italic" ? "on" : ""}" data-k="italic" data-v="${o.fontStyle === "italic" ? "" : "1"}"><i>I</i></button>
          <button class="btn sm ${o.hs.upper ? "on" : ""}" data-k="upper" data-v="${o.hs.upper ? "" : "1"}">AA</button></div>
          ${colorRow("Colour", "fill", o.fill)}${colorRow("Box behind text", "backgroundColor", o.backgroundColor, true)}
          ${num("Line height", "lineHeight", (+o.lineHeight).toFixed(2), .7, 2.2, .02)}${num("Letter spacing", "charSpacing", o.charSpacing || 0, -50, 400, 5)}`;
      } else if (t === "image") {
        h += `<p class="hint">Edits make a new copy. The original stays in Photos.</p>
          <button class="btn primary" data-photo="cutout" style="width:100%">Remove background</button>
          <button class="btn" data-photo="enhance" style="width:100%;margin-top:.4rem">Enhance</button>
          <label class="f">Looks</label><div class="ed-btns">${LOOKS.map(([k, l]) => `<button class="btn sm" data-photo="look" data-look="${k}">${l}</button>`).join("")}</div>
          <div class="ed-btns" style="margin-top:.6rem"><button class="btn sm" data-act="fill">Fill page</button><button class="btn sm ${o.flipX ? "on" : ""}" data-k="flipX" data-v="${o.flipX ? "" : "1"}">Flip</button></div>
          ${num("Corner radius", "radius", Math.round(o.hs.radius || 0), 0, Math.round(Math.min(S.doc.w, S.doc.h) / 2), 2)}`;
      } else {
        h += colorRow(t === "line" ? "Colour" : "Fill", "fill", o.fill, t !== "line");
        if (t !== "line") h += colorRow("Border", "stroke", o.stroke || "", true) + num("Border width", "stroke_w", o.strokeWidth || 0, 0, 60, 1);
        if (t === "line") h += num("Thickness", "stroke_w", Math.round(o.height), 1, 80, 1);
        if (t === "rect") h += num("Corner radius", "radius", Math.round(o.rx || 0), 0, Math.round(Math.min(o.width, o.height) / 2), 1);
      }
      h += num("Opacity", "opacity", (+o.opacity).toFixed(2), 0, 1, .02);
      h += `<p class="ed-h">Arrange</p><div class="ed-btns"><button class="btn sm" data-arr="front">Front</button><button class="btn sm" data-arr="up">Forward</button><button class="btn sm" data-arr="down">Backward</button><button class="btn sm" data-arr="back">Back</button></div>
        <p class="ed-h">Align to page</p>${alignBtns()}
        <div class="ed-btns" style="margin-top:.8rem"><button class="btn sm" data-act="dup">Duplicate</button><button class="btn sm" data-act="del">Delete</button></div>`;
      P.innerHTML = h;
    }
    bindProps(P, sel, o);
  }
  const alignBtns = () => `<div class="ed-btns">${[["left", "Left"], ["center", "Centre"], ["right", "Right"], ["top", "Top"], ["middle", "Middle"], ["bottom", "Bottom"]].map(([k, l]) => `<button class="btn sm" data-al="${k}">${l}</button>`).join("")}</div>`;

  function bindProps(P, sel, o) {
    P.querySelectorAll("[data-act]").forEach(b => b.onclick = () => ({ dup: duplicateSel, del: removeSel, fill: fillPage })[b.dataset.act]());
    P.querySelectorAll("[data-arr]").forEach(b => b.onclick = () => arrange(b.dataset.arr));
    P.querySelectorAll("[data-al]").forEach(b => b.onclick = () => align(b.dataset.al));
    P.querySelectorAll("[data-photo]").forEach(b => b.onclick = () => photoOp(b.dataset.photo, b.dataset.look));
    const apply = (key, raw, live) => {
      if (key === "bg") { S.canvas.backgroundColor = raw || "#0b0b0c"; S.canvas.requestRenderAll(); if (!live) { commit(); drawProps(); } return; }
      const val = key === "italic" || key === "upper" || key === "flipX" ? !!raw : raw;
      const targets = o ? [o] : sel;
      targets.forEach(x => { if (x.hs.type === "image" && key === "fill") return; setProp(x, key, val, true); });
      if (!live) { commit(); drawProps(); }
    };
    P.querySelectorAll("button[data-k]").forEach(b => b.onclick = () => apply(b.dataset.k, b.dataset.v, false));
    P.querySelectorAll("input[data-k],select[data-k]").forEach(inp => {
      const read = () => inp.dataset.num ? +inp.value : inp.value;
      inp.oninput = () => { const s = P.querySelector(`[data-show="${inp.dataset.k}"]`); if (s) s.textContent = inp.value; if (inp.type === "range" || inp.type === "color") apply(inp.dataset.k, read(), true); };
      inp.onchange = () => apply(inp.dataset.k, read(), false);
    });
  }

  /* ---------------------------------------------------------------- pages strip */
  function drawPages() {
    if (!S) return;
    const P = $("#ed-pages"), r = S.doc.w / S.doc.h;
    P.innerHTML = S.doc.pages.map((p, i) => `<div class="ed-pg ${i === S.page ? "on" : ""}" data-pg="${i}" style="aspect-ratio:${r}">${S.thumbs[i] ? `<img src="${S.thumbs[i]}" alt="">` : `<span style="background:${esc(p.bg)}"></span>`}<b class="mono">${i + 1}</b></div>`).join("")
      + `<button class="ed-pg add" id="ed-addpg" style="aspect-ratio:${r}" title="Add page">+</button>
      <div class="ed-pgacts"><button class="btn sm" data-pa="dup">Duplicate page</button><button class="btn sm" data-pa="left">←</button><button class="btn sm" data-pa="right">→</button><button class="btn sm" data-pa="del">Delete page</button></div>`;
    P.querySelectorAll("[data-pg]").forEach(el => el.onclick = () => goPage(+el.dataset.pg));
    $("#ed-addpg").onclick = async () => { syncPage(); S.doc.pages.splice(S.page + 1, 0, { bg: S.canvas.backgroundColor || "#0b0b0c", layers: [] }); S.thumbs.splice(S.page + 1, 0, ""); await loadPage(S.page + 1); commit(); drawPages(); drawProps(); };
    P.querySelectorAll("[data-pa]").forEach(b => b.onclick = async () => {
      syncPage(); const i = S.page, pg = S.doc.pages, th = S.thumbs;
      if (b.dataset.pa === "dup") { pg.splice(i + 1, 0, JSON.parse(JSON.stringify(pg[i]))); th.splice(i + 1, 0, th[i]); await loadPage(i + 1); }
      else if (b.dataset.pa === "del") { if (pg.length === 1) return; if (!confirm("Delete this page?")) return; pg.splice(i, 1); th.splice(i, 1); await loadPage(Math.min(i, pg.length - 1)); }
      else { const j = b.dataset.pa === "left" ? i - 1 : i + 1; if (j < 0 || j >= pg.length) return; [pg[i], pg[j]] = [pg[j], pg[i]]; [th[i], th[j]] = [th[j], th[i]]; S.page = j; }
      commit(); drawPages(); drawProps();
    });
  }
  async function goPage(i) { if (i === S.page) return; syncPage(); thumbNow(); await loadPage(i); drawPages(); drawProps(); }
  function thumbNow() {
    if (!S) return;
    try { S.canvas.discardActiveObject; const prev = S.canvas.getActiveObject(); if (prev) S.canvas.discardActiveObject(); S.thumbs[S.page] = S.canvas.toDataURL({ format: "jpeg", quality: .7, multiplier: 160 / (S.doc.w * S.zoom) }); if (prev) S.canvas.setActiveObject(prev); } catch { /* tainted or gone */ }
    const el = $(`.ed-pg[data-pg="${S.page}"]`); if (el && S.thumbs[S.page]) el.innerHTML = `<img src="${S.thumbs[S.page]}" alt=""><b class="mono">${S.page + 1}</b>`;
  }
  let _rt = 0;
  function renderThumbsLater() { // thumbnails for the other pages, drawn off-screen
    clearTimeout(_rt); _rt = setTimeout(async () => {
      if (!S) return; const sid = S.id;
      const off = new (F().StaticCanvas)(null, { width: 160, height: Math.round(160 * S.doc.h / S.doc.w) }); off.setZoom(160 / S.doc.w);
      for (let i = 0; i < S.doc.pages.length; i++) {
        if (!S || S.id !== sid) return; if (i === S.page) { thumbNow(); continue; }
        off.clear(); off.backgroundColor = S.doc.pages[i].bg;
        for (const L of S.doc.pages[i].layers) { try { const o = await objFrom(L); if (o) off.add(o); } catch { /* skip */ } }
        off.renderAll(); S.thumbs[i] = off.toDataURL({ format: "jpeg", quality: .7 });
      }
      off.dispose(); drawPages();
    }, 250);
  }

  /* ---------------------------------------------------------------- export */
  function pagePNG() { const prev = S.canvas.getActiveObject(); S.canvas.discardActiveObject(); S.canvas.renderAll(); const url = S.canvas.toDataURL({ format: "png", multiplier: 1 / S.zoom }); if (prev) S.canvas.setActiveObject(prev); return url; }
  function saveThumb() { if (!S || S.page !== 0) return; fetch(`/api/design/${S.id}/export`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page: 1, data: pagePNG() }), keepalive: true }); }
  async function exportAll() {
    syncPage(); await saveNow();
    const here = S.page, files = [];
    try {
      for (let i = 0; i < S.doc.pages.length; i++) {
        busy(`Exporting page ${i + 1} of ${S.doc.pages.length}…`);
        if (i !== S.page) await loadPage(i);
        const data = pagePNG();
        await call(`/api/design/${S.id}/export`, { page: i + 1, data });
        files.push({ n: i + 1, data });
      }
      await loadPage(here);
    } catch (e) { busy(); alert(e.message); return; }
    busy();
    const P = $("#ed-props"); const slug = (S.doc.title || "design").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "design";
    P.innerHTML = `<p class="ed-h">Exported</p><p class="hint">${files.length} PNG${files.length > 1 ? "s" : ""} at ${S.doc.w}×${S.doc.h}, saved in the design's <span class="mono">export</span> folder. Download them here too:</p>
      <div class="ed-dl">${files.map(f => `<a class="btn sm" download="${slug}-${f.n}.png" href="${f.data}">Page ${f.n}</a>`).join("")}</div>
      <p class="hint">Hermes Studio never posts. You do.</p><button class="btn sm" id="ed-done" style="margin-top:.6rem">Done</button>`;
    $("#ed-done").onclick = drawProps;
  }

  function agentInfo() {
    const P = $("#ed-props");
    P.innerHTML = `<p class="ed-h">Hermes Agent</p><p class="hint">Your agent can work on this exact design. Edits it makes show up here within a few seconds.</p>
      <label class="f">Design id</label><div class="row"><input readonly value="${esc(S.id)}" id="ed-idv"><button class="btn sm" id="ed-copyid">Copy</button></div>
      <p class="ed-h">Try asking</p><ul class="ed-asks">
      <li>“In design ${esc(S.id)}, rewrite every headline to be shorter and punchier.”</li>
      <li>“Add a slide after page 2 that explains how it works, in the same style.”</li>
      <li>“Remove the background from my photo and put it on the first page.”</li>
      <li>“Export all pages and show me them.”</li></ul>
      <p class="hint">Tools: <span class="mono">design_show · design_edit · design_render · design_resize · photo</span></p>
      <button class="btn sm" id="ed-done" style="margin-top:.6rem">Done</button>`;
    $("#ed-copyid").onclick = () => { navigator.clipboard && navigator.clipboard.writeText(S.id); $("#ed-copyid").textContent = "Copied"; };
    $("#ed-done").onclick = drawProps;
  }

  function busy(msg) { const b = S && $("#ed-busy"); if (!b) return; b.hidden = !msg; b.textContent = msg || ""; }

  window.HSDesign = { home, open, leave };
})();
