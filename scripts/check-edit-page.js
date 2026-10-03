// Drives the Edit page end to end in Chromium (manual check, not run in CI):
//   node scripts/check-edit-page.js [out-dir]
// Starts `hermes-studio studio` with a throwaway HOME and a fixed ui token (standing in for the
// desktop app's preload), makes a project, imports a generated video, adds it to the timeline,
// lets an agent (the stdio MCP proxy) add a title in Propose mode, applies it from the sidebar,
// plays, and saves screenshots 1-5 to out-dir. Needs ffmpeg, Node and Playwright with Chromium.
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
(async () => {
  for (let i = 0; i < 60 && !log.includes("Hermes Studio"); i++) await sleep(250);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = []; page.on("pageerror", (e) => errs.push("pageerror: " + e.message)); page.on("console", (m) => { if (m.type() === "error") errs.push("console: " + m.text()); });
  await page.addInitScript((t) => { window.studio = { uiToken: async () => t, retry: async () => {} }; }, TOKEN);
  const base = `http://127.0.0.1:${PORT}/`;
  await page.goto(base + "#/edit"); await page.waitForSelector("#ed-new");
  await page.screenshot({ path: path.join(OUT, "1-home.png") });
  await page.click("#ed-new"); await page.waitForSelector("#ed-path");
  await page.uncheck("#ed-words");
  await page.fill("#ed-path", vid); await page.click("#ed-import");
  await page.waitForFunction(() => /ready/.test(document.querySelector("#ed-pane").textContent), null, { timeout: 60000 });
  await page.click("[data-add]");
  await page.waitForSelector(".it.clip");
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
  await page.screenshot({ path: path.join(OUT, "3-waiting.png") });
  await page.click("[data-apply]");
  await page.waitForSelector(".it.text", { timeout: 15000 });
  await page.click("#ed-ruler", { position: { x: 40 + 2 * 60, y: 10 } });
  await sleep(1500);
  await page.screenshot({ path: path.join(OUT, "4-applied.png") });
  await page.click("#ed-play"); await sleep(2000); await page.click("#ed-play");
  const t = await page.textContent("#ed-tc");
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
  const vis = await page.evaluate(() => ({ video: getComputedStyle(document.getElementById("ed-video")).visibility, src: document.getElementById("ed-video").currentSrc, rs: document.getElementById("ed-video").readyState }));
  const bad = errs.filter((e) => !/fonts\.g|ERR_CERT|ERR_NAME|ERR_INTERNET/.test(e));
  console.log(JSON.stringify({ out: OUT, played_to: t, video: vis, agent: mout.split("\n").filter(Boolean).map((l) => l.slice(0, 160)), errors: bad }, null, 1));
  if (bad.length || t === "0:02.00") process.exitCode = 1;
  mcp.kill(); await browser.close(); srv.kill();
})().catch(async (e) => { console.error("FAIL", e.message, "\n", log.slice(-1500)); srv.kill(); process.exit(1); });
