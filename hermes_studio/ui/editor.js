/* Hermes Studio · Edit page.
   Class prefix is tl-, never ed- (that name is the Design page grid).
   Every change goes through /api/editor, which writes only via the op log. */
(function () {
  const LAB = 164; // track header width; CSS reads it as --lab, so the two can't drift
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
  if (!document.getElementById("tl-css")) {
    const s = document.createElement("style");
    s.id = "tl-css";
    s.textContent = `
      .tl{display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:52px minmax(140px,var(--stage,62fr)) 5px minmax(178px,var(--sheet,38fr));height:calc(100vh - 64px);background:var(--bg);color:var(--ink);overflow:hidden;min-width:0}
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
      .tl-stage{display:grid;grid-template-columns:minmax(0,1fr) 280px;grid-template-rows:minmax(0,1fr);min-height:0;overflow:hidden}
      .tl-view{display:grid;place-items:center;border-right:1px solid var(--line);min-width:0;min-height:0;overflow:hidden}
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
      .tl-insp{padding:16px 16px 8px;overflow:auto;min-width:0;min-height:0}
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
      .tl-sheet{min-height:0;min-width:0;display:flex;flex-direction:column;border-top:1px solid var(--line)}
      .tl-tools{height:40px;flex:none}
      .tl-scroll{flex:1;overflow:auto;position:relative}
      .tl-ruler{height:22px;margin-left:var(--lab,164px);position:relative;font:500 10px var(--mono);color:var(--dim)}
      .tl-ruler i{position:absolute;top:0;bottom:0;padding:4px 0 0 4px;border-left:1px solid var(--line-2);font-style:normal;white-space:nowrap}
      .tl-ruler b{position:absolute;bottom:0;width:1px;height:5px;background:var(--line-2)}
      .tl-rng{position:absolute;top:0;bottom:0;background:rgba(255,200,61,.22);pointer-events:none}
      .tl-mk{position:absolute;top:0;bottom:0;width:7px;border:2px solid var(--amber);pointer-events:none;box-sizing:border-box}
      .tl-mk.in{border-right:0;margin-left:0}
      .tl-mk.out{border-left:0;margin-left:-7px}
      .tl-rngv{position:absolute;top:0;bottom:0;background:rgba(255,200,61,.05);border-left:1px dashed rgba(255,200,61,.55);border-right:1px dashed rgba(255,200,61,.55);pointer-events:none;z-index:1}
      .tl-rngpill{background:rgba(255,200,61,.16);color:var(--amber)}
      --mk-cyan:#4cc9f0;--mk-green:#57d9a3;--mk-yellow:#ffc83d;--mk-orange:#ff9f45;--mk-red:#e5484d;--mk-pink:#f4a4c0;--mk-purple:#b78cff
      .tl-mlayer{position:absolute;left:var(--lab,164px);top:22px;bottom:0;right:0;pointer-events:none;z-index:6}
      .tl-mk{position:absolute;top:0;bottom:0;width:0;--mc:var(--blue,#4cc9f0)}
      .tl-mk b{position:absolute;top:-21px;left:-7px;width:14px;height:14px;line-height:13px;text-align:center;border-radius:7px;background:var(--mc);color:#000;font:600 9px var(--mono);pointer-events:auto;cursor:pointer;z-index:1}
      .tl-mk:hover:after{opacity:1}
      .tl-mk:after{content:"";position:absolute;top:15px;bottom:0;left:0;width:7px;background:var(--mc);opacity:.35;pointer-events:auto;cursor:pointer}
      .tl-mk:hover b,.tl-mk.at b{outline:2px solid rgba(255,255,255,.6);outline-offset:-1px}
      .tl-mk em{position:absolute;top:1px;left:-3px;width:7px;height:7px;background:var(--mc);transform:rotate(45deg);opacity:0;transition:opacity .12s}
      .tl-mk:hover em{opacity:1}
      .tl-mk.at b{box-shadow:0 0 0 2px rgba(255,255,255,.55)}
      .tl-mkstrip{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
      .tl-mksw{width:11px;height:11px;border-radius:3px;border:1px solid rgba(255,255,255,.25);padding:0;cursor:pointer}
      .tl-mksw.on{outline:2px solid var(--ink);outline-offset:1px}
      .tl-stack{position:relative}
      .tl-trk{display:grid;grid-template-columns:var(--lab,164px) 1fr;align-items:center;height:var(--row,var(--trk,48px));position:relative}
      .tl-rz{position:absolute;left:0;bottom:-3px;width:var(--lab,164px);height:6px;cursor:ns-resize;z-index:4}
      .tl-lab{display:flex;align-items:center;gap:6px;padding-right:9px;height:100%;box-sizing:border-box}
      .tl-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .tl-mix{display:flex;gap:3px;flex:none}
      .tl-mix button{height:18px;min-width:18px;padding:0 4px;border-radius:3px;border:1px solid var(--line-2);background:transparent;color:var(--dim);font:700 9px var(--mono);cursor:pointer;line-height:16px}
      .tl-mix .tl-m.on{background:#e5484d;border-color:#e5484d;color:#fff}
      .tl-mix .tl-s.on{background:var(--amber);border-color:var(--amber);color:var(--amber-ink)}
      .tl-mix .tl-g{min-width:40px;cursor:ns-resize;font-weight:500}
      .tl-trk.quiet .tl-lane{opacity:.4}
      .tl-vu{position:absolute;right:2px;top:5px;bottom:5px;width:3px;border-radius:2px;background:rgba(242,239,232,.08);overflow:hidden}
      .tl-vu b{position:absolute;inset:0;background:linear-gradient(to top,#3fb950 0%,#3fb950 80%,#d29922 80%,#d29922 95%,#e5484d 95%);clip-path:inset(100% 0 0 0)}
      .tl-vu.hot{box-shadow:0 0 0 1px #e5484d}
      .tl-pill.solo{background:var(--amber);color:var(--amber-ink)}
      .tl-rz:hover,.tl-rz.on{background:linear-gradient(transparent 2px,var(--amber) 2px,var(--amber) 4px,transparent 4px)}
      .tl-lab{position:sticky;left:0;z-index:3;background:var(--bg);font:500 11px var(--mono);color:var(--dim);padding-left:12px}
      .tl-lane{position:relative;height:max(12px,calc(var(--row,var(--trk,48px)) - 12px));background:rgba(242,239,232,.04);border-radius:6px;margin-right:16px}
      .tl-clip{position:absolute;top:max(2px,min(4px,calc((var(--row,var(--trk,48px)) - 12px) / 9)));height:max(8px,calc(var(--row,var(--trk,48px)) - 20px));border-radius:5px;border:1px solid var(--line-2);background:#26313d;color:var(--mute);font:500 11px var(--mono);padding:0 8px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;cursor:grab;text-align:left}
      .tl-clip.text{background:#3a2f22}
      .tl-clip{isolation:isolate}
      .tl-clip.aud{font-size:10px;line-height:11px;padding-top:1px;background:#1f2a30}
      .tl-wave{position:absolute;left:0;right:0;top:12px;bottom:1px;width:100%;height:calc(100% - 13px);z-index:-1;pointer-events:none}
      .tl-wave path{fill:rgba(242,239,232,.30)}
      .tl-clip.on .tl-wave path{fill:rgba(242,239,232,.5)}
      .tl-wave .hot rect{fill:#e5484d}
      .tl-band{position:absolute;left:0;right:0;top:12px;bottom:1px;z-index:2;pointer-events:none}
      .tl-bandsvg{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
      .tl-bl{fill:none;stroke:var(--amber);stroke-width:1.5;opacity:.9;pointer-events:none}
      .tl-bhit{fill:none;stroke:transparent;stroke-width:10;pointer-events:stroke;cursor:ns-resize}
      .tl-gk{position:absolute;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:var(--amber);border:1px solid rgba(0,0,0,.65);pointer-events:auto;cursor:move;z-index:3}
      .tl-clip.on{outline:2px solid var(--amber);color:var(--ink);z-index:2}
      /* A clip that is in the group but not the anchor: a thinner ring, so the last-clicked
         clip (the one the inspector edits) still reads as the primary. */
      .tl-clip.sel{outline:2px dashed rgba(222,171,66,.7);z-index:2}
      .tl-clip.sel.on{outline:2px solid var(--amber)}
      /* The marquee rectangle, drawn over the lanes while a drag selects. */
      .tl-clip.slipping{cursor:ew-resize;outline:2px dotted var(--amber)}
      .tl-clip.slipping .tl-wave{opacity:.85}
      .tl-marq{position:absolute;border:1px solid var(--amber);background:rgba(222,171,66,.12);pointer-events:none;z-index:6;border-radius:2px}
      .tl-h{position:absolute;top:0;bottom:0;width:7px;cursor:ew-resize;background:transparent;z-index:4}
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
  // Multi-clip selection, Resolve / Final Cut style. selSet holds every selected clip id;
  // sel stays the "last one" so the inspector keeps pointing at something concrete. An
  // anchored item (a text bound to a clip) never joins the group -- it has no timeline of
  // its own to move on -- but a marquee over the timeline still shows the clips it covers.
  let selSet = new Set();
  let tab = "clips", words = [], hist = [], folded = false, stagePct = 62;
  let waves = {}; // media id -> {rate, peaks} once fetched, "wait" while in flight
  // The preview mixer (mix.js): when every audible clip's sound is decoded, playback runs on
  // the audio clock and the picture follows it. Until then the old <video>-led path plays.
  const mix = window.HSMix ? window.HSMix.create() : null;
  let mixing = false;
  // Transport speed, signed: 1 is normal play, 2/4/8 a forward shuttle, negative plays backwards
  // (J/K/L). 1x and 2x forward play the real mix; faster and reverse are picture only.
  let rate = 1, kHeld = false, lastSeek = 0;
  // In/Out marks (I / O), kept per project in the browser: marking a range isn't an edit, so it
  // stays out of the op log, like Resolve's timeline marks. stopAt ends a "/" range play.
  let inOut = { in: null, out: null }, stopAt = null;
  // The marker being renamed in the inspector (Shift+M), or null.
  let mkSel = null, mkName = "";
  let lastMk = { id: "", t: 0 };
  function loadMarks(id) {
    try {
      const m = JSON.parse(localStorage.getItem("tl-marks:" + id) || "{}");
      return { in: Number.isFinite(m.in) ? m.in : null, out: Number.isFinite(m.out) ? m.out : null };
    } catch (e) { return { in: null, out: null }; }
  }
  function saveMarks() { try { localStorage.setItem("tl-marks:" + pid, JSON.stringify(inOut)); } catch (e) { /* private mode */ } }
  // The marked range in seconds, [in, out]; one mark alone runs to the start or the end.
  function rangeOf() {
    if (!doc || (inOut.in == null && inOut.out == null)) return null;
    const a = inOut.in == null ? 0 : Math.min(inOut.in, doc.duration);
    const b = inOut.out == null ? doc.duration : Math.min(inOut.out, doc.duration);
    return b > a ? [a, b] : null;
  }
  function setMark(which, t) {
    const v = Math.max(0, Math.min(doc.duration, frameOf(t) / fpsOf())); // on the frame grid
    inOut[which] = v;
    // A mark set past its partner clears the partner (Premiere's rule), never an inverted range.
    if (which === "in" && inOut.out != null && inOut.out <= v) inOut.out = null;
    if (which === "out" && inOut.in != null && inOut.in >= v) inOut.in = null;
    saveMarks();
    paint();
  }
  try {
    const saved = Number(localStorage.getItem("tl-stage-pct"));
    if (saved >= 24 && saved <= 86) stagePct = saved;
  } catch (err) { /* private mode: keep the default */ }
  // Per-track row heights the person dragged (a view preference, like Resolve's track height:
  // it is not an edit, so it never touches the op log). Unset tracks share what's left.
  const TRK_MIN = 20, TRK_MAX = 160;
  let trkH = {};
  try {
    const raw = JSON.parse(localStorage.getItem("tl-trk-h") || "{}");
    for (const [k, v] of Object.entries(raw || {})) if (Number(v) >= TRK_MIN && Number(v) <= TRK_MAX) trkH[k] = Number(v);
  } catch (err) { trkH = {}; }
  let lastRz = { id: "", t: 0 };
  let viewRo = null;
  function saveTrkH() { try { localStorage.setItem("tl-trk-h", JSON.stringify(trkH)); } catch (err) { /* private mode */ } }
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

  // Track mixer strip (mute / solo / gain). The op log owns the values; these just read them.
  function isAudio(tr) { return tr.role === "voice" || tr.role === "music"; }
  function audible(tr) {
    if (!isAudio(tr) || tr.mute || !(tr.gain == null || tr.gain > 0)) return false;
    return !doc.tracks.some((t) => t.solo) || !!tr.solo;
  }
  const DB_FLOOR = -48; // below this a fader reads as off (gain 0)
  function toDb(g) { return g > 0 ? 20 * Math.log10(g) : -Infinity; }
  function fromDb(db) { return db <= DB_FLOOR ? 0 : Math.min(4, Math.pow(10, db / 20)); }
  function mkSection(mk) {
    // The marker under the playhead (Resolve's marker list, inline): rename it, colour it,
    // delete it. Empty when there's none.
    if (!mk) return "";
    return `<div class="tl-row" style="background:rgba(76,201,240,.07);border-radius:4px;padding:6px"><span class="tl-mkstrip"><input data-mkname type="text" maxlength="200" value="${esc(mk.label)}" placeholder="Marker name" style="width:120px" title="Marker name"> <button type="button" data-act="mk-apply" title="Rename">Save</button> <button type="button" data-act="mk-del" title="Delete marker">Del</button> <span class="tl-mksw${(mk.color || "blue") === "blue" ? " on" : ""}" data-act="mk-color" data-color="blue" title="Blue (default)" style="background:var(--mk-cyan)"></span>${["cyan", "green", "yellow", "orange", "red", "pink", "purple"].map((c) => `<span class="tl-mksw${mk.color === c ? " on" : ""}" data-act="mk-color" data-color="${c}" title="${c}" style="background:var(--mk-${c})"></span>`).join("")}</span><b style="margin-left:auto">${esc(tc(mk.at))}</b></div>`;
  }
  function fmtDb(g) {
    const db = toDb(g == null ? 1 : g);
    if (!Number.isFinite(db)) return "−∞";
    const r = Math.round(db * 10) / 10;
    return (r > 0 ? "+" : r < 0 ? "−" : "") + Math.abs(r).toFixed(1);
  }
  let wheelT = 0, wheelGain = null;

  // The clip's volume line (rubber band) over the waveform, Resolve / Final Cut style. Its height
  // runs +12 dB at the top to silence at the bottom; it shows volume x the envelope.
  const BAND_TOP = 12, BAND_SPAN = 60;
  function envAt(keys, u) {
    if (window.HSMix && window.HSMix.envAt) return window.HSMix.envAt(keys, u);
    return keys && keys.length ? keys[0].gain : 1;
  }
  function lvlY(g) {
    const db = g > 0 ? 20 * Math.log10(g) : -Infinity;
    return ((BAND_TOP - Math.max(-48, Math.min(BAND_TOP, db))) / BAND_SPAN) * 100;
  }
  function yLvl(frac) {
    const db = BAND_TOP - frac * BAND_SPAN;
    return db <= -47.5 ? 0 : Math.min(4, Math.pow(10, db / 20));
  }
  function bandHtml(c, keys, vol) {
    const W = Math.max(1, c.dur * pps);
    const lv = (u) => vol * (keys ? envAt(keys, u) : 1);
    const pts = [[0, lv(0)]];
    if (keys) for (const k of keys) if (k.at > 0 && k.at < c.dur) pts.push([k.at, lv(k.at)]);
    pts.push([c.dur, lv(c.dur)]);
    const line = pts.map(([u, g]) => `${(u * pps).toFixed(1)},${lvlY(g).toFixed(2)}`).join(" ");
    const dots = (keys || []).map((k, i) => (k.at >= 0 && k.at <= c.dur
      ? `<i class="tl-gk" data-gk="${i}" style="left:${(k.at * pps).toFixed(1)}px;top:${lvlY(vol * k.gain).toFixed(2)}%" title="Volume key ${i + 1} · ${esc(fmtDb(vol * k.gain))} dB · drag to move · Alt-click removes"></i>`
      : "")).join("");
    return `<svg class="tl-bandsvg" viewBox="0 0 ${W.toFixed(1)} 100" preserveAspectRatio="none"><polyline class="tl-bl" points="${line}" vector-effect="non-scaling-stroke"/><polyline class="tl-bhit" data-gline="1" points="${line}" vector-effect="non-scaling-stroke"><title>Clip level · drag up or down · Alt-click adds a volume key</title></polyline></svg>${dots}`;
  }
  function band(tr, c) {
    if (c.type !== "clip" || !c.media || (tr.role !== "voice" && tr.role !== "music")) return "";
    return `<span class="tl-band" data-band="${esc(c.id)}">${bandHtml(c, c.gain_keys, c.volume == null ? 1 : c.volume)}</span>`;
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
    const vol = (c.volume == null ? 1 : c.volume) * (tr.gain == null ? 1 : tr.gain);
    const fi = c.fade_in || 0, fo = c.fade_out || 0;
    const top = [], hot = [];
    for (let j = 0; j < cols; j++) {
      const s = a + Math.floor((j * (b - a)) / cols), e = Math.max(s + 1, a + Math.floor(((j + 1) * (b - a)) / cols));
      let p = 0;
      for (let k = s; k < e; k++) if (w.peaks[k] > p) p = w.peaks[k];
      const t = ((j + 0.5) / cols) * c.dur;
      const g = Math.min(1, fi > 0 ? t / fi : 1, fo > 0 ? (c.dur - t) / fo : 1);
      const amp = (p / 1000) * vol * Math.max(0, g) * (c.gain_keys ? envAt(c.gain_keys, t) : 1);
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

  // Frames and timecode from the project's own rate (view() sends fps as [num, den]).
  function fpsOf() { const f = doc && doc.fps; const v = f && f[1] ? f[0] / f[1] : 30; return v > 0 ? v : 30; }
  function frameOf(t) { return Math.floor(Math.max(0, t) * fpsOf() + 1e-6); }
  // HH:MM:SS:FF, non-drop-frame on the nominal rate (29.97 counts as 30, as NDF does).
  function tc(t) {
    const base = Math.max(1, Math.round(fpsOf()));
    const n = frameOf(t), s = Math.floor(n / base);
    return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60, n % base].map((x) => String(x).padStart(2, "0")).join(":");
  }
  function stepFrames(n) {
    if (playing) { stop(); paint(); }
    play = Math.max(0, Math.min(doc.duration, (frameOf(play) + n) / fpsOf()));
    head();
  }
  function showRate() {
    const el = root && root.querySelector(".tl-rate");
    if (!el) return;
    el.hidden = !playing || rate === 1;
    el.textContent = (rate < 0 ? "◀◀ " : "▶▶ ") + Math.abs(rate) + "×";
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
  // ---- multi-clip selection -------------------------------------------------------
  // A movable item is one that carries its own `at` (a clip or a piece of one). An anchored
  // item (text bound to a clip) has no `at` of its own, so it never joins a group move or
  // delete -- move_items/delete_items would refuse it anyway.
  function movable(id) { const it = find(id); return !!it && it.at != null && it.type !== "transition"; }
  function selIds() { return [...selSet].filter(movable); }
  function setSelSet(ids) {
    selSet = new Set((ids || []).filter(movable));
    if (!selSet.has(sel)) sel = selSet.size ? [...selSet].pop() : "";
    selKf = -1;
  }
  function clearSelSet() { selSet = new Set(); }
  // Resolve a live drag offset into a signed seconds delta for the group.
  function groupDelta(d, e) { return snap(d.at0 + (e.clientX - d.x0) / pps) - d.at0; }
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
  function mkEdit() { return mkSel; }
  function mkHere() {
    // The marker at the playhead (within half a frame, so audio-clock drift doesn't miss it),
    // else the selected one, else null: what the inspector edits.
    const mks = doc.markers || [];
    const tol = 0.5 / fpsOf();
    return mks.find((m) => Math.abs(m.at - play) < tol) || (mkSel ? mks.find((m) => m.id === mkSel) : null) || null;
  }
  function editPoints() {
    // Every point you can jump to: clip edges, In/Out, markers. Shared by arrow-key jumping and
    // by trimming, so they always agree.
    const out = [];
    for (const tr of doc.tracks) for (const it of tr.items) { out.push(it.at); if (it.dur) out.push(it.at + it.dur); }
    if (inOut.in != null) out.push(inOut.in);
    if (inOut.out != null) out.push(inOut.out);
    for (const m of doc.markers || []) out.push(m.at);
    return [...new Set(out.map((x) => Math.round(x * 1e6) / 1e6))]
      .filter((x) => x >= 0 && x <= doc.duration + 1e-6)
      .sort((a, b) => a - b);
  }
  function nearestEdit(t, fwd) {
    const pts = editPoints();
    const i = pts.findIndex((x) => x > t + 1e-6);
    if (fwd) return i < 0 ? null : pts[i];
    // Backward. At the end (nothing is > t) step off the last point; otherwise, if the
    // playhead sits exactly on a point, step to the one before it; else back to the nearest
    // point below t (pts[i-1]).
    if (i < 0) return pts.length > 1 ? pts[pts.length - 2] : null;
    const here = i > 0 && Math.abs(pts[i - 1] - t) < 1e-6;
    return here && i > 1 ? pts[i - 2] : pts[i - 1];
  }
  function marks() {
    const out = [0, doc.duration];
    for (const tr of doc.tracks) for (const it of tr.items) out.push(it.at, it.at + it.dur);
    // In and Out are snap points too, as in Resolve: trims and moves land on the marked range.
    if (inOut.in != null) out.push(inOut.in);
    if (inOut.out != null) out.push(inOut.out);
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
    // An adaptive ruler, like Resolve's: labelled ticks at the first step that keeps labels
    // 72 px apart at this zoom, with unlabelled minor ticks between them.
    const ticks = [];
    const STEPS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
    const step = STEPS.find((s) => s * pps >= 72) || 600;
    const minor = step / (step * pps / 5 >= 10 ? 5 : 2);
    const lab = (t) => (step >= 1 ? `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}` : fmt(t));
    for (let k = 0, t = 0; t <= w + 1e-6; k++, t = k * minor) {
      const major = Math.abs(t / step - Math.round(t / step)) < 1e-6;
      ticks.push(major ? `<i style="left:${t * pps}px">${esc(lab(t))}</i>` : `<b style="left:${t * pps}px"></b>`);
    }
    const mk = (d.markers || []).slice().sort((a, b) => a.at - b.at);
    const it = find(sel);
    const rg = rangeOf();
    const nextNeighbor = it ? nextClip(it) : null;
    const curSpeed = it && it.speed != null ? it.speed : 1;
    const curTf = it && it.transform ? it.transform : { x: 0, y: 0, scale: 1, rotate: 0 };
    const rows = it
      ? [["In", fmt(it.at)], ["Out", fmt(it.at + it.dur)], ["Length", it.dur.toFixed(2) + "s"], ["Source", it.src_in != null ? fmt(it.src_in) + " – " + fmt(it.src_out) : "—"]]
      : [];
    root.innerHTML = `
      <div class="tl ${folded ? "tl-collapsed" : ""}" style="--lab:${LAB}px">
        <div class="tl-top">
          <b>Edit</b>
          <span class="tl-pill">v${esc(d.version)}</span>${d.tracks.some((t) => t.solo) ? `<span class="tl-pill solo" title="Only soloed tracks play, in the preview and in the render">Solo</span>` : ""}
          <span class="tl-clock" title="Timecode HH:MM:SS:FF at ${esc(fpsOf().toFixed(2))} fps">${esc(tc(play))} / ${esc(tc(w))}</span><span class="tl-pill tl-rate" hidden></span>${rg ? `<span class="tl-pill tl-rngpill" title="In ${esc(tc(rg[0]))} · Out ${esc(tc(rg[1]))} · / plays it · Alt+X clears">In–Out ${esc(tc(rg[1] - rg[0]))}</span>` : ""}
          <span class="tl-status">${esc(msg || "Drag an edge to trim. S splits at the playhead.")}${renderOut ? " <a class=\"tl-dl\" href=\"" + esc(renderOut.url) + "\" download>Save " + esc(renderOut.name) + "</a>" : ""}</span>
          <button type="button" data-act="play">${playing ? "Pause" : "Play"}</button>
          <button type="button" data-act="undo">Undo</button>
          <button type="button" data-act="redo">Redo</button>
          <button type="button" class="tl-go" data-act="render" title="${rg ? "Render the In–Out range only (Alt+X clears the marks)" : "Render the whole cut"}">${rg ? "Render range" : "Render"}</button>
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
            ${mkSection(mkHere())}
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
            <div class="tl-ruler" style="width:${width - LAB}px">${rg ? `<span class="tl-rng" style="left:${rg[0] * pps}px;width:${(rg[1] - rg[0]) * pps}px"></span>` : ""}${ticks.join("")}${inOut.in != null && rg ? `<span class="tl-mk in" style="left:${rg[0] * pps}px" title="In ${esc(tc(rg[0]))}"></span>` : ""}${inOut.out != null && rg ? `<span class="tl-mk out" style="left:${rg[1] * pps}px" title="Out ${esc(tc(rg[1]))}"></span>` : ""}</div>
            <div class="tl-stack" style="width:${width}px">
              <div class="tl-play" style="left:${LAB + play * pps}px"></div>
              <div class="tl-mlayer">${mk.map((m, i) => `<span class="tl-mk${m.at >= play - 1e-9 && m.at <= play + 1e-9 ? " at" : ""}" style="left:${(m.at * pps).toFixed(1)}px${m.color && m.color !== "blue" ? ";--mc:var(--mk-" + esc(m.color) + ")" : ""}" data-mk="${esc(m.id)}" title="${esc((m.label || "Marker") + " · " + tc(m.at) + " · click to go, double-click to rename")}"><b>${i + 1}</b><em data-mkcolor="${esc(m.color || "blue")}"></em></span>`).join("")}</div>
              ${rg ? `<div class="tl-rngv" style="left:${LAB + rg[0] * pps}px;width:${(rg[1] - rg[0]) * pps}px"></div>` : ""}
              ${d.tracks.map((tr) => `<div class="tl-trk${isAudio(tr) && !audible(tr) ? " quiet" : ""}" data-trk="${esc(tr.id)}"${trkH[tr.id] ? ` style="--row:${trkH[tr.id]}px` : ""}><span class="tl-lab"><span class="tl-name">${esc(tr.id)} ${esc(tr.role)}</span>${isAudio(tr) ? `<span class="tl-mix"><button type="button" class="tl-m${tr.mute ? " on" : ""}" data-mute="${esc(tr.id)}" title="Mute ${esc(tr.id)}">M</button><button type="button" class="tl-s${tr.solo ? " on" : ""}" data-solo="${esc(tr.id)}" title="Solo ${esc(tr.id)}: only soloed tracks play">S</button><button type="button" class="tl-g" data-gain="${esc(tr.id)}" title="${esc(tr.id)} gain · drag up or down, scroll, double-click for 0 dB">${esc(fmtDb(tr.gain))}</button></span><i class="tl-vu" data-vu="${esc(tr.id)}" title="${esc(tr.id)} level (after the fader)"><b></b></i>` : ""}<i class="tl-rz" data-rz="${esc(tr.id)}" title="Drag to resize ${esc(tr.id)} · double-click to reset"></i></span><div class="tl-lane" data-lane>
                ${tr.items.map((c) => `<div class="tl-clip ${c.type}${c.media && (tr.role === "voice" || tr.role === "music") ? " aud" : ""}${c.id === sel ? " on" : ""}${selSet.has(c.id) ? " sel" : ""}" data-id="${esc(c.id)}" data-at="${c.at}" data-dur="${c.dur}" style="left:${c.at * pps}px;width:${Math.max(c.dur * pps, 2)}px" title="${esc(c.label)}">${wave(tr, c)}${band(tr, c)}${c.dur * pps > 42 ? esc(c.label) : ""}${(c.keyframes || []).map((k, ki) => `<i class="tl-kf${c.id === sel && ki === selKf ? " on" : ""}" data-kfidx="${ki}" style="left:${k.at * pps}px" title="Keyframe ${ki + 1} at ${k.at.toFixed(1)}s · scale ${k.scale.toFixed(2)}× · click to select"></i>`).join("")}<i class="tl-h a" data-edge="start" data-id="${esc(c.id)}"></i><i class="tl-h b" data-edge="end" data-id="${esc(c.id)}"></i></div>`).join("")}
                ${tr.items.filter((c) => c.type === "transition").map((c) => `<button type="button" class="tl-xf" data-xf="${esc(c.id)}" data-between="${esc((c.between || []).join(","))}" data-dur="${c.dur}" style="left:${c.at * pps}px" title="Dissolve ${esc(c.dur.toFixed(1))}s — click to remove"><i>◐</i>${esc(c.dur.toFixed(1))}s</button>`).join("")}
              </div></div>`).join("")}
              <div class="tl-marq" hidden></div>
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
    root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act, b)));
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
    sc.addEventListener("wheel", (e) => {
      // Scroll over a track's dB readout: 1 dB per notch, committed once the wheel rests,
      // so one gesture is one undo step rather than twenty.
      const gEl = e.target.closest("[data-gain]");
      if (!gEl) return;
      e.preventDefault();
      const tid = gEl.dataset.gain;
      const tr = doc.tracks.find((t) => t.id === tid);
      if (!tr) return;
      if (!wheelGain || wheelGain.id !== tid) {
        const db0 = toDb(tr.gain == null ? 1 : tr.gain);
        wheelGain = { id: tid, db: Number.isFinite(db0) ? db0 : DB_FLOOR - 1 };
      }
      wheelGain.db = Math.min(12, Math.max(DB_FLOOR - 1, wheelGain.db + (e.deltaY < 0 ? 1 : -1)));
      const g = Math.round(fromDb(wheelGain.db) * 1000) / 1000;
      gEl.textContent = fmtDb(g);
      clearTimeout(wheelT);
      wheelT = setTimeout(() => { const w = wheelGain; wheelGain = null; commit({ op: "track", track: w.id, gain: g }); }, 350);
    }, { passive: false });
    sc.addEventListener("pointermove", movePtr);
    sc.addEventListener("pointerup", up);
    // The preview must follow its box whatever changed it: window, split drag, Hide, a
    // taller track. A window resize event alone misses most of those.
    if (viewRo) viewRo.disconnect();
    const view = root.querySelector(".tl-view");
    if (view && window.ResizeObserver) {
      viewRo = new ResizeObserver(() => requestAnimationFrame(() => { sizeFrame(); fitTracks(); }));
      viewRo.observe(view);
      viewRo.observe(sc);
    }
  }

  function head() {
    const line = root && root.querySelector(".tl-play");
    if (!line) return;
    line.style.left = LAB + play * pps + "px";
    const clock = root.querySelector(".tl-clock");
    const big = root.querySelector(".tl-frame .big");
    const bar = root.querySelector(".tl-bar");
    if (clock) clock.textContent = tc(play) + " / " + tc(doc.duration);
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
    if (mix) mix.unlock(); // any click is a gesture: wake the sound output before Play is pressed
    const ms = e.target.closest("[data-mute],[data-solo]");
    if (ms) {
      // Toggle on press (pointer capture would retarget a click). One undoable step.
      const tid = ms.dataset.mute || ms.dataset.solo;
      const tr = doc.tracks.find((t) => t.id === tid);
      if (!tr) return;
      const body = { op: "track", track: tid };
      if (ms.dataset.mute) body.mute = !tr.mute; else body.solo = !tr.solo;
      commit(body);
      return;
    }
    const gEl = e.target.closest("[data-gain]");
    if (gEl) {
      const tid = gEl.dataset.gain;
      const tr = doc.tracks.find((t) => t.id === tid);
      if (!tr) return;
      const now = performance.now();
      if (lastRz.id === "g:" + tid && now - lastRz.t < 400) {
        lastRz = { id: "", t: 0 };
        commit({ op: "track", track: tid, gain: 1 });
        return;
      }
      lastRz = { id: "g:" + tid, t: now };
      const db0 = toDb(tr.gain == null ? 1 : tr.gain);
      drag = { kind: "gain", id: tid, el: gEl, db0: Number.isFinite(db0) ? db0 : DB_FLOOR, y0: e.clientY, gNow: null };
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* see kf */ }
      return;
    }
    const rzEl = e.target.closest("[data-rz]");
    if (rzEl) {
      // Track height: drag the header's bottom edge, the way Resolve does. Pure view state.
      // Double-click resets. It is detected here, not with a dblclick listener: pointer capture
      // retargets click/dblclick to the scroll box, so the handle never sees them.
      const now = performance.now();
      if (lastRz.id === rzEl.dataset.rz && now - lastRz.t < 400) {
        lastRz = { id: "", t: 0 };
        delete trkH[rzEl.dataset.rz];
        saveTrkH();
        paint();
        return;
      }
      lastRz = { id: rzEl.dataset.rz, t: now };
      const row = rzEl.closest("[data-trk]");
      drag = { kind: "rz", id: rzEl.dataset.rz, row, h0: row.getBoundingClientRect().height, y0: e.clientY };
      rzEl.classList.add("on");
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* see kf */ }
      return;
    }
    stop();
    const mkEl = e.target.closest("[data-mk]");
    if (mkEl) {
      // A click goes to the marker; a second click within 400 ms opens its name in the
      // inspector. Detected here, not with a dblclick listener: pointer capture retargets
      // click/dblclick to the scroll box (same reason as the resize handle).
      // A marker only owns its own badge (b) and line (:after); everywhere else the layer is
      // pointer-transparent, so a click on the lane behind it still seeks.
      e.stopPropagation();
      const id = mkEl.dataset.mk;
      const m = (doc.markers || []).find((x) => x.id === id);
      const now = performance.now();
      const again = lastMk.id === id && now - lastMk.t < 400;
      lastMk = again ? { id: "", t: 0 } : { id, t: now };
      sel = null;
      mkSel = id; // a click always selects the marker; the rename box follows
      if (m) { play = m.at; head(); }
      // Selecting a marker changes what the inspector shows (its rename box), so repaint it.
      // head() only moves the playhead; the inspector rows come from paint().
      paint();
      // A second click within 400 ms opens the name box (as Resolve's double-click renames).
      if (again) {
        const inp = root.querySelector("[data-mkname]");
        if (inp) { inp.focus(); inp.select(); }
      }
      return;
    }
    const gkEl = e.target.closest("[data-gk]");
    const glEl = gkEl ? null : e.target.closest("[data-gline]");
    if (gkEl || glEl) {
      // The volume line. Alt-click the line adds a key at the level already there (so adding
      // one never changes the sound); Alt-click a key removes it; otherwise drag.
      const clipEl = (gkEl || glEl).closest("[data-id]");
      const it = clipEl && find(clipEl.dataset.id);
      if (!it) return;
      sel = it.id;
      const box = clipEl.querySelector(".tl-band").getBoundingClientRect();
      const keys = it.gain_keys ? it.gain_keys.map((k) => ({ ...k })) : null;
      const vol = it.volume == null ? 1 : it.volume;
      if (e.altKey && gkEl) {
        const left = keys.filter((_, i) => i !== Number(gkEl.dataset.gk));
        commit({ op: "gainkeys", id: it.id, keys: left.length ? left : null });
        return;
      }
      if (e.altKey && glEl) {
        const f = fpsOf();
        const u = Math.max(0, Math.min(it.dur, Math.round(((e.clientX - box.left) / pps) * f) / f));
        const add = { at: u, gain: keys ? envAt(keys, u) : 1 };
        const next = (keys || []).filter((k) => Math.abs(k.at - u) > 1e-6).concat([add]).sort((a, b) => a.at - b.at);
        commit({ op: "gainkeys", id: it.id, keys: next });
        return;
      }
      drag = { kind: gkEl ? "gk" : "gline", id: it.id, idx: gkEl ? Number(gkEl.dataset.gk) : -1, clipEl, box,
        keys, keys0: keys ? keys.map((k) => ({ ...k })) : null, vol, vol0: vol, x0: e.clientX, y0: e.clientY, moved: false };
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* see kf */ }
      return;
    }
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
    } else if (clip && clip.dataset.at && e.altKey && (find(clip.dataset.id) || {}).type === "clip") {
      // Alt/Option-drag slips (Final Cut's slip, Resolve's trim-mode drag on a clip body):
      // the clip stays put, its source window slides under it. Limits come from the media,
      // so the drag stops at either end instead of failing on release.
      const it = find(clip.dataset.id);
      sel = it.id;
      selKf = -1;
      selSet = new Set([sel]);
      paintSel();
      const sp = it.speed || 1;
      drag = { kind: "slip", id: it.id, x0: e.clientX, el: clip, by: 0, moved: false,
        lo: -(it.src_in || 0) / sp,
        hi: it.media_dur != null ? (it.media_dur - it.src_out) / sp : Infinity,
        src_in: it.src_in || 0, src_out: it.src_out || 0, sp };
      clip.classList.add("slipping");
    } else if (clip && clip.dataset.at) {
      sel = clip.dataset.id;
      selKf = -1;
      // Shift+click grows or shrinks the group (Resolve / Final Cut); a plain click starts
      // fresh. The whole group then drags together below in movePtr.
      if (e.shiftKey) {
        if (selSet.has(sel)) selSet.delete(sel); else selSet.add(sel);
        if (!selSet.size) selSet.add(sel);  // never leave the group empty on a click
      } else if (!selSet.has(sel)) {
        selSet = new Set([sel]);
      }
      paintSel();
      drag = { kind: "move", id: sel, at0: Number(clip.dataset.at), x0: e.clientX, moved: false, group: [...selSet] };
    } else if (e.target.closest("[data-lane]")) {
      // A drag on empty lane is a marquee selection; a plain click seeks. Only starts a
      // marquee once it moves, so a click never leaves a phantom box behind.
      const box = e.currentTarget.closest(".tl-stack").getBoundingClientRect();
      drag = { kind: "marq", x0: e.clientX, y0: e.clientY, bx: box.left, by: box.top, bw: box.width, bh: box.height,
        at0: snap(Math.max(0, Math.min(doc.duration, xToTime(e)))), group: e.shiftKey ? [...selSet] : null, moved: false };
      if (!e.shiftKey) { play = snap(Math.max(0, Math.min(doc.duration, xToTime(e)))); head(); }
    } else return;
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  // Repaint just the selection rings without rebuilding the DOM (a drag is in flight and a
  // full paint() would detach the pointer listeners mid-gesture).
  function paintSel() {
    if (!root) return;
    root.querySelectorAll(".tl-clip").forEach((n) => {
      const on = selSet.has(n.dataset.id);
      n.classList.toggle("sel", on);
    });
  }

  function movePtr(e) {
    if (!drag) return;
    if (drag.kind === "gk" || drag.kind === "gline") {
      const it = find(drag.id);
      if (!it) return;
      drag.moved = drag.moved || Math.abs(e.clientX - drag.x0) > 2 || Math.abs(e.clientY - drag.y0) > 2;
      if (!drag.moved) return;
      let readout;
      if (drag.kind === "gk") {
        // A key moves in time (on the frame grid, between its neighbours) and in level.
        const k = drag.keys, i = drag.idx, f = fpsOf();
        const lo = i > 0 ? k[i - 1].at + 1 / f : 0, hi = i < k.length - 1 ? k[i + 1].at - 1 / f : it.dur;
        const u = Math.max(lo, Math.min(hi, Math.round(((e.clientX - drag.box.left) / pps) * f) / f));
        const level = yLvl(Math.max(0, Math.min(1, (e.clientY - drag.box.top) / drag.box.height)));
        k[i] = { at: u, gain: drag.vol > 0 ? Math.min(4, level / drag.vol) : level };
        readout = `Volume key ${fmtDb(level)} dB at ${tc(it.at + u)}`;
      } else {
        // The line itself: the clip's level with no keys (Final Cut), every key together with them.
        const dDb = -((e.clientY - drag.y0) / drag.box.height) * BAND_SPAN;
        const m = Math.pow(10, dDb / 20);
        if (drag.keys0) {
          drag.keys = drag.keys0.map((k) => ({ at: k.at, gain: Math.min(4, k.gain * m) }));
          readout = `${dDb >= 0 ? "+" : "−"}${Math.abs(dDb).toFixed(1)} dB on every volume key`;
        } else {
          drag.vol = Math.max(0, Math.min(4, drag.vol0 * m));
          readout = `Clip level ${fmtDb(drag.vol)} dB`;
        }
      }
      const bandEl = drag.clipEl.querySelector(".tl-band");
      if (bandEl) bandEl.innerHTML = bandHtml(it, drag.keys, drag.vol);
      const st = root.querySelector(".tl-status");
      if (st) st.textContent = readout;
      return;
    }
    if (drag.kind === "gain") {
      // A fader: 4 px per dB, up is louder. Snaps to 0 dB within half a dB, like a detent.
      let db = drag.db0 - (e.clientY - drag.y0) / 4;
      db = Math.min(12, db);
      if (Math.abs(db) < 0.5) db = 0;
      const g = fromDb(db);
      drag.gNow = Math.round(g * 1000) / 1000;
      drag.el.textContent = fmtDb(drag.gNow);
      return;
    }
    if (drag.kind === "rz") {
      const h = Math.round(Math.max(TRK_MIN, Math.min(TRK_MAX, drag.h0 + (e.clientY - drag.y0))));
      drag.row.style.setProperty("--row", h + "px");
      drag.hNow = h;
      return;
    }
    if (drag.kind === "seek") {
      play = snap(Math.max(0, Math.min(doc.duration, xToTime(e))));
      head();
      return;
    }
    if (drag.kind === "marq") {
      // Once it actually moves, draw the box and select every clip it covers. A tiny nudge
      // (a sloppy click) is treated as no marquee, so seeking still wins.
      if (Math.abs(e.clientX - drag.x0) < 4 && Math.abs(e.clientY - drag.y0) < 4) return;
      drag.moved = true;
      const mq = root.querySelector(".tl-marq");
      const x1 = Math.min(drag.x0, e.clientX), x2 = Math.max(drag.x0, e.clientX);
      const y1 = Math.min(drag.y0, e.clientY), y2 = Math.max(drag.y0, e.clientY);
      if (mq) {
        mq.hidden = false;
        mq.style.left = (x1 - drag.bx) + "px";
        mq.style.top = (y1 - drag.by) + "px";
        mq.style.width = (x2 - x1) + "px";
        mq.style.height = (y2 - y1) + "px";
      }
      // Select clips whose box intersects the marquee, in stack coordinates. Shift adds to
      // the prior group; a plain marquee replaces it.
      const hits = new Set(drag.group || []);
      root.querySelectorAll(".tl-clip[data-id]").forEach((n) => {
        const r = n.getBoundingClientRect();
        if (r.right >= x1 && r.left <= x2 && r.bottom >= y1 && r.top <= y2 && movable(n.dataset.id)) hits.add(n.dataset.id);
      });
      setSelSet([...hits]);
      paintSel();
      return;
    }
    if (drag.kind === "slip") {
      // Timeline seconds on the frame grid, clamped to the media. Only the readout and the
      // waveform move live; the clip's box stays where it is, which is the point of a slip.
      const f = fpsOf();
      const raw = (e.clientX - drag.x0) / pps;
      drag.by = Math.max(drag.lo, Math.min(drag.hi, Math.round(raw * f) / f));
      drag.moved = drag.moved || Math.abs(e.clientX - drag.x0) > 3;
      const w = drag.el.querySelector(".tl-wave");
      if (w) w.style.transform = `translateX(${(-drag.by * pps).toFixed(1)}px)`;
      const st = root.querySelector(".tl-status");
      const a = drag.src_in + drag.by * drag.sp, b = drag.src_out + drag.by * drag.sp;
      if (st) st.textContent = `Slip ${drag.by >= 0 ? "+" : "−"}${tc(Math.abs(drag.by))} · source ${tc(a)} – ${tc(b)}${drag.by === drag.lo || drag.by === drag.hi ? " · end of media" : ""}`;
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
      drag.atNow = t;
      drag.moved = Math.abs(e.clientX - drag.x0) > 3;
      // Live-position every clip in the group; the primary one is `el`, the rest are its
      // band-mates. A full paint() here would detach the pointer listeners mid-drag.
      const delta = t - drag.at0;
      for (const gid of (drag.group || [drag.id])) {
        if (gid === drag.id) continue;
        const ge = root.querySelector(`[data-id="${gid}"]`);
        const git = find(gid);
        if (ge && git) ge.style.left = Math.max(0, git.at + delta) * pps + "px";
      }
      if (el) el.style.left = t * pps + "px";
    }
  }

  async function up() {
    const d = drag;
    drag = null;
    if (d && (d.kind === "gk" || d.kind === "gline")) {
      if (!d.moved) { paint(); return; }
      if (d.kind === "gline" && !d.keys0) await commit({ op: "volume", id: d.id, volume: Math.round(d.vol * 1000) / 1000 });
      else await commit({ op: "gainkeys", id: d.id, keys: d.keys.map((k) => ({ at: Math.round(k.at * 1e4) / 1e4, gain: Math.round(k.gain * 1000) / 1000 })) });
      return;
    }
    if (d && d.kind === "gain") {
      if (d.gNow != null) await commit({ op: "track", track: d.id, gain: d.gNow });
      return;
    }
    if (d && d.kind === "rz") {
      // A click that didn't move must leave the DOM alone, or the second click of a
      // double-click lands on a rebuilt node and the reset never fires.
      if (d.hNow == null || d.hNow === Math.round(d.h0)) { root.querySelectorAll(".tl-rz.on").forEach((n) => n.classList.remove("on")); return; }
      trkH[d.id] = d.hNow;
      saveTrkH();
      paint();
      return;
    }
    if (d && d.kind === "slip") {
      d.el.classList.remove("slipping");
      if (!d.moved || Math.abs(d.by) < 1e-9) { paint(); return; }
      await commit({ op: "slip", item: d.id, by: Math.round(d.by * 1e6) / 1e6 });
      return;
    }
    if (d && d.kind === "marq") {
      const mq = root.querySelector(".tl-marq");
      if (mq) mq.hidden = true;
      if (!d.moved) return;  // a click already seeked in down(); leave selection alone
      return;
    }
    // A plain click on a clip (no drag) changes the selection: repaint so the ring and the
    // inspector follow. This must run before the atNow check, which a click never sets.
    if (d && d.kind === "move" && !d.moved) { paint(); return; }
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
      : d.kind === "move" && d.group && d.group.length > 1
        ? { op: "move_items", ids: d.group, by: d.atNow - d.at0 }
        : { op: "move", item: d.id, at: d.atNow };
    await commit(body);
  }

  // After an edit lands: fetch any new sound, and if the mix is playing keep it in step. A
  // mixer move (mute/solo/gain) glides live; anything else re-schedules from where we are.
  function afterEdit(body) {
    if (!mix || !doc) return;
    mix.load(doc, pid);
    if (!mixing) return;
    if (body && body.op === "track") mix.mixer(doc);
    else { const p = mix.now(); mix.start(doc, p == null ? play : p); }
  }

  async function commit(body) {
    const deleting = body && (body.op === "delete_items" || (body.op === "lift" && body.ripple !== undefined));
    try {
      const data = await api(body);
      doc = data.project;
      afterEdit(body);
      msg = data.project.summary || "Saved.";
      // A group edit drops clips that no longer exist from the group, then keeps the
      // inspector pointed at something real. A plain delete clears the group outright.
      if (deleting) clearSelSet();
      else if (selSet.size) {
        for (const id of [...selSet]) if (!find(id)) selSet.delete(id);
        if (!selSet.has(sel) && selSet.size) sel = [...selSet].pop();
      }
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
    const h = sc.clientHeight;
    // A box with no height yet (just re-divided, or mid-teardown) would compute a
    // nonsense row size and hide tracks. Keep the last sane value instead.
    if (h < 40) {
      const had = Number(shell.style.getPropertyValue("--trk").replace("px", ""));
      if (Number.isFinite(had) && had >= 18) return;
      shell.style.setProperty("--trk", "22px");
      return;
    }
    // Tracks the person sized keep their height; the rest share what's left of the panel.
    const fixed = doc.tracks.reduce((s, t) => s + (trkH[t.id] || 0), 0);
    const free = doc.tracks.filter((t) => !trkH[t.id]).length;
    if (!free) return;
    const want = Math.floor((h - 22 - fixed) / free); // the ruler
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
    if (mix) mix.stop();
    mixing = false;
    rate = 1;
    stopAt = null;
    showRate();
    meters(true);
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
  // The preview plays the picture clip's own sound, which in an imported cut is the same
  // recording as the voice track. So follow that voice clip's mixer state: muted or out of
  // solo -> silent; otherwise its clip volume x track gain (a <video> can't go above 1).
  // A true multitrack preview mix needs Web Audio; until then this is honest for that case.
  function previewMix(v) {
    if (!v || !doc) return;
    let level = null;
    for (const tr of doc.tracks) {
      if (tr.role !== "voice") continue;
      const it = tr.items.find((i) => i.file === v.dataset.file && play >= i.at - 0.02 && play < i.at + i.dur);
      if (it) { level = audible(tr) ? (it.volume == null ? 1 : it.volume) * (tr.gain == null ? 1 : tr.gain) : 0; break; }
    }
    if (level == null) { v.muted = false; v.volume = 1; return; }
    v.muted = level <= 0;
    v.volume = Math.max(0, Math.min(1, level));
  }
  function bindFilm(v) {
    v.ontimeupdate = () => {
      if (!playing || !doc || mixing) return;
      previewMix(v);
      const piece = pieceAt(v.dataset.file, v.currentTime);
      if (piece) {
        play = piece.at + (v.currentTime - (piece.src_in || 0));
        if (stopAt != null && play >= stopAt) { play = stopAt; stop(); paint(); return; }
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
    previewMix(v);
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
  // Mix mode: the picture follows the audio clock. Re-seek only past 150 ms of drift (a
  // <video> seek costs a frame or two, so chasing every millisecond would stutter).
  function syncPicture() {
    const v = root && root.querySelector(".tl-vid");
    if (!v) return;
    const img = root.querySelector(".tl-pic");
    const it = mainClip(play);
    if (!it || !it.file) {
      if (!v.paused) v.pause();
      v.hidden = true;
      if (img) img.hidden = true;
      return;
    }
    v.hidden = false;
    v.muted = true; // the sound comes from the mix (or the shuttle is silent)
    if (img) img.hidden = true;
    const sp = it.speed || 1;
    const want = () => { const c = mainClip(play) || it; return (c.src_in || 0) + Math.max(0, play - c.at) * (c.speed || 1); };
    if (v.dataset.file !== it.file) {
      v.dataset.file = it.file;
      v.src = "/api/editor/" + encodeURIComponent(pid) + "/media/" + encodeURIComponent(it.file);
      v.addEventListener("loadedmetadata", () => { v.currentTime = want(); }, { once: true });
      return;
    }
    if (rate < 0) {
      // A <video> can't play backwards, so a reverse shuttle steps it: paused, one seek every
      // 80 ms (about 12 pictures a second), which is what a reverse scrub looks like anyway.
      if (!v.paused) v.pause();
      const now = performance.now();
      if (v.readyState >= 1 && now - lastSeek > 80) { lastSeek = now; v.currentTime = want(); }
      return;
    }
    const r = Math.min(16, sp * rate);
    if (v.readyState >= 1 && Math.abs(v.currentTime - want()) > 0.15 * Math.max(1, rate)) v.currentTime = want();
    if (v.playbackRate !== r) v.playbackRate = r;
    if (v.paused) { const pr = v.play(); if (pr && pr.catch) pr.catch(() => {}); }
  }

  // Post-fader track meters (Resolve style): green to -12, amber to -3, red above.
  const hotUntil = {};
  function meters(reset) {
    if (!root) return;
    const lv = reset || !mix ? {} : mix.levels();
    const now = performance.now();
    root.querySelectorAll("[data-vu]").forEach((el) => {
      const db = lv[el.dataset.vu];
      const f = Number.isFinite(db) ? Math.max(0, Math.min(1, (db + 60) / 60)) : 0;
      el.firstElementChild.style.clipPath = `inset(${((1 - f) * 100).toFixed(1)}% 0 0 0)`;
      if (Number.isFinite(db) && db > -0.5) hotUntil[el.dataset.vu] = now + 1500;
      el.classList.toggle("hot", !reset && (hotUntil[el.dataset.vu] || 0) > now);
    });
  }

  function loop(t) {
    if (!playing) return;
    if (mixing) {
      const w = mix.waiting();
      if (w > 2000) {
        // No sound output answered. Don't freeze: fall back to the picture's own sound.
        mix.stop();
        mixing = false;
        msg = "The sound output didn't start; playing the picture's own sound.";
        paint();
        if (!startFilm()) { lastT = 0; raf = requestAnimationFrame(loop); }
        return;
      }
      const st = root.querySelector(".tl-status");
      if (w > 250 && st) st.textContent = "Waking the sound output…";
      else if (st && st.textContent === "Waking the sound output…") st.textContent = msg || "";
      const p = mix.now();
      if (p != null) play = p;
    } else if (lastT) play += ((t - lastT) / 1000) * rate;
    lastT = t;
    if (play >= doc.duration) { play = doc.duration; stop(); paint(); return; }
    if (rate < 0 && play <= 0) { play = 0; stop(); paint(); return; }
    if (stopAt != null && rate > 0 && play >= stopAt - 1e-6) { play = stopAt; stop(); paint(); return; }
    head();
    if (mixing || rate !== 1) syncPicture();
    if (mixing) meters(false);
    const sc = root.querySelector(".tl-scroll");
    const x = LAB + play * pps;
    if (sc && (x < sc.scrollLeft + LAB || x > sc.scrollLeft + sc.clientWidth - 24)) sc.scrollLeft = Math.max(0, x - sc.clientWidth * 0.4);
    raf = requestAnimationFrame(loop);
  }

  // Start playback at a signed speed. Must run inside the gesture (click or key) that asked
  // for it: browsers only start audio, and an unmuted <video>, from one.
  function transport(r) {
    stop();
    rate = r;
    if (r > 0 && play >= doc.duration - 0.01) play = 0;
    if (r < 0 && play <= 0.01) play = doc.duration;
    playing = true;
    if ((r === 1 || r === 2) && mix && mix.unlock() && mix.ready(doc)) {
      mixing = true;
      mix.start(doc, play, r);
      paint();
      showRate();
      syncPicture();
      lastT = 0;
      raf = requestAnimationFrame(loop);
      return;
    }
    if (r === 1) {
      if (mix) msg = "Sound is still loading; playing the picture's own sound for now.";
      paint();
      if (!startFilm()) raf = requestAnimationFrame(loop);
      return;
    }
    // A silent shuttle (4x / 8x, or backwards): the wall clock drives, the picture follows.
    paint();
    showRate();
    syncPicture();
    lastT = 0;
    raf = requestAnimationFrame(loop);
  }

  async function act(name, el) {
    if (name === "play") {
      if (playing) { stop(); paint(); return; }
      transport(1);
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
        const rg = rangeOf();
        const res = await api(rg ? { op: "render", in: rg[0], out: rg[1] } : { op: "render" });
        doc = res.project;
        const r = res.render || {};
        const what = r.range ? `the range ${tc(r.range[0])}–${tc(r.range[1])}` : r.name || "file";
        msg = `Rendered ${what} — ${r.size ? r.size[0] + "×" + r.size[1] : ""} ${r.duration || ""}s`;
        // Cache-bust: the file keeps one name, so a browser could hand back the previous render.
        renderOut = { name: r.name || "", url: "/api/editor/" + encodeURIComponent(pid) + "/render?v=" + Date.now() };
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
      if (mixing) return; // afterEdit re-scheduled the mix; the loop keeps the picture in step
      const v = root.querySelector(".tl-vid");
      if (v && !v.paused) bindFilm(v);
      else startFilm();
      return;
    }
    stop();
    if (name === "mk-color") {
      // The clicked element IS the swatch (it carries data-color).
      if (!mkSel || !el || !el.dataset.color) return;
      await commit({ op: "marker_set", id: mkSel, color: el.dataset.color });
      return;
    }
    if (name === "mk-del") { if (mkSel) await commit({ op: "marker_del", id: mkSel }); return; }
    if (name === "mk-apply") {
      const row = el && el.closest(".tl-row");
      const box = row && row.querySelector("[data-mkname]");
      if (!mkSel || !box) return;
      await commit({ op: "marker_set", id: mkSel, label: box.value });
      return;
    }
    if (name === "undo" || name === "redo" || name === "reset") { await commit({ op: name === "reset" ? "reset" : name }); return; }
    const target = name === "split" ? under() : find(sel);
    if (!target) { msg = name === "split" ? "Move the playhead inside a clip." : "Select a clip first."; paint(); return; }
    sel = target.id;
    if (name === "split") await commit({ op: "split", item: target.id, at: play });
    // A group delete: one step for the whole selection (Delete/Backspace, or the Lift
    // button). A single selection keeps the plain lift, so history reads the same as before.
    else if (name === "lift" && selIds().length > 1) await commit({ op: "delete_items", ids: selIds(), ripple });
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
    // In/Out (I / O), as in Resolve and Premiere. e.code, because Alt+I types "ˆ" on a Mac.
    const code = e.code || "";
    if (code === "KeyI" || code === "KeyO") {
      e.preventDefault();
      const which = code === "KeyI" ? "in" : "out";
      if (e.altKey) { inOut[which] = null; saveMarks(); paint(); return; } // Alt+I / Alt+O clear one
      if (e.shiftKey) { // Shift+I / Shift+O go to the mark
        if (inOut[which] == null) return;
        if (playing) { stop(); paint(); }
        play = Math.min(inOut[which], doc.duration);
        head();
        return;
      }
      setMark(which, play);
      return;
    }
    if (code === "KeyX" && e.altKey) { e.preventDefault(); inOut = { in: null, out: null }; saveMarks(); paint(); return; }
    if (code === "Comma" || code === "Period") {
      // , and . nudge the selection a frame (Shift: a second), as in Resolve and Final Cut.
      // With Alt they slip the selected clip instead. e.code, because Alt+, types "≤" on a Mac.
      e.preventDefault();
      const f = fpsOf();
      const by = (code === "Period" ? 1 : -1) * (e.shiftKey ? Math.round(f) : 1) / f;
      if (e.altKey) {
        const it = find(sel);
        if (!it || it.type !== "clip") { msg = "Select a clip to slip."; paint(); return; }
        commit({ op: "slip", item: it.id, by: Math.round(by * 1e6) / 1e6 });
        return;
      }
      const ids = selIds().length ? selIds() : (movable(sel) ? [sel] : []);
      if (!ids.length) { msg = "Select a clip to nudge."; paint(); return; }
      // Always relative, even for one clip: the engine snaps the offset to whole frames in
      // ticks, so a nudge and its opposite land back exactly (absolute seconds here drift).
      commit({ op: "move_items", ids, by: Math.round(by * 1e6) / 1e6 });
      return;
    }
    if (k === "/") {
      // Play In to Out, then stop at Out.
      e.preventDefault();
      const rg = rangeOf();
      if (!rg) { msg = "Mark an In (I) and an Out (O) first, then / plays between them."; paint(); return; }
      play = rg[0];
      transport(1);
      stopAt = rg[1];
      return;
    }
    // Markers (Resolve: M drops one, Shift+M renames the last) and jumping.
    const mks = (doc.markers || []).slice().sort((a, b) => a.at - b.at);
    if (k === "m") {
      e.preventDefault();
      if (e.shiftKey) {
        const near = mks.filter((m) => Math.abs(m.at - play) < 0.001)[0];
        if (!near) { msg = "No marker at the playhead to name."; paint(); return; }
        mkEdit = near.id; mkName = near.label; sel = null; paint();
        const inp = root.querySelector("[data-mkname]");
        if (inp) { inp.focus(); inp.select(); }
        return;
      }
      // M at a marker deletes it (Resolve), otherwise drops one named "Marker N".
      const here = mks.findIndex((m) => Math.abs(m.at - play) < 1 / fpsOf() / 2);
      if (here >= 0) { commit({ op: "marker_del", id: mks[here].id }); return; }
      const n = mks.filter((m) => /^Marker \d+$/.test(m.label)).length + 1;
      commit({ op: "marker", at: Math.round(play * 1e6) / 1e6, label: `Marker ${n}` });
      return;
    }
    if (k === "arrowup" || k === "arrowdown") {
      // Shift+Up/Down: the previous or next marker. Plain: the previous or next edit point
      // (a clip edge, an In/Out mark or a marker), which is Resolve's Up/Down.
      if (e.altKey) return;
      e.preventDefault();
      const pts = editPoints();
      const fwd = k === "arrowdown";
      const near = (t) => pts.filter((x) => (fwd ? x > t + 1e-6 : x < t - 1e-6)).sort((a, b) => (fwd ? a - b : b - a))[0];
      const to = e.shiftKey ? near(play) : nearestEdit(play, fwd);
      if (to == null) return;
      play = Math.max(0, Math.min(doc.duration, to));
      if (playing) { stop(); }
      head();
      return;
    }
    if (k === "j" || k === "l") {
      // J/K/L shuttle, as in Final Cut, Resolve and Premiere: each press of the same key goes
      // faster (1, 2, 4, 8x); the other key turns round at 1x; K stops; K held + J/L steps a frame.
      e.preventDefault();
      if (e.repeat) return;
      const dir = k === "l" ? 1 : -1;
      if (kHeld) { stepFrames(dir); return; }
      const speeds = [1, 2, 4, 8];
      const next = playing && Math.sign(rate) === dir ? dir * speeds[Math.min(speeds.length - 1, speeds.indexOf(Math.abs(rate)) + 1)] : dir;
      transport(next);
      return;
    }
    if (k === "k") {
      e.preventDefault();
      kHeld = true;
      if (!e.repeat && playing) { stop(); paint(); }
      return;
    }
    if (k === " ") act("play");
    else if (k === "s") act("split");
    else if (k === "n") act("snap");
    else if (k === "backspace" || k === "delete") act("lift");
    else if (k === "arrowleft" || k === "arrowright") stepFrames((k === "arrowright" ? 1 : -1) * (e.shiftKey ? Math.round(fpsOf()) : 1)); // a frame; Shift = a second
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
      if (mix) mix.load(doc, pid);
      inOut = loadMarks(pid);
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
    if (viewRo) { viewRo.disconnect(); viewRo = null; }
    document.body.classList.remove("editing");
    root = null;
  }
  document.addEventListener("keydown", onKey);
  document.addEventListener("keyup", (e) => { if (e.key && e.key.toLowerCase() === "k") kHeld = false; });
  window.addEventListener("blur", () => { kHeld = false; });
  window.HSEdit = {
    open, leave,
    // Read-only view of the preview mixer, for checks and support.
    mixState: () => (mix ? { ...mix.state(), mixing, playing, play, rate, marks: { ...inOut }, stopAt, mkSel, levels: mix.levels(), waiting: mix.waiting() } : null),
    // The live audio context, so a check can suspend it to prove the stalled-clock fallback.
    mixContext: () => (mix ? mix.context : null),
  };
})();
