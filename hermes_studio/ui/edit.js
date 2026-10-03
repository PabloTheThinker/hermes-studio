/* Hermes Studio · Edit page: a timeline editor that people and agents drive through one engine.
   Every change is a tool call on /mcp with the person's ui token (the engine is the only writer),
   so the page and any agent see the same log, the same undo and the same cards.
   The token comes from the desktop app in memory (window.studio.uiToken) or is pasted once; it is
   kept in this page's memory and the media worker's, never in a URL, storage or a cookie. */
(function () {
  "use strict";
  const TICK = 705600000;
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const sec = (t) => t / TICK;
  const ticks = (s) => Math.round(s * TICK);
  const tc = (t) => { const s = Math.max(0, sec(t)); const m = Math.floor(s / 60); return `${m}:${(s - m * 60).toFixed(2).padStart(5, "0")}`; };
  const rid = () => "ui-" + Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
  const frac = (v) => (Array.isArray(v) ? v[0] / v[1] : v == null ? 1 : v);

  let TOKEN = "";
  // Proxies are H.264: Chrome, Edge and the desktop app play them; a browser without the codec
  // previews with cached still frames instead (the same frames agents see).
  const H264 = (() => { try { return !!document.createElement("video").canPlayType('video/mp4; codecs="avc1.4d401f"'); } catch { return false; } })();
  let E = null; // the open project session
  let ROOT = null;

  /* ---------------------------------------------------------------- engine calls */
  async function getToken() {
    if (TOKEN) return TOKEN;
    if (window.studio && typeof window.studio.uiToken === "function") {
      try { const t = await window.studio.uiToken(); if (/^[0-9a-f]{64}$/.test(t || "")) TOKEN = t; } catch {}
    }
    if (TOKEN) await armWorker();
    return TOKEN;
  }
  async function armWorker() {
    if (!("serviceWorker" in navigator)) return false;
    try {
      await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      const reg = await navigator.serviceWorker.ready;
      const w = navigator.serviceWorker.controller || reg.active;
      if (!w) return false;
      return await new Promise((ok) => { const ch = new MessageChannel(); ch.port1.onmessage = (e) => ok(!!(e.data && e.data.ok)); w.postMessage({ token: TOKEN }, [ch.port2]); setTimeout(() => ok(false), 1500); });
    } catch { return false; }
  }
  async function rpc(name, args) {
    const res = await fetch("/mcp", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
      body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method: "tools/call", params: { name, arguments: args || {} } }),
    });
    if (res.status === 401) { TOKEN = ""; throw Object.assign(new Error("The Edit page code is not valid any more."), { code: "unauthorized" }); }
    const j = await res.json();
    if (j.error) throw new Error(j.error.message || "protocol error");
    const r = j.result;
    if (r.isError) {
      let body = {};
      try { body = JSON.parse(r.content[r.content.length - 1].text); } catch {}
      throw Object.assign(new Error(body.error || "failed"), body);
    }
    return Object.assign(r.structuredContent || {}, { _images: r.content.filter((c) => c.type === "image").map((c) => `data:${c.mimeType};base64,${c.data}`) });
  }
  const P = (name, args) => rpc(name, Object.assign({ project_id: E.pid }, args || {}));
  async function authed(path) {
    const res = await fetch(path, { headers: { Authorization: "Bearer " + TOKEN } });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
    return res;
  }

  /* ---------------------------------------------------------------- styles */
  function css() {
    if (document.getElementById("hs-edit-css")) return;
    const st = document.createElement("style");
    st.id = "hs-edit-css";
    st.textContent = `
    main.edit-full { padding: 0; overflow: hidden; }
    main.edit-full .wrap { max-width: none; height: 100%; }
    .ed { display: grid; grid-template-columns: 270px minmax(0,1fr) 340px; grid-template-rows: 48px minmax(0,1fr) 250px; height: calc(100vh - 64px); }
    .ed-top { grid-column: 1 / -1; display: flex; align-items: center; gap: .9rem; padding: 0 1rem; border-bottom: 1px solid var(--line); font-size: 13px; overflow-x: auto; overflow-y: hidden; min-width: 0; }
    .ed-top > * { flex: none; }
    .ed-top .sp { flex: 1 1 0; min-width: 0; }
    #ed-render-st { max-width: 26ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .ed-top .pid { font: 600 12px var(--mono); color: var(--mute); }
    .ed-top .ver { font: 500 11px var(--mono); color: var(--dim); }
    .ed-top .sp { flex: 1; }
    .ed-btn { background: none; border: 1px solid var(--line-2); color: var(--ink); padding: .3rem .7rem; cursor: pointer; font: 600 12px var(--sans); white-space: nowrap; }
    .ed-top select.ed-btn, .tl-tools select.ed-btn { width: auto; flex: none; margin: 0; }
    .ed-top .pid, .ed-top .ver, .tl-tools .hint { white-space: nowrap; }
    .ed-btn:hover { border-color: var(--ink); }
    .ed-btn.amber { background: var(--amber); color: var(--amber-ink); border-color: var(--amber); }
    .ed-btn[disabled] { opacity: .4; cursor: default; }
    .seg { display: inline-flex; border: 1px solid var(--line-2); }
    .seg button { background: none; border: 0; padding: .25rem .6rem; font: 600 11px var(--sans); letter-spacing: .08em; text-transform: uppercase; color: var(--mute); cursor: pointer; }
    .seg button.on { background: var(--amber); color: var(--amber-ink); }
    .ed-left { grid-row: 2; border-right: 1px solid var(--line); overflow: auto; display: flex; flex-direction: column; }
    .tabs { display: flex; border-bottom: 1px solid var(--line); }
    .tabs button { flex: 1; letter-spacing: .08em !important; background: none; border: 0; border-bottom: 2px solid transparent; padding: .55rem 0; font: 600 11px var(--sans); letter-spacing: .14em; text-transform: uppercase; color: var(--dim); cursor: pointer; }
    .tabs button.on { color: var(--ink); border-bottom-color: var(--amber); }
    .pane { padding: .8rem; font-size: 13px; }
    .pane input[type=text] { width: 100%; background: var(--panel); border: 1px solid var(--line-2); color: var(--ink); padding: .4rem .5rem; font: 400 12px var(--mono); }
    .mrow { border-bottom: 1px solid var(--line); padding: .55rem 0; }
    .mrow .nm { font-weight: 600; word-break: break-all; }
    .mrow .meta { font: 500 11px var(--mono); color: var(--dim); }
    .bar { height: 3px; background: var(--line); margin: .35rem 0; } .bar i { display: block; height: 100%; background: var(--ember); }
    .words { line-height: 1.9; user-select: none; }
    .words span { cursor: pointer; padding: 1px 2px; border-radius: 2px; }
    .words span:hover { background: var(--line-2); }
    .words span.fill { color: var(--ember); }
    .words span.sel { background: var(--amber); color: var(--amber-ink); }
    .words span.now { box-shadow: inset 0 -2px 0 var(--amber); }
    .ed-mid { grid-row: 2; display: flex; flex-direction: column; min-width: 0; min-height: 0; background: #050505; }
    .stage { flex: 1; position: relative; display: flex; align-items: center; justify-content: center; min-height: 0; }
    .screen { position: relative; height: 100%; max-height: 100%; aspect-ratio: var(--ar, 9/16); max-width: 100%; background: #000; overflow: hidden; }
    .screen video, .screen img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
    .pane.drop { outline: 2px dashed var(--amber); outline-offset: -6px; }
    .screen .cap { position: absolute; left: 5%; right: 5%; text-align: center; font-weight: 800; font-family: "DejaVu Sans", var(--sans); paint-order: stroke; pointer-events: none; line-height: 1.15; }
    .screen .txt { position: absolute; left: 6%; right: 6%; top: 72%; transform: translateY(-50%); text-align: center; font-weight: 800; font-size: clamp(12px, 3.2vh, 34px); color: #fff; -webkit-text-stroke: 1px #000; paint-order: stroke; text-shadow: 0 2px 6px rgba(0,0,0,.6); white-space: pre-wrap; pointer-events: none; }
    .transport { display: flex; align-items: center; gap: .8rem; padding: .45rem .8rem; border-top: 1px solid var(--line); font: 500 12px var(--mono); color: var(--mute); }
    .ed-tl { grid-column: 1 / 3; grid-row: 3; border-top: 1px solid var(--line); display: flex; flex-direction: column; min-width: 0; }
    .tl-tools { display: flex; gap: .5rem; align-items: center; overflow-x: auto; overflow-y: hidden; min-width: 0; padding: .35rem .7rem; border-bottom: 1px solid var(--line); font-size: 12px; }
    .tl-scroll { flex: 1; overflow: auto; position: relative; }
    .tl-inner { position: relative; min-height: 100%; }
    .ruler { position: sticky; top: 0; height: 20px; border-bottom: 1px solid var(--line); background: var(--bg); z-index: 2; font: 500 10px var(--mono); color: var(--dim); }
    .ruler span { position: absolute; top: 3px; border-left: 1px solid var(--line-2); padding-left: 3px; }
    .trk { position: relative; height: 38px; border-bottom: 1px solid var(--line); }
    .trk .lab { position: sticky; left: 0; z-index: 1; display: inline-block; width: 34px; height: 100%; font: 600 11px var(--mono); color: var(--dim); background: var(--bg); padding: 11px 0 0 6px; border-right: 1px solid var(--line); }
    .it { position: absolute; top: 4px; height: 30px; background: #1c1c1e; border: 1px solid var(--line-2); font: 500 11px var(--sans); padding: 2px 5px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; cursor: grab; color: var(--ink); }
    .it.clip { background: #232018; } .it.text { background: #1f1a26; } .it.transition { background: repeating-linear-gradient(45deg,#3a2c14,#3a2c14 4px,#2a2010 4px,#2a2010 8px); }
    .it.agent { outline: 1px solid var(--ember); } .it.mine { outline: 1px solid var(--ink); }
    .it.sel { border-color: var(--amber); box-shadow: 0 0 0 1px var(--amber); }
    .it .tag { font: 600 9px var(--mono); color: var(--ember); margin-right: 4px; }
    .it .h { position: absolute; top: 0; bottom: 0; width: 7px; cursor: ew-resize; z-index: 2; }
    .it .h.l { left: 0; } .it .h.r { right: 0; }
    .it .h:hover, .it.sel .h { background: rgba(255,200,61,.35); }
    .it canvas.wv { position: absolute; left: 0; bottom: 0; width: 100%; height: 12px; opacity: .8; pointer-events: none; }
    .it .fs { position: absolute; left: 0; top: 0; width: 100%; height: 100%; opacity: .5; pointer-events: none; }
    .it.clip .lbl { position: relative; z-index: 1; }
    .mk { position: absolute; top: 0; height: 20px; padding: 3px 6px 0 5px; margin-left: -1px; border-left: 2px solid var(--amber); color: var(--amber); font: 600 10px var(--sans, inherit); white-space: nowrap; cursor: grab; z-index: 3; background: var(--bg); max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
    .mk.sel { background: var(--amber); color: #000; }
    .keys { display: grid; grid-template-columns: auto 1fr; gap: .25rem .9rem; font-size: 12px; line-height: 1.5; }
    .keys b { font: 600 11px var(--mono); color: var(--amber); white-space: nowrap; }
    .card .pv { margin: .5rem 0 0; padding: .45rem .5rem; max-height: 14rem; overflow: auto; font: 500 10.5px/1.45 var(--mono); color: var(--mute); background: var(--bg); border: 1px solid var(--line); white-space: pre; }
    .it.ghost { outline: 2px dashed var(--ember, #ff7a45); outline-offset: 1px; }
    .words span.hit { background: rgba(255,200,61,.22); border-radius: 2px; } .words span.hit.cur { background: var(--amber); color: #000; }
    .card .sum[data-jump] { cursor: pointer; } .card .sum[data-jump]:hover { color: var(--amber); }
    .ed :focus-visible, .gate :focus-visible, .plist :focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
    .snapl { position: absolute; top: 0; bottom: 0; width: 0; border-left: 1px dashed var(--amber); z-index: 4; pointer-events: none; display: none; }
    .ph { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--amber); z-index: 3; pointer-events: none; }
    .ed-side { grid-column: 3; grid-row: 2 / 4; border-left: 1px solid var(--line); overflow: auto; display: flex; flex-direction: column; }
    .side-h { padding: .6rem .9rem; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
    .side-h .seg { margin-left: auto; }
    .pane label.chk { display: flex; align-items: center; gap: .45rem; font-size: 12px; color: var(--mute); letter-spacing: 0; text-transform: none; margin: .5rem 0; }
    .pane label.chk input { width: auto; margin: 0; }
    .tl-tools label.chk { display: inline-flex; align-items: center; gap: .3rem; } .tl-tools label.chk input { width: auto; margin: 0; }
    .side-h .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--dim); } .side-h .dot.live { background: var(--ember); }
    .card { margin: .6rem .7rem 0; border: 1px solid var(--line-2); padding: .55rem .65rem; font-size: 13px; }
    .card.wait { border-color: var(--amber); }
    .card .who { font: 600 10px var(--mono); letter-spacing: .06em; color: var(--dim); text-transform: uppercase; }
    .card .who.agent { color: var(--ember); }
    .card .sum { margin: .2rem 0 .35rem; font-weight: 600; }
    .card .v { font: 500 11px var(--mono); color: var(--dim); }
    .card .acts { display: flex; gap: .4rem; margin-top: .45rem; flex-wrap: wrap; }
    .card .ba { display: flex; gap: 4px; margin-top: .4rem; } .card .ba img { width: 50%; border: 1px solid var(--line); }
    .card.undone { opacity: .5; }
    .toast { position: fixed; right: 1rem; bottom: 1rem; max-width: 420px; background: var(--panel); border: 1px solid var(--bad); color: var(--ink); padding: .6rem .8rem; z-index: 50; font-size: 13px; }
    .toast.ok { border-color: var(--amber); }
    .gate { max-width: 560px; }
    .gate input { width: 100%; font: 400 13px var(--mono); padding: .5rem; background: var(--panel); color: var(--ink); border: 1px solid var(--line-2); }
    .plist .row { display: flex; align-items: baseline; gap: 1rem; padding: .7rem 0; border-bottom: 1px solid var(--line); cursor: pointer; }
    .plist .row:hover .nm { color: var(--amber); }
    .plist .nm { font-weight: 600; } .plist .meta { font: 500 11px var(--mono); color: var(--dim); margin-left: auto; }
    /* narrow windows (the desktop app goes down to 760 px): last, so they win */
    @media (max-width: 1100px) {
      .ed { grid-template-columns: 220px minmax(0,1fr) 270px; grid-template-rows: 44px minmax(0,1fr) 220px; }
      .ed-top { gap: .5rem; padding: 0 .6rem; }
      #ed-render-st { max-width: 16ch; }
      .ed-top select.ed-btn { max-width: 9.5rem; }
      .tabs { overflow-x: auto; } .tabs button { flex: none; font-size: 10px; letter-spacing: .02em !important; padding: .55rem .45rem; }
      .tl-tools > * { flex: none; }
    }
    @media (max-width: 860px) {
      .ed { grid-template-columns: 190px minmax(0,1fr) 230px; }
      .ed-top .pid { max-width: 9ch; overflow: hidden; text-overflow: ellipsis; }
    }
    `;
    document.head.appendChild(st);
  }

  function toast(msg, ok) {
    const t = document.createElement("div");
    t.className = "toast" + (ok ? " ok" : "");
    t.setAttribute("role", ok ? "status" : "alert"); // read out by screen readers
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), ok ? 2500 : 6000);
  }
  function fail(e) {
    if (e && e.code === "needs_approval") return toast("Waiting for approval: " + (e.error || ""), true);
    toast((e && (e.error || e.message)) || String(e));
  }

  /* ---------------------------------------------------------------- the token gate */
  async function needToken(root, then) {
    if (await getToken()) return then();
    root.innerHTML = `<div class="gate"><p class="kicker">Edit</p><h1>Connect the editor</h1>
      <p class="lede">The desktop app connects this page by itself. In a browser, paste the <b>Edit page code</b> that
      <span class="mono">hermes-studio studio</span> printed in the terminal. It stays in this tab's memory only.</p>
      <input id="ed-code" type="password" autocomplete="off" spellcheck="false" placeholder="64-character code" />
      <p style="margin-top:.8rem"><button class="ed-btn amber" id="ed-go">Connect</button></p><p class="hint" id="ed-why"></p></div>`;
    const go = async () => {
      const v = (document.getElementById("ed-code").value || "").trim().toLowerCase();
      if (!/^[0-9a-f]{64}$/.test(v)) { document.getElementById("ed-why").textContent = "That isn't a 64-character code."; return; }
      TOKEN = v;
      try { await rpc("project_list", {}); } catch (e) { TOKEN = ""; document.getElementById("ed-why").textContent = e.message; return; }
      await armWorker();
      then();
    };
    document.getElementById("ed-go").onclick = go;
    document.getElementById("ed-code").onkeydown = (e) => { if (e.key === "Enter") go(); };
  }

  /* ---------------------------------------------------------------- home */
  async function home(root) {
    leave(); css(); ROOT = root;
    document.getElementById("main").classList.remove("edit-full");
    await needToken(root, async () => {
      let list = [];
      try { list = (await rpc("project_list", {})).projects || []; } catch (e) { fail(e); }
      root.innerHTML = `<p class="kicker">Edit</p><h1>Timeline projects</h1>
        <p class="lede">A real timeline you and your agents edit together. Every change is one entry you can undo; agent edits wait for you in Propose mode.</p>
        <p><select id="ed-shape" class="ed-btn">${["9:16", "16:9", "1:1", "4:5"].map((s) => `<option>${s}</option>`).join("")}</select>
        <button class="ed-btn amber" id="ed-new">New project</button></p>
        <div class="plist">${order(list).map((p) => p.error ? `<div class="row"><span class="nm">${esc(p.project_id)}</span><span class="meta">${esc(p.error.error)}</span></div>` :
          `<div class="row" data-pid="${esc(p.project_id)}"><span class="nm">${esc(p.project_id)}</span><span class="hint">${esc(p.size[0])}×${esc(p.size[1])} · ${esc(p.media)} media · ${esc(p.items)} items</span><span class="meta">${p.drafts ? `${p.drafts} draft${p.drafts > 1 ? "s" : ""} · ` : ""}v${esc(p.version)} · ${tc(p.end)} · ${esc(p.mode)} · ${ago(p.modified)}</span></div>`).join("") || `<p class="hint">No projects yet.</p>`}</div>`;
      root.querySelectorAll("[data-pid]").forEach((r) => {
        r.tabIndex = 0; r.setAttribute("role", "link");
        r.onclick = () => go(r.dataset.pid);
        r.onkeydown = (e) => { if (e.key === "Enter") go(r.dataset.pid); };
      });
      document.getElementById("ed-new").onclick = async () => {
        try { const p = await rpc("project_new", { shape: document.getElementById("ed-shape").value }); go(p.project_id); } catch (e) { fail(e); }
      };
    });
  }
  function go(pid) { location.hash = "#/edit/" + encodeURIComponent(pid); }
  // Newest first; a draft (<main>.d<hex>) is counted on its main project's row, not listed (open
  // it from the main's sidebar).
  function order(list) {
    const isDraft = (p) => /\.d[0-9a-f]{6}$/.test(p.project_id), mains = list.filter((p) => !isDraft(p));
    list.filter(isDraft).forEach((d) => { const m = mains.find((p) => d.project_id.startsWith(p.project_id + ".d")); if (m) m.drafts = (m.drafts || 0) + 1; else mains.push(d); });
    return mains.sort((a, b) => (b.modified || 0) - (a.modified || 0));
  }
  function ago(t) {
    if (!t) return "";
    const s = Math.max(0, Date.now() / 1000 - t);
    return s < 60 ? "edited just now" : s < 3600 ? `edited ${Math.floor(s / 60)} min ago` : s < 86400 ? `edited ${Math.floor(s / 3600)} h ago` : `edited ${new Date(t * 1000).toLocaleDateString()}`;
  }

  /* ---------------------------------------------------------------- resolve (timeline.resolve in JS) */
  function resolve(doc) {
    const by = {}, out = {};
    doc.tracks.forEach((tr) => tr.items.forEach((it) => (by[it.id] = it)));
    const dur = (it) => (it.type === "clip" ? Math.round((it.src[1] - it.src[0]) / frac((it.props || {}).speed)) : it.dur);
    Object.values(by).forEach((it) => {
      if (it.type === "transition") return;
      const s = "at" in it ? it.at : by[it.anchor.to].at + it.anchor.offset;
      out[it.id] = [s, s + dur(it)];
    });
    Object.values(by).forEach((it) => { if (it.type === "transition") { const s = out[it.between[1]][0]; out[it.id] = [s, s + it.dur]; } });
    return out;
  }
  const endOf = (spans) => Math.max(0, ...Object.values(spans).map((x) => x[1]));

  /* ---------------------------------------------------------------- open */
  async function open(root, pid) {
    leave(); css(); ROOT = root;
    await needToken(root, async () => {
      document.getElementById("main").classList.add("edit-full");
      E = { pid, doc: null, spans: {}, t: 0, zoom: 60, sel: null, tab: "media", media: {}, words: [], wsel: null, records: [], pending: [],
            mode: "propose", playing: false, render: null, ctl: new AbortController(), frames: {}, by: {}, waves: {}, thumbs: {}, sprites: {}, follow: true, sels: new Set() };
      root.innerHTML = layout();
      fitHeight(); window.addEventListener("resize", fitHeight);
      bindStatic();
      fetch("/api/caption-styles").then((r) => r.json()).then((j) => { if (E && j.ok) { E.capStyles = j; drawCaption(); } }).catch(() => {});
      try { await reload(); } catch (e) { fail(e); if (e.code === "not_found") { location.hash = "#/edit"; return; } }
      stream();
    });
  }

  // The editor fills the window below the desk's header, whatever height that header has (it
  // grows to two rows in a narrow window).
  function fitHeight() {
    const ed = ROOT && ROOT.querySelector(".ed"); if (!ed) return;
    ed.style.height = `calc(100vh - ${Math.max(0, Math.round(ed.getBoundingClientRect().top + window.scrollY))}px)`;
    if (E && E.doc) timeline();
  }
  function layout() {
    return `<div class="ed">
      <div class="ed-top"><a class="ed-btn" href="#/edit">Projects</a><span class="pid">${esc(E.pid)}</span><span class="ver" id="ed-ver"></span>
        <button class="ed-btn" id="ed-undo" title="Undo (Ctrl+Z)">Undo</button><button class="ed-btn" id="ed-redo" title="Redo (Ctrl+Shift+Z)">Redo</button>
        <span class="sp"></span><span class="hint" id="ed-render-st" aria-live="polite"></span>
        <select class="ed-btn" id="ed-cstyle" title="Captions in the render: a style, or none">${["pop", "impact", "clean", "glow", "neon", "boxed"].map((x) => `<option value="${x}">captions: ${x}</option>`).join("")}<option value="">no captions</option></select>
        <select class="ed-btn" id="ed-rsize" title="Render size"><option value="1">full size</option><option value="2">half size</option></select>
        <button class="ed-btn" id="ed-otio" title="Save the edit as OpenTimelineIO (.otio) for DaVinci Resolve, Premiere or Final Cut">Export OTIO</button>
        <button class="ed-btn amber" id="ed-render">Render MP4</button></div>
      <div class="ed-left"><div class="tabs" role="tablist" aria-label="Panels"><button data-tab="media">Media</button><button data-tab="transcript">Transcript</button><button data-tab="scenes">Scenes</button><button data-tab="item">Item</button></div><div class="pane" id="ed-pane"></div></div>
      <div class="ed-mid"><div class="stage"><div class="screen" id="ed-screen"><img id="ed-still" alt="" /><video id="ed-video" playsinline preload="auto"></video><div class="txt" id="ed-txt"></div><div class="cap" id="ed-cap"></div></div></div>
        <div class="transport"><button class="ed-btn" id="ed-play">Play</button><button class="ed-btn" id="ed-shot" title="Save the frame at the playhead as a JPEG (up to 1080 px wide), e.g. for a cover">Save frame</button><span id="ed-tc">0:00.00</span><span class="hint" id="ed-at"></span></div></div>
      <div class="ed-tl"><div class="tl-tools"><button class="ed-btn" id="ed-split" title="Split at the playhead (S)">Split</button><button class="ed-btn" id="ed-del">Delete</button>
        <label class="hint chk"><input type="checkbox" id="ed-ripple" checked /> ripple</label><label class="hint chk" title="Edges snap to cuts, markers and the playhead; hold Shift to drag freely"><input type="checkbox" id="ed-snapon" checked /> snap</label><button class="ed-btn" id="ed-text" title="Text at the playhead">+ Text</button><button class="ed-btn" id="ed-marker" title="Marker at the playhead (M)">+ Marker</button>
        <select class="ed-btn" id="ed-preset" title="Presets: one step, one undo"><option value="">Presets</option><option value="title_card">Title card</option>
          <option value="end_card">End card</option><option value="fade_in_out">Fade every clip</option><option value="crossfade_all">Crossfade every cut</option><option value="close_gaps">Close the gaps</option>
          <option value="duck_music">Duck the music</option></select>
        <span class="sp" style="flex:1"></span><button class="ed-btn" id="ed-keys" title="Keyboard shortcuts (?)">Keys</button><button class="ed-btn" id="ed-fit" title="Zoom to fit (\\)">Fit</button><span class="hint">zoom</span><input type="range" id="ed-zoom" min="5" max="240" value="60" aria-label="Timeline zoom" style="width:110px;flex:none" /></div>
        <div class="tl-scroll" id="ed-scroll"><div class="tl-inner" id="ed-tl"></div></div></div>
      <div class="ed-side" id="ed-side"></div></div>`;
  }

  function bindStatic() {
    const $ = (id) => document.getElementById(id);
    ROOT.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { E.tab = b.dataset.tab; pane(); }));
    $("ed-undo").onclick = undo; $("ed-redo").onclick = redo;
    $("ed-play").onclick = () => (E.playing ? pause() : play());
    $("ed-split").onclick = split; $("ed-del").onclick = del; $("ed-text").onclick = addText;
    $("ed-marker").onclick = addMarker; $("ed-keys").onclick = keysHelp;
    $("ed-zoom").oninput = (e) => { E.zoom = +e.target.value; timeline(); };
    $("ed-fit").onclick = fit;
    $("ed-scroll").addEventListener("wheel", (e) => {
      if (!(e.ctrlKey || e.metaKey) || !E || !E.doc) return;
      e.preventDefault();
      const sc = $("ed-scroll"), x = e.clientX - sc.getBoundingClientRect().left, t = (sc.scrollLeft + x - 40) / E.zoom;
      setZoom(E.zoom * Math.exp(-e.deltaY * 0.002));
      sc.scrollLeft = Math.max(0, 40 + t * E.zoom - x); // the second under the pointer stays under it
    }, { passive: false });
    $("ed-render").onclick = render;
    $("ed-shot").onclick = saveFrame;
    $("ed-otio").onclick = exportOtio;
    $("ed-cstyle").onchange = () => drawCaption();
    $("ed-preset").onchange = async (e) => {
      const preset = e.target.value; e.target.value = ""; if (!preset || !E) return;
      const args = { preset, base_version: E.doc.version, client_op_id: rid() };
      if (preset === "title_card" || preset === "end_card") { const t = prompt(preset === "title_card" ? "Title" : "End card text"); if (!t) return; args.text = t; }
      try { await P("apply_preset", args); await reload(); } catch (err) { fail(err); }
    };
    $("ed-video").addEventListener("timeupdate", onTime);
    E.keys = (e) => {
      if (!E || /INPUT|TEXTAREA|SELECT/.test((e.target || {}).tagName || "")) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a" && !e.shiftKey) { e.preventDefault(); selectAll(); }
      else if ((e.ctrlKey || e.metaKey) && ["c", "v", "d"].includes(e.key.toLowerCase()) && !e.shiftKey && !e.altKey) {
        const k = e.key.toLowerCase();
        if (k === "c" && (!E.sel || String(window.getSelection() || ""))) return; // plain text copy stays the browser's
        if (k === "v" && !E.clip) return;
        e.preventDefault(); ({ c: copy, v: paste, d: duplicate })[k]();
      }
      else if (e.key === " ") { e.preventDefault(); E.playing ? pause() : play(); }
      else if ((e.key === "Delete" || e.key === "Backspace") && E.sel) { e.preventDefault(); del(); }
      else if (e.ctrlKey || e.metaKey) return;
      else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        const dir = e.key === "ArrowLeft" ? -1 : 1;
        if (e.altKey) nudge(dir * (e.shiftKey ? 10 : 1)); else step(dir * (e.shiftKey ? E.doc.fps[0] / E.doc.fps[1] : 1));
      }
      else if (e.key === "[" || e.key === "]") { e.preventDefault(); jump(e.key === "]" ? 1 : -1); }
      else if (e.key === "Home") { e.preventDefault(); E.follow = false; seek(0); }
      else if (e.key === "End") { e.preventDefault(); E.follow = false; seek(endOf(E.spans)); }
      else if (e.key.toLowerCase() === "m") addMarker();
      else if (["j", "k", "l"].includes(e.key.toLowerCase()) && !e.altKey) { e.preventDefault(); shuttle(e.key.toLowerCase()); }
      else if ((e.code === "Comma" || e.code === "Period") && E.sel && E.by[E.sel] && E.by[E.sel].type === "clip") {
        e.preventDefault(); const id = E.sel;
        coalesce("slip:" + id, (e.code === "Comma" ? -1 : 1) * (e.shiftKey ? Math.round(E.doc.fps[0] / E.doc.fps[1]) : 1), (n) => slip(id, n));
      }
      else if (e.key === "?") keysHelp();
      else if (e.key === "Escape") { selOnly(null); pane(); }
      else if (e.key === "\\") { e.preventDefault(); fit(); }
      else if (e.key.toLowerCase() === "s") split();
    };
    document.addEventListener("keydown", E.keys);
  }

  async function reload() {
    clearTimeout(reloadTimer); // this reload reads the latest doc: one queued by an event (often our own write's echo) is covered
    const doc = await P("get_timeline");
    E.doc = doc; E.spans = resolve(doc);
    E.by = {}; doc.tracks.forEach((tr) => tr.items.forEach((it) => (E.by[it.id] = it)));
    document.getElementById("ed-screen").style.setProperty("--ar", `${doc.size[0]}/${doc.size[1]}`);
    document.getElementById("ed-ver").textContent = `v${doc.version}`;
    E.sels = new Set([...E.sels].filter((id) => E.by[id] || isMarker(id)));
    if (E.sel && !E.sels.has(E.sel)) E.sel = [...E.sels].pop() || null;
    await Promise.all([history(), approvals(), mediaStatus(), transcript()]);
    await mediaArt();
    if (E.followTo) { const ids = E.followTo; E.followTo = null; const ts = ids.map((i) => (E.spans[i] || [])[0]).filter((x) => x != null); if (ts.length) E.t = Math.min(...ts); }
    timeline(); pane(); side(); seek(E.t, true);
  }

  /* ---------------------------------------------------------------- live events */
  async function stream() {
    let last = null;
    for (;;) {
      if (!E) return;
      try {
        const h = { Authorization: "Bearer " + TOKEN };
        if (last != null) h["Last-Event-ID"] = String(last);
        const res = await fetch(`/api/projects/${encodeURIComponent(E.pid)}/events`, { headers: h, signal: E.ctl.signal });
        const rd = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
        for (;;) {
          const { value, done } = await rd.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
            let id = null, data = null;
            chunk.split("\n").forEach((l) => { if (l.startsWith("id: ")) id = +l.slice(4); else if (l.startsWith("data: ")) data = l.slice(6); });
            if (id != null) last = id;
            if (data) { try { onEvent(JSON.parse(data)); } catch {} }
          }
        }
      } catch (e) { if (!E || e.name === "AbortError") return; }
      await new Promise((ok) => setTimeout(ok, 1500));
    }
  }
  let reloadTimer = null;
  function soon(fn) { clearTimeout(reloadTimer); reloadTimer = setTimeout(() => fn().catch(fail), 120); }
  function onEvent(ev) {
    if (!E) return;
    const t = ev.type || "";
    if (t === "stream.reset") E.histHead = null; // read the whole history again
    if (t === "op.applied" || t === "op.undone" || t === "stream.reset") {
      if (t !== "stream.reset" && E.doc && ev.new_version <= E.doc.version) return; // our own write: already reloaded
      if (E.follow && ev.actor && ev.actor.kind === "agent" && ev.changed_ids) E.followTo = ev.changed_ids; // jump to the agent's change
      soon(reload);
    }
    else if (t.startsWith("approval.")) approvals().then(side).catch(() => {});
    else if (t === "mode.changed") { E.mode = ev.mode; side(); }
    else if (t.startsWith("media.")) {
      const m = E.media[ev.media_id] || (E.media[ev.media_id] = {});
      if (t === "media.progress") Object.assign(m, { state: "running", progress: ev.progress, stage: ev.stage });
      if (t === "media.ready") { mediaStatus().then(() => { pane(); seek(E.t, true); }); return; }
      if (E.tab === "media") pane();
    } else if (t.startsWith("render.")) {
      E.render = Object.assign(E.render || {}, { state: t === "render.ready" ? "ready" : t === "render.failed" ? "failed" : t === "render.cancelled" ? "cancelled" : "running", progress: ev.progress, render_id: ev.render_id, error: ev.error });
      renderStatus();
    }
  }

  /* ---------------------------------------------------------------- data */
  // The log only grows (an undo is a new entry), so after the first read only the new records are
  // fetched; a stream reset or a head behind what we hold starts over from version 0.
  async function history() {
    let out = E.histHead == null ? [] : E.records.slice(), since = E.histHead == null ? 0 : E.histHead, head = since;
    for (;;) {
      const h = await P("history_diff", { since_version: since, limit: 500 });
      if (h.head_version < since) { E.histHead = null; return history(); }
      out.push(...h.records); head = h.head_version;
      if (h.next_since_version == null) break; since = h.next_since_version;
    }
    E.records = out; E.histHead = head;
    const cancelled = new Set();
    for (let i = out.length - 1; i >= 0; i--) { const r = out[i]; if (cancelled.has(r.op_id)) continue; (r.undoes || []).forEach((x) => cancelled.add(x)); }
    E.cancelled = cancelled;
    E.undoTarget = [...out].reverse().find((r) => !cancelled.has(r.op_id) && !r.undoes) || null;
    E.redoTarget = [...out].reverse().find((r) => !cancelled.has(r.op_id) && r.undoes) || null;
    const lastBy = {}; out.forEach((r) => r.changed_ids.forEach((id) => (lastBy[id] = r.actor)));
    E.lastBy = lastBy;
    const u = document.getElementById("ed-undo"), r = document.getElementById("ed-redo");
    u.disabled = !E.undoTarget; r.disabled = !E.redoTarget;
    u.title = E.undoTarget ? `Undo "${E.undoTarget.summary}" (Ctrl+Z)` : "Nothing to undo";
    r.title = E.redoTarget ? `Redo "${(E.records.find((x) => x.op_id === (E.redoTarget.undoes || [])[0]) || {}).summary || E.redoTarget.summary}" (Ctrl+Shift+Z)` : "Nothing to redo";
  }
  async function approvals() {
    const a = await P("approval_list"); E.pending = a.pending; E.mode = a.mode;
    try { E.drafts = E.pid.includes(".d") ? [] : (await P("draft_list")).drafts.filter((d) => d.draft.state === "open"); } catch { E.drafts = []; }
    E.draftOf = /\.d[0-9a-f]{6}$/.test(E.pid) ? E.pid.replace(/\.d[0-9a-f]{6}$/, "") : null;
  }
  async function mediaStatus() {
    await Promise.all(Object.keys(E.doc.media).map(async (mid) => { try { E.media[mid] = await P("media_status", { media_id: mid }); } catch {} }));
  }
  async function transcript() { try { E.words = (await P("get_transcript")).words; } catch { E.words = []; } }

  // The page's writes run one at a time, each on the version the one before it left (a held
  // key's pending nudge lands first), so quick actions never trip over each other's base_version.
  function queued(fn) {
    if (E.pend) settle();
    const s = E; const run = (s.wq || Promise.resolve()).then(() => (E === s ? fn() : null));
    s.wq = run.catch(() => {});
    return run;
  }
  // ops: a list, or a function that works the list out when the write runs (on the doc as the
  // writes before it left it; null for nothing to do), for edits that are relative to now.
  function write(ops, summary) {
    return queued(async () => {
      const list = typeof ops === "function" ? ops() : ops;
      if (!list || !list.length) return null;
      try {
        const r = await P("timeline_apply", { base_version: E.doc.version, client_op_id: rid(), summary, ops: list });
        await reload();
        return r;
      } catch (e) { fail(e); if (e.code === "conflict") await reload(); return null; }
    });
  }

  /* ---------------------------------------------------------------- timeline view */
  const px = (t) => 40 + sec(t) * E.zoom;
  function timeline() {
    const el = document.getElementById("ed-tl"); if (!el || !E.doc) return;
    if (E.dragging) { E.stale = true; return; } // a reload mid-drag would pull the node from under the pointer
    E.stale = false;
    const end = Math.max(endOf(E.spans) + 10 * TICK, 30 * TICK);
    const w = px(end) + 40;
    const step = E.zoom > 80 ? 1 : E.zoom > 30 ? 5 : E.zoom > 12 ? 10 : 30;
    let ruler = "";
    for (let s = 0; s <= sec(end); s += step) ruler += `<span style="left:${px(ticks(s))}px">${tc(ticks(s))}</span>`;
    const rows = E.doc.tracks.map((tr) => `<div class="trk" data-trk="${esc(tr.id)}"><span class="lab">${esc(tr.id)}</span>${tr.items.map((it) => {
      const [a, b] = E.spans[it.id]; const who = E.lastBy[it.id];
      const cls = ["it", it.type, E.sels.has(it.id) ? "sel" : "", who && who.kind === "agent" ? "agent" : who ? "mine" : ""].join(" ");
      const tag = who && who.kind === "agent" ? `<span class="tag">${esc(who.id[0].toUpperCase())}${who.step != null ? " · step " + esc(who.step) : ""}</span>` : "";
      const label = it.type === "clip" ? `${esc(it.media)} ${tc(it.src[0])}` : it.type === "text" ? esc(it.text) : "xfade";
      const own = it.type !== "transition" && "at" in it;
      const hs = own || it.type === "clip" ? `<span class="h l" data-edge="l"></span><span class="h r" data-edge="r"></span>` : "";
      const th = it.type === "clip" && E.sprites[it.media] ? `<canvas class="fs" data-fs="${esc(it.id)}"></canvas>` : "";
      const wv = it.type === "clip" && E.waves[it.media] ? `<canvas class="wv" data-wave="${esc(it.id)}"></canvas>` : "";
      return `<div class="${cls}" data-id="${esc(it.id)}" title="${esc(it.id)}${it.type === "text" ? " · double-click to edit" : ""}" style="left:${px(a)}px;width:${Math.max(4, px(b) - px(a))}px">${th}${wv}${hs}<span class="lbl">${tag}${label}</span></div>`;
    }).join("")}</div>`).join("");
    el.style.width = w + "px";
    const mks = (E.doc.markers || []).map((m) => `<b class="mk${E.sels.has(m.id) ? " sel" : ""}" data-mk="${esc(m.id)}" title="${esc(m.label || m.id)} · ${tc(m.at)} · drag to move, double-click to rename" style="left:${px(m.at)}px">${esc(m.label || "◆")}</b>`).join("");
    el.innerHTML = `<div class="ruler" id="ed-ruler">${ruler}${mks}</div>${rows}<div class="ph" id="ed-ph" style="left:${px(E.t)}px"></div><div class="snapl" id="ed-snap"></div>`;
    el.querySelector("#ed-ruler").onclick = (e) => { const r = el.getBoundingClientRect(); E.follow = false; side(); seek(ticks(Math.max(0, (e.clientX - r.left - 40) / E.zoom))); };
    el.querySelectorAll(".it").forEach((n) => dragItem(n));
    el.querySelectorAll(".mk").forEach((n) => dragMarker(n));
    el.querySelectorAll("canvas[data-fs]").forEach(drawStrip);
    el.querySelectorAll("canvas[data-wave]").forEach(drawWave);
    el.querySelectorAll(".it.text").forEach((n) => (n.ondblclick = () => editText(n.dataset.id)));
  }
  // A clip's filmstrip: tiles across its width, each the S4 thumbnail nearest the source time
  // under the tile's middle (one every 2 s of source), so trims and slips show at a glance.
  function drawStrip(cv, shift = 0) { // shift: source ticks, for the Alt-drag slip preview
    const it = E.by[cv.dataset.fs], sp = it && E.sprites[it.media]; if (!sp) return;
    const box = cv.getBoundingClientRect(), { idx, bmp } = sp;
    cv.width = Math.max(1, Math.round(box.width)); cv.height = Math.max(1, Math.round(box.height));
    const g = cv.getContext("2d"), tw = Math.max(8, Math.round(cv.height * idx.width / idx.height));
    for (let x = 0; x < cv.width; x += tw) {
      const t = (shift + it.src[0] + (it.src[1] - it.src[0]) * Math.min(1, (x + tw / 2) / cv.width)) / TICK;
      const i = Math.max(0, Math.min(idx.count - 1, Math.floor(t / idx.every_s)));
      g.drawImage(bmp, (i % idx.cols) * idx.width, Math.floor(i / idx.cols) * idx.height, idx.width, idx.height, x, 0, tw, cv.height);
    }
  }
  function drawWave(cv) {
    const it = E.by[cv.dataset.wave]; const w = E.waves[it.media]; if (!w) return;
    const box = cv.getBoundingClientRect(); cv.width = Math.max(1, Math.round(box.width)); cv.height = 24;
    const g = cv.getContext("2d"); g.fillStyle = "rgba(255,200,61,.75)";
    const a = (it.src[0] / TICK) * w.peaks_per_s, b = (it.src[1] / TICK) * w.peaks_per_s;
    for (let x = 0; x < cv.width; x++) {
      const i = Math.floor(a + (b - a) * x / cv.width), pk = w.peaks[i]; if (!pk) continue;
      const amp = Math.max(Math.abs(pk[0]), Math.abs(pk[1])) / 128; const h = Math.max(1, amp * 24);
      g.fillRect(x, 24 - h, 1, h);
    }
  }
  async function mediaArt() {
    await Promise.all(Object.keys(E.doc.media).map(async (mid) => {
      const st = E.media[mid] || {}; const stg = st.stages || {};
      const base = `/api/projects/${encodeURIComponent(E.pid)}/media/${encodeURIComponent(mid)}/`;
      if ((stg.wave || {}).state === "ready" && !E.waves[mid]) { try { E.waves[mid] = await (await authed(base + "wave")).json(); } catch {} }
      if ((stg.thumbs || {}).state === "ready" && !E.thumbs[mid]) {
        try {
          const idx = await (await authed(base + "thumbs.json")).json(); const blob = await (await authed(base + "thumbs")).blob();
          E.sprites[mid] = { bmp: await createImageBitmap(blob), idx }; E.thumbs[mid] = true;
        } catch {}
      }
    }));
  }
  async function editText(id) {
    const it = E.by[id]; if (!it) return;
    const text = prompt("Text", it.text); if (text == null || text === it.text) return;
    await write([{ op: "edit_text", id, text }], `Edit ${id}`);
  }
  const frameT = () => TICK * E.doc.fps[1] / E.doc.fps[0];
  const snapT = (t) => Math.max(0, Math.round(Math.round(t / frameT()) * frameT()));
  // Hold timeline re-renders while the pointer drags n; draw the latest doc once it lets go.
  function holdDrag(n, e) {
    E.dragging = true;
    n.setPointerCapture(e.pointerId);
    const release = () => { if (!E || !E.dragging) return; E.dragging = false; if (E.stale) timeline(); };
    n.addEventListener("pointerup", () => setTimeout(release), { once: true }); // after the drop handler has read the node
    n.addEventListener("lostpointercapture", release, { once: true });
  }
  /* selection: E.sel is the item or marker last clicked, E.sels everything selected (Ctrl- or
     Cmd-click adds or removes one, Ctrl+A takes every clip and text item, Esc clears) */
  function selOnly(id) { E.sel = id; E.sels = new Set(id ? [id] : []); markSel(); }
  function markSel() {
    document.querySelectorAll(".it, .mk").forEach((x) => x.classList.toggle("sel", E.sels.has(x.dataset.id || x.dataset.mk)));
  }
  // A click on id: with Ctrl/Cmd it toggles id in the selection and returns true (no drag; Shift
  // is kept for dragging without snapping);
  // otherwise id alone is selected (a drag moves one item; Alt+arrows move a group).
  function pick(id, e) {
    if (e.ctrlKey || e.metaKey) {
      if (E.sels.has(id) && E.sels.size > 1) { E.sels.delete(id); E.sel = [...E.sels].pop(); }
      else { E.sels.add(id); E.sel = id; }
      markSel(); pane(); return true;
    }
    selOnly(id);
    return false;
  }
  function selectAll() {
    E.sels = new Set(E.doc.tracks.flatMap((tr) => tr.items.filter((it) => it.type !== "transition").map((it) => it.id)));
    E.sel = [...E.sels].pop() || null; markSel(); E.tab = "item"; pane();
  }
  // Snapping: while dragging, an edge within SNAP_PX of an edit point (another item's start or
  // end, a marker, the playhead) lands on it, and an amber line shows where. Shift drags free.
  const SNAP_PX = 8;
  function snapPoints(skip) {
    const pts = new Set([0, E.t]);
    Object.entries(E.spans).forEach(([id, [a, b]]) => { if (id !== skip) { pts.add(a); pts.add(b); } });
    (E.doc.markers || []).forEach((m) => { if (m.id !== skip) pts.add(m.at); });
    return [...pts].map(px);
  }
  function magnet(edges, dx, pts, free) {
    const line = document.getElementById("ed-snap");
    if (!edges) { if (line) line.style.display = "none"; return 0; }
    let best = null, at = 0;
    if (!free && document.getElementById("ed-snapon").checked) {
      edges.forEach((ex) => pts.forEach((p) => { const d = p - (ex + dx); if (Math.abs(d) <= SNAP_PX && (best == null || Math.abs(d) < Math.abs(best))) { best = d; at = p; } }));
    }
    if (line) { line.style.display = best == null ? "none" : "block"; line.style.left = at + "px"; }
    return best == null ? dx : dx + best;
  }
  function dragMarker(n) {
    const id = n.dataset.mk;
    n.onclick = (e) => e.stopPropagation();
    n.ondblclick = (e) => { e.stopPropagation(); renameMarker(id); };
    n.onpointerdown = (e) => {
      e.stopPropagation();
      const m = (E.doc.markers || []).find((x) => x.id === id); if (!m) return;
      if (pick(id, e)) return;
      E.tab = "item"; pane();
      const x0 = e.clientX, left0 = parseFloat(n.style.left); let moved = false;
      holdDrag(n, e);
      const pts = snapPoints(id);
      n.onpointermove = (mv) => { const dx = mv.clientX - x0; if (Math.abs(dx) > 3) moved = true; if (moved) n.style.left = Math.max(40, left0 + magnet([left0], dx, pts, mv.shiftKey)) + "px"; };
      n.onpointerup = () => {
        n.onpointermove = n.onpointerup = null; magnet();
        if (!moved) { E.follow = false; side(); seek(m.at); return; }
        const at = snapT(ticks((parseFloat(n.style.left) - 40) / E.zoom));
        if (at !== m.at) write([{ op: "edit_marker", id, at }], `Move marker ${m.label || id}`);
      };
    };
  }
  function renameMarker(id) {
    const m = (E.doc.markers || []).find((x) => x.id === id); if (!m) return;
    const label = prompt("Marker name", m.label); if (label == null || label === m.label) return;
    write([{ op: "edit_marker", id, label: label.normalize("NFC") }], `Rename marker ${m.label || id}`);
  }
  function addMarker() {
    if (!E) return;
    const n = (E.doc.markers || []).length + 1;
    write([{ op: "add_marker", at: snapT(E.t), label: `Marker ${n}` }], "Add marker");
  }
  function isMarker(id) { return !!(E && (E.doc.markers || []).some((m) => m.id === id)); }
  // Edit points the [ and ] keys jump between: every item's start and end, and every marker.
  function editPoints() {
    const pts = new Set([0]);
    Object.values(E.spans).forEach(([a, b]) => { pts.add(a); pts.add(b); });
    (E.doc.markers || []).forEach((m) => pts.add(m.at));
    return [...pts].sort((a, b) => a - b);
  }
  function jump(dir) {
    const pts = editPoints();
    const t = dir > 0 ? pts.find((p) => p > E.t) : [...pts].reverse().find((p) => p < E.t);
    if (t != null) { E.follow = false; seek(t); }
  }
  function step(frames) { if (E && E.doc) { pause(); E.follow = false; seek(Math.max(0, snapT(E.t) + Math.round(frames * frameT()))); } }
  // Key repeats of one action (a held Alt+arrow, , or .) add up and land as ONE entry once the
  // keys stop for KEY_SETTLE_MS; another action, or a click elsewhere, lands the pending one first.
  const KEY_SETTLE_MS = 350;
  function coalesce(key, frames, commit, preview) {
    const p = E.pend;
    if (p && p.key !== key) settle();
    const q = E.pend || (E.pend = { key, frames: 0, commit });
    q.frames += frames; if (preview) preview(q.frames);
    clearTimeout(q.timer); q.timer = setTimeout(settle, KEY_SETTLE_MS);
  }
  function settle() {
    const q = E && E.pend; if (!q) return;
    clearTimeout(q.timer); E.pend = null;
    if (q.frames) q.commit(q.frames);
  }
  function nudge(frames) {
    if (!E || !E.sel) return toast("Select an item or marker first.");
    if (E.sels.size > 1) return nudgeMany(frames);
    const id = E.sel, m = (E.doc.markers || []).find((x) => x.id === id), it = E.by[id];
    if (!m && (!it || !("at" in it))) return toast("That item moves with its clip; nudge the clip instead.");
    const at0 = m ? m.at : it.at;
    const node = () => document.querySelector(m ? `.mk[data-mk="${CSS.escape(id)}"]` : `.it[data-id="${CSS.escape(id)}"]`);
    // The nudge is relative: worked out when it runs, from where the item is then, so it never
    // undoes an edit that landed meanwhile (an agent's, or this page's own queued undo).
    coalesce("nudge:" + id, frames, (n) => write(() => {
      const by = Math.round(n * frameT()), mk = m && (E.doc.markers || []).find((x) => x.id === id), cur = m ? mk : E.by[id];
      if (!cur || !("at" in cur)) return null;
      return [m ? { op: "edit_marker", id, at: Math.max(0, cur.at + by) } : { op: "move_clip", id, at: Math.max(0, cur.at + by) }];
    }, m ? `Nudge marker ${m.label || id}` : `Nudge ${id}`), (n) => { const el = node(); if (el) el.style.left = px(Math.max(0, at0 + Math.round(n * frameT())) + (m ? 0 : E.spans[id][0] - at0)) + "px"; });
  }
  // The whole selection moves together (items with their own position, and markers); one entry.
  function nudgeMany(frames) {
    const ids = [...E.sels].sort(), mks = ids.filter(isMarker), its = ids.filter((id) => E.by[id] && "at" in E.by[id]);
    if (its.length + mks.length < ids.length) return toast("Some of these move with their clip; select the clips instead.");
    const at0 = Object.fromEntries(mks.map((id) => [id, E.doc.markers.find((m) => m.id === id).at]).concat(its.map((id) => [id, E.by[id].at])));
    const lo = Math.min(...Object.values(at0));
    const by = (n) => Math.max(-lo, Math.round(n * frameT())); // the earliest one stops at 0
    coalesce("nudge:" + ids.join(","), frames, (n) => write(() => { // relative, worked out when it runs (as nudge)
      const now = Object.fromEntries((E.doc.markers || []).map((x) => [x.id, x.at]).concat(Object.values(E.by).filter((x) => "at" in x).map((x) => [x.id, x.at])));
      if (ids.some((id) => now[id] == null)) return null;
      const d = Math.max(-Math.min(...ids.map((id) => now[id])), Math.round(n * frameT()));
      return mks.map((id) => ({ op: "edit_marker", id, at: now[id] + d })).concat(its.map((id) => ({ op: "move_clip", id, at: now[id] + d })));
    }, `Nudge ${ids.length} items`), (n) => ids.forEach((id) => {
      const el = document.querySelector(isMarker(id) ? `.mk[data-mk="${CSS.escape(id)}"]` : `.it[data-id="${CSS.escape(id)}"]`);
      if (el) el.style.left = px(at0[id] + by(n)) + "px";
    }));
  }
  // Zoom so the whole edit fits the timeline's width.
  function fit() {
    const sc = document.getElementById("ed-scroll"), end = Math.max(endOf(E.spans), TICK);
    setZoom((sc.clientWidth - 80) / sec(end));
    sc.scrollLeft = 0;
  }
  function setZoom(z) {
    const zs = document.getElementById("ed-zoom");
    E.zoom = Math.min(+zs.max, Math.max(+zs.min, z)); zs.value = String(E.zoom);
    timeline();
  }
  function keysHelp() {
    const rows = [["Space", "play / pause"], ["J K L", "slower or back a second / stop / play, faster each press (to 4×)"], ["← →", "one frame"], ["Shift ← →", "one second"], ["[ ]", "previous / next edit point"],
      ["Home End", "start / end"], ["Alt ← →", "nudge the selection a frame"], ["Alt Shift ← →", "nudge it ten frames"], [", .", "slip the clip a frame (Shift: a second)"], ["Alt drag", "slip a clip; on its right edge, roll the cut"], ["Shift drag", "drag without snapping"], ["S", "split at the playhead"],
      ["M", "marker at the playhead"], ["Delete", "delete the selection"], ["Ctrl click", "add or remove one from the selection"], ["Ctrl A", "select every clip and text item"], ["Esc", "clear the selection"], ["Ctrl C / V", "copy the selection / paste it at the playhead"], ["Ctrl D", "duplicate the selection right after it"], ["Ctrl Z", "undo"], ["Ctrl Shift Z", "redo"], ["\\", "zoom to fit"], ["Ctrl wheel", "zoom around the pointer"], ["?", "these keys"]];
    E.keyRows = rows; E.tab = "keys"; pane();
  }
  function dragItem(n) {
    n.onpointerdown = (e) => {
      const id = n.dataset.id, it = E.by[id];
      if (pick(id, e)) { e.stopPropagation(); return; }
      if (E.tab !== "item") { E.tab = "item"; } pane();
      if (!it || it.type === "transition") return;
      const edge = e.target.dataset ? e.target.dataset.edge : null;
      if (!edge && !("at" in it)) return; // anchored items move with their clip
      e.stopPropagation();
      const x0 = e.clientX, left0 = parseFloat(n.style.left), w0 = parseFloat(n.style.width); let moved = false;
      const alt = e.altKey && it.type === "clip" && edge !== "l"; // Alt: slip the body, roll the right edge
      if (alt && edge === "r" && !rollNext(it)) return toast("No clip starts where this one ends, so there is no cut to roll.");
      let slipDx = 0;
      holdDrag(n, e);
      const edges = edge === "r" ? [left0 + w0] : edge === "l" ? [left0] : [left0, left0 + w0];
      const pts = alt && !edge ? [] : snapPoints(id);
      n.onpointermove = (m) => {
        let dx = m.clientX - x0; if (Math.abs(dx) > 3) moved = true;
        if (alt && !edge) { slipDx = dx; const fs = n.querySelector("canvas[data-fs]"); if (fs) drawStrip(fs, Math.round(-dx / E.zoom * TICK * frac((it.props || {}).speed))); return; }
        if (moved) dx = magnet(edges, dx, pts, m.shiftKey);
        if (edge === "r") n.style.width = Math.max(4, w0 + dx) + "px";
        else if (edge === "l") { const d = Math.min(dx, w0 - 4); n.style.left = Math.max(40, left0 + d) + "px"; n.style.width = (w0 - (Math.max(40, left0 + d) - left0)) + "px"; }
        else n.style.left = Math.max(40, left0 + dx) + "px";
      };
      n.onpointerup = async () => {
        n.onpointermove = n.onpointerup = null; magnet();
        if (!moved) return; // a click only selects
        const fr = TICK * E.doc.fps[1] / E.doc.fps[0];
        if (alt) {
          // dragging the picture right shows earlier source, so a slip goes the other way
          const frames = Math.round((edge ? parseFloat(n.style.width) - w0 : -slipDx) / E.zoom * TICK / fr);
          if (!frames) return timeline();
          return edge ? roll(id, frames) : slip(id, frames);
        }
        const snap = (pxv) => Math.max(0, Math.round(Math.round(ticks((pxv - 40) / E.zoom) / fr) * fr));
        const [s0, e0] = E.spans[id];
        const ns = snap(parseFloat(n.style.left)), ne = snap(parseFloat(n.style.left) + parseFloat(n.style.width));
        if (!edge) return write([{ op: "move_clip", id, at: ns }], `Move ${id}`);
        if (it.type === "clip") {
          const sp = frac((it.props || {}).speed), mdur = E.doc.media[it.media].dur;
          if (edge === "r") {
            const out = Math.min(mdur, Math.round(it.src[0] + (ne - s0) * sp));
            return write([{ op: "trim_clip", id, src_out: out, ripple: document.getElementById("ed-ripple").checked }], `Trim ${id}`);
          }
          const inn = Math.max(0, Math.round(it.src[0] + (ns - s0) * sp));
          return write([{ op: "trim_clip", id, src_in: inn }], `Trim ${id}`);
        }
        if (edge === "r") return write([{ op: "trim_clip", id, dur: Math.max(fr, ne - s0) }], `Trim ${id}`);
        return write([{ op: "move_clip", id, at: ns }, { op: "trim_clip", id, dur: Math.max(Math.round(fr), e0 - ns) }], `Trim ${id}`);
      };
    };
  }

  /* ---------------------------------------------------------------- preview */
  function clipAt(t) {
    const v1 = E.doc.tracks.find((tr) => tr.id === "V1");
    return v1 ? v1.items.filter((it) => it.type === "clip").map((it) => [it, E.spans[it.id]]).sort((a, b) => a[1][0] - b[1][0]).find(([, s]) => s[0] <= t && t < s[1]) : null;
  }
  const proxyUrl = (mid) => `/api/projects/${encodeURIComponent(E.pid)}/media/${encodeURIComponent(mid)}/proxy`;
  // A clip's loudness at t, as the render mixes it: its volume times its linear fades (the page
  // can't play above 100%, so louder clips play at full volume here).
  function gain(it, t) {
    const [s0, s1] = E.spans[it.id]; let g = frac((it.props || {}).volume);
    if (it.fade_in && t - s0 < it.fade_in) g *= Math.max(0, (t - s0) / it.fade_in);
    if (it.fade_out && s1 - t < it.fade_out) g *= Math.max(0, (s1 - t) / it.fade_out);
    return Math.min(1, Math.max(0, g));
  }
  // What the other tracks (music, voice: any track but V1 and text) should sound like at t:
  // per track the clip under t, its proxy, the source second to be at, the rate and the volume.
  function audioPlan(t) {
    const out = [];
    E.doc.tracks.forEach((tr) => {
      if (tr.role === "text" || tr.id === "V1") return;
      const it = tr.items.find((x) => x.type === "clip" && E.spans[x.id][0] <= t && t < E.spans[x.id][1]);
      const st = it && E.media[it.media] && E.media[it.media].stages;
      if (!it || !st || (st.proxy || {}).state !== "ready") return;
      const sp = frac((it.props || {}).speed);
      out.push({ track: tr.id, clip: it.id, url: proxyUrl(it.media), at: (it.src[0] + (t - E.spans[it.id][0]) * sp) / TICK, rate: sp, volume: gain(it, t) });
    });
    return out;
  }
  // Plays the plan while the preview plays: one hidden <audio> per track on the S4 proxy
  // (audio-only media get an AAC proxy), kept within 0.25 s of the playhead.
  const AAC = (() => { try { return !!document.createElement("audio").canPlayType('audio/mp4; codecs="mp4a.40.2"'); } catch { return false; } })();
  function syncAudio() {
    if (!E.auds) E.auds = {};
    const live = new Set();
    if (E.playing && AAC && navigator.serviceWorker && navigator.serviceWorker.controller) {
      audioPlan(E.t).forEach((p) => {
        live.add(p.track);
        let a = E.auds[p.track];
        if (!a) { a = E.auds[p.track] = Object.assign(document.createElement("audio"), { preload: "auto" }); a.dataset.track = p.track; document.getElementById("ed-screen").appendChild(a); }
        const fresh = !a.src.endsWith(p.url); if (fresh) a.src = p.url;
        a.playbackRate = p.rate * (E.rate || 1); a.volume = p.volume;
        // re-seek only for a new source or clip, or real drift: V1's cuts must not make the music skip
        if (fresh || a.dataset.clip !== p.clip || Math.abs(a.currentTime - p.at) > 0.25) { a.currentTime = p.at; a.dataset.clip = p.clip; }
        if (a.paused) a.play().catch(() => {});
      });
    }
    Object.entries(E.auds).forEach(([id, a]) => { if (!live.has(id) && !a.paused) a.pause(); });
  }
  /* captions in the preview, drawn the way the render burns them (captions.build_ass): words
     grouped into lines of the style's length, broken at a pause or a sentence end, the word
     being said in the highlight colour. The style list comes from /api/caption-styles. */
  function capGroups(style) {
    const key = `${style}:${E.doc.hash}:${E.words.length}`;
    if (E.capKey === key) return E.capCache;
    const st = E.capStyles.styles[style], gap = ticks(E.capStyles.gap_s), out = [];
    let cur = [];
    E.words.forEach((w) => {
      if (cur.length && (cur.length >= st.words_per_line || w.at - cur[cur.length - 1].end > gap || /[.!?]$/.test(cur[cur.length - 1].w))) { out.push(cur); cur = []; }
      cur.push(w);
    });
    if (cur.length) out.push(cur);
    E.capKey = key; E.capCache = out;
    return out;
  }
  function drawCaption() {
    const el = document.getElementById("ed-cap"); if (!el) return;
    const style = document.getElementById("ed-cstyle").value;
    const st = style && E.capStyles && E.capStyles.styles[style];
    if (!st || !E.words.length) { el.textContent = ""; return; }
    const g = capGroups(style).find((g) => g[0].at <= E.t && E.t < Math.max(g[g.length - 1].end, g[0].at + ticks(0.08)));
    if (!g) { el.textContent = ""; return; }
    let i = g.findIndex((w, j) => E.t < (j + 1 < g.length ? Math.max(w.end, g[j + 1].at) : w.end)); if (i < 0) i = g.length - 1;
    const k = document.getElementById("ed-screen").clientHeight / E.capStyles.play_y;
    Object.assign(el.style, { fontSize: st.size * k + "px", bottom: st.margin_v * k + "px", WebkitTextStroke: `${Math.max(1, st.outline_w * k * 2)}px ${st.outline}` });
    el.innerHTML = g.map((w, j) => `<span style="color:${j === i ? st.highlight : st.primary}">${esc(st.uppercase ? w.w.toUpperCase() : w.w)}</span>`).join(" ");
  }
  function seek(t, force) {
    if (!E || !E.doc) return;
    E.t = Math.max(0, Math.round(t));
    syncAudio(); drawCaption();
    const ph = document.getElementById("ed-ph"); if (ph) ph.style.left = px(E.t) + "px";
    if (E.playing) { const sc = document.getElementById("ed-scroll"), x = px(E.t); if (sc && (x > sc.scrollLeft + sc.clientWidth - 40 || x < sc.scrollLeft)) sc.scrollLeft = Math.max(0, x - 80); }
    document.getElementById("ed-tc").textContent = tc(E.t);
    const txt = E.doc.tracks.filter((tr) => tr.role === "text").flatMap((tr) => tr.items).filter((it) => { const s = E.spans[it.id]; return s && s[0] <= E.t && E.t < s[1]; });
    const over = document.getElementById("ed-txt");
    over.textContent = txt.map((x) => x.text).join("\n");
    const v = document.getElementById("ed-video"), img = document.getElementById("ed-still");
    const hit = clipAt(E.t);
    const ready = hit && E.media[hit[0].media] && E.media[hit[0].media].stages && (E.media[hit[0].media].stages.proxy || {}).state === "ready";
    document.getElementById("ed-at").textContent = hit ? `${hit[0].id} · ${hit[0].media}` : "gap";
    if (hit && ready && H264 && navigator.serviceWorker && navigator.serviceWorker.controller) {
      const [it, [s]] = hit; const url = proxyUrl(it.media);
      const want = (it.src[0] + (E.t - s) * frac((it.props || {}).speed)) / TICK;
      E.cur = it.id;
      v.style.visibility = "visible"; img.style.visibility = "hidden"; over.style.visibility = "visible";
      if (!v.src.endsWith(url)) v.src = url;
      v.playbackRate = frac((it.props || {}).speed) * (E.rate || 1); v.volume = gain(it, E.t);
      if (force || Math.abs(v.currentTime - want) > 0.08) v.currentTime = want;
      return;
    }
    E.cur = null;
    if (!E.playing) { v.pause(); }
    v.style.visibility = "hidden"; img.style.visibility = "visible";
    over.style.visibility = hit ? "hidden" : "visible"; // engine frames already carry the text
    if (!hit) { img.removeAttribute("src"); return; }
    const w = E.playing ? 270 : 540; // smaller while playing: more frames a second; full when still
    stillWant(`${E.doc.hash}:${E.t}:${w}`, E.t, w);
  }
  // Engine stills, one request at a time: the newest wanted time is fetched when the last one
  // lands, and every frame that lands is shown if it is still for this doc. (Dropping each answer
  // that a newer request had overtaken showed nothing at all while playing: a frame takes longer
  // than the 1/6 s between requests.)
  function stillWant(key, t, w) {
    const f = E.frames;
    if (f.shown === key || f.busy === key) return;
    f.next = { key, t, w };
    if (!f.busy) stillPump();
  }
  function stillPump() {
    const s = E, f = E.frames, job = f.next; f.next = null;
    if (!job) { f.busy = null; return; }
    f.busy = job.key;
    authed(`/api/projects/${encodeURIComponent(s.pid)}/frame?at=${job.t}&width=${job.w}`).then((r) => r.blob()).then((b) => {
      if (E !== s) return;
      const img = document.getElementById("ed-still");
      if (img && job.key.startsWith(E.doc.hash + ":")) { if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src); img.src = URL.createObjectURL(b); f.shown = job.key; }
    }).catch(() => {}).finally(() => { if (E === s) stillPump(); });
  }
  function onTime() {
    if (!E || !E.playing || !E.cur) return;
    const it = E.by[E.cur]; const s = E.spans[E.cur]; if (!it || !s) return;
    const v = document.getElementById("ed-video");
    const t = s[0] + Math.round((v.currentTime * TICK - it.src[0]) / frac((it.props || {}).speed));
    if (t >= s[1] - TICK / 60) { seek(s[1], true); if (!clipAt(E.t)) gapPlay(); else v.play().catch(() => {}); return; }
    seek(t);
  }
  function gapPlay() {
    const t0 = performance.now(), from = E.t, end = endOf(E.spans), rate = E.rate || 1, gen = E.gen;
    const step = () => {
      if (!E || !E.playing || E.gen !== gen) return; // a newer play() owns the clock
      const t = from + ticks((performance.now() - t0) / 1000 * rate);
      if (t >= end) { pause(); return; }
      seek(t);
      if (clipAt(t) && E.cur) { document.getElementById("ed-video").play().catch(() => {}); return; }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  function play() {
    if (!E) return;
    if (E.t >= endOf(E.spans)) seek(0, true);
    E.playing = true; E.gen = (E.gen || 0) + 1; document.getElementById("ed-play").textContent = (E.rate || 1) === 1 ? "Pause" : `Pause · ${E.rate}×`;
    seek(E.t, true);
    if (!H264) return stillPlay();
    if (E.cur) document.getElementById("ed-video").play().catch(() => {}); else gapPlay();
  }
  function stillPlay() {
    const t0 = performance.now(), from = E.t, end = endOf(E.spans), rate = E.rate || 1, gen = E.gen;
    const step = () => {
      if (!E || !E.playing || E.gen !== gen) return;
      const t = from + ticks((performance.now() - t0) / 1000 * rate);
      if (t >= end) { pause(); return; }
      seek(t);
      setTimeout(step, 1000 / 6); // about 6 stills a second
    };
    step();
  }
  // J / K / L: L plays, and each press doubles the speed up to 4x; K stops; J halves the speed, and
  // at 1x steps back a second (the page can't play backwards).
  function shuttle(k) {
    if (k === "k") return pause();
    if (k === "l") {
      const was = E.playing ? E.rate || 1 : 0;
      if (was) { pause(); E.rate = Math.min(4, was * 2); } else E.rate = 1;
      return play();
    }
    if (E.playing && (E.rate || 1) > 1) { const r = E.rate / 2; pause(); E.rate = r; return play(); }
    const was = E.playing; pause(); E.follow = false; seek(Math.max(0, E.t - TICK), true); if (was) play();
  }
  function pause() {
    if (!E) return;
    E.playing = false; E.rate = 1; const b = document.getElementById("ed-play"); if (b) b.textContent = "Play";
    const v = document.getElementById("ed-video"); if (v) v.pause();
    syncAudio();
    if (E.doc && !E.cur) seek(E.t); // a paused still is the full-size frame, not the small playing one
  }

  /* ---------------------------------------------------------------- left panes */
  function pane() {
    const el = document.getElementById("ed-pane"); if (!el || !E.doc) return;
    el.ondragover = el.ondragleave = el.ondrop = null; el.classList.remove("drop"); // only the Media tab takes drops
    ROOT.querySelectorAll("[data-tab]").forEach((b) => { b.classList.toggle("on", b.dataset.tab === E.tab); b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(b.dataset.tab === E.tab)); });
    if (E.tab === "media") {
      const app = window.studio && typeof window.studio.pickFile === "function";
      el.innerHTML = `<label class="f">Import a file${app ? " (or drop it here)" : ""}</label><div style="display:flex;gap:.4rem"><input type="text" id="ed-path" placeholder="~/Videos/talk.mp4" style="flex:1;min-width:0" />${app ? `<button class="ed-btn" id="ed-browse">Browse…</button>` : ""}</div>
        <label class="chk"><input type="checkbox" id="ed-words" checked /> transcribe words (local Whisper)</label>
        <p><button class="ed-btn amber" id="ed-import">Import</button></p>
        <details id="ed-lib"${E.libOpen ? " open" : ""}><summary class="f" style="cursor:pointer">From your clips</summary><div id="ed-lib-list" class="hint">…</div></details>
        ${Object.entries(E.doc.media).map(([mid, m]) => {
          const st = E.media[mid] || {}; const p = Math.round((st.progress || 0) * 100);
          return `<div class="mrow"><div class="nm">${esc(mid)} · ${esc(String(m.path).split(/[\\/]/).pop())}</div>
            <div class="meta">${tc(m.dur)} · ${m.fps ? esc(m.fps[0] / m.fps[1]).slice(0, 5) + " fps" : "audio"} · ${esc(st.state || "none")}${st.stage ? " · " + esc(st.stage) : ""}</div>
            ${st.state === "running" || st.state === "queued" ? `<div class="bar"><i style="width:${p}%"></i></div>` : ""}
            <p style="margin:.35rem 0 0;display:flex;gap:.4rem"><button class="ed-btn" data-add="${esc(mid)}">Add to end</button><button class="ed-btn" data-music="${esc(mid)}">Add as music</button></p></div>`;
        }).join("")}`;
      if (app) {
        document.getElementById("ed-browse").onclick = async () => { const p = await window.studio.pickFile(); if (p) document.getElementById("ed-path").value = p; };
        el.ondragover = (e) => { e.preventDefault(); el.classList.add("drop"); };
        el.ondragleave = () => el.classList.remove("drop");
        el.ondrop = (e) => {
          e.preventDefault(); el.classList.remove("drop");
          const f = e.dataTransfer && e.dataTransfer.files[0], p = f && window.studio.pathOf && window.studio.pathOf(f);
          if (!p) return toast("Drop a file from your computer.");
          document.getElementById("ed-path").value = p; document.getElementById("ed-import").click();
        };
      }
      const lib = document.getElementById("ed-lib");
      lib.ontoggle = () => { E.libOpen = lib.open; if (lib.open) libList(); };
      if (lib.open) libList();
      document.getElementById("ed-import").onclick = async () => {
        const path = document.getElementById("ed-path").value.trim(); if (!path) return;
        const stages = ["proxy", "thumbs", "wave", "scenes"].concat(document.getElementById("ed-words").checked ? ["words"] : []);
        try { await P("import_media", { path, stages, client_op_id: rid() }); toast("Importing", true); await reload(); } catch (e) { fail(e); }
      };
      el.querySelectorAll("[data-music]").forEach((b) => (b.onclick = () => {
        const mid = b.dataset.music, m = E.doc.media[mid];
        const mus = E.doc.tracks.find((tr) => tr.role === "music");
        if (!mus) return toast("This project has no music track.");
        const at = Math.max(0, ...mus.items.map((it) => E.spans[it.id][1]));
        write([{ op: "insert_clip", track: mus.id, media: mid, src: [0, m.dur], at, props: { volume: [1, 4] } }], `Add ${mid} as music`);
      }));
      el.querySelectorAll("[data-add]").forEach((b) => (b.onclick = () => {
        const mid = b.dataset.add, m = E.doc.media[mid];
        const v1 = E.doc.tracks.find((tr) => tr.id === "V1");
        const at = Math.max(0, ...v1.items.map((it) => E.spans[it.id][1]));
        write([{ op: "insert_clip", track: "V1", media: mid, src: [0, m.dur], at }], `Add ${mid}`);
      }));
      return;
    }
    if (E.tab === "item") return itemPane(el);
    if (E.tab === "keys") { el.innerHTML = `<p class="kicker" style="margin-top:0">Keys</p><div class="keys">${(E.keyRows || []).map(([k, w]) => `<b>${esc(k)}</b><span>${esc(w)}</span>`).join("")}</div>`; return; }
    if (E.tab === "scenes") return scenesPane(el);
    const ws = E.words;
    el.innerHTML = `<p class="acts" style="display:flex;gap:.4rem;flex-wrap:wrap;margin:0 0 .7rem"><button class="ed-btn" id="ed-fill">Remove fillers</button><button class="ed-btn" id="ed-pause">Tighten pauses</button>
      <button class="ed-btn" id="ed-cutsel" ${E.wsel ? "" : "disabled"}>Cut selection</button></p>
      ${ws.length ? `<div style="display:flex;gap:.4rem;align-items:center;margin:0 0 .7rem"><input type="text" id="ed-find" placeholder="Find words (Enter: next)" value="${esc(E.find || "")}" style="flex:1;min-width:0" />
        <span class="hint" id="ed-find-n"></span><button class="ed-btn" id="ed-cutfind" disabled>Cut all</button></div>` : ""}
      ${ws.length ? `<div class="words">${ws.map((w, i) => `<span data-w="${i}" class="${/^(um+|uh+|uhm|erm?|hm+|mm|mhm)$/i.test(w.w.replace(/[^a-z]/gi, "")) ? "fill" : ""}${E.wsel && i >= E.wsel[0] && i <= E.wsel[1] ? " sel" : ""}">${esc(w.w)}</span>`).join(" ")}</div>`
        : `<p class="hint">No words yet. Import media with "transcribe words" on, then add it to the timeline.</p>`}`;
    el.querySelectorAll("[data-w]").forEach((s) => (s.onclick = (e) => {
      const i = +s.dataset.w;
      if (e.shiftKey && E.wsel) E.wsel = [Math.min(E.wsel[0], i), Math.max(E.wsel[1], i)]; else E.wsel = [i, i];
      seek(ws[i].at); pane();
    }));
    const cut = async (args, what) => {
      try {
        const p = await P("transcript_cut", Object.assign({ base_version: E.doc.version, client_op_id: rid(), preview: true }, args));
        if (!p.cuts.length) return toast("Nothing to cut.", true);
        if (!confirm(`${what}: ${p.cuts.length} cut${p.cuts.length > 1 ? "s" : ""}, ${p.removed_s.toFixed(1)} s. One undo brings it all back.`)) return;
        await P("transcript_cut", Object.assign({ base_version: E.doc.version, client_op_id: rid() }, args));
        E.wsel = null; await reload();
      } catch (e) { fail(e); }
    };
    document.getElementById("ed-fill").onclick = () => cut({ fillers: true }, "Remove fillers");
    document.getElementById("ed-pause").onclick = () => cut({ pauses: true }, "Tighten pauses");
    if (ws.length) findWords(cut);
    document.getElementById("ed-cutsel").onclick = () => { if (!E.wsel) return; const a = ws[E.wsel[0]], b = ws[E.wsel[1]]; cut({ ranges: [{ from_s: sec(a.at), to_s: sec(b.end) }] }, "Cut selection"); };
  }

  /* Find in the transcript: the words typed, as a phrase (case and punctuation ignored), marked
     where they're said; Enter steps through them, a click on one seeks there, and Cut all removes
     every match as one entry (transcript_cut ranges, previewed first). */
  const norm = (w) => w.toLowerCase().replace(/[^\p{L}\p{N}']+/gu, "");
  function findWords(cut) {
    const ws = E.words, box = document.getElementById("ed-find");
    let hits = [], cur = -1;
    const mark = () => {
      document.querySelectorAll(".words span.hit").forEach((x) => x.classList.remove("hit", "cur"));
      hits.forEach(([a, b], k) => { for (let i = a; i <= b; i++) { const sp = document.querySelector(`[data-w="${i}"]`); if (sp) { sp.classList.add("hit"); sp.classList.toggle("cur", k === cur); } } });
      document.getElementById("ed-find-n").textContent = E.find ? (cur >= 0 ? `${cur + 1}/${hits.length}` : String(hits.length)) : "";
      const b = document.getElementById("ed-cutfind"); b.disabled = !hits.length; b.textContent = hits.length ? `Cut all ${hits.length}` : "Cut all";
    };
    const search = () => {
      E.find = box.value; const q = box.value.split(/\s+/).map(norm).filter(Boolean);
      hits = []; cur = -1;
      if (q.length) for (let i = 0; i + q.length <= ws.length; i++) if (q.every((t, k) => norm(ws[i + k].w) === t)) hits.push([i, i + q.length - 1]);
      mark();
    };
    box.oninput = search;
    box.onkeydown = (e) => {
      if (e.key !== "Enter" || !hits.length) return;
      e.preventDefault(); cur = (cur + (e.shiftKey ? hits.length - 1 : 1)) % hits.length; mark();
      E.follow = false; seek(ws[hits[cur][0]].at);
      const sp = document.querySelector(`[data-w="${hits[cur][0]}"]`); if (sp) sp.scrollIntoView({ block: "nearest" });
    };
    document.getElementById("ed-cutfind").onclick = () => {
      if (hits.length) cut({ ranges: hits.map(([a, b]) => ({ from_s: sec(ws[a].at), to_s: sec(ws[b].end) })) }, `Cut "${E.find.trim()}"`);
    };
    search();
  }

  /* The desk's finished clip runs (/api/library), newest first: a click imports a clip into this
     project like any file (import_media: proxy, thumbs, wave, shot changes and its words). */
  async function libList() {
    const box = document.getElementById("ed-lib-list"); if (!box) return;
    let runs = [];
    try { runs = ((await (await fetch("/api/library")).json()).runs || []).filter((r) => (r.clips || []).length && r.dir); } catch {}
    runs.sort((a, b) => String(b.finished_at || "").localeCompare(String(a.finished_at || "")));
    if (!E || !document.getElementById("ed-lib-list")) return;
    box.innerHTML = runs.length ? runs.slice(0, 12).map((r) => `<div class="mrow"><div class="nm">${esc(r.title || r.id)}</div>
      ${r.clips.map((c) => `<p style="margin:.25rem 0;display:flex;gap:.4rem;align-items:center"><button class="ed-btn" data-lib="${esc(r.dir.replace(/[\\/]+$/, "") + "/" + c.file)}">Import</button><span class="meta">${esc(c.title || c.file)}</span></p>`).join("")}</div>`).join("")
      : `<p class="hint">No finished clip runs yet. Make some on the Clips page.</p>`;
    box.querySelectorAll("[data-lib]").forEach((b) => (b.onclick = async () => {
      const stages = ["proxy", "thumbs", "wave", "scenes"].concat(document.getElementById("ed-words").checked ? ["words"] : []);
      try { await P("import_media", { path: b.dataset.lib, stages, client_op_id: rid() }); toast("Importing", true); await reload(); } catch (e) { fail(e); }
    }));
  }

  /* ---------------------------------------------------------------- scenes */
  async function scenesPane(el) {
    el.innerHTML = `<p class="hint">Finding shot changes…</p>`;
    let cuts = [];
    try { cuts = (await P("get_scenes")).cuts; } catch (e) { fail(e); }
    if (!E || E.tab !== "scenes") return;
    el.innerHTML = cuts.length ? `<p><button class="ed-btn" id="sc-split">Split at every shot change (${cuts.length})</button></p>
      <div class="scenes">${cuts.map((c, i) => `<div class="mrow" data-sc="${i}" style="cursor:pointer;display:flex;gap:.6rem;align-items:center">
        <img data-scimg="${i}" alt="" style="width:54px;height:96px;object-fit:cover;background:#000" /><div><div class="nm">${tc(c.at)}</div><div class="meta">${esc(c.clip)} · ${esc(c.media)} ${tc(c.src)}</div></div></div>`).join("")}</div>`
      : `<p class="hint">No shot changes on the timeline. Import with scenes (on by default) or add clips that cross a cut.</p>`;
    el.querySelectorAll("[data-sc]").forEach((r) => (r.onclick = () => seek(cuts[+r.dataset.sc].at)));
    cuts.slice(0, 40).forEach((c, i) => authed(`/api/projects/${encodeURIComponent(E.pid)}/frame?at=${c.at}&width=108`).then((r) => r.blob()).then((b) => {
      const img = el.querySelector(`[data-scimg="${i}"]`); if (img) img.src = URL.createObjectURL(b);
    }).catch(() => {}));
    const sb = document.getElementById("sc-split");
    if (sb) sb.onclick = () => {
      const by = {}; cuts.forEach((c) => (by[c.clip] = by[c.clip] || []).push(c.at));
      const ops = []; let n = 0; const salt = rid().slice(3, 9);
      Object.entries(by).forEach(([clip, ats]) => {
        let cur = clip; // split the latest cut first, then keep splitting the left piece
        ats.sort((a, b) => b - a).forEach((at) => { const l = `${clip}.k${salt}${n++}`, r = `${clip}.k${salt}${n++}`; ops.push({ op: "split_clip", id: cur, at, ids: [l, r] }); cur = l; });
      });
      write(ops, `Split at ${cuts.length} shot change${cuts.length > 1 ? "s" : ""}`);
    };
  }

  /* ---------------------------------------------------------------- item inspector */
  const SPEEDS = [[1, 2], [3, 4], [1, 1], [5, 4], [3, 2], [2, 1]];
  function markerPane(el, m) {
    el.innerHTML = `<div class="mrow"><div class="nm">${esc(m.id)} · marker</div><div class="meta">${tc(m.at)}</div></div>
      <label class="f" style="margin-top:.8rem">Name</label><input type="text" id="mk-label" value="${esc(m.label)}" />
      <label class="f" style="margin-top:.8rem">At (s)</label><input type="text" id="mk-at" value="${sec(m.at).toFixed(3)}" />
      <p style="margin-top:.8rem;display:flex;gap:.4rem"><button class="ed-btn amber" id="mk-save">Save</button><button class="ed-btn" id="mk-here">Move to playhead</button><button class="ed-btn" id="mk-del">Delete</button></p>
      <p style="margin-top:.4rem"><button class="ed-btn" id="mk-chap" title="Every marker as a 'M:SS label' line from 0:00, for a video description">Copy all as chapters</button></p>
      <pre class="pv" id="mk-chap-out" hidden></pre>`;
    const $ = (id) => document.getElementById(id);
    $("mk-save").onclick = () => {
      const label = $("mk-label").value.normalize("NFC"), s = parseFloat($("mk-at").value);
      if (!(s >= 0)) return toast("The time must be 0 or more seconds.");
      const op = { op: "edit_marker", id: m.id }; const at = snapT(ticks(s));
      if (label !== m.label) op.label = label; if (at !== m.at) op.at = at;
      if (Object.keys(op).length > 2) write([op], `Edit marker ${m.label || m.id}`);
    };
    $("mk-here").onclick = () => { const at = snapT(E.t); if (at !== m.at) write([{ op: "edit_marker", id: m.id, at }], `Move marker ${m.label || m.id}`); };
    $("mk-chap").onclick = async () => {
      try {
        const o = await P("timeline_outline"), box = $("mk-chap-out");
        box.hidden = false; box.textContent = o.chapters;
        try { await navigator.clipboard.writeText(o.chapters); toast("Chapters copied", true); } catch { toast("Select the chapters below to copy them.", true); }
      } catch (e) { fail(e); }
    };
    $("mk-del").onclick = () => { selOnly(null); write([{ op: "remove_marker", id: m.id }], "Delete marker"); };
  }
  function itemPane(el) {
    if (E.sels.size > 1) {
      el.innerHTML = `<div class="mrow"><div class="nm">${E.sels.size} selected</div><div class="meta">${[...E.sels].map(esc).join(" · ")}</div></div>
        <p class="hint">Delete removes them all, and Alt+arrows nudge them together, each as one step. Ctrl-click adds or removes one; Esc clears.</p>
        <p><button class="ed-btn" id="sel-del">Delete ${E.sels.size}</button></p>`;
      document.getElementById("sel-del").onclick = del;
      return;
    }
    const mk = E.sel && (E.doc.markers || []).find((x) => x.id === E.sel);
    if (mk) return markerPane(el, mk);
    const it = E.sel && E.by[E.sel];
    if (!it) { el.innerHTML = `<p class="hint">Click an item on the timeline to change it here.</p>`; return; }
    const [a, b] = E.spans[it.id];
    const head = `<div class="mrow"><div class="nm">${esc(it.id)} · ${esc(it.type)}</div><div class="meta">${tc(a)} → ${tc(b)} · ${(sec(b - a)).toFixed(2)} s</div></div>`;
    if (it.type === "transition") { el.innerHTML = head + `<p class="hint">A ${sec(it.dur).toFixed(2)} s crossfade. Delete it to cut straight.</p>`; return; }
    const fades = `<label class="f" style="margin-top:.8rem">Fade in / out (s)</label><div style="display:flex;gap:.4rem"><input type="text" id="it-fi" value="${sec(it.fade_in || 0)}" /><input type="text" id="it-fo" value="${sec(it.fade_out || 0)}" /></div>`;
    if (it.type === "text") {
      el.innerHTML = head + `<label class="f" style="margin-top:.8rem">Text</label><textarea id="it-text" rows="3" style="width:100%;background:var(--panel);color:var(--ink);border:1px solid var(--line-2);font:inherit;padding:.4rem">${esc(it.text)}</textarea>
        <label class="f" style="margin-top:.6rem">Style</label><select id="it-style" class="ed-btn">${["pop", "impact"].map((x) => `<option ${x === it.style ? "selected" : ""}>${x}</option>`).join("")}</select>${fades}
        <p style="margin-top:.8rem"><button class="ed-btn amber" id="it-apply">Apply</button></p>`;
      document.getElementById("it-apply").onclick = () => {
        const ops = [], text = document.getElementById("it-text").value, style = document.getElementById("it-style").value;
        if (text !== it.text || style !== it.style) ops.push({ op: "edit_text", id: it.id, text, style });
        ops.push(...fadeOps(it));
        if (ops.length) write(ops, `Change ${it.id}`);
      };
      return;
    }
    const pr = Object.assign({ volume: [1, 1], speed: [1, 1] }, it.props || {});
    const vol = Math.round(frac(pr.volume) * 100), sp = frac(pr.speed);
    el.innerHTML = head + `<div class="meta mono">${esc(it.media)} · source ${tc(it.src[0])} → ${tc(it.src[1])}</div>
      <label class="f" style="margin-top:.8rem">Volume <span id="it-vol-v">${vol}%</span></label><input type="range" id="it-vol" min="0" max="200" step="5" value="${vol}" style="width:100%" />
      <label class="f" style="margin-top:.6rem">Speed</label><select id="it-speed" class="ed-btn">${SPEEDS.map(([n, d]) => `<option value="${n}/${d}" ${Math.abs(n / d - sp) < 1e-9 ? "selected" : ""}>${(n / d)}×</option>`).join("")}</select>${fades}
      <p style="margin-top:.8rem;display:flex;gap:.4rem;flex-wrap:wrap"><button class="ed-btn amber" id="it-apply">Apply</button>${nextOf(it) ? `<button class="ed-btn" id="it-xfade">Crossfade into next</button>` : ""}</p>
      <label class="f" style="margin-top:.9rem" title="Alt-drag the clip, or , and . (Shift: a second)">Slip: same place, other part of the source</label>${stepBtns("slip")}
      ${rollNext(it) ? `<label class="f" style="margin-top:.6rem" title="Alt-drag the clip's right edge">Roll the cut into ${esc(rollNext(it).id)}</label>${stepBtns("roll")}` : ""}`;
    el.querySelectorAll("[data-step]").forEach((b) => (b.onclick = () => (b.dataset.step === "slip" ? slip : roll)(it.id, +b.dataset.fr)));
    document.getElementById("it-vol").oninput = (e) => (document.getElementById("it-vol-v").textContent = e.target.value + "%");
    document.getElementById("it-apply").onclick = () => {
      const ops = [];
      const v = +document.getElementById("it-vol").value, [n, d] = document.getElementById("it-speed").value.split("/").map(Number);
      const props = {};
      if (v !== vol) props.volume = [v, 100];
      if (Math.abs(n / d - sp) > 1e-9) {
        props.speed = [n, d];
        const len = it.src[1] - it.src[0], keep = len - (len % n); // (out - in) / speed must be whole ticks
        if (keep !== len) ops.push({ op: "trim_clip", id: it.id, src_out: it.src[0] + keep });
      }
      if (Object.keys(props).length) ops.push({ op: "set_props", id: it.id, props });
      ops.push(...fadeOps(it));
      if (ops.length) write(ops, `Change ${it.id}`);
    };
    const xb = document.getElementById("it-xfade");
    if (xb) xb.onclick = () => crossfade(it);
  }
  function stepBtns(kind) {
    const fps = Math.round(E.doc.fps[0] / E.doc.fps[1]);
    return `<div style="display:flex;gap:.3rem">${[[-fps, "−1 s"], [-1, "−1 fr"], [1, "+1 fr"], [fps, "+1 s"]].map(([fr, l]) => `<button class="ed-btn" data-step="${kind}" data-fr="${fr}">${l}</button>`).join("")}</div>`;
  }
  // Slip: the clip stays put and shows the source `frames` later (negative: earlier).
  function slip(id, frames) {
    const by = Math.round(frames * frameT() * frac((E.by[id].props || {}).speed));
    return write([{ op: "slip_clip", id, by }], `Slip ${id}`);
  }
  // Roll: the cut after `id` moves `frames` later (negative: earlier); the total length stays.
  function roll(id, frames) { return write([{ op: "roll_edit", id, by: Math.round(frames * frameT()) }], `Roll ${id}`); }
  function fadeOps(it) {
    const fi = ticks(+document.getElementById("it-fi").value || 0), fo = ticks(+document.getElementById("it-fo").value || 0);
    const fr = TICK * E.doc.fps[1] / E.doc.fps[0], snap = (t) => Math.max(0, Math.round(Math.round(t / fr) * fr));
    const sets = {};
    if (snap(fi) !== (it.fade_in || 0)) sets.fade_in = snap(fi);
    if (snap(fo) !== (it.fade_out || 0)) sets.fade_out = snap(fo);
    return Object.keys(sets).length ? [Object.assign({ op: "set_fade", id: it.id }, sets)] : [];
  }
  function v1Clips() {
    const v1 = E.doc.tracks.find((tr) => tr.id === "V1");
    return v1 ? v1.items.filter((x) => x.type === "clip").sort((p, q) => E.spans[p.id][0] - E.spans[q.id][0]) : [];
  }
  // The clip a roll_edit on `it` moves: the one starting where `it` ends, or where their crossfade starts.
  function rollNext(it) {
    const tr = E.doc.tracks.find((t) => t.items.includes(it)); if (!tr) return null;
    const x = tr.items.find((t) => t.type === "transition" && t.between[0] === it.id);
    if (x) return E.by[x.between[1]] || null;
    return tr.items.find((c) => c.type === "clip" && c.id !== it.id && E.spans[c.id][0] === E.spans[it.id][1]) || null;
  }
  function nextOf(it) {
    const cs = v1Clips(), i = cs.findIndex((x) => x.id === it.id);
    if (i < 0 || i + 1 >= cs.length) return null;
    const nx = cs[i + 1];
    const v1 = E.doc.tracks.find((tr) => tr.id === "V1");
    const joined = v1.items.some((x) => x.type === "transition" && x.between[0] === it.id);
    return !joined && E.spans[nx.id][0] === E.spans[it.id][1] ? nx : null; // touching, not already faded
  }
  function crossfade(it) {
    const nx = nextOf(it); if (!nx) return toast("Crossfade needs the next clip right after this one.");
    const fr = TICK * E.doc.fps[1] / E.doc.fps[0], d = Math.round(Math.round(TICK / 2 / fr) * fr);
    const later = v1Clips().filter((x) => E.spans[x.id][0] >= E.spans[nx.id][0] && "at" in x);
    const ops = later.map((x) => ({ op: "move_clip", id: x.id, at: x.at - d })); // pull the rest in by the overlap
    ops.push({ op: "add_transition", between: [it.id, nx.id], dur: d });
    write(ops, `Crossfade ${it.id} → ${nx.id}`);
  }

  /* ---------------------------------------------------------------- sidebar */
  function side() {
    const el = document.getElementById("ed-side"); if (!el || !E.doc) return;
    const pend = E.pending || [];
    const recs = [...E.records].reverse().slice(0, 40);
    el.innerHTML = `<div class="side-h"><span class="dot ${pend.length ? "live" : ""}"></span><b>Hermes</b><span class="hint">${pend.length ? "waiting for you" : "idle"}</span>
        <label class="hint chk" style="display:inline-flex;gap:.3rem;align-items:center"><input type="checkbox" id="ed-follow" ${E.follow ? "checked" : ""} style="width:auto;margin:0" /> follow</label>
        <span class="seg" role="group" aria-label="What agents may do">${["ask", "propose", "auto"].map((m) => `<button data-mode="${m}" class="${E.mode === m ? "on" : ""}" aria-pressed="${E.mode === m}">${m}</button>`).join("")}</span></div>
      ${E.draftOf ? `<div class="card wait"><div class="who">draft</div><div class="sum">A draft of ${esc(E.draftOf)}</div>
        <div class="v">Edits here don't touch the main timeline until you keep them.</div>
        <div class="acts"><button class="ed-btn amber" id="dr-keep">Keep (one undo)</button><button class="ed-btn" id="dr-drop">Discard</button></div></div>` : ""}
      ${(E.drafts || []).map((d) => `<div class="card"><div class="who">draft · ${esc(d.items)} items</div><div class="sum">${esc(d.project_id)}</div>
        <div class="v">from v${esc(d.draft.from_version)} · now v${esc(d.version)}</div><div class="acts"><a class="ed-btn" href="#/edit/${encodeURIComponent(d.project_id)}">Open</a></div></div>`).join("")}
      ${!E.draftOf ? `<p style="margin:.6rem .7rem 0"><button class="ed-btn" id="dr-new">Start a draft</button></p>` : ""}
      ${pend.map((p) => `<div class="card wait"><div class="who agent">${esc(p.actor.id)}${p.step != null ? " · step " + esc(p.step) : ""} · waiting</div>
        <div class="sum">${esc(p.summary)}</div><div class="v">${esc(p.tool)} · ${esc(p.n_ops)} op${p.n_ops === 1 ? "" : "s"} · on v${esc(p.base_version)}</div>
        <pre class="pv" id="pv-${esc(p.pending_id)}" hidden></pre>
        <div class="acts"><button class="ed-btn amber" data-apply="${esc(p.pending_id)}">Apply</button><button class="ed-btn" data-skip="${esc(p.pending_id)}">Skip</button>
        <button class="ed-btn" data-preview="${esc(p.pending_id)}">Preview</button>
        <button class="ed-btn" data-rest="${esc(p.pending_id)}">Apply the rest</button></div></div>`).join("")}
      ${recs.map((r) => `<div class="card ${E.cancelled.has(r.op_id) ? "undone" : ""}"><div class="who ${r.actor.kind === "agent" ? "agent" : ""}">${esc(r.actor.kind === "human" ? "you" : r.actor.id)}${r.step != null ? " · step " + esc(r.step) : ""}${r.undoes ? " · undo" : ""}</div>
        <div class="sum" data-jump="${esc(r.op_id)}" title="Show what this changed">${esc(r.summary)}</div><div class="v">v${esc(r.base_version)} → v${esc(r.new_version)} · ${esc(r.changed_ids.length)} changed</div>
        <div class="ba" id="ba-${esc(r.op_id)}"></div>
        <pre class="pv" id="wx-${esc(r.op_id)}" hidden></pre>
        <div class="acts"><button class="ed-btn" data-frames="${esc(r.op_id)}">Before / after</button><button class="ed-btn" data-explain="${esc(r.op_id)}">What changed</button>${!r.undoes && !E.cancelled.has(r.op_id) ? `<button class="ed-btn" data-undo="${esc(r.op_id)}">Undo</button>` : ""}</div></div>`).join("")}
      <p class="hint" style="padding:.8rem .9rem">Agents edit this timeline through MCP (<span class="mono">hermes-studio mcp install claude</span>). In Propose mode each edit waits here for Apply or Skip.</p>`;
    document.getElementById("ed-follow").onchange = (e) => { E.follow = e.target.checked; };
    const dn = document.getElementById("dr-new");
    if (dn) dn.onclick = async () => { try { const d = await P("draft_new"); go(d.project_id); } catch (e) { fail(e); } };
    const dk = document.getElementById("dr-keep");
    if (dk) dk.onclick = async () => { const main = E.draftOf; try { await P("draft_keep"); toast("Kept: one entry on " + main, true); go(main); } catch (e) { fail(e); } };
    const dd = document.getElementById("dr-drop");
    if (dd) dd.onclick = async () => { const main = E.draftOf; if (!confirm("Delete this draft?")) return; try { await P("draft_discard"); go(main); } catch (e) { fail(e); } };
    el.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = async () => { try { await P("set_mode", { mode: b.dataset.mode }); E.mode = b.dataset.mode; side(); } catch (e) { fail(e); } }));
    const res = (pid, decision, rest) => P("approval_resolve", { pending_id: pid, decision, rest: !!rest }).then((r) => { if (r.resolved.state === "failed") fail(r.resolved.error); return reload(); }).catch(fail);
    el.querySelectorAll("[data-apply]").forEach((b) => (b.onclick = () => res(b.dataset.apply, "apply")));
    el.querySelectorAll("[data-skip]").forEach((b) => (b.onclick = () => res(b.dataset.skip, "skip")));
    // What changed: history_explain's outline lines, gone (−) and new (+), on the card; again hides it.
    el.querySelectorAll("[data-explain]").forEach((b) => (b.onclick = async () => {
      const box = document.getElementById("wx-" + b.dataset.explain);
      if (!box.hidden) { box.hidden = true; return; }
      try {
        const x = await P("history_explain", { op_id: b.dataset.explain });
        const len = x.length_s[0] === x.length_s[1] ? "" : `length ${x.length_s[0].toFixed(2)} → ${x.length_s[1].toFixed(2)} s\n`;
        box.textContent = len + x.removed.map((l) => "− " + l).concat(x.added.map((l) => "+ " + l)).join("\n") || "No visible change.";
        box.hidden = false;
      } catch (e) { fail(e); }
    }));
    // A history card's title: select what that step changed (what still exists) and go to it.
    el.querySelectorAll("[data-jump]").forEach((b) => (b.onclick = () => {
      const rec = E.records.find((x) => x.op_id === b.dataset.jump); if (!rec) return;
      const ids = rec.changed_ids.filter((id) => (E.by[id] && E.by[id].type !== "transition") || isMarker(id));
      if (!ids.length) return toast("Nothing that step changed is on the timeline now.");
      E.sels = new Set(ids); E.sel = ids[ids.length - 1]; markSel(); E.tab = "item"; pane();
      const at = (id) => (E.spans[id] ? E.spans[id][0] : (E.doc.markers.find((m) => m.id === id) || {}).at);
      E.follow = false; seek(Math.min(...ids.map(at)));
      const n = document.querySelector(`.it[data-id="${CSS.escape(ids[0])}"], .mk[data-mk="${CSS.escape(ids[0])}"]`); if (n) n.scrollIntoView({ block: "nearest", inline: "center" });
    }));
    // Preview: what Apply would do now (the engine dry-runs the parked edit): the items it would
    // touch get a dashed ember outline on the timeline, the playhead goes to the first, and the
    // outline of the result shows on the card. A second click hides it.
    el.querySelectorAll("[data-preview]").forEach((b) => (b.onclick = async () => {
      const id = b.dataset.preview, box = document.getElementById("pv-" + id);
      document.querySelectorAll(".it.ghost").forEach((n) => n.classList.remove("ghost"));
      if (!box.hidden) { box.hidden = true; return; }
      try {
        const st = await P("approval_status", { pending_id: id, preview: true }), pv = st.preview || {};
        box.hidden = false;
        if (!pv.would_apply) { box.textContent = "Apply would fail now: " + ((pv.error || {}).error || st.state); return; }
        box.textContent = `${pv.changed_ids.length} changed · ${pv.length_s.toFixed(2)} s long after\n\n${pv.outline}`;
        pv.changed_ids.forEach((cid) => { const n = document.querySelector(`.it[data-id="${CSS.escape(cid)}"]`); if (n) n.classList.add("ghost"); });
        const ts = pv.changed_ids.map((cid) => (E.spans[cid] || [])[0]).filter((x) => x != null);
        if (ts.length) seek(Math.min(...ts));
      } catch (e) { fail(e); }
    }));
    el.querySelectorAll("[data-rest]").forEach((b) => (b.onclick = () => res(b.dataset.rest, "apply", true)));
    el.querySelectorAll("[data-undo]").forEach((b) => (b.onclick = () => P("history_undo", { op_id: b.dataset.undo, client_op_id: rid() }).then(reload).catch(fail)));
    el.querySelectorAll("[data-frames]").forEach((b) => (b.onclick = async () => {
      const id = b.dataset.frames, box = document.getElementById("ba-" + id);
      try { const f = await P("history_frames", { op_id: id, width: 160 }); box.innerHTML = f._images.map((src) => `<img src="${src}" alt="" />`).join(""); seek(f.at); } catch (e) { fail(e); }
    }));
  }

  /* ---------------------------------------------------------------- actions */
  function undo() { if (E) return queued(async () => { if (E.undoTarget) { try { await P("history_undo", { op_id: E.undoTarget.op_id, client_op_id: rid() }); await reload(); } catch (e) { fail(e); } } }); }
  function redo() { if (E) return queued(async () => { if (E.redoTarget) { try { await P("history_redo", { op_id: E.redoTarget.op_id, client_op_id: rid() }); await reload(); } catch (e) { fail(e); } } }); }
  function split() {
    if (!E) return;
    const it = E.sel && E.by[E.sel] ? E.by[E.sel] : (clipAt(E.t) || [null])[0];
    if (!it) return toast("Put the playhead over a clip, or select one.");
    const s = E.spans[it.id];
    if (!(s[0] < E.t && E.t < s[1])) return toast("The playhead isn't inside that item.");
    const fr = TICK * E.doc.fps[1] / E.doc.fps[0];
    write([{ op: "split_clip", id: it.id, at: Math.round(Math.round(E.t / fr) * fr) }], `Split ${it.id}`);
  }
  function del() {
    if (!E || !E.sel) return toast("Select an item first.");
    if (E.sels.size > 1) return delMany([...E.sels]);
    if (isMarker(E.sel)) { const id = E.sel; selOnly(null); return write([{ op: "remove_marker", id }], "Delete marker"); }
    const ripple = document.getElementById("ed-ripple").checked && E.by[E.sel] && E.by[E.sel].type !== "transition";
    const id = E.sel; selOnly(null);
    write([{ op: "delete_clip", id, ripple }], `Delete ${id}`);
  }
  // Several at once, as one entry: markers, then crossfades, then items from the last to the first
  // (so a ripple never moves an item still to be deleted). A crossfade whose clip is going too is
  // left to go with it: deleted first, it would make that clip's ripple pull the next one too far.
  function delMany(ids) {
    const ripple = document.getElementById("ed-ripple").checked;
    const its = ids.filter((id) => E.by[id]).map((id) => E.by[id]);
    const going = new Set(its.filter((it) => it.type !== "transition").map((it) => it.id));
    const ops = ids.filter(isMarker).map((id) => ({ op: "remove_marker", id }))
      .concat(its.filter((it) => it.type === "transition" && !it.between.some((c) => going.has(c))).map((it) => ({ op: "delete_clip", id: it.id, ripple: false })))
      .concat(its.filter((it) => it.type !== "transition").sort((a, b) => E.spans[b.id][0] - E.spans[a.id][0]).map((it) => ({ op: "delete_clip", id: it.id, ripple })));
    selOnly(null);
    write(ops, `Delete ${ids.length} items`);
  }
  /* copy / paste / duplicate: a page clipboard (this tab only) of one clip or text item */
  function copy() {
    const it = E && E.sel && E.by[E.sel];
    if (!it || it.type === "transition") return toast("Select a clip or text item to copy.");
    const [a, b] = E.spans[it.id];
    E.clip = { item: JSON.parse(JSON.stringify(it)), track: E.doc.tracks.find((tr) => tr.items.includes(it)).id, dur: b - a };
    toast(`Copied ${it.id}`, true);
  }
  // The op that puts a copy of the clipboard item at `at` on its track (the engine picks the id).
  function copyOp(c, at) {
    const it = c.item, base = { track: c.track, at, fade_in: it.fade_in || 0, fade_out: it.fade_out || 0 };
    if (it.type === "clip") return Object.assign({ op: "insert_clip", media: it.media, src: it.src.slice() }, base, it.props ? { props: it.props } : {});
    return Object.assign({ op: "add_text", text: it.text, style: it.style, dur: it.dur }, base);
  }
  function paste() {
    if (!E || !E.clip) return toast("Copy a clip or text item first (Ctrl+C).");
    if (!E.doc.tracks.some((tr) => tr.id === E.clip.track)) return toast(`Track ${E.clip.track} is gone.`);
    write([copyOp(E.clip, snapT(E.t))], `Paste ${E.clip.item.id}`);
  }
  function duplicate() {
    const it = E && E.sel && E.by[E.sel];
    if (!it || it.type === "transition") return toast("Select a clip or text item to duplicate.");
    const [a, b] = E.spans[it.id];
    const c = { item: it, track: E.doc.tracks.find((tr) => tr.items.includes(it)).id, dur: b - a };
    write([copyOp(c, b)], `Duplicate ${it.id}`);
  }
  function addText() {
    if (!E) return;
    const text = prompt("Text"); if (!text) return;
    write([{ op: "add_text", text, style: "pop", at: E.t, dur: 2 * TICK }], `Add text`);
  }
  // The engine's frame at the playhead (what agents see: clips, looks and text; word captions are
  // the render's), at the edit's width up to 1080 px, saved as <project>-<time>.jpg.
  async function saveFrame() {
    try {
      const w = Math.min(1080, E.doc.size[0] - (E.doc.size[0] % 2)), at = E.t;
      const res = await authed(`/api/projects/${encodeURIComponent(E.pid)}/frame?at=${at}&width=${w}`);
      const url = URL.createObjectURL(await res.blob()), a = document.createElement("a");
      a.href = url; a.download = `${E.pid}-${tc(at).replace(/[:.]/g, "-")}.jpg`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) { fail(e); }
  }
  // export_otio writes exports/<project>-v<version>.otio; the desktop app shows it in its folder,
  // a browser says where it is (the file is on this machine either way).
  async function exportOtio() {
    try {
      const r = await P("export_otio"), rel = "exports/" + r.path.split(/[\\/]/).pop();
      const app = window.studio && typeof window.studio.showRender === "function";
      if (app && (await window.studio.showRender(E.pid, rel))) toast("OTIO saved: " + rel, true);
      else toast("OTIO saved: " + r.path, true);
    } catch (e) { fail(e); }
  }
  async function render() {
    try {
      const cs = document.getElementById("ed-cstyle").value, k = +document.getElementById("ed-rsize").value;
      const even = (v) => Math.max(16, Math.round(v / k / 2) * 2);
      const args = cs ? { caption_style: cs } : { captions: false };
      if (k !== 1) Object.assign(args, { width: even(E.doc.size[0]), height: even(E.doc.size[1]) });
      const r = await P("render_timeline", args);
      E.render = r; renderStatus();
    } catch (e) { fail(e); }
  }
  async function renderStatus() {
    const el = document.getElementById("ed-render-st"); if (!el || !E.render) return;
    const r = E.render;
    if (r.state === "ready") {
      const app = window.studio && typeof window.studio.showRender === "function";
      el.innerHTML = `<a href="#" id="ed-dl">Download ${esc(r.render_id || "")}</a>${app ? ` · <a href="#" id="ed-show">Show in folder</a>` : ""}`;
      if (app) document.getElementById("ed-show").onclick = async (e) => {
        e.preventDefault();
        try { const st = await P("render_status", { render_id: r.render_id }); if (!(await window.studio.showRender(E.pid, st.path))) toast("That file isn't in this project's exports."); } catch (err) { fail(err); }
      };
      document.getElementById("ed-dl").onclick = async (e) => {
        e.preventDefault();
        try {
          const st = await P("render_status", { render_id: r.render_id });
          const res = await authed(`/api/projects/${encodeURIComponent(E.pid)}/renders/${encodeURIComponent(st.render_id)}/file`);
          const url = URL.createObjectURL(await res.blob()); const a = document.createElement("a");
          a.href = url; a.download = st.path.split("/").pop(); a.click(); setTimeout(() => URL.revokeObjectURL(url), 5000);
        } catch (err) { fail(err); }
      };
    } else if (r.state === "failed") el.textContent = "Render failed: " + (r.error || "");
    else if (r.state === "cancelled") el.textContent = "Render stopped";
    else {
      el.innerHTML = `Rendering ${Math.round((r.progress || 0) * 100)}% · <a href="#" id="ed-rstop">Stop</a>`;
      document.getElementById("ed-rstop").onclick = async (e) => { e.preventDefault(); try { await P("render_cancel", { render_id: r.render_id }); } catch (err) { fail(err); } };
    }
  }

  function leave() {
    window.removeEventListener("resize", fitHeight);
    if (E) { E.ctl.abort(); document.removeEventListener("keydown", E.keys); const v = document.getElementById("ed-video"); if (v) v.pause(); Object.values(E.auds || {}).forEach((a) => { a.pause(); a.removeAttribute("src"); }); }
    E = null;
    const m = document.getElementById("main"); if (m) m.classList.remove("edit-full");
  }

  window.HSEdit = { home, open, leave, _resolve: resolve, _audioPlan: (t) => (E ? audioPlan(t) : []) };
})();
