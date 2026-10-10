/* Hermes Studio · Edit page.
   Class prefix is tl-, never ed- (that name is the Design page grid).
   Every change goes through /api/editor, which writes only via the op log. */
(function () {
  const LAB = 92;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
  if (!document.getElementById("tl-css")) {
    const s = document.createElement("style");
    s.id = "tl-css";
    s.textContent = `
      .tl{display:grid;grid-template-rows:52px minmax(140px,var(--stage,62fr)) 5px minmax(178px,var(--sheet,38fr));height:calc(100vh - 64px);background:var(--bg);color:var(--ink);overflow:hidden;min-width:0}
      .tl-grip{cursor:row-resize;background:var(--line);position:relative;touch-action:none}
      .tl-grip::after{content:"";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:44px;height:2px;border-radius:2px;background:var(--line-2)}
      .tl-grip:hover,.tl-grip.on{background:var(--amber)}
      .tl-grip:hover::after,.tl-grip.on::after{background:var(--amber-ink)}
      .tl-collapsed{grid-template-rows:52px minmax(0,1fr) 5px 40px!important}
      .tl-top,.tl-tools{display:flex;align-items:center;gap:8px;padding:0 16px;border-bottom:1px solid var(--line);min-width:0}
      .tl-top b{font-weight:800;letter-spacing:.04em;text-transform:uppercase;font-variation-settings:"wdth" 125}
      .tl-clock{font:500 13px var(--mono);color:var(--amber);white-space:nowrap}
      .tl-status{flex:1;min-width:0;color:var(--dim);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .tl-dl{color:var(--amber,#ffc83d);font-weight:600;text-decoration:none}
      .tl-dl:hover{text-decoration:underline}
      .tl-pill{border:1px solid var(--line-2);border-radius:99px;padding:2px 8px;color:var(--mute);font:500 11px var(--mono);white-space:nowrap}
      .tl button{background:none;border:1px solid var(--line-2);border-radius:7px;padding:5px 10px;cursor:pointer;color:var(--mute);font:600 11px var(--sans);letter-spacing:.08em;text-transform:uppercase}
      .tl button:hover{color:var(--ink);border-color:var(--amber)}
      .tl button.on{color:var(--ink);border-color:var(--amber);background:rgba(255,200,61,.08)}
      .tl-go{background:var(--amber)!important;color:var(--amber-ink)!important;border:0!important}
      .tl-stage{display:grid;grid-template-columns:minmax(0,1fr) 280px;min-height:0}
      .tl-view{display:grid;place-items:center;border-right:1px solid var(--line);min-width:0}
      .tl-frame{height:auto;width:auto;max-height:96%;max-width:96%;aspect-ratio:16/9;background:#050505;border:1px solid var(--line);display:flex;flex-direction:column;justify-content:flex-end;padding:14px;position:relative;overflow:hidden;box-sizing:border-box}
      .tl-vid,.tl-pic{object-fit:contain}
      .tl-can{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
      .tl-can2{display:flex;gap:6px;align-items:center;margin:0 0 8px}
      .tl-can2 input{width:5.2rem;margin:0;padding:.35rem .4rem}
      .tl-vid{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#050505;z-index:0}
      .tl-pic{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#050505;z-index:1}
      .tl-pick{padding:8px 4px 24px;max-width:760px}
      .tl-film{display:flex;justify-content:space-between;align-items:baseline;gap:16px;width:100%;text-align:left;background:none;border:0;border-top:1px solid var(--line);border-radius:0;padding:14px 0;color:var(--ink);cursor:pointer;text-transform:none;letter-spacing:0;font:600 16px var(--sans)}
      .tl-film span{color:var(--dim);font:500 12px var(--mono)}
      .tl-shade{position:absolute;left:0;right:0;bottom:0;height:42%;background:linear-gradient(transparent,#050505);z-index:1}
      .tl-frame .k,.tl-frame .big,.tl-frame .who{position:relative;z-index:2}
      .tl-frame .k{font:600 11px var(--sans);letter-spacing:.2em;text-transform:uppercase;color:var(--dim)}
      .tl-frame .big{font:500 28px/1 var(--mono);color:var(--amber);margin:.4rem 0 .2rem}
      .tl-frame .who{color:var(--mute);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .tl-bar{position:absolute;left:0;bottom:0;height:3px;background:var(--amber);width:0}
      .tl-insp{padding:16px 16px 8px;overflow:auto;min-width:0}
      .tl-insp h3{margin:0 0 8px;font:600 11px var(--sans);letter-spacing:.2em;text-transform:uppercase;color:var(--dim)}
      .tl-row{display:flex;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding:8px 0;font-size:13px}
      .tl-row span{color:var(--dim)} .tl-row b{font-weight:500;font-family:var(--mono);font-size:12px}
      .tl-keys{margin-top:14px;color:var(--dim);font:500 11px var(--mono);line-height:1.7}
      .tl-words{padding:10px 16px;font-size:14px;line-height:1.9;color:var(--ink)}
      .tl-words b{font-weight:500;color:var(--dim);font:500 12px var(--mono);margin-right:8px}
      .tl-word{cursor:pointer;border-radius:3px;padding:1px 2px}
      .tl-word:hover{background:rgba(255,200,61,.14)}
      .tl-word.on{background:var(--amber);color:var(--amber-ink)}
      .tl-act{padding:8px 16px;font-size:13px}
      .tl-act .row{display:flex;gap:8px;align-items:baseline;border-top:1px solid var(--line);padding:7px 0}
      .tl-act .who{font:600 10px var(--sans);letter-spacing:.08em;text-transform:uppercase;border:1px solid var(--line-2);border-radius:99px;padding:1px 7px;white-space:nowrap;color:var(--mute)}
      .tl-act .who.agent{color:var(--amber);border-color:var(--amber)}
      .tl-act .what{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .tl-act .who.undone,.tl-act .what.undone{opacity:.45;text-decoration:line-through}
      .tl-act .ver{font:500 11px var(--mono);color:var(--dim);white-space:nowrap}
      .tl-sheet{min-height:0;display:flex;flex-direction:column;border-top:1px solid var(--line)}
      .tl-tools{height:40px;flex:none}
      .tl-scroll{flex:1;overflow:auto;position:relative}
      .tl-ruler{height:22px;margin-left:92px;position:relative;font:500 10px var(--mono);color:var(--dim)}
      .tl-ruler i{position:absolute;top:4px;font-style:normal}
      .tl-stack{position:relative}
      .tl-trk{display:grid;grid-template-columns:92px 1fr;align-items:center;height:var(--trk,48px)}
      .tl-lab{position:sticky;left:0;z-index:3;background:var(--bg);font:500 11px var(--mono);color:var(--dim);padding-left:16px}
      .tl-lane{position:relative;height:36px;background:rgba(242,239,232,.04);border-radius:6px;margin-right:16px}
      .tl-clip{position:absolute;top:4px;height:28px;border-radius:5px;border:1px solid var(--line-2);background:#26313d;color:var(--mute);font:500 11px var(--mono);padding:0 8px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;cursor:grab;text-align:left}
      .tl-clip.text{background:#3a2f22}
      .tl-clip{isolation:isolate}
      .tl-clip.aud{font-size:10px;line-height:11px;padding-top:1px;background:#1f2a30}
      .tl-wave{position:absolute;left:0;right:0;top:12px;bottom:1px;width:100%;height:calc(100% - 13px);z-index:-1;pointer-events:none}
      .tl-wave path{fill:rgba(242,239,232,.30)}
      .tl-clip.on .tl-wave path{fill:rgba(242,239,232,.5)}
      .tl-wave .hot rect{fill:#e5484d}
      .tl-clip.on{outline:2px solid var(--amber);color:var(--ink);z-index:2}
      .tl-h{position:absolute;top:0;bottom:0;width:7px;cursor:ew-resize;background:transparent}
      .tl-h.a{left:0} .tl-h.b{right:0}
      .tl-clip.on .tl-h{background:var(--amber)}
      .tl-xf{position:absolute;top:50%;transform:translate(-50%,-50%);z-index:5;display:flex;align-items:center;gap:3px;height:16px;padding:0 6px;border-radius:99px;background:var(--amber);color:var(--amber-ink);font:700 9px var(--sans);letter-spacing:.04em;text-transform:uppercase;cursor:pointer;border:0;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,.5)}
      .tl-xf:hover{filter:brightness(1.12)}
      .tl-xf i{font-style:normal;font-size:10px}
      .tl-kf{position:absolute;bottom:3px;width:8px;height:8px;margin-left:-4px;background:var(--amber);transform:rotate(45deg);border-radius:1px;z-index:3;box-shadow:0 0 0 1px rgba(0,0,0,.4);cursor:pointer}
      .tl-kf:hover{filter:brightness(1.3)}
      .tl-kf.on{background:#fff;box-shadow:0 0 0 2px var(--amber);width:10px;height:10px;margin-left:-5px}
      .tl-play{position:absolute;top:0;bottom:0;width:2px;background:var(--amber);z-index:4;pointer-events:none}
      .tl-play::before{content:"";position:absolute;top:0;left:-4px;width:10px;height:8px;background:var(--amber);clip-path:polygon(0 0,100% 0,50% 100%)}
    `;
    document.head.appendChild(s);
  }

  let root = null, doc = null, sel = "", play = 0, msg = "", pps = 24, pid = "", renderOut = null;
  let selKf = -1;  // index of the selected keyframe on the selected clip, -1 = none
  let tab = "clips", words = [], hist = [], folded = false, stagePct = 62;
  let waves = {}; // media id -> {rate, peaks} once fetched, "wait" while in flight
  try {
    const saved = Number(localStorage.getItem("tl-stage-pct"));
    if (saved >= 24 && saved <= 86) stagePct = saved;
  } catch (err) { /* private mode: keep the default */ }
  let ripple = false, snapOn = true, playing = false, raf = 0, lastT = 0, drag = null;
  let rz = 0;
  window.addEventListener("resize", () => {
    clearTimeout(rz);
    rz = setTimeout(() => { if (root && doc) { sizeFrame(); fitTracks(); } }, 120);
  });

  async function api(body) {
    const res = await fetch("/api/editor/" + encodeURIComponent(pid || "demo"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || res.statusText);
    return data;
  }

  // Audio waveform for one clip, drawn the way Resolve and Final Cut do: peaks on a dB scale
  // (so quiet speech still shows), shaped by the clip's volume and fades, red where it clips.
  function wave(tr, c) {
    if (c.type !== "clip" || !c.media || (tr.role !== "voice" && tr.role !== "music")) return "";
    const w = waves[c.media];
    if (!w) {
      waves[c.media] = "wait";
      const want = pid;
      fetch("/api/editor/" + encodeURIComponent(pid) + "/wave/" + encodeURIComponent(c.media))
        .then((r) => r.json())
        .then((d) => { if (want !== pid) return; waves[c.media] = d.ok ? { rate: d.rate, peaks: d.peaks } : { rate: 50, peaks: [] }; if (!drag) paint(); })
        .catch(() => { waves[c.media] = { rate: 50, peaks: [] }; });
      return "";
    }
    if (w === "wait" || !w.peaks.length) return "";
    const a = Math.max(0, Math.floor((c.src_in || 0) * w.rate));
    const b = Math.min(w.peaks.length, Math.ceil((c.src_out || 0) * w.rate));
    if (b <= a) return "";
    const px = Math.max(1, c.dur * pps);
    const cols = Math.max(1, Math.min(b - a, Math.round(px)));
    const vol = c.volume == null ? 1 : c.volume;
    const fi = c.fade_in || 0, fo = c.fade_out || 0;
    const top = [], hot = [];
    for (let j = 0; j < cols; j++) {
      const s = a + Math.floor((j * (b - a)) / cols), e = Math.max(s + 1, a + Math.floor(((j + 1) * (b - a)) / cols));
      let p = 0;
      for (let k = s; k < e; k++) if (w.peaks[k] > p) p = w.peaks[k];
      const t = ((j + 0.5) / cols) * c.dur;
      const g = Math.min(1, fi > 0 ? t / fi : 1, fo > 0 ? (c.dur - t) / fo : 1);
      const amp = (p / 1000) * vol * Math.max(0, g);
      const db = 20 * Math.log10(Math.max(amp, 1e-6));
      top.push(Math.max(0, Math.min(1, (db + 48) / 48)));
      if (amp >= 0.98) hot.push(j);
    }
    let d = "M0 50";
    top.forEach((h, j) => { d += `L${j} ${(50 - h * 46).toFixed(1)}L${j + 1} ${(50 - h * 46).toFixed(1)}`; });
    for (let j = cols - 1; j >= 0; j--) d += `L${j + 1} ${(50 + top[j] * 46).toFixed(1)}L${j} ${(50 + top[j] * 46).toFixed(1)}`;
    const red = hot.map((j) => `<rect x="${Math.max(0, j - 0.5)}" y="0" width="2" height="100"/>`).join("");
    return `<svg class="tl-wave" viewBox="0 0 ${cols} 100" preserveAspectRatio="none" aria-hidden="true"><path d="${d}Z"/>${red ? `<g class="hot">${red}</g>` : ""}</svg>`;
  }

  function fmt(n) {
    n = Math.max(0, n);
    const s = Math.floor(n % 60);
    return Math.floor(n / 60) + ":" + String(s).padStart(2, "0") + "." + Math.floor((n % 1) * 10);
  }
  function find(id) {
    for (const tr of doc.tracks) {
      const it = tr.items.find((i) => i.id === id);
      if (it) return it;
    }
    return null;
  }
  function nextClip(it) {
    // The clip that starts where this one ends, on the same track -- the seam a dissolve
    // would live on. Returns null when there is no such neighbour (end of track, or a gap).
    if (!it) return null;
    const tr = doc.tracks.find((t) => t.items.some((i) => i.id === it.id));
    if (!tr) return null;
    const clips = tr.items.filter((i) => i.type === "clip").sort((a, b) => a.at - b.at);
    const idx = clips.findIndex((c) => c.id === it.id);
    if (idx < 0 || idx + 1 >= clips.length) return null;
    const nx = clips[idx + 1];
    return Math.abs(nx.at - (it.at + it.dur)) < 0.05 ? nx : null;
  }
  function marks() {
    const out = [0, doc.duration];
    for (const tr of doc.tracks) for (const it of tr.items) out.push(it.at, it.at + it.dur);
    return out;
  }
  function snap(t) {
    if (!snapOn) return Math.max(0, t);
    let best = t, gap = 8 / pps;
    for (const m of marks()) if (Math.abs(m - t) <= gap) { best = m; gap = Math.abs(m - t); }
    return Math.max(0, best);
  }
  function under() {
    const it = find(sel);
    if (it && play > it.at + 0.05 && play < it.at + it.dur - 0.05) return it;
    for (const tr of doc.tracks) {
      const hit = tr.items.find((i) => play > i.at + 0.05 && play < i.at + i.dur - 0.05);
      if (hit) return hit;
    }
    return null;
  }

  function paint() {
    if (!root || !doc) return;
    const live = root.querySelector(".tl-vid");
    const keep = live && !live.paused ? live : null;
    if (keep) keep.remove();
    const d = doc, w = Math.max(d.duration, 1);
    const size = d.size || [1920, 1080];
    const cw = Number(size[0]) || 1920, ch = Number(size[1]) || 1080;
    const preset = cw === 1920 && ch === 1080 ? "desktop" : cw === 1080 && ch === 1920 ? "phone" : cw === ch ? "square" : "";
    const width = LAB + w * pps + 16;
    const ticks = [];
    const step = pps >= 36 ? 1 : pps >= 16 ? 2 : 5;
    for (let t = 0; t <= w + 0.01; t += step) ticks.push(`<i style="left:${t * pps}px">${esc(fmt(t))}</i>`);
    const it = find(sel);
    const nextNeighbor = it ? nextClip(it) : null;
    const curSpeed = it && it.speed != null ? it.speed : 1;
    const curTf = it && it.transform ? it.transform : { x: 0, y: 0, scale: 1, rotate: 0 };
    const rows = it
      ? [["In", fmt(it.at)], ["Out", fmt(it.at + it.dur)], ["Length", it.dur.toFixed(2) + "s"], ["Source", it.src_in != null ? fmt(it.src_in) + " – " + fmt(it.src_out) : "—"]]
      : [];
    root.innerHTML = `
      <div class="tl ${folded ? "tl-collapsed" : ""}">
        <div class="tl-top">
          <b>Edit</b>
          <span class="tl-pill">v${esc(d.version)}</span>
          <span class="tl-clock">${esc(fmt(play))} / ${esc(fmt(w))}</span>
          <span class="tl-status">${esc(msg || "Drag an edge to trim. S splits at the playhead.")}${renderOut ? " <a class=\"tl-dl\" href=\"" + esc(renderOut.url) + "\" download>Save " + esc(renderOut.name) + "</a>" : ""}</span>
          <button type="button" data-act="play">${playing ? "Pause" : "Play"}</button>
          <button type="button" data-act="undo">Undo</button>
          <button type="button" data-act="redo">Redo</button>
          <button type="button" class="tl-go" data-act="render">Render</button>
          <button type="button" class="tl-go" data-act="split">Split</button>
        </div>
        <div class="tl-stage">
          <div class="tl-view"><div class="tl-frame" style="aspect-ratio:${cw}/${ch}">
            <video class="tl-vid" playsinline hidden></video>
            <img class="tl-pic" alt="" />
            <span class="tl-shade"></span>
            <span class="k">${esc(cw)} × ${esc(ch)}</span>
            <span class="big">${esc(fmt(play))}</span>
            <span class="who">${esc(it ? it.label : "No clip under the playhead")}</span>
            <span class="tl-bar" style="width:${(play / w) * 100}%"></span>
          </div></div>
          <aside class="tl-insp">
            <h3>${esc(it ? it.label : "Nothing selected")}</h3>
            <div class="tl-can">
              <button type="button" data-canvas="phone" class="${preset === "phone" ? "on" : ""}">Phone</button>
              <button type="button" data-canvas="desktop" class="${preset === "desktop" ? "on" : ""}">Desktop</button>
              <button type="button" data-canvas="square" class="${preset === "square" ? "on" : ""}">Square</button>
            </div>
            <div class="tl-can2">
              <input data-cw type="number" min="1" max="16384" value="${cw}" aria-label="Canvas width">
              <input data-ch type="number" min="1" max="16384" value="${ch}" aria-label="Canvas height">
              <button type="button" data-act="canvas">Set</button>
            </div>
            ${rows.map(([k, v]) => `<div class="tl-row"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}
            ${nextNeighbor ? `<div class="tl-row"><span></span><button type="button" data-act="dissolve">Dissolve to next</button></div>` : ""}
            ${it && it.type === "clip" ? `<div class="tl-row"><span>Speed</span><span style="display:flex;gap:4px;align-items:center"><select data-speed style="flex:1">${[0.25,0.5,0.75,1,1.25,1.5,2,4].map((v) => `<option value="${v}" ${Math.abs(curSpeed - v) < 1e-6 ? "selected" : ""}>${v}×</option>`).join("")}</select><button type="button" data-act="apply-speed">Set</button></span></div>` : ""}
            ${it && it.type === "clip" ? `<div class="tl-row"><span>Look</span><span style="display:flex;gap:4px;align-items:center"><select data-look style="flex:1"><option value="" ${it.look ? "" : "selected"}>None</option>${["warm","cool","punch","mono","film"].map((l) => `<option value="${l}" ${it.look === l ? "selected" : ""}>${l[0].toUpperCase() + l.slice(1)}</option>`).join("")}</select><button type="button" data-act="apply-look">Set</button></span></div>` : ""}
            ${it && it.type === "clip" ? `<div class="tl-row"><span>Volume</span><span style="display:flex;gap:4px;align-items:center"><input data-vol type="range" min="0" max="2" step="0.05" value="${it.volume != null ? it.volume : 1}" style="flex:1"><b style="min-width:34px;text-align:right">${(it.volume != null ? it.volume : 1).toFixed(2)}×</b></span></div>` : ""}
            ${it && it.type === "clip" ? `<div class="tl-row"><span>Fade in</span><input data-fadein type="number" min="0" step="0.1" value="${it.fade_in || 0}">s</div><div class="tl-row"><span>Fade out</span><input data-fadeout type="number" min="0" step="0.1" value="${it.fade_out || 0}">s <button type="button" data-act="apply-fade">Set</button></div>` : ""}
            ${it && it.type === "clip" ? `<div class="tl-row"><span>Crop</span><select data-crop style="flex:1"><option value="">None (full frame)</option><option value="c">Center 50%</option><option value="l">Left half</option><option value="r">Right half</option><option value="t">Top half</option><option value="b">Bottom half</option><option value="sq">Center square</option></select></div><div class="tl-row"><span></span><button type="button" data-act="apply-crop">Apply crop</button></div>` : ""}
            ${it && it.type === "clip" ? `<div class="tl-row"><span>Scale</span><span style="display:flex;gap:4px;align-items:center"><input data-tfscale type="range" min="0.1" max="3" step="0.05" value="${curTf.scale}" style="flex:1"><b style="min-width:40px;text-align:right">${curTf.scale.toFixed(2)}×</b></span></div><div class="tl-row"><span>Pos X</span><input data-tfx type="number" step="0.05" value="${curTf.x}"></div><div class="tl-row"><span>Pos Y</span><input data-tfy type="number" step="0.05" value="${curTf.y}"></div><div class="tl-row"><span>Rotate</span><input data-tfrot type="number" step="5" value="${curTf.rotate}">° <button type="button" data-act="apply-transform">Set</button></div><div class="tl-row"><span></span><button type="button" data-act="reset-transform">Reset</button></div>` : ""}
            ${it && it.type === "clip" ? `<div class="tl-row"><span>Animate</span><span style="display:flex;gap:4px;align-items:center">scale to <input data-kbend type="number" min="0.1" max="3" step="0.05" value="1.5" style="width:60px">× <button type="button" data-act="apply-kenburns">Add</button></span></div>${it.keyframes ? `<div class="tl-row"><span></span><span style="color:var(--dim);font-size:11px">${it.keyframes.length} keys</span> <button type="button" data-act="add-kf">+ at playhead</button> <button type="button" data-act="clear-kenburns">Clear</button></div>${selKf >= 0 && it.keyframes[selKf] ? (function(){ const k = it.keyframes[selKf]; return `<div class="tl-row" style="background:rgba(222,171,66,.08);border-radius:4px;padding:4px 6px"><span>Key ${selKf+1}</span><span style="display:flex;gap:3px;align-items:center;flex-wrap:wrap"><input data-kfat type="number" min="0" step="0.1" value="${k.at}" style="width:56px" title="Time (s)">s <input data-kfscale type="number" min="0.1" max="3" step="0.05" value="${k.scale}" style="width:56px" title="Scale">× <button type="button" data-act="set-kf">Set</button> <button type="button" data-act="del-kf">Del</button></span></div>`; })() : `<div class="tl-row"><span></span><span style="color:var(--dim);font-size:11px">Click a ◆ on the clip to edit it</span></div>`}` : ""}` : ""}
            <div class="tl-keys">Space play · S split · ⌫ lift<br>← → step · Shift 1s · N snap<br>Ctrl Z undo · − = zoom</div>
            <div class="tl-row"><span></span><button type="button" data-act="reset">Reset demo</button></div>
          </aside>
        </div>
        <div class="tl-grip" data-act="grip" title="Drag to resize the timeline"></div>
        <div class="tl-sheet">
          <div class="tl-tools">
            <button type="button" data-tab="clips" class="${tab === "clips" ? "on" : ""}">Clips</button>
            <button type="button" data-tab="words" class="${tab === "words" ? "on" : ""}">Transcript</button>
            <button type="button" data-tab="act" class="${tab === "act" ? "on" : ""}">Activity</button>
            <button type="button" data-act="fold">${folded ? "Show" : "Hide"}</button>
            <span style="flex:1"></span>
            <button type="button" data-act="lift">Lift</button>
            <button type="button" data-act="ripple" class="${ripple ? "on" : ""}">Ripple ${ripple ? "on" : "off"}</button>
            <button type="button" data-act="snap" class="${snapOn ? "on" : ""}">Snap ${snapOn ? "on" : "off"}</button>
            <button type="button" data-act="zoom-out">−</button>
            <button type="button" data-act="zoom-in">+</button>
            <button type="button" data-act="fit">Fit</button>
          </div>
          <div class="tl-scroll">
            ${tab === "words" ? `<div class="tl-words">${words.length ? words.map((wd) => `<b>${esc(fmt(wd.start))}</b><span class="tl-word${play >= wd.start && play < wd.end ? " on" : ""}" data-word="${wd.start}">${esc(wd.text)}</span>`).join(" ") : `<span style="color:var(--dim)">No words in this cut yet.</span>`}</div>` : tab === "act" ? `<div class="tl-act">${hist.length ? hist.map((h) => `<div class="row"><span class="who ${h.kind === "agent" ? "agent" : ""} ${h.undone ? "undone" : ""}">${esc(h.actor)}</span><span class="what ${h.undone ? "undone" : ""}">${esc(h.summary)}</span><span class="ver">v${esc(h.to)}</span></div>`).join("") : `<span style="color:var(--dim)">No changes yet. Trim, split or lift and each step lands here.</span>`}</div>` : `
            <div class="tl-ruler" style="width:${width - LAB}px">${ticks.join("")}</div>
            <div class="tl-stack" style="width:${width}px">
              <div class="tl-play" style="left:${LAB + play * pps}px"></div>
              ${d.tracks.map((tr) => `<div class="tl-trk"><span class="tl-lab">${esc(tr.id)} ${esc(tr.role)}</span><div class="tl-lane" data-lane>
                ${tr.items.map((c) => `<div class="tl-clip ${c.type}${c.media && (tr.role === "voice" || tr.role === "music") ? " aud" : ""}${c.id === sel ? " on" : ""}" data-id="${esc(c.id)}" data-at="${c.at}" data-dur="${c.dur}" style="left:${c.at * pps}px;width:${Math.max(c.dur * pps, 2)}px" title="${esc(c.label)}">${wave(tr, c)}${c.dur * pps > 42 ? esc(c.label) : ""}${(c.keyframes || []).map((k, ki) => `<i class="tl-kf${c.id === sel && ki === selKf ? " on" : ""}" data-kfidx="${ki}" style="left:${k.at * pps}px" title="Keyframe ${ki + 1} at ${k.at.toFixed(1)}s · scale ${k.scale.toFixed(2)}× · click to select"></i>`).join("")}<i class="tl-h a" data-edge="start" data-id="${esc(c.id)}"></i><i class="tl-h b" data-edge="end" data-id="${esc(c.id)}"></i></div>`).join("")}
                ${tr.items.filter((c) => c.type === "transition").map((c) => `<button type="button" class="tl-xf" data-xf="${esc(c.id)}" data-between="${esc((c.between || []).join(","))}" data-dur="${c.dur}" style="left:${c.at * pps}px" title="Dissolve ${esc(c.dur.toFixed(1))}s — click to remove"><i>◐</i>${esc(c.dur.toFixed(1))}s</button>`).join("")}
              </div></div>`).join("")}
            </div>`}
          </div>
        </div>
      </div>`;
    const slot = root.querySelector(".tl-vid");
    if (keep && slot) {
      slot.replaceWith(keep);
      const img = root.querySelector(".tl-pic");
      if (img) img.hidden = true;
      bindFilm(keep);
    }
    root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act)));
    // Volume is a live slider: update the readout as it drags, and commit on release.
    const vol = root.querySelector("[data-vol]");
    if (vol) {
      const readout = vol.parentElement.querySelector("b");
      vol.addEventListener("input", () => { if (readout) readout.textContent = parseFloat(vol.value).toFixed(2) + "×"; });
      vol.addEventListener("change", async () => {
        const s2 = find(sel);
        if (!s2) return;
        await commit({ op: "volume", id: s2.id, volume: parseFloat(vol.value) });
      });
    }
    // Scale slider readout updates live too.
    const tfs = root.querySelector("[data-tfscale]");
    if (tfs) {
      const readout = tfs.parentElement.querySelector("b");
      tfs.addEventListener("input", () => { if (readout) readout.textContent = parseFloat(tfs.value).toFixed(2) + "×"; });
    }
    root.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { tab = b.dataset.tab; paint(); }));
    root.querySelectorAll("[data-xf]").forEach((b) => b.addEventListener("click", async () => {
      const pair = String(b.dataset.between || "").split(",");
      if (pair.length !== 2) return;
      // Clicking a dissolve badge removes it (back to a hard cut), which is the common
      // correction; setting a length is the inspector's job.
      await commit({ op: "transition", a: pair[0], b: pair[1], seconds: 0 });
    }));
    const grip = root.querySelector(".tl-grip");
    if (grip) {
      grip.addEventListener("pointerdown", gripDown);
      grip.addEventListener("pointermove", gripMove);
      grip.addEventListener("pointerup", gripUp);
      grip.addEventListener("pointercancel", gripUp);
    }
    root.querySelectorAll("[data-word]").forEach((b) => b.addEventListener("click", () => {
      stop();
      play = Number(b.dataset.word) || 0;
      head();
      paint();
    }));
    root.querySelectorAll("[data-canvas]").forEach((b) => b.addEventListener("click", () => {
      const map = { phone: [1080, 1920], desktop: [1920, 1080], square: [1080, 1080] };
      const pair = map[b.dataset.canvas];
      if (pair) commit({ op: "canvas", width: pair[0], height: pair[1] });
    }));
    const pic = root.querySelector(".tl-pic");
    if (pic) pic.addEventListener("error", () => { pic.hidden = true; });
    showFrame();
    applySplit();
    sizeFrame();
    fitTracks();
    const sc = root.querySelector(".tl-scroll");
    sc.addEventListener("pointerdown", down);
    sc.addEventListener("pointermove", movePtr);
    sc.addEventListener("pointerup", up);
  }

  function head() {
    const line = root && root.querySelector(".tl-play");
    if (!line) return;
    line.style.left = LAB + play * pps + "px";
    const clock = root.querySelector(".tl-clock");
    const big = root.querySelector(".tl-frame .big");
    const bar = root.querySelector(".tl-bar");
    if (clock) clock.textContent = fmt(play) + " / " + fmt(doc.duration);
    if (big) big.textContent = fmt(play);
    if (bar) bar.style.width = (play / Math.max(doc.duration, 0.01)) * 100 + "%";
    showFrame();
  }

  let shown = -1;
  function showFrame() {
    const img = root && root.querySelector(".tl-pic");
    if (!img || !doc) return;
    if (playing) return;
    const t = Math.max(0, Math.round(play * 5) / 5);
    if (t === shown && img.getAttribute("src")) return;
    shown = t;
    img.hidden = false;
    img.src = "/api/editor/" + encodeURIComponent(pid || "demo") + "/frame?t=" + t;
  }

  function xToTime(e) {
    const lane = root.querySelector(".tl-lane");
    const r = lane.getBoundingClientRect();
    return (e.clientX - r.left) / pps;
  }

  function down(e) {
    if (e.button !== 0) return;
    stop();
    const kf = e.target.closest("[data-kfidx]");
    if (kf) {
      // A keyframe diamond: select it and start a drag that moves its time along the clip.
      // The scale/value is edited in the inspector; dragging scrubs *when* it happens.
      const clipEl = kf.closest("[data-id]");
      sel = clipEl.dataset.id;
      selKf = Number(kf.dataset.kfidx);
      const item = find(sel);
      const kfAt = item && item.keyframes && item.keyframes[selKf] ? item.keyframes[selKf].at : 0;
      drag = { kind: "kf", id: sel, kfidx: selKf, at0: kfAt, x0: e.clientX, moved: false };
      // Highlight the selected diamond in place -- a full paint() here would rebuild the
      // DOM and detach the pointer listeners mid-drag, so the move/up would never land.
      root.querySelectorAll(".tl-kf.on").forEach((n) => n.classList.remove("on"));
      kf.classList.add("on");
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* capture is a nicety; the scroll listener still sees the moves */ }
      return;
    }
    const edge = e.target.closest("[data-edge]");
    const clip = e.target.closest("[data-id]");
    if (edge) {
      const it = find(edge.dataset.id);
      sel = edge.dataset.id;
      drag = { kind: "trim", edge: edge.dataset.edge, id: sel, at: it.at, dur: it.dur };
    } else if (clip && clip.dataset.at) {
      sel = clip.dataset.id;
      selKf = -1;
      drag = { kind: "move", id: sel, at0: Number(clip.dataset.at), x0: e.clientX, moved: false };
    } else if (e.target.closest("[data-lane]")) {
      play = snap(Math.max(0, Math.min(doc.duration, xToTime(e))));
      drag = { kind: "seek" };
      head();
    } else return;
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function movePtr(e) {
    if (!drag) return;
    if (drag.kind === "seek") {
      play = snap(Math.max(0, Math.min(doc.duration, xToTime(e))));
      head();
      return;
    }
    if (drag.kind === "kf") {
      // Move the selected keyframe's time along the clip, clamped between its neighbours so
      // the track stays strictly increasing (dragging onto a neighbour would be refused by
      // the op, so prevent it here). Live-position the diamond; commit on release.
      const it = find(drag.id);
      if (!it || !it.keyframes) return;
      const kfs = it.keyframes;
      const i = drag.kfidx;
      const lo = i > 0 ? kfs[i - 1].at : 0;
      const hi = i < kfs.length - 1 ? kfs[i + 1].at : (it.dur || 0);
      const eps = 0.05;
      const t = snap(Math.max(lo + eps, Math.min(hi - eps, drag.at0 + (e.clientX - drag.x0) / pps)));
      const el = root.querySelector(`[data-id="${drag.id}"] .tl-kf.on`);
      if (el) el.style.left = t * pps + "px";
      drag.atNow = t;
      drag.moved = Math.abs(e.clientX - drag.x0) > 3;
      return;
    }
    const it = find(drag.id);
    const el = root.querySelector(`[data-id="${drag.id}"]`);
    if (!it || !el) return;
    if (drag.kind === "trim") {
      let t = snap(xToTime(e));
      if (drag.edge === "start") t = Math.min(Math.max(0, t), drag.at + drag.dur - 0.05);
      else t = Math.max(t, drag.at + 0.05);
      const at = drag.edge === "start" ? t : drag.at;
      const dur = drag.edge === "start" ? drag.at + drag.dur - t : t - drag.at;
      el.style.left = at * pps + "px";
      el.style.width = Math.max(dur * pps, 2) + "px";
      drag.atNow = t;
    } else {
      const t = snap(Math.max(0, drag.at0 + (e.clientX - drag.x0) / pps));
      el.style.left = t * pps + "px";
      drag.atNow = t;
      drag.moved = Math.abs(e.clientX - drag.x0) > 3;
    }
  }

  async function up() {
    const d = drag;
    drag = null;
    if (!d || d.kind === "seek" || d.atNow == null) return;
    if (d.kind === "kf") {
      if (!d.moved) { paint(); return; }
      // Re-send the keyframe track with the dragged key's time updated; the op re-validates
      // increasing-time order, so a drag that would collide with a neighbour is refused.
      const it = find(d.id);
      if (!it || !it.keyframes) { paint(); return; }
      const kfs = it.keyframes.map((k, i) => (i === d.kfidx ? { ...k, at: d.atNow } : { ...k }));
      await commit({ op: "keyframes", id: d.id, keyframes: kfs });
      return;
    }
    if (d.kind === "move" && !d.moved) { paint(); return; }
    const body = d.kind === "trim"
      ? { op: "edge", item: d.id, edge: d.edge, at: d.atNow, ripple }
      : { op: "move", item: d.id, at: d.atNow };
    await commit(body);
  }

  async function commit(body) {
    try {
      const data = await api(body);
      doc = data.project;
      msg = data.project.summary || "Saved.";
      if (sel && !find(sel)) {
        let best = null, gap = 0.25;
        for (const tr of doc.tracks) for (const i of tr.items) {
          const d = Math.abs(i.at - play);
          if (d < gap) { best = i; gap = d; }
        }
        sel = best ? best.id : "";
      }
      // The keyframe list may have shrunk or been cleared; clamp the selection so the
      // inspector doesn't point past the end.
      const cur = find(sel);
      if (!cur || !cur.keyframes || selKf >= cur.keyframes.length) selKf = -1;
    } catch (e) {
      msg = e.message;
    }
    paint();
    await loadHist();
    paint();
  }

  function gripDown(e) {
    const shell = root && root.querySelector(".tl");
    if (!shell) return;
    drag = { y: e.clientY, h: shell.getBoundingClientRect().height, from: stagePct };
    const g = e.currentTarget;
    if (g && g.classList) g.classList.add("on");
    if (g && g.setPointerCapture) { try { g.setPointerCapture(e.pointerId); } catch (err) { /* capture is a nicety */ } }
  }
  function gripMove(e) {
    if (!drag || !root) return;
    const dy = e.clientY - drag.y;
    // The shell has a 52px top bar and a 5px grip as fixed rows, so a percentage of the
    // whole shell is not a percentage of the splittable area. Work in the space that is
    // actually being divided, or the drag and the resulting layout disagree.
    const shell = root.querySelector(".tl");
    if (!shell) return;
    const rows = getComputedStyle(shell).gridTemplateRows.split(" ").map(parseFloat);
    const splittable = rows.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0) - (Number.isFinite(rows[0]) ? rows[0] : 52) - (Number.isFinite(rows[2]) ? rows[2] : 5);
    const usable = splittable > 40 ? splittable : drag.h - 57;
    const pct = drag.from + (dy / usable) * 100;
    stagePct = Math.max(24, Math.min(86, Math.round(pct)));
    applySplit();
    sizeFrame();
  }
  function gripUp() {
    if (!drag) return;
    drag = null;
    const g = root && root.querySelector(".tl-grip");
    if (g && g.classList) g.classList.remove("on");
    // Remember the split so the layout the person chose survives a reload.
    try { localStorage.setItem("tl-stage-pct", String(stagePct)); } catch (err) { /* private mode */ }
  }
  function applySplit() {
    const shell = root && root.querySelector(".tl");
    if (!shell) return;
    if (folded) return;
    shell.style.setProperty("--stage", (stagePct / Math.max(1, 100 - stagePct)).toFixed(3) + "fr");
    shell.style.setProperty("--sheet", "1fr");
    // The rows have just been re-divided, so the scroll box only knows its new height
    // after a layout pass. Measure on the next frame or the rows are sized for the
    // previous split and the bottom tracks hide behind a scrollbar.
    requestAnimationFrame(fitTracks);
  }

  function fitTracks() {
    /* Every track the cut has must be reachable without hunting for a scrollbar. When
       the panel is short, shrink the rows rather than hide the bottom tracks. */
    const sc = root && root.querySelector(".tl-scroll");
    const shell = root && root.querySelector(".tl");
    if (!sc || !shell || !doc) return;
    const n = Math.max(1, doc.tracks.length);
    const h = sc.clientHeight;
    // A box with no height yet (just re-divided, or mid-teardown) would compute a
    // nonsense row size and hide tracks. Keep the last sane value instead.
    if (h < 40) {
      const had = Number(shell.style.getPropertyValue("--trk").replace("px", ""));
      if (Number.isFinite(had) && had >= 18) return;
      shell.style.setProperty("--trk", "22px");
      return;
    }
    const want = Math.floor((h - 22) / n); // the ruler
    // 18px is the smallest row that still reads as a track; below that the panel is too
    // short to show every track, and the fold button is the honest answer.
    shell.style.setProperty("--trk", Math.max(18, Math.min(48, want)) + "px");
  }

  function sizeFrame() {
    const stage = root && root.querySelector(".tl-view");
    const frame = root && root.querySelector(".tl-frame");
    if (!stage || !frame || !doc) return;
    const box = stage.getBoundingClientRect();
    const size = doc.size || [1920, 1080];
    const cw = Number(size[0]) || 1920, ch = Number(size[1]) || 1080;
    const ratio = cw / ch;
    let fh = box.height * 0.9, fw = fh * ratio;
    if (fw > box.width * 0.94) { fw = box.width * 0.94; fh = fw / ratio; }
    frame.style.width = Math.max(120, fw) + "px";
    frame.style.height = Math.max(80, fh) + "px";
  }

  function stop() {
    playing = false;
    lastT = 0;
    if (raf) cancelAnimationFrame(raf);
    const v = root && root.querySelector(".tl-vid");
    if (v) v.pause();
  }
  function mainClip(t) {
    const tr = doc.tracks.find((x) => x.role === "main");
    return tr && tr.items.find((i) => t >= i.at && t < i.at + i.dur - 0.02);
  }
  function pieceAt(file, srcT) {
    const tr = doc.tracks.find((x) => x.role === "main");
    if (!tr) return null;
    return tr.items.find((i) => i.file === file && srcT >= (i.src_in || 0) - 0.04 && srcT < (i.src_out != null ? i.src_out : 1e9) - 0.03) || null;
  }
  function bindFilm(v) {
    v.ontimeupdate = () => {
      if (!playing || !doc) return;
      const piece = pieceAt(v.dataset.file, v.currentTime);
      if (piece) {
        play = piece.at + (v.currentTime - (piece.src_in || 0));
        head();
        return;
      }
      const items = (doc.tracks.find((x) => x.role === "main") || {}).items || [];
      const nxt = items.find((i) => i.at >= play - 0.05);
      if (!nxt) { stop(); paint(); return; }
      play = nxt.at;
      if (nxt.file !== v.dataset.file) startFilm();
      else head();
    };
  }
  function startFilm() {
    const v = root.querySelector(".tl-vid");
    const it = mainClip(play);
    if (!v || !it || !it.file) return false;
    v.hidden = false;
    v.muted = false;
    const img = root.querySelector(".tl-pic");
    if (img) img.hidden = true;
    const want = (it.src_in || 0) + Math.max(0, play - it.at);
    if (v.dataset.file !== it.file) {
      v.dataset.file = it.file;
      v.src = "/api/editor/" + encodeURIComponent(pid) + "/media/" + encodeURIComponent(it.file);
    }
    const arm = () => { if (Math.abs((v.currentTime || 0) - want) > 0.25) v.currentTime = want; };
    if (v.readyState >= 1) arm();
    else v.addEventListener("loadedmetadata", arm, { once: true });
    const pending = v.play();
    if (pending && pending.catch) pending.catch(() => { msg = "Press Play again for sound."; playing = false; });
    bindFilm(v);
    return true;
  }
  function loop(t) {
    if (!playing) return;
    if (lastT) play += (t - lastT) / 1000;
    lastT = t;
    if (play >= doc.duration) { play = doc.duration; stop(); paint(); return; }
    head();
    const sc = root.querySelector(".tl-scroll");
    const x = LAB + play * pps;
    if (sc && (x < sc.scrollLeft + LAB || x > sc.scrollLeft + sc.clientWidth - 24)) sc.scrollLeft = Math.max(0, x - sc.clientWidth * 0.4);
    raf = requestAnimationFrame(loop);
  }

  async function act(name) {
    if (name === "play") {
      if (playing) { stop(); paint(); return; }
      if (play >= doc.duration) play = 0;
      playing = true;
      paint();
      if (!startFilm()) raf = requestAnimationFrame(loop);
      return;
    }
    if (name === "fold") {
      folded = !folded;
      paint();
      return;
    }
    if (name === "grip") return;
    if (name === "dissolve") {
      const it = find(sel);
      const nx = it ? nextClip(it) : null;
      if (!nx) { msg = "No clip next to dissolve into."; paint(); return; }
      // A 0.75s dissolve is a sane default that reads on screen; undo restores the hard cut.
      await commit({ op: "transition", a: it.id, b: nx.id, seconds: 0.75 });
      return;
    }
    if (name === "apply-speed") {
      const sel2 = find(sel);
      const pick = root.querySelector("[data-speed]");
      if (!sel2 || !pick) return;
      await commit({ op: "speed", id: sel2.id, speed: parseFloat(pick.value) });
      return;
    }
    if (name === "apply-look") {
      const s2 = find(sel);
      const pick = root.querySelector("[data-look]");
      if (!s2 || !pick) return;
      await commit({ op: "look", id: s2.id, look: pick.value || null });
      return;
    }
    if (name === "apply-fade") {
      const s2 = find(sel);
      const fi = root.querySelector("[data-fadein]");
      const fo = root.querySelector("[data-fadeout]");
      if (!s2 || !fi || !fo) return;
      await commit({ op: "fade", id: s2.id, fade_in: parseFloat(fi.value) || 0, fade_out: parseFloat(fo.value) || 0 });
      return;
    }
    if (name === "apply-crop") {
      const s2 = find(sel);
      const pick = root.querySelector("[data-crop]");
      if (!s2 || !pick) return;
      const presets = {
        "": [0, 0, 1, 1], c: [0.25, 0.25, 0.5, 0.5], l: [0, 0, 0.5, 1], r: [0.5, 0, 0.5, 1],
        t: [0, 0, 1, 0.5], b: [0, 0.5, 1, 0.5], sq: [0.25, 0.125, 0.5, 0.5],
      };
      const [x, y, w, h] = presets[pick.value] || presets[""];
      await commit({ op: "crop", id: s2.id, x, y, w, h });
      return;
    }
    if (name === "apply-transform" || name === "reset-transform") {
      const s2 = find(sel);
      if (!s2) return;
      if (name === "reset-transform") {
        await commit({ op: "transform", id: s2.id, x: 0, y: 0, scale: 1, rotate: 0 });
        return;
      }
      const sc = root.querySelector("[data-tfscale]");
      const px = root.querySelector("[data-tfx]");
      const py = root.querySelector("[data-tfy]");
      const pr = root.querySelector("[data-tfrot]");
      if (!sc || !px || !py || !pr) return;
      await commit({ op: "transform", id: s2.id, scale: parseFloat(sc.value) || 1, x: parseFloat(px.value) || 0, y: parseFloat(py.value) || 0, rotate: parseFloat(pr.value) || 0 });
      return;
    }
    if (name === "apply-kenburns" || name === "clear-kenburns") {
      const s2 = find(sel);
      if (!s2) return;
      if (name === "clear-kenburns") {
        await commit({ op: "keyframes", id: s2.id, keyframes: null });
        return;
      }
      // A Ken Burns push: from the clip's current static transform to the target scale,
      // across the clip's full length. Two keyframes cover the common move.
      const endEl = root.querySelector("[data-kbend]");
      const endScale = parseFloat((endEl || {}).value) || 1.5;
      const start = s2.transform || { x: 0, y: 0, scale: 1, rotate: 0 };
      await commit({
        op: "keyframes", id: s2.id,
        keyframes: [
          { at: 0, x: start.x, y: start.y, scale: start.scale, rotate: start.rotate },
          { at: s2.dur, x: start.x, y: start.y, scale: endScale, rotate: start.rotate },
        ],
      });
      return;
    }
    if (name === "add-kf" || name === "set-kf" || name === "del-kf") {
      const s2 = find(sel);
      if (!s2 || !s2.keyframes) return;
      // Work on a copy of the keyframe list; each edit re-sends the whole track (the op is
      // all-or-nothing, which keeps the schema's increasing-time rule enforced in one place).
      let kfs = s2.keyframes.map((k) => ({ ...k }));
      if (name === "add-kf") {
        // Insert a key at the playhead, carrying the current static transform's scale so the
        // move doesn't jump. Re-sorted by time below.
        const base = s2.transform || { x: 0, y: 0, scale: 1, rotate: 0 };
        kfs.push({ at: Math.max(0, Math.min(s2.dur, play)), x: base.x, y: base.y, scale: base.scale, rotate: base.rotate });
      } else if (name === "del-kf") {
        if (selKf < 0 || selKf >= kfs.length) return;
        kfs.splice(selKf, 1);
        selKf = -1;
        await commit({ op: "keyframes", id: s2.id, keyframes: kfs.length >= 2 ? kfs : null });
        return;
      } else {  // set-kf: edit the selected keyframe's time and scale
        if (selKf < 0 || selKf >= kfs.length) return;
        const atEl = root.querySelector("[data-kfat]");
        const scEl = root.querySelector("[data-kfscale]");
        kfs[selKf].at = parseFloat((atEl || {}).value) || 0;
        kfs[selKf].scale = parseFloat((scEl || {}).value) || 1;
      }
      kfs.sort((a, b) => a.at - b.at);
      await commit({ op: "keyframes", id: s2.id, keyframes: kfs.length >= 2 ? kfs : null });
      return;
    }
    if (name === "ripple") { ripple = !ripple; paint(); return; }
    if (name === "snap") { snapOn = !snapOn; paint(); return; }
    if (name === "zoom-in" || name === "zoom-out") { pps = Math.max(8, Math.min(220, pps * (name === "zoom-in" ? 1.25 : 0.8))); paint(); return; }
    if (name === "fit") { fit(); paint(); return; }
    if (name === "canvas") {
      const w = Number(root.querySelector("[data-cw]") && root.querySelector("[data-cw]").value);
      const h = Number(root.querySelector("[data-ch]") && root.querySelector("[data-ch]").value);
      await commit({ op: "canvas", width: w, height: h });
      return;
    }
    if (name === "render") {
      msg = "Rendering… this takes a moment.";
      paint();
      try {
        const res = await api({ op: "render" });
        doc = res.project;
        const r = res.render || {};
        msg = `Rendered ${r.name || "file"} — ${r.size ? r.size[0] + "×" + r.size[1] : ""} ${r.duration || ""}s`;
        renderOut = { name: r.name || "", url: "/api/editor/" + encodeURIComponent(pid) + "/render" };
      } catch (e) {
        msg = e.message;
      }
      paint();
      return;
    }
    if (name === "split" && playing) {
      const target = under();
      if (!target) { msg = "Move the playhead inside a clip."; return; }
      sel = target.id;
      await commit({ op: "split", item: target.id, at: play });
      playing = true;
      const v = root.querySelector(".tl-vid");
      if (v && !v.paused) bindFilm(v);
      else startFilm();
      return;
    }
    stop();
    if (name === "undo" || name === "redo" || name === "reset") { await commit({ op: name === "reset" ? "reset" : name }); return; }
    const target = name === "split" ? under() : find(sel);
    if (!target) { msg = name === "split" ? "Move the playhead inside a clip." : "Select a clip first."; paint(); return; }
    sel = target.id;
    if (name === "split") await commit({ op: "split", item: target.id, at: play });
    else if (name === "lift") await commit({ op: "lift", item: target.id, ripple });
  }

  function fit() {
    const box = root ? root.clientWidth : 900;
    pps = Math.max(8, (box - LAB - 48) / Math.max(doc.duration, 1));
  }

  function onKey(e) {
    if (!document.body.classList.contains("editing") || !doc) return;
    if (e.target.closest("input, textarea")) return;
    const k = e.key.toLowerCase();
    if (k === " " || k === "s" || k === "n" || k === "backspace" || k === "delete" || k === "arrowleft" || k === "arrowright" || k === "-" || k === "=" || (e.ctrlKey && k === "z")) e.preventDefault();
    if (k === " ") act("play");
    else if (k === "s") act("split");
    else if (k === "n") act("snap");
    else if (k === "backspace" || k === "delete") act("lift");
    else if (k === "arrowleft" || k === "arrowright") { stop(); play = Math.max(0, Math.min(doc.duration, play + (k === "arrowright" ? 1 : -1) * (e.shiftKey ? 1 : 0.1))); head(); }
    else if (k === "-" || k === "=") act(k === "=" ? "zoom-in" : "zoom-out");
    else if (e.ctrlKey && k === "z") act(e.shiftKey ? "redo" : "undo");
  }

  async function films(node) {
    const res = await fetch("/api/editor/films");
    const data = await res.json().catch(() => ({}));
    const rows = (data.films || []).map((f) => `<button type="button" class="tl-film" data-film="${esc(f.id)}"><b>${esc(f.title)}</b><span>${esc(f.clips)} clips</span></button>`).join("");
    node.innerHTML = `<div class="tl-pick"><b>EDIT</b><p class="tl-status">Open a film from the library.</p>${rows || "<p class='tl-status'>No films in the library.</p>"}</div>`;
    node.querySelectorAll("[data-film]").forEach((b) => b.addEventListener("click", () => { location.hash = "#/edit/" + encodeURIComponent(b.dataset.film); }));
  }

  async function loadWords() {
    try {
      const res = await fetch("/api/editor/" + encodeURIComponent(pid) + "/transcript");
      const data = await res.json().catch(() => ({}));
      words = data.words || [];
    } catch (e) {
      words = [];
    }
  }

  async function loadHist() {
    try {
      const res = await fetch("/api/editor/" + encodeURIComponent(pid) + "/history");
      const data = await res.json().catch(() => ({}));
      hist = data.history || [];
    } catch (e) {
      hist = [];
    }
  }

  async function open(node, id) {
    root = node;
    pid = id || "";
    words = [];
    hist = [];
    waves = {};
    document.body.classList.add("editing");
    if (!pid) { await films(node); return; }
    node.innerHTML = `<p class="tl-status">Opening the film…</p>`;
    try {
      const data = pid === "demo" ? await api({ op: "open" }).catch(() => api({ op: "reset" })) : await api({ op: "import" });
      doc = data.project;
      sel = (doc.tracks[1].items[0] || {}).id || "";
      const first = find(sel);
      play = first ? first.at + Math.min(1, first.dur / 2) : 0;
      msg = data.project.summary || "";
      await loadWords();
      await loadHist();
      paint();
      requestAnimationFrame(() => { if (root && doc) { fit(); paint(); } });
    } catch (e) {
      node.innerHTML = `<p class="tl-status">${esc(e.message)}</p>`;
    }
  }
  function leave() {
    stop();
    document.body.classList.remove("editing");
    root = null;
  }
  document.addEventListener("keydown", onKey);
  window.HSEdit = { open, leave };
})();
