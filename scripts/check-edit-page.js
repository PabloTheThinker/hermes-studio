// Drives the Edit page end to end in Chromium (manual check, not run in CI):
//   node scripts/check-edit-page.js [out-dir]
// Starts `hermes-studio studio` with a throwaway HOME and a fixed ui token (standing in for the
// desktop app's preload), makes a project, imports a generated video through Browse…, adds it to the timeline,
// lets an agent (the stdio MCP proxy) add a title in Propose mode, previews it on its card, applies it from the sidebar,
// plays, trims, crossfades, drives markers and keys, and saves slips and rolls, snaps a marker to the playhead, duplicates and copy-pastes, checks the music track's preview plan, multi-selects, finds and cuts a phrase in the transcript, renders at half size without captions, and saves screenshots 1-10 to out-dir. Needs ffmpeg, Node and Playwright with Chromium.
let chromium;
try { ({ chromium } = require("playwright")); } catch { ({ chromium } = require(require("child_process").execSync("npm root -g").toString().trim() + "/playwright")); }
const { spawn, execFileSync } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");
const REPO = path.resolve(__dirname, "..");
const OUT = path.resolve(process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), "hs-edit-"))), HOME = path.join(OUT, "home");
const TOKEN = "c0ffee".repeat(10) + "abcd";
const PORT = 8771;
fs.rmSync(HOME, { recursive: true, force: true }); fs.mkdirSync(path.join(HOME, "Videos"), { recursive: true });
const vid = path.join(HOME, "Videos", "talk.mp4");
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=12", "-f", "lavfi", "-i", "sine=frequency=330:duration=12", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", vid]);
const env = { ...process.env, HOME, HERMES_STUDIO_UI_TOKEN: TOKEN, PYTHONUNBUFFERED: "1" };
const srv = spawn(path.join(REPO, ".venv/bin/hermes-studio"), ["studio", "--port", String(PORT)], { env, stdio: ["ignore", "pipe", "pipe"] });
let log = ""; srv.stdout.on("data", (b) => (log += b)); srv.stderr.on("data", (b) => (log += b));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let PAGE = null;
(async () => {
  for (let i = 0; i < 60 && !log.includes("Hermes Studio"); i++) await sleep(250);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  PAGE = page;
  const errs = []; page.on("pageerror", (e) => errs.push("pageerror: " + e.message)); page.on("console", (m) => { if (m.type() === "error") errs.push("console: " + m.text()); });
  await page.addInitScript((t) => {
    window.studio = { uiToken: async () => t, retry: async () => {}, pickFile: async () => window.__pick, pathOf: () => null, showRender: async (pid, f) => { window.__shown = pid + "/" + f; return true; } };
    window.__toasts = []; // every toast, for the failure report
    new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => { if (n.classList && n.classList.contains("toast")) window.__toasts.push(n.textContent); }))).observe(document, { childList: true, subtree: true });
  }, TOKEN);
  await page.addInitScript((v) => { window.__pick = v; }, vid); // what the desktop app's file dialog would return
  const base = `http://127.0.0.1:${PORT}/`;
  await page.goto(base + "#/edit"); await page.waitForSelector("#ed-new");
  await page.screenshot({ path: path.join(OUT, "1-home.png") });
  await page.click("#ed-new"); await page.waitForSelector("#ed-path");
  await page.uncheck("#ed-words");
  await page.click("#ed-browse"); // the desktop app's Browse… (its dialog stubbed to pick the test video)
  if ((await page.inputValue("#ed-path")) !== vid) errs.push("browse: the path field wasn't filled");
  await page.click("#ed-import");
  await page.waitForFunction(() => /ready/.test(document.querySelector("#ed-pane").textContent), null, { timeout: 60000 });
  // words for m1, as the Whisper stage would write them (media ticks), so the preview can caption them
  const pidNow = (await page.evaluate(() => location.hash)).split("/").pop();
  const S1 = 705600000, wd = path.join(HOME, ".hermes/clips/projects", pidNow, "cache/words");
  fs.mkdirSync(wd, { recursive: true });
  fs.writeFileSync(path.join(wd, "m1.json"), JSON.stringify({ words: [["hello", 0, 0.4], ["world", 0.45, 0.9], ["this", 0.95, 1.3], ["is", 1.35, 1.6], ["hermes.", 1.65, 2.2]].map(([w, a, b]) => ({ w, in: Math.round(a * S1), out: Math.round(b * S1) })) }));
  await page.click("[data-add]");
  await page.waitForSelector(".it.clip");
  // the preview captions the words in the render's pop style: the line, and the word being said in pop's highlight
  await page.click("#ed-ruler", { position: { x: 40 + 30, y: 10 } });
  await page.waitForFunction(() => /hello world this/.test(document.getElementById("ed-cap").textContent), null, { timeout: 15000 })
    .catch(() => errs.push("captions: the preview shows " + JSON.stringify("?")));
  const capHi = await page.evaluate(() => [...document.querySelectorAll("#ed-cap span")].map((x) => [x.textContent, getComputedStyle(x).color]));
  if (!capHi.length || capHi[1][1] !== "rgb(255, 229, 0)") errs.push("captions: highlight " + JSON.stringify(capHi));
  await page.click('[data-tab="scenes"]');
  await page.waitForFunction(() => /shot change/i.test(document.getElementById("ed-pane").textContent), null, { timeout: 15000 });
  await page.click('[data-tab="media"]');
  await sleep(800);
  await page.screenshot({ path: path.join(OUT, "2-clip.png") });
  // agent edit through the stdio MCP proxy (attaches to the running engine)
  const pid = (await page.evaluate(() => location.hash)).split("/").pop();
  const mcp = spawn(path.join(REPO, ".venv/bin/hermes-studio"), ["mcp"], { env: { ...process.env, HOME }, stdio: ["pipe", "pipe", "pipe"] });
  let mout = ""; mcp.stdout.on("data", (b) => (mout += b));
  const send = (o) => mcp.stdin.write(JSON.stringify(o) + "\n");
  send({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "e2e", version: "1" } } });
  const hd = JSON.parse(execFileSync("curl", ["-s", "-H", "Authorization: Bearer " + TOKEN, "-H", `Host: 127.0.0.1:${PORT}`, `${base}api/projects/${pid}/hash`]).toString());
  send({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "timeline_apply", arguments: { project_id: pid, base_version: hd.version, client_op_id: "agent-1", summary: "Add a title", ops: [{ op: "add_text", text: "Hermes", style: "pop", at_s: 1, dur_s: 3 }] } } });
  await page.waitForSelector(".card.wait", { timeout: 15000 });
  await page.click("[data-preview]");
  await page.waitForFunction(() => /changed/.test((document.querySelector(".card .pv") || {}).textContent || ""), null, { timeout: 15000 });
  const pvText = await page.textContent(".card .pv");
  if (!/"Hermes" \(pop\)/.test(pvText)) errs.push("preview: the waiting card's outline doesn't show the title: " + pvText.slice(0, 200));
  await page.screenshot({ path: path.join(OUT, "3-waiting.png") });
  await page.click("[data-apply]");
  await page.waitForSelector(".it.text", { timeout: 15000 });
  await page.click("#ed-ruler", { position: { x: 40 + 2 * 60, y: 10 } });
  await sleep(1500);
  await page.screenshot({ path: path.join(OUT, "4-applied.png") });
  await page.click("#ed-play"); await sleep(2000); await page.click("#ed-play");
  const t = await page.textContent("#ed-tc");
  // J/K/L: L L plays at 2x (the playhead runs about twice as fast), K stops, J at rest steps back a second
  await page.click("#ed-tc"); await page.keyboard.press("Home");
  await page.keyboard.press("l"); await page.keyboard.press("l");
  const lbl = await page.textContent("#ed-play"); await sleep(1500); await page.keyboard.press("k");
  const fast = await page.textContent("#ed-tc");
  const fastS = +fast.split(":")[1];
  if (lbl !== "Pause · 2×" || !(fastS > 2.2 && fastS < 4)) errs.push(`shuttle: ${lbl}, ran to ${fast} in 1.5 s at 2x`);
  await page.keyboard.press("j");
  const back = +(await page.textContent("#ed-tc")).split(":")[1];
  if (Math.abs(fastS - back - 1) > 0.02) errs.push(`shuttle: J went from ${fastS} to ${back}`);
  await page.click("[data-frames]");
  await page.waitForSelector(".ba img", { timeout: 15000 });
  await page.screenshot({ path: path.join(OUT, "5-played.png") });
  // trim the clip's right edge by 2 s, then edit the title's text
  page.on("dialog", (d) => d.accept(d.type() === "prompt" ? "Edited title" : undefined));
  const ver = async () => +(await page.textContent("#ed-ver")).slice(1);
  const v0 = await ver();
  const hb = await page.locator(".it.clip .h.r").boundingBox();
  await page.mouse.move(hb.x + 3, hb.y + 10); await page.mouse.down();
  await page.mouse.move(hb.x - 117, hb.y + 10, { steps: 6 }); await page.mouse.up();
  await page.waitForFunction((v) => +document.getElementById("ed-ver").textContent.slice(1) > v, v0, { timeout: 15000 });
  const clipW = await page.evaluate(() => parseFloat(document.querySelector(".it.clip").style.width));
  await page.dblclick(".it.text .lbl");
  await page.waitForFunction(() => /Edited title/.test(document.querySelector(".it.text").textContent), null, { timeout: 15000 });
  await page.screenshot({ path: path.join(OUT, "6-trimmed.png") });
  if (Math.abs(clipW - 600) > 2) errs.push("trim: clip is " + clipW + "px, want 600 (10 s at 60 px/s)");
  // a second clip, a crossfade into it, then 2x speed on the first
  await page.click('[data-tab="media"]'); await page.click("[data-add]");
  await page.waitForFunction(() => document.querySelectorAll(".it.clip").length === 2, null, { timeout: 15000 });
  await page.click(".it.clip >> nth=0", { position: { x: 200, y: 8 } });
  await page.click("#it-xfade");
  await page.waitForSelector(".it.transition", { timeout: 15000 });
  await sleep(500);
  await page.click(".it.clip >> nth=1", { position: { x: 200, y: 8 } }); // the second clip: 2x makes it 5 s
  await page.selectOption("#it-speed", "2/1"); await page.click("#it-apply");
  await page.waitForFunction(() => parseFloat(document.querySelectorAll(".it.clip")[1].style.width) < 400, null, { timeout: 15000 });
  await page.screenshot({ path: path.join(OUT, "7-inspector.png") });
  // keys and markers: Home, one second right, M, nudge it a frame, rename it, drag it, delete it, undo
  await page.click("#ed-tc"); // focus off any input
  await page.keyboard.press("Home"); await page.keyboard.press("Shift+ArrowRight"); await page.keyboard.press("ArrowRight");
  const tcStep = await page.textContent("#ed-tc");
  if (tcStep !== "0:01.03") errs.push("keys: Home, Shift+Right, Right went to " + tcStep + ", want 0:01.03");
  await page.keyboard.press("]");
  const tcJump = await page.textContent("#ed-tc");
  await page.keyboard.press("m");
  await page.waitForSelector(".mk", { timeout: 15000 });
  const mk0 = await page.evaluate(() => parseFloat(document.querySelector(".mk").style.left));
  await page.click(".mk", { position: { x: 4, y: 8 } }); // select (a click also seeks to it)
  await page.waitForSelector("#mk-label");
  const mkMoved = (from) => page.waitForFunction((x) => parseFloat(document.querySelector(".mk").style.left) !== x, from, { timeout: 15000 }).then(() => page.evaluate(() => parseFloat(document.querySelector(".mk").style.left)));
  await page.keyboard.press("Alt+ArrowRight");
  const mk1 = await mkMoved(mk0);
  if (Math.abs(mk1 - mk0 - 2) > 0.1) errs.push(`nudge: marker moved ${mk1 - mk0}px, want 2 (one frame at 60 px/s)`);
  // five quick Alt+Right presses: one entry, five frames (10 px)
  const v5 = await ver();
  for (let i = 0; i < 5; i++) await page.keyboard.press("Alt+ArrowRight");
  const mk5 = await mkMoved(mk1).then(() => page.waitForFunction((x) => Math.abs(parseFloat(document.querySelector(".mk").style.left) - x - 10) < 0.1, mk1, { timeout: 15000 }).then(() => true, () => false));
  await page.waitForFunction((v) => +document.getElementById("ed-ver").textContent.slice(1) > v, v5, { timeout: 15000 });
  await sleep(800);
  if (!mk5 || (await ver()) !== v5 + 1) errs.push(`held nudge: ${await ver() - v5} entries (want 1), moved to 10 px: ${mk5}`);
  await page.keyboard.press("Alt+ArrowLeft"); for (let i = 0; i < 4; i++) await page.keyboard.press("Alt+ArrowLeft"); // back to mk1
  await page.waitForFunction((x) => Math.abs(parseFloat(document.querySelector(".mk").style.left) - x) < 0.1, mk1, { timeout: 15000 });
  await sleep(800);
  await page.dblclick(".mk", { position: { x: 4, y: 8 } });
  await page.waitForFunction(() => /Edited title/.test(document.querySelector(".mk").textContent), null, { timeout: 15000 });
  const mb = await page.locator(".mk").boundingBox();
  await page.mouse.move(mb.x + 4, mb.y + 8); await page.mouse.down(); await page.mouse.move(mb.x + 124, mb.y + 8, { steps: 6 }); await page.mouse.up();
  await page.waitForFunction(() => /0:06\.0/.test(document.querySelector(".mk").title), null, { timeout: 15000 }); // the redraw from the engine, not the dragged node
  const mk2 = await page.evaluate(() => parseFloat(document.querySelector(".mk").style.left));
  if (Math.abs(mk2 - mk1 - 120) > 2) errs.push(`drag: marker moved ${mk2 - mk1}px, want 120`);
  // Fit: the whole edit fits the view, then back to 60 px/s for the steps below
  await page.click("#ed-fit");
  const fitOk = await page.evaluate(() => { const sc = document.getElementById("ed-scroll"); const right = Math.max(...[...document.querySelectorAll(".it")].map((n) => parseFloat(n.style.left) + parseFloat(n.style.width))); return right <= sc.clientWidth && right > sc.clientWidth * 0.8; });
  if (!fitOk) errs.push("fit: the edit's end isn't in the last fifth of the view");
  await page.evaluate(() => { const z = document.getElementById("ed-zoom"); z.value = "60"; z.dispatchEvent(new Event("input")); });
  await page.click("#ed-keys"); await page.waitForSelector(".keys");
  await page.screenshot({ path: path.join(OUT, "8-markers.png") });
  await page.click(".mk", { position: { x: 4, y: 8 } }); await page.keyboard.press("Delete");
  await page.waitForFunction(() => !document.querySelector(".mk"), null, { timeout: 15000 });
  await page.keyboard.press("Control+z");
  await page.waitForSelector(".mk", { timeout: 15000 });
  // roll the cut between the two clips 1 s later (through their crossfade), then slip the first clip a frame with "."
  const widths = () => page.evaluate(() => [...document.querySelectorAll(".it.clip")].map((n) => parseFloat(n.style.width)));
  const w0s = await widths();
  await page.click(".it.clip >> nth=0", { position: { x: 200, y: 8 } });
  await page.click('[data-step="roll"][data-fr="30"]');
  await page.waitForFunction((w) => parseFloat(document.querySelector(".it.clip").style.width) !== w, w0s[0], { timeout: 15000 });
  const w1s = await widths();
  if (Math.abs(w1s[0] - w0s[0] - 60) > 1 || Math.abs(w1s[1] - w0s[1] + 60) > 1) errs.push(`roll: widths ${w0s} -> ${w1s}, want +60 / -60`);
  const src0 = await page.textContent("#ed-pane .meta.mono");
  await page.click("#ed-tc"); await page.keyboard.press("Period");
  await page.waitForFunction((t) => document.querySelector("#ed-pane .meta.mono").textContent !== t, src0, { timeout: 15000 });
  const src1 = await page.textContent("#ed-pane .meta.mono");
  if (!/source 0:00\.03/.test(src1)) errs.push("slip: source is " + src1 + ", want it to start at 0:00.03");
  await page.screenshot({ path: path.join(OUT, "9-slip-roll.png") });
  // snapping: park the playhead at 3 s, drag the marker to 5 px right of it: it lands on 3 s exactly
  const rb = await page.locator("#ed-ruler").boundingBox();
  await page.mouse.click(rb.x + 40 + 3 * 60, rb.y + 10);
  if ((await page.textContent("#ed-tc")) !== "0:03.00") errs.push("snap: the ruler click went to " + (await page.textContent("#ed-tc")));
  const sb = await page.locator(".mk").boundingBox();
  await page.mouse.move(sb.x + 2, sb.y + 8); await page.mouse.down();
  await page.mouse.move(rb.x + 40 + 3 * 60 + 5, sb.y + 8, { steps: 8 });
  const snapShown = await page.evaluate(() => getComputedStyle(document.getElementById("ed-snap")).display);
  await page.mouse.up();
  await page.waitForFunction(() => /0:03\.00 ·/.test(document.querySelector(".mk").title), null, { timeout: 15000 }).catch(() => errs.push("snap: marker is at " + "?"));
  if (snapShown !== "block") errs.push("snap: no snap line while dragging");
  // duplicate the second clip with Ctrl+D (it lands right after itself), then copy the title and paste it at 0
  const nClips = await page.evaluate(() => document.querySelectorAll(".it.clip").length);
  await page.click(".it.clip >> nth=1", { position: { x: 20, y: 8 } });
  await page.keyboard.press("Control+d");
  await page.waitForFunction((n) => document.querySelectorAll(".it.clip").length === n + 1, nClips, { timeout: 15000 });
  await page.click(".it.text", { position: { x: 20, y: 8 } }); await page.keyboard.press("Control+c");
  await page.keyboard.press("Home"); await page.keyboard.press("Control+v");
  await page.waitForFunction(() => document.querySelectorAll(".it.text").length === 2, null, { timeout: 15000 });
  // the music track plays in the preview: add m1 as music; at 1 s the audio plan has it at 1 s of source, 25%
  // (this Chromium has no AAC, so the plan is checked, not the sound)
  await page.click('[data-tab="media"]'); await page.click("[data-music]");
  await page.waitForFunction(() => window.HSEdit._audioPlan(705600000).length > 0, null, { timeout: 15000 }).catch(() => {});
  const aud = await page.evaluate(() => window.HSEdit._audioPlan(705600000));
  const mus = aud.find((a) => a.track !== "V1" && Math.abs(a.at - 1) < 1e-6);
  if (!mus || Math.abs(mus.volume - 0.25) > 1e-9) errs.push("preview audio: " + JSON.stringify(aud));
  // multi-select: Ctrl-click two clips, Alt+Right moves both a frame in one entry, Delete removes both in one, undo brings them back
  await page.waitForSelector('[data-trk="A2"] .it.clip', { timeout: 15000 }); // the music clip is drawn
  const nC = await page.evaluate(() => document.querySelectorAll(".it.clip").length);
  await page.click(".it.clip >> nth=0", { position: { x: 30, y: 8 } });
  await page.click(".it.clip >> nth=2", { position: { x: 30, y: 8 }, modifiers: ["Control"] });
  if ((await page.evaluate(() => document.querySelectorAll(".it.sel").length)) !== 2) errs.push("multi-select: Ctrl-click didn't add the second clip");
  let vs = await ver(); await page.keyboard.press("Delete");
  await page.waitForFunction((n) => document.querySelectorAll(".it.clip").length === n - 2, nC, { timeout: 15000 });
  if ((await ver()) !== vs + 1) errs.push(`multi-delete: ${await ver() - vs} entries, want 1`);
  await page.keyboard.press("Control+z");
  await page.waitForFunction((n) => document.querySelectorAll(".it.clip").length === n, nC, { timeout: 15000 });
  // the two text items, Ctrl-clicked, nudge together: both 2 px right in one entry
  await page.evaluate(() => (document.getElementById("ed-scroll").scrollLeft = 0));
  const tx0 = await page.evaluate(() => [...document.querySelectorAll(".it.text")].map((n) => parseFloat(n.style.left)));
  const tb = await Promise.all([0, 1].map((i) => page.locator(".it.text").nth(i).boundingBox())); // they overlap: click where each shows
  const [tl, tr] = tb[0].x <= tb[1].x ? [0, 1] : [1, 0];
  await page.mouse.click(tb[tl].x + 6, tb[tl].y + 8);
  await page.keyboard.down("Control"); await page.mouse.click(tb[tr].x + tb[tr].width - 6, tb[tr].y + 8); await page.keyboard.up("Control");
  vs = await ver(); await page.keyboard.press("Alt+ArrowRight");
  await page.waitForFunction((v) => +document.getElementById("ed-ver").textContent.slice(1) > v, vs, { timeout: 15000 });
  await page.waitForFunction((t) => [...document.querySelectorAll(".it.text")].every((n, i) => Math.abs(parseFloat(n.style.left) - t[i] - 2) < 0.1), tx0, { timeout: 15000 })
    .catch(() => errs.push("group nudge: the text items didn't both move 2 px"));
  if ((await ver()) !== vs + 1) errs.push(`group nudge: ${await ver() - vs} entries, want 1`);
  await page.keyboard.press("Control+a");
  const nAll = await page.evaluate(() => [document.querySelectorAll(".it.sel").length, document.querySelectorAll(".it:not(.transition)").length]);
  if (nAll[0] !== nAll[1]) errs.push("select all: " + nAll);
  await page.keyboard.press("Escape");
  // find "world this" in the transcript: one match, Enter seeks to it, Cut all removes it as one entry
  await page.click('[data-tab="transcript"]'); await page.fill("#ed-find", "World, this");
  const nFind = await page.textContent("#ed-find-n");
  await page.press("#ed-find", "Enter");
  const fv = await ver(); await page.click("#ed-cutfind");
  await page.waitForFunction((v) => +document.getElementById("ed-ver").textContent.slice(1) > v, fv, { timeout: 15000 });
  // (the music clip here is the same talk, so its words stay: the phrase as said on V1 is what goes)
  await page.waitForFunction(() => !/world this/.test(document.querySelector(".words").textContent), null, { timeout: 15000 })
    .catch(async () => errs.push("find: the phrase is still in the transcript: " + (await page.textContent(".words"))));
  if (nFind !== "1" || (await ver()) !== fv + 1) errs.push(`find: ${nFind} matches (want 1), ${await ver() - fv} entries (want 1)`);
  // render at half size without captions; the download link names the size
  await page.selectOption("#ed-cstyle", ""); await page.selectOption("#ed-rsize", "2");
  await page.click("#ed-render");
  await page.waitForSelector("#ed-dl", { timeout: 240000 });
  const rendered = await page.textContent("#ed-dl");
  await page.click("#ed-show");
  const shown = await page.waitForFunction(() => window.__shown, null, { timeout: 15000 }).then((h) => h.jsonValue(), () => null);
  if (!shown || !/^p-[0-9a-f]+\/exports\/[^/]+-540x960\.mp4$/.test(shown)) errs.push("show in folder: asked for " + shown);
  if (!/540x960$/.test(rendered)) errs.push("render: " + rendered + ", want a 540x960 render without captions");
  await page.screenshot({ path: path.join(OUT, "10-rendered.png") });
  // back on the projects list: this project, newest first, says when it was edited
  const vis = await page.evaluate(() => ({ video: getComputedStyle(document.getElementById("ed-video")).visibility, src: document.getElementById("ed-video").currentSrc, rs: document.getElementById("ed-video").readyState }));
  await page.goto(base + "#/edit"); await page.waitForSelector(".plist .row");
  const row = await page.textContent(".plist .row");
  if (!/edited just now/.test(row)) errs.push("projects list: " + row);
  const bad = errs.filter((e) => !/fonts\.g|ERR_CERT|ERR_NAME|ERR_INTERNET/.test(e));
  console.log(JSON.stringify({ out: OUT, captions: capHi, rendered, played_to: t, jumped_to: tcJump, music: aud, video: vis, agent: mout.split("\n").filter(Boolean).map((l) => l.slice(0, 160)), errors: bad }, null, 1));
  if (bad.length || t === "0:02.00") process.exitCode = 1;
  mcp.kill(); await browser.close(); srv.kill();
})().catch(async (e) => {
  console.error("FAIL", e.message.split("\n")[0], (e.stack || "").split("\n").find((l) => l.includes("check-edit-page")) || "", "\n", log.slice(-1500));
  if (PAGE) { await PAGE.screenshot({ path: path.join(OUT, "fail.png") }).catch(() => {}); console.error("toasts:", await PAGE.evaluate(() => window.__toasts).catch(() => [])); }
  srv.kill(); process.exit(1);
});
