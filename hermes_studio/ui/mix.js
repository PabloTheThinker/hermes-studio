/* Hermes Studio preview mixer.
 *
 * The timeline's sound, mixed live in Web Audio, so what you hear while editing is what the
 * render writes. Every rule mirrors render_timeline.py:
 *   - a clip plays its source span (src_in..src_out) at its speed or ramp (srcAt: the same
 *     time map as timeline.source_offset);
 *   - its level is clip volume x the role weight (voice 1.0, music 0.35 -- render MIX);
 *   - fade_in / fade_out are linear ramps (ffmpeg afade's default curve);
 *   - each audio track is a strip: gain, mute, solo (any solo -> only soloed tracks play);
 *   - a limiter on the master catches stacked peaks (render: alimiter=limit=0.95).
 * The one thing it does not copy is loudnorm (a whole-file broadcast leveler), so the preview's
 * overall loudness can sit below the render's; the balance between tracks is the same.
 *
 * The audio clock is the master: now() is where the playhead is. The editor slaves the picture
 * to it, the way Resolve and Final Cut do, so the playhead moves every frame instead of on the
 * <video>'s coarse timeupdate.
 */
(function () {
  "use strict";

  const MIX = { voice: 1.0, music: 0.35 }; // keep in step with render_timeline.MIX
  const MAX_DECODE_S = 30 * 60; // decoded PCM lives in memory; longer files fall back to <video> sound
  const LEAD = 0.06; // seconds between start() and the first sample, so scheduling never lands late

  function isAudio(tr) { return tr.role === "voice" || tr.role === "music"; }

  // ---- retime: the one time map (timeline.source_offset / item_duration), shared with the page.
  // `into` is seconds into the clip on the TIMELINE; the answer is source seconds from src_in.
  // Constant speed multiplies. A ramp is linear in source time between keys, so its timeline
  // length is the integral of 1/speed (a log) and the inverse is an exponential; outside the
  // keys the end speed holds.
  function rampPts(c) { return Array.isArray(c.speed_keys) && c.speed_keys.length >= 2 ? c.speed_keys : null; }
  // Clip-timeline seconds at each ramp key (where the rate curve has its corners).
  function keyTimes(c) {
    const pts = rampPts(c);
    if (!pts) return [];
    const out = [pts[0][0] / pts[0][1]];
    for (let i = 0; i < pts.length - 1; i++) {
      const [ta, sa] = pts[i], [tb, sb] = pts[i + 1], d = tb - ta;
      const k = d > 0 ? (sb - sa) / d : 0;
      out.push(out[i] + (d <= 0 ? 0 : Math.abs(k) < 1e-12 ? d / sa : (Math.log(sb) - Math.log(sa)) / k));
    }
    return out;
  }
  function srcAt(c, into) {
    if (c.hold) return 0; // a freeze frame shows its one source frame the whole time
    const span = Math.max(0, (c.src_out || 0) - (c.src_in || 0));
    const u = Math.max(0, into);
    const pts = rampPts(c);
    let t;
    if (!pts) t = u * (c.speed || 1);
    else {
      const kt = keyTimes(c);
      if (u < kt[0]) t = u * pts[0][1];
      else {
        t = null;
        for (let i = 0; i < pts.length - 1; i++) {
          const [ta, sa] = pts[i], [tb, sb] = pts[i + 1], d = tb - ta;
          if (d <= 0 || u >= kt[i + 1]) continue;
          const k = (sb - sa) / d, w = u - kt[i];
          t = ta + (Math.abs(k) < 1e-12 ? w * sa : (sa * (Math.exp(k * w) - 1)) / k);
          break;
        }
        if (t == null) t = pts[pts.length - 1][0] + (u - kt[kt.length - 1]) * pts[pts.length - 1][1];
      }
    }
    return Math.max(0, Math.min(span, t));
  }
  // The forward map: source seconds from src_in -> seconds into the clip on the timeline (the
  // integral of 1/speed). The film path reads the <video>'s source time and needs this to place
  // the playhead.
  function tlAt(c, off) {
    const t = Math.max(0, off);
    const pts = rampPts(c);
    if (!pts) return t / (c.speed || 1);
    if (t <= pts[0][0]) return t / pts[0][1];
    let acc = pts[0][0] / pts[0][1];
    for (let i = 0; i < pts.length - 1; i++) {
      const [ta, sa] = pts[i], [tb, sb] = pts[i + 1], d = tb - ta;
      if (d <= 0) continue;
      const k = (sb - sa) / d, hi = Math.min(t, tb);
      if (hi > ta) acc += Math.abs(k) < 1e-12 ? (hi - ta) / sa : (Math.log(sa + k * (hi - ta)) - Math.log(sa)) / k;
      if (t <= tb) return acc;
    }
    return acc + (t - pts[pts.length - 1][0]) / pts[pts.length - 1][1];
  }
  // Playback speed at clip-timeline second `into`.
  function speedAt(c, into) {
    if (c.hold) return 0;
    const pts = rampPts(c);
    if (!pts) return c.speed || 1;
    const t = srcAt(c, into);
    if (t <= pts[0][0]) return pts[0][1];
    for (let i = 0; i < pts.length - 1; i++) {
      const [ta, sa] = pts[i], [tb, sb] = pts[i + 1];
      if (t <= tb) return tb > ta ? sa + ((sb - sa) * (t - ta)) / (tb - ta) : sb;
    }
    return pts[pts.length - 1][1];
  }
  // The SOURCE second shown at clip-timeline second `into`: srcAt is the offset in PLAYED order,
  // so a reversed clip reads it back from its out point (timeline.source_offset, same rule).
  function srcTime(c, into) {
    const p = srcAt(c, into);
    return c.reverse ? Math.max(c.src_in || 0, (c.src_out || 0) - p - 1e-3) : (c.src_in || 0) + p;
  }
  // Timeline length of a clip (the view already sends it; this is the fallback).
  function lenOf(c) {
    if (c.dur != null) return c.dur;
    return Math.max(0, (c.src_out || 0) - (c.src_in || 0)) / (c.speed || 1);
  }
  // The clip's volume envelope at clip-local second u: linear between keys, held outside them
  // (render_timeline._interp_expr, the same rule).
  function envAt(keys, u) {
    if (u <= keys[0].at) return keys[0].gain;
    for (let i = 1; i < keys.length; i++) {
      const a = keys[i - 1], b = keys[i];
      if (u < b.at) return b.at > a.at ? a.gain + (b.gain - a.gain) * (u - a.at) / (b.at - a.at) : a.gain;
    }
    return keys[keys.length - 1].gain;
  }
  function audible(doc, tr) {
    if (!isAudio(tr) || tr.mute || !(tr.gain == null || tr.gain > 0)) return false;
    return !doc.tracks.some((t) => t.solo) || !!tr.solo;
  }

  function create() {
    let ctx = null, master = null;
    const buffers = new Map(); // file -> AudioBuffer | "wait" | null (failed / too long)
    const strips = new Map(); // track id -> { gain, meter, data }
    let sources = [];
    let running = false, t0 = 0, p0 = 0, scope = "", rate = 1;
    let lastClock = -1, lastMove = 0; // the audio clock's last reading, and when it last moved

    function context() {
      if (!ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return null;
        ctx = new AC({ latencyHint: "interactive" });
        const limiter = ctx.createDynamicsCompressor();
        limiter.threshold.value = -0.5;
        limiter.knee.value = 0;
        limiter.ratio.value = 20;
        limiter.attack.value = 0.002;
        limiter.release.value = 0.08;
        master = ctx.createGain();
        master.connect(limiter).connect(ctx.destination);
      }
      return ctx;
    }

    // Call from the click that starts playback: browsers only let audio start inside a gesture.
    function unlock() {
      const c = context();
      if (c && c.state === "suspended") c.resume();
      return !!c;
    }

    function clips(doc) {
      const out = [];
      for (const tr of doc.tracks) {
        if (!isAudio(tr)) continue;
        for (const c of tr.items) if (c.type === "clip" && c.file && c.src_out > c.src_in) out.push([tr, c]);
      }
      return out;
    }

    // Decode every file the audio tracks use (not only the audible ones, so unmuting is instant).
    function load(doc, pid) {
      const c = context();
      if (!c) return Promise.resolve(false);
      if (scope !== pid) { scope = pid; buffers.clear(); }
      const jobs = [];
      for (const [, clip] of clips(doc)) {
        if (buffers.has(clip.file)) continue;
        if ((clip.media_dur || 0) > MAX_DECODE_S) { buffers.set(clip.file, null); continue; }
        buffers.set(clip.file, "wait");
        const want = scope;
        jobs.push(
          fetch("/api/editor/" + encodeURIComponent(pid) + "/media/" + encodeURIComponent(clip.file))
            .then((r) => { if (!r.ok) throw new Error("media " + r.status); return r.arrayBuffer(); })
            .then((ab) => c.decodeAudioData(ab))
            .then((buf) => { if (want === scope) buffers.set(clip.file, buf); })
            .catch(() => { if (want === scope) buffers.set(clip.file, null); })
        );
      }
      return Promise.all(jobs).then(() => true);
    }

    // True when every clip on an audible track has its sound decoded.
    function ready(doc) {
      if (!ctx) return false;
      for (const [tr, c] of clips(doc)) {
        if (!audible(doc, tr)) continue;
        const b = buffers.get(c.file);
        if (!b || b === "wait") return false;
      }
      return true;
    }

    function strip(id) {
      let s = strips.get(id);
      if (!s) {
        const gain = ctx.createGain();
        const meter = ctx.createAnalyser();
        meter.fftSize = 1024;
        gain.connect(meter).connect(master); // post-fader meter, like Resolve's track meters
        s = { gain, meter, data: new Float32Array(meter.fftSize) };
        strips.set(id, s);
      }
      return s;
    }

    // Mute / solo / gain move live, with a 10 ms glide so a click never pops.
    function mixer(doc) {
      if (!ctx) return;
      for (const tr of doc.tracks) {
        if (!isAudio(tr)) continue;
        const g = audible(doc, tr) ? (tr.gain == null ? 1 : tr.gain) : 0;
        strip(tr.id).gain.gain.setTargetAtTime(g, ctx.currentTime, 0.01);
      }
    }

    function stop() {
      for (const s of sources) { try { s.stop(); } catch (e) { /* not started yet */ } s.disconnect(); }
      sources = [];
      running = false;
    }

    const rev = new Map(); // file -> reversed AudioBuffer, built on first use
    function reversed(file, buf) {
      if (rev.has(file)) return rev.get(file);
      if (!buf.getChannelData || !ctx.createBuffer) return null;
      const out = ctx.createBuffer(buf.numberOfChannels, buf.length, buf.sampleRate);
      for (let ch = 0; ch < buf.numberOfChannels; ch++) {
        const a = buf.getChannelData(ch), b = out.getChannelData(ch);
        for (let i = 0, n = a.length; i < n; i++) b[i] = a[n - 1 - i];
      }
      rev.set(file, out);
      return out;
    }

    // Schedule the whole mix from timeline second `play`, at `speed` (1, or 2 for a shuttle:
    // pitched up, the way Final Cut plays a 2x shuttle). Buffer offsets and lengths stay in
    // source seconds; only the wall-clock times divide by the speed.
    function start(doc, play, speed) {
      stop();
      if (!context()) return false;
      mixer(doc);
      rate = speed > 0 ? speed : 1;
      t0 = ctx.currentTime + LEAD;
      p0 = play;
      running = true;
      lastClock = ctx.currentTime;
      lastMove = performance.now();
      for (const [tr, c] of clips(doc)) {
        let buf = buffers.get(c.file);
        if (!buf || buf === "wait") continue;
        // A reversed clip plays a reversed copy of the decoded file (Web Audio can't run a
        // buffer backwards). Position x in the file is D - x in the copy, so the played offset
        // p (from the clip's out point) sits at D - src_out + p.
        let base = c.src_in;
        if (c.reverse) {
          const rb = reversed(c.file, buf);
          if (!rb) continue;
          base = buf.duration - c.src_out;
          buf = rb;
        }
        // Fades, the volume envelope and the schedule are in clip TIMELINE seconds (the render
        // fades after atempo); only the buffer offset and length are in source seconds.
        const span = c.src_out - c.src_in;
        const L = lenOf(c);
        if (c.at + L <= play) continue;
        const into = Math.max(0, play - c.at);
        const when = t0 + Math.max(0, c.at - play) / rate;
        const off = srcAt(c, into);
        const dur = span - off; // source seconds still to play
        const level = (c.volume == null ? 1 : c.volume) * (MIX[tr.role] || 1);
        const fi = Math.min(c.fade_in || 0, L), fo = Math.min(c.fade_out || 0, L);
        const env = (u) => level * Math.max(0, Math.min(1, fi > 0 ? u / fi : 1, fo > 0 ? (L - u) / fo : 1));
        const g = ctx.createGain();
        const at = (u) => when + (u - into) / rate; // clip-local timeline time -> context time
        g.gain.setValueAtTime(env(into), when);
        if (fi > 0 && into < fi) g.gain.linearRampToValueAtTime(env(fi), at(fi));
        if (fo > 0) {
          const foStart = L - fo;
          if (into < foStart) g.gain.setValueAtTime(env(foStart), at(foStart));
          g.gain.linearRampToValueAtTime(0, at(L));
        }
        // The volume envelope rides on a second gain after the fades: value at the start point,
        // then a linear ramp to each later key inside the clip; after the last key it holds.
        let tail = g;
        const keys = Array.isArray(c.gain_keys) && c.gain_keys.length ? c.gain_keys : null;
        if (keys) {
          const env = ctx.createGain();
          env.gain.setValueAtTime(envAt(keys, into), when);
          for (const k of keys) if (k.at > into && k.at <= L) env.gain.linearRampToValueAtTime(k.gain, at(k.at));
          g.connect(env);
          tail = env;
        }
        const src = ctx.createBufferSource();
        src.buffer = buf;
        // Retimed sound: the buffer plays at the clip's speed (pitched, like a tape -- the
        // render keeps pitch with atempo, the lengths match). A ramp's speed is exponential in
        // playback time inside each segment (s = s0 * e^(k w)), which is exactly what
        // exponentialRampToValueAtTime draws, so the preview stays on the render's frames.
        const s0 = speedAt(c, into);
        src.playbackRate.value = rate * s0;
        if (rampPts(c)) {
          src.playbackRate.setValueAtTime(rate * s0, when);
          const pts = rampPts(c), kt = keyTimes(c);
          for (let i = 0; i < kt.length; i++) {
            if (kt[i] > into && kt[i] < L) src.playbackRate.exponentialRampToValueAtTime(rate * pts[i][1], at(kt[i]));
          }
        }
        src.connect(g);
        tail.connect(strip(tr.id).gain);
        src.start(when, base + off, dur);
        sources.push(src);
      }
      return true;
    }

    // How long (ms) the audio clock has been standing still. An output that is still waking
    // (Bluetooth, a cold audio service) or has just gone away can report "running" while its
    // clock doesn't move; the editor waits for it rather than let picture and sound drift
    // apart, and gives up after a while. The clock steps every 128 samples (~3 ms), so a
    // reading per animation frame always sees it move when it is alive.
    function waiting() {
      if (!running || !ctx) return 0;
      const now = performance.now();
      if (ctx.currentTime !== lastClock) { lastClock = ctx.currentTime; lastMove = now; return 0; }
      return now - lastMove;
    }

    // The playhead, in timeline seconds, while the mix runs.
    function now() {
      if (!running || !ctx) return null;
      return p0 + rate * Math.max(0, ctx.currentTime - t0);
    }

    // Post-fader peak per audio track, in dBFS (-Infinity when silent).
    function levels() {
      const out = {};
      for (const [id, s] of strips) {
        s.meter.getFloatTimeDomainData(s.data);
        let pk = 0;
        for (let i = 0; i < s.data.length; i++) { const a = Math.abs(s.data[i]); if (a > pk) pk = a; }
        out[id] = pk > 0 ? 20 * Math.log10(pk) : -Infinity;
      }
      return out;
    }

    function state() {
      return { context: ctx ? ctx.state : "none", running, clock: ctx ? +ctx.currentTime.toFixed(3) : null, t0: +t0.toFixed(3), p0, decoded: [...buffers].map(([f, b]) => [f, b === "wait" ? "wait" : b ? +b.duration.toFixed(2) : null]) };
    }

    return { unlock, load, ready, start, stop, now, waiting, mixer, levels, state,
      get running() { return running; }, get context() { return ctx; } };
  }

  window.HSMix = { create, MIX, envAt, srcAt, srcTime, tlAt, speedAt, keyTimes, lenOf };
})();
