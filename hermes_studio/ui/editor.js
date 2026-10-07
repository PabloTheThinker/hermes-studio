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
      .tl{display:grid;grid-template-rows:52px minmax(0,1fr) 292px;height:calc(100vh - 64px);background:var(--bg);color:var(--ink);overflow:hidden;min-width:0}
      .tl-top,.tl-tools{display:flex;align-items:center;gap:8px;padding:0 16px;border-bottom:1px solid var(--line);min-width:0}
      .tl-top b{font-weight:800;letter-spacing:.04em;text-transform:uppercase;font-variation-settings:"wdth" 125}
      .tl-clock{font:500 13px var(--mono);color:var(--amber);white-space:nowrap}
      .tl-status{flex:1;min-width:0;color:var(--dim);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .tl-pill{border:1px solid var(--line-2);border-radius:99px;padding:2px 8px;color:var(--mute);font:500 11px var(--mono);white-space:nowrap}
      .tl button{background:none;border:1px solid var(--line-2);border-radius:7px;padding:5px 10px;cursor:pointer;color:var(--mute);font:600 11px var(--sans);letter-spacing:.08em;text-transform:uppercase}
      .tl button:hover{color:var(--ink);border-color:var(--amber)}
      .tl button.on{color:var(--ink);border-color:var(--amber);background:rgba(255,200,61,.08)}
      .tl-go{background:var(--amber)!important;color:var(--amber-ink)!important;border:0!important}
      .tl-stage{display:grid;grid-template-columns:minmax(0,1fr) 280px;min-height:0}
      .tl-view{display:grid;place-items:center;border-right:1px solid var(--line);min-width:0}
      .tl-frame{height:auto;width:auto;max-height:86%;max-width:94%;aspect-ratio:9/16;background:#050505;border:1px solid var(--line);display:flex;flex-direction:column;justify-content:flex-end;padding:14px;position:relative;overflow:hidden}
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
      .tl-sheet{min-height:0;display:flex;flex-direction:column;border-top:1px solid var(--line)}
      .tl-tools{height:40px;flex:none}
      .tl-scroll{flex:1;overflow:auto;position:relative}
      .tl-ruler{height:22px;margin-left:92px;position:relative;font:500 10px var(--mono);color:var(--dim)}
      .tl-ruler i{position:absolute;top:4px;font-style:normal}
      .tl-stack{position:relative}
      .tl-trk{display:grid;grid-template-columns:92px 1fr;align-items:center;height:48px}
      .tl-lab{position:sticky;left:0;z-index:3;background:var(--bg);font:500 11px var(--mono);color:var(--dim);padding-left:16px}
      .tl-lane{position:relative;height:36px;background:rgba(242,239,232,.04);border-radius:6px;margin-right:16px}
      .tl-clip{position:absolute;top:4px;height:28px;border-radius:5px;border:1px solid var(--line-2);background:#26313d;color:var(--mute);font:500 11px var(--mono);padding:0 8px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;cursor:grab;text-align:left}
      .tl-clip.text{background:#3a2f22}
      .tl-clip.on{outline:2px solid var(--amber);color:var(--ink);z-index:2}
      .tl-h{position:absolute;top:0;bottom:0;width:7px;cursor:ew-resize;background:transparent}
      .tl-h.a{left:0} .tl-h.b{right:0}
      .tl-clip.on .tl-h{background:var(--amber)}
      .tl-play{position:absolute;top:0;bottom:0;width:2px;background:var(--amber);z-index:4;pointer-events:none}
      .tl-play::before{content:"";position:absolute;top:0;left:-4px;width:10px;height:8px;background:var(--amber);clip-path:polygon(0 0,100% 0,50% 100%)}
    `;
    document.head.appendChild(s);
  }

  let root = null, doc = null, sel = "", play = 0, msg = "", pps = 24, pid = "";
  let ripple = false, snapOn = true, playing = false, raf = 0, lastT = 0, drag = null;

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
    const size = d.size || [1080, 1920];
    const cw = Number(size[0]) || 1080, ch = Number(size[1]) || 1920;
    const preset = cw === 1920 && ch === 1080 ? "desktop" : cw === 1080 && ch === 1920 ? "phone" : cw === ch ? "square" : "";
    const width = LAB + w * pps + 16;
    const ticks = [];
    const step = pps >= 36 ? 1 : pps >= 16 ? 2 : 5;
    for (let t = 0; t <= w + 0.01; t += step) ticks.push(`<i style="left:${t * pps}px">${esc(fmt(t))}</i>`);
    const it = find(sel);
    const rows = it
      ? [["In", fmt(it.at)], ["Out", fmt(it.at + it.dur)], ["Length", it.dur.toFixed(2) + "s"], ["Source", it.src_in != null ? fmt(it.src_in) + " – " + fmt(it.src_out) : "—"]]
      : [];
    root.innerHTML = `
      <div class="tl">
        <div class="tl-top">
          <b>Edit</b>
          <span class="tl-pill">v${esc(d.version)}</span>
          <span class="tl-clock">${esc(fmt(play))} / ${esc(fmt(w))}</span>
          <span class="tl-status">${esc(msg || "Drag an edge to trim. S splits at the playhead.")}</span>
          <button type="button" data-act="play">${playing ? "Pause" : "Play"}</button>
          <button type="button" data-act="undo">Undo</button>
          <button type="button" data-act="redo">Redo</button>
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
            <div class="tl-keys">Space play · S split · ⌫ lift<br>← → step · Shift 1s · N snap<br>Ctrl Z undo · − = zoom</div>
            <div class="tl-row"><span></span><button type="button" data-act="reset">Reset demo</button></div>
          </aside>
        </div>
        <div class="tl-sheet">
          <div class="tl-tools">
            <button type="button" data-act="lift">Lift</button>
            <button type="button" data-act="ripple" class="${ripple ? "on" : ""}">Ripple ${ripple ? "on" : "off"}</button>
            <button type="button" data-act="snap" class="${snapOn ? "on" : ""}">Snap ${snapOn ? "on" : "off"}</button>
            <button type="button" data-act="zoom-out">−</button>
            <button type="button" data-act="zoom-in">+</button>
            <button type="button" data-act="fit">Fit</button>
          </div>
          <div class="tl-scroll">
            <div class="tl-ruler" style="width:${width - LAB}px">${ticks.join("")}</div>
            <div class="tl-stack" style="width:${width}px">
              <div class="tl-play" style="left:${LAB + play * pps}px"></div>
              ${d.tracks.map((tr) => `<div class="tl-trk"><span class="tl-lab">${esc(tr.id)} ${esc(tr.role)}</span><div class="tl-lane" data-lane>
                ${tr.items.map((c) => `<div class="tl-clip ${c.type}${c.id === sel ? " on" : ""}" data-id="${esc(c.id)}" data-at="${c.at}" data-dur="${c.dur}" style="left:${c.at * pps}px;width:${Math.max(c.dur * pps, 2)}px" title="${esc(c.label)}">${c.dur * pps > 42 ? esc(c.label) : ""}<i class="tl-h a" data-edge="start" data-id="${esc(c.id)}"></i><i class="tl-h b" data-edge="end" data-id="${esc(c.id)}"></i></div>`).join("")}
              </div></div>`).join("")}
            </div>
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
    root.querySelectorAll("[data-canvas]").forEach((b) => b.addEventListener("click", () => {
      const map = { phone: [1080, 1920], desktop: [1920, 1080], square: [1080, 1080] };
      const pair = map[b.dataset.canvas];
      if (pair) commit({ op: "canvas", width: pair[0], height: pair[1] });
    }));
    const pic = root.querySelector(".tl-pic");
    if (pic) pic.addEventListener("error", () => { pic.hidden = true; });
    showFrame();
    const stage = root.querySelector(".tl-view");
    const frame = root.querySelector(".tl-frame");
    if (stage && frame) {
      const box = stage.getBoundingClientRect();
      const ratio = cw / ch;
      let fh = box.height * 0.86, fw = fh * ratio;
      if (fw > box.width * 0.94) { fw = box.width * 0.94; fh = fw / ratio; }
      frame.style.width = Math.max(120, fw) + "px";
      frame.style.height = Math.max(80, fh) + "px";
    }
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
    const edge = e.target.closest("[data-edge]");
    const clip = e.target.closest("[data-id]");
    if (edge) {
      const it = find(edge.dataset.id);
      sel = edge.dataset.id;
      drag = { kind: "trim", edge: edge.dataset.edge, id: sel, at: it.at, dur: it.dur };
    } else if (clip && clip.dataset.at) {
      sel = clip.dataset.id;
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
    } catch (e) {
      msg = e.message;
    }
    paint();
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

  async function open(node, id) {
    root = node;
    pid = id || "";
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
